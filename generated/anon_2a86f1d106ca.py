"""Generated module: anon_2a86f1d106ca. Do not edit; regenerated from grammar."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import StringConstraints

from lexic.base import GrammarModel
from lexic.ir.nodes import (
    IrAlternation,
    IrCharClass,
    IrItem,
    IrLiteral,
    IrQuantifier,
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
    rule_name="greeting",
    class_name="Greeting",
    parent_class_name="GrammarModel",
    kind="sequence",
    items=[
        IrItem(atom=IrRuleRef("salutation"), quantifier=IrQuantifier(1, 1)),
        IrItem(atom=IrLiteral(" "), quantifier=IrQuantifier(1, 1)),
        IrItem(atom=IrRuleRef("name"), quantifier=IrQuantifier(1, 1)),
        IrItem(atom=IrLiteral("!"), quantifier=IrQuantifier(1, 1)),
    ],
    field_map={"salutation": 0, "name": 2},
    non_semantic_fields=frozenset([]),
)


Salutation.__grammar__ = RuleSpec(
    rule_name="salutation",
    class_name="Salutation",
    parent_class_name="GrammarModel",
    kind="value_str",
    items=[
        IrAlternation(
            IrSequence(IrItem(atom=IrLiteral("Hello"), quantifier=IrQuantifier(1, 1))),
            IrSequence(IrItem(atom=IrLiteral("Hi"), quantifier=IrQuantifier(1, 1))),
            IrSequence(IrItem(atom=IrLiteral("Hey"), quantifier=IrQuantifier(1, 1))),
        )
    ],
    field_map={},
    non_semantic_fields=frozenset([]),
)


Name.__grammar__ = RuleSpec(
    rule_name="name",
    class_name="Name",
    parent_class_name="GrammarModel",
    kind="value_str",
    items=[IrItem(atom=IrCharClass("A-Za-z"), quantifier=IrQuantifier(1, None))],
    field_map={},
    non_semantic_fields=frozenset([]),
)
