"""Generated module: test_codegen_refs. Do not edit; regenerated from grammar."""

from __future__ import annotations
from typing import Annotated

from pydantic import StringConstraints

from lexic.base import GrammarModel
from lexic.ir.nodes import (
    IrCharClass,
    IrItem,
    IrRuleRef,
    Quantifier,
)
from lexic.ir.spec import RuleSpec

Lower = Annotated[str, StringConstraints(pattern=r"^[a-z]+$")]


class Root(GrammarModel):
    expr: Expr


class Expr(GrammarModel):
    value: Lower


Root.__grammar__ = RuleSpec(
    rule_name="root",
    class_name="Root",
    parent_class_name="GrammarModel",
    kind="sequence",
    items=[IrItem(IrRuleRef("expr"), Quantifier(1, 1))],
    field_map={"expr": 0},
    non_semantic_fields=frozenset([]),
)


Expr.__grammar__ = RuleSpec(
    rule_name="expr",
    class_name="Expr",
    parent_class_name="GrammarModel",
    kind="value_str",
    items=[IrItem(IrCharClass("a-z"), Quantifier(1, None))],
    field_map={},
    non_semantic_fields=frozenset([]),
)
