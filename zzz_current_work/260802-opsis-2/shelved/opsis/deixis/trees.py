"""Deixis — pointing: a reading beside its text, each half naming the other.

A parse is legible when you can see which characters a node covers.
Every row here carries the span it came from and the rule that built
it, so ONE hover reaches three places: the row, the text under it, and
the grammar node above. That is the whole mechanism — one attribute,
one listener, no bookkeeping.

The spans are not guessed. A model's text is its children's texts in
order, which is the round-trip invariant, so walking in order gives
them exactly. What a reducer built covers no span at all, and says so
rather than pretending.
"""

from __future__ import annotations

from typing import NamedTuple

from opsis.opsis.draw.canvas import el
from opsis.opsis.read.parts import (
    Node,
    bounded,
    graph,
    panel,
    refusal,
)

from lexic.ir import IrDoc, IrSelf
from lexic.model import GrammarModel

__all__ = ["Twig", "instance_view", "model_rows", "tree_space", "twin"]


def instance_view(product: object, source: str) -> IrDoc:
    """A reading, as the text it read and what it built — side by side.

    Hovering a node lights the span of text it covers. The spans are
    not guessed: a model's text is its children's texts in order, which
    is the round-trip invariant, so walking in order gives them exactly.
    A product that covers no span says so rather than pretending.
    """
    if isinstance(product, GrammarModel):
        rows, count, deep = model_rows(product)
        note = f"{count} models · {deep + 1} deep · hover a node for its text"
    elif isinstance(product, IrSelf):
        rows, count, deep = _ir_rows(product)
        note = (
            f"{count} IR nodes · {deep + 1} deep · "
            "what a reducer BUILT covers no span of the input"
        )
    else:
        rows, count, deep = _plain_rows(product)
        note = f"{count} values · {deep + 1} deep · plain data, no lexic types"
    return twin(
        source,
        el(
            "div",
            None,
            el("div", {"class": "note"}, note),
            el("div", {"class": "tree"}, *rows),
        ),
    )


def twin(source: str, right: IrDoc) -> IrDoc:
    """The two panes: what was read, and what it became."""
    shown, note = bounded(source)
    return el(
        "div",
        {"class": "twin"},
        el(
            "div",
            {"class": "pane left"},
            el("div", {"class": "note"}, note or "the text it was read from"),
            el("pre", {"class": "src target"}, shown),
        ),
        el("div", {"class": "pane"}, right),
    )


class Twig(NamedTuple):
    """One row of a drawn tree — where it sits and what it stands for."""

    path: str
    depth: int
    label: str
    text: str = ""
    kids: bool = False
    rule: str = ""
    span: tuple[int, int] | None = None


def _row(twig: Twig) -> IrDoc:
    """One row of a tree: its twig, its name, what it stands for."""
    path, depth, label = twig.path, twig.depth, twig.label
    text, kids, rule, span = twig.text, twig.kids, twig.rule, twig.span
    shut = kids and depth >= 1
    classes = "twig" + (" kids" if kids else "") + (" shut" if shut else "")
    attrs: dict[str, str | None] = {
        "class": classes + (" hide" if depth > 1 else ""),
        "data-path": path,
        "style": f"padding-left:{depth * 15}px",
    }
    if span is not None:
        attrs["data-from"] = str(span[0])
        attrs["data-to"] = str(span[1])
    name: dict[str, str | None] = {"class": "name"}
    if rule:
        name["data-rule"] = rule
    preview = text if len(text) <= 56 else text[:53] + "…"
    return el(
        "div",
        attrs,
        el("b", None, ("▸" if shut else "▾") if kids else "·"),
        el("span", name, label),
        el("span", {"class": "txt"}, preview),
    )


def _model_kids(model: GrammarModel) -> list[GrammarModel]:
    """Every model this one holds, tuples flattened.

    A ``models``-mode field holds a TUPLE of models; dropping those
    would draw a parse with its repetitions cut out, which is not the
    parse that happened.
    """
    out: list[GrammarModel] = []
    for kid in model.children():
        if isinstance(kid, GrammarModel):
            out.append(kid)
        elif isinstance(kid, tuple):
            out.extend(v for v in kid if isinstance(v, GrammarModel))
    return out


def model_rows(root: GrammarModel) -> tuple[list[IrDoc], int, int]:
    """The parse as rows, each knowing the span of text it covers."""
    rows: list[IrDoc] = []
    deepest = 0
    pending: list[tuple[GrammarModel, int, str, int]] = [(root, 0, "0", 0)]
    while pending:
        model, depth, path, start = pending.pop()
        deepest = max(deepest, depth)
        kids = _model_kids(model)
        text = model.to_text()
        rows.append(
            _row(
                Twig(
                    path,
                    depth,
                    type(model).__name__,
                    text,
                    bool(kids),
                    str(model.__grammar__.name),
                    (start, start + len(text)),
                )
            )
        )
        cursor = start
        placed: list[tuple[GrammarModel, int, str, int]] = []
        for i, kid in enumerate(kids):
            placed.append((kid, depth + 1, f"{path}.{i}", cursor))
            cursor += len(kid.to_text())
        pending.extend(reversed(placed))
    return rows, len(rows), deepest


def _ir_rows(root: IrSelf) -> tuple[list[IrDoc], int, int]:
    """Any IR product as a tree — what the reducer built, node by node."""
    rows: list[IrDoc] = []
    deepest = 0
    pending: list[tuple[IrSelf, int, str]] = [(root, 0, "0")]
    while pending:
        node, depth, path = pending.pop()
        deepest = max(deepest, depth)
        kids = list(node.children())
        shown = str(node) if isinstance(node, str) else repr(node)
        rows.append(_row(Twig(path, depth, type(node).__name__, shown, bool(kids))))
        for i, kid in enumerate(reversed(kids)):
            pending.append((kid, depth + 1, f"{path}.{len(kids) - 1 - i}"))
    return rows, len(rows), deepest


def _plain_rows(root: object) -> tuple[list[IrDoc], int, int]:
    """Plain data as a tree — dicts, lists and scalars, named for what they are."""
    rows: list[IrDoc] = []
    deepest = 0
    pending: list[tuple[object, int, str, str]] = [(root, 0, "0", "")]
    while pending:
        value, depth, path, key = pending.pop()
        deepest = max(deepest, depth)
        if isinstance(value, dict):
            kids: list[tuple[object, str]] = [(v, str(k)) for k, v in value.items()]
            shown = f"{{{len(value)}}}"
        elif isinstance(value, (list, tuple)):
            kids = [(v, str(i)) for i, v in enumerate(value)]
            shown = f"[{len(value)}]"
        else:
            kids, shown = [], repr(value)
        label = f"{key} · {type(value).__name__}" if key else type(value).__name__
        rows.append(_row(Twig(path, depth, label, shown, bool(kids))))
        for i, (kid, kid_key) in enumerate(reversed(kids)):
            pending.append((kid, depth + 1, f"{path}.{len(kids) - 1 - i}", kid_key))
    return rows, len(rows), deepest


def tree_space(root: GrammarModel) -> IrDoc:
    """A parse as the tree it IS — nodes and edges, not indented rows.

    Rows are better for reading a span: they stack, they scroll, and a
    long text stays legible. A space is better for reading a SHAPE —
    where a grammar went wide, where it went deep, which arm carried
    the weight. Both are the same tree, so both are offered rather than
    one replacing the other.

    Depth is the column and document order is the row, which makes the
    drawing left-to-right exactly as the text reads.
    """
    into = _Space([], [])
    _walk(root, (0, 0), into, -1)
    nodes, edges = into.nodes, into.edges
    if not nodes:
        return refusal("this reading built nothing to draw")
    return panel(
        f"{len(nodes)} nodes · {max(n.column for n in nodes) + 1} deep · "
        "column is depth, row is document order",
        graph(nodes, edges),
    )


class _Space(NamedTuple):
    """What a tree walk is filling in — the space, and where it is."""

    nodes: list[Node]
    edges: list[tuple[int, int]]


def _walk(node: GrammarModel, at: tuple[int, int], into: _Space, parent: int) -> int:
    """One node into the space, then its children — in document order.

    :param at: ``(depth, row)`` — the column this node sits in, and the
        first row free for it.
    :returns: The next free row, so a sibling starts below this whole
        subtree rather than on top of it.
    """
    depth, start = at
    if len(into.nodes) >= _SPACE:
        return start
    here = len(into.nodes)
    into.nodes.append(
        Node(
            f"n{here}",
            type(node).__name__,
            depth,
            start,
            "cyan" if _model_kids(node) else "green",
            str(node.__grammar__.name),
            "",
        )
    )
    if parent >= 0:
        into.edges.append((parent, here))
    row = start
    for kid in _model_kids(node):
        row = _walk(kid, (depth + 1, row), into, here)
    return max(row, start + 1)


_SPACE = 240
"""How many nodes one tree space draws before it stops.

Stated in the note above it rather than silently: a tree bigger than
this is still a tree, and the rows view still shows all of it.
"""
