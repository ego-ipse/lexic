"""Generated module: anon_2a86f1d106ca. Do not edit; regenerated from grammar."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import StringConstraints

from lexic.base import GrammarModel
from lexic.ir.base import IrNone
from lexic.ir.nodes import (
    IrAlternation,
    IrCharClass,
    IrChr,
    IrItem,
    IrLiteral,
    IrQuantifier,
    IrRange,
    IrRuleRef,
    IrSequence,
)
from lexic.ir.spec import RuleSpec

Pattern = Annotated[str, StringConstraints(pattern=r"^[A-Za-z]+$")]


class Greeting(GrammarModel):
    salutation: Salutation
    name: Name


class Salutation(GrammarModel):
    value: Literal["Hello", "Hi", "Hey"]


class Name(GrammarModel):
    value: Pattern


Greeting.__grammar__ = RuleSpec(
    rule_name=IrRuleRef("greeting"),
    class_name="Greeting",
    parent_class_name="GrammarModel",
    kind="sequence",
    items=[
        IrItem(IrRuleRef("salutation")),
        IrItem(IrLiteral(" ")),
        IrItem(IrRuleRef("name")),
        IrItem(IrLiteral("!")),
    ],
    field_map={"salutation": 0, "name": 2},
    non_semantic_fields=frozenset([]),
)


Salutation.__grammar__ = RuleSpec(
    rule_name=IrRuleRef("salutation"),
    class_name="Salutation",
    parent_class_name="GrammarModel",
    kind="value_str",
    items=[
        IrAlternation(
            IrSequence(IrItem(IrLiteral("Hello"))),
            IrSequence(IrItem(IrLiteral("Hi"))),
            IrSequence(IrItem(IrLiteral("Hey"))),
        )
    ],
    field_map={},
    non_semantic_fields=frozenset([]),
)


Name.__grammar__ = RuleSpec(
    rule_name=IrRuleRef("name"),
    class_name="Name",
    parent_class_name="GrammarModel",
    kind="value_str",
    items=[
        IrItem(
            IrCharClass(IrRange(IrChr(65), IrChr(90)), IrRange(IrChr(97), IrChr(122))),
            IrQuantifier(1, IrNone),
        )
    ],
    field_map={},
    non_semantic_fields=frozenset([]),
)
