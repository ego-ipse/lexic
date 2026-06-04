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
    IrQuantifier,
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
        IrItem(atom=IrLiteral("1. "), quantifier=IrQuantifier(min=1, max=1)),
        IrItem(atom=IrRuleRef("move"), quantifier=IrQuantifier(min=1, max=1)),
        IrItem(atom=IrLiteral(" "), quantifier=IrQuantifier(min=1, max=1)),
        IrItem(atom=IrRuleRef("move"), quantifier=IrQuantifier(min=1, max=1)),
        IrItem(atom=IrLiteral("\n"), quantifier=IrQuantifier(min=1, max=1)),
        IrItem(atom=IrRuleRef("root-item"), quantifier=IrQuantifier(min=1, max=None)),
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
            atom=IrGroup(
                body=IrAlternation(
                    IrSequence(
                        IrItem(
                            atom=IrRuleRef("pawn"),
                            quantifier=IrQuantifier(min=1, max=1),
                        )
                    ),
                    IrSequence(
                        IrItem(
                            atom=IrRuleRef("nonpawn"),
                            quantifier=IrQuantifier(min=1, max=1),
                        )
                    ),
                    IrSequence(
                        IrItem(
                            atom=IrRuleRef("castle"),
                            quantifier=IrQuantifier(min=1, max=1),
                        )
                    ),
                )
            ),
            quantifier=IrQuantifier(min=1, max=1),
        ),
        IrItem(atom=IrCharClass("+#"), quantifier=IrQuantifier(min=0, max=1)),
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
        IrItem(atom=IrCharClass("NBKQR"), quantifier=IrQuantifier(min=1, max=1)),
        IrItem(atom=IrCharClass("a-h"), quantifier=IrQuantifier(min=0, max=1)),
        IrItem(atom=IrCharClass("1-8"), quantifier=IrQuantifier(min=0, max=1)),
        IrItem(atom=IrLiteral("x"), quantifier=IrQuantifier(min=0, max=1)),
        IrItem(atom=IrCharClass("a-h"), quantifier=IrQuantifier(min=1, max=1)),
        IrItem(atom=IrCharClass("1-8"), quantifier=IrQuantifier(min=1, max=1)),
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
            atom=IrGroup(
                body=IrAlternation(
                    IrSequence(
                        IrItem(
                            atom=IrCharClass("a-h"),
                            quantifier=IrQuantifier(min=1, max=1),
                        ),
                        IrItem(
                            atom=IrLiteral("x"), quantifier=IrQuantifier(min=1, max=1)
                        ),
                    )
                )
            ),
            quantifier=IrQuantifier(min=0, max=1),
        ),
        IrItem(atom=IrCharClass("a-h"), quantifier=IrQuantifier(min=1, max=1)),
        IrItem(atom=IrCharClass("1-8"), quantifier=IrQuantifier(min=1, max=1)),
        IrItem(
            atom=IrGroup(
                body=IrAlternation(
                    IrSequence(
                        IrItem(
                            atom=IrLiteral("="), quantifier=IrQuantifier(min=1, max=1)
                        ),
                        IrItem(
                            atom=IrCharClass("NBKQR"),
                            quantifier=IrQuantifier(min=1, max=1),
                        ),
                    )
                )
            ),
            quantifier=IrQuantifier(min=0, max=1),
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
        IrItem(atom=IrLiteral("O-O"), quantifier=IrQuantifier(min=1, max=1)),
        IrItem(atom=IrLiteral("-O"), quantifier=IrQuantifier(min=0, max=1)),
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
        IrItem(atom=IrCharClass("1-9"), quantifier=IrQuantifier(min=1, max=1)),
        IrItem(atom=IrCharClass("0-9"), quantifier=IrQuantifier(min=0, max=1)),
        IrItem(atom=IrLiteral(". "), quantifier=IrQuantifier(min=1, max=1)),
        IrItem(atom=IrRuleRef("move"), quantifier=IrQuantifier(min=1, max=1)),
        IrItem(atom=IrLiteral(" "), quantifier=IrQuantifier(min=1, max=1)),
        IrItem(atom=IrRuleRef("move"), quantifier=IrQuantifier(min=1, max=1)),
        IrItem(atom=IrLiteral("\n"), quantifier=IrQuantifier(min=1, max=1)),
    ],
    field_map={"head": 0, "digit": 1, "move": 3, "move2": 5},
    non_semantic_fields=frozenset([]),
)
