"""Auto-generated Pydantic models from japanese.gbnf."""

from __future__ import annotations

from abc import ABC
from typing import List

from pydantic import BaseModel


class RootItem(BaseModel):
    field1: str
    field2: List[JpChar]


class Root(BaseModel):
    field1: List[JpChar]
    field2: List[RootItem]


class JpChar(BaseModel, ABC):
    pass


class Hiragana(JpChar):
    field1: str


class Katakana(JpChar):
    field1: str


class Punctuation(JpChar):
    field1: str


class Cjk(JpChar):
    field1: str


# Resolve forward references
_ns = {k: v for k, v in globals().items() if isinstance(v, type)}
RootItem.model_rebuild(_types_namespace=_ns)
Root.model_rebuild(_types_namespace=_ns)
JpChar.model_rebuild(_types_namespace=_ns)
Hiragana.model_rebuild(_types_namespace=_ns)
Katakana.model_rebuild(_types_namespace=_ns)
Punctuation.model_rebuild(_types_namespace=_ns)
Cjk.model_rebuild(_types_namespace=_ns)
