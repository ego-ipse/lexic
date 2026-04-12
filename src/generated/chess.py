# Generated from chess.gbnf by src/codegen.py — DO NOT EDIT

from __future__ import annotations
from typing import Any, Optional, Union
from pydantic import BaseModel, Field

class Object(BaseModel):
    ws: Ws
    string: Optional[tuple[String, Ws, Value, list[tuple[Ws, String, Ws, Value]]]] = None
    ws_1: Ws

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

class ValueAlt4(Value):
    value: str
    ws: Ws

class Array(BaseModel):
    ws: Ws
    value: Optional[tuple[Value, list[tuple[Ws, Value]]]] = None
    ws_1: Ws

class String(BaseModel):
    items: list[Union[str, Union[str, tuple[str, str, str, str]]]] = Field(default_factory=list)
    ws: Ws

class Number(BaseModel):
    value: Union[str, tuple[str, list[str]]]
    items: Optional[list[str]] = None
    items_1: Optional[tuple[str, Optional[str], list[str]]] = None
    ws: Ws

class Ws(BaseModel):
    items: Optional[tuple[str, Ws]] = None


Object.model_rebuild()
Root.model_rebuild()
Value.model_rebuild()
ObjectValue.model_rebuild()
ArrayValue.model_rebuild()
StringValue.model_rebuild()
NumberValue.model_rebuild()
ValueAlt4.model_rebuild()
Array.model_rebuild()
String.model_rebuild()
Number.model_rebuild()
Ws.model_rebuild()
