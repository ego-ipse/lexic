"""GBNF_FLAVOUR mirror parity check."""

from __future__ import annotations

from lexic.grammars.flavour import IrFlavour
from lexic.grammars.gbnf.flavour import GBNF_ESCAPES, GBNF_FLAVOUR, META_GRAMMAR
from lexic.ir.nodes import (
    IrQuantifier,
)
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
        IrQuantifier(1, None),
        IrQuantifier(0, None),
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
