"""Shared fixtures for the boundary-verdict, boundary-side and live-set tests:
a live kernel, a hand-built completed side, and the tally of a parse's
meetings."""

from __future__ import annotations

from lexic.parsing.pda.core.errors import ProbeFork
from lexic.parsing.pda.runtime.admission import Side
from lexic.parsing.pda.runtime.build import Frame
from lexic.parsing.pda.runtime.kernel.kernel import PdaKernel
from lexic.parsing.pda.runtime.kernel.verdicts import liveset, sides, verdicts
from tests.paths import GROUND_TRUTH
from tests.unit.lexic.parsing.pda.runtime.flat_support import flat_arm, flat_clone
from tests.unit.lexic.parsing.pda.runtime.pda_runtime_helpers import compiled_and_pda


def live_kernel(text: str = "{}") -> PdaKernel:
    """A kernel standing where a boundary would be decided.

    A live set's readings are driven through ``_advance``, which needs a real
    cursor: a stack to swap in and out and a ``_caches`` to count probing on.
    """
    compiled, pda = compiled_and_pda(GROUND_TRUTH / "json.gbnf")
    return PdaKernel(pda, text, compiled.executor)


TOP: Frame[object] = Frame(flat_arm(1), [], flat_clone(), 0)
"""A side's copy of the boundary's frame, for a side built by hand."""


def completed_side(end: int, root: list[object]) -> Side:
    """A side that completed at ``end`` into ``root`` — empty stack, no
    sub-run left, every copied frame recorded."""
    return [], end, None, root, [], [], [TOP], ()


def meeting_tally(compiled, text: str, monkeypatch) -> dict[str, int]:
    """Parse ``text`` and classify every meeting of two readings a live set
    merged.

    Read observationally rather than re-derived: a meeting whose values agree
    returns without asking the rank, one whose values differ asks it, and a
    tie raises — so the rank calls seen DURING a ``_met`` call separate
    agreement from difference, and the strand it returns says which way it
    kept: the take is the one whose path is the greater where the two parted.
    A meeting that needed a rank on readings keeping no ledgers restarts its
    set (``unrecorded``), and is met again.
    A drive seen during a meeting would mean a meeting drove on, which none
    may: two readings that meet share their future, so nothing is left to run.
    """
    met = vars(liveset.LiveSet)["_met"]  # what each class DEFINES
    rank = vars(verdicts.Verdicts)["_rank"]
    advance = vars(sides.Sides)["_advance"]
    tally = {
        "meetings": 0,
        "agree": 0,
        "ranked": 0,
        "tie": 0,
        "unrecorded": 0,
        "took": 0,
        "drove": 0,
    }
    inside = {"depth": 0, "ranks": 0}

    def counting_met(self, one, other):
        """`_met`, classifying which of its three answers it gave."""
        tally["meetings"] += 1
        inside["depth"] += 1
        inside["ranks"] = 0
        try:
            kept = met(self, one, other)
        except ProbeFork:
            tally["tie"] += 1
            raise
        except liveset.Unrecorded:
            tally["unrecorded"] += 1
            raise
        finally:
            inside["depth"] -= 1
        tally["ranked" if inside["ranks"] else "agree"] += 1
        tally["took"] += kept.path == max(one.path, other.path)
        return kept

    def counting_rank(self, *args):
        """`_rank`, flagging a rank asked inside a meeting."""
        inside["ranks"] += bool(inside["depth"])
        return rank(self, *args)

    def counting_advance(self, *args, **kwargs):
        """`_advance`, flagging a drive inside a meeting."""
        tally["drove"] += bool(inside["depth"])
        return advance(self, *args, **kwargs)

    monkeypatch.setattr(liveset.LiveSet, "_met", counting_met)
    monkeypatch.setattr(verdicts.Verdicts, "_rank", counting_rank)
    monkeypatch.setattr(sides.Sides, "_advance", counting_advance)
    compiled.parse(text, cores=1)
    return tally


NOISE_RUNS = (
    "n ::= nunit+\n"
    "m ::= nunit+\n"
    'nunit ::= " " | cl\n'
    'cl ::= "#" [a-z]* "\\n"\n'
    'item ::= "x"\n'
)
"""Two noise runs of one unit, ``n`` then ``m``, and the ``item`` around them:
where ``n`` stops and ``m`` starts is a choice the values record."""

ENTRY_AT_THE_START = (
    "# @non-semantic n m\n"
    "root ::= a | b\n"
    'a ::= item n? m? item ";"\n'
    'b ::= item n? m? item "."\n' + NOISE_RUNS
)
"""The start rule is an attempt clone: the run itself starts its entries, and
a boundary in ``n``'s run sits inside them."""

SECTIONS = (
    'doc ::= sec+\nsec ::= stmt+ end\nstmt ::= "!" | ";"? [a;]\n'
    'end ::= [a;] | [a]* "a"\n'
)
"""Every section closes with ``end``, and ``!`` is only ever a statement."""
