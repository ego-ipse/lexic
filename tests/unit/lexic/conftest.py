"""Shared helpers for unit tests under tests/unit/lexic/."""

from __future__ import annotations

from lexic.ir.nodes import (
    IrAlternation,
    IrAst,
    IrCharClass,
    IrItem,
    IrLiteral,
    IrQuantifier,
    IrRule,
    IrRuleRef,
    IrSequence,
)
from lexic.ir.operators import IrNot

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
