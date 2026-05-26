"""AbnfEmitter — ABNF-specific syntax constants + format_quantifier prefix."""

from __future__ import annotations

from lexic.grammars.abnf.emitter import AbnfEmitter
from lexic.grammars.abnf.escapes import ABNF_ESCAPES
from lexic.ir.nodes import IrCharClass, IrItem, IrLiteral, IrQuantifier, IrRuleRef


class _TestAbnfEmitter(AbnfEmitter):
    """AbnfEmitter subclass that exposes protected emit methods for testing."""

    def emit_item(self, item: IrItem) -> str:
        """Public proxy for testing the protected _emit_item method."""
        return self._emit_item(item)


def _emitter() -> _TestAbnfEmitter:
    return _TestAbnfEmitter(escapes=ABNF_ESCAPES)


def test_rule_separator_is_equals():
    """Test that ABNF uses '=' as the rule separator."""
    e = _emitter()
    assert e.rule_separator == "="


def test_alt_separator_is_slash():
    """Test that ABNF uses ' / ' as the alternation separator."""
    assert _emitter().alt_separator == " / "


def test_format_quantifier_prefix_zero_or_more():
    """Test that format_quantifier produces ABNF prefix quantifier syntax."""
    e = _emitter()
    assert e.format_quantifier(0, None) == "*"
    assert e.format_quantifier(1, None) == "1*"
    assert e.format_quantifier(0, 1) == "*1"
    assert e.format_quantifier(2, 5) == "2*5"
    assert e.format_quantifier(3, 3) == "3"
    assert e.format_quantifier(1, 1) == ""


def test_render_charclass_emits_hex_range():
    """Test that character classes are rendered as ABNF hex ranges."""
    e = _emitter()
    out = e.render_charclass("a-z")
    assert out == "%x61-7A"


def test_render_charclass_handles_multi_range():
    """Test that multi-range character classes are grouped with alternation."""
    e = _emitter()
    out = e.render_charclass("a-zA-Z")
    assert out == "(%x61-7A / %x41-5A)"


def test_quote_uses_double_quotes():
    """Test that literals are quoted with double quotes."""
    e = _emitter()
    assert e.quote("hello") == '"hello"'


def test_supports_is_a_classvar_frozenset_not_a_property():
    """Test that supports is a ClassVar frozenset containing atom types."""
    assert isinstance(AbnfEmitter.supports, frozenset)
    assert "literal" in AbnfEmitter.supports


def test_place_quantifier_prefix_for_abnf():
    """Test that place_quantifier places quantifier as a prefix in ABNF."""
    e = _emitter()
    assert e.place_quantifier("ALPHA", "1*") == "1*ALPHA"
    assert e.place_quantifier('"hi"', "*5") == '*5"hi"'
    assert e.place_quantifier("X", "") == "X"


def test_emit_item_ruleref_with_quantifier_is_prefix():
    """Test that rule references with quantifiers use prefix notation."""
    e = _emitter()
    item = IrItem(IrRuleRef("ALPHA"), IrQuantifier(1, None))
    assert e.emit_item(item) == "1*ALPHA"


def test_emit_item_charclass_with_quantifier_is_prefix():
    """Test that character classes with quantifiers use prefix notation."""
    e = _emitter()
    item = IrItem(IrCharClass("a-z"), IrQuantifier(0, None))
    assert e.emit_item(item) == "*%x61-7A"


def test_emit_item_quantified_literal_is_prefix():
    """Test that quantified literals use prefix notation."""
    e = _emitter()
    item = IrItem(IrLiteral("-"), IrQuantifier(0, 1))
    assert e.emit_item(item) == '*1"-"'
