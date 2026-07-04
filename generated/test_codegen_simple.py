"""Generated module: test_codegen_simple. Do not edit; regenerated from grammar."""

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


class Greet(GrammarModel):
    value: str
    __grammar__: ClassVar[IrRule] = IrRule(
        "greet", IrAlternation(IrSequence(IrItem(IrLiteral("hi"))))
    )


GRAMMAR: IrAst = IrAst(
    IrSeq(IrRule("greet", IrAlternation(IrSequence(IrItem(IrLiteral("hi")))))), "greet"
)

START: str = "greet"
