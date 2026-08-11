"""What a frame is made of — marks to paint, and rectangles to land on.

Its own module because every surface needs the vocabulary and the composer
needs every surface.
"""

from __future__ import annotations

__all__ = ["CELL", "ROW", "Frame"]

CELL = 7.0
ROW = 19.0


class Frame:
    """Marks to paint, and the rectangles a pointer can land on."""

    __slots__ = ("hits", "marks", "tall", "wide")

    def __init__(self, wide: int, tall: int) -> None:
        self.marks: list[str] = []
        self.hits: list[str] = []
        self.wide = wide
        self.tall = tall

    def box(
        self, x: float, y: float, w: float, h: float, tone: str, said: str = ""
    ) -> None:
        self.marks.append(f"box {x:.1f} {y:.1f} {w:.1f} {h:.1f} {tone} {said}")

    def line(self, x1: float, y1: float, x2: float, y2: float, tone: str) -> None:
        self.marks.append(f"line {x1:.1f} {y1:.1f} {x2:.1f} {y2:.1f} {tone}")

    def text(self, x: float, y: float, tone: str, said: str, room: float = 0.0) -> None:
        """Words at a place, clipped to the room they were given."""
        if room > 0:
            fits = max(1, int(room / CELL))
            if len(said) > fits:
                said = said[: fits - 1] + "…"
        self.marks.append(f"text {x:.1f} {y:.1f} {tone} {said}")

    def hit(self, x: float, y: float, w: float, h: float, kind: str, goes: str) -> None:
        self.hits.append(f"{x:.1f} {y:.1f} {w:.1f} {h:.1f} {kind} {goes}")

    def wire(self, generation: int) -> str:
        return "\n".join(
            [
                f"#FRAME {self.wide} {self.tall} {generation} {len(self.marks)}",
                *self.marks,
                f"#HITS {len(self.hits)}",
                *self.hits,
                "",
            ]
        )
