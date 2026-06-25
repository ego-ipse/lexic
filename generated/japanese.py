"""Generated module: japanese. Do not edit; regenerated from grammar."""

from __future__ import annotations

from typing import Annotated, List

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

Pattern = Annotated[str, StringConstraints(pattern=r"^[ぁ-ゟ]$")]

Pattern2 = Annotated[str, StringConstraints(pattern=r"^[ァ-ヿ]$")]

Pattern3 = Annotated[str, StringConstraints(pattern=r"^[、-〾]$")]

Pattern4 = Annotated[str, StringConstraints(pattern=r"^[一-鿿]$")]

Pattern5 = Annotated[str, StringConstraints(pattern=r"^[ \x09\x0a]$")]


class Root(GrammarModel):
    jp_char: List[JpChar]
    root_item: List[RootItem]


class JpChar(GrammarModel):
    pass


class Hiragana(JpChar):
    value: Pattern


class Katakana(JpChar):
    value: Pattern2


class Punctuation(JpChar):
    value: Pattern3


class Cjk(JpChar):
    value: Pattern4


class RootItem(GrammarModel):
    head: Pattern5
    jp_char: List[JpChar]


Root.__grammar__ = RuleSpec(
    rule_name="root",
    class_name="Root",
    parent_class_name="GrammarModel",
    kind="sequence",
    items=[
        IrItem(IrRuleRef("jp-char"), IrQuantifier(1, IrNone)),
        IrItem(IrRuleRef("root-item"), IrQuantifier(0, IrNone)),
    ],
    field_map={"jp_char": 0, "root_item": 1},
    non_semantic_fields=frozenset([]),
)


JpChar.__grammar__ = RuleSpec(
    rule_name="jp-char",
    class_name="JpChar",
    parent_class_name="GrammarModel",
    kind="alternation",
    items=[
        IrItem(IrRuleRef("hiragana"), IrQuantifier(1, 1)),
        IrItem(IrRuleRef("katakana"), IrQuantifier(1, 1)),
        IrItem(IrRuleRef("punctuation"), IrQuantifier(1, 1)),
        IrItem(IrRuleRef("cjk"), IrQuantifier(1, 1)),
    ],
    field_map={},
    non_semantic_fields=frozenset([]),
)


Hiragana.__grammar__ = RuleSpec(
    rule_name="hiragana",
    class_name="Hiragana",
    parent_class_name="JpChar",
    kind="value_str",
    items=[
        IrItem(IrCharClass(IrRange(IrChr(12353), IrChr(12447))), IrQuantifier(1, 1))
    ],
    field_map={},
    non_semantic_fields=frozenset([]),
)


Katakana.__grammar__ = RuleSpec(
    rule_name="katakana",
    class_name="Katakana",
    parent_class_name="JpChar",
    kind="value_str",
    items=[
        IrItem(IrCharClass(IrRange(IrChr(12449), IrChr(12543))), IrQuantifier(1, 1))
    ],
    field_map={},
    non_semantic_fields=frozenset([]),
)


Punctuation.__grammar__ = RuleSpec(
    rule_name="punctuation",
    class_name="Punctuation",
    parent_class_name="JpChar",
    kind="value_str",
    items=[
        IrItem(IrCharClass(IrRange(IrChr(12289), IrChr(12350))), IrQuantifier(1, 1))
    ],
    field_map={},
    non_semantic_fields=frozenset([]),
)


Cjk.__grammar__ = RuleSpec(
    rule_name="cjk",
    class_name="Cjk",
    parent_class_name="JpChar",
    kind="value_str",
    items=[
        IrItem(IrCharClass(IrRange(IrChr(19968), IrChr(40959))), IrQuantifier(1, 1))
    ],
    field_map={},
    non_semantic_fields=frozenset([]),
)


RootItem.__grammar__ = RuleSpec(
    rule_name="root-item",
    class_name="RootItem",
    parent_class_name="GrammarModel",
    kind="sequence",
    items=[
        IrItem(IrCharClass(IrChr(32), IrChr(9), IrChr(10)), IrQuantifier(1, 1)),
        IrItem(IrRuleRef("jp-char"), IrQuantifier(1, IrNone)),
    ],
    field_map={"head": 0, "jp_char": 1},
    non_semantic_fields=frozenset([]),
)
