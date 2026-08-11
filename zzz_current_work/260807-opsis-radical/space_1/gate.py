"""What must hold, printed as facts, so a false one is visible.

Run::

    uv run python .../space_1/gate.py

Every check here defends something that was got WRONG before: the layout
being a shape someone liked, a surface silently crushed, a wrong pairing
smoothed over, a name the leaf cannot recognise.
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from chain import chain  # noqa: E402
from draw import graph_facet  # noqa: E402
from keep import keep  # noqa: E402
from lexic.compile import compile_text  # noqa: E402
from machine import machine_facet, of  # noqa: E402
from place import arrange, shares, windowed  # noqa: E402
from read import as_written, columns, read, read_up, upward  # noqa: E402
from retype import retype  # noqa: E402
from ring import GRAMMAR as POLICY  # noqa: E402
from ring import apply_record, record  # noqa: E402
from serve import PENDING, drawn, ruledefs  # noqa: E402
from watch import watch  # noqa: E402

ROOT = HERE.parents[2]
GRAMMAR = ROOT / "resources/ground_truth/json.gbnf"
DOCUMENT = HERE.parent / "tk/fixtures_long.json"
ABNF = ROOT / "resources/ground_truth/json.abnf"

# the leaf knows these four and drops a tree naming anything else
KNOWN = {"grammar", "document", "chart", "spine"}


def main() -> int:
    failed: list[str] = []

    def check(name: str, holds: bool, note: str = "") -> None:
        print(
            f"{'holds' if holds else 'FAILS'} — {name}" + (f" · {note}" if note else "")
        )
        if not holds:
            failed.append(name)

    reading = read(GRAMMAR, DOCUMENT)
    facets = reading.facets()
    check(
        "the reading is faithful — it re-emits its own text",
        reading.faithful,
        f"{len(reading.spans):,} spans in {reading.seconds:.2f}s",
    )
    check(
        "every surface is named the way the leaf names it",
        {f.name for f in facets} == KNOWN,
        " ".join(sorted(f.name for f in facets)),
    )
    check(
        "the grammar gets more room than the document when IT is the wider text",
        shares(facets, 200)["grammar"] > shares(facets, 200)["document"],
        f"grammar {facets[0].wide} cols · document {facets[1].wide} cols",
    )
    other = read(ABNF, GRAMMAR)
    swapped = other.facets()
    check(
        "the arrangement is per READING, not one shape for all",
        arrange(facets) != arrange(swapped),
        f"{arrange(facets)} vs {arrange(swapped)}",
    )
    check(
        "a wrong pairing is shown as one, in the engine's words",
        not other.faithful and not other.spans and "does not derive" in other.words,
        other.words[:60],
    )
    check(
        "ordinary squeezing is tolerated; a halving is not",
        not windowed(facets, 200) and bool(windowed(facets, 100)),
        f"at 200: none · at 100: {', '.join(windowed(facets, 100)) or 'none'}",
    )
    up = upward(reading)
    check(
        "a reader is a thing that can also be read — the rung above is named",
        up is not None and up[1].endswith("metagrammar"),
        " ⊳ ".join(up) if up else "nothing reads it",
    )
    rules = ruledefs(reading.reader_text)
    lit = {as_written(rules, s.rule) for s in reading.spans}
    named = {n for n, _, _ in rules}
    check(
        "every span lights a rule the grammar shows, in the grammar's spelling",
        lit <= named,
        f"{len(lit)} names, none dark"
        if lit <= named
        else f"dark: {sorted(lit - named)}",
    )
    machine = compile_text(reading.reader_text, flavour="gbnf")
    frames = watch(machine, reading.text)
    seats = {row[5] for row in frames}
    check(
        "the clock reports frames the kernel actually pushed, seated by clone",
        len(frames) > 1000 and len(seats) > 1,
        f"{len(frames):,} frames · {len(seats)} clones entered",
    )
    check(
        "a frame's span is measured, never assumed — the abandoned ones say so",
        all(row[1] >= row[0] for row in frames),
        f"{sum(1 for row in frames if not row[4])} abandoned",
    )
    made = keep(machine)
    check(
        "an artefact counts only once it has been LOADED BACK",
        bool(made) and all(a.witness == "holds" for a in made),
        " · ".join(a.line() for a in made),
    )
    before = reading.text
    legal = retype(reading, 0, 0, "")
    broke = retype(reading, 5000, 5001, chr(1))
    check(
        "a refused re-read restores the document and MEASURES the frontier",
        broke.state == "refused" and broke.pos == 5000 and reading.text == before,
        f"{legal.line()} · {broke.line()[:60]}",
    )
    kept = {"arrange.tree": arrange(facets), "chart.clock": "model"}
    said = Path("/tmp/opsis_record.txt")
    said.write_text(record(kept))
    mirror = read(POLICY, said)
    check(
        "the instrument reads its own state, and saving it applies it",
        mirror.faithful and apply_record(mirror.text) == kept,
        f"{len(mirror.spans)} spans over its own record",
    )
    rungs = chain(reading)
    check(
        "the chain names the rung above without parsing it",
        len(rungs) == 2 and rungs[0].visited and not rungs[1].visited,
        " | ".join(r.line() for r in rungs),
    )
    check(
        "a stratum is a DEPTH, not a position in a row",
        [r.level for r in rungs] == list(range(len(rungs))),
        " ".join(str(r.level) for r in rungs),
    )
    graph = graph_facet(machine.grammar)
    room = shares([*facets, graph], 200)["graph"]
    check(
        "the graph says what it needs, and asks for a window when it cannot fit",
        graph.wide > room and "graph" in windowed([*facets, graph], 200),
        f"needs {graph.wide} cols over {graph.tall} levels, offered {room}",
    )
    built = of(machine)
    room = machine_facet(machine)
    check(
        "the machine is the whole clone set, and it asks for a window",
        built.clones > built.rules and "machine" in windowed([*facets, room], 200),
        built.line(),
    )
    from read import Facet

    # sized so both are offered ~70% of an identical ask: comfortable for a
    # plane, a collision for a graph. Same width, same share, different kind.
    same = [
        Facet("plane-ish", "plane", 100, 10),
        Facet("graph-ish", "graph", 100, 10),
        Facet("filler", "plane", 85, 10),
    ]
    flagged = windowed(same, 200)
    check(
        "the same squeeze a plane survives is a misfit for a graph",
        "graph-ish" in flagged and "plane-ish" not in flagged,
        f"flagged {', '.join(flagged) or 'nothing'}",
    )
    frame = drawn(reading)
    check(
        "the scene carries the reader, the document, the spans and the tree",
        all(t in frame for t in ("#READER ", "#DOC ", "#SPANS ", "arrange.tree (")),
        f"{len(frame):,} chars",
    )
    for other in (ROOT / "resources/ground_truth").glob("*.gbnf"):
        if other.name == "json.gbnf":
            continue
        # a grammar read by ITSELF is a wrong pairing — arithmetic.gbnf
        # describes arithmetic, not grammar text. What this proves is that the
        # measurement works on a grammar the build never saw, and that the
        # wrong pairing is refused rather than smoothed over.
        far = read(other, other)
        check(
            f"an unfamiliar grammar measures, its wrong pairing refused: {other.name}",
            len(far.facets()) == 4 and far.facets()[0].wide > 0 and not far.faithful,
            " ".join(f"{x.name}:{x.wide}" for x in far.facets()),
        )
        break

    # parse the policy block as it IS, not at a hardcoded size: guarding on
    # "#POLICY 7" made these pass vacuously while printing "missing", which is
    # the exact failure a gate exists to prevent.
    said = frame.splitlines()
    head = next((i for i, line in enumerate(said) if line.startswith("#POLICY ")), -1)
    count = int(said[head].split()[1]) if head >= 0 else 0
    lines = dict(line.split(" ", 1) for line in said[head + 1 : head + 1 + count])
    check(
        "the policy block is there and says how long it is",
        head >= 0 and len(lines) == count > 0,
        f"{len(lines)} of {count} lines",
    )
    check(
        "every surface named in wants.window appears in needs",
        bool(lines)
        and all(
            name in lines["needs"]
            for name in lines["wants.window"].split(",")
            if name != "none"
        ),
        lines.get("wants.window", "MISSING"),
    )
    check(
        "every refused surface says where it opens, or says it cannot",
        bool(lines)
        and all(":" in part for part in lines["opens"].split(" ") if part != "none"),
        lines.get("opens", "MISSING"),
    )

    # the length-prefixed blocks are the wire's other contract: the leaf
    # slices #READER and #DOC by the count we send, so a wrong count hands it
    # the wrong text and nothing says why.
    for tag, text in (("#READER", reading.reader_text), ("#DOC", reading.text)):
        marker = f"{tag} {len(text)}\n"
        check(
            f"{tag} says its own length, and the text follows it exactly",
            marker in frame and frame.split(marker, 1)[1].startswith(text[:80]),
            f"{len(text):,} chars",
        )

    check(
        "width is COLUMNS, not characters — a wide glyph takes two",
        columns("ですが") == 6 and columns("abc") == 3,
        f"ですが={columns('ですが')} abc={columns('abc')}",
    )

    from time import perf_counter

    drawn(reading)  # warm
    mark = perf_counter()
    for _ in range(20):
        drawn(reading)
    poll = (perf_counter() - mark) / 20
    check(
        "a poll costs nothing while the text stands still",
        poll < 0.001,
        f"{poll * 1000:.3f}ms per poll",
    )
    reading.text += " "
    check(
        "and the scene is rebuilt the moment the text moves",
        drawn(reading) != frame,
        "rebuilt on change",
    )
    reading.text = reading.text[:-1]

    # travel: the ladder must walk BOTH ways. Climbing used to replace the
    # current reading, so the rungs below vanished and only "up" existed.
    above = read_up(reading)
    check(
        "the rung above is a real reading, not the one below repeated",
        above is not None
        and above.faithful
        and above.text == reading.reader_text
        and above.reader_name != reading.reader_name,
        f"{above.document.name} ⊳ {above.reader_name}" if above else "nothing above",
    )
    check(
        "the climb ends at the fixpoint — a metagrammar reads its own spelling",
        above is not None and (upward(above) or (None, ""))[1] == above.reader_name,
        (upward(above) or (None, "nothing"))[1] if above else "nothing above",
    )

    # transpile: a peer spelling, witnessed. A flavour that spells a grammar
    # but reads it back as something else has not transpiled it.
    from lexic.grammars import get_flavour

    peers = []
    for want in ("abnf", "ebnf"):
        spelled = get_flavour(want).apply(machine.grammar)
        back = compile_text(spelled, flavour=want)
        peers.append((want, len(spelled), back.grammar == machine.grammar))
    check(
        "a transpiled peer reads back EQUAL, or it is not a transpilation",
        all(same for _, _, same in peers),
        " · ".join(
            f"{n} {c:,} chars {'equal' if s else 'DIFFERENT'}" for n, c, s in peers
        ),
    )

    # the routes the leaf calls. A capability can be fully built and still be
    # invisible if nothing answers the address the leaf asks for — which is
    # how rails, verdicts, the automaton and the rooms all sat unreachable.
    asked = [
        "/scene",
        "/policy",
        "/strata",
        "/place",
        "/clock",
        "/column",
        "/rails",
        "/rail",
        "/rulegraph",
        "/verdicts",
        "/automaton",
    ]
    served = sorted(set(asked) - set(PENDING))
    check(
        "every route the leaf calls is answered by derivation, not a stub",
        not PENDING,
        f"{len(served)} answered · {len(PENDING)} stubbed"
        + (f": {', '.join(sorted(PENDING))}" if PENDING else ""),
    )

    leaf = HERE / "leaf"
    parts = ["index.html", "leaf.css", "leaf.js"]
    there = [name for name in parts if (leaf / name).is_file()]
    check(
        "the leaf is present — the measurement has somewhere to arrive",
        there == parts,
        ", ".join(there) or "nothing",
    )
    page = (leaf / "index.html").read_text() if (leaf / "index.html").is_file() else ""
    wanted = {"grammar", "document", "chart", "spine"}
    check(
        "the leaf hosts every surface this reading places",
        all(f'id="{name}"' in page for name in wanted),
        " ".join(sorted(wanted)),
    )
    print(f"{len(facets)} surfaces · {len(failed)} failures")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
