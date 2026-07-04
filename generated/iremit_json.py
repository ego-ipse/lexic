"""Generated module: iremit_json. Do not edit; regenerated from grammar."""

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

Pattern = Annotated[str, StringConstraints(pattern=r"^[\x09-\x0a\x0d ]*$")]

Pattern2 = Annotated[str, StringConstraints(pattern=r'^["/\\bfnrt]$')]

Pattern3 = Annotated[str, StringConstraints(pattern=r"^[1-9]$")]

Pattern4 = Annotated[str, StringConstraints(pattern=r"^[Ee]$")]

Pattern5 = Annotated[str, StringConstraints(pattern=r"^[ -!#-\[\]-\U0010ffff]$")]

Pattern6 = Annotated[str, StringConstraints(pattern=r"^[0-9A-Fa-f]$")]


class JsonText(GrammarModel):
    ws: Annotated[Optional[Ws], IrBind(0, "model", False)] = None
    value: Annotated[Value, IrBind(1, "model")]
    ws2: Annotated[Optional[Ws], IrBind(2, "model", False)] = None
    __grammar__: ClassVar[IrRule] = IrRule(
        "json-text",
        IrAlternation(
            IrSequence(
                IrItem(IrRuleRef("ws"), IrQuantifier(0)),
                IrItem(IrRuleRef("value")),
                IrItem(IrRuleRef("ws"), IrQuantifier(0)),
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
                    IrCharClass(IrRange(IrChr(9), IrChr(10)), IrChr(13), IrChr(32)),
                    IrQuantifier(0, IrNone),
                )
            )
        ),
        False,
    )


class Value(GrammarModel):
    __grammar__: ClassVar[IrRule] = IrRule(
        "value",
        IrAlternation(
            IrSequence(IrItem(IrRuleRef("false"))),
            IrSequence(IrItem(IrRuleRef("null"))),
            IrSequence(IrItem(IrRuleRef("true"))),
            IrSequence(IrItem(IrRuleRef("object"))),
            IrSequence(IrItem(IrRuleRef("array"))),
            IrSequence(IrItem(IrRuleRef("number"))),
            IrSequence(IrItem(IrRuleRef("string"))),
        ),
    )


class False_(Value):
    value: str
    __grammar__: ClassVar[IrRule] = IrRule(
        "false", IrAlternation(IrSequence(IrItem(IrLiteral("false"))))
    )


class Null(Value):
    value: str
    __grammar__: ClassVar[IrRule] = IrRule(
        "null", IrAlternation(IrSequence(IrItem(IrLiteral("null"))))
    )


class True_(Value):
    value: str
    __grammar__: ClassVar[IrRule] = IrRule(
        "true", IrAlternation(IrSequence(IrItem(IrLiteral("true"))))
    )


class Object(Value):
    begin_object: Annotated[BeginObject, IrBind(0, "model")]
    object_item2: Annotated[Optional[ObjectItem2], IrBind(1, "model")] = None
    end_object: Annotated[EndObject, IrBind(2, "model")]
    __grammar__: ClassVar[IrRule] = IrRule(
        "object",
        IrAlternation(
            IrSequence(
                IrItem(IrRuleRef("begin-object")),
                IrItem(IrRuleRef("object-item2"), IrQuantifier(0)),
                IrItem(IrRuleRef("end-object")),
            )
        ),
    )


class Array(Value):
    begin_array: Annotated[BeginArray, IrBind(0, "model")]
    array_item2: Annotated[Optional[ArrayItem2], IrBind(1, "model")] = None
    end_array: Annotated[EndArray, IrBind(2, "model")]
    __grammar__: ClassVar[IrRule] = IrRule(
        "array",
        IrAlternation(
            IrSequence(
                IrItem(IrRuleRef("begin-array")),
                IrItem(IrRuleRef("array-item2"), IrQuantifier(0)),
                IrItem(IrRuleRef("end-array")),
            )
        ),
    )


class Number(Value):
    minus: Annotated[Optional[Minus], IrBind(0, "model")] = None
    int: Annotated[Int, IrBind(1, "model")]
    frac: Annotated[Optional[Frac], IrBind(2, "model")] = None
    exp: Annotated[Optional[Exp], IrBind(3, "model")] = None
    __grammar__: ClassVar[IrRule] = IrRule(
        "number",
        IrAlternation(
            IrSequence(
                IrItem(IrRuleRef("minus"), IrQuantifier(0)),
                IrItem(IrRuleRef("int")),
                IrItem(IrRuleRef("frac"), IrQuantifier(0)),
                IrItem(IrRuleRef("exp"), IrQuantifier(0)),
            )
        ),
    )


class String(Value):
    quotation_mark: Annotated[QuotationMark, IrBind(0, "model")]
    char: Annotated[List[Char], IrBind(1, "models")]
    quotation_mark2: Annotated[QuotationMark, IrBind(2, "model")]
    __grammar__: ClassVar[IrRule] = IrRule(
        "string",
        IrAlternation(
            IrSequence(
                IrItem(IrRuleRef("quotation-mark")),
                IrItem(IrRuleRef("char"), IrQuantifier(0, IrNone)),
                IrItem(IrRuleRef("quotation-mark")),
            )
        ),
    )


class BeginObject(GrammarModel):
    ws: Annotated[Optional[Ws], IrBind(0, "model", False)] = None
    ws2: Annotated[Optional[Ws], IrBind(2, "model", False)] = None
    __grammar__: ClassVar[IrRule] = IrRule(
        "begin-object",
        IrAlternation(
            IrSequence(
                IrItem(IrRuleRef("ws"), IrQuantifier(0)),
                IrItem(IrLiteral("{")),
                IrItem(IrRuleRef("ws"), IrQuantifier(0)),
            )
        ),
    )


class Member(GrammarModel):
    string: Annotated[String, IrBind(0, "model")]
    name_separator: Annotated[NameSeparator, IrBind(1, "model")]
    value: Annotated[Value, IrBind(2, "model")]
    __grammar__: ClassVar[IrRule] = IrRule(
        "member",
        IrAlternation(
            IrSequence(
                IrItem(IrRuleRef("string")),
                IrItem(IrRuleRef("name-separator")),
                IrItem(IrRuleRef("value")),
            )
        ),
    )


class ValueSeparator(GrammarModel):
    ws: Annotated[Optional[Ws], IrBind(0, "model", False)] = None
    ws2: Annotated[Optional[Ws], IrBind(2, "model", False)] = None
    __grammar__: ClassVar[IrRule] = IrRule(
        "value-separator",
        IrAlternation(
            IrSequence(
                IrItem(IrRuleRef("ws"), IrQuantifier(0)),
                IrItem(IrLiteral(",")),
                IrItem(IrRuleRef("ws"), IrQuantifier(0)),
            )
        ),
    )


class EndObject(GrammarModel):
    ws: Annotated[Optional[Ws], IrBind(0, "model", False)] = None
    ws2: Annotated[Optional[Ws], IrBind(2, "model", False)] = None
    __grammar__: ClassVar[IrRule] = IrRule(
        "end-object",
        IrAlternation(
            IrSequence(
                IrItem(IrRuleRef("ws"), IrQuantifier(0)),
                IrItem(IrLiteral("}")),
                IrItem(IrRuleRef("ws"), IrQuantifier(0)),
            )
        ),
    )


class BeginArray(GrammarModel):
    ws: Annotated[Optional[Ws], IrBind(0, "model", False)] = None
    ws2: Annotated[Optional[Ws], IrBind(2, "model", False)] = None
    __grammar__: ClassVar[IrRule] = IrRule(
        "begin-array",
        IrAlternation(
            IrSequence(
                IrItem(IrRuleRef("ws"), IrQuantifier(0)),
                IrItem(IrLiteral("[")),
                IrItem(IrRuleRef("ws"), IrQuantifier(0)),
            )
        ),
    )


class EndArray(GrammarModel):
    ws: Annotated[Optional[Ws], IrBind(0, "model", False)] = None
    ws2: Annotated[Optional[Ws], IrBind(2, "model", False)] = None
    __grammar__: ClassVar[IrRule] = IrRule(
        "end-array",
        IrAlternation(
            IrSequence(
                IrItem(IrRuleRef("ws"), IrQuantifier(0)),
                IrItem(IrLiteral("]")),
                IrItem(IrRuleRef("ws"), IrQuantifier(0)),
            )
        ),
    )


class ExpItem(GrammarModel):
    __grammar__: ClassVar[IrRule] = IrRule(
        "exp-item",
        IrAlternation(
            IrSequence(IrItem(IrRuleRef("minus"))),
            IrSequence(IrItem(IrRuleRef("plus"))),
        ),
    )


class Minus(ExpItem):
    value: str
    __grammar__: ClassVar[IrRule] = IrRule(
        "minus", IrAlternation(IrSequence(IrItem(IrLiteral("-"))))
    )


class Int(GrammarModel):
    __grammar__: ClassVar[IrRule] = IrRule(
        "int",
        IrAlternation(
            IrSequence(IrItem(IrRuleRef("zero"))),
            IrSequence(IrItem(IrRuleRef("int-arm2"))),
        ),
    )


class IntArm2(Int):
    digit1_9: Annotated[Digit19, IrBind(0, "model")]
    digit: Annotated[List[Digit], IrBind(1, "models")]
    __grammar__: ClassVar[IrRule] = IrRule(
        "int-arm2",
        IrAlternation(
            IrSequence(
                IrItem(IrRuleRef("digit1-9")),
                IrItem(IrRuleRef("digit"), IrQuantifier(0, IrNone)),
            )
        ),
    )


class Frac(GrammarModel):
    decimal_point: Annotated[DecimalPoint, IrBind(0, "model")]
    digit: Annotated[List[Digit], IrBind(1, "models")]
    __grammar__: ClassVar[IrRule] = IrRule(
        "frac",
        IrAlternation(
            IrSequence(
                IrItem(IrRuleRef("decimal-point")),
                IrItem(IrRuleRef("digit"), IrQuantifier(1, IrNone)),
            )
        ),
    )


class Exp(GrammarModel):
    e: Annotated[E, IrBind(0, "model")]
    exp_item: Annotated[Optional[ExpItem], IrBind(1, "model")] = None
    digit: Annotated[List[Digit], IrBind(2, "models")]
    __grammar__: ClassVar[IrRule] = IrRule(
        "exp",
        IrAlternation(
            IrSequence(
                IrItem(IrRuleRef("e")),
                IrItem(IrRuleRef("exp-item"), IrQuantifier(0)),
                IrItem(IrRuleRef("digit"), IrQuantifier(1, IrNone)),
            )
        ),
    )


class QuotationMark(GrammarModel):
    value: str
    __grammar__: ClassVar[IrRule] = IrRule(
        "quotation-mark", IrAlternation(IrSequence(IrItem(IrLiteral('"'))))
    )


class Char(GrammarModel):
    __grammar__: ClassVar[IrRule] = IrRule(
        "char",
        IrAlternation(
            IrSequence(IrItem(IrRuleRef("unescaped"))),
            IrSequence(IrItem(IrRuleRef("char-arm2"))),
        ),
    )


class CharArm2(Char):
    escape: Annotated[Escape, IrBind(0, "model")]
    kind: Annotated[str, IrBind(1, "model")]
    __grammar__: ClassVar[IrRule] = IrRule(
        "char-arm2",
        IrAlternation(
            IrSequence(
                IrItem(IrRuleRef("escape")),
                IrItem(
                    IrAlternation(
                        IrSequence(
                            IrItem(
                                IrCharClass(
                                    IrChr(34),
                                    IrChr(47),
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
                            IrItem(IrRuleRef("hexdig"), IrQuantifier(4, 4)),
                        ),
                    )
                ),
            )
        ),
    )


class NameSeparator(GrammarModel):
    ws: Annotated[Optional[Ws], IrBind(0, "model", False)] = None
    ws2: Annotated[Optional[Ws], IrBind(2, "model", False)] = None
    __grammar__: ClassVar[IrRule] = IrRule(
        "name-separator",
        IrAlternation(
            IrSequence(
                IrItem(IrRuleRef("ws"), IrQuantifier(0)),
                IrItem(IrLiteral(":")),
                IrItem(IrRuleRef("ws"), IrQuantifier(0)),
            )
        ),
    )


class Zero(Int):
    value: str
    __grammar__: ClassVar[IrRule] = IrRule(
        "zero", IrAlternation(IrSequence(IrItem(IrLiteral("0"))))
    )


class Digit19(GrammarModel):
    value: Pattern3
    __grammar__: ClassVar[IrRule] = IrRule(
        "digit1-9",
        IrAlternation(IrSequence(IrItem(IrCharClass(IrRange(IrChr(49), IrChr(57)))))),
    )


class Digit(GrammarModel):
    value: Annotated[str, StringConstraints(pattern=r"^[0-9]$")]
    __grammar__: ClassVar[IrRule] = IrRule(
        "digit",
        IrAlternation(IrSequence(IrItem(IrCharClass(IrRange(IrChr(48), IrChr(57)))))),
    )


class DecimalPoint(GrammarModel):
    value: str
    __grammar__: ClassVar[IrRule] = IrRule(
        "decimal-point", IrAlternation(IrSequence(IrItem(IrLiteral("."))))
    )


class E(GrammarModel):
    value: Pattern4
    __grammar__: ClassVar[IrRule] = IrRule(
        "e", IrAlternation(IrSequence(IrItem(IrCharClass(IrChr(69), IrChr(101)))))
    )


class Plus(ExpItem):
    value: str
    __grammar__: ClassVar[IrRule] = IrRule(
        "plus", IrAlternation(IrSequence(IrItem(IrLiteral("+"))))
    )


class Unescaped(Char):
    value: Pattern5
    __grammar__: ClassVar[IrRule] = IrRule(
        "unescaped",
        IrAlternation(
            IrSequence(
                IrItem(
                    IrCharClass(
                        IrRange(IrChr(32), IrChr(33)),
                        IrRange(IrChr(35), IrChr(91)),
                        IrRange(IrChr(93), IrChr(1114111)),
                    )
                )
            )
        ),
    )


class Escape(GrammarModel):
    value: str
    __grammar__: ClassVar[IrRule] = IrRule(
        "escape", IrAlternation(IrSequence(IrItem(IrLiteral("\\"))))
    )


class Hexdig(GrammarModel):
    value: Pattern6
    __grammar__: ClassVar[IrRule] = IrRule(
        "hexdig",
        IrAlternation(
            IrSequence(
                IrItem(
                    IrCharClass(
                        IrRange(IrChr(48), IrChr(57)),
                        IrRange(IrChr(65), IrChr(70)),
                        IrRange(IrChr(97), IrChr(102)),
                    )
                )
            )
        ),
    )


class ObjectItem(GrammarModel):
    value_separator: Annotated[ValueSeparator, IrBind(0, "model")]
    member: Annotated[Member, IrBind(1, "model")]
    __grammar__: ClassVar[IrRule] = IrRule(
        "object-item",
        IrAlternation(
            IrSequence(
                IrItem(IrRuleRef("value-separator")), IrItem(IrRuleRef("member"))
            )
        ),
    )


class ObjectItem2(GrammarModel):
    member: Annotated[Member, IrBind(0, "model")]
    object_item: Annotated[List[ObjectItem], IrBind(1, "models")]
    __grammar__: ClassVar[IrRule] = IrRule(
        "object-item2",
        IrAlternation(
            IrSequence(
                IrItem(IrRuleRef("member")),
                IrItem(IrRuleRef("object-item"), IrQuantifier(0, IrNone)),
            )
        ),
    )


class ArrayItem(GrammarModel):
    value_separator: Annotated[ValueSeparator, IrBind(0, "model")]
    value: Annotated[Value, IrBind(1, "model")]
    __grammar__: ClassVar[IrRule] = IrRule(
        "array-item",
        IrAlternation(
            IrSequence(IrItem(IrRuleRef("value-separator")), IrItem(IrRuleRef("value")))
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
        IrRule(
            "json-text",
            IrAlternation(
                IrSequence(
                    IrItem(IrRuleRef("ws")),
                    IrItem(IrRuleRef("value")),
                    IrItem(IrRuleRef("ws")),
                )
            ),
        ),
        IrRule(
            "ws",
            IrAlternation(
                IrSequence(
                    IrItem(
                        IrCharClass(IrRange(IrChr(9), IrChr(10)), IrChr(13), IrChr(32)),
                        IrQuantifier(0, IrNone),
                    )
                )
            ),
            False,
        ),
        IrRule(
            "value",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("false"))),
                IrSequence(IrItem(IrRuleRef("null"))),
                IrSequence(IrItem(IrRuleRef("true"))),
                IrSequence(IrItem(IrRuleRef("object"))),
                IrSequence(IrItem(IrRuleRef("array"))),
                IrSequence(IrItem(IrRuleRef("number"))),
                IrSequence(IrItem(IrRuleRef("string"))),
            ),
        ),
        IrRule("false", IrAlternation(IrSequence(IrItem(IrLiteral("false"))))),
        IrRule("null", IrAlternation(IrSequence(IrItem(IrLiteral("null"))))),
        IrRule("true", IrAlternation(IrSequence(IrItem(IrLiteral("true"))))),
        IrRule(
            "object",
            IrAlternation(
                IrSequence(
                    IrItem(IrRuleRef("begin-object")),
                    IrItem(
                        IrAlternation(
                            IrSequence(
                                IrItem(IrRuleRef("member")),
                                IrItem(
                                    IrAlternation(
                                        IrSequence(
                                            IrItem(IrRuleRef("value-separator")),
                                            IrItem(IrRuleRef("member")),
                                        )
                                    ),
                                    IrQuantifier(0, IrNone),
                                ),
                            )
                        ),
                        IrQuantifier(0),
                    ),
                    IrItem(IrRuleRef("end-object")),
                )
            ),
        ),
        IrRule(
            "array",
            IrAlternation(
                IrSequence(
                    IrItem(IrRuleRef("begin-array")),
                    IrItem(
                        IrAlternation(
                            IrSequence(
                                IrItem(IrRuleRef("value")),
                                IrItem(
                                    IrAlternation(
                                        IrSequence(
                                            IrItem(IrRuleRef("value-separator")),
                                            IrItem(IrRuleRef("value")),
                                        )
                                    ),
                                    IrQuantifier(0, IrNone),
                                ),
                            )
                        ),
                        IrQuantifier(0),
                    ),
                    IrItem(IrRuleRef("end-array")),
                )
            ),
        ),
        IrRule(
            "number",
            IrAlternation(
                IrSequence(
                    IrItem(IrRuleRef("minus"), IrQuantifier(0)),
                    IrItem(IrRuleRef("int")),
                    IrItem(IrRuleRef("frac"), IrQuantifier(0)),
                    IrItem(IrRuleRef("exp"), IrQuantifier(0)),
                )
            ),
        ),
        IrRule(
            "string",
            IrAlternation(
                IrSequence(
                    IrItem(IrRuleRef("quotation-mark")),
                    IrItem(IrRuleRef("char"), IrQuantifier(0, IrNone)),
                    IrItem(IrRuleRef("quotation-mark")),
                )
            ),
        ),
        IrRule(
            "begin-object",
            IrAlternation(
                IrSequence(
                    IrItem(IrRuleRef("ws")),
                    IrItem(IrLiteral("{")),
                    IrItem(IrRuleRef("ws")),
                )
            ),
        ),
        IrRule(
            "member",
            IrAlternation(
                IrSequence(
                    IrItem(IrRuleRef("string")),
                    IrItem(IrRuleRef("name-separator")),
                    IrItem(IrRuleRef("value")),
                )
            ),
        ),
        IrRule(
            "value-separator",
            IrAlternation(
                IrSequence(
                    IrItem(IrRuleRef("ws")),
                    IrItem(IrLiteral(",")),
                    IrItem(IrRuleRef("ws")),
                )
            ),
        ),
        IrRule(
            "end-object",
            IrAlternation(
                IrSequence(
                    IrItem(IrRuleRef("ws")),
                    IrItem(IrLiteral("}")),
                    IrItem(IrRuleRef("ws")),
                )
            ),
        ),
        IrRule(
            "begin-array",
            IrAlternation(
                IrSequence(
                    IrItem(IrRuleRef("ws")),
                    IrItem(IrLiteral("[")),
                    IrItem(IrRuleRef("ws")),
                )
            ),
        ),
        IrRule(
            "end-array",
            IrAlternation(
                IrSequence(
                    IrItem(IrRuleRef("ws")),
                    IrItem(IrLiteral("]")),
                    IrItem(IrRuleRef("ws")),
                )
            ),
        ),
        IrRule("minus", IrAlternation(IrSequence(IrItem(IrLiteral("-"))))),
        IrRule(
            "int",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("zero"))),
                IrSequence(
                    IrItem(IrRuleRef("digit1-9")),
                    IrItem(IrRuleRef("digit"), IrQuantifier(0, IrNone)),
                ),
            ),
        ),
        IrRule(
            "frac",
            IrAlternation(
                IrSequence(
                    IrItem(IrRuleRef("decimal-point")),
                    IrItem(IrRuleRef("digit"), IrQuantifier(1, IrNone)),
                )
            ),
        ),
        IrRule(
            "exp",
            IrAlternation(
                IrSequence(
                    IrItem(IrRuleRef("e")),
                    IrItem(
                        IrAlternation(
                            IrSequence(IrItem(IrRuleRef("minus"))),
                            IrSequence(IrItem(IrRuleRef("plus"))),
                        ),
                        IrQuantifier(0),
                    ),
                    IrItem(IrRuleRef("digit"), IrQuantifier(1, IrNone)),
                )
            ),
        ),
        IrRule("quotation-mark", IrAlternation(IrSequence(IrItem(IrLiteral('"'))))),
        IrRule(
            "char",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("unescaped"))),
                IrSequence(
                    IrItem(IrRuleRef("escape")),
                    IrItem(
                        IrAlternation(
                            IrSequence(
                                IrItem(
                                    IrCharClass(
                                        IrChr(34),
                                        IrChr(47),
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
                                IrItem(IrRuleRef("hexdig"), IrQuantifier(4, 4)),
                            ),
                        )
                    ),
                ),
            ),
        ),
        IrRule(
            "name-separator",
            IrAlternation(
                IrSequence(
                    IrItem(IrRuleRef("ws")),
                    IrItem(IrLiteral(":")),
                    IrItem(IrRuleRef("ws")),
                )
            ),
        ),
        IrRule("zero", IrAlternation(IrSequence(IrItem(IrLiteral("0"))))),
        IrRule(
            "digit1-9",
            IrAlternation(
                IrSequence(IrItem(IrCharClass(IrRange(IrChr(49), IrChr(57)))))
            ),
        ),
        IrRule(
            "digit",
            IrAlternation(
                IrSequence(IrItem(IrCharClass(IrRange(IrChr(48), IrChr(57)))))
            ),
        ),
        IrRule("decimal-point", IrAlternation(IrSequence(IrItem(IrLiteral("."))))),
        IrRule(
            "e", IrAlternation(IrSequence(IrItem(IrCharClass(IrChr(69), IrChr(101)))))
        ),
        IrRule("plus", IrAlternation(IrSequence(IrItem(IrLiteral("+"))))),
        IrRule(
            "unescaped",
            IrAlternation(
                IrSequence(
                    IrItem(
                        IrCharClass(
                            IrRange(IrChr(32), IrChr(33)),
                            IrRange(IrChr(35), IrChr(91)),
                            IrRange(IrChr(93), IrChr(1114111)),
                        )
                    )
                )
            ),
        ),
        IrRule("escape", IrAlternation(IrSequence(IrItem(IrLiteral("\\"))))),
        IrRule(
            "hexdig",
            IrAlternation(
                IrSequence(
                    IrItem(
                        IrCharClass(
                            IrRange(IrChr(48), IrChr(57)),
                            IrRange(IrChr(65), IrChr(70)),
                            IrRange(IrChr(97), IrChr(102)),
                        )
                    )
                )
            ),
        ),
    ),
    "json-text",
)

START: str = "json-text"
