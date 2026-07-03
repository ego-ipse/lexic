"""Shared helpers for unit tests under tests/unit/lexic/."""

from __future__ import annotations

from lexic.ir.base import IrChr, IrNone
from lexic.ir.nodes import (
    IrAlternation,
    IrAst,
    IrCharClass,
    IrItem,
    IrLiteral,
    IrQuantifier,
    IrRange,
    IrRule,
    IrRuleRef,
    IrSequence,
)
from lexic.ir.operators import IrNot
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


def make_inner_outer_specs() -> tuple[RuleSpec, RuleSpec]:
    """Return (inner, outer) specs for an expr/root rule-ref pair.

    ``inner`` is a value_str rule matching ``[a-z]+``; ``outer`` is a
    sequence rule referencing ``expr``.  Shared across codegen and
    model-emitter tests that verify rule-ref handling.

    :returns: ``(inner, outer)`` tuple of :class:`~lexic.ir.spec.RuleSpec`.
    """
    inner = make_spec(
        "expr",
        "value_str",
        [IrItem(IrCharClass(IrRange(IrChr("a"), IrChr("z"))), IrQuantifier(1, IrNone))],
    )
    outer = make_spec(
        "root", "sequence", [IrItem(IrRuleRef("expr"))], field_map={"expr": 0}
    )
    return inner, outer


def make_ident_spec(**kwargs):
    """Create the ident/[a-z]/ws RuleSpec used across multiple test files."""
    return RuleSpec(
        "ident",
        "Ident",
        "GrammarModel",
        "sequence",
        items=[
            IrItem(IrCharClass(IrRange(IrChr("a"), IrChr("z")))),
            IrItem(IrRuleRef("ws")),
        ],
        field_map={"first": 0, "ws": 1},
        **kwargs,
    )
