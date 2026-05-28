"""Generated module: anon_3a6dbf42e5a5. Do not edit; regenerated from grammar."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import StringConstraints

from lexic.base import GrammarModel
from lexic.ir.nodes import (
    IrAlternation,
    IrCharClass,
    IrItem,
    IrLiteral,
    IrQuantifier,
    IrRuleRef,
    IrSequence,
)
from lexic.ir.spec import RuleSpec

Digit = Annotated[str, StringConstraints(pattern=r"^[0-9]+$")]


class Op(GrammarModel):
    value: Literal["+", "-", "*", "/"]


class Expr(GrammarModel):
    num: Num
    op: Op
    num2: Num


class Num(GrammarModel):
    value: Digit


Op.__grammar__ = RuleSpec(
    rule_name="op",
    class_name="Op",
    parent_class_name="GrammarModel",
    kind="value_str",
    items=[
        IrAlternation(
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
    ],
    field_map={},
    non_semantic_fields=frozenset([]),
)


Expr.__grammar__ = RuleSpec(
    rule_name="expr",
    class_name="Expr",
    parent_class_name="GrammarModel",
    kind="sequence",
    items=[
        IrItem(atom=IrRuleRef(value="num"), quantifier=IrQuantifier(min=1, max=1)),
        IrItem(atom=IrRuleRef(value="op"), quantifier=IrQuantifier(min=1, max=1)),
        IrItem(atom=IrRuleRef(value="num"), quantifier=IrQuantifier(min=1, max=1)),
    ],
    field_map={"num": 0, "op": 1, "num2": 2},
    non_semantic_fields=frozenset([]),
)


Num.__grammar__ = RuleSpec(
    rule_name="num",
    class_name="Num",
    parent_class_name="GrammarModel",
    kind="value_str",
    items=[
        IrItem(atom=IrCharClass(value="0-9"), quantifier=IrQuantifier(min=1, max=None))
    ],
    field_map={},
    non_semantic_fields=frozenset([]),
)
