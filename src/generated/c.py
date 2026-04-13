# Generated from c.gbnf — DO NOT EDIT

from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Any, Optional, Union
from src.base import GrammarNode

class Root(GrammarNode):
    items: list[Declaration] = Field(default_factory=list)

class Declaration(GrammarNode):
    datatype: str
    identifier: str
    parameter: Optional[str] = None
    statements: list[Statement] = Field(default_factory=list)

class Statement(GrammarNode):
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

class ForInit(GrammarNode):
    pass

class ForInitAlt0(ForInit):
    datatype: str
    identifier: str
    expression: Expression

class ForInitAlt1(ForInit):
    identifier: str
    expression: Expression

class ForUpdate(GrammarNode):
    identifier: str
    expression: Expression

class Condition(GrammarNode):
    expression: Expression
    relationoperator: str
    expression_1: Expression

class Expression(GrammarNode):
    term: Term
    terms: list[tuple[str, Term]] = Field(default_factory=list)

class Term(GrammarNode):
    factor: Factor
    factors: list[tuple[str, Factor]] = Field(default_factory=list)

class Factor(GrammarNode):
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

class UnaryTerm(GrammarNode):
    factor: Factor

class FuncCall(GrammarNode):
    identifier: str
    arglist: Optional[ArgList] = None

class ParenExpression(GrammarNode):
    expression: Expression

class ArgList(GrammarNode):
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
