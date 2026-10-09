"""Shared fixtures for the boundary-verdict and boundary-side tests: a live
kernel, a hand-built completed side, and the tally of a parse's convergences."""

from __future__ import annotations

from lexic.parsing.pda.runtime.admission import Side
from lexic.parsing.pda.runtime.build import Frame
from lexic.parsing.pda.runtime.kernel import sides, verdicts
from lexic.parsing.pda.runtime.kernel.kernel import PdaKernel
from lexic.parsing.pda.runtime.kernel.verdicts import (
    FORKED,
    STOP_FORCED,
    TAKE,
)
from tests.paths import GROUND_TRUTH
from tests.unit.lexic.parsing.pda.runtime.flat_support import flat_arm, flat_clone
from tests.unit.lexic.parsing.pda.runtime.pda_runtime_helpers import compiled_and_pda


def live_kernel(text: str = "{}") -> PdaKernel:
    """A kernel standing where a boundary would be decided.

    The lockstep's sides are driven through ``_advance``, which needs a real
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


def converged_tally(compiled, text: str, monkeypatch) -> dict[str, int]:
    """Parse ``text`` and classify every answer ``_converged`` gave.

    Read observationally rather than re-derived: the values-agree answer
    returns without driving, and both differing answers drive the common
    remainder first, so an ``_advance`` seen DURING a ``_converged`` call
    separates agreement from difference and the verdict separates the rest.
    Duplicating the branch conditions here would let the test agree with a
    wrong ``_converged`` about what it did.

    ``depth`` is kept rather than a flag because the reading would be wrong if
    the calls ever nested; they do not, since the drive runs under a probe and
    probes never fork, and a nested call would show up as a depth above one.

    Each class names BOTH what the method did and what it answered. What that
    separates, exactly: the drove bit tells agreement from difference, and the
    verdict tells the two differing answers apart — so a differing branch
    returning its SIBLING's verdict reads as that sibling rather than landing
    in ``other``. The tests below still catch the swap, because each asserts
    its own class at one and the other two at zero.
    """
    converged = vars(verdicts.Verdicts)["_converged"]  # what each class DEFINES
    advance = vars(sides.Sides)["_advance"]
    tally = {
        "converged": 0,
        "agree": 0,
        "dead": 0,
        "fork": 0,
        "ranked": 0,
        "other": 0,
        "nested": 0,
    }
    inside = {"depth": 0, "drove": 0}
    classes = {
        (False, TAKE): "agree",
        (True, TAKE): "dead",
        (True, FORKED): "fork",
        (True, STOP_FORCED): "ranked",
    }

    def counting_converged(self, *args, **kwargs):
        """`_converged`, classifying which of its three answers it gave."""
        tally["converged"] += 1
        inside["depth"] += 1
        tally["nested"] += inside["depth"] > 1
        inside["drove"] = 0
        try:
            answer = converged(self, *args, **kwargs)
        finally:
            inside["depth"] -= 1
        tally[classes.get((bool(inside["drove"]), answer), "other")] += 1
        return answer

    def counting_advance(self, *args, **kwargs):
        """`_advance`, flagging a drive that happened inside `_converged`."""
        inside["drove"] += bool(inside["depth"])
        return advance(self, *args, **kwargs)

    monkeypatch.setattr(verdicts.Verdicts, "_converged", counting_converged)
    monkeypatch.setattr(sides.Sides, "_advance", counting_advance)
    compiled.parse(text, cores=1)
    assert (
        sum(tally[name] for name in set(classes.values()) | {"other"})
        == tally["converged"]
    ), (
        "a `_converged` call was entered and never classified, so something "
        f"escaped it — which a ProbeFork now does, by design: {tally}"
    )
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
