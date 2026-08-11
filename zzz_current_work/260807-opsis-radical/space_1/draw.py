"""The rule graph — and the room it needs, which is the whole lesson.

Four rounds of layout work went into the graph before this one: fitting it,
measuring labels, wrapping crowded levels, reading it down a tall facet. All
of them were real and none of them mattered, because the same graph is
legible in a window and a smear in a quarter-width column. The picture was
never badly drawn; it was badly PLACED.

So the graph reports what it needs, in the same characters every other
surface uses, and the arrangement answers. A graph that cannot be given its
room asks for a window instead of being crushed into one.
"""

from __future__ import annotations

from lexic.ir import IrAst, IrRuleRef
from read import Facet

__all__ = ["edges", "graph_facet", "levels", "reachable"]


def edges(ast: IrAst) -> list[tuple[str, str]]:
    """Reference edges, from the AST's own ``IrRuleRef`` leaves."""
    out: list[tuple[str, str]] = []
    for rule in ast.rules:
        seen: set[str] = set()
        stack = [rule.body]
        while stack:
            node = stack.pop()
            if isinstance(node, IrRuleRef):
                name = str(node)
                if name not in seen:
                    seen.add(name)
                    out.append((str(rule.name), name))
                continue
            stack.extend(node.children())
    return out


def levels(ast: IrAst) -> dict[str, int]:
    """Derivation distance from the start rule; −1 for what it never reaches."""
    out: dict[str, list[str]] = {}
    for frm, to in edges(ast):
        out.setdefault(frm, []).append(to)
    start = str(ast.rules[0].name)
    depth = {str(rule.name): -1 for rule in ast.rules}
    depth[start] = 0
    frontier = [start]
    while frontier:
        onward = []
        for name in frontier:
            for ref in out.get(name, ()):
                if depth.get(ref, 0) == -1:
                    depth[ref] = depth[name] + 1
                    onward.append(ref)
        frontier = onward
    return depth


def graph_facet(ast: IrAst) -> Facet:
    """What the graph needs to be legible, measured the way text is.

    Wide as the busiest level's names laid side by side; tall as the chain is
    deep. These are the numbers that decide whether it gets a column or a
    window — and 126 clones over 12 levels will always ask for a window,
    which is the honest answer rather than a crushed picture.
    """
    deep = levels(ast)
    rows: dict[int, list[str]] = {}
    for name, at in deep.items():
        rows.setdefault(max(0, at), []).append(name)
    wide = max(
        (sum(len(n) + 3 for n in names) for names in rows.values()),
        default=24,
    )
    return Facet(
        "graph",
        "graph",
        wide,
        max(len(rows), 1),
        title="THE RELATIONS · which rule refers to which",
        # a second view of the reader, not a competitor for its width
        column="reader",
        relation="tabbed",
    )


def reachable(ast: IrAst, start: str) -> tuple[list[tuple[str, str]], dict[str, int]]:
    """The graph as seen FROM one rule — what it can reach, and how far.

    A rule's neighbourhood is a different graph from the whole grammar's, and
    drawing the whole thing every time is how a question about one rule gets
    answered with a picture of everything.
    """
    onward: dict[str, list[str]] = {}
    for frm, to in edges(ast):
        onward.setdefault(frm, []).append(to)
    depth = {start: 0}
    frontier = [start]
    while frontier:
        nxt: list[str] = []
        for name in frontier:
            for ref in onward.get(name, ()):
                if ref not in depth:
                    depth[ref] = depth[name] + 1
                    nxt.append(ref)
        frontier = nxt
    kept = [(a, b) for a, b in edges(ast) if a in depth and b in depth]
    return kept, depth
