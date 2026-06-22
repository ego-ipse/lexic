"""Generated module: chess. Do not edit; regenerated from grammar."""

from __future__ import annotations

from typing import Annotated, List, Optional, Union

from pydantic import StringConstraints

from lexic.base import GrammarModel
from lexic.ir.base import IrNone, IrStr
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
        IrItem(IrLiteral("1. "), IrQuantifier(1, 1)),
        IrItem(IrRuleRef("move"), IrQuantifier(1, 1)),
        IrItem(IrLiteral(" "), IrQuantifier(1, 1)),
        IrItem(IrRuleRef("move"), IrQuantifier(1, 1)),
        IrItem(IrLiteral("\n"), IrQuantifier(1, 1)),
        IrItem(IrRuleRef("root-item"), IrQuantifier(1, IrNone)),
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
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("pawn"), IrQuantifier(1, 1))),
                IrSequence(IrItem(IrRuleRef("nonpawn"), IrQuantifier(1, 1))),
                IrSequence(IrItem(IrRuleRef("castle"), IrQuantifier(1, 1))),
            ),
            IrQuantifier(1, 1),
        ),
        IrItem(IrCharClass(IrStr("+#")), IrQuantifier(0, 1)),
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
        IrItem(IrCharClass(IrStr("NBKQR")), IrQuantifier(1, 1)),
        IrItem(IrCharClass(IrRange(IrChr(97), IrChr(104))), IrQuantifier(0, 1)),
        IrItem(IrCharClass(IrRange(IrChr(49), IrChr(56))), IrQuantifier(0, 1)),
        IrItem(IrLiteral("x"), IrQuantifier(0, 1)),
        IrItem(IrCharClass(IrRange(IrChr(97), IrChr(104))), IrQuantifier(1, 1)),
        IrItem(IrCharClass(IrRange(IrChr(49), IrChr(56))), IrQuantifier(1, 1)),
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
            IrAlternation(
                IrSequence(
                    IrItem(
                        IrCharClass(IrRange(IrChr(97), IrChr(104))), IrQuantifier(1, 1)
                    ),
                    IrItem(IrLiteral("x"), IrQuantifier(1, 1)),
                )
            ),
            IrQuantifier(0, 1),
        ),
        IrItem(IrCharClass(IrRange(IrChr(97), IrChr(104))), IrQuantifier(1, 1)),
        IrItem(IrCharClass(IrRange(IrChr(49), IrChr(56))), IrQuantifier(1, 1)),
        IrItem(
            IrAlternation(
                IrSequence(
                    IrItem(IrLiteral("="), IrQuantifier(1, 1)),
                    IrItem(IrCharClass(IrStr("NBKQR")), IrQuantifier(1, 1)),
                )
            ),
            IrQuantifier(0, 1),
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
        IrItem(IrLiteral("O-O"), IrQuantifier(1, 1)),
        IrItem(IrLiteral("-O"), IrQuantifier(0, 1)),
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
        IrItem(IrCharClass(IrRange(IrChr(49), IrChr(57))), IrQuantifier(1, 1)),
        IrItem(IrCharClass(IrRange(IrChr(48), IrChr(57))), IrQuantifier(0, 1)),
        IrItem(IrLiteral(". "), IrQuantifier(1, 1)),
        IrItem(IrRuleRef("move"), IrQuantifier(1, 1)),
        IrItem(IrLiteral(" "), IrQuantifier(1, 1)),
        IrItem(IrRuleRef("move"), IrQuantifier(1, 1)),
        IrItem(IrLiteral("\n"), IrQuantifier(1, 1)),
    ],
    field_map={"head": 0, "digit": 1, "move": 3, "move2": 5},
    non_semantic_fields=frozenset([]),
)
