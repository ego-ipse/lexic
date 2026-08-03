"""The engine floor — what actually happens when a text is read.

Below the rungs everyone looks at there is a parse, and it is made of
things: a compiled predictive program, a shared packed forest, islands
where the predictive half hands back to Earley, and — where a text
means more than one thing — several derivations rather than one.

Nothing here re-parses a text to make a claim about it. Every count is
measured off the artefacts the engines actually produced, and a claim
that could not be measured is drawn as unmeasured rather than assumed.
"""

from __future__ import annotations

from lexic.compile import CompiledGrammar
from lexic.exceptions import LexicError
from lexic.ir import IrAst, IrDoc, IrSelf
from lexic.parsing import (
    derivations,
    earley_model,
    is_ambiguous,
    lift_optional_nullables,
    normalize,
    recognize,
)
from opsis.opsis.canvas import el
from opsis.opsis.canvas import text as _text
from opsis.opsis.views import Node, bounded, graph, refusal

__all__ = ["derivation_view", "floor_view", "forest_view", "tables_view"]

_ARMS = 60
"""How many forest nodes one space draws before it states the rest."""

_WALKED: dict[int, IrAst] = {}
"""Engine grammar per codegen grammar identity — the same memo key the
engine uses, so the floor measures what the parse actually ran on."""


def walked(compiled: CompiledGrammar) -> IrAst:
    """The grammar the engine actually walks — lifted, then normalised.

    Not the codegen grammar and not the canonical one: handing Earley
    either would measure a parse that never happens. The lift is not a
    formality — an unlifted json text derives sixteen thousand ways and
    a lifted one derives once.
    """
    key = id(compiled.codegen_grammar)
    if key not in _WALKED:
        _WALKED[key] = normalize(lift_optional_nullables(compiled.codegen_grammar))
    return _WALKED[key]


def _claim(what: str, ok: bool | None, detail: str) -> IrDoc:
    """One measured claim — true, false, or honestly unmeasured."""
    mark = {True: "✓", False: "✗", None: "—"}[ok]
    hue = {True: "ok", False: "no", None: "un"}[ok]
    return el(
        "div",
        {"class": f"claim {hue}"},
        _text(f"{what} {mark}"),
        el("em", None, _text(detail)),
    )


def floor_view(compiled: CompiledGrammar, text: str) -> IrDoc:
    """Both engines on one text, and whether they say the same thing.

    The agreement claim is the one that matters: the predictive runtime
    and Earley are two answers to one question, and a floor that only
    showed one of them would be hiding the interesting case.
    """
    grammar = walked(compiled)
    return el(
        "div",
        None,
        _recognized(grammar, text),
        _ambiguity(grammar, text),
        _lift(compiled, text),
        _agreement(compiled, text),
    )


def _lift(compiled: CompiledGrammar, text: str) -> IrDoc:
    """What the nullable lift is worth, on this very text.

    Measured both ways rather than asserted: the unlifted grammar is
    parsed too, and the two derivation counts are the claim.
    """
    try:
        bare = len(derivations(normalize(compiled.codegen_grammar), text))
        lifted = len(derivations(walked(compiled), text))
    except LexicError as exc:
        return _claim("the lift settles it", None, str(exc)[:120])
    return _claim(
        "the lift settles it",
        lifted < bare or bare == lifted == 1,
        f"{bare:,} derivations unlifted · {lifted:,} lifted",
    )


def _recognized(grammar: IrAst, text: str) -> IrDoc:
    """Whether Earley recognises the text at all."""
    try:
        return _claim(
            "recognized",
            bool(int(recognize(grammar, text))),
            f"{len(text):,} characters",
        )
    except LexicError as exc:
        return _claim("recognized", None, str(exc)[:120])


def _ambiguity(grammar: IrAst, text: str) -> IrDoc:
    """Whether the text derives more than one way, and how many."""
    try:
        many = bool(int(is_ambiguous(grammar, text)))
        count = len(derivations(grammar, text)) if many else 1
        return _claim(
            "unambiguous" if not many else "ambiguous",
            not many,
            f"{count} derivation{'s' if count != 1 else ''}",
        )
    except LexicError as exc:
        return _claim("unambiguous", None, str(exc)[:120])


def _agreement(compiled: CompiledGrammar, text: str) -> IrDoc:
    """Whether the two engines build the same model of this text.

    Both are driven directly rather than through the artefact's own
    entry, because the point is to compare them — asking the artefact
    would get whichever one it chose.
    """
    try:
        fused = compiled.parse(text)
        classic = earley_model(walked(compiled), text, compiled.fold)
    except LexicError as exc:
        return _claim("the engines agree", None, str(exc)[:140])
    same = fused == classic and fused.to_text() == classic.to_text()
    return _claim(
        "the engines agree",
        same,
        f"predictive {type(fused).__name__} · earley {type(classic).__name__}",
    )


def tables_view(compiled: CompiledGrammar) -> IrDoc:
    """The predictive artefact — what was compiled, and where it escapes.

    An island is where the predictive half cannot decide and hands the
    span to Earley. Their count is the honest measure of how predictive
    this grammar actually is, so it is stated whether or not it is zero.
    """
    try:
        tables = compiled.pda_tables()
    except LexicError as exc:
        return refusal(f"{type(exc).__name__}: {exc}")
    islands = sorted(str(name) for name in tables.islands)
    delegates = sum(len(tables.island_delegates(name)) for name in islands)
    rows = [
        ("clones", f"{len(tables.clones):,}", "one per decision context"),
        ("delegates", f"{delegates:,}", "per-island interior parsers"),
        ("islands", f"{len(islands):,}", "spans handed back to Earley"),
        ("start", str(tables.start_key.name), "where the program enters"),
    ]
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
        _island_list(islands),
    )


def _island_list(islands: list[str]) -> IrDoc:
    """Which rules escape, named — or the statement that none do."""
    if not islands:
        return el(
            "div",
            {"class": "note"},
            "no islands: this grammar is predictive all the way down",
        )
    shown = islands[:_ARMS]
    rest = f" (of {len(islands):,})" if len(islands) > _ARMS else ""
    return el(
        "div",
        {"class": "row"},
        el("span", {"class": "name"}, "where"),
        el("pre", {"class": "src"}, _text(", ".join(shown) + rest)),
    )


def forest_view(compiled: CompiledGrammar, text: str) -> IrDoc:
    """The forest — every derivation at once, shared where they share.

    The packing is the point: two derivations of one text agree about
    most of it, and a node drawn once for a span that both reach is
    what "shared packed" MEANS. Where they disagree, the space forks,
    and that fork is the ambiguity.
    """
    try:
        trees = derivations(walked(compiled), text)
    except LexicError as exc:
        return refusal(f"{type(exc).__name__}: {exc}")
    if not trees:
        return refusal("no derivation: this text is not in the language")
    nodes, edges, total = _packed(list(trees))
    head = el(
        "div",
        {"class": "note"},
        _text(
            f"{len(trees)} derivation{'s' if len(trees) != 1 else ''} packed into "
            f"{total:,} distinct nodes"
            + (f" — {len(nodes)} drawn" if total > len(nodes) else "")
        ),
    )
    return el("div", None, head, graph(nodes, edges))


def _packed(trees: list[IrSelf]) -> tuple[list[Node], list[tuple[int, int]], int]:
    """Every derivation merged — one node per distinct symbol-and-shape.

    Merging by the node's own value is what shares them: two derivations
    that built the same subtree built an equal one, and the spine's
    equality is structural, so equal subtrees ARE one node here.
    """
    at: dict[IrSelf, int] = {}
    nodes: list[Node] = []
    edges: set[tuple[int, int]] = set()
    depth: dict[IrSelf, int] = {}
    queue: list[tuple[IrSelf, int]] = [(t, 0) for t in trees]
    order: dict[int, int] = {}
    while queue:
        here, level = queue.pop(0)
        if here not in at:
            depth[here] = level
            at[here] = len(at)
        for kid in here.children():
            if kid not in at:
                queue.append((kid, level + 1))
    for node, index in sorted(at.items(), key=lambda kv: (depth[kv[0]], kv[1])):
        if len(nodes) >= _ARMS:
            break
        order[index] = len(nodes)
        nodes.append(
            Node(
                f"p{len(nodes)}",
                _label(node),
                depth[node],
                len(nodes),
                _hue(node),
                _label(node),
            )
        )
    for node, index in at.items():
        for kid in node.children():
            pair = (order.get(index), order.get(at.get(kid, -1)))
            if pair[0] is not None and pair[1] is not None:
                edges.add((pair[0], pair[1]))
    return nodes, sorted(edges), len(at)


def _hue(node: IrSelf) -> str:
    """What a forest node is: a leaf, or a symbol that was expanded."""
    return "cyan" if list(node.children()) else "green"


def _label(node: IrSelf) -> str:
    """A forest node as the symbol it stands for."""
    symbol = getattr(node, "symbol", None)
    if symbol is not None:
        return str(symbol)
    shown, _note = bounded(str(node), 40)
    return shown.replace("\n", " ")


def derivation_view(compiled: CompiledGrammar, text: str) -> IrDoc:
    """Every way this text derives — the ambiguity, spelled out.

    One derivation is the ordinary case and is drawn as such. More than
    one is what a resolver is FOR, so the window says how many there are
    and what each one is, rather than picking.
    """
    try:
        found = derivations(walked(compiled), text)
    except LexicError as exc:
        return refusal(f"{type(exc).__name__}: {exc}")
    rows = [
        el(
            "div",
            {"class": "row"},
            el("span", {"class": "name"}, _text(f"#{i + 1}")),
            el("pre", {"class": "src"}, _text(bounded(str(one), 600)[0])),
        )
        for i, one in enumerate(found)
    ]
    head = el(
        "div",
        {"class": "note"},
        _text(
            f"{len(found)} derivation{'s' if len(found) != 1 else ''} — "
            + (
                "the text means one thing"
                if len(found) == 1
                else "a resolver chooses, or the read refuses"
            )
        ),
    )
    return el("div", None, head, *rows)
