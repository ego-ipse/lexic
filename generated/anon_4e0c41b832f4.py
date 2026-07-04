"""Generated module: anon_4e0c41b832f4. Do not edit; regenerated from grammar."""

from __future__ import annotations

from typing import Annotated, ClassVar

from pydantic import StringConstraints

from lexic.base import GrammarModel
from lexic.ir import (
    IrAlternation,
    IrAst,
    IrBind,
    IrCharClass,
    IrChr,
    IrItem,
    IrNone,
    IrQuantifier,
    IrRange,
    IrRule,
    IrRuleRef,
    IrSeq,
    IrSequence,
)

Digit = Annotated[str, StringConstraints(pattern=r"^[0-9]+$")]

Pattern = Annotated[str, StringConstraints(pattern=r"^[*-+-/]$")]


class Expr(GrammarModel):
    num: Annotated[Num, IrBind(0, "model")]
    op: Annotated[Op, IrBind(1, "model")]
    num2: Annotated[Num, IrBind(2, "model")]
    __grammar__: ClassVar[IrRule] = IrRule(
        "expr",
        IrAlternation(
            IrSequence(
                IrItem(IrRuleRef("num")),
                IrItem(IrRuleRef("op")),
                IrItem(IrRuleRef("num")),
            )
        ),
    )


class Num(GrammarModel):
    value: Digit
    __grammar__: ClassVar[IrRule] = IrRule(
        "num",
        IrAlternation(
            IrSequence(
                IrItem(
                    IrCharClass(IrRange(IrChr(48), IrChr(57))), IrQuantifier(1, IrNone)
                )
            )
        ),
    )


class Op(GrammarModel):
    value: Pattern
    __grammar__: ClassVar[IrRule] = IrRule(
        "op",
        IrAlternation(
            IrSequence(
                IrItem(IrCharClass(IrRange(IrChr(42), IrChr(43)), IrChr(45), IrChr(47)))
            )
        ),
    )


GRAMMAR: IrAst = IrAst(
    IrSeq(
        IrRule(
            "expr",
            IrAlternation(
                IrSequence(
                    IrItem(IrRuleRef("num")),
                    IrItem(IrRuleRef("op")),
                    IrItem(IrRuleRef("num")),
                )
            ),
        ),
        IrRule(
            "num",
            IrAlternation(
                IrSequence(
                    IrItem(
                        IrCharClass(IrRange(IrChr(48), IrChr(57))),
                        IrQuantifier(1, IrNone),
                    )
                )
            ),
        ),
        IrRule(
            "op",
            IrAlternation(
                IrSequence(
                    IrItem(
                        IrCharClass(IrRange(IrChr(42), IrChr(43)), IrChr(45), IrChr(47))
                    )
                )
            ),
        ),
    ),
    "expr",
)

START: str = "expr"
