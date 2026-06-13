"""charclass utilities — parse_charclass_chars and charclass_pattern."""

from __future__ import annotations

from lexic.ir.base import IrStr
from lexic.ir.escapes import CANONICAL_ESCAPES, EscapeCodec
from lexic.ir.nodes import IrCharClass, IrRange
from lexic.utils.charclass import charclass_pattern, parse_charclass_chars

# ── parse_charclass_chars ─────────────────────────────────────────────


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


# ── charclass_pattern ─────────────────────────────────────────────────


def test_charclass_pattern_single_range():
    """A single IrRange flattens to ``lo-hi``."""
    cls = IrCharClass(IrRange("a", "z"))
    assert charclass_pattern(cls) == "a-z"


def test_charclass_pattern_run_only():
    """A bare IrStr run emits its characters verbatim."""
    cls = IrCharClass(IrStr("abc"))
    assert charclass_pattern(cls) == "abc"


def test_charclass_pattern_mixed_run_then_range():
    """A run followed by a range concatenates correctly."""
    cls = IrCharClass(IrStr("abc"), IrRange("0", "9"))
    assert charclass_pattern(cls) == "abc0-9"


def test_charclass_pattern_encoded_hex_units():
    """Encoded hex escape units are kept verbatim in the interior pattern."""
    cls = IrCharClass(IrRange("\\x00", "\\x1F"))
    assert charclass_pattern(cls) == "\\x00-\\x1F"
