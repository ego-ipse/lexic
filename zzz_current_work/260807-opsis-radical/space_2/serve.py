"""The instrument, over one socket — a size and a gesture in, a frame out.

One route. The leaf posts how big its paper is and what the hand just did;
what comes back is the whole instrument as final pixels, hit rectangles and
the text planes the browser draws itself. There is nothing else to ask for,
because there is nothing left for the leaf to decide.
"""

from __future__ import annotations

import sys
from collections import ChainMap
from collections.abc import MutableMapping
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from kairos.parse import watch  # noqa: E402
from opsis.frame import compose  # noqa: E402
from opsis.scene import reader_of  # noqa: E402
from praxis.reading import Reading  # noqa: E402
from praxis.routes import Routes  # noqa: E402
from praxis.session import Session  # noqa: E402

__all__ = ["Handler", "main"]

FILES = {".html": "text/html", ".js": "text/javascript", ".css": "text/css"}


class Held:
    """The one session this socket serves, and what has been worked out about it.

    The predictive run over the whole document is the same answer for every
    surface that asks and for every frame until the text changes, so it is
    kept against the reading that produced it rather than re-run per gesture.
    """

    here: Session
    key: tuple[int, int] = (-1, -1)
    rows: list[list[object]] = []
    other: Routes = Routes()
    # a window's own layer over the session's policy — its view, its camera,
    # its scroll. The cursor is NOT in here: it is a cursor on the subject,
    # and the whole point of it is being visible everywhere at once.
    windows: dict[str, dict[str, str]] = {}

    @classmethod
    def layer(cls, window: str) -> MutableMapping[str, str]:
        """What this window is looking through — its own layer, then the session's."""
        if not window:
            return cls.here.main
        return ChainMap(cls.windows.setdefault(window, {}), cls.here.main)

    @classmethod
    def watched(cls) -> list[list[object]]:
        """What the predictive machine did to this document."""
        key = (cls.here.generation, len(cls.here.reading.text))
        if cls.key != key:
            machine = reader_of(cls.here.reading)
            cls.key = key
            cls.rows = (
                watch(machine, cls.here.reading.text) if machine is not None else []
            )
        return cls.rows


class Handler(BaseHTTPRequestHandler):
    """One socket over one reading."""

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        return

    def send(self, body: str, kind: str = "text/plain") -> None:
        raw = body.encode()
        self.send_response(200)
        self.send_header("Content-Type", f"{kind}; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:  # noqa: N802
        name = urlparse(self.path).path.lstrip("/") or "index.html"
        here = HERE / "leaf" / name
        if here.is_file() and here.suffix in FILES:
            self.send(here.read_text(), FILES[here.suffix])
            return
        self.send_error(404)

    def do_POST(self) -> None:  # noqa: N802
        if urlparse(self.path).path != "/frame":
            self.send_error(404)
            return
        body = self.rfile.read(int(self.headers.get("Content-Length", 0))).decode()
        wide, tall, only, window, gesture, said = 1400, 800, "", "", "", ""
        lines = body.split("\n")
        for i, line in enumerate(lines):
            word, _, rest = line.partition(" ")
            if word == "size" and len(rest.split()) == 2:
                wide, tall = (int(n) for n in rest.split())
            elif word == "only":
                only = rest.strip()
            elif word == "win":
                window = rest.strip()
            elif line.strip():
                # a gesture that carries text carries ALL of it: the rest of
                # the body is the payload, newlines and all
                gesture, said = line.strip(), "\n".join(lines[i + 1 :])
                break
        session = Held.here
        state = Held.layer(window)
        if gesture:
            session.gesture(gesture, said, state)
        # the road not taken, started once per reading and drawn while it runs
        Held.other.ask(
            reader_of(session.reading), session.reading.text, session.generation
        )
        self.send(
            compose(
                session.reading,
                wide,
                tall,
                session.at,
                state,
                Held.watched(),
                session.generation,
                climbed=session.climbed,
                typed=session.typed,
                frontier=session.frontier(),
                routes=Held.other.line(),
                only=only,
            ).wire(session.generation)
        )


def main() -> None:
    """Read the pair named on the command line, then serve frames of it."""
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) < 2:
        print("usage: serve.py <grammar> <document> [port]")
        raise SystemExit(2)
    reading = Reading(Path(args[0]), Path(args[1]))
    reading.hold()
    Held.here = Session(reading)
    port = int(args[2]) if len(args) > 2 else 8918
    print(f"opsis · {args[0]} ⊳ {args[1]} · http://127.0.0.1:{port}/")
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()


if __name__ == "__main__":
    main()
