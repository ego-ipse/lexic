"""What a surface is handed when it is asked to draw itself.

Computed once per frame — the reader compiled, the spans open at the cursor,
which rules those are and which lines spell them. Every surface reads the
same view, so two of them can never disagree about what is live.
"""

from __future__ import annotations

from typing import Any

from lexic.compile import CompiledGrammar

from deixis.points import open_at
from kairos.parse import hypotheses, watch
from praxis.memory import Memory
from praxis.looking import Looking
from praxis.reading import Reading, Span, as_written, reader_of, ruledefs

__all__ = ["View"]

# what the machine did to this document — the same answer for every surface
# that asks, and re-asked only when the reading itself changes
WATCHED: Memory[list[list[Any]]] = Memory()
HELD: Memory[list[tuple[int, int, int]]] = Memory()


def _spans(machine: CompiledGrammar, text: str) -> list[tuple[int, int, int]]:
    """Earley's hypotheses, read off as start, end and depth."""
    said, _names = hypotheses(machine, text)
    return [
        (int(p[0]), int(p[1]), int(p[2]))
        for p in (line.split(" ") for line in said)
        if len(p) >= 3
    ]


class View:
    """One reading, at one moment, looked at one way."""

    __slots__ = (
        "at",
        "lit_lines",
        "lit_rules",
        "live",
        "looking",
        "machine",
        "reading",
        "rules",
    )

    def __init__(self, reading: Reading, at: float, looking: Looking) -> None:
        self.reading = reading
        self.at = at
        self.looking = looking
        self.machine: CompiledGrammar | None = reader_of(reading)
        self.rules: list[tuple[str, int, int]] = ruledefs(reading.reader_text)
        self.live: list[Span] = open_at(reading, at)
        self.lit_rules = {as_written(self.rules, span.rule) for span in self.live}
        self.lit_lines = {
            line
            for name, first, last in self.rules
            if name in self.lit_rules
            for line in range(first, last + 1)
        }

    def watched(self) -> list[list[Any]]:
        """Every frame the predictive machine opened, in the order it opened it."""
        machine = self.machine
        if machine is None:
            return []
        text = self.reading.text
        return WATCHED.once(f"{self.reading.stamp}", lambda: watch(machine, text))

    def held(self) -> list[tuple[int, int, int]]:
        """Every hypothesis the other engine carried, as start, end and depth."""
        machine = self.machine
        if machine is None:
            return []
        text = self.reading.text
        return HELD.once(f"{self.reading.stamp}", lambda: _spans(machine, text))

    def named(self, rule: str) -> str:
        """A rule, spelled the way the reader spells it."""
        return as_written(self.rules, rule)
