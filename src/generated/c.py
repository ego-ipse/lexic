"""Auto-generated Pydantic models from c.gbnf."""

from __future__ import annotations

from abc import ABC
from typing import List, Optional

from pydantic import BaseModel


class Root(BaseModel):
    field1: List[Declaration]


class Declaration(BaseModel):
    field1: DataType
    field2: Identifier
    field3: str
    field4: Optional[Parameter]
    field5: str
    field6: str
    field7: List[Statement]
    field8: str


class DataType(BaseModel):
    value: str


class Factor(BaseModel, ABC):
    pass


class Identifier(Factor):
    field1: str
    field2: str


class Parameter(BaseModel):
    field1: DataType
    field2: Identifier


class Statement(BaseModel, ABC):
    pass


class StatementArm1(Statement):
    field1: DataType
    field2: Identifier
    field3: str
    field4: Expression
    field5: str


class StatementArm2(Statement):
    field1: Identifier
    field2: str
    field3: Expression
    field4: str


class StatementArm3(Statement):
    field1: Identifier
    field2: str
    field3: Optional[ArgList]
    field4: str
    field5: str


class StatementArm4(Statement):
    field1: str
    field2: Expression
    field3: str


class StatementArm5(Statement):
    field1: str
    field2: str
    field3: Condition
    field4: str
    field5: str
    field6: List[Statement]
    field7: str


class StatementArm6(Statement):
    field1: str
    field2: str
    field3: ForInit
    field4: str
    field5: Condition
    field6: str
    field7: ForUpdate
    field8: str
    field9: str
    field10: List[Statement]
    field11: str


class StatementArm7Opt(BaseModel):
    field1: str
    field2: str
    field3: List[Statement]
    field4: str


class StatementArm7(Statement):
    field1: str
    field2: str
    field3: Condition
    field4: str
    field5: str
    field6: List[Statement]
    field7: str
    field8: Optional[StatementArm7Opt]


class ForInit(BaseModel, ABC):
    pass


class ForInitArm1(ForInit):
    field1: DataType
    field2: Identifier
    field3: str
    field4: Expression


class ForInitArm2(ForInit):
    field1: Identifier
    field2: str
    field3: Expression


class ForUpdate(BaseModel):
    field1: Identifier
    field2: str
    field3: Expression


class Condition(BaseModel):
    field1: Expression
    field2: RelationOperator
    field3: Expression


class RelationOperator(BaseModel):
    value: str


class ExpressionItem(BaseModel):
    field1: str
    field2: Term


class Expression(BaseModel):
    field1: Term
    field2: List[ExpressionItem]


class TermItem(BaseModel):
    field1: str
    field2: Factor


class Term(BaseModel):
    field1: Factor
    field2: List[TermItem]


class UnaryTerm(Factor):
    field1: str
    field2: Factor


class FuncCall(Factor):
    field1: Identifier
    field2: str
    field3: Optional[ArgList]
    field4: str


class ParenExpression(Factor):
    field1: str
    field2: Expression
    field3: str


class ArgListItem(BaseModel):
    field1: str
    field2: Expression


class ArgList(BaseModel):
    field1: Expression
    field2: List[ArgListItem]


class Number(Factor):
    field1: str


class SingleLineComment(Statement):
    value: str


class MultiLineComment(Statement):
    value: str


class Ws(BaseModel):
    value: str


# Resolve forward references
_ns = {k: v for k, v in globals().items() if isinstance(v, type)}
Root.model_rebuild(_types_namespace=_ns)
Declaration.model_rebuild(_types_namespace=_ns)
DataType.model_rebuild(_types_namespace=_ns)
Factor.model_rebuild(_types_namespace=_ns)
Identifier.model_rebuild(_types_namespace=_ns)
Parameter.model_rebuild(_types_namespace=_ns)
Statement.model_rebuild(_types_namespace=_ns)
StatementArm1.model_rebuild(_types_namespace=_ns)
StatementArm2.model_rebuild(_types_namespace=_ns)
StatementArm3.model_rebuild(_types_namespace=_ns)
StatementArm4.model_rebuild(_types_namespace=_ns)
StatementArm5.model_rebuild(_types_namespace=_ns)
StatementArm6.model_rebuild(_types_namespace=_ns)
StatementArm7Opt.model_rebuild(_types_namespace=_ns)
StatementArm7.model_rebuild(_types_namespace=_ns)
ForInit.model_rebuild(_types_namespace=_ns)
ForInitArm1.model_rebuild(_types_namespace=_ns)
ForInitArm2.model_rebuild(_types_namespace=_ns)
ForUpdate.model_rebuild(_types_namespace=_ns)
Condition.model_rebuild(_types_namespace=_ns)
RelationOperator.model_rebuild(_types_namespace=_ns)
ExpressionItem.model_rebuild(_types_namespace=_ns)
Expression.model_rebuild(_types_namespace=_ns)
TermItem.model_rebuild(_types_namespace=_ns)
Term.model_rebuild(_types_namespace=_ns)
UnaryTerm.model_rebuild(_types_namespace=_ns)
FuncCall.model_rebuild(_types_namespace=_ns)
ParenExpression.model_rebuild(_types_namespace=_ns)
ArgListItem.model_rebuild(_types_namespace=_ns)
ArgList.model_rebuild(_types_namespace=_ns)
Number.model_rebuild(_types_namespace=_ns)
SingleLineComment.model_rebuild(_types_namespace=_ns)
MultiLineComment.model_rebuild(_types_namespace=_ns)
Ws.model_rebuild(_types_namespace=_ns)
