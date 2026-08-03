"""Views — a product becomes a window body, in the shape that product has.

A reading is not a blob of text with a label. A grammar is a GRAPH of
rules; an instance is the TREE its parse built, beside the text it
covers; a vocabulary is a size and a pipeline; plain data is data. Each
gets the shape it actually has, because giving two different products
the same shape is how a window stops saying anything.

The table is open with a raising default, and the raise is caught at
the drawing boundary and DRAWN — a product opsis cannot show is a
visible refusal, never an empty window.
"""

from __future__ import annotations

from typing import NamedTuple, Sequence

from lexic.compile import CompiledGrammar, export_source
from lexic.exceptions import UnsupportedConstructError
from lexic.grammars import get_flavour
from lexic.ir import (
    IrAction,
    IrAst,
    IrDoc,
    IrLeaf,
    IrRule,
    IrSelf,
    IrTokenizer,
    IrTypeMap,
)
from lexic.model import GrammarModel
from opsis.eidolon import Topology
from opsis.opsis.canvas import el, raw
from opsis.opsis.graphic import RAIL_CSS, rule_svg

__all__ = [
    "BIG",
    "VIEWS",
    "bounded",
    "carve_view",
    "constrain_view",
    "graph",
    "instance_view",
    "module_view",
    "pipeline_view",
    "railroad_view",
    "refusal",
    "rules_view",
    "view_of",
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
    if isinstance(product, IrTokenizer):
        return _twin(source, tokenizer_view(product))
    if isinstance(product, GrammarModel):
        rows, count, deep = _model_rows(product)
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
    return _twin(
        source,
        el(
            "div",
            None,
            el("div", {"class": "note"}, note),
            el("div", {"class": "tree"}, *rows),
        ),
    )


def _twin(source: str, right: IrDoc) -> IrDoc:
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


def _row(
    path: str,
    depth: int,
    label: str,
    text: str,
    kids: bool,
    rule: str,
    span: tuple[int, int] | None = None,
) -> IrDoc:
    """One row of a tree: its twig, its name, what it stands for."""
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


def _model_rows(root: GrammarModel) -> tuple[list[IrDoc], int, int]:
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
                path,
                depth,
                type(model).__name__,
                text,
                bool(kids),
                str(model.__grammar__.name),
                (start, start + len(text)),
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
        rows.append(_row(path, depth, type(node).__name__, shown, bool(kids), ""))
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
        rows.append(_row(path, depth, label, shown, bool(kids), ""))
        for i, (kid, kid_key) in enumerate(reversed(kids)):
            stack.append((kid, depth + 1, f"{path}.{len(kids) - 1 - i}", kid_key))
    return rows, len(rows), deepest


# ── a vocabulary is a size and a pipeline ─────────────────────────────


def tokenizer_view(tok: IrTokenizer) -> IrDoc:
    """What a tokenizer IS: its size, its stages, a look at its entries.

    A vocabulary of a hundred thousand entries is not drawn entry by
    entry — the count is stated and a sample is shown, which is the
    scale rule: no silent caps, and no pretending the rest is absent.
    """
    stages = list(tok.pipeline)
    entries = list(tok.encode.items())[:40]
    sample = ", ".join(f"{str(text)!r}={int(ident)}" for text, ident in entries)
    return el(
        "div",
        None,
        el(
            "div",
            {"class": "row"},
            el("span", {"class": "name"}, str(tok.name)),
            el(
                "div",
                {"class": "note"},
                f"{len(tok.encode):,} entries · {len(tok.ranks):,} merge ranks · "
                f"segmented by {type(tok.segmenter).__name__}",
            ),
        ),
        el(
            "div",
            {"class": "row"},
            el("span", {"class": "name"}, f"pipeline · {len(stages)} stages"),
            el(
                "div",
                {"class": "note"},
                " → ".join(type(stage).__name__ for stage in stages) or "none",
            ),
        ),
        el(
            "div",
            {"class": "row"},
            el("span", {"class": "name"}, "vocabulary"),
            el(
                "div",
                {"class": "note"},
                f"the first {len(entries)} of {len(tok.encode):,}",
            ),
            el("pre", {"class": "src"}, sample),
        ),
    )


def constrain_view(
    ident: str, spelled: str, admitted: str, count: int, whole: bool
) -> IrDoc:
    """The cursor at its prefix — what is spelled, and what may come next.

    Every claim on it is measured: whether the prefix is a whole string
    is what the cursor answers, not what the shape of the text suggests.
    """
    return el(
        "div",
        None,
        el(
            "div",
            {"class": "row"},
            el("span", {"class": "name"}, "prefix"),
            el("pre", {"class": "src"}, spelled or "· nothing pushed yet ·"),
        ),
        el(
            "div",
            {"class": "row"},
            el("span", {"class": "name"}, f"admits {count:,}"),
            el("div", {"class": "note"}, admitted),
        ),
        el(
            "div",
            {"class": "claim ok" if whole else "claim no"},
            "a whole string ✓" if whole else "not a whole string yet",
        ),
        el(
            "div",
            {"class": "controls"},
            el(
                "input",
                {
                    "id": f"push-{ident}",
                    "placeholder": "a token, spelled",
                    "spellcheck": "false",
                    "data-push": ident,
                },
            ),
            el("button", {"class": "go", "data-do": f"/push/{ident}"}, "push"),
            el("button", {"class": "go", "data-do": f"/back/{ident}"}, "back"),
            el("button", {"class": "go", "data-do": f"/reset/{ident}"}, "reset"),
        ),
    )


def carve_view(ident: str, shape: str, spec: str, rows, note: str) -> IrDoc:
    """The template editor — the shape, the paths, and what came out."""
    return el(
        "div",
        None,
        el(
            "div",
            {"class": "row"},
            el("span", {"class": "name"}, "shape"),
            el(
                "input",
                {
                    "id": f"sh-{ident}",
                    "value": shape,
                    "spellcheck": "false",
                    "placeholder": "section, entry, key, value",
                },
            ),
        ),
        el(
            "div",
            {"class": "note"},
            "which of this grammar's rules make one mapping level — the "
            "section, one entry, and the entry's key and value fields",
        ),
        el(
            "div",
            {"class": "row"},
            el("span", {"class": "name"}, "keep"),
            el(
                "textarea",
                {
                    "id": f"sp-{ident}",
                    "spellcheck": "false",
                    "placeholder": "one dotted path per line",
                },
                spec,
            ),
        ),
        el(
            "div",
            {"class": "controls"},
            el("button", {"class": "go", "data-do": f"/carve/{ident}"}, "extract"),
            el("span", {"class": "note"}, note),
        ),
        *(
            el(
                "div",
                {"class": "cell"},
                el("code", None, path),
                el("span", None, value),
            )
            for path, value in rows
        ),
    )


# ── the compile, stage by stage ───────────────────────────────────────


def pipeline_view(stages: Sequence[tuple[str, IrAst | None, str]]) -> IrDoc:
    """The compile as stages, each opening what IT changed.

    A stage is a diff, not a dump: what it added, what it rewrote shown
    before and after, and how much it left alone. A stage that does not
    occur in this compile is drawn as the absence it is.
    """
    nodes: list[Node] = []
    edges: list[tuple[int, int]] = []
    details: list[IrDoc] = []
    before: IrAst | None = None
    before_name = ""
    for column, (name, ast, why) in enumerate(stages):
        if ast is None:
            nodes.append(
                Node(
                    f"st-{name}",
                    f"{name} · not here",
                    column,
                    0,
                    "dim",
                    "",
                    f"st-{name}",
                )
            )
            details.append(_stage(name, why, [], [], 0, before_name))
        else:
            added, changed = _diff(before, ast)
            mark = f"{name} · {len(list(ast.rules))} rules"
            if before is not None:
                mark += f" · +{len(added)} ~{len(changed)}"
            hue = (
                "amber"
                if before is None
                else ("green" if not (added or changed) else "cyan")
            )
            nodes.append(Node(f"st-{name}", mark, column, 0, hue, "", f"st-{name}"))
            details.append(
                _stage(
                    name,
                    why,
                    added,
                    changed,
                    len(list(ast.rules)) - len(added) - len(changed),
                    before_name,
                )
            )
            before, before_name = ast, name
        if column:
            edges.append((column - 1, column))
    return el(
        "div",
        None,
        el(
            "div",
            {"class": "note"},
            "each stage is what the one before it became · +added ~rewritten",
        ),
        graph(nodes, edges),
        *details,
    )


def _diff(
    before: IrAst | None, after: IrAst
) -> tuple[list[tuple[str, str]], list[tuple[str, str, str]]]:
    """Which rules a stage added, and which it rewrote — with their text."""
    if before is None:
        return [], []
    spell = get_flavour("gbnf")
    was = {str(rule.name): rule for rule in before.rules}
    added: list[tuple[str, str]] = []
    changed: list[tuple[str, str, str]] = []
    for rule in after.rules:
        name = str(rule.name)
        older = was.get(name)
        if older is None:
            added.append((name, str(spell.apply(rule, None))))
        elif repr(older.body) != repr(rule.body):
            changed.append(
                (name, str(spell.apply(older, None)), str(spell.apply(rule, None)))
            )
    return added, changed


def _stage(
    name: str,
    why: str,
    added: list[tuple[str, str]],
    changed: list[tuple[str, str, str]],
    untouched: int,
    before: str,
) -> IrDoc:
    """One stage's own window — what it did, rule by rule."""
    from opsis.opsis.space import frame

    rows: list[IrDoc] = [el("div", {"class": "note"}, why)]
    if not before:
        rows.append(
            el("div", {"class": "note"}, "the first stage — nothing precedes it")
        )
    elif not added and not changed:
        rows.append(el("div", {"class": "note"}, f"changed nothing from {before}"))
    for rule, source in added:
        rows.append(
            el(
                "div",
                {"class": "row added"},
                el("span", {"class": "name", "data-rule": rule}, f"+ {rule}"),
                el("pre", {"class": "src"}, source),
            )
        )
    for rule, was, now in changed:
        rows.append(
            el(
                "div",
                {"class": "row changed"},
                el("span", {"class": "name", "data-rule": rule}, f"~ {rule}"),
                el("pre", {"class": "src was"}, was),
                el("pre", {"class": "src"}, now),
            )
        )
    if untouched and before:
        rows.append(el("div", {"class": "note"}, f"{untouched} rules untouched"))
    return frame(
        f"st-{name}",
        f"{name} — what it changed",
        24,
        76,
        560,
        270,
        *rows,
        shown=False,
        sub=True,
    )


def module_view(compiled: CompiledGrammar, surface: str) -> IrDoc:
    """The importable twin this grammar would export.

    The grammar is the ground truth; a module is one way of writing it
    down, and its docstrings must be spelled in SOME surface. A grammar
    born from IR names none of its own, so one is chosen and said out
    loud — nothing is recompiled for it, only the label the exporter
    spells with.
    """
    from dataclasses import replace

    artefact = compiled
    note = f"what export_module writes for {compiled.flavour}"
    if compiled.flavour != surface:
        artefact = replace(compiled, flavour=surface)
        note = (
            f"this grammar came from {compiled.flavour}, which spells no "
            f"surface of its own — its module is written out in {surface}"
        )
    source = export_source(artefact)
    return el(
        "div",
        None,
        el(
            "div",
            {"class": "note"},
            f"{len(source.splitlines())} lines · {note} · "
            "derived from the grammar, never the other way round",
        ),
        el("pre", {"class": "src"}, source),
    )


# ── the registry: a product with no view is a DRAWN refusal ───────────


class GrammarView(IrLeaf[IrSelf, IrSelf]):
    """A grammar met as a product — its rules, as a graph."""

    def eval(self, _d: IrSelf, n: IrSelf, _nc: Sequence[IrSelf], /) -> IrSelf:
        return rules_view(IrAst.ensure(n, "views: a grammar"))


class ModelView(IrLeaf[IrSelf, IrSelf]):
    """A model met on its own — its text and its tree."""

    def eval(self, _d: IrSelf, n: IrSelf, _nc: Sequence[IrSelf], /) -> IrSelf:
        model = GrammarModel.ensure(n, "views: a model")
        return instance_view(model, model.to_text())


class TokenizerView(IrLeaf[IrSelf, IrSelf]):
    """A vocabulary met on its own."""

    def eval(self, _d: IrSelf, n: IrSelf, _nc: Sequence[IrSelf], /) -> IrSelf:
        return tokenizer_view(IrTokenizer.ensure(n, "views: a tokenizer"))


VIEWS: IrTypeMap = IrTypeMap(
    IrAction(IrAst, GrammarView()),
    IrAction(GrammarModel, ModelView()),
    IrAction(IrTokenizer, TokenizerView()),
)
"""The registry — open, concrete-first via MRO, raising default."""


def view_of(product: IrSelf) -> IrDoc:
    """A product's body — its view, or the drawn refusal.

    The raising default is the coverage doctrine's runtime form: the
    raise is caught HERE and drawn with its real message, so a gap is a
    visible defect rather than an empty window.
    """
    try:
        return IrDoc.ensure(VIEWS.eval(VIEWS, product, ()), "views: a body")
    except UnsupportedConstructError as exc:
        return refusal(f"{type(exc).__name__}: {exc}")


def rule_of(ast: IrAst, name: str) -> IrRule | None:
    """One rule by name, for a window that wants only that one."""
    return next((r for r in ast.rules if str(r.name) == name), None)
