"""Generated module: anon_4b3139ea397e. Do not edit; regenerated from grammar."""

from __future__ import annotations

from typing import Annotated, List

from pydantic import StringConstraints

from lexic.base import GrammarModel
from lexic.ir.base import IrNone
from lexic.ir.nodes import (
    IrCharClass,
    IrChr,
    IrItem,
    IrLiteral,
    IrQuantifier,
    IrRange,
    IrRuleRef,
)
from lexic.ir.spec import RuleSpec

Pattern = Annotated[
    str, StringConstraints(pattern=r"^[\x00-\x09\x0e-\x84\x86-‧\u202a-\U0010ffff]+$")
]


class Root(GrammarModel):
    item: List[Item]


class Item(GrammarModel):
    value: str


Root.__grammar__ = RuleSpec(
    rule_name="root",
    class_name="Root",
    parent_class_name="GrammarModel",
    kind="sequence",
    items=[IrItem(IrRuleRef("item"), IrQuantifier(1, IrNone))],
    field_map={"item": 0},
    non_semantic_fields=frozenset([]),
)


Item.__grammar__ = RuleSpec(
    rule_name="item",
    class_name="Item",
    parent_class_name="GrammarModel",
    kind="value_str",
    items=[
        IrItem(IrLiteral("- ")),
        IrItem(
            IrCharClass(
                IrRange(IrChr(0), IrChr(9)),
                IrRange(IrChr(14), IrChr(132)),
                IrRange(IrChr(134), IrChr(8231)),
                IrRange(IrChr(8234), IrChr(1114111)),
            ),
            IrQuantifier(1, IrNone),
        ),
        IrItem(IrLiteral("\n")),
    ],
    field_map={},
    non_semantic_fields=frozenset([]),
)
