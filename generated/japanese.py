"""Auto-generated Pydantic models from resources/ground_truth/japanese.gbnf."""

from __future__ import annotations

from abc import ABC
from typing import List

from pydantic import BaseModel


class RootItem(BaseModel):
    field1: str
    field2: List[JpChar]

    def to_text(self) -> str:
        return self.field1 + "".join(i.to_text() for i in self.field2)


class Root(BaseModel):
    """root ::= jp-char+ ([ \\t\\n] jp-char+)*"""

    field1: List[JpChar]
    field2: List[RootItem]

    def to_text(self) -> str:
        return "".join(i.to_text() for i in self.field1) + "".join(
            i.to_text() for i in self.field2
        )


class JpChar(BaseModel, ABC):
    """jp-char ::= hiragana | katakana | punctuation | cjk"""

    pass

    def to_text(self) -> str:
        raise NotImplementedError


class Hiragana(JpChar):
    """hiragana ::= [ぁ-ゟ]"""

    field1: str

    def to_text(self) -> str:
        return self.field1


class Katakana(JpChar):
    """katakana ::= [ァ-ヿ]"""

    field1: str

    def to_text(self) -> str:
        return self.field1


class Punctuation(JpChar):
    """punctuation ::= [、-〾]"""

    field1: str

    def to_text(self) -> str:
        return self.field1


class Cjk(JpChar):
    """cjk ::= [一-鿿]"""

    field1: str

    def to_text(self) -> str:
        return self.field1


# Resolve forward references
_ns = {k: v for k, v in globals().items() if isinstance(v, type)}
RootItem.model_rebuild(_types_namespace=_ns)
Root.model_rebuild(_types_namespace=_ns)
JpChar.model_rebuild(_types_namespace=_ns)
Hiragana.model_rebuild(_types_namespace=_ns)
Katakana.model_rebuild(_types_namespace=_ns)
Punctuation.model_rebuild(_types_namespace=_ns)
Cjk.model_rebuild(_types_namespace=_ns)
