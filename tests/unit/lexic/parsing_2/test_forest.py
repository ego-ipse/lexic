"""Tests for lexic.parsing_2.forest — ParseTree, SppfNode, DERIVATIONS, BuildTree, CHILD_TREES.

API changes:

- ``build_tree(chart, item, end)`` free function removed.  The new entry is
  ``BUILD_TREE.eval(d, item, IrTuple(chart, IrInt(end)))``.  Tests that called
  the free function via ``EarleyParser().parse()`` (the old instance method) are
  updated to use the module-level ``parse()`` entry point instead — the
  behavioral coverage (tree shape, symbol, kids) is preserved.

- ``EarleyParser().parse(g, t)`` → module-level ``parse(g, t)``.
"""

from __future__ import annotations

from typing import cast

import pytest

from lexic.exceptions import UnsupportedConstructError
from lexic.ir.base import IrInt, IrNoneType, IrSeq, IrStr, IrTuple
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
from lexic.parsing_2 import parse, parse_forest
from lexic.parsing_2.chart import Chart
from lexic.parsing_2.engine import ACCEPTING, EarleyParser
from lexic.parsing_2.forest import (
    BUILD_TREE,
    CHILD_TREES,
    DERIVATIONS,
    BuildTree,
    Derivations,
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
