"""Auto-generated Pydantic models from /home/mika/projects/vyx_2/resources/ground_truth/list.gbnf."""
from __future__ import annotations

from typing import List

from pydantic import BaseModel


class Root(BaseModel):
    """root ::= item+"""
    field1: List[Item]


class Item(BaseModel):
    """item ::= \"- \" [^\\r\\n\\x0b\\x0c\\x85\\u2028\\u2029]+ \"\\n\""""
    field1: str
    field2: str
    field3: str


# Resolve forward references
_ns = {k: v for k, v in globals().items() if isinstance(v, type)}
Root.model_rebuild(_types_namespace=_ns)
Item.model_rebuild(_types_namespace=_ns)
