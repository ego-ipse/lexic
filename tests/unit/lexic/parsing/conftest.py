"""Shared helpers for parsing unit tests."""

from __future__ import annotations

from lexic.ir.spec import NewRuleSpec


def make_spec(name, kind, items, field_map=None, *, parent="GrammarModel"):
    """Helper to create a NewRuleSpec with the given items."""
    return NewRuleSpec(
        rule_name=name,
        class_name=name.title(),
        parent_class_name=parent,
        kind=kind,
        items=list(items),
        field_map=field_map or {},
    )
