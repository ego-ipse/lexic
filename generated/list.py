"""Generated module: list. Do not edit; regenerated from grammar."""

from __future__ import annotations

from typing import Annotated, List

from pydantic import StringConstraints

from lexic.base import GrammarModel
from lexic.ir.nodes import (
    IrCharClass,
    IrItem,
    IrLiteral,
    IrNot,
    IrQuantifier,
    IrRuleRef,
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
    items=[IrItem(atom=IrRuleRef("item"), quantifier=IrQuantifier(1, None))],
    field_map={"item": 0},
    non_semantic_fields=frozenset([]),
)


Item.__grammar__ = RuleSpec(
    rule_name="item",
    class_name="Item",
    parent_class_name="GrammarModel",
    kind="value_str",
    items=[
        IrItem(atom=IrLiteral("- "), quantifier=IrQuantifier(1, 1)),
        IrItem(
            atom=IrNot(body=IrCharClass("\\r\\n\\x0b\\x0c\\x85\\u2028\\u2029")),
            quantifier=IrQuantifier(1, None),
        ),
        IrItem(atom=IrLiteral("\n"), quantifier=IrQuantifier(1, 1)),
    ],
    field_map={},
    non_semantic_fields=frozenset([]),
)
