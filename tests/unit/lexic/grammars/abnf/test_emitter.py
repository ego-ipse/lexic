"""AbnfEmitter — ABNF-specific syntax constants + format_quantifier prefix."""

from __future__ import annotations

from lexic.grammars.abnf.emitter import AbnfEmitter
from lexic.grammars.abnf.escapes import ABNF_ESCAPES
from lexic.ir import CharClassAtom, QuantifiedLiteralAtom, RuleRefAtom


def _emitter() -> AbnfEmitter:
    return AbnfEmitter(escapes=ABNF_ESCAPES)


def test_rule_separator_is_equals():
    """ABNF rule separator is '='"""
    e = _emitter()
    assert e.rule_separator == "="


def test_alt_separator_is_slash():
    """ABNF alt separator is ' / '"""
    assert _emitter().alt_separator == " / "


def test_format_quantifier_prefix_zero_or_more():
    """ABNF `*body` for zero-or-more — but the emitter's interface expects suffix.
    For Phase C, format_quantifier returns the *prefix-style* token; the
    emit algorithm rearranges placement at render-atom time.
    """
    e = _emitter()
    # We adopt prefix-quantifier semantics by returning a marker the algorithm
    # interprets. See AbnfEmitter.format_quantifier for details.
    assert e.format_quantifier(0, None) == "*"
    assert e.format_quantifier(1, None) == "1*"
    assert e.format_quantifier(0, 1) == "*1"  # zero or one == *1
    assert e.format_quantifier(2, 5) == "2*5"
    assert e.format_quantifier(3, 3) == "3"
    assert e.format_quantifier(1, 1) == ""


def test_render_charclass_emits_hex_range():
    """Canonical POSIX 'a-z' → ABNF `%x61-7A`."""
    e = _emitter()
    out = e.render_charclass("a-z")
    assert out == "%x61-7A"


def test_render_charclass_handles_multi_range():
    """Multiple ranges are joined with ' / '."""
    e = _emitter()
    out = e.render_charclass("a-zA-Z")
    # Two range segments
    assert out == "(%x61-7A / %x41-5A)"


def test_quote_uses_double_quotes():
    """Double quotes are used for string literals."""
    e = _emitter()
    assert e.quote("hello") == '"hello"'


def test_supports_is_a_classvar_frozenset_not_a_property():
    """Decision B: supports is a ClassVar, not @property."""
    # Class-level read returns the frozenset directly, not a property descriptor.
    assert isinstance(AbnfEmitter.supports, frozenset)
    assert "literal" in AbnfEmitter.supports


def test_place_quantifier_prefix_for_abnf():
    """place_quantifier places the quantifier *before* the atom for ABNF."""
    e = _emitter()
    assert e.place_quantifier("ALPHA", "1*") == "1*ALPHA"
    assert e.place_quantifier('"hi"', "*5") == '*5"hi"'
    assert e.place_quantifier("X", "") == "X"  # no quantifier → identity


def test_render_atom_ruleref_with_quantifier_is_prefix():
    """render_atom routes through place_quantifier — quantifier appears before rule name."""
    e = _emitter()
    atom = RuleRefAtom(rule_name="ALPHA", min=1, max=None)
    assert e.render_atom(atom) == "1*ALPHA"


def test_render_atom_charclass_with_quantifier_is_prefix():
    """render_atom routes charclass through place_quantifier — prefix form."""
    e = _emitter()
    atom = CharClassAtom(pattern="a-z", min=0, max=None)
    assert e.render_atom(atom) == "*%x61-7A"


def test_render_atom_quantified_literal_is_prefix():
    """render_atom routes QuantifiedLiteralAtom through place_quantifier — prefix form."""
    e = _emitter()
    atom = QuantifiedLiteralAtom(value="-", min=0, max=1)
    assert e.render_atom(atom) == '*1"-"'
