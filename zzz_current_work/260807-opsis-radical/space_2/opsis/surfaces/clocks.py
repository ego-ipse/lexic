"""The derivation and the spine — the reading against time.

The derivation is drawn on a clock, and which clock is a property of the
surface, not a mode of the instrument: the model's own spans, the predictive
run, or every hypothesis Earley held. The spine is read AT the cursor the
derivation is scrubbing, which is why it shares that column.
"""

from __future__ import annotations

from opsis.frame.marks import ROW, Frame
from opsis.frame.tones import runs
from opsis.paint import Drawing, band_drawing, chart_drawing, clock_drawing, packed
from opsis.surfaces.surface import Box, Surface
from praxis.memory import Memory
from praxis.view import View

__all__ = ["CLOCKS", "Derivation", "Spine"]

CLOCKS = ("model", "pda", "earley")
PITCH = 5.0


DRAWN: Memory[list[tuple[int, int, float, float, str]]] = Memory()
BANDS: Memory[Drawing] = Memory()


def _on(view: View, which: str, tall: int) -> list[tuple[int, int, float, float, str]]:
    """The derivation as the clock it is read against — as spans, ready to place.

    Read off the drawing ONCE: a frame that re-splits fifty thousand mark
    strings to move a cursor six pixels is the difference between an
    instrument and a slideshow.
    """
    key = f"{view.reading.stamp}:{which}:{tall}"
    return DRAWN.once(key, lambda: _spans(_draw(view, which, tall)))


def _spans(drawn: Drawing) -> list[tuple[int, int, float, float, str]]:
    """A clock's boxes as what they mean: from, to, lane top, lane height, tone."""
    out: list[tuple[int, int, float, float, str]] = []
    for mark in drawn.marks:
        p = mark.split(" ")
        if p[0] != "box":
            continue
        s0, e0, _index = (int(n) for n in p[6].split(":"))
        out.append((s0, e0, float(p[2]), float(p[4]), p[5]))
    return out


def _draw(view: View, which: str, tall: int) -> Drawing:
    """Which clock, drawn — three answers, one shape."""
    across = len(view.reading.text)
    if view.machine is not None and which == "pda":
        rows = [(s0, e0, d0, ok) for s0, e0, d0, _n, ok, _seat in view.watched()]
        return clock_drawing(rows, across, tall)
    if view.machine is not None and which == "earley":
        return clock_drawing(packed(view.held()), across, tall)
    return chart_drawing(view.reading, tall)


def _standing(s0: int, e0: int, at: float, first: int, last: int) -> str:
    """What a span is to the cursor — done, happening, enclosing, or ahead.

    A span you are INSIDE is context: it runs off both edges of the window and
    filling it amber says nothing except that everything is amber. What is
    happening is what starts or ends where you are standing.
    """
    if e0 <= at:
        return "closed"
    if s0 > at:
        return "ahead"
    return "open" if s0 < first and e0 > last else "live"


class Derivation(Surface):
    """Text is the time axis — every span the reader built, where it built it."""

    name = "chart"
    title = "THE DERIVATION · text is the time axis"
    column = "derivation"
    relation = "stacked"

    def room(self, view: View) -> tuple[int, int]:
        deep = max((span.depth for span in view.reading.spans), default=0) + 1
        widest = max((len(line) for line in view.reading.text.split("\n")), default=1)
        return max(widest, deep * 4), deep

    def draw(self, said: Frame, box: Box, view: View) -> None:
        x, y, w, h = box
        band = BANDS.once(
            f"{view.reading.stamp}",
            lambda: band_drawing(view.reading, 18, None, "model"),
        )
        # the band says WHERE in the document, so it takes the whole width
        # and keeps its own height: 14px of strip, not a stretched block
        said.place(band, x, y + 4, w / max(1.0, band.wide), 14.0 / max(1.0, band.tall))
        self._chips(said, x + 6, y + 26, view)
        drawn = _on(view, view.looking.clock, max(20, int(h - 52)))
        self._lanes(said, drawn, box, view)

    def _chips(self, said: Frame, x: float, y: float, view: View) -> None:
        """Which clock the derivation is read on — the surface's own property."""
        for name in CLOCKS:
            here = name == view.looking.clock
            room = runs("label", name) + 18
            said.box(x, y, room, 15, "lit" if here else "panel")
            said.text(x + 9, y + 11, "ink" if here else "dim", name, room - 12)
            said.hit(x, y, room, 15, "clock", name)
            x += room + 4

    def _lanes(
        self,
        said: Frame,
        spans: list[tuple[int, int, float, float, str]],
        box: Box,
        view: View,
    ) -> None:
        """The spans, in document coordinates, through the window on screen."""
        x, y, w, h = box
        at, text = view.at, view.reading.text
        window = max(8, int((w - 12) / PITCH))
        start = max(0, min(int(at) - int(window * 0.6), max(0, len(text) - window)))
        for s0, e0, lane, deep, tone in spans:
            top = y + 46 + lane
            if e0 < start or s0 > start + window or top + deep > y + h:
                continue
            x1 = x + 6 + (max(s0, start) - start) * PITCH
            x2 = x + 6 + (min(e0, start + window) - start) * PITCH
            if tone in ("span", "kept"):
                tone = _standing(s0, e0, at, start, start + window)
            said.box(x1, top, max(1.5, x2 - x1), deep, tone)
            said.hit(x1, top, max(3.0, x2 - x1), deep, "span", f"{s0}:{e0}")
        cursor = x + 6 + (min(max(at, start), start + window) - start) * PITCH
        said.line(cursor, y + 44, cursor, y + h, "cursor")


class Spine(Surface):
    """What is open at the cursor, innermost last — the reading's own stack."""

    name = "spine"
    title = "THE SPINE · open at the cursor"
    column = "derivation"
    relation = "stacked"

    def room(self, view: View) -> tuple[int, int]:
        deep = max((span.depth for span in view.reading.spans), default=0) + 1
        return 48, max(4, deep // 2)

    def draw(self, said: Frame, box: Box, view: View) -> None:
        x, y, w, h = box
        live = view.live
        shown = live[-max(1, int((h - 10) // ROW)) :]
        if not shown:
            said.text(x + 12, y + 22, "dim", "JUST CLOSED")
            return
        for i, span in enumerate(shown):
            step = min(span.depth, 8) * 7
            said.text(
                x + 12 + step,
                y + 20 + i * ROW,
                "live" if span is live[-1] else "dim",
                f"d{span.depth} {view.named(span.rule)} {span.start:,}..{span.end:,}",
                w - 24 - step,
            )
            said.hit(x, y + 6 + i * ROW, w, ROW, "span", f"{span.start}:{span.end}")
