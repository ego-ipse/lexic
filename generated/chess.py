"""Generated module: chess. Do not edit; regenerated from grammar."""

from __future__ import annotations

from typing import Annotated, List, Optional, Union

from pydantic import StringConstraints

from lexic.base import GrammarModel
from lexic.ir.nodes import (
    IrAlternation,
    IrCharClass,
    IrGroup,
    IrItem,
    IrLiteral,
    IrRuleRef,
    IrSequence,
    Quantifier,
)
from lexic.ir.spec import RuleSpec

Pattern = Annotated[str, StringConstraints(pattern=r"^[+#]?$")]

Pattern2 = Annotated[str, StringConstraints(pattern=r"^[NBKQR]$")]

Pattern3 = Annotated[str, StringConstraints(pattern=r"^[a-h]?$")]

Pattern4 = Annotated[str, StringConstraints(pattern=r"^[1-8]?$")]

Pattern5 = Annotated[str, StringConstraints(pattern=r"^[a-h]$")]

Pattern6 = Annotated[str, StringConstraints(pattern=r"^[1-8]$")]

Pattern7 = Annotated[str, StringConstraints(pattern=r"^([a-h]x)?$")]

Pattern8 = Annotated[str, StringConstraints(pattern=r"^(=[NBKQR])?$")]

Pattern9 = Annotated[str, StringConstraints(pattern=r"^[1-9]$")]

Digit = Annotated[str, StringConstraints(pattern=r"^[0-9]?$")]


class Root(GrammarModel):
    move: Move
    move2: Move
    root_item: List[RootItem]


class Move(GrammarModel):
    kind: Union[Pawn, Nonpawn, Castle]
    head: Optional[Pattern] = None


class Nonpawn(GrammarModel):
    value: str


class Pawn(GrammarModel):
    value: str


class Castle(GrammarModel):
    value: str


class RootItem(GrammarModel):
    head: Pattern9
    digit: Optional[Digit] = None
    move: Move
    move2: Move


Root.__grammar__ = RuleSpec(
    rule_name="root",
    class_name="Root",
    parent_class_name="GrammarModel",
    kind="sequence",
    items=[
        IrItem(IrLiteral("1. "), Quantifier(1, 1)),
        IrItem(IrRuleRef("move"), Quantifier(1, 1)),
        IrItem(IrLiteral(" "), Quantifier(1, 1)),
        IrItem(IrRuleRef("move"), Quantifier(1, 1)),
        IrItem(IrLiteral("\n"), Quantifier(1, 1)),
        IrItem(IrRuleRef("root-item"), Quantifier(1, None)),
    ],
    field_map={"move": 1, "move2": 3, "root_item": 5},
    non_semantic_fields=frozenset([]),
)


Move.__grammar__ = RuleSpec(
    rule_name="move",
    class_name="Move",
    parent_class_name="GrammarModel",
    kind="sequence",
    items=[
        IrItem(
            IrGroup(
                IrAlternation(
                    arms=(
                        IrSequence(
                            items=(IrItem(IrRuleRef("pawn"), Quantifier(1, 1)),)
                        ),
                        IrSequence(
                            items=(IrItem(IrRuleRef("nonpawn"), Quantifier(1, 1)),)
                        ),
                        IrSequence(
                            items=(IrItem(IrRuleRef("castle"), Quantifier(1, 1)),)
                        ),
                    )
                )
            ),
            Quantifier(1, 1),
        ),
        IrItem(IrCharClass("+#"), Quantifier(0, 1)),
    ],
    field_map={"kind": 0, "head": 1},
    non_semantic_fields=frozenset([]),
)


Nonpawn.__grammar__ = RuleSpec(
    rule_name="nonpawn",
    class_name="Nonpawn",
    parent_class_name="GrammarModel",
    kind="value_str",
    items=[
        IrItem(IrCharClass("NBKQR"), Quantifier(1, 1)),
        IrItem(IrCharClass("a-h"), Quantifier(0, 1)),
        IrItem(IrCharClass("1-8"), Quantifier(0, 1)),
        IrItem(IrLiteral("x"), Quantifier(0, 1)),
        IrItem(IrCharClass("a-h"), Quantifier(1, 1)),
        IrItem(IrCharClass("1-8"), Quantifier(1, 1)),
    ],
    field_map={},
    non_semantic_fields=frozenset([]),
)


Pawn.__grammar__ = RuleSpec(
    rule_name="pawn",
    class_name="Pawn",
    parent_class_name="GrammarModel",
    kind="value_str",
    items=[
        IrItem(
            IrGroup(
                IrAlternation(
                    arms=(
                        IrSequence(
                            items=(
                                IrItem(IrCharClass("a-h"), Quantifier(1, 1)),
                                IrItem(IrLiteral("x"), Quantifier(1, 1)),
                            )
                        ),
                    )
                )
            ),
            Quantifier(0, 1),
        ),
        IrItem(IrCharClass("a-h"), Quantifier(1, 1)),
        IrItem(IrCharClass("1-8"), Quantifier(1, 1)),
        IrItem(
            IrGroup(
                IrAlternation(
                    arms=(
                        IrSequence(
                            items=(
                                IrItem(IrLiteral("="), Quantifier(1, 1)),
                                IrItem(IrCharClass("NBKQR"), Quantifier(1, 1)),
                            )
                        ),
                    )
                )
            ),
            Quantifier(0, 1),
        ),
    ],
    field_map={},
    non_semantic_fields=frozenset([]),
)


Castle.__grammar__ = RuleSpec(
    rule_name="castle",
    class_name="Castle",
    parent_class_name="GrammarModel",
    kind="value_str",
    items=[
        IrItem(IrLiteral("O-O"), Quantifier(1, 1)),
        IrItem(IrLiteral("-O"), Quantifier(0, 1)),
    ],
    field_map={},
    non_semantic_fields=frozenset([]),
)


RootItem.__grammar__ = RuleSpec(
    rule_name="root-item",
    class_name="RootItem",
    parent_class_name="GrammarModel",
    kind="sequence",
    items=[
        IrItem(IrCharClass("1-9"), Quantifier(1, 1)),
        IrItem(IrCharClass("0-9"), Quantifier(0, 1)),
        IrItem(IrLiteral(". "), Quantifier(1, 1)),
        IrItem(IrRuleRef("move"), Quantifier(1, 1)),
        IrItem(IrLiteral(" "), Quantifier(1, 1)),
        IrItem(IrRuleRef("move"), Quantifier(1, 1)),
        IrItem(IrLiteral("\n"), Quantifier(1, 1)),
    ],
    field_map={"head": 0, "digit": 1, "move": 3, "move2": 5},
    non_semantic_fields=frozenset([]),
)
