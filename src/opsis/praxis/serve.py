"""The live loop — a loopback-only stdlib HTTP server around one Session.

One mutation route per task; reads are drawn, refusals carry real messages.
"""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from lexic.compile import CompiledGrammar, Directives, export_module, verify_module
from lexic.exceptions import LexicError, UnsupportedConstructError
from lexic.ir import IrCat, IrDoc, IrNone
from opsis.opsis import Rail, Ring, Space, VisualNode, page, view_body
from opsis.opsis.canvas import el, html, raw, void
from opsis.praxis.roots import Opened, Workspace, open_path
from opsis.praxis.state import Ladder, Rung

__all__ = [
    "Handler",
    "OpsisServer",
    "Session",
    "frames_of",
    "picker_frame",
    "scene_of",
    "serve",
    "session_window",
    "spawn_bar",
]

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


def _ring_pos(k: int, i: int) -> tuple[int, int]:
    """The ``k``-th ladder's rung-``i`` ring position — the trivial grid."""
    return 160 + k * 260, 140 + i * 150


def _ladder_parts(ladder: Ladder, k: int) -> list[VisualNode]:
    """One ring per rung of ``ladder`` (the ``k``-th ladder), plus its rails."""
    parts: list[VisualNode] = []
    prev_name = ""
    for i, rung in enumerate(ladder.rungs):
        name = f"l{k}r{i}"
        terminal = i == len(ladder.rungs) - 1
        hue = "err" if rung.errors else ("green" if terminal else "cyan")
        payload = rung.compiled.grammar if rung.compiled is not None else IrNone
        x, y = _ring_pos(k, i)
        parts.append(Ring(name, payload=payload, hue=hue, x=x, y=y))
        if i:
            parts.append(Rail(src=prev_name, dst=name))
        prev_name = name
    return parts


def frames_of(session: Session) -> str:
    """Pre-rendered editor and fan-detail frames, for every rung in view.

    Sits alongside :func:`scene_of` as the world's other half: the scene
    is the frozen ring/rail layer the camera draws once, this is the
    per-rung DOM (editors, fan nodes) the camera's own JS toggles.
    """
    parts: list[IrDoc] = []
    k = 0
    for entry in session.entries:
        if entry.ladder is not None:
            parts.extend(_ladder_frames(entry.ladder, k))
            k += 1
    return html(IrCat(*parts))


def _ladder_frames(ladder: Ladder, k: int) -> list[IrDoc]:
    """Editor + fan frames for every rung of ``ladder`` (the ``k``-th ladder)."""
    parts: list[IrDoc] = []
    for i, rung in enumerate(ladder.rungs):
        x, y = _ring_pos(k, i)
        parts.append(_editor_frame(ladder, k, i, rung, x, y))
        parts.extend(_fan_frames(k, i, rung, x, y))
    return parts


def _editor_frame(
    ladder: Ladder, k: int, i: int, rung: Rung, ring_x: int, ring_y: int
) -> IrDoc:
    """The rung's editor: a chips row, its text, and a button to re-read it."""
    x, y = ring_x + 340, ring_y - 20
    frame_id = f"l{k}r{i}"
    return el(
        "div",
        {
            "class": "frame editor",
            "data-frame": f"ed-{frame_id}",
            "style": f"left:{x}px;top:{y}px;width:420px;height:240px",
        },
        el("header", None, el("span", None, f"l{k} · rung {i} — editor")),
        el(
            "div",
            {"class": "fbody"},
            _chips_row(ladder, rung, frame_id),
            el("textarea", {"id": f"t-{frame_id}"}, rung.text),
            el("button", {"class": "read", "data-post": f"/rung/{k}/{i}"}, "read ▸"),
        ),
    )


def _chips_row(ladder: Ladder, rung: Rung, frame_id: str) -> IrDoc:
    """The rung's directive chips — disabled with a reason on a comment-less root."""
    off = not ladder.root.comment_forms
    start = rung.directives.start or ""
    non_semantic = rung.directives.non_semantic
    ns = ",".join(sorted(non_semantic)) if non_semantic else ""
    kids = [
        el(
            "span",
            {"class": "chip"},
            void("input", {"id": f"c-start-{frame_id}", "value": start}),
        ),
        el(
            "span",
            {"class": "chip"},
            void("input", {"id": f"c-ns-{frame_id}", "value": ns}),
        ),
    ]
    if off:
        kids.append(
            el(
                "span",
                {"class": "why"},
                "this root's surface carries no comments — flags ride the argument channel",
            )
        )
    return el("div", {"class": "chips off" if off else "chips"}, *kids)


def _fan_frames(k: int, i: int, rung: Rung, ring_x: int, ring_y: int) -> list[IrDoc]:
    """Tethered fan dots, one per reading this rung actually has."""
    parts: list[IrDoc] = []
    slot = 0
    if rung.compiled is not None:
        parts.extend(
            _fan_pair(
                "rules",
                "rules",
                view_body(rung.compiled.grammar),
                k,
                i,
                slot,
                ring_x,
                ring_y,
            )
        )
        slot += 1
    if rung.instance is not None:
        parts.extend(
            _fan_pair(
                "instance",
                "instance ▲",
                view_body(rung.instance),
                k,
                i,
                slot,
                ring_x,
                ring_y,
            )
        )
        slot += 1
    return parts


def _fan_pair(
    kind: str,
    label: str,
    body: IrDoc,
    k: int,
    i: int,
    slot: int,
    ring_x: int,
    ring_y: int,
) -> list[IrDoc]:
    """One fan node plus its hidden-by-default detail frame."""
    fx, fy = ring_x + 40, ring_y + 26 + 24 * slot
    open_id = f"fan-l{k}r{i}-{kind}"
    fan = el(
        "div",
        {
            "class": "fan",
            "id": f"fn-l{k}r{i}-{kind}",
            "data-open": open_id,
            "style": f"left:{fx}px;top:{fy}px",
        },
        el("div", {"class": "fdot"}),
        el("div", {"class": "rlabel"}, label),
    )
    frame = el(
        "div",
        {
            "class": "frame",
            "data-frame": open_id,
            "style": (
                f"left:{fx + 120}px;top:{fy}px;width:420px;height:240px;display:none"
            ),
        },
        el("header", None, el("span", None, label)),
        el("div", {"class": "fbody"}, body),
    )
    return [fan, frame]


def spawn_bar() -> IrDoc:
    """The spawn bar — the ingress affordance, bottom-center by default.

    Its position is camera state: dragging moves the DOM, and a freeze
    (a DOM snapshot) carries wherever it sits. The file bnode opens the
    picker; freeze and session are the artifact's two halves — the
    filled page, and its machine-reloadable ``repr(scene)``.
    """
    return el(
        "div",
        {"class": "bar", "id": "spawnbar"},
        el("u", None, "spawn"),
        el(
            "div",
            {"class": "bnode", "data-act": "picker"},
            el("div", {"class": "bdot"}),
            el("span", None, "file"),
        ),
        el("span", {"class": "act", "data-act": "freeze"}, "freeze ▾"),
        el("span", {"class": "act", "data-act": "session"}, "session ▾"),
    )


def picker_frame() -> IrDoc:
    """The picker window — filled from ``GET /files`` when opened."""
    return el(
        "div",
        {
            "class": "frame",
            "data-frame": "picker",
            "style": "left:480px;top:560px;width:420px;height:260px;display:none",
        },
        el("header", None, el("span", None, "open — workspace files")),
        el("div", {"class": "fbody", "id": "picker-rows"}),
    )


def session_window(scene: Space) -> IrDoc:
    """The session-file window — this page's own ``repr(scene)``, drawn."""
    return el(
        "div",
        {
            "class": "frame",
            "data-frame": "session-file",
            "style": "left:960px;top:560px;width:420px;height:260px;display:none",
        },
        el("header", None, el("span", None, "session — repr(scene)")),
        el(
            "div",
            {"class": "fbody"},
            el("pre", {"class": "notation", "id": "session-notation"}, repr(scene)),
        ),
    )


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


SERVE_JS = """
"use strict";
const FROZEN = document.body.classList.contains("frozen");
function toggleFrame(name) {
  const frame = document.querySelector(`.frame[data-frame="${name}"]`);
  if (frame) frame.style.display = frame.style.display === "none" ? "flex" : "none";
  return frame;
}
function openPicker() {
  const frame = toggleFrame("picker");
  if (!frame || frame.style.display === "none") return;
  fetch("/files").then(r => r.text()).then(text => {
    const rows = document.getElementById("picker-rows");
    rows.textContent = "";
    text.split("\\n").filter(Boolean).forEach(path => {
      const row = document.createElement("div");
      row.className = "prow";
      row.textContent = path;
      row.addEventListener("click", () =>
        fetch("/open", {method: "POST", body: path}).then(() => location.reload()));
      rows.appendChild(row);
    });
  });
}
function freezeSnapshot() {
  const clone = document.documentElement.cloneNode(true);
  clone.querySelector("body").classList.add("frozen");
  const blob = new Blob(["<!DOCTYPE html>" + clone.outerHTML], {type: "text/html"});
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "opsis-frozen.html";
  a.click();
  URL.revokeObjectURL(a.href);
}
document.addEventListener("click", e => {
  if (FROZEN) return;
  const act = e.target.closest("[data-act]");
  if (act) {
    if (act.dataset.act === "picker") openPicker();
    if (act.dataset.act === "freeze") freezeSnapshot();
    if (act.dataset.act === "session") location.href = "/session";
    return;
  }
  const fan = e.target.closest(".fan[data-open]");
  if (fan) {
    toggleFrame(fan.dataset.open);
    return;
  }
  const btn = e.target.closest(".read[data-post]");
  if (!btn) return;
  const editor = btn.closest(".editor");
  const textarea = editor.querySelector("textarea");
  const start = editor.querySelector('input[id^="c-start-"]');
  const ns = editor.querySelector('input[id^="c-ns-"]');
  const params = new URLSearchParams();
  if (start && start.value) params.set("start", start.value);
  if (ns && ns.value) params.set("non_semantic", ns.value);
  const qs = params.toString();
  fetch(btn.dataset.post + (qs ? `?${qs}` : ""), {method: "POST", body: textarea.value})
    .then(() => location.reload());
});
const bar = document.getElementById("spawnbar");
if (bar) bar.addEventListener("pointerdown", e => {
  if (e.target.closest("[data-act]") || FROZEN) return;
  const rect = bar.getBoundingClientRect();
  bar.style.left = rect.left + "px";
  bar.style.top = rect.top + "px";
  bar.style.bottom = "auto";
  bar.style.transform = "none";
  const sx = e.clientX - rect.left, sy = e.clientY - rect.top;
  const move = ev => {
    bar.style.left = (ev.clientX - sx) + "px";
    bar.style.top = (ev.clientY - sy) + "px";
  };
  const up = () => {
    window.removeEventListener("pointermove", move);
    window.removeEventListener("pointerup", up);
  };
  window.addEventListener("pointermove", move);
  window.addEventListener("pointerup", up);
});
"""
"""The rung frames' + bar's behavior — fan/picker toggling, the read-post
gesture, the freeze snapshot (the DOM is the camera: whatever was dragged
freezes where it sits), and the bar drag (its position is camera state).
In a frozen artifact every gesture is dead and drawn so. Deixis stays
CAMERA's; neither script re-registers the other's listener."""


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
        elif url.path == "/session":
            self._get_session()
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
        scene = scene_of(session)
        extra = (
            frames_of(session)
            + html(IrCat(spawn_bar(), picker_frame(), session_window(scene)))
            + html(el("script", None, raw(SERVE_JS)))
        )
        self._send(page(scene, subtitle=subtitle, extra=extra))

    def _get_files(self) -> None:
        listing = self._session().workspace.listing()
        self._send("\n".join(listing), kind="text/plain")

    def _get_session(self) -> None:
        """The artifact's machine-reloadable half — ``repr(scene)``, to disk."""
        self._send(
            repr(scene_of(self._session())),
            kind="text/plain",
            download="session.scene",
        )

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
        data = self.rfile.read(length)
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError:
            self._send("body is not UTF-8", code=400, kind="text/plain")
            return None

    def _send(
        self,
        body: str,
        code: int = 200,
        kind: str = "text/html",
        download: str | None = None,
    ) -> None:
        data = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", f"{kind}; charset=utf-8")
        if download is not None:
            self.send_header(
                "Content-Disposition", f'attachment; filename="{download}"'
            )
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
