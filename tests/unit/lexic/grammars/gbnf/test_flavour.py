"""GbnfFlavour mirror parity check."""

from __future__ import annotations

from lexic.grammars.flavour import Flavour
from lexic.grammars.gbnf.flavour import GbnfFlavour as LegacyFlavour
from lexic.grammars.gbnf.flavour import GbnfFlavour as NewFlavour


def test_subclass():
    """GbnfFlavour is a Flavour subclass."""
    assert issubclass(NewFlavour, Flavour)


def test_metadata():
    """GbnfFlavour metadata is the same as LegacyFlavour."""
    assert NewFlavour.name == LegacyFlavour.name == "gbnf"
    assert NewFlavour.extensions == LegacyFlavour.extensions == (".gbnf",)


def test_meta_grammar_identity():
    """GbnfFlavour.meta_grammar is the same as LegacyFlavour.meta_grammar."""
    assert NewFlavour.meta_grammar == LegacyFlavour.meta_grammar


def test_parse_quantifier_parity():
    """GbnfFlavour.parse_quantifier is the same as LegacyFlavour.parse_quantifier."""
    cases = ["", "?", "+", "*", "{2,5}", "{0,15}", "{3}"]
    for s in cases:
        assert NewFlavour.parse_quantifier(s) == LegacyFlavour.parse_quantifier(s)


def test_parse_charclass_parity():
    """GbnfFlavour.parse_charclass is the same as LegacyFlavour.parse_charclass."""
    cases = ["[a-z]", "[0-9]", "[^abc]", r"[\\\"]"]
    for s in cases:
        assert NewFlavour.parse_charclass(s) == LegacyFlavour.parse_charclass(s)


def test_line_comment_token():
    """GbnfFlavour.line_comment is the same as LegacyFlavour.line_comment."""
    assert NewFlavour.line_comment == LegacyFlavour.line_comment
