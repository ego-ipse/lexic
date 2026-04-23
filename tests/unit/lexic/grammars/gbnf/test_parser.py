"""Unit tests for src/lexic/grammars/gbnf/parser.py"""

from __future__ import annotations

import pytest

from lexic.grammars.gbnf.ast import (
    CharClass,
)
from lexic.grammars.gbnf.parser import GbnfParser, parse_gbnf


def test_parse_single_literal_rule():
    rules = parse_gbnf('root ::= "hello"')
    assert len(rules) == 1
    assert rules[0].name == "root"


def test_parse_rule_ref():
    rules = parse_gbnf("root ::= expr\nexpr ::= ident")
    names = [r.name for r in rules]
    assert names == ["root", "expr"]


def test_parse_charclass():
    rules = parse_gbnf("digit ::= [0-9]")
    assert rules[0].name == "digit"
    seq = rules[0].body.seqs[0]
    assert isinstance(seq.items[0].atom, CharClass)
    assert seq.items[0].atom.pattern == "[0-9]"


def test_parse_alternation():
    rules = parse_gbnf('val ::= "a" | "b"')
    assert len(rules[0].body.seqs) == 2


def test_parse_quantifier_question():
    rules = parse_gbnf("root ::= sign?")
    item = rules[0].body.seqs[0].items[0]
    assert item.quantifier == "?"


def test_parse_quantifier_star():
    rules = parse_gbnf("root ::= digit*")
    item = rules[0].body.seqs[0].items[0]
    assert item.quantifier == "*"


def test_parse_quantifier_plus():
    rules = parse_gbnf("root ::= digit+")
    item = rules[0].body.seqs[0].items[0]
    assert item.quantifier == "+"


def test_parse_repeat_bounds():
    rules = parse_gbnf("root ::= digit{2,4}")
    item = rules[0].body.seqs[0].items[0]
    assert item.quantifier == "{2,4}"


def test_gbnf_parser_class_delegates_to_parse_gbnf():
    parser = GbnfParser()
    rules = parser.parse('root ::= "x"')
    assert rules == parse_gbnf('root ::= "x"')


def test_parse_invalid_syntax_raises():
    with pytest.raises(Exception):
        parse_gbnf("not valid ::= !!!")
