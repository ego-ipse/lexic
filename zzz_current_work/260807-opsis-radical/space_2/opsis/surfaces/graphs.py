"""The three pictures of the grammar — relations, rails, and the machine.

Each is a drawing `paint.py` already emits; a surface here is what decides
how big to ask for it and where its own scroll sits.
"""

from __future__ import annotations

from lexic.compile import CompiledGrammar

from kairos.engine import automaton
from opsis.frame.marks import Frame
from eidolon.camera import project
from eidolon.layout import VIEWS, positions
from eidolon.topology import edges
from opsis.frame.tones import runs
from opsis.grammar import rails
from opsis.paint import automaton_drawing, graph_drawing, rails_drawing
from opsis.surfaces.surface import Box, Surface
from praxis.view import View

__all__ = ["Machine", "Railroad", "Relations"]


class Graph(Surface):
    """A picture of the grammar, sharing the reader's column."""

    column = "reader"
    relation = "tabbed"

    def room(self, view: View) -> tuple[int, int]:
        rules = view.machine.grammar.rules if view.machine else ()
        return 80, max(8, len(rules) * 3)

    def draw(self, said: Frame, box: Box, view: View) -> None:
        if view.machine is None:
            said.text(box[0] + 12, box[1] + 24, "dim", "this reading has no machine")
            return
        self.picture(said, box, view, view.machine)

    def picture(
        self, said: Frame, box: Box, view: View, machine: CompiledGrammar
    ) -> None:
        """The picture itself, once there is a machine to draw one of."""
        raise NotImplementedError


class Relations(Graph):
    """Which rule reaches which — flat, arced, or as rings in three-space."""

    name = "relations"
    title = "RELATIONS · which rule reaches which"

    def picture(
        self, said: Frame, box: Box, view: View, machine: CompiledGrammar
    ) -> None:
        x, y, w, h = box
        how = view.looking.graph
        self._chips(said, x + 8, y + 6, how)
        room = (x, y + 26, w, h - 26)
        if how == "rings":
            self._rings(said, room, view, machine)
            return
        drawn = graph_drawing(
            machine.grammar, how, int(w), int(h - 26), None, view.lit_rules
        )
        said.place(drawn, x, y + 26)

    def _chips(self, said: Frame, x: float, y: float, how: str) -> None:
        """Which way of looking — a property of the surface, said in place."""
        for name in VIEWS:
            here = name == how
            room = runs("label", name) + 16
            said.box(x, y, room, 15, "lit" if here else "panel")
            said.text(x + 8, y + 11, "ink" if here else "dim", name, room - 12)
            said.hit(x, y, room, 15, "graph", name)
            x += room + 4

    def _rings(
        self, said: Frame, box: Box, view: View, machine: CompiledGrammar
    ) -> None:
        """A ring per level, turned by the hand — the camera is here, not there."""
        x, y, w, h = box
        look = view.looking
        at = project(
            # a tall thin tube of rings reads as a smear; the levels are
            # pulled close enough that the whole stack is one object
            positions(machine.grammar, "rings", int(w), int(h), {"levelstep": 70.0}),
            look.yaw,
            look.pitch,
            w,
            h,
        )
        lit = view.lit_rules
        for a, b in edges(machine.grammar):
            one, two = at.get(a), at.get(b)
            if one is None or two is None:
                continue
            tone = "hot" if a in lit and b in lit else "cool"
            said.line(x + one[0], y + one[1], x + two[0], y + two[1], tone)
        # far first, so what is nearest is drawn last and reads as nearest
        for name in sorted(at, key=lambda n: at[n][2]):
            px, py, near = at[name]
            says = name if len(name) <= 24 else name[:23] + "…"
            room = runs("ink", says) + 8
            said.box(
                x + px - room / 2,
                y + py - 8,
                room,
                16,
                "hot" if name in lit else ("ref" if near > 0.9 else "seen"),
                says,
            )
            said.hit(x + px - room / 2, y + py - 8, room, 16, "rule", name)


class Railroad(Graph):
    """Each rule as the track it describes."""

    name = "railroad"
    title = "RAILROAD · each rule as the track it describes"

    def picture(
        self, said: Frame, box: Box, view: View, machine: CompiledGrammar
    ) -> None:
        x, y, w, _h = box
        drawn = rails_drawing(rails(machine.grammar), int(w - 20))
        said.place(drawn, x + 10, y + 6 - view.looking.rail_top)


class Machine(Graph):
    """The predictive automaton, seat by seat — lit where the cursor stands."""

    name = "machine"
    title = "MACHINE · the predictive automaton, seat by seat"

    def picture(
        self, said: Frame, box: Box, view: View, machine: CompiledGrammar
    ) -> None:
        x, y, w, _h = box
        seats = {
            seat
            for s0, e0, _d, _n, ok, seat in view.watched()
            if ok and s0 <= view.at < e0
        }
        drawn = automaton_drawing(automaton(machine.pda_tables()), seats, set())
        said.place(drawn, x + 10, y + 6, min(1.0, (w - 20) / max(1.0, drawn.wide)))
