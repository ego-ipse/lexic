"""Generated module: json_arr. Do not edit; regenerated from grammar."""

from __future__ import annotations
from typing import Annotated, List, Optional

from pydantic import StringConstraints

from lexic.base import GrammarModel
from lexic.ir.nodes import (
    IrAlternation,
    IrCharClass,
    IrGroup,
    IrItem,
    IrLiteral,
    IrRuleRef,
    IrSequence,
    Quantifier,
)
from lexic.ir.spec import RuleSpec

Pattern = Annotated[str, StringConstraints(pattern=r"^(true|false|null)$")]

Pattern2 = Annotated[str, StringConstraints(pattern=r'^[^"\\\x7F\x00-\x1F]$')]

Pattern3 = Annotated[str, StringConstraints(pattern=r'^["\\bfnrt]$')]

Hex = Annotated[str, StringConstraints(pattern=r"^[0-9a-fA-F]{4}$")]

Pattern4 = Annotated[str, StringConstraints(pattern=r'^(["\\bfnrt]|u[0-9a-fA-F]{4})$')]

Pattern5 = Annotated[
    str,
    StringConstraints(
        pattern=r'^([^"\\\x7F\x00-\x1F]|\\(["\\bfnrt]|u[0-9a-fA-F]{4}))*$'
    ),
]

Digit = Annotated[str, StringConstraints(pattern=r"^[0-9]$")]

Pattern6 = Annotated[str, StringConstraints(pattern=r"^[1-9]$")]

Digit2 = Annotated[str, StringConstraints(pattern=r"^[0-9]{0,15}$")]

Pattern7 = Annotated[str, StringConstraints(pattern=r"^([0-9]|[1-9][0-9]{0,15})$")]

Pattern8 = Annotated[str, StringConstraints(pattern=r"^(\-?([0-9]|[1-9][0-9]{0,15}))$")]

Digit3 = Annotated[str, StringConstraints(pattern=r"^[0-9]+$")]

Pattern9 = Annotated[str, StringConstraints(pattern=r"^(\.[0-9]+)?$")]

Pattern10 = Annotated[str, StringConstraints(pattern=r"^[eE]$")]

Pattern11 = Annotated[str, StringConstraints(pattern=r"^[-+]?$")]

Pattern12 = Annotated[str, StringConstraints(pattern=r"^([eE][-+]?[1-9][0-9]{0,15})?$")]

Pattern13 = Annotated[str, StringConstraints(pattern=r"^[ \t]{0,20}$")]


class Root(GrammarModel):
    arr: Arr


class Value(GrammarModel):
    pass


class ValueArm5(Value):
    true: Pattern
    ws: Optional[Ws] = None


class Arr(GrammarModel):
    ws: Optional[Ws] = None
    arr_item2: Optional[ArrItem2] = None


class Object(Value):
    ws: Optional[Ws] = None
    object_item2: Optional[ObjectItem2] = None
    ws2: Optional[Ws] = None


class Array(Value):
    ws: Optional[Ws] = None
    array_item2: Optional[ArrayItem2] = None
    ws2: Optional[Ws] = None


class String(Value):
    x7fx00_x1f: Pattern5
    ws: Optional[Ws] = None


class Number(Value):
    sign: Pattern8
    dot: Optional[Pattern9] = None
    ee: Optional[Pattern12] = None
    ws: Optional[Ws] = None


class Ws(GrammarModel):
    value: str


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
    items=[IrItem(IrRuleRef("arr"), Quantifier(1, 1))],
    field_map={"arr": 0},
    non_semantic_fields=frozenset([]),
)


Value.__grammar__ = RuleSpec(
    rule_name="value",
    class_name="Value",
    parent_class_name="GrammarModel",
    kind="alternation",
    items=[
        IrItem(IrRuleRef("object"), Quantifier(1, 1)),
        IrItem(IrRuleRef("array"), Quantifier(1, 1)),
        IrItem(IrRuleRef("string"), Quantifier(1, 1)),
        IrItem(IrRuleRef("number"), Quantifier(1, 1)),
        IrItem(IrRuleRef("value-arm5"), Quantifier(1, 1)),
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
            IrGroup(
                IrAlternation(
                    arms=(
                        IrSequence(
                            items=(IrItem(IrLiteral("true"), Quantifier(1, 1)),)
                        ),
                        IrSequence(
                            items=(IrItem(IrLiteral("false"), Quantifier(1, 1)),)
                        ),
                        IrSequence(
                            items=(IrItem(IrLiteral("null"), Quantifier(1, 1)),)
                        ),
                    )
                )
            ),
            Quantifier(1, 1),
        ),
        IrItem(IrRuleRef("ws"), Quantifier(0, 1)),
    ],
    field_map={"true": 0, "ws": 1},
    non_semantic_fields=frozenset(["ws"]),
)


Arr.__grammar__ = RuleSpec(
    rule_name="arr",
    class_name="Arr",
    parent_class_name="GrammarModel",
    kind="sequence",
    items=[
        IrItem(IrLiteral("[\n"), Quantifier(1, 1)),
        IrItem(IrRuleRef("ws"), Quantifier(0, 1)),
        IrItem(IrRuleRef("arr-item2"), Quantifier(0, 1)),
        IrItem(IrLiteral("]"), Quantifier(1, 1)),
    ],
    field_map={"ws": 1, "arr_item2": 2},
    non_semantic_fields=frozenset(["ws"]),
)


Object.__grammar__ = RuleSpec(
    rule_name="object",
    class_name="Object",
    parent_class_name="Value",
    kind="sequence",
    items=[
        IrItem(IrLiteral("{"), Quantifier(1, 1)),
        IrItem(IrRuleRef("ws"), Quantifier(0, 1)),
        IrItem(IrRuleRef("object-item2"), Quantifier(0, 1)),
        IrItem(IrLiteral("}"), Quantifier(1, 1)),
        IrItem(IrRuleRef("ws"), Quantifier(0, 1)),
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
        IrItem(IrLiteral("["), Quantifier(1, 1)),
        IrItem(IrRuleRef("ws"), Quantifier(0, 1)),
        IrItem(IrRuleRef("array-item2"), Quantifier(0, 1)),
        IrItem(IrLiteral("]"), Quantifier(1, 1)),
        IrItem(IrRuleRef("ws"), Quantifier(0, 1)),
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
        IrItem(IrLiteral('"'), Quantifier(1, 1)),
        IrItem(
            IrGroup(
                IrAlternation(
                    arms=(
                        IrSequence(
                            items=(
                                IrItem(
                                    IrCharClass('"\\\\\\x7F\\x00-\\x1F', negated=True),
                                    Quantifier(1, 1),
                                ),
                            )
                        ),
                        IrSequence(
                            items=(
                                IrItem(IrLiteral("\\"), Quantifier(1, 1)),
                                IrItem(
                                    IrGroup(
                                        IrAlternation(
                                            arms=(
                                                IrSequence(
                                                    items=(
                                                        IrItem(
                                                            IrCharClass(
                                                                '"\\\\bfnrt',
                                                                negated=False,
                                                            ),
                                                            Quantifier(1, 1),
                                                        ),
                                                    )
                                                ),
                                                IrSequence(
                                                    items=(
                                                        IrItem(
                                                            IrLiteral("u"),
                                                            Quantifier(1, 1),
                                                        ),
                                                        IrItem(
                                                            IrCharClass(
                                                                "0-9a-fA-F",
                                                                negated=False,
                                                            ),
                                                            Quantifier(4, 4),
                                                        ),
                                                    )
                                                ),
                                            )
                                        )
                                    ),
                                    Quantifier(1, 1),
                                ),
                            )
                        ),
                    )
                )
            ),
            Quantifier(0, None),
        ),
        IrItem(IrLiteral('"'), Quantifier(1, 1)),
        IrItem(IrRuleRef("ws"), Quantifier(0, 1)),
    ],
    field_map={"x7fx00_x1f": 1, "ws": 3},
    non_semantic_fields=frozenset(["ws"]),
)


Number.__grammar__ = RuleSpec(
    rule_name="number",
    class_name="Number",
    parent_class_name="Value",
    kind="sequence",
    items=[
        IrItem(
            IrGroup(
                IrAlternation(
                    arms=(
                        IrSequence(
                            items=(
                                IrItem(IrLiteral("-"), Quantifier(0, 1)),
                                IrItem(
                                    IrGroup(
                                        IrAlternation(
                                            arms=(
                                                IrSequence(
                                                    items=(
                                                        IrItem(
                                                            IrCharClass(
                                                                "0-9", negated=False
                                                            ),
                                                            Quantifier(1, 1),
                                                        ),
                                                    )
                                                ),
                                                IrSequence(
                                                    items=(
                                                        IrItem(
                                                            IrCharClass(
                                                                "1-9", negated=False
                                                            ),
                                                            Quantifier(1, 1),
                                                        ),
                                                        IrItem(
                                                            IrCharClass(
                                                                "0-9", negated=False
                                                            ),
                                                            Quantifier(0, 15),
                                                        ),
                                                    )
                                                ),
                                            )
                                        )
                                    ),
                                    Quantifier(1, 1),
                                ),
                            )
                        ),
                    )
                )
            ),
            Quantifier(1, 1),
        ),
        IrItem(
            IrGroup(
                IrAlternation(
                    arms=(
                        IrSequence(
                            items=(
                                IrItem(IrLiteral("."), Quantifier(1, 1)),
                                IrItem(
                                    IrCharClass("0-9", negated=False),
                                    Quantifier(1, None),
                                ),
                            )
                        ),
                    )
                )
            ),
            Quantifier(0, 1),
        ),
        IrItem(
            IrGroup(
                IrAlternation(
                    arms=(
                        IrSequence(
                            items=(
                                IrItem(
                                    IrCharClass("eE", negated=False), Quantifier(1, 1)
                                ),
                                IrItem(
                                    IrCharClass("-+", negated=False), Quantifier(0, 1)
                                ),
                                IrItem(
                                    IrCharClass("1-9", negated=False), Quantifier(1, 1)
                                ),
                                IrItem(
                                    IrCharClass("0-9", negated=False), Quantifier(0, 15)
                                ),
                            )
                        ),
                    )
                )
            ),
            Quantifier(0, 1),
        ),
        IrItem(IrRuleRef("ws"), Quantifier(0, 1)),
    ],
    field_map={"sign": 0, "dot": 1, "ee": 2, "ws": 3},
    non_semantic_fields=frozenset(["ws"]),
)


Ws.__grammar__ = RuleSpec(
    rule_name="ws",
    class_name="Ws",
    parent_class_name="GrammarModel",
    kind="value_str",
    items=[
        IrAlternation(
            arms=(
                IrSequence(items=()),
                IrSequence(items=(IrItem(IrLiteral(" "), Quantifier(1, 1)),)),
                IrSequence(
                    items=(
                        IrItem(IrLiteral("\n"), Quantifier(1, 1)),
                        IrItem(IrCharClass(" \\t", negated=False), Quantifier(0, 20)),
                    )
                ),
            )
        )
    ],
    field_map={},
    non_semantic_fields=frozenset([]),
)


ArrItem.__grammar__ = RuleSpec(
    rule_name="arr-item",
    class_name="ArrItem",
    parent_class_name="GrammarModel",
    kind="sequence",
    items=[
        IrItem(IrLiteral(",\n"), Quantifier(1, 1)),
        IrItem(IrRuleRef("ws"), Quantifier(0, 1)),
        IrItem(IrRuleRef("value"), Quantifier(1, 1)),
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
        IrItem(IrRuleRef("value"), Quantifier(1, 1)),
        IrItem(IrRuleRef("arr-item"), Quantifier(0, None)),
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
        IrItem(IrLiteral(","), Quantifier(1, 1)),
        IrItem(IrRuleRef("ws"), Quantifier(0, 1)),
        IrItem(IrRuleRef("string"), Quantifier(1, 1)),
        IrItem(IrLiteral(":"), Quantifier(1, 1)),
        IrItem(IrRuleRef("ws"), Quantifier(0, 1)),
        IrItem(IrRuleRef("value"), Quantifier(1, 1)),
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
        IrItem(IrRuleRef("string"), Quantifier(1, 1)),
        IrItem(IrLiteral(":"), Quantifier(1, 1)),
        IrItem(IrRuleRef("ws"), Quantifier(0, 1)),
        IrItem(IrRuleRef("value"), Quantifier(1, 1)),
        IrItem(IrRuleRef("object-item"), Quantifier(0, None)),
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
        IrItem(IrLiteral(","), Quantifier(1, 1)),
        IrItem(IrRuleRef("ws"), Quantifier(0, 1)),
        IrItem(IrRuleRef("value"), Quantifier(1, 1)),
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
        IrItem(IrRuleRef("value"), Quantifier(1, 1)),
        IrItem(IrRuleRef("array-item"), Quantifier(0, None)),
    ],
    field_map={"value": 0, "array_item": 1},
    non_semantic_fields=frozenset([]),
)
