"""The socket — it serves a frame and receives a gesture. Nothing else.

Run from the repo root::

    uv run python .../space_2/serve.py <grammar> <document> [port]

Every request is the same shape: the leaf says how big it is and what the
hand just did; this answers with the whole instrument, drawn. Where space_1
had a wire of a dozen routes and a leaf that assembled a picture from them,
there is one route here and the leaf assembles nothing.
"""

from __future__ import annotations

import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from frame import frame  # noqa: E402
from read.reading import Reading, read  # noqa: E402

__all__ = ["Handler", "main"]

FILES = {".html": "text/html", ".js": "text/javascript", ".css": "text/css"}


class Session:
    """What the hand has done so far — the only state there is."""

    reading: Reading
    at: float = 0.0
    reader_top: int = 0
    doc_top: int = 0
    playing: bool = False
    generation: int = 1

    @classmethod
    def gesture(cls, said: str, wide: int, tall: int) -> None:
        """One gesture, applied. The leaf knows none of this arithmetic."""
        word, _, rest = said.strip().partition(" ")
        length = len(cls.reading.text)
        if word == "point":
            # a point in the derivation is a time; the picture's own pitch
            # is known here, so the leaf never converts pixels to offsets
            parts = rest.split()
            if len(parts) == 2 and parts[0].lstrip("-").isdigit():
                x = int(parts[0])
                left = wide * 0.34 + wide * 0.32
                pitch = 5.0
                window = max(8, int((wide - left - 20) / pitch))
                start = max(
                    0, min(int(cls.at) - int(window * 0.6), max(0, length - window))
                )
                if x >= left:
                    cls.at = max(0.0, min(start + (x - left - 10) / pitch, length))
        elif word == "at":
            kind, _, address = rest.partition(" ")
            if kind == "span" and ":" in address:
                cls.at = float(address.split(":")[0])
            elif kind == "line" and address.isdigit():
                cls.doc_top = int(address)
        elif word == "step":
            cls.at = max(0.0, min(cls.at + float(rest or 1), length))
        elif word == "go":
            cls.at = float(length if rest == "end" else 0)
        elif word == "play":
            cls.playing = not cls.playing
        elif word == "tick" and cls.playing:
            cls.at = min(cls.at + length / 90, length)
            cls.playing = cls.at < length


class Handler(BaseHTTPRequestHandler):
    """One socket over one reading: files out, frames out, gestures in."""

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
        path = urlparse(self.path).path
        name = "index.html" if path in ("/", "") else path.lstrip("/")
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
        head, _, gesture = body.partition("\n")
        parts = head.split()
        wide = int(parts[1]) if len(parts) > 2 and parts[1].isdigit() else 1400
        tall = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 800
        if gesture.strip():
            Session.gesture(gesture, wide, tall)
        self.send(
            frame(
                Session.reading,
                wide,
                tall,
                Session.at,
                Session.reader_top,
                Session.doc_top,
            ).wire(Session.generation)
        )


def main() -> int:
    """Read the pair, then serve frames of it."""
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    if len(args) < 2:
        print("serve.py <grammar> <document> [port]")
        return 2
    reading = read(Path(args[0]), Path(args[1]))
    port = int(args[2]) if len(args) > 2 else 8918
    print(
        f"{reading.reader_name} read {len(reading.text):,} chars in "
        f"{reading.seconds:.2f}s · {len(reading.spans):,} spans · "
        f"faithful {reading.faithful}"
    )
    Session.reading = reading
    print(f"http://127.0.0.1:{port}/")
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
