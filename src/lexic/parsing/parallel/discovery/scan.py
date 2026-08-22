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


class Scanner:
    """The role-driven structural scan for one grammar's derived roles.

    :ivar openers: Depth-increment characters.
    :ivar closers: Depth-decrement characters.
    :ivar separators: Mark characters (roles' separators AND terminators,
        minus any that also play a pair role).
    :ivar opaque: Regions that hide marks and open only where a unit begins;
        empty for every grammar whose marks are all visible, which is what
        keeps those on the windowed path.
    """

    def __init__(self, derived: Roles, opaque: tuple[Interior, ...] = ()) -> None:
        """Fix the role character sets the scan classifies against."""
        self.openers = frozenset(opener for opener, _closer in derived.pairs)
        self.closers = frozenset(closer for _opener, closer in derived.pairs)
        self.separators = derived.marks - self.openers - self.closers
        self.opaque = opaque
        self._chars = tuple(self.openers | self.closers | self.separators)
        self._skips = skip_table(opaque)

    def window(self, text: str, lo: int, hi: int) -> Window:
        """Scan ``[lo, hi)`` with no knowledge of anything to its left.

        One C-level ``str.find`` sweep per role character, merged by sort —
        the Python loop runs only over the structural occurrences, and
        ``src`` carries no regex engine.

        :param text: The whole document (windows index into it, no copies).
        :param lo: Window start.
        :param hi: Window end (exclusive).
        :returns: The window's relative-depth product.
        """
        offsets: list[int] = []
        for char in self._chars:
            at = text.find(char, lo, hi)
            while at != -1:
                offsets.append(at)
                at = text.find(char, at + 1, hi)
        offsets.sort()
        depth = 0
        floor = 0
        segment = 0
        marks: list[tuple[int, int, int]] = []
        for at in offsets:
            char = text[at]
            if char in self.openers:
                depth += 1
            elif char in self.closers:
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
            mark = self._next_mark(text, after) if after < len(text) else -1
            if mark < 0:
                break
            marks.append((mark, 0, 0))
            at = mark + 1
        return Window(0, 0, 0, 0, tuple(marks))

    def _next_mark(self, text: str, at: int) -> int:
        """The first mark character at or after ``at``, or ``-1``."""
        found = [
            where for char in self.separators if (where := text.find(char, at)) != -1
        ]
        return min(found) if found else -1

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
