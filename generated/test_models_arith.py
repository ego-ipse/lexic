"""Generated module: test_models_arith. Do not edit; regenerated from grammar."""

from __future__ import annotations

from typing import Annotated, List, Optional

from pydantic import StringConstraints

from lexic.base import GrammarModel
from lexic.ir.base import IrNone
from lexic.ir.nodes import (
    IrCharClass,
    IrChr,
    IrItem,
    IrLiteral,
    IrQuantifier,
    IrRange,
    IrRuleRef,
)
from lexic.ir.spec import RuleSpec

Lower = Annotated[str, StringConstraints(pattern=r"^[a-z]$")]

Pattern = Annotated[str, StringConstraints(pattern=r"^[a-z0-9_]*$")]

Digit = Annotated[str, StringConstraints(pattern=r"^[0-9]+$")]

Pattern2 = Annotated[str, StringConstraints(pattern=r"^[ \x09\x0a]*$")]

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
    rule_name=IrRuleRef("root"),
    class_name="Root",
    parent_class_name="GrammarModel",
    kind="sequence",
    items=[IrItem(IrRuleRef("root-item"), IrQuantifier(1, IrNone))],
    field_map={"root_item": 0},
    non_semantic_fields=frozenset([]),
)


Expr.__grammar__ = RuleSpec(
    rule_name=IrRuleRef("expr"),
    class_name="Expr",
    parent_class_name="GrammarModel",
    kind="sequence",
    items=[
        IrItem(IrRuleRef("term"), IrQuantifier(1, 1)),
        IrItem(IrRuleRef("expr-item"), IrQuantifier(0, IrNone)),
    ],
    field_map={"term": 0, "expr_item": 1},
    non_semantic_fields=frozenset([]),
)


Term.__grammar__ = RuleSpec(
    rule_name=IrRuleRef("term"),
    class_name="Term",
    parent_class_name="GrammarModel",
    kind="alternation",
    items=[
        IrItem(IrRuleRef("ident"), IrQuantifier(1, 1)),
        IrItem(IrRuleRef("num"), IrQuantifier(1, 1)),
        IrItem(IrRuleRef("term-arm3"), IrQuantifier(1, 1)),
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
        IrItem(IrLiteral("("), IrQuantifier(1, 1)),
        IrItem(IrRuleRef("ws"), IrQuantifier(0, 1)),
        IrItem(IrRuleRef("expr"), IrQuantifier(1, 1)),
        IrItem(IrLiteral(")"), IrQuantifier(1, 1)),
        IrItem(IrRuleRef("ws"), IrQuantifier(0, 1)),
    ],
    field_map={"ws": 1, "expr": 2, "ws2": 4},
    non_semantic_fields=frozenset(["ws", "ws2"]),
)


Ident.__grammar__ = RuleSpec(
    rule_name=IrRuleRef("ident"),
    class_name="Ident",
    parent_class_name="Term",
    kind="sequence",
    items=[
        IrItem(IrCharClass(IrRange(IrChr(97), IrChr(122))), IrQuantifier(1, 1)),
        IrItem(
            IrCharClass(
                IrRange(IrChr(97), IrChr(122)), IrRange(IrChr(48), IrChr(57)), IrChr(95)
            ),
            IrQuantifier(0, IrNone),
        ),
        IrItem(IrRuleRef("ws"), IrQuantifier(0, 1)),
    ],
    field_map={"lower": 0, "head": 1, "ws": 2},
    non_semantic_fields=frozenset(["ws"]),
)


Num.__grammar__ = RuleSpec(
    rule_name=IrRuleRef("num"),
    class_name="Num",
    parent_class_name="Term",
    kind="sequence",
    items=[
        IrItem(IrCharClass(IrRange(IrChr(48), IrChr(57))), IrQuantifier(1, IrNone)),
        IrItem(IrRuleRef("ws"), IrQuantifier(0, 1)),
    ],
    field_map={"digit": 0, "ws": 1},
    non_semantic_fields=frozenset(["ws"]),
)


Ws.__grammar__ = RuleSpec(
    rule_name=IrRuleRef("ws"),
    class_name="Ws",
    parent_class_name="GrammarModel",
    kind="value_str",
    items=[
        IrItem(IrCharClass(IrChr(32), IrChr(9), IrChr(10)), IrQuantifier(0, IrNone))
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
        IrItem(IrRuleRef("expr"), IrQuantifier(1, 1)),
        IrItem(IrLiteral("="), IrQuantifier(1, 1)),
        IrItem(IrRuleRef("ws"), IrQuantifier(0, 1)),
        IrItem(IrRuleRef("term"), IrQuantifier(1, 1)),
        IrItem(IrLiteral("\n"), IrQuantifier(1, 1)),
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
        IrItem(
            IrCharClass(IrChr(45), IrChr(43), IrChr(42), IrChr(47)), IrQuantifier(1, 1)
        ),
        IrItem(IrRuleRef("term"), IrQuantifier(1, 1)),
    ],
    field_map={"head": 0, "term": 1},
    non_semantic_fields=frozenset([]),
)
