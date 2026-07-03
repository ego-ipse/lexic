"""Generated module: list. Do not edit; regenerated from grammar."""

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
    IrRuleRef,
)
from lexic.ir.operators import IrNot
from lexic.ir.spec import RuleSpec

Pattern = Annotated[
    str, StringConstraints(pattern=r"^[^\x0d\x0a\x0b\x0c\x85\u2028\u2029]+$")
]


class Root(GrammarModel):
    item: List[Item]


class Item(GrammarModel):
    value: str


Root.__grammar__ = RuleSpec(
    rule_name=IrRuleRef("root"),
    class_name="Root",
    parent_class_name="GrammarModel",
    kind="sequence",
    items=[IrItem(IrRuleRef("item"), IrQuantifier(1, IrNone))],
    field_map={"item": 0},
    non_semantic_fields=frozenset([]),
)


Item.__grammar__ = RuleSpec(
    rule_name=IrRuleRef("item"),
    class_name="Item",
    parent_class_name="GrammarModel",
    kind="value_str",
    items=[
        IrItem(IrLiteral("- ")),
        IrItem(
            IrNot(
                IrCharClass(
                    IrChr(13),
                    IrChr(10),
                    IrChr(11),
                    IrChr(12),
                    IrChr(133),
                    IrChr(8232),
                    IrChr(8233),
                )
            ),
            IrQuantifier(1, IrNone),
        ),
        IrItem(IrLiteral("\n")),
    ],
    field_map={},
    non_semantic_fields=frozenset([]),
)
