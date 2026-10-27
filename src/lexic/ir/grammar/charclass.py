"""The character-set node and its interval algebra.

:class:`IrCharClass` is a grammar atom over code points, built of
:class:`IrRange` spans and single :class:`~lexic.ir.spine.scalars.IrChr`
points. Its set questions — the coalesced interval cover, complement, the
canonical form, sampling, and how it is spelled inside a regex class — are the
node's own, and they all work in the interval domain, never point by point,
because a negated class spans most of Unicode.
"""

from __future__ import annotations

import random
from bisect import bisect_right
from collections.abc import Container, Iterable, Sequence
from typing import ClassVar

from lexic.ir.grammar.nodes import IrBounds
from lexic.ir.spine.records import IrSeq
from lexic.ir.spine.scalars import IrChr
from lexic.ir.spine.spine import IrAtom, IrNone, IrNoneType

__all__ = ["IrCharClass", "IrRange", "MAX_CODEPOINT"]

MAX_CODEPOINT = 0x10FFFF
"""Highest Unicode code point — the upper bound of a char-class complement."""

_SURROGATE_LO = 0xD800
_SURROGATE_HI = 0xDFFF
"""The UTF-16 surrogate block — excised from :meth:`IrCharClass.sample`'s
interval choices (a lone surrogate has no valid UTF-8 encoding)."""

_CLASS_METACHARS = frozenset("[]^-")
"""Regex-class metacharacters that need a backslash inside ``[...]``.

``-`` is positional in Python ``re`` (literal only at class start/end), and a
bare ``--`` reads as set difference in some regex engines — a range whose LOW
BOUND is ``-`` (e.g. ``[!&--.]``) silently corrupts the class there. Escaping
the dash unconditionally is valid everywhere and position-independent."""


def _escape_regex_point(point: int) -> str:
    """Escape a single code point for safe use inside a regex ``[...]``.

    :param point: The code point to escape.
    :returns: The escaped single-member text (``\\\\``/``\\xNN``/glyph).
    """
    ch = chr(point)
    if ch == "\\":
        return "\\\\"
    if ch in _CLASS_METACHARS:
        return f"\\{ch}"
    if ch.isprintable():
        return ch
    if point <= 0xFF:
        return f"\\x{point:02x}"
    if point <= 0xFFFF:
        return f"\\u{point:04x}"
    return f"\\U{point:08x}"


class IrRange(IrBounds):
    """Inclusive char range — ``IrChr`` code-point endpoints, always closed.

    Endpoints are required (no defaults): a range is always built from explicit
    code points, so there is no placeholder bound.
    """

    _child_attrs: ClassVar[tuple[str, ...]] = ()
    lo: IrChr
    hi: IrChr


class IrCharClass(IrSeq[IrRange | IrChr], IrAtom):
    """Character class over code points — ``IrRange`` spans and single ``IrChr``.

    The node IS its element tuple: :class:`IrRange` entries for explicit
    ``x-y`` ranges, single :class:`~lexic.ir.base.IrChr` code points otherwise —
    ``[a0-9]`` → ``IrCharClass(IrChr("a"), IrRange(IrChr("0"), IrChr("9")))``.

    Brackets are NOT stored — the flavour renderer emits them. Negation is NOT
    stored — ``[^...]`` parses to ``IrNot(IrCharClass(...))``; the negation hands
    its mark to the class action via the argument channel. Glyph/escape spelling
    happens only at emit time, per flavour.

    Member/complement math is intrinsic: :meth:`pattern` renders the flat
    regex interior, :meth:`members` enumerates covered code points, and
    :meth:`normalized`/:meth:`complement` produce the canonical set-form and
    Unicode complement the canonicaliser relies on.
    """

    def pattern(self) -> str:
        """Flatten to a regex/source-safe interior pattern (per-member escaped).

        Each member is a code point (or a code-point range); every point is
        escaped on its own value — regex metacharacters get a backslash, a bare
        backslash doubles, non-printable points become ``\\xNN`` / ``\\uNNNN`` /
        ``\\UNNNNNNNN``.

        :returns: The flat interior pattern, members escaped for a regex class.
        """
        parts: list[str] = []
        for el in self:
            if isinstance(el, IrRange):
                parts.append(
                    f"{_escape_regex_point(int(el.lo))}-{_escape_regex_point(int(el.hi))}"
                )
            else:
                parts.append(_escape_regex_point(int(el)))
        return "".join(parts)

    def sample(self, rng: random.Random) -> int:
        """Pick one covered code point uniformly, without materialising members.

        A complement class can span the whole Unicode range; enumerating its
        members would be prohibitive, so this samples by interval instead. The
        UTF-16 surrogate block (U+D800-U+DFFF) is excluded from the intervals
        sampled from — a lone surrogate has no valid UTF-8 encoding, so
        ``chr()`` of one would fail a text round-trip.

        :param rng: The random source.
        :returns: A covered code point.
        """
        intervals = self._desurrogated_intervals()
        sizes = [hi - lo + 1 for lo, hi in intervals]
        lo, hi = rng.choices(intervals, weights=sizes)[0]
        return rng.randint(lo, hi)

    def _desurrogated_intervals(self) -> "list[tuple[int, int]]":
        """The interval cover with the UTF-16 surrogate block excised.

        An interval straddling the block splits into its two flanking pieces;
        one wholly inside the block is dropped. Falls back to the raw cover in
        the degenerate all-surrogate case, so ``sample`` never raises on an
        empty choice set. The represented set itself (:meth:`intervals`,
        :meth:`complement`, :meth:`members`, :meth:`normalized`) is unaffected —
        only sampling avoids the block.

        :returns: The interval cover, surrogate points removed.
        """
        cleaned: list[tuple[int, int]] = []
        for lo, hi in self.intervals():
            if hi < _SURROGATE_LO or lo > _SURROGATE_HI:
                cleaned.append((lo, hi))
                continue
            if lo < _SURROGATE_LO:
                cleaned.append((lo, _SURROGATE_LO - 1))
            if hi > _SURROGATE_HI:
                cleaned.append((_SURROGATE_HI + 1, hi))
        return cleaned or self.intervals()

    def members(self) -> list[int]:
        """Enumerate every code point the class covers, in element order.

        Ranges expand to all endpoints inclusive; single ``IrChr`` members
        contribute one point each.

        .. warning::
           Do **not** call on a Unicode-scale class (e.g. a ``[^...]``
           complement, which can span ~1.1M points): the returned list holds
           one entry per covered point. Set/merge math should go through
           :meth:`intervals` / :meth:`from_intervals`, which stay in the
           interval domain.

        :returns: The covered code points, ranges expanded.
        """
        points: list[int] = []
        for el in self:
            if isinstance(el, IrRange):
                points.extend(range(int(el.lo), int(el.hi) + 1))
            else:
                points.append(int(el))
        return points

    @staticmethod
    def _coalesce(raw: list[tuple[int, int]]) -> list[tuple[int, int]]:
        """Sort ``raw`` spans and merge overlapping/adjacent ones into a cover.

        The single home for the interval merge algorithm — :meth:`intervals`
        and :meth:`from_intervals` both call it, and so does the canonicaliser
        (via those). Shared so the sort+merge lives in exactly one place.

        :param raw: Unordered ``(lo, hi)`` inclusive spans (may overlap).
        :returns: The minimal sorted disjoint cover.
        """
        merged: list[tuple[int, int]] = []
        for lo, hi in sorted(raw):
            if merged and lo <= merged[-1][1] + 1:
                merged[-1] = (merged[-1][0], max(merged[-1][1], hi))
            else:
                merged.append((lo, hi))
        return merged

    def intervals(self) -> list[tuple[int, int]]:
        """Return the sorted, coalesced ``(lo, hi)`` inclusive interval cover.

        Overlapping or adjacent spans merge, so the result is a minimal
        disjoint cover of the class in ascending code-point order. This is the
        Unicode-safe view of the class's membership — it never materialises
        individual points, so it is the right basis for set/merge math.

        :returns: The minimal sorted interval cover.
        """
        raw: list[tuple[int, int]] = []
        for el in self:
            if isinstance(el, IrRange):
                raw.append((int(el.lo), int(el.hi)))
            else:
                raw.append((int(el), int(el)))
        return self._coalesce(raw)

    @classmethod
    def from_intervals(cls, spans: Iterable[tuple[int, int]]) -> IrCharClass:
        """Build a normalised class from ``(lo, hi)`` intervals, coalescing first.

        Members are constructed directly (``IrChr`` for a single point, an
        ``IrRange`` for a wider span) from the coalesced cover — no per-point
        materialisation. The result is already in :meth:`normalized` form.

        :param spans: ``(lo, hi)`` inclusive intervals (may overlap/repeat).
        :returns: The canonical-form class over the union of ``spans``.
        """
        return cls(*(cls._span(lo, hi) for lo, hi in cls._coalesce(list(spans))))

    @staticmethod
    def _span(lo: int, hi: int) -> IrRange | IrChr:
        """A single code point renders as ``IrChr``; a wider span as ``IrRange``."""
        return IrChr(lo) if lo == hi else IrRange(IrChr(lo), IrChr(hi))

    def vanishes(self, nullable: Container[str]) -> bool:
        """A character class always matches one character — never nothing."""
        return False

    def normalized(self) -> "IrCharClass":
        """Return the canonical set-form — deduped, sorted, ranges coalesced.

        Members are collapsed to their minimal disjoint interval cover; each
        run of one code point becomes an ``IrChr``, each wider run an
        ``IrRange``. Two classes describing the same set compare equal after
        this.

        :returns: The canonical-form character class.
        """
        return IrCharClass(*(self._span(lo, hi) for lo, hi in self.intervals()))

    @property
    def is_any(self) -> bool:
        """Whether this class covers the whole Unicode range — the ``.`` class.

        ``.`` (any character) canonicalises to the positive full-span class
        ``[0, MAX_CODEPOINT]`` (via ``IrNot(IrCharClass())`` → :meth:`complement`),
        indistinguishable in the IR from ``[^]`` or ``[\\x00-\\U0010ffff]``. A
        flavour whose surface has an any-char token (GBNF ``.``) reads this to
        restore that spelling on emit.

        :returns: ``True`` iff the coalesced cover is exactly ``[(0, MAX_CODEPOINT)]``.
        """
        return self.intervals() == [(0, MAX_CODEPOINT)]

    @property
    def is_empty(self) -> bool:
        """Whether this class has no members — the empty set.

        ``IrNot(IrCharClass())`` (the raw, un-canonicalised parse of ``.`` /
        ``[^]``) negates the empty class, so it denotes any character; a flavour
        with a ``.`` surface reads this on emit to restore that spelling even off
        the non-canonical ``parse_grammar`` seam (the canonical full-span form is
        :meth:`is_any`).

        :returns: ``True`` iff the class has no ``IrRange``/``IrChr`` members.
        """
        return len(self) == 0

    def complement(self) -> "IrCharClass":
        """Return the positive canonical-form class over the Unicode complement.

        The complement is taken against ``[0, MAX_CODEPOINT]`` — every code
        point NOT in this class, as coalesced ``IrRange``/``IrChr`` spans. Used
        by the canonicaliser to rewrite ``IrNot(charclass)`` to positive spans
        (ABNF cannot express negation).

        :returns: The complement class in canonical form.
        """
        spans: list[IrRange | IrChr] = []
        cursor = 0
        for lo, hi in self.intervals():
            if lo > cursor:
                spans.append(self._span(cursor, lo - 1))
            cursor = max(cursor, hi + 1)
        if cursor <= MAX_CODEPOINT:
            spans.append(self._span(cursor, MAX_CODEPOINT))
        return IrCharClass(*spans)

    def holds(self, point: int) -> bool:
        """Whether code point ``point`` is a member."""
        return self.cover_holds(self.intervals(), point)

    @staticmethod
    def cover_holds(cover: Sequence[tuple[int, int]], point: int) -> bool:
        """Whether ``point`` lies in a sorted, coalesced cover — one bisect."""
        at = bisect_right(cover, (point, MAX_CODEPOINT + 1)) - 1
        return at >= 0 and cover[at][1] >= point

    def meets(self, other: IrCharClass) -> bool:
        """Whether the two classes share a code point — one merge walk."""
        a, b = self.intervals(), other.intervals()
        i = j = 0
        while i < len(a) and j < len(b):
            if a[i][1] < b[j][0]:
                i += 1
            elif b[j][1] < a[i][0]:
                j += 1
            else:
                return True
        return False

    def within(self, other: IrCharClass) -> bool:
        """Whether every member is also ``other``'s — one merge walk."""
        b, j = other.intervals(), 0
        for lo, hi in self.intervals():
            while j < len(b) and b[j][1] < lo:
                j += 1
            if j == len(b) or b[j][0] > lo or b[j][1] < hi:
                return False
        return True

    def listed(self, cap: int) -> tuple[frozenset[str], bool] | IrNoneType:
        """``(members, False)`` when at most ``cap`` points are members, else
        ``(non-members, True)`` when at most ``cap`` are not, else ``IrNone``."""
        for side, negated in ((self, False), (self.complement(), True)):
            spans = side.intervals()
            if sum(hi - lo + 1 for lo, hi in spans) <= cap:
                points = (chr(p) for lo, hi in spans for p in range(lo, hi + 1))
                return frozenset(points), negated
        return IrNone
