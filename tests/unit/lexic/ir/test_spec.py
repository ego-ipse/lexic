"""Unit tests for src/lexic/ir/spec.py"""

from __future__ import annotations

from lexic.ir.spec import RuleSpec
from tests.unit.lexic.conftest import make_ident_spec


def test_rulespec_defaults():
    """Default field values are empty."""
    spec = RuleSpec("ws", "Ws", "GrammarModel", "value_str")
    assert not spec.items
    assert not spec.field_map


def test_rulespec_field_map_populated():
    """Field map is stored and indexable."""
    spec = make_ident_spec()
    assert spec.field_map["first"] == 0
    assert spec.field_map["ws"] == 1


def test_rulespec_kind_literals():
    """All three kind values round-trip."""
    for kind in ("sequence", "alternation", "value_str"):
        spec = RuleSpec("r", "R", "GrammarModel", kind)
        assert spec.kind == kind


def test_rulespec_non_semantic_fields_default_empty():
    """non_semantic_fields defaults to an empty frozenset."""
    spec = RuleSpec("r", "R", "GrammarModel", "sequence")
    assert spec.non_semantic_fields == frozenset()


def test_rulespec_non_semantic_fields_set():
    """non_semantic_fields accepts an explicit frozenset."""
    spec = RuleSpec(
        "r", "R", "GrammarModel", "sequence", non_semantic_fields=frozenset({"ws"})
    )
    assert "ws" in spec.non_semantic_fields
