"""The socket: the leaf's files, and the gestures it sends back.

Run from the repo root::

    uv run python .../space_1/serve.py <grammar> <document> [port]

What the leaf receives is built in ``wire/`` — the scene, the ladder, the
rooms, the derived routes. This module routes, serves files, and carries a
gesture to the state it belongs in. It decides nothing about a frame.
"""

from __future__ import annotations

import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from kairos.parse import column, decisions, hypotheses, parity, watch  # noqa: E402
from kairos.engine import automaton, verdicts  # noqa: E402
from lexic.exceptions import LexicError  # noqa: E402
from lexic.grammars import get_flavour  # noqa: E402
from lexic.compile import compile_text  # noqa: E402
from praxis.reading import (  # noqa: E402
    Reading,
    as_written,
    read,
    read_up,
)
from praxis.history import retype  # noqa: E402
from deixis.points import wire as point  # noqa: E402
from eidolon.layout import positions  # noqa: E402
from eidolon.topology import edges, levels, reachable  # noqa: E402
from opsis.grammar import rail, rails  # noqa: E402
from opsis.paint import (  # noqa: E402
    automaton_drawing,
    chart_drawing,
    graph_drawing,
    rail_drawing,
    rails_drawing,
)
from eidolon.value import wire as ir_wire  # noqa: E402
from kairos.pipeline import form_of, spelled  # noqa: E402
from opsis.scene import (  # noqa: E402
    GENERATION,
    drawn,
    moved,
    reader_of,
    ruledefs,
)
from opsis.rooms import room, subject  # noqa: E402
from opsis.space import arrange  # noqa: E402
from praxis.strata import strata  # noqa: E402

__all__ = ["Handler", "main"]

FILES = {".html": "text/html", ".css": "text/css", ".js": "text/javascript"}


# What this build does not derive yet. Each says what it is; an empty body is
# not an answer, and the leaf's parsers cannot read one.
PENDING: dict[str, str] = {}


# what the leaf receives is built in `wire/`; the socket serves it and
# carries gestures back. It decides nothing about what is in a frame.


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

    def cast(self, asked: str) -> str:
        """Transpile: this grammar, spelled through another flavour.

        Computed, never declared — the flavour is asked to spell the AST and
        the answer is whether it can. A flavour that cannot say what this
        grammar means refuses in its own words rather than producing text
        that reads back as something else.
        """
        want = asked.removeprefix("transpile").strip()
        if not want:
            return "refuse name a flavour to spell it through\n"
        try:
            flavour = get_flavour(want)
        except LexicError:
            return f"refuse no flavour called {want!r}\n"
        try:
            machine = compile_text(
                self.reading.reader_text, flavour=self.reading.flavour or "gbnf"
            )
            spelled = flavour.apply(machine.grammar)
        except (LexicError, RecursionError, ValueError) as refusal:
            return f"refuse {want} cannot spell this — {str(refusal)[:120]}\n"
        try:
            back = compile_text(spelled, flavour=flavour)
        except (LexicError, RecursionError, ValueError) as refusal:
            return f"refuse {want} spelled it but cannot read it back — {refusal}\n"
        same = back.grammar == machine.grammar
        return (
            f"ok {want} {len(spelled):,} chars · "
            f"{'reads back equal' if same else 'reads back DIFFERENT'}\n"
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
        moved()
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
            "/routes",
            "/draw",
            "/irvalue",
        ):
            return None
        try:
            machine = compile_text(
                self.reading.reader_text, flavour=self.reading.flavour or "gbnf"
            )
        except LexicError, RecursionError, ValueError:
            return "no reader to draw\n"
        if path == "/routes":
            seconds, verdict, words = parity(machine, self.reading.text)
            return "\n".join(
                [
                    "primary the engine's own composition",
                    f"primary_seconds {self.reading.seconds:.2f}",
                    "status done",
                    "name Earley (explicit)",
                    f"seconds {seconds:.2f}",
                    f"parity {verdict}",
                    "pos -1",
                    f"words {words}",
                    "",
                ]
            )
        if path == "/irvalue":
            asked = parse_qs(query)
            value = subject(self.reading, asked.get("place", [""])[0], machine)
            if value is None:
                # the surface reads a value; absence IS one, so it is spelled
                # as a value rather than sent as an empty body it cannot parse
                return "type nothing\ntier absence\nnodes 0\nedges 0\n"
            return ir_wire(value, asked.get("path", [""])[0])
        if path == "/column":
            at = dict(
                part.split("=", 1) for part in query.split("&") if "=" in part
            ).get("i", "0")
            return column(machine, self.reading.text, int(at) if at.isdigit() else 0)
        if path == "/place":
            which = dict(
                part.split("=", 1) for part in query.split("&") if "=" in part
            ).get("id", "index")
            return room(unquote(which), machine, self.reading, Handler.state)
        if path == "/rulegraph":
            # a graph view can be about ONE rule: asked from a rule's room,
            # the answer is that rule's neighbourhood, not the whole grammar
            asked = parse_qs(query).get("place", [""])[0]
            shown = form_of(machine, self.reading, Handler.state.get("form", "source"))
            if (
                asked.startswith("rule:")
                and subject(self.reading, asked, machine) is not None
            ):
                drawn_edges, names = reachable(shown, asked[5:])
            else:
                drawn_edges, names = edges(shown), levels(shown)
            # WHERE each node sits is derived here too: the leaf receives
            # coordinates and paints them. It kept the ring maths, the band
            # wrapping and the declaration-order row — all derivation, in
            # the one place no fact can reach.
            said_form = Handler.state.get("form", "source")
            asked_view = parse_qs(query).get("view", ["rings"])[0]
            box = parse_qs(query).get("box", ["900x600"])[0].split("x")
            wide = int(box[0]) if box[0].isdigit() else 900
            tall = int(box[1]) if len(box) > 1 and box[1].isdigit() else 600
            # the sliders are configuration, and configuration is state:
            # the hand posts what it dragged and receives new places
            dial = {
                key[len("graph.") :]: float(value)
                for key, value in Handler.state.items()
                if key.startswith("graph.")
                and value.replace(".", "", 1).replace("-", "", 1).isdigit()
            }
            placed = positions(shown, asked_view, wide, tall, dial)
            # spelled the way this form spells it, like every other name the
            # leaf receives — a position keyed on a name nothing else uses
            # lights nothing and moves nothing
            known = ruledefs(spelled(self.reading, shown, said_form))
            placed = {as_written(known, name): at for name, at in placed.items()}
            return "\n".join(
                [
                    f"#EDGES {len(drawn_edges)}",
                    *(f"{a} {b}" for a, b in drawn_edges),
                    f"#DEPTHS {len(names)}",
                    *(f"{name} {at}" for name, at in names.items()),
                    f"#PLACES {len(placed)} {asked_view}",
                    *(
                        f"{x:.2f} {y:.2f} {z:.2f} {name}"
                        for name, (x, y, z) in placed.items()
                    ),
                    "",
                ]
            )
        if path == "/strata":
            return strata(self.reading, Handler.climbed or [self.reading])
        if path == "/clock":
            frames = watch(machine, self.reading.text)
            chose = decisions(frames)
            hyps, hnames = hypotheses(machine, self.reading.text)
            names = sorted({str(row[3]) for row in frames})
            at = {name: i for i, name in enumerate(names)}
            return "\n".join(
                [
                    "status done",
                    f"generation {GENERATION[0]}",
                    "pda_end -1",
                    "dropped 0",
                    f"#PDAFRAMES {len(frames)}",
                    *(
                        f"{s} {e} {d} {at[str(n)]} {seat} {ok}"
                        for s, e, d, n, ok, seat in frames
                    ),
                    f"#PDANAMES {len(names)}",
                    *names,
                    # where the machine had to choose — the lanes have always
                    # shown the rollbacks; nothing read them as decisions, so
                    # the panel said "none" on a grammar of nothing but
                    f"#EVENTS {len(chose)}",
                    *(f"{at} {kind} {said}" for at, kind, said in chose),
                    f"#EARLEY {len(hyps)}",
                    *hyps,
                    f"#EARLEYNAMES {len(hnames)}",
                    *hnames,
                    "",
                ]
            )
        if path == "/draw":
            # the picture itself, said in full. A surface that computes its
            # own geometry is a surface no fact can check — and both of
            # these are geometry over things this side already knows.
            asked = parse_qs(query)
            what = asked.get("what", ["rails"])[0]
            box = asked.get("box", ["900x600"])[0].split("x")
            wide = int(box[0]) if box[0].isdigit() else 900
            if what == "rails":
                shown = form_of(
                    machine, self.reading, Handler.state.get("form", "source")
                )
                return rails_drawing(rails(shown), wide).wire("rails")
            if what == "chart":
                tall = int(box[1]) if len(box) > 1 and box[1].isdigit() else 400
                at = float(asked.get("t", ["0"])[0] or 0)
                start = int(float(asked.get("from", ["0"])[0] or 0))
                win = int(float(asked.get("win", ["400"])[0] or 400))
                return chart_drawing(self.reading, at, start, win, wide, tall).wire(
                    "chart"
                )
            if what == "rail":
                shown = form_of(
                    machine, self.reading, Handler.state.get("form", "source")
                )
                return rail_drawing(rails(shown), asked.get("name", [""])[0]).wire(
                    "rail"
                )
            if what == "graph":
                shown = form_of(
                    machine, self.reading, Handler.state.get("form", "source")
                )
                tall = int(box[1]) if len(box) > 1 and box[1].isdigit() else 600
                dial = {
                    key[len("graph.") :]: float(value)
                    for key, value in Handler.state.items()
                    if key.startswith("graph.")
                    and value.replace(".", "", 1).replace("-", "", 1).isdigit()
                }
                known = ruledefs(spelled(self.reading, shown, "source"))
                asked_view = asked.get("view", ["flat"])[0]
                at = float(asked.get("t", ["0"])[0] or 0)
                alight = {
                    as_written(known, span.rule)
                    for span in self.reading.spans
                    if span.start <= at < span.end
                }
                return graph_drawing(shown, asked_view, wide, tall, dial, alight).wire(
                    "graph"
                )
            if what == "automaton":
                at = float(asked.get("t", ["0"])[0] or 0)
                frames = watch(machine, self.reading.text)
                lit = {seat for s, e, _d, _n, ok, seat in frames if ok and s <= at < e}
                seen = {seat for s, e, _d, _n, ok, seat in frames if ok and e <= at}
                return automaton_drawing(
                    automaton(machine.pda_tables()), lit, seen - lit
                ).wire("automaton")
            return f"#DRAW 0 {what} 0 0\n"
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
            # a REFUSED edit did not change the text, so nothing derived from
            # it is stale — saying otherwise makes every surface recompute to
            # arrive at what it already had
            if done.state != "refused":
                moved()
            if done.state == "refused":
                self.send(f"refuse {done.pos}\n{done.words}\n")
            else:
                self.send(f"ok {done.seconds:.2f}\n")
            return
        if path == "/cursor":
            # the cursor MOVED, so the answer to "what is open here" moved
            # with it. The leaf used to scan every span on every frame to
            # find that out; now it asks once, where it was already writing.
            digits = [w for w in body.split() if w.replace(".", "", 1).isdigit()]
            at = float(digits[0]) if digits else 0.0
            machine = reader_of(self.reading)
            form = Handler.state.get("form", "source")
            shown = form_of(machine, self.reading, form) if machine else None
            known = ruledefs(spelled(self.reading, shown, form))
            said = {
                span.rule: as_written(known, span.rule) for span in self.reading.spans
            }
            self.send(point(self.reading, at, said))
            return
        if path == "/cast":
            self.send(self.cast(body.strip()))
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
    Handler.reading = reading
    Handler.climbed = [reading]
    port = int(args[2]) if len(args) > 2 else 8917
    print(f"space_1 at http://127.0.0.1:{port}/")
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
