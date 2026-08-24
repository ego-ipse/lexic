"""Code-point sets, and the partition that makes a two-tier lexer possible.

A scannerless grammar names overlapping character classes freely — GBNF has
`cmchar = [^\\n]` and `namehead = [A-Za-z_]`, and the letter `a` is in both. An
Earley or PEG engine reads them in context and never notices. A LEXER cannot: it
assigns `a` one token type before the parser is consulted, and whichever class
wins, the other can never match again.

Minting one token per class is therefore not a translation, it is a coin flip.
The fix is standard and mechanical: refine the classes into the coarsest
partition that respects all of them, give each BLOCK a token, and let a class be
the alternation of its blocks. Every character then has exactly one token type,
the lexer is deterministic, and no class loses.

Sets are closed inclusive intervals over the Unicode range, kept sorted and
disjoint so membership and complement stay cheap.
"""

from __future__ import annotations

from bisect import bisect_right
from collections.abc import Iterable

MAX_POINT = 0x10FFFF
"""The last Unicode code point; the universe every complement is taken in."""

Interval = tuple[int, int]
CharSet = tuple[Interval, ...]
"""Sorted, disjoint, inclusive intervals. `()` is the empty set."""


def normalized(intervals: Iterable[Interval]) -> CharSet:
    """Sort and merge ``intervals``, coalescing anything touching or overlapping."""
    out: list[Interval] = []
    for lo, hi in sorted(intervals):
        if out and lo <= out[-1][1] + 1:
            out[-1] = (out[-1][0], max(out[-1][1], hi))
        else:
            out.append((lo, hi))
    return tuple(out)


def of_points(points: Iterable[str]) -> CharSet:
    """The set holding exactly ``points``, consecutive ones folded into ranges."""
    return normalized((ord(char), ord(char)) for char in points)


def complement(charset: CharSet) -> CharSet:
    """Every code point ``charset`` does not hold."""
    out: list[Interval] = []
    cursor = 0
    for lo, hi in charset:
        if cursor < lo:
            out.append((cursor, lo - 1))
        cursor = hi + 1
    if cursor <= MAX_POINT:
        out.append((cursor, MAX_POINT))
    return tuple(out)


def holds(charset: CharSet, point: int) -> bool:
    """Whether ``charset`` holds ``point``."""
    index = bisect_right(charset, (point, MAX_POINT + 1)) - 1
    return index >= 0 and charset[index][1] >= point


def overlap(left: CharSet, right: CharSet) -> bool:
    """Whether two sets share any code point."""
    return any(
        lo <= other_hi and other_lo <= hi
        for lo, hi in left
        for other_lo, other_hi in right
    )


def partition(sets: list[CharSet]) -> tuple[list[CharSet], list[list[int]]]:
    """Refine ``sets`` into disjoint blocks, and say which blocks each is made of.

    Two code points share a block exactly when the same input sets hold them,
    which is the coarsest refinement keeping every set expressible — so the block
    count follows the grammar's real distinctions, not the size of the Unicode
    range. Code points no set holds get no block: they are not in the language
    and no token should accept them.

    :param sets: The character classes the emitted grammar needs.
    :returns: ``(blocks, members)`` — the disjoint blocks, and per input set the
        indices of the blocks whose union it is.
    """
    edges = {0, MAX_POINT + 1}
    for charset in sets:
        for lo, hi in charset:
            edges.add(lo)
            edges.add(hi + 1)
    points = sorted(edges)
    grouped: dict[frozenset[int], list[Interval]] = {}
    for start, stop in zip(points, points[1:]):
        signature = frozenset(i for i, s in enumerate(sets) if holds(s, start))
        if signature:
            grouped.setdefault(signature, []).append((start, stop - 1))
    signatures = list(grouped)
    blocks = [normalized(grouped[sig]) for sig in signatures]
    members = [
        [b for b, sig in enumerate(signatures) if i in sig] for i in range(len(sets))
    ]
    return blocks, members
