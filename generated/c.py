"""Generated module: c. Do not edit; regenerated from grammar."""

from __future__ import annotations

from typing import Annotated, List, Optional

from pydantic import StringConstraints

from lexic.base import GrammarModel
from lexic.ir.base import IrNone
from lexic.ir.nodes import (
    IrAlternation,
    IrCharClass,
    IrChr,
    IrItem,
    IrLiteral,
    IrQuantifier,
    IrRange,
    IrRuleRef,
    IrSequence,
)
from lexic.ir.spec import RuleSpec

Pattern = Annotated[str, StringConstraints(pattern=r"^[A-Z_a-z]$")]

Pattern2 = Annotated[str, StringConstraints(pattern=r"^[0-9A-Z_a-z]*$")]

Pattern3 = Annotated[str, StringConstraints(pattern=r"^[\x09-\x0a ]+$")]

Pattern4 = Annotated[str, StringConstraints(pattern=r"^[\x00-\x09\x0b-\U0010ffff]*$")]

Pattern5 = Annotated[str, StringConstraints(pattern=r"^[\x00-)+-\U0010ffff]$")]

Pattern6 = Annotated[str, StringConstraints(pattern=r"^[\x00-.0-\U0010ffff]$")]

Pattern7 = Annotated[
    str, StringConstraints(pattern=r"^([\x00-)+-\U0010ffff]|\*[\x00-.0-\U0010ffff])*$")
]

Pattern8 = Annotated[str, StringConstraints(pattern=r"^(<=|<|==|!=|>=|>)$")]

Digit = Annotated[str, StringConstraints(pattern=r"^[0-9]+$")]

Pattern9 = Annotated[str, StringConstraints(pattern=r"^[+-]$")]

Pattern10 = Annotated[str, StringConstraints(pattern=r"^[*/]$")]


class Root(GrammarModel):
    declaration: List[Declaration]


class Declaration(GrammarModel):
    datatype: Datatype
    identifier: Identifier
    parameter: Optional[Parameter] = None
    statement: List[Statement]


class Datatype(GrammarModel):
    pass


class DatatypeArm1(Datatype):
    ws: Optional[Ws] = None


class DatatypeArm2(Datatype):
    ws: Optional[Ws] = None


class DatatypeArm3(Datatype):
    ws: Optional[Ws] = None


class Factor(GrammarModel):
    pass


class Identifier(Factor):
    value: str


class Parameter(GrammarModel):
    datatype: Datatype
    identifier: Identifier


class Statement(GrammarModel):
    pass


class StatementArm1(Statement):
    datatype: Datatype
    identifier: Identifier
    ws: Optional[Ws] = None
    ws2: Optional[Ws] = None
    expression: Expression


class StatementArm2(Statement):
    identifier: Identifier
    ws: Optional[Ws] = None
    ws2: Optional[Ws] = None
    expression: Expression


class StatementArm3(Statement):
    identifier: Identifier
    ws: Optional[Ws] = None
    arglist: Optional[Arglist] = None


class StatementArm4(Statement):
    ws: Optional[Ws] = None
    expression: Expression


class StatementArm5(Statement):
    condition: Condition
    statement: List[Statement]


class StatementArm6(Statement):
    forinit: Forinit
    ws: Optional[Ws] = None
    condition: Condition
    ws2: Optional[Ws] = None
    forupdate: Forupdate
    statement: List[Statement]


class StatementArm7(Statement):
    condition: Condition
    statement: List[Statement]
    statement_item: Optional[StatementItem] = None


class Ws(GrammarModel):
    value: Pattern3


class Expression(GrammarModel):
    term: Term
    expression_item: List[ExpressionItem]


class Arglist(GrammarModel):
    expression: Expression
    arglist_item: List[ArglistItem]


class Condition(GrammarModel):
    expression: Expression
    relationoperator: Relationoperator
    expression2: Expression


class Forinit(GrammarModel):
    pass


class ForinitArm1(Forinit):
    datatype: Datatype
    identifier: Identifier
    ws: Optional[Ws] = None
    ws2: Optional[Ws] = None
    expression: Expression


class ForinitArm2(Forinit):
    identifier: Identifier
    ws: Optional[Ws] = None
    ws2: Optional[Ws] = None
    expression: Expression


class Forupdate(GrammarModel):
    identifier: Identifier
    ws: Optional[Ws] = None
    ws2: Optional[Ws] = None
    expression: Expression


class Singlelinecomment(Statement):
    value: str


class Multilinecomment(Statement):
    value: str


class Term(GrammarModel):
    factor: Factor
    term_item: List[TermItem]


class Relationoperator(GrammarModel):
    value: Pattern8


class Number(Factor):
    value: Digit


class Unaryterm(Factor):
    factor: Factor


class Funccall(Factor):
    identifier: Identifier
    arglist: Optional[Arglist] = None


class Parenexpression(Factor):
    ws: Optional[Ws] = None
    expression: Expression
    ws2: Optional[Ws] = None


class StatementItem(GrammarModel):
    statement: List[Statement]


class ExpressionItem(GrammarModel):
    head: Pattern9
    term: Term


class ArglistItem(GrammarModel):
    ws: Optional[Ws] = None
    expression: Expression


class TermItem(GrammarModel):
    head: Pattern10
    factor: Factor


Root.__grammar__ = RuleSpec(
    rule_name="root",
    class_name="Root",
    parent_class_name="GrammarModel",
    kind="sequence",
    items=[IrItem(IrRuleRef("declaration"), IrQuantifier(0, IrNone))],
    field_map={"declaration": 0},
    non_semantic_fields=frozenset([]),
)


Declaration.__grammar__ = RuleSpec(
    rule_name="declaration",
    class_name="Declaration",
    parent_class_name="GrammarModel",
    kind="sequence",
    items=[
        IrItem(IrRuleRef("datatype")),
        IrItem(IrRuleRef("identifier")),
        IrItem(IrLiteral("(")),
        IrItem(IrRuleRef("parameter"), IrQuantifier(0)),
        IrItem(IrLiteral("){")),
        IrItem(IrRuleRef("statement"), IrQuantifier(0, IrNone)),
        IrItem(IrLiteral("}")),
    ],
    field_map={"datatype": 0, "identifier": 1, "parameter": 3, "statement": 5},
    non_semantic_fields=frozenset([]),
)


Datatype.__grammar__ = RuleSpec(
    rule_name="datatype",
    class_name="Datatype",
    parent_class_name="GrammarModel",
    kind="alternation",
    items=[
        IrItem(IrRuleRef("datatype-arm1")),
        IrItem(IrRuleRef("datatype-arm2")),
        IrItem(IrRuleRef("datatype-arm3")),
    ],
    field_map={},
    non_semantic_fields=frozenset([]),
)


DatatypeArm1.__grammar__ = RuleSpec(
    rule_name="datatype-arm1",
    class_name="DatatypeArm1",
    parent_class_name="Datatype",
    kind="sequence",
    items=[IrItem(IrLiteral("int")), IrItem(IrRuleRef("ws"), IrQuantifier(0))],
    field_map={"ws": 1},
    non_semantic_fields=frozenset(["ws"]),
)


DatatypeArm2.__grammar__ = RuleSpec(
    rule_name="datatype-arm2",
    class_name="DatatypeArm2",
    parent_class_name="Datatype",
    kind="sequence",
    items=[IrItem(IrLiteral("float")), IrItem(IrRuleRef("ws"), IrQuantifier(0))],
    field_map={"ws": 1},
    non_semantic_fields=frozenset(["ws"]),
)


DatatypeArm3.__grammar__ = RuleSpec(
    rule_name="datatype-arm3",
    class_name="DatatypeArm3",
    parent_class_name="Datatype",
    kind="sequence",
    items=[IrItem(IrLiteral("char")), IrItem(IrRuleRef("ws"), IrQuantifier(0))],
    field_map={"ws": 1},
    non_semantic_fields=frozenset(["ws"]),
)


Factor.__grammar__ = RuleSpec(
    rule_name="factor",
    class_name="Factor",
    parent_class_name="GrammarModel",
    kind="alternation",
    items=[
        IrItem(IrRuleRef("identifier")),
        IrItem(IrRuleRef("number")),
        IrItem(IrRuleRef("unaryterm")),
        IrItem(IrRuleRef("funccall")),
        IrItem(IrRuleRef("parenexpression")),
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
            IrCharClass(
                IrRange(IrChr(65), IrChr(90)), IrChr(95), IrRange(IrChr(97), IrChr(122))
            )
        ),
        IrItem(
            IrCharClass(
                IrRange(IrChr(48), IrChr(57)),
                IrRange(IrChr(65), IrChr(90)),
                IrChr(95),
                IrRange(IrChr(97), IrChr(122)),
            ),
            IrQuantifier(0, IrNone),
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
    items=[IrItem(IrRuleRef("datatype")), IrItem(IrRuleRef("identifier"))],
    field_map={"datatype": 0, "identifier": 1},
    non_semantic_fields=frozenset([]),
)


Statement.__grammar__ = RuleSpec(
    rule_name="statement",
    class_name="Statement",
    parent_class_name="GrammarModel",
    kind="alternation",
    items=[
        IrItem(IrRuleRef("statement-arm1")),
        IrItem(IrRuleRef("statement-arm2")),
        IrItem(IrRuleRef("statement-arm3")),
        IrItem(IrRuleRef("statement-arm4")),
        IrItem(IrRuleRef("statement-arm5")),
        IrItem(IrRuleRef("statement-arm6")),
        IrItem(IrRuleRef("statement-arm7")),
        IrItem(IrRuleRef("singlelinecomment")),
        IrItem(IrRuleRef("multilinecomment")),
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
        IrItem(IrRuleRef("datatype")),
        IrItem(IrRuleRef("identifier")),
        IrItem(IrRuleRef("ws"), IrQuantifier(0)),
        IrItem(IrLiteral("=")),
        IrItem(IrRuleRef("ws"), IrQuantifier(0)),
        IrItem(IrRuleRef("expression")),
        IrItem(IrLiteral(";")),
    ],
    field_map={"datatype": 0, "identifier": 1, "ws": 2, "ws2": 4, "expression": 5},
    non_semantic_fields=frozenset(["ws", "ws2"]),
)


StatementArm2.__grammar__ = RuleSpec(
    rule_name="statement-arm2",
    class_name="StatementArm2",
    parent_class_name="Statement",
    kind="sequence",
    items=[
        IrItem(IrRuleRef("identifier")),
        IrItem(IrRuleRef("ws"), IrQuantifier(0)),
        IrItem(IrLiteral("=")),
        IrItem(IrRuleRef("ws"), IrQuantifier(0)),
        IrItem(IrRuleRef("expression")),
        IrItem(IrLiteral(";")),
    ],
    field_map={"identifier": 0, "ws": 1, "ws2": 3, "expression": 4},
    non_semantic_fields=frozenset(["ws", "ws2"]),
)


StatementArm3.__grammar__ = RuleSpec(
    rule_name="statement-arm3",
    class_name="StatementArm3",
    parent_class_name="Statement",
    kind="sequence",
    items=[
        IrItem(IrRuleRef("identifier")),
        IrItem(IrRuleRef("ws"), IrQuantifier(0)),
        IrItem(IrLiteral("(")),
        IrItem(IrRuleRef("arglist"), IrQuantifier(0)),
        IrItem(IrLiteral(");")),
    ],
    field_map={"identifier": 0, "ws": 1, "arglist": 3},
    non_semantic_fields=frozenset(["ws"]),
)


StatementArm4.__grammar__ = RuleSpec(
    rule_name="statement-arm4",
    class_name="StatementArm4",
    parent_class_name="Statement",
    kind="sequence",
    items=[
        IrItem(IrLiteral("return")),
        IrItem(IrRuleRef("ws"), IrQuantifier(0)),
        IrItem(IrRuleRef("expression")),
        IrItem(IrLiteral(";")),
    ],
    field_map={"ws": 1, "expression": 2},
    non_semantic_fields=frozenset(["ws"]),
)


StatementArm5.__grammar__ = RuleSpec(
    rule_name="statement-arm5",
    class_name="StatementArm5",
    parent_class_name="Statement",
    kind="sequence",
    items=[
        IrItem(IrLiteral("while(")),
        IrItem(IrRuleRef("condition")),
        IrItem(IrLiteral("){")),
        IrItem(IrRuleRef("statement"), IrQuantifier(0, IrNone)),
        IrItem(IrLiteral("}")),
    ],
    field_map={"condition": 1, "statement": 3},
    non_semantic_fields=frozenset([]),
)


StatementArm6.__grammar__ = RuleSpec(
    rule_name="statement-arm6",
    class_name="StatementArm6",
    parent_class_name="Statement",
    kind="sequence",
    items=[
        IrItem(IrLiteral("for(")),
        IrItem(IrRuleRef("forinit")),
        IrItem(IrLiteral(";")),
        IrItem(IrRuleRef("ws"), IrQuantifier(0)),
        IrItem(IrRuleRef("condition")),
        IrItem(IrLiteral(";")),
        IrItem(IrRuleRef("ws"), IrQuantifier(0)),
        IrItem(IrRuleRef("forupdate")),
        IrItem(IrLiteral("){")),
        IrItem(IrRuleRef("statement"), IrQuantifier(0, IrNone)),
        IrItem(IrLiteral("}")),
    ],
    field_map={
        "forinit": 1,
        "ws": 3,
        "condition": 4,
        "ws2": 6,
        "forupdate": 7,
        "statement": 9,
    },
    non_semantic_fields=frozenset(["ws", "ws2"]),
)


StatementArm7.__grammar__ = RuleSpec(
    rule_name="statement-arm7",
    class_name="StatementArm7",
    parent_class_name="Statement",
    kind="sequence",
    items=[
        IrItem(IrLiteral("if(")),
        IrItem(IrRuleRef("condition")),
        IrItem(IrLiteral("){")),
        IrItem(IrRuleRef("statement"), IrQuantifier(0, IrNone)),
        IrItem(IrLiteral("}")),
        IrItem(IrRuleRef("statement-item"), IrQuantifier(0)),
    ],
    field_map={"condition": 1, "statement": 3, "statement_item": 5},
    non_semantic_fields=frozenset([]),
)


Ws.__grammar__ = RuleSpec(
    rule_name="ws",
    class_name="Ws",
    parent_class_name="GrammarModel",
    kind="value_str",
    items=[
        IrItem(
            IrCharClass(IrRange(IrChr(9), IrChr(10)), IrChr(32)),
            IrQuantifier(1, IrNone),
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
        IrItem(IrRuleRef("term")),
        IrItem(IrRuleRef("expression-item"), IrQuantifier(0, IrNone)),
    ],
    field_map={"term": 0, "expression_item": 1},
    non_semantic_fields=frozenset([]),
)


Arglist.__grammar__ = RuleSpec(
    rule_name="arglist",
    class_name="Arglist",
    parent_class_name="GrammarModel",
    kind="sequence",
    items=[
        IrItem(IrRuleRef("expression")),
        IrItem(IrRuleRef("arglist-item"), IrQuantifier(0, IrNone)),
    ],
    field_map={"expression": 0, "arglist_item": 1},
    non_semantic_fields=frozenset([]),
)


Condition.__grammar__ = RuleSpec(
    rule_name="condition",
    class_name="Condition",
    parent_class_name="GrammarModel",
    kind="sequence",
    items=[
        IrItem(IrRuleRef("expression")),
        IrItem(IrRuleRef("relationoperator")),
        IrItem(IrRuleRef("expression")),
    ],
    field_map={"expression": 0, "relationoperator": 1, "expression2": 2},
    non_semantic_fields=frozenset([]),
)


Forinit.__grammar__ = RuleSpec(
    rule_name="forinit",
    class_name="Forinit",
    parent_class_name="GrammarModel",
    kind="alternation",
    items=[IrItem(IrRuleRef("forinit-arm1")), IrItem(IrRuleRef("forinit-arm2"))],
    field_map={},
    non_semantic_fields=frozenset([]),
)


ForinitArm1.__grammar__ = RuleSpec(
    rule_name="forinit-arm1",
    class_name="ForinitArm1",
    parent_class_name="Forinit",
    kind="sequence",
    items=[
        IrItem(IrRuleRef("datatype")),
        IrItem(IrRuleRef("identifier")),
        IrItem(IrRuleRef("ws"), IrQuantifier(0)),
        IrItem(IrLiteral("=")),
        IrItem(IrRuleRef("ws"), IrQuantifier(0)),
        IrItem(IrRuleRef("expression")),
    ],
    field_map={"datatype": 0, "identifier": 1, "ws": 2, "ws2": 4, "expression": 5},
    non_semantic_fields=frozenset(["ws", "ws2"]),
)


ForinitArm2.__grammar__ = RuleSpec(
    rule_name="forinit-arm2",
    class_name="ForinitArm2",
    parent_class_name="Forinit",
    kind="sequence",
    items=[
        IrItem(IrRuleRef("identifier")),
        IrItem(IrRuleRef("ws"), IrQuantifier(0)),
        IrItem(IrLiteral("=")),
        IrItem(IrRuleRef("ws"), IrQuantifier(0)),
        IrItem(IrRuleRef("expression")),
    ],
    field_map={"identifier": 0, "ws": 1, "ws2": 3, "expression": 4},
    non_semantic_fields=frozenset(["ws", "ws2"]),
)


Forupdate.__grammar__ = RuleSpec(
    rule_name="forupdate",
    class_name="Forupdate",
    parent_class_name="GrammarModel",
    kind="sequence",
    items=[
        IrItem(IrRuleRef("identifier")),
        IrItem(IrRuleRef("ws"), IrQuantifier(0)),
        IrItem(IrLiteral("=")),
        IrItem(IrRuleRef("ws"), IrQuantifier(0)),
        IrItem(IrRuleRef("expression")),
    ],
    field_map={"identifier": 0, "ws": 1, "ws2": 3, "expression": 4},
    non_semantic_fields=frozenset(["ws", "ws2"]),
)


Singlelinecomment.__grammar__ = RuleSpec(
    rule_name="singlelinecomment",
    class_name="Singlelinecomment",
    parent_class_name="Statement",
    kind="value_str",
    items=[
        IrItem(IrLiteral("//")),
        IrItem(
            IrCharClass(
                IrRange(IrChr(0), IrChr(9)), IrRange(IrChr(11), IrChr(1114111))
            ),
            IrQuantifier(0, IrNone),
        ),
        IrItem(IrLiteral("\n")),
    ],
    field_map={},
    non_semantic_fields=frozenset([]),
)


Multilinecomment.__grammar__ = RuleSpec(
    rule_name="multilinecomment",
    class_name="Multilinecomment",
    parent_class_name="Statement",
    kind="value_str",
    items=[
        IrItem(IrLiteral("/*")),
        IrItem(
            IrAlternation(
                IrSequence(
                    IrItem(
                        IrCharClass(
                            IrRange(IrChr(0), IrChr(41)),
                            IrRange(IrChr(43), IrChr(1114111)),
                        )
                    )
                ),
                IrSequence(
                    IrItem(IrLiteral("*")),
                    IrItem(
                        IrCharClass(
                            IrRange(IrChr(0), IrChr(46)),
                            IrRange(IrChr(48), IrChr(1114111)),
                        )
                    ),
                ),
            ),
            IrQuantifier(0, IrNone),
        ),
        IrItem(IrLiteral("*/")),
    ],
    field_map={},
    non_semantic_fields=frozenset([]),
)


Term.__grammar__ = RuleSpec(
    rule_name="term",
    class_name="Term",
    parent_class_name="GrammarModel",
    kind="sequence",
    items=[
        IrItem(IrRuleRef("factor")),
        IrItem(IrRuleRef("term-item"), IrQuantifier(0, IrNone)),
    ],
    field_map={"factor": 0, "term_item": 1},
    non_semantic_fields=frozenset([]),
)


Relationoperator.__grammar__ = RuleSpec(
    rule_name="relationoperator",
    class_name="Relationoperator",
    parent_class_name="GrammarModel",
    kind="value_str",
    items=[
        IrItem(
            IrAlternation(
                IrSequence(IrItem(IrLiteral("<="))),
                IrSequence(IrItem(IrLiteral("<"))),
                IrSequence(IrItem(IrLiteral("=="))),
                IrSequence(IrItem(IrLiteral("!="))),
                IrSequence(IrItem(IrLiteral(">="))),
                IrSequence(IrItem(IrLiteral(">"))),
            )
        )
    ],
    field_map={},
    non_semantic_fields=frozenset([]),
)


Number.__grammar__ = RuleSpec(
    rule_name="number",
    class_name="Number",
    parent_class_name="Factor",
    kind="value_str",
    items=[IrItem(IrCharClass(IrRange(IrChr(48), IrChr(57))), IrQuantifier(1, IrNone))],
    field_map={},
    non_semantic_fields=frozenset([]),
)


Unaryterm.__grammar__ = RuleSpec(
    rule_name="unaryterm",
    class_name="Unaryterm",
    parent_class_name="Factor",
    kind="sequence",
    items=[IrItem(IrLiteral("-")), IrItem(IrRuleRef("factor"))],
    field_map={"factor": 1},
    non_semantic_fields=frozenset([]),
)


Funccall.__grammar__ = RuleSpec(
    rule_name="funccall",
    class_name="Funccall",
    parent_class_name="Factor",
    kind="sequence",
    items=[
        IrItem(IrRuleRef("identifier")),
        IrItem(IrLiteral("(")),
        IrItem(IrRuleRef("arglist"), IrQuantifier(0)),
        IrItem(IrLiteral(")")),
    ],
    field_map={"identifier": 0, "arglist": 2},
    non_semantic_fields=frozenset([]),
)


Parenexpression.__grammar__ = RuleSpec(
    rule_name="parenexpression",
    class_name="Parenexpression",
    parent_class_name="Factor",
    kind="sequence",
    items=[
        IrItem(IrLiteral("(")),
        IrItem(IrRuleRef("ws"), IrQuantifier(0)),
        IrItem(IrRuleRef("expression")),
        IrItem(IrRuleRef("ws"), IrQuantifier(0)),
        IrItem(IrLiteral(")")),
    ],
    field_map={"ws": 1, "expression": 2, "ws2": 3},
    non_semantic_fields=frozenset(["ws", "ws2"]),
)


StatementItem.__grammar__ = RuleSpec(
    rule_name="statement-item",
    class_name="StatementItem",
    parent_class_name="GrammarModel",
    kind="sequence",
    items=[
        IrItem(IrLiteral("else{")),
        IrItem(IrRuleRef("statement"), IrQuantifier(0, IrNone)),
        IrItem(IrLiteral("}")),
    ],
    field_map={"statement": 1},
    non_semantic_fields=frozenset([]),
)


ExpressionItem.__grammar__ = RuleSpec(
    rule_name="expression-item",
    class_name="ExpressionItem",
    parent_class_name="GrammarModel",
    kind="sequence",
    items=[IrItem(IrCharClass(IrChr(43), IrChr(45))), IrItem(IrRuleRef("term"))],
    field_map={"head": 0, "term": 1},
    non_semantic_fields=frozenset([]),
)


ArglistItem.__grammar__ = RuleSpec(
    rule_name="arglist-item",
    class_name="ArglistItem",
    parent_class_name="GrammarModel",
    kind="sequence",
    items=[
        IrItem(IrLiteral(",")),
        IrItem(IrRuleRef("ws"), IrQuantifier(0)),
        IrItem(IrRuleRef("expression")),
    ],
    field_map={"ws": 1, "expression": 2},
    non_semantic_fields=frozenset(["ws"]),
)


TermItem.__grammar__ = RuleSpec(
    rule_name="term-item",
    class_name="TermItem",
    parent_class_name="GrammarModel",
    kind="sequence",
    items=[IrItem(IrCharClass(IrChr(42), IrChr(47))), IrItem(IrRuleRef("factor"))],
    field_map={"head": 0, "factor": 1},
    non_semantic_fields=frozenset([]),
)
