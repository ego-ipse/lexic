"""Generated module: json_arr. Do not edit; regenerated from grammar."""

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

Pattern = Annotated[str, StringConstraints(pattern=r"^[\x09 ]{0,20}$")]

Pattern2 = Annotated[str, StringConstraints(pattern=r"^(true|false|null)$")]

Pattern3 = Annotated[str, StringConstraints(pattern=r"^[ -!#-\[\]-~\x80-\U0010ffff]$")]

Pattern4 = Annotated[str, StringConstraints(pattern=r'^["\\bfnrt]$')]

Pattern5 = Annotated[str, StringConstraints(pattern=r"^[0-9A-Fa-f]{4}$")]

Pattern6 = Annotated[str, StringConstraints(pattern=r'^(["\\bfnrt]|u[0-9A-Fa-f]{4})$')]

Pattern7 = Annotated[
    str,
    StringConstraints(
        pattern=r'^([ -!#-\[\]-~\x80-\U0010ffff]|\\(["\\bfnrt]|u[0-9A-Fa-f]{4}))*$'
    ),
]

Digit = Annotated[str, StringConstraints(pattern=r"^[0-9]$")]

Pattern8 = Annotated[str, StringConstraints(pattern=r"^[1-9]$")]

Digit2 = Annotated[str, StringConstraints(pattern=r"^[0-9]{0,15}$")]

Pattern9 = Annotated[str, StringConstraints(pattern=r"^([0-9]|[1-9][0-9]{0,15})$")]

Digit3 = Annotated[str, StringConstraints(pattern=r"^[0-9]+$")]

Pattern10 = Annotated[str, StringConstraints(pattern=r"^(\.[0-9]+)?$")]

Pattern11 = Annotated[str, StringConstraints(pattern=r"^[Ee]$")]

Pattern12 = Annotated[str, StringConstraints(pattern=r"^[+-]?$")]

Pattern13 = Annotated[str, StringConstraints(pattern=r"^([Ee][+-]?[1-9][0-9]{0,15})?$")]


class Root(GrammarModel):
    arr: Arr


class Arr(GrammarModel):
    ws: Optional[Ws] = None
    arr_item2: Optional[ArrItem2] = None


class Ws(GrammarModel):
    value: str


class Value(GrammarModel):
    pass


class ValueArm5(Value):
    true: Pattern2
    ws: Optional[Ws] = None


class Object(Value):
    ws: Optional[Ws] = None
    object_item2: Optional[ObjectItem2] = None
    ws2: Optional[Ws] = None


class Array(Value):
    ws: Optional[Ws] = None
    array_item2: Optional[ArrayItem2] = None
    ws2: Optional[Ws] = None


class String(Value):
    x80_u0010fff: Pattern7
    ws: Optional[Ws] = None


class Number(Value):
    sign: Optional[str] = None
    digit: Pattern9
    dot: Optional[Pattern10] = None
    ee: Optional[Pattern13] = None
    ws: Optional[Ws] = None


class ArrItem(GrammarModel):
    ws: Optional[Ws] = None
    value: Value


class ArrItem2(GrammarModel):
    value: Value
    arr_item: List[ArrItem]


class ObjectItem(GrammarModel):
    ws: Optional[Ws] = None
    string: String
    ws2: Optional[Ws] = None
    value: Value


class ObjectItem2(GrammarModel):
    string: String
    ws: Optional[Ws] = None
    value: Value
    object_item: List[ObjectItem]


class ArrayItem(GrammarModel):
    ws: Optional[Ws] = None
    value: Value


class ArrayItem2(GrammarModel):
    value: Value
    array_item: List[ArrayItem]


Root.__grammar__ = RuleSpec(
    rule_name="root",
    class_name="Root",
    parent_class_name="GrammarModel",
    kind="sequence",
    items=[IrItem(IrRuleRef("arr"))],
    field_map={"arr": 0},
    non_semantic_fields=frozenset([]),
)


Arr.__grammar__ = RuleSpec(
    rule_name="arr",
    class_name="Arr",
    parent_class_name="GrammarModel",
    kind="sequence",
    items=[
        IrItem(IrLiteral("[\n")),
        IrItem(IrRuleRef("ws"), IrQuantifier(0)),
        IrItem(IrRuleRef("arr-item2"), IrQuantifier(0)),
        IrItem(IrLiteral("]")),
    ],
    field_map={"ws": 1, "arr_item2": 2},
    non_semantic_fields=frozenset(["ws"]),
)


Ws.__grammar__ = RuleSpec(
    rule_name="ws",
    class_name="Ws",
    parent_class_name="GrammarModel",
    kind="value_str",
    items=[
        IrAlternation(
            IrSequence(),
            IrSequence(IrItem(IrLiteral(" "))),
            IrSequence(
                IrItem(IrLiteral("\n")),
                IrItem(IrCharClass(IrChr(9), IrChr(32)), IrQuantifier(0, 20)),
            ),
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
        IrItem(IrRuleRef("object")),
        IrItem(IrRuleRef("array")),
        IrItem(IrRuleRef("string")),
        IrItem(IrRuleRef("number")),
        IrItem(IrRuleRef("value-arm5")),
    ],
    field_map={},
    non_semantic_fields=frozenset([]),
)


ValueArm5.__grammar__ = RuleSpec(
    rule_name="value-arm5",
    class_name="ValueArm5",
    parent_class_name="Value",
    kind="sequence",
    items=[
        IrItem(
            IrAlternation(
                IrSequence(IrItem(IrLiteral("true"))),
                IrSequence(IrItem(IrLiteral("false"))),
                IrSequence(IrItem(IrLiteral("null"))),
            )
        ),
        IrItem(IrRuleRef("ws"), IrQuantifier(0)),
    ],
    field_map={"true": 0, "ws": 1},
    non_semantic_fields=frozenset(["ws"]),
)


Object.__grammar__ = RuleSpec(
    rule_name="object",
    class_name="Object",
    parent_class_name="Value",
    kind="sequence",
    items=[
        IrItem(IrLiteral("{")),
        IrItem(IrRuleRef("ws"), IrQuantifier(0)),
        IrItem(IrRuleRef("object-item2"), IrQuantifier(0)),
        IrItem(IrLiteral("}")),
        IrItem(IrRuleRef("ws"), IrQuantifier(0)),
    ],
    field_map={"ws": 1, "object_item2": 2, "ws2": 4},
    non_semantic_fields=frozenset(["ws", "ws2"]),
)


Array.__grammar__ = RuleSpec(
    rule_name="array",
    class_name="Array",
    parent_class_name="Value",
    kind="sequence",
    items=[
        IrItem(IrLiteral("[")),
        IrItem(IrRuleRef("ws"), IrQuantifier(0)),
        IrItem(IrRuleRef("array-item2"), IrQuantifier(0)),
        IrItem(IrLiteral("]")),
        IrItem(IrRuleRef("ws"), IrQuantifier(0)),
    ],
    field_map={"ws": 1, "array_item2": 2, "ws2": 4},
    non_semantic_fields=frozenset(["ws", "ws2"]),
)


String.__grammar__ = RuleSpec(
    rule_name="string",
    class_name="String",
    parent_class_name="Value",
    kind="sequence",
    items=[
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
    ],
    field_map={"x80_u0010fff": 1, "ws": 3},
    non_semantic_fields=frozenset(["ws"]),
)


Number.__grammar__ = RuleSpec(
    rule_name="number",
    class_name="Number",
    parent_class_name="Value",
    kind="sequence",
    items=[
        IrItem(IrLiteral("-"), IrQuantifier(0)),
        IrItem(
            IrAlternation(
                IrSequence(IrItem(IrCharClass(IrRange(IrChr(48), IrChr(57))))),
                IrSequence(
                    IrItem(IrCharClass(IrRange(IrChr(49), IrChr(57)))),
                    IrItem(
                        IrCharClass(IrRange(IrChr(48), IrChr(57))), IrQuantifier(0, 15)
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
                    IrItem(IrCharClass(IrRange(IrChr(49), IrChr(57)))),
                    IrItem(
                        IrCharClass(IrRange(IrChr(48), IrChr(57))), IrQuantifier(0, 15)
                    ),
                )
            ),
            IrQuantifier(0),
        ),
        IrItem(IrRuleRef("ws"), IrQuantifier(0)),
    ],
    field_map={"sign": 0, "digit": 1, "dot": 2, "ee": 3, "ws": 4},
    non_semantic_fields=frozenset(["ws"]),
)


ArrItem.__grammar__ = RuleSpec(
    rule_name="arr-item",
    class_name="ArrItem",
    parent_class_name="GrammarModel",
    kind="sequence",
    items=[
        IrItem(IrLiteral(",\n")),
        IrItem(IrRuleRef("ws"), IrQuantifier(0)),
        IrItem(IrRuleRef("value")),
    ],
    field_map={"ws": 1, "value": 2},
    non_semantic_fields=frozenset(["ws"]),
)


ArrItem2.__grammar__ = RuleSpec(
    rule_name="arr-item2",
    class_name="ArrItem2",
    parent_class_name="GrammarModel",
    kind="sequence",
    items=[
        IrItem(IrRuleRef("value")),
        IrItem(IrRuleRef("arr-item"), IrQuantifier(0, IrNone)),
    ],
    field_map={"value": 0, "arr_item": 1},
    non_semantic_fields=frozenset([]),
)


ObjectItem.__grammar__ = RuleSpec(
    rule_name="object-item",
    class_name="ObjectItem",
    parent_class_name="GrammarModel",
    kind="sequence",
    items=[
        IrItem(IrLiteral(",")),
        IrItem(IrRuleRef("ws"), IrQuantifier(0)),
        IrItem(IrRuleRef("string")),
        IrItem(IrLiteral(":")),
        IrItem(IrRuleRef("ws"), IrQuantifier(0)),
        IrItem(IrRuleRef("value")),
    ],
    field_map={"ws": 1, "string": 2, "ws2": 4, "value": 5},
    non_semantic_fields=frozenset(["ws", "ws2"]),
)


ObjectItem2.__grammar__ = RuleSpec(
    rule_name="object-item2",
    class_name="ObjectItem2",
    parent_class_name="GrammarModel",
    kind="sequence",
    items=[
        IrItem(IrRuleRef("string")),
        IrItem(IrLiteral(":")),
        IrItem(IrRuleRef("ws"), IrQuantifier(0)),
        IrItem(IrRuleRef("value")),
        IrItem(IrRuleRef("object-item"), IrQuantifier(0, IrNone)),
    ],
    field_map={"string": 0, "ws": 2, "value": 3, "object_item": 4},
    non_semantic_fields=frozenset(["ws"]),
)


ArrayItem.__grammar__ = RuleSpec(
    rule_name="array-item",
    class_name="ArrayItem",
    parent_class_name="GrammarModel",
    kind="sequence",
    items=[
        IrItem(IrLiteral(",")),
        IrItem(IrRuleRef("ws"), IrQuantifier(0)),
        IrItem(IrRuleRef("value")),
    ],
    field_map={"ws": 1, "value": 2},
    non_semantic_fields=frozenset(["ws"]),
)


ArrayItem2.__grammar__ = RuleSpec(
    rule_name="array-item2",
    class_name="ArrayItem2",
    parent_class_name="GrammarModel",
    kind="sequence",
    items=[
        IrItem(IrRuleRef("value")),
        IrItem(IrRuleRef("array-item"), IrQuantifier(0, IrNone)),
    ],
    field_map={"value": 0, "array_item": 1},
    non_semantic_fields=frozenset([]),
)
