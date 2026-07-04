"""Generated module: anon_68f70d18447b. Do not edit; regenerated from grammar."""

from __future__ import annotations

from typing import Annotated, ClassVar, Optional

from pydantic import StringConstraints

from lexic.base import GrammarModel
from lexic.ir import (
    IrAlternation,
    IrAst,
    IrBind,
    IrCharClass,
    IrChr,
    IrItem,
    IrLiteral,
    IrNone,
    IrQuantifier,
    IrRule,
    IrRuleRef,
    IrSeq,
    IrSequence,
)

Pattern = Annotated[str, StringConstraints(pattern=r"^[\x09 ]*$")]


class Root(GrammarModel):
    ws: Annotated[Optional[Ws], IrBind(0, "model", False)] = None
    value: Annotated[Value, IrBind(1, "model")]
    ws2: Annotated[Optional[Ws], IrBind(2, "model", False)] = None
    __grammar__: ClassVar[IrRule] = IrRule(
        "root",
        IrAlternation(
            IrSequence(
                IrItem(IrRuleRef("ws"), IrQuantifier(0)),
                IrItem(IrRuleRef("value")),
                IrItem(IrRuleRef("ws"), IrQuantifier(0)),
            )
        ),
    )


class Ws(GrammarModel):
    value: Pattern
    __grammar__: ClassVar[IrRule] = IrRule(
        "ws",
        IrAlternation(
            IrSequence(
                IrItem(IrCharClass(IrChr(9), IrChr(32)), IrQuantifier(0, IrNone))
            )
        ),
        False,
    )


class Value(GrammarModel):
    value: str
    __grammar__: ClassVar[IrRule] = IrRule(
        "value", IrAlternation(IrSequence(IrItem(IrLiteral("x"))))
    )


GRAMMAR: IrAst = IrAst(
    IrSeq(
        IrRule(
            "root",
            IrAlternation(
                IrSequence(
                    IrItem(IrRuleRef("ws")),
                    IrItem(IrRuleRef("value")),
                    IrItem(IrRuleRef("ws")),
                )
            ),
        ),
        IrRule(
            "ws",
            IrAlternation(
                IrSequence(
                    IrItem(IrCharClass(IrChr(9), IrChr(32)), IrQuantifier(0, IrNone))
                )
            ),
            False,
        ),
        IrRule("value", IrAlternation(IrSequence(IrItem(IrLiteral("x"))))),
    ),
    "root",
)

START: str = "root"
