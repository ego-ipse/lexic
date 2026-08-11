"""The five facets, drawn — one function each, on an open table.

The drawings themselves already exist: `paint.py` has emitted the band, the
lanes, both clocks, the rule graph, the rails and the automaton since the
first build. What lives here is only what each facet does with the room it
was given, and what its head carries. Adding a facet is a function and a
row; nothing else in the frame dispatches on which facet this is.
"""

from __future__ import annotations

from collections.abc import Callable
from collections.abc import Mapping
from typing import Any

from deixis.points import closed_before, open_at
from eidolon.camera import project
from eidolon.layout import TUNE, positions
from eidolon.topology import edges
from kairos.engine import automaton, verdicts
from kairos.parse import column, decisions, hypotheses
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
    rail_drawing,
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

# AUTO_INK — what a clone IS, in colour. A frame is tinted by the KIND of
# clone that pushed it, which is how a machine of 126 distinct clones reads as
# 126 distinct things rather than one rule entered over and over.
AUTO_INK = {
    "dispatch": "cool",
    "alt": "warm",
    "seq": "token",
    "value_str": "violet",
    "group": "dim",
}


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
        "generation",
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
        state: Mapping[str, str],
        watched: list[list[Any]],
        typed: dict[str, str] | None = None,
        frontier: int = -1,
        routes: Aside | None = None,
        generation: int = 1,
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
        self.generation = generation

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
        """The rules that light: what is open, what was chosen, what is under
        the pointer. Three cursors, one highlight, and every facet renders it
        in its own coordinates."""
        names = {as_written(self.it.rules, span.rule) for span in self.live()}
        if self.chosen:
            names.add(self.chosen)
        named = self.hovered()
        if named:
            names.add(named)
        return names

    def hovered(self) -> str:
        """Which rule the pointer is over, whatever KIND of thing it is over."""
        said = self.says("hover", "")
        kind, _, goes = said.partition(" ")
        if kind == "rule":
            return goes
        if kind == "span" and ":" in goes:
            start, _, end = goes.partition(":")
            if start.isdigit() and end.isdigit():
                held = [
                    span
                    for span in self.reading.spans
                    if span.start == int(start) and span.end == int(end)
                ]
                if held:
                    return as_written(self.it.rules, held[0].rule)
        if kind == "readerline" and goes.isdigit():
            return next(
                (
                    name
                    for name, first, last in self.it.rules
                    if first <= int(goes) <= last
                ),
                "",
            )
        return ""


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
    heads = {at: rule for rule, at, _last in look.it.rules} if name == "grammar" else {}
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
        # ▤ rail — raised beside the rule that was just clicked, the same
        # gesture shape as the pin chip: a NEW window is only ever the chip
        if name == "grammar" and heads.get(line, "") == look.chosen and look.chosen:
            _chip(said, x + 14 + runs("chip", lines[line]) + 20, top, look.chosen)
        if numbered:
            said.text(
                x + 1.5 * CELL, top + ROW - 5, "dimmer", f"{line + 1:>4}", 5 * CELL
            )
            said.hit(x, top, 6.5 * CELL, ROW, "gutter", str(line))
    said.plane(name, run, y + 8, w - (run - x) - 8, h - 12, text, first, True)
    # a plane holding text that has not been read says so, where the eye
    # leaves the plane: everything derived beside it is of the LAST reading
    if name in look.typed:
        said.text(
            x + w - 12,
            y + h - 6,
            "red",
            "edited — unread · ⏎ re-reads · ⎋ reverts",
            anchor="r",
            face="chip",
        )
    if name == "document":
        _under(said, room, look, text, first, run, rows)
    _frontier(said, room, look, text, first, run, rows)
    if name == "document":
        _pinchip(said, room, look, text, first, run, rows)


def _starts(text: str) -> list[int]:
    """Where each line begins — the one number a character offset needs."""
    out, at = [0], text.find("\n")
    while at >= 0:
        out.append(at + 1)
        at = text.find("\n", at + 1)
    return out


def _segments(
    starts: list[int], s0: int, e0: int, first: int, rows: int
) -> list[tuple[int, int, int]]:
    """One span as the rows it actually covers: (row on screen, from, to).

    A span is a range of the TEXT; the page is lines. Anything that draws
    under real text has to cross that, and doing it once here is why the
    highlight lands on the characters it is about.
    """
    out: list[tuple[int, int, int]] = []
    for i in range(rows):
        line = first + i
        if line >= len(starts):
            break
        at = starts[line]
        end = starts[line + 1] - 1 if line + 1 < len(starts) else 1 << 62
        if e0 < at or s0 > end:
            continue
        out.append((i, max(s0, at) - at, min(e0, end) - at))
    return out


def _under(
    said: Frame, room: Room, look: Look, text: str, first: int, run: float, rows: int
) -> None:
    """What is true about the document, drawn under its own characters.

    In the reference's order, because they overlap and the last one drawn
    wins: what the cursor stands inside, then every span of the chosen rule
    outlined violet, then what is under the hand, then what is selected.
    """
    _x, y, _w, _h = room
    starts = _starts(text)

    def paint(s0: int, e0: int, tone: str, ring: bool) -> None:
        for i, c0, c1 in _segments(starts, s0, e0, first, rows):
            x1, top = run + c0 * CELL, y + 8 + i * ROW
            wide = max(1.5, (c1 - c0) * CELL)
            if ring:
                said.ring(x1, top + 1, wide, ROW - 2, tone)
            else:
                said.box(x1, top, wide, ROW, tone)

    for span in look.live():
        paint(span.start, span.end, "open", False)
    if look.chosen:
        for span in look.reading.spans:
            if span.rule == look.chosen:
                paint(span.start, span.end, "violet", True)
    kind, _, goes = look.says("hover", "").partition(" ")
    if kind == "span" and ":" in goes:
        s0, _, e0 = goes.partition(":")
        paint(int(s0), int(e0), "faded", False)
    where = look.says("sel", "")
    if ":" in where:
        s0, _, e0 = where.partition(":")
        paint(int(s0), int(e0), "hotline", False)
        for i, c0, c1 in _segments(starts, int(s0), int(e0), first, rows):
            said.ring(
                run + c0 * CELL,
                y + 8 + i * ROW,
                max(1.5, (c1 - c0) * CELL),
                ROW,
                "warm",
            )


def _pinchip(
    said: Frame, room: Room, look: Look, text: str, first: int, run: float, rows: int
) -> None:
    """⌖ pin — raised at the selection, because that is where the hand is."""
    where = look.says("sel", "")
    start, _, end = where.partition(":")
    _x, y, _w, _h = room
    if not start.isdigit() or not end.isdigit() or start == end:
        return
    before = text[: min(int(start), len(text))].split("\n")
    row, column = len(before) - 1, len(before[-1])
    if not first <= row < first + rows:
        return
    top = y + 8 + (row - first) * ROW - ROW
    was = said.lift()
    wide = runs("chip", "⌖ pin") + 14
    said.box(run + column * CELL, top, wide, 15, "field2")
    for x1, y1, x2, y2 in (
        (run + column * CELL, top, run + column * CELL + wide, top),
        (run + column * CELL, top + 15, run + column * CELL + wide, top + 15),
        (run + column * CELL, top, run + column * CELL, top + 15),
        (run + column * CELL + wide, top, run + column * CELL + wide, top + 15),
    ):
        said.line(x1, y1, x2, y2, "warm")
    said.text(run + column * CELL + 7, top + 11, "warm", "⌖ pin", face="chip")
    said.hit(run + column * CELL, top, wide, 15, "pin", f"{start}:{end}")
    said.drop(was)


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

    EVERY rule the analysis classified, `predictive` included. Showing only
    the ones that gave the machine trouble made a grammar of 39 rules look
    like a grammar of one, and hid the very thing the badges are for: that
    the other 38 are settled without a single decision at runtime.

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
        # `class notes name`, then exactly that many note lines — walked by
        # the count, because a note is free text and may say anything
        i = 1
        while i < len(said):
            words = said[i].split(" ")
            i += 1
            if len(words) < 3 or words[0] not in BADGE or not words[1].isdigit():
                continue
            out[" ".join(words[2:])] = words[0]
            i += int(words[1])
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


def _chip(said: Frame, x: float, top: float, rule: str) -> None:
    """▤ rail — the chip that opens this rule as the track it describes."""
    was = said.lift()
    wide = runs("chip", "▤ rail") + 14
    said.box(x, top, wide, 15, "field2")
    for x1, y1, x2, y2 in (
        (x, top, x + wide, top),
        (x, top + 15, x + wide, top + 15),
        (x, top, x, top + 15),
        (x + wide, top, x + wide, top + 15),
    ):
        said.line(x1, y1, x2, y2, "violet")
    said.text(x + 7, top + 11, "violet", "▤ rail", face="chip")
    said.hit(x, top, wide, 15, "rail", rule)
    said.drop(was)


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
    _dials(said, room, look)


# #gtune — what the hand can change about a layout. The dials sit out of the
# picture's way, bottom-right, where a railroad list and a graph both have
# their least content. What each view offers is its own business.
DIALS = {
    "depth3d": (
        ("levelstep", 60.0, 280.0),
        ("ringscale", 0.4, 2.0),
        ("flatten", 0.2, 1.2),
    ),
    "flat": (("levelstep", 60.0, 280.0), ("ringscale", 0.4, 2.0)),
    "arcs": (("ringscale", 0.4, 2.0),),
    "rails": (),
    "automaton": (),
}


def _dials(said: Frame, room: Room, look: Look) -> None:
    """The sliders, drawn where they are least in the way, and read as state.

    A slider is configuration, and configuration is the server's: what the
    hand drags is posted, and what comes back are new places. Nothing here
    keeps a second copy of a number the layout already has.
    """
    x, y, w, h = room
    dials = DIALS.get(look.says("graph.view", "depth3d"), ())
    if not dials:
        return
    wide, step = 96.0, 18.0
    left = x + w - wide - 78
    top = y + h - len(dials) * step - 14
    for i, (name, low, high) in enumerate(dials):
        at = top + i * step
        now = float(look.says(f"graph.{name}", str(TUNE[name])))
        part = max(0.0, min(1.0, (now - low) / (high - low)))
        said.text(left - 8, at + 4, "chip", name[:4], anchor="r", face="chip")
        said.line(left, at, left + wide, at, "dimmer")
        said.box(left + part * wide - 4, at - 4, 8, 8, "cool")
        said.hit(left, at - 7, wide, 14, f"dial.{name}", f"{low}:{high}")


def _depth3d(said: Frame, room: Room, look: Look) -> None:
    """A ring per level in three-space — z is derivation distance, earned."""
    x, y, w, h = room
    shown = look.it.shown
    at = project(
        positions(shown, "rings", int(w), int(h), _tuned(look)),
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


def _tuned(look: Look) -> dict[str, float]:
    """What the hand has said about this layout, in the layout's own words."""
    return {
        name: float(look.says(f"graph.{name}", str(fallback)))
        for name, fallback in TUNE.items()
    }


def _flat(said: Frame, room: Room, look: Look) -> None:
    x, y, w, h = room
    said.place(
        graph_drawing(
            look.it.shown, "flat", int(w), int(h), _tuned(look), look.lit(), look.keep()
        ),
        x,
        y,
    )


def _arcs(said: Frame, room: Room, look: Look) -> None:
    x, y, w, h = room
    said.place(
        graph_drawing(
            look.it.shown, "arcs", int(w), int(h), _tuned(look), look.lit(), look.keep()
        ),
        x,
        y + h / 3,
    )


def _rails(said: Frame, room: Room, look: Look) -> None:
    """A list of railroads is READ, not surveyed: full size, and you drag it.

    Its scroll can also be a NAME. The drawing labels every rule's row, so
    `▤ rail` scrolls to the rule it was raised on without anyone having to
    compute a layout twice or hold a second copy of one.
    """
    x, y, w, _h = room
    drawn = rails_drawing(rails(look.it.shown), int(w - 20))
    said.place(drawn, x + 10, y + 8 - _railtop(drawn, look))


def rail(said: Frame, room: Room, look: Look) -> None:
    """ONE rule's track, alone — what the ▤ chip beside a rule opens.

    Not the whole railway scrolled to it: the chip is raised beside a single
    rule, and the window it opens is that rule and nothing else.
    """
    x, y, w, h = room
    name = look.says("rail.rule", "")
    drawn = _kept(
        f"rail:{name}:{look.reading.reader_name}",
        lambda: rail_drawing(rails(look.it.shown), name),
    )
    if not drawn.marks:
        said.text(x + 12, y + 22, "dim", f"no track for {name or 'nothing'}")
        return
    said.place(drawn, x + 12, y + 10, min(1.0, (w - 24) / max(1.0, drawn.wide)))
    if drawn.tall * min(1.0, (w - 24) / max(1.0, drawn.wide)) > h - 18:
        said.text(
            x + w - 10,
            y + h - 6,
            "dimmer",
            "resize to see more",
            anchor="r",
            face="chip",
        )


# what one notch of a wheel moves a DRAWING. A plane scrolls in lines and the
# plane knows what a line is; a stack of railroads has no lines, so the facet
# says what a notch is worth in it.
NOTCH = 26.0


def _railtop(drawn: Drawing, look: Look) -> float:
    """How far down the rails are scrolled — by notches, or to a named rule.

    On the facet's OWN key. The chip wrote `top.rails` and the wheel wrote
    `top.graph`, so the chip worked and the wheel did nothing at all.
    """
    where = look.says("top.graph", "0")
    if not where.startswith("rule:"):
        return float(look.top("graph")) * NOTCH
    wanted = where[len("rule:") :]
    for mark in drawn.marks:
        parts = mark.split(" ")
        if parts[0] == "text" and parts[3] == "name" and " ".join(parts[4:]) == wanted:
            return max(0.0, float(parts[2]) - ROW)
    return 0.0


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
    if which == "pda":
        pda_lanes(said, room, look)
        return
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


_MODES: dict[str, list[str]] = {}


def modes(look: Look) -> list[str]:
    """Each clone's mode, by seat — static per machine, read once."""
    if look.it.machine is None:
        return []
    key = f"{look.reading.reader_name}:{len(look.reading.reader_text)}"
    if key not in _MODES:
        said = automaton(look.it.machine.pda_tables()).split("\n")
        count = (
            int(said[0].split(" ")[1]) if said and said[0].startswith("#ACLONES") else 0
        )
        _MODES.clear()
        _MODES[key] = [row.split(" ")[1] for row in said[1 : 1 + count]]
    return _MODES[key]


def pda_lanes(said: Frame, room: Room, look: Look) -> None:
    """The PDA's own clock: every frame the kernel pushed, at ITS depth.

    Not the model's lanes with different numbers in them. A frame's row is
    its STACK DEPTH, its colour is the kind of clone that pushed it, a frame
    the attempt machinery rolled back is red — abandoned, the same fate
    register as Earley's dead hypotheses — and a frame wide enough to read
    SAYS WHAT IT IS. Boxes alone made the two clocks look like the same
    picture twice.
    """
    x, y, w, h = room
    lanes, floor = y + 36, y + h - 4
    text = look.reading.text
    pitch = PITCH * look.zoom("chart")
    window = max(8, int((w - 12) / pitch))
    start = max(0, min(int(look.at) - int(window * 0.6), max(0, len(text) - window)))
    seated = modes(look)
    deep = max((int(f[2]) for f in look.watched), default=0) + 1
    lane = max(2.0, min(16.0, (floor - lanes - 4) / max(1, deep)))
    for s0, e0, depth, name, ok, seat in look.watched:
        if e0 <= start or s0 >= start + window:
            continue
        top = lanes + int(depth) * lane
        if top + lane > floor:
            continue
        x1 = x + 6 + (max(int(s0), start) - start) * pitch
        x2 = max(x + 6 + (min(int(e0), start + window) - start) * pitch, x1 + 1.5)
        mode = seated[int(seat)] if 0 <= int(seat) < len(seated) else "seq"
        base = AUTO_INK.get(mode, "token")
        done, live = e0 <= look.at, e0 > look.at and s0 < look.at
        if not ok:
            # pushed by an attempt, taken away by the rollback
            if done:
                said.box(x1, top, x2 - x1, lane - 1, "lost")
            said.ring(x1, top, x2 - x1, lane - 1, "red")
        else:
            if done:
                said.box(x1, top, x2 - x1, lane - 1, f"{base}20")
            elif live:
                here = x + 6 + (min(look.at, start + window) - start) * pitch
                said.box(x1, top, max(1.5, here - x1), lane - 1, "active")
            said.ring(x1, top, x2 - x1, lane - 1, "warm" if live else base)
        # what it IS, when there is room to say it
        if x2 - x1 > 34 and lane >= 9:
            said.text(
                x1 + 3,
                top + lane - 3,
                "red" if not ok else "dim",
                str(name),
                x2 - x1 - 6,
                face="chip",
            )
        said.hit(x1, top, max(3.0, x2 - x1), lane, "frame", f"{s0}:{e0}:{depth}:{name}")
    cursor = x + 6 + (min(max(look.at, start), start + window) - start) * pitch
    said.line(cursor, y + 32, cursor, y + h, "cursor")


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
    """THE SPINE — what is open at the cursor, ACCORDING TO THE CLOCK.

    Three accounts of the same position, and picking a clock picks which one
    answers: the model's own open spans, the predictive machine's stack plus
    the decisions it made near here, or the Earley chart's column at the
    cursor with what can come next. A chip that redrew one panel and left the
    spine talking about a different engine would be a chip that lied about
    what it selected.
    """
    STACKS.get(look.says("chart.clock", "model"), _model_stack)(said, room, look)


def _rows(
    said: Frame, room: Room, look: Look, rows: list[tuple[str, str, str]], foot: bool
) -> float:
    """A stack, scrolled — `(gutter, words, tone)` per row, deepest last."""
    x, y, w, h = room
    keep = ROW * 5 + 14 if foot else 0.0
    if h < keep + ROW * 3:
        keep = 0.0
    body = max(ROW, h - keep - 12 - (ROW if keep else 0))
    fits = max(1, int(min(body, h - 20) // ROW))
    first = min(look.top("spine"), max(0, len(rows) - fits))
    # the gutter is as wide as the widest thing IN it: `@4,188` is not `d7`,
    # and a column of origins clipped to `@41…` says nothing at all
    step = max((len(g) for g, _w, _t in rows), default=0) * CELL + (8 if rows else 0)
    top = y + 12
    for gutter, words, tone in rows[first : first + fits]:
        if gutter:
            said.text(x + 14, top + 10, "dimmer", gutter)
        said.text(x + 14 + step, top + 10, tone, words, w - 34 - step)
        top += ROW
    if first + fits < len(rows):
        said.text(
            x + 14, top + 10, "dimmer", f"{len(rows) - first - fits} more — scroll"
        )
    return keep


def _model_stack(said: Frame, room: Room, look: Look) -> None:
    """model — the open model spans, as ever."""
    x, y, w, h = room
    live = look.live()
    rows = [
        (
            f"d{span.depth}",
            f"{as_written(look.it.rules, span.rule)} {span.start:,}..{span.end:,}",
            "warm" if span is live[-1] else "ink",
        )
        for span in live
    ]
    if not rows:
        said.text(x + 14, y + 22, "fsub", "nothing open here")
    keep = _rows(said, room, look, rows, foot=True)
    for span in live:
        said.hit(x, y, 0, 0, "span", f"{span.start}:{span.end}")
    if not keep:
        return
    top = y + h - keep
    said.text(x + 14, top + 10, "ftitle", "JUST CLOSED")
    top += ROW + 2
    for span in closed_before(look.reading, look.at)[:4]:
        name = as_written(look.it.rules, span.rule)
        said.text(
            x + 14, top + 10, "dim", f"{name} {span.start:,}..{span.end:,}", w - 30
        )
        said.hit(x, top, w, ROW, "span", f"{span.start}:{span.end}")
        top += ROW


def _pda_stack(said: Frame, room: Room, look: Look) -> None:
    """pda — the kernel's own frames at the cursor, and the choices near it."""
    x, y, _w, _h = room
    open_here = [
        (int(s0), int(e0), int(depth), str(name), bool(ok))
        for s0, e0, depth, name, ok, _seat in look.watched
        if s0 <= look.at < e0
    ]
    rows = [
        (
            f"d{depth}",
            f"{name} {s0:,}..{e0:,}" + ("" if ok else "  ROLLED BACK"),
            "warm" if ok else "red",
        )
        for s0, e0, depth, name, ok in sorted(open_here, key=lambda f: f[2])
    ]
    if not rows:
        said.text(
            x + 14, y + 22, "fsub", "the machine holds no frame here — see the graph"
        )
    near = [
        (at, said_words, chose)
        for at, said_words, chose in decisions(look.watched)
        if abs(at - look.at) < 400
    ][:6]
    rows += [("", f"{at:,}  {words} → {chose}", "violet") for at, words, chose in near]
    _rows(said, room, look, rows, foot=False)


def _earley_stack(said: Frame, room: Room, look: Look) -> None:
    """earley — the cursor's own column, as dotted items, and what can follow."""
    x, y, _w, _h = room
    machine = look.it.machine
    if machine is None:
        said.text(x + 14, y + 22, "fsub", "this reading has no machine")
        return
    said_column = _column(look, int(look.at))
    rows: list[tuple[str, str, str]] = []
    expecting = False
    for line in said_column.split("\n"):
        if line.startswith("#COLUMN"):
            continue
        if line.startswith("#EXPECT"):
            expecting = True
            rows.append(("", "CAN COME NEXT", "ftitle"))
            continue
        if not line.strip():
            continue
        if expecting:
            rows.append(("", line, "cool"))
            continue
        origin, _, rest = line.partition(" ")
        role, _, item = rest.partition(" ")
        rows.append((f"@{origin}", item, "green" if role == "complete" else "ink"))
    if not rows:
        said.text(x + 14, y + 22, "fsub", "the chart holds nothing at this character")
    _rows(said, room, look, rows, foot=False)


_COLUMNS: dict[str, str] = {}


def _column(look: Look, at: int) -> str:
    """One column of the chart, fetched per cursor move and kept per reading."""
    key = f"{len(look.reading.text)}:{at}"
    if key not in _COLUMNS:
        if len(_COLUMNS) > 8:
            _COLUMNS.clear()
        _COLUMNS[key] = column(look.it.machine, look.reading.text, at)
    return _COLUMNS[key]


STACKS: dict[str, Callable[[Frame, Room, Look], None]] = {
    "model": _model_stack,
    "pda": _pda_stack,
    "earley": _earley_stack,
}


def pin(said: Frame, room: Room, look: Look) -> None:
    """A PIN — one span, held still while the reading moves on around it.

    The ruled exception to regions: a window, because simultaneity is the one
    thing a tiling cannot express. It carries what it is about in its own
    layer, so it keeps saying that even when the cursor has gone elsewhere,
    and it says out loud when the reading it was made against is gone.
    """
    x, y, w, h = room
    where = look.says("pin.span", "")
    start, _, end = where.partition(":")
    if not start.isdigit() or not end.isdigit():
        said.text(x + 14, y + 22, "fsub", "this window is about nothing yet")
        return
    s0, e0 = int(start), int(end)
    # what this range IS: the exact span if there is one, else the smallest
    # occurrence covering it — the same answer selecting text gets, because
    # it is the same question
    covering = [
        span
        for span in look.reading.spans
        if span.start <= s0 and span.end >= max(e0, s0 + 1)
    ]
    span = min(covering, key=lambda s: s.end - s.start) if covering else None
    was = look.says("pin.gen", "")
    if was.isdigit() and int(was) != look.generation:
        # the reading it was made against is gone: it still says what it said,
        # and says that it is saying it about a text that has moved on
        said.text(
            x + w - 14,
            y + 22,
            "red",
            f"STALE · made against gen {was}",
            anchor="r",
            face="chip",
        )
    said.text(x + 14, y + 22, "ftitle", f"{s0:,}..{e0:,}")
    at = x + 14 + runs("ftitle", f"{s0:,}..{e0:,}") + 12
    if span is not None:
        name = as_written(look.it.rules, span.rule)
        exact = span.start == s0 and span.end == e0
        said.text(
            at,
            y + 22,
            "warm" if exact else "dim",
            f"{name} · d{span.depth}"
            + ("" if exact else f" · covering {span.start:,}..{span.end:,}"),
            w - (at - x) - 20,
        )
        said.hit(x, y + 8, w, ROW, "rule", name)
    else:
        said.text(at, y + 22, "red", "no occurrence covers this any more")
    # the text it is about, wrapped to the window rather than clipped
    room_chars = max(8, int((w - 28) / CELL))
    lines = _wrapped(look.reading.text[s0:e0], room_chars)
    for i, line in enumerate(lines[: max(1, int((h - 52) // ROW))]):
        said.text(x + 14, y + 52 + i * ROW, "ink", line)
    if len(lines) > (h - 52) // ROW:
        said.text(
            x + 14, y + h - 8, "dimmer", f"{len(lines)} lines · resize to see more"
        )


def _wrapped(said: str, room: int) -> list[str]:
    """Text broken to a width — a window shows what it holds, it does not clip."""
    out: list[str] = []
    for line in said.split("\n"):
        while len(line) > room:
            out.append(line[:room])
            line = line[room:]
        out.append(line)
    return out


DRAWN: dict[str, Callable[[Frame, Room, Look], None]] = {
    "pin": pin,
    "rail": rail,
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
    """What a facet's head carries — its own controls, then the ones every
    facet has.

    A select is ONE control showing the value it is on, not a row of every
    value it could be: `#gform`, `#gview` and `#cclock` are `<select>`s, and a
    row of five chips is both a different instrument and too wide for the head
    it has to sit in.

    `⧉` and `⊞` belong to EVERY facet. Popping one out was written for the
    graph alone, which made it a property of that picture rather than of
    facets — and a window is not something only one of them can be.
    """
    own: list[tuple[str, str, str, bool]] = []
    if name == "grammar":
        forms = tuple(FORMS)
        own = [(look.it.form, "form", _next(forms, look.it.form), True)]
    elif name == "graph":
        keys = tuple(key for key, _word in GRAPHS)
        here = look.says("graph.view", "depth3d")
        own = [
            (dict(GRAPHS).get(here, here), "graph.view", _next(keys, here), True),
            ("◉ focus", "graph.focus", "on", look.says("graph.focus", "off") == "on"),
        ]
    elif name == "chart":
        keys = tuple(key for key, _word in CLOCKS)
        here = look.says("chart.clock", "model")
        own = [(dict(CLOCKS).get(here, here), "chart.clock", _next(keys, here), True)]
    # ⧉ pops it out; ⊞ opens a SECOND one, which is the same window with its
    # own layer — two views of one facet, each with its own camera and scroll
    return [*own, ("⧉", "pop", name, False), ("⊞", "clone", name, False)]


HEADS = _heads
