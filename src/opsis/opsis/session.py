"""Drawing a session — praxis holds the readings, the spectacle shows them.

Everything here turns readings into rings, rails and windows. It decides
where things sit and which readings a node offers; it never decides what
a reading MEANS.

What a node offers follows from what it actually produced. A reading
with no compiled grammar has no rules window, because there are no
rules — not because a flag was off. That is the whole rule for the fan.
"""

from __future__ import annotations

from lexic.compile import CompiledGrammar
from lexic.exceptions import UnsupportedConstructError
from lexic.ir import (
    IrAst,
    IrCat,
    IrDoc,
    IrNone,
    IrRule,
    IrSeq,
)
from opsis.eidolon import layout
from opsis.opsis.canvas import el, html, raw
from opsis.opsis.canvas import text as _text
from opsis.opsis.graphic import RAIL_CSS, rule_svg
from opsis.opsis.panes import Pane, artefact, fan, window
from opsis.opsis.scene import Moon, Rail, Ring, Space
from opsis.opsis.space import Box, Frame, frame, render_scene
from opsis.opsis.views import (
    refusal,
    view_of,
)
from opsis.praxis.reading import FOREIGN, Reading
from opsis.praxis.reflect import drawn_by
from opsis.praxis.session import Session

__all__ = [
    "spawn_bar",
    "hint",
    "legend",
    "picker",
    "scene_of",
    "windows_of",
    "world_of",
]

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
        held = artefact(reading)
        if held is not None:
            parts.extend(_railroads(held.grammar, at[0] + 320, at[1] + 40))
    return html(IrCat(*parts))


def _fan_windows(
    session: Session, reading: Reading, at: tuple[int, int]
) -> list[IrDoc]:
    """One reading's windows, fanned out from where its ring sits.

    The frames ship empty and fill when opened. Not a cap — every window
    a reading offers is still here, still where it belongs — but a page
    that eagerly built all of them would pay for compiling a self
    grammar's predictive tables before anyone had asked to see them.
    """
    out: list[IrDoc] = []
    for slot, (kind, _label) in enumerate(fan(session, reading)):
        moon = f"m-{reading.ident}-{kind}"
        out.append(
            frame(
                Frame(
                    f"w-{moon}",
                    _title(session, reading, kind),
                    Box(
                        at[0] + 250 + slot * 26,
                        max(60, at[1] - 60 + slot * 44),
                        *_size(session, reading, kind),
                    ),
                    shown=False,
                    editor=kind == "text",
                    owner=moon,
                ),
                el("div", {"data-pane": f"{reading.ident}/{kind}"}),
            )
        )
    return out


def _title(session: Session, reading: Reading, kind: str) -> str:
    """A window's name, which costs nothing to know before it opens."""
    try:
        return window(session, reading, kind).title
    except FOREIGN:
        return f"{reading.title} — {kind}"


def _size(session: Session, reading: Reading, kind: str) -> tuple[int, int]:
    """A window's shape, also known before its body is built."""
    try:
        return window(session, reading, kind).size
    except FOREIGN:
        return (520, 240)


def pane_body(session: Session, ident: str, kind: str) -> str:
    """One window's contents, built now because somebody opened it."""
    reading = session.readings.get(ident)
    if reading is None:
        raise UnsupportedConstructError(f"no reading called {ident!r}")
    return html(IrCat(*_pane(session, reading, kind).build()))


def _pane(session: Session, reading: Reading, kind: str) -> Pane:
    """A window, or one that draws whatever went wrong building it.

    A window that cannot be built must never take the page down with
    it, and must never be blank either: the refusal IS the content.
    """
    try:
        pane = window(session, reading, kind)
        body = pane.build()
    except FOREIGN as exc:
        drawn = [refusal(f"{type(exc).__name__}: {exc}")]
        return Pane(f"{reading.title} — {kind}", (520, 240), lambda: drawn)
    return Pane(pane.title, pane.size, lambda: body)


def rail_body(session: Session, name: str) -> str:
    """One rule's diagram, built when its window is opened."""
    for reading in session.readings.values():
        held = artefact(reading)
        rule = _rule(held, name) if held is not None else None
        if rule is not None:
            return html(
                el(
                    "div",
                    {"class": "rr"},
                    raw(f"<style>{RAIL_CSS}</style>"),
                    raw(rule_svg(rule)),
                )
            )
    raise UnsupportedConstructError(f"no rule called {name!r} is open")


def _rule(held: CompiledGrammar, name: str) -> IrRule | None:
    """That rule of this grammar, if it has one."""
    return next((r for r in held.grammar.rules if str(r.name) == name), None)


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
            el("div", {"data-rail": str(rule.name)}),
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
