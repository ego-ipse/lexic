"""Generated module: anon_68f70d18447b. Do not edit; regenerated from grammar."""

from __future__ import annotations

from typing import Annotated, Optional

from pydantic import StringConstraints

from lexic.base import GrammarModel
from lexic.ir.nodes import (
    IrCharClass,
    IrItem,
    IrLiteral,
    IrQuantifier,
    IrRuleRef,
)
from lexic.ir.spec import RuleSpec

Pattern = Annotated[str, StringConstraints(pattern=r"^[ \t]*$")]


class Root(GrammarModel):
    ws: Optional[Ws] = None
    value: Value
    ws2: Optional[Ws] = None


class Value(GrammarModel):
    value: str


class Ws(GrammarModel):
    value: Pattern


Root.__grammar__ = RuleSpec(
    rule_name="root",
    class_name="Root",
    parent_class_name="GrammarModel",
    kind="sequence",
    items=[
        IrItem(atom=IrRuleRef(value="ws"), quantifier=IrQuantifier(min=0, max=1)),
        IrItem(atom=IrRuleRef(value="value"), quantifier=IrQuantifier(min=1, max=1)),
        IrItem(atom=IrRuleRef(value="ws"), quantifier=IrQuantifier(min=0, max=1)),
    ],
    field_map={"ws": 0, "value": 1, "ws2": 2},
    non_semantic_fields=frozenset(["ws", "ws2"]),
)


Value.__grammar__ = RuleSpec(
    rule_name="value",
    class_name="Value",
    parent_class_name="GrammarModel",
    kind="value_str",
    items=[IrItem(atom=IrLiteral(value="x"), quantifier=IrQuantifier(min=1, max=1))],
    field_map={},
    non_semantic_fields=frozenset([]),
)


Ws.__grammar__ = RuleSpec(
    rule_name="ws",
    class_name="Ws",
    parent_class_name="GrammarModel",
    kind="value_str",
    items=[
        IrItem(atom=IrCharClass(value=" \\t"), quantifier=IrQuantifier(min=0, max=None))
    ],
    field_map={},
    non_semantic_fields=frozenset([]),
)
