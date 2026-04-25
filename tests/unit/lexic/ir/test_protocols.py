"""Tests for ir/protocols.py — HelperRuleRegistry and IRBuilder protocol wiring."""

from __future__ import annotations
import pytest
from lexic.ir import RuleSpec
from lexic.ir.protocols import HelperRuleRegistry


def _spec(name: str) -> RuleSpec:
    return RuleSpec(
        rule_name=name,
        class_name="X",
        parent_class_name="GrammarModel",
        kind="sequence",
        items=[],
        field_map={},
    )


def test_helper_registry_reserve_base_on_first_use():
    reg = HelperRuleRegistry()
    assert reg.reserve("arithmetic-item") == "arithmetic-item"


def test_helper_registry_reserve_numbers_collisions():
    reg = HelperRuleRegistry()
    reg.register(_spec("arithmetic-item"))
    assert reg.reserve("arithmetic-item") == "arithmetic-item2"
    reg.register(_spec("arithmetic-item2"))
    assert reg.reserve("arithmetic-item") == "arithmetic-item3"


def test_helper_registry_reserve_idempotent_before_register():
    reg = HelperRuleRegistry()
    reg.register(_spec("a"))
    assert reg.reserve("a") == "a2"
    assert reg.reserve("a") == "a2"


def test_helper_registry_all_specs_order():
    reg = HelperRuleRegistry()
    reg.register(_spec("p"))
    reg.register(_spec("q"))
    assert [s.rule_name for s in reg.all_specs()] == ["p", "q"]


def test_helper_registry_rejects_duplicate():
    reg = HelperRuleRegistry()
    reg.register(_spec("x"))
    with pytest.raises(ValueError, match="already registered"):
        reg.register(_spec("x"))
