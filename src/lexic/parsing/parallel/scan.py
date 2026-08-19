"""Self-locating window scan — split offsets with no sequential pass.

Windows are assigned arithmetically; each scans only its own range and
reports marks at depth RELATIVE to its window start. That is sound
because every scanned character is an anchor (no opaque interior can emit
one), so a window needs nothing to its left. An O(windows) prefix sum
rebases relative depths to absolute, and separators at the chosen
absolute depth are the split offsets. One window IS the sequential scan —
the same code path, not a second one.
"""

from __future__ import annotations

from typing import NamedTuple

from lexic.parsing.parallel.roles import Roles


class Window(NamedTuple):
    """One window's scan product, relative to its own start.

    :ivar lo: The window's start offset in the document.
    :ivar delta: Net depth change across the window.
    :ivar floor: Minimum relative depth reached (how far it pops below 0).
    :ivar marks: ``(offset, relative depth)`` per separator occurrence.
    """

    lo: int
    delta: int
    floor: int
    marks: tuple[tuple[int, int], ...]


class Scanner:
    """The role-driven structural scan for one grammar's derived roles.

    :ivar openers: Depth-increment characters.
    :ivar closers: Depth-decrement characters.
    :ivar separators: Mark characters (roles' separators minus pair chars).
    """

    def __init__(self, derived: Roles) -> None:
        """Fix the role character sets the scan classifies against."""
        self.openers = frozenset(opener for opener, _closer in derived.pairs)
        self.closers = frozenset(closer for _opener, closer in derived.pairs)
        self.separators = derived.separators - self.openers - self.closers
        self._chars = tuple(self.openers | self.closers | self.separators)

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
        marks: list[tuple[int, int]] = []
        for at in offsets:
            char = text[at]
            if char in self.openers:
                depth += 1
            elif char in self.closers:
                depth -= 1
                floor = min(floor, depth)
            else:
                marks.append((at, depth))
        return Window(lo, depth, floor, tuple(marks))

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
            for offset, relative in window.marks:
                if running + relative == depth:
                    out.append(offset)
            running += window.delta
        return out
