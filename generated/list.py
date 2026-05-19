"""Generated module: list. Do not edit; regenerated from grammar."""

from __future__ import annotations
from typing import Annotated, List

from pydantic import StringConstraints

from lexic.base import GrammarModel
from lexic.ir.nodes import (
    IrCharClass,
    IrItem,
    IrLiteral,
    IrRuleRef,
    Quantifier,
)
from lexic.ir.spec import RuleSpec

Pattern = Annotated[
    str, StringConstraints(pattern=r"^[^\r\n\x0b\x0c\x85\u2028\u2029]+$")
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
    items=[IrItem(IrRuleRef("item"), Quantifier(1, None))],
    field_map={"item": 0},
    non_semantic_fields=frozenset([]),
)


Item.__grammar__ = RuleSpec(
    rule_name="item",
    class_name="Item",
    parent_class_name="GrammarModel",
    kind="value_str",
    items=[
        IrItem(IrLiteral("- "), Quantifier(1, 1)),
        IrItem(
            IrCharClass("\\r\\n\\x0b\\x0c\\x85\\u2028\\u2029", negated=True),
            Quantifier(1, None),
        ),
        IrItem(IrLiteral("\n"), Quantifier(1, 1)),
    ],
    field_map={},
    non_semantic_fields=frozenset([]),
)
