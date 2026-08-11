"""One frame: the masthead, the grid of regions, and the status bar.

`scene.staged` decides; this presents. There is no list of facets here and no
branch on which one is which — the arrangement tree says what goes where,
`facets.DRAWN` says how each one draws itself, and a new facet changes
nothing in this file.

The chrome is `leaf.css`'s: #mast and #status are one line each with a
hairline between them and the grid, and every region carries its own head.
"""

from __future__ import annotations

from typing import Any

from opsis.frame.facets import DRAWN, HEADS, Look
from opsis.frame.marks import Frame
from opsis.frame.panels import head, walked
from opsis.frame.tones import runs
from opsis.scene import Staged, staged
from praxis.reading import Reading

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
    state: dict[str, str],
    watched: list[list[Any]],
    generation: int,
    typed: dict[str, str] | None = None,
    frontier: int = -1,
    only: str = "",
) -> Frame:
    """The instrument, at this size, at this moment, as one frame.

    :param only: one facet's name — what a window popped off the grid asks for.
    """
    said = Frame(wide, tall)
    it = staged(reading, state)
    look = Look(reading, it, at, state, watched, typed, frontier)
    titles = {facet.name: facet.title for facet in it.facets}
    columns = {facet.name: facet.column or facet.name for facet in it.facets}
    said.box(0, 0, wide, tall, "field")

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
        room = head(said, region, titles, HEADS(look, region.name), columns)
        draw(said, room, look)
    for seam in grid.seams:
        said.hit(seam.x, seam.y, seam.w, seam.h, "seam", str(seam.at))
    _status(said, reading, look, wide, tall)
    return said


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


def _status(said: Frame, reading: Reading, look: Look, wide: int, tall: int) -> None:
    """#status — where the cursor is, the transport, and what the hand can do."""
    y = tall - BAR
    said.line(0, y, wide, y, "hair")
    where = f"char {int(look.at):,} / {len(reading.text):,}"
    said.text(PAD, y + 22, "verdict", where, face="verdict")
    at = PAD + 32 * 6.6
    # #transport — − ‹ ▶ › + ×n
    for glyph, gesture in (
        ("−", "speed~-"),
        ("‹", "step~-1"),
        ("▶", "play"),
        ("›", "step~1"),
        ("+", "speed~+"),
    ):
        said.box(at, y + 8, 20, 16, "field")
        for x1, y1, x2, y2 in (
            (at, y + 8, at + 20, y + 8),
            (at, y + 24, at + 20, y + 24),
            (at, y + 8, at, y + 24),
            (at + 20, y + 8, at + 20, y + 24),
        ):
            said.line(x1, y1, x2, y2, "hair")
        said.text(at + 6, y + 20, "chip", glyph)
        said.hit(at, y + 8, 20, 16, "do", gesture)
        at += 22
    said.text(at + 6, y + 20, "dimmer", f"×{look.says('speed', '1')}", 40, face="chip")
    at += 52
    hint = (
        "select text to co-select · click a rule to choose it · "
        "click a line number to set the cursor · type in the document — "
        "Ctrl+Enter re-reads · Ctrl+S saves, and saving compiles · Esc reverts · "
        "Space plays · the chart scrubs"
    )
    said.text(at, y + 22, "fsub", hint, wide - at - PAD)
