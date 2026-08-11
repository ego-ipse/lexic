"""What must hold, printed as facts, so a false one is visible.

Run::

    uv run python .../space_1/gate.py

Every check here defends something that was got WRONG before: the layout
being a shape someone liked, a surface silently crushed, a wrong pairing
smoothed over, a name the leaf cannot recognise.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from praxis.state import chain  # noqa: E402
from eidolon.topology import graph_facet  # noqa: E402
from kairos.artefacts import keep  # noqa: E402
from lexic.compile import compile_text  # noqa: E402
from kairos.machine import of  # noqa: E402
from opsis.space import FLOOR, arrange, shares  # noqa: E402
from praxis.reading import (  # noqa: E402
    Facet,
    as_written,
    columns,
    read,
    read_up,
    upward,
)
from praxis.history import retype  # noqa: E402
from praxis.roots import GRAMMAR as POLICY  # noqa: E402
from praxis.roots import apply_record, record  # noqa: E402
from eidolon.value import graph as ir_graph  # noqa: E402
from eidolon.value import wire as ir_wire  # noqa: E402
from kairos.pipeline import FORMS  # noqa: E402
from opsis.grammar import rails  # noqa: E402
from opsis.scene import drawn, moved, ruledefs  # noqa: E402
from praxis.strata import strata  # noqa: E402
from serve import PENDING  # noqa: E402
from kairos.parse import watch  # noqa: E402
from kairos.engine import automaton  # noqa: E402

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
    # a share is a proportion of what was ASKED for: a surface that asks for
    # twice as much gets more room, and nothing falls under the floor, where
    # a column shows nothing but a name and an ellipsis.
    given = shares(facets, 200)
    order = [f.name for f in sorted(facets, key=lambda f: f.wide)]
    got = [given[name] for name in order]
    check(
        "room is given in proportion to what was asked, and never under the floor",
        got == sorted(got) and min(got) >= FLOOR,
        " · ".join(f"{n}:{given[n]}" for n in order),
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
    # the relations SHARE the reader's column, as tabs. Two views of one
    # subject do not compete for width — each takes the whole column when it
    # is the one being looked at, which is what the graph needed all along.
    graph = graph_facet(machine.grammar)
    tree = arrange([*facets[:1], graph, *facets[1:]])
    check(
        "the relations share the reader's column instead of competing for it",
        "(t 0 grammar graph)" in tree,
        tree,
    )
    built = of(machine)
    check(
        "the machine is the whole clone set, not the rules it was cut from",
        built.clones > built.rules,
        built.line(),
    )
    # a column asks for its WIDEST member, not the sum: tab-mates take turns
    # at the full width, so pairing two views must not halve either of them.
    pair = [
        Facet("a", "plane", 100, 10, column="one", relation="tabbed"),
        Facet("b", "graph", 100, 10, column="one", relation="tabbed"),
        Facet("c", "plane", 100, 10),
    ]
    paired = arrange(pair)
    check(
        "two views of one subject take turns at a column, they do not halve it",
        "(t 0 a b)" in paired and paired.startswith("(h 0.5"),
        paired,
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
    # the arrangement names surfaces, and every one must be a surface this
    # reading actually placed — a tree naming a facet nobody sends is a
    # layout the leaf silently drops on the floor
    at = next(i for i, line in enumerate(said) if line.startswith("#FACETS "))
    placed = {
        line.split(" ", 1)[0]
        for line in said[at + 1 : at + 1 + int(said[at].split()[1])]
    }
    named = {
        word.strip("()")
        for word in lines.get("arrange.tree", "").split(" ")
        if word.strip("()") and not word.strip("()")[0].isdigit()
    } - {"h", "v", "t"}
    check(
        "the arrangement places every surface, and invents none",
        bool(lines) and named == placed,
        " ".join(sorted(named))
        + (f" · UNPLACED {named - placed}" if named - placed else ""),
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

    # the ladder, walked. Climbing and descending is the one navigation this
    # instrument has, and a rung marked visited with no numbers threw the
    # leaf's renderer mid-draw — which looks like "only the first layer".
    climbed = [reading]
    walked: list[str] = []
    for step in (1, 0, 1):
        while len(climbed) <= step:
            above = read_up(climbed[-1])
            if above is None:
                break
            climbed.append(above)
        said = strata(climbed[step], climbed)
        stats = [ln for ln in said.split("\n") if ln.startswith("k ")]
        cards = [ln for ln in said.split("\n") if ln.startswith("c ")]
        visited = [ln for ln in cards if ln.split(" ")[5] == "1"]
        walked.append(
            f"rung {step}: {len(cards)} cards · {len(visited)} visited · "
            f"{len(stats)} with numbers"
        )
        if len(stats) != len(visited):
            walked[-1] += " ← MISMATCH"
    check(
        "every rung the ladder says is visited carries its own numbers",
        all("MISMATCH" not in line for line in walked),
        " · ".join(walked),
    )

    # the automaton's edges are INDICES into its clone list. Emitting a
    # filtered list after building the edges shifted every index past the
    # first missing clone, and a dangling index threw inside the draw — which
    # killed the animation frame chain, so the derivation could not be played
    # at all while that view was open.
    said_auto = automaton(machine.pda_tables())
    parts: dict[str, list[str]] = {}
    where = ""
    for line in said_auto.split("\n"):
        if line.startswith("#"):
            where = line.split()[0]
            parts[where] = []
        elif where and line:
            parts[where].append(line)
    drawable = len(parts.get("#ACLONES", []))
    links = [tuple(map(int, line.split())) for line in parts.get("#AEDGES", [])]
    dangling = [e for e in links if e[0] >= drawable or e[1] >= drawable]
    check(
        "every automaton edge points at a clone the automaton also sent",
        not dangling and bool(links),
        f"{drawable} clones · {len(links)} edges · {len(dangling)} dangling",
    )

    # an edit moves EVERYTHING derived from the text. The scene said
    # "generation 1" as a literal, so the leaf never learned the text had
    # moved: only the model came back new while every clock, automaton and
    # graph kept answering for the text before the edit.
    from opsis.scene import GENERATION

    put = '\n  "gate-probe": [1, 2, 3],'
    was = (GENERATION[0], len(reading.spans), len(watch(machine, reading.text)))
    edited = retype(reading, 1, 1, put)
    if edited.state != "refused":
        moved()
    now = (GENERATION[0], len(reading.spans), len(watch(machine, reading.text)))
    retype(reading, 1, 1 + len(put), "")
    moved()
    check(
        "an edit moves the generation AND everything derived from the text",
        edited.state != "refused" and all(a != b for a, b in zip(was, now)),
        f"generation {was[0]}→{now[0]} · spans {was[1]:,}→{now[1]:,} · "
        f"pda frames {was[2]:,}→{now[2]:,}",
    )

    # FORMS. The same language at three moments of the pipeline — as
    # written, canonical, as codegen cut it. Each is a legitimate picture,
    # and a view drawing one while another view draws a second is why a
    # choice the machine made never lit: the node was not in that picture.
    # What must hold in EVERY form: every rule a span names is a node of the
    # graph that form draws, or the light has nowhere to land.
    joins: list[str] = []
    for which in FORMS:
        said = drawn(reading, {"form": which})
        block_at = next(
            i for i, line in enumerate(said.split("\n")) if line.startswith("#DEPTHS ")
        )
        rows = said.split("\n")[block_at:]
        nodes = {
            line.rsplit(" ", 1)[0] for line in rows[1 : 1 + int(rows[0].split()[1])]
        }
        names_at = next(
            i
            for i, line in enumerate(said.split("\n"))
            if line.startswith("#RULENAMES ")
        )
        rows2 = said.split("\n")[names_at:]
        used = set(rows2[1 : 1 + int(rows2[0].split()[1])])
        joins.append(f"{which}: {len(used & nodes)}/{len(used)} of the spans' rules")
        if used - nodes:
            joins[-1] += f" ← {sorted(used - nodes)[:2]} NOT in the picture"
    moved()
    check(
        "in every form, what the model names is what the graph draws",
        all("NOT in the picture" not in said for said in joins),
        " · ".join(joins),
    )

    # a track is measured HERE, in columns, because a railroad measured by
    # a browser's font metrics is a shape nothing can check. What must hold:
    # nothing is given less room than what it says, and every node line has
    # a box — an off-by-one in the pairing silently shifts every size.
    tracks = rails(machine.grammar)
    pairs, tight = 0, []
    for block_text in tracks.split("#RAIL ")[1:]:
        head, _, body = block_text.partition("\n")
        count = int(head.split()[-1])
        rows = body.split("\n")
        node_lines, box_lines = rows[:count], rows[count + 1 : count + 1 + count]
        pairs += len(node_lines)
        if len(box_lines) != len(node_lines):
            tight.append(
                f"{head.split()[0]}: {len(box_lines)} boxes for {len(node_lines)}"
            )
            continue
        for measured in box_lines:
            fields = measured.split(" ", 3)
            label = fields[3] if len(fields) > 3 else ""
            if label and float(fields[0]) < columns(label):
                tight.append(f"{label!r} in {float(fields[0]):.0f} columns")
    check(
        "every track is measured in columns, and nothing is smaller than it says",
        not tight and pairs > 0,
        f"{pairs} nodes measured" + (f" · TIGHT {tight[:2]}" if tight else ""),
    )

    # the relationships. The leaf's scene reader has always had a place for
    # these two blocks and the server never filled it, so every graph drew
    # rules as unrelated dots — for the life of the build, unnoticed.
    frame = drawn(reading)

    def block(tag: str) -> list[str]:
        if f"#{tag} " not in frame:
            return []
        head, rest = frame.split(f"#{tag} ", 1)[1].split("\n", 1)
        return rest.split("\n")[: int(head)]

    relations, depths = block("EDGES"), block("DEPTHS")
    reached = [line for line in depths if not line.endswith(" -1")]
    check(
        "the scene carries WHICH RULE REFERS TO WHICH, not just the names",
        bool(relations) and len(reached) > 1,
        f"{len(relations)} edges · {len(reached)}/{len(depths)} rules reachable "
        f"from the start rule",
    )

    # the value surface: what a grammar IS once loaded. Two things must
    # hold or the picture lies — the wire must survive values whose payload
    # contains a newline (the reducer's own literals do), and a shared object
    # must be ONE node reached N times, never N copies.
    loaded = compile_text(reading.reader_text, flavour="gbnf")
    subjects = {
        "grammar": loaded.grammar,
        "codegen": loaded.codegen_grammar,
        "reducer": get_flavour("gbnf").reducer,
    }
    torn: list[str] = []
    identity: list[str] = []
    sharing: list[int] = []
    for name, value in subjects.items():
        body = ir_wire(value)
        rows = body.split("#NODES ", 1)[1].split("\n")
        count = int(rows[0])
        torn += [
            f"{name}:{i}"
            for i, row in enumerate(rows[1 : count + 1])
            if not row.split(" ", 1)[0].isdigit()
        ]
        walk = ir_graph(value)
        shared = [at for at, n in walk.refs.items() if n > 1]
        sharing.append(len(shared))
        identity.append(
            f"{name} {len(walk.nodes)} nodes · {len(shared)} shared "
            f"reached {sum(walk.refs[at] for at in shared)}×"
        )
    check(
        "a value's wire survives its own payloads, and sharing is identity",
        not torn and all(sharing),
        " · ".join(identity) + (f" · TORN {torn[:3]}" if torn else ""),
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
    page = (leaf / "index.html").read_text()
    # the leaf is one program living in several files, so its parts are
    # whatever the page NAMES — a script that stops being served takes its
    # whole section down silently, and nothing else would notice
    named = [
        *re.findall(r'<script src="/([^"]+)"', page),
        *re.findall(r'<link[^>]+href="/([^"]+)"', page),
    ]
    absent = [name for name in named if not (leaf / name).is_file()]
    check(
        "every part the leaf's page names is a file the socket can serve",
        not absent and bool(named),
        f"{len(named)} parts · {sum((leaf / n).stat().st_size for n in named if (leaf / n).is_file()) // 1024}KB"
        + (f" · MISSING {', '.join(absent)}" if absent else ""),
    )
    check(
        "the leaf hosts every surface this reading places",
        all(f'id="{name}"' in page for name in placed),
        " ".join(sorted(placed)),
    )
    print(f"{len(facets)} surfaces · {len(failed)} failures")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
