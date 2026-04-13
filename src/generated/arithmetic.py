# Generated from arithmetic.gbnf — DO NOT EDIT

from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Any, Optional, Union
from src.base import GrammarNode

class Root(GrammarNode):
    items: list[tuple[Expr, Term]] = Field(default_factory=list)

class Expr(GrammarNode):
    term: Term
    terms: list[tuple[str, Term]] = Field(default_factory=list)

class Term(GrammarNode):
    pass

class IdentTerm(Term):
    value: str

class NumTerm(Term):
    value: str

class TermAlt2(Term):
    expr: Expr


Root.model_rebuild()
Expr.model_rebuild()
Term.model_rebuild()
IdentTerm.model_rebuild()
NumTerm.model_rebuild()
TermAlt2.model_rebuild()
