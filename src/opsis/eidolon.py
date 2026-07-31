"""Eidolon — structure before presentation.

The rule graph's math, no pixels: reference edges, BFS levels from the
start rule, cycle membership. :mod:`opsis.graphic` lays it out.
"""

from __future__ import annotations

from typing import Any

from lexic.ir import IrAlternation, IrRuleRef


class Topology:
    """One grammar's rule graph: names, edges, levels, cycles, start."""

    def __init__(self, ast: Any) -> None:
        rules = list(ast.rules)
        self.names: list[str] = [str(r.name) for r in rules]
        self.semantic: dict[str, bool] = {str(r.name): bool(r.semantic) for r in rules}
        defined = set(self.names)
        self.out: dict[str, list[str]] = {n: [] for n in self.names}
        for r in rules:
            for target in sorted(_refs(r.body) & defined):
                self.out[str(r.name)].append(target)
        self.start: str | None = self.names[0] if self.names else None
        self.levels: dict[str, int] = _levels(self.names, self.out, self.start)
        self.cyclic: set[str] = _cyclic(self.names, self.out)

    @property
    def edges(self) -> list[tuple[str, str]]:
        """Every reference edge, source order."""
        return [(src, dst) for src, kids in self.out.items() for dst in kids]


def _refs(body: Any) -> set[str]:
    """Every rule name referenced anywhere under an alternation body."""
    found: set[str] = set()
    stack = [body]
    while stack:
        node = stack.pop()
        if isinstance(node, IrRuleRef):
            found.add(str(node))
        elif isinstance(node, IrAlternation):
            for arm in node:
                for item in arm:
                    stack.append(item.atom)
    return found


def _levels(names: list[str], out: dict[str, list[str]], start: str | None) -> dict[str, int]:
    """BFS depth from the start rule; unreachable rules get ``-1``."""
    levels = {n: -1 for n in names}
    if start is None:
        return levels
    levels[start] = 0
    queue = [start]
    while queue:
        node = queue.pop(0)
        for nxt in out[node]:
            if levels[nxt] == -1:
                levels[nxt] = levels[node] + 1
                queue.append(nxt)
    return levels


def _cyclic(names: list[str], out: dict[str, list[str]]) -> set[str]:
    """Rules on any reference cycle — nontrivial SCC members or self-loops.

    Iterative Tarjan; the engine's no-recursion discipline applies to
    every opsis walk too.
    """
    index: dict[str, int] = {}
    low: dict[str, int] = {}
    on_stack: set[str] = set()
    order: list[str] = []
    result: set[str] = set()
    counter = 0
    for root in names:
        if root in index:
            continue
        work: list[tuple[str, int]] = [(root, 0)]
        while work:
            node, edge_i = work.pop()
            if edge_i == 0:
                index[node] = low[node] = counter
                counter += 1
                order.append(node)
                on_stack.add(node)
            descended = False
            kids = out[node]
            for j in range(edge_i, len(kids)):
                kid = kids[j]
                if kid not in index:
                    work.append((node, j + 1))
                    work.append((kid, 0))
                    descended = True
                    break
                if kid in on_stack:
                    low[node] = min(low[node], index[kid])
            if descended:
                continue
            if low[node] == index[node]:
                component = []
                while True:
                    top = order.pop()
                    on_stack.discard(top)
                    component.append(top)
                    if top == node:
                        break
                if len(component) > 1 or node in out[node]:
                    result.update(component)
            if work:
                parent = work[-1][0]
                low[parent] = min(low[parent], low[node])
    return result
