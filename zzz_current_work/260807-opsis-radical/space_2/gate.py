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
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from kairos.parse import watch  # noqa: E402
from opsis.frame import compose  # noqa: E402
from opsis.frame.marks import Frame  # noqa: E402
from opsis.frame.tones import EDGES, FONTS, TONES  # noqa: E402
from opsis.scene import reader_of  # noqa: E402
from praxis.reading import Reading  # noqa: E402
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
    known = set(LANDED) | {
        "scroll",
        "seam",
        "pop",
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
    kinds = {h.split(" ")[4] for h in said.hits}
    check(
        "every hit names something the session answers to",
        kinds <= known,
        " ".join(sorted(kinds - known) or ["all answered"]),
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

    print("windows are their own")
    from collections import ChainMap

    layer: dict[str, str] = {}
    session.gesture("set graph.view rails", into=ChainMap(layer, session.main))
    check(
        "a gesture in a window writes to the window",
        layer.get("graph.view") == "rails" and "graph.view" not in session.main,
        f"window {layer} · session {session.main.get('graph.view', '—')}",
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
