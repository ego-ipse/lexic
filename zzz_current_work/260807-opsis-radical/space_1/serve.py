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
from urllib.parse import unquote, urlparse

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from chain import chain  # noqa: E402
from draw import graph_facet  # noqa: E402
from lexic.compile import CompiledGrammar, compile_text  # noqa: E402
from machine import machine_facet  # noqa: E402
from place import DEFAULT, ENOUGH, arrange, shares, windowed  # noqa: E402
from lexic.exceptions import LexicError  # noqa: E402
from chain import Rung  # noqa: E402
from read import Facet, Reading, as_written, read, read_up, upward  # noqa: E402
from retype import retype  # noqa: E402
from draw import edges, levels  # noqa: E402
from keep import keep  # noqa: E402
from machine import of  # noqa: E402
from track import rail, rails  # noqa: E402
from watch import column, hypotheses, watch  # noqa: E402
from wire_machine import automaton, verdicts  # noqa: E402

__all__ = ["Handler", "main", "scene"]

FILES = {".html": "text/html", ".css": "text/css", ".js": "text/javascript"}

# the addresses the leaf understands for opening a surface at full size
OPENS = {"graph": "?graph=1&gpin=1"}
HEAD = re.compile(r"^([A-Za-z0-9_-]+)\s*(?:::=|=/|=)")

# What this build does not derive yet. Each says what it is; an empty body is
# not an answer, and the leaf's parsers cannot read one.
PENDING = {
    "/routes": "primary the engine's own composition\nprimary_seconds 0.00\n"
    "status pending\n",
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


def scene(reading: Reading, state: dict[str, str] | None = None) -> str:
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
    given = shares(facets, 200)
    widest = max(given.values())
    elsewhere = offered(reading)
    wants = [
        *windowed(facets, 200),
        *(f.name for f in elsewhere if f.wide * ENOUGH.get(f.kind, DEFAULT) > widest),
    ]
    policy = {
        "needs": " ".join(f"{f.name}:{f.wide}x{f.tall}" for f in [*facets, *elsewhere]),
        "offered": " ".join(f"{name}:{cols}" for name, cols in given.items()),
        "arrange.tree": arrange(facets),
        "wants.window": ",".join(wants) or "none",
        # where a refused surface can be opened at full size. Only the rule
        # graph has an address today; the machine is a view inside the same
        # window and has none yet, which is said rather than faked with the
        # graph's address.
        "opens": " ".join(
            # a value with spaces cannot survive a space-separated field —
            # the gate caught "machine:no address yet" parsing as three
            f"{name}:{OPENS.get(name, 'none-yet')}"
            for name in wants
        )
        or "none",
        "chain": " | ".join(rung.line() for rung in chain(reading)),
    }
    # what the leaf remembers about how it is looking at this reading — modes,
    # views, pins — belongs in the frame it boots from, or a reload silently
    # drops back to the primary view
    policy.update(state or {})
    return "\n".join(
        [
            "#META",
            f"fixture {reading.document.name} ⊳ {reading.reader_name}",
            f"reader {reading.reader_name}",
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


_DRAWN: dict[int, str] = {}


def drawn(reading: Reading, state: dict[str, str] | None = None) -> str:
    """The scene, built once per state of the text.

    A quarter of a megabyte was being rebuilt — spans, both text blocks, every
    measurement — on every poll the leaf makes. It changes when the text
    changes, so that is when it is rebuilt.
    """
    key = hash(
        (reading.text, reading.reader_text, tuple(sorted((state or {}).items())))
    )
    if key not in _DRAWN:
        _DRAWN.clear()
        _DRAWN[key] = scene(reading, state)
    return _DRAWN[key]


class Handler(BaseHTTPRequestHandler):
    """One socket over one reading. It serves; it does not know."""

    reading: Reading
    # the leaf keeps its pins, arrangement and view state HERE: it posts a
    # gesture and reconciles against the next poll. Discarding writes made it
    # delete every pin it had just created, one poll later.
    state: dict[str, str] = {}
    # every rung entered so far, bottom first: the ladder you can walk BACK
    # down. Without it, climbing threw away the reading below.
    climbed: list[Reading] = []

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
        if path == "/policy":
            self.send("".join(f"{k} {v}\n" for k, v in Handler.state.items()))
            return
        if path == "/scene":
            self.send(drawn(self.reading, Handler.state))
            return
        answer = self.derived(path, urlparse(self.path).query)
        if answer is not None:
            self.send(answer)
            return
        self.send(PENDING.get(path, ""))

    def room(self, which: str, machine: CompiledGrammar) -> str:
        """One room, spelled. A room nobody authored says so, in place."""
        if which in ("index", ""):
            rows = [
                "the machine — clones, not rules\tplace:machine",
                "the artefacts — each one loaded back\tplace:artefacts",
            ]
            return "\n".join(
                [
                    "#PLACE index rooms the rooms this reading holds",
                    "#SEC title 1",
                    "ROOMS",
                    f"#SEC list {len(rows)}",
                    *rows,
                    "",
                ]
            )
        if which == "machine":
            built = of(machine)
            return "\n".join(
                [
                    "#PLACE machine compiler the machine this grammar compiles to",
                    "#SEC title 1",
                    built.line(),
                    "#SEC kv 3",
                    f"clones built\t{built.clones}",
                    f"rules\t{built.rules}",
                    f"deep\t{built.deepest}",
                    "",
                ]
            )
        if which == "artefacts":
            made = keep(machine)
            return "\n".join(
                [
                    "#PLACE artefacts artefacts what this reader can be written as",
                    "#SEC title 1",
                    "ARTEFACTS — none counts until it loads back",
                    f"#SEC kv {len(made)}",
                    *(
                        f"{a.name}\t{a.chars:,} chars · {a.witness} — {a.words}"
                        for a in made
                    ),
                    "",
                ]
            )
        return "\n".join(
            [
                f"#PLACE {which} missing no such room",
                "#SEC title 1",
                "NO SUCH ROOM",
                "#SEC refusal 1",
                f"nothing here is addressed {which!r} — index, machine, artefacts",
                "",
            ]
        )

    def travel(self, rung: int) -> str:
        """Enter a rung of the chain — up OR down.

        The climb is a STACK, not a replacement. Overwriting the current
        reading on the way up left nothing to come back to: the chain is
        computed from where you stand, so descending had no floor to stand
        on. Every rung already entered is kept, so going down costs nothing
        and going up costs one parse, once.
        """
        if rung < 0:
            return "refuse no such rung\n"
        while len(Handler.climbed) <= rung:
            above = read_up(Handler.climbed[-1])
            if above is None:
                return "refuse nothing reads that\n"
            Handler.climbed.append(above)
        Handler.reading = Handler.climbed[rung]
        _DRAWN.clear()
        return "ok\n"

    def derived(self, path: str, query: str) -> str | None:
        """The routes the leaf calls that this instrument can already answer."""
        if path not in (
            "/rails",
            "/rail",
            "/verdicts",
            "/automaton",
            "/clock",
            "/strata",
            "/rulegraph",
            "/place",
            "/column",
        ):
            return None
        try:
            machine = compile_text(
                self.reading.reader_text, flavour=self.reading.flavour or "gbnf"
            )
        except LexicError, RecursionError, ValueError:
            return "no reader to draw\n"
        if path == "/column":
            at = dict(
                part.split("=", 1) for part in query.split("&") if "=" in part
            ).get("i", "0")
            return column(machine, self.reading.text, int(at) if at.isdigit() else 0)
        if path == "/place":
            which = dict(
                part.split("=", 1) for part in query.split("&") if "=" in part
            ).get("id", "index")
            return self.room(unquote(which), machine)
        if path == "/rulegraph":
            names = levels(machine.grammar)
            return "\n".join(
                [
                    f"#EDGES {len(edges(machine.grammar))}",
                    *(f"{a} {b}" for a, b in edges(machine.grammar)),
                    f"#DEPTHS {len(names)}",
                    *(f"{name} {at}" for name, at in names.items()),
                    "",
                ]
            )
        if path == "/strata":
            # the ladder is what has been CLIMBED plus the one rung above it,
            # named. Computing it from the current reading made the rungs
            # below vanish the moment you stepped up.
            walked = Handler.climbed or [self.reading]
            here = walked.index(self.reading) if self.reading in walked else 0
            rungs = [
                Rung(r.document.name, r.reader_name, i, True)
                for i, r in enumerate(walked)
            ]
            # the rung above is THIS reader read as a document. Once the
            # reader IS a metagrammar, the next rung would be it reading its
            # own spelling — the fixpoint — and naming it again just repeated
            # the rung you are standing on.
            top = walked[-1]
            named = upward(top)
            if named is not None and top.reader_name != named[1]:
                rungs.append(Rung(top.reader_name, named[1], len(rungs), False))
            lanes = [rung.document for rung in rungs]
            return "\n".join(
                [
                    f"#STRATA {len(rungs)} {here}",
                    *(f"L {i} {name}" for i, name in enumerate(lanes)),
                    *(
                        f"c {i} {rung.level} {i} r {1 if rung.visited else 0} "
                        f"{rung.document} ⊳ {rung.reader}"
                        for i, rung in enumerate(rungs)
                    ),
                    # one string, not a splat: *(f"...") unpacks it into
                    # characters, which is how a card became 24 lines
                    f"k 0 {len(self.reading.text)} {len(self.reading.spans)}"
                    f" {self.reading.reader_text.count('::=')}"
                    f" {self.reading.seconds:.2f}"
                    f" {1 if self.reading.faithful else 0} 0",
                    "",
                ]
            )
        if path == "/clock":
            frames = watch(machine, self.reading.text)
            hyps, hnames = hypotheses(machine, self.reading.text)
            names = sorted({str(row[3]) for row in frames})
            at = {name: i for i, name in enumerate(names)}
            return "\n".join(
                [
                    "status done",
                    "generation 1",
                    "pda_end -1",
                    "dropped 0",
                    f"#PDAFRAMES {len(frames)}",
                    *(
                        f"{s} {e} {d} {at[str(n)]} {seat} {ok}"
                        for s, e, d, n, ok, seat in frames
                    ),
                    f"#PDANAMES {len(names)}",
                    *names,
                    "#EVENTS 0",
                    f"#EARLEY {len(hyps)}",
                    *hyps,
                    f"#EARLEYNAMES {len(hnames)}",
                    *hnames,
                    "",
                ]
            )
        if path == "/rails":
            return rails(machine.grammar)
        if path == "/rail":
            name = dict(
                part.split("=", 1) for part in query.split("&") if "=" in part
            ).get("rule", "")
            return rail(machine.grammar, unquote(name))
        if path == "/verdicts":
            return verdicts(machine)
        return automaton(machine.pda_tables())

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length).decode("utf-8")
        if urlparse(self.path).path == "/focus":
            # the leaf posts "focus 1", not "1": take the last number in the
            # body and refuse in words if there is none, rather than throwing
            digits = [word for word in body.split() if word.lstrip("-").isdigit()]
            if not digits:
                self.send("refuse a rung is named by a number\n")
                return
            self.send(self.travel(int(digits[-1])))
            return
        path = urlparse(self.path).path
        if path in ("/edit", "/save"):
            head, _, put = body.partition("\n")
            bounds = [w for w in head.split() if w.lstrip("-").isdigit()]
            if len(bounds) != 2:
                self.send("refuse an edit says WHERE before it says what\n")
                return
            done = retype(self.reading, int(bounds[0]), int(bounds[1]), put)
            _DRAWN.clear()
            if done.state == "refused":
                self.send(f"refuse {done.pos}\n{done.words}\n")
            else:
                self.send(f"ok {done.seconds:.2f}\n")
            return
        if path == "/cursor":
            self.send("ok\n")  # fire-and-forget, by design
            return
        if path == "/cast":
            self.send("refuse this build has no casts yet\n")
            return
        if path == "/policy":
            for line in body.splitlines():
                key, _, value = line.partition(" ")
                if not key:
                    continue
                if value == "-":
                    Handler.state.pop(key, None)
                else:
                    Handler.state[key] = value
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
    Handler.climbed = [reading]
    port = int(args[2]) if len(args) > 2 else 8917
    print(f"space_1 at http://127.0.0.1:{port}/")
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
