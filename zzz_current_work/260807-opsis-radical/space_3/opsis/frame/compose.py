"""One frame: the masthead, the grid of regions, and the status bar.

`scene.staged` decides; this presents. There is no list of facets here and no
branch on which one is which — the arrangement tree says what goes where,
`facets.DRAWN` says how each one draws itself, and a new facet changes
nothing in this file.

The chrome is `leaf.css`'s: #mast and #status are one line each with a
hairline between them and the grid, and every region carries its own head.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from kairos.artefacts import Artefact
from opsis.frame.facets import DRAWN, GRAPHS, HEADS, Look
from opsis.frame.marks import Frame
from opsis.frame.panels import Region, called, head, walked
from opsis.frame.places import draw as places_draw
from opsis.frame.strata import draw as strata_draw
from opsis.frame.tones import runs
from opsis.rooms import room, subject
from opsis.scene import Staged, staged
from opsis.space import zone_at
from praxis.reading import Reading, as_written
from praxis.routes import Aside
from praxis.strata import strata

from lexic.ir import IrSelf

__all__ = ["compose"]

# what each clock's spine is SHOWING, said where `spineClock` says it
CAPTION = {
    "model": "open at the cursor",
    "pda": "the PDA's stack at t",
    "earley": "the chart's column at t",
}


_FACETS: dict[tuple[str, int], tuple[str, ...]] = {}


def _every(reading: Reading, generation: int) -> tuple[str, ...]:
    """Every facet this reading HAS, present or not — what the dock lists."""
    # Measuring a facet walks every character of both texts. That is a fact
    # about a reading, not about a cursor, scroll position or camera angle;
    # doing it twice per frame consumed most of the interaction budget.
    key = (reading.identity, generation)
    made = _FACETS.get(key)
    if made is None:
        facets = reading.facets()
        made = tuple(
            [facet.name for facet in facets[:1]]
            + ["graph", *(facet.name for facet in facets[1:])]
        )
        _FACETS[key] = made
        if len(_FACETS) > 8:
            del _FACETS[next(iter(_FACETS))]
    return made


# #mast / #status: padding 10px 18px over a 12px line. #pos is `min-width:
# 30ch` and WRAPS inside that, which is why the transport beside it does not
# move when the reading starts playing or the speed gains a character — so
# the status bar is two lines tall and the masthead is one.
BAR = 34.0
STATUS = 46.0
PAD = 18.0
# `min-width: 30ch`, but flex lets it take its natural width and wrap only
# when the row runs out — which lands `char N / M · line L / T ·` on the
# first line and the rest on the second. That is what the box measures.
POS = 44 * 6.6


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
    layers: Mapping[str, Mapping[str, str]] | None = None,
    artefacts: Sequence[Artefact] | None = None,
    praxis: IrSelf | None = None,
) -> Frame:
    """The instrument, at this size, at this moment, as one frame.

    :param only: one facet's name — what a window popped off the grid asks for.
    """
    said = Frame(wide, tall)
    it = staged(reading, state)
    look = Look(reading, it, at, state, watched, typed, frontier, routes, generation)
    titles = {facet.name: facet.title for facet in it.facets}
    titles["graph"] = "THE RELATIONS"
    titles["pin"] = "PINNED · one span, held still"
    # `spineClock` writes the caption into the head's own `<em>`, beside the
    # title — not as a line inside the body, which pushed every row down and
    # gave the panel a second heading it does not have
    titles["spine"] = (
        f"THE SPINE · {CAPTION.get(state.get('chart.clock', 'model'), '')}"
    )
    columns = {facet.name: facet.column or facet.name for facet in it.facets}
    columns["graph"] = "reader"
    said.box(0, 0, wide, tall, "field")

    where = state.get("place", "")
    if where and not only:
        # a room the reading holds — reached through a door in the strata
        places_draw(
            said,
            room(
                where,
                it.machine,
                reading,
                dict(state),
                generation,
                artefacts,
                praxis,
            ),
            wide,
            tall,
            subject(reading, where.removeprefix("ir:"), it.machine, praxis),
            it.shown,
        )
        return said

    if state.get("showing", "") == "strata" and not only:
        strata_draw(
            said,
            strata(reading, list(climbed or [reading])),
            wide,
            tall,
        )
        return said

    if only in DRAWN:
        region = walked(only, 0, 0, wide, tall).regions[0]
        DRAWN[only](said, head(said, region, titles, HEADS(look, only), columns), look)
        return said

    _masthead(
        said,
        reading,
        it,
        wide,
        generation,
        list(_every(reading, generation)),
        look,
        titles,
    )
    grid = walked(str(it.policy["arrange.tree"]), 0, BAR, wide, tall - BAR - STATUS)
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
        said.clip(*inside)
        draw(said, inside, look)
        said.unclip()
    for seam in grid.seams:
        said.hit(
            seam.x, seam.y, seam.w, seam.h, "seam", str(seam.at), seam.base, seam.size
        )
    _zone(said, look, grid, titles)
    _windows(said, look, titles, columns, wide, tall, layers or {})
    _railchip(said, look, wide, tall)
    _status(said, reading, look, wide, tall)
    _banner(said, reading, wide, tall)
    return said


def _zone(said: Frame, look: Look, grid: object, titles: dict[str, str]) -> None:
    """The drop overlay — what would happen if the hand let go here.

    A topology change is a SHAPE, and a shape you cannot see before you
    commit to it is a gamble. This is `#dropzone`: the half or quarter that
    would be taken, named in the words of what it would do.
    """
    dragged, _, rest = look.says("drop", "").partition(" ")
    target, _, at = rest.partition(" ")
    if not dragged or not target or dragged == target or " " not in at:
        return
    across, _, down = at.partition(" ")
    zone = zone_at(float(across), float(down))
    for region in getattr(grid, "regions", []):
        if region.name != target:
            continue
        rx, ry, rw, rh = region.x, region.y, region.w, region.h
        if zone == "left":
            rw /= 2
        elif zone == "right":
            rx, rw = rx + rw / 2, rw / 2
        elif zone == "top":
            rh /= 2
        elif zone == "bottom":
            ry, rh = ry + rh / 2, rh / 2
        else:
            # `zoneRect`'s tab case: INSET a fifth on every side, a smaller
            # box floating inside the surface. A split takes half and says
            # so by covering that half; joining a tab set takes no half at
            # all, and covering the whole region said it did.
            rx, ry = rx + rw * 0.2, ry + rh * 0.2
            rw, rh = rw * 0.6, rh * 0.6
        was = said.lift()
        said.box(rx, ry, rw, rh, "drop_wash")
        said.dashes(rx, ry, rw, rh, "violet")
        # `wire.js`: `zone === 'tab' ? 'tab with ' + FACET_WORD[name]
        # : 'split ' + zone` — and FACET_WORD is the facet's own word, with
        # its "THE " gone. Not the dragged surface's name, not "the document".
        word = (
            f"tab with {worded(titles, target)}" if zone == "tab" else f"split {zone}"
        )
        # in the MIDDLE of the zone it names: at the top it sat on the head
        # of the surface it was covering, and two lines of text in one place
        # is worse than none
        # centred both ways, as `#dropzone` centres its own text
        says = word
        said.text(
            rx + max(8.0, (rw - runs("drawn", says)) / 2),
            ry + rh / 2,
            "violet",
            says,
            rw - 16,
            face="drawn",
        )
        said.drop(was)
        return


GRAPH_PIN_VIEWS = (*GRAPHS, ("text", "text"))


def _pin_meta(look: Look, wid: str, about: str) -> tuple[str, str, bool]:
    """The three things Space 1 puts in a pin's header."""
    start, _, end = about.partition(":")
    if not start.isdigit() or not end.isdigit():
        return "PINNED", about, False
    s0, e0 = int(start), int(end)
    covering = [
        span
        for span in look.reading.spans
        if span.start <= s0 and span.end >= max(e0, s0 + 1)
    ]
    span = min(covering, key=lambda held: held.end - held.start) if covering else None
    title = as_written(look.it.rules, span.rule) if span is not None else "PINNED"
    addr = f"{s0:,}..{e0:,}" + (f" · d{span.depth}" if span is not None else "")
    made = look.says(f"gen.{wid}", str(look.generation))
    return title, addr, made.isdigit() and int(made) != look.generation


def _rail_parents(look: Look, rule: str) -> tuple[str, ...]:
    """Distinct rules which refer to this one, in source order."""
    held: list[str] = []
    for parent, child in look.it.relations:
        parent = as_written(look.it.rules, parent)
        child = as_written(look.it.rules, child)
        if child == rule and parent != rule and parent not in held:
            held.append(parent)
    return tuple(held)


def _windows(
    said: Frame,
    look: Look,
    titles: dict[str, str],
    columns: dict[str, str],
    wide: int,
    tall: int,
    layers: Mapping[str, Mapping[str, str]],
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
        layer = dict(look.state)
        layer.update(layers.get(wid, {}))
        popped = bool(look.says(f"home.{wid}", ""))
        header = called(titles.get(facet, facet))[0]
        addr, stale = "", False
        if facet == "pin":
            header, addr, stale = _pin_meta(look, wid, about)
        elif facet == "rail":
            header, addr = "RAILROAD", about
        elif facet == "graph" and not popped:
            header = "RULE GRAPH"
        elif not popped:
            header += " — a second view"

        # Compact windows have their own CSS chrome in Space 1. A pin's
        # padded header is 27px including the outer edge; the rail's 15px
        # parent select makes that 29px. Generic facet windows retain the
        # port's 20px head.
        chrome = 27 if facet == "pin" else (29 if facet == "rail" else 20)
        head_baseline = y + (18 if facet in ("pin", "rail") else 14)

        said.open_layer(wid)
        # the shadow is cast by the window's own body and nothing after it
        said.shadow("cast")
        said.box(x, y, w, h, "field2")
        said.shadow()
        said.ring(x, y, w, h, "dimmer" if stale else "warm")
        # the head IS the handle: dragging it moves the window, and the
        # corner resizes it — the same two gestures every window has ever had
        said.hit(x, y, w, h, "win", wid)
        said.hit(x, y, w - 22, chrome, "winhead", wid)
        said.hit(x + w - 14, y + h - 14, 14, 14, "wincorner", wid)
        said.line(x + w - 14, y + h, x + w, y + h - 14, "warm")
        control_left = x + w - 30
        if facet == "graph" and not popped:
            control_left -= 82
            with said.within(wid):
                said.pick(
                    "graph.view",
                    control_left,
                    y + 3,
                    76,
                    15,
                    layer.get("graph.view", "depth3d"),
                    GRAPH_PIN_VIEWS,
                )
        elif facet == "rail":
            cursor = x + 11 + runs("winhead", header) + 8 + runs("pinaddr", addr) + 8
            history = look.says(f"rail.hist.{wid}", "").split()
            if history:
                said.ring(cursor, y + 7, 22, 14, "hair")
                said.text(cursor + 6, head_baseline, "dim", "↩", face="chip")
                said.hit(cursor, y + 7, 22, 14, "railback", wid)
                cursor += 26
            parents = _rail_parents(look, about)
            if parents:
                control_left = min(cursor, x + w - 90)
                with said.within(wid):
                    said.pick(
                        f"rail.parent.{wid}",
                        control_left,
                        y + 7,
                        58,
                        15,
                        "",
                        (("", f"▲ {len(parents)}"), *((p, p) for p in parents)),
                    )
        title_tone = "dim" if stale else "warm"
        said.text(
            x + 11,
            head_baseline,
            title_tone,
            header,
            control_left - x - 17,
            face="winhead",
        )
        if addr:
            at = x + 11 + runs("winhead", header) + 8
            said.text(
                at,
                head_baseline,
                "dim",
                addr,
                max(1, control_left - at - 4),
                face="pinaddr" if facet in ("pin", "rail") else "chip",
            )
        if stale:
            said.text(
                control_left - 6,
                head_baseline,
                "red",
                "stale",
                anchor="r",
                face="chip",
            )
        said.text(
            x + w - 9,
            head_baseline,
            "dim",
            "×",
            anchor="r",
            face="winhead" if facet in ("pin", "rail") else "chip",
        )
        said.hit(x + w - 22, y, 22, chrome, "shut", wid)
        said.line(x, y + chrome, x + w, y + chrome, "hair")
        # nothing reaches THROUGH a window: its own rectangle takes the
        # pointer before anything it happens to be floating over
        # THE WHOLE WINDOW, head included. The leaf lays a pane of glass over
        # this rectangle so the window takes the pointer: the text planes are
        # real elements and a canvas drawn above one still lets every click
        # through to it, which is a window you can see and cannot touch.
        said.clip(x, y + chrome, w, h - chrome)
        _inside(
            said,
            look,
            wid,
            facet,
            about,
            (x, y + chrome, w, h - chrome),
            titles,
            columns,
            layer,
            popped,
        )
        said.unclip()
        said.close_layer()
    said.drop(was)


def _inside(
    said: Frame,
    look: Look,
    wid: str,
    facet: str,
    about: str,
    room: tuple[float, float, float, float],
    titles: dict[str, str],
    columns: dict[str, str],
    layer: dict[str, str],
    popped: bool,
) -> None:
    """What one window SHOWS — the facet it was torn from, in its own room."""
    draw = DRAWN.get(facet)
    if draw is None:
        said.text(room[0] + 12, room[1] + 22, "dim", f"nothing draws a {facet}")
        return
    # a window carries what it is ABOUT in its own layer, so it keeps saying
    # that after the cursor has gone elsewhere
    layer["window.kind"] = "pop" if popped else "clone"
    if facet == "pin":
        layer["pin.span"] = about
        layer["pin.gen"] = look.says(f"gen.{wid}", str(look.generation))
    elif facet == "rail":
        layer["rail.rule"] = about
        layer["rail.window"] = wid
    window = Look(
        look.reading,
        look.it,
        look.at,
        layer,
        look.watched,
        look.typed,
        look.frontier,
        look.routes,
        look.generation,
        wid,
    )
    with said.within(wid):
        inside = room
        if popped:
            region = Region(facet, *room, (facet,), 0)
            controls = [
                control for control in HEADS(window, facet) if control[1] != "pop"
            ]
            inside = head(said, region, titles, controls, columns)
            said.clip(*inside)
        draw(said, inside, window)
        if popped:
            said.unclip()


def _railchip(said: Frame, look: Look, wide: int, tall: int) -> None:
    """#railchip — ONE chip, floating, raised where the rule was chosen.

    `rails.js`: fixed at the pointer, six across and thirty-four up, clamped
    to the window. It is raised from the reader, the rails, the automaton and
    the graph alike, because a rule you have just chosen is a rule you might
    want the track of, and which picture you chose it in has nothing to do
    with that. Any other click, or a scroll, lets it go.
    """
    rule, _, at = look.says("railchip", "").partition(" ")
    across, _, down = at.partition(" ")
    if not rule or not across or not down:
        return
    room = runs("railchip", "▤ rail") + 20
    x = max(8.0, min(float(across) + 6, wide - 86.0))
    y = max(8.0, min(float(down) - 34, tall - 42.0))
    said.lift()
    said.box(x, y, room, 22, "field2")
    said.ring(x, y, room, 22, "violet")
    said.text(x + 10, y + 15, "violet", "▤ rail", face="railchip")
    said.hit(x, y, room, 22, "rail", rule)
    said.drop()


def _banner(said: Frame, reading: Reading, wide: int, tall: int) -> None:
    """#banner — a refusal, in the engine's own words, verbatim.

    A reading that did not read says so in the words of the thing that
    refused it. `NOT FAITHFUL` on its own is a flag, and a flag is not a
    reason: the engine already said what went wrong, and passing that on is
    the whole of what is owed here.
    """
    if reading.ambiguous:
        # One row per candidate, never a first-match verdict. Accepted rows
        # are doors; refused rows retain the engine's words verbatim.
        height = 38 + len(reading.probes) * 22
        x = max(24.0, wide * 0.16)
        y = tall - STATUS - height - 18
        room = wide - x - 24
        said.lift()
        said.box(x, y, room, height, "field2")
        said.ring(x, y, room, height, "warm")
        offered = " and ".join(name.upper() for name in reading.offers)
        said.text(
            x + 14,
            y + 22,
            "warm",
            f"{offered} both accept this reader — choose one relation",
            room - 28,
            face="verdict",
        )
        top = y + 31
        for answer in reading.probes:
            if answer.accepted:
                words = f"{answer.flavour.upper()} — accepts · click to read"
                said.box(x + 10, top, room - 20, 19, "open")
                said.ring(x + 10, top, room - 20, 19, "green")
                said.text(x + 18, top + 14, "green", words, face="verdict")
                said.hit(x + 10, top, room - 20, 19, "cast", answer.flavour)
            else:
                words = f"{answer.flavour.upper()} — {answer.words}"
                said.text(x + 18, top + 14, "red", words, room - 36, face="verdict")
            top += 22
        return
    if not reading.words:
        return
    # a refusal is read OVER the text it is about
    said.lift()
    words = reading.words if len(reading.words) < 140 else reading.words[:139] + "…"
    room = runs("verdict", words) + 36
    x = max(24.0, wide * 0.24)
    y = tall - STATUS - 58
    said.box(x, y, min(room, wide - x - 24), 40, "field2")
    said.ring(x, y, min(room, wide - x - 24), 40, "red")
    said.text(
        x + 16, y + 25, "red", words, min(room, wide - x - 24) - 32, face="verdict"
    )


def worded(titles: dict[str, str], facet: str) -> str:
    """What a facet is CALLED in the dock — its own title's first word.

    `FACET_WORD` — "THE DERIVATION · text is the time axis" is `derivation`.
    A dock spelling the internal names (grammar, graph, chart) named things
    the instrument never calls them anywhere else on the screen.
    """
    return called(titles.get(facet, facet))[0].removeprefix("THE ").strip().lower()


def _docked(titles: dict[str, str], shown: list[str]) -> float:
    """How wide the dock is — where whatever follows it starts."""
    return sum(runs("node", worded(titles, f)) + 31 for f in shown)


def _masthead(
    said: Frame,
    reading: Reading,
    it: Staged,
    wide: int,
    generation: int,
    shown: list[str],
    look: Look,
    titles: dict[str, str],
) -> None:
    """#mast — the name, what is loaded, the ladder, the dock, the verdict."""
    said.line(0, BAR, wide, BAR, "hair")
    said.text(PAD, 22, "title", "FACETS")
    at = PAD + runs("title", "FACETS") + 18
    # #sub — what READ what, and how long it took. Not the pairing again: the
    # ladder chip beside it already says that, and saying it twice cost the
    # room the reading's own numbers needed.
    # `boot.js`: what READ what, how long it took, and what came of it —
    # the spans and the depth are the reading's own measure of itself
    deep = max((span.depth for span in reading.spans), default=0)
    sub = (
        f"{reading.reader_name} read {len(reading.text):,} chars "
        f"in {reading.seconds:.2f}s · {len(reading.spans):,} spans · depth {deep}"
    )
    # #sub takes its natural width — it is a flex item, not a column, and
    # clipping it at thirty characters cut the reading's own measure of
    # itself off at "15,769 chars i…"
    said.text(at, 22, "fsub", sub)
    at += runs("fsub", sub) + 16
    at = _ladder(said, it, at)
    _map(said, at)
    # #ladder is `flex: 1` — it takes what is left, so the dock and the
    # verdict sit at the RIGHT edge. Packing them beside the chip put five
    # chips in the middle of a bar that is mostly empty on the right.
    # `boot.js` writes the verdict as a CLAIM and a FINDING: the claim in the
    # inherited ink, `— holds` in green or `— FAILS` in red. One tone for the
    # whole line said the instrument was pleased with itself.
    claim = "model.to_text() == document "
    found = "— holds" if reading.faithful else "— FAILS"
    said.text(wide - PAD, 22, "green" if reading.faithful else "red", found, anchor="r")
    said.text(
        wide - PAD - runs("verdict", found),
        22,
        "ink",
        claim,
        face="verdict",
        anchor="r",
    )
    right = wide - PAD - runs("verdict", claim + found) - 34
    windows = [w for w in look.says("windows", "").split(" ") if w]
    if windows:
        right -= runs("verdict", f"pinned {len(windows)}") + 16
        said.text(right + 8, 22, "warm", f"pinned {len(windows)}", face="verdict")
    _dock(said, it, titles, shown, right - _docked(titles, shown))


def _ladder(said: Frame, it: Staged, at: float) -> float:
    """The one chip in the masthead: WHERE YOU ARE, and the way back out.

    The strip is dead. A row of rungs with separators was a map of the climb
    drawn in the one place with no room for a map — and the climb already has
    its own picture. This chip says where you are standing and opens it.
    """
    said_chain = str(it.policy.get("chain", ""))
    here = next((r for r in said_chain.split(" | ") if r.strip().startswith("0 ")), "")
    _level, _, rest = here.partition(" ")
    pair, _, _seen = rest.partition(" · ")
    word = f"{pair or '…'}  ∴"
    # Keep the pairing verbatim and give it its natural room. The old 26ch
    # ceiling clipped the final reader name while leaving the text itself in
    # place, so the top button looked cut off rather than abbreviated.
    wide = runs("chip", word) + 16
    said.ring(at, 8, wide, 26 - 8, "warm")
    said.text(at + 8, 21, "warm", word, wide - 14, face="chip")
    said.hit(at, 8, wide, 18, "strata", "on")
    return at + wide + 14


def _map(said: Frame, at: float) -> float:
    """The fifth travel move — distinct from the ladder it once displaced."""
    word = "⌗ map"
    wide = runs("chip", word) + 16
    said.ring(at, 8, wide, 18, "hair")
    said.text(at + 8, 21, "cool", word, wide - 14, face="chip")
    said.hit(at, 8, wide, 18, "ingress", "map")
    return at + wide + 14


def _dock(
    said: Frame, it: Staged, titles: dict[str, str], shown: list[str], at: float
) -> None:
    """#dock — every facet as a node: lit is present, dim is minimized.

    Clicking one toggles it. A minimized facet is not gone: it keeps all its
    state in policy, and the tree simply closes over the space it had.
    """
    for facet in shown:
        here = any(f.name == facet for f in it.facets)
        word = worded(titles, facet)
        wide = runs("node", word) + 25
        said.ring(at, 8, wide, 26 - 8, "hair")
        # .fnode-chip i — a ROUND dot, 6px, cool when the facet is present
        # `#dock .fnode-chip i`: 6px, border-radius 50%, cool — or dimmer
        # when the facet is minimized
        said.dot(at + 9, 17, 3, "cool" if here else "dimmer")
        said.text(at + 17, 21, "node" if here else "dimmer", word, face="node")
        said.hit(at, 8, wide, 18, "facet", facet)
        at += wide + 6


def _pincount(said: Frame, look: Look, at: float) -> None:
    """#pincount — how many windows are open, where the masthead says it.

    The strata is reached through the ladder's own chip, and the instrument's
    own state is a door IN the strata, so neither is a button up here. Two
    chips for one door is how a masthead fills with things nobody presses.
    """
    windows = [w for w in look.says("windows", "").split(" ") if w]
    if windows:
        said.text(at, 21, "warm", f"pinned {len(windows)}", face="verdict")


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
    if not words:
        live = look.live()
        words = (
            "at the cursor · "
            + _span_words(reading, f"{live[-1].start}:{live[-1].end}")
            if live
            else "at the cursor · no span is open"
        )
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


def spoken(said: str) -> str:
    """×2, or ×1/4 — `speedWord`. A speed under one is a FRACTION."""
    rate = float(said)
    return f"×{rate:g}" if rate >= 1 else f"×1/{round(1 / rate)}"


def _wrap(said: str, room: float, face: str) -> list[str]:
    """Those words, broken where they fit — what a flex box does for free."""
    out: list[str] = []
    line = ""
    for word in said.split(" "):
        if line and runs(face, f"{line} {word}") > room:
            out.append(line)
            line = word
        else:
            line = f"{line} {word}" if line else word
    if line:
        out.append(line)
    return out


def _status(said: Frame, reading: Reading, look: Look, wide: int, tall: int) -> None:
    """#status — where the cursor is, the transport, and what the hand is on."""
    y = tall - STATUS
    said.line(0, y, wide, y, "hair")
    playing = look.says("playing", "0") == "1"
    at = int(min(look.at, len(reading.text)))
    state = (
        "playing" if playing else ("complete" if at >= len(reading.text) else "paused")
    )
    speed = look.says("speed", "1")
    where = (
        f"char {at:,} / {len(reading.text):,} · "
        f"line {reading.text.count(chr(10), 0, at) + 1:,} / "
        f"{reading.text.count(chr(10)) + 1:,} · {state} · "
        + (f"speed {spoken(speed)} · " if speed != "1" else "")
        + f"gen {look.generation}"
    )
    for i, line in enumerate(_wrap(where, POS, "verdict")[:2]):
        # #pos { color: var(--ink) } — it is the one thing in this bar that
        # is not commentary
        said.text(PAD, y + 18 + i * 15, "ink", line, POS, face="verdict")
    # a FIXED place, because #pos is a box that wraps rather than one that grows
    at_x = PAD + POS + 18
    for glyph, gesture in (
        ("−", "speed~-"),
        ("‹", "step~-1"),
        ("⏸" if playing else "▶", "play"),
        ("›", "step~1"),
        ("+", "speed~+"),
    ):
        said.box(at_x, y + 12, 20, 16, "field")
        said.ring(at_x, y + 12, 20, 16, "hair")
        said.text(at_x + 6, y + 24, "chip", glyph)
        said.hit(at_x, y + 12, 20, 16, "do", gesture)
        at_x += 22
    # #tb-speed: min-width 4ch, so the hint after it does not shuffle either
    said.text(at_x + 6, y + 24, "dimmer", spoken(speed), 4 * 6.0, face="chip")
    at_x += 6 + 4 * 6.0 + 18
    # #readout takes the right edge; the hint fills what is left, over two
    # lines, because what the hand is ON matters more than a standing list of
    # what it COULD do
    words = _readout(reading, look)
    room = runs("verdict", words) if words else 0.0
    if words:
        said.text(wide - PAD, y + 18, "warm", words, face="verdict", anchor="r")
    left = max(120.0, wide - at_x - PAD - room - 24)
    for i, line in enumerate(_wrap(HINT, left, "fsub")[:2]):
        said.text(at_x, y + 18 + i * 15, "fsub", line, left)
