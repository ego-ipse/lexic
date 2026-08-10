"""The socket. It resolves a path and writes what something else spelled.

Run from the repo root::

    uv run python .../space_1/serve.py <grammar> <document> [port]
    uv run python .../space_1/serve.py <grammar> <document> --gate

The leaf is kept as it stands; the adjustment is here. A route this
instrument cannot yet answer says so in words — pending is a sentence, never
a blank.
"""

from __future__ import annotations

import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import clocks  # noqa: E402
import machine  # noqa: E402
import places  # noqa: E402
import scene as scenes  # noqa: E402
import strata as maps  # noqa: E402
import viewing  # noqa: E402, F401 — importing registers the kind
from reading import Reading, Turn, turn  # noqa: E402, F401 — registers the kind
from relate import DOCUMENT, READER, Session, Text  # noqa: E402

__all__ = ["Handler", "gate", "main", "open_session"]

FILES = {".html": "text/html", ".css": "text/css", ".js": "text/javascript"}

# What this instrument does not derive yet. The leaf polls them; each says
# what it is instead of failing, so a missing capability reads as missing.
PENDING = {
    "/routes": "primary the engine's own composition\nprimary_seconds 0.00\n"
    "status pending\n",
    "/rails": "",
}


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
        self.send(artifact.read_text(), FILES.get(artifact.suffix, "text/plain"))
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
        """The focused reading, the map of rooms, the policy, the honest rest."""
        session = self.session
        if path == "/scene":
            return scenes.scene(session, session.focus)
        if path == "/strata":
            return maps.frame(session)
        if path == "/policy":
            return "".join(f"{k} {v}\n" for k, v in session.policy.items())
        if path == "/clock":
            turned = self.reader()
            relation = session.relations.get(session.focus)
            if turned is None or not isinstance(relation, Reading):
                return None
            return clocks.pda_clock(turned.machine, relation.document())
        if path == "/column":
            turned = self.reader()
            relation = session.relations.get(session.focus)
            if turned is None or not isinstance(relation, Reading):
                return None
            return clocks.column(
                turned.machine, relation.document(), int(query.get("i", "0"))
            )
        if path == "/automaton":
            turned = self.reader()
            return machine.automaton(turned.machine.pda_tables()) if turned else None
        if path == "/verdicts":
            turned = self.reader()
            return machine.verdicts(turned.machine) if turned else None
        if path == "/place":
            return places.frame(session, query.get("id", ""))
        if path == "/irvalue":
            room = session.relations.get(query.get("place", ""))
            return room.frame() if isinstance(room, viewing.Viewing) else None
        return PENDING.get(path)

    def reader(self) -> Turn | None:
        """The focused reading's reader, as a machine — or nothing to ask."""
        relation = self.session.relations.get(self.session.focus)
        if not isinstance(relation, Reading):
            return None
        return turn(relation.cast[READER.name])

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length).decode("utf-8")
        self.send(self.took(urlparse(self.path).path, body))

    def took(self, path: str, body: str) -> str:
        """A gesture: policy written, focus moved, a cursor noted."""
        session = self.session
        if path == "/policy":
            for line in body.splitlines():
                key, _, value = line.partition(" ")
                if value == "-":
                    session.policy.pop(key, None)
                else:
                    session.policy[key] = value
            return "ok\n"
        if path == "/focus":
            return self.travel(int(body.strip() or "0"))
        if path == "/cursor":
            return "ok\n"
        return "refuse unknown route\n"

    def travel(self, place: int) -> str:
        """One index into the map: focus it, and hold it if it was a ghost."""
        session = self.session
        order = maps.cards(session)
        if not 0 <= place < len(order):
            return "refuse no such rung\n"
        session.focus = order[place]
        session.relations[session.focus].hold()
        return "ok\n"


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
    drawn = scenes.scene(session, base.rid) or ""
    check(
        "the scene carries the reader, the document, the spans and the graph",
        all(tag in drawn for tag in ("#READER ", "#DOC ", "#SPANS ", "#EDGES ")),
        f"{len(drawn):,} chars",
    )
    picture = maps.frame(session)
    ghosts = [line for line in picture.splitlines() if line.startswith("c ")]
    check(
        "the map holds ghosts — instances licensed but not yet visited",
        any(row.split(" ")[5] == "0" for row in ghosts),
        f"{len(ghosts)} cards",
    )
    before = len(session.relations)
    session.relations[maps.cards(session)[1]].hold()
    check(
        "holding a ghost costs a parse, not a new node",
        len(session.relations) == before,
        f"{before} relations",
    )
    check(
        "a miss is said in words, not drawn as a blank",
        scenes.scene(session, "nope") is None,
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
