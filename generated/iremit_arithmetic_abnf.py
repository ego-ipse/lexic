"""Generated module: iremit_arithmetic_abnf. Do not edit; regenerated from grammar."""

from __future__ import annotations

from typing import Annotated, ClassVar, List

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

Pattern = Annotated[str, StringConstraints(pattern=r"^[*-+-/]$")]

Pattern2 = Annotated[str, StringConstraints(pattern=r"^[\x09 ]$")]


class Root(GrammarModel):
    expr: Annotated[Expr, IrBind(0, "model")]
    __grammar__: ClassVar[IrRule] = IrRule(
        "root", IrAlternation(IrSequence(IrItem(IrRuleRef("expr"))))
    )


class Expr(GrammarModel):
    term: Annotated[Term, IrBind(0, "model")]
    expr_item: Annotated[List[ExprItem], IrBind(1, "models")]
    __grammar__: ClassVar[IrRule] = IrRule(
        "expr",
        IrAlternation(
            IrSequence(
                IrItem(IrRuleRef("term")),
                IrItem(IrRuleRef("expr-item"), IrQuantifier(0, IrNone)),
            )
        ),
    )


class Term(GrammarModel):
    num: Annotated[Num, IrBind(0, "model")]
    __grammar__: ClassVar[IrRule] = IrRule(
        "term", IrAlternation(IrSequence(IrItem(IrRuleRef("num"))))
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


class Num(GrammarModel):
    digit: Annotated[List[Digit], IrBind(0, "models")]
    __grammar__: ClassVar[IrRule] = IrRule(
        "num",
        IrAlternation(IrSequence(IrItem(IrRuleRef("digit"), IrQuantifier(1, IrNone)))),
    )


class Digit(GrammarModel):
    value: Annotated[str, StringConstraints(pattern=r"^[0-9]$")]
    __grammar__: ClassVar[IrRule] = IrRule(
        "digit",
        IrAlternation(IrSequence(IrItem(IrCharClass(IrRange(IrChr(48), IrChr(57)))))),
    )


class Wsp(GrammarModel):
    value: Pattern2
    __grammar__: ClassVar[IrRule] = IrRule(
        "wsp",
        IrAlternation(IrSequence(IrItem(IrCharClass(IrChr(9), IrChr(32))))),
        False,
    )


class ExprItem(GrammarModel):
    op: Annotated[Op, IrBind(0, "model")]
    term: Annotated[Term, IrBind(1, "model")]
    __grammar__: ClassVar[IrRule] = IrRule(
        "expr-item",
        IrAlternation(IrSequence(IrItem(IrRuleRef("op")), IrItem(IrRuleRef("term")))),
    )


GRAMMAR: IrAst = IrAst(
    IrSeq(
        IrRule("root", IrAlternation(IrSequence(IrItem(IrRuleRef("expr"))))),
        IrRule(
            "expr",
            IrAlternation(
                IrSequence(
                    IrItem(IrRuleRef("term")),
                    IrItem(
                        IrAlternation(
                            IrSequence(
                                IrItem(IrRuleRef("op")), IrItem(IrRuleRef("term"))
                            )
                        ),
                        IrQuantifier(0, IrNone),
                    ),
                )
            ),
        ),
        IrRule("term", IrAlternation(IrSequence(IrItem(IrRuleRef("num"))))),
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
        IrRule(
            "num",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("digit"), IrQuantifier(1, IrNone)))
            ),
        ),
        IrRule(
            "digit",
            IrAlternation(
                IrSequence(IrItem(IrCharClass(IrRange(IrChr(48), IrChr(57)))))
            ),
        ),
        IrRule(
            "wsp",
            IrAlternation(IrSequence(IrItem(IrCharClass(IrChr(9), IrChr(32))))),
            False,
        ),
    ),
    "root",
)

START: str = "root"
