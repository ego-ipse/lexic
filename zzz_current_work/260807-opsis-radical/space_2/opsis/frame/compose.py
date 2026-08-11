"""One frame — the arrangement, applied, with every surface drawn into it.

There is no list of surfaces here and no branch on which one is which.
`surfaces` is the open table: it measures, `space.arrange` decides the
arrangement, `panels` applies it, and each node draws itself into the room it
was handed. A new surface changes nothing in this file.
"""

from __future__ import annotations

from opsis.frame.marks import Frame
from opsis.frame.panels import chrome, rooms
from opsis.frame.tones import runs
from opsis.space import arrange, columns_of
from opsis.surfaces import SHOWN, by_name, facets
from praxis.looking import Looking
from praxis.reading import Reading
from praxis.view import View

__all__ = ["compose"]

BAR = 32.0
FOOT = 28.0
EDGE = 8.0


def _masthead(said: Frame, reading: Reading, wide: int) -> None:
    """The instrument's name, what is loaded, and whether the reading holds."""
    said.box(0, 0, wide, BAR, "head")
    said.line(0, BAR, wide, BAR, "hair")
    said.text(14, 21, "title", "FACETS")
    said.text(
        86,
        21,
        "note",
        f"{reading.reader_name} read {len(reading.text):,} chars "
        f"in {reading.seconds:.2f}s",
        420,
    )
    holds = (
        "model.to_text() == document — holds" if reading.faithful else "NOT FAITHFUL"
    )
    said.text(
        wide - 14 - runs("label", holds),
        21,
        "label" if reading.faithful else "bad",
        holds,
    )


def _footer(said: Frame, reading: Reading, at: float, wide: int, tall: int) -> None:
    """The transport, and what the cursor stands on."""
    y = tall - FOOT
    said.box(0, y, wide, FOOT, "head")
    said.line(0, y, wide, y, "hair")
    chip = 14.0
    for glyph, gesture in (("‹", "step~-1"), ("▶", "play"), ("›", "step~1")):
        said.box(chip, y + 6, 22, 16, "panel")
        said.text(chip + 8, y + 18, "ink", glyph)
        said.hit(chip, y + 6, 22, 16, "do", gesture)
        chip += 26
    said.text(
        chip + 8,
        y + 18,
        "note",
        f"char {int(at):,} / {len(reading.text):,} · {len(reading.spans):,} spans · "
        "click a tab, a span, a rule · space plays · ⧉ pops a room out",
        wide - chip - 24,
    )


def compose(
    reading: Reading,
    wide: int,
    tall: int,
    at: float,
    looking: Looking,
    only: str = "",
) -> Frame:
    """The instrument, at this size, at this moment, as one frame.

    :param only: a single surface's name — what a popped-out window asks for.
    """
    said = Frame(wide, tall)
    view = View(reading, at, looking)
    said.box(0, 0, wide, tall, "field")
    titles = {surface.name: surface.title for surface in SHOWN}

    alone = by_name(only)
    if alone is not None:
        room = rooms(alone.name, EDGE, EDGE, wide - EDGE * 2, tall - EDGE * 2)[0]
        alone.draw(said, chrome(said, room, titles, keep=False), view)
        return said

    _masthead(said, reading, wide)
    measured = facets(view)
    showing = {
        group[0].column or group[0].name: next(
            (i for i, facet in enumerate(group) if facet.name == looking.surface), 0
        )
        for group in columns_of(measured)
    }
    for room in rooms(
        arrange(measured, 200, showing),
        EDGE,
        BAR + EDGE,
        wide - EDGE * 2,
        tall - BAR - FOOT - EDGE * 2,
    ):
        surface = by_name(room.name)
        if surface is not None:
            surface.draw(said, chrome(said, room, titles), view)
    _footer(said, reading, at, wide, tall)
    return said
