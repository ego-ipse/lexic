"""Tests for lexic.ir.helpers."""

import pytest

from lexic.ir import RuleSpec
from lexic.ir.helpers import HelperRuleRegistry


def _spec(name: str) -> RuleSpec:
    """Helper to create a dummy RuleSpec with the given name."""
    return RuleSpec(
        rule_name=name,
        class_name="X",
        parent_class_name="GrammarModel",
        kind="sequence",
        items=[],
        field_map={},
    )


def test_reserve_returns_base_on_first_use():
    """If base_name isn't taken, reserve() returns it as-is without mutation."""
    reg = HelperRuleRegistry()
    assert reg.reserve("arithmetic-item") == "arithmetic-item"


def test_reserve_numbers_collisions():
    """If base_name is taken, reserve() returns base_name2, then base_name3, etc."""
    reg = HelperRuleRegistry()
    reg.register(_spec("arithmetic-item"))
    assert reg.reserve("arithmetic-item") == "arithmetic-item2"
    reg.register(_spec("arithmetic-item2"))
    assert reg.reserve("arithmetic-item") == "arithmetic-item3"


def test_reserve_is_idempotent_before_register():
    """Reserve does NOT mutate the registry — only register() does."""
    reg = HelperRuleRegistry()
    reg.register(_spec("a"))
    assert reg.reserve("a") == "a2"
    assert reg.reserve("a") == "a2"  # still a2, because a2 isn't registered yet


def test_all_specs_returned_in_registration_order():
    """all_specs() returns all registered specs in the order they were registered."""
    reg = HelperRuleRegistry()
    reg.register(_spec("p"))
    reg.register(_spec("q"))
    reg.register(_spec("r"))
    assert [s.rule_name for s in reg.all_specs()] == ["p", "q", "r"]


def test_register_rejects_duplicate_name():
    """Registering a spec with a name already in the registry raises ValueError."""
    reg = HelperRuleRegistry()
    reg.register(_spec("x"))
    with pytest.raises(ValueError, match=r"already registered"):
        reg.register(_spec("x"))
