"""Auto-generated Pydantic models from /home/mika/projects/vyx_2/resources/ground_truth/c.gbnf."""
from __future__ import annotations

from abc import ABC
from typing import ClassVar, List, Optional

from base import GrammarModel
from codegen.ir import RuleSpec, AlternationAtom, CharClassAtom, LiteralAtom, RuleRefAtom


class Root(GrammarModel):
    """root ::= (see __grammar__)"""
    __grammar__: ClassVar[RuleSpec] = RuleSpec(
        rule_name="root",
        class_name="Root",
        parent_class_name="GrammarModel",
        kind="sequence",
        items=[RuleRefAtom("root-item", min=0, max=None)],
        field_map={"root_item": 0},
    )
    root_item: List[RootItem]


class RootItem(GrammarModel):
    """root-item ::= (see __grammar__)"""
    __grammar__: ClassVar[RuleSpec] = RuleSpec(
        rule_name="root-item",
        class_name="RootItem",
        parent_class_name="GrammarModel",
        kind="sequence",
        items=[RuleRefAtom("declaration", min=1, max=1)],
        field_map={"declaration": 0},
    )
    declaration: Declaration


class Declaration(GrammarModel):
    """declaration ::= (see __grammar__)"""
    __grammar__: ClassVar[RuleSpec] = RuleSpec(
        rule_name="declaration",
        class_name="Declaration",
        parent_class_name="GrammarModel",
        kind="sequence",
        items=[RuleRefAtom("dataType", min=1, max=1), RuleRefAtom("identifier", min=1, max=1), LiteralAtom("("), RuleRefAtom("parameter", min=0, max=1), LiteralAtom(")"), LiteralAtom("{"), RuleRefAtom("statement", min=0, max=None), LiteralAtom("}")],
        field_map={"dataType": 0, "identifier": 1, "parameter": 3, "statement": 6},
    )
    dataType: DataType
    identifier: Identifier
    parameter: Optional[Parameter] = None
    statement: List[Statement]


class DataType(GrammarModel):
    """dataType ::= (see __grammar__)"""
    __grammar__: ClassVar[RuleSpec] = RuleSpec(
        rule_name="dataType",
        class_name="DataType",
        parent_class_name="GrammarModel",
        kind="value_str",
        items=[LiteralAtom("int"), LiteralAtom("float"), LiteralAtom("char")],
        field_map={},
    )
    value: str


class Factor(GrammarModel, ABC):
    """factor ::= (see __grammar__)"""
    __grammar__: ClassVar[RuleSpec] = RuleSpec(
        rule_name="factor",
        class_name="Factor",
        parent_class_name="GrammarModel",
        kind="alternation",
        items=[AlternationAtom(["identifier", "number", "unaryTerm", "funcCall", "parenExpression"])],
        field_map={},
    )
    pass


class Identifier(Factor):
    """identifier ::= (see __grammar__)"""
    __grammar__: ClassVar[RuleSpec] = RuleSpec(
        rule_name="identifier",
        class_name="Identifier",
        parent_class_name="Factor",
        kind="value_str",
        items=[CharClassAtom("[a-zA-Z_]", min=1, max=1), CharClassAtom("[a-zA-Z_0-9]", min=0, max=None)],
        field_map={},
    )
    value: str


class Parameter(GrammarModel):
    """parameter ::= (see __grammar__)"""
    __grammar__: ClassVar[RuleSpec] = RuleSpec(
        rule_name="parameter",
        class_name="Parameter",
        parent_class_name="GrammarModel",
        kind="sequence",
        items=[RuleRefAtom("dataType", min=1, max=1), RuleRefAtom("identifier", min=1, max=1)],
        field_map={"dataType": 0, "identifier": 1},
    )
    dataType: DataType
    identifier: Identifier


class Statement(GrammarModel, ABC):
    """statement ::= (see __grammar__)"""
    __grammar__: ClassVar[RuleSpec] = RuleSpec(
        rule_name="statement",
        class_name="Statement",
        parent_class_name="GrammarModel",
        kind="alternation",
        items=[AlternationAtom(["statement-arm1", "statement-arm2", "statement-arm3", "statement-arm4", "statement-arm5", "statement-arm6", "statement-arm7", "singleLineComment", "multiLineComment"])],
        field_map={},
    )
    pass


class StatementArm1(Statement):
    """statement-arm1 ::= (see __grammar__)"""
    __grammar__: ClassVar[RuleSpec] = RuleSpec(
        rule_name="statement-arm1",
        class_name="StatementArm1",
        parent_class_name="Statement",
        kind="sequence",
        items=[RuleRefAtom("dataType", min=1, max=1), RuleRefAtom("identifier", min=1, max=1), LiteralAtom("="), RuleRefAtom("expression", min=1, max=1), LiteralAtom(";")],
        field_map={"dataType": 0, "identifier": 1, "expression": 3},
    )
    dataType: DataType
    identifier: Identifier
    expression: Expression


class StatementArm2(Statement):
    """statement-arm2 ::= (see __grammar__)"""
    __grammar__: ClassVar[RuleSpec] = RuleSpec(
        rule_name="statement-arm2",
        class_name="StatementArm2",
        parent_class_name="Statement",
        kind="sequence",
        items=[RuleRefAtom("identifier", min=1, max=1), LiteralAtom("="), RuleRefAtom("expression", min=1, max=1), LiteralAtom(";")],
        field_map={"identifier": 0, "expression": 2},
    )
    identifier: Identifier
    expression: Expression


class StatementArm3(Statement):
    """statement-arm3 ::= (see __grammar__)"""
    __grammar__: ClassVar[RuleSpec] = RuleSpec(
        rule_name="statement-arm3",
        class_name="StatementArm3",
        parent_class_name="Statement",
        kind="sequence",
        items=[RuleRefAtom("identifier", min=1, max=1), LiteralAtom("("), RuleRefAtom("argList", min=0, max=1), LiteralAtom(")"), LiteralAtom(";")],
        field_map={"identifier": 0, "argList": 2},
    )
    identifier: Identifier
    argList: Optional[ArgList] = None


class StatementArm4(Statement):
    """statement-arm4 ::= (see __grammar__)"""
    __grammar__: ClassVar[RuleSpec] = RuleSpec(
        rule_name="statement-arm4",
        class_name="StatementArm4",
        parent_class_name="Statement",
        kind="sequence",
        items=[LiteralAtom("return"), RuleRefAtom("expression", min=1, max=1), LiteralAtom(";")],
        field_map={"expression": 1},
    )
    expression: Expression


class StatementArm5(Statement):
    """statement-arm5 ::= (see __grammar__)"""
    __grammar__: ClassVar[RuleSpec] = RuleSpec(
        rule_name="statement-arm5",
        class_name="StatementArm5",
        parent_class_name="Statement",
        kind="sequence",
        items=[LiteralAtom("while"), LiteralAtom("("), RuleRefAtom("condition", min=1, max=1), LiteralAtom(")"), LiteralAtom("{"), RuleRefAtom("statement", min=0, max=None), LiteralAtom("}")],
        field_map={"condition": 2, "statement": 5},
    )
    condition: Condition
    statement: List[Statement]


class StatementArm6(Statement):
    """statement-arm6 ::= (see __grammar__)"""
    __grammar__: ClassVar[RuleSpec] = RuleSpec(
        rule_name="statement-arm6",
        class_name="StatementArm6",
        parent_class_name="Statement",
        kind="sequence",
        items=[LiteralAtom("for"), LiteralAtom("("), RuleRefAtom("forInit", min=1, max=1), LiteralAtom(";"), RuleRefAtom("condition", min=1, max=1), LiteralAtom(";"), RuleRefAtom("forUpdate", min=1, max=1), LiteralAtom(")"), LiteralAtom("{"), RuleRefAtom("statement", min=0, max=None), LiteralAtom("}")],
        field_map={"forInit": 2, "condition": 4, "forUpdate": 6, "statement": 9},
    )
    forInit: ForInit
    condition: Condition
    forUpdate: ForUpdate
    statement: List[Statement]


class Statementarm7Item(GrammarModel):
    """statementarm7-item ::= (see __grammar__)"""
    __grammar__: ClassVar[RuleSpec] = RuleSpec(
        rule_name="statementarm7-item",
        class_name="Statementarm7Item",
        parent_class_name="GrammarModel",
        kind="sequence",
        items=[LiteralAtom("else"), LiteralAtom("{"), RuleRefAtom("statement", min=0, max=None), LiteralAtom("}")],
        field_map={"statement": 2},
    )
    statement: List[Statement]


class StatementArm7(Statement):
    """statement-arm7 ::= (see __grammar__)"""
    __grammar__: ClassVar[RuleSpec] = RuleSpec(
        rule_name="statement-arm7",
        class_name="StatementArm7",
        parent_class_name="Statement",
        kind="sequence",
        items=[LiteralAtom("if"), LiteralAtom("("), RuleRefAtom("condition", min=1, max=1), LiteralAtom(")"), LiteralAtom("{"), RuleRefAtom("statement", min=0, max=None), LiteralAtom("}"), RuleRefAtom("statementarm7-item", min=0, max=1)],
        field_map={"condition": 2, "statement": 5, "statementarm7_item": 7},
    )
    condition: Condition
    statement: List[Statement]
    statementarm7_item: Optional[Statementarm7Item] = None


class ForInit(GrammarModel, ABC):
    """forInit ::= (see __grammar__)"""
    __grammar__: ClassVar[RuleSpec] = RuleSpec(
        rule_name="forInit",
        class_name="ForInit",
        parent_class_name="GrammarModel",
        kind="alternation",
        items=[AlternationAtom(["forInit-arm1", "forInit-arm2"])],
        field_map={},
    )
    pass


class ForInitArm1(ForInit):
    """forInit-arm1 ::= (see __grammar__)"""
    __grammar__: ClassVar[RuleSpec] = RuleSpec(
        rule_name="forInit-arm1",
        class_name="ForInitArm1",
        parent_class_name="ForInit",
        kind="sequence",
        items=[RuleRefAtom("dataType", min=1, max=1), RuleRefAtom("identifier", min=1, max=1), LiteralAtom("="), RuleRefAtom("expression", min=1, max=1)],
        field_map={"dataType": 0, "identifier": 1, "expression": 3},
    )
    dataType: DataType
    identifier: Identifier
    expression: Expression


class ForInitArm2(ForInit):
    """forInit-arm2 ::= (see __grammar__)"""
    __grammar__: ClassVar[RuleSpec] = RuleSpec(
        rule_name="forInit-arm2",
        class_name="ForInitArm2",
        parent_class_name="ForInit",
        kind="sequence",
        items=[RuleRefAtom("identifier", min=1, max=1), LiteralAtom("="), RuleRefAtom("expression", min=1, max=1)],
        field_map={"identifier": 0, "expression": 2},
    )
    identifier: Identifier
    expression: Expression


class ForUpdate(GrammarModel):
    """forUpdate ::= (see __grammar__)"""
    __grammar__: ClassVar[RuleSpec] = RuleSpec(
        rule_name="forUpdate",
        class_name="ForUpdate",
        parent_class_name="GrammarModel",
        kind="sequence",
        items=[RuleRefAtom("identifier", min=1, max=1), RuleRefAtom("ws", min=1, max=1), LiteralAtom("="), RuleRefAtom("ws", min=1, max=1), RuleRefAtom("expression", min=1, max=1)],
        field_map={"identifier": 0, "ws": 1, "ws2": 3, "expression": 4},
    )
    identifier: Identifier
    ws: Ws
    ws2: Ws
    expression: Expression


class Condition(GrammarModel):
    """condition ::= (see __grammar__)"""
    __grammar__: ClassVar[RuleSpec] = RuleSpec(
        rule_name="condition",
        class_name="Condition",
        parent_class_name="GrammarModel",
        kind="sequence",
        items=[RuleRefAtom("expression", min=1, max=1), RuleRefAtom("relationOperator", min=1, max=1), RuleRefAtom("expression", min=1, max=1)],
        field_map={"expression": 0, "relationOperator": 1, "expression2": 2},
    )
    expression: Expression
    relationOperator: RelationOperator
    expression2: Expression


class RelationOperator(GrammarModel):
    """relationOperator ::= (see __grammar__)"""
    __grammar__: ClassVar[RuleSpec] = RuleSpec(
        rule_name="relationOperator",
        class_name="RelationOperator",
        parent_class_name="GrammarModel",
        kind="value_str",
        items=[LiteralAtom("<="), LiteralAtom("<"), LiteralAtom("=="), LiteralAtom("!="), LiteralAtom(">="), LiteralAtom(">")],
        field_map={},
    )
    value: str


class ExpressionItem(GrammarModel):
    """expression-item ::= (see __grammar__)"""
    __grammar__: ClassVar[RuleSpec] = RuleSpec(
        rule_name="expression-item",
        class_name="ExpressionItem",
        parent_class_name="GrammarModel",
        kind="sequence",
        items=[CharClassAtom("(\"+\"|\"-\")", min=1, max=1), RuleRefAtom("term", min=1, max=1)],
        field_map={"first": 0, "term": 1},
    )
    first: str
    term: Term


class Expression(GrammarModel):
    """expression ::= (see __grammar__)"""
    __grammar__: ClassVar[RuleSpec] = RuleSpec(
        rule_name="expression",
        class_name="Expression",
        parent_class_name="GrammarModel",
        kind="sequence",
        items=[RuleRefAtom("term", min=1, max=1), RuleRefAtom("expression-item", min=0, max=None)],
        field_map={"term": 0, "expression_item": 1},
    )
    term: Term
    expression_item: List[ExpressionItem]


class TermItem(GrammarModel):
    """term-item ::= (see __grammar__)"""
    __grammar__: ClassVar[RuleSpec] = RuleSpec(
        rule_name="term-item",
        class_name="TermItem",
        parent_class_name="GrammarModel",
        kind="sequence",
        items=[CharClassAtom("(\"*\"|\"/\")", min=1, max=1), RuleRefAtom("factor", min=1, max=1)],
        field_map={"first": 0, "factor": 1},
    )
    first: str
    factor: Factor


class Term(GrammarModel):
    """term ::= (see __grammar__)"""
    __grammar__: ClassVar[RuleSpec] = RuleSpec(
        rule_name="term",
        class_name="Term",
        parent_class_name="GrammarModel",
        kind="sequence",
        items=[RuleRefAtom("factor", min=1, max=1), RuleRefAtom("term-item", min=0, max=None)],
        field_map={"factor": 0, "term_item": 1},
    )
    factor: Factor
    term_item: List[TermItem]


class UnaryTerm(Factor):
    """unaryTerm ::= (see __grammar__)"""
    __grammar__: ClassVar[RuleSpec] = RuleSpec(
        rule_name="unaryTerm",
        class_name="UnaryTerm",
        parent_class_name="Factor",
        kind="sequence",
        items=[LiteralAtom("-"), RuleRefAtom("factor", min=1, max=1)],
        field_map={"factor": 1},
    )
    factor: Factor


class FuncCall(Factor):
    """funcCall ::= (see __grammar__)"""
    __grammar__: ClassVar[RuleSpec] = RuleSpec(
        rule_name="funcCall",
        class_name="FuncCall",
        parent_class_name="Factor",
        kind="sequence",
        items=[RuleRefAtom("identifier", min=1, max=1), LiteralAtom("("), RuleRefAtom("argList", min=0, max=1), LiteralAtom(")")],
        field_map={"identifier": 0, "argList": 2},
    )
    identifier: Identifier
    argList: Optional[ArgList] = None


class ParenExpression(Factor):
    """parenExpression ::= (see __grammar__)"""
    __grammar__: ClassVar[RuleSpec] = RuleSpec(
        rule_name="parenExpression",
        class_name="ParenExpression",
        parent_class_name="Factor",
        kind="sequence",
        items=[LiteralAtom("("), RuleRefAtom("ws", min=1, max=1), RuleRefAtom("expression", min=1, max=1), RuleRefAtom("ws", min=1, max=1), LiteralAtom(")")],
        field_map={"ws": 1, "expression": 2, "ws2": 3},
    )
    ws: Ws
    expression: Expression
    ws2: Ws


class ArglistItem(GrammarModel):
    """arglist-item ::= (see __grammar__)"""
    __grammar__: ClassVar[RuleSpec] = RuleSpec(
        rule_name="arglist-item",
        class_name="ArglistItem",
        parent_class_name="GrammarModel",
        kind="sequence",
        items=[LiteralAtom(","), RuleRefAtom("expression", min=1, max=1)],
        field_map={"expression": 1},
    )
    expression: Expression


class ArgList(GrammarModel):
    """argList ::= (see __grammar__)"""
    __grammar__: ClassVar[RuleSpec] = RuleSpec(
        rule_name="argList",
        class_name="ArgList",
        parent_class_name="GrammarModel",
        kind="sequence",
        items=[RuleRefAtom("expression", min=1, max=1), RuleRefAtom("arglist-item", min=0, max=None)],
        field_map={"expression": 0, "arglist_item": 1},
    )
    expression: Expression
    arglist_item: List[ArglistItem]


class Number(Factor):
    """number ::= (see __grammar__)"""
    __grammar__: ClassVar[RuleSpec] = RuleSpec(
        rule_name="number",
        class_name="Number",
        parent_class_name="Factor",
        kind="value_str",
        items=[CharClassAtom("[0-9]", min=1, max=None)],
        field_map={},
    )
    value: str


class SingleLineComment(Statement):
    """singleLineComment ::= (see __grammar__)"""
    __grammar__: ClassVar[RuleSpec] = RuleSpec(
        rule_name="singleLineComment",
        class_name="SingleLineComment",
        parent_class_name="Statement",
        kind="value_str",
        items=[LiteralAtom("//"), CharClassAtom("[^\\n]", min=0, max=None), LiteralAtom("\\n")],
        field_map={},
    )
    value: str


class MultiLineComment(Statement):
    """multiLineComment ::= (see __grammar__)"""
    __grammar__: ClassVar[RuleSpec] = RuleSpec(
        rule_name="multiLineComment",
        class_name="MultiLineComment",
        parent_class_name="Statement",
        kind="value_str",
        items=[LiteralAtom("/*"), CharClassAtom("([^*]|*[^/])", min=0, max=None), LiteralAtom("*/")],
        field_map={},
    )
    value: str


class Ws(GrammarModel):
    """ws ::= (see __grammar__)"""
    __grammar__: ClassVar[RuleSpec] = RuleSpec(
        rule_name="ws",
        class_name="Ws",
        parent_class_name="GrammarModel",
        kind="value_str",
        items=[CharClassAtom("[ \\t\\n]", min=1, max=None)],
        field_map={},
    )
    value: str


# Resolve forward references
_ns = {k: v for k, v in globals().items() if isinstance(v, type)}
Root.model_rebuild(_types_namespace=_ns)
RootItem.model_rebuild(_types_namespace=_ns)
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
Statementarm7Item.model_rebuild(_types_namespace=_ns)
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
ArglistItem.model_rebuild(_types_namespace=_ns)
ArgList.model_rebuild(_types_namespace=_ns)
Number.model_rebuild(_types_namespace=_ns)
SingleLineComment.model_rebuild(_types_namespace=_ns)
MultiLineComment.model_rebuild(_types_namespace=_ns)
Ws.model_rebuild(_types_namespace=_ns)
