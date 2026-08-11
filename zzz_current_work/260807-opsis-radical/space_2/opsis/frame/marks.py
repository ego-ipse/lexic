"""What a frame is made of — marks to paint, rectangles to land on, real text.

A text plane is NOT painted. The browser's own text engine draws it: native
selection, a real caret, a double-click on a word, an input method — none of
which a canvas can answer for, and the reason a drawn document feels broken
to the hand. What the frame decides is WHERE it goes and on what geometry;
the drawn half and the text half are welded by that one geometry, which is
what keeps a highlight on the character it is about.
"""

from __future__ import annotations

from opsis.frame.tones import ADVANCE, register

__all__ = ["CELL", "ROW", "Frame"]

# --fs 12.5px in --mono is 7.5px per glyph; --lh is 19px
CELL = 7.5
ROW = 19.0

# how many x,y pairs lead a mark of each kind; the rest rides along unchanged
POINTS = {"line": 2, "curve": 3, "bez": 4}


class Frame:
    """One frame: marks, hit rectangles, and the text planes welded into it."""

    __slots__ = ("hits", "lifted", "marks", "over", "planes", "tall", "texts", "wide")

    def __init__(self, wide: int, tall: int) -> None:
        self.marks: list[str] = []
        # what is drawn ABOVE the text planes. They are real elements, so
        # anything the one canvas painted in their rectangle was behind them:
        # a refusal banner nobody could read, a chip under the line it is
        # about. The instrument has always welded an under and an over canvas
        # around its text; this is that over.
        self.over: list[str] = []
        self.lifted = False
        self.hits: list[str] = []
        self.planes: list[str] = []
        self.texts: list[str] = []
        self.wide = wide
        self.tall = tall

    def _put(self, mark: str) -> None:
        """One mark, onto whichever canvas is being drawn on."""
        (self.over if self.lifted else self.marks).append(mark)

    def lift(self) -> bool:
        """Draw above the text from here — for what must be read over it.

        :returns: whether it was ALREADY above, so that something drawn
            inside a window — which is itself over the text — can put the
            frame back where it found it instead of dropping the window.
        """
        was = self.lifted
        self.lifted = True
        return was

    def drop(self, was: bool = False) -> None:
        """Back below the text, or back to whatever a nested lift found."""
        self.lifted = was

    def box(self, x: float, y: float, w: float, h: float, tone: str) -> None:
        self._put(f"box {x:.1f} {y:.1f} {w:.1f} {h:.1f} {tone}")

    def line(self, x1: float, y1: float, x2: float, y2: float, tone: str) -> None:
        self._put(f"line {x1:.1f} {y1:.1f} {x2:.1f} {y2:.1f} {tone}")

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
        """A quadratic bend — a rail turning off its line."""
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
        self._put(f"arc {x:.1f} {y:.1f} {r:.1f} {tone}")

    def ring(self, x: float, y: float, w: float, h: float, tone: str) -> None:
        """An outline and nothing else — what a lane's span is drawn WITH."""
        self._put(f"ring {x:.1f} {y:.1f} {w:.1f} {h:.1f} {tone}")

    def text(
        self,
        x: float,
        y: float,
        tone: str,
        said: str,
        room: float = 0.0,
        anchor: str = "l",
        face: str = "",
    ) -> None:
        """Words at a place.

        :param room: what it must fit in. A facet under pressure derives less
            rather than clipping, so this is given only where a name genuinely
            cannot wrap.
        :param anchor: which edge `x` is — ``l`` or ``r``. Right-aligning by an
            ESTIMATE of the width is how the parity verdict ended up hanging
            off the masthead; the engine that knows the true width does it.
        :param face: which face to set it in, when that is not the tone's own.
            A COLOUR is not a SIZE: a chip lit `cool` is still a chip, and
            deriving one from the other set head chips at 12.5px and made them
            overlap each other.
        """
        put = face or tone
        if room > 0:
            fits = max(1, int(room / ADVANCE.get(put, CELL)))
            if len(said) > fits:
                said = said[: fits - 1] + "…"
        self._put(f"text {x:.1f} {y:.1f} {tone} {put} {anchor} {said}")

    def hit(
        self,
        x: float,
        y: float,
        w: float,
        h: float,
        kind: str,
        goes: str,
        run: float = 0.0,
        cell: float = 0.0,
    ) -> None:
        """A rectangle a pointer can land on, and what to say when it does.

        :param run: where text inside it starts, when landing WITHIN it means
            something — a click in a line of text names a column.
        :param cell: how wide one of those steps is.
        """
        self.hits.append(
            f"{x:.1f} {y:.1f} {w:.1f} {h:.1f} {kind} {goes} {run:.1f} {cell:.1f}"
        )

    def plane(
        self,
        name: str,
        x: float,
        y: float,
        w: float,
        h: float,
        said: str,
        top: int,
        editable: bool,
    ) -> None:
        """Real text, at a place, on this frame's own glyph geometry."""
        self.planes.append(
            f"{name} {x:.1f} {y:.1f} {w:.1f} {h:.1f} {ROW} {CELL} {top} "
            f"{1 if editable else 0} {len(said)}"
        )
        self.texts.append(said)

    def place(
        self, drawing: object, x: float, y: float, scale: float = 1.0, down: float = 0.0
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
                self._put(
                    " ".join([kind, *(f"{n:.1f}" for n in moved), *parts[1 + count :]])
                )
            elif kind == "box":
                self.box(
                    x + float(parts[1]) * scale,
                    y + float(parts[2]) * tall,
                    float(parts[3]) * scale,
                    float(parts[4]) * tall,
                    parts[5],
                )
                label = " ".join(parts[7:]) if len(parts) > 7 else ""
                if label:
                    self.text(
                        x + float(parts[1]) * scale + 4,
                        y + (float(parts[2]) + float(parts[4]) * 0.72) * tall,
                        "ink",
                        label,
                        float(parts[3]) * scale - 6,
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

    def wire(self, generation: int, playing: bool = False) -> str:
        """The whole frame. Text blocks go LAST, raw, counted in characters.

        :param playing: whether the reading is running. The leaf used to keep
            its own answer to that and tick from it, so starting playback
            from the transport — which the leaf never sees — began a
            playback nobody drove. One truth, and it is this one.
        """
        return "\n".join(
            [
                *register(),
                f"#FRAME {self.wide} {self.tall} {generation} {len(self.marks)} "
                f"{1 if playing else 0}",
                *self.marks,
                f"#HITS {len(self.hits)}",
                *self.hits,
                f"#OVER {len(self.over)}",
                *self.over,
                f"#PLANES {len(self.planes)}",
                *self.planes,
                "#TEXT",
                "",
            ]
        ) + "".join(self.texts)
