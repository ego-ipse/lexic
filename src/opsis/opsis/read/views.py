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

from typing import Sequence

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
    render,
)
from lexic.model import GrammarModel
from opsis.deixis.trees import instance_view, model_rows, twin
from opsis.opsis.draw.canvas import el
from opsis.opsis.draw.canvas import text as _text
from opsis.opsis.read.parts import (
    BIG,
    Node,
    bounded,
    button,
    controls,
    facts,
    field,
    graph,
    grid,
    panel,
    refusal,
    titled,
)
from opsis.opsis.read.trees import railroad_view, rules_view

__all__ = [
    "BIG",
    "VIEWS",
    "binding_facts",
    "bounded",
    "button",
    "carve_view",
    "controls",
    "doc_view",
    "field",
    "grid",
    "facts",
    "panel",
    "constrain_view",
    "graph",
    "instance_view",
    "railroad_view",
    "refusal",
    "regrammar_view",
    "resume_view",
    "shadow_view",
    "titled",
    "rules_view",
    "semantic_view",
    "view_of",
]

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


def doc_view(doc: IrDoc, width: int, what: str) -> IrDoc:
    """A layout document, rendered live at a width you can drag.

    Emission is not string concatenation here: a document is a tree of
    width-aware combinators, and what it looks like is a function of the
    width it is given. So the width is a control rather than a constant,
    and this window is where it lives.
    """
    shown, note = bounded(render(doc, width))
    return el(
        "div",
        None,
        el(
            "div",
            {"class": "note"},
            _text(
                f"{what} · rendered at {width} columns{' · ' + note if note else ''}"
            ),
        ),
        controls(
            el(
                "input",
                {
                    "id": "width",
                    "type": "range",
                    "min": "20",
                    "max": "200",
                    "value": str(width),
                    "data-width": "1",
                },
            ),
            el("span", {"class": "note"}, _text(f"{width}")),
        ),
        el("pre", {"class": "src ruled", "style": f"--cols:{width}"}, _text(shown)),
    )


def shadow_view(name: str, rows: Sequence[tuple[str, str]]) -> IrDoc:
    """Two readers answering to one name, and who reads with which.

    Not refused, and not resolved behind anyone's back: a name is how a
    flavour is spoken about, not what it IS, so the session holds both
    and every grammar names the reading that reads it. What would be
    wrong is a registry silently picking.
    """
    return panel(
        f"{len(rows)} readings produce a flavour called {name!r} — nothing is "
        "shadowed away: each grammar names the one that reads it, and a name is "
        "how a flavour is spoken about, not what it is",
        grid(rows),
    )


def semantic_view(model: GrammarModel, source: str) -> IrDoc:
    """The model with its noise dimmed — the same tree, read for meaning.

    Not a filtered tree: every node is still there and still points at
    its span, because what counts as noise is the grammar's judgement
    and hiding it would be opsis making that judgement instead.
    """
    rows, _deepest, _n = model_rows(model)
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
        twin(source, el("div", {"class": "semantic"}, *rows)),
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
    """What a tokenizer IS: its size, its stages as a space, its entries.

    The pipeline is drawn as the chain it is — normalize, pretoken,
    segment — because the stages are ordered and each one hands its
    output to the next. A vocabulary of a hundred thousand entries is
    not drawn entry by entry: the count is stated and a sample shown,
    which is the scale rule.
    """
    stages = list(tok.pipeline)
    entries = list(tok.encode.items())[:40]
    sample = ", ".join(f"{str(text)!r}={int(ident)}" for text, ident in entries)
    return el(
        "div",
        None,
        facts(
            [
                ("name", str(tok.name), f"{len(tok.encode):,} entries"),
                (
                    "merges",
                    f"{len(tok.ranks):,} ranks",
                    f"segmented by {type(tok.segmenter).__name__}",
                ),
                ("pipeline", f"{len(stages)} stages", "each one hands its output on"),
            ]
        ),
        _stage_space(stages, type(tok.segmenter).__name__),
        el(
            "div",
            {"class": "row"},
            el("span", {"class": "name"}, "vocabulary"),
            el(
                "div",
                {"class": "note"},
                _text(f"the first {len(entries)} of {len(tok.encode):,}"),
            ),
            el("pre", {"class": "src"}, _text(sample)),
        ),
    )


def _stage_space(stages: Sequence[object], segmenter: str) -> IrDoc:
    """The token pipeline as a chain — text in one end, ids out the other."""
    names = [type(stage).__name__ for stage in stages] + [segmenter]
    nodes = [
        Node(f"tp{i}", name, i, 0, "magenta" if i == len(names) - 1 else "cyan")
        for i, name in enumerate(names)
    ]
    edges = [(i, i + 1) for i in range(len(names) - 1)]
    return graph(nodes, edges)


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
