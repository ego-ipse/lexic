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
from opsis.frame.panels import Control
from opsis.frame.tones import runs
from opsis.grammar import rails
from opsis.paint import (
    Drawing,
    automaton_drawing,
    band_drawing,
    chart_drawing,
    clock_drawing,
    packed,
    rail_drawing,
    rails_drawing,
)
from opsis.scene import Staged
from praxis.reading import Reading, as_written
from praxis.routes import Aside

__all__ = ["DRAWN", "HEADS", "Look", "Room"]

Room = tuple[float, float, float, float]
# one row of the spine, whichever clock is answering: what stands in the
# gutter, the thing itself, its extent, and the tone the thing is said in
# ...and what that row IS, when a hand can land on it. Only the model spine's
# rows carry one: `drawPdaSpine` and `drawEarleySpine` build rows with no
# `dataset.i`, so clicking those does nothing in the reference either.
Row = tuple[str, str, str, str, str]

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

# `chart.js`: `const pad = 10` — the band, the window outline, the lanes and
# the cursor all measure from it. Three different left edges in one facet is
# why clicking the lanes landed on the wrong character.
PAD = 10.0

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
        "_live",
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
        self._live = None

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
        if self._live is None:
            self._live = open_at(self.reading, self.at)
        return self._live

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
def _showing(look: Look, name: str, first: int, rows: int) -> int:
    """Where the plane really starts — NEAREST, when something must be seen.

    `scrollIntoView({block: "nearest"})`: a line that is already on screen
    does not move the page, and one that is not is brought just inside.
    Scrolling by hand says where you want to be, and clears this.
    """
    said = look.says(f"show.{name}", "")
    if not said.isdigit() or rows < 3:
        return first
    line = int(said)
    if name == "document":
        # `followCursor`: the document is being READ as it goes, so when the
        # cursor leaves the page it lands four tenths down — where the eye
        # already is — not one line inside the edge it just crossed.
        if first + 2 <= line < first + rows - 3:
            return first
        return max(0, line - int(rows * 0.4))
    if line < first:
        return line
    if line >= first + rows - 2:
        return max(0, line - rows + 3)
    return first


def _plane(
    said: Frame, room: Room, look: Look, name: str, text: str, numbered: bool
) -> None:
    """A block of REAL text, with what is true about it drawn underneath."""
    x, y, w, h = room
    lines = text.split("\n")
    # Ctrl+wheel over a text pane is `applyDocZoom`: --fs and --lh both scale,
    # so every number under the text scales with them or the drawing lands on
    # the wrong characters
    zoom = look.zoom("doc")
    cell, row = CELL * zoom, ROW * zoom
    rows = max(0, int((h - 8) // row))
    first = _showing(look, name, look.top(name), rows)
    # .ln .g { width: 5ch; padding-right: 1.5ch } — the gutter is 6.5ch
    run = x + (6.5 * cell if numbered else 1.5 * cell)
    lit = _held(look, name)
    badges = _badges(look) if name == "grammar" else {}
    heads = {at: rule for rule, at, _last in look.it.rules} if name == "grammar" else {}
    for i in range(rows):
        line = first + i
        if line >= len(lines):
            break
        top = y + 8 + i * row
        tone = lit.get(line, "")
        if tone:
            said.box(x, top, w, row, tone)
        badge = badges.get(heads.get(line, ""), "")
        if badge:
            _badge(said, x + w - 12, top + 3, badge)
        if numbered:
            said.text(
                x + 1.5 * cell, top + row - 5, "dimmer", f"{line + 1:>4}", 5 * cell
            )
            said.hit(x, top, 6.5 * cell, row, "gutter", str(line))
    # ONLY THE DOCUMENT IS TYPED IN. `#grammarBody` is built of `.ln` rows
    # and is not editable, which is what lets Space play, `g` show the graph
    # and `[` `]` change speed while the reader has the hand — a reader you
    # can type into swallows every key the status bar promises.
    said.plane(
        name,
        run,
        y + 8,
        w - (run - x) - 8,
        h - 12,
        text,
        first,
        name == "document",
        zoom,
        "dim" if name == "grammar" else "ink",
    )
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
        _under(said, room, look, text, first, run, rows, cell, row)
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


# where a chosen rule OCCURS — a fact about the reading and the rule, not
# about the page. Scanning twelve thousand spans and respelling every one of
# them per frame cost 39.6ms against 7.3, so scrolling with a rule chosen
# outran the server and the document jumped.
_WHERE: dict[str, list[tuple[int, int]]] = {}


def occurrences(look: Look) -> list[tuple[int, int]]:
    """Every span of the chosen rule, worked out once for that rule.

    AS WRITTEN: a span carries the codegen name — `json-text` — and the
    reader shows the source's spelling, `JSON-text`. Comparing the two
    directly meant the start rule, and every rule codegen respelled,
    highlighted nothing at all.
    """
    if not look.chosen:
        return []
    key = f"{look.generation}:{len(look.reading.spans)}:{look.chosen}"
    if key not in _WHERE:
        _WHERE.clear()
        _WHERE[key] = [
            (span.start, span.end)
            for span in look.reading.spans
            if as_written(look.it.rules, span.rule) == look.chosen
        ]
    return _WHERE[key]


def _under(
    said: Frame,
    room: Room,
    look: Look,
    text: str,
    first: int,
    run: float,
    rows: int,
    cell: float = CELL,
    row: float = ROW,
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
            x1, top = run + c0 * cell, y + 8 + i * row
            wide = max(1.5, (c1 - c0) * cell)
            if ring:
                said.ring(x1, top + 1, wide, row - 2, tone)
            else:
                said.box(x1, top, wide, row, tone)

    for span in look.live():
        paint(span.start, span.end, "open", False)
    # A prolific rule can have thousands of occurrences. Reject the ones
    # outside this page once; asking `_segments` to walk every visible row for
    # every off-screen occurrence is the scroll-time multiplication that
    # produced the spike.
    page_start = starts[first] if first < len(starts) else len(text)
    after = min(len(starts), first + rows)
    page_end = starts[after] if after < len(starts) else len(text)
    for start, end in occurrences(look):
        if end >= page_start and start <= page_end:
            paint(start, end, "violet", True)
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
    said.ring(run + column * CELL, top, wide, 15, "warm")
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
    """Which lines are lit, and in what — `.ln.live`, `.ln.lit`, `.ln.hot`.

    THREE STATES, not two, and they are three different questions. `.live` is
    the rules the derivation is inside RIGHT NOW, so playing walks the grammar
    itself rather than only the picture of it. `.lit` is what has been chosen.
    `.hot` is what the hand is on. They are drawn weakest first, so the hand
    always wins the line it is over.
    """
    if name != "grammar":
        return {}
    live = {as_written(look.it.rules, span.rule) for span in look.live()}
    hovered = look.hovered()
    out: dict[int, str] = {}
    for tone, wanted in (
        ("liveline", live),
        ("lit", {look.chosen} if look.chosen else set()),
        ("hotline", {hovered} if hovered else set()),
    ):
        for rule, first, last in look.it.rules:
            if rule not in wanted:
                continue
            for line in range(first, last + 1):
                out[line] = tone
    return out


def _badge(said: Frame, right: float, top: float, kind: str) -> None:
    """One rule's verdict, worn on its own head line, in that class's colour."""
    tone = BADGE.get(kind, "dimmer")
    wide = runs("chip", kind) + 12
    said.ring(right - wide, top, wide, 13, tone)
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
    GRAPHVIEWS.get(look.says("graph.view", "depth3d"), _flat)(said, room, look)
    _dials(said, room, look)


# #gtune — what the hand can change about a layout. The dials sit out of the
# picture's way, bottom-right, where a railroad list and a graph both have
# their least content. What each view offers is its own business.
# `index.html`'s own four, with their own bounds and steps: a control the
# browser owns cannot be painted, and a drawn slider cannot be grabbed,
# arrowed or tabbed to. `labelscale` is --glabel, and was never here at all.
DIAL = {
    "levelstep": ("depth", 60.0, 280.0, 10.0),
    "ringscale": ("ring", 0.4, 2.0, 0.05),
    "flatten": ("flat", 0.2, 1.2, 0.05),
    "labelscale": ("label", 0.7, 1.8, 0.05),
}
DIALS = {
    "depth3d": ("levelstep", "ringscale", "flatten", "labelscale"),
    "flat": ("levelstep", "ringscale", "labelscale"),
    "arcs": ("levelstep", "ringscale", "labelscale"),
    "rails": ("levelstep", "labelscale"),
    "automaton": ("levelstep", "ringscale", "labelscale"),
}
DIAL_WORDS = {
    "flat": {"levelstep": "cols", "ringscale": "rows"},
    "arcs": {"levelstep": "pitch", "ringscale": "lift"},
    "rails": {"levelstep": "gap"},
    "automaton": {"levelstep": "depth", "ringscale": "spread"},
}
DIAL_DEFAULT = {**TUNE, "labelscale": 1.0}


def _dials(said: Frame, room: Room, look: Look) -> None:
    """#gtune — REAL range inputs, placed where they are least in the way.

    A slider is a control the browser owns: it can be grabbed, arrowed and
    tabbed to, and none of that can be painted. The frame says where each one
    goes, what it spans and where it stands; the browser draws it.
    """
    x, y, w, h = room
    view = look.says("graph.view", "depth3d")
    wanted = DIALS.get(view, ())
    if not wanted:
        return
    # `#gtune`: bottom 8, right 10, padding 8x10, gap 5, a 4ch label column
    # and a 96px track — on a translucent panel behind a hairline
    step, track, name_wide = 17.0, 96.0, 4 * 5.4 + 8
    inside = name_wide + track
    left = x + w - 10 - inside - 10
    top = y + h - 8 - len(wanted) * step - 11
    said.box(left - 10, top - 8, inside + 20, len(wanted) * step + 11, "tune")
    said.ring(left - 10, top - 8, inside + 20, len(wanted) * step + 11, "hair")
    for i, name in enumerate(wanted):
        default_word, low, high, by = DIAL[name]
        word = DIAL_WORDS.get(view, {}).get(name, default_word)
        at = top + i * step
        now = float(look.says(f"graph.{name}", str(DIAL_DEFAULT[name])))
        # `grid-template-columns: 4ch 1fr` sets the column, not a clip: a
        # five-letter word spills into the 8px gap rather than becoming "dep…"
        said.text(left, at + 10, "dial", word, face="dial")
        said.slider(
            f"graph.{name}", left + name_wide, at, track, 12, now, low, high, by
        )


def camera(look: Look, room: Room) -> tuple[float, float, float]:
    """Where the hand has put this picture, and how close: pan x, pan y, zoom.

    A CAMERA PER VIEW. `v.cams[mode]` saves the one you are leaving and
    restores the one you are entering — the railroad you had scrolled and the
    orbit you had turned are not the same camera and never were.
    """
    _x, _y, w, h = room
    view = look.says("graph.view", "depth3d")
    return (
        float(look.says(f"graph.{view}.pan.x", "0")) * w,
        float(look.says(f"graph.{view}.pan.y", "0")) * h,
        look.zoom(f"graph.{view}"),
    )


def _nodes(said: Frame, room: Room, look: Look, view: str) -> None:
    """The three PROJECTED views — places in, edges and chips out.

    `drawGraphView` builds only TWO of the five from a drawing: the railroads
    and the automaton. depth3d, flat and arcs project their places and draw
    their own edges and chips, because a node has to know whether it is lit,
    chosen or under the hand, and a drawing made before any of that was asked
    cannot say.
    """
    x, y, w, h = room
    px, py, _k = camera(look, room)
    x, y = x + px, y + py
    shown = look.it.shown
    laid = _laid(look, view, w, h)
    named = {name: as_written(look.it.rules, name) for name in laid}
    if view == "depth3d":
        at = project(
            laid,
            float(look.says("graph.depth3d.yaw", "0.42")),
            float(look.says("graph.depth3d.pitch", "0.92")),
            w,
            h,
            # ITS OWN zoom: this was reading `graph.zoom`, a key nothing
            # writes, which is why three-space would not zoom at all.
            look.zoom("graph.depth3d"),
        )
    else:
        at = _spread(
            laid, named, w, h, look.zoom(f"graph.{view}"), _framed(look, view, w, h)
        )
    live_path = [as_written(look.it.rules, span.rule) for span in look.live()]
    live = set(live_path)
    live_edges = set(zip(live_path, live_path[1:]))
    hovered = look.hovered()
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
        step = (named.get(a, a), named.get(b, b)) in live_edges
        tone = (
            "hot"
            if step
            else (
                "loop"
                if look.chosen in (named.get(a, a), named.get(b, b))
                else "cool_wash"
            )
        )
        if view != "arcs":
            said.line(
                x + one[0],
                y + one[1],
                x + two[0],
                y + two[1],
                tone,
                2.0 if step else 1.0,
            )
            continue
        if a == b:
            # a rule that refers to ITSELF is a ring, not an arc to nowhere
            said.arc(x + one[0], y + one[1] - 9, 7.0, tone)
            continue
        # a FORWARD reference lifts above its line, a backward one below, by
        # `(12 + |dx| * 0.28) * ringscale`
        aim = 1.0 if two[0] >= one[0] else -1.0
        lift = (
            aim
            * (12 + abs(two[0] - one[0]) * 0.28)
            * float(look.says("graph.ringscale", str(TUNE.get("ringscale", 1.0))))
        )
        said.curve(
            x + one[0],
            y + one[1],
            x + (one[0] + two[0]) / 2,
            y + one[1] - lift,
            x + two[0],
            y + two[1],
            tone,
            2.0 if step else 1.0,
        )
    # far first, so what is nearest is drawn last and reads as nearest
    # .gchip.start — where every derivation begins, and it is warm
    start = next((name for name, at_ in look.it.deep.items() if at_ == 0), "")
    for name in sorted(at, key=lambda n: at[n][2]):
        px, py, near = at[name]
        says = named.get(name, name)
        # ◉ focus: what the chosen rule cannot reach fades out of the way
        # rather than out of existence — you can still see the shape it left
        faded = keep is not None and says not in keep
        # .gchip: a NAME IN A BOX, and its distance is in the size of it
        # `--glabel` scales `.gchip`'s font-size. Three faces are what a mark
        # can name, so the dial biases WHICH of them a node's distance earns:
        # at 1.8 every name is near-sized, at 0.7 every name is far.
        lit_by = near * float(look.says("graph.labelscale", "1"))
        face = "gnear" if lit_by > 1.1 else ("chip" if lit_by > 0.85 else "gfar")
        padding, tall = {
            "gnear": (14.0, 19.0),
            "chip": (12.0, 16.0),
            "gfar": (10.0, 13.0),
        }[face]
        wide = runs(face, says) + padding
        # .near / .start / .marked / .hot — the four things a node can be
        hot = says == hovered
        is_live = says in live
        edge = (
            "warm"
            if is_live or says == start or hot
            else (
                "violet"
                if says == look.chosen
                else ("cool" if near > 0.85 else "dimmer")
            )
        )
        # In the arcs view ordinary rules are points on the declaration line.
        # Naming every one turns the view into a pile of labels and contradicts
        # the reference's `.gchip.dot` contract.
        if view == "arcs" and says not in {hovered, look.chosen, start}:
            radius = 4.0 * max(0.55, min(near, 1.2))
            said.dot(x + px, y + py, radius, "dimmer" if faded else "cool")
            said.hit(
                x + px - radius,
                y + py - radius,
                radius * 2,
                radius * 2,
                "rule",
                says,
            )
            continue
        if faded:
            said.text(px + x - wide / 2 + 6, y + py + 3, "faded", says, face=face)
            continue
        # .gchip.hot: the warm fills, and the name is read out of it
        said.box(
            x + px - wide / 2, y + py - tall / 2, wide, tall, "hot" if hot else "field2"
        )
        for x1, y1, x2, y2 in (
            (
                x + px - wide / 2,
                y + py - tall / 2,
                x + px + wide / 2,
                y + py - tall / 2,
            ),
            (
                x + px - wide / 2,
                y + py + tall / 2,
                x + px + wide / 2,
                y + py + tall / 2,
            ),
            (
                x + px - wide / 2,
                y + py - tall / 2,
                x + px - wide / 2,
                y + py + tall / 2,
            ),
            (
                x + px + wide / 2,
                y + py - tall / 2,
                x + px + wide / 2,
                y + py + tall / 2,
            ),
        ):
            said.line(x1, y1, x2, y2, edge)
        said.text(
            x + px - wide / 2 + 6,
            y + py + 3,
            "field"
            if hot
            else (
                "warm"
                if is_live or says == start
                else (
                    "violet"
                    if says == look.chosen
                    else ("ink" if near > 0.85 else "dim")
                )
            ),
            says,
            face=face,
        )
        said.hit(x + px - wide / 2, y + py - tall / 2, wide, tall, "rule", says)


def _spread(
    laid: dict[str, tuple[float, float, float]],
    named: dict[str, str],
    w: float,
    h: float,
    zoom: float,
    frame: dict[str, tuple[float, float, float]],
) -> dict[str, tuple[float, float, float]]:
    """A flat layout, fitted and centred — `{x, y, s: 1}` with the camera on.

    `drawGraphView` projects a non-3d view as the place itself, then fits
    against the extent and centres on its middle. Every node's `s` is 1, so
    every chip is `.near`: ink on cool, whatever its depth.
    """
    if not laid:
        return {}
    source = frame or laid
    xs = [p[0] for p in source.values()]
    ys = [p[1] for p in source.values()]
    x0, x1 = min(xs), max(xs)
    y0, y1 = min(ys), max(ys)
    mx, my = (x0 + x1) / 2, (y0 + y1) / 2
    pad_x = max(
        10.0,
        max(
            ((runs("chip", name) + 12) / 2 + 4 for name in named.values()), default=10.0
        ),
    )
    pad_y = 12.0
    avail_w = max(60.0, w - 2 * pad_x)
    avail_h = max(60.0, h - 2 * pad_y)
    k = (
        min(
            avail_w / max(40.0, x1 - x0),
            avail_h / max(40.0, y1 - y0),
            2.4,
        )
        * zoom
    )
    out = {
        name: (w / 2 + (p[0] - mx) * k, h / 2 + (p[1] - my) * k, 1.0)
        for name, p in laid.items()
    }
    # `graph.js` frames the first column at 70px only when the projected
    # picture is wider than the room. Centring an overflowing graph hides its
    # beginning and makes horizontal exploration start in the middle.
    if (x1 - x0) * k > avail_w + 2:
        shift = 70.0 - min(px for px, _py, _near in out.values())
        out = {name: (px + shift, py, near) for name, (px, py, near) in out.items()}
    return out


def _tuned(look: Look) -> dict[str, float]:
    """What the hand has said about this layout, in the layout's own words."""
    return {
        name: float(look.says(f"graph.{name}", str(fallback)))
        for name, fallback in TUNE.items()
    }


_LAYOUTS: dict[tuple[object, ...], dict[str, tuple[float, float, float]]] = {}


def _laid(
    look: Look, view: str, wide: float, tall: float
) -> dict[str, tuple[float, float, float]]:
    """A layout changes with its tuning and room, never with the camera."""
    dial = _tuned(look)
    key = (
        id(look.reading),
        look.generation,
        view,
        int(wide),
        int(tall),
        *sorted(dial.items()),
    )
    if key not in _LAYOUTS:
        if len(_LAYOUTS) >= 8:
            del _LAYOUTS[next(iter(_LAYOUTS))]
        layout_view = {"depth3d": "rings"}.get(view, view)
        _LAYOUTS[key] = positions(
            look.it.shown, layout_view, int(wide), int(tall), dial
        )
    return _LAYOUTS[key]


_FRAMES: dict[tuple[object, ...], dict[str, tuple[float, float, float]]] = {}


def _framed(
    look: Look, view: str, wide: float, tall: float
) -> dict[str, tuple[float, float, float]]:
    """The untouched layout which establishes a view's stable frame."""
    layout_view = {"depth3d": "rings"}.get(view, view)
    key = (id(look.reading), look.generation, view, int(wide), int(tall))
    if key not in _FRAMES:
        if len(_FRAMES) >= 8:
            del _FRAMES[next(iter(_FRAMES))]
        _FRAMES[key] = positions(look.it.shown, layout_view, int(wide), int(tall), TUNE)
    return _FRAMES[key]


def _depth3d(said: Frame, room: Room, look: Look) -> None:
    """A ring per level in three-space — z is derivation distance, earned."""
    _nodes(said, room, look, "depth3d")


def _flat(said: Frame, room: Room, look: Look) -> None:
    """Levels left to right — the SAME path as three-space, flattened.

    `drawGraphView` builds only TWO of the five views from a drawing: the
    railroads and the automaton. This one projects the places and draws its
    own edges and its own chips, exactly as the three-space view does, and
    for the same reason — a node has to know whether it is lit, chosen or
    under the hand, and a drawing made before any of that was asked cannot.
    """
    _nodes(said, room, look, "flat")


def _arcs(said: Frame, room: Room, look: Look) -> None:
    """One line of rules, every reference an arc over it.

    A forward reference lifts ABOVE the line and a backward one below, by
    `(12 + |dx| * 0.28) * ringscale`, and a rule that refers to itself is a
    ring. Only the start, the chosen and the hovered are named; the rest are
    `.gchip.dot`.
    """
    _nodes(said, room, look, "arcs")


def _label_face(look: Look) -> str:
    """The three real drawing faces nearest the continuous label dial."""
    scale = float(look.says("graph.labelscale", "1"))
    return "gfar" if scale < 0.9 else ("drawn" if scale < 1.25 else "gnear")


def _rails(said: Frame, room: Room, look: Look) -> None:
    """A list of railroads is READ, not surveyed: full size, and you drag it.

    Its scroll can also be a NAME. The drawing labels every rule's row, so
    `▤ rail` scrolls to the rule it was raised on without anyone having to
    compute a layout twice or hold a second copy of one.
    """
    x, y, w, _h = room
    px, py, k = camera(look, room)
    drawn = rails_drawing(rails(look.it.shown), int(w - 20))
    gap = (
        float(look.says("graph.levelstep", str(TUNE["levelstep"]))) / TUNE["levelstep"]
    )
    said.place(
        drawn,
        x + 10 + px,
        y + 8 + py - _railtop(drawn, look) * gap,
        k,
        k * gap,
        face=_label_face(look),
    )


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
    scale = min(1.0, (w - 24) / max(1.0, drawn.wide))
    wid = look.says("rail.window", "")
    said.place(
        drawn,
        x + 12,
        y + 10,
        scale,
        face=_label_face(look),
        door="railgo" if wid else "rule",
        prefix=f"{wid}:" if wid else "",
    )
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
    x, y, w, h = room
    px, py, k = camera(look, room)
    tables = look.it.machine.pda_tables()
    step = float(look.says("graph.levelstep", str(TUNE["levelstep"])))
    spread = 15.0 * float(look.says("graph.ringscale", str(TUNE["ringscale"])))
    seats = {
        seat for s0, e0, _d, _n, ok, seat in look.watched if ok and s0 <= look.at < e0
    }
    seen = {seat for _s0, e0, _d, _n, ok, seat in look.watched if ok and e0 <= look.at}
    drawn = automaton_drawing(automaton(tables, step, spread), seats, seen - seats)
    # Match space_1's Drawing painter exactly: the automaton is one shape,
    # uniformly fitted into its room from the top-left. Independent x/y
    # scaling turned its circular states into ellipses and made the clone
    # columns look like a different machine.
    fit = min(
        1.0,
        max(
            0.25,
            min(w / max(1.0, drawn.wide), h / max(1.0, drawn.tall)),
        ),
    )
    said.place(
        drawn,
        x + px,
        y + py,
        fit * k,
        face=_label_face(look),
        recolor={"cool": "cool_wash"},
    )


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


def window_of(look: Look, w: float) -> tuple[int, int, float]:
    """Which slice of the document the lanes are of: where it starts, how
    wide, and what one character is worth in pixels.

    THE WINDOW STAYS PUT until the cursor leaves it. `chart.js` keeps `view0`
    and only re-centres when the cursor falls before the window or past 72%
    of it — a window recomputed from the cursor on every frame slides out
    from under the hand that just clicked in it, which is what made clicking
    the right-hand side of the lanes throw the picture somewhere else.
    """
    pitch = PITCH * look.zoom("chart")
    window = max(8, int((w - 2 * PAD) / pitch))
    length = len(look.reading.text)
    said = look.says("chart.at", "")
    was = int(said) if said.isdigit() else 0
    start = max(0, min(was, max(0, length - window)))
    if look.at < start or look.at > start + window * 0.72:
        start = max(0, min(int(look.at - window * 0.6), max(0, length - window)))
    return start, window, pitch


def _pointed(said: str) -> tuple[int, int]:
    """A span a cursor is on, as the pair the lanes are keyed by."""
    where = said.partition(" ")[2] if said.startswith("span ") else said
    start, _, end = where.partition(":")
    return (int(start), int(end)) if start.isdigit() and end.isdigit() else (-1, -1)


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
    start, window, _pitch = window_of(look, w)
    hand, chose = _pointed(look.says("hover", "")), _pointed(look.says("sel", ""))
    for s0, e0, lane, deep, tone in spans:
        top = lanes + lane
        if e0 < start or s0 > start + window or top + deep > y + h:
            continue
        x1 = x + PAD + (max(s0, start) - start) * pitch
        x2 = x + PAD + (min(e0, start + window) - start) * pitch
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
            here = x + PAD + (min(look.at, start + window) - start) * pitch
            said.box(x1, top, max(1.5, here - x1), deep, "active")
        said.ring(
            x1,
            top,
            max(1.5, x2 - x1),
            deep,
            "cool" if e0 <= look.at else ("warm" if s0 < look.at else "pending"),
        )
        # THE SAME SPAN, WHEREVER IT IS. A span under the hand or chosen in
        # the spine is outlined here too — ink for the hand, warm for the
        # selection, violet for every span of the chosen rule. Three cursors,
        # one highlight, each facet in its own coordinates.
        if (s0, e0) == hand:
            said.ring(x1 - 1.5, top - 1.5, max(1.5, x2 - x1) + 3, deep + 3, "ink")
        elif (s0, e0) == chose:
            said.ring(x1 - 1.5, top - 1.5, max(1.5, x2 - x1) + 3, deep + 3, "warm")
        if (s0, e0) in picked:
            said.ring(x1 - 1.5, top - 1.5, max(1.5, x2 - x1) + 3, deep + 3, "violet")
        said.hit(x1, top, max(3.0, x2 - x1), deep, "span", f"{s0}:{e0}")
    cursor = x + PAD + (min(max(look.at, start), start + window) - start) * pitch
    said.line(cursor, y + 32, cursor, y + h, "cursor")


def chart(said: Frame, room: Room, look: Look) -> None:
    """THE DERIVATION — the overview band, then the lanes under a cursor."""
    x, y, w, h = room
    stamp = f"{len(look.reading.text)}:{len(look.reading.spans)}"
    which = look.says("chart.clock", "model")
    # THE BAND IS THE CLOCK'S OWN. Only the model's overview is the reading's
    # structure; the PDA's is its stack depth and Earley's is how many
    # hypotheses were alive — a band that stayed the model's while the lanes
    # changed underneath it said the same thing about three different runs.
    if which == "model" or look.it.machine is None:
        band = _kept(
            f"band:{stamp}", lambda: band_drawing(look.reading, 18, None, "model")
        )
        # the band is a TEXTURE — buckets of colour, filled. `drawChartBand`
        # fills them; only a graph's nodes are outlines.
        said.place(
            band,
            x + PAD,
            y + 6,
            (w - 2 * PAD) / max(1.0, band.wide),
            22.0 / max(1.0, band.tall),
            fills=True,
        )
    else:
        _texture(said, (x + PAD, y + 6, w - 2 * PAD, 22.0), look, which, stamp)
    _window(said, room, look)
    # THE CHART SCRUBS — the status bar has always said so. Dragging in the
    # band moves the cursor across the whole document; dragging in the lanes
    # moves it within the window they show. Two different sums, so two hits,
    # each carrying what the leaf needs to do its own half in one subtraction.
    start, _window_, pitch = window_of(look, w)
    # the session remembers where the lanes are looking, because only the
    # frame knows how wide they are
    said.reported["chart.at"] = str(start)
    said.hit(x + PAD, y + 4, w - 2 * PAD, 28, "scrub", "band", x + PAD, w - 2 * PAD)
    said.hit(x, y + 36, w, h - 40, "scrub", f"lanes:{start}", x + PAD, pitch)
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


def _window(said: Frame, room: Room, look: Look) -> None:
    """The outline on the band saying WHICH STRETCH the lanes below are of.

    An overview and a window into it are two pictures of one text, and
    without this they are two pictures of nothing in particular.
    """
    x, y, w, _h = room
    start, window, _pitch = window_of(look, w)
    length = max(1, len(look.reading.text))
    left = x + PAD + (w - 2 * PAD) * start / length
    right = x + PAD + (w - 2 * PAD) * min(start + window, length) / length
    said.ring(left, y + 5, max(right, left + 2) - left, 24, "warm")


_TEXTURE: dict[str, tuple[list[int], list[int], list[int]]] = {}


def texture(
    look: Look, which: str, stamp: str, buckets: int
) -> tuple[list[int], list[int], list[int]]:
    """The band's texture, bucketed: what stood here, what died here, and where.

    A fact about the whole RUN, so it is worked out once per reading and per
    width rather than summed over six thousand frames because a cursor moved.
    """
    key = f"{stamp}:{which}:{buckets}"
    if key in _TEXTURE:
        return _TEXTURE[key]
    length = max(1, len(look.reading.text))
    high = [0] * buckets
    lost = [0] * buckets
    marks = [0] * buckets
    at = lambda off: min(buckets - 1, int(off * buckets / length))  # noqa: E731
    if which == "pda":
        for s0, e0, depth, _name, ok, _seat in look.watched:
            for b in range(at(int(s0)), at(max(int(e0) - 1, int(s0))) + 1):
                high[b] = max(high[b], int(depth))
                if not ok:
                    lost[b] = 1
        for point, _kind, _said in decisions(look.watched):
            marks[at(int(point))] = 1
    elif look.it.machine is not None:
        said, _names = hypotheses(look.it.machine, look.reading.text)
        for line in said:
            parts = line.split(" ")
            if len(parts) < 3:
                continue
            start, last, done = int(parts[0]), int(parts[1]), parts[2] == "1"
            for b in range(at(start), at(max(last - 1, start)) + 1):
                if done:
                    high[b] += 1
                else:
                    lost[b] += 1
    _TEXTURE.clear()
    _TEXTURE[key] = (high, lost, marks)
    return _TEXTURE[key]


def _texture(said: Frame, room: Room, look: Look, which: str, stamp: str) -> None:
    """`drawClockBand` — the run's own texture, bucketed by the pixel."""
    x, y, w, h = room
    buckets = max(8, int(w))
    high, lost, marks = texture(look, which, stamp, buckets)
    top = max(1, max(high, default=1))
    step = w / buckets
    for b in range(buckets):
        if which == "pda":
            tone = (
                "pdadecided"
                if marks[b]
                else (
                    "field2" if not high[b] else f"pdaband{min(3, high[b] * 4 // top)}"
                )
            )
        elif lost[b] and not high[b]:
            tone = "hypdead"
        elif lost[b] and high[b]:
            tone = f"hypboth{min(3, high[b] * 4 // top)}"
        else:
            tone = f"hypband{min(3, high[b] * 4 // top)}" if high[b] else "field2"
        said.box(x + b * step, y, max(1.0, step), h, tone)


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
    start, window, pitch = window_of(look, w)
    seated = modes(look)
    deep = max((int(f[2]) for f in look.watched), default=0) + 1
    lane = max(2.0, min(16.0, (floor - lanes - 4) / max(1, deep)))
    for s0, e0, depth, name, ok, seat in look.watched:
        if e0 <= start or s0 >= start + window:
            continue
        top = lanes + int(depth) * lane
        if top + lane > floor:
            continue
        x1 = x + PAD + (max(int(s0), start) - start) * pitch
        x2 = max(x + PAD + (min(int(e0), start + window) - start) * pitch, x1 + 1.5)
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
                here = x + PAD + (min(look.at, start + window) - start) * pitch
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
    cursor = x + PAD + (min(max(look.at, start), start + window) - start) * pitch
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
    said: Frame,
    room: Room,
    look: Look,
    caption: str,
    rows: list[Row],
    foot: tuple[str, list[Row]] | None = None,
) -> None:
    """A stack, scrolled — and the panel under it, whichever clock answers.

    ONE row shape and TWO panels, always. `leaf.css` gives the spine a single
    rule: the gutter dimmer in its own column, the thing itself in ink and
    warm on the deepest row, its extent dim beside it. And the spine always
    has a caption saying what it is showing and a second panel under it —
    JUST CLOSED, DECISIONS or CAN COME NEXT — because three clocks that each
    invented their own furniture made one panel read as three.
    """
    x, y, w, h = room
    # The reference has one scrolling element containing the open stack, the
    # second heading and its rows. Reserving room for the foot truncated the
    # deepest open frames and pinned JUST CLOSED in place.
    title, under = foot or ("", [])
    content = list(rows)
    if foot is not None:
        content.append(("", title, "", "ftitle", ""))
        content.extend(under[:4])
    fits = max(1, int((h - 24) // ROW))
    first = min(look.top("spine"), max(0, len(content) - fits))
    visible = content[first : first + fits]
    clipped = first + fits < len(content)
    if clipped and fits > 1:
        visible = visible[:-1]
    # Both panels use one gutter column, as the single `.scroll` does.
    step = max((len(row[0]) for row in [*rows, *under]), default=0) * CELL + (
        8 if rows or under else 0
    )
    top = y + 12
    for gutter, words, extent, tone, goes in visible:
        if tone == "ftitle":
            said.text(x + 14, top + 10, "ftitle", words)
            top += ROW
            continue
        if goes:
            said.hit(x + 8, top, w - 24, ROW, "span", goes)
        if gutter:
            said.text(x + 14, top + 10, "dimmer", gutter)
        room_for = max(0.0, w - 34 - step)
        said.text(x + 14 + step, top + 10, tone, words, room_for)
        if extent:
            said.text(
                x + 14 + step + min(runs(tone, words), room_for) + 8,
                top + 10,
                "dim",
                extent,
                max(0.0, room_for - runs(tone, words) - 8),
            )
        top += ROW
    if clipped:
        said.text(
            x + 14,
            top + 10,
            "dimmer",
            f"{len(content) - first - len(visible)} more — scroll",
        )


def _snip(said: str) -> str:
    """What a closed span HELD, in one line — `''` when it held nothing."""
    if not said:
        return "''"
    one = said.replace("\n", "⏎").replace("\t", "→")
    return one if len(one) <= 28 else one[:27] + "…"


def _model_stack(said: Frame, room: Room, look: Look) -> None:
    """model — the open model spans, as ever."""
    live = look.live()
    rows: list[Row] = [
        (
            f"d{span.depth}",
            as_written(look.it.rules, span.rule),
            f"{span.start:,}..{span.end:,}",
            "warm" if span is live[-1] else "ink",
            f"{span.start}:{span.end}",
        )
        for span in live
    ]
    if not rows:
        rows = [
            ("", "nothing open — before the first span, or complete", "", "fsub", "")
        ]
    # `#closedBody` rows carry `d{depth}` and the span's TEXT — not its
    # extent, which is what the OPEN rows carry — and a row is `.fresh`,
    # warm, when the cursor has only just passed its end.
    closed: list[Row] = [
        (
            f"d{span.depth}",
            as_written(look.it.rules, span.rule),
            _snip(look.reading.text[span.start : span.end]),
            "warm" if look.at - span.end < 3 else "dim",
            f"{span.start}:{span.end}",
        )
        for span in reversed(closed_before(look.reading, look.at))
    ]
    _rows(said, room, look, "open at the cursor", rows, ("JUST CLOSED", closed))


def _pda_stack(said: Frame, room: Room, look: Look) -> None:
    """pda — the kernel's own frames at the cursor, and the choices near it."""
    open_here = [
        (int(s0), int(e0), int(depth), str(name), bool(ok))
        for s0, e0, depth, name, ok, _seat in look.watched
        if s0 <= look.at < e0
    ]
    good = sorted((frame for frame in open_here if frame[4]), key=lambda f: f[2])
    rows: list[Row] = [
        (
            f"d{depth}",
            name,
            f"{s0:,}..{e0:,}",
            "warm" if depth == good[-1][2] else "ink",
            "",
        )
        for s0, e0, depth, name, _ok in good
    ]
    probing = sum(1 for frame in open_here if not frame[4])
    if probing:
        rows.append(
            ("", f"+ {probing} probe frames here — rolled back", "", "fsub", "")
        )
    if not rows:
        rows = [
            ("", "no frame open — a frameless leaf run carries this", "", "fsub", "")
        ]
    # DECISIONS — the last few the walk made, warm where it just made one
    near = [
        (at, words, chose)
        for at, words, chose in decisions(look.watched)
        if at <= look.at
    ][-7:]
    made: list[Row] = [
        (
            f"@{at}",
            f"{words} → {chose}",
            "",
            "warm" if abs(at - look.at) < 2 else "dim",
            "",
        )
        for at, words, chose in near
    ]
    if not made:
        made = [
            (
                "",
                "none — the whole walk is deterministic descent; the automaton shows where decisions could arise",
                "",
                "dim",
                "",
            )
        ]
    _rows(said, room, look, "the PDA's stack at t", rows, ("DECISIONS", made))


def _earley_stack(said: Frame, room: Room, look: Look) -> None:
    """earley — the cursor's own column, as dotted items, and what can follow."""
    x, y, _w, _h = room
    if look.it.machine is None:
        said.text(x + 14, y + 40, "fsub", "this reading has no machine")
        return
    said_column = _column(look, int(look.at))
    rows: list[Row] = []
    expect: list[str] = []
    expecting = False
    for line in said_column.split("\n"):
        if line.startswith("#COLUMN"):
            continue
        if line.startswith("#EXPECT"):
            expecting = True
            continue
        if not line.strip():
            continue
        if expecting:
            expect.append(line)
            continue
        origin, _, rest = line.partition(" ")
        role, _, item = rest.partition(" ")
        rows.append(
            (f"@{origin}", item, role, "green" if role == "complete" else "ink", "")
        )
    total = len(rows)
    if total > 40:
        rows = [*rows[:40], ("", f"+{total - 40} more items", "", "fsub", "")]
    if not rows:
        rows = [
            (
                "",
                "empty — inside a lexical run; the kernel scanned past this column",
                "",
                "fsub",
                "",
            )
        ]
    _rows(
        said,
        room,
        look,
        f"Earley column {int(look.at):,} — {total} items",
        rows,
        ("CAN COME NEXT", _echips(expect)),
    )


def _echips(expect: list[str]) -> list[Row]:
    """.echip — what can come next, warm, as many to a line as fit."""
    if not expect:
        return [("", "nothing — every item is complete", "", "dim", "")]
    lines: list[Row] = []
    said = ""
    for term in expect:
        if len(said) + len(term) > 46:
            lines.append(("", said, "", "warm", ""))
            said = ""
        said += ("  " if said else "") + term
    if said:
        lines.append(("", said, "", "warm", ""))
    return lines


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


def _heads(look: Look, name: str) -> list[Control]:
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
    own: list[Control] = []
    if name == "grammar":
        own = [
            (
                look.it.form,
                "form",
                look.it.form,
                True,
                tuple((form, form) for form in FORMS),
            )
        ]
    elif name == "graph":
        here = look.says("graph.view", "depth3d")
        own = [
            (dict(GRAPHS).get(here, here), "graph.view", here, True, GRAPHS),
            ("◉ focus", "graph.focus", "on", look.says("graph.focus", "off") == "on"),
        ]
    elif name == "chart":
        here = look.says("chart.clock", "model")
        own = [(dict(CLOCKS).get(here, here), "chart.clock", here, True, CLOCKS)]
    # ⧉ pops it out; ⧉+ opens a SECOND one — the same window with its own
    # layer, two views of one facet, each with its own camera and scroll.
    # The glyphs are `popout.js`'s: a twin is the same mark and one more.
    return [*own, ("⧉", "pop", name, False), ("⧉+", "clone", name, False)]


HEADS = _heads
