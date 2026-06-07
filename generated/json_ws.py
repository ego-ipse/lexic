"""Generated module: json_ws. Do not edit; regenerated from grammar."""

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
    IrNot,
    IrQuantifier,
    IrRuleRef,
    IrSequence,
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

Pattern12 = Annotated[str, StringConstraints(pattern=r"^[1-9]{0,15}$")]

Pattern13 = Annotated[str, StringConstraints(pattern=r"^([eE][-+]?[0-9][1-9]{0,15})?$")]

Pattern14 = Annotated[str, StringConstraints(pattern=r"^[ \t]{0,20}$")]


class Root(GrammarModel):
    object: Object


class Value(GrammarModel):
    pass


class ValueArm5(Value):
    true: Pattern
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
    x7fx00_x1f: Pattern5
    ws: Optional[Ws] = None


class Number(Value):
    sign: Pattern8
    dot: Optional[Pattern9] = None
    ee: Optional[Pattern13] = None
    ws: Optional[Ws] = None


class Ws(GrammarModel):
    value: str


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
    items=[IrItem(atom=IrRuleRef("object"), quantifier=IrQuantifier(1, 1))],
    field_map={"object": 0},
    non_semantic_fields=frozenset([]),
)


Value.__grammar__ = RuleSpec(
    rule_name="value",
    class_name="Value",
    parent_class_name="GrammarModel",
    kind="alternation",
    items=[
        IrItem(atom=IrRuleRef("object"), quantifier=IrQuantifier(1, 1)),
        IrItem(atom=IrRuleRef("array"), quantifier=IrQuantifier(1, 1)),
        IrItem(atom=IrRuleRef("string"), quantifier=IrQuantifier(1, 1)),
        IrItem(atom=IrRuleRef("number"), quantifier=IrQuantifier(1, 1)),
        IrItem(atom=IrRuleRef("value-arm5"), quantifier=IrQuantifier(1, 1)),
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
            atom=IrGroup(
                body=IrAlternation(
                    IrSequence(
                        IrItem(atom=IrLiteral("true"), quantifier=IrQuantifier(1, 1))
                    ),
                    IrSequence(
                        IrItem(atom=IrLiteral("false"), quantifier=IrQuantifier(1, 1))
                    ),
                    IrSequence(
                        IrItem(atom=IrLiteral("null"), quantifier=IrQuantifier(1, 1))
                    ),
                )
            ),
            quantifier=IrQuantifier(1, 1),
        ),
        IrItem(atom=IrRuleRef("ws"), quantifier=IrQuantifier(0, 1)),
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
        IrItem(atom=IrLiteral("{"), quantifier=IrQuantifier(1, 1)),
        IrItem(atom=IrRuleRef("ws"), quantifier=IrQuantifier(0, 1)),
        IrItem(atom=IrRuleRef("object-item2"), quantifier=IrQuantifier(0, 1)),
        IrItem(atom=IrLiteral("}"), quantifier=IrQuantifier(1, 1)),
        IrItem(atom=IrRuleRef("ws"), quantifier=IrQuantifier(0, 1)),
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
        IrItem(atom=IrLiteral("["), quantifier=IrQuantifier(1, 1)),
        IrItem(atom=IrRuleRef("ws"), quantifier=IrQuantifier(0, 1)),
        IrItem(atom=IrRuleRef("array-item2"), quantifier=IrQuantifier(0, 1)),
        IrItem(atom=IrLiteral("]"), quantifier=IrQuantifier(1, 1)),
        IrItem(atom=IrRuleRef("ws"), quantifier=IrQuantifier(0, 1)),
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
        IrItem(atom=IrLiteral('"'), quantifier=IrQuantifier(1, 1)),
        IrItem(
            atom=IrGroup(
                body=IrAlternation(
                    IrSequence(
                        IrItem(
                            atom=IrNot(body=IrCharClass('"\\\\\\x7F\\x00-\\x1F')),
                            quantifier=IrQuantifier(1, 1),
                        )
                    ),
                    IrSequence(
                        IrItem(atom=IrLiteral("\\"), quantifier=IrQuantifier(1, 1)),
                        IrItem(
                            atom=IrGroup(
                                body=IrAlternation(
                                    IrSequence(
                                        IrItem(
                                            atom=IrCharClass('"\\\\bfnrt'),
                                            quantifier=IrQuantifier(1, 1),
                                        )
                                    ),
                                    IrSequence(
                                        IrItem(
                                            atom=IrLiteral("u"),
                                            quantifier=IrQuantifier(1, 1),
                                        ),
                                        IrItem(
                                            atom=IrCharClass("0-9a-fA-F"),
                                            quantifier=IrQuantifier(4, 4),
                                        ),
                                    ),
                                )
                            ),
                            quantifier=IrQuantifier(1, 1),
                        ),
                    ),
                )
            ),
            quantifier=IrQuantifier(0, None),
        ),
        IrItem(atom=IrLiteral('"'), quantifier=IrQuantifier(1, 1)),
        IrItem(atom=IrRuleRef("ws"), quantifier=IrQuantifier(0, 1)),
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
            atom=IrGroup(
                body=IrAlternation(
                    IrSequence(
                        IrItem(atom=IrLiteral("-"), quantifier=IrQuantifier(0, 1)),
                        IrItem(
                            atom=IrGroup(
                                body=IrAlternation(
                                    IrSequence(
                                        IrItem(
                                            atom=IrCharClass("0-9"),
                                            quantifier=IrQuantifier(1, 1),
                                        )
                                    ),
                                    IrSequence(
                                        IrItem(
                                            atom=IrCharClass("1-9"),
                                            quantifier=IrQuantifier(1, 1),
                                        ),
                                        IrItem(
                                            atom=IrCharClass("0-9"),
                                            quantifier=IrQuantifier(0, 15),
                                        ),
                                    ),
                                )
                            ),
                            quantifier=IrQuantifier(1, 1),
                        ),
                    )
                )
            ),
            quantifier=IrQuantifier(1, 1),
        ),
        IrItem(
            atom=IrGroup(
                body=IrAlternation(
                    IrSequence(
                        IrItem(atom=IrLiteral("."), quantifier=IrQuantifier(1, 1)),
                        IrItem(
                            atom=IrCharClass("0-9"), quantifier=IrQuantifier(1, None)
                        ),
                    )
                )
            ),
            quantifier=IrQuantifier(0, 1),
        ),
        IrItem(
            atom=IrGroup(
                body=IrAlternation(
                    IrSequence(
                        IrItem(atom=IrCharClass("eE"), quantifier=IrQuantifier(1, 1)),
                        IrItem(atom=IrCharClass("-+"), quantifier=IrQuantifier(0, 1)),
                        IrItem(atom=IrCharClass("0-9"), quantifier=IrQuantifier(1, 1)),
                        IrItem(atom=IrCharClass("1-9"), quantifier=IrQuantifier(0, 15)),
                    )
                )
            ),
            quantifier=IrQuantifier(0, 1),
        ),
        IrItem(atom=IrRuleRef("ws"), quantifier=IrQuantifier(0, 1)),
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
            IrSequence(),
            IrSequence(IrItem(atom=IrLiteral(" "), quantifier=IrQuantifier(1, 1))),
            IrSequence(
                IrItem(atom=IrLiteral("\n"), quantifier=IrQuantifier(1, 1)),
                IrItem(atom=IrCharClass(" \\t"), quantifier=IrQuantifier(0, 20)),
            ),
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
        IrItem(atom=IrLiteral(","), quantifier=IrQuantifier(1, 1)),
        IrItem(atom=IrRuleRef("ws"), quantifier=IrQuantifier(0, 1)),
        IrItem(atom=IrRuleRef("string"), quantifier=IrQuantifier(1, 1)),
        IrItem(atom=IrLiteral(":"), quantifier=IrQuantifier(1, 1)),
        IrItem(atom=IrRuleRef("ws"), quantifier=IrQuantifier(0, 1)),
        IrItem(atom=IrRuleRef("value"), quantifier=IrQuantifier(1, 1)),
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
        IrItem(atom=IrRuleRef("string"), quantifier=IrQuantifier(1, 1)),
        IrItem(atom=IrLiteral(":"), quantifier=IrQuantifier(1, 1)),
        IrItem(atom=IrRuleRef("ws"), quantifier=IrQuantifier(0, 1)),
        IrItem(atom=IrRuleRef("value"), quantifier=IrQuantifier(1, 1)),
        IrItem(atom=IrRuleRef("object-item"), quantifier=IrQuantifier(0, None)),
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
        IrItem(atom=IrLiteral(","), quantifier=IrQuantifier(1, 1)),
        IrItem(atom=IrRuleRef("ws"), quantifier=IrQuantifier(0, 1)),
        IrItem(atom=IrRuleRef("value"), quantifier=IrQuantifier(1, 1)),
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
        IrItem(atom=IrRuleRef("value"), quantifier=IrQuantifier(1, 1)),
        IrItem(atom=IrRuleRef("array-item"), quantifier=IrQuantifier(0, None)),
    ],
    field_map={"value": 0, "array_item": 1},
    non_semantic_fields=frozenset([]),
)
