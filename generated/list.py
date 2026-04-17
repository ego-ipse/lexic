"""Auto-generated Pydantic models from /home/mika/projects/vyx_2/resources/ground_truth/list.gbnf."""

from __future__ import annotations

from typing import ClassVar, List

from base import GrammarModel
from codegen.ir import RuleSpec, CharClassAtom, LiteralAtom, RuleRefAtom


class Root(GrammarModel):
    """root ::= (see __grammar__)"""

    __grammar__: ClassVar[RuleSpec] = RuleSpec(
        rule_name="root",
        class_name="Root",
        parent_class_name="GrammarModel",
        kind="sequence",
        items=[RuleRefAtom("item", min=1, max=None)],
        field_map={"item": 0},
    )
    item: List[Item]


class Item(GrammarModel):
    """item ::= (see __grammar__)"""

    __grammar__: ClassVar[RuleSpec] = RuleSpec(
        rule_name="item",
        class_name="Item",
        parent_class_name="GrammarModel",
        kind="value_str",
        items=[
            LiteralAtom("- "),
            CharClassAtom("[^\\r\\n\\x0b\\x0c\\x85\\u2028\\u2029]", min=1, max=None),
            LiteralAtom("\\n"),
        ],
        field_map={},
    )
    value: str


# Resolve forward references
_ns = {k: v for k, v in globals().items() if isinstance(v, type)}
Root.model_rebuild(_types_namespace=_ns)
Item.model_rebuild(_types_namespace=_ns)
