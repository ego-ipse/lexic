"""The live loop — a loopback-only stdlib HTTP server around one Praxis.

Routes: ``GET /`` the live shell; ``POST /compile`` (raw grammar text,
flavour as a query parameter) answering with the rendered section
fragments, or 422 and the error text; ``GET /freeze`` the session as a
self-contained artifact. A local instrument, not a service: binds
``127.0.0.1``, single session, body size capped. No serialization in
either direction — text up, markup down.
"""

from __future__ import annotations

import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from opsis.praxis import Praxis
from opsis.shell import artifact, fragments, live_page

_MAX_BODY = 2 * 1024 * 1024


class _Handler(BaseHTTPRequestHandler):
    """Thin praxis dispatch — no state of its own."""

    server: "OpsisServer"

    def do_GET(self) -> None:  # noqa: N802 — http.server's contract
        praxis = self.server.praxis
        if self.path == "/":
            self._send(live_page(praxis.source, praxis.flavour, praxis.sections,
                                 praxis.input))
        elif self.path == "/freeze":
            if not praxis.sections:
                self._send("nothing compiled yet", code=409, kind="text/plain")
            else:
                self._send(
                    artifact(praxis.source, praxis.flavour, praxis.sections,
                             praxis.input),
                    download="opsis.html",
                )
        else:
            self.send_error(404)

    def do_POST(self) -> None:  # noqa: N802 — http.server's contract
        url = urlsplit(self.path)
        if url.path not in ("/compile", "/parse"):
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", 0))
        if length > _MAX_BODY:
            self.send_error(413)
            return
        try:
            text = self.rfile.read(length).decode("utf-8")
        except UnicodeDecodeError:
            self._send("body is not UTF-8", code=400, kind="text/plain")
            return
        if url.path == "/compile":
            flavour = parse_qs(url.query).get("flavour", ["gbnf"])[0]
            sections = self.server.praxis.compile(text, flavour)
        else:
            sections = self.server.praxis.parse(text)
        if "error" in sections:
            self._send(sections["error"], code=422, kind="text/plain")
        else:
            self._send(fragments(sections))

    def _send(self, body: str, code: int = 200, kind: str = "text/html",
              download: str | None = None) -> None:
        data = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", f"{kind}; charset=utf-8")
        if download is not None:
            self.send_header("Content-Disposition", f'attachment; filename="{download}"')
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format: str, *args: object) -> None:
        """Quiet — the terminal is the user's, not the access log's."""


class OpsisServer(ThreadingHTTPServer):
    """The loopback server owning one praxis session."""

    def __init__(self, praxis: Praxis, port: int = 0) -> None:
        super().__init__(("127.0.0.1", port), _Handler)
        self.praxis = praxis


def serve(praxis: Praxis, port: int = 0, *, open_browser: bool = True) -> OpsisServer:
    """Start the live loop; returns the running server (caller owns shutdown)."""
    server = OpsisServer(praxis, port)
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    print(f"opsis live at {url}  (Ctrl-C to stop)")
    if open_browser:
        webbrowser.open(url)
    return server
