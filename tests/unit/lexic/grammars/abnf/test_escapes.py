# tests/unit/lexic/grammars/abnf/test_escapes.py
"""AbnfEscapes — ABNF literals are already canonical Python; codec is identity."""

from __future__ import annotations

from lexic.grammars.abnf.escapes import ABNF_ESCAPES, AbnfEscapes
from lexic.ir.escapes import EscapeCodec


def test_abnf_escapes_is_an_escape_codec():
    """AbnfEscapes is an EscapeCodec."""
    assert isinstance(ABNF_ESCAPES, EscapeCodec)
    assert isinstance(ABNF_ESCAPES, AbnfEscapes)


def test_decode_is_identity():
    """Decode is identity. ABNF literals are already canonical Python strings."""
    assert ABNF_ESCAPES.decode("hello") == "hello"
    assert ABNF_ESCAPES.decode("") == ""
    assert ABNF_ESCAPES.decode("ab\\cd") == "ab\\cd"
    assert ABNF_ESCAPES.decode("\\n") == "\\n"
    assert ABNF_ESCAPES.decode("\\t") == "\\t"


def test_encode_is_identity():
    """Encode is identity. ABNF literals are already canonical Python strings."""
    assert ABNF_ESCAPES.encode("hello") == "hello"
    assert ABNF_ESCAPES.encode("") == ""
    assert ABNF_ESCAPES.encode("ab\\cd") == "ab\\cd"
    assert ABNF_ESCAPES.encode("\n") == "\n"


def test_read_escape_passes_through_unknown():
    """read_escape on an unrecognised sequence returns the raw follow-char."""
    char, new_i = ABNF_ESCAPES.read_escape("\\n", 0)
    assert char == "n"
    assert new_i == 2
