"""Tests for lexic.parsing.pda.core.charsets — CharSet, the pivot-1 polarity algebra.

Hand cases cover all four ``(negated, negated)`` combinations for
``union``/``subtract``/``overlaps``, the EOF sentinel convention, the
``EMPTY``/``ANY`` singletons, ``from_charclass``'s range-expansion cap, and
``from_not``'s complement semantics. A hypothesis section checks the algebra
against brute-force membership over a small alphabet extended with one
"outside" character standing in for the rest of the (effectively unbounded)
universe, so co-finite (negated) sets brute-force correctly too.
"""

from __future__ import annotations

import hypothesis.strategies as st
from hypothesis import given, settings

from lexic.ir.nodes import MAX_CODEPOINT, IrCharClass, IrChr, IrRange
from lexic.parsing.pda.core.charsets import MAX_RANGE_EXPANSION, CharSet

_A = frozenset({"a", "b"})
_B = frozenset({"b", "c"})


# ── singletons ──────────────────────────────────────────────────────────


def test_empty_singleton_has_no_members():
    """EMPTY is the positive empty set: not negated, has() nothing."""
    assert CharSet.EMPTY.is_empty()
    assert not CharSet.EMPTY.negated
    assert not CharSet.EMPTY.has("a")


def test_any_singleton_contains_every_real_char():
    """ANY is negated with no exclusions: has() every real char."""
    assert CharSet.ANY.negated
    assert CharSet.ANY.has("a")
    assert CharSet.ANY.has("\n")


def test_any_singleton_is_not_empty():
    """A negated set is never is_empty(), including ANY."""
    assert not CharSet.ANY.is_empty()


def test_any_singleton_does_not_contain_eof_sentinel():
    """ANY excludes real chars only, never EOF, so has("") is False."""
    assert not CharSet.ANY.has("")


# ── has() and the EOF sentinel ─────────────────────────────────────────


def test_has_positive_set_contains_listed_chars():
    """A positive set's has() is plain membership in chars."""
    cs = CharSet(_A, False)
    assert cs.has("a")
    assert not cs.has("c")


def test_has_negated_set_excludes_listed_chars():
    """A negated set's has() is membership in the complement of chars."""
    cs = CharSet(_A, True)
    assert not cs.has("a")
    assert cs.has("c")


def test_has_negated_set_never_contains_eof_sentinel():
    """has("") is False for any negated set, regardless of chars."""
    assert not CharSet(frozenset(), True).has("")


def test_has_positive_set_can_contain_eof_sentinel():
    """A positive set built via from_chars can carry the EOF sentinel."""
    assert CharSet.from_chars("").has("")


# ── is_empty ────────────────────────────────────────────────────────────


def test_is_empty_true_only_for_the_positive_empty_set():
    """is_empty() is True only for the positive set with no chars."""
    assert CharSet(frozenset(), False).is_empty()
    assert not CharSet(frozenset({"a"}), False).is_empty()
    assert not CharSet(frozenset(), True).is_empty()
    assert not CharSet(frozenset({"a"}), True).is_empty()


# ── union — all four polarity combinations ─────────────────────────────


def test_union_positive_positive_is_plain_set_union():
    """positive ∪ positive is plain frozenset union."""
    result = CharSet(_A, False).union(CharSet(_B, False))
    assert result == CharSet(frozenset({"a", "b", "c"}), False)


def test_union_negated_negated_intersects_the_exclusions():
    """negated ∪ negated intersects the two exclusion sets."""
    result = CharSet(_A, True).union(CharSet(_B, True))
    assert result == CharSet(frozenset({"b"}), True)


def test_union_positive_negated_shrinks_the_exclusion_by_the_positive_set():
    """positive ∪ negated removes the positive set's chars from the exclusion."""
    result = CharSet(_A, False).union(CharSet(_B, True))
    assert result == CharSet(frozenset({"c"}), True)


def test_union_negated_positive_shrinks_the_exclusion_by_the_positive_set():
    """negated ∪ positive removes the positive set's chars from the exclusion."""
    result = CharSet(_A, True).union(CharSet(_B, False))
    assert result == CharSet(frozenset({"a"}), True)


def test_union_drops_eof_when_the_result_is_negated():
    """Documented structural cap: a negated result can never carry EOF.

    ``ANY`` (negated, no exclusions) unioned with a positive set that
    includes the EOF sentinel stays negated — and therefore loses that EOF
    membership, since a negated ``CharSet.has("")`` is always ``False``. See
    ``union``'s docstring.
    """
    result = CharSet.ANY.union(CharSet.from_chars("a", ""))
    assert result.negated
    assert not result.has("")


# ── subtract — all four polarity combinations ──────────────────────────


def test_subtract_positive_positive_is_plain_set_difference():
    """positive − positive is plain frozenset difference."""
    result = CharSet(_A, False).subtract(CharSet(_B, False))
    assert result == CharSet(frozenset({"a"}), False)


def test_subtract_positive_negated_is_intersection():
    """positive − negated is intersection with the negated set's chars."""
    result = CharSet(_A, False).subtract(CharSet(_B, True))
    assert result == CharSet(frozenset({"b"}), False)


def test_subtract_positive_negated_passes_through_self_eof():
    """A negated ``other`` never removes EOF (it can never have it), so
    subtracting it always keeps ``self``'s own EOF membership.
    """
    result = CharSet.from_chars("a", "").subtract(CharSet(_A, True))
    assert result.has("")


def test_overlaps_positive_negated_ignores_eof_on_the_positive_side():
    """EOF can never be the shared member when either side is negated —
    a negated operand's ``has("")`` is always ``False``.
    """
    positive_with_eof = CharSet.from_chars("a", "")
    negated_excludes_a = CharSet(frozenset({"a"}), True)
    assert not positive_with_eof.overlaps(negated_excludes_a)


def test_subtract_negated_positive_unions_the_exclusions():
    """negated − positive unions the two exclusion sets."""
    result = CharSet(_A, True).subtract(CharSet(_B, False))
    assert result == CharSet(frozenset({"a", "b", "c"}), True)


def test_subtract_negated_negated_is_the_reverse_difference():
    """negated − negated is the reverse (other − self) chars difference."""
    result = CharSet(_A, True).subtract(CharSet(_B, True))
    assert result == CharSet(frozenset({"c"}), False)


# ── overlaps — all four polarity combinations ──────────────────────────


def test_overlaps_positive_positive_true_when_shared_char():
    """Two positive sets overlap iff they share a char."""
    assert CharSet(_A, False).overlaps(CharSet(_B, False))


def test_overlaps_positive_positive_false_when_disjoint():
    """Two disjoint positive sets do not overlap."""
    assert not CharSet(_A, False).overlaps(CharSet(frozenset({"d"}), False))


def test_overlaps_negated_negated_is_always_true_even_when_exclusions_are_disjoint():
    """Two negated sets always overlap, even with disjoint exclusions."""
    disjoint_exclusion = CharSet(frozenset({"d"}), True)
    assert CharSet(_A, True).overlaps(disjoint_exclusion)


def test_overlaps_positive_negated_true_when_positive_has_an_uncovered_char():
    """positive overlaps negated when the positive set has a char outside the exclusion."""
    assert CharSet(_A, False).overlaps(CharSet(_B, True))


def test_overlaps_positive_negated_false_when_positive_is_subset_of_the_exclusion():
    """positive does not overlap negated when it is entirely excluded."""
    assert not CharSet(_B, False).overlaps(CharSet(_B, True))


def test_overlaps_negated_positive_true_when_positive_has_an_uncovered_char():
    """negated overlaps positive when the positive set has a char outside the exclusion."""
    assert CharSet(_A, True).overlaps(CharSet(_B, False))


def test_overlaps_negated_positive_false_when_positive_equals_the_exclusion():
    """negated does not overlap positive when the positive set equals the exclusion."""
    assert not CharSet(_A, True).overlaps(CharSet(_A, False))


# ── from_charclass ──────────────────────────────────────────────────────


def test_from_charclass_expands_single_chars():
    """from_charclass expands standalone IrChr members to their glyphs."""
    cc = IrCharClass(IrChr("a"), IrChr("b"))
    assert CharSet.from_charclass(cc) == CharSet(frozenset({"a", "b"}), False)


def test_from_charclass_expands_a_range():
    """from_charclass expands an IrRange to every glyph it covers."""
    cc = IrCharClass(IrRange(IrChr("0"), IrChr("9")))
    assert CharSet.from_charclass(cc) == CharSet(frozenset("0123456789"), False)


def test_from_charclass_mixes_ranges_and_single_chars():
    """from_charclass handles a class mixing IrRange and IrChr members."""
    cc = IrCharClass(IrChr("_"), IrRange(IrChr("a"), IrChr("c")))
    assert CharSet.from_charclass(cc) == CharSet(frozenset({"_", "a", "b", "c"}), False)


def test_from_charclass_caps_a_wide_range_to_any():
    """A range roughly bisecting the code-point space is too big to enumerate
    on EITHER side (positive or complement) — the only case ANY remains."""
    cc = IrCharClass(IrRange(IrChr(0), IrChr(MAX_RANGE_EXPANSION + 2)))
    assert CharSet.from_charclass(cc) == CharSet.ANY


def test_from_charclass_cap_is_a_strict_greater_than(monkeypatch):
    """The expansion cap check is strict '>': exactly at cap still expands
    positive; one past it is too big for both sides here, so it falls to ANY."""
    monkeypatch.setattr("lexic.parsing.pda.core.charsets.MAX_RANGE_EXPANSION", 5)
    at_cap = IrCharClass(IrRange(IrChr(0), IrChr(4)))  # 5 code points
    assert CharSet.from_charclass(at_cap) == CharSet(
        frozenset(chr(c) for c in range(5)), False
    )
    over_cap = IrCharClass(IrRange(IrChr(0), IrChr(5)))  # 6 code points
    assert CharSet.from_charclass(over_cap) == CharSet.ANY


# ── from_charclass / from_not — exact beyond the cap (P1) ────────────────
#
# Reference oracle: a plain Python membership scan over the raw (lo, hi)
# ranges used to author the IrCharClass — independent of anything
# CharSet/IrCharClass compute internally (no intervals()/complement() calls
# in the oracle itself, so it can't share a bug with the code under test).


def _ranges_to_charclass(ranges: list[tuple[int, int]]) -> IrCharClass:
    return IrCharClass(
        *(IrChr(lo) if lo == hi else IrRange(IrChr(lo), IrChr(hi)) for lo, hi in ranges)
    )


def _reference_member(ranges: list[tuple[int, int]], cp: int) -> bool:
    """Independent membership oracle: brute-force scan of the raw ranges."""
    return any(lo <= cp <= hi for lo, hi in ranges)


def test_from_charclass_exact_for_a_small_positive_class():
    """A small class stays positive and exact — no cap involved."""
    ranges = [(ord("a"), ord("e")), (ord("x"), ord("x"))]
    cc = _ranges_to_charclass(ranges)
    cs = CharSet.from_charclass(cc)
    assert not cs.negated
    for cp in range(200):
        assert cs.has(chr(cp)) == _reference_member(ranges, cp)


def test_from_charclass_goes_negated_when_the_complement_is_small():
    """A near-universal class (small complement) expands the complement
    side exactly, instead of widening the whole thing to ANY."""
    gap = 0x2028  # an arbitrary interior code point excluded from the class
    ranges = [(0, gap - 1), (gap + 1, MAX_CODEPOINT)]
    cc = _ranges_to_charclass(ranges)
    cs = CharSet.from_charclass(cc)
    assert cs.negated
    assert cs.chars == frozenset({chr(gap)})
    for cp in (0, 1, gap - 1, gap, gap + 1, MAX_CODEPOINT):
        assert cs.has(chr(cp)) == _reference_member(ranges, cp)


def test_from_charclass_stays_any_when_both_sides_exceed_the_cap():
    """A range roughly bisecting the code-point space stays ANY: neither the
    positive set nor its complement fits under the expansion cap."""
    ranges = [(0, MAX_CODEPOINT // 2)]
    cc = _ranges_to_charclass(ranges)
    assert CharSet.from_charclass(cc) == CharSet.ANY


def test_from_not_exact_complement_when_inner_is_near_universal():
    """from_not exactly complements a near-universal inner class instead of
    ANY-ing — the complement of a small-complement class is small-positive."""
    gap = 0x2028
    ranges = [(0, gap - 1), (gap + 1, MAX_CODEPOINT)]
    cc = _ranges_to_charclass(ranges)
    cs = CharSet.from_not(cc)
    assert not cs.negated
    assert cs.chars == frozenset({chr(gap)})
    for cp in (0, 1, gap - 1, gap, gap + 1, MAX_CODEPOINT):
        assert cs.has(chr(cp)) == (not _reference_member(ranges, cp))


def test_from_not_stays_any_when_inner_exceeds_the_cap_on_both_sides():
    """from_not falls back to ANY only when inner's own from_charclass did."""
    ranges = [(0, MAX_CODEPOINT // 2)]
    cc = _ranges_to_charclass(ranges)
    assert CharSet.from_not(cc) == CharSet.ANY


@given(
    ranges=st.lists(
        st.tuples(st.integers(0, 500), st.integers(0, 500)).map(
            lambda pair: (min(pair), max(pair))
        ),
        min_size=1,
        max_size=6,
    )
)
@settings(max_examples=200)
def test_from_charclass_matches_reference_over_random_small_ranges(
    ranges: list[tuple[int, int]],
) -> None:
    """Brute-force fuzz: from_charclass's has() agrees with the independent
    range-scan oracle over every code point the ranges could plausibly touch,
    plus the far extreme (MAX_CODEPOINT)."""
    cc = _ranges_to_charclass(ranges)
    cs = CharSet.from_charclass(cc)
    for cp in (*range(600), MAX_CODEPOINT):
        assert cs.has(chr(cp)) == _reference_member(ranges, cp)


# ── from_not ─────────────────────────────────────────────────────────────


def test_from_not_negates_a_capped_charclass():
    """from_not negates a within-cap class's positive expansion."""
    cc = IrCharClass(IrChr('"'))
    assert CharSet.from_not(cc) == CharSet(frozenset({'"'}), True)


def test_from_not_of_an_uncapped_range_stays_any():
    """from_not of an over-cap range stays the conservative ANY."""
    cc = IrCharClass(IrRange(IrChr(0), IrChr(MAX_RANGE_EXPANSION + 2)))
    assert CharSet.from_not(cc) == CharSet.ANY


# ── from_chars ───────────────────────────────────────────────────────────


def test_from_chars_builds_an_exact_positive_set():
    """from_chars builds an exact positive set from its arguments."""
    assert CharSet.from_chars("a", "b") == CharSet(frozenset({"a", "b"}), False)


def test_from_chars_eof_sentinel_convention():
    """from_chars("") builds the EOF-only positive set."""
    eof_set = CharSet.from_chars("")
    assert eof_set.has("")
    assert not eof_set.negated


# ── hashability / equality ──────────────────────────────────────────────


def test_equal_charsets_compare_equal():
    """Two CharSets with equal chars/negated compare equal."""
    assert CharSet(frozenset({"a"}), False) == CharSet(frozenset({"a"}), False)


def test_different_polarity_is_not_equal_even_with_the_same_chars():
    """Same chars, different polarity: not equal."""
    assert CharSet(frozenset({"a"}), False) != CharSet(frozenset({"a"}), True)


def test_equal_charsets_share_a_hash():
    """Equal CharSets (chars order aside) hash the same."""
    left = CharSet(frozenset({"a", "b"}), False)
    right = CharSet(frozenset({"b", "a"}), False)
    assert hash(left) == hash(right)


def test_charset_is_usable_as_a_dict_key():
    """A CharSet works as a dict key, looked up by an equal value."""
    key = CharSet(frozenset({"a"}), False)
    table = {key: "value"}
    assert table[CharSet(frozenset({"a"}), False)] == "value"


# ── property: algebra vs. brute-force membership ────────────────────────
#
# _OUTSIDE stands in for "any character never drawn into an explicit chars
# set" — the strategy below only ever draws explicit chars from _ALPHABET/
# _EOF, so brute-forcing membership over _UNIVERSE (which adds _OUTSIDE)
# correctly exercises the co-finite (negated) case: a negated set always
# contains _OUTSIDE, a positive set never does.
#
# EOF is only ever drawn for a POSITIVE set — matching the real invariant
# (from_charclass/from_not never see "", from_chars never returns negated)
# — so a negated set here never carries "" in chars, same as production.

_ALPHABET = ("a", "b", "c", "d", "e")
_EOF = ""
_OUTSIDE = "￿"
_UNIVERSE = (*_ALPHABET, _EOF, _OUTSIDE)


@st.composite
def _charset_strategy(draw: st.DrawFn) -> CharSet:
    negated = draw(st.booleans())
    pool = _ALPHABET if negated else (*_ALPHABET, _EOF)
    chars = draw(st.frozensets(st.sampled_from(pool), max_size=4))
    return CharSet(chars, negated)


_charsets = _charset_strategy()


@given(a=_charsets, b=_charsets)
@settings(max_examples=200)
def test_union_matches_membership_up_to_the_documented_eof_cap(
    a: CharSet, b: CharSet
) -> None:
    """Union matches brute-force membership for every real character always.

    For the EOF sentinel specifically: if the union is negated, EOF is
    always absent (the documented structural cap — see ``union``'s
    docstring), never a random mismatch; otherwise EOF membership is exact
    too.
    """
    result = a.union(b)
    for ch in _UNIVERSE:
        if ch == "" and result.negated:
            assert not result.has(ch)
            continue
        assert result.has(ch) == (a.has(ch) or b.has(ch))


@given(a=_charsets, b=_charsets)
@settings(max_examples=200)
def test_subtract_matches_brute_force_membership(a: CharSet, b: CharSet) -> None:
    """subtract matches brute-force membership over the universe, EOF included."""
    result = a.subtract(b)
    for ch in _UNIVERSE:
        assert result.has(ch) == (a.has(ch) and not b.has(ch))


@given(a=_charsets, b=_charsets)
@settings(max_examples=200)
def test_overlaps_matches_brute_force_membership(a: CharSet, b: CharSet) -> None:
    """overlaps matches brute-force membership over the universe, EOF included."""
    expected = any(a.has(ch) and b.has(ch) for ch in _UNIVERSE)
    assert a.overlaps(b) == expected


@given(a=_charsets, b=_charsets)
@settings(max_examples=200)
def test_subtract_is_intersection_with_the_real_char_complement(
    a: CharSet, b: CharSet
) -> None:
    """De Morgan-ish: ``a - b == a`` intersected with ``b``'s complement.

    Polarity-flipping a ``CharSet`` is a genuine set complement only over
    *real* characters — a negated set never contains the EOF sentinel by
    design (module docstring), so ``""`` is excluded from this check.
    """
    b_complement = CharSet(b.chars, not b.negated)
    result = a.subtract(b)
    for ch in (*_ALPHABET, _OUTSIDE):
        assert result.has(ch) == (a.has(ch) and b_complement.has(ch))
