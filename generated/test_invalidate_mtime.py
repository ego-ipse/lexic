"""Generated module: test_invalidate_mtime. Do not edit; regenerated from grammar."""

from __future__ import annotations


from lexic.base import GrammarModel
from lexic.ir.nodes import (
    IrItem,
    IrLiteral,
    IrQuantifier,
)
from lexic.ir.spec import RuleSpec


class Root(GrammarModel):
    value: str


Root.__grammar__ = RuleSpec(
    rule_name="root",
    class_name="Root",
    parent_class_name="GrammarModel",
    kind="value_str",
    items=[IrItem(atom=IrLiteral(value="b"), quantifier=IrQuantifier(min=1, max=1))],
    field_map={},
    non_semantic_fields=frozenset([]),
)
