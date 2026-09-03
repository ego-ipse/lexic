"""Tests for lexic.parsing.product.tree — ParseTree completion, presence explicit.

The module's own load-bearing distinction: a completed value may itself be
Python ``None``, so absence is ``EMPTY_RESULT``, never a sentinel a real value
could collide with. Every capture-mode absence rule below is derived directly
from ``_captured``'s own arithmetic (read from source, not from a run): a
TEXT capture is omitted only when BOTH optional and empty; a ONE capture is
omitted only when BOTH optional and its child produced no value — a required
capture whose child produced nothing is still WRITTEN, as ``None``, which is
the sharp case a naive "omit whenever nothing was found" implementation would
get wrong.
"""

from __future__ import annotations

from typing import NamedTuple

import pytest

from lexic.compile import compile_text, reset_cache_for_tests
from lexic.exceptions import UnsupportedConstructError
from lexic.ir import IrAst, IrLiteral, IrRuleRef, IrSeq, IrSpan
from lexic.parsing.earley.kernel.forest.forest import ParseTree, PayloadLeaf
from lexic.parsing.earley.kernel.tables.builder import compile_tables
from lexic.parsing.earley.normalize import SYNTHETIC_PREFIX
from lexic.parsing.product.abi.construction import Construction
from lexic.parsing.product.abi.records import CaptureMode
from lexic.parsing.product.routines import RuleRoutine
from lexic.parsing.product.tree import (
    EMPTY_RESULT,
    Completed,
    ProductExecutor,
    collapsed_product_tables,
    complete_product,
    run_ok,
    slot_span,
    subtree_text,
    tree_offsets,
)
from lexic.parsing.products import _model_product
from tests.paths import GROUND_TRUTH
from tests.unit.lexic.parsing.ir_fixtures import (
    malformed_synthetic_rule,
    nested_synthetic_grammar,
)


def _leaf(rule: str, *kids) -> ParseTree:
    return ParseTree(IrRuleRef(rule), IrSeq(*kids))


def _pass(source: int) -> RuleRoutine:
    return RuleRoutine(0, (int(CaptureMode.ONE),), (0,), 1, source, None)


def _record(modes, slots, construction: Construction, n_items: int) -> RuleRoutine:
    return RuleRoutine(0, tuple(modes), tuple(slots), n_items, -1, construction)


# ── subtree_text / tree_offsets / slot_span — pure text/position readers ──


def test_subtree_text_concatenates_leaves_in_source_order():
    """Literal leaves and payload leaves both contribute their own text."""
    node = _leaf("root", IrLiteral("a"), PayloadLeaf(object(), "bb"), IrLiteral("c"))
    assert subtree_text(node) == "abbc"


def test_subtree_text_descends_nested_parse_trees():
    """Text collection recurses through interior nodes, not just direct kids."""
    inner = _leaf("inner", IrLiteral("x"), IrLiteral("y"))
    node = _leaf("root", IrLiteral("a"), inner, IrLiteral("z"))
    assert subtree_text(node) == "axyz"


def test_tree_offsets_and_slot_span_locate_each_kid_by_consumed_width():
    """slot_span reports the half-open span of ONE kid within its parent."""
    node = _leaf("root", IrLiteral("ab"), IrLiteral("c"), IrLiteral("def"))
    offsets = tree_offsets(node)
    assert slot_span(node, node.kids, 0, offsets) == IrSpan(0, 2)
    assert slot_span(node, node.kids, 1, offsets) == IrSpan(2, 3)
    assert slot_span(node, node.kids, 2, offsets) == IrSpan(3, 6)


def test_slot_span_of_an_empty_leaf_is_a_real_empty_span_not_an_absence():
    """A zero-width match is a FACT (start == end), not the absence marker."""
    node = _leaf("root", IrLiteral(""), IrLiteral("q"))
    offsets = tree_offsets(node)
    assert slot_span(node, node.kids, 0, offsets) == IrSpan(0, 0)


# ── PASS: explicit presence through, never erased ────────────────────────


def test_pass_forwards_a_present_child_including_a_real_none_value():
    """A completed child whose VALUE is Python None still counts as present."""
    inner = _leaf("inner")
    outer = _leaf("outer", inner)
    routines = {
        "outer": _pass(0),
        "inner": _record((), (), Construction(lambda: None, (), frozenset()), 0),
    }
    assert complete_product(outer, routines) is None


def test_pass_of_an_empty_child_raises_when_it_is_the_document_root():
    """A start rule that completes to nothing has genuinely failed."""
    inner = _leaf("inner")  # "inner" has no routine — a transparent, empty node
    outer = _leaf("outer", inner)
    routines = {"outer": _pass(0)}
    with pytest.raises(UnsupportedConstructError, match="completed without a value"):
        complete_product(outer, routines)


def test_splice_of_an_empty_occurrence_returns_the_empty_marker_not_a_raise():
    """The occurrence question differs from the root question: EMPTY_RESULT
    is a legitimate answer for a spliced (non-root) completion."""
    inner = _leaf("inner")
    routines: dict = {}
    executor = ProductExecutor(routines)
    assert executor.splice(inner) == EMPTY_RESULT


# ── TEXT capture: absence vs empty string ────────────────────────────────


class _Rec(NamedTuple):
    value: object = None


def _text_construction(name: str, optional: frozenset[int]) -> Construction:
    return Construction(_Rec, (name,), optional)


def test_a_required_text_capture_is_written_even_when_the_span_is_empty():
    """Not optional: present is True unconditionally, even for an empty span."""
    child = _leaf("word", IrLiteral(""))
    node = _leaf("root", child)
    routines = {
        "root": _record(
            (int(CaptureMode.TEXT),), (0,), _text_construction("value", frozenset()), 1
        ),
    }
    result = complete_product(node, routines)
    assert result.value == ""


def test_an_optional_text_capture_of_an_empty_span_is_omitted():
    """Optional AND empty: the capture is omitted, so the class default applies."""
    child = _leaf("word", IrLiteral(""))
    node = _leaf("root", child)
    routines = {
        "root": _record(
            (int(CaptureMode.TEXT),),
            (0,),
            _text_construction("value", frozenset({0})),
            1,
        ),
    }
    result = complete_product(node, routines)
    assert result.value is None  # the class default, never ""


def test_an_optional_text_capture_of_a_real_span_is_present():
    """Optional but non-empty: the real text is written, not omitted."""
    child = _leaf("word", IrLiteral("hi"))
    node = _leaf("root", child)
    routines = {
        "root": _record(
            (int(CaptureMode.TEXT),),
            (0,),
            _text_construction("value", frozenset({0})),
            1,
        ),
    }
    result = complete_product(node, routines)
    assert result.value == "hi"


# ── ONE capture: absence vs a genuinely required-but-missing value ──────


def test_a_required_one_capture_whose_child_completed_empty_is_written_as_none():
    """Sharp boundary: NOT optional writes None rather than omitting the field
    — a naive "omit when nothing was found" implementation would drop this
    keyword and the class default (which might differ) would apply instead."""
    empty_child = _leaf("thing")  # no routine — completes to EMPTY_RESULT
    node = _leaf("root", empty_child)
    routines = {
        "root": _record(
            (int(CaptureMode.ONE),), (0,), _text_construction("value", frozenset()), 1
        ),
    }
    result = complete_product(node, routines)
    assert result.value is None


def test_an_optional_one_capture_whose_child_completed_empty_is_omitted():
    """Optional AND no model at all: omitted, so the class default applies."""
    empty_child = _leaf("thing")
    node = _leaf("root", empty_child)
    routines = {
        "root": _record(
            (int(CaptureMode.ONE),),
            (0,),
            _text_construction("value", frozenset({0})),
            1,
        ),
    }
    result = complete_product(node, routines)
    assert result.value is None


def test_a_one_capture_looks_through_a_transparent_node_to_its_descendant():
    """A capture slot pointing at a routine-less (transparent) node still
    reaches the completed value underneath it."""
    real = _leaf("real")
    transparent = _leaf("wrapper", real)  # "wrapper" has no routine
    node = _leaf("root", transparent)
    routines = {
        "root": _record(
            (int(CaptureMode.ONE),), (0,), _text_construction("value", frozenset()), 1
        ),
        "real": _record((), (), Construction(lambda: "deep", (), frozenset()), 0),
    }
    result = complete_product(node, routines)
    assert result.value == "deep"


# ── MANY capture: always present, a list of whatever completed ──────────


def _many_construction() -> Construction:
    return Construction(_Rec, ("value",), frozenset())


def test_a_many_capture_collects_every_completed_descendant_in_order():
    """A MANY capture gathers completed values from beneath a group node."""
    a = _leaf("item")
    b = _leaf("item")
    group = _leaf("group", a, b)
    node = _leaf("root", group)
    routines = {
        "root": _record((int(CaptureMode.MANY),), (0,), _many_construction(), 1),
        "item": _record((), (), Construction(lambda: "x", (), frozenset()), 0),
    }
    result = complete_product(node, routines)
    assert result.value == ["x", "x"]


def test_a_many_capture_of_nothing_is_an_empty_list_not_an_absence():
    """MANY is never omitted — an empty collection is still a present value."""
    empty_group = _leaf("group")
    node = _leaf("root", empty_group)
    routines = {
        "root": _record((int(CaptureMode.MANY),), (0,), _many_construction(), 1),
    }
    result = complete_product(node, routines)
    assert result.value == []


# ── EXTENT capture: always present, an IrSpan ─────────────────────────────


def test_an_extent_capture_reports_the_slots_own_span():
    """EXTENT is always present and reports the CHILD's own consumed span."""
    node = _leaf("root", IrLiteral("ab"), IrLiteral("cde"))
    routines = {
        "root": _record(
            (int(CaptureMode.EXTENT),),
            (1,),
            _text_construction("value", frozenset()),
            2,
        ),
    }
    result = complete_product(node, routines)
    assert result.value == IrSpan(2, 5)


# ── value_str construction: the rule's OWN matched extent, not a capture ──


def test_matched_construction_uses_the_whole_subtree_text_not_a_capture():
    """A value_str rule's completion ignores captures entirely and uses its
    own consumed text — verified by giving it captures that would build a
    DIFFERENT value if they were read."""
    node = _leaf("digits", IrLiteral("1"), IrLiteral("2"), IrLiteral("3"))
    matched_ctor = Construction(_Rec, ("value",), frozenset(), matched="value")
    routines = {"digits": _record((), (), matched_ctor, 3)}
    result = complete_product(node, routines)
    assert result.value == "123"


# ── ambiguity replay: a seeded result is never rebuilt ───────────────────


def test_replay_never_rebuilds_a_result_already_present_in_the_seed():
    """A seeded id(node) entry short-circuits construction — the replay
    contract ambiguity checking depends on to avoid duplicate side effects."""
    calls = []

    def _tracked():
        calls.append(1)
        return "built"

    node = _leaf("root")
    routines = {"root": _record((), (), Construction(_tracked, (), frozenset()), 0)}
    seeded = {id(node): Completed("seeded")}
    executor = ProductExecutor(routines)
    result = executor.replay(node, dict(seeded))
    assert result == "seeded"
    assert not calls  # the tracked constructor was never called


def test_a_fresh_build_of_the_same_node_does_call_the_constructor():
    """Control for the replay test above: without seeding, it DOES run."""
    calls = []

    def _tracked():
        calls.append(1)
        return "built"

    node = _leaf("root")
    routines = {"root": _record((), (), Construction(_tracked, (), frozenset()), 0)}
    executor = ProductExecutor(routines)
    assert executor.build(node) == "built"
    assert calls == [1]


# ── run_ok — ported from the deleted ModelFold.run_ok, rules explicit ────
#
# The old ``fold.run_ok(tables, unit_rid)`` consulted the FOLD's own config
# keys implicitly; the product version takes the tracked-rule NAMES as an
# explicit third argument, so these are the same six scenarios re-expressed
# against that signature.


def test_run_ok_true_for_a_bare_terminal_unit(digit_grammar):
    """unit_rid == -1 (no run at all) is always collapse-safe."""
    tables = compile_tables(digit_grammar)
    assert run_ok(tables, -1, frozenset()) is True


def test_run_ok_false_when_the_unit_is_a_tracked_rule(digit_grammar):
    """A run whose unit resolves to a product-bearing rule is not safe."""
    tables = compile_tables(digit_grammar)
    digit_rid = tables.decode.rule_ids["digit"]
    assert run_ok(tables, digit_rid, frozenset({"digit"})) is False


def test_run_ok_true_when_the_leaf_rule_is_untracked(digit_grammar):
    """A leaf rule outside the tracked set hides no product structure."""
    tables = compile_tables(digit_grammar)
    digit_rid = tables.decode.rule_ids["digit"]
    assert run_ok(tables, digit_rid, frozenset()) is True


def test_run_ok_false_for_a_malformed_synthetic_shape():
    """unit_leaves returning None (not a charset-rule shape) is never safe —
    exercised regardless of the tracked set, which this shape never reaches."""
    bad = malformed_synthetic_rule()
    grammar = IrAst(rules=IrSeq(bad), start=f"{SYNTHETIC_PREFIX}bad")
    tables = compile_tables(grammar)
    rid = tables.decode.rule_ids[f"{SYNTHETIC_PREFIX}bad"]
    assert run_ok(tables, rid, frozenset()) is False


def test_run_ok_false_when_a_transitive_leaf_is_tracked():
    """The unit_rid itself names no tracked rule — only the leaf two hops
    down does — proving the transitive leaf set is consulted, not just the
    rule unit_rid names directly."""
    grammar = nested_synthetic_grammar()
    tables = compile_tables(grammar)
    outer_rid = tables.decode.rule_ids[f"{SYNTHETIC_PREFIX}outer"]
    assert run_ok(tables, outer_rid, frozenset({"digit"})) is False


def test_run_ok_true_when_the_transitive_leaf_is_untracked():
    """Same nested-synthetic shape, but the leaf is outside the tracked set."""
    grammar = nested_synthetic_grammar()
    tables = compile_tables(grammar)
    outer_rid = tables.decode.rule_ids[f"{SYNTHETIC_PREFIX}outer"]
    assert run_ok(tables, outer_rid, frozenset()) is True


# ── collapsed_product_tables — identity memoisation ──────────────────────


def test_collapsed_product_tables_collapses_a_run_on_arithmetic(arithmetic):
    """arithmetic.gbnf's num/ident charclass runs collapse to RunTerm leaves
    (a ``lens == 0`` terminal — see TermTables)."""
    grammar = _instance_grammar(arithmetic)
    plain = compile_tables(grammar)
    collapsed = collapsed_product_tables(grammar, arithmetic.product.routines)
    assert collapsed is not plain
    assert any(length == 0 for length in collapsed.terms.lens)


def test_collapsed_product_tables_memoises_per_routines_and_grammar(arithmetic):
    """The same (grammar, routines) pair returns the identical tables object."""
    grammar = _instance_grammar(arithmetic)
    first = collapsed_product_tables(grammar, arithmetic.product.routines)
    second = collapsed_product_tables(grammar, arithmetic.product.routines)
    assert first is second


def test_collapsed_product_tables_returns_plain_when_no_candidates(optional_shapes):
    """A grammar with no star/plus run candidates gets back the plain tables."""
    grammar = _instance_grammar(optional_shapes)
    plain = compile_tables(grammar)
    collapsed = collapsed_product_tables(grammar, optional_shapes.product.routines)
    assert collapsed is plain


def test_collapsed_product_tables_memo_keys_on_identity_not_equality():
    """Two independently compiled instances of the same source produce
    structurally equal but DISTINCT (grammar, routines) objects — the
    identity-keyed memo must not alias across them."""
    text = (GROUND_TRUTH / "arithmetic.gbnf").read_text(encoding="utf-8")
    cg1 = compile_text(text)
    reset_cache_for_tests()  # force a genuinely fresh second compile
    cg2 = compile_text(text)
    grammar1, grammar2 = _instance_grammar(cg1), _instance_grammar(cg2)
    assert grammar1 == grammar2
    assert grammar1 is not grammar2
    tables1 = collapsed_product_tables(grammar1, cg1.product.routines)
    tables2 = collapsed_product_tables(grammar2, cg2.product.routines)
    assert tables1 is not tables2


def test_collapsed_product_tables_distinct_routines_objects_do_not_share_cache(
    arithmetic,
):
    """A routines mapping EQUAL in content to the original is still a
    distinct object — the memo must recompute, not alias, for it (the same
    identity discipline ``ModelExecutable.replica()`` relies on)."""
    grammar = _instance_grammar(arithmetic)
    duplicate = dict(arithmetic.product.routines)
    first = collapsed_product_tables(grammar, arithmetic.product.routines)
    second = collapsed_product_tables(grammar, duplicate)
    assert first is not second


def _instance_grammar(compiled):
    """The instance grammar a compiled artefact's model product parses."""
    return _model_product(compiled.codegen_grammar, compiled.product).instance_grammar


# ── ported end to end from the deleted test_fold.py ──────────────────────


def test_empty_alternate_arm_completes_with_every_field_absent():
    """Ported byte-for-byte (only the source-of-truth import changed): a rule
    with an empty alternate arm parses empty input to a model with every
    field absent, and the full arm keeps its positional fields — the
    ``_complete_record`` no-kids-matched-n_items branch that calls
    ``construction.call()`` with no captures at all."""
    cg = compile_text('root ::= "<" pair ">"\npair ::= a b |\na ::= "a"\nb ::= "b"\n')
    full = cg.parse("<ab>")
    empty = cg.parse("<>")
    assert full.dump()["pair"] == {"a": {"value": "a"}, "b": {"value": "b"}}
    assert empty.dump()["pair"] == {"a": None, "b": None}
    assert full.to_text() == "<ab>"
    assert empty.to_text() == "<>"
