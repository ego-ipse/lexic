"""Auto-generated Pydantic models from resources/ground_truth/arithmetic.gbnf."""
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
    """root ::= (expr \"=\" ws term \"\\n\")+"""
    field1: List[RootItem]


class ExprItem(BaseModel):
    field1: str
    field2: Term


class Expr(BaseModel):
    """expr ::= term ([-+*/] term)*"""
    field1: Term
    field2: List[ExprItem]


class Term(BaseModel, ABC):
    """term ::= ident | num | \"(\" ws expr \")\" ws"""
    pass


class TermArm3(Term):
    """Anonymous arm 3 of term"""
    field1: str
    field2: Expr
    field3: str


class Ident(Term):
    """ident ::= [a-z] [a-z0-9_]* ws"""
    field1: str
    field2: str


class Num(Term):
    """num ::= [0-9]+ ws"""
    field1: str


class Ws(BaseModel):
    """ws ::= [ \\t\\n]*"""
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
