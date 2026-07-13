"""EscapeCodec ABC — encode/decode/read_escape via fake subclass + canonical instance."""

from __future__ import annotations

import pytest

from lexic.exceptions import UnsupportedConstructError
from lexic.grammars.abnf import ABNF_ESCAPES
from lexic.grammars.gbnf import GBNF_ESCAPES
from lexic.ir.escapes import CANONICAL_ESCAPES, EscapeCodec


class _Codec(EscapeCodec):
    """Minimal EscapeCodec subclass used for ABC-algorithm tests."""

    SHORT_ESCAPES = {"n": "\n", "t": "\t", '"': '"', "\\": "\\"}
    HEX_ESCAPES = (("x", 2), ("u", 4))


_C = _Codec()


class _ClassCodec(EscapeCodec):
    """A codec with bracket-class + quoted-form tables, for encode_point/spellable.

    ``CLASS_SHORT`` and ``CLASS_META`` deliberately overlap the same code
    points (``-`` is claimed by both) so the priority-order tests can prove
    ``CLASS_SHORT`` wins over the ``CLASS_META`` backslash.
    """

    SHORT_ESCAPES = {"n": "\n"}
    HEX_ESCAPES = (("x", 2), ("u", 4))
    CLASS_SHORT = {0x2D: "SHORT-DASH"}  # '-'
    CLASS_META = frozenset("-^")
    QUOTE_SAFE = ((0x20, 0x21), (0x23, 0x7E))  # excludes '"' (0x22)


_CC = _ClassCodec()


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


# ── encode_point — priority order, via a local codec ────────────────────


def test_encode_point_class_short_wins_over_class_meta():
    """A code point present in CLASS_SHORT is spelled via that table even when
    it also takes a CLASS_META backslash — CLASS_SHORT is checked first."""
    assert _CC.encode_point(0x2D) == "SHORT-DASH"


def test_encode_point_class_meta_gets_a_backslash():
    """A code point in CLASS_META (but not CLASS_SHORT) is backslash-escaped."""
    assert _CC.encode_point(0x5E) == "\\^"  # '^'


def test_encode_point_printable_glyph_falls_through_bare():
    """A printable code point outside CLASS_SHORT/CLASS_META spells as itself."""
    assert _CC.encode_point(ord("a")) == "a"


def test_encode_point_uses_narrowest_hex_escape_that_fits():
    """A non-printable code point outside the class tables falls to the
    narrowest HEX_ESCAPES form that fits — here the 2-digit ``x`` form."""
    assert _CC.encode_point(0x01) == "\\x01"


def test_encode_point_raises_when_no_hex_form_fits():
    """encode_point raises UnsupportedConstructError when the code point
    exceeds every configured HEX_ESCAPES width."""
    with pytest.raises(UnsupportedConstructError, match="no hex escape fits"):
        _CC.encode_point(0x100000)  # wider than the local codec's widest (u, 4)


# ── spellable — via a local codec ────────────────────────────────────────


def test_spellable_true_when_every_char_in_quote_safe_ranges():
    """spellable is True when every character falls within QUOTE_SAFE."""
    assert _CC.spellable("abc") is True


def test_spellable_false_on_excluded_char():
    """spellable is False when a character (here '\"') falls outside every
    QUOTE_SAFE range."""
    assert _CC.spellable('a"b') is False


def test_spellable_empty_text_is_true():
    """spellable on empty text is vacuously True (no character fails)."""
    assert _CC.spellable("") is True


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
