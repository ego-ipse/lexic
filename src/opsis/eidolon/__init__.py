"""Eidolon — ideal form: where things sit, and what a grammar's shape is.

Two duties, both of them opsis's own work rather than lexic's. Layout
turns the naming graph into positions: a tidy tree, parents centred
over what they read, roots spread apart. Topology answers what a
grammar's rules refer to and how deep each sits, which is what a rules
graph is drawn from.

Nothing here reads a text. Deciding where a node sits is opsis's
business; deciding what a text means never is.
"""

from __future__ import annotations

from collections import deque

from lexic.ir import IrAst, IrRuleRef, IrSelf

__all__ = ["Topology", "layout"]

COL = 470
"""Horizontal step between siblings."""

ROW = 300
"""Vertical step between a reader and what it reads."""

ORIGIN = (520, 240)
"""Where the first root sits."""


def layout(parents: dict[str, str], idents: list[str]) -> dict[str, tuple[int, int]]:
    """Where every reading sits, from nothing but who reads whom.

    Leaves take the next free column and a parent centres over its
    children, so the picture is a tidy tree without anyone having said
    so. Readings nobody reads are roots, laid out left to right in the
    order they arrived.

    :param parents: reading ident → the ident that reads it.
    :param idents: every reading, in the order they were opened.
    :returns: ident → (x, y).
    """
    kids: dict[str, list[str]] = {ident: [] for ident in idents}
    for child, parent in parents.items():
        if parent in kids and child in kids:
            kids[parent].append(child)
    roots = [i for i in idents if parents.get(i, "") not in kids]
    place: dict[str, tuple[int, int]] = {}
    slot = 0

    def visit(ident: str, depth: int) -> float:
        nonlocal slot
        here = kids[ident]
        if not here:
            column = float(slot)
            slot += 1
        else:
            spread = [visit(kid, depth + 1) for kid in here]
            column = sum(spread) / len(spread)
        place[ident] = (
            ORIGIN[0] + int(column * COL),
            ORIGIN[1] + depth * ROW,
        )
        return column

    for root in roots:
        visit(root, 0)
        slot += 1  # a gap, so one tree never crowds the next
    return place


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
