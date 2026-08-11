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
from opsis.scene import staged
from praxis.reading import Reading

__all__ = ["compose"]

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
    said.box(0, 0, wide, tall, "field")

    if only in DRAWN:
        region = walked(only, 0, 0, wide, tall).regions[0]
        DRAWN[only](said, head(said, region, titles, HEADS(look, only)), look)
        return said

    _masthead(said, reading, it, wide, generation)
    grid = walked(str(it.policy["arrange.tree"]), 0, BAR, wide, tall - BAR * 2)
    for region in grid.regions:
        draw = DRAWN.get(region.name)
        if draw is None:
            continue
        draw(said, head(said, region, titles, HEADS(look, region.name)), look)
    for seam in grid.seams:
        said.hit(seam.x, seam.y, seam.w, seam.h, "seam", str(seam.at))
    _status(said, reading, look, wide, tall)
    return said


def _masthead(
    said: Frame, reading: Reading, it: object, wide: int, generation: int
) -> None:
    """#mast — the name, what is loaded, the ladder, and the parity verdict."""
    said.line(0, BAR, wide, BAR, "hair")
    said.text(PAD, 22, "title", "FACETS")
    at = PAD + runs("title", "FACETS") + 18
    said.text(
        at,
        22,
        "fsub",
        f"{reading.document.name} ⊳ {reading.reader_name} · "
        f"{len(reading.text):,} chars in {reading.seconds:.2f}s · gen {generation}",
        wide - at - 320,
    )
    holds = (
        "model.to_text() == document — holds" if reading.faithful else "NOT FAITHFUL"
    )
    said.text(
        wide - PAD - runs("verdict", holds),
        22,
        "green" if reading.faithful else "red",
        holds,
    )


def _status(said: Frame, reading: Reading, look: Look, wide: int, tall: int) -> None:
    """#status — where the cursor is, the transport, and what the hand can do."""
    y = tall - BAR
    said.line(0, y, wide, y, "hair")
    where = f"char {int(look.at):,} / {len(reading.text):,}"
    said.text(PAD, y + 22, "verdict", where)
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
    said.text(at + 6, y + 20, "dimmer", f"×{look.says('speed', '1')}", 40)
    at += 52
    hint = (
        "select text to co-select · click a rule to choose it · "
        "click a line number to set the cursor · type in the document — "
        "Ctrl+Enter re-reads · Ctrl+S saves, and saving compiles · Esc reverts · "
        "Space plays · the chart scrubs"
    )
    said.text(at, y + 22, "fsub", hint, wide - at - PAD)
