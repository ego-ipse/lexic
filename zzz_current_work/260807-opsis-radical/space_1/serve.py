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
from urllib.parse import parse_qs, unquote, urlparse

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from chain import chain  # noqa: E402
from draw import graph_facet  # noqa: E402
from lexic.compile import (  # noqa: E402
    CompiledGrammar,
    canonical_grammar,
    compile_text,
)
from lexic.ir import IrAst  # noqa: E402
from machine import machine_facet  # noqa: E402
from place import arrange, shares  # noqa: E402
from lexic.exceptions import LexicError  # noqa: E402
from lexic.grammars import get_flavour  # noqa: E402
from lexic.parsing.fold import lift_optional_nullables  # noqa: E402
from chain import Rung  # noqa: E402
from read import (  # noqa: E402
    Facet,
    Reading,
    as_written,
    profile,
    read,
    read_up,
    upward,
)
from retype import retype  # noqa: E402
from draw import edges, levels, reachable  # noqa: E402
from keep import keep  # noqa: E402
from machine import of  # noqa: E402
from track import rail, rails  # noqa: E402
from irvalue import graph as ir_graph  # noqa: E402
from irvalue import refused as ir_refused  # noqa: E402
from irvalue import wire as ir_wire  # noqa: E402
from lexic.ir.spine.spine import IrSelf  # noqa: E402
from watch import column, decisions, hypotheses, parity, watch  # noqa: E402
from wire_machine import automaton, verdicts  # noqa: E402

__all__ = ["Handler", "main", "scene"]

FILES = {".html": "text/html", ".css": "text/css", ".js": "text/javascript"}

HEAD = re.compile(r"^([A-Za-z0-9_-]+)\s*(?:::=|=/|=)")

# What this build does not derive yet. Each says what it is; an empty body is
# not an answer, and the leaf's parsers cannot read one.
PENDING: dict[str, str] = {}


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


# The same language, at three moments of the pipeline. None of them is more
# true than the others: a grammar as WRITTEN, in its canonical normal form,
# and as codegen cut it for the parser. The views disagreed because each was
# drawing a different one — the automaton is built from the codegen form, so
# a choice it makes has no node in the source form at all.
FORMS = ("source", "canonical", "codegen", "lifted")


def form_of(machine: CompiledGrammar, reading: Reading, which: str) -> IrAst:
    """This reader at one moment of the pipeline."""
    if which == "lifted":
        # what the Earley engine actually runs: the codegen grammar with its
        # optional nullables lifted. The last moment before the parse, and
        # the one no view was drawing.
        return lift_optional_nullables(machine.codegen_grammar)
    if which == "codegen":
        return machine.codegen_grammar
    if which == "canonical":
        return canonical_grammar(
            reading.reader_text, get_flavour(reading.flavour or "gbnf")
        )
    return machine.grammar


def spelled(reading: Reading, shown: IrAst | None, form: str) -> str:
    """This form as grammar TEXT — what the reader displays.

    The source form is the file as written; the other two are spelled by the
    flavour that read it, so a form is never shown as a description of
    itself. If it cannot be spelled, the reader keeps showing what it has.
    """
    if form == "source" or shown is None:
        return reading.reader_text
    try:
        return get_flavour(reading.flavour or "gbnf").apply(shown)
    except LexicError, RecursionError, ValueError:
        return reading.reader_text


def reader_of(reading: Reading) -> CompiledGrammar | None:
    """This reading's reader, compiled — or nothing, if nothing reads it."""
    try:
        return compile_text(reading.reader_text, flavour=reading.flavour or "gbnf")
    except LexicError, RecursionError, ValueError:
        return None


def offered(machine: CompiledGrammar | None, placed: bool = False) -> list[Facet]:
    """The surfaces this reading COULD show, each already sized.

    They are not placed — they are offered, with the room each needs, so the
    arrangement can answer "here" or "in a window" instead of drawing a
    picture nobody can read.
    """
    if machine is None:
        return []  # an unreadable reader offers nothing to look at
    rest = [machine_facet(machine)]
    return rest if placed else [graph_facet(machine.grammar), *rest]


# Which reading this is. Every derived surface — the clocks, the automaton,
# the verdicts, the value — is a function of the text, so the leaf must be
# able to tell that the text moved. It was a literal 1, so after a re-read
# only the model came back new and every other surface stayed stale.
GENERATION = [1]


def moved() -> None:
    """The text (or the rung) changed: everything derived from it is old."""
    GENERATION[0] += 1
    _DRAWN.clear()


def scene(reading: Reading, state: dict[str, str] | None = None) -> str:
    """The reading, spelled — with the arrangement its surfaces asked for."""
    machine = reader_of(reading)
    # the relations are a PLACED surface, between the reader they are a
    # picture of and the document. Offered-but-never-placed is how the graph
    # spent four rounds being drawn into a column measured for text.
    facets = reading.facets()
    if machine is not None:
        facets = [*facets[:1], graph_facet(machine.grammar), *facets[1:]]
    # THE FORM IS A PROPERTY OF THE READER: it decides what the reader
    # displays. The grammar as written, its canonical normal form, or the
    # form codegen cut for the parser — each spelled by the flavour, so the
    # reader shows real grammar text in every one of them, and every name
    # downstream (the graph's nodes, the spans' rules, the spine) is read off
    # THAT text. One spelling, one picture, whichever form you are in.
    form = (state or {}).get("form", "source")
    shown = form_of(machine, reading, form) if machine else None
    reader_text = spelled(reading, shown, form)
    rules = ruledefs(reader_text)
    said = [as_written(rules, span.rule) for span in reading.spans]
    names = sorted(set(said))
    fields = sorted({s.field for s in reading.spans})
    at = {name: i for i, name in enumerate(names)}
    fat = {name: i for i, name in enumerate(fields)}
    # two populations, judged separately: what is PLACED is judged against
    # the split it actually got, and what is merely OFFERED is judged against
    # the widest column that split leaves. Mixing them made every surface
    # read as not fitting.
    given = shares(facets, 200)
    elsewhere = offered(machine, placed=True)
    # WHICH RULE REFERS TO WHICH — the relationships. The leaf's wire reader
    # has always had a place for these two blocks; nothing ever filled it, so
    # every graph drew rules as unrelated dots and read as broken.
    relations = (
        [(as_written(rules, a), as_written(rules, b)) for a, b in edges(shown)]
        if shown
        else []
    )
    deep = (
        {as_written(rules, name): at for name, at in levels(shown).items()}
        if shown
        else {}
    )
    policy = {
        "needs": " ".join(f"{f.name}:{f.wide}x{f.tall}" for f in [*facets, *elsewhere]),
        "offered": " ".join(f"{name}:{cols}" for name, cols in given.items()),
        "arrange.tree": arrange(
            facets,
            showing={
                key[len("tab.") :]: int(value)
                for key, value in (state or {}).items()
                if key.startswith("tab.") and value.isdigit()
            },
        ),
        "chain": " | ".join(rung.line() for rung in chain(reading)),
        # which moment of the pipeline every view is drawing
        "form": form,
        "forms": " ".join(FORMS),
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
            f"generation {GENERATION[0]}",
            "t 0.0",
            f"#POLICY {len(policy)}",
            *(f"{k} {v}" for k, v in policy.items()),
            f"#RULEDEFS {len(rules)}",
            *(f"{n} {a} {b}" for n, a, b in rules),
            f"#RULENAMES {len(names)}",
            *names,
            f"#FIELDNAMES {len(fields)}",
            *fields,
            # what each surface is CALLED and where it lives. The leaf used
            # to carry "THE READER" in its own markup and a facet list in its
            # own source, so adding a surface meant editing the leaf.
            f"#FACETS {len(facets)}",
            *(f.wire()[len("#FACET ") :] for f in facets),
            f"#EDGES {len(relations)}",
            *(f"{a} {b}" for a, b in relations),
            f"#DEPTHS {len(deep)}",
            *(f"{name} {at_}" for name, at_ in deep.items()),
            f"#SPANS {len(reading.spans)}",
            *(
                f"{s.start} {s.end} {s.depth} {at[r]} {fat[s.field]}"
                for s, r in zip(reading.spans, said, strict=True)
            ),
            f"#READER {len(reader_text)}",
            reader_text,
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
        (
            GENERATION[0],
            reading.text,
            reading.reader_text,
            tuple(sorted((state or {}).items())),
        )
    )
    if key not in _DRAWN:
        _DRAWN.clear()
        _DRAWN[key] = scene(reading, state)
    return _DRAWN[key]


def strata(reading: Reading, climbed: list[Reading]) -> str:
    """The ladder: every rung walked, the one above it, and the doors it holds.

    A function of the two things it depends on — where you stand and what
    you have climbed — so what the leaf is sent can be asked for and
    checked without a socket in the way.
    """
    machine = reader_of(reading)
    if machine is None:
        return "#STRATA 0 0\n"
    # the ladder is what has been CLIMBED plus the one rung above it,
    # named. Computing it from the current reading made the rungs
    # below vanish the moment you stepped up.
    walked = climbed or [reading]
    here = walked.index(reading) if reading in walked else 0
    rungs = [
        Rung(r.document.name, r.reader_name, i, True) for i, r in enumerate(walked)
    ]
    # the rung above is THIS reader read as a document. Once the
    # reader IS a metagrammar, the next rung would be it reading its
    # own spelling — the fixpoint — and naming it again just repeated
    # the rung you are standing on.
    top = walked[-1]
    named = upward(top)
    if named is not None and top.reader_name != named[1]:
        rungs.append(Rung(top.reader_name, named[1], len(rungs), False))
    # the rooms, as doors under the column of the thing they are of.
    # They existed at /place with nothing pointing at them, which is
    # how a whole capability stays on the wire and off the screen.
    built = of(machine)
    made = keep(machine)
    witnessed = sum(1 for a in made if a.witness == "holds")
    walk = ir_graph(machine.grammar)
    doors = [
        f"P ir:grammar {here} {rungs[here].level} value ok "
        f"{reading.reader_name} — as a value\t"
        f"{len(walk.nodes)} nodes · {len(walk.edges)} edges",
        f"P machine {here} {rungs[here].level} compiler ok "
        f"{reading.reader_name} — as a machine\t{built.line()}",
        f"P artefacts {here} {rungs[here].level} artefacts ok "
        f"{reading.reader_name} — as artefacts\t"
        f"{len(made)} artefacts · {witnessed} witnessed",
    ]
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
            *doors,
            # ONE PER VISITED RUNG, each carrying its own numbers.
            # A single line pinned to card 0 gave every rung the
            # current reading's stats, and left the rung you had just
            # climbed to marked visited with no stats at all — which
            # threw the leaf's card renderer mid-draw, so everything
            # after the first stratum simply never appeared.
            # the little graph on a visited card: how deep that reading goes
            # across its own document. A card with a number and no shape says
            # almost nothing about the reading it stands for.
            *(
                f"b {i} {' '.join(str(v) for v in profile(r))}"
                for i, r in enumerate(walked)
                if r.spans
            ),
            *(
                f"k {i} {len(r.text)} {len(r.spans)}"
                f" {len(ruledefs(r.reader_text))}"
                f" {r.seconds:.2f}"
                f" {1 if r.faithful else 0} 0"
                for i, r in enumerate(walked)
            ),
            "",
        ]
    )


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

    def subject(self, pid: str, machine: CompiledGrammar) -> IrSelf | None:
        """What a place id NAMES, as a live value — never a description of one."""
        if pid == "grammar":
            return machine.grammar
        if pid == "reducer":
            return get_flavour(self.reading.flavour or "gbnf").reducer
        if pid == "codegen":
            return machine.codegen_grammar
        if pid.startswith("rule:"):
            wanted = pid[5:].casefold()
            for rule in machine.grammar.rules:
                if str(rule.name).casefold() == wanted:
                    return rule
        return None

    def room(self, which: str, machine: CompiledGrammar) -> str:
        """One room, spelled. A room nobody authored says so, in place."""
        if which in ("index", ""):
            rows = [
                "the pipeline — the same language, four moments\tplace:pipeline",
                "the rules — each one, by what it accounts for\tplace:rules",
                "the machine — clones, not rules\tplace:machine",
                "the artefacts — each one loaded back\tplace:artefacts",
                "the grammar as a VALUE — the IR it loaded to\tplace:ir:grammar",
                "what codegen made of it — the grammar the parser runs"
                "\tplace:ir:codegen",
                "the reducer as a VALUE — where meaning attaches\tplace:ir:reducer",
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
        if which == "pipeline":
            # the pipeline as STEPS with checked claims, not a list of names.
            # What each moment did to the one before is a fact about two
            # grammars, so it is computed from them rather than described.
            here = Handler.state.get("form", "source")
            rows: list[str] = []
            facts: list[str] = []
            before: IrAst | None = None
            for which_form in FORMS:
                now = form_of(machine, self.reading, which_form)
                names = [str(rule.name) for rule in now.rules]
                spelled_now = spelled(self.reading, now, which_form)
                if before is None:
                    said = f"{len(names)} rules · {len(spelled_now):,} chars"
                else:
                    was = {str(rule.name) for rule in before.rules}
                    cut = sorted(set(names) - was)
                    gone = sorted(was - set(names))
                    said = (
                        f"{len(names)} rules"
                        + (f" · +{len(cut)}: {', '.join(cut[:3])}" if cut else "")
                        + (f" · −{len(gone)}: {', '.join(gone[:3])}" if gone else "")
                        + ("" if cut or gone else " · same rules, respelled")
                    )
                facts.append(f"{which_form}\t{said}")
                rows.append(
                    f"{'▸ ' if which_form == here else ''}{which_form} — {said}"
                    f"\tform:{which_form}"
                )
                before = now
            reads = self.reading.faithful
            return "\n".join(
                [
                    "#PLACE pipeline pipeline the same language, four moments",
                    "#SEC title 1",
                    f"{self.reading.reader_name} — showing the {here} form",
                    f"#SEC kv {len(facts) + 1}",
                    *facts,
                    "the parse of this document\t"
                    + ("re-emits its own text" if reads else "IS NOT FAITHFUL"),
                    f"#SEC list {len(rows)}",
                    *rows,
                    "",
                ]
            )
        if which == "rules":
            # ordered by how much of the document each rule ACCOUNTS FOR, not
            # alphabetically: the ordering is a reading of this document, and
            # a name-sorted list says nothing about what was parsed
            counts: dict[str, int] = {}
            for span in self.reading.spans:
                counts[span.rule] = counts.get(span.rule, 0) + 1
            ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
            rules = ruledefs(self.reading.reader_text)
            return "\n".join(
                [
                    f"#PLACE rules rules the {len(ranked)} rules this document used",
                    "#SEC title 1",
                    f"{len(ranked)} rules used · "
                    f"{len(self.reading.spans):,} occurrences",
                    f"#SEC list {len(ranked)}",
                    *(
                        f"{as_written(rules, name)} — {n:,} occurrences"
                        f"\tplace:rule:{as_written(rules, name)}"
                        for name, n in ranked
                    ),
                    "",
                ]
            )
        if which.startswith("rule:"):
            rule = self.subject(which, machine)
            if rule is None:
                return self.nothing(which, "this reader defines no rule called")
            name = which[5:]
            here = [
                s for s in self.reading.spans if s.rule.casefold() == name.casefold()
            ]
            _, depth = reachable(machine.grammar, name)
            clones = sum(
                1
                for key in machine.pda_tables().clones
                if getattr(key, "name", "").casefold() == name.casefold()
            )
            walk = ir_graph(rule)
            return "\n".join(
                [
                    f"#PLACE {which} rule one rule — everything it is",
                    "#SEC title 1",
                    f"{name} — {len(here)} occurrences in this document",
                    "#SEC kv 5",
                    f"occurrences\t{len(here):,}",
                    f"deepest occurrence\t{max((s.depth for s in here), default=0)}",
                    f"rules it can reach\t{len(depth) - 1}",
                    f"clones compiled for it\t{clones}",
                    f"its own IR\t{len(walk.nodes)} nodes, {len(walk.edges)} edges",
                    "#SEC graphview 1",
                    which,
                    "#SEC irvalue 1",
                    which,
                    "#SEC list 2",
                    "the whole grammar's graph\tplace:ir:grammar",
                    "the machine\tplace:machine",
                    "",
                ]
            )
        if which.startswith("ir:"):
            pid = which[3:]
            value = self.subject(pid, machine)
            if value is None:
                return self.nothing(which, "no value here is addressed")
            walk = ir_graph(value)
            shared = [at for at, n in walk.refs.items() if n > 1]
            return "\n".join(
                [
                    f"#PLACE {which} value the {pid} as the value it IS",
                    "#SEC title 1",
                    f"{type(value).__name__} — {len(walk.nodes)} unique nodes, "
                    f"{len(walk.edges)} edges",
                    "#SEC kv 4",
                    f"unique nodes\t{len(walk.nodes)}",
                    f"edges\t{len(walk.edges)}",
                    f"shared objects\t{len(shared)} reached "
                    f"{sum(walk.refs[at] for at in shared)} times",
                    f"the notation refuses\t"
                    f"{sum(1 for n in walk.nodes if ir_refused(n))} nodes",
                    "#SEC irvalue 1",
                    pid,
                    "#SEC list 2",
                    "the grammar as a value\tplace:ir:grammar",
                    "the reducer as a value\tplace:ir:reducer",
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
        return self.nothing(which, "no room here is addressed")

    def nothing(self, which: str, why: str) -> str:
        """A refusal, in place — with what this reading DOES hold."""
        return "\n".join(
            [
                f"#PLACE {which} missing no such room",
                "#SEC title 1",
                "NO SUCH ROOM",
                "#SEC refusal 1",
                f"{why} {which!r}",
                "#SEC list 4",
                "the machine\tplace:machine",
                "the artefacts\tplace:artefacts",
                "the grammar as a value\tplace:ir:grammar",
                "the reducer as a value\tplace:ir:reducer",
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
            value = self.subject(asked.get("place", [""])[0], machine)
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
            return self.room(unquote(which), machine)
        if path == "/rulegraph":
            # a graph view can be about ONE rule: asked from a rule's room,
            # the answer is that rule's neighbourhood, not the whole grammar
            asked = parse_qs(query).get("place", [""])[0]
            shown = form_of(machine, self.reading, Handler.state.get("form", "source"))
            if asked.startswith("rule:") and self.subject(asked, machine) is not None:
                drawn_edges, names = reachable(shown, asked[5:])
            else:
                drawn_edges, names = edges(shown), levels(shown)
            return "\n".join(
                [
                    f"#EDGES {len(drawn_edges)}",
                    *(f"{a} {b}" for a, b in drawn_edges),
                    f"#DEPTHS {len(names)}",
                    *(f"{name} {at}" for name, at in names.items()),
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
            self.send("ok\n")  # fire-and-forget, by design
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
