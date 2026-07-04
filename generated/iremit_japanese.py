"""Generated module: iremit_japanese. Do not edit; regenerated from grammar."""

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

Pattern = Annotated[str, StringConstraints(pattern=r"^[ぁ-ゟ]$")]

Pattern2 = Annotated[str, StringConstraints(pattern=r"^[ァ-ヿ]$")]

Pattern3 = Annotated[str, StringConstraints(pattern=r"^[、-〾]$")]

Pattern4 = Annotated[str, StringConstraints(pattern=r"^[一-鿿]$")]

Pattern5 = Annotated[str, StringConstraints(pattern=r"^[\x09-\x0a ]$")]


class Root(GrammarModel):
    jp_char: Annotated[List[JpChar], IrBind(0, "models")]
    root_item: Annotated[List[RootItem], IrBind(1, "models")]
    __grammar__: ClassVar[IrRule] = IrRule(
        "root",
        IrAlternation(
            IrSequence(
                IrItem(IrRuleRef("jp-char"), IrQuantifier(1, IrNone)),
                IrItem(IrRuleRef("root-item"), IrQuantifier(0, IrNone)),
            )
        ),
    )


class JpChar(GrammarModel):
    __grammar__: ClassVar[IrRule] = IrRule(
        "jp-char",
        IrAlternation(
            IrSequence(IrItem(IrRuleRef("hiragana"))),
            IrSequence(IrItem(IrRuleRef("katakana"))),
            IrSequence(IrItem(IrRuleRef("punctuation"))),
            IrSequence(IrItem(IrRuleRef("cjk"))),
        ),
    )


class Hiragana(JpChar):
    value: Pattern
    __grammar__: ClassVar[IrRule] = IrRule(
        "hiragana",
        IrAlternation(
            IrSequence(IrItem(IrCharClass(IrRange(IrChr(12353), IrChr(12447)))))
        ),
    )


class Katakana(JpChar):
    value: Pattern2
    __grammar__: ClassVar[IrRule] = IrRule(
        "katakana",
        IrAlternation(
            IrSequence(IrItem(IrCharClass(IrRange(IrChr(12449), IrChr(12543)))))
        ),
    )


class Punctuation(JpChar):
    value: Pattern3
    __grammar__: ClassVar[IrRule] = IrRule(
        "punctuation",
        IrAlternation(
            IrSequence(IrItem(IrCharClass(IrRange(IrChr(12289), IrChr(12350)))))
        ),
    )


class Cjk(JpChar):
    value: Pattern4
    __grammar__: ClassVar[IrRule] = IrRule(
        "cjk",
        IrAlternation(
            IrSequence(IrItem(IrCharClass(IrRange(IrChr(19968), IrChr(40959)))))
        ),
    )


class RootItem(GrammarModel):
    head: Annotated[Pattern5, IrBind(0, "text")]
    jp_char: Annotated[List[JpChar], IrBind(1, "models")]
    __grammar__: ClassVar[IrRule] = IrRule(
        "root-item",
        IrAlternation(
            IrSequence(
                IrItem(IrCharClass(IrRange(IrChr(9), IrChr(10)), IrChr(32))),
                IrItem(IrRuleRef("jp-char"), IrQuantifier(1, IrNone)),
            )
        ),
    )


GRAMMAR: IrAst = IrAst(
    IrSeq(
        IrRule(
            "root",
            IrAlternation(
                IrSequence(
                    IrItem(IrRuleRef("jp-char"), IrQuantifier(1, IrNone)),
                    IrItem(
                        IrAlternation(
                            IrSequence(
                                IrItem(
                                    IrCharClass(IrRange(IrChr(9), IrChr(10)), IrChr(32))
                                ),
                                IrItem(IrRuleRef("jp-char"), IrQuantifier(1, IrNone)),
                            )
                        ),
                        IrQuantifier(0, IrNone),
                    ),
                )
            ),
        ),
        IrRule(
            "jp-char",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("hiragana"))),
                IrSequence(IrItem(IrRuleRef("katakana"))),
                IrSequence(IrItem(IrRuleRef("punctuation"))),
                IrSequence(IrItem(IrRuleRef("cjk"))),
            ),
        ),
        IrRule(
            "hiragana",
            IrAlternation(
                IrSequence(IrItem(IrCharClass(IrRange(IrChr(12353), IrChr(12447)))))
            ),
        ),
        IrRule(
            "katakana",
            IrAlternation(
                IrSequence(IrItem(IrCharClass(IrRange(IrChr(12449), IrChr(12543)))))
            ),
        ),
        IrRule(
            "punctuation",
            IrAlternation(
                IrSequence(IrItem(IrCharClass(IrRange(IrChr(12289), IrChr(12350)))))
            ),
        ),
        IrRule(
            "cjk",
            IrAlternation(
                IrSequence(IrItem(IrCharClass(IrRange(IrChr(19968), IrChr(40959)))))
            ),
        ),
    ),
    "root",
)

START: str = "root"
