"""Unit tests for src/lexic/ir/spec.py"""

from __future__ import annotations
from lexic.ir import RuleSpec, CharClassAtom, RuleRefAtom


def test_rulespec_defaults():
    spec = RuleSpec("ws", "Ws", "GrammarModel", "value_str")
    assert spec.items == []
    assert spec.field_map == {}


def test_rulespec_field_map_populated():
    spec = RuleSpec(
        "ident",
        "Ident",
        "GrammarModel",
        "sequence",
        items=[CharClassAtom("[a-z]", 1, 1), RuleRefAtom("ws", 1, 1)],
        field_map={"first": 0, "ws": 1},
    )
    assert spec.field_map["first"] == 0
    assert spec.field_map["ws"] == 1


def test_rulespec_kind_literals():
    for kind in ("sequence", "alternation", "value_str"):
        spec = RuleSpec("r", "R", "GrammarModel", kind)
        assert spec.kind == kind
