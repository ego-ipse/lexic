"""Generated module: json_grammar_test. Do not edit; regenerated from grammar."""

from __future__ import annotations

from typing import Annotated, List, Optional

from pydantic import StringConstraints

from lexic.base import GrammarModel
from lexic.ir.base import IrNone
from lexic.ir.nodes import (
    IrAlternation,
    IrCharClass,
    IrChr,
    IrItem,
    IrLiteral,
    IrQuantifier,
    IrRange,
    IrRuleRef,
    IrSequence,
)
from lexic.ir.spec import RuleSpec

Pattern = Annotated[str, StringConstraints(pattern=r"^[ \x09\x0a\x0d]*$")]

Pattern2 = Annotated[str, StringConstraints(pattern=r"^[1-9]$")]

Pattern3 = Annotated[str, StringConstraints(pattern=r"^[eE]$")]

Pattern4 = Annotated[str, StringConstraints(pattern=r'^["\\/bfnrt]$')]

Pattern5 = Annotated[str, StringConstraints(pattern=r"^[ -!#-\[\]-\U0010ffff]$")]

Pattern6 = Annotated[str, StringConstraints(pattern=r"^[0-9A-Fa-f]$")]


class JSONText(GrammarModel):
    ws: Optional[Ws] = None
    value: Value
    ws2: Optional[Ws] = None


class BeginArray(GrammarModel):
    ws: Optional[Ws] = None
    ws2: Optional[Ws] = None


class BeginObject(GrammarModel):
    ws: Optional[Ws] = None
    ws2: Optional[Ws] = None


class EndArray(GrammarModel):
    ws: Optional[Ws] = None
    ws2: Optional[Ws] = None


class EndObject(GrammarModel):
    ws: Optional[Ws] = None
    ws2: Optional[Ws] = None


class NameSeparator(GrammarModel):
    ws: Optional[Ws] = None
    ws2: Optional[Ws] = None


class ValueSeparator(GrammarModel):
    ws: Optional[Ws] = None
    ws2: Optional[Ws] = None


class Ws(GrammarModel):
    value: Pattern


class Value(GrammarModel):
    pass


class False_(Value):
    value: str


class Null(Value):
    value: str


class True_(Value):
    value: str


class Object(Value):
    begin_object: BeginObject
    object_item2: Optional[ObjectItem2] = None
    end_object: EndObject


class Member(GrammarModel):
    string: String
    name_separator: NameSeparator
    value: Value


class Array(Value):
    begin_array: BeginArray
    array_item2: Optional[ArrayItem2] = None
    end_array: EndArray


class Number(Value):
    minus: Optional[Minus] = None
    int: Int
    frac: Optional[Frac] = None
    exp: Optional[Exp] = None


class DecimalPoint(GrammarModel):
    value: str


class Digit19(GrammarModel):
    value: Pattern2


class E(GrammarModel):
    value: Pattern3


class Exp(GrammarModel):
    e: E
    exp_item: Optional[ExpItem] = None
    digit: List[Digit]


class Frac(GrammarModel):
    decimal_point: DecimalPoint
    digit: List[Digit]


class Int(GrammarModel):
    pass


class IntArm2(Int):
    digit1_9: Digit19
    digit: List[Digit]


class ExpItem(GrammarModel):
    pass


class Minus(ExpItem):
    value: str


class Plus(ExpItem):
    value: str


class Zero(Int):
    value: str


class Digit(GrammarModel):
    value: Annotated[str, StringConstraints(pattern=r"^[0-9]$")]


class String(Value):
    quotation_mark: QuotationMark
    char: List[Char]
    quotation_mark2: QuotationMark


class Char(GrammarModel):
    pass


class CharArm2(Char):
    escape: Escape
    kind: str


class Escape(GrammarModel):
    value: str


class QuotationMark(GrammarModel):
    value: str


class Unescaped(Char):
    value: Pattern5


class Hexdig(GrammarModel):
    value: Pattern6


class ObjectItem(GrammarModel):
    value_separator: ValueSeparator
    member: Member


class ObjectItem2(GrammarModel):
    member: Member
    object_item: List[ObjectItem]


class ArrayItem(GrammarModel):
    value_separator: ValueSeparator
    value: Value


class ArrayItem2(GrammarModel):
    value: Value
    array_item: List[ArrayItem]


JSONText.__grammar__ = RuleSpec(
    rule_name="JSON-text",
    class_name="JSONText",
    parent_class_name="GrammarModel",
    kind="sequence",
    items=[
        IrItem(IrRuleRef("ws"), IrQuantifier(0, 1)),
        IrItem(IrRuleRef("value"), IrQuantifier(1, 1)),
        IrItem(IrRuleRef("ws"), IrQuantifier(0, 1)),
    ],
    field_map={"ws": 0, "value": 1, "ws2": 2},
    non_semantic_fields=frozenset(["ws", "ws2"]),
)


BeginArray.__grammar__ = RuleSpec(
    rule_name="begin-array",
    class_name="BeginArray",
    parent_class_name="GrammarModel",
    kind="sequence",
    items=[
        IrItem(IrRuleRef("ws"), IrQuantifier(0, 1)),
        IrItem(IrLiteral("["), IrQuantifier(1, 1)),
        IrItem(IrRuleRef("ws"), IrQuantifier(0, 1)),
    ],
    field_map={"ws": 0, "ws2": 2},
    non_semantic_fields=frozenset(["ws", "ws2"]),
)


BeginObject.__grammar__ = RuleSpec(
    rule_name="begin-object",
    class_name="BeginObject",
    parent_class_name="GrammarModel",
    kind="sequence",
    items=[
        IrItem(IrRuleRef("ws"), IrQuantifier(0, 1)),
        IrItem(IrLiteral("{"), IrQuantifier(1, 1)),
        IrItem(IrRuleRef("ws"), IrQuantifier(0, 1)),
    ],
    field_map={"ws": 0, "ws2": 2},
    non_semantic_fields=frozenset(["ws", "ws2"]),
)


EndArray.__grammar__ = RuleSpec(
    rule_name="end-array",
    class_name="EndArray",
    parent_class_name="GrammarModel",
    kind="sequence",
    items=[
        IrItem(IrRuleRef("ws"), IrQuantifier(0, 1)),
        IrItem(IrLiteral("]"), IrQuantifier(1, 1)),
        IrItem(IrRuleRef("ws"), IrQuantifier(0, 1)),
    ],
    field_map={"ws": 0, "ws2": 2},
    non_semantic_fields=frozenset(["ws", "ws2"]),
)


EndObject.__grammar__ = RuleSpec(
    rule_name="end-object",
    class_name="EndObject",
    parent_class_name="GrammarModel",
    kind="sequence",
    items=[
        IrItem(IrRuleRef("ws"), IrQuantifier(0, 1)),
        IrItem(IrLiteral("}"), IrQuantifier(1, 1)),
        IrItem(IrRuleRef("ws"), IrQuantifier(0, 1)),
    ],
    field_map={"ws": 0, "ws2": 2},
    non_semantic_fields=frozenset(["ws", "ws2"]),
)


NameSeparator.__grammar__ = RuleSpec(
    rule_name="name-separator",
    class_name="NameSeparator",
    parent_class_name="GrammarModel",
    kind="sequence",
    items=[
        IrItem(IrRuleRef("ws"), IrQuantifier(0, 1)),
        IrItem(IrLiteral(":"), IrQuantifier(1, 1)),
        IrItem(IrRuleRef("ws"), IrQuantifier(0, 1)),
    ],
    field_map={"ws": 0, "ws2": 2},
    non_semantic_fields=frozenset(["ws", "ws2"]),
)


ValueSeparator.__grammar__ = RuleSpec(
    rule_name="value-separator",
    class_name="ValueSeparator",
    parent_class_name="GrammarModel",
    kind="sequence",
    items=[
        IrItem(IrRuleRef("ws"), IrQuantifier(0, 1)),
        IrItem(IrLiteral(","), IrQuantifier(1, 1)),
        IrItem(IrRuleRef("ws"), IrQuantifier(0, 1)),
    ],
    field_map={"ws": 0, "ws2": 2},
    non_semantic_fields=frozenset(["ws", "ws2"]),
)


Ws.__grammar__ = RuleSpec(
    rule_name="ws",
    class_name="Ws",
    parent_class_name="GrammarModel",
    kind="value_str",
    items=[
        IrItem(
            IrCharClass(IrChr(32), IrChr(9), IrChr(10), IrChr(13)),
            IrQuantifier(0, IrNone),
        )
    ],
    field_map={},
    non_semantic_fields=frozenset([]),
)


Value.__grammar__ = RuleSpec(
    rule_name="value",
    class_name="Value",
    parent_class_name="GrammarModel",
    kind="alternation",
    items=[
        IrItem(IrRuleRef("false"), IrQuantifier(1, 1)),
        IrItem(IrRuleRef("null"), IrQuantifier(1, 1)),
        IrItem(IrRuleRef("true"), IrQuantifier(1, 1)),
        IrItem(IrRuleRef("object"), IrQuantifier(1, 1)),
        IrItem(IrRuleRef("array"), IrQuantifier(1, 1)),
        IrItem(IrRuleRef("number"), IrQuantifier(1, 1)),
        IrItem(IrRuleRef("string"), IrQuantifier(1, 1)),
    ],
    field_map={},
    non_semantic_fields=frozenset([]),
)


False_.__grammar__ = RuleSpec(
    rule_name="false",
    class_name="False_",
    parent_class_name="Value",
    kind="value_str",
    items=[IrItem(IrLiteral("false"), IrQuantifier(1, 1))],
    field_map={},
    non_semantic_fields=frozenset([]),
)


Null.__grammar__ = RuleSpec(
    rule_name="null",
    class_name="Null",
    parent_class_name="Value",
    kind="value_str",
    items=[IrItem(IrLiteral("null"), IrQuantifier(1, 1))],
    field_map={},
    non_semantic_fields=frozenset([]),
)


True_.__grammar__ = RuleSpec(
    rule_name="true",
    class_name="True_",
    parent_class_name="Value",
    kind="value_str",
    items=[IrItem(IrLiteral("true"), IrQuantifier(1, 1))],
    field_map={},
    non_semantic_fields=frozenset([]),
)


Object.__grammar__ = RuleSpec(
    rule_name="object",
    class_name="Object",
    parent_class_name="Value",
    kind="sequence",
    items=[
        IrItem(IrRuleRef("begin-object"), IrQuantifier(1, 1)),
        IrItem(IrRuleRef("object-item2"), IrQuantifier(0, 1)),
        IrItem(IrRuleRef("end-object"), IrQuantifier(1, 1)),
    ],
    field_map={"begin_object": 0, "object_item2": 1, "end_object": 2},
    non_semantic_fields=frozenset([]),
)


Member.__grammar__ = RuleSpec(
    rule_name="member",
    class_name="Member",
    parent_class_name="GrammarModel",
    kind="sequence",
    items=[
        IrItem(IrRuleRef("string"), IrQuantifier(1, 1)),
        IrItem(IrRuleRef("name-separator"), IrQuantifier(1, 1)),
        IrItem(IrRuleRef("value"), IrQuantifier(1, 1)),
    ],
    field_map={"string": 0, "name_separator": 1, "value": 2},
    non_semantic_fields=frozenset([]),
)


Array.__grammar__ = RuleSpec(
    rule_name="array",
    class_name="Array",
    parent_class_name="Value",
    kind="sequence",
    items=[
        IrItem(IrRuleRef("begin-array"), IrQuantifier(1, 1)),
        IrItem(IrRuleRef("array-item2"), IrQuantifier(0, 1)),
        IrItem(IrRuleRef("end-array"), IrQuantifier(1, 1)),
    ],
    field_map={"begin_array": 0, "array_item2": 1, "end_array": 2},
    non_semantic_fields=frozenset([]),
)


Number.__grammar__ = RuleSpec(
    rule_name="number",
    class_name="Number",
    parent_class_name="Value",
    kind="sequence",
    items=[
        IrItem(IrRuleRef("minus"), IrQuantifier(0, 1)),
        IrItem(IrRuleRef("int"), IrQuantifier(1, 1)),
        IrItem(IrRuleRef("frac"), IrQuantifier(0, 1)),
        IrItem(IrRuleRef("exp"), IrQuantifier(0, 1)),
    ],
    field_map={"minus": 0, "int": 1, "frac": 2, "exp": 3},
    non_semantic_fields=frozenset([]),
)


DecimalPoint.__grammar__ = RuleSpec(
    rule_name="decimal-point",
    class_name="DecimalPoint",
    parent_class_name="GrammarModel",
    kind="value_str",
    items=[IrItem(IrLiteral("."), IrQuantifier(1, 1))],
    field_map={},
    non_semantic_fields=frozenset([]),
)


Digit19.__grammar__ = RuleSpec(
    rule_name="digit1-9",
    class_name="Digit19",
    parent_class_name="GrammarModel",
    kind="value_str",
    items=[IrItem(IrCharClass(IrRange(IrChr(49), IrChr(57))), IrQuantifier(1, 1))],
    field_map={},
    non_semantic_fields=frozenset([]),
)


E.__grammar__ = RuleSpec(
    rule_name="e",
    class_name="E",
    parent_class_name="GrammarModel",
    kind="value_str",
    items=[IrItem(IrCharClass(IrChr(101), IrChr(69)), IrQuantifier(1, 1))],
    field_map={},
    non_semantic_fields=frozenset([]),
)


Exp.__grammar__ = RuleSpec(
    rule_name="exp",
    class_name="Exp",
    parent_class_name="GrammarModel",
    kind="sequence",
    items=[
        IrItem(IrRuleRef("e"), IrQuantifier(1, 1)),
        IrItem(IrRuleRef("exp-item"), IrQuantifier(0, 1)),
        IrItem(IrRuleRef("digit"), IrQuantifier(1, IrNone)),
    ],
    field_map={"e": 0, "exp_item": 1, "digit": 2},
    non_semantic_fields=frozenset([]),
)


Frac.__grammar__ = RuleSpec(
    rule_name="frac",
    class_name="Frac",
    parent_class_name="GrammarModel",
    kind="sequence",
    items=[
        IrItem(IrRuleRef("decimal-point"), IrQuantifier(1, 1)),
        IrItem(IrRuleRef("digit"), IrQuantifier(1, IrNone)),
    ],
    field_map={"decimal_point": 0, "digit": 1},
    non_semantic_fields=frozenset([]),
)


Int.__grammar__ = RuleSpec(
    rule_name="int",
    class_name="Int",
    parent_class_name="GrammarModel",
    kind="alternation",
    items=[
        IrItem(IrRuleRef("zero"), IrQuantifier(1, 1)),
        IrItem(IrRuleRef("int-arm2"), IrQuantifier(1, 1)),
    ],
    field_map={},
    non_semantic_fields=frozenset([]),
)


IntArm2.__grammar__ = RuleSpec(
    rule_name="int-arm2",
    class_name="IntArm2",
    parent_class_name="Int",
    kind="sequence",
    items=[
        IrItem(IrRuleRef("digit1-9"), IrQuantifier(1, 1)),
        IrItem(IrRuleRef("digit"), IrQuantifier(0, IrNone)),
    ],
    field_map={"digit1_9": 0, "digit": 1},
    non_semantic_fields=frozenset([]),
)


ExpItem.__grammar__ = RuleSpec(
    rule_name="exp-item",
    class_name="ExpItem",
    parent_class_name="GrammarModel",
    kind="alternation",
    items=[
        IrItem(IrRuleRef("minus"), IrQuantifier(1, 1)),
        IrItem(IrRuleRef("plus"), IrQuantifier(1, 1)),
    ],
    field_map={},
    non_semantic_fields=frozenset([]),
)


Minus.__grammar__ = RuleSpec(
    rule_name="minus",
    class_name="Minus",
    parent_class_name="ExpItem",
    kind="value_str",
    items=[IrItem(IrLiteral("-"), IrQuantifier(1, 1))],
    field_map={},
    non_semantic_fields=frozenset([]),
)


Plus.__grammar__ = RuleSpec(
    rule_name="plus",
    class_name="Plus",
    parent_class_name="ExpItem",
    kind="value_str",
    items=[IrItem(IrLiteral("+"), IrQuantifier(1, 1))],
    field_map={},
    non_semantic_fields=frozenset([]),
)


Zero.__grammar__ = RuleSpec(
    rule_name="zero",
    class_name="Zero",
    parent_class_name="Int",
    kind="value_str",
    items=[IrItem(IrLiteral("0"), IrQuantifier(1, 1))],
    field_map={},
    non_semantic_fields=frozenset([]),
)


Digit.__grammar__ = RuleSpec(
    rule_name="digit",
    class_name="Digit",
    parent_class_name="GrammarModel",
    kind="value_str",
    items=[IrItem(IrCharClass(IrRange(IrChr(48), IrChr(57))), IrQuantifier(1, 1))],
    field_map={},
    non_semantic_fields=frozenset([]),
)


String.__grammar__ = RuleSpec(
    rule_name="string",
    class_name="String",
    parent_class_name="Value",
    kind="sequence",
    items=[
        IrItem(IrRuleRef("quotation-mark"), IrQuantifier(1, 1)),
        IrItem(IrRuleRef("char"), IrQuantifier(0, IrNone)),
        IrItem(IrRuleRef("quotation-mark"), IrQuantifier(1, 1)),
    ],
    field_map={"quotation_mark": 0, "char": 1, "quotation_mark2": 2},
    non_semantic_fields=frozenset([]),
)


Char.__grammar__ = RuleSpec(
    rule_name="char",
    class_name="Char",
    parent_class_name="GrammarModel",
    kind="alternation",
    items=[
        IrItem(IrRuleRef("unescaped"), IrQuantifier(1, 1)),
        IrItem(IrRuleRef("char-arm2"), IrQuantifier(1, 1)),
    ],
    field_map={},
    non_semantic_fields=frozenset([]),
)


CharArm2.__grammar__ = RuleSpec(
    rule_name="char-arm2",
    class_name="CharArm2",
    parent_class_name="Char",
    kind="sequence",
    items=[
        IrItem(IrRuleRef("escape"), IrQuantifier(1, 1)),
        IrItem(
            IrAlternation(
                IrSequence(
                    IrItem(
                        IrCharClass(
                            IrChr(34),
                            IrChr(92),
                            IrChr(47),
                            IrChr(98),
                            IrChr(102),
                            IrChr(110),
                            IrChr(114),
                            IrChr(116),
                        ),
                        IrQuantifier(1, 1),
                    )
                ),
                IrSequence(
                    IrItem(IrLiteral("u"), IrQuantifier(1, 1)),
                    IrItem(IrRuleRef("hexdig"), IrQuantifier(4, 4)),
                ),
            ),
            IrQuantifier(1, 1),
        ),
    ],
    field_map={"escape": 0, "kind": 1},
    non_semantic_fields=frozenset([]),
)


Escape.__grammar__ = RuleSpec(
    rule_name="escape",
    class_name="Escape",
    parent_class_name="GrammarModel",
    kind="value_str",
    items=[IrItem(IrLiteral("\\"), IrQuantifier(1, 1))],
    field_map={},
    non_semantic_fields=frozenset([]),
)


QuotationMark.__grammar__ = RuleSpec(
    rule_name="quotation-mark",
    class_name="QuotationMark",
    parent_class_name="GrammarModel",
    kind="value_str",
    items=[IrItem(IrLiteral('"'), IrQuantifier(1, 1))],
    field_map={},
    non_semantic_fields=frozenset([]),
)


Unescaped.__grammar__ = RuleSpec(
    rule_name="unescaped",
    class_name="Unescaped",
    parent_class_name="Char",
    kind="value_str",
    items=[
        IrItem(
            IrCharClass(
                IrRange(IrChr(32), IrChr(33)),
                IrRange(IrChr(35), IrChr(91)),
                IrRange(IrChr(93), IrChr(1114111)),
            ),
            IrQuantifier(1, 1),
        )
    ],
    field_map={},
    non_semantic_fields=frozenset([]),
)


Hexdig.__grammar__ = RuleSpec(
    rule_name="hexdig",
    class_name="Hexdig",
    parent_class_name="GrammarModel",
    kind="value_str",
    items=[
        IrItem(
            IrCharClass(
                IrRange(IrChr(48), IrChr(57)),
                IrRange(IrChr(65), IrChr(70)),
                IrRange(IrChr(97), IrChr(102)),
            ),
            IrQuantifier(1, 1),
        )
    ],
    field_map={},
    non_semantic_fields=frozenset([]),
)


ObjectItem.__grammar__ = RuleSpec(
    rule_name="object-item",
    class_name="ObjectItem",
    parent_class_name="GrammarModel",
    kind="sequence",
    items=[
        IrItem(IrRuleRef("value-separator"), IrQuantifier(1, 1)),
        IrItem(IrRuleRef("member"), IrQuantifier(1, 1)),
    ],
    field_map={"value_separator": 0, "member": 1},
    non_semantic_fields=frozenset([]),
)


ObjectItem2.__grammar__ = RuleSpec(
    rule_name="object-item2",
    class_name="ObjectItem2",
    parent_class_name="GrammarModel",
    kind="sequence",
    items=[
        IrItem(IrRuleRef("member"), IrQuantifier(1, 1)),
        IrItem(IrRuleRef("object-item"), IrQuantifier(0, IrNone)),
    ],
    field_map={"member": 0, "object_item": 1},
    non_semantic_fields=frozenset([]),
)


ArrayItem.__grammar__ = RuleSpec(
    rule_name="array-item",
    class_name="ArrayItem",
    parent_class_name="GrammarModel",
    kind="sequence",
    items=[
        IrItem(IrRuleRef("value-separator"), IrQuantifier(1, 1)),
        IrItem(IrRuleRef("value"), IrQuantifier(1, 1)),
    ],
    field_map={"value_separator": 0, "value": 1},
    non_semantic_fields=frozenset([]),
)


ArrayItem2.__grammar__ = RuleSpec(
    rule_name="array-item2",
    class_name="ArrayItem2",
    parent_class_name="GrammarModel",
    kind="sequence",
    items=[
        IrItem(IrRuleRef("value"), IrQuantifier(1, 1)),
        IrItem(IrRuleRef("array-item"), IrQuantifier(0, IrNone)),
    ],
    field_map={"value": 0, "array_item": 1},
    non_semantic_fields=frozenset([]),
)
