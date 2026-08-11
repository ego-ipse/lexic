"""The two planes of text — the reader, and the document it reads.

Both are the same surface with different answers: what text, scrolled where,
which lines are lit, and whether a hand can change it.
"""

from __future__ import annotations

from opsis.frame.marks import ROW, Frame
from opsis.surfaces.surface import Box, Surface
from praxis.view import View

__all__ = ["Document", "Plane", "Reader"]

GUTTER = 46.0


def _widest(lines: list[str]) -> int:
    return max((len(line) for line in lines), default=1)


class Plane(Surface):
    """A block of text, read line by line, clipped to its column."""

    numbered = False
    kind = "line"

    def text(self, view: View) -> str:
        raise NotImplementedError

    def top(self, view: View) -> int:
        """Which line is at the top of the column."""
        raise NotImplementedError

    def lit(self, view: View) -> set[int]:
        """Lines the cursor is standing inside, if any are."""
        return set()

    def room(self, view: View) -> tuple[int, int]:
        lines = self.text(view).split("\n")
        return _widest(lines), len(lines)

    def draw(self, said: Frame, box: Box, view: View) -> None:
        x, y, w, h = box
        lines = self.text(view).split("\n")
        first, lit = self.top(view), self.lit(view)
        run = GUTTER if self.numbered else 10.0
        for i in range(max(0, int(h // ROW))):
            at = first + i
            top = y + 4 + i * ROW
            if at >= len(lines) or top + ROW > y + h:
                break
            if at in lit:
                said.box(x, top, w, ROW, "lit")
            if self.numbered:
                said.text(x + 6, top + ROW - 5, "dimmer", str(at + 1), GUTTER - 10)
            said.text(x + run, top + ROW - 5, "ink", lines[at], w - run - 8)
            said.hit(x, top, w, ROW, self.kind, str(at))


class Reader(Plane):
    """The grammar — the ground truth this reading is under."""

    name = "grammar"
    title = "THE READER · grammar is the ground truth"
    column = "reader"
    relation = "tabbed"
    kind = "readerline"

    def text(self, view: View) -> str:
        return view.reading.reader_text

    def top(self, view: View) -> int:
        return view.looking.reader_top

    def lit(self, view: View) -> set[int]:
        return view.lit_lines


class Document(Plane):
    """The real text — the thing being read."""

    name = "document"
    title = "THE DOCUMENT · real text — select it"
    numbered = True

    def text(self, view: View) -> str:
        return view.reading.text

    def top(self, view: View) -> int:
        return view.looking.doc_top
