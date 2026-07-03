"""Generated module: test_invalidate_size. Do not edit; regenerated from grammar."""

from __future__ import annotations

from lexic.base import GrammarModel
from lexic.ir.nodes import (
    IrItem,
    IrLiteral,
    IrQuantifier,
    IrRuleRef,
)
from lexic.ir.spec import RuleSpec


class Root(GrammarModel):
    value: str


Root.__grammar__ = RuleSpec(
    rule_name=IrRuleRef("root"),
    class_name="Root",
    parent_class_name="GrammarModel",
    kind="value_str",
    items=[IrItem(IrLiteral("bbb"), IrQuantifier(1, 1))],
    field_map={},
    non_semantic_fields=frozenset([]),
)
