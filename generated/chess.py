"""Auto-generated Pydantic models from resources/ground_truth/chess.gbnf."""
from __future__ import annotations

from typing import List, Optional, Union

from pydantic import BaseModel


class RootItem(BaseModel):
    field1: str
    field2: Optional[str]
    field3: str
    field4: Move
    field5: str
    field6: Move
    field7: str


class Root(BaseModel):
    """root ::= \"1. \" move \" \" move \"\\n\" ([1-9] [0-9]? \". \" move \" \" move \"\\n\")+"""
    field1: str
    field2: Move
    field3: str
    field4: Move
    field5: str
    field6: List[RootItem]


class Move(BaseModel):
    """move ::= (pawn | nonpawn | castle) [+#]?"""
    field1: Union[Pawn, Nonpawn, Castle]
    field2: Optional[str]


class Nonpawn(BaseModel):
    """nonpawn ::= [NBKQR] [a-h]? [1-8]? \"x\"? [a-h] [1-8]"""
    field1: str
    field2: Optional[str]
    field3: Optional[str]
    field4: Optional[str]
    field5: str
    field6: str


class PawnOpt1(BaseModel):
    field1: str
    field2: str


class PawnOpt2(BaseModel):
    field1: str
    field2: str


class Pawn(BaseModel):
    """pawn ::= ([a-h] \"x\")? [a-h] [1-8] (\"=\" [NBKQR])?"""
    field1: Optional[PawnOpt1]
    field2: str
    field3: str
    field4: Optional[PawnOpt2]


class Castle(BaseModel):
    """castle ::= \"O-O\" \"-O\"?"""
    field1: str
    field2: Optional[str]


# Resolve forward references
_ns = {k: v for k, v in globals().items() if isinstance(v, type)}
RootItem.model_rebuild(_types_namespace=_ns)
Root.model_rebuild(_types_namespace=_ns)
Move.model_rebuild(_types_namespace=_ns)
Nonpawn.model_rebuild(_types_namespace=_ns)
PawnOpt1.model_rebuild(_types_namespace=_ns)
PawnOpt2.model_rebuild(_types_namespace=_ns)
Pawn.model_rebuild(_types_namespace=_ns)
Castle.model_rebuild(_types_namespace=_ns)
