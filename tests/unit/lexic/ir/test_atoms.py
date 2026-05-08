"""Unit tests for src/lexic/ir/atoms.py"""

from __future__ import annotations

from lexic.ir import (
    AlternationAtom,
    Atom,
    CharClassAtom,
    InlineAlternationAtom,
    InlineRegexAtom,
    LiteralAtom,
    QuantifiedLiteralAtom,
    RuleRefAtom,
)


def test_literal_atom():
    a = LiteralAtom("=")
    assert a.value == "="


def test_char_class_atom():
    a = CharClassAtom("[a-z]", 1, 1)
    assert a.pattern == "[a-z]"
    assert a.min == 1
    assert a.max == 1


def test_char_class_atom_unbounded():
    a = CharClassAtom("[a-z]", 0, None)
    assert a.max is None


def test_rule_ref_atom():
    a = RuleRefAtom("ws", 1, 1)
    assert a.rule_name == "ws"


def test_alternation_atom():
    a = AlternationAtom(["a", "b", "c"])
    assert a.arm_rule_names == ["a", "b", "c"]


def test_quantified_literal_atom():
    a = QuantifiedLiteralAtom("-", 0, 1)
    assert a.value == "-"
    assert a.min == 0
    assert a.max == 1


def test_inline_regex_atom():
    a = InlineRegexAtom("(true|false)", '("true"|"false")', 1, 1)
    assert a.regex == "(true|false)"
    assert a.gbnf == '("true"|"false")'


def test_inline_alternation_atom():
    a = InlineAlternationAtom(["pawn", "nonpawn", "castle"])
    assert a.arm_rule_names == ["pawn", "nonpawn", "castle"]


def test_all_concrete_atoms_satisfy_protocol():
    instances = [
        LiteralAtom("="),
        CharClassAtom("[a-z]", 1, 1),
        QuantifiedLiteralAtom("-", 0, 1),
        InlineRegexAtom("(true|false)", '("true"|"false")', 1, 1),
        RuleRefAtom("ws", 1, 1),
        AlternationAtom(["a", "b"]),
        InlineAlternationAtom(["x", "y"]),
    ]
    for atom in instances:
        assert isinstance(atom, Atom), (
            f"{type(atom).__name__} must satisfy Atom protocol"
        )
