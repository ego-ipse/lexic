"""Auto-generated Pydantic models from /home/mika/projects/lexic/resources/ground_truth/json_ws.gbnf."""
from __future__ import annotations

from abc import ABC
from typing import ClassVar, List, Optional

from lexic.base import GrammarModel
from lexic.ir import RuleSpec, AlternationAtom, CharClassAtom, InlineRegexAtom, LiteralAtom, QuantifiedLiteralAtom, RuleRefAtom


class Root(GrammarModel):
    """root ::= (see __grammar__)"""
    __grammar__: ClassVar[RuleSpec] = RuleSpec(
        rule_name="root",
        class_name="Root",
        parent_class_name="GrammarModel",
        kind="sequence",
        items=[RuleRefAtom("object", min=1, max=1)],
        field_map={"object": 0},
    )
    object: Object


class Value(GrammarModel, ABC):
    """value ::= (see __grammar__)"""
    __grammar__: ClassVar[RuleSpec] = RuleSpec(
        rule_name="value",
        class_name="Value",
        parent_class_name="GrammarModel",
        kind="alternation",
        items=[AlternationAtom(["object", "array", "string", "number", "value-arm5"])],
        field_map={},
    )
    pass


class ValueArm5(Value):
    """value-arm5 ::= (see __grammar__)"""
    __grammar__: ClassVar[RuleSpec] = RuleSpec(
        rule_name="value-arm5",
        class_name="ValueArm5",
        parent_class_name="Value",
        kind="sequence",
        items=[InlineRegexAtom("(true|false|null)", "(\"true\"|\"false\"|\"null\")", min=1, max=1)],
        field_map={"first": 0},
    )
    first: str


class ObjectitemItem(GrammarModel):
    """objectitem-item ::= (see __grammar__)"""
    __grammar__: ClassVar[RuleSpec] = RuleSpec(
        rule_name="objectitem-item",
        class_name="ObjectitemItem",
        parent_class_name="GrammarModel",
        kind="sequence",
        items=[LiteralAtom(","), RuleRefAtom("string", min=1, max=1), LiteralAtom(":"), RuleRefAtom("value", min=1, max=1)],
        field_map={"string": 1, "value": 3},
    )
    string: String
    value: Value


class ObjectItem(GrammarModel):
    """object-item ::= (see __grammar__)"""
    __grammar__: ClassVar[RuleSpec] = RuleSpec(
        rule_name="object-item",
        class_name="ObjectItem",
        parent_class_name="GrammarModel",
        kind="sequence",
        items=[RuleRefAtom("string", min=1, max=1), LiteralAtom(":"), RuleRefAtom("value", min=1, max=1), RuleRefAtom("objectitem-item", min=0, max=None)],
        field_map={"string": 0, "value": 2, "objectitem_item": 3},
    )
    string: String
    value: Value
    objectitem_item: List[ObjectitemItem]


class Object(Value):
    """object ::= (see __grammar__)"""
    __grammar__: ClassVar[RuleSpec] = RuleSpec(
        rule_name="object",
        class_name="Object",
        parent_class_name="Value",
        kind="sequence",
        items=[LiteralAtom("{"), RuleRefAtom("ws", min=1, max=1), RuleRefAtom("object-item", min=0, max=1), LiteralAtom("}"), RuleRefAtom("ws", min=1, max=1)],
        field_map={"ws": 1, "object_item": 2, "ws2": 4},
    )
    ws: Ws
    object_item: Optional[ObjectItem] = None
    ws2: Ws


class ArrayitemItem(GrammarModel):
    """arrayitem-item ::= (see __grammar__)"""
    __grammar__: ClassVar[RuleSpec] = RuleSpec(
        rule_name="arrayitem-item",
        class_name="ArrayitemItem",
        parent_class_name="GrammarModel",
        kind="sequence",
        items=[LiteralAtom(","), RuleRefAtom("value", min=1, max=1)],
        field_map={"value": 1},
    )
    value: Value


class ArrayItem(GrammarModel):
    """array-item ::= (see __grammar__)"""
    __grammar__: ClassVar[RuleSpec] = RuleSpec(
        rule_name="array-item",
        class_name="ArrayItem",
        parent_class_name="GrammarModel",
        kind="sequence",
        items=[RuleRefAtom("value", min=1, max=1), RuleRefAtom("arrayitem-item", min=0, max=None)],
        field_map={"value": 0, "arrayitem_item": 1},
    )
    value: Value
    arrayitem_item: List[ArrayitemItem]


class Array(Value):
    """array ::= (see __grammar__)"""
    __grammar__: ClassVar[RuleSpec] = RuleSpec(
        rule_name="array",
        class_name="Array",
        parent_class_name="Value",
        kind="sequence",
        items=[LiteralAtom("["), RuleRefAtom("ws", min=1, max=1), RuleRefAtom("array-item", min=0, max=1), LiteralAtom("]"), RuleRefAtom("ws", min=1, max=1)],
        field_map={"ws": 1, "array_item": 2, "ws2": 4},
    )
    ws: Ws
    array_item: Optional[ArrayItem] = None
    ws2: Ws


class String(Value):
    """string ::= (see __grammar__)"""
    __grammar__: ClassVar[RuleSpec] = RuleSpec(
        rule_name="string",
        class_name="String",
        parent_class_name="Value",
        kind="value_str",
        items=[LiteralAtom("\\\""), InlineRegexAtom("([^\"\\\\\\x7F\\x00-\\x1F]|\\\\\\\\([\"\\\\bfnrt]|u[0-9a-fA-F]{4}))", "([^\"\\\\\\x7F\\x00-\\x1F]|\"\\\\\"([\"\\\\bfnrt]|\"u\"[0-9a-fA-F]{4}))", min=0, max=None), LiteralAtom("\\\"")],
        field_map={},
    )
    value: str


class Number(Value):
    """number ::= (see __grammar__)"""
    __grammar__: ClassVar[RuleSpec] = RuleSpec(
        rule_name="number",
        class_name="Number",
        parent_class_name="Value",
        kind="sequence",
        items=[QuantifiedLiteralAtom("-", min=0, max=1), InlineRegexAtom("([0-9]|[1-9][0-9]{0,15})", "([0-9]|[1-9][0-9]{0,15})", min=1, max=1), InlineRegexAtom("\\.[0-9]+", "\".\"[0-9]+", min=0, max=1), InlineRegexAtom("[eE][-+]?[0-9][1-9]{0,15}", "[eE][-+]?[0-9][1-9]{0,15}", min=0, max=1), RuleRefAtom("ws", min=1, max=1)],
        field_map={"first": 0, "second": 1, "third": 2, "fourth": 3, "ws": 4},
    )
    first: str
    second: str
    third: str
    fourth: str
    ws: Ws


class Ws(GrammarModel):
    """ws ::= (see __grammar__)"""
    __grammar__: ClassVar[RuleSpec] = RuleSpec(
        rule_name="ws",
        class_name="Ws",
        parent_class_name="GrammarModel",
        kind="value_str",
        items=[LiteralAtom(" "), LiteralAtom("\\n"), CharClassAtom("[ \\t]", min=0, max=20)],
        field_map={},
    )
    value: str


# Resolve forward references
_ns = {k: v for k, v in globals().items() if isinstance(v, type)}
Root.model_rebuild(_types_namespace=_ns)
Value.model_rebuild(_types_namespace=_ns)
ValueArm5.model_rebuild(_types_namespace=_ns)
ObjectitemItem.model_rebuild(_types_namespace=_ns)
ObjectItem.model_rebuild(_types_namespace=_ns)
Object.model_rebuild(_types_namespace=_ns)
ArrayitemItem.model_rebuild(_types_namespace=_ns)
ArrayItem.model_rebuild(_types_namespace=_ns)
Array.model_rebuild(_types_namespace=_ns)
String.model_rebuild(_types_namespace=_ns)
Number.model_rebuild(_types_namespace=_ns)
Ws.model_rebuild(_types_namespace=_ns)
