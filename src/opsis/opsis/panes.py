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

from typing import Callable, NamedTuple

from lexic.compile import CompiledGrammar
from lexic.exceptions import UnsupportedConstructError
from lexic.ir import IrAst, IrDoc, IrFlavour, IrTokenizer
from lexic.model import GrammarModel
from lexic.parsing import lift_optional_nullables
from opsis.opsis.analysis import analysis_view
from opsis.opsis.binding import binding_view, fold_view, runs_of
from opsis.opsis.canvas import el
from opsis.opsis.canvas import text as _text
from opsis.opsis.chart import chart_view, segmentation_view
from opsis.opsis.emission import emit_doc
from opsis.opsis.engine import (
    derivation_view,
    floor_view,
    forest_view,
    tables_view,
)
from opsis.opsis.lanes import lane_of, lane_view
from opsis.opsis.stages import module_view, pipeline_view
from opsis.opsis.tables import flavour_view, registry_view, table_view
from opsis.opsis.views import (
    binding_facts,
    bounded,
    button,
    carve_view,
    constrain_view,
    controls,
    doc_view,
    instance_view,
    railroad_view,
    refusal,
    regrammar_view,
    resume_view,
    rules_view,
    semantic_view,
    shadow_view,
    tokenizer_view,
)
from opsis.praxis.acts import Deed, deeds
from opsis.praxis.carve import bench
from opsis.praxis.constrain import Cursors, sample
from opsis.praxis.reading import Reading, self_compiled
from opsis.praxis.resume import Resumes
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


def artefact(reading: Reading) -> CompiledGrammar | None:
    """The grammar this reading IS, however it came to be one.

    A grammar reading compiled one; a flavour reading carries one — its
    own self-grammar, which is a grammar like any other and gets the
    same windows. That equivalence is the meta ladder, and it is one
    function rather than a special case in each of them.
    """
    if reading.compiled is not None:
        return reading.compiled
    return self_compiled(reading.flavour) if reading.flavour is not None else None


def fan(session: Session, reading: Reading) -> list[tuple[str, str]]:
    """The readings this one actually has — nothing offered that isn't."""
    out = [("text", "text")]
    out += _grammar_fan(reading)
    out += _product_fan(reading)
    reader = session.reader_for(reading)
    if reader is not None and reader.grammar is not None:
        out.append(("reader", "its reader"))
    out += [(f"do:{deed.name}", deed.label) for deed in deeds(reading)]
    if reader is not None and reader.of and _under(session, reading) is not None:
        out += [
            ("floor", "the floor"),
            ("forest", "forest"),
            ("derivations", "derivations"),
            ("chart", "its chart"),
        ]
        if _segments(session, reading) is not None:
            out.append(("segmentation", "its tokens ▲"))
    if reading.flavour is not None:
        out += [("flavour", "what it IS"), ("dispatch", "its tables")]
    if shadows(session, reading):
        out.append(("shadow", "it shadows ⚠"))
    if lanes(session, reading):
        out.append(("lanes", "its lanes ≅"))
    if not reading.reader:
        out.append(("registry", "the registry"))
    if _wants(reading):
        out.append(("plug", "plug ⊕"))
    return out


def _grammar_fan(reading: Reading) -> list[tuple[str, str]]:
    """Everything a reading offers because it IS a grammar."""
    held = artefact(reading)
    if held is None:
        return []
    out = [
        ("rules", "rules"),
        ("railroad", "railroad"),
        ("pipeline", "pipeline"),
        ("module", "module"),
        ("doc", "its document"),
        ("tables", "its tables"),
        ("binding", "binding"),
        ("fold", "its fold"),
        ("runs", "its runs"),
        ("analysis", "its verdicts"),
        ("tokens", "its token facts"),
        ("resume", "resume"),
        ("carve", "template"),
    ]
    if held.tokens.tokenizer is not None:
        out.append(("bound", "bound to ▲"))
    return out


def _product_fan(reading: Reading) -> list[tuple[str, str]]:
    """Everything a reading offers because of what it PRODUCED."""
    out: list[tuple[str, str]] = []
    if reading.tokenizer is not None:
        out.append(("vocabulary", "vocabulary ▲"))
    if reading.instance is not None:
        out.append(("instance", "instance ▲"))
    if reading.product is not None and reading.compiled is None:
        out.append(("product", "product ▲"))
    if isinstance(reading.product, GrammarModel):
        out += [("semantic", "semantic ▲"), ("regrammar", "its grammar ▲")]
    return out


RESUMES = Resumes()
"""Every reading's growing chart — dropped when its grammar re-reads."""

CURSORS = Cursors()
"""Every reading's constraint cursor — thrown away when it re-reads."""

_SPELLABLE = ("gbnf", "abnf", "ebnf")
"""Surfaces the exporter can spell a module's docstrings in."""


class Pane(NamedTuple):
    """One window: what it is called, how big, and how to build it."""

    title: str
    size: tuple[int, int]
    build: Callable[[], list[IrDoc]]


def _text_pane(session: Session, reading: Reading) -> Pane:
    """A reading's own text, editable."""
    return Pane(
        f"{reading.title} — its text", (480, 340), lambda: _editor(session, reading)
    )


def _instance_pane(session: Session, reading: Reading) -> Pane:
    """The other reading of this text."""
    return Pane(
        f"{reading.title} — instance ▲",
        (760, 430),
        lambda: [instance_view(session.instance_of(reading), reading.text)],
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
    compiled = _grammar(reading)
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
    grammar = _grammar(reading).grammar
    return Pane(f"{reading.title} — rules", (680, 440), lambda: [rules_view(grammar)])


def _railroad_pane(_session: Session, reading: Reading) -> Pane:
    """Every rule's track, stacked."""
    grammar = _grammar(reading).grammar
    return Pane(
        f"{reading.title} — railroad", (700, 460), lambda: [railroad_view(grammar)]
    )


def _module_pane(_session: Session, reading: Reading) -> Pane:
    """The importable twin this grammar would export."""
    compiled = _grammar(reading)
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
    compiled = _grammar(reading)
    return Pane(
        f"{reading.title} — binding", (660, 420), lambda: [binding_view(compiled)]
    )


def _fold_pane(_session: Session, reading: Reading) -> Pane:
    """How an instance of this grammar is built, field by field."""
    compiled = _grammar(reading)
    return Pane(
        f"{reading.title} — its fold", (660, 420), lambda: [fold_view(compiled)]
    )


def _runs_pane(_session: Session, reading: Reading) -> Pane:
    """The lexical layer this grammar derives, and what it forecloses."""
    compiled = _grammar(reading)
    return Pane(f"{reading.title} — its runs", (620, 340), lambda: [runs_of(compiled)])


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


def _analysis_pane(_session: Session, reading: Reading) -> Pane:
    """Every decision the predictive analysis settled, in its own words."""
    compiled = _grammar(reading)
    return Pane(
        f"{reading.title} — its verdicts", (660, 420), lambda: [analysis_view(compiled)]
    )


def _tokens_pane(_session: Session, reading: Reading) -> Pane:
    """What this grammar knows about tokens — bound, segments, unresolved."""
    compiled = _grammar(reading)
    return Pane(
        f"{reading.title} — its token facts",
        (620, 340),
        lambda: [binding_facts(compiled)],
    )


def _resume_pane(_session: Session, reading: Reading) -> Pane:
    """The growing chart, its marks, and what it accepts so far."""
    held = RESUMES.of(reading)
    return Pane(
        f"{reading.title} — resume",
        (600, 380),
        lambda: [resume_view(reading.ident, held)],
    )


WIDTHS: dict[str, int] = {}
"""The width each reading's document window is rendered at."""


def _doc_pane(_session: Session, reading: Reading) -> Pane:
    """The layout document an emission IS, at a width you can drag."""
    compiled = _grammar(reading)
    width = WIDTHS.get(reading.ident, 88)
    doc = emit_doc(compiled.grammar, _spelling(compiled))
    return Pane(
        f"{reading.title} — its document",
        (640, 420),
        lambda: [doc_view(doc, width, f"this grammar in {_spelling(compiled)}")],
    )


def _spelling(compiled: CompiledGrammar) -> str:
    """Which surface this grammar's own emission is spelled in."""
    return compiled.flavour if compiled.flavour in _SPELLABLE else "gbnf"


def _tables_pane(_session: Session, reading: Reading) -> Pane:
    """The predictive artefact this grammar compiled to."""
    compiled = _grammar(reading)
    return Pane(
        f"{reading.title} — its tables", (640, 380), lambda: [tables_view(compiled)]
    )


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
    _grammar(reading)
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


def _segments(session: Session, reading: Reading) -> IrTokenizer | None:
    """The vocabulary this text is cut by, when it is read as tokens."""
    under = _under(session, reading)
    if under is None or not under.tokens.segmented:
        return None
    return under.tokens.tokenizer


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


def _lanes_pane(session: Session, reading: Reading) -> Pane:
    """Whether the other grammars here are the same language as this one."""
    ours = _grammar(reading).grammar
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


def _chart_pane(session: Session, reading: Reading) -> Pane:
    """The Earley chart this text fills, column by column."""
    under = _read_by(session, reading)
    text = reading.text
    return Pane(
        f"{reading.title} — its chart", (700, 460), lambda: [chart_view(under, text)]
    )


def _segmentation_pane(session: Session, reading: Reading) -> Pane:
    """Where this text was cut into tokens, and into which ids."""
    vocab = _segments(session, reading)
    if vocab is None:
        raise UnsupportedConstructError(f"{reading.title} is not read as tokens")
    text = reading.text
    return Pane(
        f"{reading.title} — its tokens ▲",
        (640, 420),
        lambda: [segmentation_view(vocab, text)],
    )


def _floor_pane(session: Session, reading: Reading) -> Pane:
    """Both engines on this text, and whether they agree."""
    under = _read_by(session, reading)
    text = reading.text
    return Pane(
        f"{reading.title} — floor",
        (640, 380),
        lambda: [floor_view(under, text), _resolver(reading)],
    )


def _forest_pane(session: Session, reading: Reading) -> Pane:
    """The forest this text derives."""
    under = _read_by(session, reading)
    text = reading.text
    return Pane(
        f"{reading.title} — forest", (700, 460), lambda: [forest_view(under, text)]
    )


def _derivations_pane(session: Session, reading: Reading) -> Pane:
    """Every way this text derives."""
    under = _read_by(session, reading)
    text = reading.text
    return Pane(
        f"{reading.title} — derivations",
        (640, 380),
        lambda: [derivation_view(under, text), _resolver(reading)],
    )


def _deed_pane(_session: Session, reading: Reading, name: str) -> Pane:
    """One of a reading's deeds, and the button that does it."""
    deed = next(d for d in deeds(reading) if d.name == name)
    return Pane(
        f"{reading.title} — {deed.label}", (480, 200), lambda: [_deed(reading, deed)]
    )


def _grammar(reading: Reading) -> CompiledGrammar:
    """The grammar this reading is, or the refusal saying it is not one."""
    held = artefact(reading)
    if held is None:
        raise UnsupportedConstructError(f"{reading.title} is not a grammar")
    return held


def _read_by(session: Session, reading: Reading) -> CompiledGrammar:
    """The compiled grammar that read this text, or the refusal."""
    under = _under(session, reading)
    if under is None:
        raise UnsupportedConstructError(
            f"{reading.title} was not read by a compiled grammar"
        )
    return under


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
    "tables": _tables_pane,
    "binding": _binding_pane,
    "fold": _fold_pane,
    "runs": _runs_pane,
    "analysis": _analysis_pane,
    "tokens": _tokens_pane,
    "resume": _resume_pane,
    "doc": _doc_pane,
    "semantic": _semantic_pane,
    "regrammar": _regrammar_pane,
    "flavour": _flavour_pane,
    "shadow": _shadow_pane,
    "dispatch": _dispatch_pane,
    "carve": _carve_pane,
    "plug": _plug_pane,
    "registry": _registry_pane,
    "floor": _floor_pane,
    "forest": _forest_pane,
    "derivations": _derivations_pane,
    "chart": _chart_pane,
    "segmentation": _segmentation_pane,
    "lanes": _lanes_pane,
}
"""Fan kind → the window it opens.

Open and table-driven, like every other consumer here: a kind with no
row raises, the drawing boundary catches that and DRAWS it, so a gap is
a visible refusal rather than a silent blank. A cascade of eighteen
returns is what this replaced.
"""


def window(session: Session, reading: Reading, kind: str) -> Pane:
    """The window a fan entry opens.

    :raises UnsupportedConstructError: When nothing knows that kind —
        which the caller draws rather than swallows.
    """
    if kind.startswith("do:"):
        name = kind.removeprefix("do:")
        if name == "constrain":
            return _constrain_pane(session, reading)
        return _deed_pane(session, reading, name)
    build = PANES.get(kind)
    if build is None:
        raise UnsupportedConstructError(f"no window for {kind!r}")
    return build(session, reading)


def _resolver(reading: Reading) -> IrDoc:
    """The resolver plug — the caller's answer to an ambiguity.

    Not a flag: an ambiguity is refused unless somebody says which
    derivation they meant, and this is where they say it. Empty means
    refuse, which is the default and the honest one.
    """
    return el(
        "div",
        {"class": "controls"},
        _chip(
            "resolver",
            f"c-res-{reading.ident}",
            reading.params.resolver,
            "empty refuses",
            False,
        ),
        el(
            "span",
            {"class": "note"},
            "'first' takes the first derivation; empty refuses an ambiguous "
            "span rather than choosing for you",
        ),
    )


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
    return compiled.flavour if compiled.flavour in _SPELLABLE else "gbnf"


def _pipeline(session: Session, reading: Reading) -> IrDoc:
    """The compile's stages for this reading."""
    compiled = _grammar(reading)
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
                _chip(
                    "@start",
                    f"c-start-{reading.ident}",
                    reading.params.directives.start or "",
                    "first rule",
                    off,
                ),
                _chip(
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


def _chip(label: str, ident: str, value: str, empty: str, off: bool) -> IrDoc:
    """One directive chip — a small editable datum that reads on change."""
    return el(
        "span",
        {"class": "chip off" if off else "chip"},
        label,
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


def _under(session: Session, reading: Reading) -> CompiledGrammar | None:
    """The compiled grammar that read this text, if one did.

    The floor is about a PARSE, so it exists only where a grammar
    actually read something — a grammar with nothing under it has no
    forest, and a text nobody reads has no engine.
    """
    above = session.readings.get(reading.reader)
    return above.compiled if above is not None and reading.text else None


def _wants(reading: Reading) -> list[str]:
    """The encoding names this reading asks to be read under, unmet or not.

    A grammar that names an encoding needs a vocabulary bound under that
    name before it can be read at all — so the plug affordance exists
    exactly where the grammar itself says it does.
    """
    return alphabets(reading.instance)
