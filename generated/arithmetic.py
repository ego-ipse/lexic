"""Generated module: arithmetic. Do not edit; regenerated from grammar."""

from __future__ import annotations

from typing import Annotated, List, Optional

from pydantic import StringConstraints

from lexic.base import GrammarModel
from lexic.ir.nodes import (
    IrCharClass,
    IrItem,
    IrLiteral,
    IrRuleRef,
    Quantifier,
)
from lexic.ir.spec import RuleSpec

Lower = Annotated[str, StringConstraints(pattern=r"^[a-z]$")]

Pattern = Annotated[str, StringConstraints(pattern=r"^[a-z0-9_]*$")]

Digit = Annotated[str, StringConstraints(pattern=r"^[0-9]+$")]

Pattern2 = Annotated[str, StringConstraints(pattern=r"^[ \t\n]*$")]

Pattern3 = Annotated[str, StringConstraints(pattern=r"^[-+*/]$")]


class Root(GrammarModel):
    root_item: List[RootItem]


class Expr(GrammarModel):
    term: Term
    expr_item: List[ExprItem]


class Term(GrammarModel):
    pass


class TermArm3(Term):
    ws: Optional[Ws] = None
    expr: Expr
    ws2: Optional[Ws] = None


class Ident(Term):
    lower: Lower
    head: Pattern
    ws: Optional[Ws] = None


class Num(Term):
    digit: Digit
    ws: Optional[Ws] = None


class Ws(GrammarModel):
    value: Pattern2


class RootItem(GrammarModel):
    expr: Expr
    ws: Optional[Ws] = None
    term: Term


class ExprItem(GrammarModel):
    head: Pattern3
    term: Term


Root.__grammar__ = RuleSpec(
    rule_name="root",
    class_name="Root",
    parent_class_name="GrammarModel",
    kind="sequence",
    items=[IrItem(IrRuleRef("root-item"), Quantifier(1, None))],
    field_map={"root_item": 0},
    non_semantic_fields=frozenset([]),
)


Expr.__grammar__ = RuleSpec(
    rule_name="expr",
    class_name="Expr",
    parent_class_name="GrammarModel",
    kind="sequence",
    items=[
        IrItem(IrRuleRef("term"), Quantifier(1, 1)),
        IrItem(IrRuleRef("expr-item"), Quantifier(0, None)),
    ],
    field_map={"term": 0, "expr_item": 1},
    non_semantic_fields=frozenset([]),
)


Term.__grammar__ = RuleSpec(
    rule_name="term",
    class_name="Term",
    parent_class_name="GrammarModel",
    kind="alternation",
    items=[
        IrItem(IrRuleRef("ident"), Quantifier(1, 1)),
        IrItem(IrRuleRef("num"), Quantifier(1, 1)),
        IrItem(IrRuleRef("term-arm3"), Quantifier(1, 1)),
    ],
    field_map={},
    non_semantic_fields=frozenset([]),
)


TermArm3.__grammar__ = RuleSpec(
    rule_name="term-arm3",
    class_name="TermArm3",
    parent_class_name="Term",
    kind="sequence",
    items=[
        IrItem(IrLiteral("("), Quantifier(1, 1)),
        IrItem(IrRuleRef("ws"), Quantifier(0, 1)),
        IrItem(IrRuleRef("expr"), Quantifier(1, 1)),
        IrItem(IrLiteral(")"), Quantifier(1, 1)),
        IrItem(IrRuleRef("ws"), Quantifier(0, 1)),
    ],
    field_map={"ws": 1, "expr": 2, "ws2": 4},
    non_semantic_fields=frozenset(["ws", "ws2"]),
)


Ident.__grammar__ = RuleSpec(
    rule_name="ident",
    class_name="Ident",
    parent_class_name="Term",
    kind="sequence",
    items=[
        IrItem(IrCharClass("a-z", negated=False), Quantifier(1, 1)),
        IrItem(IrCharClass("a-z0-9_", negated=False), Quantifier(0, None)),
        IrItem(IrRuleRef("ws"), Quantifier(0, 1)),
    ],
    field_map={"lower": 0, "head": 1, "ws": 2},
    non_semantic_fields=frozenset(["ws"]),
)


Num.__grammar__ = RuleSpec(
    rule_name="num",
    class_name="Num",
    parent_class_name="Term",
    kind="sequence",
    items=[
        IrItem(IrCharClass("0-9", negated=False), Quantifier(1, None)),
        IrItem(IrRuleRef("ws"), Quantifier(0, 1)),
    ],
    field_map={"digit": 0, "ws": 1},
    non_semantic_fields=frozenset(["ws"]),
)


Ws.__grammar__ = RuleSpec(
    rule_name="ws",
    class_name="Ws",
    parent_class_name="GrammarModel",
    kind="value_str",
    items=[IrItem(IrCharClass(" \\t\\n", negated=False), Quantifier(0, None))],
    field_map={},
    non_semantic_fields=frozenset([]),
)


RootItem.__grammar__ = RuleSpec(
    rule_name="root-item",
    class_name="RootItem",
    parent_class_name="GrammarModel",
    kind="sequence",
    items=[
        IrItem(IrRuleRef("expr"), Quantifier(1, 1)),
        IrItem(IrLiteral("="), Quantifier(1, 1)),
        IrItem(IrRuleRef("ws"), Quantifier(0, 1)),
        IrItem(IrRuleRef("term"), Quantifier(1, 1)),
        IrItem(IrLiteral("\n"), Quantifier(1, 1)),
    ],
    field_map={"expr": 0, "ws": 2, "term": 3},
    non_semantic_fields=frozenset(["ws"]),
)


ExprItem.__grammar__ = RuleSpec(
    rule_name="expr-item",
    class_name="ExprItem",
    parent_class_name="GrammarModel",
    kind="sequence",
    items=[
        IrItem(IrCharClass("-+*/", negated=False), Quantifier(1, 1)),
        IrItem(IrRuleRef("term"), Quantifier(1, 1)),
    ],
    field_map={"head": 0, "term": 1},
    non_semantic_fields=frozenset([]),
)
