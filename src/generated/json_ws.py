# Generated from json_ws.gbnf by src/codegen.py — DO NOT EDIT

from __future__ import annotations
from typing import Any, Optional, Union
from pydantic import BaseModel, Field

class Object(BaseModel):
    string: Optional[tuple[str, Value, list[tuple[str, Value]]]] = None

class Root(Object):
    pass

class Value(BaseModel):
    pass

class ObjectValue(Value):
    object: Object

class ArrayValue(Value):
    array: Array

class StringValue(Value):
    value: str

class NumberValue(Value):
    value: str

class ValueAlt4(Value):
    value: str

class Array(BaseModel):
    value: Optional[tuple[Value, list[Value]]] = None


Object.model_rebuild()
Root.model_rebuild()
Value.model_rebuild()
ObjectValue.model_rebuild()
ArrayValue.model_rebuild()
StringValue.model_rebuild()
NumberValue.model_rebuild()
ValueAlt4.model_rebuild()
Array.model_rebuild()
