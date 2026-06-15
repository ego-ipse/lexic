"""Generated module: anon_714657e37009. Do not edit; regenerated from grammar."""

from __future__ import annotations

from typing import Annotated

from pydantic import StringConstraints

from lexic.base import GrammarModel
from lexic.ir.base import IrNone, IrStr
from lexic.ir.nodes import (
    IrCharClass,
    IrItem,
    IrQuantifier,
    IrRange,
    IrRuleRef,
)
from lexic.ir.spec import RuleSpec

Pattern = Annotated[str, StringConstraints(pattern=r"^[-+*/]$")]

Digit = Annotated[str, StringConstraints(pattern=r"^[0-9]+$")]


class Root(GrammarModel):
    expr: Expr


class Expr(GrammarModel):
    term: Term
    op: Op
    term2: Term


class Term(GrammarModel):
    num: Num


class Op(GrammarModel):
    value: Pattern


class Num(GrammarModel):
    value: Digit


Root.__grammar__ = RuleSpec(
    rule_name="root",
    class_name="Root",
    parent_class_name="GrammarModel",
    kind="sequence",
    items=[IrItem(IrRuleRef("expr"), IrQuantifier(1, 1))],
    field_map={"expr": 0},
    non_semantic_fields=frozenset([]),
)


Expr.__grammar__ = RuleSpec(
    rule_name="expr",
    class_name="Expr",
    parent_class_name="GrammarModel",
    kind="sequence",
    items=[
        IrItem(IrRuleRef("term"), IrQuantifier(1, 1)),
        IrItem(IrRuleRef("op"), IrQuantifier(1, 1)),
        IrItem(IrRuleRef("term"), IrQuantifier(1, 1)),
    ],
    field_map={"term": 0, "op": 1, "term2": 2},
    non_semantic_fields=frozenset([]),
)


Term.__grammar__ = RuleSpec(
    rule_name="term",
    class_name="Term",
    parent_class_name="GrammarModel",
    kind="sequence",
    items=[IrItem(IrRuleRef("num"), IrQuantifier(1, 1))],
    field_map={"num": 0},
    non_semantic_fields=frozenset([]),
)


Op.__grammar__ = RuleSpec(
    rule_name="op",
    class_name="Op",
    parent_class_name="GrammarModel",
    kind="value_str",
    items=[IrItem(IrCharClass(IrStr("-+*/")), IrQuantifier(1, 1))],
    field_map={},
    non_semantic_fields=frozenset([]),
)


Num.__grammar__ = RuleSpec(
    rule_name="num",
    class_name="Num",
    parent_class_name="GrammarModel",
    kind="value_str",
    items=[IrItem(IrCharClass(IrRange("0", "9")), IrQuantifier(1, IrNone))],
    field_map={},
    non_semantic_fields=frozenset([]),
)
