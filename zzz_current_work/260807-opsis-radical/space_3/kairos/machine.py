"""The compiled machine — clones, and the room they would need.

Nodes here are CLONES, not rules: the same rule compiled for two hard
continuations IS two nodes, and that multiplication is the machine. The build
before this one learned the rest the hard way:

- serving only the clones a run entered showed a decomposed view and called
  it the automaton — the walk LIGHTS the machine, it does not replace it;
- a clone id must index the table it was measured against, or it lights the
  wrong clone;
- 126 clones over 12 levels cannot be drawn in a quarter-width column at any
  spacing, which is a placement answer, not a layout one.
"""

from __future__ import annotations

from praxis.reading import Facet

from lexic.compile import CompiledGrammar
from lexic.parsing.pda.compiler.specs import CloneKey

__all__ = ["Machine", "machine_facet", "of"]


class Machine:
    """What the compiler built, counted rather than described."""

    __slots__ = ("clones", "deepest", "rules")

    def __init__(self, clones: int, rules: int, deepest: int) -> None:
        self.clones = clones
        self.rules = rules
        self.deepest = deepest

    def line(self) -> str:
        return (
            f"{self.clones} clones built from {self.rules} rules, {self.deepest} deep"
        )


def of(compiled: CompiledGrammar) -> Machine:
    """The machine this grammar compiles to — read off the artefact itself."""
    tables = compiled.pda_tables()
    names = {key.name for key in tables.clones if isinstance(key, CloneKey)}
    depth = 0
    start = tables.start_key
    if isinstance(start, CloneKey):
        seen = {start}
        frontier = [start]
        while frontier and depth < 64:
            onward: list[CloneKey] = []
            for key in frontier:
                spec = tables.clones.get(key)
                if spec is None:
                    continue
                for arm in spec.arms:
                    for item in arm.specs:
                        target = item.payload
                        if isinstance(target, CloneKey) and target not in seen:
                            seen.add(target)
                            onward.append(target)
            if onward:
                depth += 1
            frontier = onward
    return Machine(len(tables.clones), len(names), depth)


def machine_facet(compiled: CompiledGrammar) -> Facet:
    """The room the machine would need — which is more than a column has."""
    machine = of(compiled)
    wide = max(24, machine.clones * 6)
    return Facet("machine", "graph", wide, max(1, machine.deepest))
