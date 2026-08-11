"""What must hold about a FRAME, printed as facts, so a false one is visible.

Run::

    uv run python .../space_2/gate.py

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
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from kairos.parse import watch  # noqa: E402
from opsis.frame import compose  # noqa: E402
from opsis.frame.facets import HEADS, Look  # noqa: E402
from opsis.frame.marks import Frame  # noqa: E402
from opsis.frame.tones import EDGES, FONTS, TONES  # noqa: E402
from opsis.scene import reader_of, ruledefs, staged  # noqa: E402
from opsis.space import moved  # noqa: E402
from praxis.reading import Reading, as_written  # noqa: E402
from praxis.session import KEYS, LANDED, SAYS, Session  # noqa: E402
from praxis.state import chain  # noqa: E402

ROOT = HERE.parents[2]
GROUND = ROOT / "resources" / "ground_truth"
READER = GROUND / "json.gbnf"
DOCUMENT = HERE.parent / "tk" / "fixtures_long.json"

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
    faces = {m.split(" ")[4] for m in said.marks if m.startswith("text ")}
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
    by_session = set(LANDED) | {
        "scroll",
        "seam",
        "pin",
        "rail",
        "facet",
        "strata",
        "place",
        "do",
        "form",
        "graph.view",
        "chart.clock",
        "graph.focus",
        "dial.levelstep",
        "dial.ringscale",
        "dial.flatten",
    }
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
        any(m[5] == "hotline" for m in marks(chosen, "box")),
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
    typer = Session(Reading(READER, DOCUMENT))
    typer.reading.hold()
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
    broke = Session(Reading(READER, DOCUMENT))
    broke.reading.hold()
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
        popper.main.get("facet.spine") == "off"
        and "THE SPINE"
        not in words(compose(reading, 1500, 850, 0.0, popper.main, watched, 1)),
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
            "STALE" in w
            for w in words(frame({"pin.span": "20:46", "pin.gen": "0"}, only="pin"))
        ),
    )

    print("travel")
    climber = Session(Reading(READER, DOCUMENT))
    climber.reading.hold()
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
    climber.gesture("at rung 0")
    check(
        "and the rung below is still there to come back to",
        climber.reading is climber.climbed[0],
    )

    print("the ring")
    ringer = Session(Reading(READER, DOCUMENT))
    ringer.reading.hold()
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
        any(
            w.startswith("char ") and " · line " in w and w.endswith("gen 1")
            for w in words(lit)
        )
        and any("outlined violet" in w for w in words(lit)),
        next((w for w in words(lit) if w.startswith("char ")), "no position"),
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
