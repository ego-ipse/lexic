"""The frame — one reading, drawn whole, in pixels, ready to paint.

space_1 kept a model in the leaf: the leaf owned the window, the cursor and
the tint, while this side owned where things sit. Two geometries that had to
agree, and every one of that build's late failures was them disagreeing — a
hover a lane deep, a picture identical at every cursor position, a band
painted in a colour the leaf did not know.

Here there is one geometry. A frame carries FINAL pixel coordinates and
named tones, plus the hit rectangles that say what the pointer can land on
and what to post when it does. The leaf paints marks and reports gestures.
It holds no opinion about what any of it means, so there is nothing left to
drift.

Marks, one per line::

    box    x y w h tone [label]
    line   x1 y1 x2 y2 tone
    text   x y tone words…
    hit    x y w h kind address
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from read.points import open_at  # noqa: E402
from shape.layout import positions  # noqa: E402
from shape.topology import edges  # noqa: E402
from lexic.compile import CompiledGrammar, compile_text  # noqa: E402
from lexic.exceptions import LexicError  # noqa: E402
from read.reading import Reading, as_written  # noqa: E402

__all__ = ["Frame", "frame"]

HEAD = re.compile(r"^([A-Za-z0-9_-]+)\s*(?:::=|=/|=)")


def ruledefs(text: str) -> list[tuple[str, int, int]]:
    """Where each rule lives in the reader text — its written spelling."""
    heads = [
        (m.group(1), i)
        for i, line in enumerate(text.split("\n"))
        if (m := HEAD.match(line))
    ]
    return [
        (name, start, (heads[i + 1][1] - 1 if i + 1 < len(heads) else text.count("\n")))
        for i, (name, start) in enumerate(heads)
    ]


def reader_of(reading: Reading) -> CompiledGrammar | None:
    """This reading's reader, compiled — or nothing, if nothing reads it."""
    try:
        return compile_text(reading.reader_text, flavour=reading.flavour or "gbnf")
    except LexicError, RecursionError, ValueError:
        return None


ROW = 19.0  # one line of text
CELL = 7.4  # one column
GUTTER = 54.0  # room for a line number


class Frame:
    """Marks to paint, and the rectangles a pointer can land on."""

    __slots__ = ("hits", "marks", "tall", "wide")

    def __init__(self, wide: int, tall: int) -> None:
        self.marks: list[str] = []
        self.hits: list[str] = []
        self.wide = wide
        self.tall = tall

    def box(
        self, x: float, y: float, w: float, h: float, tone: str, said: str = ""
    ) -> None:
        self.marks.append(f"box {x:.1f} {y:.1f} {w:.1f} {h:.1f} {tone} {said}")

    def line(self, x1: float, y1: float, x2: float, y2: float, tone: str) -> None:
        self.marks.append(f"line {x1:.1f} {y1:.1f} {x2:.1f} {y2:.1f} {tone}")

    def text(self, x: float, y: float, tone: str, said: str) -> None:
        self.marks.append(f"text {x:.1f} {y:.1f} {tone} {said}")

    def hit(self, x: float, y: float, w: float, h: float, kind: str, goes: str) -> None:
        self.hits.append(f"{x:.1f} {y:.1f} {w:.1f} {h:.1f} {kind} {goes}")

    def wire(self, generation: int) -> str:
        return "\n".join(
            [
                f"#FRAME {self.wide} {self.tall} {generation} {len(self.marks)}",
                *self.marks,
                f"#HITS {len(self.hits)}",
                *self.hits,
                "",
            ]
        )


def _plane(
    said: Frame,
    text: str,
    x: float,
    y: float,
    w: float,
    h: float,
    first: int,
    tone: str,
) -> int:
    """A block of text, line-numbered, clipped to the room it was given."""
    lines = text.split("\n")
    rows = int((h - ROW) // ROW)
    for i in range(rows):
        at = first + i
        if at >= len(lines):
            break
        top = y + i * ROW
        said.text(x + 6, top + ROW - 5, "dim", str(at + 1))
        said.text(x + GUTTER, top + ROW - 5, tone, lines[at][:200])
        said.hit(x, top, w, ROW, "line", str(at))
    return len(lines)


def frame(
    reading: Reading,
    wide: int,
    tall: int,
    at: float,
    reader_top: int = 0,
    doc_top: int = 0,
) -> Frame:
    """The whole instrument, at this size, at this moment — drawn once.

    Three columns: the reader as written, the document as read, and the
    derivation over a window of it with the cursor where it stands. Every
    number here is a pixel, so the leaf paints without deciding anything.
    """
    said = Frame(wide, tall)
    head = 30.0
    left = wide * 0.34
    middle = wide * 0.32
    right = wide - left - middle
    body = tall - head - 26

    said.box(0, 0, wide, head, "head")
    said.text(12, 20, "title", "FACETS")
    said.text(110, 20, "dim", f"{reading.document.name} ⊳ {reading.reader_name}")
    said.text(
        wide - 260,
        20,
        "good" if reading.faithful else "bad",
        "model.to_text() == document" if reading.faithful else "NOT FAITHFUL",
    )

    # ── the reader ───────────────────────────────────────────────────────
    said.text(12, head + 16, "label", "THE READER")
    _plane(said, reading.reader_text, 0, head + 24, left, body - 24, reader_top, "ink")
    said.line(left, head, left, tall - 26, "hair")

    # ── the document ─────────────────────────────────────────────────────
    said.text(left + 12, head + 16, "label", "THE DOCUMENT")
    _plane(said, reading.text, left, head + 24, middle, body - 24, doc_top, "ink")
    said.line(left + middle, head, left + middle, tall - 26, "hair")

    # ── the derivation, windowed and tinted HERE ─────────────────────────
    x0 = left + middle
    said.text(x0 + 12, head + 16, "label", "THE DERIVATION")
    lanes_y = head + 30
    deep = max((span.depth for span in reading.spans), default=0) + 1
    lane = max(4.0, min(20.0, (body - 40) / deep))
    pitch = 5.0
    window = max(8, int((right - 20) / pitch))
    start = max(0, min(int(at) - int(window * 0.6), max(0, len(reading.text) - window)))
    for span in reading.spans:
        if span.end < start or span.start > start + window:
            continue
        x1 = x0 + 10 + (max(span.start, start) - start) * pitch
        x2 = x0 + 10 + (min(span.end, start + window) - start) * pitch
        y = lanes_y + span.depth * lane
        tone = "closed" if span.end <= at else ("live" if span.start < at else "ahead")
        said.box(x1, y, max(1.5, x2 - x1), lane - 2, tone)
        said.hit(x1, y, max(3.0, x2 - x1), lane - 2, "span", f"{span.start}:{span.end}")
    cursor = x0 + 10 + (min(max(at, start), start + window) - start) * pitch
    said.line(cursor, lanes_y - 6, cursor, tall - 26, "cursor")

    # ── the relations, under the derivation ──────────────────────────────
    # A WHOLE NEW SURFACE, and the leaf gains no code for it: rules are
    # boxes, references are lines, and each rule is a hit that posts its own
    # name. That is the test of whether the protocol is real.
    machine = reader_of(reading)
    lit = {span.rule for span in open_at(reading, at)}
    if machine is not None:
        graph_top = lanes_y + deep * lane + 16
        graph_tall = max(80.0, tall - 26 - graph_top - 8)
        rules = ruledefs(reading.reader_text)
        places = positions(machine.grammar, "flat", int(right - 24), int(graph_tall))
        if places:
            spread_x = max(1.0, max(x for x, _y, _z in places.values()))
            top_y = min(y for _x, y, _z in places.values())
            span_y = max(1.0, max(y for _x, y, _z in places.values()) - top_y)

            def place(name: str) -> tuple[float, float]:
                x, y, _z = places[name]
                return (
                    x0 + 14 + (x / spread_x) * (right - 120),
                    graph_top + 14 + ((y - top_y) / span_y) * (graph_tall - 34),
                )

            for one, two in edges(machine.grammar):
                if one in places and two in places:
                    ax, ay = place(one)
                    bx, by = place(two)
                    said.line(ax + 20, ay, bx, by, "hair")
            for name in places:
                px, py = place(name)
                shown = as_written(rules, name)
                on = shown in lit or name in lit
                said.box(
                    px, py - 7, 8 + len(shown) * 6.2, 14, "live" if on else "ahead"
                )
                said.text(px + 4, py + 4, "ink" if on else "dim", shown)
                said.hit(px, py - 7, 8 + len(shown) * 6.2, 14, "rule", shown)

    # ── the stack at the cursor, said in words ───────────────────────────
    live = open_at(reading, at)
    for i, span in enumerate(live[:8]):
        said.text(
            left + 12,
            tall - 26 - ROW * (len(live[:8]) - i),
            "live" if i == len(live) - 1 else "dim",
            f"d{span.depth} {span.rule} {span.start:,}..{span.end:,}",
        )

    said.box(0, tall - 26, wide, 26, "head")
    said.text(
        12,
        tall - 8,
        "dim",
        f"char {int(at):,} / {len(reading.text):,} · {len(reading.spans):,} spans · "
        f"read in {reading.seconds:.2f}s · click a line, drag the derivation",
    )
    return said
