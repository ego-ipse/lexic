"""Changed path → the benchmark seats whose paid path it sits on.

A table, deliberately. Which rows a change can reach is a fact about the
tree's layout, and a fact belongs somewhere a reader can check it rather than
in a condition they have to execute in their head.

The table errs toward measuring too much: a path under the package that no row
names reaches every seat, because minutes are cheaper than a regression nobody
saw. A path outside the package reaches nothing at all.
"""

from __future__ import annotations

from collections.abc import Sequence

__all__ = [
    "EARLEY_SEATS",
    "EVERY_SEAT",
    "MT_SEATS",
    "PDA_SEATS",
    "SEATS_BY_PATH",
    "SOURCE_ROOT",
    "seats_for",
]

SOURCE_ROOT = "src/lexic/"
"""The only paths that can reach a paid path.

A change anywhere else — a test, a document, the benchmark harness itself —
selects no rows, and a run over it says so and exits 0 rather than measuring
the roster to prove nothing moved. The harness is the one arguable exclusion:
editing it makes the two arms incomparable rather than slower, and the run
already prints both benchmark digests for exactly that.
"""

PDA_SEATS = ("lexic-pda", "lexic-lex", "lexic-lex-ns", "lexic-mt", "lexic-mt-lex-ns")
"""Seats whose parse runs through the predictive PDA.

``lexic-lex`` and ``lexic-lex-ns`` are the PDA with ``@lexical`` /
``@non-semantic`` folding, and both threaded seats are the PDA over the full
corpus — so a change under ``parsing/pda/`` reaches five of the six seats, not
one. The threaded pair is still opt-in behind ``--mt``; being reachable and
being measured are different questions.
"""

EARLEY_SEATS = ("lexic-earley",)
"""The gated engine's own seat — the route that does not take the PDA."""

MT_SEATS = ("lexic-mt", "lexic-mt-lex-ns")
"""The threaded seats — the only ones a document-split change can reach."""

EVERY_SEAT = frozenset(PDA_SEATS) | frozenset(EARLEY_SEATS)
"""Every seat the roster carries, spelled from the families above.

Written as a union rather than as its own list so the two cannot drift: a seat
added to a family is in this set by construction. A test pins it against the
roster the trees actually define.
"""

SEATS_BY_PATH: tuple[tuple[str, frozenset[str]], ...] = (
    ("src/lexic/parsing/pda/", frozenset(PDA_SEATS)),
    ("src/lexic/parsing/earley/", frozenset(EARLEY_SEATS)),
    ("src/lexic/parsing/parallel/", frozenset(MT_SEATS)),
    ("src/lexic/ir/", EVERY_SEAT),
    ("src/lexic/compile/", EVERY_SEAT),
    ("src/lexic/model", EVERY_SEAT),
)
"""Changed path → the seats whose paid path it sits on, most specific first.

DATA, and deliberately so: which rows a change can reach is a fact about the
tree's layout, and a fact belongs in a table a reader can check rather than in
a condition they have to execute. The three rows that map to one family are the
whole point of the tier; the three that map to everything are listed anyway,
because a reader should see that the IR spine, the compile seam and the model
were CONSIDERED and reach every seat, not that they fell off the end of the
table into a default.

A path under :data:`SOURCE_ROOT` matching no prefix reaches every seat too.
That is the safe direction: an unrecognised module is one nobody has placed
yet, and measuring too many rows costs time where measuring too few costs a
missed regression.
"""


def seats_for(paths: Sequence[str]) -> frozenset[str]:
    """The seats the changed ``paths`` can reach.

    :param paths: Repository-relative paths, as ``git`` spells them.
    :returns: Seat names; empty when nothing changed sits on a paid path.
    """
    reached: set[str] = set()
    for path in paths:
        if not path.startswith(SOURCE_ROOT):
            continue
        for prefix, seats in SEATS_BY_PATH:
            if path.startswith(prefix):
                reached |= seats
                break
        else:
            reached |= EVERY_SEAT
    return frozenset(reached)
