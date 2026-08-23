"""EscapeCodec record — emit-side encode/encode_point/spellable via from_tables."""

from __future__ import annotations

import pytest

from lexic.exceptions import UnsupportedConstructError
from lexic.grammars.abnf import ABNF_ESCAPES
from lexic.grammars.gbnf import GBNF_ESCAPES
from lexic.ir.text.codec.escapes import EscapeCodec

# Minimal codec for the encode algorithm test.
C = EscapeCodec.from_tables(
    short={"n": "\n", "t": "\t", '"': '"', "\\": "\\"},
    hexes=(("x", 2), ("u", 4)),
)


# A codec with bracket-class + quoted-form tables, for encode_point/spellable.
# ``class_short`` and ``class_meta`` deliberately overlap the same code point
# (``-`` is claimed by both) so the priority-order test can prove ``class_short``
# wins over the ``class_meta`` backslash.
CC = EscapeCodec.from_tables(
    short={"n": "\n"},
    hexes=(("x", 2), ("u", 4)),
    class_short={0x2D: "SHORT-DASH"},  # '-'
    class_meta="-^",
    quote_safe=((0x20, 0x21), (0x23, 0x7E)),  # excludes '"' (0x22)
)


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
    assert C.encode(canonical) == expected


# ── encode_point — priority order, via a local codec ────────────────────


def test_encode_point_class_short_wins_over_class_meta():
    """A code point present in CLASS_SHORT is spelled via that table even when
    it also takes a CLASS_META backslash — CLASS_SHORT is checked first."""
    assert CC.encode_point(0x2D) == "SHORT-DASH"


def test_encode_point_class_meta_gets_a_backslash():
    """A code point in CLASS_META (but not CLASS_SHORT) is backslash-escaped."""
    assert CC.encode_point(0x5E) == "\\^"  # '^'


def test_encode_point_printable_glyph_falls_through_bare():
    """A printable code point outside CLASS_SHORT/CLASS_META spells as itself."""
    assert CC.encode_point(ord("a")) == "a"


def test_encode_point_uses_narrowest_hex_escape_that_fits():
    """A non-printable code point outside the class tables falls to the
    narrowest HEX_ESCAPES form that fits — here the 2-digit ``x`` form."""
    assert CC.encode_point(0x01) == "\\x01"


def test_encode_point_raises_when_no_hex_form_fits():
    """encode_point raises UnsupportedConstructError when the code point
    exceeds every configured HEX_ESCAPES width."""
    with pytest.raises(UnsupportedConstructError, match="no hex escape fits"):
        CC.encode_point(0x100000)  # wider than the local codec's widest (u, 4)


# ── spellable — via a local codec ────────────────────────────────────────


def test_spellable_true_when_every_char_in_quote_safe_ranges():
    """spellable is True when every character falls within QUOTE_SAFE."""
    assert CC.spellable("abc") is True


def test_spellable_false_on_excluded_char():
    """spellable is False when a character (here '\"') falls outside every
    QUOTE_SAFE range."""
    assert CC.spellable('a"b') is False


def test_spellable_empty_text_is_true():
    """spellable on empty text is vacuously True (no character fails)."""
    assert CC.spellable("") is True


# ── encode_point / spellable — via the production GBNF/ABNF singletons ──


def test_gbnf_encode_point_control_char_uses_class_short():
    """GBNF_ESCAPES.encode_point(10) → '\\n', the CLASS_SHORT spelling."""
    assert GBNF_ESCAPES.encode_point(10) == "\\n"


def test_gbnf_encode_point_meta_char_gets_backslash():
    """GBNF_ESCAPES.encode_point(']') → '\\]', a CLASS_META bracket-meta char."""
    assert GBNF_ESCAPES.encode_point(ord("]")) == "\\]"


def test_gbnf_encode_point_printable_ascii_is_bare():
    """GBNF_ESCAPES.encode_point('a') → 'a' — printable, no table entry."""
    assert GBNF_ESCAPES.encode_point(ord("a")) == "a"


def test_gbnf_encode_point_del_control_uses_narrow_hex():
    """GBNF_ESCAPES.encode_point(0x7F) → '\\x7f' — non-printable DEL, 2-digit hex."""
    assert GBNF_ESCAPES.encode_point(0x7F) == "\\x7f"


def test_gbnf_encode_point_wide_nonprintable_uses_widest_hex():
    """GBNF_ESCAPES.encode_point of a non-printable code point beyond the
    ``u`` (4-digit) width falls to the ``U`` (8-digit) form.

    0x10000 itself is a *printable* Unicode character (Linear B), so it spells
    as its bare glyph rather than exercising the hex fallback — 0x100000 (an
    unassigned, non-printable plane) is the case that actually needs ``U``.
    """
    assert GBNF_ESCAPES.encode_point(0x100000) == "\\U00100000"


def test_abnf_spellable_plain_ascii_true():
    """ABNF_ESCAPES.spellable('abc') is True — plain printable ASCII."""
    assert ABNF_ESCAPES.spellable("abc") is True


def test_abnf_spellable_embedded_quote_false():
    """ABNF_ESCAPES.spellable('a\"b') is False — RFC 7405 excludes the quote."""
    assert ABNF_ESCAPES.spellable('a"b') is False


def test_abnf_spellable_empty_true():
    """ABNF_ESCAPES.spellable('') is True — vacuously spellable."""
    assert ABNF_ESCAPES.spellable("") is True


def test_abnf_spellable_non_ascii_false():
    """ABNF_ESCAPES.spellable('é') is False — outside the ASCII QUOTE_SAFE ranges."""
    assert ABNF_ESCAPES.spellable("é") is False
