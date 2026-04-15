# Generated from c.gbnf — DO NOT EDIT

from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Any, Optional, Union

class Root(BaseModel):
    items: list[Declaration] = Field(default_factory=list)

class Declaration(BaseModel):
    datatype: str
    identifier: str
    parameter: Optional[str] = None
    statements: list[Statement] = Field(default_factory=list)

class Statement(BaseModel):
    pass

class StatementDataType(Statement):
    datatype: str
    identifier: str
    expression: Expression

class StatementIdentifier(Statement):
    identifier: str
    expression: Expression

class StatementIdentifier2(Statement):
    identifier: str
    arglist: Optional[ArgList] = None

class StatementReturn(Statement):
    expression: Expression

class StatementWhile(Statement):
    condition: Condition
    statements: list[Statement] = Field(default_factory=list)

class StatementFor(Statement):
    forinit: ForInit
    condition: Condition
    forupdate: ForUpdate
    statements: list[Statement] = Field(default_factory=list)

class StatementIf(Statement):
    condition: Condition
    statements: list[Statement] = Field(default_factory=list)
    items: Optional[list[Statement]] = None

class SingleLineCommentStatement(Statement):
    value: str

class MultiLineCommentStatement(Statement):
    value: str

class ForInit(BaseModel):
    pass

class ForInitDataType(ForInit):
    datatype: str
    identifier: str
    expression: Expression

class ForInitIdentifier(ForInit):
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

class UnaryTermFactor(Factor):
    unaryterm: UnaryTerm

class FuncCallFactor(Factor):
    funccall: FuncCall

class ParenExpressionFactor(Factor):
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
StatementDataType.model_rebuild()
StatementIdentifier.model_rebuild()
StatementIdentifier2.model_rebuild()
StatementReturn.model_rebuild()
StatementWhile.model_rebuild()
StatementFor.model_rebuild()
StatementIf.model_rebuild()
SingleLineCommentStatement.model_rebuild()
MultiLineCommentStatement.model_rebuild()
ForInit.model_rebuild()
ForInitDataType.model_rebuild()
ForInitIdentifier.model_rebuild()
ForUpdate.model_rebuild()
Condition.model_rebuild()
Expression.model_rebuild()
Term.model_rebuild()
Factor.model_rebuild()
IdentifierFactor.model_rebuild()
NumberFactor.model_rebuild()
UnaryTermFactor.model_rebuild()
FuncCallFactor.model_rebuild()
ParenExpressionFactor.model_rebuild()
UnaryTerm.model_rebuild()
FuncCall.model_rebuild()
ParenExpression.model_rebuild()
ArgList.model_rebuild()
