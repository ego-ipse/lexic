"""The windows a reading offers — one builder per kind, on a table.

A window is what a fan entry opens. Which windows exist is a fact about
what a reading HAS, so this file is a table from kind to builder and
nothing else decides it: a kind with no row raises, and the drawing
boundary catches that and DRAWS the refusal rather than leaving a blank.

Nothing here builds a body until somebody opens it. A self-grammar's
predictive tables take fifty seconds to compile, and a page that built
every window eagerly would charge that to whoever loaded it.
"""

from __future__ import annotations

from typing import Callable

from lexic.compile import CompiledGrammar
from lexic.exceptions import UnsupportedConstructError
from lexic.ir import IrAst, IrDoc, IrFlavour, IrTokenizer
from lexic.model import GrammarModel
from lexic.parsing import lift_optional_nullables
from opsis.deixis.trees import tree_space
from opsis.kairos.constrain import sample
from opsis.opsis.draw.canvas import el
from opsis.opsis.draw.canvas import text as _text
from opsis.opsis.fan import OFFERS, fan, fanned, parts_of
from opsis.opsis.floor.lanes import lane_of, lane_view, transpile_view
from opsis.opsis.floor.panes import (
    analysis_pane,
    chart_pane,
    derivations_pane,
    execution_pane,
    floor_pane,
    forest_pane,
    resume_pane,
    segmentation_pane,
    tables_pane,
)
from opsis.opsis.pane import (
    CURSORS,
    RESUMES,
    SPELLABLE,
    WIDTHS,
    Pane,
    artefact,
    grammar_of,
)
from opsis.opsis.read.binding import binding_view, fold_view, runs_of
from opsis.opsis.read.emission import emit_doc
from opsis.opsis.read.parts import (
    bounded,
    button,
    chip,
    controls,
    refusal,
    row,
    section,
    stack,
)
from opsis.opsis.read.stages import module_view, pipeline_view
from opsis.opsis.read.tables import flavour_view, registry_view, table_view
from opsis.opsis.read.views import (
    binding_facts,
    carve_view,
    constrain_view,
    doc_view,
    instance_view,
    railroad_view,
    regrammar_view,
    rules_view,
    semantic_view,
    shadow_view,
    tokenizer_view,
)
from opsis.praxis.deeds.acts import Deed, deeds
from opsis.praxis.deeds.carve import bench
from opsis.praxis.reading import Reading
from opsis.praxis.session import Session, alphabets

__all__ = [
    "CURSORS",
    "PANES",
    "RESUMES",
    "Pane",
    "WIDTHS",
    "artefact",
    "fan",
    "lanes",
    "shadows",
    "window",
]


def _text_pane(session: Session, reading: Reading) -> Pane:
    """A reading's own text, editable."""
    return Pane(
        f"{reading.title} — its text", (480, 340), lambda: _editor(session, reading)
    )


def _instance_pane(_session: Session, reading: Reading) -> Pane:
    """What this reading built — whichever of its two readings there is.

    A flavour builds an AST and compiles it; a grammar builds a model.
    Showing the one that exists is the point; showing ``None`` because
    a reader offers no second reading was a window saying nothing.
    """
    built = reading.instance if reading.instance is not None else reading.product
    return Pane(
        f"{reading.title} — what it built",
        (760, 430),
        lambda: [instance_view(built, reading.text)],
    )


def _product_pane(_session: Session, reading: Reading) -> Pane:
    """Whatever came back, drawn by its own view."""
    return Pane(
        f"{reading.title} — product ▲",
        (760, 430),
        lambda: [instance_view(reading.product, reading.text)],
    )


def _vocabulary_pane(_session: Session, reading: Reading) -> Pane:
    """The vocabulary this reading produced."""
    vocab = IrTokenizer.ensure(reading.tokenizer, "a vocabulary")
    return Pane(
        f"{reading.title} — vocabulary ▲", (620, 380), lambda: [tokenizer_view(vocab)]
    )


def _bound_pane(_session: Session, reading: Reading) -> Pane:
    """The vocabulary this grammar is bound to."""
    compiled = grammar_of(reading)
    vocab = IrTokenizer.ensure(compiled.tokens.tokenizer, "a bound vocabulary")
    return Pane(
        f"{reading.title} — bound to {vocab.name}",
        (620, 380),
        lambda: [tokenizer_view(vocab)],
    )


def _reader_pane(session: Session, reading: Reading) -> Pane:
    """The grammar of whatever reads this one."""
    reader = session.reader_for(reading)
    grammar = reader.grammar if reader is not None else None
    name = reader.name if reader is not None else "?"
    body = (
        (lambda: [rules_view(grammar)])
        if grammar is not None
        else (lambda: [refusal("its reader has no grammar of its own")])
    )
    return Pane(f"{reading.title} — read by {name}", (660, 430), body)


def _rules_pane(_session: Session, reading: Reading) -> Pane:
    """This grammar's rules, by distance from the start."""
    grammar = grammar_of(reading).grammar
    return Pane(f"{reading.title} — rules", (680, 440), lambda: [rules_view(grammar)])


def _railroad_pane(_session: Session, reading: Reading) -> Pane:
    """Every rule's track, stacked."""
    grammar = grammar_of(reading).grammar
    return Pane(
        f"{reading.title} — railroad", (700, 460), lambda: [railroad_view(grammar)]
    )


def _module_pane(_session: Session, reading: Reading) -> Pane:
    """The importable twin this grammar would export."""
    compiled = grammar_of(reading)
    return Pane(
        f"{reading.title} — module",
        (700, 440),
        lambda: [module_view(compiled, _surface(compiled))],
    )


def _pipeline_pane(session: Session, reading: Reading) -> Pane:
    """The compile, stage by stage."""
    return Pane(
        f"{reading.title} — pipeline", (720, 440), lambda: [_pipeline(session, reading)]
    )


def _binding_pane(_session: Session, reading: Reading) -> Pane:
    """Where this grammar's classes and field names come from."""
    compiled = grammar_of(reading)
    return Pane(
        f"{reading.title} — binding", (660, 420), lambda: [binding_view(compiled)]
    )


def _fold_pane(_session: Session, reading: Reading) -> Pane:
    """How an instance of this grammar is built, field by field."""
    compiled = grammar_of(reading)
    return Pane(
        f"{reading.title} — its fold", (660, 420), lambda: [fold_view(compiled)]
    )


def _runs_pane(_session: Session, reading: Reading) -> Pane:
    """The lexical layer this grammar derives, and what it forecloses."""
    compiled = grammar_of(reading)
    return Pane(f"{reading.title} — its runs", (620, 340), lambda: [runs_of(compiled)])


def _space_pane(_session: Session, reading: Reading) -> Pane:
    """The same tree drawn as a space — where it went wide, where deep."""
    model = GrammarModel.ensure(reading.product, "a model")
    return Pane(
        f"{reading.title} — its shape",
        (760, 460),
        lambda: [tree_space(model)],
    )


def _semantic_pane(_session: Session, reading: Reading) -> Pane:
    """The same model with its noise dimmed — what it MEANS."""
    model = GrammarModel.ensure(reading.product, "a model")
    return Pane(
        f"{reading.title} — semantic ▲",
        (760, 430),
        lambda: [semantic_view(model, reading.text)],
    )


def _regrammar_pane(session: Session, reading: Reading) -> Pane:
    """This model, back as the grammar text that would read it.

    The arrow's other direction: grammar is the ground truth, and a
    model can say which grammar it is of. Written in the surface its
    own reader speaks, because that is the one it came from.
    """
    model = GrammarModel.ensure(reading.product, "a model")
    reader = session.reader_for(reading)
    flavour = _surface_of(session, reading)
    name = reader.name if reader is not None else "?"
    return Pane(
        f"{reading.title} — its grammar ▲ ({flavour})",
        (660, 430),
        lambda: [regrammar_view(model, flavour, name)],
    )


def _surface_of(session: Session, reading: Reading) -> str:
    """Which surface to spell a model's own grammar in."""
    above = session.readings.get(reading.reader)
    held = artefact(above) if above is not None else None
    return held.flavour if held is not None else "gbnf"


def _tokens_pane(_session: Session, reading: Reading) -> Pane:
    """What this grammar knows about tokens — bound, segments, unresolved."""
    compiled = grammar_of(reading)
    return Pane(
        f"{reading.title} — its token facts",
        (620, 340),
        lambda: [binding_facts(compiled)],
    )


def _doc_pane(_session: Session, reading: Reading) -> Pane:
    """The layout document an emission IS, at a width you can drag."""
    compiled = grammar_of(reading)
    width = WIDTHS.get(reading.ident, 88)
    doc = emit_doc(compiled.grammar, _spelling(compiled))
    return Pane(
        f"{reading.title} — its document",
        (640, 420),
        lambda: [doc_view(doc, width, f"this grammar in {_spelling(compiled)}")],
    )


def _spelling(compiled: CompiledGrammar) -> str:
    """Which surface this grammar's own emission is spelled in."""
    return compiled.flavour if compiled.flavour in SPELLABLE else "gbnf"


def shadows(session: Session, reading: Reading) -> list[Reading]:
    """Other readings whose product answers to this one's name.

    A flavour is named, and two flavours can be named the same thing —
    a manifest you wrote called ``gbnf`` beside the one lexic ships.
    Neither is refused: the session holds both, and each grammar names
    which one reads it. What is refused is pretending only one exists,
    so the collision is drawn.
    """
    flavour = reading.flavour
    if flavour is None:
        return []
    name = str(type(flavour).name)
    return [
        other
        for other in session.readings.values()
        if other.ident != reading.ident
        and other.flavour is not None
        and str(type(other.flavour).name) == name
    ]


def _shadow_pane(session: Session, reading: Reading) -> Pane:
    """Who else answers to this reading's name, and what reads with which."""
    flavour = IrFlavour.ensure(reading.flavour, "a flavour")
    name = str(type(flavour).name)
    held = [reading, *shadows(session, reading)]
    rows = tuple((one.title, _reads_with(session, one)) for one in held)
    return Pane(
        f"{reading.title} — it shadows ⚠",
        (600, 340),
        lambda: [shadow_view(name, rows)],
    )


def _reads_with(session: Session, reader: Reading) -> str:
    """What this particular reader is currently reading."""
    named = [r.title for r in session.readings.values() if r.reader == reader.ident]
    return ", ".join(named) if named else "nothing reads with it yet"


def _flavour_pane(_session: Session, reading: Reading) -> Pane:
    """A flavour as what it is — metadata and tables."""
    shown = IrFlavour.ensure(reading.flavour, "a flavour")
    return Pane(
        f"{reading.title} — what it IS", (660, 460), lambda: [flavour_view(shown)]
    )


def _dispatch_pane(_session: Session, reading: Reading) -> Pane:
    """Everything a flavour dispatches on."""
    carrier = IrFlavour.ensure(reading.flavour, "a flavour")
    return Pane(
        f"{reading.title} — its tables",
        (660, 460),
        lambda: [table_view(carrier, str(type(carrier).name))],
    )


def _carve_pane(session: Session, reading: Reading) -> Pane:
    """This grammar's template bench."""
    grammar_of(reading)
    return Pane(
        f"{reading.title} — template", (620, 420), lambda: [_carve(session, reading)]
    )


def _plug_pane(session: Session, reading: Reading) -> Pane:
    """What this reading needs bound, and what could be it."""
    return Pane(
        f"{reading.title} — plug ⊕", (520, 320), lambda: [_plug(session, reading)]
    )


def _registry_pane(_session: Session, reading: Reading) -> Pane:
    """The views registry — the coverage doctrine, looking at itself."""
    return Pane(
        f"{reading.title} — the registry", (620, 380), lambda: [registry_view()]
    )


def _constrain_pane(session: Session, reading: Reading) -> Pane:
    """The live constraint cursor for this grammar."""
    return Pane(
        f"{reading.title} — constrain",
        (560, 300),
        lambda: [_constrain(session, reading)],
    )


def lanes(session: Session, reading: Reading) -> list[Reading]:
    """Other grammars in the session this one could be a lane with.

    Any two grammars can be asked whether they are the same language —
    the answer is measured, so there is no need to guess which pairs are
    worth asking about.
    """
    if artefact(reading) is None:
        return []
    return [
        other
        for other in session.readings.values()
        if other.ident != reading.ident and artefact(other) is not None
    ]


def _transpile_pane(_session: Session, reading: Reading) -> Pane:
    """This grammar spelled in every other surface, and whether it holds."""
    compiled = grammar_of(reading)
    return Pane(
        f"{reading.title} — transpile",
        (720, 480),
        lambda: [transpile_view(compiled.grammar, compiled.flavour)],
    )


def _lanes_pane(session: Session, reading: Reading) -> Pane:
    """Whether the other grammars here are the same language as this one."""
    ours = grammar_of(reading).grammar
    found = tuple(
        (other.title, lane_of(ours, held.grammar))
        for other in lanes(session, reading)
        if (held := artefact(other)) is not None
    )
    return Pane(
        f"{reading.title} — its lanes ≅",
        (680, 420),
        lambda: (
            [lane_view(reading.title, name, lane) for name, lane in found]
            or [refusal("nothing else here is a grammar to compare with")]
        ),
    )


def _deed_pane(_session: Session, reading: Reading, name: str) -> Pane:
    """One of a reading's deeds, and the button that does it."""
    deed = next(d for d in deeds(reading) if d.name == name)
    return Pane(
        f"{reading.title} — {deed.label}", (480, 200), lambda: [_deed(reading, deed)]
    )


PANES: dict[str, Callable[[Session, Reading], Pane]] = {
    "text": _text_pane,
    "instance": _instance_pane,
    "product": _product_pane,
    "vocabulary": _vocabulary_pane,
    "bound": _bound_pane,
    "reader": _reader_pane,
    "rules": _rules_pane,
    "railroad": _railroad_pane,
    "module": _module_pane,
    "pipeline": _pipeline_pane,
    "tables": tables_pane,
    "binding": _binding_pane,
    "fold": _fold_pane,
    "runs": _runs_pane,
    "analysis": analysis_pane,
    "tokens": _tokens_pane,
    "resume": resume_pane,
    "doc": _doc_pane,
    "space": _space_pane,
    "semantic": _semantic_pane,
    "regrammar": _regrammar_pane,
    "flavour": _flavour_pane,
    "shadow": _shadow_pane,
    "dispatch": _dispatch_pane,
    "carve": _carve_pane,
    "plug": _plug_pane,
    "registry": _registry_pane,
    "floor": floor_pane,
    "forest": forest_pane,
    "derivations": derivations_pane,
    "chart": chart_pane,
    "execution": execution_pane,
    "segmentation": segmentation_pane,
    "lanes": _lanes_pane,
    "transpile": _transpile_pane,
}
"""Fan kind → the window it opens.

Open and table-driven, like every other consumer here: a kind with no
row raises, the drawing boundary catches that and DRAWS it, so a gap is
a visible refusal rather than a silent blank. A cascade of eighteen
returns is what this replaced.
"""


SIZES: dict[str, tuple[int, int]] = {
    "text": (480, 340),
    "shape": (720, 480),
    "built": (780, 460),
    "parse": (720, 480),
    "compile": (740, 480),
    "tokens": (660, 420),
    "bench": (640, 440),
    "meta": (680, 440),
    "do": (520, 300),
}
"""How big each window opens — bigger than one part needs, because a
window holds several and people open two of them at once."""


def _shell(session: Session, reading: Reading, kind: str) -> Pane:
    """A window as its parts, each opening when it is wanted.

    A window that built everything at once would be unreadable and
    expensive — several of these cost a compile — so a part is a
    heading and an empty slot until somebody expands it.
    """
    label = next((o.label for o in OFFERS if o.kind == kind), kind)
    title = f"{reading.title} — {label}"
    if kind == "text":
        return Pane(title, SIZES["text"], lambda: _editor(session, reading))
    if kind == "do":
        return Pane(title, SIZES["do"], lambda: [_deeds(reading)])
    inside = parts_of(fanned(session, reading), kind)
    if not inside:
        return Pane(
            title,
            SIZES[kind],
            lambda: [refusal(f"{reading.title} has no {label} to show")],
        )
    return Pane(
        title,
        SIZES[kind],
        lambda: [
            section(part.label, f"{reading.ident}/{part.kind}", part.why, shown=i == 0)
            for i, part in enumerate(inside)
        ],
    )


def _deeds(reading: Reading) -> IrDoc:
    """Everything this reading can do, each with the button that does it."""
    found = deeds(reading)
    if not found:
        return refusal(f"{reading.title} has nothing to do")
    return stack(
        [
            row(
                deed.label,
                el("div", {"class": "note"}, _text(deed.why)),
                controls(button(deed.label, f"/do/{reading.ident}/{deed.name}")),
            )
            for deed in found
        ]
    )


def window(session: Session, reading: Reading, kind: str) -> Pane:
    """The window a moon opens, or the part a section fills.

    One function for both, because they are the same question asked at
    two depths: a window is a shell of sections, and a section is one
    of the bodies this table has always built.

    :raises UnsupportedConstructError: When nothing knows that kind —
        which the caller draws rather than swallows.
    """
    if kind in SIZES:
        return _shell(session, reading, kind)
    if kind.startswith("do:"):
        name = kind.removeprefix("do:")
        if name == "constrain":
            return _constrain_pane(session, reading)
        return _deed_pane(session, reading, name)
    build = PANES.get(kind)
    if build is None:
        raise UnsupportedConstructError(f"no window for {kind!r}")
    return build(session, reading)


def _carve(session: Session, reading: Reading) -> IrDoc:
    """This grammar's template bench, over whichever text it last read.

    The document is a reading below this one — templating extracts from
    a DOCUMENT, and the documents this grammar has are the readings it
    reads.
    """
    held = bench(reading.ident)
    below = session.readers_of(reading.ident)
    doc = next((r.title for r in below if r.text), "")
    note = held.result.note + (f" · over {doc}" if doc else " · nothing under it yet")
    return carve_view(reading.ident, held.shape, held.spec, held.result.paths, note)


def _plug(session: Session, reading: Reading) -> IrDoc:
    """What this reading needs bound, and everything that could be it.

    Dragging one node onto another is the gesture; this is the same
    gesture said in words, for the case where the two nodes are a
    screen apart. It lists only vocabularies that exist in the session,
    and says so plainly when there are none.
    """
    wants = _wants(reading)
    have = [r for r in session.readings.values() if r.tokenizer is not None]
    bound = session.readings.get(reading.params.bound)
    rows: list[IrDoc] = [
        el(
            "div",
            {"class": "note"},
            _text(
                f"this grammar reads its terminals under "
                f"{', '.join(wants)} — bind a vocabulary under that name"
            ),
        ),
        el(
            "div",
            {"class": "claim ok" if bound else "claim no"},
            _text(f"bound to {bound.title}" if bound else "nothing bound yet"),
            el("em", None, _text(reading.error[:90] if reading.error else "")),
        ),
    ]
    if not have:
        rows.append(
            el(
                "div",
                {"class": "note"},
                "no vocabulary is open — open a tokenizer.json from the "
                "bar and it appears here",
            )
        )
    rows.extend(
        el(
            "div",
            {"class": "controls"},
            el("span", {"class": "name"}, _text(str(r.tokenizer.name))),
            el(
                "span", {"class": "note"}, _text(f"{len(r.tokenizer.encode):,} entries")
            ),
            el(
                "button",
                {"class": "go", "data-do": f"/drop/{r.ident}/{reading.ident}"},
                "bind",
            ),
        )
        for r in have
        if r.tokenizer is not None
    )
    if bound is not None:
        rows.append(controls(button("unbind", f"/drop//{reading.ident}")))
    return el("div", None, *rows)


def _constrain(session: Session, reading: Reading) -> IrDoc:
    """The live cursor for this reading, at whatever prefix it is at."""
    at = CURSORS.of(session, reading.ident)
    admitted = at.mask()
    return constrain_view(
        reading.ident,
        at.text,
        sample(admitted, at.vocabulary),
        len(admitted),
        at.accepts(),
    )


def _deed(reading: Reading, deed: Deed) -> IrDoc:
    """A deed, as the sentence it is and the button that does it."""
    return el(
        "div",
        None,
        el("div", {"class": "note"}, _text(deed.why)),
        el(
            "div",
            {"class": "controls"},
            el(
                "button",
                {"class": "go", "data-do": f"/do/{reading.ident}/{deed.name}"},
                _text(deed.label),
            ),
        ),
    )


def _surface(compiled: CompiledGrammar) -> str:
    """Which surface a module is spelled in when the grammar names none."""
    return compiled.flavour if compiled.flavour in SPELLABLE else "gbnf"


def _pipeline(session: Session, reading: Reading) -> IrDoc:
    """The compile's stages for this reading."""
    compiled = grammar_of(reading)
    parsed = session.instance_of(reading)
    concretized = (
        compiled.codegen_grammar if compiled.tokens.tokenizer is not None else None
    )
    return pipeline_view(
        (
            (
                "parsed",
                parsed if isinstance(parsed, IrAst) else None,
                "what the reader's own reduction built",
            ),
            (
                "canonical",
                compiled.grammar,
                "names folded, shape normalised — what the grammar IS",
            ),
            ("concretized", concretized, "alphabets resolved against a vocabulary"),
            (
                "codegen",
                compiled.codegen_grammar,
                "groups and arms hoisted, noise relaxed — what binds to classes",
            ),
            (
                "lifted",
                lift_optional_nullables(compiled.codegen_grammar),
                "nullables lifted — the shape the engine walks",
            ),
        )
    )


def _editor(session: Session, reading: Reading) -> list[IrDoc]:
    """A reading's own text, its chips, and what refused."""
    body: list[IrDoc] = []
    reader = session.reader_for(reading)
    if reader is not None and reader.kind in ("flavour", "notation", "module"):
        off = not reader.comments
        body.append(
            el(
                "div",
                {"class": "controls"},
                chip(
                    "@start",
                    f"c-start-{reading.ident}",
                    reading.params.directives.start or "",
                    "first rule",
                    off,
                ),
                chip(
                    "@non-semantic",
                    f"c-ns-{reading.ident}",
                    ",".join(
                        sorted(reading.params.directives.non_semantic or frozenset())
                    ),
                    "ws,sp",
                    off,
                ),
            )
        )
        body.append(
            el(
                "div",
                {"class": "note"},
                "this reader has no comment form, so directives ride the "
                "argument channel — the chips still apply"
                if off
                else "the @directives, as arguments — they key the compile",
            )
        )
    shown, note = bounded(reading.text)
    if note:
        body.append(el("div", {"class": "note"}, f"{note} · read-only here"))
        body.append(el("pre", {"class": "src"}, shown))
    else:
        body.append(
            el(
                "textarea",
                {
                    "id": f"t-{reading.ident}",
                    "spellcheck": "false",
                    "data-post": f"/text/{reading.ident}",
                },
                reading.text,
            )
        )
        body.append(
            el(
                "div",
                {"class": "controls"},
                el(
                    "span",
                    {"class": "note"},
                    "reads as you type · every edit cascades downward",
                ),
            )
        )
    if reading.error:
        body.append(refusal(reading.error))
    if not reading.reader:
        body.append(
            el(
                "div",
                {"class": "note"},
                "nothing reads this yet — drop it on a reader, or drop a reader on it",
            )
        )
    return body


def _under(session: Session, reading: Reading) -> CompiledGrammar | None:
    """The grammar that read this text, whatever kind of reading held it.

    The floor is about a PARSE, and every reading with something above
    it was parsed — a grammar read by a flavour was parsed by that
    flavour's own self-grammar, exactly as a document is parsed by the
    grammar above IT. Asking the layer above what it IS, rather than
    whether it happens to be a compiled artefact, is what stops that
    from being two different situations.
    """
    return fanned(session, reading).read_by


def _wants(reading: Reading) -> list[str]:
    """The encoding names this reading asks to be read under, unmet or not.

    A grammar that names an encoding needs a vocabulary bound under that
    name before it can be read at all — so the plug affordance exists
    exactly where the grammar itself says it does.
    """
    return alphabets(reading.instance)
