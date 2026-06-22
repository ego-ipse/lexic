"""Tests for lexic.parsing_2.forest — ParseTree and BuildTree.

API changes:

- ``build_tree(chart, item, end)`` free function removed.  The new entry is
  ``BUILD_TREE.eval(d, item, IrTuple(chart, IrInt(end)))``.  Tests that called
  the free function via ``EarleyParser().parse()`` (the old instance method) are
  updated to use the module-level ``parse()`` entry point instead — the
  behavioral coverage (tree shape, symbol, kids) is preserved.

- ``EarleyParser().parse(g, t)`` → module-level ``parse(g, t)``.
"""

from __future__ import annotations

from lexic.ir.base import IrSeq
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
from lexic.parsing_2.engine import parse
from lexic.parsing_2.forest import BUILD_TREE, BuildTree, ParseTree

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
