"""GbnfFlavour mirror parity check."""

from __future__ import annotations

from lexic.grammars.flavour import IrFlavour
from lexic.grammars.gbnf.flavour import GbnfFlavour
from lexic.ir.nodes import IrQuantifier


def test_subclass():
    """GbnfFlavour is a IrFlavour subclass."""
    assert issubclass(GbnfFlavour, IrFlavour)


def test_metadata():
    """GbnfFlavour metadata is stable."""
    assert GbnfFlavour.name == "gbnf"
    assert GbnfFlavour.extensions == (".gbnf",)


def test_meta_grammar_identity():
    """GbnfFlavour.meta_grammar is a non-empty string."""
    assert isinstance(GbnfFlavour.meta_grammar, str)
    assert len(GbnfFlavour.meta_grammar) > 0


def test_parse_quantifier_parity():
    """parse_quantifier produces expected IrQuantifier values."""
    cases = ["", "?", "+", "*", "{2,5}", "{0,15}", "{3}"]
    expected = [
        IrQuantifier(1, 1),
        IrQuantifier(0, 1),
        IrQuantifier(1, None),
        IrQuantifier(0, None),
        IrQuantifier(2, 5),
        IrQuantifier(0, 15),
        IrQuantifier(3, 3),
    ]
    for s, exp in zip(cases, expected):
        assert GbnfFlavour.parse_quantifier(s) == exp


def test_parse_charclass_parity():
    """parse_charclass handles negation and escapes."""
    cases = ["[a-z]", "[0-9]", "[^abc]", r'[\\"]']
    expected = [("a-z", False), ("0-9", False), ("abc", True), (r'\\"', False)]
    for s, exp in zip(cases, expected):
        assert GbnfFlavour.parse_charclass(s) == exp


def test_line_comment_token():
    """GbnfFlavour line comment marker is '#'."""
    assert GbnfFlavour.line_comment == "#"
