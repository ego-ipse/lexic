"""What a grammar's shape IS — who names whom, and how far from the start.

Not a drawing and not a layout: the graph itself. What is reachable,
what is noise, and the breadth-first distance that makes a rules window
read left to right as depth.
"""

from __future__ import annotations

from collections import deque

from lexic.ir import IrAst, IrRuleRef, IrSelf

__all__ = ["Topology"]


class Topology:
    """A grammar's rule graph: who names whom, and how far from the start."""

    __slots__ = ("names", "out", "levels", "semantic", "start")

    def __init__(self, ast: IrAst) -> None:
        rules = list(ast.rules)
        self.names: list[str] = [str(rule.name) for rule in rules]
        self.semantic: dict[str, bool] = {
            str(rule.name): bool(rule.semantic) for rule in rules
        }
        defined = set(self.names)
        self.out: dict[str, list[str]] = {
            str(rule.name): sorted(_refs(rule.body) & defined) for rule in rules
        }
        self.start: str = str(ast.start) or (self.names[0] if self.names else "")
        self.levels: dict[str, int] = self._depths()

    def reaches(self, name: str) -> bool:
        """Whether the start rule can get to this one at all."""
        return self.levels.get(name, -1) >= 0

    def deepest(self) -> int:
        """How far from the start the furthest reachable rule sits."""
        return max(self.levels.values(), default=0)

    def _depths(self) -> dict[str, int]:
        """Breadth-first distance from the start rule; unreachable is -1."""
        levels = dict.fromkeys(self.names, -1)
        if self.start not in levels:
            return levels
        levels[self.start] = 0
        queue = deque([self.start])
        while queue:
            here = queue.popleft()
            for nxt in self.out.get(here, []):
                if levels.get(nxt, 0) < 0:
                    levels[nxt] = levels[here] + 1
                    queue.append(nxt)
        return levels


def _refs(node: IrSelf) -> set[str]:
    """Every rule name referenced under ``node`` — a plain spine walk."""
    out: set[str] = set()
    stack: list[IrSelf] = [node]
    while stack:
        here = stack.pop()
        if isinstance(here, IrRuleRef):
            out.add(str(here))
        stack.extend(here.children())
    return out
