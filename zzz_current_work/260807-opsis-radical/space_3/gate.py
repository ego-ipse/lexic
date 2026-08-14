"""What must hold about a FRAME, printed as facts, so a false one is visible.

Run::

    uv run python .../space_3/gate.py

Every check defends something that was got wrong before, in space_1 or here:
a colour derived from a size, a width guessed instead of measured, a verdict
clipped into its opposite, a memo keyed on the wrong question, a control that
redrew one panel and left the rest talking about another engine.

The frame is DATA, so this drives the real composer and reads what came out.
Nothing is mocked and no browser is needed: if a fact here is true, it is
true of what the leaf would be sent.
"""

from __future__ import annotations

import re
import sys
import time
from collections import ChainMap
from copy import copy
from pathlib import Path
from tempfile import TemporaryDirectory

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from lexic.compile import export_source  # noqa: E402
from lexic.ir import IrFlavour  # noqa: E402
from kairos.parse import watch  # noqa: E402
from opsis.frame import compose  # noqa: E402
from opsis.frame.facets import HEADS, Look  # noqa: E402
from opsis.frame.marks import Frame  # noqa: E402
from opsis.frame.tones import EDGES, FONTS, TONES  # noqa: E402
from opsis.scene import reader_of, ruledefs, staged  # noqa: E402
from opsis.space import moved  # noqa: E402
from praxis.ingress import import_payload, land, probe_file  # noqa: E402
from praxis.reading import Reading, as_written, probe, read, turn  # noqa: E402
from praxis.session import KEYS, LANDED, SAYS, Session  # noqa: E402
from praxis.roots import GRAMMAR as POLICY  # noqa: E402
from praxis.state import chain  # noqa: E402
from praxis.strata import strata  # noqa: E402
from serve import Instrument  # noqa: E402

ROOT = HERE.parents[2]
GROUND = ROOT / "resources" / "ground_truth"
READER = GROUND / "json.gbnf"
DOCUMENT = HERE.parent / "tk" / "fixtures_long.json"
AMBIGUOUS_READER = HERE / "fixtures" / "ambiguous.ebnf"
AMBIGUOUS_DOCUMENT = HERE / "fixtures" / "ambiguous.txt"

# every pairing this gate reads. One fixture proves one fixture: the refusal
# banner was missing for as long as this only ever read a document that read.
PAIRINGS = (
    ("the json grammar reading a real document", READER, DOCUMENT),
    ("the ABNF spelling of it, reading the same", GROUND / "json.abnf", DOCUMENT),
    (
        "a grammar whose arms cannot be decided",
        HERE / "fixtures" / "decide.gbnf",
        HERE / "fixtures" / "decide.txt",
    ),
    (
        "a reader that REFUSES its document",
        GROUND / "arithmetic.gbnf",
        GROUND / "json.gbnf",
    ),
)

failed: list[str] = []


def check(said: str, held: bool, note: str = "") -> None:
    """One fact, printed either way — a false one has to be visible."""
    print(f"  {'ok  ' if held else 'FAIL'}  {said}" + (f"   · {note}" if note else ""))
    if not held:
        failed.append(said)


def marks(frame: Frame, kind: str) -> list[list[str]]:
    return [m.split(" ") for m in frame.marks if m.split(" ")[0] == kind]


def words(frame: Frame) -> list[str]:
    """What a frame SAYS — on BOTH canvases.

    A refusal is drawn over the text, so a reader of frames that looks only
    at what is under it will report that the instrument said nothing.
    """
    return [
        " ".join(m.split(" ")[6:])
        for m in [*frame.marks, *frame.over]
        if m.startswith("text ")
    ]


# where a mark carries its tone, per kind. Reading them all at one index is
# how this gate first reported that the frame asks for a tone called `1053.2`.
TONE_AT = {"box": 5, "ring": 5, "line": 5, "curve": 7, "bez": 9, "arc": 4, "text": 3}


def asked(frame: Frame) -> set[str]:
    """Every tone the frame asked for, wherever that kind keeps it."""
    said: set[str] = set()
    for mark in [*frame.marks, *frame.over]:
        parts = mark.split(" ")
        at = TONE_AT.get(parts[0])
        if at is not None and len(parts) > at:
            said.add(parts[at])
    return said


def hits(frame: Frame, kind: str) -> list[str]:
    return [h.split(" ")[5] for h in frame.hits if h.split(" ")[4] == kind]


def every() -> int:
    """Every pairing: the facts that must hold of ANY reading, not one."""
    print("every reading, not one")
    for says, reader, document in PAIRINGS:
        held = Reading(reader, document)
        held.hold()
        machine = reader_of(held)
        seen = watch(machine, held.text) if machine and held.spans else []
        frames = {}
        for state in (
            {},
            {"showing": "strata"},
            {"place": "machine"},
            {"tab.reader": "1"},
            {"chart.clock": "pda"},
        ):
            try:
                frames[str(state)] = compose(held, 1500, 850, 0.0, state, seen, 1)
            except Exception as burst:  # noqa: BLE001 — a raise IS the finding
                check(
                    f"{says}: {state} draws", False, f"{type(burst).__name__}: {burst}"
                )
                frames[str(state)] = None
        check(
            f"{says}: every way of looking at it draws",
            all(f is not None and f.marks for f in frames.values()),
            f"{len(held.text):,} chars · {len(held.spans):,} spans"
            + ("" if held.faithful else " · REFUSED"),
        )
        if not held.faithful and held.words:
            check(
                f"{says}: the refusal is in the engine's own words",
                any(held.words[:30] in w for w in words(frames["{}"])),
                held.words[:52],
            )
    return 0


def main() -> int:
    """Drive the composer over one real reading and read what came out."""
    every()
    reading = Reading(READER, DOCUMENT)
    reading.hold()
    session = Session(reading)
    machine = reader_of(reading)
    watched = watch(machine, reading.text) if machine else []

    def frame(state: dict[str, str], at: float = 4200.0, **rest: object) -> Frame:
        return compose(reading, 1500, 850, at, state, watched, 1, **rest)  # type: ignore[arg-type]

    print("the reading")
    check(
        "it reads, and re-emits its own text",
        reading.faithful,
        f"{len(reading.text):,} chars · {len(reading.spans):,} spans",
    )

    print("reader ingress offers")
    ambiguous_text = AMBIGUOUS_READER.read_text()
    tested = probe(ambiguous_text)
    accepted = {answer.flavour for answer in tested if answer.accepted}
    check(
        "ingress asks every pure candidate and retains every answer",
        len(tested) == 3 and accepted == {"abnf", "ebnf"},
        " · ".join(
            f"{answer.flavour}:{'accepts' if answer.accepted else 'refuses'}"
            for answer in tested
        ),
    )
    check(
        "an ambiguous reader is never silently first-matched",
        turn(ambiguous_text) is None
        and turn(ambiguous_text, "abnf") is not None
        and turn(ambiguous_text, "ebnf") is not None,
    )
    ambiguous = Reading(AMBIGUOUS_READER, AMBIGUOUS_DOCUMENT)
    ambiguous.hold()
    ingress = Session(ambiguous)
    offered = {
        relation.flavour
        for relation in ingress.graph.relations.values()
        if relation.kind == "offer"
    }
    check(
        "multiple acceptors become multiple unparsed offered read relations",
        ambiguous.ambiguous
        and not ambiguous.spans
        and offered == {"abnf", "ebnf"},
        " ".join(sorted(offered)),
    )
    ingress_frame = compose(ambiguous, 1400, 850, 0.0, {}, [], 1)
    ingress_words = words(ingress_frame)
    refused = [answer for answer in tested if not answer.accepted]
    check(
        "the chooser shows accepted relations and each refusal verbatim",
        set(hits(ingress_frame, "cast")) == {"abnf", "ebnf"}
        and all(any(answer.words in line for line in ingress_words) for answer in refused),
        " · ".join(ingress_words[-4:]),
    )
    ingress.gesture("at cast ebnf")
    check(
        "only an explicit cast parses and roots the chosen reading",
        ingress.reading.flavour == "ebnf"
        and ingress.reading.faithful
        and ingress.graph.root == ingress.graph.focus
        and len(ingress.reading.spans) > 0,
        f"{ingress.reading.flavour} · {len(ingress.reading.spans)} spans",
    )

    print("general file ingress")
    manifest = probe_file(ROOT / "src" / "lexic" / "grammars" / "ebnf.flavour.ir")
    check(
        "a flavour manifest retains both pure notation and live-flavour answers",
        [answer.reader for answer in manifest.probes[:2]]
        == ["IR notation", "flavour manifest"]
        and all(answer.accepted for answer in manifest.probes[:2])
        and any(isinstance(answer.value, IrFlavour) for answer in manifest.accepted),
        " · ".join(
            f"{answer.reader}:{answer.state}" for answer in manifest.probes[:2]
        ),
    )
    empty = land([], (HERE / "fixtures", ROOT / "generated"))
    check(
        "an empty ingress keeps its fixture and generated doors",
        not empty.subjects
        and empty.doors == (HERE / "fixtures", ROOT / "generated"),
    )
    tiny = turn('root ::= "x"')
    with TemporaryDirectory(prefix="opsis-ingress-") as temporary:
        scratch = Path(temporary)
        twin = scratch / "reader.py"
        twin.write_text(
            export_source(tiny[0]) if tiny is not None else "", encoding="utf-8"
        )
        twin_subject = probe_file(twin)
        check(
            "a twin module is parsed by its grammar while execution stays offered",
            any(
                answer.reader == "module self-grammar" and answer.accepted
                for answer in twin_subject.probes
            )
            and any(
                answer.reader == "Python payload" and answer.offered
                for answer in twin_subject.probes
            ),
        )

        marker = scratch / "executed"
        payload = scratch / "payload.py"
        payload.write_text(
            "from pathlib import Path\n"
            "from lexic.ir import IrStr\n"
            f"Path({str(marker)!r}).write_text('ran', encoding='utf-8')\n"
            "VALUE = IrStr('held')\n",
            encoding="utf-8",
        )
        payload_subject = probe_file(payload)
        untouched = not marker.exists()
        offered_payload = any(
            answer.reader == "Python payload" and answer.offered
            for answer in payload_subject.probes
        )
        executed = import_payload(payload_subject)
        loaded = executed.value
        check(
            "probing Python never executes it; the explicit import does",
            untouched
            and offered_payload
            and marker.read_text(encoding="utf-8") == "ran"
            and executed.accepted
            and loaded is not None
            and getattr(loaded, "module_name", "").endswith(
                payload_subject.sid[:12]
            )
            and getattr(loaded, "exports", ()) == ("VALUE",),
            executed.words,
        )

    print("the register")
    check(
        "every face the register names has a colour under the same name",
        all(name in TONES for name in FONTS),
        " ".join(sorted(FONTS)),
    )
    check(
        "every outline is an outline of something that is filled",
        all(name in TONES for name in EDGES),
        " ".join(sorted(EDGES)),
    )
    said = frame({})
    used = asked(said)
    check(
        "every tone a frame asks for is one the register carries",
        used <= set(TONES),
        " ".join(sorted(used - set(TONES)) or ["all known"]),
    )
    faces = {
        (word.split(":")[1] if word.startswith("scaled:") else word)
        for word in (m.split(" ")[4] for m in said.marks if m.startswith("text "))
    }
    check(
        "every face a frame asks for is a face or a tone that has one",
        faces <= set(FONTS) | set(TONES),
        " ".join(sorted(faces - set(FONTS) - set(TONES)) or ["all known"]),
    )

    print("the arrangement")
    check(
        "the five facets are drawn",
        {"THE READER", "THE DOCUMENT", "THE DERIVATION", "THE SPINE"}
        <= set(words(said)),
        " · ".join(w for w in words(said) if w.startswith("THE ")),
    )
    check(
        "both planes are REAL text, not painted",
        {p.split(" ")[0] for p in said.planes} == {"grammar", "document"},
        " ".join(p.split(" ")[0] for p in said.planes),
    )
    plane_tones = {p.split(" ")[0]: p.split(" ")[-1] for p in said.planes}
    check(
        "the reader is dim and the document is ink, as the real planes were",
        plane_tones == {"grammar": "dim", "document": "ink"},
        " ".join(f"{name}:{tone}" for name, tone in plane_tones.items()),
    )
    check(
        "the document's own text is what was sent for it",
        reading.text in said.texts,
        f"{sum(len(t) for t in said.texts):,} chars",
    )
    check(
        "a minimized facet leaves the arrangement",
        "THE SPINE" not in words(frame({"facet.spine": "off"})),
    )

    print("what the hand can land on")
    # a hit is answered by the SESSION or by the LEAF, and which is which
    # matters: the leaf answers only what a browser must do — open a window —
    # and everything else has to be a gesture the session knows
    by_leaf = {"pop", "clone"}
    # a handle is not a target: these are taken HOLD of, and what they mean
    # arrives as `spin`, `seam`, `zone` or `move` — gestures the session
    # answers, from a hit nobody ever clicks
    handles = {"head", "winhead", "wincorner"}
    # NOT a list of what SHOULD be answered — the tables themselves. Naming
    # `do` here while `LANDED` had no such key is how every button in the
    # status bar passed this gate and did nothing.
    by_session = (
        set(LANDED)
        | set(SAYS)
        | {
            "form",
            "graph.view",
            "chart.clock",
            "graph.focus",
            "dial.levelstep",
            "dial.ringscale",
            "dial.flatten",
        }
    )
    kinds = {h.split(" ")[4] for h in said.hits} - handles
    check(
        "every hit is answered by the session, or by the leaf opening a window",
        kinds <= by_session | by_leaf,
        " ".join(sorted(kinds - by_session - by_leaf) or ["all answered"]),
    )
    check(
        "and the leaf answers only what a browser must do",
        kinds & by_leaf <= {"pop", "clone"},
        " ".join(sorted(kinds & by_leaf)),
    )
    check(
        "a line number sets the reading's time",
        [n for n in hits(said, "gutter") if n.isdigit()] != [],
        f"{len(hits(said, 'gutter'))} numbered lines",
    )

    print("the clock is a lens, not a panel")
    spines = {}
    for clock in ("model", "pda", "earley"):
        rows = words(frame({"chart.clock": clock}))
        spines[clock] = [r for r in rows if ".." in r or "::=" in r]
    check(
        "each clock's spine says something the others do not",
        len({tuple(v[:3]) for v in spines.values()}) == 3,
        " | ".join(f"{k}: {v[0][:28] if v else '—'}" for k, v in spines.items()),
    )
    check(
        "the PDA clock badges the rules the analysis did not call predictive",
        any(
            w in ("attempt", "island", "gated", "hard")
            for w in words(frame({"chart.clock": "pda"}))
        ),
    )

    print("the lanes, against the cursor")
    lanes = frame({})
    filled = {m[5] for m in marks(lanes, "box")}
    check(
        "a span still ahead of the cursor is outlined, never filled",
        "ahead" not in filled and any(m[5] == "pending" for m in marks(lanes, "ring")),
        " ".join(sorted(filled & {"closed", "active"})),
    )
    check(
        "an open span is filled only as far as the cursor has come",
        any(m[5] == "active" for m in marks(lanes, "box")),
    )

    print("choosing a rule")
    # a rule the MODEL names — `value` is spelled by whichever arm it took,
    # so it has no spans of its own and would test nothing
    chosen = frame({"chosen": "string", "top.grammar": "34"})
    check(
        "its spans are ringed violet wherever they are",
        any(m[5] == "violet" for m in marks(chosen, "ring")),
        f"{sum(1 for m in marks(chosen, 'ring') if m[5] == 'violet')} rings",
    )
    check(
        "the rule's own lines are held in the reader",
        # `.lit` is what has been CHOSEN; `.hot` is what the hand is on. This
        # asked for hot, which is a different question about a different rule
        any(m[5] == "lit" for m in marks(chosen, "box")),
    )
    check(
        "focus fades what the chosen rule cannot reach",
        any(
            m.split(" ")[3] == "faded"
            for m in frame(
                {"chosen": "number", "graph.focus": "on", "tab.reader": "1"}
            ).marks
        ),
    )

    print("one truth about what is running")
    player = Session(reading)
    check(
        "a frame at rest says it is not playing",
        player.reading is reading and not player.playing,
    )
    player.gesture("do play")
    check(
        "the transport starts it — the same gesture the leaf's Space sends",
        player.playing,
    )
    was = player.at
    player.gesture("tick")
    check(
        "and a tick moves the reading while it is running",
        player.at > was,
        f"{was:.0f} → {player.at:.0f}",
    )
    player.gesture("do play")
    stopped = player.at
    player.gesture("tick")
    check("a tick moves nothing when it is not", player.at == stopped)

    def running(wire: str) -> str:
        """What the frame's own head says about whether it is playing."""
        return next(
            (
                line.split(" ")[5]
                for line in wire.split("\n")
                if line.startswith("#FRAME")
            ),
            "—",
        )

    told = compose(reading, 800, 600, 0.0, {}, [], 1)
    check(
        "the frame SAYS which it is, so nothing has to keep its own answer",
        running(told.wire(1, True)) == "1" and running(told.wire(1, False)) == "0",
        f"playing → {running(told.wire(1, True))} · "
        f"at rest → {running(told.wire(1, False))}",
    )

    print("the hand moves the arrangement")

    def head_at(state: dict[str, str], name: str = "THE DOCUMENT") -> float:
        for mark in frame(state).marks:
            if mark.startswith("text ") and " ".join(mark.split(" ")[6:]) == name:
                return float(mark.split(" ")[1])
        return -1.0

    rest = head_at({})
    check(
        "a seam the hand moved is where the next arrangement is measured from",
        head_at({"arrange.shares": "0.25"}) < rest < head_at({"arrange.shares": "0.6"}),
        f"{head_at({'arrange.shares': '0.25'}):.0f} < {rest:.0f} "
        f"< {head_at({'arrange.shares': '0.6'}):.0f}",
    )

    def rail_at(state: dict[str, str]) -> float:
        for mark in frame({**state, "tab.reader": "1", "graph.view": "rails"}).marks:
            parts = mark.split(" ")
            if (
                mark.startswith("text ")
                and parts[3] == "name"
                and " ".join(parts[6:]) == "json-text"
            ):
                return float(parts[2])
        return -1.0

    check(
        "the rails scroll on the wheel, on the facet's own key",
        rail_at({"top.graph": "3"}) < rail_at({}),
        f"{rail_at({}):.0f} → {rail_at({'top.graph': '3'}):.0f}",
    )
    check(
        "and ▤ rail scrolls them to a rule BY NAME",
        rail_at({"top.graph": "rule:number"}) < rail_at({}),
    )

    print("three cursors on one subject")

    def held(state: dict[str, str]) -> set[str]:
        return {
            m.split(" ")[2]
            for m in frame(state).marks
            if m.startswith("box ") and m.split(" ")[5] in ("lit", "hotline")
        }

    quiet = held({})
    check(
        "hovering a rule lights it, without choosing it",
        held({"hover": "rule value"}) > quiet,
        f"{len(quiet)} → {len(held({'hover': 'rule value'}))} lines",
    )
    # a span whose rule is NOT already lit — hovering something already lit
    # proves nothing, which is the third dead fact this gate has caught in me
    names = ruledefs(reading.reader_text)
    away = next(
        (
            span
            for span in reading.spans
            if as_written(names, span.rule)
            not in Look(reading, staged(reading, {}), 4200.0, {}, watched).lit()
        ),
        reading.spans[0],
    )
    check(
        "hovering a SPAN lights the rule that read it",
        held({"hover": f"span {away.start}:{away.end}"}) > quiet,
        f"{as_written(names, away.rule)} at {away.start:,}",
    )
    check("letting go lets go", held({"hover": ""}) == quiet)
    hoverer = Session(reading)
    hoverer.at = 4200.0
    hoverer.gesture("hover rule value")
    check(
        "hover does not move the cursor — it is not selection",
        hoverer.at == 4200.0 and hoverer.main.get("chosen", "") == "",
        f"at {hoverer.at:,.0f} · chosen {hoverer.main.get('chosen') or '—'}",
    )
    picked = Session(reading)
    picked.gesture("sel grammar 640 660")
    check(
        "selecting in the READER chooses the rule those characters are part of",
        bool(picked.main.get("chosen")),
        picked.main.get("chosen", "—"),
    )
    picked.gesture("sel document 4200 4260")
    check(
        "selecting in the DOCUMENT chooses the smallest occurrence covering it",
        bool(picked.main.get("chosen")),
        picked.main.get("chosen", "—"),
    )

    print("editing is a re-reading")
    was = reading.text
    session.gesture("text document", was[:100] + "OOPS" + was[100:])
    check(
        "a plane that has been typed in says so",
        any("edited — unread" in w for w in words(frame({}, typed=session.typed))),
    )
    session.gesture("key Ctrl+Enter")
    check(
        "a refused read keeps the typed text and says where it stopped",
        session.said is not None
        and session.said.state == "refused"
        and session.said.pos >= 0,
        f"frontier at {session.said.pos if session.said else '—'}",
    )
    check(
        "the frontier is drawn IN the text it stopped in",
        any(
            m[5] == "red"
            for m in marks(
                frame(
                    {},
                    typed=session.typed,
                    frontier=session.said.pos if session.said else -1,
                ),
                "box",
            )
        ),
    )
    session.gesture("key Escape")
    check("reverting puts the reading back", reading.text == was and not session.typed)

    print("the grammar is the ground truth")
    typer = Session(read(READER, DOCUMENT))
    # renaming a rule everywhere is the SAME LANGUAGE under new names: the
    # span count is expected to hold, and what must change is what the spans
    # are CALLED — which is read off the reader's text, so it proves the new
    # reader is the one that read
    typer.gesture("text grammar", typer.reading.reader_text.replace("ws", "sp"))
    typer.gesture("key Ctrl+Enter")
    named = {
        as_written(ruledefs(typer.reading.reader_text), s.rule)
        for s in typer.reading.spans
    }
    check(
        "typing in the READER re-reads the document with the new reader",
        typer.said is not None
        and typer.said.state != "refused"
        and "sp" in named
        and "ws" not in named,
        f"{len(typer.reading.spans):,} spans, now called "
        + " ".join(sorted(n for n in named if n in ("sp", "ws")) or ["—"]),
    )
    changed_relation = typer.graph.relation(typer.reading)
    check(
        "a successful re-reading re-addresses its graph relation",
        changed_relation is not None
        and changed_relation.rid == typer.reading.identity
        and typer.graph.root == changed_relation.rid,
        typer.reading.identity[:12],
    )
    broke = Session(read(READER, DOCUMENT))
    stood = broke.reading.reader_text
    broke.gesture("text grammar", "this is not a grammar at all\n")
    broke.gesture("key Ctrl+Enter")
    check(
        "a reader that no longer compiles is a refusal, and the old one stands",
        broke.reading.reader_text == stood
        and broke.said is not None
        and broke.said.state == "refused"
        and bool(broke.reading.spans),
        f"{len(broke.reading.spans):,} spans still",
    )
    check(
        "and what was typed is still where it was typed",
        broke.typed.get("grammar", "").startswith("this is not"),
    )

    print("windows are their own")
    layer: dict[str, str] = {}
    session.gesture("set graph.view rails", into=ChainMap(layer, session.main))
    check(
        "a gesture in a window writes to the window",
        layer.get("graph.view") == "rails" and "graph.view" not in session.main,
        f"window {layer} · session {session.main.get('graph.view', '—')}",
    )
    every_facet = ("grammar", "graph", "document", "chart", "spine")
    look = Look(reading, staged(reading, {}), 0.0, {}, watched)
    check(
        "every facet can be popped out and cloned, not only the graph",
        all(
            {"pop", "clone"} <= {control[1] for control in HEADS(look, name)}
            for name in every_facet
        ),
        " ".join(every_facet),
    )
    check(
        "a window on any facet draws that facet",
        all(bool(frame({}, only=name).marks) for name in every_facet),
    )
    popper = Session(reading)
    popper.gesture("pop spine")
    check(
        "⧉ takes the facet OUT of the grid — it is somewhere else now",
        # out of the GRID — the window it went to wears the facet's own
        # title, so its NAME is still on the screen and should be
        popper.main.get("facet.spine") == "off"
        and "spine"
        not in {
            h.split(" ")[5]
            for h in compose(reading, 1500, 850, 0.0, popper.main, watched, 1).hits
            if h.split(" ")[4] == "head"
        },
        "and the dock is where it comes back from",
    )
    cloner = Session(reading)
    cloner.gesture("clone spine")
    check(
        "⊞ leaves the grid the one it has",
        cloner.main.get("facet.spine") is None
        and "THE SPINE"
        in words(compose(reading, 1500, 850, 0.0, cloner.main, watched, 1)),
    )
    one, two = ChainMap({}, session.main), ChainMap({}, session.main)
    session.gesture("set chart.clock pda", into=one)
    check(
        "two clones of one facet keep their own view",
        one.get("chart.clock") == "pda" and two.get("chart.clock") is None,
        f"clone one {one.get('chart.clock')} · "
        f"clone two {two.get('chart.clock') or '—'}",
    )
    first_server = Instrument(Session(reading))
    second_server = Instrument(Session(reading))
    first_server.layer("w0")["graph.view"] = "rails"
    check(
        "server instances share no session or window state",
        first_server.here is not second_server.here
        and second_server.layer("w0").get("graph.view") is None,
    )
    traveller = Session(reading)
    traveller.policy["speed"] = "4"
    traveller.main["graph.view"] = "rails"
    policy_reading = Reading(POLICY, POLICY)
    policy_reading.reader_name = "the policy grammar"
    policy_reading.reader_text = POLICY.read_text()
    policy_reading.text = "speed 4\n"
    policy_reading.hold()
    traveller.enter(policy_reading, "policy")
    separate = traveller.main.get("graph.view") is None
    traveller.main["graph.view"] = "flat"
    traveller.enter(reading)
    restored = traveller.main.get("graph.view") == "rails"
    traveller.enter(policy_reading, "policy")
    check(
        "relation travel restores each room and keeps session policy",
        separate
        and restored
        and traveller.main.get("graph.view") == "flat"
        and traveller.main.get("speed") == "4",
    )
    check(
        "a pin says what it is about, and what covers it",
        any(
            "covering" in w or "·" in w
            for w in words(frame({"pin.span": "20:46"}, only="pin"))
        ),
    )
    check(
        "a pin made against another reading says it is stale",
        any(
            "the document has moved on" in w
            for w in words(frame({"pin.span": "20:46", "pin.gen": "0"}, only="pin"))
        ),
    )
    copied = frame(
        {
            "windows": "w0 w1",
            "win.w0": "document 240 110 620 460",
            "win.w1": "graph 266 136 620 460",
        },
        layers={"w0": {"top.document": "4"}, "w1": {"graph.view": "text"}},
    )
    check(
        "copied facets keep distinct real text planes and controls",
        {"document", "w0~document", "w1~relations-text"}
        <= {plane.split(" ")[0] for plane in copied.planes}
        and "w1~graph.view" in {pick.split(" ")[0] for pick in copied.picks},
    )
    check(
        "each popup is emitted as its own visual stack",
        {"layer w0", "layer w1"} <= set(copied.over)
        and copied.over.count("unlayer") == 2,
    )
    popped_graph = frame(
        {
            "windows": "w2",
            "win.w2": "graph 240 110 620 460",
            "home.w2": "(t 0 grammar graph)",
        },
        layers={"w2": {"graph.view": "depth3d"}},
    )
    check(
        "a popped Relations facet keeps its full slider set",
        {
            "w2~graph.levelstep",
            "w2~graph.ringscale",
            "w2~graph.flatten",
            "w2~graph.labelscale",
        }
        <= {pick.split(" ")[0] for pick in popped_graph.picks},
    )

    print("travel")
    same = Reading(READER, DOCUMENT)
    same.hold()
    check(
        "reading identity comes from ordered content and the reader cast",
        same == reading and same.identity == reading.identity,
        reading.identity[:12],
    )
    same.text += "\n"
    check("changed content is a different reading", same != reading)
    climber = Session(read(READER, DOCUMENT))
    check(
        "the session stores subjects and relations in a graph",
        len(climber.graph.subjects) == 2 and len(climber.graph.relations) == 1,
        f"{len(climber.graph.subjects)} subjects · "
        f"{len(climber.graph.relations)} relation",
    )
    first_window = climber.open_window("graph", "graph")
    was = climber.reading.reader_name
    climber.gesture("at rung 1")
    check(
        "entering a rung builds it",
        climber.reading is not climber.climbed[0] and bool(climber.reading.spans),
        f"{was} → {climber.reading.reader_name} · {len(climber.reading.spans):,} spans",
    )
    check(
        "the metagrammar is named as what it IS, not as a file",
        "metagrammar" in climber.reading.reader_name,
        climber.reading.reader_name,
    )
    rungs = chain(climber.reading)
    check(
        "the ladder stops at the fixpoint",
        len(rungs) == 1,
        " | ".join(r.line()[:44] for r in rungs),
    )
    check(
        "standing somewhere new is a new generation",
        climber.generation > 1,
        f"gen {climber.generation}",
    )
    next_window = climber.open_window("chart", "chart")
    check(
        "window ids are session-lifetime and never reused across travel",
        first_window == "w0" and next_window == "w1",
        f"{first_window} → {next_window}",
    )
    climber.gesture("at rung 0")
    check(
        "and the rung below is still there to come back to",
        climber.reading is climber.climbed[0],
    )

    print("the ring")
    ringer = Session(read(READER, DOCUMENT))
    ringer.gesture("set chart.clock pda")
    ringer.gesture("at ring on")
    check(
        "the instrument opens as a reading of its own state",
        ringer.reading.reader_name == "the policy grammar",
        ringer.reading.reader_name,
    )
    check(
        "and that reading READS — spans, spine, verdict, like any other",
        ringer.reading.faithful and bool(ringer.reading.spans),
        f"{len(ringer.reading.spans)} spans over {len(ringer.reading.text)} chars",
    )
    check(
        "what it says is what the instrument is",
        "chart.clock pda" in ringer.reading.text,
        ringer.reading.text.strip()[:44],
    )
    walked_before = tuple(ringer.climbed)
    relations_before = len(ringer.graph.relations)
    ringer.gesture("at ring on")
    check(
        "re-entering the ring neither grows nor rewrites the ladder",
        tuple(ringer.climbed) == walked_before
        and len(ringer.graph.relations) == relations_before,
        f"{len(ringer.climbed)} rungs · {len(ringer.graph.relations)} relations",
    )
    rooted = Session(read(READER, DOCUMENT))
    root = rooted.reading
    rooted.gesture("at ring on")
    rooted.gesture("at rung 2")
    check(
        "a climb after the ring remains rooted in the original reading",
        rooted.climbed[0] is root
        and rooted.reading.document == READER
        and all(r.document != POLICY for r in rooted.climbed),
        " → ".join(r.reader_name for r in rooted.climbed),
    )
    ringer.gesture("text document", "chart.clock earley\nfacet.spine off\n")
    ringer.gesture("key Ctrl+s")
    check(
        "saving that record APPLIES it — the ring closes",
        ringer.main.get("chart.clock") == "earley"
        and ringer.main.get("facet.spine") == "off",
        " ".join(f"{k}={v}" for k, v in sorted(ringer.main.items()) if v),
    )
    # a record the grammar REFUSES: a key is [a-z0-9._-], so this is not one
    ringer.gesture("text document", "CHART.CLOCK model\n")
    ringer.gesture("key Ctrl+s")
    check(
        "a record the grammar refuses is not applied",
        ringer.main.get("chart.clock") == "earley"
        and ringer.said is not None
        and ringer.said.state == "refused",
        f"still {ringer.main.get('chart.clock')}"
        + (f" · {ringer.said.words[:44]}" if ringer.said else ""),
    )

    print("where the reading sits")
    map_wire = strata(reading, [reading])
    check(
        "the map offers cheap licences and defers expensive witnesses",
        "witness on room entry" in map_wire,
    )
    check(
        "the strata draws the climb",
        "THE STRATA" in words(frame({"showing": "strata"})),
    )
    for place in ("machine", "artefacts", "rules", "ir:grammar", "rule:number"):
        check(
            f"the room {place!r} draws",
            bool(words(frame({"place": place}))),
            words(frame({"place": place}))[1] if words(frame({"place": place})) else "",
        )
    check(
        "a room nobody authored says so rather than drawing nothing",
        "NO SUCH ROOM" in words(frame({"place": "nowhere"})),
    )

    print("what came back from real use")
    model_frame, pda_frame = (
        frame({"chart.clock": "model"}),
        frame({"chart.clock": "pda"}),
    )
    check(
        "the PDA clock is not the model clock with other numbers in it",
        {m[5] for m in marks(pda_frame, "ring")}
        != {m[5] for m in marks(model_frame, "ring")}
        and len(
            {m[5] for m in marks(pda_frame, "ring")}
            & {"cool", "warm", "token", "violet", "dim"}
        )
        > 1,
        " ".join(sorted({m[5] for m in marks(pda_frame, "ring")})),
    )
    check(
        "a frame wide enough to read says what it IS",
        sum(1 for m in marks(pda_frame, "text") if m[4] == "chip") > 20,
        f"{sum(1 for m in marks(pda_frame, 'text') if m[4] == 'chip')} named",
    )
    check(
        "and hovering one names it in the readout",
        any(
            w.startswith("frame ") and "stack depth" in w
            for w in words(
                frame(
                    {
                        "chart.clock": "pda",
                        "hover": f"frame {hits(pda_frame, 'frame')[0]}",
                    }
                )
            )
        ),
        hits(pda_frame, "frame")[0]
        if hits(pda_frame, "frame")
        else "no frame to hover",
    )
    said_badges = [
        w
        for w in words(pda_frame)
        if w in ("predictive", "gated", "attempt", "island", "hard")
    ]
    check(
        "EVERY classified rule wears its class, predictive included",
        said_badges.count("predictive") > 5,
        f"{len(said_badges)} badges · {said_badges.count('predictive')} predictive",
    )
    lit = frame({"chosen": "member"})
    check(
        "choosing a rule outlines its spans in the document",
        sum(1 for m in marks(lit, "ring") if m[5] == "violet") > 4,
        f"{sum(1 for m in marks(lit, 'ring') if m[5] == 'violet')} outlined",
    )
    check(
        "the status bar says where, how fast, and what is under the hand",
        # it WRAPS, so "char …" and "gen 1" are two different marks now
        any(w.startswith("char ") and " · line " in w for w in words(lit))
        and any(w.endswith("gen 1") for w in words(lit))
        and any("outlined violet" in w for w in words(lit)),
        next((w for w in words(lit) if w.startswith("char ")), "no position"),
    )

    # Compact windows are measured against the same 1400×900 room used for
    # the live Space 1 comparison. `true` is its minimum-width content case;
    # `member` is a rail whose drawing exposes the old artificial 40px floor.
    pinning = Session(reading)
    pinning.viewport = (1400, 900)
    true_span = next(
        span
        for span in reading.spans
        if reading.text[span.start : span.end] == "true"
        and as_written(staged(reading, {}).rules, span.rule) == "true"
    )
    pinning.gesture(f"at pin {true_span.start}:{true_span.end}")
    pin_parts = pinning.main["win.w0"].split(" ", 5)
    check(
        "a small occurrence pin has Space 1's content-driven size",
        pin_parts[3:5] == ["280", "97"],
        "×".join(pin_parts[3:5]),
    )
    pin_frame = frame(dict(pinning.main))
    pin_copy = [
        mark.split(" ")
        for mark in pin_frame.over
        if mark.startswith("text ") and float(mark.split(" ")[1]) >= 240
    ]
    check(
        "its header, address, snippet, facts and definition use their real faces",
        {part[4] for part in pin_copy}
        >= {"winhead", "pinaddr", "pinbody", "pinfact"},
        " ".join(sorted({part[4] for part in pin_copy})),
    )
    check(
        "a trailing source newline does not become a phantom definition row",
        sum(1 for part in pin_copy if part[3:5] == ["cool", "pinbody"]) == 1,
        f"{sum(1 for part in pin_copy if part[3:5] == ['cool', 'pinbody'])} definition rows",
    )

    rail_sizing = Session(reading)
    rail_sizing.viewport = (1400, 900)
    rail_sizing.gesture("at rail member")
    rail_parts = rail_sizing.main["win.w0"].split(" ", 5)
    check(
        "a small rail pin is its track plus Space 1's 52×58 chrome",
        rail_parts[3:5] == ["376", "91"],
        "×".join(rail_parts[3:5]),
    )

    spine_base = frame({})
    spine_row = next(
        part
        for part in (hit.split(" ") for hit in spine_base.hits)
        if part[4] == "span" and float(part[3]) == 19.0
    )
    spine_hot = frame({"hover": f"span {spine_row[5]}"})
    check(
        "hovering the spine washes the exact row under the hand",
        any(
            part[1:5] == spine_row[0:4] and part[5] == "liveline"
            for part in (mark.split(" ") for mark in spine_hot.marks)
            if part[0] == "box"
        ),
        spine_row[5],
    )

    railed = frame({"windows": "w0", "win.w0": "rail 200 200 560 200 member"})
    every_rail = frame({"windows": "w0", "win.w0": "rails 200 200 560 200"})
    check(
        "▤ rail opens ONE rule's track, not the whole railway",
        0 < len(railed.over) < len(every_rail.marks),
        f"{len(railed.over)} marks for one · {len(every_rail.marks)} for the facet",
    )
    check(
        "a window is drawn IN the frame, over the text it floats on",
        len(railed.over) > len(frame({}).over)
        and {"winhead", "wincorner", "shut"} <= {h.split(" ")[4] for h in railed.hits},
    )
    check(
        "and nothing reaches through it",
        "win" in {h.split(" ")[4] for h in railed.hits},
    )
    check(
        "a facet clips: what runs past its edge stops there",
        sum(1 for m in frame({}).marks if m.startswith("clip ")) >= 4
        and sum(1 for m in frame({}).marks if m == "unclip")
        == sum(1 for m in frame({}).marks if m.startswith("clip ")),
    )
    railer = Session(reading)
    railer.main.update({"windows": "w0", "win.w0": "rail 200 200 560 200 member"})
    railer.gesture("at railgo w0:array")
    check(
        "a door in a pinned rail navigates that rail in place",
        railer.main.get("windows") == "w0"
        and railer.main.get("win.w0", "").endswith(" array"),
        railer.main.get("win.w0", "missing"),
    )
    check(
        "a pinned rail's rule doors address their own window",
        any(
            part[4] == "railgo" and part[5].startswith("w0~w0:")
            for part in (hit.split(" ") for hit in railed.hits)
        ),
    )
    check(
        "the idle readout always says what is at the cursor",
        any(word.startswith("at the cursor ·") for word in words(frame({}))),
    )
    check(
        "the ladder keeps its complete text",
        f"{DOCUMENT.name} ⊳ {READER.name}  ∴" in words(frame({})),
        f"{DOCUMENT.name} ⊳ {READER.name} ∴",
    )

    dial_sets = {
        "depth3d": {"levelstep", "ringscale", "flatten", "labelscale"},
        "flat": {"levelstep", "ringscale", "labelscale"},
        "arcs": {"levelstep", "ringscale", "labelscale"},
        "rails": {"levelstep", "labelscale"},
        "automaton": {"levelstep", "ringscale", "labelscale"},
    }
    alternatives = {
        "levelstep": "280",
        "ringscale": "2",
        "flatten": "0.2",
        "labelscale": "1.8",
    }
    for view, expected in dial_sets.items():
        state = {"graph.view": view, "tab.reader": "1"}
        base = frame(state)
        dials = {
            part[0].removeprefix("graph."): part
            for part in (pick.split(" ") for pick in base.picks)
            if part[6].startswith("range:")
        }
        check(
            f"the {view} sliders are real ranges with the right jobs",
            set(dials) == expected
            and all(
                float(parts[5]) >= float(parts[6].split(":")[1])
                for parts in dials.values()
            )
            and float(dials["labelscale"][5]) == 1.0,
            " ".join(sorted(dials)),
        )
        for key in expected:
            tuned = frame({**state, f"graph.{key}": alternatives[key]})
            check(
                f"the {view} {key} slider changes its drawing",
                tuned.marks != base.marks or tuned.hits != base.hits,
            )
    auto = frame({"graph.view": "automaton", "tab.reader": "1"})
    check(
        "the automaton draws filled states, including states already visited",
        len(marks(auto, "dot")) > 8,
        f"{len(marks(auto, 'dot'))} filled states",
    )
    check(
        "a control with more than one value is a real dropdown",
        {"form", "chart.clock"} <= {p.split(" ")[0] for p in frame({}).picks}
        and all(len(p.split(" ")[6].split("|")) > 1 for p in frame({}).picks),
        " · ".join(p.split(" ")[0] for p in frame({}).picks),
    )
    # THE SAME ROWS ON THE SAME LINES, whichever clock is asked. The name
    # column follows the widest gutter — `@4,188` is not `d7` — so it is the
    # gutter and the pitch that must not move, and three panels that each
    # invented their own tones and spacing is what the defect was.
    shapes = {
        clock: sorted(
            {
                (float(m[1]), float(m[2]))
                for m in marks(frame({"chart.clock": clock}, at=900.0), "text")
                if m[3] == "dimmer" and float(m[1]) > 1060 and 590 < float(m[2]) < 700
            }
        )[:4]
        for clock in ("model", "pda", "earley")
    }
    # the band's own tones, wherever the region put it — a y that happened to
    # be right in one arrangement is a fact about the arrangement
    bands = {
        clock: {
            m[5]
            for m in marks(frame({"chart.clock": clock}), "box")
            if m[5].startswith(("modelband", "pdaband", "hypband", "hypboth"))
            or m[5] in ("pdadecided", "hypdead")
        }
        for clock in ("model", "pda", "earley")
    }
    check(
        "the overview band is the CLOCK's, not the model's three times over",
        len({frozenset(said) for said in bands.values()}) == 3,
        " · ".join(f"{c}:{len(s)}" for c, s in bands.items()),
    )

    def window(at: float) -> float:
        """Where the outline on the band sits — the stretch the lanes are of."""
        # it is one ring now, not four lines drawn by hand
        outlines = [
            float(m[1])
            for m in marks(frame({}, at=at), "ring")
            # the outline on the BAND — above where the lanes start, which
            # carry warm rings of their own
            if m[5] == "warm" and float(m[1]) > 1060 and float(m[2]) < 90
        ]
        return min(outlines) if outlines else -1.0

    check(
        "the band says WHICH stretch the lanes below are of, and follows",
        0 < window(1000.0) < window(8000.0) < window(15000.0),
        f"{window(1000.0):.0f} → {window(8000.0):.0f} → {window(15000.0):.0f}",
    )

    # every clock says WHAT IT IS SHOWING, and carries a second panel under
    # its stack — three clocks that each invented their own furniture made
    # one panel read as three
    for clock, caption, foot in (
        ("model", "open at the cursor", "JUST CLOSED"),
        ("pda", "the PDA's stack at t", "DECISIONS"),
        ("earley", "the chart's column at t", "CAN COME NEXT"),
    ):
        spoken = words(frame({"chart.clock": clock}, at=900.0))
        below = words(frame({"chart.clock": clock, "top.spine": "9999"}, at=900.0))
        check(
            f"the {clock} spine says what it is showing, and what is beside it",
            any(w.startswith(caption) for w in spoken) and foot in below,
            f"{caption} · {foot}",
        )
    check(
        "the spine keeps one voice, whichever clock answers",
        len({tuple(rows) for rows in shapes.values() if rows}) == 1,
        " · ".join(f"{c}:{len(r)}" for c, r in shapes.items()),
    )

    def seams(state: dict[str, str]) -> list[tuple[int, float, float, float]]:
        """Every seam: which split, where it sits, and whose box it divides."""
        return [
            (int(h[5]), float(h[0]), float(h[6]), float(h[7]))
            for h in (said.split(" ") for said in frame(state).hits)
            if h[4] == "seam"
        ]

    was = seams({})
    check(
        "a seam knows WHOSE box its share is a share of",
        len(was) > 2 and any(base > 0 for _at, _x, base, _size in was),
        " · ".join(f"{at}:{base:.0f}+{size:.0f}" for at, _x, base, size in was),
    )
    # the hand puts a nested seam at 1200: (1200 - base) / size is what the
    # leaf sends, and the cut must land back under the pointer
    at, _x, base, size = was[1]
    dragged_to = seams(
        {"arrange.shares": " ".join(["-1"] * at + [f"{(1200 - base) / size:.3f}"])}
    )
    check(
        "a seam lands where the hand put it",
        abs(dragged_to[1][1] + 3 - 1200) < 2,
        f"asked 1200 · got {dragged_to[1][1] + 3:.0f}",
    )
    check(
        "and moving one seam moves NOTHING else",
        abs(dragged_to[0][1] - was[0][1]) < 0.5,
        f"seam 0 was {was[0][1]:.0f}, now {dragged_to[0][1]:.0f}",
    )

    shape = str(staged(reading, {}).policy["arrange.tree"])
    surfaces = {
        word.strip("()")
        for word in shape.split()
        if word.strip("()") and not word.strip("()")[0].isdigit()
    } - {"h", "v", "t"}
    check(
        "a surface's head is an alias of its node — you can take hold of it",
        {h.split(" ")[5] for h in frame({}).hits if h.split(" ")[4] == "head"}
        == surfaces - {"graph"},
        f"{len(surfaces)} surfaces",
    )
    for zone, at in (("bottom", "0.5 0.9"), ("left", "0.1 0.5"), ("tab", "0.5 0.5")):
        said_move = moved(shape, "spine", "grammar", zone)
        kept = {
            word.strip("()")
            for word in said_move.split()
            if word.strip("()") and not word.strip("()")[0].isdigit()
        } - {"h", "v", "t"}
        check(
            f"dropping a surface {zone} of another keeps every surface",
            kept == surfaces and said_move != shape,
            said_move,
        )
    check(
        "and says what it would do BEFORE the hand lets go",
        any(
            "tab with" in w or "split bottom" in w
            for w in words(frame({"drop": "chart document 0.5 0.5"}))
        ),
        next(
            (
                w
                for w in words(frame({"drop": "chart document 0.5 0.5"}))
                if "tab with" in w or "split " in w
            ),
            "said nothing",
        ),
    )

    def reader_top(state: dict[str, str]) -> int:
        return next(
            (
                int(p.split(" ")[7])
                for p in frame(state).planes
                if p.startswith("grammar ")
            ),
            -1,
        )

    torn_reader = Session(reading)
    torn_reader.gesture("at rule digit")
    check(
        "choosing a rule SHOWS it — a highlight you must go looking for is none",
        reader_top({}) == 0 and reader_top(dict(torn_reader.main)) > 0,
        f"{reader_top({})} → {reader_top(dict(torn_reader.main))}",
    )
    torn_reader.gesture("scrolled grammar 0")
    check(
        "and a hand that scrolls says where it wants to be",
        reader_top(dict(torn_reader.main)) == 0,
        f"back to {reader_top(dict(torn_reader.main))}",
    )

    # THE STATUS BAR PROMISES THESE. A promise the instrument does not keep
    # is worse than one it never made.
    keyed = Session(reading)
    keyed.gesture("key ]")
    keyed.gesture("key ]")
    check(
        "] and [ are the speed the hint says they are",
        keyed.main.get("speed") == "4",
        f"×{keyed.main.get('speed')}",
    )
    keyed.gesture("key [")
    check("and back", keyed.main.get("speed") == "2", f"×{keyed.main.get('speed')}")
    keyed.gesture("key g")
    check(
        "g takes the relations out of the arrangement, and brings them back",
        keyed.main.get("facet.graph") == "off",
        keyed.main.get("facet.graph", "unset"),
    )
    keyed.gesture("sel document 100 140")
    keyed.gesture("key p")
    check(
        "p pins what is selected",
        bool(keyed.main.get("windows")),
        keyed.main.get("win.w0", "no window"),
    )

    def doc_top(state: dict[str, str]) -> int:
        return next(
            (
                int(p.split(" ")[7])
                for p in frame(state).planes
                if p.startswith("document ")
            ),
            -1,
        )

    walked_on = Session(reading)
    walked_on.gesture("go 8000")
    followed = doc_top(dict(walked_on.main))
    line = reading.text.count("\n", 0, 8000)
    check(
        "the document FOLLOWS the cursor — it is being read as it goes",
        0 < followed < line and line - followed < 30,
        f"char 8,000 is line {line:,} · page starts at {followed:,}",
    )
    walked_on.gesture("scrolled document 300")
    check(
        "until a hand says otherwise",
        doc_top(dict(walked_on.main)) == 300,
        f"{doc_top(dict(walked_on.main))}",
    )

    reader_lines = {
        m[5]
        for m in marks(
            frame({"chosen": "member", "hover": "rule value"}, at=900.0), "box"
        )
        if m[5] in ("liveline", "lit", "hotline")
    }
    check(
        "the reader lights three different questions, not one",
        reader_lines == {"liveline", "lit", "hotline"},
        " ".join(sorted(reader_lines)),
    )

    graphed = frame({"tab.reader": "1"})
    boxed = {m[5] for m in marks(graphed, "line") if float(m[2]) == float(m[4])}
    check(
        "a graph's node is a NAME IN A BOX, and the box says what it is",
        {"cool", "warm"} <= boxed,
        " ".join(sorted(boxed)),
    )
    check(
        "and its distance is in the size of its name",
        len(
            {
                m[4]
                for m in marks(graphed, "text")
                if m[4].startswith("g") or m[4] == "chip"
            }
        )
        > 1,
        " ".join(sorted({m[4] for m in marks(graphed, "text")})),
    )

    quiet_graph = frame({"tab.reader": "1"})
    hovered_graph = frame({"tab.reader": "1", "hover": "rule value"})
    check(
        "live graph nodes are warm outlines, not hot filled slabs",
        not any(m[5] == "hot" for m in marks(quiet_graph, "box")),
    )
    check(
        "only the graph node under the hand fills hot",
        any(m[5] == "hot" for m in marks(hovered_graph, "box")),
    )
    check(
        "a live graph edge is the 2px step in the open stack",
        any(
            m[5] == "hot" and len(m) > 6 and m[6] == "2.0"
            for m in marks(quiet_graph, "line")
        ),
    )

    arcs = frame({"tab.reader": "1", "graph.view": "arcs"})
    check(
        "the arcs view names only exceptional nodes and draws the rest as dots",
        len(marks(arcs, "dot")) > 20,
        f"{len(marks(arcs, 'dot'))} dots",
    )

    flat = frame({"tab.reader": "1", "graph.view": "flat"})
    rule_names = {name for name, _first, _last in names}
    flat_faces = {
        m[4]
        for m in marks(flat, "text")
        if m[4] in {"gnear", "gfar", "chip"} and " ".join(m[6:]) in rule_names
    }
    check(
        "a flat graph at scale one uses the normal 10px node face",
        flat_faces == {"chip"},
        " ".join(sorted(flat_faces)),
    )

    def placed(session_state: Session) -> dict[str, tuple[float, float]]:
        said_frame = compose(
            reading, 1500, 850, 4200.0, dict(session_state.main), watched, 1
        )
        return {
            h.split(" ")[5]: (float(h.split(" ")[0]), float(h.split(" ")[1]))
            for h in said_frame.hits
            if h.split(" ")[4] == "head"
        }

    torn = Session(reading)
    before = placed(torn)
    torn.gesture("pop spine")
    during = placed(torn)
    torn.gesture("at shut w0")
    check(
        "a popped facet leaves the tree, and comes back exactly where it was",
        "spine" not in during and placed(torn) == before,
        f"{len(before)} → {len(during)} → {len(placed(torn))} surfaces",
    )

    # ONE STATE, ONE FRAME. The reference's graph is not reproducible across
    # loads — its frame cache is keyed by a value assigned before the fetch
    # that fills it resolves, so two captures of one settled session differ
    # across most of the facet. Everything here is worked out from the
    # drawing it is about to place, in the same frame, and that is why this
    # port can be compared to anything at all.
    twice_over: list[tuple[str, dict[str, str]]] = [
        *(
            (view, {"graph.view": view, "tab.reader": "1"})
            for view in ("depth3d", "flat", "arcs", "rails", "automaton")
        ),
        *(
            (f"{clock} clock", {"chart.clock": clock})
            for clock in ("model", "pda", "earley")
        ),
        ("strata", {"showing": "strata"}),
        ("a room", {"place": "machine"}),
    ]
    for says, state in twice_over:
        once = frame(state).wire(1)
        again = frame(state).wire(1)
        check(
            f"{says} draws the same picture twice",
            once == again,
            f"{len(once):,} bytes",
        )

    print("what it costs")
    frame({})
    clock = time.perf_counter()
    for i in range(20):
        frame({}, at=4200.0 + i)
    each = (time.perf_counter() - clock) * 1000 / 20
    check(
        "a frame costs under 20 ms once the reading is known",
        each < 20,
        f"{each:.1f} ms",
    )
    map_subjects = [reading]
    for i in range(1, 20):
        another = copy(reading)
        another.text = f"{reading.text}\n{i}"
        map_subjects.append(another)
    frame({"showing": "strata"}, climbed=map_subjects)
    clock = time.perf_counter()
    for _ in range(10):
        frame({"showing": "strata"}, climbed=map_subjects)
    each = (time.perf_counter() - clock) * 1000 / 10
    check(
        "the map frame costs under 20 ms at 20 subjects",
        each < 20,
        f"{each:.1f} ms",
    )

    hot_paths = (
        (
            "scrolling a prolific selected rule stays inside the frame budget",
            [{"chosen": "ws", "top.document": str(250 + i)} for i in range(20)],
        ),
        (
            "turning the 3d graph during playback stays inside the frame budget",
            [
                {
                    "tab.reader": "1",
                    "graph.view": "depth3d",
                    "playing": "1",
                    "graph.depth3d.yaw": str(0.42 + i * 0.01),
                    "graph.depth3d.pitch": str(0.92 - i * 0.005),
                }
                for i in range(20)
            ],
        ),
    )
    for claim, states in hot_paths:
        frame(states[0])
        clock = time.perf_counter()
        for i, state in enumerate(states):
            frame(state, at=4200.0 + i)
        each = (time.perf_counter() - clock) * 1000 / len(states)
        check(claim, each < 20, f"{each:.1f} ms")

    print("the leaf")
    leaf = HERE / "leaf"
    page = (leaf / "index.html").read_text()
    named = [n for n in ("leaf.js", "leaf.css") if n in page]
    check(
        "the page names its parts and they are files",
        len(named) == 2 and all((leaf / n).is_file() for n in named),
    )
    js = (leaf / "leaf.js").read_text()
    check(
        "the leaf holds no colour of its own",
        # a colour LITERAL — not a wire block, which is also spelled with a
        # hash and is the leaf reading what it was sent
        not re.search(r"#[0-9a-fA-F]{3,8}\b|rgba?\(", js),
        f"{len(js.splitlines())} lines",
    )

    print(f"\n{len(SAYS)} gestures · {len(KEYS)} keys · {len(failed)} failures")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
