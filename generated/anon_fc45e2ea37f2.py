"""Generated module: anon_fc45e2ea37f2. Do not edit; regenerated from grammar."""

from __future__ import annotations

from typing import ClassVar

from lexic.base import GrammarModel
from lexic.ir import (
    IrAlternation,
    IrAst,
    IrItem,
    IrLiteral,
    IrRule,
    IrSeq,
    IrSequence,
)


class Root(GrammarModel):
    value: str
    __grammar__: ClassVar[IrRule] = IrRule(
        "root", IrAlternation(IrSequence(IrItem(IrLiteral("x"))))
    )


GRAMMAR: IrAst = IrAst(
    IrSeq(IrRule("root", IrAlternation(IrSequence(IrItem(IrLiteral("x")))))), "root"
)

START: str = "root"
