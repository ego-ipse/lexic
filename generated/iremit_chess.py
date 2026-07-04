"""Generated module: iremit_chess. Do not edit; regenerated from grammar."""

from __future__ import annotations

from typing import Annotated, ClassVar, List, Optional, Union

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

Pattern = Annotated[str, StringConstraints(pattern=r"^[#+]?$")]

Pattern2 = Annotated[str, StringConstraints(pattern=r"^[a-h]$")]

Pattern3 = Annotated[str, StringConstraints(pattern=r"^([a-h]x)?$")]

Pattern4 = Annotated[str, StringConstraints(pattern=r"^[1-8]$")]

Pattern5 = Annotated[str, StringConstraints(pattern=r"^[BKNQ-R]$")]

Pattern6 = Annotated[str, StringConstraints(pattern=r"^(=[BKNQ-R])?$")]

Pattern7 = Annotated[str, StringConstraints(pattern=r"^[a-h]?$")]

Pattern8 = Annotated[str, StringConstraints(pattern=r"^[1-8]?$")]

Pattern9 = Annotated[str, StringConstraints(pattern=r"^[1-9]$")]

Digit = Annotated[str, StringConstraints(pattern=r"^[0-9]?$")]


class Root(GrammarModel):
    move: Annotated[Move, IrBind(1, "model")]
    move2: Annotated[Move, IrBind(3, "model")]
    root_item: Annotated[List[RootItem], IrBind(5, "models")]
    __grammar__: ClassVar[IrRule] = IrRule(
        "root",
        IrAlternation(
            IrSequence(
                IrItem(IrLiteral("1. ")),
                IrItem(IrRuleRef("move")),
                IrItem(IrLiteral(" ")),
                IrItem(IrRuleRef("move")),
                IrItem(IrLiteral("\n")),
                IrItem(IrRuleRef("root-item"), IrQuantifier(1, IrNone)),
            )
        ),
    )


class Move(GrammarModel):
    kind: Annotated[Union[Pawn, Nonpawn, Castle], IrBind(0, "model")]
    head: Annotated[Optional[Pattern], IrBind(1, "text")] = None
    __grammar__: ClassVar[IrRule] = IrRule(
        "move",
        IrAlternation(
            IrSequence(
                IrItem(
                    IrAlternation(
                        IrSequence(IrItem(IrRuleRef("pawn"))),
                        IrSequence(IrItem(IrRuleRef("nonpawn"))),
                        IrSequence(IrItem(IrRuleRef("castle"))),
                    )
                ),
                IrItem(IrCharClass(IrChr(35), IrChr(43)), IrQuantifier(0)),
            )
        ),
    )


class Pawn(GrammarModel):
    value: str
    __grammar__: ClassVar[IrRule] = IrRule(
        "pawn",
        IrAlternation(
            IrSequence(
                IrItem(
                    IrAlternation(
                        IrSequence(
                            IrItem(IrCharClass(IrRange(IrChr(97), IrChr(104)))),
                            IrItem(IrLiteral("x")),
                        )
                    ),
                    IrQuantifier(0),
                ),
                IrItem(IrCharClass(IrRange(IrChr(97), IrChr(104)))),
                IrItem(IrCharClass(IrRange(IrChr(49), IrChr(56)))),
                IrItem(
                    IrAlternation(
                        IrSequence(
                            IrItem(IrLiteral("=")),
                            IrItem(
                                IrCharClass(
                                    IrChr(66),
                                    IrChr(75),
                                    IrChr(78),
                                    IrRange(IrChr(81), IrChr(82)),
                                )
                            ),
                        )
                    ),
                    IrQuantifier(0),
                ),
            )
        ),
    )


class Nonpawn(GrammarModel):
    value: str
    __grammar__: ClassVar[IrRule] = IrRule(
        "nonpawn",
        IrAlternation(
            IrSequence(
                IrItem(
                    IrCharClass(
                        IrChr(66), IrChr(75), IrChr(78), IrRange(IrChr(81), IrChr(82))
                    )
                ),
                IrItem(IrCharClass(IrRange(IrChr(97), IrChr(104))), IrQuantifier(0)),
                IrItem(IrCharClass(IrRange(IrChr(49), IrChr(56))), IrQuantifier(0)),
                IrItem(IrLiteral("x"), IrQuantifier(0)),
                IrItem(IrCharClass(IrRange(IrChr(97), IrChr(104)))),
                IrItem(IrCharClass(IrRange(IrChr(49), IrChr(56)))),
            )
        ),
    )


class Castle(GrammarModel):
    value: str
    __grammar__: ClassVar[IrRule] = IrRule(
        "castle",
        IrAlternation(
            IrSequence(
                IrItem(IrLiteral("O-O")), IrItem(IrLiteral("-O"), IrQuantifier(0))
            )
        ),
    )


class RootItem(GrammarModel):
    head: Annotated[Pattern9, IrBind(0, "text")]
    digit: Annotated[Optional[Digit], IrBind(1, "text")] = None
    move: Annotated[Move, IrBind(3, "model")]
    move2: Annotated[Move, IrBind(5, "model")]
    __grammar__: ClassVar[IrRule] = IrRule(
        "root-item",
        IrAlternation(
            IrSequence(
                IrItem(IrCharClass(IrRange(IrChr(49), IrChr(57)))),
                IrItem(IrCharClass(IrRange(IrChr(48), IrChr(57))), IrQuantifier(0)),
                IrItem(IrLiteral(". ")),
                IrItem(IrRuleRef("move")),
                IrItem(IrLiteral(" ")),
                IrItem(IrRuleRef("move")),
                IrItem(IrLiteral("\n")),
            )
        ),
    )


GRAMMAR: IrAst = IrAst(
    IrSeq(
        IrRule(
            "root",
            IrAlternation(
                IrSequence(
                    IrItem(IrLiteral("1. ")),
                    IrItem(IrRuleRef("move")),
                    IrItem(IrLiteral(" ")),
                    IrItem(IrRuleRef("move")),
                    IrItem(IrLiteral("\n")),
                    IrItem(
                        IrAlternation(
                            IrSequence(
                                IrItem(IrCharClass(IrRange(IrChr(49), IrChr(57)))),
                                IrItem(
                                    IrCharClass(IrRange(IrChr(48), IrChr(57))),
                                    IrQuantifier(0),
                                ),
                                IrItem(IrLiteral(". ")),
                                IrItem(IrRuleRef("move")),
                                IrItem(IrLiteral(" ")),
                                IrItem(IrRuleRef("move")),
                                IrItem(IrLiteral("\n")),
                            )
                        ),
                        IrQuantifier(1, IrNone),
                    ),
                )
            ),
        ),
        IrRule(
            "move",
            IrAlternation(
                IrSequence(
                    IrItem(
                        IrAlternation(
                            IrSequence(IrItem(IrRuleRef("pawn"))),
                            IrSequence(IrItem(IrRuleRef("nonpawn"))),
                            IrSequence(IrItem(IrRuleRef("castle"))),
                        )
                    ),
                    IrItem(IrCharClass(IrChr(35), IrChr(43)), IrQuantifier(0)),
                )
            ),
        ),
        IrRule(
            "pawn",
            IrAlternation(
                IrSequence(
                    IrItem(
                        IrAlternation(
                            IrSequence(
                                IrItem(IrCharClass(IrRange(IrChr(97), IrChr(104)))),
                                IrItem(IrLiteral("x")),
                            )
                        ),
                        IrQuantifier(0),
                    ),
                    IrItem(IrCharClass(IrRange(IrChr(97), IrChr(104)))),
                    IrItem(IrCharClass(IrRange(IrChr(49), IrChr(56)))),
                    IrItem(
                        IrAlternation(
                            IrSequence(
                                IrItem(IrLiteral("=")),
                                IrItem(
                                    IrCharClass(
                                        IrChr(66),
                                        IrChr(75),
                                        IrChr(78),
                                        IrRange(IrChr(81), IrChr(82)),
                                    )
                                ),
                            )
                        ),
                        IrQuantifier(0),
                    ),
                )
            ),
        ),
        IrRule(
            "nonpawn",
            IrAlternation(
                IrSequence(
                    IrItem(
                        IrCharClass(
                            IrChr(66),
                            IrChr(75),
                            IrChr(78),
                            IrRange(IrChr(81), IrChr(82)),
                        )
                    ),
                    IrItem(
                        IrCharClass(IrRange(IrChr(97), IrChr(104))), IrQuantifier(0)
                    ),
                    IrItem(IrCharClass(IrRange(IrChr(49), IrChr(56))), IrQuantifier(0)),
                    IrItem(IrLiteral("x"), IrQuantifier(0)),
                    IrItem(IrCharClass(IrRange(IrChr(97), IrChr(104)))),
                    IrItem(IrCharClass(IrRange(IrChr(49), IrChr(56)))),
                )
            ),
        ),
        IrRule(
            "castle",
            IrAlternation(
                IrSequence(
                    IrItem(IrLiteral("O-O")), IrItem(IrLiteral("-O"), IrQuantifier(0))
                )
            ),
        ),
    ),
    "root",
)

START: str = "root"
