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
from kairos.engine import automaton, verdicts
from kairos.parse import hypotheses
from kairos.pipeline import FORMS
from opsis.frame.marks import CELL, ROW, Frame
from opsis.frame.tones import runs
from opsis.grammar import rails
from opsis.paint import (
    Drawing,
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
from praxis.routes import Aside

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

    Handed to every facet, so that two of them cannot disagree about what is
    live, what is chosen, or which form is being read.
    """

    __slots__ = (
        "at",
        "chosen",
        "frontier",
        "it",
        "reading",
        "routes",
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
        routes: Aside | None = None,
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
        # what the other engine made of this reading, and the tone to say it in
        self.routes = routes

    def says(self, key: str, fallback: str) -> str:
        """One policy key, as the hand left it."""
        return self.state.get(key, fallback)

    def shows(self, name: str, held: str) -> str:
        """What a plane shows — what was typed, which may be ahead of the read."""
        return self.typed.get(name, held)

    def top(self, name: str) -> int:
        """Which line, or which row, that facet is scrolled to."""
        said = self.state.get(f"top.{name}", "0")
        return int(said) if said.lstrip("-").isdigit() else 0

    def zoom(self, name: str) -> float:
        """How much of its own scale a facet is drawn at."""
        said = self.state.get(f"{name}.zoom", "1")
        try:
            return max(0.35, min(3.0, float(said)))
        except ValueError:
            return 1.0

    def live(self) -> list:
        """What is open at the cursor — the spans the reading is standing in."""
        return open_at(self.reading, self.at)

    def keep(self) -> set[str] | None:
        """What ◉ focus keeps: the chosen rule, its reach, and who refers to it.

        Nothing when no rule is chosen or focus is off — a focus with nothing
        to focus ON would simply fade the whole picture.
        """
        if self.says("graph.focus", "off") != "on" or not self.chosen:
            return None
        pairs = self.it.relations
        keep = {self.chosen}
        for a, b in pairs:
            if b == self.chosen:
                keep.add(a)
        frontier = [self.chosen]
        while frontier:
            onward = []
            for a, b in pairs:
                if a in frontier and b not in keep:
                    keep.add(b)
                    onward.append(b)
            frontier = onward
        return keep

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
    badges = _badges(look) if name == "grammar" else {}
    heads = {at: rule for rule, at, _last in look.it.rules} if badges else {}
    for i in range(rows):
        line = first + i
        if line >= len(lines):
            break
        top = y + 8 + i * ROW
        tone = lit.get(line, "")
        if tone:
            said.box(x, top, w, ROW, tone)
        badge = badges.get(heads.get(line, ""), "")
        if badge:
            _badge(said, x + w - 12, top + 3, badge)
        if numbered:
            said.text(
                x + 1.5 * CELL, top + ROW - 5, "dimmer", f"{line + 1:>4}", 5 * CELL
            )
            said.hit(x, top, 6.5 * CELL, ROW, "gutter", str(line))
    said.plane(name, run, y + 8, w - (run - x) - 8, h - 12, text, first, True)
    _frontier(said, room, look, text, first, run, rows)


# .vbadge — what the PDA analysis decided about a rule, in its own words.
# Static per grammar: the machine does not change because a cursor moved.
_VERDICTS: dict[str, dict[str, str]] = {}
BADGE = {
    "attempt": "warm",
    "island": "violet",
    "hard": "red",
    "gated": "cool",
    "predictive": "dimmer",
}


def _badges(look: Look) -> dict[str, str]:
    """Each rule's class, from the analysis' own transcript.

    Only drawn on the PDA clock, and only where there is something to say:
    SILENCE IS THE DETERMINISTIC VERDICT, so a predictive rule wears nothing.
    """
    if look.it.machine is None or look.says("chart.clock", "model") != "pda":
        return {}
    key = str(look.reading.reader_text.__hash__())
    if key not in _VERDICTS:
        _VERDICTS.clear()
        said = verdicts(look.it.machine).split("\n")
        out: dict[str, str] = {}
        for line in said[1:]:
            words = line.split(" ")
            if len(words) >= 3 and words[0] in BADGE and words[1].isdigit():
                if words[0] != "predictive":
                    out[" ".join(words[2:])] = words[0]
        _VERDICTS[key] = out
    return _VERDICTS[key]


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


def _badge(said: Frame, right: float, top: float, kind: str) -> None:
    """One rule's verdict, worn on its own head line, in that class's colour."""
    tone = BADGE.get(kind, "dimmer")
    wide = runs("chip", kind) + 12
    for x1, y1, x2, y2 in (
        (right - wide, top, right, top),
        (right - wide, top + 13, right, top + 13),
        (right - wide, top, right - wide, top + 13),
        (right, top, right, top + 13),
    ):
        said.line(x1, y1, x2, y2, tone)
    said.text(right - wide + 6, top + 10, tone, kind, face="chip")


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
    if look.it.machine is None or look.it.shown is None:
        said.text(room[0] + 14, room[1] + 20, "fsub", "this reading has no machine")
        return
    GRAPHVIEWS.get(look.says("graph.view", "depth3d"), _depth3d)(said, room, look)


def _depth3d(said: Frame, room: Room, look: Look) -> None:
    """A ring per level in three-space — z is derivation distance, earned."""
    x, y, w, h = room
    shown = look.it.shown
    at = project(
        positions(shown, "rings", int(w), int(h)),
        float(look.says("graph.yaw", "0.42")),
        float(look.says("graph.pitch", "0.92")),
        w,
        h,
        look.zoom("graph"),
    )
    lit = look.lit()
    keep = look.keep()
    named = {name: as_written(look.it.rules, name) for name in at}
    for a, b in edges(shown):
        one, two = at.get(a), at.get(b)
        if one is None or two is None:
            continue
        if keep is not None and not (
            named.get(a, a) in keep and named.get(b, b) in keep
        ):
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
        # ◉ focus: what the chosen rule cannot reach fades out of the way
        # rather than out of existence — you can still see the shape it left
        faded = keep is not None and says not in keep
        wide = runs("chip", says) + 12
        if not faded:
            said.box(x + px - wide / 2, y + py - 8, wide, 16, "field2")
        said.text(
            x + px - wide / 2 + 6,
            y + py + 3,
            "faded"
            if faded
            else ("hot" if says in lit else ("ink" if near > 0.9 else "chip")),
            says,
            face="chip",
        )
        if not faded:
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
    """A list of railroads is READ, not surveyed: full size, and you drag it."""
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


# the band and the clock are facts about a READING, not about a cursor: both
# fold every span in the document, and a frame per gesture cannot afford to
# do that again because the cursor moved
# a handful, newest kept: the band and the clock are asked for in the same
# frame, so clearing on a miss means neither is ever there when it is wanted
KEPT = 6
_DRAWINGS: dict[str, Drawing] = {}


def _kept(key: str, make: Callable[[], Drawing]) -> Drawing:
    """A drawing, worked out at most once for the question that produced it."""
    if key in _DRAWINGS:
        _DRAWINGS[key] = _DRAWINGS.pop(key)  # newest last
        return _DRAWINGS[key]
    _DRAWINGS[key] = make()
    while len(_DRAWINGS) > KEPT:
        del _DRAWINGS[next(iter(_DRAWINGS))]
    return _DRAWINGS[key]


def _boxes(drawn: Drawing) -> list[tuple[int, int, float, float, str]]:
    """A clock's boxes as what they MEAN: from, to, lane top, lane height, tone.

    Read off once. A frame that re-splits sixty thousand mark strings to move
    a cursor six pixels is the difference between an instrument and a
    slideshow.
    """
    out: list[tuple[int, int, float, float, str]] = []
    for mark in drawn.marks:
        p = mark.split(" ")
        if p[0] != "box":
            continue
        s0, e0, _index = (int(n) for n in p[6].split(":"))
        out.append((s0, e0, float(p[2]), float(p[4]), p[5]))
    return out


def lanes_of(
    said: Frame,
    room: Room,
    look: Look,
    spans: list[tuple[int, int, float, float, str]],
    picked: set[tuple[int, int]],
    pitch: float,
) -> None:
    """The lanes: every span the clock holds, against where the cursor stands.

    Toned as the derivation has always toned them — a closed span filled and
    outlined cool, an open one filled ONLY as far as the cursor has come and
    outlined warm, and one still ahead outlined and left empty. Filling a
    span across its whole width is what made the picture a wall of amber.
    """
    x, y, w, h = room
    lanes = y + 36
    text = look.reading.text
    window = max(8, int((w - 12) / pitch))
    start = max(0, min(int(look.at) - int(window * 0.6), max(0, len(text) - window)))
    for s0, e0, lane, deep, tone in spans:
        top = lanes + lane
        if e0 < start or s0 > start + window or top + deep > y + h:
            continue
        x1 = x + 6 + (max(s0, start) - start) * pitch
        x2 = x + 6 + (min(e0, start + window) - start) * pitch
        if tone == "eps":
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
            here = x + 6 + (min(look.at, start + window) - start) * pitch
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
    cursor = x + 6 + (min(max(look.at, start), start + window) - start) * pitch
    said.line(cursor, y + 32, cursor, y + h, "cursor")


def chart(said: Frame, room: Room, look: Look) -> None:
    """THE DERIVATION — the overview band, then the lanes under a cursor."""
    x, y, w, h = room
    stamp = f"{len(look.reading.text)}:{len(look.reading.spans)}"
    band = _kept(f"band:{stamp}", lambda: band_drawing(look.reading, 18, None, "model"))
    said.place(band, x, y + 6, w / max(1.0, band.wide), 22.0 / max(1.0, band.tall))
    which = look.says("chart.clock", "model")
    deep = int(max(20, h - 44))
    drawn = _kept(f"clock:{stamp}:{which}:{deep}", lambda: _clock(look, deep))
    picked = _picked(look, stamp)
    lanes_of(
        said,
        room,
        look,
        _spans(look, drawn, stamp),
        picked,
        PITCH * look.zoom("chart"),
    )


_PICKED: dict[str, set[tuple[int, int]]] = {}


def _picked(look: Look, stamp: str) -> set[tuple[int, int]]:
    """Every occurrence of the chosen rule — a fact about the READING.

    Twelve thousand spans re-scanned per frame because a cursor moved is
    thirty milliseconds nobody asked for; the answer only changes when the
    choice or the reading does.
    """
    if not look.chosen:
        return set()
    key = f"{stamp}:{look.chosen}"
    if key not in _PICKED:
        _PICKED.clear()
        _PICKED[key] = {
            (span.start, span.end)
            for span in look.reading.spans
            if as_written(look.it.rules, span.rule) == look.chosen
        }
    return _PICKED[key]


_SPANS: dict[str, list[tuple[int, int, float, float, str]]] = {}


def _spans(
    look: Look, drawn: Drawing, stamp: str
) -> list[tuple[int, int, float, float, str]]:
    """This clock's boxes, read off once per reading and per clock."""
    key = f"{stamp}:{look.says('chart.clock', 'model')}:{len(drawn.marks)}"
    if key not in _SPANS:
        _SPANS.clear()
        _SPANS[key] = _boxes(drawn)
    return _SPANS[key]


def _clock(look: Look, tall: int) -> Drawing:
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
    """THE SPINE — what is open at the cursor, then what just closed.

    A region, not a list that runs off the bottom: the stack can be deeper
    than the room it was given, so it scrolls like the plane it sits under,
    and JUST CLOSED keeps its own place at the foot whatever the stack does.
    """
    x, y, w, h = room
    live = look.live()
    closed = closed_before(look.reading, look.at)
    # the foot is reserved before anything is drawn into the body, and it is
    # dropped entirely when the room cannot hold it: a facet under pressure
    # derives LESS, it does not draw over its neighbour
    foot = ROW * (1 + min(len(closed), 4)) + 14
    if h < foot + ROW * 3:
        foot = 0.0
    # the line saying how much more there is needs a line of its own, or it
    # lands on top of JUST CLOSED
    body = max(ROW, h - foot - 12 - (ROW if foot else 0))
    fits = max(1, int(min(body, h - 20) // ROW))
    first = min(look.top("spine"), max(0, len(live) - fits))
    top = y + 12
    if not live:
        said.text(x + 14, top + 10, "fsub", "nothing open here")
    for span in live[first : first + fits]:
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
    if first + fits < len(live):
        said.text(
            x + 14, top + 10, "dimmer", f"{len(live) - first - fits} deeper — scroll"
        )
    if not foot:
        return
    # #closedHead / #closedBody — the foot, where it has always been
    top = y + h - foot
    said.text(x + 14, top + 10, "ftitle", "JUST CLOSED")
    top += ROW + 2
    for span in closed[:4]:
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


def _next(options: tuple[str, ...], here: str) -> str:
    """The one after this one, wrapping — what a select does when you use it."""
    at = options.index(here) if here in options else -1
    return options[(at + 1) % len(options)]


def _heads(look: Look, name: str) -> list[tuple[str, str, str, bool]]:
    """What a facet's head carries — its own controls, and nothing else's.

    A select is ONE control showing the value it is on, not a row of every
    value it could be: `#gform`, `#gview` and `#cclock` are `<select>`s, and a
    row of five chips is both a different instrument and too wide for the head
    it has to sit in.
    """
    if name == "grammar":
        forms = tuple(FORMS)
        return [(look.it.form, "form", _next(forms, look.it.form), True)]
    if name == "graph":
        keys = tuple(key for key, _word in GRAPHS)
        here = look.says("graph.view", "depth3d")
        word = dict(GRAPHS).get(here, here)
        return [
            (word, "graph.view", _next(keys, here), True),
            ("◉ focus", "graph.focus", "on", look.says("graph.focus", "off") == "on"),
            ("⧉ window", "pop", "graph", False),
        ]
    if name == "chart":
        keys = tuple(key for key, _word in CLOCKS)
        here = look.says("chart.clock", "model")
        word = dict(CLOCKS).get(here, here)
        return [(word, "chart.clock", _next(keys, here), True)]
    return []


HEADS = _heads
