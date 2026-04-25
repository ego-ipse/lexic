"""Auto-generated Pydantic models from <string:anon_cec7bda1a4a6>."""

from __future__ import annotations

from typing import ClassVar

from lexic.base import GrammarModel
from lexic.ir import RuleSpec, LiteralAtom


class Root(GrammarModel):
    """root ::= (see __grammar__)"""

    __grammar__: ClassVar[RuleSpec] = RuleSpec(
        rule_name="root",
        class_name="Root",
        parent_class_name="GrammarModel",
        kind="value_str",
        items=[LiteralAtom("a")],
        field_map={},
    )
    value: str


# Resolve forward references
_ns = {k: v for k, v in globals().items() if isinstance(v, type)}
Root.model_rebuild(_types_namespace=_ns)
