"""Tests for ``lexic.ir.grammar.charclass`` — the character-set node and its
interval algebra: pattern spelling, members, the normal form, complement,
sampling (surrogates excised), and the interval cover.
"""

from __future__ import annotations

import random

from lexic.ir.grammar.charclass import MAX_CODEPOINT, IrCharClass, IrRange
from lexic.ir.spine.scalars import IrChr

# ── IrCharClass intrinsic behaviour (relocated from utils/test_charclass) ──


def test_charclass_pattern_single_range():
    """A single IrRange flattens to ``lo-hi``."""
    assert IrCharClass(IrRange(IrChr("a"), IrChr("z"))).pattern() == "a-z"


def test_charclass_pattern_run_only():
    """A run of code points emits its characters verbatim."""
    assert IrCharClass(IrChr("a"), IrChr("b"), IrChr("c")).pattern() == "abc"


def test_charclass_pattern_mixed_run_then_range():
    """A run of code points followed by a range concatenates correctly."""
    cls = IrCharClass(
        IrChr("a"), IrChr("b"), IrChr("c"), IrRange(IrChr("0"), IrChr("9"))
    )
    assert cls.pattern() == "abc0-9"


def test_charclass_pattern_encoded_hex_units():
    """Non-printable code-point endpoints are escaped in the interior pattern."""
    assert IrCharClass(IrRange(IrChr(0), IrChr(0x1F))).pattern() == "\\x00-\\x1f"


def test_charclass_pattern_control_char_escapes_to_hex():
    """Non-printable code points (≤ 0xFF) are rendered as ``\\xNN``."""
    assert IrCharClass(IrChr("\x01")).pattern() == "\\x01"
    assert IrCharClass(IrChr("\t")).pattern() == "\\x09"


def test_charclass_pattern_metachars_are_escaped():
    """Raw ``]``/``^``/``-``/``\\`` in a run are backslash-escaped."""
    assert IrCharClass(IrChr("]")).pattern() == "\\]"
    assert IrCharClass(IrChr("^")).pattern() == "\\^"
    assert IrCharClass(IrChr("-")).pattern() == "\\-"
    assert IrCharClass(IrChr("\\")).pattern() == "\\\\"


def test_charclass_pattern_dash_range_bound_is_escaped():
    """A range whose low bound is ``-`` (0x2D) escapes the dash.

    Unescaped, ``[!&--.]`` reads as set difference in some regex engines
    when a lower-codepoint member precedes the ``-``–``.`` range, and the
    class silently drops members.
    """
    cls = IrCharClass(IrChr("!"), IrChr("&"), IrRange(IrChr("-"), IrChr(".")))
    assert cls.pattern() == "!&\\--."


def test_charclass_members_expands_range():
    """A range enumerates its endpoints inclusive."""
    assert IrCharClass(IrRange(IrChr("a"), IrChr("c"))).members() == [97, 98, 99]


def test_charclass_members_mixed():
    """Members preserve element order: run then range."""
    cls = IrCharClass(IrChr("x"), IrRange(IrChr("0"), IrChr("2")))
    assert [chr(c) for c in cls.members()] == ["x", "0", "1", "2"]


def test_charclass_normalized_sorts_and_coalesces():
    """Normal form dedupes, sorts, and coalesces adjacent runs into ranges."""
    cls = IrCharClass(IrChr("\t"), IrChr("\n"), IrChr("\r"), IrChr(" "))
    assert cls.normalized() == IrCharClass(
        IrRange(IrChr(9), IrChr(10)), IrChr(13), IrChr(32)
    )


def test_charclass_normalized_single_run_is_range():
    """A run of two adjacent points coalesces to one IrRange."""
    assert IrCharClass(IrChr("A"), IrChr("B")).normalized() == IrCharClass(
        IrRange(IrChr("A"), IrChr("B"))
    )


def test_charclass_complement_of_two_points():
    """Complement of ``"`` and ``\\`` is the positive span cover to MAX_CODEPOINT."""
    cls = IrCharClass(IrChr('"'), IrChr("\\"))
    assert cls.complement() == IrCharClass(
        IrRange(IrChr(0), IrChr(33)),
        IrRange(IrChr(35), IrChr(91)),
        IrRange(IrChr(93), IrChr(0x10FFFF)),
    )


# ── IrCharClass intrinsics (Task 2 extension): sample/normalized/complement ──


def test_charclass_sample_always_returns_a_covered_member():
    """sample() never returns a code point outside the class's own members."""
    cls = IrCharClass(IrChr("a"), IrRange(IrChr("0"), IrChr("9")))
    members = set(cls.members())
    rng = random.Random(1729)
    assert all(cls.sample(rng) in members for _ in range(200))


def test_charclass_sample_covers_a_complement_class_without_materialising_it():
    """sample() works on a wide complement class (interval-based, not enumerated)."""
    cls = IrCharClass(IrChr("a")).complement()
    rng = random.Random(7)
    samples = [cls.sample(rng) for _ in range(50)]
    assert all(point != ord("a") for point in samples)


def test_charclass_normalized_dedupes_duplicate_members():
    """Repeated identical members collapse to one in the normal form."""
    cls = IrCharClass(IrChr("a"), IrChr("a"), IrChr("a"))
    assert cls.normalized() == IrCharClass(IrChr("a"))


def test_charclass_complement_round_trips_through_normalized_original():
    """complement(complement(x)) == normalized(x) — the double-complement identity."""
    cls = IrCharClass(IrChr("a"), IrRange(IrChr("0"), IrChr("9")))
    assert cls.complement().complement() == cls.normalized()


# ── IrCharClass.sample() surrogate exclusion (generate.py round-trip fix) ──


def test_charclass_sample_never_returns_a_lone_surrogate():
    """sample() never picks a code point in U+D800-U+DFFF (no valid UTF-8)."""
    cls = IrCharClass(IrChr("a")).complement()
    rng = random.Random(2026)
    for _ in range(20000):
        point = cls.sample(rng)
        assert not 0xD800 <= point <= 0xDFFF
        chr(point).encode("utf-8")  # never raises


def test_charclass_sample_complement_still_represents_the_surrogate_block():
    """The represented set is unchanged — only sampling avoids the block."""
    cls = IrCharClass(IrChr("a")).complement()
    intervals = cls.intervals()
    assert any(lo <= 0xD800 and 0xDFFF <= hi for lo, hi in intervals)


def test_charclass_sample_splits_a_straddling_interval_into_flanking_pieces():
    """A single interval spanning the block only ever samples its two flanks."""
    cls = IrCharClass(IrRange(IrChr(0xD000), IrChr(0xE000)))
    rng = random.Random(3)
    samples = {cls.sample(rng) for _ in range(5000)}
    assert samples <= (set(range(0xD000, 0xD800)) | {0xE000})


def test_charclass_sample_drops_an_interval_wholly_inside_the_block():
    """A class with one surrogate-only member and one real member always samples real."""
    cls = IrCharClass(IrChr("a"), IrRange(IrChr(0xD900), IrChr(0xD9FF)))
    rng = random.Random(4)
    assert all(cls.sample(rng) == ord("a") for _ in range(200))


def test_charclass_sample_falls_back_when_the_whole_class_is_surrogate():
    """A class wholly inside the block still samples (degenerate fallback), never raises."""
    cls = IrCharClass(IrRange(IrChr(0xD800), IrChr(0xDFFF)))
    rng = random.Random(5)
    point = cls.sample(rng)
    assert 0xD800 <= point <= 0xDFFF


def test_charclass_sample_all_surrogate_class_still_returns_int():
    """sample() on a degenerate all-surrogate class never raises."""
    cls = IrCharClass(IrRange(IrChr(0xD800), IrChr(0xDFFF)))
    rng = random.Random(1)
    point = cls.sample(rng)
    assert 0xD800 <= point <= 0xDFFF


def test_charclass_empty_class_edges():
    """An empty char class has empty pattern/members and complements to full range."""
    empty = IrCharClass()
    assert empty.pattern() == ""
    assert not empty.members()
    assert empty.normalized() == IrCharClass()
    assert empty.complement() == IrCharClass(IrRange(IrChr(0), IrChr(MAX_CODEPOINT)))


def test_charclass_full_range_class_edges():
    """A class spanning the whole Unicode range complements to empty and is its own normal form."""
    full = IrCharClass(IrRange(IrChr(0), IrChr(MAX_CODEPOINT)))
    assert full.complement() == IrCharClass()
    assert full.normalized() == full


def test_charclass_is_any_only_for_full_unicode_span():
    """``is_any`` is True iff the coalesced cover is exactly ``[0, MAX_CODEPOINT]``."""
    assert IrCharClass(IrRange(IrChr(0), IrChr(MAX_CODEPOINT))).is_any
    # `.` canonicalises to the complement of the empty class — also full-span.
    assert IrCharClass().complement().is_any
    # Adjacent spans coalesce to the full span → is_any.
    assert IrCharClass(
        IrRange(IrChr(0), IrChr(64)), IrRange(IrChr(65), IrChr(MAX_CODEPOINT))
    ).is_any
    # Anything short of the whole range is not any-char.
    assert not IrCharClass(IrRange(IrChr(ord("a")), IrChr(ord("z")))).is_any
    assert not IrCharClass(IrRange(IrChr(0), IrChr(MAX_CODEPOINT - 1))).is_any
    assert not IrCharClass().is_any


def test_charclass_is_empty_only_for_no_members():
    """``is_empty`` is True iff the class has no members (the negated-`.` source)."""
    assert IrCharClass().is_empty
    assert not IrCharClass(IrChr(ord("a"))).is_empty
    assert not IrCharClass(IrRange(IrChr(ord("a")), IrChr(ord("z")))).is_empty


# ── IrCharClass interval intrinsics (Task 1): intervals / from_intervals ──


def test_charclass_intervals_coalesces_disjoint_cover():
    """intervals() returns the minimal sorted disjoint (lo, hi) cover."""
    cls = IrCharClass(IrChr("\t"), IrChr("\n"), IrChr("\r"), IrChr(" "))
    assert cls.intervals() == [(9, 10), (13, 13), (32, 32)]


def test_charclass_from_intervals_builds_normalized_class():
    """from_intervals() builds IrChr/IrRange members directly, already normalised."""
    cc = IrCharClass.from_intervals([(65, 65), (48, 57)])
    assert cc == IrCharClass(IrRange(IrChr(48), IrChr(57)), IrChr(65))
    assert cc == cc.normalized()


def test_charclass_from_intervals_coalesces_overlapping_and_adjacent():
    """from_intervals() merges overlapping and adjacent spans (no per-point work)."""
    cc = IrCharClass.from_intervals([(1, 3), (4, 6), (2, 2)])
    assert cc == IrCharClass(IrRange(IrChr(1), IrChr(6)))


def test_charclass_from_intervals_does_not_materialise_a_unicode_complement():
    """A ~1.1M-point complement cover builds via intervals without enumerating points.

    Guards the canonicaliser's merge path (round-trip included): the complement
    of a single point is two huge spans; from_intervals must construct a
    two-member class, never a million-entry member list. A tight time bound
    would flake, so the guard is structural — a handful of members, and
    intervals() ∘ from_intervals() reproduces the complement exactly.
    """
    complement = IrCharClass(IrChr("a")).complement()
    rebuilt = IrCharClass.from_intervals(complement.intervals())
    assert rebuilt == complement
    assert len(rebuilt) < 8  # spans, not ~1.1M points


def test_charclass_intervals_of_empty_class_is_empty_list():
    """intervals() on an empty IrCharClass returns []."""
    assert not IrCharClass().intervals()


def test_charclass_from_intervals_coalesces_duplicate_and_reversed_spans():
    """from_intervals() sorts and merges spans regardless of input order,
    including exact duplicates, into the minimal canonical cover."""
    cc = IrCharClass.from_intervals([(5, 9), (0, 3), (5, 9), (2, 6)])
    assert cc == IrCharClass(IrRange(IrChr(0), IrChr(9)))
    assert cc.intervals() == [(0, 9)]


def test_charclass_from_intervals_intervals_round_trip_on_normal_form():
    """from_intervals(intervals(x)) == x when x is already in normal form."""
    cls = IrCharClass(IrRange(IrChr(9), IrChr(10)), IrChr(13), IrChr(32))
    assert cls == cls.normalized()
    assert IrCharClass.from_intervals(cls.intervals()) == cls


def test_charclass_members_and_intervals_agree_on_width():
    """The total width of intervals() equals the member count from members()."""
    cls = IrCharClass.from_intervals([(0, 2), (5, 5)])
    width = sum(hi - lo + 1 for lo, hi in cls.intervals())
    assert width == len(cls.members())
