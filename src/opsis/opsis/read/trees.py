"""A grammar as a graph, and a reading as the tree it built.

Two shapes for two questions. A grammar is a graph of rules laid out by
distance from the start, so the columns ARE the depth. A reading is a
tree beside the text it came from, and hovering a row lights the span
it covers — the pointing that makes a parse legible.

Every row carries the rule it came from, so the same hover reaches the
grammar node too: one attribute, one listener, both directions.
"""

from __future__ import annotations

from typing import NamedTuple

from lexic.ir import IrAst, IrDoc, IrSelf
from lexic.model import GrammarModel
from opsis.eidolon import Topology
from opsis.opsis.draw.canvas import el, raw
from opsis.opsis.draw.graphic import RAIL_CSS, rule_svg
from opsis.opsis.read.parts import Node, bounded, graph

__all__ = [
    "Twig",
    "instance_view",
    "model_rows",
    "railroad_view",
    "rules_view",
    "twin",
]

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
    stack: list[tuple[GrammarModel, int, str, int]] = [(root, 0, "0", 0)]
    while stack:
        model, depth, path, start = stack.pop()
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
        stack.extend(reversed(placed))
    return rows, len(rows), deepest


def _ir_rows(root: IrSelf) -> tuple[list[IrDoc], int, int]:
    """Any IR product as a tree — what the reducer built, node by node."""
    rows: list[IrDoc] = []
    deepest = 0
    stack: list[tuple[IrSelf, int, str]] = [(root, 0, "0")]
    while stack:
        node, depth, path = stack.pop()
        deepest = max(deepest, depth)
        kids = list(node.children())
        shown = str(node) if isinstance(node, str) else repr(node)
        rows.append(_row(Twig(path, depth, type(node).__name__, shown, bool(kids))))
        for i, kid in enumerate(reversed(kids)):
            stack.append((kid, depth + 1, f"{path}.{len(kids) - 1 - i}"))
    return rows, len(rows), deepest


def _plain_rows(root: object) -> tuple[list[IrDoc], int, int]:
    """Plain data as a tree — dicts, lists and scalars, named for what they are."""
    rows: list[IrDoc] = []
    deepest = 0
    stack: list[tuple[object, int, str, str]] = [(root, 0, "0", "")]
    while stack:
        value, depth, path, key = stack.pop()
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
            stack.append((kid, depth + 1, f"{path}.{len(kids) - 1 - i}", kid_key))
    return rows, len(rows), deepest
