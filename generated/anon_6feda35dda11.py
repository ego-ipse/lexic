"""Generated module: anon_6feda35dda11. Do not edit; regenerated from grammar."""

from __future__ import annotations
from typing import Annotated

from pydantic import StringConstraints

from lexic.base import GrammarModel
from lexic.ir.nodes import (
    IrCharClass,
    IrItem,
    IrRuleRef,
    IrQuantifier,
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
    items=[IrItem(atom=IrRuleRef(value="term"), quantifier=IrQuantifier(min=1, max=1))],
    field_map={"term": 0},
    non_semantic_fields=frozenset([]),
)


Term.__grammar__ = RuleSpec(
    rule_name="term",
    class_name="Term",
    parent_class_name="GrammarModel",
    kind="alternation",
    items=[
        IrItem(atom=IrRuleRef(value="num"), quantifier=IrQuantifier(min=1, max=1)),
        IrItem(atom=IrRuleRef(value="ident"), quantifier=IrQuantifier(min=1, max=1)),
    ],
    field_map={},
    non_semantic_fields=frozenset([]),
)


Num.__grammar__ = RuleSpec(
    rule_name="num",
    class_name="Num",
    parent_class_name="Term",
    kind="value_str",
    items=[
        IrItem(atom=IrCharClass(value="0-9"), quantifier=IrQuantifier(min=1, max=None))
    ],
    field_map={},
    non_semantic_fields=frozenset([]),
)


Ident.__grammar__ = RuleSpec(
    rule_name="ident",
    class_name="Ident",
    parent_class_name="Term",
    kind="value_str",
    items=[
        IrItem(atom=IrCharClass(value="a-z"), quantifier=IrQuantifier(min=1, max=None))
    ],
    field_map={},
    non_semantic_fields=frozenset([]),
)
