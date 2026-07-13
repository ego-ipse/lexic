"""Shared helpers for unit tests under tests/unit/lexic/."""

from __future__ import annotations

from typing import Iterable

from lexic.ir.base import IrSelf
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


def contains_ir_type(roots: Iterable[IrSelf], target: type) -> bool:
    """Whether ``target`` appears anywhere in the trees rooted at ``roots``.

    A plain identity-guarded DFS over ``.children()`` — used to assert a
    flavour's action/reduction tables carry no stray instance of a given IR
    node type (e.g. no leftover :class:`~lexic.ir.base.IrLambda` procedural
    escape hatch in a table meant to be pure algebra).
    """
    seen: set[int] = set()
    stack = list(roots)
    while stack:
        node = stack.pop()
        if id(node) in seen:
            continue
        seen.add(id(node))
        if isinstance(node, target):
            return True
        if isinstance(node, IrSelf):
            stack.extend(node.children())
    return False
