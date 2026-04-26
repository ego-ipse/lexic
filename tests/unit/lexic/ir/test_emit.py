"""FlavourEmitter ABC — DEFAULT_HANDLERS + decorators tested via a fake subclass."""

from __future__ import annotations
from dataclasses import dataclass

from lexic.ir import (
    AlternationAtom,
    CharClassAtom,
    InlineAlternationAtom,
    LiteralAtom,
    QuantifiedLiteralAtom,
    RuleRefAtom,
    RuleSpec,
)
from lexic.ir.emit import FlavourEmitter


class FakeEscapes:
    """A fake EscapeCodec that does nothing, for testing purposes."""

    def encode(self, value):
        """Encode a string by returning it unchanged."""
        return value

    def decode(self, source):
        """Decode a string by returning it unchanged."""
        return source


class _TestEmitter(FlavourEmitter):
    """A test emitter that uses the default handlers and a fake escape codec."""

    @property
    def supports(self):
        """The set of atom types this emitter supports; for testing, support the default ones."""
        return frozenset({"literal", "char_class", "alternation", "quantifier"})


@dataclass(frozen=True)
class CustomTestAtom:
    """A custom atom type for testing the ability to register extra handlers."""

    marker: str


class SingleQuote(_TestEmitter):
    """A test emitter subclass that overrides the quote character for literals."""

    quote_char = "'"


def _new(handlers=None) -> _TestEmitter:
    """Helper to create a new _TestEmitter with the default handlers plus any overrides."""
    return _TestEmitter(escapes=FakeEscapes(), handlers=handlers)


def test_default_literal_handler_quotes():
    """The default literal handler should quote the value."""
    e = _new()
    assert e.render_atom(LiteralAtom(value="hi")) == '"hi"'


def test_default_quantified_literal_appends_quantifier():
    """The default quantified literal handler should render the literal and append quantifier."""
    e = _new()
    assert e.render_atom(QuantifiedLiteralAtom(value="-", min=0, max=1)) == '"-"?'


def test_default_charclass_appends_quantifier():
    """The default char class handler should render the pattern and append quantifier."""
    e = _new()
    assert e.render_atom(CharClassAtom(pattern="[0-9]", min=1, max=None)) == "[0-9]+"


def test_default_ruleref_appends_quantifier():
    """The default ruleref handler should render the rule name and append quantifier."""
    e = _new()
    assert e.render_atom(RuleRefAtom(rule_name="x", min=0, max=1)) == "x?"


def test_default_alternation_joins_with_alt_separator():
    """The default alternation handler should join the arm rule names with alternative separator."""
    e = _new()
    assert e.render_atom(AlternationAtom(arm_rule_names=["a", "b"])) == "a | b"


def test_default_inline_alternation_wraps_with_group():
    """The default inline alternation handler should wrap the arms with a group."""
    e = _new()
    assert e.render_atom(InlineAlternationAtom(arm_rule_names=["a", "b"])) == "(a | b)"


def test_emit_rule_renders_value_str_body():
    """emit_rule should render a value_str rule by rendering its body atoms."""
    spec = RuleSpec(
        rule_name="num",
        class_name="Num",
        parent_class_name="GrammarModel",
        kind="value_str",
        items=[CharClassAtom("[0-9]", 1, None)],
        field_map={},
    )
    e = _new()
    assert e.emit_rule(spec) == "num ::= [0-9]+"


def test_emit_joins_rules_with_newlines():
    """emit should join rules with newlines."""
    a = RuleSpec(
        rule_name="a",
        class_name="A",
        parent_class_name="GrammarModel",
        kind="value_str",
        items=[LiteralAtom("x")],
        field_map={},
    )
    b = RuleSpec(
        rule_name="b",
        class_name="B",
        parent_class_name="GrammarModel",
        kind="value_str",
        items=[LiteralAtom("y")],
        field_map={},
    )
    e = _new()
    assert e.emit([a, b]) == 'a ::= "x"\nb ::= "y"\n'


def test_subclass_can_override_quote_char():
    """A subclass should be able to override the quote character used for literals."""
    e = SingleQuote(escapes=FakeEscapes())
    assert e.render_atom(LiteralAtom(value="hi")) == "'hi'"


def test_subclass_can_register_extra_handler():
    """A subclass should be able to register an extra handler for a custom atom type."""
    e = _new(
        handlers={
            **FlavourEmitter.DEFAULT_HANDLERS,
            CustomTestAtom: lambda a, em: f"<{a.marker}>",
        }
    )
    assert e.render_atom(CustomTestAtom(marker="x")) == "<x>"
