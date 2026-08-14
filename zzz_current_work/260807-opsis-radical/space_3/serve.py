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

__all__ = ["Handler", "Instrument", "Server", "main"]

FILES = {".html": "text/html", ".js": "text/javascript", ".css": "text/css"}


class RoomWork:
    """Derived work and window overlays for one relation instance."""

    __slots__ = ("key", "other", "rows", "windows")

    def __init__(self) -> None:
        self.key: tuple[int, int] = (-1, -1)
        self.rows: list[list[object]] = []
        self.other = Routes()
        self.windows: dict[str, dict[str, str]] = {}


class Instrument:
    """One server-owned session and its relation-keyed derived work.

    The predictive run over the whole document is the same answer for every
    surface that asks and for every frame until the text changes, so it is
    kept against the reading that produced it rather than re-run per gesture.
    """

    __slots__ = ("focus", "here", "rooms")

    def __init__(self, session: Session) -> None:
        self.here = session
        self.focus = session.graph.focus
        self.rooms: dict[str, RoomWork] = {self.focus: RoomWork()}

    def room(self) -> RoomWork:
        """Work for the focused relation, migrating it across a successful edit."""
        focus = self.here.graph.focus
        if focus != self.focus and self.focus not in self.here.graph.relations:
            self.rooms[focus] = self.rooms.pop(self.focus, RoomWork())
        self.focus = focus
        return self.rooms.setdefault(focus, RoomWork())

    def layer(self, window: str) -> MutableMapping[str, str]:
        """What this window is looking through — its own layer, then the session's."""
        if not window:
            return self.here.main
        return ChainMap(self.room().windows.setdefault(window, {}), self.here.main)

    def watched(self) -> list[list[object]]:
        """What the predictive machine did to this document."""
        room = self.room()
        key = (self.here.generation, len(self.here.reading.text))
        if room.key != key:
            machine = reader_of(self.here.reading)
            room.key = key
            room.rows = (
                watch(machine, self.here.reading.text) if machine is not None else []
            )
        return room.rows


class Server(ThreadingHTTPServer):
    """A socket with one explicit instrument owner."""

    def __init__(
        self,
        address: tuple[str, int],
        instrument: Instrument,
    ) -> None:
        self.instrument = instrument
        super().__init__(address, Handler)


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
        if not isinstance(self.server, Server):
            raise RuntimeError("frame handler has no instrument")
        held = self.server.instrument
        session = held.here
        session.viewport = (wide, tall)
        state = held.layer(window)
        if gesture:
            session.gesture(gesture, said, state)
        # The page always composes through the session layer; only a dedicated
        # `?only=...&win=...` document composes through one window. Otherwise
        # changing a clone would repaint the main grid through the clone's view.
        composed = state if only else session.main
        alive = set(session.main.get("windows", "").split())
        work = held.room()
        for gone in [wid for wid in work.windows if wid not in alive]:
            work.windows.pop(gone, None)
        # the road not taken, started once per reading and drawn while it runs
        work.other.ask(
            reader_of(session.reading), session.reading.text, session.generation
        )
        drawn = compose(
            session.reading,
            wide,
            tall,
            session.at,
            composed,
            held.watched(),
            session.generation,
            climbed=session.climbed,
            typed=session.typed,
            frontier=session.frontier(),
            routes=work.other.line(),
            only=only,
            layers=work.windows,
        )
        # what the frame WORKED OUT belongs to the session: the lanes' window
        # depends on a width only the frame has, and a window recomputed from
        # the cursor every time slides out from under the hand
        for address, value in drawn.reported.items():
            scope, divided, key = address.partition("~")
            if divided:
                held.layer(scope)[key] = value
            else:
                composed[key] = value
        self.send(drawn.wire(session.generation, session.playing))


def main() -> None:
    """Read the pair named on the command line, then serve frames of it."""
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) < 2:
        print("usage: serve.py <grammar> <document> [port]")
        raise SystemExit(2)
    reading = Reading(Path(args[0]), Path(args[1]))
    reading.hold()
    instrument = Instrument(Session(reading))
    port = int(args[2]) if len(args) > 2 else 8918
    print(f"opsis · {args[0]} ⊳ {args[1]} · http://127.0.0.1:{port}/")
    Server(("127.0.0.1", port), instrument).serve_forever()


if __name__ == "__main__":
    main()
