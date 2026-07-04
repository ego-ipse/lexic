"""Generated module: json_ws. Do not edit; regenerated from grammar."""

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

Pattern = Annotated[str, StringConstraints(pattern=r"^[\x09 ]{0,20}$")]

Pattern2 = Annotated[str, StringConstraints(pattern=r"^[ -!#-\[\]-~\x80-\U0010ffff]$")]

Pattern3 = Annotated[str, StringConstraints(pattern=r'^["\\bfnrt]$')]

Hex = Annotated[str, StringConstraints(pattern=r"^[0-9A-Fa-f]{4}$")]

Pattern4 = Annotated[str, StringConstraints(pattern=r'^(["\\bfnrt]|u[0-9A-Fa-f]{4})$')]

Pattern5 = Annotated[
    str,
    StringConstraints(
        pattern=r'^([ -!#-\[\]-~\x80-\U0010ffff]|\\(["\\bfnrt]|u[0-9A-Fa-f]{4}))*$'
    ),
]

Pattern6 = Annotated[str, StringConstraints(pattern=r"^(true|false|null)$")]

Digit = Annotated[str, StringConstraints(pattern=r"^[0-9]$")]

Pattern7 = Annotated[str, StringConstraints(pattern=r"^[1-9]$")]

Digit2 = Annotated[str, StringConstraints(pattern=r"^[0-9]{0,15}$")]

Pattern8 = Annotated[str, StringConstraints(pattern=r"^([0-9]|[1-9][0-9]{0,15})$")]

Digit3 = Annotated[str, StringConstraints(pattern=r"^[0-9]+$")]

Pattern9 = Annotated[str, StringConstraints(pattern=r"^(\.[0-9]+)?$")]

Pattern10 = Annotated[str, StringConstraints(pattern=r"^[Ee]$")]

Pattern11 = Annotated[str, StringConstraints(pattern=r"^[+-]?$")]

Pattern12 = Annotated[str, StringConstraints(pattern=r"^[1-9]{0,15}$")]

Pattern13 = Annotated[str, StringConstraints(pattern=r"^([Ee][+-]?[0-9][1-9]{0,15})?$")]


class Root(GrammarModel):
    object: Annotated[Object, IrBind(0, "model")]
    __grammar__: ClassVar[IrRule] = IrRule(
        "root", IrAlternation(IrSequence(IrItem(IrRuleRef("object"))))
    )


class Value(GrammarModel):
    __grammar__: ClassVar[IrRule] = IrRule(
        "value",
        IrAlternation(
            IrSequence(IrItem(IrRuleRef("object"))),
            IrSequence(IrItem(IrRuleRef("array"))),
            IrSequence(IrItem(IrRuleRef("string"))),
            IrSequence(IrItem(IrRuleRef("number"))),
            IrSequence(IrItem(IrRuleRef("value-arm5"))),
        ),
    )


class Object(Value):
    ws: Annotated[Optional[Ws], IrBind(1, "model", False)] = None
    object_item2: Annotated[Optional[ObjectItem2], IrBind(2, "model")] = None
    ws2: Annotated[Optional[Ws], IrBind(4, "model", False)] = None
    __grammar__: ClassVar[IrRule] = IrRule(
        "object",
        IrAlternation(
            IrSequence(
                IrItem(IrLiteral("{")),
                IrItem(IrRuleRef("ws"), IrQuantifier(0)),
                IrItem(IrRuleRef("object-item2"), IrQuantifier(0)),
                IrItem(IrLiteral("}")),
                IrItem(IrRuleRef("ws"), IrQuantifier(0)),
            )
        ),
    )


class Ws(GrammarModel):
    value: str
    __grammar__: ClassVar[IrRule] = IrRule(
        "ws",
        IrAlternation(
            IrSequence(),
            IrSequence(IrItem(IrLiteral(" "))),
            IrSequence(
                IrItem(IrLiteral("\n")),
                IrItem(IrCharClass(IrChr(9), IrChr(32)), IrQuantifier(0, 20)),
            ),
        ),
        False,
    )


class String(Value):
    x80_u0010fff: Annotated[Pattern5, IrBind(1, "gtext")]
    ws: Annotated[Optional[Ws], IrBind(3, "model", False)] = None
    __grammar__: ClassVar[IrRule] = IrRule(
        "string",
        IrAlternation(
            IrSequence(
                IrItem(IrLiteral('"')),
                IrItem(
                    IrAlternation(
                        IrSequence(
                            IrItem(
                                IrCharClass(
                                    IrRange(IrChr(32), IrChr(33)),
                                    IrRange(IrChr(35), IrChr(91)),
                                    IrRange(IrChr(93), IrChr(126)),
                                    IrRange(IrChr(128), IrChr(1114111)),
                                )
                            )
                        ),
                        IrSequence(
                            IrItem(IrLiteral("\\")),
                            IrItem(
                                IrAlternation(
                                    IrSequence(
                                        IrItem(
                                            IrCharClass(
                                                IrChr(34),
                                                IrChr(92),
                                                IrChr(98),
                                                IrChr(102),
                                                IrChr(110),
                                                IrChr(114),
                                                IrChr(116),
                                            )
                                        )
                                    ),
                                    IrSequence(
                                        IrItem(IrLiteral("u")),
                                        IrItem(
                                            IrCharClass(
                                                IrRange(IrChr(48), IrChr(57)),
                                                IrRange(IrChr(65), IrChr(70)),
                                                IrRange(IrChr(97), IrChr(102)),
                                            ),
                                            IrQuantifier(4, 4),
                                        ),
                                    ),
                                )
                            ),
                        ),
                    ),
                    IrQuantifier(0, IrNone),
                ),
                IrItem(IrLiteral('"')),
                IrItem(IrRuleRef("ws"), IrQuantifier(0)),
            )
        ),
    )


class ValueArm5(Value):
    true: Annotated[Pattern6, IrBind(0, "gtext")]
    ws: Annotated[Optional[Ws], IrBind(1, "model", False)] = None
    __grammar__: ClassVar[IrRule] = IrRule(
        "value-arm5",
        IrAlternation(
            IrSequence(
                IrItem(
                    IrAlternation(
                        IrSequence(IrItem(IrLiteral("true"))),
                        IrSequence(IrItem(IrLiteral("false"))),
                        IrSequence(IrItem(IrLiteral("null"))),
                    )
                ),
                IrItem(IrRuleRef("ws"), IrQuantifier(0)),
            )
        ),
    )


class Array(Value):
    ws: Annotated[Optional[Ws], IrBind(1, "model", False)] = None
    array_item2: Annotated[Optional[ArrayItem2], IrBind(2, "model")] = None
    ws2: Annotated[Optional[Ws], IrBind(4, "model", False)] = None
    __grammar__: ClassVar[IrRule] = IrRule(
        "array",
        IrAlternation(
            IrSequence(
                IrItem(IrLiteral("[")),
                IrItem(IrRuleRef("ws"), IrQuantifier(0)),
                IrItem(IrRuleRef("array-item2"), IrQuantifier(0)),
                IrItem(IrLiteral("]")),
                IrItem(IrRuleRef("ws"), IrQuantifier(0)),
            )
        ),
    )


class Number(Value):
    sign: Annotated[Optional[str], IrBind(0, "text")] = None
    digit: Annotated[Pattern8, IrBind(1, "gtext")]
    dot: Annotated[Optional[Pattern9], IrBind(2, "gtext")] = None
    ee: Annotated[Optional[Pattern13], IrBind(3, "gtext")] = None
    ws: Annotated[Optional[Ws], IrBind(4, "model", False)] = None
    __grammar__: ClassVar[IrRule] = IrRule(
        "number",
        IrAlternation(
            IrSequence(
                IrItem(IrLiteral("-"), IrQuantifier(0)),
                IrItem(
                    IrAlternation(
                        IrSequence(IrItem(IrCharClass(IrRange(IrChr(48), IrChr(57))))),
                        IrSequence(
                            IrItem(IrCharClass(IrRange(IrChr(49), IrChr(57)))),
                            IrItem(
                                IrCharClass(IrRange(IrChr(48), IrChr(57))),
                                IrQuantifier(0, 15),
                            ),
                        ),
                    )
                ),
                IrItem(
                    IrAlternation(
                        IrSequence(
                            IrItem(IrLiteral(".")),
                            IrItem(
                                IrCharClass(IrRange(IrChr(48), IrChr(57))),
                                IrQuantifier(1, IrNone),
                            ),
                        )
                    ),
                    IrQuantifier(0),
                ),
                IrItem(
                    IrAlternation(
                        IrSequence(
                            IrItem(IrCharClass(IrChr(69), IrChr(101))),
                            IrItem(IrCharClass(IrChr(43), IrChr(45)), IrQuantifier(0)),
                            IrItem(IrCharClass(IrRange(IrChr(48), IrChr(57)))),
                            IrItem(
                                IrCharClass(IrRange(IrChr(49), IrChr(57))),
                                IrQuantifier(0, 15),
                            ),
                        )
                    ),
                    IrQuantifier(0),
                ),
                IrItem(IrRuleRef("ws"), IrQuantifier(0)),
            )
        ),
    )


class ObjectItem(GrammarModel):
    ws: Annotated[Optional[Ws], IrBind(1, "model", False)] = None
    string: Annotated[String, IrBind(2, "model")]
    ws2: Annotated[Optional[Ws], IrBind(4, "model", False)] = None
    value: Annotated[Value, IrBind(5, "model")]
    __grammar__: ClassVar[IrRule] = IrRule(
        "object-item",
        IrAlternation(
            IrSequence(
                IrItem(IrLiteral(",")),
                IrItem(IrRuleRef("ws"), IrQuantifier(0)),
                IrItem(IrRuleRef("string")),
                IrItem(IrLiteral(":")),
                IrItem(IrRuleRef("ws"), IrQuantifier(0)),
                IrItem(IrRuleRef("value")),
            )
        ),
    )


class ObjectItem2(GrammarModel):
    string: Annotated[String, IrBind(0, "model")]
    ws: Annotated[Optional[Ws], IrBind(2, "model", False)] = None
    value: Annotated[Value, IrBind(3, "model")]
    object_item: Annotated[List[ObjectItem], IrBind(4, "models")]
    __grammar__: ClassVar[IrRule] = IrRule(
        "object-item2",
        IrAlternation(
            IrSequence(
                IrItem(IrRuleRef("string")),
                IrItem(IrLiteral(":")),
                IrItem(IrRuleRef("ws"), IrQuantifier(0)),
                IrItem(IrRuleRef("value")),
                IrItem(IrRuleRef("object-item"), IrQuantifier(0, IrNone)),
            )
        ),
    )


class ArrayItem(GrammarModel):
    ws: Annotated[Optional[Ws], IrBind(1, "model", False)] = None
    value: Annotated[Value, IrBind(2, "model")]
    __grammar__: ClassVar[IrRule] = IrRule(
        "array-item",
        IrAlternation(
            IrSequence(
                IrItem(IrLiteral(",")),
                IrItem(IrRuleRef("ws"), IrQuantifier(0)),
                IrItem(IrRuleRef("value")),
            )
        ),
    )


class ArrayItem2(GrammarModel):
    value: Annotated[Value, IrBind(0, "model")]
    array_item: Annotated[List[ArrayItem], IrBind(1, "models")]
    __grammar__: ClassVar[IrRule] = IrRule(
        "array-item2",
        IrAlternation(
            IrSequence(
                IrItem(IrRuleRef("value")),
                IrItem(IrRuleRef("array-item"), IrQuantifier(0, IrNone)),
            )
        ),
    )


GRAMMAR: IrAst = IrAst(
    IrSeq(
        IrRule("root", IrAlternation(IrSequence(IrItem(IrRuleRef("object"))))),
        IrRule(
            "object",
            IrAlternation(
                IrSequence(
                    IrItem(IrLiteral("{")),
                    IrItem(IrRuleRef("ws")),
                    IrItem(
                        IrAlternation(
                            IrSequence(
                                IrItem(IrRuleRef("string")),
                                IrItem(IrLiteral(":")),
                                IrItem(IrRuleRef("ws")),
                                IrItem(IrRuleRef("value")),
                                IrItem(
                                    IrAlternation(
                                        IrSequence(
                                            IrItem(IrLiteral(",")),
                                            IrItem(IrRuleRef("ws")),
                                            IrItem(IrRuleRef("string")),
                                            IrItem(IrLiteral(":")),
                                            IrItem(IrRuleRef("ws")),
                                            IrItem(IrRuleRef("value")),
                                        )
                                    ),
                                    IrQuantifier(0, IrNone),
                                ),
                            )
                        ),
                        IrQuantifier(0),
                    ),
                    IrItem(IrLiteral("}")),
                    IrItem(IrRuleRef("ws")),
                )
            ),
        ),
        IrRule(
            "ws",
            IrAlternation(
                IrSequence(),
                IrSequence(IrItem(IrLiteral(" "))),
                IrSequence(
                    IrItem(IrLiteral("\n")),
                    IrItem(IrCharClass(IrChr(9), IrChr(32)), IrQuantifier(0, 20)),
                ),
            ),
            False,
        ),
        IrRule(
            "string",
            IrAlternation(
                IrSequence(
                    IrItem(IrLiteral('"')),
                    IrItem(
                        IrAlternation(
                            IrSequence(
                                IrItem(
                                    IrCharClass(
                                        IrRange(IrChr(32), IrChr(33)),
                                        IrRange(IrChr(35), IrChr(91)),
                                        IrRange(IrChr(93), IrChr(126)),
                                        IrRange(IrChr(128), IrChr(1114111)),
                                    )
                                )
                            ),
                            IrSequence(
                                IrItem(IrLiteral("\\")),
                                IrItem(
                                    IrAlternation(
                                        IrSequence(
                                            IrItem(
                                                IrCharClass(
                                                    IrChr(34),
                                                    IrChr(92),
                                                    IrChr(98),
                                                    IrChr(102),
                                                    IrChr(110),
                                                    IrChr(114),
                                                    IrChr(116),
                                                )
                                            )
                                        ),
                                        IrSequence(
                                            IrItem(IrLiteral("u")),
                                            IrItem(
                                                IrCharClass(
                                                    IrRange(IrChr(48), IrChr(57)),
                                                    IrRange(IrChr(65), IrChr(70)),
                                                    IrRange(IrChr(97), IrChr(102)),
                                                ),
                                                IrQuantifier(4, 4),
                                            ),
                                        ),
                                    )
                                ),
                            ),
                        ),
                        IrQuantifier(0, IrNone),
                    ),
                    IrItem(IrLiteral('"')),
                    IrItem(IrRuleRef("ws")),
                )
            ),
        ),
        IrRule(
            "value",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("object"))),
                IrSequence(IrItem(IrRuleRef("array"))),
                IrSequence(IrItem(IrRuleRef("string"))),
                IrSequence(IrItem(IrRuleRef("number"))),
                IrSequence(
                    IrItem(
                        IrAlternation(
                            IrSequence(IrItem(IrLiteral("true"))),
                            IrSequence(IrItem(IrLiteral("false"))),
                            IrSequence(IrItem(IrLiteral("null"))),
                        )
                    ),
                    IrItem(IrRuleRef("ws")),
                ),
            ),
        ),
        IrRule(
            "array",
            IrAlternation(
                IrSequence(
                    IrItem(IrLiteral("[")),
                    IrItem(IrRuleRef("ws")),
                    IrItem(
                        IrAlternation(
                            IrSequence(
                                IrItem(IrRuleRef("value")),
                                IrItem(
                                    IrAlternation(
                                        IrSequence(
                                            IrItem(IrLiteral(",")),
                                            IrItem(IrRuleRef("ws")),
                                            IrItem(IrRuleRef("value")),
                                        )
                                    ),
                                    IrQuantifier(0, IrNone),
                                ),
                            )
                        ),
                        IrQuantifier(0),
                    ),
                    IrItem(IrLiteral("]")),
                    IrItem(IrRuleRef("ws")),
                )
            ),
        ),
        IrRule(
            "number",
            IrAlternation(
                IrSequence(
                    IrItem(IrLiteral("-"), IrQuantifier(0)),
                    IrItem(
                        IrAlternation(
                            IrSequence(
                                IrItem(IrCharClass(IrRange(IrChr(48), IrChr(57))))
                            ),
                            IrSequence(
                                IrItem(IrCharClass(IrRange(IrChr(49), IrChr(57)))),
                                IrItem(
                                    IrCharClass(IrRange(IrChr(48), IrChr(57))),
                                    IrQuantifier(0, 15),
                                ),
                            ),
                        )
                    ),
                    IrItem(
                        IrAlternation(
                            IrSequence(
                                IrItem(IrLiteral(".")),
                                IrItem(
                                    IrCharClass(IrRange(IrChr(48), IrChr(57))),
                                    IrQuantifier(1, IrNone),
                                ),
                            )
                        ),
                        IrQuantifier(0),
                    ),
                    IrItem(
                        IrAlternation(
                            IrSequence(
                                IrItem(IrCharClass(IrChr(69), IrChr(101))),
                                IrItem(
                                    IrCharClass(IrChr(43), IrChr(45)), IrQuantifier(0)
                                ),
                                IrItem(IrCharClass(IrRange(IrChr(48), IrChr(57)))),
                                IrItem(
                                    IrCharClass(IrRange(IrChr(49), IrChr(57))),
                                    IrQuantifier(0, 15),
                                ),
                            )
                        ),
                        IrQuantifier(0),
                    ),
                    IrItem(IrRuleRef("ws")),
                )
            ),
        ),
    ),
    "root",
)

START: str = "root"
