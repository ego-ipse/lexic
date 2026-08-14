"""The ladder — every rung walked, the one above it, and the doors it holds.

A function of where you stand and what you have climbed, so what the leaf is
sent can be asked for and checked without a socket in the way.
"""

from __future__ import annotations

from eidolon.value import graph as ir_graph
from kairos.artefacts import licences
from kairos.machine import of
from opsis.scene import reader_of, ruledefs
from praxis.reading import Reading, profile, upward
from praxis.state import Rung

__all__ = ["strata"]


_PROFILES: dict[tuple[str, int], tuple[int, ...]] = {}


def _band(reading: Reading, buckets: int = 120) -> tuple[int, ...]:
    """Return the cached depth projection of one content-addressed subject."""
    key = (reading.identity, buckets)
    made = _PROFILES.get(key)
    if made is None:
        made = tuple(profile(reading, buckets))
        _PROFILES[key] = made
        if len(_PROFILES) > 64:
            del _PROFILES[next(iter(_PROFILES))]
    return made


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
    offered = licences(machine)
    walk = ir_graph(machine.grammar)
    doors = [
        f"P ir:grammar {here} {rungs[here].level} value ok "
        f"{reading.reader_name} — as a value\t"
        f"{len(walk.nodes)} nodes · {len(walk.edges)} edges",
        f"P machine {here} {rungs[here].level} compiler ok "
        f"{reading.reader_name} — as a machine\t{built.line()}",
        f"P artefacts {here} {rungs[here].level} artefacts ok "
        f"{reading.reader_name} — as artefacts\t"
        f"{len(offered)} offered · witness on room entry",
    ]
    # THE INSTRUMENT IS ITS OWN LANE. It is not a stratum of this climb —
    # it is the thing doing the climbing — so it stands in its own column
    # with its own door, which is where the reference puts a lane that is
    # not in the chain. A door in the masthead beside the way INTO the
    # strata was two buttons for one place.
    doors.append(
        f"P ring {len(rungs)} 0 policy ok the instrument — as a reading of its "
        f"own state\tits policy, read by the policy grammar"
    )
    lanes = [rung.document for rung in rungs] + ["the instrument"]
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
                f"b {i} {' '.join(str(v) for v in _band(r))}"
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
