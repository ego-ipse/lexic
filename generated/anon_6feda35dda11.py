"""Generated module: anon_6feda35dda11. Do not edit; regenerated from grammar."""

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

Lower = Annotated[str, StringConstraints(pattern=r"^[a-z]+$")]


class Root(GrammarModel):
    term: Annotated[Term, IrBind(0, "model")]
    __grammar__: ClassVar[IrRule] = IrRule(
        "root", IrAlternation(IrSequence(IrItem(IrRuleRef("term"))))
    )


class Term(GrammarModel):
    __grammar__: ClassVar[IrRule] = IrRule(
        "term",
        IrAlternation(
            IrSequence(IrItem(IrRuleRef("num"))), IrSequence(IrItem(IrRuleRef("ident")))
        ),
    )


class Num(Term):
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


class Ident(Term):
    value: Lower
    __grammar__: ClassVar[IrRule] = IrRule(
        "ident",
        IrAlternation(
            IrSequence(
                IrItem(
                    IrCharClass(IrRange(IrChr(97), IrChr(122))), IrQuantifier(1, IrNone)
                )
            )
        ),
    )


GRAMMAR: IrAst = IrAst(
    IrSeq(
        IrRule("root", IrAlternation(IrSequence(IrItem(IrRuleRef("term"))))),
        IrRule(
            "term",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("num"))),
                IrSequence(IrItem(IrRuleRef("ident"))),
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
            "ident",
            IrAlternation(
                IrSequence(
                    IrItem(
                        IrCharClass(IrRange(IrChr(97), IrChr(122))),
                        IrQuantifier(1, IrNone),
                    )
                )
            ),
        ),
    ),
    "root",
)

START: str = "root"
