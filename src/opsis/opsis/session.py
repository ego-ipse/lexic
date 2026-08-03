"""Drawing a session — praxis holds the readings, the spectacle shows them.

Everything here turns readings into rings, rails and windows. It decides
where things sit and which readings a node offers; it never decides what
a reading MEANS.

What a node offers follows from what it actually produced. A reading
with no compiled grammar has no rules window, because there are no
rules — not because a flag was off. That is the whole rule for the fan.
"""

from __future__ import annotations

from typing import Callable, NamedTuple

from lexic.compile import CompiledGrammar
from lexic.exceptions import LexicError, UnsupportedConstructError
from lexic.ir import IrAst, IrCat, IrDoc, IrFlavour, IrNone, IrSeq, IrTokenizer
from lexic.parsing import lift_optional_nullables
from opsis.eidolon import layout
from opsis.opsis.canvas import el, html, raw
from opsis.opsis.canvas import text as _text
from opsis.opsis.engine import (
    derivation_view,
    floor_view,
    forest_view,
    tables_view,
)
from opsis.opsis.graphic import RAIL_CSS, rule_svg
from opsis.opsis.scene import Moon, Rail, Ring, Space
from opsis.opsis.space import Box, Frame, frame, render_scene
from opsis.opsis.tables import flavour_view, registry_view, table_view
from opsis.opsis.views import (
    bounded,
    carve_view,
    constrain_view,
    instance_view,
    module_view,
    pipeline_view,
    railroad_view,
    refusal,
    rules_view,
    tokenizer_view,
    view_of,
)
from opsis.praxis.acts import Deed, deeds
from opsis.praxis.carve import bench
from opsis.praxis.constrain import Cursors, sample
from opsis.praxis.reading import Reading
from opsis.praxis.reflect import drawn_by
from opsis.praxis.session import Session, alphabets

__all__ = [
    "spawn_bar",
    "hint",
    "legend",
    "picker",
    "scene_of",
    "windows_of",
    "world_of",
]

CURSORS = Cursors()
"""Every reading's constraint cursor — thrown away when it re-reads."""

_SPELLABLE = ("gbnf", "abnf", "ebnf")
"""Surfaces the exporter can spell a module's docstrings in."""


# ── the scene ─────────────────────────────────────────────────────────


def _hue(reading: Reading) -> str:
    """What a reading's state looks like."""
    if reading.error:
        return "err"
    if not reading.text:
        return "dim"
    if reading.flavour is not None:
        return "amber"
    if reading.tokenizer is not None:
        return "magenta"
    if reading.compiled is not None:
        return "cyan"
    return "green"


def _sub(reading: Reading) -> str:
    """The dim line under a name — what this reading IS right now."""
    return _unread(reading) or _produced(reading)


def _unread(reading: Reading) -> str:
    """Why there is nothing to say about a product yet, if there isn't."""
    if reading.error:
        return "refused — its text window carries the message"
    if not reading.text:
        return "empty — type its text and it reads"
    if not reading.reader:
        return f"{len(reading.text):,} chars · nothing reads it yet"
    return ""


def _produced(reading: Reading) -> str:
    """What this reading turned out to be, once something read it."""
    compiled = reading.compiled
    if compiled is not None:
        rules = len(list(compiled.grammar.rules))
        bound = compiled.tokens.tokenizer
        vocab = f" · bound to {bound.name}" if bound is not None else ""
        return f"{rules} rules · reads what is dropped on it{vocab}"
    if reading.flavour is not None:
        return "a reader · drop a grammar on it to read it"
    if reading.tokenizer is not None:
        return f"{len(reading.tokenizer.encode):,} entries · drop it on a grammar"
    return f"{type(reading.product).__name__} · {len(reading.text):,} chars"


def fan(session: Session, reading: Reading) -> list[tuple[str, str]]:
    """The readings this one actually has — nothing offered that isn't."""
    out = [("text", "text")]
    if reading.compiled is not None:
        out += [
            ("rules", "rules"),
            ("railroad", "railroad"),
            ("pipeline", "pipeline"),
            ("module", "module"),
        ]
    if reading.tokenizer is not None:
        out.append(("vocabulary", "vocabulary ▲"))
    if reading.instance is not None:
        out.append(("instance", "instance ▲"))
    if reading.product is not None and reading.compiled is None:
        out.append(("product", "product ▲"))
    if reading.compiled is not None and reading.compiled.tokens.tokenizer is not None:
        out.append(("bound", "bound to ▲"))
    reader = session.reader_for(reading)
    if reader is not None and reader.grammar is not None:
        out.append(("reader", "its reader"))
    out += [(f"do:{deed.name}", deed.label) for deed in deeds(reading)]
    if reader is not None and reader.of and _under(session, reading) is not None:
        out += [
            ("floor", "the floor"),
            ("forest", "forest"),
            ("derivations", "derivations"),
        ]
    if reading.compiled is not None:
        out += [("tables", "its tables"), ("carve", "template")]
    if reading.flavour is not None:
        out += [("flavour", "what it IS"), ("dispatch", "its tables")]
    if not reading.reader:
        out.append(("registry", "the registry"))
    if _wants(reading):
        out.append(("plug", "plug ⊕"))
    return out


def _wants(reading: Reading) -> list[str]:
    """The encoding names this reading asks to be read under, unmet or not.

    A grammar that names an encoding needs a vocabulary bound under that
    name before it can be read at all — so the plug affordance exists
    exactly where the grammar itself says it does.
    """
    return alphabets(reading.instance)


def _under(session: Session, reading: Reading) -> CompiledGrammar | None:
    """The compiled grammar that read this text, if one did.

    The floor is about a PARSE, so it exists only where a grammar
    actually read something — a grammar with nothing under it has no
    forest, and a text nobody reads has no engine.
    """
    above = session.readings.get(reading.reader)
    return above.compiled if above is not None and reading.text else None


def placement(session: Session) -> dict[str, tuple[int, int]]:
    """Where every reading sits — derived, and held by nobody.

    Positions belong to the picture, not to the readings: a reading
    knows what it is and what reads it, and would be the same reading
    laid out any other way.
    """
    idents = list(session.readings)
    return layout({i: session.readings[i].reader for i in idents}, idents)


def scene_of(session: Session) -> Space:
    """Every reading as a ring, every naming as a rail."""
    place = placement(session)
    parts: list[Ring | Rail] = []
    for ident in session.readings:
        reading = session.readings[ident]
        x, y = place.get(ident, (400, 300))
        payload = reading.product if isinstance(reading.product, IrAst) else IrNone
        compiled = reading.compiled
        if compiled is not None:
            payload = compiled.grammar
        parts.append(
            Ring(
                ident,
                payload,
                _hue(reading),
                x,
                y,
                reading.title,
                _sub(reading),
                IrSeq(
                    *(
                        Moon(f"m-{ident}-{kind}", label, kind)
                        for kind, label in fan(session, reading)
                    )
                ),
                f"reading:{ident}",
                "reads" if reading.reads else "idle",
            )
        )
        if reading.reader in session.readings:
            ok = not reading.error
            parts.append(
                Rail(
                    src=reading.reader,
                    dst=ident,
                    hue="green" if ok else "err",
                    label="reads",
                    sub=f"{session.readings[reading.reader].title} reads this text",
                    bow=0,
                )
            )
    return Space(*parts)


# ── the windows a fan opens ───────────────────────────────────────────


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


def _tables_pane(_session: Session, reading: Reading) -> Pane:
    """The predictive artefact this grammar compiled to."""
    compiled = _grammar(reading)
    return Pane(
        f"{reading.title} — its tables", (640, 380), lambda: [tables_view(compiled)]
    )


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
    """The artefact this reading produced, or the refusal saying it did not."""
    compiled = reading.compiled
    if compiled is None:
        raise UnsupportedConstructError(f"{reading.title} compiled nothing")
    return compiled


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
    "flavour": _flavour_pane,
    "dispatch": _dispatch_pane,
    "carve": _carve_pane,
    "plug": _plug_pane,
    "registry": _registry_pane,
    "floor": _floor_pane,
    "forest": _forest_pane,
    "derivations": _derivations_pane,
}
"""Fan kind → the window it opens.

Open and table-driven, like every other consumer here: a kind with no
row raises, the drawing boundary catches that and DRAWS it, so a gap is
a visible refusal rather than a silent blank. A cascade of eighteen
returns is what this replaced.
"""


def _window(session: Session, reading: Reading, kind: str) -> Pane:
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
        rows.append(
            el(
                "div",
                {"class": "controls"},
                el(
                    "button",
                    {"class": "go", "data-do": f"/drop//{reading.ident}"},
                    "unbind",
                ),
            )
        )
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
    compiled = reading.compiled
    assert compiled is not None
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


def payloads_of(space: Space) -> list[IrDoc]:
    """A window per ring that is ABOUT something, built from the SPACE.

    From the space and not from the readings, so a hand-edited scene
    opens the payload it now names. That is the reflective rung's whole
    claim made good: change the node, change what it shows.
    """
    out: list[IrDoc] = []
    for part in space:
        if not isinstance(part, Ring) or part.payload is IrNone:
            continue
        out.append(
            frame(
                Frame(
                    f"ir-{part.name}",
                    f"{part.label or part.name} — ◈ what it is about",
                    Box(part.x + 210, part.y + 90, 640, 400),
                    shown=False,
                ),
                view_of(part.payload),
            )
        )
    return out


def windows_of(session: Session) -> str:
    """Every window every reading offers, plus each grammar's railroads."""
    parts: list[IrDoc] = []
    place = placement(session)
    for ident, reading in session.readings.items():
        at = place.get(ident, (400, 300))
        parts.extend(_fan_windows(session, reading, at))
        compiled = reading.compiled
        if compiled is not None:
            parts.extend(_railroads(compiled.grammar, at[0] + 320, at[1] + 40))
    return html(IrCat(*parts))


def _fan_windows(
    session: Session, reading: Reading, at: tuple[int, int]
) -> list[IrDoc]:
    """One reading's windows, fanned out from where its ring sits."""
    out: list[IrDoc] = []
    for slot, (kind, _label) in enumerate(fan(session, reading)):
        moon = f"m-{reading.ident}-{kind}"
        pane = _pane(session, reading, kind)
        out.append(
            frame(
                Frame(
                    f"w-{moon}",
                    pane.title,
                    Box(
                        at[0] + 250 + slot * 26,
                        max(60, at[1] - 60 + slot * 44),
                        pane.size[0],
                        pane.size[1],
                    ),
                    shown=False,
                    editor=kind == "text",
                    owner=moon,
                ),
                *pane.build(),
            )
        )
    return out


def _pane(session: Session, reading: Reading, kind: str) -> Pane:
    """A window, or one that draws whatever went wrong building it.

    A window that cannot be built must never take the page down with
    it, and must never be blank either: the refusal IS the content.
    """
    try:
        pane = _window(session, reading, kind)
        body = pane.build()
    except (LexicError, RecursionError) as exc:
        drawn = [refusal(f"{type(exc).__name__}: {exc}")]
        return Pane(f"{reading.title} — {kind}", (520, 240), lambda: drawn)
    return Pane(pane.title, pane.size, lambda: body)


def _railroads(ast: IrAst, x: int, y: int) -> list[IrDoc]:
    """A window per rule's diagram, in the world.

    A diagram belongs to its rule, not to whichever window asked for
    it: opening ``value`` from a rules graph and from a reference box
    inside another railroad reaches the SAME window.
    """
    return [
        frame(
            Frame(
                f"rr-{rule.name}",
                f"{rule.name} · railroad",
                Box(x + (i % 6) * 34, y + (i % 6) * 28, 540, 200),
                shown=False,
                rule=str(rule.name),
            ),
            el(
                "div",
                {"class": "rr"},
                raw(f"<style>{RAIL_CSS}</style>"),
                raw(rule_svg(rule)),
            ),
        )
        for i, rule in enumerate(ast.rules)
    ]


# ── the furniture ─────────────────────────────────────────────────────


def spawn_bar() -> IrDoc:
    """Where new readings come from, fixed to the viewport.

    There is no list of flavours here and no vocabulary button: a
    surface you can read with is a READING the session holds, and you
    drag it. The bar only makes what nothing else can — a picker, and
    two empty texts.
    """
    return el(
        "div",
        {"class": "bar", "id": "bar"},
        el("u", None, "open"),
        el(
            "div",
            {"class": "bnode cyan", "data-act": "picker"},
            el("i", None),
            el("em", None, "file"),
        ),
        el("u", None, "new"),
        el(
            "div",
            {"class": "bnode cyan", "data-spawn": "grammar"},
            el("i", None),
            el("em", None, "grammar"),
        ),
        el(
            "div",
            {"class": "bnode green", "data-spawn": "text"},
            el("i", None),
            el("em", None, "text"),
        ),
        el("u", None, "itself"),
        el(
            "div",
            {"class": "bnode magenta", "data-act": "reflect"},
            el("i", None),
            el("em", None, "the scene"),
        ),
        el("u", None, "session"),
        el(
            "span",
            {"class": "bnode", "data-act": "freeze"},
            el("i", None),
            el("em", None, "freeze"),
        ),
    )


def picker() -> IrDoc:
    """The picker — the whole workspace, browsable, held by the viewport."""
    return frame(
        Frame(
            "picker",
            "open — anything in the workspace",
            Box(0, 0, 580, 420),
            shown=False,
            hud=True,
        ),
        el("div", {"class": "note", "id": "where"}, "the workspace"),
        el("div", {"id": "rows"}),
    )


def legend() -> IrDoc:
    """What the hues mean — stated, not remembered."""
    marks = (
        ("amber", "a reader"),
        ("cyan", "a grammar"),
        ("green", "a text"),
        ("magenta", "a vocabulary"),
        ("err", "refused"),
        ("dim", "unread"),
    )
    return el(
        "div",
        {"id": "legend"},
        *(
            IrCat(el("i", {"style": f"background:var(--{hue})"}), _text(what))
            for hue, what in marks
        ),
    )


def hint() -> IrDoc:
    """The gestures, said once."""
    return el(
        "div",
        {"id": "hint"},
        "drag the void to pan · wheel to zoom · click a moon for a reading",
        el("br", None),
        "drop one node on another to say what reads what — a reader reads a "
        "grammar, a vocabulary binds to one",
        el("br", None),
        "⊗ unplugs · × removes · ⌖ folds · windows drag, resize and close",
    )


def world_of(session: Session) -> str:
    """Everything inside ``#world`` — the swappable fragment.

    Derived from the readings, unless somebody has written the scene
    down: a hand-edited scene is an instruction, not a report, and the
    windows still come from the readings so the two halves of a node
    never disagree about which reading they belong to.
    """
    written = drawn_by(session)
    space = written if written is not None else scene_of(session)
    payloads = html(IrCat(*payloads_of(space)))
    return render_scene(space) + windows_of(session) + payloads
