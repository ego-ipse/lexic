"""Shared IrItem-based fixture helpers for the unit test suite."""

from __future__ import annotations

from typing import Iterable, Literal

from lexic.ir.nodes import IrItem, Quantifier
from lexic.ir.spec import RuleSpec

REQ = Quantifier(1, 1)
OPT = Quantifier(0, 1)
PLUS = Quantifier(1, None)

Kind = Literal["sequence", "alternation", "value_str"]


def item(atom, q: Quantifier = REQ) -> IrItem:
    """Create an IrItem with the given atom and quantifier."""
    return IrItem(atom=atom, quantifier=q)


def spec(
    rule_name: str,
    kind: Kind,
    items: Iterable,
    *,
    field_map: dict[str, int] | None = None,
    non_semantic_fields: frozenset[str] = frozenset(),
) -> RuleSpec:
    """Create a RuleSpec with the given items."""
    return RuleSpec(
        rule_name=rule_name,
        class_name=rule_name.title().replace("-", ""),
        parent_class_name="GrammarModel",
        kind=kind,
        items=list(items),
        field_map=field_map or {},
        non_semantic_fields=non_semantic_fields,
    )
