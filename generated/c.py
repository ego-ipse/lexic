"""Auto-generated Pydantic models from /home/mika/projects/vyx_2/resources/ground_truth/c.gbnf."""
from __future__ import annotations

from abc import ABC
from typing import List, Optional

from pydantic import BaseModel


class Root(BaseModel):
    """root ::= (declaration)*"""
    field1: List[Declaration]
    def to_text(self) -> str:
        return "".join(i.to_text() for i in self.field1)


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
    def to_text(self) -> str:
        return self.field1.to_text() + self.field2.to_text() + self.field3 + (self.field4.to_text() if self.field4 else "") + self.field5 + self.field6 + "".join(i.to_text() for i in self.field7) + self.field8


class DataType(BaseModel):
    """dataType ::= \"int\" ws | \"float\" ws | \"char\" ws"""
    value: str
    def to_text(self) -> str:
        return self.value


class Factor(BaseModel, ABC):
    """factor ::= identifier | number | unaryTerm | funcCall | parenExpression"""
    pass
    def to_text(self) -> str:
        raise NotImplementedError


class Identifier(Factor):
    """identifier ::= [a-zA-Z_] [a-zA-Z_0-9]*"""
    field1: str
    field2: str
    def to_text(self) -> str:
        return self.field1 + self.field2


class Parameter(BaseModel):
    """parameter ::= dataType identifier"""
    field1: DataType
    field2: Identifier
    def to_text(self) -> str:
        return self.field1.to_text() + self.field2.to_text()


class Statement(BaseModel, ABC):
    """statement ::= (dataType identifier ws \"=\" ws expression \";\") | (identifier ws \"=\" ws expression \";\") | (identifier ws \"(\" argList? \")\" \";\") | (\"return\" ws expression \";\") | (\"while\" \"(\" condition \")\" \"{\" statement* \"}\") | (\"for\" \"(\" forInit \";\" ws condition \";\" ws forUpdate \")\" \"{\" statement* \"}\") | (\"if\" \"(\" condition \")\" \"{\" statement* \"}\" (\"else\" \"{\" statement* \"}\")?) | (singleLineComment) | (multiLineComment)"""
    pass
    def to_text(self) -> str:
        raise NotImplementedError


class StatementArm1(Statement):
    """Anonymous arm 1 of statement"""
    field1: DataType
    field2: Identifier
    field3: str
    field4: Expression
    field5: str
    def to_text(self) -> str:
        return self.field1.to_text() + self.field2.to_text() + self.field3 + self.field4.to_text() + self.field5


class StatementArm2(Statement):
    """Anonymous arm 2 of statement"""
    field1: Identifier
    field2: str
    field3: Expression
    field4: str
    def to_text(self) -> str:
        return self.field1.to_text() + self.field2 + self.field3.to_text() + self.field4


class StatementArm3(Statement):
    """Anonymous arm 3 of statement"""
    field1: Identifier
    field2: str
    field3: Optional[ArgList]
    field4: str
    field5: str
    def to_text(self) -> str:
        return self.field1.to_text() + self.field2 + (self.field3.to_text() if self.field3 else "") + self.field4 + self.field5


class StatementArm4(Statement):
    """Anonymous arm 4 of statement"""
    field1: str
    field2: Expression
    field3: str
    def to_text(self) -> str:
        return self.field1 + self.field2.to_text() + self.field3


class StatementArm5(Statement):
    """Anonymous arm 5 of statement"""
    field1: str
    field2: str
    field3: Condition
    field4: str
    field5: str
    field6: List[Statement]
    field7: str
    def to_text(self) -> str:
        return self.field1 + self.field2 + self.field3.to_text() + self.field4 + self.field5 + "".join(i.to_text() for i in self.field6) + self.field7


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
    def to_text(self) -> str:
        return self.field1 + self.field2 + self.field3.to_text() + self.field4 + self.field5.to_text() + self.field6 + self.field7.to_text() + self.field8 + self.field9 + "".join(i.to_text() for i in self.field10) + self.field11


class StatementArm7Opt(BaseModel):
    field1: str
    field2: str
    field3: List[Statement]
    field4: str
    def to_text(self) -> str:
        return self.field1 + self.field2 + "".join(i.to_text() for i in self.field3) + self.field4


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
    def to_text(self) -> str:
        return self.field1 + self.field2 + self.field3.to_text() + self.field4 + self.field5 + "".join(i.to_text() for i in self.field6) + self.field7 + (self.field8.to_text() if self.field8 else "")


class ForInit(BaseModel, ABC):
    """forInit ::= dataType identifier ws \"=\" ws expression | identifier ws \"=\" ws expression"""
    pass
    def to_text(self) -> str:
        raise NotImplementedError


class ForInitArm1(ForInit):
    """Anonymous arm 1 of forInit"""
    field1: DataType
    field2: Identifier
    field3: str
    field4: Expression
    def to_text(self) -> str:
        return self.field1.to_text() + self.field2.to_text() + self.field3 + self.field4.to_text()


class ForInitArm2(ForInit):
    """Anonymous arm 2 of forInit"""
    field1: Identifier
    field2: str
    field3: Expression
    def to_text(self) -> str:
        return self.field1.to_text() + self.field2 + self.field3.to_text()


class ForUpdate(BaseModel):
    """forUpdate ::= identifier ws \"=\" ws expression"""
    field1: Identifier
    field2: str
    field3: Expression
    def to_text(self) -> str:
        return self.field1.to_text() + self.field2 + self.field3.to_text()


class Condition(BaseModel):
    """condition ::= expression relationOperator expression"""
    field1: Expression
    field2: RelationOperator
    field3: Expression
    def to_text(self) -> str:
        return self.field1.to_text() + self.field2.to_text() + self.field3.to_text()


class RelationOperator(BaseModel):
    """relationOperator ::= (\"<=\" | \"<\" | \"==\" | \"!=\" | \">=\" | \">\")"""
    value: str
    def to_text(self) -> str:
        return self.value


class ExpressionItem(BaseModel):
    field1: str
    field2: Term
    def to_text(self) -> str:
        return self.field1 + self.field2.to_text()


class Expression(BaseModel):
    """expression ::= term ((\"+\" | \"-\") term)*"""
    field1: Term
    field2: List[ExpressionItem]
    def to_text(self) -> str:
        return self.field1.to_text() + "".join(i.to_text() for i in self.field2)


class TermItem(BaseModel):
    field1: str
    field2: Factor
    def to_text(self) -> str:
        return self.field1 + self.field2.to_text()


class Term(BaseModel):
    """term ::= factor ((\"*\" | \"/\") factor)*"""
    field1: Factor
    field2: List[TermItem]
    def to_text(self) -> str:
        return self.field1.to_text() + "".join(i.to_text() for i in self.field2)


class UnaryTerm(Factor):
    """unaryTerm ::= \"-\" factor"""
    field1: str
    field2: Factor
    def to_text(self) -> str:
        return self.field1 + self.field2.to_text()


class FuncCall(Factor):
    """funcCall ::= identifier \"(\" argList? \")\""""
    field1: Identifier
    field2: str
    field3: Optional[ArgList]
    field4: str
    def to_text(self) -> str:
        return self.field1.to_text() + self.field2 + (self.field3.to_text() if self.field3 else "") + self.field4


class ParenExpression(Factor):
    """parenExpression ::= \"(\" ws expression ws \")\""""
    field1: str
    field2: Expression
    field3: str
    def to_text(self) -> str:
        return self.field1 + self.field2.to_text() + self.field3


class ArgListItem(BaseModel):
    field1: str
    field2: Expression
    def to_text(self) -> str:
        return self.field1 + self.field2.to_text()


class ArgList(BaseModel):
    """argList ::= expression (\",\" ws expression)*"""
    field1: Expression
    field2: List[ArgListItem]
    def to_text(self) -> str:
        return self.field1.to_text() + "".join(i.to_text() for i in self.field2)


class Number(Factor):
    """number ::= [0-9]+"""
    field1: str
    def to_text(self) -> str:
        return self.field1


class SingleLineComment(Statement):
    """singleLineComment ::= \"//\" [^\\n]* \"\\n\""""
    field1: str
    field2: str
    field3: str
    def to_text(self) -> str:
        return self.field1 + self.field2 + self.field3


class MultiLineComment(Statement):
    """multiLineComment ::= \"/*\" ([^*] | (\"*\" [^/]))* \"*/\""""
    value: str
    def to_text(self) -> str:
        return self.value


class Ws(BaseModel):
    """ws ::= ([ \\t\\n]+)"""
    field1: str
    def to_text(self) -> str:
        return self.field1


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
