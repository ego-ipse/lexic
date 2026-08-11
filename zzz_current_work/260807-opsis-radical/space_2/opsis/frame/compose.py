"""One frame: the masthead, the grid of regions, and the status bar.

`scene.staged` decides; this presents. There is no list of facets here and no
branch on which one is which — the arrangement tree says what goes where,
`facets.DRAWN` says how each one draws itself, and a new facet changes
nothing in this file.

The chrome is `leaf.css`'s: #mast and #status are one line each with a
hairline between them and the grid, and every region carries its own head.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from opsis.frame.facets import DRAWN, HEADS, Look
from opsis.frame.marks import Frame
from opsis.frame.panels import head, walked
from opsis.frame.places import draw as places_draw
from opsis.frame.strata import draw as strata_draw
from opsis.frame.tones import runs
from opsis.rooms import room, subject
from opsis.scene import Staged, staged
from praxis.reading import Reading
from praxis.routes import Aside
from praxis.strata import strata

__all__ = ["compose"]


def _every(reading: Reading) -> list[str]:
    """Every facet this reading HAS, present or not — what the dock lists."""
    return [facet.name for facet in reading.facets()[:1]] + [
        "graph",
        *(facet.name for facet in reading.facets()[1:]),
    ]


# #mast / #status: padding 10px 18px over a 12px line
BAR = 34.0
PAD = 18.0


def compose(
    reading: Reading,
    wide: int,
    tall: int,
    at: float,
    state: Mapping[str, str],
    watched: list[list[Any]],
    generation: int,
    climbed: list[Reading] | None = None,
    typed: dict[str, str] | None = None,
    frontier: int = -1,
    routes: Aside | None = None,
    only: str = "",
) -> Frame:
    """The instrument, at this size, at this moment, as one frame.

    :param only: one facet's name — what a window popped off the grid asks for.
    """
    said = Frame(wide, tall)
    it = staged(reading, state)
    look = Look(reading, it, at, state, watched, typed, frontier, routes, generation)
    titles = {facet.name: facet.title for facet in it.facets}
    titles["pin"] = "PINNED · one span, held still"
    columns = {facet.name: facet.column or facet.name for facet in it.facets}
    said.box(0, 0, wide, tall, "field")

    where = state.get("place", "")
    if where and not only:
        # a room the reading holds — reached through a door in the strata
        places_draw(
            said,
            room(where, it.machine, reading, dict(state)),
            wide,
            tall,
            subject(reading, where.removeprefix("ir:"), it.machine),
            it.shown,
        )
        return said

    if state.get("showing", "") == "strata" and not only:
        strata_draw(said, strata(reading, list(climbed or [reading])), wide, tall)
        return said

    if only in DRAWN:
        region = walked(only, 0, 0, wide, tall).regions[0]
        DRAWN[only](said, head(said, region, titles, HEADS(look, only), columns), look)
        return said

    _masthead(said, reading, it, wide, generation, _every(reading))
    grid = walked(str(it.policy["arrange.tree"]), 0, BAR, wide, tall - BAR * 2)
    for region in grid.regions:
        draw = DRAWN.get(region.name)
        if draw is None:
            continue
        # what a head hands back is the INSIDE of the region, which is not
        # the same word as the room a reading holds
        inside = head(
            said,
            region,
            titles,
            HEADS(look, region.name),
            columns,
            look.routes if region.name == "chart" else None,
        )
        draw(said, inside, look)
    for seam in grid.seams:
        said.hit(seam.x, seam.y, seam.w, seam.h, "seam", str(seam.at))
    _windows(said, look, titles, columns, wide, tall)
    _status(said, reading, look, wide, tall)
    _banner(said, reading, wide, tall)
    return said


def _windows(
    said: Frame,
    look: Look,
    titles: dict[str, str],
    columns: dict[str, str],
    wide: int,
    tall: int,
) -> None:
    """The windows, over the grid — the ruled exception to a tiling.

    Simultaneity is the one thing an arrangement cannot express: two things
    at once, one of them held still. They are drawn last so they are on top,
    and they are drawn HERE, over the same picture, because a browser window
    is a different document and cannot overlap what it was torn from.
    """
    # a window is READ OVER the picture it floats on, and the text planes are
    # real elements: anything a window draws on the under canvas is behind
    # the very text it was torn off to sit beside
    was = said.lift()
    for wid in [w for w in look.says("windows", "").split(" ") if w]:
        parts = look.says(f"win.{wid}", "").split(" ", 5)
        if len(parts) < 5:
            continue
        facet, x, y, w, h = parts[0], *(float(n) for n in parts[1:5])
        about = parts[5] if len(parts) > 5 else ""
        x, y = min(x, wide - 80), min(y, tall - 40)
        w, h = min(w, wide - x - 8), min(h, tall - y - 8)
        said.box(x, y, w, h, "field2")
        for x1, y1, x2, y2 in (
            (x, y, x + w, y),
            (x, y + h, x + w, y + h),
            (x, y, x, y + h),
            (x + w, y, x + w, y + h),
        ):
            said.line(x1, y1, x2, y2, "warm")
        # the head IS the handle: dragging it moves the window, and the
        # corner resizes it — the same two gestures every window has ever had
        said.hit(x, y, w - 22, 20, "winhead", wid)
        said.hit(x + w - 14, y + h - 14, 14, 14, "wincorner", wid)
        said.line(x + w - 14, y + h, x + w, y + h - 14, "warm")
        said.text(
            x + 10, y + 14, "ftitle", f"{facet}{f' · {about}' if about else ''}", w - 40
        )
        said.text(x + w - 8, y + 14, "dim", "×", anchor="r", face="chip")
        said.hit(x + w - 22, y, 22, 20, "shut", wid)
        said.line(x, y + 20, x + w, y + 20, "hair")
        # nothing reaches THROUGH a window: its own rectangle takes the
        # pointer before anything it happens to be floating over
        said.hit(x, y + 20, w, h - 20, "win", wid)
        _inside(said, look, wid, facet, about, (x, y + 20, w, h - 20))
    said.drop(was)


def _inside(
    said: Frame,
    look: Look,
    wid: str,
    facet: str,
    about: str,
    room: tuple[float, float, float, float],
) -> None:
    """What one window SHOWS — the facet it was torn from, in its own room."""
    draw = DRAWN.get(facet)
    if draw is None:
        said.text(room[0] + 12, room[1] + 22, "dim", f"nothing draws a {facet}")
        return
    # a window carries what it is ABOUT in its own layer, so it keeps saying
    # that after the cursor has gone elsewhere
    layer = dict(look.state)
    if facet == "pin":
        layer["pin.span"] = about
        layer["pin.gen"] = look.says(f"gen.{wid}", str(look.generation))
    elif facet == "rail":
        layer["rail.rule"] = about
    draw(
        said,
        room,
        Look(
            look.reading,
            look.it,
            look.at,
            layer,
            look.watched,
            look.typed,
            look.frontier,
            look.routes,
            look.generation,
        ),
    )


def _banner(said: Frame, reading: Reading, wide: int, tall: int) -> None:
    """#banner — a refusal, in the engine's own words, verbatim.

    A reading that did not read says so in the words of the thing that
    refused it. `NOT FAITHFUL` on its own is a flag, and a flag is not a
    reason: the engine already said what went wrong, and passing that on is
    the whole of what is owed here.
    """
    if not reading.words:
        return
    # a refusal is read OVER the text it is about
    said.lift()
    words = reading.words if len(reading.words) < 140 else reading.words[:139] + "…"
    room = runs("verdict", words) + 36
    x = max(24.0, wide * 0.24)
    y = tall - BAR - 58
    said.box(x, y, min(room, wide - x - 24), 40, "field2")
    for x1, y1, x2, y2 in (
        (x, y, x + min(room, wide - x - 24), y),
        (x, y + 40, x + min(room, wide - x - 24), y + 40),
        (x, y, x, y + 40),
        (x + min(room, wide - x - 24), y, x + min(room, wide - x - 24), y + 40),
    ):
        said.line(x1, y1, x2, y2, "red")
    said.text(
        x + 16, y + 25, "red", words, min(room, wide - x - 24) - 32, face="verdict"
    )


def _masthead(
    said: Frame,
    reading: Reading,
    it: Staged,
    wide: int,
    generation: int,
    shown: list[str],
) -> None:
    """#mast — the name, what is loaded, the ladder, the dock, the verdict."""
    said.line(0, BAR, wide, BAR, "hair")
    said.text(PAD, 22, "title", "FACETS")
    at = PAD + runs("title", "FACETS") + 18
    sub = (
        f"{reading.document.name} ⊳ {reading.reader_name} · "
        f"{len(reading.text):,} chars in {reading.seconds:.2f}s · gen {generation}"
    )
    said.text(at, 22, "fsub", sub, 30 * 6.4)
    at += min(runs("fsub", sub), 30 * 6.4) + 16
    at = _ladder(said, it, at)
    _dock(said, it, shown, at)
    holds = (
        "model.to_text() == document — holds" if reading.faithful else "NOT FAITHFUL"
    )
    said.text(wide - PAD, 22, "green" if reading.faithful else "red", holds, anchor="r")


def _ladder(said: Frame, it: Staged, at: float) -> float:
    """#ladder — the lineage strip: every reader is also a text.

    Each rung is a reading this one implies. The one you are in is warm; a
    rung not yet visited is dim, and entering it is what builds it.
    """
    said_chain = str(it.policy.get("chain", ""))
    for rung in [r for r in said_chain.split(" | ") if r.strip()]:
        level, _, rest = rung.partition(" ")
        pair, _, seen = rest.partition(" · ")
        here = level == "0"
        wide = min(26 * 6.0, runs("chip", pair)) + 16
        for x1, y1, x2, y2 in (
            (at, 8, at + wide, 8),
            (at, 26, at + wide, 26),
            (at, 8, at, 26),
            (at + wide, 8, at + wide, 26),
        ):
            said.line(x1, y1, x2, y2, "warm" if here else "hair")
        said.text(at + 8, 21, "warm" if here else "chip", pair, wide - 14, face="chip")
        if not here:
            said.hit(at, 8, wide, 18, "rung", level)
        at += wide + 5
        said.text(at, 21, "dimmer", "›")
        at += 12
    return at + 6


def _dock(said: Frame, it: Staged, shown: list[str], at: float) -> None:
    """#dock — every facet as a node: lit is present, dim is minimized.

    Clicking one toggles it. A minimized facet is not gone: it keeps all its
    state in policy, and the tree simply closes over the space it had.
    """
    for facet in shown:
        here = any(f.name == facet for f in it.facets)
        word = facet
        wide = runs("chip", word) + 22
        for x1, y1, x2, y2 in (
            (at, 8, at + wide, 8),
            (at, 26, at + wide, 26),
            (at, 8, at, 26),
            (at + wide, 8, at + wide, 26),
        ):
            said.line(x1, y1, x2, y2, "hair")
        # the chip's own dot: cool when the facet is present, dimmer when not
        said.box(at + 6, 15, 6, 6, "cool" if here else "dimmer")
        said.text(at + 16, 21, "chip" if here else "dimmer", word, face="chip")
        said.hit(at, 8, wide, 18, "facet", facet)
        at += wide + 6
    # the way OUT of the reading and into the climb it sits in
    wide = runs("chip", "⌗ strata") + 22
    for x1, y1, x2, y2 in (
        (at + 8, 8, at + 8 + wide, 8),
        (at + 8, 26, at + 8 + wide, 26),
        (at + 8, 8, at + 8, 26),
        (at + 8 + wide, 8, at + 8 + wide, 26),
    ):
        said.line(x1, y1, x2, y2, "hair")
    said.text(at + 18, 21, "violet", "⌗ strata", face="chip")
    said.hit(at + 8, 8, wide, 18, "strata", "on")
    at += wide + 14
    # the ring: this instrument, as a reading of its own state
    wide = runs("chip", "◌ ring") + 22
    for x1, y1, x2, y2 in (
        (at, 8, at + wide, 8),
        (at, 26, at + wide, 26),
        (at, 8, at, 26),
        (at + wide, 8, at + wide, 26),
    ):
        said.line(x1, y1, x2, y2, "hair")
    said.text(at + 10, 21, "violet", "◌ ring", face="chip")
    said.hit(at, 8, wide, 18, "ring", "on")


HINT = (
    "select text → a pin chip appears · g graph · [ ] speed · type in the "
    "document — Ctrl+Enter re-reads · Ctrl+S saves, and saving compiles · Esc "
    "reverts · select text to co-select · click a line number to set the "
    "cursor · Space plays · the chart scrubs"
)


def _readout(reading: Reading, look: Look) -> str:
    """#readout — what the hand is on, in the words of the thing it is on.

    THE HAND WINS. A selection persists; a hover is where the pointer is right
    now, and reading out the selection while the pointer is elsewhere is the
    instrument describing a different thing than the one it is highlighting.
    """
    kind, _, goes = look.says("hover", "").partition(" ")
    words = ""
    if kind == "span" and ":" in goes:
        words = "under the hand · " + _span_words(reading, goes)
    elif look.says("sel", ""):
        words = "selected · " + _span_words(reading, look.says("sel", ""))
    elif look.chosen:
        words = f"rule {look.chosen} — its spans outlined violet"
    if kind == "frame":
        s0, e0, depth, name = goes.split(":", 3)
        clock = look.says("chart.clock", "model")
        said = (
            f"frame {name} · {int(s0):,}..{int(e0):,} · stack depth {depth}"
            if clock == "pda"
            else f"hypothesis {name} · {int(s0):,}..{int(e0):,}"
        )
        words = said + (f" · {words}" if words else "")
    return words


def _span_words(reading: Reading, goes: str) -> str:
    """One span, said: its rule, its field, its extent, its depth.

    A span that covers nothing is not a defect and not a gap — the rule
    derived ε, so the model holds an object the text does not show. Saying so
    is the difference between structure and noise.
    """
    s0, _, e0 = goes.partition(":")
    start, end = int(s0), int(e0 or s0)
    for span in reading.spans:
        if span.start == start and span.end == end:
            extent = (
                f"{start:,}..{end:,}"
                if end > start
                else f"at {start:,} — matched NO text (the rule derives ε)"
            )
            field = f" · field {span.field}" if span.field else ""
            return f"{span.rule}{field} · {extent} · d{span.depth}"
    return f"{start:,}..{end:,}"


def _status(said: Frame, reading: Reading, look: Look, wide: int, tall: int) -> None:
    """#status — where the cursor is, the transport, and what the hand is on."""
    y = tall - BAR
    said.line(0, y, wide, y, "hair")
    playing = look.says("playing", "0") == "1"
    at = int(min(look.at, len(reading.text)))
    state = (
        "playing" if playing else ("complete" if at >= len(reading.text) else "paused")
    )
    speed = look.says("speed", "1")
    where = (
        f"char {at:,} / {len(reading.text):,}"
        f" · line {reading.text.count(chr(10), 0, at) + 1:,}"
        f" / {reading.text.count(chr(10)) + 1:,} · {state}"
        + (f" · speed {speed}" if speed != "1" else "")
        + f" · gen {look.generation}"
    )
    said.text(PAD, y + 22, "verdict", where, face="verdict")
    at_x = PAD + max(32 * 6.6, runs("verdict", where) + 18)
    # #transport — − ‹ ▶ › + ×n
    for glyph, gesture in (
        ("−", "speed~-"),
        ("‹", "step~-1"),
        ("⏸" if playing else "▶", "play"),
        ("›", "step~1"),
        ("+", "speed~+"),
    ):
        said.box(at_x, y + 8, 20, 16, "field")
        for x1, y1, x2, y2 in (
            (at_x, y + 8, at_x + 20, y + 8),
            (at_x, y + 24, at_x + 20, y + 24),
            (at_x, y + 8, at_x, y + 24),
            (at_x + 20, y + 8, at_x + 20, y + 24),
        ):
            said.line(x1, y1, x2, y2, "hair")
        said.text(at_x + 6, y + 20, "chip", glyph)
        said.hit(at_x, y + 8, 20, 16, "do", gesture)
        at_x += 22
    said.text(at_x + 6, y + 20, "dimmer", f"×{speed}", 40, face="chip")
    at_x += 52
    # the readout takes the right edge — margin-left: auto — and the hint
    # fills only what is left over, because what the hand is ON matters more
    # than a standing list of what it COULD do
    words = _readout(reading, look)
    room = runs("verdict", words) if words else 0.0
    if words:
        said.text(wide - PAD, y + 22, "warm", words, face="verdict", anchor="r")
    said.text(at_x, y + 22, "fsub", HINT, max(0.0, wide - at_x - PAD - room - 24))
