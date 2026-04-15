"""Auto-generated Pydantic models from json_ws.gbnf."""

from __future__ import annotations

from abc import ABC
from typing import List, Optional

from pydantic import BaseModel


class Root(BaseModel):
    field1: Object


class Value(BaseModel, ABC):
    pass


class ValueArm5(Value):
    field1: str


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
    field1: str
    field2: Optional[ArrayOpt]
    field3: str


class String(Value):
    value: str


class Number(Value):
    value: str


class Ws(BaseModel):
    value: str


# Resolve forward references
_ns = {k: v for k, v in globals().items() if isinstance(v, type)}
Root.model_rebuild(_types_namespace=_ns)
Value.model_rebuild(_types_namespace=_ns)
ValueArm5.model_rebuild(_types_namespace=_ns)
ObjectOptItem.model_rebuild(_types_namespace=_ns)
ObjectOpt.model_rebuild(_types_namespace=_ns)
Object.model_rebuild(_types_namespace=_ns)
ArrayOptItem.model_rebuild(_types_namespace=_ns)
ArrayOpt.model_rebuild(_types_namespace=_ns)
Array.model_rebuild(_types_namespace=_ns)
String.model_rebuild(_types_namespace=_ns)
Number.model_rebuild(_types_namespace=_ns)
Ws.model_rebuild(_types_namespace=_ns)
