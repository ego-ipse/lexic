"""The structural scan — where a document's marks stand at depth 0.

Every scanned character is an anchor (no opaque interior can emit one), so the
depth at any offset is a COUNT: openers minus closers before it, which
``str.count`` answers at C speed with no Python step per occurrence. That is
what lets a cut search read only the text near its targets: the depth at a
stretch's start is counted, and only the stretch itself is walked.

That argument dies the moment a mark can hide inside a skippable region: a
count cannot know whether an offset lies inside one. A scanner carrying such
regions therefore walks the document once, from a unit boundary to the next —
which is exactly where its regions are certified to open. The walk stays exact
rather than fast, and the plan that needs it is the plan whose marks are
otherwise unreadable.
"""

from __future__ import annotations

from typing import NamedTuple

from lexic.ir import IrAst
from lexic.parsing.parallel.discovery.interiors import (
    Interior,
    skip_opaque,
    skip_table,
)
from lexic.parsing.parallel.discovery.shapes import first_charset, last_charset
from lexic.parsing.parallel.roles import Roles


def spelling_offsets(text: str, spelling: str, lo: int, hi: int) -> list[int]:
    """Every offset in ``[lo, hi)`` where ``spelling`` STARTS, ascending.

    The search runs past the window end by the spelling's own width so that a
    mark beginning at the last offset is still found whole, and belongs to the
    window it starts in rather than to neither.
    """
    end = hi + len(spelling) - 1
    out: list[int] = []
    at = text.find(spelling, lo, end)
    while at != -1 and at < hi:
        out.append(at)
        at = text.find(spelling, at + 1, end)
    return out


def occurrences(text: str, spelling: str, lo: int, hi: int) -> int:
    """How many times ``spelling`` STARTS in ``[lo, hi)`` — a C-level count
    for one character, :func:`spelling_offsets` for a longer spelling, which
    may overlap itself where ``str.count`` would not."""
    if len(spelling) == 1:
        return text.count(spelling, lo, hi)
    return len(spelling_offsets(text, spelling, lo, hi))


class Scanner:
    """The role-driven structural scan for one grammar's derived roles.

    :ivar openers: Depth-increment characters.
    :ivar closers: Depth-decrement characters.
    :ivar separators: Mark spellings (roles' separators AND terminators, minus
        any whose characters also play a pair role).
    :ivar flat: Whether there is no pair to open or close, so every mark stands
        at depth 0 and no depth is ever counted.
    :ivar opaque: Regions that hide marks and open only where a unit begins;
        empty for every grammar whose marks are all visible, which is what
        keeps those on the windowed path.
    """

    def __init__(self, derived: Roles, opaque: tuple[Interior, ...] = ()) -> None:
        """Fix the role sets the scan classifies against."""
        self.openers = frozenset(opener for opener, _closer in derived.pairs)
        self.closers = frozenset(closer for _opener, closer in derived.pairs)
        paired = self.openers | self.closers
        self.flat = not paired
        self.separators = frozenset(
            mark for mark in derived.marks if not set(mark) & paired
        )
        self.opaque = opaque
        self._skips = skip_table(opaque)

    def drift(self, text: str, lo: int, hi: int) -> int:
        """Net depth change across ``[lo, hi)``: openers minus closers that
        start there, counted rather than walked."""
        opened = sum(occurrences(text, char, lo, hi) for char in self.openers)
        return opened - sum(occurrences(text, char, lo, hi) for char in self.closers)

    def level(self, text: str, lo: int, hi: int, base: int) -> list[int]:
        """The separators starting in ``[lo, hi)`` that stand at depth 0,
        ascending, given the depth ``base`` at ``lo``.

        One ``str.find`` sweep per role spelling, merged by sort; the Python
        loop runs only over the stretch's own structural occurrences. A mark
        that STARTS in the stretch is its own, however far past ``hi`` it
        reaches. A grammar with no pair has no depth to count: every mark
        stands at 0, and a scanner with no separator can report none, for any
        document — which its vocabulary says before any text is read.

        :param text: The whole document (stretches index into it, no copies).
        :param lo: Stretch start.
        :param hi: Stretch end (exclusive).
        :param base: The absolute depth at ``lo``.
        :returns: The depth-0 separator offsets in the stretch.
        """
        if not self.separators:
            return []
        found = [spelling_offsets(text, mark, lo, hi) for mark in self.separators]
        merged = found[0] if len(found) == 1 else sorted(set().union(*found))
        if self.flat:
            return merged
        events = [(at, 0) for at in merged]
        for char in self.openers:
            events += [(at, 1) for at in spelling_offsets(text, char, lo, hi)]
        for char in self.closers:
            events += [(at, -1) for at in spelling_offsets(text, char, lo, hi)]
        events.sort()
        depth = base
        level: list[int] = []
        for at, role in events:
            depth += role
            if not role and not depth:
                level.append(at)
        return level

    def walk(self, text: str) -> list[int]:
        """Scan the whole document unit by unit, skipping opaque regions.

        Each mark ends a unit, so the character after it begins the next one
        — the only place a carried region is certified to open. Every mark
        the walk reports therefore stands outside every region, at depth 0:
        a scanner carrying regions has no pairs to count.

        :param text: The whole document.
        :returns: Every mark, ascending — each at depth 0.
        """
        marks: list[int] = []
        at = 0
        while at < len(text):
            after = skip_opaque(text, at, self._skips.get(text[at], ()))
            found = self._next_mark(text, after) if after < len(text) else None
            if found is None:
                break
            mark, width = found
            marks.append(mark)
            at = mark + width
        return marks

    def _next_mark(self, text: str, at: int) -> tuple[int, int] | None:
        """The first mark at or after ``at``, with its width, or ``None``."""
        found = [
            (where, len(mark))
            for mark in self.separators
            if (where := text.find(mark, at)) != -1
        ]
        return min(found) if found else None


class Overlap(NamedTuple):
    """How a mark's own overlapping occurrences sit around a true boundary.

    A spelling whose prefix is also its suffix reads more than once in a run of
    its characters, and all but one of those readings is false.

    :ivar decided: Whether one occurrence of a run is identifiable at all.
    :ivar trailing: Whether that occurrence is the run's LAST.
    """

    decided: bool
    trailing: bool


def mark_overlap(grammar: IrAst, owner: str, mark: str) -> Overlap:
    """Which occurrence of an overlapping run is the grammar's boundary.

    Text ending with the mark's border pushes the run LEFT of the boundary, so
    the boundary is its last occurrence; text beginning with the border pushes
    it right, so the boundary is the first. An owner able to do both leaves
    nothing to say where, and the plan declines. A mark that is not its own
    border never overlaps.

    :param grammar: The analysis view.
    :param owner: The repeated unit the mark separates.
    :param mark: The mark spelling.
    :returns: The verdict — the caller drops an undecided plan.
    """
    if len(mark) < 2 or mark[0] != mark[1]:
        return Overlap(True, False)
    rules = {str(rule.name): rule for rule in grammar.rules}
    target = rules.get(owner)
    if target is None:
        return Overlap(False, False)
    path = frozenset({owner})
    ends = any(
        last_charset(tuple(arm), rules, path).has(mark[0]) for arm in target.body
    )
    begins = any(
        first_charset(tuple(arm), rules, path).has(mark[1]) for arm in target.body
    )
    return Overlap(False, False) if ends and begins else Overlap(True, ends)
