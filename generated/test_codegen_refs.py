"""Generated module: test_codegen_refs. Do not edit; regenerated from grammar."""

from __future__ import annotations

from typing import Annotated

from pydantic import StringConstraints

from lexic.base import GrammarModel
from lexic.ir.base import IrNone
from lexic.ir.nodes import (
    IrCharClass,
    IrItem,
    IrQuantifier,
    IrRuleRef,
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
    items=[IrItem(IrRuleRef("expr"), IrQuantifier(1, 1))],
    field_map={"expr": 0},
    non_semantic_fields=frozenset([]),
)


Expr.__grammar__ = RuleSpec(
    rule_name="expr",
    class_name="Expr",
    parent_class_name="GrammarModel",
    kind="value_str",
    items=[IrItem(IrCharClass("a-z"), IrQuantifier(1, IrNone))],
    field_map={},
    non_semantic_fields=frozenset([]),
)
