"""The socket: the leaf's files, and one reading spelled for it.

Run from the repo root::

    uv run python .../space_1/serve.py <grammar> <document> [port]

The arrangement it sends is COMPUTED from what the surfaces measured
themselves to need, and it rides in the policy the leaf already interprets —
so the layout on screen is the measurement, not a shape someone liked.
"""

from __future__ import annotations

import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from chain import chain  # noqa: E402
from draw import graph_facet  # noqa: E402
from lexic.compile import compile_text  # noqa: E402
from machine import machine_facet  # noqa: E402
from place import ENOUGH, arrange, shares, windowed  # noqa: E402
from lexic.exceptions import LexicError  # noqa: E402
from read import Facet, Reading, as_written, read  # noqa: E402

__all__ = ["Handler", "main", "scene"]

FILES = {".html": "text/html", ".css": "text/css", ".js": "text/javascript"}
HEAD = re.compile(r"^([A-Za-z0-9_-]+)\s*(?:::=|=/|=)")

# What this build does not derive yet. Each says what it is; an empty body is
# not an answer, and the leaf's parsers cannot read one.
PENDING = {
    "/policy": "",
    "/routes": "primary the engine's own composition\nprimary_seconds 0.00\n"
    "status pending\n",
    "/clock": "status pending\ngeneration 1\npda_end -1\ndropped 0\n"
    "#PDAFRAMES 0\n#PDANAMES 0\n#EVENTS 0\n#EARLEY 0\n#EARLEYNAMES 0\n",
    "/verdicts": "#VERDICTS 0\n",
    "/automaton": "#ACLONES 0\n#ANAMES 0\n#AEDGES 0\n",
    "/rails": "",
    "/column": "#COLUMN 0 0\n#EXPECT 0\n",
    "/strata": "#STRATA 1 0\nL 0 this reading\nc 0 0 0 r 1 the only reading\n",
}


def ruledefs(text: str) -> list[tuple[str, int, int]]:
    """Where each rule lives in the reader text — line ranges, addressable."""
    heads = [
        (m.group(1), i)
        for i, line in enumerate(text.split("\n"))
        if (m := HEAD.match(line))
    ]
    out = []
    for place, (name, start) in enumerate(heads):
        stop = heads[place + 1][1] - 1 if place + 1 < len(heads) else text.count("\n")
        out.append((name, start, stop))
    return out


def offered(reading: Reading) -> list[Facet]:
    """The surfaces this reading COULD show, each already sized.

    They are not placed — they are offered, with the room each needs, so the
    arrangement can answer "here" or "in a window" instead of drawing a
    picture nobody can read.
    """
    try:
        machine = compile_text(reading.reader_text, flavour=reading.flavour or "gbnf")
    except LexicError, RecursionError, ValueError:
        return []  # an unreadable reader offers nothing to look at
    return [graph_facet(machine.grammar), machine_facet(machine)]


def scene(reading: Reading) -> str:
    """The reading, spelled — with the arrangement its surfaces asked for."""
    facets = reading.facets()
    rules = ruledefs(reading.reader_text)
    said = [as_written(rules, s.rule) for s in reading.spans]
    names = sorted(set(said))
    fields = sorted({s.field for s in reading.spans})
    at = {name: i for i, name in enumerate(names)}
    fat = {name: i for i, name in enumerate(fields)}
    # two populations, judged separately: what is PLACED is judged against
    # the split it actually got, and what is merely OFFERED is judged against
    # the widest column that split leaves. Mixing them made every surface
    # read as not fitting.
    room = max(shares(facets, 200).values())
    wants = [
        *windowed(facets, 200),
        *(f.name for f in offered(reading) if f.wide * ENOUGH > room),
    ]
    policy = {
        "arrange.tree": arrange(facets),
        "wants.window": ",".join(wants) or "none",
        "chain": " | ".join(rung.line() for rung in chain(reading)),
    }
    return "\n".join(
        [
            "#META",
            f"fixture {reading.document.name} ⊳ {reading.reader.name}",
            f"reader {reading.reader.name}",
            f"seconds {reading.seconds:.2f}",
            "resolver 0",
            f"faithful {1 if reading.faithful else 0}",
            "generation 1",
            "t 0.0",
            f"#POLICY {len(policy)}",
            *(f"{k} {v}" for k, v in policy.items()),
            f"#RULEDEFS {len(rules)}",
            *(f"{n} {a} {b}" for n, a, b in rules),
            f"#RULENAMES {len(names)}",
            *names,
            f"#FIELDNAMES {len(fields)}",
            *fields,
            f"#SPANS {len(reading.spans)}",
            *(
                f"{s.start} {s.end} {s.depth} {at[r]} {fat[s.field]}"
                for s, r in zip(reading.spans, said, strict=True)
            ),
            f"#READER {len(reading.reader_text)}",
            reading.reader_text,
            f"#DOC {len(reading.text)}",
            reading.text,
            "",
        ]
    )


class Handler(BaseHTTPRequestHandler):
    """One socket over one reading. It serves; it does not know."""

    reading: Reading

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        """Silence: the instrument's own output is the interesting one."""

    def send(self, body: str, kind: str = "text/plain") -> None:
        data = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", f"{kind}; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:  # noqa: N802 — the base class names it
        path = urlparse(self.path).path
        name = "index.html" if path == "/" else path.lstrip("/")
        artifact = (HERE / "leaf" / name).resolve()
        if artifact.is_file() and artifact.parent == (HERE / "leaf").resolve():
            self.send(artifact.read_text(), FILES.get(artifact.suffix, "text/plain"))
            return
        if path == "/scene":
            self.send(scene(self.reading))
            return
        self.send(PENDING.get(path, ""))

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        self.rfile.read(length)
        self.send("ok\n")


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) < 2:
        print("usage: serve.py <grammar> <document> [port]")
        return 2
    reading = read(Path(args[0]), Path(args[1]))
    facets = reading.facets()
    print(
        f"{reading.document.name} ⊳ {reading.reader.name} · {len(reading.spans):,} spans"
    )
    print(f"arrangement {arrange(facets)}")
    print(f"wants a window: {windowed(facets, 200) or 'nothing'}")
    Handler.reading = reading
    port = int(args[2]) if len(args) > 2 else 8917
    print(f"space_1 at http://127.0.0.1:{port}/")
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
