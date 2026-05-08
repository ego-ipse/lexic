"""Auto-generated Pydantic models from <string:arithmetic_b>."""

from __future__ import annotations

from abc import ABC
from typing import ClassVar, List

from lexic.base import GrammarModel
from lexic.ir import AlternationAtom, CharClassAtom, LiteralAtom, RuleRefAtom, RuleSpec


class Root(GrammarModel):
    """root ::= (see __grammar__)"""

    __grammar__: ClassVar[RuleSpec] = RuleSpec(
        rule_name="root",
        class_name="Root",
        parent_class_name="GrammarModel",
        kind="sequence",
        items=[RuleRefAtom("root-item", min=1, max=None)],
        field_map={"root_item": 0},
    )
    root_item: List[RootItem]


class Expr(GrammarModel):
    """expr ::= (see __grammar__)"""

    __grammar__: ClassVar[RuleSpec] = RuleSpec(
        rule_name="expr",
        class_name="Expr",
        parent_class_name="GrammarModel",
        kind="sequence",
        items=[
            RuleRefAtom("term", min=1, max=1),
            RuleRefAtom("expr-item", min=0, max=None),
        ],
        field_map={"term": 0, "expr_item": 1},
    )
    term: Term
    expr_item: List[ExprItem]


class Term(GrammarModel, ABC):
    """term ::= (see __grammar__)"""

    __grammar__: ClassVar[RuleSpec] = RuleSpec(
        rule_name="term",
        class_name="Term",
        parent_class_name="GrammarModel",
        kind="alternation",
        items=[AlternationAtom(["ident", "num", "term-arm3"])],
        field_map={},
    )
    pass


class TermArm3(Term):
    """term-arm3 ::= (see __grammar__)"""

    __grammar__: ClassVar[RuleSpec] = RuleSpec(
        rule_name="term-arm3",
        class_name="TermArm3",
        parent_class_name="Term",
        kind="sequence",
        items=[LiteralAtom("("), RuleRefAtom("expr", min=1, max=1), LiteralAtom(")")],
        field_map={"expr": 1},
    )
    expr: Expr


class Ident(Term):
    """ident ::= (see __grammar__)"""

    __grammar__: ClassVar[RuleSpec] = RuleSpec(
        rule_name="ident",
        class_name="Ident",
        parent_class_name="Term",
        kind="sequence",
        items=[
            CharClassAtom("[a-z]", min=1, max=1),
            CharClassAtom("[a-z0-9_]", min=0, max=None),
            RuleRefAtom("ws", min=1, max=1),
        ],
        field_map={"lower": 0, "a_z0_9": 1, "ws": 2},
    )
    lower: str
    a_z0_9: str
    ws: Ws


class Num(Term):
    """num ::= (see __grammar__)"""

    __grammar__: ClassVar[RuleSpec] = RuleSpec(
        rule_name="num",
        class_name="Num",
        parent_class_name="Term",
        kind="sequence",
        items=[
            CharClassAtom("[0-9]", min=1, max=None),
            RuleRefAtom("ws", min=1, max=1),
        ],
        field_map={"digit": 0, "ws": 1},
    )
    digit: str
    ws: Ws


class Ws(GrammarModel):
    """ws ::= (see __grammar__)"""

    __grammar__: ClassVar[RuleSpec] = RuleSpec(
        rule_name="ws",
        class_name="Ws",
        parent_class_name="GrammarModel",
        kind="value_str",
        items=[CharClassAtom("[ \\t\\n]", min=0, max=None)],
        field_map={},
    )
    value: str


class RootItem(GrammarModel):
    """root-item ::= (see __grammar__)"""

    __grammar__: ClassVar[RuleSpec] = RuleSpec(
        rule_name="root-item",
        class_name="RootItem",
        parent_class_name="GrammarModel",
        kind="sequence",
        items=[
            RuleRefAtom("expr", min=1, max=1),
            LiteralAtom("="),
            RuleRefAtom("term", min=1, max=1),
            LiteralAtom("\\n"),
        ],
        field_map={"expr": 0, "term": 2},
    )
    expr: Expr
    term: Term


class ExprItem(GrammarModel):
    """expr-item ::= (see __grammar__)"""

    __grammar__: ClassVar[RuleSpec] = RuleSpec(
        rule_name="expr-item",
        class_name="ExprItem",
        parent_class_name="GrammarModel",
        kind="sequence",
        items=[
            CharClassAtom("[-+*/]", min=1, max=1),
            RuleRefAtom("term", min=1, max=1),
        ],
        field_map={"cc": 0, "term": 1},
    )
    cc: str
    term: Term


# Resolve forward references
_ns = {k: v for k, v in globals().items() if isinstance(v, type)}
Root.model_rebuild(_types_namespace=_ns)
Expr.model_rebuild(_types_namespace=_ns)
Term.model_rebuild(_types_namespace=_ns)
TermArm3.model_rebuild(_types_namespace=_ns)
Ident.model_rebuild(_types_namespace=_ns)
Num.model_rebuild(_types_namespace=_ns)
Ws.model_rebuild(_types_namespace=_ns)
RootItem.model_rebuild(_types_namespace=_ns)
ExprItem.model_rebuild(_types_namespace=_ns)
