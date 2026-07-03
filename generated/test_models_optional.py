"""Generated module: test_models_optional. Do not edit; regenerated from grammar."""

from __future__ import annotations

from typing import Annotated, Optional

from pydantic import StringConstraints

from lexic.base import GrammarModel
from lexic.ir.nodes import (
    IrAlternation,
    IrItem,
    IrLiteral,
    IrQuantifier,
    IrRuleRef,
    IrSequence,
)
from lexic.ir.spec import RuleSpec

Pattern = Annotated[str, StringConstraints(pattern=r"^(!)?$")]


class Root(GrammarModel):
    thing: Optional[Thing] = None
    head: Optional[Pattern] = None


class Thing(GrammarModel):
    value: str


Root.__grammar__ = RuleSpec(
    rule_name=IrRuleRef("root"),
    class_name="Root",
    parent_class_name="GrammarModel",
    kind="sequence",
    items=[
        IrItem(IrLiteral("a"), IrQuantifier(1, 1)),
        IrItem(IrRuleRef("thing"), IrQuantifier(0, 1)),
        IrItem(
            IrAlternation(IrSequence(IrItem(IrLiteral("!"), IrQuantifier(1, 1)))),
            IrQuantifier(0, 1),
        ),
        IrItem(IrLiteral("b"), IrQuantifier(1, 1)),
    ],
    field_map={"thing": 1, "head": 2},
    non_semantic_fields=frozenset([]),
)


Thing.__grammar__ = RuleSpec(
    rule_name=IrRuleRef("thing"),
    class_name="Thing",
    parent_class_name="GrammarModel",
    kind="value_str",
    items=[IrItem(IrLiteral("T"), IrQuantifier(1, 1))],
    field_map={},
    non_semantic_fields=frozenset([]),
)
