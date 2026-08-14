"""The instrument, over one socket — a size and a gesture in, a frame out.

One route. The leaf posts how big its paper is and what the hand just did;
what comes back is the whole instrument as final pixels, hit rectangles and
the text planes the browser draws itself. There is nothing else to ask for,
because there is nothing left for the leaf to decide.
"""

from __future__ import annotations

import sys
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from collections import ChainMap
from collections.abc import MutableMapping
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from kairos.artefacts import Artefacts  # noqa: E402
from kairos.parse import watch  # noqa: E402
from opsis.frame import compose  # noqa: E402
from opsis.frame.landing import draw as landing_draw  # noqa: E402
from opsis.frame.landing import draw_value as landing_value  # noqa: E402
from opsis.frame.marks import Frame  # noqa: E402
from opsis.scene import reader_of  # noqa: E402
from praxis.ingress import Ingress, Payload  # noqa: E402
from praxis.reading import Reading  # noqa: E402
from praxis.routes import Routes  # noqa: E402
from praxis.session import Session  # noqa: E402
from lexic.ir import IrSelf  # noqa: E402

__all__ = ["Handler", "Instrument", "Server", "main"]

FILES = {".html": "text/html", ".js": "text/javascript", ".css": "text/css"}


class RoomWork:
    """Derived work and window overlays for one relation instance."""

    __slots__ = ("artefacts", "key", "other", "rows", "windows")

    def __init__(self) -> None:
        self.artefacts = Artefacts()
        self.key: tuple[int, int] = (-1, -1)
        self.rows: list[list[object]] = []
        self.other = Routes()
        self.windows: dict[str, dict[str, str]] = {}


@dataclass(frozen=True, slots=True)
class ValueFocus:
    """A live file value and the reader answer that produced it."""

    value: object
    name: str
    reader: str


class Instrument:
    """One server-owned graph, landing, history, workers, and reading rooms."""

    __slots__ = (
        "_executor",
        "focus",
        "here",
        "history",
        "ingress",
        "mode",
        "notice",
        "pending",
        "pending_label",
        "rooms",
        "value",
    )

    def __init__(self, session: Session | None, ingress: Ingress | None = None) -> None:
        self.here = session
        self.ingress = ingress
        self.mode = "reading" if session is not None else "landing"
        self.focus = session.graph.focus if session is not None else ""
        self.rooms: dict[str, RoomWork] = {self.focus: RoomWork()} if self.focus else {}
        self.history: list[tuple[str, object | None]] = []
        self.value: ValueFocus | None = None
        self.pending: Future[Session] | None = None
        self.pending_label = ""
        self.notice = ""
        self._executor = ThreadPoolExecutor(
            max_workers=2, thread_name_prefix="opsis-cast"
        )

    def room(self) -> RoomWork:
        """Work for the focused relation, migrating it across a successful edit."""
        if self.here is None:
            raise RuntimeError("a non-reading mode has no reading room")
        focus = self.here.graph.focus
        if focus != self.focus and self.focus not in self.here.graph.relations:
            self.rooms[focus] = self.rooms.pop(self.focus, RoomWork())
        self.focus = focus
        return self.rooms.setdefault(focus, RoomWork())

    def layer(self, window: str) -> MutableMapping[str, str]:
        """What this window is looking through — its own layer, then the session's."""
        if self.here is None:
            raise RuntimeError("a non-reading mode has no presentation layer")
        if not window:
            return self.here.main
        return ChainMap(self.room().windows.setdefault(window, {}), self.here.main)

    def watched(self) -> list[list[object]]:
        """What the predictive machine did to this document."""
        if self.here is None:
            return []
        room = self.room()
        key = (self.here.generation, len(self.here.reading.text))
        if room.key != key:
            machine = reader_of(self.here.reading)
            room.key = key
            room.rows = watch(machine, self.here.reading.text) if machine else []
        return room.rows

    def _snapshot(self) -> tuple[str, object | None]:
        if self.mode == "reading":
            return self.mode, self.here
        if self.mode == "value":
            return self.mode, self.value
        return "landing", None

    def _enter(self, mode: str, value: object | None = None) -> None:
        self.history.append(self._snapshot())
        self.mode = mode
        self.notice = ""
        if mode == "reading" and isinstance(value, Session):
            self.here = value
            self.focus = value.graph.focus
            self.rooms.setdefault(self.focus, RoomWork())
        elif mode == "value" and isinstance(value, ValueFocus):
            self.value = value

    def _back(self) -> None:
        if not self.history:
            return
        mode, value = self.history.pop()
        self.mode = mode
        self.notice = ""
        if mode == "reading" and isinstance(value, Session):
            self.here = value
        elif mode == "value" and isinstance(value, ValueFocus):
            self.value = value

    @staticmethod
    def _read(reader: Path, document: Path, flavour: str) -> Session:
        held = Reading(reader, document, flavour)
        held.hold()
        return Session(held)

    def _start_read(self, words: list[str]) -> None:
        if self.ingress is None or len(words) < 4 or self.pending is not None:
            return
        try:
            reader_at, document_at = int(words[1]), int(words[2])
            reader = self.ingress.entries[reader_at]
            document = self.ingress.entries[document_at]
        except IndexError, ValueError:
            return
        if reader.subject is None or document.subject is None:
            return
        self.history.append(self._snapshot())
        self.mode = "pending"
        self.pending_label = f"{reader.path.name} ⊳ {document.path.name}"
        self.pending = self._executor.submit(
            self._read, reader.path, document.path, words[3]
        )

    def poll(self) -> None:
        """Promote completed file and cast work without blocking a frame."""
        if self.ingress is not None:
            self.ingress.poll()
        if self.pending is None or not self.pending.done():
            return
        try:
            session = self.pending.result()
        except Exception as refusal:  # noqa: BLE001 — visible refusal
            self.mode = "landing"
            self.notice = str(refusal)
        else:
            self.mode = "reading"
            self.here = session
            self.focus = session.graph.focus
            self.rooms.setdefault(self.focus, RoomWork())
        self.pending = None
        self.pending_label = ""

    def navigate(self, gesture: str) -> bool:
        """Apply map/value/history gestures; return whether one was consumed."""
        words = gesture.strip().split()
        if self.ingress is not None and words == ["at", "strata", "on"]:
            self._enter("landing")
            return True
        if len(words) != 3 or words[:2] != ["at", "ingress"]:
            return False
        action, *arguments = words[2].split(":")
        if action == "back":
            self._back()
        elif action == "map":
            self._enter("landing")
        elif action == "read" and len(arguments) == 3:
            self._start_read([action, *arguments])
        elif (
            action == "payload"
            and self.ingress is not None
            and len(arguments) == 1
            and arguments[0].isdigit()
        ):
            self.ingress.import_at(int(arguments[0]))
        elif action == "value" and len(arguments) == 2:
            self._open_value(arguments)
        elif action == "payloadvalue" and len(arguments) == 2:
            self._open_payload(arguments)
        elif action == "door" and len(arguments) == 1:
            self._open_door(arguments)
        else:
            return False
        return True

    def _open_value(self, words: list[str]) -> None:
        if self.ingress is None or len(words) < 2:
            return
        try:
            entry = self.ingress.entries[int(words[0])]
            answer = entry.subject.probes[int(words[1])] if entry.subject else None
        except IndexError, ValueError:
            return
        if answer is not None and answer.accepted:
            self._enter(
                "value", ValueFocus(answer.value, entry.path.name, answer.reader)
            )

    def _open_payload(self, words: list[str]) -> None:
        if self.ingress is None or len(words) < 2:
            return
        try:
            entry = self.ingress.entries[int(words[0])]
        except IndexError, ValueError:
            return
        loaded = (
            entry.payload.value if entry.payload and entry.payload.accepted else None
        )
        if not isinstance(loaded, Payload):
            return
        value = getattr(loaded.module, words[1], None)
        self._enter(
            "value", ValueFocus(value, f"{entry.path.name}:{words[1]}", "payload")
        )

    def _open_door(self, words: list[str]) -> None:
        if self.ingress is None or not words or not words[0].isdigit():
            return
        try:
            door = self.ingress.doors[int(words[0])]
        except IndexError:
            return
        paths = sorted(path for path in door.iterdir() if path.is_file())
        old = self.ingress
        self.ingress = Ingress(paths, old.doors)
        old.close()
        self.mode = "landing"
        self.history.clear()

    def special(self, wide: int, tall: int) -> Frame | None:
        """A non-reading frame, or none when the reading room should compose."""
        self.poll()
        if self.ingress is None:
            return None
        if self.mode in ("landing", "pending"):
            pending = self.pending_label if self.mode == "pending" else self.notice
            return landing_draw(
                self.ingress, wide, tall, history=bool(self.history), pending=pending
            )
        if self.mode == "value" and self.value is not None:
            if isinstance(self.value.value, IrSelf):
                return landing_value(
                    self.value.value, self.value.name, self.value.reader, wide, tall
                )
            self.mode = "landing"
            self.notice = "the selected payload is not an IrSelf value"
            return landing_draw(self.ingress, wide, tall, history=bool(self.history))
        return None

    def working(self) -> bool:
        """Whether server-owned work needs the leaf to request another frame."""
        if self.pending is not None:
            return True
        ingress = self.ingress is not None and any(
            entry.pending or entry.payload_pending for entry in self.ingress.entries
        )
        return ingress or any(room.artefacts.pending for room in self.rooms.values())

    def close(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)
        if self.ingress is not None:
            self.ingress.close()


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
        held.poll()
        if gesture and held.navigate(gesture):
            gesture = ""
        special = held.special(wide, tall)
        if special is not None:
            self.send(special.wire(0, False, held.working()))
            return
        session = held.here
        if session is None:
            raise RuntimeError("reading mode has no session")
        session.viewport = (wide, tall)
        state = held.layer(window)
        if gesture:
            session.gesture(gesture, said, state)
        composed = state if only else session.main
        alive = set(session.main.get("windows", "").split())
        work = held.room()
        for gone in [wid for wid in work.windows if wid not in alive]:
            work.windows.pop(gone, None)
        machine = reader_of(session.reading)
        work.other.ask(machine, session.reading.text, session.generation)
        made = None
        if composed.get("place") == "artefacts":
            work.artefacts.ask(
                machine,
                session.reading.text,
                session.reading.identity,
                session.generation,
            )
            made = work.artefacts.line()
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
            artefacts=made,
        )
        for address, value in drawn.reported.items():
            scope, divided, key = address.partition("~")
            if divided:
                held.layer(scope)[key] = value
            else:
                composed[key] = value
        self.send(drawn.wire(session.generation, session.playing, held.working()))


def main() -> None:
    """Serve any file set at the map; `--direct` preserves the pair harness."""
    direct = "--direct" in sys.argv[1:]
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    port = 8918
    if args and args[-1].isdigit():
        port = int(args.pop())
    paths = [Path(arg) for arg in args]
    root = HERE.parents[2]
    doors = tuple(
        path for path in (HERE / "fixtures", root / "generated") if path.is_dir()
    )
    ingress = Ingress(paths, doors)
    session: Session | None = None
    if direct:
        if len(paths) != 2:
            print("usage: serve.py --direct <grammar> <document> [port]")
            raise SystemExit(2)
        reading = Reading(paths[0], paths[1])
        reading.hold()
        session = Session(reading)
    instrument = Instrument(session, ingress)
    named = " · ".join(str(path) for path in paths) or "empty landing"
    print(f"opsis · {named} · http://127.0.0.1:{port}/")
    try:
        Server(("127.0.0.1", port), instrument).serve_forever()
    finally:
        instrument.close()


if __name__ == "__main__":
    main()
