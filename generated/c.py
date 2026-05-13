"""Generated module: c. Do not edit; regenerated from grammar."""

from __future__ import annotations

from typing import Annotated, List, Optional

from pydantic import StringConstraints

from lexic.base import GrammarModel
from lexic.ir.nodes import (
    IrAlternation,
    IrCharClass,
    IrGroup,
    IrItem,
    IrLiteral,
    IrRuleRef,
    IrSequence,
    Quantifier,
)
from lexic.ir.spec import RuleSpec

Pattern = Annotated[str, StringConstraints(pattern=r"^[a-zA-Z_]$")]

Alnum = Annotated[str, StringConstraints(pattern=r"^[a-zA-Z_0-9]*$")]

Pattern2 = Annotated[str, StringConstraints(pattern=r"^(<=|<|==|!=|>=|>)$")]

Digit = Annotated[str, StringConstraints(pattern=r"^[0-9]+$")]

Pattern3 = Annotated[str, StringConstraints(pattern=r"^[^\n]*$")]

Pattern4 = Annotated[str, StringConstraints(pattern=r"^[^*]$")]

Pattern5 = Annotated[str, StringConstraints(pattern=r"^[^/]$")]

Pattern6 = Annotated[str, StringConstraints(pattern=r"^(\*[^/])$")]

Pattern7 = Annotated[str, StringConstraints(pattern=r"^([^*]|(\*[^/]))*$")]

Pattern8 = Annotated[str, StringConstraints(pattern=r"^[ \t\n]+$")]

Pattern9 = Annotated[str, StringConstraints(pattern=r"^([ \t\n]+)$")]

Pattern10 = Annotated[str, StringConstraints(pattern=r"^(\+|\-)$")]

Pattern11 = Annotated[str, StringConstraints(pattern=r"^(\*|/)$")]


class Root(GrammarModel):
    root_item: List[RootItem]


class Declaration(GrammarModel):
    dataType: DataType
    identifier: Identifier
    parameter: Optional[Parameter] = None
    statement: List[Statement]


class DataType(GrammarModel):
    pass


class DataTypeArm1(DataType):
    ws: Optional[Ws] = None


class DataTypeArm2(DataType):
    ws: Optional[Ws] = None


class DataTypeArm3(DataType):
    ws: Optional[Ws] = None


class Factor(GrammarModel):
    pass


class Identifier(Factor):
    value: str


class Parameter(GrammarModel):
    dataType: DataType
    identifier: Identifier


class Statement(GrammarModel):
    pass


class StatementArm1(Statement):
    kind: str


class StatementArm2(Statement):
    kind: str


class StatementArm3(Statement):
    kind: str


class StatementArm4(Statement):
    kind: str


class StatementArm5(Statement):
    kind: str


class StatementArm6(Statement):
    kind: str


class StatementArm7(Statement):
    kind: str


class StatementArm8(Statement):
    kind: SingleLineComment


class StatementArm9(Statement):
    kind: MultiLineComment


class ForInit(GrammarModel):
    pass


class ForInitArm1(ForInit):
    dataType: DataType
    identifier: Identifier
    ws: Optional[Ws] = None
    ws2: Optional[Ws] = None
    expression: Expression


class ForInitArm2(ForInit):
    identifier: Identifier
    ws: Optional[Ws] = None
    ws2: Optional[Ws] = None
    expression: Expression


class ForUpdate(GrammarModel):
    identifier: Identifier
    ws: Optional[Ws] = None
    ws2: Optional[Ws] = None
    expression: Expression


class Condition(GrammarModel):
    expression: Expression
    relationOperator: RelationOperator
    expression2: Expression


class RelationOperator(GrammarModel):
    value: Pattern2


class Expression(GrammarModel):
    term: Term
    expression_item: List[ExpressionItem]


class Term(GrammarModel):
    factor: Factor
    term_item: List[TermItem]


class UnaryTerm(Factor):
    factor: Factor


class FuncCall(Factor):
    identifier: Identifier
    argList: Optional[ArgList] = None


class ParenExpression(Factor):
    ws: Optional[Ws] = None
    expression: Expression
    ws2: Optional[Ws] = None


class ArgList(GrammarModel):
    expression: Expression
    argList_item: List[ArgListItem]


class Number(Factor):
    value: Digit


class SingleLineComment(GrammarModel):
    value: str


class MultiLineComment(GrammarModel):
    value: str


class Ws(GrammarModel):
    value: Pattern9


class RootItem(GrammarModel):
    declaration: Declaration


class StatementItem(GrammarModel):
    statement: List[Statement]


class ExpressionItem(GrammarModel):
    sign: Pattern10
    term: Term


class TermItem(GrammarModel):
    head: Pattern11
    factor: Factor


class ArgListItem(GrammarModel):
    ws: Optional[Ws] = None
    expression: Expression


Root.__grammar__ = RuleSpec(
    rule_name="root",
    class_name="Root",
    parent_class_name="GrammarModel",
    kind="sequence",
    items=[IrItem(IrRuleRef("root-item"), Quantifier(0, None))],
    field_map={"root_item": 0},
    non_semantic_fields=frozenset([]),
)


Declaration.__grammar__ = RuleSpec(
    rule_name="declaration",
    class_name="Declaration",
    parent_class_name="GrammarModel",
    kind="sequence",
    items=[
        IrItem(IrRuleRef("dataType"), Quantifier(1, 1)),
        IrItem(IrRuleRef("identifier"), Quantifier(1, 1)),
        IrItem(IrLiteral("("), Quantifier(1, 1)),
        IrItem(IrRuleRef("parameter"), Quantifier(0, 1)),
        IrItem(IrLiteral(")"), Quantifier(1, 1)),
        IrItem(IrLiteral("{"), Quantifier(1, 1)),
        IrItem(IrRuleRef("statement"), Quantifier(0, None)),
        IrItem(IrLiteral("}"), Quantifier(1, 1)),
    ],
    field_map={"dataType": 0, "identifier": 1, "parameter": 3, "statement": 6},
    non_semantic_fields=frozenset([]),
)


DataType.__grammar__ = RuleSpec(
    rule_name="dataType",
    class_name="DataType",
    parent_class_name="GrammarModel",
    kind="alternation",
    items=[
        IrItem(IrRuleRef("dataType-arm1"), Quantifier(1, 1)),
        IrItem(IrRuleRef("dataType-arm2"), Quantifier(1, 1)),
        IrItem(IrRuleRef("dataType-arm3"), Quantifier(1, 1)),
    ],
    field_map={},
    non_semantic_fields=frozenset([]),
)


DataTypeArm1.__grammar__ = RuleSpec(
    rule_name="dataType-arm1",
    class_name="DataTypeArm1",
    parent_class_name="DataType",
    kind="sequence",
    items=[
        IrItem(IrLiteral("int"), Quantifier(1, 1)),
        IrItem(IrRuleRef("ws"), Quantifier(0, 1)),
    ],
    field_map={"ws": 1},
    non_semantic_fields=frozenset(["ws"]),
)


DataTypeArm2.__grammar__ = RuleSpec(
    rule_name="dataType-arm2",
    class_name="DataTypeArm2",
    parent_class_name="DataType",
    kind="sequence",
    items=[
        IrItem(IrLiteral("float"), Quantifier(1, 1)),
        IrItem(IrRuleRef("ws"), Quantifier(0, 1)),
    ],
    field_map={"ws": 1},
    non_semantic_fields=frozenset(["ws"]),
)


DataTypeArm3.__grammar__ = RuleSpec(
    rule_name="dataType-arm3",
    class_name="DataTypeArm3",
    parent_class_name="DataType",
    kind="sequence",
    items=[
        IrItem(IrLiteral("char"), Quantifier(1, 1)),
        IrItem(IrRuleRef("ws"), Quantifier(0, 1)),
    ],
    field_map={"ws": 1},
    non_semantic_fields=frozenset(["ws"]),
)


Factor.__grammar__ = RuleSpec(
    rule_name="factor",
    class_name="Factor",
    parent_class_name="GrammarModel",
    kind="alternation",
    items=[
        IrItem(IrRuleRef("identifier"), Quantifier(1, 1)),
        IrItem(IrRuleRef("number"), Quantifier(1, 1)),
        IrItem(IrRuleRef("unaryTerm"), Quantifier(1, 1)),
        IrItem(IrRuleRef("funcCall"), Quantifier(1, 1)),
        IrItem(IrRuleRef("parenExpression"), Quantifier(1, 1)),
    ],
    field_map={},
    non_semantic_fields=frozenset([]),
)


Identifier.__grammar__ = RuleSpec(
    rule_name="identifier",
    class_name="Identifier",
    parent_class_name="Factor",
    kind="value_str",
    items=[
        IrItem(IrCharClass("a-zA-Z_", negated=False), Quantifier(1, 1)),
        IrItem(IrCharClass("a-zA-Z_0-9", negated=False), Quantifier(0, None)),
    ],
    field_map={},
    non_semantic_fields=frozenset([]),
)


Parameter.__grammar__ = RuleSpec(
    rule_name="parameter",
    class_name="Parameter",
    parent_class_name="GrammarModel",
    kind="sequence",
    items=[
        IrItem(IrRuleRef("dataType"), Quantifier(1, 1)),
        IrItem(IrRuleRef("identifier"), Quantifier(1, 1)),
    ],
    field_map={"dataType": 0, "identifier": 1},
    non_semantic_fields=frozenset([]),
)


Statement.__grammar__ = RuleSpec(
    rule_name="statement",
    class_name="Statement",
    parent_class_name="GrammarModel",
    kind="alternation",
    items=[
        IrItem(IrRuleRef("statement-arm1"), Quantifier(1, 1)),
        IrItem(IrRuleRef("statement-arm2"), Quantifier(1, 1)),
        IrItem(IrRuleRef("statement-arm3"), Quantifier(1, 1)),
        IrItem(IrRuleRef("statement-arm4"), Quantifier(1, 1)),
        IrItem(IrRuleRef("statement-arm5"), Quantifier(1, 1)),
        IrItem(IrRuleRef("statement-arm6"), Quantifier(1, 1)),
        IrItem(IrRuleRef("statement-arm7"), Quantifier(1, 1)),
        IrItem(IrRuleRef("statement-arm8"), Quantifier(1, 1)),
        IrItem(IrRuleRef("statement-arm9"), Quantifier(1, 1)),
    ],
    field_map={},
    non_semantic_fields=frozenset([]),
)


StatementArm1.__grammar__ = RuleSpec(
    rule_name="statement-arm1",
    class_name="StatementArm1",
    parent_class_name="Statement",
    kind="sequence",
    items=[
        IrItem(
            IrGroup(
                IrAlternation(
                    arms=(
                        IrSequence(
                            items=(
                                IrItem(IrRuleRef("dataType"), Quantifier(1, 1)),
                                IrItem(IrRuleRef("identifier"), Quantifier(1, 1)),
                                IrItem(IrRuleRef("ws"), Quantifier(1, 1)),
                                IrItem(IrLiteral("="), Quantifier(1, 1)),
                                IrItem(IrRuleRef("ws"), Quantifier(1, 1)),
                                IrItem(IrRuleRef("expression"), Quantifier(1, 1)),
                                IrItem(IrLiteral(";"), Quantifier(1, 1)),
                            )
                        ),
                    )
                )
            ),
            Quantifier(1, 1),
        )
    ],
    field_map={"kind": 0},
    non_semantic_fields=frozenset([]),
)


StatementArm2.__grammar__ = RuleSpec(
    rule_name="statement-arm2",
    class_name="StatementArm2",
    parent_class_name="Statement",
    kind="sequence",
    items=[
        IrItem(
            IrGroup(
                IrAlternation(
                    arms=(
                        IrSequence(
                            items=(
                                IrItem(IrRuleRef("identifier"), Quantifier(1, 1)),
                                IrItem(IrRuleRef("ws"), Quantifier(1, 1)),
                                IrItem(IrLiteral("="), Quantifier(1, 1)),
                                IrItem(IrRuleRef("ws"), Quantifier(1, 1)),
                                IrItem(IrRuleRef("expression"), Quantifier(1, 1)),
                                IrItem(IrLiteral(";"), Quantifier(1, 1)),
                            )
                        ),
                    )
                )
            ),
            Quantifier(1, 1),
        )
    ],
    field_map={"kind": 0},
    non_semantic_fields=frozenset([]),
)


StatementArm3.__grammar__ = RuleSpec(
    rule_name="statement-arm3",
    class_name="StatementArm3",
    parent_class_name="Statement",
    kind="sequence",
    items=[
        IrItem(
            IrGroup(
                IrAlternation(
                    arms=(
                        IrSequence(
                            items=(
                                IrItem(IrRuleRef("identifier"), Quantifier(1, 1)),
                                IrItem(IrRuleRef("ws"), Quantifier(1, 1)),
                                IrItem(IrLiteral("("), Quantifier(1, 1)),
                                IrItem(IrRuleRef("argList"), Quantifier(0, 1)),
                                IrItem(IrLiteral(")"), Quantifier(1, 1)),
                                IrItem(IrLiteral(";"), Quantifier(1, 1)),
                            )
                        ),
                    )
                )
            ),
            Quantifier(1, 1),
        )
    ],
    field_map={"kind": 0},
    non_semantic_fields=frozenset([]),
)


StatementArm4.__grammar__ = RuleSpec(
    rule_name="statement-arm4",
    class_name="StatementArm4",
    parent_class_name="Statement",
    kind="sequence",
    items=[
        IrItem(
            IrGroup(
                IrAlternation(
                    arms=(
                        IrSequence(
                            items=(
                                IrItem(IrLiteral("return"), Quantifier(1, 1)),
                                IrItem(IrRuleRef("ws"), Quantifier(1, 1)),
                                IrItem(IrRuleRef("expression"), Quantifier(1, 1)),
                                IrItem(IrLiteral(";"), Quantifier(1, 1)),
                            )
                        ),
                    )
                )
            ),
            Quantifier(1, 1),
        )
    ],
    field_map={"kind": 0},
    non_semantic_fields=frozenset([]),
)


StatementArm5.__grammar__ = RuleSpec(
    rule_name="statement-arm5",
    class_name="StatementArm5",
    parent_class_name="Statement",
    kind="sequence",
    items=[
        IrItem(
            IrGroup(
                IrAlternation(
                    arms=(
                        IrSequence(
                            items=(
                                IrItem(IrLiteral("while"), Quantifier(1, 1)),
                                IrItem(IrLiteral("("), Quantifier(1, 1)),
                                IrItem(IrRuleRef("condition"), Quantifier(1, 1)),
                                IrItem(IrLiteral(")"), Quantifier(1, 1)),
                                IrItem(IrLiteral("{"), Quantifier(1, 1)),
                                IrItem(IrRuleRef("statement"), Quantifier(0, None)),
                                IrItem(IrLiteral("}"), Quantifier(1, 1)),
                            )
                        ),
                    )
                )
            ),
            Quantifier(1, 1),
        )
    ],
    field_map={"kind": 0},
    non_semantic_fields=frozenset([]),
)


StatementArm6.__grammar__ = RuleSpec(
    rule_name="statement-arm6",
    class_name="StatementArm6",
    parent_class_name="Statement",
    kind="sequence",
    items=[
        IrItem(
            IrGroup(
                IrAlternation(
                    arms=(
                        IrSequence(
                            items=(
                                IrItem(IrLiteral("for"), Quantifier(1, 1)),
                                IrItem(IrLiteral("("), Quantifier(1, 1)),
                                IrItem(IrRuleRef("forInit"), Quantifier(1, 1)),
                                IrItem(IrLiteral(";"), Quantifier(1, 1)),
                                IrItem(IrRuleRef("ws"), Quantifier(1, 1)),
                                IrItem(IrRuleRef("condition"), Quantifier(1, 1)),
                                IrItem(IrLiteral(";"), Quantifier(1, 1)),
                                IrItem(IrRuleRef("ws"), Quantifier(1, 1)),
                                IrItem(IrRuleRef("forUpdate"), Quantifier(1, 1)),
                                IrItem(IrLiteral(")"), Quantifier(1, 1)),
                                IrItem(IrLiteral("{"), Quantifier(1, 1)),
                                IrItem(IrRuleRef("statement"), Quantifier(0, None)),
                                IrItem(IrLiteral("}"), Quantifier(1, 1)),
                            )
                        ),
                    )
                )
            ),
            Quantifier(1, 1),
        )
    ],
    field_map={"kind": 0},
    non_semantic_fields=frozenset([]),
)


StatementArm7.__grammar__ = RuleSpec(
    rule_name="statement-arm7",
    class_name="StatementArm7",
    parent_class_name="Statement",
    kind="sequence",
    items=[
        IrItem(
            IrGroup(
                IrAlternation(
                    arms=(
                        IrSequence(
                            items=(
                                IrItem(IrLiteral("if"), Quantifier(1, 1)),
                                IrItem(IrLiteral("("), Quantifier(1, 1)),
                                IrItem(IrRuleRef("condition"), Quantifier(1, 1)),
                                IrItem(IrLiteral(")"), Quantifier(1, 1)),
                                IrItem(IrLiteral("{"), Quantifier(1, 1)),
                                IrItem(IrRuleRef("statement"), Quantifier(0, None)),
                                IrItem(IrLiteral("}"), Quantifier(1, 1)),
                                IrItem(IrRuleRef("statement-item"), Quantifier(0, 1)),
                            )
                        ),
                    )
                )
            ),
            Quantifier(1, 1),
        )
    ],
    field_map={"kind": 0},
    non_semantic_fields=frozenset([]),
)


StatementArm8.__grammar__ = RuleSpec(
    rule_name="statement-arm8",
    class_name="StatementArm8",
    parent_class_name="Statement",
    kind="sequence",
    items=[
        IrItem(
            IrGroup(
                IrAlternation(
                    arms=(
                        IrSequence(
                            items=(
                                IrItem(
                                    IrRuleRef("singleLineComment"), Quantifier(1, 1)
                                ),
                            )
                        ),
                    )
                )
            ),
            Quantifier(1, 1),
        )
    ],
    field_map={"kind": 0},
    non_semantic_fields=frozenset([]),
)


StatementArm9.__grammar__ = RuleSpec(
    rule_name="statement-arm9",
    class_name="StatementArm9",
    parent_class_name="Statement",
    kind="sequence",
    items=[
        IrItem(
            IrGroup(
                IrAlternation(
                    arms=(
                        IrSequence(
                            items=(
                                IrItem(IrRuleRef("multiLineComment"), Quantifier(1, 1)),
                            )
                        ),
                    )
                )
            ),
            Quantifier(1, 1),
        )
    ],
    field_map={"kind": 0},
    non_semantic_fields=frozenset([]),
)


ForInit.__grammar__ = RuleSpec(
    rule_name="forInit",
    class_name="ForInit",
    parent_class_name="GrammarModel",
    kind="alternation",
    items=[
        IrItem(IrRuleRef("forInit-arm1"), Quantifier(1, 1)),
        IrItem(IrRuleRef("forInit-arm2"), Quantifier(1, 1)),
    ],
    field_map={},
    non_semantic_fields=frozenset([]),
)


ForInitArm1.__grammar__ = RuleSpec(
    rule_name="forInit-arm1",
    class_name="ForInitArm1",
    parent_class_name="ForInit",
    kind="sequence",
    items=[
        IrItem(IrRuleRef("dataType"), Quantifier(1, 1)),
        IrItem(IrRuleRef("identifier"), Quantifier(1, 1)),
        IrItem(IrRuleRef("ws"), Quantifier(0, 1)),
        IrItem(IrLiteral("="), Quantifier(1, 1)),
        IrItem(IrRuleRef("ws"), Quantifier(0, 1)),
        IrItem(IrRuleRef("expression"), Quantifier(1, 1)),
    ],
    field_map={"dataType": 0, "identifier": 1, "ws": 2, "ws2": 4, "expression": 5},
    non_semantic_fields=frozenset(["ws", "ws2"]),
)


ForInitArm2.__grammar__ = RuleSpec(
    rule_name="forInit-arm2",
    class_name="ForInitArm2",
    parent_class_name="ForInit",
    kind="sequence",
    items=[
        IrItem(IrRuleRef("identifier"), Quantifier(1, 1)),
        IrItem(IrRuleRef("ws"), Quantifier(0, 1)),
        IrItem(IrLiteral("="), Quantifier(1, 1)),
        IrItem(IrRuleRef("ws"), Quantifier(0, 1)),
        IrItem(IrRuleRef("expression"), Quantifier(1, 1)),
    ],
    field_map={"identifier": 0, "ws": 1, "ws2": 3, "expression": 4},
    non_semantic_fields=frozenset(["ws", "ws2"]),
)


ForUpdate.__grammar__ = RuleSpec(
    rule_name="forUpdate",
    class_name="ForUpdate",
    parent_class_name="GrammarModel",
    kind="sequence",
    items=[
        IrItem(IrRuleRef("identifier"), Quantifier(1, 1)),
        IrItem(IrRuleRef("ws"), Quantifier(0, 1)),
        IrItem(IrLiteral("="), Quantifier(1, 1)),
        IrItem(IrRuleRef("ws"), Quantifier(0, 1)),
        IrItem(IrRuleRef("expression"), Quantifier(1, 1)),
    ],
    field_map={"identifier": 0, "ws": 1, "ws2": 3, "expression": 4},
    non_semantic_fields=frozenset(["ws", "ws2"]),
)


Condition.__grammar__ = RuleSpec(
    rule_name="condition",
    class_name="Condition",
    parent_class_name="GrammarModel",
    kind="sequence",
    items=[
        IrItem(IrRuleRef("expression"), Quantifier(1, 1)),
        IrItem(IrRuleRef("relationOperator"), Quantifier(1, 1)),
        IrItem(IrRuleRef("expression"), Quantifier(1, 1)),
    ],
    field_map={"expression": 0, "relationOperator": 1, "expression2": 2},
    non_semantic_fields=frozenset([]),
)


RelationOperator.__grammar__ = RuleSpec(
    rule_name="relationOperator",
    class_name="RelationOperator",
    parent_class_name="GrammarModel",
    kind="value_str",
    items=[
        IrItem(
            IrGroup(
                IrAlternation(
                    arms=(
                        IrSequence(items=(IrItem(IrLiteral("<="), Quantifier(1, 1)),)),
                        IrSequence(items=(IrItem(IrLiteral("<"), Quantifier(1, 1)),)),
                        IrSequence(items=(IrItem(IrLiteral("=="), Quantifier(1, 1)),)),
                        IrSequence(items=(IrItem(IrLiteral("!="), Quantifier(1, 1)),)),
                        IrSequence(items=(IrItem(IrLiteral(">="), Quantifier(1, 1)),)),
                        IrSequence(items=(IrItem(IrLiteral(">"), Quantifier(1, 1)),)),
                    )
                )
            ),
            Quantifier(1, 1),
        )
    ],
    field_map={},
    non_semantic_fields=frozenset([]),
)


Expression.__grammar__ = RuleSpec(
    rule_name="expression",
    class_name="Expression",
    parent_class_name="GrammarModel",
    kind="sequence",
    items=[
        IrItem(IrRuleRef("term"), Quantifier(1, 1)),
        IrItem(IrRuleRef("expression-item"), Quantifier(0, None)),
    ],
    field_map={"term": 0, "expression_item": 1},
    non_semantic_fields=frozenset([]),
)


Term.__grammar__ = RuleSpec(
    rule_name="term",
    class_name="Term",
    parent_class_name="GrammarModel",
    kind="sequence",
    items=[
        IrItem(IrRuleRef("factor"), Quantifier(1, 1)),
        IrItem(IrRuleRef("term-item"), Quantifier(0, None)),
    ],
    field_map={"factor": 0, "term_item": 1},
    non_semantic_fields=frozenset([]),
)


UnaryTerm.__grammar__ = RuleSpec(
    rule_name="unaryTerm",
    class_name="UnaryTerm",
    parent_class_name="Factor",
    kind="sequence",
    items=[
        IrItem(IrLiteral("-"), Quantifier(1, 1)),
        IrItem(IrRuleRef("factor"), Quantifier(1, 1)),
    ],
    field_map={"factor": 1},
    non_semantic_fields=frozenset([]),
)


FuncCall.__grammar__ = RuleSpec(
    rule_name="funcCall",
    class_name="FuncCall",
    parent_class_name="Factor",
    kind="sequence",
    items=[
        IrItem(IrRuleRef("identifier"), Quantifier(1, 1)),
        IrItem(IrLiteral("("), Quantifier(1, 1)),
        IrItem(IrRuleRef("argList"), Quantifier(0, 1)),
        IrItem(IrLiteral(")"), Quantifier(1, 1)),
    ],
    field_map={"identifier": 0, "argList": 2},
    non_semantic_fields=frozenset([]),
)


ParenExpression.__grammar__ = RuleSpec(
    rule_name="parenExpression",
    class_name="ParenExpression",
    parent_class_name="Factor",
    kind="sequence",
    items=[
        IrItem(IrLiteral("("), Quantifier(1, 1)),
        IrItem(IrRuleRef("ws"), Quantifier(0, 1)),
        IrItem(IrRuleRef("expression"), Quantifier(1, 1)),
        IrItem(IrRuleRef("ws"), Quantifier(0, 1)),
        IrItem(IrLiteral(")"), Quantifier(1, 1)),
    ],
    field_map={"ws": 1, "expression": 2, "ws2": 3},
    non_semantic_fields=frozenset(["ws", "ws2"]),
)


ArgList.__grammar__ = RuleSpec(
    rule_name="argList",
    class_name="ArgList",
    parent_class_name="GrammarModel",
    kind="sequence",
    items=[
        IrItem(IrRuleRef("expression"), Quantifier(1, 1)),
        IrItem(IrRuleRef("argList-item"), Quantifier(0, None)),
    ],
    field_map={"expression": 0, "argList_item": 1},
    non_semantic_fields=frozenset([]),
)


Number.__grammar__ = RuleSpec(
    rule_name="number",
    class_name="Number",
    parent_class_name="Factor",
    kind="value_str",
    items=[IrItem(IrCharClass("0-9", negated=False), Quantifier(1, None))],
    field_map={},
    non_semantic_fields=frozenset([]),
)


SingleLineComment.__grammar__ = RuleSpec(
    rule_name="singleLineComment",
    class_name="SingleLineComment",
    parent_class_name="GrammarModel",
    kind="value_str",
    items=[
        IrItem(IrLiteral("//"), Quantifier(1, 1)),
        IrItem(IrCharClass("\\n", negated=True), Quantifier(0, None)),
        IrItem(IrLiteral("\n"), Quantifier(1, 1)),
    ],
    field_map={},
    non_semantic_fields=frozenset([]),
)


MultiLineComment.__grammar__ = RuleSpec(
    rule_name="multiLineComment",
    class_name="MultiLineComment",
    parent_class_name="GrammarModel",
    kind="value_str",
    items=[
        IrItem(IrLiteral("/*"), Quantifier(1, 1)),
        IrItem(
            IrGroup(
                IrAlternation(
                    arms=(
                        IrSequence(
                            items=(
                                IrItem(
                                    IrCharClass("*", negated=True), Quantifier(1, 1)
                                ),
                            )
                        ),
                        IrSequence(
                            items=(
                                IrItem(
                                    IrGroup(
                                        IrAlternation(
                                            arms=(
                                                IrSequence(
                                                    items=(
                                                        IrItem(
                                                            IrLiteral("*"),
                                                            Quantifier(1, 1),
                                                        ),
                                                        IrItem(
                                                            IrCharClass(
                                                                "/", negated=True
                                                            ),
                                                            Quantifier(1, 1),
                                                        ),
                                                    )
                                                ),
                                            )
                                        )
                                    ),
                                    Quantifier(1, 1),
                                ),
                            )
                        ),
                    )
                )
            ),
            Quantifier(0, None),
        ),
        IrItem(IrLiteral("*/"), Quantifier(1, 1)),
    ],
    field_map={},
    non_semantic_fields=frozenset([]),
)


Ws.__grammar__ = RuleSpec(
    rule_name="ws",
    class_name="Ws",
    parent_class_name="GrammarModel",
    kind="value_str",
    items=[
        IrItem(
            IrGroup(
                IrAlternation(
                    arms=(
                        IrSequence(
                            items=(
                                IrItem(
                                    IrCharClass(" \\t\\n", negated=False),
                                    Quantifier(1, None),
                                ),
                            )
                        ),
                    )
                )
            ),
            Quantifier(1, 1),
        )
    ],
    field_map={},
    non_semantic_fields=frozenset([]),
)


RootItem.__grammar__ = RuleSpec(
    rule_name="root-item",
    class_name="RootItem",
    parent_class_name="GrammarModel",
    kind="sequence",
    items=[IrItem(IrRuleRef("declaration"), Quantifier(1, 1))],
    field_map={"declaration": 0},
    non_semantic_fields=frozenset([]),
)


StatementItem.__grammar__ = RuleSpec(
    rule_name="statement-item",
    class_name="StatementItem",
    parent_class_name="GrammarModel",
    kind="sequence",
    items=[
        IrItem(IrLiteral("else"), Quantifier(1, 1)),
        IrItem(IrLiteral("{"), Quantifier(1, 1)),
        IrItem(IrRuleRef("statement"), Quantifier(0, None)),
        IrItem(IrLiteral("}"), Quantifier(1, 1)),
    ],
    field_map={"statement": 2},
    non_semantic_fields=frozenset([]),
)


ExpressionItem.__grammar__ = RuleSpec(
    rule_name="expression-item",
    class_name="ExpressionItem",
    parent_class_name="GrammarModel",
    kind="sequence",
    items=[
        IrItem(
            IrGroup(
                IrAlternation(
                    arms=(
                        IrSequence(items=(IrItem(IrLiteral("+"), Quantifier(1, 1)),)),
                        IrSequence(items=(IrItem(IrLiteral("-"), Quantifier(1, 1)),)),
                    )
                )
            ),
            Quantifier(1, 1),
        ),
        IrItem(IrRuleRef("term"), Quantifier(1, 1)),
    ],
    field_map={"sign": 0, "term": 1},
    non_semantic_fields=frozenset([]),
)


TermItem.__grammar__ = RuleSpec(
    rule_name="term-item",
    class_name="TermItem",
    parent_class_name="GrammarModel",
    kind="sequence",
    items=[
        IrItem(
            IrGroup(
                IrAlternation(
                    arms=(
                        IrSequence(items=(IrItem(IrLiteral("*"), Quantifier(1, 1)),)),
                        IrSequence(items=(IrItem(IrLiteral("/"), Quantifier(1, 1)),)),
                    )
                )
            ),
            Quantifier(1, 1),
        ),
        IrItem(IrRuleRef("factor"), Quantifier(1, 1)),
    ],
    field_map={"head": 0, "factor": 1},
    non_semantic_fields=frozenset([]),
)


ArgListItem.__grammar__ = RuleSpec(
    rule_name="argList-item",
    class_name="ArgListItem",
    parent_class_name="GrammarModel",
    kind="sequence",
    items=[
        IrItem(IrLiteral(","), Quantifier(1, 1)),
        IrItem(IrRuleRef("ws"), Quantifier(0, 1)),
        IrItem(IrRuleRef("expression"), Quantifier(1, 1)),
    ],
    field_map={"ws": 1, "expression": 2},
    non_semantic_fields=frozenset(["ws"]),
)
