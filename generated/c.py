"""Auto-generated Pydantic models from /home/mika/projects/vyx_2/resources/ground_truth/c.gbnf."""
from __future__ import annotations

from abc import ABC
from typing import List, Optional

from pydantic import BaseModel


class Root(BaseModel):
    """root ::= (declaration)*"""
    field1: List[Declaration]


class Declaration(BaseModel):
    """declaration ::= dataType identifier \"(\" parameter? \")\" \"{\" statement* \"}\""""
    field1: DataType
    field2: Identifier
    field3: str
    field4: Optional[Parameter]
    field5: str
    field6: str
    field7: List[Statement]
    field8: str


class DataType(BaseModel):
    """dataType ::= \"int\" ws | \"float\" ws | \"char\" ws"""
    value: str


class Factor(BaseModel, ABC):
    """factor ::= identifier | number | unaryTerm | funcCall | parenExpression"""
    pass


class Identifier(Factor):
    """identifier ::= [a-zA-Z_] [a-zA-Z_0-9]*"""
    field1: str
    field2: str


class Parameter(BaseModel):
    """parameter ::= dataType identifier"""
    field1: DataType
    field2: Identifier


class Statement(BaseModel, ABC):
    """statement ::= (dataType identifier ws \"=\" ws expression \";\") | (identifier ws \"=\" ws expression \";\") | (identifier ws \"(\" argList? \")\" \";\") | (\"return\" ws expression \";\") | (\"while\" \"(\" condition \")\" \"{\" statement* \"}\") | (\"for\" \"(\" forInit \";\" ws condition \";\" ws forUpdate \")\" \"{\" statement* \"}\") | (\"if\" \"(\" condition \")\" \"{\" statement* \"}\" (\"else\" \"{\" statement* \"}\")?) | (singleLineComment) | (multiLineComment)"""
    pass


class StatementArm1(Statement):
    """Anonymous arm 1 of statement"""
    field1: DataType
    field2: Identifier
    field3: str
    field4: Expression
    field5: str


class StatementArm2(Statement):
    """Anonymous arm 2 of statement"""
    field1: Identifier
    field2: str
    field3: Expression
    field4: str


class StatementArm3(Statement):
    """Anonymous arm 3 of statement"""
    field1: Identifier
    field2: str
    field3: Optional[ArgList]
    field4: str
    field5: str


class StatementArm4(Statement):
    """Anonymous arm 4 of statement"""
    field1: str
    field2: Expression
    field3: str


class StatementArm5(Statement):
    """Anonymous arm 5 of statement"""
    field1: str
    field2: str
    field3: Condition
    field4: str
    field5: str
    field6: List[Statement]
    field7: str


class StatementArm6(Statement):
    """Anonymous arm 6 of statement"""
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
    """Anonymous arm 7 of statement"""
    field1: str
    field2: str
    field3: Condition
    field4: str
    field5: str
    field6: List[Statement]
    field7: str
    field8: Optional[StatementArm7Opt]


class ForInit(BaseModel, ABC):
    """forInit ::= dataType identifier ws \"=\" ws expression | identifier ws \"=\" ws expression"""
    pass


class ForInitArm1(ForInit):
    """Anonymous arm 1 of forInit"""
    field1: DataType
    field2: Identifier
    field3: str
    field4: Expression


class ForInitArm2(ForInit):
    """Anonymous arm 2 of forInit"""
    field1: Identifier
    field2: str
    field3: Expression


class ForUpdate(BaseModel):
    """forUpdate ::= identifier ws \"=\" ws expression"""
    field1: Identifier
    field2: str
    field3: Expression


class Condition(BaseModel):
    """condition ::= expression relationOperator expression"""
    field1: Expression
    field2: RelationOperator
    field3: Expression


class RelationOperator(BaseModel):
    """relationOperator ::= (\"<=\" | \"<\" | \"==\" | \"!=\" | \">=\" | \">\")"""
    value: str


class ExpressionItem(BaseModel):
    field1: str
    field2: Term


class Expression(BaseModel):
    """expression ::= term ((\"+\" | \"-\") term)*"""
    field1: Term
    field2: List[ExpressionItem]


class TermItem(BaseModel):
    field1: str
    field2: Factor


class Term(BaseModel):
    """term ::= factor ((\"*\" | \"/\") factor)*"""
    field1: Factor
    field2: List[TermItem]


class UnaryTerm(Factor):
    """unaryTerm ::= \"-\" factor"""
    field1: str
    field2: Factor


class FuncCall(Factor):
    """funcCall ::= identifier \"(\" argList? \")\""""
    field1: Identifier
    field2: str
    field3: Optional[ArgList]
    field4: str


class ParenExpression(Factor):
    """parenExpression ::= \"(\" ws expression ws \")\""""
    field1: str
    field2: Expression
    field3: str


class ArgListItem(BaseModel):
    field1: str
    field2: Expression


class ArgList(BaseModel):
    """argList ::= expression (\",\" ws expression)*"""
    field1: Expression
    field2: List[ArgListItem]


class Number(Factor):
    """number ::= [0-9]+"""
    field1: str


class SingleLineComment(Statement):
    """singleLineComment ::= \"//\" [^\\n]* \"\\n\""""
    value: str


class MultiLineComment(Statement):
    """multiLineComment ::= \"/*\" ([^*] | (\"*\" [^/]))* \"*/\""""
    value: str


class Ws(BaseModel):
    """ws ::= ([ \\t\\n]+)"""
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
