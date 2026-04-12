# Generated from c.gbnf by src/codegen.py — DO NOT EDIT

from __future__ import annotations
from typing import Any, Optional, Union
from pydantic import BaseModel, Field

class Root(BaseModel):
    items: list[Declaration] = Field(default_factory=list)

class Declaration(BaseModel):
    datatype: str
    identifier: str
    parameter: Optional[str] = None
    statements: list[Statement] = Field(default_factory=list)

class Statement(BaseModel):
    pass

class StatementAlt0(Statement):
    datatype: str
    identifier: str
    expression: Expression

class StatementAlt1(Statement):
    identifier: str
    expression: Expression

class StatementAlt2(Statement):
    identifier: str
    arglist: Optional[ArgList] = None

class StatementAlt3(Statement):
    expression: Expression

class StatementAlt4(Statement):
    condition: Condition
    statements: list[Statement] = Field(default_factory=list)

class StatementAlt5(Statement):
    forinit: ForInit
    condition: Condition
    forupdate: ForUpdate
    statements: list[Statement] = Field(default_factory=list)

class StatementAlt6(Statement):
    condition: Condition
    statements: list[Statement] = Field(default_factory=list)
    items: Optional[list[Statement]] = None

class SinglelinecommentStatement(Statement):
    value: str

class MultilinecommentStatement(Statement):
    value: str

class ForInit(BaseModel):
    pass

class ForInitAlt0(ForInit):
    datatype: str
    identifier: str
    expression: Expression

class ForInitAlt1(ForInit):
    identifier: str
    expression: Expression

class ForUpdate(BaseModel):
    identifier: str
    expression: Expression

class Condition(BaseModel):
    expression: Expression
    relationoperator: str
    expression_1: Expression

class Expression(BaseModel):
    term: Term
    terms: list[tuple[str, Term]] = Field(default_factory=list)

class Term(BaseModel):
    factor: Factor
    factors: list[tuple[str, Factor]] = Field(default_factory=list)

class Factor(BaseModel):
    pass

class IdentifierFactor(Factor):
    value: str

class NumberFactor(Factor):
    value: str

class UnarytermFactor(Factor):
    unaryterm: UnaryTerm

class FunccallFactor(Factor):
    funccall: FuncCall

class ParenexpressionFactor(Factor):
    parenexpression: ParenExpression

class UnaryTerm(BaseModel):
    factor: Factor

class FuncCall(BaseModel):
    identifier: str
    arglist: Optional[ArgList] = None

class ParenExpression(BaseModel):
    expression: Expression

class ArgList(BaseModel):
    expression: Expression
    expressions: list[Expression] = Field(default_factory=list)


Root.model_rebuild()
Declaration.model_rebuild()
Statement.model_rebuild()
StatementAlt0.model_rebuild()
StatementAlt1.model_rebuild()
StatementAlt2.model_rebuild()
StatementAlt3.model_rebuild()
StatementAlt4.model_rebuild()
StatementAlt5.model_rebuild()
StatementAlt6.model_rebuild()
SinglelinecommentStatement.model_rebuild()
MultilinecommentStatement.model_rebuild()
ForInit.model_rebuild()
ForInitAlt0.model_rebuild()
ForInitAlt1.model_rebuild()
ForUpdate.model_rebuild()
Condition.model_rebuild()
Expression.model_rebuild()
Term.model_rebuild()
Factor.model_rebuild()
IdentifierFactor.model_rebuild()
NumberFactor.model_rebuild()
UnarytermFactor.model_rebuild()
FunccallFactor.model_rebuild()
ParenexpressionFactor.model_rebuild()
UnaryTerm.model_rebuild()
FuncCall.model_rebuild()
ParenExpression.model_rebuild()
ArgList.model_rebuild()
