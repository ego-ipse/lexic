"""Generated module: anon_a3ffacaf4b52. Do not edit; regenerated from grammar."""

from __future__ import annotations

from typing import Annotated, Optional

from pydantic import StringConstraints

from lexic.base import GrammarModel
from lexic.ir.base import IrNone
from lexic.ir.nodes import (
    IrCharClass,
    IrChr,
    IrItem,
    IrQuantifier,
    IrRange,
    IrRuleRef,
)
from lexic.ir.spec import RuleSpec

Pattern = Annotated[str, StringConstraints(pattern=r"^[ ]*$")]

Lower = Annotated[str, StringConstraints(pattern=r"^[a-z]+$")]


class Root(GrammarModel):
    ws: Optional[Ws] = None
    value: Value


class Ws(GrammarModel):
    value: Pattern


class Value(GrammarModel):
    value: Lower


Root.__grammar__ = RuleSpec(
    rule_name=IrRuleRef("root"),
    class_name="Root",
    parent_class_name="GrammarModel",
    kind="sequence",
    items=[IrItem(IrRuleRef("ws"), IrQuantifier(0)), IrItem(IrRuleRef("value"))],
    field_map={"ws": 0, "value": 1},
    non_semantic_fields=frozenset(["ws"]),
)


Ws.__grammar__ = RuleSpec(
    rule_name=IrRuleRef("ws"),
    class_name="Ws",
    parent_class_name="GrammarModel",
    kind="value_str",
    items=[IrItem(IrCharClass(IrChr(32)), IrQuantifier(0, IrNone))],
    field_map={},
    non_semantic_fields=frozenset([]),
)


Value.__grammar__ = RuleSpec(
    rule_name=IrRuleRef("value"),
    class_name="Value",
    parent_class_name="GrammarModel",
    kind="value_str",
    items=[
        IrItem(IrCharClass(IrRange(IrChr(97), IrChr(122))), IrQuantifier(1, IrNone))
    ],
    field_map={},
    non_semantic_fields=frozenset([]),
)
