"""Generated module: japanese. Do not edit; regenerated from grammar."""

from __future__ import annotations

from typing import Annotated, List

from pydantic import StringConstraints

from lexic.base import GrammarModel
from lexic.ir.nodes import (
    IrCharClass,
    IrItem,
    IrQuantifier,
    IrRuleRef,
)
from lexic.ir.spec import RuleSpec

Pattern = Annotated[str, StringConstraints(pattern=r"^[ぁ-ゟ]$")]

Pattern2 = Annotated[str, StringConstraints(pattern=r"^[ァ-ヿ]$")]

Pattern3 = Annotated[str, StringConstraints(pattern=r"^[、-〾]$")]

Pattern4 = Annotated[str, StringConstraints(pattern=r"^[一-鿿]$")]

Pattern5 = Annotated[str, StringConstraints(pattern=r"^[ \t\n]$")]


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
        IrItem(atom=IrRuleRef("jp-char"), quantifier=IrQuantifier(1, None)),
        IrItem(atom=IrRuleRef("root-item"), quantifier=IrQuantifier(0, None)),
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
        IrItem(atom=IrRuleRef("hiragana"), quantifier=IrQuantifier(1, 1)),
        IrItem(atom=IrRuleRef("katakana"), quantifier=IrQuantifier(1, 1)),
        IrItem(atom=IrRuleRef("punctuation"), quantifier=IrQuantifier(1, 1)),
        IrItem(atom=IrRuleRef("cjk"), quantifier=IrQuantifier(1, 1)),
    ],
    field_map={},
    non_semantic_fields=frozenset([]),
)


Hiragana.__grammar__ = RuleSpec(
    rule_name="hiragana",
    class_name="Hiragana",
    parent_class_name="JpChar",
    kind="value_str",
    items=[IrItem(atom=IrCharClass("ぁ-ゟ"), quantifier=IrQuantifier(1, 1))],
    field_map={},
    non_semantic_fields=frozenset([]),
)


Katakana.__grammar__ = RuleSpec(
    rule_name="katakana",
    class_name="Katakana",
    parent_class_name="JpChar",
    kind="value_str",
    items=[IrItem(atom=IrCharClass("ァ-ヿ"), quantifier=IrQuantifier(1, 1))],
    field_map={},
    non_semantic_fields=frozenset([]),
)


Punctuation.__grammar__ = RuleSpec(
    rule_name="punctuation",
    class_name="Punctuation",
    parent_class_name="JpChar",
    kind="value_str",
    items=[IrItem(atom=IrCharClass("、-〾"), quantifier=IrQuantifier(1, 1))],
    field_map={},
    non_semantic_fields=frozenset([]),
)


Cjk.__grammar__ = RuleSpec(
    rule_name="cjk",
    class_name="Cjk",
    parent_class_name="JpChar",
    kind="value_str",
    items=[IrItem(atom=IrCharClass("一-鿿"), quantifier=IrQuantifier(1, 1))],
    field_map={},
    non_semantic_fields=frozenset([]),
)


RootItem.__grammar__ = RuleSpec(
    rule_name="root-item",
    class_name="RootItem",
    parent_class_name="GrammarModel",
    kind="sequence",
    items=[
        IrItem(atom=IrCharClass(" \\t\\n"), quantifier=IrQuantifier(1, 1)),
        IrItem(atom=IrRuleRef("jp-char"), quantifier=IrQuantifier(1, None)),
    ],
    field_map={"head": 0, "jp_char": 1},
    non_semantic_fields=frozenset([]),
)
