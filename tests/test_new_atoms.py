"""Tests for the three new IR atom types."""

from __future__ import annotations
import typing
from lexic.ir import (
    QuantifiedLiteralAtom,
    InlineRegexAtom,
    InlineAlternationAtom,
)
from lexic.ir.atoms import Atom


def test_quantified_literal_atom_fields():
    a = QuantifiedLiteralAtom(value="-", min=0, max=1)
    assert a.value == "-"
    assert a.min == 0
    assert a.max == 1


def test_inline_regex_atom_has_both_fields():
    a = InlineRegexAtom(
        regex="(true|false|null)", gbnf='("true"|"false"|"null")', min=1, max=1
    )
    assert a.regex == "(true|false|null)"
    assert a.gbnf == '("true"|"false"|"null")'
    assert a.min == 1
    assert a.max == 1


def test_inline_alternation_atom_fields():
    a = InlineAlternationAtom(arm_rule_names=["pawn", "nonpawn", "castle"])
    assert a.arm_rule_names == ["pawn", "nonpawn", "castle"]


def test_atom_union_includes_new_types():
    args = typing.get_args(Atom)
    names = {a.__name__ for a in args}
    assert "QuantifiedLiteralAtom" in names
    assert "InlineRegexAtom" in names
    assert "InlineAlternationAtom" in names
