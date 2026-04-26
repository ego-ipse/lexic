"""parse_charclass_chars — bracket-expression enumeration over canonical patterns."""

from __future__ import annotations

from lexic.ir.charclass import parse_charclass_chars
from lexic.ir.escapes import CANONICAL_ESCAPES, EscapeCodec


def test_simple_range():
    """A single range expands to all chars between its endpoints inclusive."""
    assert parse_charclass_chars("a-c") == ["a", "b", "c"]


def test_multiple_ranges():
    """Adjacent ranges concatenate in order."""
    assert parse_charclass_chars("a-cA-C") == ["a", "b", "c", "A", "B", "C"]


def test_literal_chars_only():
    """Bare chars are emitted one-for-one."""
    assert parse_charclass_chars("xyz") == ["x", "y", "z"]


def test_mixed_range_and_literal():
    """Ranges and literals can intermix in a single expression."""
    assert parse_charclass_chars("a-c_") == ["a", "b", "c", "_"]


def test_escape_in_range_endpoint():
    """Hex-escaped endpoints participate in range expansion."""
    # \\x41 = 'A', \\x43 = 'C'.
    assert parse_charclass_chars(r"\x41-\x43") == ["A", "B", "C"]


def test_escaped_meta_passes_through():
    """An escaped hyphen is a literal, not a range marker."""
    assert parse_charclass_chars(r"a\-z") == ["a", "-", "z"]


def test_default_codec_is_canonical_escapes():
    """Calling without an explicit codec uses CANONICAL_ESCAPES."""
    assert parse_charclass_chars("a-c") == parse_charclass_chars(
        "a-c", CANONICAL_ESCAPES
    )


def test_codec_is_parametric():
    """A custom codec can advertise different escape semantics."""

    class _Custom(EscapeCodec):
        SHORT_ESCAPES = {"q": "Z"}
        HEX_ESCAPES = ()

    assert parse_charclass_chars(r"\q", _Custom()) == ["Z"]
