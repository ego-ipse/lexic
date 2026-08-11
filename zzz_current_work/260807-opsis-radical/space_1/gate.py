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

from place import arrange, shares, windowed  # noqa: E402
from read import as_written, read, upward  # noqa: E402
from serve import scene  # noqa: E402

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
        "a surface that cannot be honoured asks for a window",
        bool(windowed(facets, 120)),
        ", ".join(windowed(facets, 120)),
    )
    up = upward(reading)
    check(
        "a reader is a thing that can also be read — the rung above is named",
        up is not None and up[1].endswith("metagrammar"),
        " ⊳ ".join(up) if up else "nothing reads it",
    )
    from serve import ruledefs

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
    from lexic.compile import compile_text
    from watch import watch

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
    from keep import keep

    made = keep(machine)
    check(
        "an artefact counts only once it has been LOADED BACK",
        bool(made) and all(a.witness == "holds" for a in made),
        " · ".join(a.line() for a in made),
    )
    drawn = scene(reading)
    check(
        "the scene carries the reader, the document, the spans and the tree",
        all(t in drawn for t in ("#READER ", "#DOC ", "#SPANS ", "arrange.tree (")),
        f"{len(drawn):,} chars",
    )
    print(f"{len(facets)} surfaces · {len(failed)} failures")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
