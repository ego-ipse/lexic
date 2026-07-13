"""Tests for lexic.parsing.earley.forest — ParseTree, SppfNode, DERIVATIONS, BuildTree.

API changes (old → new):

- ``PREFIXES`` / ``Prefixes``  →  ``PrefixSource(node, ctx)`` cogen, driven via
  ``list(Trampoline(PrefixSource(node, ctx)))``.
- ``CHILD_TREES`` / ``ChildTrees`` / ``Whole``  →  ``ChildDerivs(child, ctx)`` cogen.
- ``CHILD_STREAMS`` / ``ChildStream`` / ``LiteralStream``  →  ``ChildDerivs`` cogen;
  a literal child yields exactly itself, an SppfNode child yields ParseTree derivations.
- ``FamilyPrefixes``  →  folded into ``PrefixSource``; covered by PrefixSource tests.
- ``ForestCtx`` no longer has a map interface (``key in ctx`` / ``ctx[key]`` / ``+=``
  are gone); it now exposes only ``chart`` and ``open``.  Sharing / memo tests are
  rewritten as behavioral correctness tests.
- ``ACCEPTING`` (engine.py) is GONE — the accepting SPPF node and decoded chart are
  now obtained by running :class:`~lexic.parsing.earley.kernel.Kernel` directly and
  calling :meth:`~lexic.parsing.earley.kernel.Kernel.accept_node` /
  :meth:`~lexic.parsing.earley.kernel.Kernel.to_chart`.  The local ``_accept`` helper is
  rewritten on top of ``Kernel`` + ``compile_tables``; its signature and callers are
  unchanged.
- The old ``chart[0]`` per-column iteration (used to hunt a dot-0 EarleyItem) has no
  equivalent — ``Chart`` no longer indexes by column. The one test that did this
  (``test_prefix_source_dot_zero_single_empty_prefix``) is rewritten to build a dot-0
  ``SppfNode`` directly from ``kernel.decode_item(dot0_item)`` instead of scanning a
  column.

Preserved unchanged (kept, only construction syntax fixed if needed): ``ParseTree``,
``SppfNode``, ``IrStream`` (all ``test_stream_*`` white-box tests), ``Derivations`` /
``DERIVATIONS``, ``DerivationStream`` / ``DERIVATION_STREAM``, ``BuildTree`` /
``BUILD_TREE``.
"""

from __future__ import annotations

import threading
from typing import Iterator, cast

import pytest

import lexic.parsing.earley.forest as forest_mod
from lexic.exceptions import UnsupportedConstructError
from lexic.ir.base import IrLeaf, IrNone, IrNoneType, IrSelf, IrSeq, IrTuple
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
from lexic.parsing import derivations, parse, parse_forest
from lexic.parsing.earley.chart import Chart
from lexic.parsing.earley.engine import EarleyParser
from lexic.parsing.earley.forest import (
    BUILD_TREE,
    DERIVATION_STREAM,
    DERIVATIONS,
    BuildTree,
    ChildDerivs,
    Derivations,
    DerivationStream,
    ForestCtx,
    IrStream,
    NodeDerivs,
    ParseTree,
    PrefixSource,
    SppfNode,
)
from lexic.parsing.earley.kernel import Kernel
from lexic.parsing.earley.normalize import normalize
from lexic.parsing.earley.tables import ORIGIN_BITS, compile_tables
from lexic.parsing.earley.trampoline import Trampoline
from tests._ir_fixtures import digit_grammar as _digit_grammar
from tests._ir_fixtures import word_grammar as _word_grammar


def _accept(grammar: IrAst, text: str) -> tuple[EarleyParser, Chart, SppfNode, int]:
    """Run a :class:`Kernel` over ``grammar``/``text`` and unpack for forest tests.

    A test-local helper (not a src symbol): compiles and runs the kernel, then
    decodes its accepting node and full chart so the low-level forest nodes can
    be exercised directly. Assumes ``text`` parses, so the node is a real
    :class:`SppfNode`.

    :param grammar: The grammar to parse with.
    :param text: The input string that must parse successfully.
    :returns: ``(parser, chart, accepting_node, len(text))``.
    """
    kernel = Kernel(compile_tables(grammar), text, record_links=True).run()
    assert kernel.accept >= 0
    chart = kernel.to_chart()
    node = kernel.accept_node()
    return EarleyParser(), chart, cast(SppfNode, node), len(text)


# ── ParseTree fields ──────────────────────────────────────────────────


def test_parse_tree_has_symbol_field():
    """ParseTree.symbol holds the IrRuleRef naming the matched rule."""
    tree = ParseTree(IrRuleRef("s"), IrSeq())
    assert tree.symbol == IrRuleRef("s")
    assert isinstance(tree.symbol, IrRuleRef)


def test_parse_tree_has_kids_field():
    """ParseTree.kids holds the matched sub-trees / terminals in source order."""
    kids = IrSeq(IrLiteral("a"), IrLiteral("b"))
    tree = ParseTree(IrRuleRef("s"), kids)
    assert tree.kids is kids


def test_parse_tree_child_attrs_is_kids():
    """The walk protocol routes through 'kids' (not a 'children' attr)."""
    kids = IrSeq(IrLiteral("x"))
    tree = ParseTree(IrRuleRef("r"), kids)
    assert tree.children()[0] is kids


def test_parse_tree_children_returns_kids_tuple():
    """children() returns (kids,) — the single dispatched attribute."""
    kids = IrSeq(IrLiteral("x"))
    tree = ParseTree(IrRuleRef("r"), kids)
    result = tree.children()
    assert result == (kids,)


def test_parse_tree_kids_not_named_children():
    """The field is 'kids', not 'children' — to avoid shadowing the protocol method."""
    tree = ParseTree(IrRuleRef("r"), IrSeq(IrLiteral("x")))
    assert hasattr(tree, "kids")
    assert not hasattr(tree, "_children_field")


# ── BuildTree node ────────────────────────────────────────────────────


def test_build_tree_singleton_is_build_tree_instance():
    """BUILD_TREE is an instance of BuildTree."""
    assert isinstance(BUILD_TREE, BuildTree)


# ── build_tree via parse() ────────────────────────────────────────────

# We build a minimal grammar directly and run the engine, then verify
# the tree structure, rather than manually populating chart.links
# (which is an internal implementation detail).


def test_build_tree_returns_parse_tree():
    """parse() returns a ParseTree for a simple single-char input."""
    grammar = _digit_grammar()
    tree = parse(grammar, "5")
    assert isinstance(tree, ParseTree)


def test_build_tree_symbol_is_start_rule():
    """The root ParseTree's symbol is the start rule's IrRuleRef."""
    grammar = _digit_grammar()
    tree = parse(grammar, "7")
    assert tree.symbol == IrRuleRef("digit")


def test_build_tree_kids_in_source_order():
    """build_tree returns kids in source order (left-to-right input order)."""
    # Grammar: word = letter letter
    grammar = _word_grammar()
    tree = parse(grammar, "hi")
    assert isinstance(tree, ParseTree)
    # Two sub-trees for the two letter matches
    assert len(tree.kids) == 2
    first_kid = tree.kids[0]
    second_kid = tree.kids[1]
    assert isinstance(first_kid, ParseTree)
    assert isinstance(second_kid, ParseTree)
    # First sub-tree consumed 'h', second consumed 'i'
    assert first_kid.kids[0] == IrLiteral("h")
    assert second_kid.kids[0] == IrLiteral("i")


def test_build_tree_leaf_kids_are_ir_literals():
    """Terminal (scanned) children in the tree are IrLiteral values."""
    grammar = _digit_grammar()
    tree = parse(grammar, "3")
    assert len(tree.kids) == 1
    assert isinstance(tree.kids[0], IrLiteral)
    assert tree.kids[0] == IrLiteral("3")


def test_build_tree_recursive_grammar_nests_correctly(expr_grammar: IrAst):
    """build_tree reconstructs nested derivation correctly for recursive grammar."""
    tree = parse(expr_grammar, "(5)")
    # Root: expr with three kids: '(', inner expr subtree, ')'
    assert tree.symbol == IrRuleRef("expr")
    assert len(tree.kids) == 3
    assert tree.kids[0] == IrLiteral("(")
    assert isinstance(tree.kids[1], ParseTree)
    assert tree.kids[1].symbol == IrRuleRef("expr")
    assert tree.kids[2] == IrLiteral(")")


# ── SppfNode construction / identity ─────────────────────────────────


def test_sppf_node_construction(digit_grammar: IrAst):
    """SppfNode returned by ACCEPTING stores item and end correctly."""
    grammar = digit_grammar
    _, __, item, end = _accept(grammar, "5")
    assert not isinstance(item, IrNoneType)
    assert isinstance(item, SppfNode)
    assert isinstance(item.item, tuple)  # raw EarleyItem is a plain tuple
    assert item.end == end


def test_sppf_node_equality_same_item_and_end(digit_grammar: IrAst):
    """Two SppfNode instances with equal item/end are equal (tuple identity)."""
    grammar = digit_grammar
    _, __, item, ___ = _accept(grammar, "5")
    # item is the SppfNode; build a second one from the same raw fields
    node_b = SppfNode(item.item, item.end)
    assert item == node_b


def test_sppf_node_inequality_different_end(digit_grammar: IrAst):
    """SppfNode instances with different end columns are not equal."""
    grammar = digit_grammar
    _, _, item, end = _accept(grammar, "5")
    assert item != SppfNode(item.item, end + 1)


# ── DERIVATIONS — all ParseTrees ──────────────────────────────────────


def test_derivations_unambiguous_yields_one_tree(digit_grammar: IrAst):
    """DERIVATIONS returns exactly one ParseTree for an unambiguous parse."""
    grammar = digit_grammar
    parser, chart, item, _ = _accept(grammar, "7")
    assert not isinstance(item, IrNoneType)
    trees = DERIVATIONS.eval(parser, item, IrTuple(chart))
    assert isinstance(trees, IrSeq)
    assert len(trees) == 1
    assert isinstance(trees[0], ParseTree)


def test_derivations_singleton_matches_parse(digit_grammar: IrAst):
    """The single derivation from DERIVATIONS equals parse()'s result."""
    grammar = digit_grammar
    parser, chart, item, _ = _accept(grammar, "9")
    trees = DERIVATIONS.eval(parser, item, IrTuple(chart))
    expected = parse(grammar, "9")
    assert trees[0] == expected


def test_derivations_ambiguous_yields_two_trees(sss_grammar: IrAst):
    """DERIVATIONS returns 2 distinct ParseTrees for 's = s s / \"a\"' over 'aaa'."""
    parser, chart, item, _ = _accept(sss_grammar, "aaa")
    assert not isinstance(item, IrNoneType)
    trees = DERIVATIONS.eval(parser, item, IrTuple(chart))
    assert len(trees) == 2
    # The two derivations must be distinct
    assert trees[0] != trees[1]


def test_derivations_singleton_is_derivations_instance():
    """DERIVATIONS is a Derivations instance."""
    assert isinstance(DERIVATIONS, Derivations)


# ── BUILD_TREE strict façade ──────────────────────────────────────────


def test_build_tree_strict_returns_single_tree_for_unambiguous(digit_grammar: IrAst):
    """BUILD_TREE.eval succeeds and returns a ParseTree for unambiguous input."""
    grammar = digit_grammar
    parser, chart, item, _ = _accept(grammar, "4")
    tree = BUILD_TREE.eval(parser, item, IrTuple(chart))
    assert isinstance(tree, ParseTree)


def test_build_tree_strict_raises_for_ambiguous(sss_grammar: IrAst):
    """BUILD_TREE.eval raises UnsupportedConstructError for ambiguous input."""
    parser, chart, item, _ = _accept(sss_grammar, "aaa")
    assert not isinstance(item, IrNoneType)
    with pytest.raises(UnsupportedConstructError):
        BUILD_TREE.eval(parser, item, IrTuple(chart))


def test_parse_raises_for_ambiguous_input(sss_grammar: IrAst):
    """parse() raises UnsupportedConstructError when input is ambiguous."""
    with pytest.raises(UnsupportedConstructError):
        parse(sss_grammar, "aaa")


# ── ChildDerivs cogen (adapted from CHILD_TREES / Whole / CHILD_STREAMS) ──
#
# Old: CHILD_TREES dispatched IrLiteral → Whole (single-element seq of itself)
#       and SppfNode → ChildTrees (all ParseTree derivations).
# New: ChildDerivs(child, ctx) cogen driven via Trampoline:
#       - terminal IrLiteral child → [that literal] (its sole derivation)
#       - SppfNode child → its ParseTree derivations


def test_child_derivs_literal_yields_the_literal_itself(digit_grammar: IrAst):
    """ChildDerivs on an IrLiteral terminal yields the literal as its sole derivation.

    Adapted from ``test_child_trees_literal_dispatches_to_whole`` and
    ``test_child_trees_whole_singleton``.
    """
    _, chart, _, __ = _accept(digit_grammar, "5")
    ctx = ForestCtx(chart)
    lit = IrLiteral("x")
    result = list(Trampoline(ChildDerivs(lit, ctx)))
    assert len(result) == 1
    assert result[0] is lit


def test_child_derivs_sppf_node_yields_parse_tree_derivations(digit_grammar: IrAst):
    """ChildDerivs on an SppfNode yields its ParseTree derivations.

    Adapted from ``test_child_trees_sppf_node_dispatches_to_child_trees``.
    """
    grammar = digit_grammar
    _, chart, item, _ = _accept(grammar, "3")
    assert not isinstance(item, IrNoneType)
    ctx = ForestCtx(chart)
    result = list(Trampoline(ChildDerivs(item, ctx)))
    assert len(result) == 1
    assert isinstance(result[0], ParseTree)


def test_child_derivs_literal_vs_sppf_dispatch(digit_grammar: IrAst):
    """ChildDerivs dispatches differently for IrLiteral and SppfNode children.

    Adapted from ``test_child_streams_dispatch``: a literal child returns
    exactly itself (one element); an SppfNode child returns ParseTree
    derivations.
    """
    grammar = digit_grammar
    _, chart, item, _ = _accept(grammar, "3")
    ctx = ForestCtx(chart)

    # Literal arm
    lit = IrLiteral("q")
    lit_result = list(Trampoline(ChildDerivs(lit, ctx)))
    assert len(lit_result) == 1
    assert lit_result[0] is lit

    # SppfNode arm
    node_result = list(Trampoline(ChildDerivs(item, ctx)))
    assert len(node_result) >= 1
    assert isinstance(node_result[0], ParseTree)


# ── PrefixSource cogen (adapted from PREFIXES / Prefixes / FamilyPrefixes) ──
#
# Old: PREFIXES.eval(d, node, IrTuple(ctx)) → IrStream of IrSeq prefixes.
# New: PrefixSource(node, ctx) cogen driven via Trampoline.


def test_prefix_source_dot_zero_single_empty_prefix(digit_grammar: IrAst):
    """A dot-0 handle's PrefixSource yields exactly one empty IrSeq.

    Adapted from ``test_prefixes_dot_zero_single_empty_prefix``: the old
    lookup scanned ``chart[0]`` (a per-column Earley set) for a dot-0 item;
    ``Chart`` no longer indexes by column, so the dot-0 item is decoded
    directly from the kernel's dot-0 code for the start rule instead.
    """
    tables = compile_tables(digit_grammar)
    kernel = Kernel(tables, "5", record_links=True).run()
    (dot0_code,) = tables.codes.rule_dot0[tables.start_id]
    dot0_item = dot0_code << ORIGIN_BITS  # origin 0
    dot_zero = kernel.decode_item(dot0_item)
    assert dot_zero[2] == 0  # dot position
    node = SppfNode(dot_zero, 0)
    chart = kernel.to_chart()
    ctx = ForestCtx(chart)
    prefixes = list(Trampoline(PrefixSource(node, ctx)))
    assert len(prefixes) == 1
    assert prefixes[0] == IrSeq()


def test_prefix_source_yields_irseq_prefixes(sss_grammar: IrAst):
    """PrefixSource yields IrSeq kid-sequences (prefixes) for a completed handle.

    Adapted from ``test_prefixes_returns_irstream``: the new API is a cogen
    whose emits are IrSeq values (not wrapped in an IrStream).
    """
    _, chart, item, _ = _accept(sss_grammar, "aaa")
    ctx = ForestCtx(chart)
    result = list(Trampoline(PrefixSource(item, ctx)))
    assert len(result) > 0
    for prefix in result:
        assert isinstance(prefix, IrSeq)


def test_derivation_stream_returns_irstream(sss_grammar: IrAst):
    """DERIVATION_STREAM.eval returns an IrStream for a valid SppfNode handle.

    Adapted from ``test_prefixes_returns_irstream``: the top-level lazy stream
    is now accessed via ``DERIVATION_STREAM.eval(d, node, IrTuple(ctx))``.
    """
    parser, chart, item, _ = _accept(sss_grammar, "aaa")
    ctx = ForestCtx(chart)
    result = DERIVATION_STREAM.eval(parser, item, IrTuple(ctx))
    assert isinstance(result, IrStream)


# ── ForestCtx sharing / correctness (adapted from memo tests) ─────────
#
# Old tests asserted ForestCtx had a map interface (``key in ctx`` / ``ctx[key]``).
# The new ForestCtx exposes only ``.chart`` and ``.open`` (a set of mid-production
# handles).  Instead we test the behavioral guarantees:
#   (a) Ambiguous derivations are complete and correct.
#   (b) After a full drain, ctx.open is empty (the add/discard cycle is balanced).


def test_ambiguous_grammar_yields_correct_derivation_count(sss_grammar: IrAst):
    """Enumerating 'aaa' yields exactly 2 derivations; 'aaaa' yields exactly 5.

    Adapted from ``test_prefixes_memoised_same_handle`` and
    ``test_shared_subhandle_expanded_once``: the correctness guarantee survives
    even without the old map-interface sharing proof.  A wrong count would
    signal over- or under-expansion of shared sub-handles.
    """
    count_aaa = len(derivations(sss_grammar, "aaa"))
    assert count_aaa == 2, f"expected 2 derivations for 'aaa', got {count_aaa}"

    count_aaaa = len(derivations(sss_grammar, "aaaa"))
    assert count_aaaa == 5, f"expected 5 derivations for 'aaaa', got {count_aaaa}"


def test_forest_ctx_open_empty_after_full_drain(sss_grammar: IrAst):
    """After a full derivation drain, ForestCtx.open is empty.

    Adapted from ``test_shared_subhandle_expanded_once``: the cycle-guard's
    add/discard cycle must be balanced so an exhausted handle is not permanently
    locked out.
    """
    _, chart, item, _ = _accept(sss_grammar, "aaa")
    ctx = ForestCtx(chart)
    trees = list(Trampoline(NodeDerivs(item, ctx)))
    assert len(trees) == 2
    assert ctx.open == set(), (
        f"ForestCtx.open should be empty after drain, got {ctx.open}"
    )


def test_forest_ctx_has_chart_and_open_attributes(digit_grammar: IrAst):
    """ForestCtx exposes .chart (Chart) and .open (set) only — no map interface."""
    _, chart, _, __ = _accept(digit_grammar, "5")
    ctx = ForestCtx(chart)
    assert ctx.chart is chart
    assert isinstance(ctx.open, set)
    assert not hasattr(ctx, "__getitem__"), "ForestCtx must not have a map interface"
    assert not hasattr(ctx, "__contains__"), "ForestCtx must not have a map interface"


# ── parse_forest entry ────────────────────────────────────────────────


def test_parse_forest_returns_sppf_node_on_valid_input(digit_grammar: IrAst):
    """parse_forest() returns an SppfNode for parseable input."""
    grammar = digit_grammar
    result = parse_forest(grammar, "6")
    assert isinstance(result, SppfNode)


def test_parse_forest_returns_ir_none_on_no_parse(digit_grammar: IrAst):
    """parse_forest() returns IrNone when the input does not parse."""
    grammar = digit_grammar
    result = parse_forest(grammar, "z")
    assert isinstance(result, IrNoneType)


# ── IrStream white-box ────────────────────────────────────────────────


class _CountingSource(IrLeaf[IrSelf, IrSelf]):
    """Test source whose __iter__ counts how many times it is driven."""

    __slots__ = ("count", "elems")

    def __init__(self, elems: list[IrSeq]) -> None:
        self.count = 0
        self.elems = elems

    def __iter__(self) -> Iterator[IrSeq]:
        self.count += 1
        yield from self.elems


def test_stream_yields_source_elements():
    """IrStream(IrSeq(a,b,c)) iterates to the three elements in order."""
    a = IrSeq(IrLiteral("a"))
    b = IrSeq(IrLiteral("b"))
    c = IrSeq(IrLiteral("c"))
    stream: IrStream[IrSeq] = IrStream(IrSeq(a, b, c))
    result = list(stream)
    assert result == [a, b, c]


def test_stream_replays_for_multiple_consumers():
    """Iterating the same IrStream twice yields the same elements (buffer replay).

    The source's __iter__ counter proves the source is driven exactly once even
    though two independent consumers see all elements.
    """
    elems = [IrSeq(IrLiteral("x")), IrSeq(IrLiteral("y"))]
    src = _CountingSource(elems)
    stream: IrStream[IrSeq] = IrStream(src)
    r1 = list(stream)
    r2 = list(stream)
    assert r1 == elems
    assert r2 == elems
    assert src.count == 1


def test_stream_single_drive_counter():
    """Full consume → partial consume → full consume drives the source exactly once."""
    elems = [IrSeq(IrLiteral("a")), IrSeq(IrLiteral("b")), IrSeq(IrLiteral("c"))]
    src = _CountingSource(elems)
    stream: IrStream[IrSeq] = IrStream(src)
    # First full drain
    full1 = list(stream)
    assert len(full1) == 3
    # Partial consume (first element only)
    partial = next(iter(stream))
    assert partial == elems[0]
    # Second full drain
    full2 = list(stream)
    assert full2 == elems
    # Source must have been driven exactly once
    assert src.count == 1


def test_stream_cycle_sentinel_on_reentrant_iteration():
    """A re-entrant (cyclic) iteration replays the on_cycle sentinel, not more elements.

    The source re-iterates the stream mid-yield (simulating the prefix-stream cycle),
    and we assert it captured exactly the sentinel tuple — not a recursive infinite loop.
    """

    class _ReentrantSource(IrLeaf[IrSelf, IrSelf]):
        __slots__ = ("stream", "captured")

        def __init__(self) -> None:
            self.stream: IrStream[IrSeq] | None = None
            self.captured: list[IrSeq] = []

        def __iter__(self) -> Iterator[IrSeq]:
            # Re-enter the not-yet-done stream to capture the cycle sentinel
            assert self.stream is not None
            self.captured = list(self.stream)
            yield IrSeq(IrLiteral("real"))

    sentinel = IrSeq()
    src = _ReentrantSource()
    stream: IrStream[IrSeq] = IrStream(src, (sentinel,))
    src.stream = stream

    result = list(stream)

    assert result == [IrSeq(IrLiteral("real"))]
    # The re-entrant call should have received exactly the on_cycle sentinel
    assert src.captured == [sentinel]


def test_stream_empty_source():
    """IrStream over an empty IrSeq yields nothing and replays nothing."""
    src = _CountingSource([])
    stream: IrStream[IrSeq] = IrStream(src)
    assert not list(stream)
    # A second iteration still yields nothing (buffer replay, not re-drive)
    assert not list(stream)
    # The source was driven exactly once even though it produced nothing
    assert src.count == 1


# ── Nullable cycle termination ────────────────────────────────────────


def _make_nullable_cycle_grammar() -> IrAst:
    """Build: a = b ; b = a / '' — a→b→a reference with an empty-span arm."""
    b_rule = IrRule(
        "b",
        IrAlternation(
            IrSequence(IrItem(IrRuleRef("a"))),
            IrSequence(),  # empty arm makes b (and a) nullable
        ),
    )
    a_rule = IrRule(
        "a",
        IrAlternation(IrSequence(IrItem(IrRuleRef("b")))),
    )
    return IrAst(rules=IrSeq(a_rule, b_rule), start="a")


def test_nullable_cycle_terminates():
    """derivations() on a grammar with a nullable a→b→a cycle terminates and is finite.

    A regression guard: a naive forest enumeration without the _DRIVING sentinel
    would loop forever on this cycle.  A hanging test will be killed by the thread
    timeout, and the assertion will report the failure.
    """
    grammar = _make_nullable_cycle_grammar()
    result: list[IrSeq] = []

    def _run() -> None:
        result.append(derivations(grammar, ""))

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(timeout=5.0)
    assert not t.is_alive(), "derivations() on a nullable cycle did not terminate in 5s"
    # If derivations() raised, result is empty; check it succeeded
    assert result, "derivations() raised an exception in the thread"
    assert isinstance(result[0], IrSeq)
    assert len(result[0]) > 0  # at least one derivation


# ── Lazy short-circuit proofs ─────────────────────────────────────────


def test_build_tree_strict_short_circuits(sss_grammar: IrAst):
    """BUILD_TREE stops at the 2nd derivation and raises ambiguity without driving more.

    A counter-based stream records how many elements were consumed.  We assert
    UnsupportedConstructError is raised AND that the counter never exceeds 2.
    """
    parser, chart, item, _ = _accept(sss_grammar, "aaa")
    real_ds = DERIVATIONS.eval(parser, item, IrTuple(chart))
    t1, t2 = real_ds[0], real_ds[1]

    consumed: list[int] = [0]

    class _CountingDerivStream(DerivationStream):
        def eval(self, _d: IrSelf, n: IrSelf, nc: object, /) -> IrStream[ParseTree]:
            def _src():
                consumed[0] += 1
                yield t1
                consumed[0] += 1
                yield t2
                raise AssertionError("over-enumerated: BUILD_TREE drove past 2")

            return IrStream(_src())

    orig = forest_mod.DERIVATION_STREAM
    forest_mod.DERIVATION_STREAM = _CountingDerivStream()
    try:
        with pytest.raises(UnsupportedConstructError):
            BUILD_TREE.eval(parser, item, IrTuple(chart))
    finally:
        forest_mod.DERIVATION_STREAM = orig
    assert consumed[0] == 2, f"expected 2 elements consumed, got {consumed[0]}"


def test_build_tree_zero_derivations_raises(digit_grammar: IrAst):
    """BUILD_TREE raises UnsupportedConstructError when the handle has no families.

    A broken chart with an accepting item but no links: the fast path cannot find
    children (returns IrNone) and the fallback trampoline path then raises.
    """
    parser, _chart, item, _ = _accept(digit_grammar, "5")
    empty_chart = _chart.__class__()
    with pytest.raises(UnsupportedConstructError):
        BUILD_TREE.eval(parser, item, IrTuple(empty_chart))


def test_derivations_realises_all(sss_grammar: IrAst):
    """DERIVATIONS returns Catalan(3)=5 distinct trees for sss 'aaaa', stable across calls."""
    result1 = derivations(sss_grammar, "aaaa")
    result2 = derivations(sss_grammar, "aaaa")
    assert isinstance(result1, IrSeq)
    assert len(result1) == 5
    assert all(isinstance(t, ParseTree) for t in result1)
    # All 5 trees are pairwise distinct
    trees = list(result1)
    for i, ta in enumerate(trees):
        for tb in trees[:i]:
            assert ta != tb, f"trees[{i}] should differ from earlier tree"
    # Stable across calls: same length and equal element-wise
    assert len(result2) == 5
    assert all(result1[i] == result2[i] for i in range(5))


# ── Depth-safety regression test ──────────────────────────────────────


def _make_right_recursive_grammar() -> IrAst:
    """Build: S = 'a'* — a right-recursive nullable grammar.

    Normalised via :func:`~lexic.parsing.earley.normalize.normalize`, the
    quantifier desugars to right-recursive rules that produce an arbitrarily
    deep parse spine for long input.

    :returns: The normalised :class:`IrAst` ready to pass to ``parse``.
    """
    rule = IrRule(
        "S",
        IrAlternation(IrSequence(IrItem(IrLiteral("a"), IrQuantifier(0, IrNone)))),
    )
    return normalize(IrAst(rules=IrSeq(rule), start="S"))


def test_deep_right_recursion_does_not_crash():
    """parse() on a 1500-character right-recursive input does not raise RecursionError.

    N=1500 is far past the ~300-level crash threshold of the old nested-generator
    walk and is safe on memory (the Earley chart is O(n²) — 1500² ≈ 2.25M cells).
    This test runs on the main thread at the DEFAULT recursion limit; no
    ``sys.setrecursionlimit`` call.
    """
    grammar = _make_right_recursive_grammar()
    n = 1500
    tree = parse(grammar, "a" * n)
    assert isinstance(tree, ParseTree)
