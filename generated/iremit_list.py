"""Generated module: iremit_list. Do not edit; regenerated from grammar."""

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
    IrLiteral,
    IrNone,
    IrQuantifier,
    IrRange,
    IrRule,
    IrRuleRef,
    IrSeq,
    IrSequence,
)

Pattern = Annotated[
    str, StringConstraints(pattern=r"^[\x00-\x09\x0e-\x84\x86-‧\u202a-\U0010ffff]+$")
]


class Root(GrammarModel):
    item: Annotated[List[Item], IrBind(0, "models")]
    __grammar__: ClassVar[IrRule] = IrRule(
        "root",
        IrAlternation(IrSequence(IrItem(IrRuleRef("item"), IrQuantifier(1, IrNone)))),
    )


class Item(GrammarModel):
    value: str
    __grammar__: ClassVar[IrRule] = IrRule(
        "item",
        IrAlternation(
            IrSequence(
                IrItem(IrLiteral("- ")),
                IrItem(
                    IrCharClass(
                        IrRange(IrChr(0), IrChr(9)),
                        IrRange(IrChr(14), IrChr(132)),
                        IrRange(IrChr(134), IrChr(8231)),
                        IrRange(IrChr(8234), IrChr(1114111)),
                    ),
                    IrQuantifier(1, IrNone),
                ),
                IrItem(IrLiteral("\n")),
            )
        ),
    )


GRAMMAR: IrAst = IrAst(
    IrSeq(
        IrRule(
            "root",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("item"), IrQuantifier(1, IrNone)))
            ),
        ),
        IrRule(
            "item",
            IrAlternation(
                IrSequence(
                    IrItem(IrLiteral("- ")),
                    IrItem(
                        IrCharClass(
                            IrRange(IrChr(0), IrChr(9)),
                            IrRange(IrChr(14), IrChr(132)),
                            IrRange(IrChr(134), IrChr(8231)),
                            IrRange(IrChr(8234), IrChr(1114111)),
                        ),
                        IrQuantifier(1, IrNone),
                    ),
                    IrItem(IrLiteral("\n")),
                )
            ),
        ),
    ),
    "root",
)

START: str = "root"
