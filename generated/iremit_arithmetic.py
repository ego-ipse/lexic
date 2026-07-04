"""Generated module: iremit_arithmetic. Do not edit; regenerated from grammar."""

from __future__ import annotations

from typing import Annotated, ClassVar, List, Optional

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
    IrRange,
    IrRule,
    IrRuleRef,
    IrSeq,
    IrSequence,
)

Pattern = Annotated[str, StringConstraints(pattern=r"^[\x09-\x0a ]*$")]

Lower = Annotated[str, StringConstraints(pattern=r"^[a-z]$")]

Pattern2 = Annotated[str, StringConstraints(pattern=r"^[0-9_a-z]*$")]

Digit = Annotated[str, StringConstraints(pattern=r"^[0-9]+$")]

Pattern3 = Annotated[str, StringConstraints(pattern=r"^[*-+-/]$")]


class Root(GrammarModel):
    root_item: Annotated[List[RootItem], IrBind(0, "models")]
    __grammar__: ClassVar[IrRule] = IrRule(
        "root",
        IrAlternation(
            IrSequence(IrItem(IrRuleRef("root-item"), IrQuantifier(1, IrNone)))
        ),
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


class Ws(GrammarModel):
    value: Pattern
    __grammar__: ClassVar[IrRule] = IrRule(
        "ws",
        IrAlternation(
            IrSequence(
                IrItem(
                    IrCharClass(IrRange(IrChr(9), IrChr(10)), IrChr(32)),
                    IrQuantifier(0, IrNone),
                )
            )
        ),
        False,
    )


class Term(GrammarModel):
    __grammar__: ClassVar[IrRule] = IrRule(
        "term",
        IrAlternation(
            IrSequence(IrItem(IrRuleRef("ident"))),
            IrSequence(IrItem(IrRuleRef("num"))),
            IrSequence(IrItem(IrRuleRef("term-arm3"))),
        ),
    )


class TermArm3(Term):
    ws: Annotated[Optional[Ws], IrBind(1, "model", False)] = None
    expr: Annotated[Expr, IrBind(2, "model")]
    ws2: Annotated[Optional[Ws], IrBind(4, "model", False)] = None
    __grammar__: ClassVar[IrRule] = IrRule(
        "term-arm3",
        IrAlternation(
            IrSequence(
                IrItem(IrLiteral("(")),
                IrItem(IrRuleRef("ws"), IrQuantifier(0)),
                IrItem(IrRuleRef("expr")),
                IrItem(IrLiteral(")")),
                IrItem(IrRuleRef("ws"), IrQuantifier(0)),
            )
        ),
    )


class Ident(Term):
    lower: Annotated[Lower, IrBind(0, "text")]
    head: Annotated[Pattern2, IrBind(1, "text")]
    ws: Annotated[Optional[Ws], IrBind(2, "model", False)] = None
    __grammar__: ClassVar[IrRule] = IrRule(
        "ident",
        IrAlternation(
            IrSequence(
                IrItem(IrCharClass(IrRange(IrChr(97), IrChr(122)))),
                IrItem(
                    IrCharClass(
                        IrRange(IrChr(48), IrChr(57)),
                        IrChr(95),
                        IrRange(IrChr(97), IrChr(122)),
                    ),
                    IrQuantifier(0, IrNone),
                ),
                IrItem(IrRuleRef("ws"), IrQuantifier(0)),
            )
        ),
    )


class Num(Term):
    digit: Annotated[Digit, IrBind(0, "text")]
    ws: Annotated[Optional[Ws], IrBind(1, "model", False)] = None
    __grammar__: ClassVar[IrRule] = IrRule(
        "num",
        IrAlternation(
            IrSequence(
                IrItem(
                    IrCharClass(IrRange(IrChr(48), IrChr(57))), IrQuantifier(1, IrNone)
                ),
                IrItem(IrRuleRef("ws"), IrQuantifier(0)),
            )
        ),
    )


class RootItem(GrammarModel):
    expr: Annotated[Expr, IrBind(0, "model")]
    ws: Annotated[Optional[Ws], IrBind(2, "model", False)] = None
    term: Annotated[Term, IrBind(3, "model")]
    __grammar__: ClassVar[IrRule] = IrRule(
        "root-item",
        IrAlternation(
            IrSequence(
                IrItem(IrRuleRef("expr")),
                IrItem(IrLiteral("=")),
                IrItem(IrRuleRef("ws"), IrQuantifier(0)),
                IrItem(IrRuleRef("term")),
                IrItem(IrLiteral("\n")),
            )
        ),
    )


class ExprItem(GrammarModel):
    head: Annotated[Pattern3, IrBind(0, "text")]
    term: Annotated[Term, IrBind(1, "model")]
    __grammar__: ClassVar[IrRule] = IrRule(
        "expr-item",
        IrAlternation(
            IrSequence(
                IrItem(
                    IrCharClass(IrRange(IrChr(42), IrChr(43)), IrChr(45), IrChr(47))
                ),
                IrItem(IrRuleRef("term")),
            )
        ),
    )


GRAMMAR: IrAst = IrAst(
    IrSeq(
        IrRule(
            "root",
            IrAlternation(
                IrSequence(
                    IrItem(
                        IrAlternation(
                            IrSequence(
                                IrItem(IrRuleRef("expr")),
                                IrItem(IrLiteral("=")),
                                IrItem(IrRuleRef("ws")),
                                IrItem(IrRuleRef("term")),
                                IrItem(IrLiteral("\n")),
                            )
                        ),
                        IrQuantifier(1, IrNone),
                    )
                )
            ),
        ),
        IrRule(
            "expr",
            IrAlternation(
                IrSequence(
                    IrItem(IrRuleRef("term")),
                    IrItem(
                        IrAlternation(
                            IrSequence(
                                IrItem(
                                    IrCharClass(
                                        IrRange(IrChr(42), IrChr(43)),
                                        IrChr(45),
                                        IrChr(47),
                                    )
                                ),
                                IrItem(IrRuleRef("term")),
                            )
                        ),
                        IrQuantifier(0, IrNone),
                    ),
                )
            ),
        ),
        IrRule(
            "ws",
            IrAlternation(
                IrSequence(
                    IrItem(
                        IrCharClass(IrRange(IrChr(9), IrChr(10)), IrChr(32)),
                        IrQuantifier(0, IrNone),
                    )
                )
            ),
            False,
        ),
        IrRule(
            "term",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("ident"))),
                IrSequence(IrItem(IrRuleRef("num"))),
                IrSequence(
                    IrItem(IrLiteral("(")),
                    IrItem(IrRuleRef("ws")),
                    IrItem(IrRuleRef("expr")),
                    IrItem(IrLiteral(")")),
                    IrItem(IrRuleRef("ws")),
                ),
            ),
        ),
        IrRule(
            "ident",
            IrAlternation(
                IrSequence(
                    IrItem(IrCharClass(IrRange(IrChr(97), IrChr(122)))),
                    IrItem(
                        IrCharClass(
                            IrRange(IrChr(48), IrChr(57)),
                            IrChr(95),
                            IrRange(IrChr(97), IrChr(122)),
                        ),
                        IrQuantifier(0, IrNone),
                    ),
                    IrItem(IrRuleRef("ws")),
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
                    ),
                    IrItem(IrRuleRef("ws")),
                )
            ),
        ),
    ),
    "root",
)

START: str = "root"
