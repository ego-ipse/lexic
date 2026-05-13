"""GbnfEscapes — encode/decode round-trip and specific cases."""

from __future__ import annotations

from lexic.grammars.gbnf.escapes import GbnfEscapes


def test_decode_newline():
    assert GbnfEscapes().decode(r"\n") == "\n"


def test_decode_tab():
    assert GbnfEscapes().decode(r"\t") == "\t"


def test_decode_carriage_return():
    assert GbnfEscapes().decode(r"\r") == "\r"


def test_decode_backslash():
    assert GbnfEscapes().decode(r"\\") == "\\"


def test_decode_quote():
    assert GbnfEscapes().decode(r"\"") == '"'


def test_decode_plain_text():
    assert GbnfEscapes().decode("abc") == "abc"


def test_encode_newline():
    assert GbnfEscapes().encode("\n") == r"\n"


def test_encode_tab():
    assert GbnfEscapes().encode("\t") == r"\t"


def test_encode_backslash():
    assert GbnfEscapes().encode("\\") == r"\\"


def test_encode_quote():
    assert GbnfEscapes().encode('"') == r"\""


def test_encode_plain_text():
    assert GbnfEscapes().encode("abc") == "abc"


def test_round_trip():
    escapes = GbnfEscapes()
    for raw in ["\n", "\t", "\\", '"', "hello", "\x00"]:
        assert escapes.decode(escapes.encode(raw)) == raw
