"""Auto-generated Pydantic models from <string:chess>."""

from __future__ import annotations

from typing import ClassVar, List, Union

from lexic.base import GrammarModel
from lexic.ir import (
    RuleSpec,
    CharClassAtom,
    InlineAlternationAtom,
    InlineRegexAtom,
    LiteralAtom,
    QuantifiedLiteralAtom,
    RuleRefAtom,
)


class Root(GrammarModel):
    """root ::= (see __grammar__)"""

    __grammar__: ClassVar[RuleSpec] = RuleSpec(
        rule_name="root",
        class_name="Root",
        parent_class_name="GrammarModel",
        kind="sequence",
        items=[
            LiteralAtom("1. "),
            RuleRefAtom("move", min=1, max=1),
            LiteralAtom(" "),
            RuleRefAtom("move", min=1, max=1),
            LiteralAtom("\\n"),
            RuleRefAtom("root-item", min=1, max=None),
        ],
        field_map={"move": 1, "move2": 3, "root_item": 5},
    )
    move: Move
    move2: Move
    root_item: List[RootItem]


class Move(GrammarModel):
    """move ::= (see __grammar__)"""

    __grammar__: ClassVar[RuleSpec] = RuleSpec(
        rule_name="move",
        class_name="Move",
        parent_class_name="GrammarModel",
        kind="sequence",
        items=[
            InlineAlternationAtom(["pawn", "nonpawn", "castle"]),
            CharClassAtom("[+#]", min=0, max=1),
        ],
        field_map={"value": 0, "annotation": 1},
    )
    value: Union[Pawn, Nonpawn, Castle]
    annotation: str


class Nonpawn(GrammarModel):
    """nonpawn ::= (see __grammar__)"""

    __grammar__: ClassVar[RuleSpec] = RuleSpec(
        rule_name="nonpawn",
        class_name="Nonpawn",
        parent_class_name="GrammarModel",
        kind="value_str",
        items=[
            CharClassAtom("[NBKQR]", min=1, max=1),
            CharClassAtom("[a-h]", min=0, max=1),
            CharClassAtom("[1-8]", min=0, max=1),
            QuantifiedLiteralAtom("x", min=0, max=1),
            CharClassAtom("[a-h]", min=1, max=1),
            CharClassAtom("[1-8]", min=1, max=1),
        ],
        field_map={},
    )
    value: str


class Pawn(GrammarModel):
    """pawn ::= (see __grammar__)"""

    __grammar__: ClassVar[RuleSpec] = RuleSpec(
        rule_name="pawn",
        class_name="Pawn",
        parent_class_name="GrammarModel",
        kind="sequence",
        items=[
            InlineRegexAtom("[a-h]x", '[a-h]"x"', min=0, max=1),
            CharClassAtom("[a-h]", min=1, max=1),
            CharClassAtom("[1-8]", min=1, max=1),
            InlineRegexAtom("=[NBKQR]", '"="[NBKQR]', min=0, max=1),
        ],
        field_map={"a_h_x": 0, "a_h": 1, "cc_1_8": 2, "nbkqr": 3},
    )
    a_h_x: str
    a_h: str
    cc_1_8: str
    nbkqr: str


class Castle(GrammarModel):
    """castle ::= (see __grammar__)"""

    __grammar__: ClassVar[RuleSpec] = RuleSpec(
        rule_name="castle",
        class_name="Castle",
        parent_class_name="GrammarModel",
        kind="value_str",
        items=[LiteralAtom("O-O"), QuantifiedLiteralAtom("-O", min=0, max=1)],
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
            CharClassAtom("[1-9]", min=1, max=1),
            CharClassAtom("[0-9]", min=0, max=1),
            LiteralAtom(". "),
            RuleRefAtom("move", min=1, max=1),
            LiteralAtom(" "),
            RuleRefAtom("move", min=1, max=1),
            LiteralAtom("\\n"),
        ],
        field_map={"digit": 0, "digit2": 1, "move": 3, "move2": 5},
    )
    digit: str
    digit2: str
    move: Move
    move2: Move


# Resolve forward references
_ns = {k: v for k, v in globals().items() if isinstance(v, type)}
Root.model_rebuild(_types_namespace=_ns)
Move.model_rebuild(_types_namespace=_ns)
Nonpawn.model_rebuild(_types_namespace=_ns)
Pawn.model_rebuild(_types_namespace=_ns)
Castle.model_rebuild(_types_namespace=_ns)
RootItem.model_rebuild(_types_namespace=_ns)
