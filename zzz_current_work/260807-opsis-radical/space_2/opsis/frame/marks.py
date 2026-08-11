"""What a frame is made of — marks to paint, and rectangles to land on.

Its own module because every surface needs the vocabulary and the composer
needs every surface.
"""

from __future__ import annotations

from opsis.frame.tones import ADVANCE, register

__all__ = ["CELL", "ROW", "Frame"]

CELL = 7.0
ROW = 19.0

# how many x,y pairs lead a mark of each kind; the rest rides along unchanged
POINTS = {"line": 2, "curve": 3, "bez": 4}


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
        """A rectangle, and — if it is labelled — the words that sit in it."""
        self.marks.append(f"box {x:.1f} {y:.1f} {w:.1f} {h:.1f} {tone}")
        if said:
            self.text(x + 4, y + h / 2 + 4, "ink", said, w - 6)

    def line(self, x1: float, y1: float, x2: float, y2: float, tone: str) -> None:
        self.marks.append(f"line {x1:.1f} {y1:.1f} {x2:.1f} {y2:.1f} {tone}")

    def curve(
        self,
        x1: float,
        y1: float,
        cx: float,
        cy: float,
        x2: float,
        y2: float,
        tone: str,
    ) -> None:
        """A quadratic bend — a rail turning off its line, and the graph's edges."""
        self.marks.append(
            f"curve {x1:.1f} {y1:.1f} {cx:.1f} {cy:.1f} {x2:.1f} {y2:.1f} {tone}"
        )

    def bez(
        self,
        x1: float,
        y1: float,
        ax: float,
        ay: float,
        bx: float,
        by: float,
        x2: float,
        y2: float,
        tone: str,
    ) -> None:
        """A cubic S — what a railroad branch actually is."""
        self.marks.append(
            f"bez {x1:.1f} {y1:.1f} {ax:.1f} {ay:.1f} {bx:.1f} {by:.1f} "
            f"{x2:.1f} {y2:.1f} {tone}"
        )

    def arc(self, x: float, y: float, r: float, tone: str) -> None:
        self.marks.append(f"arc {x:.1f} {y:.1f} {r:.1f} {tone}")

    def text(self, x: float, y: float, tone: str, said: str, room: float = 0.0) -> None:
        """Words at a place, clipped to the room they were given."""
        if room > 0:
            fits = max(1, int(room / ADVANCE.get(tone, CELL)))
            if len(said) > fits:
                said = said[: fits - 1] + "…"
        self.marks.append(f"text {x:.1f} {y:.1f} {tone} {said}")

    def hit(self, x: float, y: float, w: float, h: float, kind: str, goes: str) -> None:
        self.hits.append(f"{x:.1f} {y:.1f} {w:.1f} {h:.1f} {kind} {goes}")

    def place(
        self,
        drawing: object,
        x: float,
        y: float,
        scale: float = 1.0,
        down: float = 0.0,
    ) -> None:
        """A drawing's own marks, moved into the room it was given.

        :param down: the vertical scale, when it differs from the horizontal —
            a band stretched across a column must not also stretch down it.
        """
        tall = down or scale
        for mark in getattr(drawing, "marks", []):
            parts = mark.split(" ")
            kind = parts[0]
            if kind in POINTS:
                count = POINTS[kind] * 2
                moved = [
                    (x + float(n) * scale) if i % 2 == 0 else (y + float(n) * tall)
                    for i, n in enumerate(parts[1 : 1 + count])
                ]
                self.marks.append(
                    " ".join([kind, *(f"{n:.1f}" for n in moved), *parts[1 + count :]])
                )
            elif kind == "box":
                self.box(
                    x + float(parts[1]) * scale,
                    y + float(parts[2]) * tall,
                    float(parts[3]) * scale,
                    float(parts[4]) * tall,
                    parts[5],
                    " ".join(parts[7:]) if len(parts) > 7 else "",
                )
            elif kind == "arc":
                self.arc(
                    x + float(parts[1]) * scale,
                    y + float(parts[2]) * tall,
                    float(parts[3]) * scale,
                    parts[4],
                )
            elif kind == "text":
                self.text(
                    x + float(parts[1]) * scale,
                    y + float(parts[2]) * tall,
                    parts[3],
                    " ".join(parts[4:]),
                )

    def wire(self, generation: int) -> str:
        return "\n".join(
            [
                *register(),
                f"#FRAME {self.wide} {self.tall} {generation} {len(self.marks)}",
                *self.marks,
                f"#HITS {len(self.hits)}",
                *self.hits,
                "",
            ]
        )
