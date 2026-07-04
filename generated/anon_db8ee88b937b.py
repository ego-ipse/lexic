"""Generated module: anon_db8ee88b937b. Do not edit; regenerated from grammar."""

from __future__ import annotations

from typing import Annotated, ClassVar, Optional

from lexic.base import GrammarModel
from lexic.ir import (
    IrAlternation,
    IrAst,
    IrBind,
    IrItem,
    IrLiteral,
    IrRule,
    IrRuleRef,
    IrSeq,
    IrSequence,
)


class Root(GrammarModel):
    pair: Annotated[Pair, IrBind(1, "model")]
    __grammar__: ClassVar[IrRule] = IrRule(
        "root",
        IrAlternation(
            IrSequence(
                IrItem(IrLiteral("<")),
                IrItem(IrRuleRef("pair")),
                IrItem(IrLiteral(">")),
            )
        ),
    )


class Pair(GrammarModel):
    a: Annotated[Optional[A], IrBind(0, "model")] = None
    b: Annotated[Optional[B], IrBind(1, "model")] = None
    __grammar__: ClassVar[IrRule] = IrRule(
        "pair",
        IrAlternation(
            IrSequence(IrItem(IrRuleRef("a")), IrItem(IrRuleRef("b"))), IrSequence()
        ),
    )


class A(GrammarModel):
    value: str
    __grammar__: ClassVar[IrRule] = IrRule(
        "a", IrAlternation(IrSequence(IrItem(IrLiteral("a"))))
    )


class B(GrammarModel):
    value: str
    __grammar__: ClassVar[IrRule] = IrRule(
        "b", IrAlternation(IrSequence(IrItem(IrLiteral("b"))))
    )


GRAMMAR: IrAst = IrAst(
    IrSeq(
        IrRule(
            "root",
            IrAlternation(
                IrSequence(
                    IrItem(IrLiteral("<")),
                    IrItem(IrRuleRef("pair")),
                    IrItem(IrLiteral(">")),
                )
            ),
        ),
        IrRule(
            "pair",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("a")), IrItem(IrRuleRef("b"))), IrSequence()
            ),
        ),
        IrRule("a", IrAlternation(IrSequence(IrItem(IrLiteral("a"))))),
        IrRule("b", IrAlternation(IrSequence(IrItem(IrLiteral("b"))))),
    ),
    "root",
)

START: str = "root"
