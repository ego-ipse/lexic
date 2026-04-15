"""Auto-generated Pydantic models from /home/mika/projects/vyx_2/resources/ground_truth/chess.gbnf."""
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
    def to_text(self) -> str:
        return self.field1 + (self.field2 or "") + self.field3 + self.field4.to_text() + self.field5 + self.field6.to_text() + self.field7


class Root(BaseModel):
    """root ::= \"1. \" move \" \" move \"\\n\" ([1-9] [0-9]? \". \" move \" \" move \"\\n\")+"""
    field1: str
    field2: Move
    field3: str
    field4: Move
    field5: str
    field6: List[RootItem]
    def to_text(self) -> str:
        return self.field1 + self.field2.to_text() + self.field3 + self.field4.to_text() + self.field5 + "".join(i.to_text() for i in self.field6)


class Move(BaseModel):
    """move ::= (pawn | nonpawn | castle) [+#]?"""
    field1: Union[Pawn, Nonpawn, Castle]
    field2: Optional[str]
    def to_text(self) -> str:
        return self.field1.to_text() + (self.field2 or "")


class Nonpawn(BaseModel):
    """nonpawn ::= [NBKQR] [a-h]? [1-8]? \"x\"? [a-h] [1-8]"""
    field1: str
    field2: Optional[str]
    field3: Optional[str]
    field4: Optional[str]
    field5: str
    field6: str
    def to_text(self) -> str:
        return self.field1 + (self.field2 or "") + (self.field3 or "") + (self.field4 or "") + self.field5 + self.field6


class PawnOpt1(BaseModel):
    field1: str
    field2: str
    def to_text(self) -> str:
        return self.field1 + self.field2


class PawnOpt2(BaseModel):
    field1: str
    field2: str
    def to_text(self) -> str:
        return self.field1 + self.field2


class Pawn(BaseModel):
    """pawn ::= ([a-h] \"x\")? [a-h] [1-8] (\"=\" [NBKQR])?"""
    field1: Optional[PawnOpt1]
    field2: str
    field3: str
    field4: Optional[PawnOpt2]
    def to_text(self) -> str:
        return (self.field1.to_text() if self.field1 else "") + self.field2 + self.field3 + (self.field4.to_text() if self.field4 else "")


class Castle(BaseModel):
    """castle ::= \"O-O\" \"-O\"?"""
    field1: str
    field2: Optional[str]
    def to_text(self) -> str:
        return self.field1 + (self.field2 or "")


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
