"""Generated module: anon_4e0c41b832f4. Do not edit; regenerated from grammar."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import StringConstraints

from lexic.base import GrammarModel
from lexic.ir.base import IrNone
from lexic.ir.nodes import (
    IrAlternation,
    IrCharClass,
    IrItem,
    IrLiteral,
    IrQuantifier,
    IrRange,
    IrRuleRef,
    IrSequence,
)
from lexic.ir.spec import RuleSpec

Digit = Annotated[str, StringConstraints(pattern=r"^[0-9]+$")]


class Expr(GrammarModel):
    num: Num
    op: Op
    num2: Num


class Op(GrammarModel):
    value: Literal["+", "-", "*", "/"]


class Num(GrammarModel):
    value: Digit


Expr.__grammar__ = RuleSpec(
    rule_name="expr",
    class_name="Expr",
    parent_class_name="GrammarModel",
    kind="sequence",
    items=[
        IrItem(IrRuleRef("num"), IrQuantifier(1, 1)),
        IrItem(IrRuleRef("op"), IrQuantifier(1, 1)),
        IrItem(IrRuleRef("num"), IrQuantifier(1, 1)),
    ],
    field_map={"num": 0, "op": 1, "num2": 2},
    non_semantic_fields=frozenset([]),
)


Op.__grammar__ = RuleSpec(
    rule_name="op",
    class_name="Op",
    parent_class_name="GrammarModel",
    kind="value_str",
    items=[
        IrAlternation(
            IrSequence(IrItem(IrLiteral("+"), IrQuantifier(1, 1))),
            IrSequence(IrItem(IrLiteral("-"), IrQuantifier(1, 1))),
            IrSequence(IrItem(IrLiteral("*"), IrQuantifier(1, 1))),
            IrSequence(IrItem(IrLiteral("/"), IrQuantifier(1, 1))),
        )
    ],
    field_map={},
    non_semantic_fields=frozenset([]),
)


Num.__grammar__ = RuleSpec(
    rule_name="num",
    class_name="Num",
    parent_class_name="GrammarModel",
    kind="value_str",
    items=[IrItem(IrCharClass(IrRange("0", "9")), IrQuantifier(1, IrNone))],
    field_map={},
    non_semantic_fields=frozenset([]),
)
