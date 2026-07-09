"""Tests for lexic.parsing.fold — the positional instance-parsing bridge.

A plain-data config (rule name → RuleFold) drives PositionalFold over
``parse_first`` trees of the *real* instance grammar — no wrapper rules.
End-to-end fold behaviors run through the compiled pipeline fixtures
(``arithmetic`` / ``optional_shapes`` in conftest); the generic-fold sections
use opaque dict constructors to prove the fold needs no pydantic knowledge.
"""

from __future__ import annotations

import pytest

from lexic.compile import compile_text, reset_cache_for_tests
from lexic.exceptions import UnsupportedConstructError
from lexic.ir.base import IrSeq
from lexic.ir.nodes import (
    IrAlternation,
    IrAst,
    IrItem,
    IrLiteral,
    IrQuantifier,
    IrRule,
    IrRuleRef,
    IrSequence,
)
from lexic.parsing import parse_first
from lexic.parsing.fold import (
    FieldFold,
    PositionalFold,
    RuleFold,
    collapsed_fold_tables,
    lift_optional_nullables,
)
from lexic.parsing.earley.forest import ParseTree
from lexic.parsing.earley.normalize import SYNTHETIC_PREFIX, normalize
from lexic.parsing.earley.tables import compile_tables
from tests._ir_fixtures import malformed_synthetic_rule, nested_synthetic_grammar
from tests.paths import GROUND_TRUTH

# ── the compiled config — structure ─────────────────────────────────────


def test_instance_grammar_is_normalized(arithmetic):
    """The compiled instance grammar is Earley-normalized: parse_first accepts
    it directly (tables.py raises 'run normalize() before compiling' on a raw
    grammar, so a successful parse is itself proof of normalization)."""
    tree = parse_first(arithmetic.instance_grammar, "x=1\n")
    assert tree is not None


def test_config_carries_modes_and_lo_for_field_bearing_items(arithmetic):
    """Each field-bearing item folds under the expected mode and original
    (pre-lift) quantifier lo — the successor of the wrapper-rule registry."""
    config = arithmetic.fold.config
    by_name = {
        rule: {f.name: (f.mode, f.lo) for f in rf.fields} for rule, rf in config.items()
    }
    assert by_name["root"]["root_item"] == ("models", 1)
    assert by_name["expr"]["term"] == ("model", 1)
    assert by_name["expr"]["expr_item"] == ("models", 0)
    assert by_name["ident"]["lower"] == ("text", 1)
    assert by_name["num"]["digit"] == ("text", 1)


def test_unquantified_literals_stay_inline_no_field(arithmetic):
    """Structural (1,1) literals never get a field, but keep their kid slot.

    root-item ::= expr "=" ws term "\\n" — items 1 ('=') and 4 ('\\n') are
    unquantified literals: absent from the fields, present in n_items.
    """
    root_item = arithmetic.fold.config["root-item"]
    bound_slots = {f.item for f in root_item.fields}
    assert 1 not in bound_slots
    assert 4 not in bound_slots
    assert root_item.n_items == 5


# ── PositionalFold construction — config validation ─────────────────────


def test_fold_rejects_unknown_kind():
    """A config kind outside FOLD_KINDS is refused at construction."""
    config = {"r": RuleFold("mystery", dict, 0, ())}
    with pytest.raises(UnsupportedConstructError, match="unknown kind"):
        PositionalFold(config)


def test_fold_rejects_unknown_mode():
    """A field mode outside BIND_MODES is refused at construction."""
    config = {"r": RuleFold("sequence", dict, 1, (FieldFold(0, "bogus", "x", 1),))}
    with pytest.raises(UnsupportedConstructError, match="unknown mode"):
        PositionalFold(config)


def test_fold_kid_count_mismatch_raises():
    """Non-zero kids that match neither n_items nor the empty arm raise."""
    fold = PositionalFold({"r": RuleFold("sequence", dict, 2, ())})
    node = ParseTree(IrRuleRef("r"), IrSeq(IrLiteral("a")))
    with pytest.raises(UnsupportedConstructError, match="do not match"):
        fold.apply(node)


def test_fold_sequence_zero_item_arm_takes_the_equal_length_path():
    """A rule whose single (non-alternate) arm is itself empty (n_items=0)
    folds through the equal-length branch, not the empty-alternate-arm
    mismatch branch — both end up calling ctor() with no kwargs, but a
    kid-count mismatch there would incorrectly raise (kids=0, n_items=0 are
    equal, so ``if len(kids) != rule_fold.n_items`` is False from the start)."""
    fold = PositionalFold({"r": RuleFold("sequence", dict, 0, ())})
    node = ParseTree(IrRuleRef("r"), IrSeq())
    assert fold.apply(node) == {}


# ── PositionalFold.apply — fold behaviors end-to-end ────────────────────


def test_sequence_kwargs_by_position(arithmetic):
    """A sequence rule's fields fold from their positional kid slots."""
    model = arithmetic.parse("x=1\n")
    item = model.root_item[0]
    assert item.expr.term.lower == "x"
    assert item.term.digit == "1"


def test_terminal_field_empty_match_is_empty_string(arithmetic):
    """An empty terminal match (ident's [a-z0-9_]* tail, unmatched) folds to ''."""
    model = arithmetic.parse("x=1\n")
    ident = model.root_item[0].expr.term
    assert ident.head == ""


def test_ruleref_list_field_unbounded(arithmetic):
    """An unbounded ref list ('root_item', one per repetition) collects all."""
    model = arithmetic.parse("x=1\ny=2\n")
    assert len(model.root_item) == 2
    assert model.root_item[0].expr.term.lower == "x"
    assert model.root_item[1].expr.term.lower == "y"


def test_alternation_passthrough(arithmetic):
    """An alternation-kind rule ('term') folds through to its matched arm's model."""
    model = arithmetic.parse("x=1\n")
    term = model.root_item[0].expr.term
    assert type(term).__name__ == "Ident"


def test_value_str_joins_matched_text(arithmetic):
    """A value_str rule ('ws') folds to its matched span joined as one string."""
    model = arithmetic.parse("x = 1\n")
    # ident's own trailing ws eats the space before '='; root-item's ws slot
    # eats the space after '=' — two distinct single-space gaps, not one.
    assert model.root_item[0].expr.term.ws.value == " "
    assert model.root_item[0].ws.value == " "


def test_end_to_end_round_trip(arithmetic):
    """parse(text).to_text() reproduces the input exactly."""
    text = "x=1\n"
    assert arithmetic.parse(text).to_text() == text


def test_optional_ref_absent_is_none(optional_shapes):
    """An optional ref to a non-nullable rule is None when absent."""
    model = optional_shapes.parse("ab")
    assert model.thing is None


def test_optional_ref_present_is_the_submodel(optional_shapes):
    """An optional ref to a non-nullable rule is the sub-model when present."""
    model = optional_shapes.parse("aTb")
    assert model.thing.value == "T"


def test_optional_literal_group_absent_is_empty_text(optional_shapes):
    """``("!")?`` is empty text ('text' mode) when absent.

    canonicalize's rewrite 6 (quantifier push-onto-inner-atom) collapses the
    single-arm single-item group ``("!")?`` to the plain quantified literal
    ``"!"?`` before codegen ever sees it — an ordinary 'text'-mode field
    (``''`` when absent), field name ``lit``.
    """
    model = optional_shapes.parse("ab")
    assert model.lit == ""


def test_optional_literal_group_present_is_text(optional_shapes):
    """``("!")?`` is the matched text when present — same collapse as above."""
    model = optional_shapes.parse("a!b")
    assert model.lit == "!"


# ── zero-kid nodes (empty alternate arm) ─────────────────────────────────


def test_empty_alternate_arm_folds_with_no_kwargs():
    """A rule with an empty alternate arm parses empty input to a model with
    every field absent, and the full arm keeps its positional fields.

    New capability of the positional pipeline (the old derive silently
    dropped empty arms). When the full arm is itself all-nullable the empty
    match is ambiguous between the arms; parse_first resolves it to the
    first derivation, deterministically.
    """
    cg = compile_text('root ::= "<" pair ">"\npair ::= a b |\na ::= "a"\nb ::= "b"\n')
    full = cg.parse("<ab>")
    empty = cg.parse("<>")
    assert full.model_dump()["pair"] == {"a": {"value": "a"}, "b": {"value": "b"}}
    assert empty.model_dump()["pair"] == {"a": None, "b": None}
    assert full.to_text() == "<ab>"
    assert empty.to_text() == "<>"


def test_fold_is_generic_over_opaque_constructors():
    """The fold needs no pydantic: dict constructors work positionally."""
    grammar = normalize(
        IrAst(
            rules=IrSeq(
                IrRule(
                    "pair",
                    IrAlternation(
                        IrSequence(IrItem(IrRuleRef("a")), IrItem(IrRuleRef("b"))),
                        IrSequence(),
                    ),
                ),
                IrRule("a", IrAlternation(IrSequence(IrItem(IrLiteral("a"))))),
                IrRule("b", IrAlternation(IrSequence(IrItem(IrLiteral("b"))))),
            ),
            start="pair",
        )
    )
    fold = PositionalFold(
        {
            "pair": RuleFold(
                "sequence",
                dict,
                2,
                (FieldFold(0, "model", "a", 1), FieldFold(1, "model", "b", 1)),
            ),
            "a": RuleFold("value_str", lambda value: value, 1, ()),
            "b": RuleFold("value_str", lambda value: value, 1, ()),
        }
    )
    assert fold.apply(parse_first(grammar, "ab")) == {"a": "a", "b": "b"}
    assert fold.apply(parse_first(grammar, "")) == {}


# ── lift_optional_nullables ──────────────────────────────────────────────


def test_lift_rewrites_optional_ref_to_nullable_as_mandatory():
    """An optional (0,1) ref to a nullable rule is lifted to (1,1)."""
    empty = IrRule("empty", IrAlternation(IrSequence(IrItem(IrLiteral("")))))
    host = IrRule(
        "host",
        IrAlternation(IrSequence(IrItem(IrRuleRef("empty"), IrQuantifier(0, 1)))),
    )
    lifted = lift_optional_nullables(IrAst(rules=IrSeq(empty, host), start="host"))
    host_lifted = next(r for r in lifted.rules if str(r.name) == "host")
    item = host_lifted.body[0][0]
    assert item.atom == IrRuleRef("empty")
    assert item.quantifier == IrQuantifier(1, 1)


def test_lift_leaves_optional_ref_to_non_nullable_untouched():
    """An optional (0,1) ref to a non-nullable rule is left as-is."""
    solid = IrRule("solid", IrAlternation(IrSequence(IrItem(IrLiteral("z")))))
    host = IrRule(
        "host",
        IrAlternation(IrSequence(IrItem(IrRuleRef("solid"), IrQuantifier(0, 1)))),
    )
    lifted = lift_optional_nullables(IrAst(rules=IrSeq(solid, host), start="host"))
    host_lifted = next(r for r in lifted.rules if str(r.name) == "host")
    item = host_lifted.body[0][0]
    assert item.quantifier == IrQuantifier(0, 1)


def test_lift_preserves_positions_and_start():
    """The lift rewrites items in place: item count, order and start stable."""
    empty = IrRule("empty", IrAlternation(IrSequence(IrItem(IrLiteral("")))))
    host = IrRule(
        "host",
        IrAlternation(
            IrSequence(
                IrItem(IrLiteral("x")),
                IrItem(IrRuleRef("empty"), IrQuantifier(0, 1)),
                IrItem(IrLiteral("y")),
            )
        ),
    )
    lifted = lift_optional_nullables(IrAst(rules=IrSeq(empty, host), start="host"))
    assert lifted.start == "host"
    host_lifted = next(r for r in lifted.rules if str(r.name) == "host")
    arm = host_lifted.body[0]
    assert len(arm) == 3
    assert arm[0].atom == IrLiteral("x")
    assert arm[2].atom == IrLiteral("y")


def test_lift_is_idempotent():
    """Lifting an already-lifted grammar changes nothing further: once an
    item is (1, 1) the rewrite condition (``lo == 0``) no longer holds."""
    empty = IrRule("empty", IrAlternation(IrSequence(IrItem(IrLiteral("")))))
    host = IrRule(
        "host",
        IrAlternation(IrSequence(IrItem(IrRuleRef("empty"), IrQuantifier(0, 1)))),
    )
    ast = IrAst(rules=IrSeq(empty, host), start="host")
    once = lift_optional_nullables(ast)
    twice = lift_optional_nullables(once)
    assert twice == once


# ── collapsed_fold_tables ────────────────────────────────────────────────


def test_collapsed_fold_tables_collapses_a_run_on_arithmetic(arithmetic):
    """arithmetic.gbnf's num/ident charclass runs collapse to RunTerm leaves.

    A collapsed run shows up as a ``lens == 0`` terminal — see
    :class:`~lexic.parsing.earley.tables.TermTables`.
    """
    plain = compile_tables(arithmetic.instance_grammar)
    collapsed = collapsed_fold_tables(arithmetic.instance_grammar, arithmetic.fold)
    assert collapsed is not plain
    assert any(length == 0 for length in collapsed.terms.lens)


def test_collapsed_fold_tables_memoises_per_fold_and_grammar(arithmetic):
    """The same (fold, grammar) pair returns the identical tables object."""
    first = collapsed_fold_tables(arithmetic.instance_grammar, arithmetic.fold)
    second = collapsed_fold_tables(arithmetic.instance_grammar, arithmetic.fold)
    assert first is second


def test_collapsed_fold_tables_returns_plain_when_no_candidates(optional_shapes):
    """A grammar with no star/plus run candidates gets back the plain tables."""
    plain = compile_tables(optional_shapes.instance_grammar)
    collapsed = collapsed_fold_tables(
        optional_shapes.instance_grammar, optional_shapes.fold
    )
    assert collapsed is plain


def test_compiled_tables_are_the_collapsed_ones(arithmetic):
    """CompiledGrammar.tables is exactly the memoised collapsed tables."""
    assert arithmetic.tables is collapsed_fold_tables(
        arithmetic.instance_grammar, arithmetic.fold
    )


def test_collapsed_fold_tables_memo_keys_on_identity_not_equality():
    """Two independent compiles of the same source produce structurally equal
    but distinct (grammar, fold) objects — the memo (keyed on ``id()``, per
    its own docstring) must not alias across them."""
    text = (GROUND_TRUTH / "arithmetic.gbnf").read_text(encoding="utf-8")
    cg1 = compile_text(text)
    reset_cache_for_tests()  # force a genuinely fresh second compile
    cg2 = compile_text(text)
    assert cg1.instance_grammar == cg2.instance_grammar
    assert cg1.instance_grammar is not cg2.instance_grammar
    assert cg1.tables is not cg2.tables


def test_collapsed_fold_tables_distinct_fold_objects_do_not_share_cache(arithmetic):
    """A fold object with an identical config is still a distinct object —
    collapsed_fold_tables must recompute, not alias, for it."""
    duplicate_fold = PositionalFold(dict(arithmetic.fold.config))
    first = collapsed_fold_tables(arithmetic.instance_grammar, arithmetic.fold)
    second = collapsed_fold_tables(arithmetic.instance_grammar, duplicate_fold)
    assert first is not second


# ── PositionalFold.run_ok (the run-collapse licence) ─────────────────────


def test_run_ok_true_for_bare_terminal_unit(digit_grammar):
    """A bare-terminal run unit (unit_rid == -1) is always fold-safe."""
    fold = PositionalFold({})
    tables = compile_tables(digit_grammar)
    assert fold.run_ok(tables, -1) is True


def test_run_ok_false_when_unit_is_a_config_rule(digit_grammar):
    """A run whose unit resolves to a constructor-bearing rule is not safe."""
    fold = PositionalFold({"digit": RuleFold("value_str", dict, 1, ())})
    tables = compile_tables(digit_grammar)
    digit_rid = tables.decode.rule_ids["digit"]
    assert fold.run_ok(tables, digit_rid) is False


def test_run_ok_true_when_leaf_rule_untracked_by_fold(digit_grammar):
    """A leaf rule absent from the fold config hides no model structure."""
    fold = PositionalFold({})
    tables = compile_tables(digit_grammar)
    digit_rid = tables.decode.rule_ids["digit"]
    assert fold.run_ok(tables, digit_rid) is True


def test_run_ok_false_for_malformed_synthetic_shape():
    """unit_leaves returning None (not a charset-rule shape) is not fold-safe.

    The existing run_ok tests only exercise a non-synthetic unit_rid, where
    unit_leaves short-circuits to ``({rid}, False)`` without ever reaching
    the transitive walk or its failure mode. This drives that branch.
    """
    bad = malformed_synthetic_rule()
    g = IrAst(rules=IrSeq(bad), start=f"{SYNTHETIC_PREFIX}bad")
    tables = compile_tables(g)
    rid = tables.decode.rule_ids[f"{SYNTHETIC_PREFIX}bad"]
    fold = PositionalFold({})
    assert fold.run_ok(tables, rid) is False


def test_run_ok_false_when_transitive_leaf_is_a_config_rule():
    """The unit_rid passed in names no config rule directly ('__outer' isn't a
    config key) — only the leaf two hops down ('digit') is. run_ok must still
    block, proving it consults the full transitive leaf set, not just the
    rule named by unit_rid itself."""
    g = nested_synthetic_grammar()
    tables = compile_tables(g)
    outer_rid = tables.decode.rule_ids[f"{SYNTHETIC_PREFIX}outer"]
    fold = PositionalFold({"digit": RuleFold("value_str", dict, 0, ())})
    assert fold.run_ok(tables, outer_rid) is False


def test_run_ok_true_when_transitive_leaf_untracked():
    """Same nested-synthetic structure, but the leaf carries no config entry —
    the run is safe to collapse."""
    g = nested_synthetic_grammar()
    tables = compile_tables(g)
    outer_rid = tables.decode.rule_ids[f"{SYNTHETIC_PREFIX}outer"]
    fold = PositionalFold({})
    assert fold.run_ok(tables, outer_rid) is True


def test_ambiguous_input_folds_deterministically(arithmetic):
    """parse_first under collapsed tables equals the plain-tables fold output."""
    text = "ab1+cd2*34/x9-z=result0\n"
    collapsed_model = arithmetic.parse(text)
    plain_model = arithmetic.fold.apply(parse_first(arithmetic.instance_grammar, text))
    assert collapsed_model.model_dump() == plain_model.model_dump()
    assert collapsed_model.to_text() == plain_model.to_text() == text


# ── run-collapse licence smoke over the sequence text fold ──────────────


def test_run_collapsed_leaf_text_reads_identically(arithmetic):
    """A collapsed multi-char run leaf yields the same field text (probe b)."""
    model = arithmetic.parse("abc1=z\n")
    ident = model.root_item[0].expr.term
    assert ident.lower == "a"
    assert ident.head == "bc1"


def test_fold_value_str_via_hand_tree():
    """value_str folds to ctor(value=<all consumed chars under the node>)."""
    fold = PositionalFold({"w": RuleFold("value_str", dict, 0, ())})
    node = ParseTree(IrRuleRef("w"), IrSeq(IrLiteral("a"), IrLiteral("bc")))
    assert fold.apply(node) == {"value": "abc"}
