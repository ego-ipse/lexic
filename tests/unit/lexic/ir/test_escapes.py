"""EscapeCodec ABC — encode/decode/read_escape via fake subclass + canonical instance."""

from __future__ import annotations

import pytest

from lexic.ir.escapes import CANONICAL_ESCAPES, EscapeCodec


class _Codec(EscapeCodec):
    """Minimal EscapeCodec subclass used for ABC-algorithm tests."""

    SHORT_ESCAPES = {"n": "\n", "t": "\t", '"': '"', "\\": "\\"}
    HEX_ESCAPES = (("x", 2), ("u", 4))


_C = _Codec()


@pytest.mark.parametrize(
    "src,expected",
    [
        (r"\n", "\n"),
        (r"\t", "\t"),
        (r"\\", "\\"),
        (r"\"", '"'),
        (r"\x41", "A"),
        (r"é", "é"),
        (r"hello\nworld", "hello\nworld"),
        ("plain", "plain"),
    ],
)
def test_decode_short_and_hex(src, expected):
    """decode handles short escapes, hex escapes, and bare text uniformly."""
    assert _C.decode(src) == expected


@pytest.mark.parametrize(
    "canonical,expected",
    [
        ("\n", r"\n"),
        ("\t", r"\t"),
        ("\\", r"\\"),
        ('"', r"\""),
        ("hello\nworld", r"hello\nworld"),
        ("plain", "plain"),
    ],
)
def test_encode_inverts_short_table(canonical, expected):
    """encode produces the source-form for each canonical char in SHORT_ESCAPES."""
    assert _C.encode(canonical) == expected


def test_encode_decode_roundtrip_on_canonical_python():
    """Round-trip: encode then decode returns the original canonical string."""
    s = "tab\there\nnewline"
    assert _C.decode(_C.encode(s)) == s


def test_read_escape_short():
    """read_escape returns the canonical char and advances past the 2-char escape."""
    assert _C.read_escape(r"\nrest", 0) == ("\n", 2)


def test_read_escape_hex():
    """read_escape decodes hex escapes and advances past the full sequence."""
    assert _C.read_escape(r"\x41rest", 0) == ("A", 4)


def test_read_escape_unrecognised_returns_literal_char():
    """An unrecognised follow-char is returned as itself."""
    assert _C.read_escape(r"\zrest", 0) == ("z", 2)


def test_canonical_escapes_supports_posix_meta():
    """POSIX bracket-meta chars must be readable as themselves when escaped."""
    assert CANONICAL_ESCAPES.read_escape(r"\]rest", 0) == ("]", 2)
    assert CANONICAL_ESCAPES.read_escape(r"\-rest", 0) == ("-", 2)
    assert CANONICAL_ESCAPES.read_escape(r"\^rest", 0) == ("^", 2)


def test_canonical_escapes_decodes_python_control_and_hex():
    """The canonical codec decodes \\n and \\xNN as expected."""
    assert CANONICAL_ESCAPES.decode(r"a\nb\x41") == "a\nbA"
