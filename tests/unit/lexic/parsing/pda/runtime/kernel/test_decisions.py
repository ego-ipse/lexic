"""Tests for lexic.parsing.pda.runtime.kernel.decisions — the attempt/probe
decision half of ``PdaKernel``.

``Attempting``'s methods read the live kernel cursor's state (``pos``,
``stack``, ``_caches``) and are exercised end to end through real parses in
``tests/unit/lexic/parsing/pda/test_group_attempt.py`` and the parity suite;
this file targets the module's cursor-free pure helpers directly — the
loop-close bookkeeping. The admission predicates it once hosted live in
:mod:`lexic.parsing.pda.runtime.admission`, and their tests beside it.
"""

from __future__ import annotations

import pytest

from lexic.parsing.pda.compiler.program.flatten import FlatArm, FlatClone
from lexic.parsing.pda.compiler.program.opcodes import OP_ISLAND
from lexic.parsing.pda.compiler.specs import IslandPayload
from lexic.parsing.pda.core.errors import PdaFail, ProbeFork
from lexic.parsing.pda.runtime.admission import Side
from lexic.parsing.pda.runtime.build import Frame
from lexic.parsing.pda.runtime.kernel import decisions
from lexic.parsing.pda.runtime.kernel.decisions import (
    _FORKED,
    _TAKE,
    Attempting,
)
from lexic.parsing.pda.runtime.kernel.kernel import PdaKernel
from tests.paths import GROUND_TRUTH
from tests.unit.lexic.parsing.pda.runtime.flat_support import flat_arm, flat_clone
from tests.unit.lexic.parsing.pda.runtime.pda_runtime_helpers import compiled_and_pda
from tools.benchmark.cases.corpora import meta_corpus
from tools.benchmark.cases.grammars import BENCHES


def test_close_loop_resets_count_advances_i_and_records_the_end():
    """The frame's loop-close bookkeeping: count reset, ``i`` advanced, end recorded.

    Item ``i``'s end is ``ends[i + 1]``, because ``ends[0]`` is the frame's own
    span start — the layout that removes the first-item test from every reader.
    """
    frame = Frame(flat_arm(3), [], flat_clone(), 0)
    frame.count = 5
    result = frame.close_loop(1, 42)
    assert result == 2
    assert frame.count == 0
    assert frame.i == 2
    ends = frame.ends
    assert ends is not None  # this clone keeps boundaries
    assert ends[2] == 42


def _raise(why: BaseException) -> None:
    """Raise from inside a lambda, so the patched drive stays one expression."""
    raise why


def _live_kernel(text: str = "{}") -> PdaKernel:
    """A kernel standing where a boundary would be decided.

    The lockstep's sides are driven through ``_advance``, which needs a real
    cursor: a stack to swap in and out and a ``_caches`` to count probing on.
    """
    compiled, pda = compiled_and_pda(GROUND_TRUTH / "json.gbnf")
    return PdaKernel(pda, text, compiled.executor)


def _side(kern: PdaKernel) -> Side:
    """The lockstep side ``_advance`` swaps in — the cursor triple, as a value.

    The reach is the subject, not an accident of testing: ``_routes`` is
    private because nothing outside the kernel may steer it, and a test of
    that seam's exception contract has to stand exactly where the seam does.
    The three tests below reach through here, so the reach is stated once.
    """
    return kern.stack, kern.pos, kern._routes  # pylint: disable=protected-access


def _cursor(kern: PdaKernel) -> tuple[Side, int, bool]:
    """Everything ``_advance``'s ``finally`` promises to put back."""
    caches = kern._caches  # pylint: disable=protected-access  # the seam — see `_side`
    return _side(kern), caches.probing, caches.uncertain


def _advance(kern: PdaKernel, side: Side) -> Side | None:
    """Drive one side to exhaustion — the method whose contract is under test."""
    return kern._advance(side, -1)  # pylint: disable=protected-access  # see `_side`


def test_a_probe_fork_propagates_out_of_advance(monkeypatch) -> None:
    """Undecidable is not death, and ``_advance`` says so by RAISING.

    ``ProbeFork`` subclasses :class:`PdaFail`, so the ordinary handler would
    swallow it and hand back ``None`` — indistinguishable from a side that
    died. The lockstep answers :data:`_TAKE` on a dead STOP side, so a
    swallowed fork would commit a take the gated engine never got to refuse.

    Injected at the seam deliberately: the contract under test is the
    EXCEPTION's, and a grammar that happens to fork here would test the
    grammar as much as the handler.
    """
    kern = _live_kernel()
    side = _side(kern)
    monkeypatch.setattr(
        PdaKernel, "_drive", lambda *_a, **_k: _raise(ProbeFork("undecidable", 0))
    )
    with pytest.raises(ProbeFork):
        _advance(kern, side)


def test_advance_restores_the_cursor_when_a_probe_fork_propagates(
    monkeypatch,
) -> None:
    """The ``finally`` holds under the raise path.

    Early propagation is the one thing that could leave the cursor swapped in:
    the stack, position, routes and both cache counters are saved around the
    drive and must come back whether it returned, failed, or raised through.
    """
    kern = _live_kernel()
    before = _cursor(kern)
    side = _side(kern)
    monkeypatch.setattr(
        PdaKernel, "_drive", lambda *_a, **_k: _raise(ProbeFork("undecidable", 0))
    )
    with pytest.raises(ProbeFork):
        _advance(kern, side)
    assert _cursor(kern) == before


def test_an_ordinary_failure_still_reads_as_a_dead_side(monkeypatch) -> None:
    """A real :class:`PdaFail` is death, and ``_advance`` still answers ``None``.

    The guard must not widen: only the fork propagates.
    """
    kern = _live_kernel()
    side = _side(kern)
    monkeypatch.setattr(
        PdaKernel, "_drive", lambda *_a, **_k: _raise(PdaFail("dead", 0))
    )
    assert _advance(kern, side) is None


def test_a_dead_stop_side_costs_two_stack_copies_not_three(monkeypatch) -> None:
    """The lockstep answers the verdict a third copy used to re-derive.

    A fork verdict forks the stack twice for the lockstep's two sides; when the
    STOP side dies there, the verdict is already settled, and probing the stop
    side again only re-establishes that death. Counted rather than asserted
    about: every :func:`frames_copy` call during a parse that forks, against
    the number of verdicts that asked.

    The copy count alone would hold for the wrong reason — two copies per
    verdict says only that no verdict fell through to a probe, which any
    lockstep settlement satisfies. So the dead-stop settlements are counted
    too: ``_lockstep_verdict`` settles through ``_converged`` or through the
    branch this commit adds, and nothing else, so the difference IS that
    branch and a non-zero difference is the evidence it ran.
    """
    bench = next(one for one in BENCHES if one.name == "gbnf-meta")
    counted = {"copies": 0, "verdicts": 0, "settled": 0, "converged": 0}
    copy = decisions.frames_copy
    defined = vars(decisions.Attempting)  # what the class DEFINES
    verdict, lockstep, converged = (
        defined["_fork_verdict"],
        defined["_lockstep_verdict"],
        defined["_converged"],
    )

    def counting_copy(stack):
        """`frames_copy`, counted."""
        counted["copies"] += 1
        return copy(stack)

    def counting_verdict(self, *args, **kwargs):
        """`_fork_verdict`, counted."""
        counted["verdicts"] += 1
        return verdict(self, *args, **kwargs)

    def counting_lockstep(self, *args, **kwargs):
        """`_lockstep_verdict`, counting the boundaries it SETTLES."""
        answer = lockstep(self, *args, **kwargs)
        counted["settled"] += answer is not None
        return answer

    def counting_converged(self, *args, **kwargs):
        """`_converged`, counting the settlements that came from convergence."""
        answer = converged(self, *args, **kwargs)
        counted["converged"] += answer is not None
        return answer

    monkeypatch.setattr(decisions, "frames_copy", counting_copy)
    monkeypatch.setattr(decisions.Attempting, "_fork_verdict", counting_verdict)
    monkeypatch.setattr(decisions.Attempting, "_lockstep_verdict", counting_lockstep)
    monkeypatch.setattr(decisions.Attempting, "_converged", counting_converged)
    bench.compiled.parse(meta_corpus("json.gbnf", 2), cores=1)

    assert counted["verdicts"], (
        "this document no longer forks — the test proves nothing"
    )
    assert counted["settled"] > counted["converged"], (
        "no boundary settled on a dead STOP side — the branch under test "
        "never ran, so the copy count below proves nothing about it"
    )
    assert counted["copies"] == 2 * counted["verdicts"]


def _converged_tally(compiled, text: str, monkeypatch) -> dict[str, int]:
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
    defined = vars(decisions.Attempting)  # what the class DEFINES
    converged, advance = defined["_converged"], defined["_advance"]
    tally = {"converged": 0, "agree": 0, "dead": 0, "fork": 0, "other": 0, "nested": 0}
    inside = {"depth": 0, "drove": 0}
    classes = {(False, _TAKE): "agree", (True, _TAKE): "dead", (True, _FORKED): "fork"}

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

    monkeypatch.setattr(decisions.Attempting, "_converged", counting_converged)
    monkeypatch.setattr(decisions.Attempting, "_advance", counting_advance)
    compiled.parse(text, cores=1)
    assert (
        sum(tally[name] for name in set(classes.values()) | {"other"})
        == tally["converged"]
    ), (
        "a `_converged` call was entered and never classified, so something "
        f"escaped it — which a ProbeFork now does, by design: {tally}"
    )
    return tally


def test_the_lockstep_settles_a_converged_boundary_when_the_values_agree(
    monkeypatch,
) -> None:
    """The O(1) case the lockstep exists for, on a real grammar file.

    Every trailing comment line in a GBNF file is a boundary the meta grammar
    cannot settle by lookahead: the next ``#`` is admitted both by another
    iteration of the comment run and by what follows it. Both sides survive,
    reconverge on the same position and control state, and build the SAME
    values — the comment run is noise — so the boundary is settled without
    either side running to end-of-input.

    One convergence per trailing comment, so the count is a statement about
    the document rather than a number copied off a run.
    """
    bench = next(one for one in BENCHES if one.name == "gbnf-meta")
    comments = ("# one\n", "# two\n", "# three\n")
    text = 'root ::= "a"\n' + "".join(comments)
    tally = _converged_tally(bench.compiled, text, monkeypatch)

    assert tally["converged"] == len(comments), (
        "the convergence path did not run once per trailing comment — this "
        f"document no longer witnesses it: {tally}"
    )
    assert tally["agree"] == len(comments), (
        f"a converged boundary here must settle on AGREEING values: {tally}"
    )
    assert (tally["dead"], tally["fork"]) == (0, 0), tally
    assert (tally["other"], tally["nested"]) == (0, 0), tally


def test_a_converged_boundary_takes_when_the_common_remainder_dies(
    monkeypatch,
) -> None:
    """Values DIFFER, so the remainder decides — and it does not complete.

    The two sides reconverge, but each built a different value getting there,
    which is the question a fork exists to ask. The remainder past the
    convergence is COMMON, so it is run ONCE rather than twice: dying means
    neither side completes, and the boundary is :data:`_TAKE` exactly as a
    dead stop side is.

    The document is a vyx packet the property suite generated — a natural
    witness rather than an injected one, found by tallying this method's
    answers across the whole test suite and keeping the input that reached
    this branch.
    """
    bench = next(one for one in BENCHES if one.name == "vyx")
    text = "!X:P L2< \U00097f2f \U0003fe58\U0007d18e\U000ed509 \U000deadc >\n"
    tally = _converged_tally(bench.compiled, text, monkeypatch)

    assert tally["converged"] == 1, (
        f"this packet no longer converges — it witnesses nothing: {tally}"
    )
    assert tally["dead"] == 1, (
        "a converged boundary here must settle on a remainder that DIES, not "
        f"on agreement and not on a fork: {tally}"
    )
    assert (tally["agree"], tally["fork"]) == (0, 0), tally
    assert (tally["other"], tally["nested"]) == (0, 0), tally


def test_a_converged_boundary_forks_when_the_common_remainder_completes(
    monkeypatch,
) -> None:
    """Values DIFFER and the remainder COMPLETES — the difference is real.

    The third answer, and the only one of the three reached by injection
    rather than by a document: agreement is denied at the single site that
    asks for it, so the same converged boundary that settles on agreement
    above must now run the common remainder. It reaches end-of-input, which
    makes the two values a genuine fork rather than a benign split, and
    :data:`_FORKED` is the gated engine's question.

    ``values_agree`` is CONSULTED at exactly one site, inside ``_converged``,
    so nothing else in the parse READS the denied function — its own recursion
    in ``admission`` resolves the name there and this patch does not reach it.
    The parse itself does diverge, and must: the changed verdict propagates,
    which is why this document converges once here and three times above.

    Searched for first, and the injection is what the search licenses: over a
    whole suite run this method answered 278 times — 258 on agreement, 20 on a
    dead remainder, and NONE here. A forking convergence is what the repo
    refuses everywhere else, so no document it keeps can carry one.
    """
    bench = next(one for one in BENCHES if one.name == "gbnf-meta")
    monkeypatch.setattr(decisions, "values_agree", lambda _left, _right: False)
    tally = _converged_tally(
        bench.compiled, 'root ::= "a"\n# one\n# two\n# three\n', monkeypatch
    )

    assert tally["converged"] == 1, (
        f"the convergence path did not run — this witnesses nothing: {tally}"
    )
    assert tally["fork"] == 1, (
        "a converged boundary whose remainder completes must answer FORKED, "
        f"not settle the boundary itself: {tally}"
    )
    assert (tally["agree"], tally["dead"]) == (0, 0), tally
    assert (tally["other"], tally["nested"]) == (0, 0), tally


# ── an attempted island that cannot settle its extent bails ─────────────────


class _IslandUndecidable(Attempting[str]):
    """An attempted island iteration whose sub-parse finds two ends, either
    of which could compose: the island raises ``ProbeFork``."""

    __slots__ = ("text", "pos", "stack")

    def __init__(self, text: str) -> None:
        self.text = text
        self.pos = 0
        self.stack = []

    def _stop_viable(self, arm: FlatArm, i: int, char: str) -> bool:
        return False  # the one-character stop test says nothing here

    def _enter(self, clone: FlatClone[str], out: list[str]) -> bool:
        raise AssertionError("an island iteration pushes no frame")

    def _drive(self, floor: int = 0, limit: int = -1) -> None:
        raise AssertionError("an island iteration drives nothing")

    def _sink_for(self, frame: Frame[str], arm: FlatArm, i: int) -> list[str]:
        return []

    def _island(self, ref: IslandPayload, sink: list[str]) -> None:
        raise ProbeFork("island spans two ends and the shorter could compose", 0)


def test_an_attempted_island_that_cannot_settle_bails_instead_of_closing() -> None:
    """Read as a failed iteration, the refusal closed the loop at the current
    count and committed a carving the gated engine had been asked to decide."""
    arm = flat_arm(
        1,
        kinds=(OP_ISLAND,),
        los=(0,),
        his=(-1,),
        gate_data=(((frozenset("a"), False), (frozenset(), False)),),
        payloads=(None,),
    )
    frame: Frame[str] = Frame(arm, [], flat_clone(), 0)
    with pytest.raises(ProbeFork):
        _IslandUndecidable("a").attempt_iteration(frame, arm, 0, 0)
