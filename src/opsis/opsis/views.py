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

from lexic.compile import CompiledGrammar
from lexic.exceptions import LexicError, UnsupportedConstructError
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
from opsis.opsis.canvas import text as _text
from opsis.opsis.graphic import RAIL_CSS, rule_svg

__all__ = [
    "BIG",
    "VIEWS",
    "binding_facts",
    "bounded",
    "button",
    "carve_view",
    "controls",
    "field",
    "facts",
    "panel",
    "constrain_view",
    "graph",
    "instance_view",
    "railroad_view",
    "refusal",
    "regrammar_view",
    "resume_view",
    "rules_view",
    "semantic_view",
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


# ── a vocabulary is a size and a pipeline ─────────────────────────────


def binding_facts(compiled: CompiledGrammar) -> IrDoc:
    """What a grammar knows about tokens — three facts, not one state.

    Bound and segmented are separate questions, and conflating them is
    what breaks additivity: a char grammar can carry a vocabulary for
    generation and still parse as a char grammar. So the socket says
    both, and says what a rebind would start from.
    """
    tokens = compiled.tokens
    bound = tokens.tokenizer
    rows = [
        (
            "bound",
            str(bound.name) if bound is not None else "nothing",
            f"{len(bound.encode):,} entries"
            if bound is not None
            else "no vocabulary is docked",
        ),
        (
            "segments",
            "yes" if tokens.segmented else "no",
            "its terminals name an encoding, so its input is segmented"
            if tokens.segmented
            else "its terminals are characters — a docked vocabulary does not "
            "change that",
        ),
        (
            "unresolved",
            "kept" if tokens.unresolved is not None else "none",
            "the pre-resolution grammar a rebind re-concretizes; resolution is "
            "lossy, so a rebind cannot start from the codegen grammar",
        ),
    ]
    return facts(
        rows,
        el(
            "div",
            {"class": "claim ok" if not _mismatch(tokens) else "claim no"},
            _text(_additivity(tokens)),
        ),
    )


def _mismatch(tokens: object) -> bool:
    """Whether the docked vocabulary and the grammar disagree about tokens."""
    return bool(getattr(tokens, "segmented", False)) and (
        getattr(tokens, "tokenizer", None) is None
    )


def _additivity(tokens: object) -> str:
    """The additivity invariant, said for this particular grammar."""
    bound = getattr(tokens, "tokenizer", None) is not None
    segments = bool(getattr(tokens, "segmented", False))
    if segments and not bound:
        return (
            "this grammar names an encoding but nothing is bound — it cannot "
            "be read until a vocabulary is"
        )
    if segments:
        return "a token grammar with its vocabulary — its terminals ARE ids"
    if bound:
        return (
            "a char grammar carrying a vocabulary: it still parses as a char "
            "grammar, and the vocabulary is there for generation"
        )
    return "a char grammar, reading characters"


def resume_view(ident: str, held: object) -> IrDoc:
    """A chart that is still growing: what has arrived, and where to return to.

    Marks are TEMPORAL — points in this session's history, not offsets
    in a document — so they are listed in the order they were taken and
    rolling back to one drops the ones after it.
    """
    text = str(getattr(held, "text", ""))
    marks = list(getattr(held, "marks", ()))
    runs = list(getattr(held, "runs", ()))
    accepting = bool(getattr(held, "accepting", False))
    rows: list[IrDoc] = [
        el(
            "div",
            {"class": "row"},
            el("span", {"class": "name"}, "so far"),
            el("pre", {"class": "src"}, _text(text or "· nothing yet ·")),
        ),
        el(
            "div",
            {"class": "claim ok" if accepting else "claim no"},
            _text(
                "a whole string ✓"
                if accepting
                else "not a whole string yet — the chart is open"
            ),
        ),
    ]
    if runs:
        rows.append(
            el(
                "div",
                {"class": "note"},
                _text(
                    f"{len(runs)} rule{'s' if len(runs) != 1 else ''} could be collapsed "
                    f"into run terminals ({', '.join(str(r) for r in runs[:4])}). This "
                    "chart runs on PLAIN tables so it can grow — a collapsed one could "
                    "not, because a run has already consumed past where you are."
                ),
            )
        )
    rows.append(
        controls(
            field(f"ext-{ident}", "more text", push=ident),
            button("extend", f"/extend/{ident}"),
            button("mark", f"/mark/{ident}"),
        )
    )
    rows.extend(
        el(
            "div",
            {"class": "cell"},
            el("code", None, _text(f"mark {mark.at}")),
            el("span", None, _text(repr(mark.text)[:60])),
            button("back to here", f"/rewind/{ident}/{mark.at}"),
        )
        for mark in marks
    )
    return el("div", None, *rows)


def semantic_view(model: GrammarModel, source: str) -> IrDoc:
    """The model with its noise dimmed — the same tree, read for meaning.

    Not a filtered tree: every node is still there and still points at
    its span, because what counts as noise is the grammar's judgement
    and hiding it would be opsis making that judgement instead.
    """
    rows, _deepest, _n = _model_rows(model)
    kept, whole = len(model.semantic_dump()), len(model.dump())
    return el(
        "div",
        None,
        el(
            "div",
            {"class": "note"},
            _text(
                f"semantic · {kept} meaningful of {whole} top-level parts — "
                "noise dimmed, never removed: what counts as noise is the "
                "grammar's judgement, not this window's"
            ),
        ),
        _twin(source, el("div", {"class": "semantic"}, *rows)),
    )


def regrammar_view(model: GrammarModel, flavour: str, reader: str) -> IrDoc:
    """A model as the grammar text that would read it.

    Grammar is the ground truth and a class is its representation, so
    this direction is the one that has to hold: any model can say which
    grammar it is of, losslessly, in a named surface.
    """
    try:
        text = str(model.to_grammar(flavour))
    except LexicError as exc:
        return refusal(f"{type(exc).__name__}: {exc}")
    shown, note = bounded(text)
    return el(
        "div",
        None,
        el(
            "div",
            {"class": "note"},
            _text(
                f"{len(text.splitlines())} line{'s' if len(text.splitlines()) != 1 else ''} "
                f"in {flavour} · what {reader} would "
                f"read back as this very model{' · ' + note if note else ''}"
            ),
        ),
        el("pre", {"class": "src"}, shown),
    )


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
