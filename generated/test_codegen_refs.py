"""Generated module: test_codegen_refs. Do not edit; regenerated from grammar."""

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

Lower = Annotated[str, StringConstraints(pattern=r"^[a-z]+$")]


class Root(GrammarModel):
    expr: Annotated[Expr, IrBind(0, "model")]
    __grammar__: ClassVar[IrRule] = IrRule(
        "root", IrAlternation(IrSequence(IrItem(IrRuleRef("expr"))))
    )


class Expr(GrammarModel):
    value: Lower
    __grammar__: ClassVar[IrRule] = IrRule(
        "expr",
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
        IrRule("root", IrAlternation(IrSequence(IrItem(IrRuleRef("expr"))))),
        IrRule(
            "expr",
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
