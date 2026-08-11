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

from opsis.frame import frame  # noqa: E402
from praxis.session import Session  # noqa: E402
from praxis.reading import read  # noqa: E402

__all__ = ["Handler", "main"]

FILES = {".html": "text/html", ".js": "text/javascript", ".css": "text/css"}


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
