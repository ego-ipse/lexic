"""Shared IrItem-based fixture helpers for the unit test suite."""

from __future__ import annotations

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
from lexic.parsing.earley.normalize import SYNTHETIC_PREFIX

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


def malformed_synthetic_rule(name: str = f"{SYNTHETIC_PREFIX}bad") -> IrRule:
    """A synthetic-named rule whose arm is not a single item — not a valid
    charset-collapse shape. Probes the ``unit_leaves``/``PositionalFold.run_ok``
    "not this shape at all" path.
    """
    return IrRule(
        name, IrAlternation(IrSequence(IrItem(IrLiteral("a")), IrItem(IrLiteral("b"))))
    )


def nested_synthetic_grammar() -> IrAst:
    """``__outer`` -> ``__inner`` -> ``digit`` / bare ``'x'``.

    A synthetic charset rule hopping through another synthetic rule, so the
    transitive leaf-collection walk (``unit_leaves`` / ``PositionalFold.run_ok``)
    has more than one hop to resolve, and a bare-terminal arm sits alongside
    the ruleref arm.
    """
    digit = IrRule(
        "digit",
        IrAlternation(IrSequence(IrItem(IrCharClass(IrRange(IrChr("0"), IrChr("9")))))),
    )
    inner = IrRule(
        f"{SYNTHETIC_PREFIX}inner",
        IrAlternation(
            IrSequence(IrItem(IrLiteral("x"))),
            IrSequence(IrItem(IrRuleRef("digit"))),
        ),
    )
    outer = IrRule(
        f"{SYNTHETIC_PREFIX}outer",
        IrAlternation(IrSequence(IrItem(IrRuleRef(f"{SYNTHETIC_PREFIX}inner")))),
    )
    return IrAst(rules=IrSeq(outer, inner, digit), start=f"{SYNTHETIC_PREFIX}outer")
