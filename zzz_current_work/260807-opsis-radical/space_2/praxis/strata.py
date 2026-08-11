"""The ladder — every rung walked, the one above it, and the doors it holds.

A function of where you stand and what you have climbed, so what the leaf is
sent can be asked for and checked without a socket in the way.
"""

from __future__ import annotations

from praxis.state import Rung
from praxis.reading import Reading, reader_of, ruledefs, profile, upward
from kairos.machine import of
from eidolon.value import graph as ir_graph
from kairos.artefacts import keep

__all__ = ["strata"]


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
