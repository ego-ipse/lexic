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

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPACE_1 = HERE.parent / "space_1"
for path in (str(HERE), str(SPACE_1)):
    if path not in sys.path:
        sys.path.insert(0, path)

from deixis.points import open_at  # noqa: E402
from praxis.reading import Reading  # noqa: E402

__all__ = ["Frame", "frame"]

ROW = 19.0        # one line of text
CELL = 7.4        # one column
GUTTER = 54.0     # room for a line number


class Frame:
    """Marks to paint, and the rectangles a pointer can land on."""

    __slots__ = ("hits", "marks", "tall", "wide")

    def __init__(self, wide: int, tall: int) -> None:
        self.marks: list[str] = []
        self.hits: list[str] = []
        self.wide = wide
        self.tall = tall

    def box(self, x: float, y: float, w: float, h: float, tone: str, said: str = "") -> None:
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
    said: Frame, text: str, x: float, y: float, w: float, h: float, first: int, tone: str
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
    _plane(
        said, reading.text, left, head + 24, middle, body - 24, doc_top, "ink"
    )
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

    # ── the stack at the cursor, said in words ───────────────────────────
    live = open_at(reading, at)
    for i, span in enumerate(live[:12]):
        said.text(
            x0 + 12,
            lanes_y + deep * lane + 24 + i * ROW,
            "live" if i == len(live) - 1 else "ink",
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
