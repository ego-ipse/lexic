"""Where each node SITS — derived here, drawn there.

The leaf used to compute this: rings per level, bands across the width, a row
in declaration order. That is derivation, not drawing, and it lived in the
one place that cannot be checked by a fact. So the positions are an eidolon
product now — the leaf receives coordinates and paints them, and the camera
(yaw, pitch, zoom, pan) stays with the hand that moves it.

Three layouts, because a graph answers three different questions:

- **flat** — bands across the width by derivation distance, each band
  wrapped into as many sub-columns as a name's width allows. Reads as "what
  follows what".
- **arcs** — one row in the grammar's own declaration order, so an edge's
  arc shows how far a reference reaches. Reads as "what reaches where".
- **rings** — a ring per level in 3-space, depth as the earned axis. Reads
  as "how deep this goes"; the leaf projects it under its camera.
"""

from __future__ import annotations

from math import cos, pi, sin

from shape.topology import levels
from lexic.ir import IrAst

__all__ = ["TUNE", "VIEWS", "positions"]

VIEWS = ("flat", "arcs", "rings")

# a name's box, in the same characters every other surface is measured in —
# the room a label needs before it collides with its neighbour
NAME = 78
ROW = 26

# what the hand can change about a layout, and what it means when unset.
# These arrive as state: a slider is configuration, and configuration is the
# server's — the leaf posts what was dragged and receives new places.
TUNE = {"levelstep": 140.0, "ringscale": 1.0, "flatten": 1.0}


def _tuned(tune: dict[str, float] | None) -> dict[str, float]:
    said = dict(TUNE)
    said.update({k: v for k, v in (tune or {}).items() if k in TUNE})
    return said


def _bands(ast: IrAst) -> dict[int, list[str]]:
    """Rules grouped by derivation distance; unreachable ones sit past the end."""
    deep = levels(ast)
    reached = [at for at in deep.values() if at >= 0]
    beyond = (max(reached) if reached else 0) + 1
    out: dict[int, list[str]] = {}
    for name, at in deep.items():
        out.setdefault(beyond if at < 0 else at, []).append(name)
    return out


def flat(
    ast: IrAst, wide: int, tall: int, tune: dict[str, float] | None = None
) -> dict[str, tuple[float, float, float]]:
    """Bands across the width, wrapped so a crowded level stays legible."""
    dial = _tuned(tune)
    bands = _bands(ast)
    deepest = max(bands) if bands else 0
    band_wide = max(90.0, (wide - 40) / (deepest + 1))
    out: dict[str, tuple[float, float, float]] = {}
    for at, names in bands.items():
        columns = max(1, min(len(names), int(band_wide // NAME) or 1))
        rows = -(-len(names) // columns)
        row_tall = min(ROW * dial["ringscale"], max(14.0, (tall - 40) / max(1, rows)))
        for i, name in enumerate(names):
            column, row = i % columns, i // columns
            out[name] = (
                20 + at * band_wide + (column + 0.5) * (band_wide / columns),
                (row - (rows - 1) / 2) * row_tall,
                0.0,
            )
    return out


def arcs(
    ast: IrAst, wide: int, _tall: int, tune: dict[str, float] | None = None
) -> dict[str, tuple[float, float, float]]:
    """One row, in the order the grammar declares its rules."""
    dial = _tuned(tune)
    names = [str(rule.name) for rule in ast.rules]
    pitch = max(18.0, (wide - 40) / max(1, len(names))) * dial["ringscale"]
    return {name: (20 + i * pitch, 0.0, 0.0) for i, name in enumerate(names)}


def rings(
    ast: IrAst, _wide: int, _tall: int, tune: dict[str, float] | None = None
) -> dict[str, tuple[float, float, float]]:
    """A ring per level in 3-space — z is derivation distance, the earned axis."""
    dial = _tuned(tune)
    out: dict[str, tuple[float, float, float]] = {}
    for at, names in _bands(ast).items():
        count = len(names)
        radius = (0.0 if count == 1 else 46 + min(230, count * 15)) * dial["ringscale"]
        for i, name in enumerate(names):
            angle = (i / count) * pi * 2 + at * 0.7
            out[name] = (
                cos(angle) * radius,
                sin(angle) * radius * dial["flatten"],
                -at * dial["levelstep"],
            )
    return out


LAYOUTS = {"flat": flat, "arcs": arcs, "rings": rings}


def positions(
    ast: IrAst,
    view: str = "rings",
    wide: int = 900,
    tall: int = 600,
    tune: dict[str, float] | None = None,
) -> dict[str, tuple[float, float, float]]:
    """Every rule's place, for one way of looking at the grammar."""
    return LAYOUTS.get(view, rings)(ast, wide, tall, tune)
