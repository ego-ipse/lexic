"""Unit tests for src/lexic/codegen/ast.py"""

from lexic.grammars.gbnf.ast import (
    Literal,
    CharClass,
    RuleRef,
    Item,
    Sequence,
    Alternation,
    Rule,
)


def test_literal():
    assert Literal("=").value == "="


def test_charclass():
    assert CharClass("[a-z]").pattern == "[a-z]"


def test_ruleref():
    assert RuleRef("ws").name == "ws"


def test_item_with_quantifier():
    it = Item(Literal("x"), "?")
    assert it.quantifier == "?"


def test_item_bare():
    it = Item(Literal("x"), None)
    assert it.quantifier is None


def test_sequence():
    s = Sequence([Item(Literal("a"), None)])
    assert len(s.items) == 1


def test_alternation():
    a = Alternation([Sequence([]), Sequence([])])
    assert len(a.seqs) == 2


def test_rule():
    r = Rule("ws", Alternation([]))
    assert r.name == "ws"
