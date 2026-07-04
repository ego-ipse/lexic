"""Generated module: anon_ebd23fd13e62. Do not edit; regenerated from grammar."""

from __future__ import annotations

from typing import Annotated, ClassVar, Optional

from lexic.base import GrammarModel
from lexic.ir import (
    IrAlternation,
    IrAst,
    IrBind,
    IrItem,
    IrLiteral,
    IrQuantifier,
    IrRule,
    IrRuleRef,
    IrSeq,
    IrSequence,
)


class Root(GrammarModel):
    thing: Annotated[Optional[Thing], IrBind(1, "model")] = None
    lit: Annotated[Optional[str], IrBind(2, "text")] = None
    __grammar__: ClassVar[IrRule] = IrRule(
        "root",
        IrAlternation(
            IrSequence(
                IrItem(IrLiteral("a")),
                IrItem(IrRuleRef("thing"), IrQuantifier(0)),
                IrItem(IrLiteral("!"), IrQuantifier(0)),
                IrItem(IrLiteral("b")),
            )
        ),
    )


class Thing(GrammarModel):
    value: str
    __grammar__: ClassVar[IrRule] = IrRule(
        "thing", IrAlternation(IrSequence(IrItem(IrLiteral("T"))))
    )


GRAMMAR: IrAst = IrAst(
    IrSeq(
        IrRule(
            "root",
            IrAlternation(
                IrSequence(
                    IrItem(IrLiteral("a")),
                    IrItem(IrRuleRef("thing"), IrQuantifier(0)),
                    IrItem(IrLiteral("!"), IrQuantifier(0)),
                    IrItem(IrLiteral("b")),
                )
            ),
        ),
        IrRule("thing", IrAlternation(IrSequence(IrItem(IrLiteral("T"))))),
    ),
    "root",
)

START: str = "root"
