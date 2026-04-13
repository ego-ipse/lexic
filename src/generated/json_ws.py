# Generated from json_ws.gbnf — DO NOT EDIT

from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Any, Optional, Union
from src.base import GrammarNode

class Object(GrammarNode):
    strings: Optional[tuple[str, Value, list[tuple[str, Value]]]] = None

class Root(Object):
    pass

class Value(GrammarNode):
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

class Array(GrammarNode):
    values: Optional[tuple[Value, list[Value]]] = None


Object.model_rebuild()
Root.model_rebuild()
Value.model_rebuild()
ObjectValue.model_rebuild()
ArrayValue.model_rebuild()
StringValue.model_rebuild()
NumberValue.model_rebuild()
ValueAlt4.model_rebuild()
Array.model_rebuild()
