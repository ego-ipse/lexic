"""Unit tests for src/lexic/ir/spec.py"""

from __future__ import annotations

from lexic.ir.nodes import IrCharClass, IrItem, IrRuleRef
from lexic.ir.spec import RuleSpec


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
        items=[IrItem(IrCharClass("a-z")), IrItem(IrRuleRef("ws"))],
        field_map={"first": 0, "ws": 1},
    )
    assert spec.field_map["first"] == 0
    assert spec.field_map["ws"] == 1


def test_rulespec_kind_literals():
    for kind in ("sequence", "alternation", "value_str"):
        spec = RuleSpec("r", "R", "GrammarModel", kind)
        assert spec.kind == kind


def test_rulespec_non_semantic_fields_default_empty():
    spec = RuleSpec("r", "R", "GrammarModel", "sequence")
    assert spec.non_semantic_fields == frozenset()


def test_rulespec_non_semantic_fields_set():
    spec = RuleSpec(
        "r", "R", "GrammarModel", "sequence", non_semantic_fields=frozenset({"ws"})
    )
    assert "ws" in spec.non_semantic_fields
