"""Auto-generated Pydantic models from <string:anon_68b436a25256>."""

from __future__ import annotations

from abc import ABC
from typing import ClassVar, List

from lexic.base import GrammarModel
from lexic.ir import AlternationAtom, CharClassAtom, RuleRefAtom, RuleSpec


class Root(GrammarModel):
    """root ::= (see __grammar__)"""

    __grammar__: ClassVar[RuleSpec] = RuleSpec(
        rule_name="root",
        class_name="Root",
        parent_class_name="GrammarModel",
        kind="sequence",
        items=[
            RuleRefAtom("jp-char", min=1, max=None),
            RuleRefAtom("root-item", min=0, max=None),
        ],
        field_map={"jp_char": 0, "root_item": 1},
    )
    jp_char: List[JpChar]
    root_item: List[RootItem]


class JpChar(GrammarModel, ABC):
    """jp-char ::= (see __grammar__)"""

    __grammar__: ClassVar[RuleSpec] = RuleSpec(
        rule_name="jp-char",
        class_name="JpChar",
        parent_class_name="GrammarModel",
        kind="alternation",
        items=[AlternationAtom(["hiragana", "katakana", "punctuation", "cjk"])],
        field_map={},
    )
    pass


class Hiragana(JpChar):
    """hiragana ::= (see __grammar__)"""

    __grammar__: ClassVar[RuleSpec] = RuleSpec(
        rule_name="hiragana",
        class_name="Hiragana",
        parent_class_name="JpChar",
        kind="value_str",
        items=[CharClassAtom("[ぁ-ゟ]", min=1, max=1)],
        field_map={},
    )
    value: str


class Katakana(JpChar):
    """katakana ::= (see __grammar__)"""

    __grammar__: ClassVar[RuleSpec] = RuleSpec(
        rule_name="katakana",
        class_name="Katakana",
        parent_class_name="JpChar",
        kind="value_str",
        items=[CharClassAtom("[ァ-ヿ]", min=1, max=1)],
        field_map={},
    )
    value: str


class Punctuation(JpChar):
    """punctuation ::= (see __grammar__)"""

    __grammar__: ClassVar[RuleSpec] = RuleSpec(
        rule_name="punctuation",
        class_name="Punctuation",
        parent_class_name="JpChar",
        kind="value_str",
        items=[CharClassAtom("[、-〾]", min=1, max=1)],
        field_map={},
    )
    value: str


class Cjk(JpChar):
    """cjk ::= (see __grammar__)"""

    __grammar__: ClassVar[RuleSpec] = RuleSpec(
        rule_name="cjk",
        class_name="Cjk",
        parent_class_name="JpChar",
        kind="value_str",
        items=[CharClassAtom("[一-鿿]", min=1, max=1)],
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
            CharClassAtom("[ \\t\\n]", min=1, max=1),
            RuleRefAtom("jp-char", min=1, max=None),
        ],
        field_map={"tn": 0, "jp_char": 1},
    )
    tn: str
    jp_char: List[JpChar]


# Resolve forward references
_ns = {k: v for k, v in globals().items() if isinstance(v, type)}
Root.model_rebuild(_types_namespace=_ns)
JpChar.model_rebuild(_types_namespace=_ns)
Hiragana.model_rebuild(_types_namespace=_ns)
Katakana.model_rebuild(_types_namespace=_ns)
Punctuation.model_rebuild(_types_namespace=_ns)
Cjk.model_rebuild(_types_namespace=_ns)
RootItem.model_rebuild(_types_namespace=_ns)
