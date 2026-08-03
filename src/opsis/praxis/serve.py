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
from urllib.parse import parse_qs, urlsplit

from lexic.compile import Directives, Vocabulary
from lexic.exceptions import UnsupportedConstructError
from lexic.ir import IrCat
from opsis.opsis.canvas import el, html, raw
from opsis.opsis.scene import Space
from opsis.opsis.session import bar, hint, legend, picker, world_of
from opsis.opsis.space import page
from opsis.praxis.ingress import (
    browse,
    manifest_reader,
    manifests,
    open_file,
    surfaces,
    vocabulary_reader,
)
from opsis.praxis.reading import Reading
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

    def do_GET(self) -> None:
        url = urlsplit(self.path)
        session = self._session()
        if url.path == "/":
            self._send(self._page(session))
        elif url.path == "/world":
            self._send(world_of(session))
        elif url.path == "/files":
            at = (parse_qs(url.query).get("at") or [""])[0]
            try:
                rows = browse(session.root, at)
            except UnsupportedConstructError as exc:
                self._send(str(exc), 422, "text/plain")
                return
            self._send("\n".join("\t".join(row) for row in rows), kind="text/plain")
        else:
            self.send_error(404)

    def do_POST(self) -> None:
        url = urlsplit(self.path)
        body = self._body()
        if body is None:
            return
        parts = url.path.strip("/").split("/")
        try:
            self._route(parts, url.query, body)
        except UnsupportedConstructError as exc:
            self._send(str(exc), 422, "text/plain")

    def _route(self, parts: list[str], query: str, body: str) -> None:
        """One gesture, dispatched by what it is."""
        session = self._session()
        if parts == ["open"]:
            self._open(session, body.strip())
        elif parts == ["new"] and body in ("grammar", "text"):
            session.add(f"new {body}", body)
            self._send("spawned", kind="text/plain")
        elif len(parts) == 2 and parts[0] == "text":
            session.edit(parts[1], body, _params(session, parts[1], query))
            self._send("read", kind="text/plain")
        elif len(parts) == 3 and parts[0] == "drop":
            self._drop(session, parts[1], parts[2])
        elif len(parts) == 2 and parts[0] == "unplug":
            session.name_reader(parts[1], "")
            self._send("unplugged", kind="text/plain")
        elif len(parts) == 2 and parts[0] == "remove":
            gone = session.drop(parts[1])
            self._send(f"removed {gone.title if gone else ''}", kind="text/plain")
        else:
            self.send_error(404)

    def _open(self, session: Session, rel: str) -> None:
        """A file becomes a reading, read by whatever turned out to read it."""
        opened = open_file(session.root, rel)
        if opened.reader is None:
            self._send(opened.note, 422, "text/plain")
            return
        name = session.surface(opened.reader)
        session.add(opened.title, opened.kind, name, opened.text, rel)
        self._send(f"{opened.note} · {opened.title}", kind="text/plain")

    def _drop(self, session: Session, source: str, target: str) -> None:
        """Dropping one node on another says what reads what.

        The meaning is what the two nodes ARE, and the gesture is read
        the way a hand reads it: what you drop something ONTO takes it.
        Drop a grammar on a reader and that reader reads it; drop a
        reader on a loose text and it reads that text; drop a vocabulary
        on a grammar and it binds. Anything else refuses by saying which
        of the two was supposed to read.
        """
        held = session.readings.get(source)
        landed = session.readings.get(target)
        if held is None or landed is None:
            raise UnsupportedConstructError("one of those is no longer here")
        if landed.kind == "vocabulary" and held.compiled is not None:
            self._reformulate(session, held, landed)
            return
        if landed.as_reader() is not None and held.tokenizer is None:
            session.name_reader(source, target)
            self._send(f"{landed.title} now reads {held.title}", kind="text/plain")
            return
        if held.tokenizer is not None:
            compiled = landed.compiled
            if compiled is None:
                raise UnsupportedConstructError(
                    "a vocabulary binds to a compiled grammar; this one has none"
                )
            landed.params.vocabulary = Vocabulary(tokenizer=held.tokenizer)
            session.read(landed.ident)
            self._send(f"bound · {held.tokenizer.name}", kind="text/plain")
            return
        if held.as_reader() is not None:
            session.name_reader(target, source)
            self._send(f"{held.title} now reads {landed.title}", kind="text/plain")
            return
        raise UnsupportedConstructError(
            f"{held.title} reads nothing and {landed.title} reads nothing — "
            "one of them has to be a reader"
        )

    def _reformulate(self, session: Session, held: Reading, landed: Reading) -> None:
        """Read a vocabulary with a DIFFERENT json formulation.

        This is the one place the "no privileged formulation" rule is
        visible as a gesture rather than as a claim: the shipped json
        grammar is what a vocabulary opens with, and dropping another
        json grammar on it swaps which grammar does the reading. If the
        two disagree about what the rules are called, the reduction
        refuses and the node says so — which is the honest answer, not a
        silent fall back to the shipped one.
        """
        compiled = held.compiled
        assert compiled is not None
        name = session.surface(
            vocabulary_reader(
                compiled.grammar, name=f"vocabulary via {held.title}", of=held.ident
            )
        )
        landed.reader = name
        session.read(landed.ident)
        outcome = landed.error or f"read by {held.title}"
        self._send(f"{landed.title} · {outcome}", kind="text/plain")

    def _page(self, session: Session) -> str:
        """The page, served once; everything after this is a fragment."""
        n = len(session.readings)
        subtitle = (
            f"{n} reading{'s' if n != 1 else ''} · {session.root.name}"
            if n
            else "open a file from the bar below, or make a new text"
        )
        hud = html(
            IrCat(bar(), picker(), legend(), hint(), el("script", None, raw(CLIENT)))
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

    def log_message(self, format: str, *args: object) -> None:
        """Quiet — the terminal belongs to whoever started this."""


def _params(session: Session, ident: str, query: str):
    """A reading's params, with the chips this edit carried."""
    reading = session.readings.get(ident)
    params = reading.params if reading is not None else None
    if params is None:
        return None
    qs = parse_qs(query)
    start = (qs.get("start") or [""])[0] or None
    names = (qs.get("non_semantic") or [""])[0]
    params.directives = Directives(
        start=start,
        non_semantic=frozenset(names.split(",")) if names else None,
    )
    return params


CLIENT = r"""
"use strict";
function toast(message) {
  const old = document.querySelector(".toast");
  if (old) old.remove();
  const t = document.createElement("div");
  t.className = "toast";
  t.textContent = message;
  t.addEventListener("click", () => t.remove());
  document.body.appendChild(t);
}
let framed = true;
function refresh() {
  // The caret is carried across the swap by hand, or reading-as-you-type
  // would fight the typing.
  const a = document.activeElement;
  const held = a && a.id && (a.tagName === "TEXTAREA" || a.tagName === "INPUT")
    ? {id: a.id, s: a.selectionStart, e: a.selectionEnd, top: a.scrollTop} : null;
  return fetch("/world").then(r => r.text()).then(w => {
    const cam = window.opsisCamera.snapshot();
    document.getElementById("world").innerHTML = w;
    window.opsisCamera.restore(cam);
    if (!framed) { framed = true; window.opsisCamera.fit(90); }
    if (!held) return;
    const el = document.getElementById(held.id);
    if (!el) return;
    el.focus();
    if (el.setSelectionRange) el.setSelectionRange(held.s, held.e);
    el.scrollTop = held.top;
  });
}
const posted = r => r.ok ? refresh() : r.text().then(toast);
function browse(at) {
  fetch("/files?at=" + encodeURIComponent(at)).then(r => r.text()).then(text => {
    const rows = document.getElementById("rows");
    const where = document.getElementById("where");
    rows.textContent = "";
    where.textContent = at ? at + "/" : "the workspace";
    text.split("\n").filter(Boolean).forEach(line => {
      const [kind, path, name, size] = line.split("\t");
      const row = document.createElement("div");
      row.className = "prow" + (kind === "dir" ? " dir" : "");
      row.appendChild(document.createTextNode(name));
      if (size) {
        const tag = document.createElement("em");
        tag.textContent = size;
        row.appendChild(tag);
      }
      row.addEventListener("click", () => {
        if (kind === "dir") { browse(path); return; }
        fetch("/open", {method: "POST", body: path}).then(r => {
          if (!r.ok) return r;
          framed = false;
          document.querySelector('.frame[data-frame="picker"]').style.display = "none";
          return r;
        }).then(posted);
      });
      rows.appendChild(row);
    });
  });
}
// ── reading as you type ──
const pending = new Map();
document.addEventListener("input", e => {
  const field = e.target.closest("[data-post]");
  if (!field) return;
  const win = field.closest(".frame");
  const area = win.querySelector("textarea[data-post]");
  if (!area) return;
  const route = area.dataset.post;
  clearTimeout(pending.get(route));
  pending.set(route, setTimeout(() => {
    pending.delete(route);
    const start = win.querySelector('input[id^="c-start-"]');
    const ns = win.querySelector('input[id^="c-ns-"]');
    const q = new URLSearchParams();
    if (start && start.value.trim()) q.set("start", start.value.trim());
    if (ns && ns.value.trim()) q.set("non_semantic", ns.value.trim());
    const qs = q.toString();
    fetch(route + (qs ? "?" + qs : ""), {method: "POST", body: area.value})
      .then(posted);
  }, 450));
});
// ── the bar: a picker, new texts, a frozen artifact ──
let ghost = null;
document.addEventListener("pointerdown", e => {
  const src = e.target.closest(".bnode[data-spawn]");
  if (!src) return;
  e.preventDefault();
  ghost = src.cloneNode(true);
  ghost.classList.add("ghost");
  ghost.dataset.kind = src.dataset.spawn;
  document.body.appendChild(ghost);
  ghost.style.left = (e.clientX - 30) + "px";
  ghost.style.top = (e.clientY - 20) + "px";
});
addEventListener("pointermove", e => {
  if (!ghost) return;
  ghost.style.left = (e.clientX - 30) + "px";
  ghost.style.top = (e.clientY - 20) + "px";
});
addEventListener("pointerup", e => {
  if (!ghost) return;
  const kind = ghost.dataset.kind;
  ghost.remove(); ghost = null;
  if (e.target.closest(".frame, .bar")) { toast("drop it on the canvas"); return; }
  fetch("/new", {method: "POST", body: kind}).then(posted);
});
document.addEventListener("click", e => {
  const act = e.target.closest("[data-act]");
  if (act) {
    if (act.dataset.act === "picker") {
      const f = window.opsisCamera.toggle("picker");
      if (f && f.style.display !== "none") browse("");
    }
    if (act.dataset.act === "freeze") freeze();
    return;
  }
  const ring = e.target.closest(".nd.ring[data-reading]");
  const off = e.target.closest(".act.unplug");
  const gone = e.target.closest(".act.remove");
  if (off && ring) {
    fetch("/unplug/" + ring.dataset.reading, {method: "POST", body: ""}).then(posted);
  } else if (gone && ring) {
    fetch("/remove/" + ring.dataset.reading, {method: "POST", body: ""}).then(posted);
  }
});
// ── dropping one node on another ──
window.opsisLanding = (el, cx, cy) => {
  for (const hit of document.elementsFromPoint(cx, cy)) {
    const node = hit.closest(".nd.ring[data-reading]");
    if (node && node !== el) return node;
  }
  return null;
};
window.opsisDrop = (el, cx, cy) => {
  const onto = window.opsisLanding(el, cx, cy);
  if (!onto) return;
  fetch(`/drop/${el.dataset.reading}/${onto.dataset.reading}`,
        {method: "POST", body: ""}).then(posted);
};
// ── a frozen artifact: the page as it stands, gestures dead ──
function freeze() {
  const clone = document.documentElement.cloneNode(true);
  clone.querySelector("body").classList.add("frozen");
  const blob = new Blob(["<!DOCTYPE html>" + clone.outerHTML], {type: "text/html"});
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "opsis.html";
  a.click();
  URL.revokeObjectURL(a.href);
}
// ── text ↔ tree: a node lights the span it covers ──
document.addEventListener("pointerover", e => {
  const row = e.target.closest(".twig[data-from]");
  if (!row) return;
  const pane = row.closest(".twin");
  const target = pane && pane.querySelector(".target");
  if (!target) return;
  if (target.dataset.plain === undefined) target.dataset.plain = target.textContent;
  const text = target.dataset.plain;
  const a = +row.dataset.from, b = +row.dataset.to;
  target.textContent = "";
  target.appendChild(document.createTextNode(text.slice(0, a)));
  const lit = document.createElement("mark");
  lit.textContent = text.slice(a, b);
  target.appendChild(lit);
  target.appendChild(document.createTextNode(text.slice(b)));
});
// ── trees open and shut ──
document.addEventListener("click", e => {
  const twig = e.target.closest(".twig.kids b");
  if (!twig) return;
  const row = twig.closest(".twig");
  const shut = !row.classList.contains("shut");
  row.classList.toggle("shut", shut);
  twig.textContent = shut ? "▸" : "▾";
  const prefix = row.dataset.path + ".";
  row.parentElement.querySelectorAll(".twig").forEach(other => {
    if (!other.dataset.path.startsWith(prefix)) return;
    if (shut) { other.classList.add("hide"); return; }
    const rest = other.dataset.path.slice(prefix.length).split(".");
    let path = row.dataset.path, visible = true;
    for (const step of rest.slice(0, -1)) {
      path += "." + step;
      const mid = row.parentElement.querySelector(`.twig[data-path="${path}"]`);
      if (mid && mid.classList.contains("shut")) { visible = false; break; }
    }
    other.classList.toggle("hide", !visible);
  });
});
// ── the bar itself drags ──
const bar = document.getElementById("bar");
bar.addEventListener("pointerdown", e => {
  if (e.target.closest("[data-act], [data-spawn]")) return;
  const r = bar.getBoundingClientRect();
  bar.style.left = r.left + "px"; bar.style.top = r.top + "px";
  bar.style.bottom = "auto"; bar.style.transform = "none";
  const sx = e.clientX - r.left, sy = e.clientY - r.top;
  const move = ev => {
    bar.style.left = (ev.clientX - sx) + "px";
    bar.style.top = (ev.clientY - sy) + "px";
  };
  const up = () => {
    removeEventListener("pointermove", move);
    removeEventListener("pointerup", up);
  };
  addEventListener("pointermove", move);
  addEventListener("pointerup", up);
});
"""
"""The session's own gestures. Window chrome, wires, folding and deixis
belong to the camera; neither script registers the other's listeners."""


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
        session.add(name, "manifest", notation, text, f"lexic ships {name}")
