"""The live loop — a loopback-only stdlib HTTP server around one Session.

One mutation route per task; reads are drawn, refusals carry real messages.
"""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from lexic.compile import CompiledGrammar, Directives, export_module, verify_module
from lexic.exceptions import LexicError, UnsupportedConstructError
from lexic.ir import IrNone
from opsis.opsis import Rail, Ring, Space, VisualNode, page
from opsis.praxis.roots import Opened, Workspace, open_path
from opsis.praxis.state import Ladder

__all__ = ["Handler", "OpsisServer", "Session", "scene_of", "serve"]

_MAX_BODY = 2_000_000


class Session:
    """The server's cursor: a workspace plus every opened entry, in order."""

    __slots__ = ("workspace", "entries")

    def __init__(self, workspace: Workspace) -> None:
        self.workspace = workspace
        self.entries: list[Opened] = []


def scene_of(session: Session) -> Space:
    """The session's scene: one ring per ladder rung, wired in sequence.

    Trivial grid placement — a stand-in the eidolon layout derivation will
    replace, positions and hue policy both.
    """
    parts: list[VisualNode] = []
    k = 0
    for entry in session.entries:
        if entry.ladder is not None:
            parts.extend(_ladder_parts(entry.ladder, k))
            k += 1
        elif entry.scene is not None:
            parts.extend(entry.scene)
    return Space(*parts)


def _ladder_parts(ladder: Ladder, k: int) -> list[VisualNode]:
    """One ring per rung of ``ladder`` (the ``k``-th ladder), plus its rails."""
    parts: list[VisualNode] = []
    prev_name = ""
    for i, rung in enumerate(ladder.rungs):
        name = f"l{k}r{i}"
        terminal = i == len(ladder.rungs) - 1
        hue = "err" if rung.errors else ("green" if terminal else "cyan")
        payload = rung.compiled.grammar if rung.compiled is not None else IrNone
        parts.append(
            Ring(name, payload=payload, hue=hue, x=160 + k * 260, y=140 + i * 150)
        )
        if i:
            parts.append(Rail(src=prev_name, dst=name))
        prev_name = name
    return parts


def _rung_directives(query: str) -> Directives | None:
    """``start``/``non_semantic`` query params as Directives, or None if absent."""
    qs = parse_qs(query)
    start = (qs.get("start") or [""])[0] or None
    has_non_semantic = "non_semantic" in qs
    non_semantic = (
        frozenset(qs["non_semantic"][0].split(",")) if has_non_semantic else None
    )
    if start is None and non_semantic is None:
        return None
    return Directives(start=start, non_semantic=non_semantic)


def _mark(ok: bool, err: str) -> str:
    """One ``✓``/``✗ <err>`` reading mark."""
    return "✓" if ok else f"✗ {err}"


def _ladder_summary(ladder: Ladder) -> str:
    """One line per rung: its compiled and instance readings, as content."""
    lines = [
        f"rung {j} · compiled {_mark(rung.compiled is not None, rung.errors.get('compiled', ''))} "
        f"· instance {_mark(rung.instance is not None, rung.errors.get('instance', ''))}"
        for j, rung in enumerate(ladder.rungs)
    ]
    return "\n".join(lines)


def _matches_grammar(compiled: CompiledGrammar, target: Path) -> bool:
    """Whether ``target`` already holds a twin module of ``compiled``."""
    try:
        verify_module(compiled, target.read_text(encoding="utf-8"))
    except LexicError:
        return False
    return True


class Handler(BaseHTTPRequestHandler):
    """One session's routes — GET reads, POST is the one mutation each task owns."""

    def _session(self) -> Session:
        server = self.server
        if not isinstance(server, OpsisServer):
            raise UnsupportedConstructError(
                "serve: handler's server is not an OpsisServer"
            )
        return server.session

    def do_GET(self) -> None:
        url = urlsplit(self.path)
        if url.path == "/":
            self._get_root()
        elif url.path == "/files":
            self._get_files()
        else:
            self.send_error(404)

    def do_POST(self) -> None:
        url = urlsplit(self.path)
        body = self._read_body()
        if body is None:
            return
        segments = url.path.strip("/").split("/")
        if url.path == "/open":
            self._post_open(body)
        elif url.path == "/export":
            self._post_export(body)
        elif len(segments) == 3 and segments[0] == "rung":
            self._post_rung(segments[1], segments[2], url.query, body)
        else:
            self.send_error(404)

    def _get_root(self) -> None:
        session = self._session()
        n = sum(1 for entry in session.entries if entry.ladder is not None)
        subtitle = f"{n} roots · workspace {session.workspace.root.name}"
        self._send(page(scene_of(session), subtitle=subtitle))

    def _get_files(self) -> None:
        listing = self._session().workspace.listing()
        self._send("\n".join(listing), kind="text/plain")

    def _post_open(self, body: str) -> None:
        session = self._session()
        try:
            opened = open_path(session.workspace, body)
        except UnsupportedConstructError as exc:
            self._send(str(exc), code=422, kind="text/plain")
            return
        if opened.kind == "refused":
            self._send(opened.note, code=422, kind="text/plain")
            return
        session.entries.append(opened)
        self._send(f"{opened.kind} · {opened.note}", kind="text/plain")

    def _post_rung(self, l_str: str, i_str: str, query: str, body: str) -> None:
        if not (l_str.isdigit() and i_str.isdigit()):
            self.send_error(404)
            return
        ladders = [
            entry.ladder
            for entry in self._session().entries
            if entry.ladder is not None
        ]
        ladder_i, rung_i = int(l_str), int(i_str)
        if ladder_i >= len(ladders):
            self.send_error(404)
            return
        ladder = ladders[ladder_i]
        ladder.edit(rung_i, body, directives=_rung_directives(query))
        self._send(_ladder_summary(ladder), kind="text/plain")

    def _post_export(self, body: str) -> None:
        parts = body.strip().split("/")
        if len(parts) != 2 or not (parts[0].isdigit() and parts[1].isdigit()):
            self._send("export: expected '<L>/<i>'", code=422, kind="text/plain")
            return
        session = self._session()
        ladders = [
            entry.ladder for entry in session.entries if entry.ladder is not None
        ]
        ladder_i, rung_i = int(parts[0]), int(parts[1])
        if ladder_i >= len(ladders) or rung_i >= len(ladders[ladder_i].rungs):
            self._send("export: no such rung", code=422, kind="text/plain")
            return
        compiled = ladders[ladder_i].rungs[rung_i].compiled
        if compiled is None:
            self._send("nothing compiled at that rung", code=422, kind="text/plain")
            return
        target = session.workspace.root / "generated" / f"{compiled.stem}.py"
        if target.exists() and not _matches_grammar(compiled, target):
            self._send(
                f"{target.name} already exists and is not a twin of this grammar",
                code=409,
                kind="text/plain",
            )
            return
        try:
            written = export_module(compiled, target)
        except LexicError as exc:
            self._send(str(exc), code=422, kind="text/plain")
            return
        self._send(
            written.relative_to(session.workspace.root).as_posix(), kind="text/plain"
        )

    def _read_body(self) -> str | None:
        length = int(self.headers.get("Content-Length", 0))
        if length > _MAX_BODY:
            self.send_error(413)
            return None
        raw = self.rfile.read(length)
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError:
            self._send("body is not UTF-8", code=400, kind="text/plain")
            return None

    def _send(self, body: str, code: int = 200, kind: str = "text/html") -> None:
        data = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", f"{kind}; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format: str, *args: object) -> None:
        """Quiet — the terminal is the caller's, not the access log's."""


class OpsisServer(HTTPServer):
    """The loopback server owning one session."""

    def __init__(self, session: Session, port: int) -> None:
        super().__init__(("127.0.0.1", port), Handler)
        self.session = session


def serve(workspace_root: Path, port: int = 0) -> OpsisServer:
    """Bind a session server at 127.0.0.1; the caller drives ``serve_forever``."""
    return OpsisServer(Session(Workspace(workspace_root)), port)
