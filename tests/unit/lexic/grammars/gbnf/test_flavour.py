# tests/unit/lexic/grammars/gbnf/test_flavour.py
"""GbnfFlavour — full Flavour binding for GBNF."""

from __future__ import annotations

from lexic.grammars.flavour import Flavour
from lexic.grammars.gbnf.flavour import GbnfFlavour
from lexic.ir.escapes import EscapeCodec
from lexic.ir.nodes import IrLiteral, Quantifier


def test_gbnf_flavour_is_a_flavour_subclass():
    """GbnfFlavour must be a subclass of Flavour."""
    assert issubclass(GbnfFlavour, Flavour)


def test_gbnf_flavour_metadata():
    """GbnfFlavour must declare a name, extensions, and line_comment."""
    assert GbnfFlavour.name == "gbnf"
    assert ".gbnf" in GbnfFlavour.extensions
    assert GbnfFlavour.line_comment == "#"


def test_gbnf_flavour_meta_grammar_is_imported():
    """GbnfFlavour must declare a meta-grammar string."""
    assert "ir_rule" in GbnfFlavour.meta_grammar
    assert "::=" in GbnfFlavour.meta_grammar


def test_gbnf_flavour_escapes_decodes_backslash_n():
    """GbnfFlavour must declare an EscapeCodec subclass."""
    assert issubclass(type(GbnfFlavour.escapes), EscapeCodec)
    assert GbnfFlavour.escapes.decode(r"\n") == "\n"
    assert GbnfFlavour.escapes.decode(r"a\tb") == "a\tb"


def test_parse_quantifier_question_mark():
    """GbnfFlavour must declare a parse_quantifier method."""
    assert GbnfFlavour.parse_quantifier("?") == Quantifier(0, 1)


def test_parse_quantifier_star():
    """GbnfFlavour must declare a parse_quantifier method."""
    assert GbnfFlavour.parse_quantifier("*") == Quantifier(0, None)


def test_parse_quantifier_plus():
    """GbnfFlavour must declare a parse_quantifier method."""
    assert GbnfFlavour.parse_quantifier("+") == Quantifier(1, None)


def test_parse_quantifier_braces_exact():
    """GbnfFlavour must declare a parse_quantifier method."""
    assert GbnfFlavour.parse_quantifier("{3}") == Quantifier(3, 3)


def test_parse_quantifier_braces_range():
    """GbnfFlavour must declare a parse_quantifier method."""
    assert GbnfFlavour.parse_quantifier("{1,5}") == Quantifier(1, 5)


def test_parse_quantifier_braces_unbounded():
    """GbnfFlavour must declare a parse_quantifier method."""
    assert GbnfFlavour.parse_quantifier("{2,}") == Quantifier(2, None)


def test_parse_charclass_basic():
    """GbnfFlavour must declare a parse_charclass method."""
    pattern, negated = GbnfFlavour.parse_charclass("[a-z]")
    assert pattern == "a-z"
    assert negated is False


def test_parse_charclass_negated():
    """GbnfFlavour must declare a parse_charclass method."""
    pattern, negated = GbnfFlavour.parse_charclass(r'[^"\\]')
    assert pattern == r'"\\'
    assert negated is True


def test_normalize_literal_default_identity():
    """GbnfFlavour must declare a normalize_literal method."""
    assert GbnfFlavour.normalize_literal("hello") == IrLiteral("hello")
