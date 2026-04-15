"""Auto-generated Pydantic models from arithmetic.gbnf."""

from __future__ import annotations

from abc import ABC
from typing import List

from pydantic import BaseModel


class RootItem(BaseModel):
    field1: Expr
    field2: str
    field3: Term
    field4: str


class Root(BaseModel):
    field1: List[RootItem]


class ExprItem(BaseModel):
    field1: str
    field2: Term


class Expr(BaseModel):
    field1: Term
    field2: List[ExprItem]


class Term(BaseModel, ABC):
    pass


class TermArm3(Term):
    field1: str
    field2: Expr
    field3: str


class Ident(Term):
    field1: str
    field2: str


class Num(Term):
    field1: str


class Ws(BaseModel):
    value: str


# Resolve forward references
_ns = {k: v for k, v in globals().items() if isinstance(v, type)}
RootItem.model_rebuild(_types_namespace=_ns)
Root.model_rebuild(_types_namespace=_ns)
ExprItem.model_rebuild(_types_namespace=_ns)
Expr.model_rebuild(_types_namespace=_ns)
Term.model_rebuild(_types_namespace=_ns)
TermArm3.model_rebuild(_types_namespace=_ns)
Ident.model_rebuild(_types_namespace=_ns)
Num.model_rebuild(_types_namespace=_ns)
Ws.model_rebuild(_types_namespace=_ns)
