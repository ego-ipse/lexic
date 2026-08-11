"""What every surface is — the one thing they all have in common.

A surface knows three things about itself: what it is called, how much room
it wants, and how to draw itself into the room it got. It knows nothing about
any other surface, and nothing about where it ended up.
"""

from __future__ import annotations

from opsis.frame.marks import Frame
from praxis.reading import Facet
from praxis.view import View

__all__ = ["Box", "Surface"]

Box = tuple[float, float, float, float]


class Surface:
    """One thing the instrument can show."""

    name = ""
    title = ""
    column = ""
    relation = "beside"

    def room(self, view: View) -> tuple[int, int]:
        """The room it needs, in characters — its widest line, and its lines."""
        raise NotImplementedError

    def draw(self, said: Frame, box: Box, view: View) -> None:
        """Itself, into the rectangle it was given."""
        raise NotImplementedError

    def facet(self, view: View) -> Facet:
        """What it declares to the arrangement — measured, never assumed."""
        wide, tall = self.room(view)
        return Facet(
            self.name,
            type(self).__name__.casefold(),
            wide,
            tall,
            title=self.title,
            column=self.column or self.name,
            relation=self.relation,
        )
