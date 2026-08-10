"""The socket. It resolves a path and writes what something else spelled.

Run from the repo root::

    uv run python .../space_1/serve.py <grammar> <document> [port]
    uv run python .../space_1/serve.py <grammar> <document> --gate
"""

from __future__ import annotations

import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from reading import Reading  # noqa: E402, F401 — importing registers the kind
from relate import DOCUMENT, READER, Session, Text  # noqa: E402

__all__ = ["Handler", "gate", "main", "open_session"]

KINDS = {".html": "text/html", ".css": "text/css", ".js": "text/javascript"}


def open_session(grammar: Path, document: Path) -> Session:
    """One reading, from two files. Everything else is reached by casting."""
    session = Session()
    reader = Text("t.reader", grammar.name, grammar.read_text(), grammar)
    doc = Text("t.document", document.name, document.read_text(), document)
    session.enter("reading", {READER.name: reader, DOCUMENT.name: doc})
    return session


class Handler(BaseHTTPRequestHandler):
    """One socket over a session. It serves; it does not know."""

    session: Session

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        """Silence: the instrument's own output is the interesting one."""

    def send(self, body: str, kind: str = "text/plain") -> None:
        data = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", f"{kind}; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def leaf(self, name: str) -> bool:
        """Any leaf artifact, as itself — versioned files, never a blob."""
        artifact = (HERE / "leaf" / name).resolve()
        if not artifact.is_file() or artifact.parent != (HERE / "leaf").resolve():
            return False
        self.send(artifact.read_text(), KINDS.get(artifact.suffix, "text/plain"))
        return True

    def do_GET(self) -> None:  # noqa: N802 — the base class names it
        url = urlparse(self.path)
        if self.leaf("index.html" if url.path == "/" else url.path.lstrip("/")):
            return
        query = {
            key: unquote(value)
            for key, value in (
                p.split("=", 1) for p in url.query.split("&") if "=" in p
            )
        }
        answer = self.answer(url.path, query)
        if answer is None:
            self.send_response(404)
            self.end_headers()
            return
        self.send(answer)

    def answer(self, path: str, query: dict[str, str]) -> str | None:
        """Three routes: what is here, what it can be asked, and where to go."""
        session = self.session
        if path == "/room":
            return session.frame(query.get("id") or session.focus)
        if path == "/ask":
            return session.ask(query)
        if path == "/cast":
            to = session.cast(
                query.get("room", session.focus),
                query.get("thing", ""),
                query.get("kind", ""),
                query.get("role", ""),
            )
            return f"#WENT {to}\n" if to else "#REFUSED that cast is not licensed\n"
        return None


def gate(session: Session) -> int:
    """What must hold, printed as facts, so a false one is visible."""
    failures: list[str] = []

    def check(name: str, holds: bool, note: str = "") -> None:
        print(
            f"{'holds' if holds else 'FAILS'} — {name}" + (f" · {note}" if note else "")
        )
        if not holds:
            failures.append(name)

    base = session.relations[session.focus]
    check(
        "the reading is faithful — it re-emits its own text",
        getattr(base, "faithful", False),
        f"{len(getattr(base, 'spans', [])):,} spans",
    )
    offers = session.offers(base.rid)
    readers = {o.thing.tid for o in offers if o.role.name == READER.name}
    check(
        "chirality is computed — the grammar has both hands, the document one",
        "t.reader" in readers and "t.document" not in readers,
        f"{len(offers)} licensed casts",
    )
    went = session.cast(base.rid, "t.reader", "reading", DOCUMENT.name)
    check(
        "a cast completes itself — the reader becomes a document, read by its own"
        " metagrammar",
        went is not None and went != base.rid,
        str(went),
    )
    if went:
        check(
            "the strip is derived from the edges, not stored",
            list(session.strip(went)) == [base.rid, went],
            " → ".join(session.strip(went)),
        )
    frame = session.frame(base.rid) or ""
    check(
        "the room spells four facets",
        frame.count("#FACET ") == 4,
        f"{frame.count('#FACET ')} facets",
    )
    check(
        "a miss is said in words, not drawn as a blank", session.frame("nope") is None
    )
    print(f"{len(session.relations)} relations · {len(failures)} failures")
    return 1 if failures else 0


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) < 2:
        print("usage: serve.py <grammar> <document> [port]")
        return 2
    session = open_session(Path(args[0]), Path(args[1]))
    if "--gate" in sys.argv:
        return gate(session)
    port = int(args[2]) if len(args) > 2 else 8917
    Handler.session = session
    print(f"space_1 at http://127.0.0.1:{port}/ — {len(session.relations)} relations")
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
