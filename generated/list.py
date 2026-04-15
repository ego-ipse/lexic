"""Auto-generated Pydantic models from resources/ground_truth/list.gbnf."""

from __future__ import annotations

from typing import List

from pydantic import BaseModel


class Root(BaseModel):
    """root ::= item+"""

    field1: List[Item]

    def to_text(self) -> str:
        return "".join(i.to_text() for i in self.field1)


class Item(BaseModel):
    """item ::= \"- \" [^\\r\\n\\x0b\\x0c\\x85\\u2028\\u2029]+ \"\\n\""""

    field1: str
    field2: str
    field3: str

    def to_text(self) -> str:
        return self.field1 + self.field2 + self.field3


# Resolve forward references
_ns = {k: v for k, v in globals().items() if isinstance(v, type)}
Root.model_rebuild(_types_namespace=_ns)
Item.model_rebuild(_types_namespace=_ns)
