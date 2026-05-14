"""GbnfEscapes — encode/decode round-trip and specific cases."""

from __future__ import annotations

from lexic.grammars.gbnf.escapes import GbnfEscapes


def test_decode_newline():
    """Backslash-n decodes to newline."""
    assert GbnfEscapes().decode(r"\n") == "\n"


def test_decode_tab():
    """Backslash-t decodes to tab."""
    assert GbnfEscapes().decode(r"\t") == "\t"


def test_decode_carriage_return():
    """Backslash-r decodes to carriage return."""
    assert GbnfEscapes().decode(r"\r") == "\r"


def test_decode_backslash():
    """Double backslash decodes to single backslash."""
    assert GbnfEscapes().decode(r"\\") == "\\"


def test_decode_quote():
    """Escaped quote decodes to double quote."""
    assert GbnfEscapes().decode(r"\"") == '"'


def test_decode_plain_text():
    """Plain text decodes unchanged."""
    assert GbnfEscapes().decode("abc") == "abc"


def test_encode_newline():
    """Newline encodes to backslash-n."""
    assert GbnfEscapes().encode("\n") == r"\n"


def test_encode_tab():
    """Tab encodes to backslash-t."""
    assert GbnfEscapes().encode("\t") == r"\t"


def test_encode_backslash():
    """Backslash encodes to double backslash."""
    assert GbnfEscapes().encode("\\") == r"\\"


def test_encode_quote():
    """Double quote encodes to escaped quote."""
    assert GbnfEscapes().encode('"') == r"\""


def test_encode_plain_text():
    """Plain text encodes unchanged."""
    assert GbnfEscapes().encode("abc") == "abc"


def test_round_trip():
    """encode(decode(x)) == x for a variety of characters."""
    escapes = GbnfEscapes()
    for raw in ["\n", "\t", "\\", '"', "hello", "\x00"]:
        assert escapes.decode(escapes.encode(raw)) == raw
