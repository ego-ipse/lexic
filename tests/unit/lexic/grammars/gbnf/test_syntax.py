"""GBNF flavour syntax — GbnfEscapes subclass + bracket converters."""

from __future__ import annotations

import pytest

from lexic.grammars.gbnf.syntax import (
    GBNF_ESCAPES,
    GbnfEscapes,
    canonical_to_gbnf_bracket,
    decode_gbnf_escapes,
    encode_gbnf_escapes,
    gbnf_bracket_to_canonical,
)
from lexic.ir.escapes import EscapeCodec


def test_gbnf_escapes_is_subclass_of_escape_codec():
    """GbnfEscapes inherits the algorithm from the EscapeCodec ABC."""
    assert issubclass(GbnfEscapes, EscapeCodec)


def test_module_aliases_are_bound_to_canonical_instance():
    """The free-function aliases delegate to GBNF_ESCAPES, not to a separate impl."""
    assert decode_gbnf_escapes == GBNF_ESCAPES.decode
    assert encode_gbnf_escapes == GBNF_ESCAPES.encode


# ── decode/encode (delegate to inherited algorithm) ──────────────────


@pytest.mark.parametrize(
    "src,expected",
    [
        (r"\n", "\n"),
        (r"\t", "\t"),
        (r"\r", "\r"),
        (r"\\", "\\"),
        (r"\"", '"'),
        (r"\x41", "A"),
        ("A", "A"),
        (r"hello\nworld", "hello\nworld"),
    ],
)
def test_decode_gbnf_escapes(src, expected):
    """Test that decode_gbnf_escapes correctly decodes GBNF escape sequences."""
    assert decode_gbnf_escapes(src) == expected


@pytest.mark.parametrize(
    "canonical,expected",
    [
        ("\n", r"\n"),
        ("\t", r"\t"),
        ("\r", r"\r"),
        ("\\", r"\\"),
        ('"', r"\""),
        ("hello\nworld", r"hello\nworld"),
        ("plain", "plain"),
    ],
)
def test_encode_gbnf_escapes(canonical, expected):
    """Test that encode_gbnf_escapes correctly encodes special characters."""
    assert encode_gbnf_escapes(canonical) == expected


def test_decode_then_encode_roundtrip_on_pure_ascii():
    """Test that decode_gbnf_escapes and encode_gbnf_escapes round-trip on pure ASCII."""
    s = "abc-def_123"
    assert encode_gbnf_escapes(decode_gbnf_escapes(s)) == s


def test_encode_then_decode_roundtrip_on_canonical_python():
    """Test round-trip on canonical Python strings."""
    s = "tab\there\nnewline"
    assert decode_gbnf_escapes(encode_gbnf_escapes(s)) == s


# ── bracket canonicalisation ─────────────────────────────────────────


def test_gbnf_bracket_to_canonical_passes_through_simple():
    """Test that gbnf_bracket_to_canonical returns the same string for simple cases."""
    assert gbnf_bracket_to_canonical("[0-9]") == "[0-9]"
    assert gbnf_bracket_to_canonical("[a-zA-Z_]") == "[a-zA-Z_]"


def test_gbnf_bracket_to_canonical_handles_negation():
    """Test that gbnf_bracket_to_canonical correctly handles negated character classes."""
    assert gbnf_bracket_to_canonical("[^abc]") == "[^abc]"


def test_canonical_to_gbnf_bracket_passes_through():
    """Test that canonical_to_gbnf_bracket returns the same string for already-GBNF cases."""
    # POSIX is already canonical; GBNF accepts it directly.
    assert canonical_to_gbnf_bracket("[0-9]") == "[0-9]"
