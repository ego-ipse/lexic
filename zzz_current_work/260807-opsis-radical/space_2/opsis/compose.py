"""One frame out of every surface the instrument has.

The drawings already exist — `paint.py` has emitted marks for the railroad,
the automaton, the relations, the derivation, the band and both clocks since
space_1. What was missing was somewhere to put them: space_1 sent each to a
leaf that laid them out, tinted them and hit-tested them, which is the model
that kept drifting.

Composing happens here instead. Each surface is drawn into the room the
measured arrangement gives it, offset into place, and the whole thing leaves
as one frame of final pixels. Nothing downstream decides anything.
"""

from __future__ import annotations

from deixis.points import open_at
from kairos.engine import automaton
from kairos.parse import hypotheses, watch
from opsis.grammar import rails
from opsis.marks import ROW, Frame
from opsis.paint import (
    automaton_drawing,
    band_drawing,
    chart_drawing,
    clock_drawing,
    graph_drawing,
    packed,
    rails_drawing,
)
from opsis.scene import reader_of, ruledefs
from opsis.space import shares
from praxis.looking import Looking
from praxis.reading import Reading, as_written

__all__ = ["compose"]

BAR = 30.0
FOOT = 26.0
GUTTER = 46.0

# every surface this build can show, and which drawing answers for it
SURFACES = ("derivation", "relations", "railroad", "machine", "pda", "earley")


def _place(said: Frame, drawing: object, x: float, y: float, scale: float) -> None:
    """A drawing's own marks, moved into the room it was given."""
    for mark in getattr(drawing, "marks", []):
        parts = mark.split(" ")
        kind = parts[0]
        if kind == "box":
            said.box(
                x + float(parts[1]) * scale,
                y + float(parts[2]) * scale,
                float(parts[3]) * scale,
                float(parts[4]) * scale,
                parts[5],
                " ".join(parts[7:]) if len(parts) > 7 else "",
            )
        elif kind == "line":
            said.line(
                x + float(parts[1]) * scale,
                y + float(parts[2]) * scale,
                x + float(parts[3]) * scale,
                y + float(parts[4]) * scale,
                parts[5],
            )
        elif kind in ("curve", "bez"):
            # a curve is drawn as its chord when a frame carries only lines;
            # the shape is the reading's, the simplification is stated
            last = 7 if kind == "curve" else 9
            said.line(
                x + float(parts[1]) * scale,
                y + float(parts[2]) * scale,
                x + float(parts[last - 2]) * scale,
                y + float(parts[last - 1]) * scale,
                parts[last],
            )
        elif kind == "text":
            said.text(
                x + float(parts[1]) * scale,
                y + float(parts[2]) * scale,
                parts[3],
                " ".join(parts[4:]),
            )


def _plane(
    said: Frame,
    text: str,
    x: float,
    y: float,
    w: float,
    h: float,
    first: int,
    lit: set[int],
    kind: str,
) -> None:
    """A block of text, line-numbered, every line clipped to its column."""
    lines = text.split("\n")
    for i in range(max(0, int(h // ROW))):
        at = first + i
        if at >= len(lines):
            break
        top = y + i * ROW
        if at in lit:
            said.box(x, top, w, ROW, "lit")
        said.text(x + 6, top + ROW - 5, "dim", str(at + 1), GUTTER - 10)
        said.text(x + GUTTER, top + ROW - 5, "ink", lines[at], w - GUTTER - 8)
        said.hit(x, top, w, ROW, kind, str(at))


def compose(
    reading: Reading, wide: int, tall: int, at: float, looking: Looking
) -> Frame:
    """The instrument, at this size, at this moment, as one frame."""
    said = Frame(wide, tall)
    facets = reading.facets()
    given = shares(facets, 200)
    total = sum(given.values()) or 1
    titles = {f.name: f.title for f in facets}
    left = wide * given.get("grammar", 60) / total
    middle = wide * given.get("document", 40) / total
    right = max(300.0, wide - left - middle)
    x0 = left + middle
    body = tall - BAR - FOOT
    machine = reader_of(reading)
    rules = ruledefs(reading.reader_text)
    live = open_at(reading, at)
    lit_rules = {as_written(rules, span.rule) for span in live}
    lit_lines = {
        line
        for name, first, last in rules
        if name in lit_rules
        for line in range(first, last + 1)
    }
    showing = looking.surface
    clock = looking.clock

    said.box(0, 0, wide, BAR, "head")
    said.text(12, 20, "title", "FACETS")
    said.text(96, 20, "dim", f"{reading.document.name} ⊳ {reading.reader_name}", 380)
    for i, name in enumerate(SURFACES):
        tab_x = wide - 620 + i * 96
        said.box(tab_x, 6, 92, 18, "live" if name == showing else "ahead")
        said.text(tab_x + 6, 19, "ink" if name == showing else "dim", name, 84)
        said.hit(tab_x, 6, 92, 18, "surface", name)

    # ── the two planes ───────────────────────────────────────────────────
    strip = 96.0
    said.text(12, BAR + 16, "label", titles.get("grammar", "THE READER"), left - 20)
    _plane(
        said,
        reading.reader_text,
        0,
        BAR + 24,
        left,
        body - 24 - strip,
        looking.reader_top,
        lit_lines,
        "readerline",
    )
    said.text(
        left + 12,
        BAR + 16,
        "label",
        titles.get("document", "THE DOCUMENT"),
        middle - 20,
    )
    _plane(
        said,
        reading.text,
        left,
        BAR + 24,
        middle,
        body - 24 - strip,
        looking.doc_top,
        set(),
        "line",
    )
    for edge in (left, x0):
        said.line(edge, BAR, edge, tall - FOOT, "hair")
    said.line(0, tall - FOOT - strip, x0, tall - FOOT - strip, "hair")

    # ── whichever surface is showing, drawn into the third column ────────
    said.text(x0 + 12, BAR + 16, "label", showing.upper(), right - 20)
    top = BAR + 26
    room_w, room_h = right - 20, tall - FOOT - top - 8
    if showing == "derivation" or showing in ("pda", "earley"):
        band = band_drawing(reading, 20, None, "model")
        _place(said, band, x0 + 10, top, room_w / max(1.0, band.wide))
        lanes_top = top + 26
        if showing == "derivation":
            drawing = chart_drawing(reading, int(room_h - 30))
        elif machine is not None and showing == "pda":
            rows = [
                (s0, e0, d0, ok)
                for s0, e0, d0, _n, ok, _seat in watch(machine, reading.text)
            ]
            drawing = clock_drawing(rows, len(reading.text), int(room_h - 30))
        else:
            said_hyps, _names = (
                hypotheses(machine, reading.text) if machine else ([], [])
            )
            held = [
                (int(p[0]), int(p[1]), int(p[2]))
                for p in (line.split(" ") for line in said_hyps)
                if len(p) >= 3
            ]
            drawing = clock_drawing(packed(held), len(reading.text), int(room_h - 30))
        # the window: the picture is in document coordinates, so the frame
        # decides which stretch of it is on screen — and says so in pixels
        pitch = 5.0
        window = max(8, int(room_w / pitch))
        start = max(
            0, min(int(at) - int(window * 0.6), max(0, len(reading.text) - window))
        )
        for mark in drawing.marks:
            p = mark.split(" ")
            if p[0] != "box":
                continue
            s0, e0, index = (int(n) for n in p[6].split(":"))
            if e0 < start or s0 > start + window:
                continue
            x1 = x0 + 10 + (max(s0, start) - start) * pitch
            x2 = x0 + 10 + (min(e0, start + window) - start) * pitch
            tone = p[5]
            if tone in ("span", "kept"):
                tone = "closed" if e0 <= at else ("live" if s0 < at else "ahead")
            elif tone == "lost":
                tone = "lost"
            said.box(x1, lanes_top + float(p[2]), max(1.5, x2 - x1), float(p[4]), tone)
            said.hit(
                x1,
                lanes_top + float(p[2]),
                max(3.0, x2 - x1),
                float(p[4]),
                "span",
                f"{s0}:{e0}",
            )
        cursor = x0 + 10 + (min(max(at, start), start + window) - start) * pitch
        said.line(cursor, lanes_top - 6, cursor, tall - FOOT, "cursor")
    elif showing == "relations" and machine is not None:
        drawing = graph_drawing(
            machine.grammar, "flat", int(room_w), int(room_h), None, lit_rules
        )
        _place(said, drawing, x0 + 10, top, 1.0)
    elif showing == "railroad" and machine is not None:
        drawing = rails_drawing(rails(machine.grammar), int(room_w))
        _place(said, drawing, x0 + 10, top - looking.rail_top, 1.0)
    elif showing == "machine" and machine is not None:
        lit_seats = {
            seat
            for s0, e0, _d, _n, ok, seat in watch(machine, reading.text)
            if ok and s0 <= at < e0
        }
        drawing = automaton_drawing(automaton(machine.pda_tables()), lit_seats, set())
        scale = min(1.0, room_w / max(1.0, drawing.wide))
        _place(said, drawing, x0 + 10, top, scale)

    # ── the stack, in the strip under the reader ─────────────────────────
    for i, span in enumerate(live[-8:]):
        said.text(
            12,
            tall - FOOT - ROW * (len(live[-8:]) - i),
            "live" if span is live[-1] else "dim",
            f"d{span.depth} {as_written(rules, span.rule)} "
            f"{span.start:,}..{span.end:,}",
            left - 20,
        )

    said.box(0, tall - FOOT, wide, FOOT, "head")
    said.text(
        12,
        tall - 8,
        "dim",
        f"char {int(at):,} / {len(reading.text):,} · {len(reading.spans):,} spans · "
        f"{reading.seconds:.2f}s · {clock} · click a tab, a span, a rule · space plays",
        wide - 24,
    )
    return said
