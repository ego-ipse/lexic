"""The socket — files out, frames out, gestures in. Nothing else.

    uv run python .../space_2/serve.py <grammar> <document> [port]

space_1's derivation is here whole; what changed is where the picture is
assembled. One route answers with the instrument drawn, and the leaf holds
no geometry to disagree with it.
"""

from __future__ import annotations

import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from opsis.frame import compose  # noqa: E402
from praxis.reading import read  # noqa: E402
from praxis.session import Session  # noqa: E402


class SESSION:
    """The one session this socket serves."""

    here: Session


__all__ = ["Handler", "main"]

FILES = {".html": "text/html", ".js": "text/javascript", ".css": "text/css"}


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
        # one line per thing said: how big the paper is, which room this
        # window is (a popped-out one is only ever one), and what the hand did
        wide, tall, only, gesture = 1400, 800, "", ""
        for line in body.split("\n"):
            word, _, rest = line.strip().partition(" ")
            if word == "size" and len(rest.split()) == 2:
                wide, tall = (int(n) for n in rest.split())
            elif word == "only":
                only = rest.strip()
            elif line.strip():
                gesture = line.strip()
        if gesture:
            SESSION.here.gesture(gesture)
        self.send(
            compose(
                SESSION.here.reading,
                wide,
                tall,
                SESSION.here.at,
                SESSION.here,
                only,
            ).wire(SESSION.here.generation)
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
        f"{reading.seconds:.2f}s · {len(reading.spans):,} spans"
    )
    SESSION.here = Session(reading)
    print(f"http://127.0.0.1:{port}/")
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
