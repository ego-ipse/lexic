"""Self-locating window scan — split offsets with no sequential pass.

Windows are assigned arithmetically; each scans only its own range and
reports marks at depth RELATIVE to its window start. That is sound
because every scanned character is an anchor (no opaque interior can emit
one), so a window needs nothing to its left. An O(windows) prefix sum
rebases relative depths to absolute, and separators at the chosen
absolute depth are the split offsets. One window IS the sequential scan —
the same code path, not a second one.

That argument dies the moment a mark can hide inside a skippable region: a
window cannot know whether it BEGINS inside one. A scanner carrying such
regions therefore walks the document once, from a unit boundary to the next
— which is exactly where its regions are certified to open — and reports one
whole-document window. The walk stays exact rather than fast, and the plan
that needs it is the plan whose marks are otherwise unreadable.
"""

from __future__ import annotations

from typing import NamedTuple

from lexic.parsing.parallel.discovery.interiors import (
    Interior,
    skip_opaque,
    skip_table,
)
from lexic.parsing.parallel.roles import Roles


class Window(NamedTuple):
    """One window's scan product, relative to its own start.

    :ivar lo: The window's start offset in the document.
    :ivar delta: Net depth change across the window.
    :ivar floor: Minimum relative depth reached (how far it pops below 0).
    :ivar tail_floor: Minimum relative depth since the LAST mark (the whole
        window when there are none) — with each mark's segment floor, what
        cut validation needs: a dip between two same-depth marks means they
        sit in different containers.
    :ivar marks: ``(offset, relative depth, segment floor)`` per separator —
        the segment floor is the minimum depth since the previous mark.
    """

    lo: int
    delta: int
    floor: int
    tail_floor: int
    marks: tuple[tuple[int, int, int], ...]


def _occurrences(text: str, spelling: str, lo: int, hi: int) -> set[int]:
    """Every offset in ``[lo, hi)`` where ``spelling`` STARTS.

    The search runs past the window end by the spelling's own width so that a
    mark beginning at the last offset is still found whole, and belongs to the
    window it starts in rather than to neither.
    """
    end = hi + len(spelling) - 1
    out: set[int] = set()
    at = text.find(spelling, lo, end)
    while at != -1 and at < hi:
        out.add(at)
        at = text.find(spelling, at + 1, end)
    return out


class Scanner:
    """The role-driven structural scan for one grammar's derived roles.

    :ivar openers: Depth-increment characters.
    :ivar closers: Depth-decrement characters.
    :ivar separators: Mark spellings (roles' separators AND terminators, minus
        any whose characters also play a pair role).
    :ivar opaque: Regions that hide marks and open only where a unit begins;
        empty for every grammar whose marks are all visible, which is what
        keeps those on the windowed path.
    """

    def __init__(self, derived: Roles, opaque: tuple[Interior, ...] = ()) -> None:
        """Fix the role sets the scan classifies against."""
        self.openers = frozenset(opener for opener, _closer in derived.pairs)
        self.closers = frozenset(closer for _opener, closer in derived.pairs)
        paired = self.openers | self.closers
        self.separators = frozenset(
            mark for mark in derived.marks if not set(mark) & paired
        )
        self.opaque = opaque
        self._skips = skip_table(opaque)

    def window(self, text: str, lo: int, hi: int) -> Window:
        """Scan ``[lo, hi)`` with no knowledge of anything to its left.

        One C-level ``str.find`` sweep per role spelling, merged by sort — the
        Python loop runs only over the structural occurrences, and ``src``
        carries no regex engine. A mark that STARTS inside the window is the
        window's own, however far past the end it reaches, so a spelling
        straddling an arithmetic boundary is found exactly once.

        :param text: The whole document (windows index into it, no copies).
        :param lo: Window start.
        :param hi: Window end (exclusive).
        :returns: The window's relative-depth product.
        """
        found: list[tuple[int, int]] = []
        for char in self.openers:
            found += [(at, 1) for at in _occurrences(text, char, lo, hi)]
        for char in self.closers:
            found += [(at, -1) for at in _occurrences(text, char, lo, hi)]
        seen: set[int] = set()
        for mark in self.separators:
            seen |= _occurrences(text, mark, lo, hi)
        found += [(at, 0) for at in seen]
        found.sort()
        depth = 0
        floor = 0
        segment = 0
        marks: list[tuple[int, int, int]] = []
        for at, role in found:
            if role > 0:
                depth += 1
            elif role < 0:
                depth -= 1
                floor = min(floor, depth)
                segment = min(segment, depth)
            else:
                marks.append((at, depth, segment))
                segment = depth
        return Window(lo, depth, floor, segment, tuple(marks))

    def walk(self, text: str) -> Window:
        """Scan the whole document unit by unit, skipping opaque regions.

        Each mark ends a unit, so the character after it begins the next one
        — the only place a carried region is certified to open. Every mark
        the walk reports therefore stands outside every region, at depth 0:
        a scanner carrying regions has no pairs to count.

        :param text: The whole document.
        :returns: One window covering it, so the prefix rebase is a no-op.
        """
        marks: list[tuple[int, int, int]] = []
        at = 0
        while at < len(text):
            after = skip_opaque(text, at, self._skips.get(text[at], ()))
            found = self._next_mark(text, after) if after < len(text) else None
            if found is None:
                break
            mark, width = found
            marks.append((mark, 0, 0))
            at = mark + width
        return Window(0, 0, 0, 0, tuple(marks))

    def _next_mark(self, text: str, at: int) -> tuple[int, int] | None:
        """The first mark at or after ``at``, with its width, or ``None``."""
        found = [
            (where, len(mark))
            for mark in self.separators
            if (where := text.find(mark, at)) != -1
        ]
        return min(found) if found else None

    def offsets(self, windows: list[Window], depth: int = 0) -> list[int]:
        """Rebase window marks to absolute depth and keep those at ``depth``.

        The O(windows) prefix sum of the barrier-free design: window k's
        absolute base is the sum of deltas before it, so no window ever
        waited on another to scan.

        :param windows: The windows in document order.
        :param depth: The absolute depth split offsets must stand at.
        :returns: The split offsets, in document order.
        """
        out: list[int] = []
        running = 0
        for window in windows:
            for offset, relative, _segment in window.marks:
                if running + relative == depth:
                    out.append(offset)
            running += window.delta
        return out


def clustered(marks: list[int], width: int, trailing: bool) -> list[int]:
    """One boundary per overlapping RUN of a spelling's occurrences.

    A spelling that is its own border reads several times inside a run of its
    characters, and the grammar has one boundary there — at the run's end or at
    its start, whichever the owner's own edges settled. A one-character mark
    never overlaps, so every occurrence is its own run and this is the identity.

    :param marks: The scanned offsets, in document order.
    :param width: The mark spelling's width.
    :param trailing: Whether a run's LAST occurrence is its boundary.
    :returns: One offset per run, in document order.
    """
    if width == 1 or not marks:
        return marks
    kept: list[int] = []
    run = previous = marks[0]
    for at in marks[1:]:
        if at - previous >= width:
            kept.append(run)
            run = at
        elif trailing:
            run = at
        previous = at
    kept.append(run)
    return kept
