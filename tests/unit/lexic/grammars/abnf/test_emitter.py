"""AbnfEmitter — ABNF-specific syntax constants + format_quantifier prefix."""

from __future__ import annotations

from lexic.grammars.abnf.emitter import AbnfEmitter
from lexic.grammars.abnf.escapes import ABNF_ESCAPES
from lexic.ir.nodes import IrCharClass, IrItem, IrLiteral, IrRuleRef, Quantifier


def _emitter() -> AbnfEmitter:
    return AbnfEmitter(escapes=ABNF_ESCAPES)


def test_rule_separator_is_equals():
    e = _emitter()
    assert e.rule_separator == "="


def test_alt_separator_is_slash():
    assert _emitter().alt_separator == " / "


def test_format_quantifier_prefix_zero_or_more():
    e = _emitter()
    assert e.format_quantifier(0, None) == "*"
    assert e.format_quantifier(1, None) == "1*"
    assert e.format_quantifier(0, 1) == "*1"
    assert e.format_quantifier(2, 5) == "2*5"
    assert e.format_quantifier(3, 3) == "3"
    assert e.format_quantifier(1, 1) == ""


def test_render_charclass_emits_hex_range():
    e = _emitter()
    out = e.render_charclass("a-z")
    assert out == "%x61-7A"


def test_render_charclass_handles_multi_range():
    e = _emitter()
    out = e.render_charclass("a-zA-Z")
    assert out == "(%x61-7A / %x41-5A)"


def test_quote_uses_double_quotes():
    e = _emitter()
    assert e.quote("hello") == '"hello"'


def test_supports_is_a_classvar_frozenset_not_a_property():
    assert isinstance(AbnfEmitter.supports, frozenset)
    assert "literal" in AbnfEmitter.supports


def test_place_quantifier_prefix_for_abnf():
    e = _emitter()
    assert e.place_quantifier("ALPHA", "1*") == "1*ALPHA"
    assert e.place_quantifier('"hi"', "*5") == '*5"hi"'
    assert e.place_quantifier("X", "") == "X"


def test_emit_item_ruleref_with_quantifier_is_prefix():
    e = _emitter()
    item = IrItem(IrRuleRef("ALPHA"), Quantifier(1, None))
    assert e._emit_item(item) == "1*ALPHA"


def test_emit_item_charclass_with_quantifier_is_prefix():
    e = _emitter()
    item = IrItem(IrCharClass("a-z"), Quantifier(0, None))
    assert e._emit_item(item) == "*%x61-7A"


def test_emit_item_quantified_literal_is_prefix():
    e = _emitter()
    item = IrItem(IrLiteral("-"), Quantifier(0, 1))
    assert e._emit_item(item) == '*1"-"'
