"""Generated module: anon_2a86f1d106ca. Do not edit; regenerated from grammar."""

from __future__ import annotations

from typing import Annotated, ClassVar, Literal

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

Letter = Annotated[str, StringConstraints(pattern=r"^[A-Za-z]+$")]


class Greeting(GrammarModel):
    salutation: Annotated[Salutation, IrBind(0, "model")]
    name: Annotated[Name, IrBind(2, "model")]
    __grammar__: ClassVar[IrRule] = IrRule(
        "greeting",
        IrAlternation(
            IrSequence(
                IrItem(IrRuleRef("salutation")),
                IrItem(IrLiteral(" ")),
                IrItem(IrRuleRef("name")),
                IrItem(IrLiteral("!")),
            )
        ),
    )


class Salutation(GrammarModel):
    value: Literal["Hello", "Hi", "Hey"]
    __grammar__: ClassVar[IrRule] = IrRule(
        "salutation",
        IrAlternation(
            IrSequence(IrItem(IrLiteral("Hello"))),
            IrSequence(IrItem(IrLiteral("Hi"))),
            IrSequence(IrItem(IrLiteral("Hey"))),
        ),
    )


class Name(GrammarModel):
    value: Letter
    __grammar__: ClassVar[IrRule] = IrRule(
        "name",
        IrAlternation(
            IrSequence(
                IrItem(
                    IrCharClass(
                        IrRange(IrChr(65), IrChr(90)), IrRange(IrChr(97), IrChr(122))
                    ),
                    IrQuantifier(1, IrNone),
                )
            )
        ),
    )


GRAMMAR: IrAst = IrAst(
    IrSeq(
        IrRule(
            "greeting",
            IrAlternation(
                IrSequence(
                    IrItem(IrRuleRef("salutation")),
                    IrItem(IrLiteral(" ")),
                    IrItem(IrRuleRef("name")),
                    IrItem(IrLiteral("!")),
                )
            ),
        ),
        IrRule(
            "salutation",
            IrAlternation(
                IrSequence(IrItem(IrLiteral("Hello"))),
                IrSequence(IrItem(IrLiteral("Hi"))),
                IrSequence(IrItem(IrLiteral("Hey"))),
            ),
        ),
        IrRule(
            "name",
            IrAlternation(
                IrSequence(
                    IrItem(
                        IrCharClass(
                            IrRange(IrChr(65), IrChr(90)),
                            IrRange(IrChr(97), IrChr(122)),
                        ),
                        IrQuantifier(1, IrNone),
                    )
                )
            ),
        ),
    ),
    "greeting",
)

START: str = "greeting"
