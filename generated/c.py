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
    IrNot,
    IrRuleRef,
    IrSequence,
    IrQuantifier,
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
    items=[
        IrItem(
            atom=IrRuleRef(value="root-item"), quantifier=IrQuantifier(min=0, max=None)
        )
    ],
    field_map={"root_item": 0},
    non_semantic_fields=frozenset([]),
)


Declaration.__grammar__ = RuleSpec(
    rule_name="declaration",
    class_name="Declaration",
    parent_class_name="GrammarModel",
    kind="sequence",
    items=[
        IrItem(atom=IrRuleRef(value="dataType"), quantifier=IrQuantifier(min=1, max=1)),
        IrItem(
            atom=IrRuleRef(value="identifier"), quantifier=IrQuantifier(min=1, max=1)
        ),
        IrItem(atom=IrLiteral(value="("), quantifier=IrQuantifier(min=1, max=1)),
        IrItem(
            atom=IrRuleRef(value="parameter"), quantifier=IrQuantifier(min=0, max=1)
        ),
        IrItem(atom=IrLiteral(value=")"), quantifier=IrQuantifier(min=1, max=1)),
        IrItem(atom=IrLiteral(value="{"), quantifier=IrQuantifier(min=1, max=1)),
        IrItem(
            atom=IrRuleRef(value="statement"), quantifier=IrQuantifier(min=0, max=None)
        ),
        IrItem(atom=IrLiteral(value="}"), quantifier=IrQuantifier(min=1, max=1)),
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
        IrItem(
            atom=IrRuleRef(value="dataType-arm1"), quantifier=IrQuantifier(min=1, max=1)
        ),
        IrItem(
            atom=IrRuleRef(value="dataType-arm2"), quantifier=IrQuantifier(min=1, max=1)
        ),
        IrItem(
            atom=IrRuleRef(value="dataType-arm3"), quantifier=IrQuantifier(min=1, max=1)
        ),
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
        IrItem(atom=IrLiteral(value="int"), quantifier=IrQuantifier(min=1, max=1)),
        IrItem(atom=IrRuleRef(value="ws"), quantifier=IrQuantifier(min=0, max=1)),
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
        IrItem(atom=IrLiteral(value="float"), quantifier=IrQuantifier(min=1, max=1)),
        IrItem(atom=IrRuleRef(value="ws"), quantifier=IrQuantifier(min=0, max=1)),
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
        IrItem(atom=IrLiteral(value="char"), quantifier=IrQuantifier(min=1, max=1)),
        IrItem(atom=IrRuleRef(value="ws"), quantifier=IrQuantifier(min=0, max=1)),
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
        IrItem(
            atom=IrRuleRef(value="identifier"), quantifier=IrQuantifier(min=1, max=1)
        ),
        IrItem(atom=IrRuleRef(value="number"), quantifier=IrQuantifier(min=1, max=1)),
        IrItem(
            atom=IrRuleRef(value="unaryTerm"), quantifier=IrQuantifier(min=1, max=1)
        ),
        IrItem(atom=IrRuleRef(value="funcCall"), quantifier=IrQuantifier(min=1, max=1)),
        IrItem(
            atom=IrRuleRef(value="parenExpression"),
            quantifier=IrQuantifier(min=1, max=1),
        ),
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
        IrItem(
            atom=IrCharClass(value="a-zA-Z_"), quantifier=IrQuantifier(min=1, max=1)
        ),
        IrItem(
            atom=IrCharClass(value="a-zA-Z_0-9"),
            quantifier=IrQuantifier(min=0, max=None),
        ),
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
        IrItem(atom=IrRuleRef(value="dataType"), quantifier=IrQuantifier(min=1, max=1)),
        IrItem(
            atom=IrRuleRef(value="identifier"), quantifier=IrQuantifier(min=1, max=1)
        ),
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
        IrItem(
            atom=IrRuleRef(value="statement-arm1"),
            quantifier=IrQuantifier(min=1, max=1),
        ),
        IrItem(
            atom=IrRuleRef(value="statement-arm2"),
            quantifier=IrQuantifier(min=1, max=1),
        ),
        IrItem(
            atom=IrRuleRef(value="statement-arm3"),
            quantifier=IrQuantifier(min=1, max=1),
        ),
        IrItem(
            atom=IrRuleRef(value="statement-arm4"),
            quantifier=IrQuantifier(min=1, max=1),
        ),
        IrItem(
            atom=IrRuleRef(value="statement-arm5"),
            quantifier=IrQuantifier(min=1, max=1),
        ),
        IrItem(
            atom=IrRuleRef(value="statement-arm6"),
            quantifier=IrQuantifier(min=1, max=1),
        ),
        IrItem(
            atom=IrRuleRef(value="statement-arm7"),
            quantifier=IrQuantifier(min=1, max=1),
        ),
        IrItem(
            atom=IrRuleRef(value="statement-arm8"),
            quantifier=IrQuantifier(min=1, max=1),
        ),
        IrItem(
            atom=IrRuleRef(value="statement-arm9"),
            quantifier=IrQuantifier(min=1, max=1),
        ),
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
            atom=IrGroup(
                body=IrAlternation(
                    arms=(
                        IrSequence(
                            items=(
                                IrItem(
                                    atom=IrRuleRef(value="dataType"),
                                    quantifier=IrQuantifier(min=1, max=1),
                                ),
                                IrItem(
                                    atom=IrRuleRef(value="identifier"),
                                    quantifier=IrQuantifier(min=1, max=1),
                                ),
                                IrItem(
                                    atom=IrRuleRef(value="ws"),
                                    quantifier=IrQuantifier(min=1, max=1),
                                ),
                                IrItem(
                                    atom=IrLiteral(value="="),
                                    quantifier=IrQuantifier(min=1, max=1),
                                ),
                                IrItem(
                                    atom=IrRuleRef(value="ws"),
                                    quantifier=IrQuantifier(min=1, max=1),
                                ),
                                IrItem(
                                    atom=IrRuleRef(value="expression"),
                                    quantifier=IrQuantifier(min=1, max=1),
                                ),
                                IrItem(
                                    atom=IrLiteral(value=";"),
                                    quantifier=IrQuantifier(min=1, max=1),
                                ),
                            )
                        ),
                    )
                )
            ),
            quantifier=IrQuantifier(min=1, max=1),
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
            atom=IrGroup(
                body=IrAlternation(
                    arms=(
                        IrSequence(
                            items=(
                                IrItem(
                                    atom=IrRuleRef(value="identifier"),
                                    quantifier=IrQuantifier(min=1, max=1),
                                ),
                                IrItem(
                                    atom=IrRuleRef(value="ws"),
                                    quantifier=IrQuantifier(min=1, max=1),
                                ),
                                IrItem(
                                    atom=IrLiteral(value="="),
                                    quantifier=IrQuantifier(min=1, max=1),
                                ),
                                IrItem(
                                    atom=IrRuleRef(value="ws"),
                                    quantifier=IrQuantifier(min=1, max=1),
                                ),
                                IrItem(
                                    atom=IrRuleRef(value="expression"),
                                    quantifier=IrQuantifier(min=1, max=1),
                                ),
                                IrItem(
                                    atom=IrLiteral(value=";"),
                                    quantifier=IrQuantifier(min=1, max=1),
                                ),
                            )
                        ),
                    )
                )
            ),
            quantifier=IrQuantifier(min=1, max=1),
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
            atom=IrGroup(
                body=IrAlternation(
                    arms=(
                        IrSequence(
                            items=(
                                IrItem(
                                    atom=IrRuleRef(value="identifier"),
                                    quantifier=IrQuantifier(min=1, max=1),
                                ),
                                IrItem(
                                    atom=IrRuleRef(value="ws"),
                                    quantifier=IrQuantifier(min=1, max=1),
                                ),
                                IrItem(
                                    atom=IrLiteral(value="("),
                                    quantifier=IrQuantifier(min=1, max=1),
                                ),
                                IrItem(
                                    atom=IrRuleRef(value="argList"),
                                    quantifier=IrQuantifier(min=0, max=1),
                                ),
                                IrItem(
                                    atom=IrLiteral(value=")"),
                                    quantifier=IrQuantifier(min=1, max=1),
                                ),
                                IrItem(
                                    atom=IrLiteral(value=";"),
                                    quantifier=IrQuantifier(min=1, max=1),
                                ),
                            )
                        ),
                    )
                )
            ),
            quantifier=IrQuantifier(min=1, max=1),
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
            atom=IrGroup(
                body=IrAlternation(
                    arms=(
                        IrSequence(
                            items=(
                                IrItem(
                                    atom=IrLiteral(value="return"),
                                    quantifier=IrQuantifier(min=1, max=1),
                                ),
                                IrItem(
                                    atom=IrRuleRef(value="ws"),
                                    quantifier=IrQuantifier(min=1, max=1),
                                ),
                                IrItem(
                                    atom=IrRuleRef(value="expression"),
                                    quantifier=IrQuantifier(min=1, max=1),
                                ),
                                IrItem(
                                    atom=IrLiteral(value=";"),
                                    quantifier=IrQuantifier(min=1, max=1),
                                ),
                            )
                        ),
                    )
                )
            ),
            quantifier=IrQuantifier(min=1, max=1),
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
            atom=IrGroup(
                body=IrAlternation(
                    arms=(
                        IrSequence(
                            items=(
                                IrItem(
                                    atom=IrLiteral(value="while"),
                                    quantifier=IrQuantifier(min=1, max=1),
                                ),
                                IrItem(
                                    atom=IrLiteral(value="("),
                                    quantifier=IrQuantifier(min=1, max=1),
                                ),
                                IrItem(
                                    atom=IrRuleRef(value="condition"),
                                    quantifier=IrQuantifier(min=1, max=1),
                                ),
                                IrItem(
                                    atom=IrLiteral(value=")"),
                                    quantifier=IrQuantifier(min=1, max=1),
                                ),
                                IrItem(
                                    atom=IrLiteral(value="{"),
                                    quantifier=IrQuantifier(min=1, max=1),
                                ),
                                IrItem(
                                    atom=IrRuleRef(value="statement"),
                                    quantifier=IrQuantifier(min=0, max=None),
                                ),
                                IrItem(
                                    atom=IrLiteral(value="}"),
                                    quantifier=IrQuantifier(min=1, max=1),
                                ),
                            )
                        ),
                    )
                )
            ),
            quantifier=IrQuantifier(min=1, max=1),
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
            atom=IrGroup(
                body=IrAlternation(
                    arms=(
                        IrSequence(
                            items=(
                                IrItem(
                                    atom=IrLiteral(value="for"),
                                    quantifier=IrQuantifier(min=1, max=1),
                                ),
                                IrItem(
                                    atom=IrLiteral(value="("),
                                    quantifier=IrQuantifier(min=1, max=1),
                                ),
                                IrItem(
                                    atom=IrRuleRef(value="forInit"),
                                    quantifier=IrQuantifier(min=1, max=1),
                                ),
                                IrItem(
                                    atom=IrLiteral(value=";"),
                                    quantifier=IrQuantifier(min=1, max=1),
                                ),
                                IrItem(
                                    atom=IrRuleRef(value="ws"),
                                    quantifier=IrQuantifier(min=1, max=1),
                                ),
                                IrItem(
                                    atom=IrRuleRef(value="condition"),
                                    quantifier=IrQuantifier(min=1, max=1),
                                ),
                                IrItem(
                                    atom=IrLiteral(value=";"),
                                    quantifier=IrQuantifier(min=1, max=1),
                                ),
                                IrItem(
                                    atom=IrRuleRef(value="ws"),
                                    quantifier=IrQuantifier(min=1, max=1),
                                ),
                                IrItem(
                                    atom=IrRuleRef(value="forUpdate"),
                                    quantifier=IrQuantifier(min=1, max=1),
                                ),
                                IrItem(
                                    atom=IrLiteral(value=")"),
                                    quantifier=IrQuantifier(min=1, max=1),
                                ),
                                IrItem(
                                    atom=IrLiteral(value="{"),
                                    quantifier=IrQuantifier(min=1, max=1),
                                ),
                                IrItem(
                                    atom=IrRuleRef(value="statement"),
                                    quantifier=IrQuantifier(min=0, max=None),
                                ),
                                IrItem(
                                    atom=IrLiteral(value="}"),
                                    quantifier=IrQuantifier(min=1, max=1),
                                ),
                            )
                        ),
                    )
                )
            ),
            quantifier=IrQuantifier(min=1, max=1),
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
            atom=IrGroup(
                body=IrAlternation(
                    arms=(
                        IrSequence(
                            items=(
                                IrItem(
                                    atom=IrLiteral(value="if"),
                                    quantifier=IrQuantifier(min=1, max=1),
                                ),
                                IrItem(
                                    atom=IrLiteral(value="("),
                                    quantifier=IrQuantifier(min=1, max=1),
                                ),
                                IrItem(
                                    atom=IrRuleRef(value="condition"),
                                    quantifier=IrQuantifier(min=1, max=1),
                                ),
                                IrItem(
                                    atom=IrLiteral(value=")"),
                                    quantifier=IrQuantifier(min=1, max=1),
                                ),
                                IrItem(
                                    atom=IrLiteral(value="{"),
                                    quantifier=IrQuantifier(min=1, max=1),
                                ),
                                IrItem(
                                    atom=IrRuleRef(value="statement"),
                                    quantifier=IrQuantifier(min=0, max=None),
                                ),
                                IrItem(
                                    atom=IrLiteral(value="}"),
                                    quantifier=IrQuantifier(min=1, max=1),
                                ),
                                IrItem(
                                    atom=IrRuleRef(value="statement-item"),
                                    quantifier=IrQuantifier(min=0, max=1),
                                ),
                            )
                        ),
                    )
                )
            ),
            quantifier=IrQuantifier(min=1, max=1),
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
            atom=IrGroup(
                body=IrAlternation(
                    arms=(
                        IrSequence(
                            items=(
                                IrItem(
                                    atom=IrRuleRef(value="singleLineComment"),
                                    quantifier=IrQuantifier(min=1, max=1),
                                ),
                            )
                        ),
                    )
                )
            ),
            quantifier=IrQuantifier(min=1, max=1),
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
            atom=IrGroup(
                body=IrAlternation(
                    arms=(
                        IrSequence(
                            items=(
                                IrItem(
                                    atom=IrRuleRef(value="multiLineComment"),
                                    quantifier=IrQuantifier(min=1, max=1),
                                ),
                            )
                        ),
                    )
                )
            ),
            quantifier=IrQuantifier(min=1, max=1),
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
        IrItem(
            atom=IrRuleRef(value="forInit-arm1"), quantifier=IrQuantifier(min=1, max=1)
        ),
        IrItem(
            atom=IrRuleRef(value="forInit-arm2"), quantifier=IrQuantifier(min=1, max=1)
        ),
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
        IrItem(atom=IrRuleRef(value="dataType"), quantifier=IrQuantifier(min=1, max=1)),
        IrItem(
            atom=IrRuleRef(value="identifier"), quantifier=IrQuantifier(min=1, max=1)
        ),
        IrItem(atom=IrRuleRef(value="ws"), quantifier=IrQuantifier(min=0, max=1)),
        IrItem(atom=IrLiteral(value="="), quantifier=IrQuantifier(min=1, max=1)),
        IrItem(atom=IrRuleRef(value="ws"), quantifier=IrQuantifier(min=0, max=1)),
        IrItem(
            atom=IrRuleRef(value="expression"), quantifier=IrQuantifier(min=1, max=1)
        ),
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
        IrItem(
            atom=IrRuleRef(value="identifier"), quantifier=IrQuantifier(min=1, max=1)
        ),
        IrItem(atom=IrRuleRef(value="ws"), quantifier=IrQuantifier(min=0, max=1)),
        IrItem(atom=IrLiteral(value="="), quantifier=IrQuantifier(min=1, max=1)),
        IrItem(atom=IrRuleRef(value="ws"), quantifier=IrQuantifier(min=0, max=1)),
        IrItem(
            atom=IrRuleRef(value="expression"), quantifier=IrQuantifier(min=1, max=1)
        ),
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
        IrItem(
            atom=IrRuleRef(value="identifier"), quantifier=IrQuantifier(min=1, max=1)
        ),
        IrItem(atom=IrRuleRef(value="ws"), quantifier=IrQuantifier(min=0, max=1)),
        IrItem(atom=IrLiteral(value="="), quantifier=IrQuantifier(min=1, max=1)),
        IrItem(atom=IrRuleRef(value="ws"), quantifier=IrQuantifier(min=0, max=1)),
        IrItem(
            atom=IrRuleRef(value="expression"), quantifier=IrQuantifier(min=1, max=1)
        ),
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
        IrItem(
            atom=IrRuleRef(value="expression"), quantifier=IrQuantifier(min=1, max=1)
        ),
        IrItem(
            atom=IrRuleRef(value="relationOperator"),
            quantifier=IrQuantifier(min=1, max=1),
        ),
        IrItem(
            atom=IrRuleRef(value="expression"), quantifier=IrQuantifier(min=1, max=1)
        ),
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
            atom=IrGroup(
                body=IrAlternation(
                    arms=(
                        IrSequence(
                            items=(
                                IrItem(
                                    atom=IrLiteral(value="<="),
                                    quantifier=IrQuantifier(min=1, max=1),
                                ),
                            )
                        ),
                        IrSequence(
                            items=(
                                IrItem(
                                    atom=IrLiteral(value="<"),
                                    quantifier=IrQuantifier(min=1, max=1),
                                ),
                            )
                        ),
                        IrSequence(
                            items=(
                                IrItem(
                                    atom=IrLiteral(value="=="),
                                    quantifier=IrQuantifier(min=1, max=1),
                                ),
                            )
                        ),
                        IrSequence(
                            items=(
                                IrItem(
                                    atom=IrLiteral(value="!="),
                                    quantifier=IrQuantifier(min=1, max=1),
                                ),
                            )
                        ),
                        IrSequence(
                            items=(
                                IrItem(
                                    atom=IrLiteral(value=">="),
                                    quantifier=IrQuantifier(min=1, max=1),
                                ),
                            )
                        ),
                        IrSequence(
                            items=(
                                IrItem(
                                    atom=IrLiteral(value=">"),
                                    quantifier=IrQuantifier(min=1, max=1),
                                ),
                            )
                        ),
                    )
                )
            ),
            quantifier=IrQuantifier(min=1, max=1),
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
        IrItem(atom=IrRuleRef(value="term"), quantifier=IrQuantifier(min=1, max=1)),
        IrItem(
            atom=IrRuleRef(value="expression-item"),
            quantifier=IrQuantifier(min=0, max=None),
        ),
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
        IrItem(atom=IrRuleRef(value="factor"), quantifier=IrQuantifier(min=1, max=1)),
        IrItem(
            atom=IrRuleRef(value="term-item"), quantifier=IrQuantifier(min=0, max=None)
        ),
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
        IrItem(atom=IrLiteral(value="-"), quantifier=IrQuantifier(min=1, max=1)),
        IrItem(atom=IrRuleRef(value="factor"), quantifier=IrQuantifier(min=1, max=1)),
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
        IrItem(
            atom=IrRuleRef(value="identifier"), quantifier=IrQuantifier(min=1, max=1)
        ),
        IrItem(atom=IrLiteral(value="("), quantifier=IrQuantifier(min=1, max=1)),
        IrItem(atom=IrRuleRef(value="argList"), quantifier=IrQuantifier(min=0, max=1)),
        IrItem(atom=IrLiteral(value=")"), quantifier=IrQuantifier(min=1, max=1)),
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
        IrItem(atom=IrLiteral(value="("), quantifier=IrQuantifier(min=1, max=1)),
        IrItem(atom=IrRuleRef(value="ws"), quantifier=IrQuantifier(min=0, max=1)),
        IrItem(
            atom=IrRuleRef(value="expression"), quantifier=IrQuantifier(min=1, max=1)
        ),
        IrItem(atom=IrRuleRef(value="ws"), quantifier=IrQuantifier(min=0, max=1)),
        IrItem(atom=IrLiteral(value=")"), quantifier=IrQuantifier(min=1, max=1)),
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
        IrItem(
            atom=IrRuleRef(value="expression"), quantifier=IrQuantifier(min=1, max=1)
        ),
        IrItem(
            atom=IrRuleRef(value="argList-item"),
            quantifier=IrQuantifier(min=0, max=None),
        ),
    ],
    field_map={"expression": 0, "argList_item": 1},
    non_semantic_fields=frozenset([]),
)


Number.__grammar__ = RuleSpec(
    rule_name="number",
    class_name="Number",
    parent_class_name="Factor",
    kind="value_str",
    items=[
        IrItem(atom=IrCharClass(value="0-9"), quantifier=IrQuantifier(min=1, max=None))
    ],
    field_map={},
    non_semantic_fields=frozenset([]),
)


SingleLineComment.__grammar__ = RuleSpec(
    rule_name="singleLineComment",
    class_name="SingleLineComment",
    parent_class_name="GrammarModel",
    kind="value_str",
    items=[
        IrItem(atom=IrLiteral(value="//"), quantifier=IrQuantifier(min=1, max=1)),
        IrItem(
            atom=IrNot(body=IrCharClass(value="\\n")),
            quantifier=IrQuantifier(min=0, max=None),
        ),
        IrItem(atom=IrLiteral(value="\n"), quantifier=IrQuantifier(min=1, max=1)),
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
        IrItem(atom=IrLiteral(value="/*"), quantifier=IrQuantifier(min=1, max=1)),
        IrItem(
            atom=IrGroup(
                body=IrAlternation(
                    arms=(
                        IrSequence(
                            items=(
                                IrItem(
                                    atom=IrNot(body=IrCharClass(value="*")),
                                    quantifier=IrQuantifier(min=1, max=1),
                                ),
                            )
                        ),
                        IrSequence(
                            items=(
                                IrItem(
                                    atom=IrGroup(
                                        body=IrAlternation(
                                            arms=(
                                                IrSequence(
                                                    items=(
                                                        IrItem(
                                                            atom=IrLiteral(value="*"),
                                                            quantifier=IrQuantifier(
                                                                min=1, max=1
                                                            ),
                                                        ),
                                                        IrItem(
                                                            atom=IrNot(
                                                                body=IrCharClass(
                                                                    value="/"
                                                                )
                                                            ),
                                                            quantifier=IrQuantifier(
                                                                min=1, max=1
                                                            ),
                                                        ),
                                                    )
                                                ),
                                            )
                                        )
                                    ),
                                    quantifier=IrQuantifier(min=1, max=1),
                                ),
                            )
                        ),
                    )
                )
            ),
            quantifier=IrQuantifier(min=0, max=None),
        ),
        IrItem(atom=IrLiteral(value="*/"), quantifier=IrQuantifier(min=1, max=1)),
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
            atom=IrGroup(
                body=IrAlternation(
                    arms=(
                        IrSequence(
                            items=(
                                IrItem(
                                    atom=IrCharClass(value=" \\t\\n"),
                                    quantifier=IrQuantifier(min=1, max=None),
                                ),
                            )
                        ),
                    )
                )
            ),
            quantifier=IrQuantifier(min=1, max=1),
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
    items=[
        IrItem(
            atom=IrRuleRef(value="declaration"), quantifier=IrQuantifier(min=1, max=1)
        )
    ],
    field_map={"declaration": 0},
    non_semantic_fields=frozenset([]),
)


StatementItem.__grammar__ = RuleSpec(
    rule_name="statement-item",
    class_name="StatementItem",
    parent_class_name="GrammarModel",
    kind="sequence",
    items=[
        IrItem(atom=IrLiteral(value="else"), quantifier=IrQuantifier(min=1, max=1)),
        IrItem(atom=IrLiteral(value="{"), quantifier=IrQuantifier(min=1, max=1)),
        IrItem(
            atom=IrRuleRef(value="statement"), quantifier=IrQuantifier(min=0, max=None)
        ),
        IrItem(atom=IrLiteral(value="}"), quantifier=IrQuantifier(min=1, max=1)),
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
            atom=IrGroup(
                body=IrAlternation(
                    arms=(
                        IrSequence(
                            items=(
                                IrItem(
                                    atom=IrLiteral(value="+"),
                                    quantifier=IrQuantifier(min=1, max=1),
                                ),
                            )
                        ),
                        IrSequence(
                            items=(
                                IrItem(
                                    atom=IrLiteral(value="-"),
                                    quantifier=IrQuantifier(min=1, max=1),
                                ),
                            )
                        ),
                    )
                )
            ),
            quantifier=IrQuantifier(min=1, max=1),
        ),
        IrItem(atom=IrRuleRef(value="term"), quantifier=IrQuantifier(min=1, max=1)),
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
            atom=IrGroup(
                body=IrAlternation(
                    arms=(
                        IrSequence(
                            items=(
                                IrItem(
                                    atom=IrLiteral(value="*"),
                                    quantifier=IrQuantifier(min=1, max=1),
                                ),
                            )
                        ),
                        IrSequence(
                            items=(
                                IrItem(
                                    atom=IrLiteral(value="/"),
                                    quantifier=IrQuantifier(min=1, max=1),
                                ),
                            )
                        ),
                    )
                )
            ),
            quantifier=IrQuantifier(min=1, max=1),
        ),
        IrItem(atom=IrRuleRef(value="factor"), quantifier=IrQuantifier(min=1, max=1)),
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
        IrItem(atom=IrLiteral(value=","), quantifier=IrQuantifier(min=1, max=1)),
        IrItem(atom=IrRuleRef(value="ws"), quantifier=IrQuantifier(min=0, max=1)),
        IrItem(
            atom=IrRuleRef(value="expression"), quantifier=IrQuantifier(min=1, max=1)
        ),
    ],
    field_map={"ws": 1, "expression": 2},
    non_semantic_fields=frozenset(["ws"]),
)
