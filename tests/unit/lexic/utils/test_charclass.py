"""charclass utilities — parse_charclass_chars and charclass_pattern."""

from __future__ import annotations

from lexic.ir.escapes import CANONICAL_ESCAPES, EscapeCodec
from lexic.ir.nodes import IrCharClass, IrChr, IrRange
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
    cls = IrCharClass(IrRange(IrChr("a"), IrChr("z")))
    assert charclass_pattern(cls) == "a-z"


def test_charclass_pattern_run_only():
    """A run of code points emits its characters verbatim."""
    cls = IrCharClass(IrChr("a"), IrChr("b"), IrChr("c"))
    assert charclass_pattern(cls) == "abc"


def test_charclass_pattern_mixed_run_then_range():
    """A run of code points followed by a range concatenates correctly."""
    cls = IrCharClass(
        IrChr("a"), IrChr("b"), IrChr("c"), IrRange(IrChr("0"), IrChr("9"))
    )
    assert charclass_pattern(cls) == "abc0-9"


def test_charclass_pattern_encoded_hex_units():
    """Non-printable code-point endpoints are escaped in the interior pattern."""
    cls = IrCharClass(IrRange(IrChr(0), IrChr(0x1F)))
    assert charclass_pattern(cls) == "\\x00-\\x1f"


# ── charclass_pattern — per-code-point escaping rules ─────────────────


def test_control_char_escapes_to_hex():
    """Non-printable code points (≤ 0xFF) are rendered as ``\\xNN``."""
    cls = IrCharClass(IrChr("\x01"))
    assert charclass_pattern(cls) == "\\x01"


def test_non_printable_tab_escapes_to_hex():
    """Tab (``\\t``, U+0009) is non-printable → ``\\x09``."""
    cls = IrCharClass(IrChr("\t"))
    assert charclass_pattern(cls) == "\\x09"


def test_raw_close_bracket_is_escaped():
    """A raw ``]`` in a char-class run is escaped to ``\\]``."""
    cls = IrCharClass(IrChr("]"))
    assert charclass_pattern(cls) == "\\]"


def test_raw_caret_is_escaped():
    """A raw ``^`` in a char-class run is escaped to ``\\^``."""
    cls = IrCharClass(IrChr("^"))
    assert charclass_pattern(cls) == "\\^"


def test_preescaped_unit_passes_through():
    """Non-printable code-point endpoints render as hex escape sequences.

    IrChr stores ordinals; charclass_pattern escapes non-printable points to
    ``\\xNN`` — so the round-trip through IrChr and charclass_pattern is stable.
    """
    cls = IrCharClass(IrRange(IrChr(0), IrChr(0x1F)))
    result = charclass_pattern(cls)
    assert result == "\\x00-\\x1f"


def test_lone_backslash_is_escaped():
    """A lone ``\\`` (single backslash character) is escaped to ``\\\\``."""
    cls = IrCharClass(IrChr("\\"))
    assert charclass_pattern(cls) == "\\\\"
