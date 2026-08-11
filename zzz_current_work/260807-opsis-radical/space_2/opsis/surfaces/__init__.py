"""Every surface the instrument can show — one node each, on an open table.

A surface is a NODE, not a branch of a composer: it says what it is called,
which column it belongs to, how much room it needs, and how to draw itself.
Adding one means writing one class and listing it here; the arrangement, the
tabs, the header, the scroll and the hit rectangles all fall out. Nothing
downstream asks *which* surface this is.
"""

from __future__ import annotations

from opsis.surfaces.clocks import Derivation, Spine
from opsis.surfaces.graphs import Machine, Railroad, Relations
from opsis.surfaces.planes import Document, Reader
from opsis.surfaces.surface import Box, Surface
from praxis.reading import Facet
from praxis.view import View

__all__ = ["Box", "SHOWN", "Surface", "by_name", "facets"]

# order is meaning: left to right, and within a column, top to bottom
SHOWN: tuple[Surface, ...] = (
    Reader(),
    Relations(),
    Railroad(),
    Machine(),
    Document(),
    Derivation(),
    Spine(),
)


def by_name(name: str) -> Surface | None:
    """The surface that answers to a name, if one does."""
    return next((surface for surface in SHOWN if surface.name == name), None)


def facets(view: View) -> list[Facet]:
    """Each surface's declared appetite, measured against this reading."""
    return [surface.facet(view) for surface in SHOWN]
