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

import itertools

import pytest

from lexic.compile import compile_text
from lexic.exceptions import LexicError
from lexic.ir import IrNamedTuple, IrStr
from lexic.parsing.pda.compiler.program.flatten import FlatArm, FlatClone
from lexic.parsing.pda.compiler.program.opcodes import (
    BUILD_TRANSPARENT,
    GATE_ATTEMPT,
    OP_GRP,
    OP_ISLAND,
    OP_REF,
)
from lexic.parsing.pda.compiler.specs import IslandPayload
from lexic.parsing.pda.core.errors import PdaFail, ProbeFork
from lexic.parsing.pda.runtime.admission import Floor, KernelCaches, Side
from lexic.parsing.pda.runtime.build import Frame
from lexic.parsing.pda.runtime.kernel import decisions
from lexic.parsing.pda.runtime.kernel.decisions import (
    _FORKED,
    _STOP_FORCED,
    _TAKE,
    Attempting,
    descending,
    entered,
    iterating,
    landing,
)
from lexic.parsing.pda.runtime.kernel.kernel import PdaKernel
from tests import parity_helpers
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
    return kern.stack, kern.pos, kern._routes, [], []  # pylint: disable=protected-access


def _cursor(kern: PdaKernel) -> tuple[Side, int, bool]:
    """Everything ``_advance``'s ``finally`` promises to put back."""
    caches = kern._caches  # pylint: disable=protected-access  # the seam — see `_side`
    return _side(kern), caches.probing, caches.uncertain


def _advance(kern: PdaKernel, side: Side) -> Side | None:
    """Drive one side to exhaustion — the method whose contract is under test."""
    return kern._advance(side, -1)[0]  # pylint: disable=protected-access  # see `_side`


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
    """The O(1) case the lockstep exists for: two sides at one position and
    control state that built the same values since the boundary settle the
    take, without driving the remainder.

    gbnf-meta's trailing comments once reached it only because their stop side
    drove past the attempted iteration it was forked inside, re-attempting it
    from zero. Settled as the live parse settles it, that stop side dies
    (:func:`test_a_fork_inside_a_loop_iteration_settles_it`). So the vyx packet
    below, which converges with values that DIFFER, is made to agree at the
    one site that reads the snapshots.
    """
    bench = next(one for one in BENCHES if one.name == "vyx")
    monkeypatch.setattr(decisions, "pending_values", lambda _stack, _shape: ())
    tally = _converged_tally(bench.compiled, VYX_CONVERGES, monkeypatch)

    assert tally["converged"] == 1, (
        f"this packet no longer converges — it witnesses nothing: {tally}"
    )
    assert tally["agree"] == 1, (
        f"agreeing snapshots must settle without a drive: {tally}"
    )
    assert (tally["dead"], tally["fork"]) == (0, 0), tally
    assert (tally["other"], tally["nested"]) == (0, 0), tally


VYX_CONVERGES = "!X:P L2< \U00097f2f \U0003fe58\U0007d18e\U000ed509 \U000deadc >\n"
"""A vyx packet the property suite generated, whose one boundary converges with
values that differ and a common remainder that dies."""


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
    tally = _converged_tally(bench.compiled, VYX_CONVERGES, monkeypatch)

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

    Reached by injection on a real convergence: the vyx packet's snapshots are
    made distinct at the one site that reads them, and its shared remainder —
    which dies on its own — is reported complete, so the converged boundary
    must fork rather than settle. No document in the suite converges mid-parse
    onto a remainder that completes.
    """
    bench = next(one for one in BENCHES if one.name == "vyx")
    distinct = itertools.count()
    monkeypatch.setattr(
        decisions, "pending_values", lambda _stack, _shape: (next(distinct),)
    )
    drive = vars(Attempting)["_advance"]

    def completing(self, side, limit, shared=False):
        if shared:
            return side, False
        return drive(self, side, limit, shared)

    monkeypatch.setattr(Attempting, "_advance", completing)
    tally = _converged_tally(bench.compiled, VYX_CONVERGES, monkeypatch)

    assert tally["converged"] >= 1, (
        f"the convergence path did not run — this witnesses nothing: {tally}"
    )
    assert tally["fork"] == tally["converged"], (
        "a converged boundary whose remainder completes must answer FORKED, "
        f"not settle the boundary itself: {tally}"
    )
    assert (tally["agree"], tally["dead"]) == (0, 0), tally
    assert (tally["other"], tally["nested"]) == (0, 0), tally


def test_a_refusal_on_a_converged_remainder_is_undecidable(monkeypatch) -> None:
    """Values DIFFER and the common remainder REFUSES — the boundary bails.

    The remainder is run once, on the LEFT side's stack, so its completions
    read the values the left side built. A refusal there is a verdict about
    those values, not about the right side's: it is neither a death of both
    sides nor a completion, so ``_converged`` raises :class:`ProbeFork` and
    the gated engine answers. Read as a death, it would settle :data:`_TAKE`.

    The document is the dead-remainder witness above: its remainder completes
    ``inline-content`` before it dies, and that completion is made to refuse
    — only inside ``_converged``'s own drive.
    """
    bench = next(one for one in BENCHES if one.name == "vyx")
    text = VYX_CONVERGES
    converged = vars(decisions.Attempting)["_converged"]
    complete = next(
        vars(c)["_complete"] for c in PdaKernel.__mro__ if "_complete" in vars(c)
    )
    inside, refused, answers = [0], [0], []

    def converging(self, *args):
        inside[0] += 1
        try:
            answers.append(converged(self, *args))
        except ProbeFork as bail:
            answers.append(str(bail))
            raise
        finally:
            inside[0] -= 1
        return answers[-1]

    def refusing(self, frame):
        if inside[0]:
            refused[0] += 1
            raise LexicError("refused on a value the left side built")
        return complete(self, frame)

    monkeypatch.setattr(decisions.Attempting, "_converged", converging)
    monkeypatch.setattr(PdaKernel, "_complete", refusing)
    kernel = PdaKernel(bench.compiled.pda_tables(), text, bench.compiled.executor)
    with pytest.raises(PdaFail):
        kernel.run()
    assert refused[0], "no completion refused inside the drive — nothing tested"
    assert len(answers) == 1 and "shared remainder" in str(answers[0]), answers


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


# ── values compared by class and fields ─────────────────────────────────────


class _Left(IrNamedTuple[IrStr]):
    """One record class."""

    w: IrStr


class _Right(IrNamedTuple[IrStr]):
    """Another, with the same field and the same value."""

    w: IrStr


def _holding(value: object) -> list[Frame[object]]:
    """A one-frame stack whose output holds ``value``, its one item done."""
    frame: Frame[object] = Frame(flat_arm(1), [value], flat_clone(), 0)
    frame.i = 1
    return [frame]


def test_converged_sides_whose_records_differ_in_class_do_not_agree(
    monkeypatch,
) -> None:
    """``_Left('x')`` and ``_Right('x')`` are two meanings with one field tuple:
    read apart, the common remainder decides, and here it completes, so the
    boundary forks."""
    kern = _live_kernel()
    end = len(kern.text)
    monkeypatch.setattr(
        Attempting,
        "_advance",
        lambda _self, side, _limit, shared=False: (([], end, None, [], []), False),
    )
    converged = vars(Attempting)["_converged"]
    left = (_holding(_Left(IrStr("x"))), end, None, [], [])
    right = (_holding(_Right(IrStr("x"))), end, None, [], [])
    assert converged(kern, left, right, (), False) == _FORKED
    same = (_holding(_Left(IrStr("x"))), end, None, [], [])
    assert converged(kern, left, same, (), False) == _TAKE


# ── the sampled-death rule ──────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("stop", "take", "verdict"),
    [
        ((None, True), (["s"], False), _FORKED),
        ((None, False), (["s"], False), _TAKE),
        ((["s"], False), (None, True), _FORKED),
        ((["s"], False), (None, False), _STOP_FORCED),
        ((["s"], True), (["s"], False), _FORKED),
        ((["s"], False), (["s"], False), _TAKE),
    ],
    ids=[
        "stop-guessed",
        "stop-dead",
        "take-guessed",
        "take-dead",
        "agreement-guessed",
        "agreement",
    ],
)
def test_an_outcome_a_guess_reached_decides_nothing(
    monkeypatch, stop, take, verdict: int
) -> None:
    """A side that died, or two that agreed, after a drive guessed at a
    boundary did so on the guess's path, not on every path: it proves
    nothing, so the boundary forks. With no guess on the way it settles."""
    kern = _live_kernel()
    monkeypatch.setattr(Attempting, "_lockstep_verdict", lambda *_a: None)
    monkeypatch.setattr(
        Attempting,
        "_probe",
        lambda _self, _arm, _i, _pos, taken: stop if taken is None else take,
    )
    fork_verdict = vars(Attempting)["_fork_verdict"]
    assert fork_verdict(kern, flat_arm(1), 0, 0, (1, [])) == verdict


@pytest.mark.parametrize(
    ("stop_guessed", "take_guessed", "verdict"),
    [(True, False, _FORKED), (False, True, _TAKE), (False, False, _TAKE)],
    ids=["stop-guessed", "only-take-guessed", "clean"],
)
def test_a_stop_side_death_is_judged_by_its_own_drive(
    monkeypatch, stop_guessed: bool, take_guessed: bool, verdict: int
) -> None:
    """The lockstep's stop side dies on its first advance. Only ITS drive's
    guess unsettles that death: a guess on the take side's drive says nothing
    about whether stopping could have survived."""
    kern = _live_kernel()
    sides = iter([([], 0, None, [], []), ([], 1, None, [], [])])
    monkeypatch.setattr(Attempting, "_side", lambda *_a: next(sides))
    monkeypatch.setattr(
        Attempting,
        "_advance",
        lambda _self, side, _limit, shared=False: (
            (None, stop_guessed) if side[1] == 0 else (side, take_guessed)
        ),
    )
    lockstep = vars(Attempting)["_lockstep_verdict"]
    assert lockstep(kern, flat_arm(1), 0, 0, (1, [])) == verdict


@pytest.mark.parametrize(
    ("stack", "verdict"), [("mid-parse", _FORKED), ("completed", _TAKE)]
)
def test_only_a_mid_parse_convergence_is_unsettled_by_a_guess(
    monkeypatch, stack: str, verdict: int
) -> None:
    """Both convergences agree and both were reached after a guess. The
    mid-parse one forks; the completed one takes, as it did before guesses
    were read at all — two completed carvings are the ranked verdict's to
    compare and to doubt, not convergence's."""
    kern = _live_kernel()
    frames = _holding("v") if stack == "mid-parse" else []
    monkeypatch.setattr(
        Attempting, "_advance", lambda _self, side, _limit, shared=False: (side, False)
    )
    side = (frames, len(kern.text), None, [], [])
    assert vars(Attempting)["_converged"](kern, side, side, (), True) == verdict


@pytest.mark.parametrize(
    ("sampled", "verdict"), [(True, _FORKED), (False, _TAKE)], ids=["sampled", "clean"]
)
def test_a_shared_remainder_that_dies_after_a_guess_decides_nothing(
    monkeypatch, sampled: bool, verdict: int
) -> None:
    """Converged sides whose values differ run their common remainder once,
    and here it dies. Reached through a guess, the death is the guess's, so
    the boundary forks; with none, neither side completes and the take
    stands."""
    kern = _live_kernel()
    monkeypatch.setattr(
        Attempting,
        "_advance",
        lambda _self, side, _limit, shared=False: (None, sampled),
    )
    left = (_holding(_Left(IrStr("x"))), 1, None, [], [])
    right = (_holding(_Right(IrStr("x"))), 1, None, [], [])
    assert vars(Attempting)["_converged"](kern, left, right, (), False) == verdict


@pytest.mark.parametrize(
    ("floors", "verdict"), [([], _FORKED), ([None], _TAKE)], ids=["same", "apart"]
)
def test_sides_converge_only_inside_the_same_sub_runs(
    monkeypatch, floors: list[None], verdict: int
) -> None:
    """Two sides at one position in one control state share a future only if
    they stand inside the same sub-runs: one still inside a floor settles it
    on the way, the other does not. Apart, the sides advance instead — and
    here the stop side dies, so the take is forced."""
    kern = _live_kernel()
    frames = _holding("v")
    sides = iter([(frames, 1, None, [], []), (frames, 1, None, [], floors)])
    monkeypatch.setattr(Attempting, "_side", lambda *_a: next(sides))
    monkeypatch.setattr(Attempting, "_converged", lambda *_a: _FORKED)
    monkeypatch.setattr(
        Attempting, "_advance", lambda _self, side, _limit, shared=False: (None, False)
    )
    lockstep = vars(Attempting)["_lockstep_verdict"]
    assert lockstep(kern, flat_arm(1), 0, 0, (1, [])) == verdict


RANKED = pytest.mark.xfail(
    strict=True,
    reason="two completed carvings are not compared at convergence; the "
    "ranked verdict settles them by the decider",
)


@RANKED
def test_sides_that_converge_by_completing_compare_their_root_outputs(
    monkeypatch,
) -> None:
    """Two completed sides hold empty stacks, whose pending snapshots are both
    ``()``. What they built is in the root outputs they completed into, and
    those differ."""
    kern = _live_kernel()
    end = len(kern.text)
    monkeypatch.setattr(
        Attempting, "_advance", lambda _self, side, _limit, shared=False: (side, False)
    )
    converged = vars(Attempting)["_converged"]
    left = ([], end, None, ["x", "y"], [])
    assert converged(kern, left, ([], end, None, ["xy"], []), (), False) == _FORKED


TAIL_CARVING = (
    'root ::= w "b"?\nw ::= x? tail?\nx ::= item+\nitem ::= "a"\ntail ::= "a" "b"\n'
)
"""``aab`` completes two ways: ``x`` takes both ``a`` and ``"b"?`` the ``b``, or
``x`` takes one and ``tail`` the rest — which the decider keeps."""


@RANKED
def test_a_completed_carving_the_decider_does_not_keep_is_not_committed() -> None:
    """Both sides of a boundary complete ``aab``. Read at convergence as two
    empty snapshots, they agree, and the predictive parse commits the take: a
    model the gated engine, keeping the decider's carving, does not build."""
    predictive, gated = parity_helpers.answers(
        TAIL_CARVING, "decisions-tail-carving", "aab"
    )
    assert gated == "Root(W(X((Item('a'),)), Tail('ab')), '')"
    assert predictive == gated


TWO_RUNS = (
    "# @non-semantic n m\n"
    "doc ::= item n? m? item\n"
    "n ::= nunit+\n"
    "m ::= nunit+\n"
    'nunit ::= " " | cl\n'
    'cl ::= "#" [a-z]* "\\n"\n'
    'item ::= "x"\n'
)
"""Two runs of one unit side by side: where ``n`` stops and ``m`` starts is a
choice the values record."""


def test_a_completed_carving_the_decider_keeps_stays_on_the_pda() -> None:
    """Both sides complete ``x #a\\nx``, and the take is the carving the decider
    keeps (``n`` longest): the predictive parse answers, with the gated
    engine's model."""
    predictive, gated = parity_helpers.answers(
        TWO_RUNS, "decisions-two-runs", "x #a\nx"
    )
    assert predictive != parity_helpers.DECLINED
    assert predictive == gated


# ── a fork inside an attempt sub-run settles it, as the live parse would ────


def _floors_seen(compiled, text: str, monkeypatch) -> list[list[str]]:
    """Parse ``text`` and name the caller of every floor each side was built
    with — ``loop``, ``entry`` or ``audit`` — recorded at :meth:`_side_floors`."""
    real = vars(Attempting)["_side_floors"]
    seen: list[list[str]] = []

    def caller(floor: Floor) -> str:
        entry = floor[5]
        if entry is None:
            return "loop"
        return "entry" if entry[3] is None else "audit"

    def recording(self, forked):
        root, floors = real(self, forked)
        seen.append([caller(f) for f in floors])
        return root, floors

    monkeypatch.setattr(Attempting, "_side_floors", recording)
    compiled.parse(text, cores=1)
    return seen


def test_a_fork_inside_a_loop_iteration_settles_it(monkeypatch) -> None:
    """gbnf-meta's trailing comment line is a boundary inside the ``n?``
    iteration the grammar loop is attempting. The stop side ends ``n`` there;
    settled as the live loop settles it, the rest of the line cannot be a
    ``tail-comment`` (no newline in one), so the stop side dies and the take
    settles — without the sides ever converging."""
    bench = next(one for one in BENCHES if one.name == "gbnf-meta")
    text = "q::=\nBcQ::=#\n#\n"
    tally = _converged_tally(bench.compiled, text, monkeypatch)
    monkeypatch.undo()
    seen = _floors_seen(bench.compiled, text, monkeypatch)
    predictive, _gated = parity_helpers.answers(bench.source, "decisions-gbnf", text)

    assert ["loop"] in seen, f"no side was forked inside a loop iteration: {seen}"
    assert tally["converged"] == 0, tally
    assert predictive != parity_helpers.DECLINED


def test_a_fork_inside_an_attempt_entry_settles_it(monkeypatch) -> None:
    """A vyx packet whose boundary sits inside an attempt clone's entry
    sub-run: each side carries the entry, and the predictive parse builds the
    gated engine's model."""
    bench = next(one for one in BENCHES if one.name == "vyx")
    text = "!E ^k L083< D:{s=} >"
    seen = _floors_seen(bench.compiled, text, monkeypatch)
    predictive, gated = parity_helpers.answers(bench.source, "decisions-vyx", text)

    assert ["entry"] in seen, f"no side was forked inside an attempt entry: {seen}"
    assert predictive == gated


ENTRY_AT_THE_START = (
    "# @non-semantic n m\n"
    "root ::= a | b\n"
    'a ::= item n? m? item ";"\n'
    'b ::= item n? m? item "."\n'
    "n ::= nunit+\n"
    "m ::= nunit+\n"
    'nunit ::= " " | cl\n'
    'cl ::= "#" [a-z]* "\\n"\n'
    'item ::= "x"\n'
)
"""The start rule is an attempt clone: the run itself starts its entries, and
a boundary in ``n``'s run sits inside them."""


def test_an_entry_the_run_started_settles_into_the_sides_own_root(
    monkeypatch,
) -> None:
    """Nothing below the bottom sub-run holds what the winner splices into:
    the run's holder is not on the stack. Each side completes into a root of
    its own — the value the end-of-input comparison reads — and the parse
    builds the gated engine's model."""
    real_floors, real_converged = (
        vars(Attempting)["_side_floors"],
        vars(Attempting)["_converged"],
    )
    bottoms: list[bool] = []
    roots: list[tuple[int, int]] = []

    def floors(self, forked):
        root, found = real_floors(self, forked)
        bottoms.extend(root is f[5][1] for f in found if f[0] == 0)
        return root, found

    def converged(self, left, right, shape, guessed):
        roots.append((len(left[3]), len(right[3])))
        return real_converged(self, left, right, shape, guessed)

    monkeypatch.setattr(Attempting, "_side_floors", floors)
    monkeypatch.setattr(Attempting, "_converged", converged)
    predictive, gated = parity_helpers.answers(
        ENTRY_AT_THE_START, "decisions-entry-start", "x #a\nx."
    )

    assert bottoms and all(bottoms), "the start entry splices into the side's root"
    assert roots and all(left and right for left, right in roots), roots
    assert (
        predictive
        == gated
        == "B(Item('x'), Item('x'), N((NunitArm1(' '), Cl('#a\\n'))))"
    )


def test_a_fork_inside_an_audit_settles_it_as_the_audit_would(monkeypatch) -> None:
    """``a`` wins ``x #a\\nx;`` and the attempt audits ``b``, whose sub-run
    meets a boundary in its ``n`` run. The sides settle that audit from the
    record its attempt pushed — ``b`` fails at ``;``, the audit passes, ``a``
    commits — and the parse builds the gated engine's model."""
    compiled = compile_text(ENTRY_AT_THE_START, cache_key="decisions-entry-start")
    seen = _floors_seen(compiled, "x #a\nx;", monkeypatch)
    predictive, gated = parity_helpers.answers(
        ENTRY_AT_THE_START, "decisions-entry-start", "x #a\nx;"
    )
    assert any("audit" in floors for floors in seen), seen
    assert (
        predictive
        == gated
        == "A(Item('x'), Item('x'), N((NunitArm1(' '), Cl('#a\\n'))))"
    )


def _stacked(*frames: Frame[str], text: str = "x") -> PdaKernel:
    """A kernel standing on ``frames``, as a fork would find it."""
    kern = _live_kernel(text)
    kern.stack = list(frames)
    return kern


def _floors_of(kern: PdaKernel) -> tuple[list[str], list[Floor]]:
    """What :meth:`_side_floors` reads off ``kern``'s stack."""
    return vars(Attempting)["_side_floors"](kern, decisions.frames_copy(kern.stack))


def _marked(clone: FlatClone[str], start: int) -> Frame[str]:
    """A sub-run's root frame, marked as :meth:`_attempt_run` marks one, on a
    clone the program flags as one a sub-run can root."""
    clone.sub_root = True
    frame: Frame[str] = Frame(flat_arm(1), [], clone, 0)
    frame.start = start
    return frame


def test_an_audit_with_no_record_is_undecidable() -> None:
    """An audit's sub-run is settled from the record its attempt pushed; a
    frame marked as an audit's with no record at its depth is nobody's."""
    below: Frame[str] = Frame(flat_arm(1), [], flat_clone(), 0)
    with pytest.raises(ProbeFork, match="no record"):
        _floors_of(_stacked(below, _marked(flat_clone(), -1)))


def test_a_fork_inside_a_span_check_is_undecidable() -> None:
    """``_spans_exactly`` re-runs an entry on the text truncated at the
    winner's end, a question about that one span: a side forked inside it has
    no caller to hand an answer back to, so the fork refuses."""
    below: Frame[str] = Frame(flat_arm(1), [], flat_clone(), 0)
    with pytest.raises(ProbeFork, match="span check"):
        _floors_of(_stacked(below, _marked(flat_clone(), -2)))


def test_a_sub_run_at_the_bottom_must_be_an_entry_of_the_start_clone() -> None:
    """A marked frame with nothing below it was started by the run itself;
    one the start clone does not enter is nobody's to settle."""
    with pytest.raises(ProbeFork, match="unowned"):
        _floors_of(_stacked(_marked(flat_clone(), 0)))


def _attempting(*subs: FlatClone[str]) -> FlatClone[str]:
    """An attempt clone whose entries all admit, so none is substituted."""
    return flat_clone(attempt=(None, tuple((None, False, None, None, s) for s in subs)))


@pytest.mark.parametrize(
    ("lo", "count", "callers"),
    [(0, 1, ["loop", "entry"]), (1, 2, ["loop", "entry"]), (1, 1, None)],
    ids=["optional", "past-its-minimum", "at-its-minimum"],
)
def test_an_attempt_entry_inside_a_loop_iteration_is_read_by_its_count(
    lo: int, count: int, callers: list[str] | None
) -> None:
    """A loop item whose payload is an attempt clone: the entry's frame is the
    only one on the stack, and whether a loop iteration runs it or a
    mandatory descent does is told by the count alone. Past the minimum only
    an iteration can; below it, only a descent; AT it, either — and a reading
    the stack cannot single out is refused, never guessed."""
    entry, other = flat_clone(attempt=None), flat_clone(attempt=None)
    arm = flat_arm(
        1,
        kinds=(OP_REF,),
        gate_kinds=(GATE_ATTEMPT,),
        los=(lo,),
        his=(-1,),
        payloads=(_attempting(entry, other),),
    )
    below: Frame[str] = Frame(arm, [], flat_clone(), 0)
    below.count = count
    kern = _stacked(below, _marked(entry, 0))
    if callers is None:
        with pytest.raises(ProbeFork, match="unowned"):
            _floors_of(kern)
        return
    _root, floors = _floors_of(kern)
    assert ["loop" if f[4] is not None else "entry" for f in floors] == callers
    entry_caller = floors[1][5]
    assert entry_caller is not None and entry_caller[1] is floors[0][2], (
        "the entry splices into the iteration"
    )


def test_a_plain_clone_lands_on_itself() -> None:
    """Nothing to chase and no entries to choose: ``_enter`` pushes the clone."""
    clone: FlatClone[str] = flat_clone(attempt=None)
    assert landing(clone, "x", 0) is clone
    assert landing(None, "x", 0) is None


def test_a_sole_admitted_entry_lands_where_it_does() -> None:
    """An attempt clone with one admitted entry is replaced by it, as
    ``_settle`` replaces it."""
    sole, barred = flat_clone(attempt=None), flat_clone(attempt=None)
    clone = flat_clone(
        attempt=(
            None,
            (
                (frozenset("x"), False, None, None, sole),
                (frozenset("y"), False, None, None, barred),
            ),
        )
    )
    assert landing(clone, "x", 0) is sole


def test_an_entry_two_subs_land_on_is_nobodys() -> None:
    """``entered`` names THE entry: two entries landing on one clone would
    leave the side to guess which one the live attempt was running."""
    target = flat_clone(attempt=None)
    assert entered(_attempting(target, flat_clone(attempt=None)), target, "x", 0)
    assert entered(_attempting(target, target), target, "x", 0) is None
    assert entered(flat_clone(attempt=None), target, "x", 0) is None


# ── a side drives floor by floor ────────────────────────────────────────────


def test_a_failure_above_a_floor_fails_the_sub_run_not_the_side(monkeypatch) -> None:
    """The live loop closes when its iteration fails; the side must too. The
    failure is settled at the floor, and the side drives on."""
    kern = _live_kernel("")
    kern.stack = [Frame(flat_arm(1), [], flat_clone(), 0)]
    floor = (1, 0, [], [], None, None)
    settled: list[bool] = []
    drives = iter([PdaFail("dead above the floor", 0), None])

    def drive(self, floor_depth: int = 0, _limit: int = -1) -> None:
        failure = next(drives)
        if failure is not None:
            raise failure
        del self.stack[floor_depth:]

    def settle(self, settling, derived: bool) -> None:
        settled.append(derived)
        del self.stack[settling[0] :]

    monkeypatch.setattr(PdaKernel, "_drive", drive)
    monkeypatch.setattr(Attempting, "_settle_floor", settle)
    vars(Attempting)["_drive_floors"](kern, [floor], -1)
    assert settled == [False]
    assert kern.stack == []


def test_a_side_that_drains_short_of_the_end_is_dead(monkeypatch) -> None:
    """With no floor left, an empty stack before the end is trailing input:
    the side is dead, and a side that drained AT the end completed."""
    kern = _live_kernel("ab")
    monkeypatch.setattr(PdaKernel, "_drive", lambda *_a, **_k: None)
    advance = vars(Attempting)["_advance"]
    assert advance(kern, ([], 1, None, [], []), -1) == (None, False)
    done, _sampled = advance(kern, ([], 2, None, ["r"], []), -1)
    assert done is not None and done[1] == 2 and done[3] == ["r"]


def test_the_recovery_restates_what_the_live_parse_did(monkeypatch) -> None:
    """A fork reads the stack with side-effect-free restatements of what the
    live parse decided, so on every corpus that attempts: each push is the
    clone ``landing`` names, each attempted iteration's frame is one
    ``iterating`` admits, each descent's item is one ``descending`` names, and
    each frame a sub-run marked is on a clone flagged ``sub_root`` — audit
    roots included."""
    real_enter = next(
        vars(c)["_enter"] for c in PdaKernel.__mro__ if "_enter" in vars(c)
    )
    real_drive = next(
        vars(c)["_drive"] for c in PdaKernel.__mro__ if "_drive" in vars(c)
    )
    real_iteration = Attempting.attempt_iteration
    seen = {"pushed": 0, "iterated": 0, "descended": 0, "marked": 0, "audits": 0}

    def descent_item(frame, clone, out) -> int:
        """The item ``frame`` is descending into with ``clone``, or ``-1``."""
        for k in (frame.i, frame.i - 1):
            if 0 <= k < frame.arm.n and frame.arm.payloads[k] is clone:
                transparent = frame.clone.mode == BUILD_TRANSPARENT
                sinks = frame.sinks
                if out is (frame.out if transparent else sinks and sinks[k]):
                    return k
        return -1

    def enter(self, clone, out):
        if self.stack and (k := descent_item(self.stack[-1], clone, out)) >= 0:
            assert k in descending(self.stack[-1])
            seen["descended"] += 1
        pos, depth = self.pos, len(self.stack)
        pushed = real_enter(self, clone, out)
        if pushed:
            assert landing(clone, self.text, pos) is self.stack[depth].clone
            seen["pushed"] += 1
        return pushed

    def drive(self, floor: int = 0, limit: int = -1) -> None:
        for frame in self.stack:
            start = getattr(frame, "start", None)
            if start is not None:
                assert frame.clone.sub_root
                seen["marked"] += 1
                seen["audits"] += start == -1
        return real_drive(self, floor, limit)

    def iteration(self, frame, arm, i, pos):
        if arm.kinds[i] in (OP_REF, OP_GRP):
            assert iterating(frame)
            seen["iterated"] += 1
        return real_iteration(self, frame, arm, i, pos)

    monkeypatch.setattr(PdaKernel, "_enter", enter)
    monkeypatch.setattr(PdaKernel, "_drive", drive)
    monkeypatch.setattr(Attempting, "attempt_iteration", iteration)
    for bench in BENCHES:
        if bench.name in ("gbnf-meta", "abnf-meta", "vyx", "markdown"):
            bench.compiled.parse(bench.corpus, cores=1)
    assert all(seen.values()), seen


def test_a_program_that_cannot_fork_marks_no_sub_run(monkeypatch) -> None:
    """A fork is an attempted loop's boundary, so markdown — attempt entries,
    no item gated ``GATE_ATTEMPT`` — flags no clone ``sub_root``: its
    sub-runs push frames that carry no start, and its audits hold no record."""
    real_drive = next(
        vars(c)["_drive"] for c in PdaKernel.__mro__ if "_drive" in vars(c)
    )
    real_init = KernelCaches.__init__
    seen = {"frames": 0, "marked": 0, "records": 0}

    class Audits(list):
        """The audit stack, counting what is pushed on it."""

        def append(self, record) -> None:
            seen["records"] += 1
            super().append(record)

    def init(self) -> None:
        real_init(self)
        self.audits = Audits()

    def drive(self, floor: int = 0, limit: int = -1) -> None:
        if floor:  # a sub-run's drive: its root frame sits at the floor
            seen["frames"] += 1
            seen["marked"] += hasattr(self.stack[floor], "start")
        return real_drive(self, floor, limit)

    monkeypatch.setattr(KernelCaches, "__init__", init)
    monkeypatch.setattr(PdaKernel, "_drive", drive)
    bench = next(b for b in BENCHES if b.name == "markdown")
    bench.compiled.parse(bench.corpus, cores=1)
    assert seen["frames"] and not seen["marked"] and not seen["records"], seen
