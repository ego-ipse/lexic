"""The pieces every window is built from.

One shape per job: a note over rows, a grid of cells, a titled block, a
row of named measurements, a control, a drawn refusal — and the node
space every graph in this instrument is laid out in. Written once so
that two windows showing the same kind of thing look the same, which is
the only reason anybody can read the second one quickly.
"""

from __future__ import annotations

from typing import NamedTuple, Sequence

from lexic.ir import IrDoc
from opsis.opsis.draw.canvas import el
from opsis.opsis.draw.canvas import text as _text

__all__ = [
    "BIG",
    "Node",
    "bounded",
    "button",
    "chip",
    "controls",
    "facts",
    "field",
    "graph",
    "grid",
    "panel",
    "refusal",
    "titled",
]

BIG = 60_000
"""Beyond this many characters a text is windowed, and says so."""

_COL = 200
_ROW = 30


def bounded(text: str, limit: int = BIG) -> tuple[str, str]:
    """A text the DOM can hold, and the honest note about the rest.

    No silent caps: the true size is stated, and so is how much of it
    is on screen.
    """
    if len(text) <= limit:
        return text, ""
    return (
        text[:limit],
        f"{len(text):,} characters · showing the first {limit:,} — "
        "the rest is on disk, not hidden",
    )


def button(label: str, does: str) -> IrDoc:
    """One control that does one thing, and says which."""
    return el("button", {"class": "go", "data-do": does}, _text(label))


def controls(*parts: IrDoc) -> IrDoc:
    """A row of controls — the one shape every window's affordances take."""
    return el("div", {"class": "controls"}, *parts)


def field(ident: str, empty: str, push: str = "") -> IrDoc:
    """A small editable datum a control reads when it fires."""
    attrs: dict[str, str | None] = {
        "id": ident,
        "spellcheck": "false",
        "placeholder": empty,
    }
    if push:
        attrs["data-push"] = push
    return el("input", attrs)


def grid(rows: Sequence[tuple[str, str]]) -> IrDoc:
    """A scrolling grid of key/value cells — the one shape a listing takes."""
    return el(
        "div",
        {"class": "grid"},
        *(
            el(
                "div",
                {"class": "cell"},
                el("code", None, _text(key)),
                el("span", None, _text(value)),
            )
            for key, value in rows
        ),
    )


def titled(name: str, measure: str, why: str, *body: IrDoc) -> IrDoc:
    """A named block: what it is, how much of it, and why — then itself."""
    return el(
        "div",
        {"class": "table"},
        el(
            "div",
            {"class": "row"},
            el("span", {"class": "name"}, _text(name)),
            el("b", None, _text(measure)),
            el("div", {"class": "note"}, _text(why)),
        ),
        *body,
    )


def chip(label: str, ident: str, value: str, empty: str, off: bool = False) -> IrDoc:
    """A small editable datum, labelled — a directive, a resolver, a name.

    A chip that cannot apply is drawn OFF rather than hidden: an
    unavailable control is a stated fact about the reader, and hiding
    it would make the reason unavailable too.
    """
    return el(
        "span",
        {"class": "chip off" if off else "chip"},
        _text(label),
        el(
            "input",
            {
                "id": ident,
                "value": value,
                "placeholder": empty,
                "spellcheck": "false",
                "data-post": "chip",
            },
        ),
    )


def panel(note: str, *rows: IrDoc) -> IrDoc:
    """A body that opens by saying what it is, then shows it.

    Every window here has the same shape — a sentence, then the thing —
    so it is written once.
    """
    return el("div", None, el("div", {"class": "note"}, _text(note)), *rows)


def facts(rows: Sequence[tuple[str, str, str]], *rest: IrDoc) -> IrDoc:
    """Named measurements, one per line: what, how much, and why."""
    return el(
        "div",
        None,
        *(
            el(
                "div",
                {"class": "row"},
                el("span", {"class": "name"}, _text(name)),
                el("b", None, _text(value)),
                el("div", {"class": "note"}, _text(why)),
            )
            for name, value, why in rows
        ),
        *rest,
    )


def refusal(message: str) -> IrDoc:
    """A drawn refusal — the real message, in the register's err voice."""
    return el("div", {"class": "refusal"}, message)


# ── a node space: what every graph in a window is drawn as ────────────


class Node(NamedTuple):
    """One node of a drawn graph: where it sits and what it says."""

    ident: str
    label: str
    column: int
    row: int
    hue: str = "cyan"
    rule: str = ""
    opens: str = ""


def graph(nodes: Sequence[Node], edges: Sequence[tuple[int, int]]) -> IrDoc:
    """A graph as a node space — edges beneath, nodes over them.

    Rows are barycentred first: each node drifts toward the average row
    of what names it, which is the difference between a graph and a
    thicket.
    """
    if not nodes:
        return el("div", {"class": "note"}, "nothing to draw")
    placed = _barycentre(list(nodes), list(edges))
    width = 26 + max(n.column for n in placed) * _COL + 250
    height = 22 + max(n.row for n in placed) * _ROW + 40
    wires = el(
        "svg",
        {"class": "gwires", "width": str(width), "height": str(height)},
        *(_edge(placed[a], placed[b]) for a, b in edges),
    )
    drawn: list[IrDoc] = []
    for node in placed:
        x, y = 26 + node.column * _COL, 22 + node.row * _ROW
        attrs: dict[str, str | None] = {
            "class": f"gnode v-{node.hue}",
            "style": f"left:{x}px;top:{y}px",
        }
        if node.rule:
            attrs["data-rule"] = node.rule
        if node.opens:
            attrs["data-open"] = node.opens
        drawn.append(el("div", attrs, el("i", None), node.label))
    return el(
        "div",
        {"class": "gspace", "style": f"width:{width}px;height:{height}px"},
        wires,
        *drawn,
    )


def _barycentre(nodes: list[Node], edges: list[tuple[int, int]]) -> list[Node]:
    """Two sweeps toward the average row of each node's namers."""
    incoming: dict[int, list[int]] = {i: [] for i in range(len(nodes))}
    for a, b in edges:
        incoming[b].append(a)
    rows = {i: float(n.row) for i, n in enumerate(nodes)}
    for _sweep in range(2):
        for i in range(len(nodes)):
            namers = incoming[i]
            if namers:
                rows[i] = sum(rows[p] for p in namers) / len(namers)
        columns: dict[int, list[int]] = {}
        for i, node in enumerate(nodes):
            columns.setdefault(node.column, []).append(i)
        for members in columns.values():
            for slot, i in enumerate(sorted(members, key=lambda j: rows[j])):
                rows[i] = float(slot)
    return [n._replace(row=int(rows[i])) for i, n in enumerate(nodes)]


def _edge(a: Node, b: Node) -> IrDoc:
    """One edge — a flat cubic, so columns read left to right."""
    x1, y1 = 26 + a.column * _COL + 8, 22 + a.row * _ROW
    x2, y2 = 26 + b.column * _COL - 8, 22 + b.row * _ROW
    return el(
        "path",
        {"class": "gedge", "d": f"M{x1},{y1} C{x1 + 48},{y1} {x2 - 48},{y2} {x2},{y2}"},
    )
