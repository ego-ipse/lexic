# Generated from japanese.gbnf — DO NOT EDIT

from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Any, Optional, Union

class Object(BaseModel):
    strings: Optional[tuple[String, Value, list[tuple[String, Value]]]] = None

class Root(Object):
    pass

class Value(BaseModel):
    pass

class ObjectValue(Value):
    object: Object

class ArrayValue(Value):
    array: Array

class StringValue(Value):
    string: String

class NumberValue(Value):
    number: Number

class ValueLiteral(Value):
    value: str

class Array(BaseModel):
    values: Optional[tuple[Value, list[Value]]] = None

class String(BaseModel):
    items: list[Union[str, Union[str, tuple[str, str, str, str]]]] = Field(default_factory=list)

class Number(BaseModel):
    value: Union[str, tuple[str, list[str]]]
    items: Optional[list[str]] = None
    items_1: Optional[tuple[str, Optional[str], list[str]]] = None

class Ws(BaseModel):
    items: Optional[str] = Field(default_factory=list)


Object.model_rebuild()
Root.model_rebuild()
Value.model_rebuild()
ObjectValue.model_rebuild()
ArrayValue.model_rebuild()
StringValue.model_rebuild()
NumberValue.model_rebuild()
ValueLiteral.model_rebuild()
Array.model_rebuild()
String.model_rebuild()
Number.model_rebuild()
Ws.model_rebuild()
