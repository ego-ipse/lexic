"""A grammar as the graph it is, two ways.

Laid out by distance from the start, so the columns ARE the depth and
an unreachable rule is visibly off to one side. The railroad says the
same thing rule by rule, in the shape people read grammars in.

The pointing half — a reading beside its text — is deixis, because it
is about making two things name each other rather than about form.
"""

from __future__ import annotations

from lexic.ir import IrAst, IrDoc
from opsis.eidolon.topology import Topology
from opsis.opsis.draw.canvas import el, raw
from opsis.opsis.draw.graphic import RAIL_CSS, rule_svg
from opsis.opsis.read.parts import Node, graph

__all__ = ["railroad_view", "rules_view"]

# ── a grammar is a graph of rules ─────────────────────────────────────


def rules_view(ast: IrAst) -> IrDoc:
    """Rules by distance from the start, edges by reference.

    Hue says what a rule IS at a glance: the start rule, structural
    noise, something nothing reaches, or an ordinary rule. Clicking one
    opens its railroad — which lives in the world, because a diagram
    belongs to its rule and not to whichever window asked.
    """
    topo = Topology(ast)
    rows: dict[int, int] = {}
    nodes: list[Node] = []
    index: dict[str, int] = {}
    unreachable = max(topo.levels.values(), default=0) + 1
    for name in topo.names:
        level = topo.levels.get(name, -1)
        column = level if level >= 0 else unreachable
        row = rows.get(column, 0)
        rows[column] = row + 1
        index[name] = len(nodes)
        nodes.append(
            Node(name, name, column, row, _rule_hue(name, topo), name, f"rr-{name}")
        )
    edges = [
        (index[src], index[dst])
        for src, named in topo.out.items()
        for dst in named
        if src in index and dst in index
    ]
    note = (
        f"{len(nodes)} rules · {len(edges)} references · start is {topo.start} · "
        "click a rule for its railroad"
    )
    return el("div", None, el("div", {"class": "note"}, note), graph(nodes, edges))


def _rule_hue(name: str, topo: Topology) -> str:
    """What a rule is: the start, noise, unreachable, or ordinary."""
    if name == topo.start:
        return "amber"
    if topo.levels.get(name, -1) < 0:
        return "err"
    if not topo.semantic.get(name, True):
        return "dim"
    return "cyan"


def railroad_view(ast: IrAst) -> IrDoc:
    """Every rule's track, stacked — the grammar as one long diagram."""
    rows = [
        el(
            "div",
            {"class": "row"},
            el("div", {"class": "name", "data-rule": str(rule.name)}, str(rule.name)),
            el("div", {"class": "rr"}, raw(rule_svg(rule))),
        )
        for rule in ast.rules
    ]
    return el(
        "div",
        None,
        raw(f"<style>{RAIL_CSS}</style>"),
        el("div", {"class": "note"}, f"{len(rows)} rules · every track it walks"),
        *rows,
    )


# ── an instance is the tree its parse built, beside its text ──────────
