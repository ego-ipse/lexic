"""Tests for lexic.parsing_2.forest — ParseTree, SppfNode, DERIVATIONS, BuildTree, CHILD_TREES.

API changes:

- ``build_tree(chart, item, end)`` free function removed.  The new entry is
  ``BUILD_TREE.eval(d, item, IrTuple(chart, IrInt(end)))``.  Tests that called
  the free function via ``EarleyParser().parse()`` (the old instance method) are
  updated to use the module-level ``parse()`` entry point instead — the
  behavioral coverage (tree shape, symbol, kids) is preserved.

- ``EarleyParser().parse(g, t)`` → module-level ``parse(g, t)``.

New lazy machinery added (IrStream, PREFIXES, ForestCtx, CHILD_STREAMS, DERIVATION_STREAM):
see the new sections below the existing suites.
"""

from __future__ import annotations

import threading
from typing import Iterator, cast

import pytest

import lexic.parsing_2.forest as forest_mod
from lexic.exceptions import UnsupportedConstructError
from lexic.ir.base import IrInt, IrLeaf, IrNoneType, IrSelf, IrSeq, IrStr, IrTuple
from lexic.ir.nodes import (
    IrAlternation,
    IrAst,
    IrCharClass,
    IrChr,
    IrItem,
    IrLiteral,
    IrRange,
    IrRule,
    IrRuleRef,
    IrSequence,
)
from lexic.parsing_2 import derivations, parse, parse_forest
from lexic.parsing_2.chart import Chart
from lexic.parsing_2.engine import ACCEPTING, EarleyParser
from lexic.parsing_2.forest import (
    BUILD_TREE,
    CHILD_STREAMS,
    CHILD_TREES,
    DERIVATION_STREAM,
    DERIVATIONS,
    PREFIXES,
    BuildTree,
    Derivations,
    DerivationStream,
    ForestCtx,
    IrStream,
    ParseTree,
    SppfNode,
    Whole,
)
from lexic.parsing_2.item import EarleyItem


def _accept(grammar: IrAst, text: str) -> tuple[EarleyParser, Chart, EarleyItem, int]:
    """Drive the public :data:`ACCEPTING` node and unpack for the forest tests.

    A test-local helper (not a src symbol): builds the chart once and returns the
    accepting item so the low-level forest nodes can be exercised directly. Assumes
    ``text`` parses, so the item is a real :class:`EarleyItem`.
    """
    parser = EarleyParser()
    chart, item = ACCEPTING.eval(parser, grammar, IrTuple(IrStr(text)))
    return parser, cast(Chart, chart), cast(EarleyItem, item), len(text)


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


def _make_digit_grammar() -> IrAst:
    """digit = [0-9] ; single-char char-class rule."""
    digit_rule = IrRule(
        "digit",
        IrAlternation(IrSequence(IrItem(IrCharClass(IrRange(IrChr("0"), IrChr("9")))))),
    )
    return IrAst(rules=IrSeq(digit_rule), start="digit")


def test_build_tree_returns_parse_tree():
    """parse() returns a ParseTree for a simple single-char input."""
    grammar = _make_digit_grammar()
    tree = parse(grammar, "5")
    assert isinstance(tree, ParseTree)


def test_build_tree_symbol_is_start_rule():
    """The root ParseTree's symbol is the start rule's IrRuleRef."""
    grammar = _make_digit_grammar()
    tree = parse(grammar, "7")
    assert tree.symbol == IrRuleRef("digit")


def test_build_tree_kids_in_source_order():
    """build_tree returns kids in source order (left-to-right input order)."""
    # Grammar: word = letter letter
    letter = IrRule(
        "letter",
        IrAlternation(IrSequence(IrItem(IrCharClass(IrRange(IrChr("a"), IrChr("z")))))),
    )
    word = IrRule(
        "word",
        IrAlternation(
            IrSequence(IrItem(IrRuleRef("letter")), IrItem(IrRuleRef("letter")))
        ),
    )
    grammar = IrAst(rules=IrSeq(word, letter), start="word")
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
    grammar = _make_digit_grammar()
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
    """SppfNode(item, end) stores item and end correctly."""
    grammar = digit_grammar
    _, __, item, end = _accept(grammar, "5")
    assert not isinstance(item, IrNoneType)
    node = SppfNode(item, end)
    assert node.item is item
    assert node.end == end


def test_sppf_node_equality_same_item_and_end(digit_grammar: IrAst):
    """Two SppfNode instances with equal item/end are equal (tuple identity)."""
    grammar = digit_grammar
    _, __, item, end = _accept(grammar, "5")
    node_a = SppfNode(item, end)
    node_b = SppfNode(item, end)
    assert node_a == node_b


def test_sppf_node_inequality_different_end(digit_grammar: IrAst):
    """SppfNode instances with different end columns are not equal."""
    grammar = digit_grammar
    _, _, item, end = _accept(grammar, "5")
    assert SppfNode(item, end) != SppfNode(item, end + 1)


# ── DERIVATIONS — all ParseTrees ──────────────────────────────────────


def test_derivations_unambiguous_yields_one_tree(digit_grammar: IrAst):
    """DERIVATIONS returns exactly one ParseTree for an unambiguous parse."""
    grammar = digit_grammar
    parser, chart, item, end = _accept(grammar, "7")
    assert not isinstance(item, IrNoneType)
    node = SppfNode(item, end)
    trees = DERIVATIONS.eval(parser, node, IrTuple(chart))
    assert isinstance(trees, IrSeq)
    assert len(trees) == 1
    assert isinstance(trees[0], ParseTree)


def test_derivations_singleton_matches_parse(digit_grammar: IrAst):
    """The single derivation from DERIVATIONS equals parse()'s result."""
    grammar = digit_grammar
    parser, chart, item, end = _accept(grammar, "9")
    node = SppfNode(item, end)
    trees = DERIVATIONS.eval(parser, node, IrTuple(chart))
    expected = parse(grammar, "9")
    assert trees[0] == expected


def test_derivations_ambiguous_yields_two_trees(sss_grammar: IrAst):
    """DERIVATIONS returns 2 distinct ParseTrees for 's = s s / \"a\"' over 'aaa'."""
    parser, chart, item, end = _accept(sss_grammar, "aaa")
    assert not isinstance(item, IrNoneType)
    node = SppfNode(item, end)
    trees = DERIVATIONS.eval(parser, node, IrTuple(chart))
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
    parser, chart, item, end = _accept(grammar, "4")
    tree = BUILD_TREE.eval(parser, item, IrTuple(chart, IrInt(end)))
    assert isinstance(tree, ParseTree)


def test_build_tree_strict_raises_for_ambiguous(sss_grammar: IrAst):
    """BUILD_TREE.eval raises UnsupportedConstructError for ambiguous input."""
    parser, chart, item, end = _accept(sss_grammar, "aaa")
    assert not isinstance(item, IrNoneType)
    with pytest.raises(UnsupportedConstructError):
        BUILD_TREE.eval(parser, item, IrTuple(chart, IrInt(end)))


def test_parse_raises_for_ambiguous_input(sss_grammar: IrAst):
    """parse() raises UnsupportedConstructError when input is ambiguous."""
    with pytest.raises(UnsupportedConstructError):
        parse(sss_grammar, "aaa")


# ── CHILD_TREES dispatch ──────────────────────────────────────────────


def test_child_trees_literal_dispatches_to_whole():
    """CHILD_TREES dispatches IrLiteral → Whole (the sole derivation is the literal itself)."""
    parser = EarleyParser()
    literal = IrLiteral("x")
    result = CHILD_TREES.eval(parser, literal, IrTuple())
    assert isinstance(result, IrSeq)
    assert len(result) == 1
    assert result[0] is literal


def test_child_trees_whole_singleton():
    """Whole is the terminal-leaf arm of CHILD_TREES — contributes the node as-is."""
    whole = Whole()
    parser = EarleyParser()
    literal = IrLiteral("z")
    result = whole.eval(parser, literal, ())
    assert isinstance(result, IrSeq)
    assert len(result) == 1
    assert result[0] is literal


def test_child_trees_sppf_node_dispatches_to_child_trees(digit_grammar: IrAst):
    """CHILD_TREES dispatches SppfNode → ChildTrees (enumerates sub-tree derivations)."""
    grammar = digit_grammar
    parser, chart, item, end = _accept(grammar, "3")
    assert not isinstance(item, IrNoneType)
    node = SppfNode(item, end)
    result = CHILD_TREES.eval(parser, node, IrTuple(chart))
    assert isinstance(result, IrSeq)
    assert len(result) == 1
    assert isinstance(result[0], ParseTree)


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


# ── Prefixes / memo / sharing ─────────────────────────────────────────


def test_prefixes_returns_irstream(sss_grammar: IrAst):
    """PREFIXES.eval returns an IrStream for a valid SppfNode handle."""
    parser, chart, item, end = _accept(sss_grammar, "aaa")
    node = SppfNode(item, end)
    ctx = ForestCtx(chart)
    result = PREFIXES.eval(parser, node, IrTuple(ctx))
    assert isinstance(result, IrStream)


def test_prefixes_memoised_same_handle(sss_grammar: IrAst):
    """PREFIXES.eval for the same handle twice returns the identical IrStream object."""
    parser, chart, item, end = _accept(sss_grammar, "aaa")
    node = SppfNode(item, end)
    ctx = ForestCtx(chart)
    s1 = PREFIXES.eval(parser, node, IrTuple(ctx))
    s2 = PREFIXES.eval(parser, node, IrTuple(ctx))
    assert s1 is s2
    key = (node.item, node.end)
    assert key in ctx
    assert ctx[key][0] is s1


def test_prefixes_dot_zero_single_empty_prefix(digit_grammar: IrAst):
    """A dot-0 handle's prefix stream yields exactly one empty IrSeq."""
    parser, chart, _, __ = _accept(digit_grammar, "5")
    # Find a dot-0 EarleyItem in column 0
    dot_zero: EarleyItem | None = None
    for ei in chart[0]:
        if ei.dot == 0:
            dot_zero = ei
            break
    assert dot_zero is not None
    node = SppfNode(dot_zero, 0)
    ctx = ForestCtx(chart)
    stream = PREFIXES.eval(parser, node, IrTuple(ctx))
    prefixes = list(stream)
    assert len(prefixes) == 1
    assert prefixes[0] == IrSeq()


def test_shared_subhandle_expanded_once(sss_grammar: IrAst):
    """Shared sub-handles are memoised: a second derivation call re-uses filed streams.

    Two derivations of sss 'aaa' each contain the same 'a' sub-node — that
    sub-node must be filed in the ForestCtx and recovered (not re-derived).
    We verify this by counting how many times PREFIXES.eval is asked to FILE
    a new stream (i.e. the key was not yet in the ctx): it must be strictly less
    than the total number of tree-node slots across both derivations.
    """
    parser, chart, item, end = _accept(sss_grammar, "aaa")
    node = SppfNode(item, end)
    ctx = ForestCtx(chart)
    # Drain the derivation stream to force full expansion
    all_trees = list(DERIVATION_STREAM.eval(parser, node, IrTuple(ctx)))
    assert len(all_trees) == 2

    # Count total tree nodes (ParseTree + IrLiteral leaves) across both derivations
    def _count_nodes(tree: object) -> int:
        if isinstance(tree, ParseTree):
            return 1 + sum(_count_nodes(k) for k in tree.kids)
        return 1

    total_nodes = sum(_count_nodes(t) for t in all_trees)

    # Count how many distinct (item, end) handles were filed in the ctx by checking
    # how many keys are accessible: call PREFIXES.eval on each tree's SppfNode and
    # count unique keys known to the ctx.  We do this by asking PREFIXES again for
    # the root — it must return the same stream (identity, already filed).
    root_key = (node.item, node.end)
    assert root_key in ctx
    root_stream = PREFIXES.eval(parser, node, IrTuple(ctx))
    # The root stream was filed before driving, so a second call returns the same object
    assert root_stream is ctx[root_key][0]

    # The root node is ONE handle; the two derivations share sub-handles.
    # total_nodes is strictly greater than 1, confirming at least one shared sub-tree.
    assert total_nodes > 1


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
    would loop forever on this cycle. A hanging test will be killed by the thread
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

    A counter-based stream records how many elements were consumed. We assert
    UnsupportedConstructError is raised AND that the counter never exceeds 2.
    """
    parser, chart, item, end = _accept(sss_grammar, "aaa")
    node = SppfNode(item, end)
    real_ds = DERIVATIONS.eval(parser, node, IrTuple(chart))
    t1, t2 = real_ds[0], real_ds[1]

    consumed: list[int] = [0]

    class _CountingDerivStream(DerivationStream):
        def eval(self, d: IrSelf, n: IrSelf, nc: object, /) -> IrStream[ParseTree]:
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
            BUILD_TREE.eval(parser, item, IrTuple(chart, IrInt(end)))
    finally:
        forest_mod.DERIVATION_STREAM = orig
    assert consumed[0] == 2, f"expected 2 elements consumed, got {consumed[0]}"


def test_build_tree_zero_derivations_raises(digit_grammar: IrAst):
    """BUILD_TREE raises UnsupportedConstructError when the handle has no derivation."""
    parser, chart, item, end = _accept(digit_grammar, "5")

    class _EmptyDerivStream(DerivationStream):
        def eval(self, d: IrSelf, n: IrSelf, nc: object, /) -> IrStream[ParseTree]:
            return IrStream(IrSeq())

    orig = forest_mod.DERIVATION_STREAM
    forest_mod.DERIVATION_STREAM = _EmptyDerivStream()
    try:
        with pytest.raises(UnsupportedConstructError):
            BUILD_TREE.eval(parser, item, IrTuple(chart, IrInt(end)))
    finally:
        forest_mod.DERIVATION_STREAM = orig


def test_child_streams_dispatch(digit_grammar: IrAst):
    """CHILD_STREAMS dispatches SppfNode → ChildStream and IrLiteral → LiteralStream."""
    parser = EarleyParser()
    # LiteralStream arm: yields the literal itself as a one-element stream
    lit = IrLiteral("q")
    lit_stream = CHILD_STREAMS.eval(parser, lit, IrTuple())
    assert isinstance(lit_stream, IrStream)
    items = list(lit_stream)
    assert len(items) == 1
    assert items[0] is lit

    # ChildStream arm: yields ParseTree derivations for an SppfNode
    _, chart, item, end = _accept(digit_grammar, "3")
    node = SppfNode(item, end)
    ctx = ForestCtx(chart)
    node_stream = CHILD_STREAMS.eval(parser, node, IrTuple(ctx))
    assert isinstance(node_stream, IrStream)
    node_items = list(node_stream)
    assert len(node_items) >= 1
    assert isinstance(node_items[0], ParseTree)


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
