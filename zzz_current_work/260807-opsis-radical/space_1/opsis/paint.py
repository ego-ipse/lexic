"""Drawings — what to paint, said in full, so the leaf only paints.

A surface that computes its own picture is a surface no fact can check. The
railroad and the automaton were the last two doing it; both are pure
geometry over things this side already knows, so both are sent as drawings.

The vocabulary is five words, each one line::

    box    x y w h tone [label]
    line   x1 y1 x2 y2 tone
    curve  x1 y1 cx cy x2 y2 tone
    arc    x y r tone
    text   x y tone words…

Coordinates are pixels in the box the caller asked for, because the caller
said how big its box is. Tones are names, not colours: the register lives in
the leaf's stylesheet, so a drawing never carries a hex code.
"""

from __future__ import annotations

from opsis.measure import Box, boxes
from praxis.reading import columns

__all__ = ["Drawing", "automaton_drawing", "rails_drawing"]

CELL = 7.2  # one column, in pixels, at the leaf's rail font
ROW = 22.0  # one row


class Drawing:
    """A list of things to paint, and how big the whole is."""

    __slots__ = ("marks", "tall", "wide")

    def __init__(self) -> None:
        self.marks: list[str] = []
        self.wide = 0.0
        self.tall = 0.0

    def box(
        self, x: float, y: float, w: float, h: float, tone: str, said: str = ""
    ) -> None:
        self.marks.append(f"box {x:.1f} {y:.1f} {w:.1f} {h:.1f} {tone} {said}")
        self.wide = max(self.wide, x + w)
        self.tall = max(self.tall, y + h)

    def line(self, x1: float, y1: float, x2: float, y2: float, tone: str) -> None:
        self.marks.append(f"line {x1:.1f} {y1:.1f} {x2:.1f} {y2:.1f} {tone}")
        self.wide = max(self.wide, x1, x2)
        self.tall = max(self.tall, y1, y2)

    def curve(
        self,
        x1: float,
        y1: float,
        cx: float,
        cy: float,
        x2: float,
        y2: float,
        tone: str,
    ) -> None:
        self.marks.append(
            f"curve {x1:.1f} {y1:.1f} {cx:.1f} {cy:.1f} {x2:.1f} {y2:.1f} {tone}"
        )
        self.wide = max(self.wide, x1, x2)
        self.tall = max(self.tall, y1, y2)

    def dot(self, x: float, y: float, r: float, tone: str) -> None:
        self.marks.append(f"arc {x:.1f} {y:.1f} {r:.1f} {tone}")

    def text(self, x: float, y: float, tone: str, said: str) -> None:
        self.marks.append(f"text {x:.1f} {y:.1f} {tone} {said}")
        self.wide = max(self.wide, x + columns(said) * CELL)
        self.tall = max(self.tall, y)

    def wire(self, what: str) -> str:
        return "\n".join(
            [
                f"#DRAW {len(self.marks)} {what} {self.wide:.0f} {self.tall:.0f}",
                *self.marks,
                "",
            ]
        )


def _track(
    node: tuple[str, str, list],
    room: list[Box],
    at: list[int],
    draw: Drawing,
    x: float,
    y: float,
) -> None:
    """One node of a railroad, drawn where it was measured to sit."""
    kind, payload, kids = node
    box = room[at[0]]
    at[0] += 1
    w, h, spine = box.wide * CELL, box.tall * ROW, box.spine * ROW
    if kind == "seq":
        cursor = x
        for kid in kids:
            kid_box = room[at[0]]
            draw.line(cursor, y + spine, cursor, y + spine, "rail")
            _track(kid, room, at, draw, cursor, y + spine - kid_box.spine * ROW)
            after = cursor + kid_box.wide * CELL
            if kid is not kids[-1]:
                draw.line(after, y + spine, after + 3 * CELL, y + spine, "rail")
            cursor = after + 3 * CELL
        return
    if kind == "alt":
        top = y
        for kid in kids:
            kid_box = room[at[0]]
            inner = x + 3 * CELL
            draw.curve(
                x, y + spine, inner, y + spine, inner, top + kid_box.spine * ROW, "rail"
            )
            _track(kid, room, at, draw, inner, top)
            right = inner + kid_box.wide * CELL
            edge = x + w
            draw.curve(
                right,
                top + kid_box.spine * ROW,
                edge - 3 * CELL,
                top + kid_box.spine * ROW,
                edge,
                y + spine,
                "rail",
            )
            top += kid_box.tall * ROW + ROW
        return
    if kind == "many":
        low, high = (payload.split() + ["1", "1"])[:2]
        kid_box = room[at[0]]
        inner_y = y + (2 * ROW if low == "0" else 0)
        _track(kids[0], room, at, draw, x + 2 * CELL, inner_y)
        left, right = x, x + w
        mid = inner_y + kid_box.spine * ROW
        draw.line(left, mid, x + 2 * CELL, mid, "rail")
        draw.line(x + 2 * CELL + kid_box.wide * CELL, mid, right, mid, "rail")
        if low == "0":
            draw.curve(
                left, mid, left, y + ROW, (left + right) / 2, y + ROW * 0.6, "loop"
            )
            draw.curve(
                (left + right) / 2, y + ROW * 0.6, right, y + ROW, right, mid, "loop"
            )
        if high != "1":
            under = inner_y + kid_box.tall * ROW + ROW * 0.8
            draw.curve(right, mid, right, under, (left + right) / 2, under, "loop")
            draw.curve((left + right) / 2, under, left, under, left, mid, "loop")
        return
    if kind in ("not", "alpha"):
        tag = "¬ none of" if kind == "not" else f"⟨{payload}⟩"
        draw.text(x, y + ROW * 0.8, "dim", tag)
        _track(kids[0], room, at, draw, x + CELL, y + ROW)
        return
    tone = {"ref": "ref", "class": "class", "nil": "dim"}.get(kind, "token")
    draw.box(x, y, w, h, tone, box.label)


def rails_drawing(tracks: str, wide: int) -> Drawing:
    """Every rule's track, laid down the page — one drawing, whole."""
    draw = Drawing()
    y = ROW
    for block in tracks.split("#RAIL ")[1:]:
        head, _, body = block.partition("\n")
        name, count = head.split()[0], int(head.split()[-1])
        rows = body.split("\n")
        lines, said = rows[:count], rows[count + 1 : count + 1 + count]
        room = [
            Box(float(p[0]), float(p[1]), float(p[2]), p[3] if len(p) > 3 else "")
            for p in (line.split(" ", 3) for line in said)
        ]
        if not room:
            continue
        draw.text(CELL * 2, y, "name", name)
        y += ROW * 0.8
        node = _relines(lines)
        _track(node, room, [0], draw, CELL * 4, y)
        y += room[0].tall * ROW + ROW * 1.6
    draw.wide = max(draw.wide, float(wide))
    return draw


def _relines(lines: list[str]) -> tuple[str, str, list]:
    """The track's lines back into their nesting (the boxes are parallel)."""
    root: tuple[str, str, list] = ("seq", "", [])
    stack: list[tuple[str, str, list]] = [root]
    for line in lines:
        depth, _, rest = line.partition(" ")
        if not depth.isdigit():
            continue
        kind, _, payload = rest.partition(" ")
        node = (kind, payload, [])
        stack[int(depth)][2].append(node)
        stack[int(depth) + 1 :] = [node]
    kids = root[2]
    return kids[0] if len(kids) == 1 else root


def automaton_drawing(said: str, lit: set[int], seen: set[int]) -> Drawing:
    """The clone set, drawn where the machine seated it, lit by the walk."""
    draw = Drawing()
    parts: dict[str, list[str]] = {}
    where = ""
    for line in said.split("\n"):
        if line.startswith("#"):
            where = line.split()[0]
            parts[where] = []
        elif where and line:
            parts[where].append(line)
    clones = [line.split(" ") for line in parts.get("#ACLONES", [])]
    names = parts.get("#ANAMES", [])
    places = [line.split(" ") for line in parts.get("#APLACES", [])]
    if not places:
        return draw
    left = min(float(p[0]) for p in places)
    top = min(float(p[1]) for p in places)
    at = [(float(p[0]) - left + 30, float(p[1]) - top + 20) for p in places]
    for line in parts.get("#AEDGES", []):
        a, b = (int(n) for n in line.split(" "))
        if a >= len(at) or b >= len(at):
            continue
        (x1, y1), (x2, y2) = at[a], at[b]
        tone = "hot" if a in lit and b in lit else "cool"
        draw.curve(x1 + 4, y1, (x1 + x2) / 2, y1, x2 - 4, y2, tone)
    for i, ((x, y), clone) in enumerate(zip(at, clones)):
        tone = "hot" if i in lit else ("seen" if i in seen else clone[1])
        draw.dot(x, y, 3.0, tone)
        name = (
            names[int(clone[0])]
            if clone[0].isdigit() and int(clone[0]) < len(names)
            else ""
        )
        if name:
            draw.text(x + 6, y + 3, tone, name)
    return draw
