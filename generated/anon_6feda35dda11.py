"""Generated module: anon_6feda35dda11. Do not edit; regenerated from grammar."""

from __future__ import annotations

from typing import Annotated

from pydantic import StringConstraints

from lexic.base import GrammarModel
from lexic.ir.base import IrNone
from lexic.ir.nodes import (
    IrCharClass,
    IrChr,
    IrItem,
    IrQuantifier,
    IrRange,
    IrRuleRef,
)
from lexic.ir.spec import RuleSpec

Digit = Annotated[str, StringConstraints(pattern=r"^[0-9]+$")]

Lower = Annotated[str, StringConstraints(pattern=r"^[a-z]+$")]


class Root(GrammarModel):
    term: Term


class Term(GrammarModel):
    pass


class Num(Term):
    value: Digit


class Ident(Term):
    value: Lower


Root.__grammar__ = RuleSpec(
    rule_name="root",
    class_name="Root",
    parent_class_name="GrammarModel",
    kind="sequence",
    items=[IrItem(IrRuleRef("term"))],
    field_map={"term": 0},
    non_semantic_fields=frozenset([]),
)


Term.__grammar__ = RuleSpec(
    rule_name="term",
    class_name="Term",
    parent_class_name="GrammarModel",
    kind="alternation",
    items=[IrItem(IrRuleRef("num")), IrItem(IrRuleRef("ident"))],
    field_map={},
    non_semantic_fields=frozenset([]),
)


Num.__grammar__ = RuleSpec(
    rule_name="num",
    class_name="Num",
    parent_class_name="Term",
    kind="value_str",
    items=[IrItem(IrCharClass(IrRange(IrChr(48), IrChr(57))), IrQuantifier(1, IrNone))],
    field_map={},
    non_semantic_fields=frozenset([]),
)


Ident.__grammar__ = RuleSpec(
    rule_name="ident",
    class_name="Ident",
    parent_class_name="Term",
    kind="value_str",
    items=[
        IrItem(IrCharClass(IrRange(IrChr(97), IrChr(122))), IrQuantifier(1, IrNone))
    ],
    field_map={},
    non_semantic_fields=frozenset([]),
)
