"""Auto-generated Pydantic models from resources/ground_truth/json_arr.gbnf."""
from __future__ import annotations

from abc import ABC
from typing import List, Optional

from pydantic import BaseModel


class Root(BaseModel):
    """root ::= arr"""
    field1: Arr


class Value(BaseModel, ABC):
    """value ::= object | array | string | number | (\"true\" | \"false\" | \"null\") ws"""
    pass


class ValueArm5(Value):
    """Anonymous arm 5 of value"""
    field1: str


class ArrOptItem(BaseModel):
    field1: str
    field2: Value


class ArrOpt(BaseModel):
    field1: Value
    field2: List[ArrOptItem]


class Arr(BaseModel):
    """arr ::= \"[\\n\" ws (value (\",\\n\" ws value)*)? \"]\""""
    field1: str
    field2: Optional[ArrOpt]
    field3: str


class ObjectOptItem(BaseModel):
    field1: str
    field2: String
    field3: str
    field4: Value


class ObjectOpt(BaseModel):
    field1: String
    field2: str
    field3: Value
    field4: List[ObjectOptItem]


class Object(Value):
    """object ::= \"{\" ws (string \":\" ws value (\",\" ws string \":\" ws value)*)? \"}\" ws"""
    field1: str
    field2: Optional[ObjectOpt]
    field3: str


class ArrayOptItem(BaseModel):
    field1: str
    field2: Value


class ArrayOpt(BaseModel):
    field1: Value
    field2: List[ArrayOptItem]


class Array(Value):
    """array ::= \"[\" ws (value (\",\" ws value)*)? \"]\" ws"""
    field1: str
    field2: Optional[ArrayOpt]
    field3: str


class String(Value):
    """string ::= \"\\\"\" ([^\"\\\\\\x7F\\x00-\\x1F] | \"\\\\\" ([\"\\\\bfnrt] | \"u\" [0-9a-fA-F]))* \"\\\"\" ws"""
    value: str


class Number(Value):
    """number ::= (\"-\"? ([0-9] | [1-9] [0-9])) (\".\" [0-9]+)? ([eE] [-+]? [1-9] [0-9])? ws"""
    value: str


class Ws(BaseModel):
    """ws ::=  | \" \" | \"\\n\" [ \\t]"""
    value: str


# Resolve forward references
_ns = {k: v for k, v in globals().items() if isinstance(v, type)}
Root.model_rebuild(_types_namespace=_ns)
Value.model_rebuild(_types_namespace=_ns)
ValueArm5.model_rebuild(_types_namespace=_ns)
ArrOptItem.model_rebuild(_types_namespace=_ns)
ArrOpt.model_rebuild(_types_namespace=_ns)
Arr.model_rebuild(_types_namespace=_ns)
ObjectOptItem.model_rebuild(_types_namespace=_ns)
ObjectOpt.model_rebuild(_types_namespace=_ns)
Object.model_rebuild(_types_namespace=_ns)
ArrayOptItem.model_rebuild(_types_namespace=_ns)
ArrayOpt.model_rebuild(_types_namespace=_ns)
Array.model_rebuild(_types_namespace=_ns)
String.model_rebuild(_types_namespace=_ns)
Number.model_rebuild(_types_namespace=_ns)
Ws.model_rebuild(_types_namespace=_ns)
