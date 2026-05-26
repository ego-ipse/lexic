"""Generated module: test_codegen_simple. Do not edit; regenerated from grammar."""

from __future__ import annotations

from lexic.base import GrammarModel
from lexic.ir.nodes import (
    IrItem,
    IrLiteral,
    IrQuantifier,
)
from lexic.ir.spec import RuleSpec


class Greet(GrammarModel):
    value: str


Greet.__grammar__ = RuleSpec(
    rule_name="greet",
    class_name="Greet",
    parent_class_name="GrammarModel",
    kind="value_str",
    items=[IrItem(atom=IrLiteral(value="hi"), quantifier=IrQuantifier(min=1, max=1))],
    field_map={},
    non_semantic_fields=frozenset([]),
)
