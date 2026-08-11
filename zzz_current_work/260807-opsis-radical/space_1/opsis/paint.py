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

from eidolon.layout import positions
from eidolon.topology import edges
from lexic.ir import IrAst
from opsis.measure import BRACKET, GAP, LOOP, VGAP, Box
from praxis.reading import columns

__all__ = [
    "Drawing",
    "automaton_drawing",
    "band_drawing",
    "clock_drawing",
    "packed",
    "chart_drawing",
    "graph_drawing",
    "band_drawing",
    "clock_drawing",
    "packed",
    "chart_drawing",
    "rail_drawing",
    "rails_drawing",
]

CELL = 7.2  # one column, in pixels, at the leaf's rail font
ROW = 22.0  # one row
CORNER = 7.0  # how tightly the track turns


class Drawing:
    """A list of things to paint, and how big the whole is."""

    __slots__ = ("marks", "tall", "wide")

    def __init__(self) -> None:
        self.marks: list[str] = []
        self.wide = 0.0
        self.tall = 0.0

    def box(
        self,
        x: float,
        y: float,
        w: float,
        h: float,
        tone: str,
        said: str = "",
        goes: str = "",
    ) -> None:
        # a mark can carry an ADDRESS: where clicking it leads. The leaf
        # hit-tests rectangles; it does not know what a railroad is.
        self.marks.append(
            f"box {x:.1f} {y:.1f} {w:.1f} {h:.1f} {tone} {goes or '-'} {said}"
        )
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

    def bez(
        self,
        x1: float,
        y1: float,
        ax: float,
        ay: float,
        bx: float,
        by: float,
        x2: float,
        y2: float,
        tone: str,
    ) -> None:
        """An S-curve: the branch a railroad actually draws off its line."""
        self.marks.append(
            f"bez {x1:.1f} {y1:.1f} {ax:.1f} {ay:.1f} {bx:.1f} {by:.1f} "
            f"{x2:.1f} {y2:.1f} {tone}"
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


def _arch(
    draw: Drawing, left: float, right: float, line: float, away: float, tone: str
) -> None:
    """A line that leaves the track, runs parallel and comes back."""
    radius = min(CORNER, abs(away - line) / 2)
    step = 1.0 if away > line else -1.0
    draw.curve(left, line, left, away, left + radius, away, tone)
    draw.line(left + radius, away, right - radius, away, tone)
    draw.curve(right - radius, away, right, away, right, line, tone)
    _ = step


def _turn(
    draw: Drawing,
    edge: float,
    spine: float,
    bus: float,
    mid: float,
    arm: float,
    out: bool,
) -> None:
    """One branch off the line: leave, round down, run, round back in."""
    radius = min(CORNER, abs(mid - spine) / 2)
    step = 1.0 if mid > spine else -1.0
    if out:
        draw.line(edge, spine, bus - radius, spine, "rail")
        draw.curve(bus - radius, spine, bus, spine, bus, spine + step * radius, "rail")
        draw.line(bus, spine + step * radius, bus, mid - step * radius, "rail")
        draw.curve(bus, mid - step * radius, bus, mid, bus + radius, mid, "rail")
        draw.line(bus + radius, mid, arm, mid, "rail")
        return
    draw.line(arm, mid, bus - radius, mid, "rail")
    draw.curve(bus - radius, mid, bus, mid, bus, mid - step * radius, "rail")
    draw.line(bus, mid - step * radius, bus, spine + step * radius, "rail")
    draw.curve(bus, spine + step * radius, bus, spine, bus + radius, spine, "rail")
    draw.line(bus + radius, spine, edge, spine, "rail")


def inner_left(bus: float) -> float:
    """Where an arm starts: one column clear of the bus it hangs from."""
    return bus + CELL


def _track(
    node: tuple[str, str, list],
    room: list[Box],
    at: list[int],
    draw: Drawing,
    x: float,
    y: float,
) -> None:
    """One node of a railroad, drawn where it was measured to sit.

    A track is read left to right along one line: everything enters at its
    spine and leaves at its spine, and the connectors between are what make
    it a line rather than a scatter of boxes.
    """
    kind, payload, kids = node
    box = room[at[0]]
    at[0] += 1
    w, spine = box.wide * CELL, box.spine * ROW
    if kind == "seq":
        cursor = x
        for i, kid in enumerate(kids):
            kid_box = room[at[0]]
            _track(kid, room, at, draw, cursor, y + spine - kid_box.spine * ROW)
            cursor += kid_box.wide * CELL
            if i < len(kids) - 1:
                draw.line(cursor, y + spine, cursor + GAP * CELL, y + spine, "rail")
                cursor += GAP * CELL
        return
    if kind == "alt":
        # A branch is an S-CURVE off the line, one per arm, with its control
        # points at the horizontal midpoint — the shape the earlier build
        # drew and the one that reads as track. A shared vertical bus reads
        # as a bracket; a single long diagonal reads as a funnel.
        top = y
        arm_left = x + BRACKET / 2 * CELL
        for kid in kids:
            kid_box = room[at[0]]
            mid = top + kid_box.spine * ROW
            _track(kid, room, at, draw, arm_left, top)
            arm_right = arm_left + kid_box.wide * CELL
            middle = (x + arm_left) / 2
            draw.bez(
                x, y + spine, middle, y + spine, middle, mid, arm_left, mid, "rail"
            )
            out_middle = (arm_right + x + w) / 2
            draw.bez(
                arm_right,
                mid,
                out_middle,
                mid,
                out_middle,
                y + spine,
                x + w,
                y + spine,
                "rail",
            )
            top += kid_box.tall * ROW + VGAP * ROW
        return
    if kind == "many":
        low, high = (payload.split() + ["1", "1"])[:2]
        kid_box = room[at[0]]
        inner_x = x + 2 * CELL
        inner_y = y + (LOOP * ROW if low == "0" else 0)
        _track(kids[0], room, at, draw, inner_x, inner_y)
        mid = inner_y + kid_box.spine * ROW
        right_of_kid = inner_x + kid_box.wide * CELL
        draw.line(x, mid, inner_x, mid, "rail")
        draw.line(right_of_kid, mid, x + w, mid, "rail")
        if low == "0":  # the bypass arches over
            draw.bez(
                x,
                mid,
                x + 2,
                mid - LOOP * ROW * 0.7,
                x + w - 2,
                mid - LOOP * ROW * 0.7,
                x + w,
                mid,
                "loop",
            )
        if high != "1":  # the repeat arches back under
            drop = kid_box.tall * ROW + ROW * 0.7
            draw.bez(
                x + w, mid, x + w - 2, mid + drop, x + 2, mid + drop, x, mid, "loop"
            )
        return

    if kind in ("not", "alpha"):
        tag = "¬ none of" if kind == "not" else f"⟨{payload}⟩"
        draw.text(x, y + ROW * 0.7, "dim", tag)
        _track(kids[0], room, at, draw, x + CELL, y + ROW)
        return
    tone = {"ref": "ref", "class": "class", "nil": "dim"}.get(kind, "token")
    # a ref is a DOOR: it carries the rule it names, so the leaf can be
    # clicked through to it without knowing anything about railroads
    draw.box(
        x, y, w, box.tall * ROW, tone, box.label, box.label if kind == "ref" else ""
    )


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


def graph_drawing(
    ast: IrAst,
    view: str,
    wide: int,
    tall: int,
    tune: dict[str, float] | None = None,
    lit: set[str] | None = None,
) -> Drawing:
    """The relations as a drawing — nodes where they sit, edges between them.

    The flat and arc views are two dimensions, so the whole picture can be
    said here. The ring view keeps its camera in the leaf, because a camera
    is the hand's and a round trip per frame is not a rotation.
    """
    draw = Drawing()
    places = positions(ast, view, wide, tall, tune)
    if not places:
        return draw
    left = min(x for x, _y, _z in places.values())
    top = min(y for _x, y, _z in places.values())
    at = {name: (x - left + 30, y - top + 24) for name, (x, y, _z) in places.items()}
    alight = lit or set()
    for a, b in edges(ast):
        one, two = at.get(a), at.get(b)
        if one is None or two is None:
            continue
        tone = "hot" if a in alight and b in alight else "cool"
        if view == "arcs":
            lift = min(160.0, abs(two[0] - one[0]) * 0.4) + 12
            draw.curve(
                one[0],
                one[1],
                (one[0] + two[0]) / 2,
                one[1] - lift,
                two[0],
                two[1],
                tone,
            )
        else:
            draw.line(one[0], one[1], two[0], two[1], tone)
    for name, (x, y) in at.items():
        tone = "hot" if name in alight else "ref"
        said = name if len(name) <= 24 else name[:23] + "…"
        draw.box(x - 4, y - ROW / 2, columns(said) * CELL + 8, ROW * 0.8, tone, said)
    return draw


def rail_drawing(tracks: str, name: str) -> Drawing:
    """One rule's track, alone — what a pinned railroad window shows."""
    draw = Drawing()
    for block in tracks.split("#RAIL ")[1:]:
        head, _, body = block.partition("\n")
        if head.split()[0].casefold() != name.casefold():
            continue
        count = int(head.split()[-1])
        rows = body.split("\n")
        lines, said = rows[:count], rows[count + 1 : count + 1 + count]
        room = [
            Box(float(p[0]), float(p[1]), float(p[2]), p[3] if len(p) > 3 else "")
            for p in (line.split(" ", 3) for line in said)
        ]
        if room:
            _track(_relines(lines), room, [0], draw, CELL * 2, ROW * 0.5)
        break
    return draw


def chart_drawing(reading: object, tall: int) -> Drawing:
    """The whole derivation, in DOCUMENT coordinates — x IS the offset.

    Drawn once per reading, not once per window. Keying a drawing to the
    window meant every frame of playback scrolled it, invalidated it and
    refetched a whole-document computation — which is why the clock died
    the moment you pressed play. A window is a transform, and a transform
    belongs to the side doing the looking.
    """
    draw = Drawing()
    spans = list(getattr(reading, "spans", []))
    if not spans:
        return draw
    deep = max(span.depth for span in spans) + 1
    lane = max(6.0, min(22.0, (tall - 24) / deep))
    for index, span in enumerate(spans):
        y = span.depth * lane
        goes = f"{span.start}:{span.end}:{index}"
        if span.end == span.start:
            draw.box(float(span.start), y, 0.0, lane - 2, "eps", "", goes)
            continue
        draw.box(
            float(span.start),
            y,
            float(span.end - span.start),
            lane - 2,
            "span",
            "",
            goes,
        )
    draw.wide = float(len(getattr(reading, "text", "")) or 1)
    draw.tall = deep * lane
    return draw


def band_drawing(reading: object, wide: int, tall: int, steps: int = 240) -> Drawing:
    """The whole document at a glance — how much structure sits where.

    The overview strip above the derivation. The leaf built this by summing
    a coverage array over twelve thousand spans; it is a property of the
    reading, so it is one here, and it does not change as the cursor moves.
    """
    draw = Drawing()
    spans = list(getattr(reading, "spans", []))
    text = getattr(reading, "text", "")
    if not spans or not text:
        return draw
    size = max(1, len(text) // steps)
    cover = [0] * (len(text) // size + 1)
    for span in spans:
        first = span.start // size
        last = min(span.end // size, len(cover) - 1)
        for at in range(first, last + 1):
            cover[at] += 1
    top = max(cover) or 1
    pitch = wide / max(1, len(cover))
    for at, deep in enumerate(cover):
        shade = min(3, (deep * 4) // (top + 1))
        draw.box(at * pitch, 0.0, max(1.0, pitch), float(tall), f"band{shade}")
    draw.wide = float(wide)
    draw.tall = float(tall)
    return draw


def clock_drawing(
    rows: list[tuple[int, int, int, int]], across: int, tall: int
) -> Drawing:
    """An engine's clock, in DOCUMENT coordinates — one box per thing held.

    ``rows`` are ``(start, end, lane, fate)``. Like the derivation, this is
    the whole document at once: the window is the leaf's transform, so
    scrubbing and playing cost nothing and change nothing here.
    """
    draw = Drawing()
    if not rows:
        return draw
    deep = max(lane for _s, _e, lane, _f in rows) + 1
    lane_tall = max(2.0, min(16.0, (tall - 12) / deep))
    for index, (start, end, lane, fate) in enumerate(rows):
        draw.box(
            float(start),
            lane * lane_tall,
            float(max(end - start, 0)),
            lane_tall - 1,
            "kept" if fate else "lost",
            "",
            f"{start}:{end}:{index}",
        )
    draw.wide = float(across or 1)
    draw.tall = deep * lane_tall
    return draw


def packed(rows: list[tuple[int, int, int]]) -> list[tuple[int, int, int, int]]:
    """Give every extent a row where it does not overlap what is already there.

    Earley holds thousands of hypotheses at once and they have no natural
    depth, so a row is something a picture must INVENT — the leaf used to,
    and dropping that on the way over put every one of them in row zero.
    Rows are filled in order, first that fits.
    """
    ends: list[int] = []
    out: list[tuple[int, int, int, int]] = []
    for start, end, fate in rows:
        lane = next((i for i, free in enumerate(ends) if free <= start), len(ends))
        if lane == len(ends):
            ends.append(0)
        ends[lane] = max(end, start + 1)
        out.append((start, end, lane, fate))
    return out
