"""Shared helpers for unit tests under tests/unit/lexic/."""

from __future__ import annotations

from lexic.ir.nodes import (
    IrAlternation,
    IrAst,
    IrCharClass,
    IrItem,
    IrLiteral,
    IrNot,
    IrQuantifier,
    IrRule,
    IrRuleRef,
    IrSequence,
)
from lexic.ir.spec import RuleSpec

# Canonical set of all grammar-AST IR types that every flavour must cover.
GRAMMAR_AST_TYPES: frozenset[type] = frozenset(
    {
        IrLiteral,
        IrCharClass,
        IrNot,
        IrRuleRef,
        IrQuantifier,
        IrItem,
        IrSequence,
        IrAlternation,
        IrRule,
        IrAst,
    }
)


def make_spec(name, kind, items, field_map=None, *, parent="GrammarModel"):
    """Create a RuleSpec with standard defaults."""
    return RuleSpec(
        rule_name=name,
        class_name=name.title(),
        parent_class_name=parent,
        kind=kind,
        items=list(items),
        field_map=field_map or {},
    )


def make_ident_spec(**kwargs):
    """Create the ident/[a-z]/ws RuleSpec used across multiple test files."""
    return RuleSpec(
        "ident",
        "Ident",
        "GrammarModel",
        "sequence",
        items=[IrItem(IrCharClass("a-z")), IrItem(IrRuleRef("ws"))],
        field_map={"first": 0, "ws": 1},
        **kwargs,
    )
