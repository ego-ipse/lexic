"""GBNF_FLAVOUR mirror parity check."""

from __future__ import annotations

import pytest

from lexic.exceptions import UnsupportedConstructError
from lexic.grammars.flavour import IrFlavour
from lexic.grammars.gbnf import (
    GBNF_ESCAPES,
    GBNF_FLAVOUR,
    GBNF_QUANTIFIERS,
    META_GRAMMAR,
)
from lexic.ir.base import IrNone, IrStr
from lexic.ir.nodes import (
    IrAlternation,
    IrCharClass,
    IrItem,
    IrLiteral,
    IrQuantifier,
    IrRange,
    IrRuleRef,
    IrSequence,
)
from lexic.ir.operators import IrNot
from tests.unit.lexic.conftest import GRAMMAR_AST_TYPES


def test_subclass():
    """GBNF_FLAVOUR is an IrFlavour singleton."""
    assert isinstance(GBNF_FLAVOUR, IrFlavour)


def test_metadata():
    """GBNF_FLAVOUR metadata is stable."""
    assert GBNF_FLAVOUR.name == "gbnf"
    assert GBNF_FLAVOUR.extensions == (".gbnf",)


def test_meta_grammar_identity():
    """GBNF_FLAVOUR.meta_grammar is a non-empty string."""
    assert isinstance(GBNF_FLAVOUR.meta_grammar, str)
    assert len(GBNF_FLAVOUR.meta_grammar) > 0


def test_parse_quantifier_parity():
    """parse_quantifier produces expected IrQuantifier values."""
    cases = ["", "?", "+", "*", "{2,5}", "{0,15}", "{3}"]
    expected = [
        IrQuantifier(1, 1),
        IrQuantifier(0, 1),
        IrQuantifier(1, IrNone),
        IrQuantifier(0, IrNone),
        IrQuantifier(2, 5),
        IrQuantifier(0, 15),
        IrQuantifier(3, 3),
    ]
    for s, exp in zip(cases, expected):
        assert GBNF_FLAVOUR.parse_quantifier(s) == exp


def test_parse_charclass_parity():
    """parse_charclass handles negation and escapes."""
    cases = ["[a-z]", "[0-9]", "[^abc]", r'[\\"]']
    expected = [("a-z", False), ("0-9", False), ("abc", True), (r'\\"', False)]
    for s, exp in zip(cases, expected):
        assert GBNF_FLAVOUR.parse_charclass(s) == exp


def test_line_comment_token():
    """GBNF_FLAVOUR line comment marker is '#'."""
    assert GBNF_FLAVOUR.line_comment == "#"


def test_decode_newline():
    """Backslash-n decodes to newline."""
    assert GBNF_ESCAPES.decode(r"\n") == "\n"


def test_decode_tab():
    """Backslash-t decodes to tab."""
    assert GBNF_ESCAPES.decode(r"\t") == "\t"


def test_decode_carriage_return():
    """Backslash-r decodes to carriage return."""
    assert GBNF_ESCAPES.decode(r"\r") == "\r"


def test_decode_backslash():
    """Double backslash decodes to single backslash."""
    assert GBNF_ESCAPES.decode(r"\\") == "\\"


def test_decode_quote():
    """Escaped quote decodes to double quote."""
    assert GBNF_ESCAPES.decode(r"\"") == '"'


def test_decode_plain_text():
    """Plain text decodes unchanged."""
    assert GBNF_ESCAPES.decode("abc") == "abc"


def test_encode_newline():
    """Newline encodes to backslash-n."""
    assert GBNF_ESCAPES.encode("\n") == r"\n"


def test_encode_tab():
    """Tab encodes to backslash-t."""
    assert GBNF_ESCAPES.encode("\t") == r"\t"


def test_encode_backslash():
    """Backslash encodes to double backslash."""
    assert GBNF_ESCAPES.encode("\\") == r"\\"


def test_encode_quote():
    """Double quote encodes to escaped quote."""
    assert GBNF_ESCAPES.encode('"') == r"\""


def test_encode_plain_text():
    """Plain text encodes unchanged."""
    assert GBNF_ESCAPES.encode("abc") == "abc"


def test_round_trip():
    """encode(decode(x)) == x for a variety of characters."""
    escapes = GBNF_ESCAPES
    for raw in ["\n", "\t", "\\", '"', "hello", "\x00"]:
        assert escapes.decode(escapes.encode(raw)) == raw


def test_meta_grammar_is_non_empty_string():
    """META_GRAMMAR is a non-empty string."""
    assert isinstance(META_GRAMMAR, str)
    assert len(META_GRAMMAR) > 0


def test_gbnf_emitter_iremit_default_unreachable():
    """Every IR-AST node type has an explicit action — IrEmit default never fires.

    If any type is missing an action, the emitter would fall through to its
    IrEmit default body and silently emit ``str(n)`` instead of raising.
    This test locks that the default is structurally unreachable for GBNF.
    """
    registered = set(GBNF_FLAVOUR.actions.keys())
    missing = GRAMMAR_AST_TYPES - registered
    assert not missing, f"GBNF_FLAVOUR missing explicit actions for: {missing}"


# ── GBNF_QUANTIFIERS ──────────────────────────────────────────────────


def test_gbnf_quantifiers_maps_four_bounds_to_symbols():
    """GBNF_QUANTIFIERS maps the four canonical quantifier bounds to their symbols."""
    assert GBNF_QUANTIFIERS[IrQuantifier(1, 1)] == ""
    assert GBNF_QUANTIFIERS[IrQuantifier(0, 1)] == "?"
    assert GBNF_QUANTIFIERS[IrQuantifier(0, IrNone)] == "*"
    assert GBNF_QUANTIFIERS[IrQuantifier(1, IrNone)] == "+"


def test_gbnf_quantifiers_miss_raises_unsupported():
    """GBNF_FLAVOUR.apply on an out-of-table quantifier raises UnsupportedConstructError."""
    with pytest.raises(UnsupportedConstructError):
        GBNF_FLAVOUR.apply(IrQuantifier(2, 5))


def test_gbnf_quantifier_hit_question_mark():
    """GBNF_FLAVOUR.apply(IrQuantifier(0, 1)) emits '?'."""
    assert GBNF_FLAVOUR.apply(IrQuantifier(0, 1)) == "?"


# ── Declarative literal emission ──────────────────────────────────────


def test_gbnf_literal_emission_escapes_and_quotes():
    """GBNF_FLAVOUR.apply on a literal escapes special chars and wraps in quotes."""
    result = GBNF_FLAVOUR.apply(IrLiteral('a"b'))
    assert result == '"a\\"b"'


# ── Item parenthesisation ─────────────────────────────────────────────


def test_gbnf_item_alternation_atom_is_parenthesised():
    """An IrItem whose atom is an IrAlternation renders wrapped in parens."""
    item = IrItem(atom=IrAlternation(IrSequence(IrItem(atom=IrLiteral("x")))))
    assert GBNF_FLAVOUR.apply(item) == '("x")'


def test_gbnf_item_ruleref_atom_is_not_parenthesised():
    """An IrItem whose atom is an IrRuleRef renders without wrapping parens."""
    item = IrItem(atom=IrRuleRef("foo"))
    assert GBNF_FLAVOUR.apply(item) == "foo"


# ── IrNot / negated charclass emission ───────────────────────────────


def test_gbnf_not_charclass_renders_negated_bracket():
    """GBNF_FLAVOUR.apply(IrNot(IrCharClass(IrRange("a", "z")))) renders "[^a-z]"."""
    assert GBNF_FLAVOUR.apply(IrNot(IrCharClass(IrRange("a", "z")))) == "[^a-z]"


def test_gbnf_charclass_renders_without_negation_mark():
    """Plain IrCharClass renders without a caret — no mark leakage from IrNot."""
    assert GBNF_FLAVOUR.apply(IrCharClass(IrRange("a", "z"))) == "[a-z]"


def test_gbnf_not_non_charclass_raises_unsupported():
    """IrNot wrapping a non-IrCharClass node raises UnsupportedConstructError.

    The error message names the dispatcher and the rejected node type.
    """
    with pytest.raises(UnsupportedConstructError, match="cannot negate 'IrRuleRef'"):
        GBNF_FLAVOUR.apply(IrNot(IrRuleRef("ws")))


# ── Structured IrCharClass emission ──────────────────────────────────


def test_gbnf_charclass_range_emits_bracket_with_dash():
    """A range-only class emits ``[lo-hi]``."""
    assert GBNF_FLAVOUR.apply(IrCharClass(IrRange("0", "9"))) == "[0-9]"


def test_gbnf_charclass_run_emits_bracket_with_chars():
    """A run-only class emits ``[chars]``."""
    assert GBNF_FLAVOUR.apply(IrCharClass(IrStr("abc"))) == "[abc]"


def test_gbnf_charclass_mixed_emits_run_then_range():
    """A mixed run + range class emits ``[runchars lo-hi]``."""
    assert (
        GBNF_FLAVOUR.apply(IrCharClass(IrStr("abc"), IrRange("0", "9"))) == "[abc0-9]"
    )
