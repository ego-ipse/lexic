"""Shared IrItem-based fixture helpers for the unit test suite."""

from __future__ import annotations

from typing import Iterable, Literal

from lexic.ir.base import IrNone, IrSeq
from lexic.ir.nodes import (
    IrAlternation,
    IrAst,
    IrCharClass,
    IrChr,
    IrItem,
    IrLiteral,
    IrQuantifier,
    IrRange,
    IrRule,
    IrRuleRef,
    IrSequence,
)
from lexic.ir.spec import RuleSpec

REQ = IrQuantifier(1, 1)
OPT = IrQuantifier(0, 1)
PLUS = IrQuantifier(1, IrNone)

# RFC 8259 rule names, in JSON_GRAMMAR's declaration order.
JSON_RULE_NAMES: tuple[str, ...] = (
    "JSON-text",
    "begin-array",
    "begin-object",
    "end-array",
    "end-object",
    "name-separator",
    "value-separator",
    "ws",
    "value",
    "false",
    "null",
    "true",
    "object",
    "member",
    "array",
    "number",
    "decimal-point",
    "digit1-9",
    "e",
    "exp",
    "frac",
    "int",
    "minus",
    "plus",
    "zero",
    "digit",
    "string",
    "char",
    "escape",
    "quotation-mark",
    "unescaped",
    "hexdig",
)

Kind = Literal["sequence", "alternation", "value_str"]


def item(atom, q: IrQuantifier = REQ) -> IrItem:
    """Create an IrItem with the given atom and quantifier."""
    return IrItem(atom=atom, quantifier=q)


def digit_grammar() -> IrAst:
    """digit = [0-9] ; single-rule, single-arm, single-item grammar."""
    return IrAst(
        rules=IrSeq(
            IrRule(
                "digit",
                IrAlternation(
                    IrSequence(IrItem(IrCharClass(IrRange(IrChr("0"), IrChr("9")))))
                ),
            ),
        ),
        start="digit",
    )


def letter_word_rules() -> tuple[IrRule, IrRule]:
    """The shared rule pair: word = letter letter ; letter = [a-z].

    :returns: ``(word, letter)``.
    """
    letter = IrRule(
        "letter",
        IrAlternation(IrSequence(IrItem(IrCharClass(IrRange(IrChr("a"), IrChr("z")))))),
    )
    word = IrRule(
        "word",
        IrAlternation(
            IrSequence(IrItem(IrRuleRef("letter")), IrItem(IrRuleRef("letter")))
        ),
    )
    return word, letter


def word_grammar() -> IrAst:
    """word = letter letter ; letter = [a-z]."""
    word, letter = letter_word_rules()
    return IrAst(rules=IrSeq(word, letter), start="word")


def sss_grammar() -> IrAst:
    """Genuinely ambiguous: s = s s / 'a'.

    Over 'aaa' this has exactly 2 derivations (Catalan C_2).
    """
    s_rule = IrRule(
        "s",
        IrAlternation(
            IrSequence(IrItem(IrRuleRef("s")), IrItem(IrRuleRef("s"))),
            IrSequence(IrItem(IrLiteral("a"))),
        ),
    )
    return IrAst(rules=IrSeq(s_rule), start="s")


def spec(
    rule_name: str,
    kind: Kind,
    items: Iterable,
    *,
    field_map: dict[str, int] | None = None,
    non_semantic_fields: frozenset[str] = frozenset(),
) -> RuleSpec:
    """Create a RuleSpec with the given items."""
    return RuleSpec(
        rule_name=rule_name,
        class_name=rule_name.title().replace("-", ""),
        parent_class_name="GrammarModel",
        kind=kind,
        items=list(items),
        field_map=field_map or {},
        non_semantic_fields=non_semantic_fields,
    )
