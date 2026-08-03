"""The live loop — a loopback server over one session.

One route per gesture, and no page reloads: the page is served once,
every mutation answers with the new ``#world`` fragment, and the client
swaps it in under a camera snapshot so nothing anyone placed moves. A
refusal travels as its real message and the page draws it.

Threaded on purpose: reading a thirty-megabyte module takes as long as
it takes, and the instrument stays alive while it happens.
"""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable, NamedTuple
from urllib.parse import SplitResult, parse_qs, urlsplit

from lexic.compile import Directives
from lexic.exceptions import LexicError, UnsupportedConstructError
from lexic.ir import IrCat, IrTokenizer
from opsis.opsis.draw.canvas import el, html, raw
from opsis.opsis.draw.scene import Space
from opsis.opsis.draw.space import page
from opsis.opsis.panes import CURSORS, RESUMES, WIDTHS
from opsis.opsis.session import (
    hint,
    legend,
    pane_body,
    picker,
    rail_body,
    scene_of,
    spawn_bar,
    world_of,
)
from opsis.praxis.client import CLIENT
from opsis.praxis.deeds.acts import perform
from opsis.praxis.deeds.carve import run_bench
from opsis.praxis.ingress.frozen import freeze, thaw
from opsis.praxis.ingress.ingress import (
    SHIPPED,
    browse,
    manifest_reader,
    manifests,
    open_file,
    surfaces,
    vocabulary_reader,
)
from opsis.praxis.ingress.reflect import REFLECTED, scene_reader, scene_text
from opsis.praxis.reading import FOREIGN, Reading, Source
from opsis.praxis.session import Session

__all__ = ["Handler", "OpsisServer", "serve"]

_MAX_BODY = 2_000_000


class Handler(BaseHTTPRequestHandler):
    """One session's routes."""

    def _session(self) -> Session:
        server = self.server
        if not isinstance(server, OpsisServer):
            raise UnsupportedConstructError("serve: not an opsis server")
        return server.session

    def get(self) -> None:
        """Answer a read gesture, or the refusal it turned out to be."""
        try:
            self._get(urlsplit(self.path))
        except FOREIGN as exc:
            self._refuse(exc)

    def _get(self, url: SplitResult) -> None:
        """One read gesture — the page, the world, or the workspace."""
        session = self._session()
        if url.path == "/":
            self._send(self._page(session))
        elif url.path == "/world":
            self._send(world_of(session))
        elif url.path.startswith("/pane/"):
            ident, _, kind = url.path.removeprefix("/pane/").partition("/")
            self._send(pane_body(session, ident, kind))
        elif url.path.startswith("/rail/"):
            self._send(rail_body(session, url.path.removeprefix("/rail/")))
        elif url.path == "/files":
            at = (parse_qs(url.query).get("at") or [""])[0]
            rows = browse(session.root, at)
            self._send("\n".join("\t".join(row) for row in rows), kind="text/plain")
        else:
            self.send_error(404)

    def post(self) -> None:
        """Answer a write gesture, or the refusal it turned out to be."""
        url = urlsplit(self.path)
        body = self._body()
        if body is None:
            return
        try:
            self._route(url.path.strip("/").split("/"), url.query, body)
        except FOREIGN as exc:
            self._refuse(exc)

    # http.server dispatches on ``do_`` plus the verb; these are the
    # names it looks up, and the two above are the ones anyone reads.
    do_GET = get
    do_POST = post

    def _refuse(self, exc: BaseException) -> None:
        """Answer with the refusal, whatever kind of thing raised it.

        A refusal lexic states is a 422 — it is an answer about the
        input. Anything else is a 500 that still carries its message,
        because a page that says what broke is worth more than a
        connection that closes, and one bad gesture must never take the
        instrument down.
        """
        answer = 422 if isinstance(exc, LexicError) else 500
        self._send(f"{type(exc).__name__}: {exc}", answer, "text/plain")

    def _route(self, parts: list[str], query: str, body: str) -> None:
        """One gesture, dispatched by the name it came in under.

        A table, so a route that does not exist is a 404 and a route
        that does is one line — not a sixteen-branch ladder where the
        last gesture is the cheapest to get wrong.
        """
        session = self._session()
        verb, rest = parts[0], parts[1:]
        take = _ROUTES.get((verb, len(rest)))
        if take is None:
            self.send_error(404)
            return
        self._send(take(session, rest, Ask(query, body)), kind="text/plain")

    def _page(self, session: Session) -> str:
        """The page, served once; everything after this is a fragment."""
        n = len(session.readings)
        subtitle = (
            f"{n} reading{'s' if n != 1 else ''} · {session.root.name}"
            if n
            else "open a file from the bar below, or make a new text"
        )
        hud = html(
            IrCat(
                spawn_bar(), picker(), legend(), hint(), el("script", None, raw(CLIENT))
            )
        )
        return page(Space(), subtitle, world_of(session), hud)

    def _body(self) -> str | None:
        length = int(self.headers.get("Content-Length", 0))
        if length > _MAX_BODY:
            self.send_error(413)
            return None
        try:
            return self.rfile.read(length).decode("utf-8")
        except UnicodeDecodeError:
            self._send("body is not UTF-8", 400, "text/plain")
            return None

    def _send(self, body: str, code: int = 200, kind: str = "text/html") -> None:
        data = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", f"{kind}; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_request(self, code: int | str = "-", size: int | str = "-") -> None:
        """Say nothing about a request that worked.

        Only the successful ones: a refusal still reaches the terminal,
        because somebody running this wants to see the one gesture that
        went wrong without reading a line for every one that did not.
        """


class Ask(NamedTuple):
    """What a gesture carried besides its name — its query and its body."""

    query: str = ""
    body: str = ""


def _open(session: Session, _rest: list[str], ask: Ask) -> str:
    """A file becomes a reading, read by whatever turned out to read it."""
    opened = open_file(session.root, ask.body.strip())
    if opened.kind == "session":
        return f"{opened.note} · {thaw(session, opened.text)} readings"
    if opened.reader is None:
        raise UnsupportedConstructError(opened.note)
    name = session.reader_named(opened.reader.name) or session.surface(opened.reader)
    session.add(opened.title, opened.kind, name, Source(opened.text, ask.body.strip()))
    return f"{opened.note} · {opened.title}"


def _new(session: Session, _rest: list[str], ask: Ask) -> str:
    """An empty reading to type into."""
    if ask.body not in ("grammar", "text"):
        raise UnsupportedConstructError(
            f"new: {ask.body!r} is not something to make — 'grammar' or 'text'"
        )
    session.add(f"new {ask.body}", ask.body)
    return "spawned"


def _edit(session: Session, rest: list[str], ask: Ask) -> str:
    """A reading's text, and everything under it, read again."""
    session.edit(rest[0], ask.body, _params(session, rest[0], ask.query))
    return "read"


def _drop(session: Session, rest: list[str], _ask: Ask) -> str:
    """Dropping one node on another says what reads what.

    The meaning is what the two nodes ARE, and the gesture is read the
    way a hand reads it: what you drop something ONTO takes it. Drop a
    grammar on a reader and that reader reads it; drop a reader on a
    loose text and it reads that text; drop a vocabulary on a grammar
    and it binds. Anything else refuses by saying which of the two was
    supposed to read.
    """
    source, target = rest
    landed = session.readings.get(target)
    if not source and landed is not None:
        session.bind(target, "")
        return f"{landed.title} · unbound"
    held = session.readings.get(source)
    if held is None or landed is None:
        raise UnsupportedConstructError("one of those is no longer here")
    if landed.kind == "vocabulary" and held.compiled is not None:
        return _reformulate(session, held, landed)
    if landed.as_reader() is not None and held.tokenizer is None:
        session.name_reader(source, target)
        return f"{landed.title} now reads {held.title}"
    if held.tokenizer is not None:
        return _bind(session, held, landed)
    if held.as_reader() is not None:
        session.name_reader(target, source)
        return f"{held.title} now reads {landed.title}"
    raise UnsupportedConstructError(
        f"{held.title} reads nothing and {landed.title} reads nothing — "
        "one of them has to be a reader"
    )


def _bind(session: Session, held: Reading, landed: Reading) -> str:
    """A vocabulary onto a grammar — the binding, by ident."""
    if landed.compiled is None:
        raise UnsupportedConstructError(
            "a vocabulary binds to a compiled grammar; this one has none"
        )
    session.bind(landed.ident, held.ident)
    vocab = IrTokenizer.ensure(held.tokenizer, "a vocabulary")
    return f"bound · {vocab.name}"


def _reformulate(session: Session, held: Reading, landed: Reading) -> str:
    """Read a vocabulary with a DIFFERENT json formulation.

    This is the one place the "no privileged formulation" rule is
    visible as a gesture rather than as a claim: the shipped json
    grammar is what a vocabulary opens with, and dropping another json
    grammar on it swaps which grammar does the reading. If the two
    disagree about what the rules are called, the reduction refuses and
    the node says so — not a silent fall back to the shipped one.
    """
    compiled = held.compiled
    if compiled is None:
        raise UnsupportedConstructError(f"{held.title} compiled nothing to read with")
    landed.reader = session.surface(
        vocabulary_reader(
            compiled.grammar, name=f"vocabulary via {held.title}", of=held.ident
        )
    )
    session.read(landed.ident)
    return f"{landed.title} · {landed.error or f'read by {held.title}'}"


def _unplug(session: Session, rest: list[str], _ask: Ask) -> str:
    """Nothing reads it any more, but it is kept."""
    session.name_reader(rest[0], "")
    return "unplugged"


def _remove(session: Session, rest: list[str], _ask: Ask) -> str:
    """Out of the session — never off the disk."""
    gone = session.drop(rest[0])
    if gone is None:
        raise UnsupportedConstructError(f"no reading called {rest[0]!r}")
    return f"removed {gone.title}"


def _do(session: Session, rest: list[str], _ask: Ask) -> str:
    """One of a reading's deeds."""
    reading = session.readings.get(rest[0])
    if reading is None:
        raise UnsupportedConstructError("that reading is no longer here")
    return perform(session, reading, rest[1])


def _cursor(session: Session, rest: list[str], ask: Ask) -> str:
    """One move of a constraint cursor."""
    return _step(session, rest[0], rest[1], ask.body)


def _template(session: Session, rest: list[str], ask: Ask) -> str:
    """One run of a reading's template bench."""
    return _carve(session, rest[0], ask.query)


def _freeze(session: Session, _rest: list[str], _ask: Ask) -> str:
    """The session as the notation that reads it back."""
    return freeze(session)


def _thaw(session: Session, _rest: list[str], ask: Ask) -> str:
    """That notation, back into a session."""
    return f"thawed · {thaw(session, ask.body)} readings"


def _carve(session: Session, ident: str, query: str) -> str:
    """Run a reading's template bench with what its window says."""
    reading = session.readings.get(ident)
    compiled = reading.compiled if reading is not None else None
    if reading is None or compiled is None:
        raise UnsupportedConstructError("templating needs a compiled grammar")
    below = [r for r in session.readers_of(ident) if r.text]
    if not below:
        raise UnsupportedConstructError(
            "nothing under this grammar to extract from — give it a text first"
        )
    qs = parse_qs(query)
    held = run_bench(
        ident,
        compiled,
        (qs.get("shape") or [""])[0],
        (qs.get("spec") or [""])[0],
        below[0].text,
    )
    return held.result.note


def _extend(session: Session, rest: list[str], ask: Ask) -> str:
    """More text onto a growing chart."""
    held = RESUMES.of(_held(session, rest[0]))
    held.extend(ask.body)
    return f"extended · {'accepts' if held.accepting else 'still open'}"


def _mark(session: Session, rest: list[str], _ask: Ask) -> str:
    """A point on this chart worth coming back to."""
    return f"marked at {RESUMES.of(_held(session, rest[0])).mark().at}"


def _rewind(session: Session, rest: list[str], _ask: Ask) -> str:
    """Back to a mark, dropping everything taken after it."""
    held = RESUMES.of(_held(session, rest[0]))
    held.rollback(int(rest[1]))
    return f"back to {rest[1]} · {held.text!r}"


def _held(session: Session, ident: str) -> Reading:
    """The reading by that name, or the refusal naming it."""
    reading = session.readings.get(ident)
    if reading is None:
        raise UnsupportedConstructError(f"no reading called {ident!r}")
    return reading


def _width(session: Session, rest: list[str], ask: Ask) -> str:
    """How wide to render a reading's document.

    Held per reading rather than globally: two documents open at once
    are two questions, and one slider answering both would be a setting
    pretending to be a control.
    """
    _held(session, rest[0])
    WIDTHS[rest[0]] = max(20, min(200, int(ask.body or "88")))
    return f"{WIDTHS[rest[0]]} columns"


def _reflect(session: Session, _rest: list[str], _ask: Ask) -> str:
    """Write the picture down as a reading, so it can be edited.

    The scene is snapshotted at the moment it is written: from then on
    the text is the source and the drawing follows it, which is what
    makes editing a node's payload change what that node shows.
    """
    space = scene_of(session)
    name = session.surface(scene_reader())
    session.add("the scene", REFLECTED, name, Source(scene_text(space)))
    return f"the scene, written down · {len(space)} records — edit it and it draws"


def _step(session: Session, what: str, ident: str, body: str) -> str:
    """One move of a constraint cursor — push, undo, or start over."""
    if what == "reset":
        CURSORS.reset(session, ident)
        return "back to the empty prefix"
    at = CURSORS.of(session, ident)
    if what == "back":
        at.back()
        return f"undone · {at.text!r}"
    pushed = at.push_text(body)
    return f"pushed {pushed} · {at.text!r}"


def _params(session: Session, ident: str, query: str):
    """A reading's params, with the chips this edit carried."""
    reading = session.readings.get(ident)
    params = reading.params if reading is not None else None
    if params is None:
        return None
    qs = parse_qs(query)
    names = (qs.get("non_semantic") or [""])[0]
    return params._replace(
        resolver=(qs.get("resolver") or [""])[0],
        directives=Directives(
            start=(qs.get("start") or [""])[0] or None,
            non_semantic=frozenset(names.split(",")) if names else None,
        ),
    )


class OpsisServer(ThreadingHTTPServer):
    """The loopback server owning one session."""

    daemon_threads = True

    def __init__(self, session: Session, port: int) -> None:
        super().__init__(("127.0.0.1", port), Handler)
        self.session = session


def serve(root: Path, port: int = 0) -> OpsisServer:
    """Bind a session server over a seeded session; the caller drives it."""
    session = Session(root)
    for reader in surfaces():
        session.surface(reader)
    seed(session)
    return OpsisServer(session, port)


def seed(session: Session) -> None:
    """Put the flavours lexic ships on the canvas, as readings.

    A flavour is not a menu entry here and never was: it is a manifest
    text read by the notation, whose product happens to read grammars.
    Seeding them means the top rung is on screen at launch, that editing
    one changes what it reads with, and that opening a manifest of your
    own lands beside them as the same kind of thing.
    """
    notation = session.surface(manifest_reader())
    for name, text in manifests():
        session.add(name, "manifest", notation, Source(text, SHIPPED + name))


_ROUTES: dict[tuple[str, int], Callable[[Session, list[str], Ask], str]] = {
    ("open", 0): _open,
    ("new", 0): _new,
    ("text", 1): _edit,
    ("drop", 2): _drop,
    ("unplug", 1): _unplug,
    ("remove", 1): _remove,
    ("do", 2): _do,
    ("push", 1): lambda s, r, a: _cursor(s, ["push", r[0]], a),
    ("back", 1): lambda s, r, a: _cursor(s, ["back", r[0]], a),
    ("reset", 1): lambda s, r, a: _cursor(s, ["reset", r[0]], a),
    ("carve", 1): _template,
    ("extend", 1): _extend,
    ("mark", 1): _mark,
    ("rewind", 2): _rewind,
    ("width", 1): _width,
    ("reflect", 0): _reflect,
    ("freeze", 0): _freeze,
    ("thaw", 0): _thaw,
}
"""(verb, how many names follow) → the gesture it is.

Keyed by arity too, so ``/drop/a`` is a 404 rather than a crash inside
a route that expected two names.
"""
