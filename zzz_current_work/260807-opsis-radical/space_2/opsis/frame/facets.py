"""The five facets, drawn — one function each, on an open table.

The drawings themselves already exist: `paint.py` has emitted the band, the
lanes, both clocks, the rule graph, the rails and the automaton since the
first build. What lives here is only what each facet does with the room it
was given, and what its head carries. Adding a facet is a function and a
row; nothing else in the frame dispatches on which facet this is.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from deixis.points import closed_before, open_at
from eidolon.camera import project
from eidolon.layout import positions
from eidolon.topology import edges
from kairos.engine import automaton
from kairos.parse import hypotheses
from kairos.pipeline import FORMS
from opsis.frame.marks import CELL, ROW, Frame
from opsis.frame.tones import runs
from opsis.grammar import rails
from opsis.paint import (
    automaton_drawing,
    band_drawing,
    chart_drawing,
    clock_drawing,
    graph_drawing,
    packed,
    rails_drawing,
)
from opsis.scene import Staged
from praxis.reading import Reading, as_written

__all__ = ["DRAWN", "HEADS", "Look", "Room"]

Room = tuple[float, float, float, float]

# #gview's own option list, in its own words
GRAPHS = (
    ("depth3d", "depth 3d"),
    ("flat", "flat"),
    ("arcs", "arcs"),
    ("rails", "rails"),
    ("automaton", "automaton"),
)
# #cclock's
CLOCKS = (("model", "model"), ("pda", "pda clock"), ("earley", "earley clock"))

PITCH = 5.0


class Look:
    """One reading at one moment, and how the hand is looking at it.

    Handed to every facet, so two of them cannot disagree about what is live.
    """

    __slots__ = (
        "at",
        "chosen",
        "frontier",
        "it",
        "reading",
        "state",
        "typed",
        "watched",
    )

    def __init__(
        self,
        reading: Reading,
        it: Staged,
        at: float,
        state: dict[str, str],
        watched: list[list[Any]],
        typed: dict[str, str] | None = None,
        frontier: int = -1,
    ) -> None:
        self.reading = reading
        self.it = it
        self.at = at
        self.state = state
        self.chosen = state.get("chosen", "")
        self.watched = watched
        # what has been typed but not yet read, per plane
        self.typed = typed or {}
        self.frontier = frontier

    def shows(self, name: str, held: str) -> str:
        """What a plane shows — what was typed, which may be ahead of the read."""
        return self.typed.get(name, held)

    def says(self, key: str, fallback: str) -> str:
        return self.state.get(key, fallback)

    def top(self, name: str) -> int:
        said = self.state.get(f"top.{name}", "0")
        return int(said) if said.lstrip("-").isdigit() else 0

    def live(self) -> list:
        """What is open at the cursor — the spans the reading is standing in."""
        return open_at(self.reading, self.at)

    def lit(self) -> set[str]:
        """The rules that light: what is open, and whatever was chosen."""
        names = {as_written(self.it.rules, span.rule) for span in self.live()}
        if self.chosen:
            names.add(self.chosen)
        return names


# ── the reader and the document ──────────────────────────────────────────
def _plane(
    said: Frame, room: Room, look: Look, name: str, text: str, numbered: bool
) -> None:
    """A block of REAL text, with what is true about it drawn underneath."""
    x, y, w, h = room
    lines = text.split("\n")
    first = look.top(name)
    # .ln .g { width: 5ch; padding-right: 1.5ch } — the gutter is 6.5ch
    run = x + (6.5 * CELL if numbered else 1.5 * CELL)
    rows = max(0, int((h - 8) // ROW))
    lit = _held(look, name)
    for i in range(rows):
        line = first + i
        if line >= len(lines):
            break
        top = y + 8 + i * ROW
        tone = lit.get(line, "")
        if tone:
            said.box(x, top, w, ROW, tone)
        if numbered:
            said.text(
                x + 1.5 * CELL, top + ROW - 5, "dimmer", f"{line + 1:>4}", 5 * CELL
            )
            said.hit(x, top, 6.5 * CELL, ROW, "gutter", str(line))
    said.plane(name, run, y + 8, w - (run - x) - 8, h - 12, text, first, True)
    _frontier(said, room, look, text, first, run, rows)


def _held(look: Look, name: str) -> dict[int, str]:
    """Which lines are lit, and in what: #grammarBody .ln.lit / .ln.hot."""
    if name != "grammar":
        return {}
    lit = look.lit()
    out: dict[int, str] = {}
    for rule, first, last in look.it.rules:
        if rule not in lit:
            continue
        tone = "hotline" if rule == look.chosen else "lit"
        for line in range(first, last + 1):
            out[line] = tone
    return out


def _frontier(
    said: Frame, room: Room, look: Look, text: str, first: int, run: float, rows: int
) -> None:
    """Where a refused read stopped — a red caret and underline, in the text."""
    at = look.frontier
    _x, y, w, _h = room
    if at < 0:
        return
    before = text[: min(at, len(text))].split("\n")
    row, column = len(before) - 1, len(before[-1])
    if not first <= row < first + rows:
        return
    top = y + 8 + (row - first) * ROW
    said.box(run + column * CELL - 1, top, 2, ROW, "red")
    said.line(run, top + ROW - 2, run + w * 0.8, top + ROW - 2, "red")


def grammar(said: Frame, room: Room, look: Look) -> None:
    """THE READER — the grammar, in whichever form the reader is showing."""
    _plane(
        said, room, look, "grammar", look.shows("grammar", look.it.reader_text), False
    )


def document(said: Frame, room: Room, look: Look) -> None:
    """THE DOCUMENT — the real text, editable, line-numbered."""
    _plane(
        said, room, look, "document", look.shows("document", look.reading.text), True
    )


# ── the relations ────────────────────────────────────────────────────────
def graph(said: Frame, room: Room, look: Look) -> None:
    """THE RELATIONS — five ways of looking at the same rules."""
    machine = look.it.machine
    if machine is None or look.it.shown is None:
        said.text(room[0] + 14, room[1] + 20, "fsub", "this reading has no machine")
        return
    GRAPHVIEWS.get(look.says("graph.view", "depth3d"), _depth3d)(said, room, look)


def _depth3d(said: Frame, room: Room, look: Look) -> None:
    """A ring per level in three-space — z is derivation distance, earned."""
    x, y, w, h = room
    shown = look.it.shown
    at = project(
        positions(shown, "rings", int(w), int(h)),
        float(look.says("graph.yaw", "0.6")),
        float(look.says("graph.pitch", "0.35")),
        w,
        h,
    )
    lit = look.lit()
    named = {name: as_written(look.it.rules, name) for name in at}
    for a, b in edges(shown):
        one, two = at.get(a), at.get(b)
        if one is None or two is None:
            continue
        hot = named.get(a, a) in lit and named.get(b, b) in lit
        said.line(
            x + one[0],
            y + one[1],
            x + two[0],
            y + two[1],
            "hot" if hot else "cool_wash",
        )
    # far first, so what is nearest is drawn last and reads as nearest
    for name in sorted(at, key=lambda n: at[n][2]):
        px, py, near = at[name]
        says = named.get(name, name)
        wide = runs("chip", says) + 12
        said.box(x + px - wide / 2, y + py - 8, wide, 16, "field2")
        said.text(
            x + px - wide / 2 + 6,
            y + py + 3,
            "hot" if says in lit else ("ink" if near > 0.9 else "chip"),
            says,
            wide - 10,
        )
        said.hit(x + px - wide / 2, y + py - 8, wide, 16, "rule", says)


def _flat(said: Frame, room: Room, look: Look) -> None:
    x, y, w, h = room
    said.place(
        graph_drawing(look.it.shown, "flat", int(w), int(h), None, look.lit()), x, y
    )


def _arcs(said: Frame, room: Room, look: Look) -> None:
    x, y, w, h = room
    said.place(
        graph_drawing(look.it.shown, "arcs", int(w), int(h), None, look.lit()),
        x,
        y + h / 3,
    )


def _rails(said: Frame, room: Room, look: Look) -> None:
    x, y, w, _h = room
    said.place(
        rails_drawing(rails(look.it.shown), int(w - 20)),
        x + 10,
        y + 8 - look.top("rails"),
    )


def _automaton(said: Frame, room: Room, look: Look) -> None:
    """The machine, walk-lit: the frames open at the cursor light their clones."""
    x, y, w, _h = room
    seats = {
        seat for s0, e0, _d, _n, ok, seat in look.watched if ok and s0 <= look.at < e0
    }
    drawn = automaton_drawing(automaton(look.it.machine.pda_tables()), seats, set())
    said.place(drawn, x + 10, y + 8, min(1.0, (w - 20) / max(1.0, drawn.wide)))


GRAPHVIEWS: dict[str, Callable[[Frame, Room, Look], None]] = {
    "depth3d": _depth3d,
    "flat": _flat,
    "arcs": _arcs,
    "rails": _rails,
    "automaton": _automaton,
}


# ── the derivation ───────────────────────────────────────────────────────
def chart(said: Frame, room: Room, look: Look) -> None:
    """THE DERIVATION — the overview band, then the lanes under a cursor."""
    x, y, w, h = room
    band = band_drawing(look.reading, 18, None, "model")
    said.place(band, x, y + 6, w / max(1.0, band.wide), 22.0 / max(1.0, band.tall))
    drawn = _clock(look, max(20, int(h - 44)))
    lanes = y + 36
    text = look.reading.text
    window = max(8, int((w - 12) / PITCH))
    start = max(0, min(int(look.at) - int(window * 0.6), max(0, len(text) - window)))
    picked = {
        (span.start, span.end)
        for span in look.reading.spans
        if look.chosen and as_written(look.it.rules, span.rule) == look.chosen
    }
    for mark in drawn.marks:
        p = mark.split(" ")
        if p[0] != "box":
            continue
        s0, e0, _index = (int(n) for n in p[6].split(":"))
        top = lanes + float(p[2])
        deep = float(p[4])
        if e0 < start or s0 > start + window or top + deep > y + h:
            continue
        x1 = x + 6 + (max(s0, start) - start) * PITCH
        x2 = x + 6 + (min(e0, start + window) - start) * PITCH
        if p[5] == "eps":
            # a rule that derives nothing is a tick, not a box: there is no
            # width to fill, and filling one would claim text it never took
            said.line(
                x1,
                top + 1,
                x1,
                top + deep - 1,
                "dimmer" if s0 <= look.at else "pending",
            )
            continue
        if e0 <= look.at:
            said.box(x1, top, max(1.5, x2 - x1), deep, "closed")
        elif s0 < look.at:
            # open: filled only as far as the cursor has come, so the fill IS
            # how much of this span has been read
            here = x + 6 + (min(look.at, start + window) - start) * PITCH
            said.box(x1, top, max(1.5, here - x1), deep, "active")
        said.ring(
            x1,
            top,
            max(1.5, x2 - x1),
            deep,
            "cool" if e0 <= look.at else ("warm" if s0 < look.at else "pending"),
        )
        if (s0, e0) in picked:
            said.ring(x1 - 1.5, top - 1.5, max(1.5, x2 - x1) + 3, deep + 3, "violet")
        said.hit(x1, top, max(3.0, x2 - x1), deep, "span", f"{s0}:{e0}")
    cursor = x + 6 + (min(max(look.at, start), start + window) - start) * PITCH
    said.line(cursor, y + 32, cursor, y + h, "cursor")


def _clock(look: Look, tall: int):
    """Which clock the lanes tell — the model's spans, the PDA's, or Earley's."""
    which = look.says("chart.clock", "model")
    machine = look.it.machine
    if machine is not None and which == "pda":
        rows = [(s0, e0, d0, ok) for s0, e0, d0, _n, ok, _seat in look.watched]
        return clock_drawing(rows, len(look.reading.text), tall)
    if machine is not None and which == "earley":
        said, _names = hypotheses(machine, look.reading.text)
        held = [
            (int(p[0]), int(p[1]), int(p[2]))
            for p in (line.split(" ") for line in said)
            if len(p) >= 3
        ]
        return clock_drawing(packed(held), len(look.reading.text), tall)
    return chart_drawing(look.reading, tall)


# ── the spine ────────────────────────────────────────────────────────────
def spine(said: Frame, room: Room, look: Look) -> None:
    """THE SPINE — what is open at the cursor, then what just closed."""
    x, y, w, h = room
    live = look.live()
    top = y + 12
    if not live:
        said.text(x + 14, top + 8, "fsub", "nothing open here")
    for span in live:
        if top > y + h - 40:
            break
        name = as_written(look.it.rules, span.rule)
        said.text(x + 14, top + 10, "dimmer", f"d{span.depth}", 4 * CELL)
        said.text(
            x + 14 + 4.5 * CELL,
            top + 10,
            "warm" if span is live[-1] else "ink",
            f"{name} {span.start:,}..{span.end:,}",
            w - 30 - 4.5 * CELL,
        )
        said.hit(x, top, w, ROW, "span", f"{span.start}:{span.end}")
        top += ROW
    top += 8
    said.text(x + 14, top + 10, "ftitle", "JUST CLOSED")
    top += ROW + 2
    for span in closed_before(look.reading, look.at):
        if top > y + h - 12:
            break
        name = as_written(look.it.rules, span.rule)
        said.text(
            x + 14, top + 10, "dim", f"{name} {span.start:,}..{span.end:,}", w - 30
        )
        said.hit(x, top, w, ROW, "span", f"{span.start}:{span.end}")
        top += ROW


DRAWN: dict[str, Callable[[Frame, Room, Look], None]] = {
    "grammar": grammar,
    "graph": graph,
    "document": document,
    "chart": chart,
    "spine": spine,
}


def _heads(look: Look, name: str) -> list[tuple[str, str, str, bool]]:
    """What a facet's head carries — its own selects, and nothing else's."""
    if name == "grammar":
        here = look.it.form
        return [(form, "form", form, form == here) for form in FORMS]
    if name == "graph":
        here = look.says("graph.view", "depth3d")
        return [(word, "graph.view", key, key == here) for key, word in GRAPHS]
    if name == "chart":
        here = look.says("chart.clock", "model")
        return [(word, "chart.clock", key, key == here) for key, word in CLOCKS]
    return []


HEADS = _heads
