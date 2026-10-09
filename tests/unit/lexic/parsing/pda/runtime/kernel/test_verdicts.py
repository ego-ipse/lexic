"""Tests for lexic.parsing.pda.runtime.kernel.verdicts — the boundary verdict
``Attempting`` inherits.

A verdict reads the live cursor, so its seams are driven on real kernels: the
lockstep's convergence and its exception contract, the sampled-death rule, and
the sub-runs a side recovers from the stack and settles as their live callers
would, pinned against what the live parse actually did.
"""

from __future__ import annotations

import itertools

import pytest

from lexic.exceptions import LexicError
from lexic.ir import IrNamedTuple, IrStr
from lexic.parsing.earley.kernel.forest.support.ambiguity import ParseConfig
from lexic.parsing.earley.kernel.tables.decider import LEFTMOST_LONGEST, Decider
from lexic.parsing.pda.compiler.program.opcodes import (
    OP_REF,
    OP_REF1,
)
from lexic.parsing.pda.core.errors import PdaFail, ProbeFork
from lexic.parsing.pda.runtime import admission
from lexic.parsing.pda.runtime.admission import Side
from lexic.parsing.pda.runtime.build import Frame
from lexic.parsing.pda.runtime.kernel import sides, verdicts
from lexic.parsing.pda.runtime.kernel.kernel import PdaKernel, pda_model
from lexic.parsing.pda.runtime.kernel.sides import (
    PENDING,
    UNSEEN,
    Sides,
)
from lexic.parsing.pda.runtime.kernel.verdicts import (
    FORKED,
    STOP_FORCED,
    TAKE,
    Makers,
    Verdicts,
)
from tests import parity_helpers
from tests.paths import GROUND_TRUTH
from tests.unit.lexic.parsing.pda.runtime.flat_support import flat_arm, flat_clone
from tests.unit.lexic.parsing.pda.runtime.kernel.side_support import (
    NOISE_RUNS,
    TOP,
    completed_side,
    converged_tally,
    live_kernel,
)
from tests.unit.lexic.parsing.pda.runtime.pda_runtime_helpers import compiled_and_pda
from tools.benchmark.cases.grammars import BENCHES


def _at_a_boundary(kern: PdaKernel) -> PdaKernel:
    """``kern`` standing in a boundary's frame: the verdict reads its count."""
    kern.stack = [Frame(flat_arm(1), [], flat_clone(), 0)]
    return kern


def test_a_dead_stop_side_costs_two_stack_copies_not_three(monkeypatch) -> None:
    """The lockstep answers the verdict a third copy used to re-derive.

    A fork verdict forks the stack twice for the lockstep's two sides; when the
    STOP side dies there, the verdict is already settled, and probing the stop
    side again only re-establishes that death. Counted rather than asserted
    about: every :func:`frames_copy` call during a parse that forks, against
    the number of lockstep verdicts asked, a boundary inside a side included.

    The copy count alone would hold for the wrong reason — two copies per
    verdict says only that no verdict fell through to a probe, which any
    lockstep settlement satisfies. So the dead-stop settlements are counted
    too: ``_lockstep_verdict`` settles through ``_converged`` or through the
    branch this commit adds, and nothing else, so the difference IS that
    branch and a non-zero difference is the evidence it ran.
    """
    bench = next(one for one in BENCHES if one.name == "vyx")
    counted = {"copies": 0, "verdicts": 0, "asked": 0, "settled": 0, "converged": 0}
    copy = sides.frames_copy
    defined = vars(verdicts.Verdicts)  # what the class DEFINES
    verdict, lockstep, converged = (
        defined["_fork_verdict"],
        defined["_lockstep_verdict"],
        defined["_converged"],
    )

    def counting_copy(stack, every_end=False, remap=None):
        """`frames_copy`, counted."""
        counted["copies"] += 1
        return copy(stack, every_end, remap)

    def counting_verdict(self, *args, **kwargs):
        """`_fork_verdict`, counted."""
        counted["verdicts"] += 1
        return verdict(self, *args, **kwargs)

    def counting_lockstep(self, *args, **kwargs):
        """`_lockstep_verdict`, counting the boundaries it SETTLES."""
        counted["asked"] += 1
        answer = lockstep(self, *args, **kwargs)
        counted["settled"] += answer is not None
        return answer

    def counting_converged(self, *args, **kwargs):
        """`_converged`, counting the settlements that came from convergence."""
        answer = converged(self, *args, **kwargs)
        counted["converged"] += answer is not None
        return answer

    monkeypatch.setattr(sides, "frames_copy", counting_copy)
    monkeypatch.setattr(verdicts.Verdicts, "_fork_verdict", counting_verdict)
    monkeypatch.setattr(verdicts.Verdicts, "_lockstep_verdict", counting_lockstep)
    monkeypatch.setattr(verdicts.Verdicts, "_converged", counting_converged)
    bench.compiled.parse(bench.corpus, cores=1)

    assert counted["verdicts"], (
        "this document no longer forks — the test proves nothing"
    )
    assert counted["settled"] > counted["converged"], (
        "no boundary settled on a dead STOP side — the branch under test "
        "never ran, so the copy count below proves nothing about it"
    )
    assert counted["asked"] >= counted["verdicts"]
    assert counted["copies"] == 2 * counted["asked"]


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
    monkeypatch.setattr(verdicts, "pending_values", lambda _stack, _shape: ())
    tally = converged_tally(bench.compiled, VYX_CONVERGES, monkeypatch)

    assert tally["converged"] == 1, (
        f"this packet no longer converges — it witnesses nothing: {tally}"
    )
    assert tally["agree"] == 1, (
        f"agreeing snapshots must settle without a drive: {tally}"
    )
    assert (tally["dead"], tally["fork"]) == (0, 0), tally
    assert (tally["other"], tally["nested"]) == (0, 0), tally


VYX_CONVERGES = "!P %P \U000e465b\\n# \\nS:t={y} >\n"
"""A generated vyx packet (seed 221) whose one boundary converges, unguessed,
with values that differ and a common remainder that dies."""


def test_a_converged_boundary_takes_when_the_common_remainder_dies(
    monkeypatch,
) -> None:
    """Values DIFFER, so the remainder decides — and it does not complete.

    The two sides reconverge, but each built a different value getting there,
    which is the question a fork exists to ask. The remainder past the
    convergence is COMMON, so it is run ONCE rather than twice: dying means
    neither side completes, and the boundary is :data:`TAKE` exactly as a
    dead stop side is.

    The document is a generated vyx packet, a natural witness: neither side
    guessed on its way to the convergence, so the remainder's death settles
    it. The packet the property suite once found here reached it only because
    the stop side misread an ``OP_REF1``-suspended frame's rest; read
    correctly, its sides guess, and a guess settles nothing.
    """
    bench = next(one for one in BENCHES if one.name == "vyx")
    tally = converged_tally(bench.compiled, VYX_CONVERGES, monkeypatch)

    assert tally["converged"] == 1, (
        f"this packet no longer converges — it witnesses nothing: {tally}"
    )
    assert tally["dead"] == 1, (
        "a converged boundary here must settle on a remainder that DIES, not "
        f"on agreement and not on a fork: {tally}"
    )
    assert (tally["agree"], tally["fork"]) == (0, 0), tally
    assert (tally["other"], tally["nested"]) == (0, 0), tally


def test_a_converged_boundary_is_ranked_when_the_common_remainder_completes(
    monkeypatch,
) -> None:
    """Values DIFFER and the remainder COMPLETES — the difference is real, and
    the decider's rank answers it.

    Reached by injection on a real convergence: the vyx packet's snapshots are
    made distinct at the one site that reads them, its shared remainder is
    reported complete, and the rank answers a verdict nothing else here gives,
    so the converged boundary must answer the rank's verdict rather than settle
    whatever the remainder would have done.
    """
    bench = next(one for one in BENCHES if one.name == "vyx")
    distinct = itertools.count()
    monkeypatch.setattr(
        verdicts, "pending_values", lambda _stack, _shape: (next(distinct),)
    )
    drive = vars(Sides)["_advance"]

    def completing(self, side, limit, shared=False):
        if shared:
            return side, False
        return drive(self, side, limit, shared)

    monkeypatch.setattr(Sides, "_advance", completing)
    monkeypatch.setattr(Verdicts, "_ranked", lambda *_a: STOP_FORCED)
    tally = converged_tally(bench.compiled, VYX_CONVERGES, monkeypatch)

    assert tally["converged"] >= 1, (
        f"the convergence path did not run — this witnesses nothing: {tally}"
    )
    assert tally["ranked"] == tally["converged"], (
        "a converged boundary whose remainder completes must answer the rank, "
        f"not settle the boundary itself: {tally}"
    )
    assert (tally["agree"], tally["dead"], tally["fork"]) == (0, 0, 0), tally
    assert (tally["other"], tally["nested"]) == (0, 0), tally


def test_a_refusal_on_a_converged_remainder_is_undecidable(monkeypatch) -> None:
    """Values DIFFER and the common remainder REFUSES — the boundary bails.

    The remainder is run once, on the LEFT side's stack, so its completions
    read the values the left side built. A refusal there is a verdict about
    those values, not about the right side's: it is neither a death of both
    sides nor a completion, so ``_converged`` raises :class:`ProbeFork` and
    the gated engine answers. Read as a death, it would settle :data:`TAKE`.

    The document is the convergence witness above: its remainder completes
    ``inline-content``, and that completion is made to refuse
    — only inside ``_converged``'s own drive.
    """
    bench = next(one for one in BENCHES if one.name == "vyx")
    text = VYX_CONVERGES
    converged = vars(verdicts.Verdicts)["_converged"]
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

    monkeypatch.setattr(verdicts.Verdicts, "_converged", converging)
    monkeypatch.setattr(PdaKernel, "_complete", refusing)
    kernel = PdaKernel(bench.compiled.pda_tables(), text, bench.compiled.executor)
    with pytest.raises(PdaFail):
        kernel.run()
    assert refused[0], "no completion refused inside the drive — nothing tested"
    assert len(answers) == 1 and "shared remainder" in str(answers[0]), answers


# ── an attempted island that cannot settle its extent bails ─────────────────


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
    read apart, the common remainder decides; here it completes, and with no
    step the rank can read, the boundary forks."""
    kern = _at_a_boundary(live_kernel())
    end = len(kern.text)
    monkeypatch.setattr(
        Sides,
        "_advance",
        lambda _self, side, _limit, shared=False: (completed_side(end, []), False),
    )
    converged = vars(Verdicts)["_converged"]
    left = (_holding(_Left(IrStr("x"))), end, None, [], [], [], [TOP], ())
    right = (_holding(_Right(IrStr("x"))), end, None, [], [], [], [TOP], ())
    assert converged(kern, left, right, (), False, _made(left, right)) == FORKED
    same = (_holding(_Left(IrStr("x"))), end, None, [], [], [], [TOP], ())
    assert converged(kern, left, same, (), False, _made(left, same)) == TAKE


# ── the sampled-death rule ──────────────────────────────────────────────────


def _as_side(probed: tuple[list[str] | None, bool]) -> tuple[Side | None, bool]:
    """A probe's ``(root output | None, uncertain)`` as ``_probe`` reports it."""
    values, uncertain = probed
    return (None if values is None else completed_side(1, list(values))), uncertain


@pytest.mark.parametrize(
    ("stop", "take", "verdict"),
    [
        ((None, True), (["s"], False), FORKED),
        ((None, False), (["s"], False), TAKE),
        ((["s"], False), (None, True), FORKED),
        ((["s"], False), (None, False), STOP_FORCED),
        ((["s"], True), (["s"], False), FORKED),
        ((["s"], False), (["s"], False), TAKE),
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
    kern = live_kernel()
    monkeypatch.setattr(Verdicts, "_lockstep_verdict", lambda *_a: None)
    monkeypatch.setattr(
        Sides,
        "_probe",
        lambda _self, _arm, _i, _pos, taken: _as_side(stop if taken is None else take),
    )
    fork_verdict = vars(Verdicts)["_fork_verdict"]
    assert fork_verdict(kern, flat_arm(1), 0, 0, (1, [])) == verdict


@pytest.mark.parametrize(
    ("stop_guessed", "take_guessed", "verdict"),
    [(True, False, FORKED), (False, True, TAKE), (False, False, TAKE)],
    ids=["stop-guessed", "only-take-guessed", "clean"],
)
def test_a_stop_side_death_is_judged_by_its_own_drive(
    monkeypatch, stop_guessed: bool, take_guessed: bool, verdict: int
) -> None:
    """The lockstep's stop side dies on its first advance. Only ITS drive's
    guess unsettles that death: a guess on the take side's drive says nothing
    about whether stopping could have survived."""
    kern = live_kernel()
    made = iter([completed_side(0, []), completed_side(1, [])])
    monkeypatch.setattr(Sides, "_side", lambda *_a: next(made))
    monkeypatch.setattr(
        Sides,
        "_advance",
        lambda _self, side, _limit, shared=False: (
            (None, stop_guessed) if side[1] == 0 else (side, take_guessed)
        ),
    )
    lockstep = vars(Verdicts)["_lockstep_verdict"]
    assert lockstep(kern, flat_arm(1), 0, 0, (1, [])) == verdict


@pytest.mark.parametrize(
    ("stack", "verdict"), [("mid-parse", FORKED), ("completed", FORKED)]
)
def test_a_guess_unsettles_every_convergence(
    monkeypatch, stack: str, verdict: int
) -> None:
    """Both convergences agree and both were reached after a guess, so both
    fork: a side that guessed may have dropped the carving the decider keeps,
    agreement included, and completing does not change that."""
    kern = live_kernel()
    frames = _holding("v") if stack == "mid-parse" else []
    monkeypatch.setattr(
        Sides, "_advance", lambda _self, side, _limit, shared=False: (side, False)
    )
    side = (frames, len(kern.text), None, [], [], [], [TOP], ())
    assert (
        vars(Verdicts)["_converged"](kern, side, side, (), True, _made(side, side))
        == verdict
    )


@pytest.mark.parametrize(
    ("sampled", "verdict"), [(True, FORKED), (False, TAKE)], ids=["sampled", "clean"]
)
def test_a_shared_remainder_that_dies_after_a_guess_decides_nothing(
    monkeypatch, sampled: bool, verdict: int
) -> None:
    """Converged sides whose values differ run their common remainder once,
    and here it dies. Reached through a guess, the death is the guess's, so
    the boundary forks; with none, neither side completes and the take
    stands."""
    kern = _at_a_boundary(live_kernel())
    monkeypatch.setattr(
        Sides, "_advance", lambda _self, side, _limit, shared=False: (None, sampled)
    )
    left = (_holding(_Left(IrStr("x"))), 1, None, [], [], [], [TOP], ())
    right = (_holding(_Right(IrStr("x"))), 1, None, [], [], [], [TOP], ())
    assert (
        vars(Verdicts)["_converged"](kern, left, right, (), False, _made(left, right))
        == verdict
    )


@pytest.mark.parametrize(
    ("floors", "verdict"), [([], FORKED), ([None], TAKE)], ids=["same", "apart"]
)
def test_sides_converge_only_inside_the_same_sub_runs(
    monkeypatch, floors: list[None], verdict: int
) -> None:
    """Two sides at one position in one control state share a future only if
    they stand inside the same sub-runs: one still inside a floor settles it
    on the way, the other does not. Apart, the sides advance instead — and
    here the stop side dies, so the take is forced."""
    kern = live_kernel()
    frames = _holding("v")
    made = iter(
        [
            (frames, 1, None, [], [], [], [TOP], ()),
            (frames, 1, None, [], floors, [], [TOP], ()),
        ]
    )
    monkeypatch.setattr(Sides, "_side", lambda *_a: next(made))
    monkeypatch.setattr(Verdicts, "_converged", lambda *_a: FORKED)
    monkeypatch.setattr(
        Sides, "_advance", lambda _self, side, _limit, shared=False: (None, False)
    )
    lockstep = vars(Verdicts)["_lockstep_verdict"]
    assert lockstep(kern, flat_arm(1), 0, 0, (1, [])) == verdict


def test_completed_sides_that_differ_are_ranked(monkeypatch) -> None:
    """Two completed sides hold empty stacks, whose pending snapshots are both
    ``()``. What they built is in their root outputs; those differ, so the
    rank decides — and where it cannot read the step, or a guess reached the
    sides, the boundary forks."""
    kern = _at_a_boundary(live_kernel())
    end = len(kern.text)
    converged = vars(Verdicts)["_converged"]
    ranks = iter([STOP_FORCED, FORKED])
    monkeypatch.setattr(Verdicts, "_ranked", lambda *_a: next(ranks))
    left, right = completed_side(end, ["x", "y"]), completed_side(end, ["xy"])
    assert converged(kern, left, right, (), False, _made(left, right)) == STOP_FORCED
    assert converged(kern, left, right, (), False, _made(left, right)) == FORKED
    assert converged(kern, left, right, (), True, _made(left, right)) == FORKED
    assert (
        converged(
            kern,
            left,
            completed_side(end, ["x", "y"]),
            (),
            False,
            _made(left, completed_side(end, ["x", "y"])),
        )
        == TAKE
    )


# ── the rank: the first frame whose carving differs, at its step ───────────


class _Shortest(Decider):
    """The first slot takes as little as it can."""

    def slot(self, end: int) -> int:
        return -end


def _made(left: Side, right: Side) -> Makers:
    """Makers handing back two sides built by hand, whatever is asked."""
    return (lambda side, _record: side), (left,), (right,)


def _boundary(
    parent: Frame | None = None, count: int = 1, decide: Decider = LEFTMOST_LONGEST
) -> PdaKernel:
    """A kernel standing at a boundary at 2 whose loop has taken ``count``,
    under ``parent`` — by default a frame descending into an exactly-once
    reference — and parsing under ``decide``."""
    compiled, pda = compiled_and_pda(GROUND_TRUTH / "json.gbnf")
    kern = PdaKernel(
        pda, "x" * 10, compiled.executor, config=ParseConfig(decide=decide)
    )
    if parent is None:
        parent = Frame(flat_arm(1, kinds=(OP_REF1,)), [], flat_clone(), 0)
        parent.i = 1
    top = Frame(flat_arm(1), [], flat_clone(), 0)
    top.count = count
    kern.stack, kern.pos = [parent, top], 2
    return kern


def _ranked(
    kern: PdaKernel,
    stop: list[int],
    take: list[int],
    loops: tuple[int | None, int | None] = (None, None),
) -> int:
    """``_rank`` at ``kern``'s boundary on two completed sides with these
    ledgers (:func:`_sides`)."""
    return vars(Verdicts)["_rank"](kern, *_sides(kern, stop, take, loops))


def _sides(
    kern: PdaKernel,
    stop: list[int],
    take: list[int],
    loops: tuple[int | None, int | None] = (None, None),
) -> tuple[Side, Side]:
    """Two completed sides at ``kern``'s boundary with these ledgers, the
    boundary's loop ending at 2 on the stop side and at 5 on the take side.
    ``loops`` closes the parent's loop on each side at that end (``None``:
    still open)."""
    arm = kern.stack[0].arm
    pairs = []
    for ledger, loop_end, closed in zip((stop, take), (2, 5), loops):
        mine = Frame(arm, [], flat_clone(), 0)
        mine.ends = [-1] * (arm.n + 1)
        if closed is not None:
            mine.i, mine.ends[1] = 1, closed
        copy = Frame(flat_arm(1), [], flat_clone(), 0)
        copy.ends = [-1, loop_end]
        pairs.append(([], 10, None, [], [], ledger, [mine, copy], ()))
    return pairs[0], pairs[1]


@pytest.mark.parametrize(
    ("stop", "take", "decide", "verdict"),
    [
        ([10, 3], [10, 5], LEFTMOST_LONGEST, TAKE),
        ([10, 6], [10, 5], LEFTMOST_LONGEST, STOP_FORCED),
        ([10, 3], [10, 5], _Shortest(frozenset()), STOP_FORCED),
    ],
    ids=["longer-take", "longer-stop", "shortest"],
)
def test_the_first_frame_completing_apart_is_ranked_at_its_parents_step(
    stop: list[int], take: list[int], decide: Decider, verdict: int
) -> None:
    """The root completes alike; the boundary's frame does not, so its
    parent's step into it is the first that differs, and the decider's slot
    for that end decides."""
    assert _ranked(_boundary(decide=decide), stop, take) == verdict


@pytest.mark.parametrize(
    ("decide", "verdict"),
    [(LEFTMOST_LONGEST, TAKE), (_Shortest(frozenset()), STOP_FORCED)],
    ids=["leftmost-longest", "shortest"],
)
def test_frames_completing_alike_leave_the_boundarys_loop_end(
    decide: Decider, verdict: int
) -> None:
    """Every copied frame completes at one place on both sides, so the first
    differing step is the boundary's own loop: it ends at the boundary when
    stopped, later when taken — the loop is one step, as Earley reads it."""
    assert _ranked(_boundary(decide=decide), [10, 7], [10, 7]) == verdict


def _in_a_loop() -> Frame:
    """A parent frame descending into an unbounded loop it has counted."""
    frame: Frame[object] = Frame(
        flat_arm(1, kinds=(OP_REF,), los=(0,), his=(-1,), gate_kinds=(0,)),
        [],
        flat_clone(),
        0,
    )
    frame.count = 1
    return frame


@pytest.mark.parametrize(
    ("stop", "take", "parent", "count"),
    [
        ([10, -2], [10, -2], None, 1),
        ([10, 2], [10, 5], _in_a_loop(), 0),
    ],
    ids=["settled-elsewhere", "zero-width-iteration"],
)
def test_a_step_the_ledger_cannot_read_forks(
    stop: list[int], take: list[int], parent: Frame | None, count: int
) -> None:
    """A sub-run its caller settled on something else, and an iteration the
    loop's carving may drop — the stop side's, at a boundary whose loop had
    taken nothing, in a loop that ends alike on both sides — both fork."""
    assert _ranked(_boundary(parent, count), stop, take) == FORKED


@pytest.mark.parametrize(
    ("decide", "at", "verdict"),
    [
        (LEFTMOST_LONGEST, 4, TAKE),
        (_Shortest(frozenset()), 4, FORKED),
        (LEFTMOST_LONGEST, 3, FORKED),
    ],
    ids=["longest", "shortest-iterations-fork", "may-end-alike"],
)
def test_a_child_still_open_at_a_convergence_ranks_by_where_it_can_end(
    decide: Decider, at: int, verdict: int
) -> None:
    """The stop side's iteration completed at 3; the take side's is still
    open at the convergence, so it ends at the convergence or later. Where
    every such end ranks the same way against 3 the rank answers; where one
    of them is 3 itself, it cannot. They are iterations of a loop, which only
    leftmost-longest's order is known to rank as Earley does."""
    kern = _boundary(_in_a_loop(), decide=decide)
    kern.text = "x" * 6
    stop, take = _sides(kern, [10, 3], [10, PENDING])
    assert vars(Verdicts)["_rank"](kern, stop[:1] + (at,) + stop[2:], take) == verdict


@pytest.mark.parametrize(
    ("loops", "verdict"),
    [
        ((8, 6), STOP_FORCED),
        ((6, 8), TAKE),
        ((None, None), FORKED),
        ((8, None), FORKED),
    ],
    ids=["stop-ends-later", "take-ends-later", "loop-open", "closed-on-one-side"],
)
def test_a_child_the_ledger_cannot_read_is_ranked_by_its_parents_loop_end(
    loops, verdict: int
) -> None:
    """The take side's iteration was a sub-run its loop closed instead of
    committing, so where that child completed is unreadable. The parent's
    loop still recorded where it ended on both sides — the parent's own step
    — and that ranks; with no end recorded on both sides, nothing does."""
    kern = _boundary(_in_a_loop())
    assert _ranked(kern, [10, 4], [10, UNSEEN], loops) == verdict


@pytest.mark.parametrize(
    ("stop", "take", "decide", "verdict"),
    [
        ([10, 2], [10, 5], LEFTMOST_LONGEST, TAKE),
        ([10, 7], [10, 7], LEFTMOST_LONGEST, TAKE),
        ([10, 2], [10, 5], _Shortest(frozenset()), STOP_FORCED),
        ([10, 7], [10, 7], _Shortest(frozenset()), STOP_FORCED),
    ],
    ids=["step-longest", "loop-longest", "step-shortest", "loop-shortest"],
)
def test_a_zero_width_step_of_a_node_is_ranked_raw(
    stop: list[int], take: list[int], decide: Decider, verdict: int
) -> None:
    """The boundary's loop had taken nothing, so the stop side's step — the
    child's end, or the loop's own — ends where the one before it did. Earley
    compares a node's boundaries raw, that step included, so the rank answers:
    the decider's slot for the first end that differs."""
    assert _ranked(_boundary(count=0, decide=decide), stop, take) == verdict


@pytest.mark.parametrize(
    ("loops", "verdict"),
    [((None, None), TAKE), ((8, 6), STOP_FORCED), ((8, None), FORKED)],
    ids=["loop-open", "loop-ends-apart", "closed-on-one-side"],
)
def test_a_frame_suspended_in_a_loop_ranks_its_loop_end_first(
    loops, verdict: int
) -> None:
    """The parent's step into a loop is where the LOOP ends: two loop ends
    that differ decide it; a loop still open on both sides ends alike, so its
    iterations decide, the forked one's end first; a loop closed on one side
    only cannot be read, and forks."""
    assert _ranked(_boundary(_in_a_loop()), [10, 3], [10, 5], loops) == verdict


TAIL_CARVING = (
    'root ::= w "b"?\nw ::= x? tail?\nx ::= item+\nitem ::= "a"\ntail ::= "a" "b"\n'
)
"""``aab`` completes two ways: ``x`` takes both ``a`` and ``"b"?`` the ``b``, or
``x`` takes one and ``tail`` the rest — which the decider keeps."""


def test_a_completed_carving_the_decider_does_not_keep_is_not_committed() -> None:
    """Both sides of a boundary complete ``aab``. Read at convergence as two
    empty snapshots, they agree, and the predictive parse commits the take: a
    model the gated engine, keeping the decider's carving, does not build."""
    predictive, gated = parity_helpers.answers(
        TAIL_CARVING, "verdicts-tail-carving", "aab"
    )
    assert gated == "Root(W(X((Item('a'),)), Tail('ab')), '')"
    assert predictive == gated


TWO_RUNS = "# @non-semantic n m\ndoc ::= item n? m? item\n" + NOISE_RUNS
"""Two runs of one unit side by side: where ``n`` stops and ``m`` starts is a
choice the values record."""


def test_a_completed_carving_the_decider_keeps_stays_on_the_pda() -> None:
    """Both sides complete ``x #a\\nx``, and the take is the carving the decider
    keeps (``n`` longest): the predictive parse answers, with the gated
    engine's model."""
    predictive, gated = parity_helpers.answers(TWO_RUNS, "verdicts-two-runs", "x #a\nx")
    assert predictive != parity_helpers.DECLINED
    assert predictive == gated


SECTIONS = (
    'doc ::= sec+\nsec ::= stmt+ end\nstmt ::= "!" | ";"? [a;]\n'
    'end ::= [a;] | [a]* "a"\n'
)
"""Every section closes with ``end``, and ``!`` is only ever a statement."""


@pytest.mark.parametrize("text", [";aaaa!", ";aaa;!"])
def test_a_retry_nested_four_deep_rejects_what_no_carving_derives(text: str) -> None:
    """No carving derives the text: the trailing ``!`` opens a section no
    ``end`` closes. The first boundary's sides meet an island with two ends,
    each needing a verdict of its own four sides deep before every side dies
    exactly; nested less deep, the deaths are guesses, the boundary forks and
    the predictive engine declines a document it can reject itself."""
    compiled, product = parity_helpers.built(SECTIONS, "verdicts-sections")
    with pytest.raises(PdaFail) as refusal:
        pda_model(product.pda, text, compiled.product.executor)
    assert not isinstance(refusal.value, ProbeFork), refusal.value
    assert parity_helpers.answers(SECTIONS, "verdicts-sections", text)[1] == (
        parity_helpers.REFUSED
    )


def test_a_parse_whose_allowance_is_spent_forks_as_before_the_retry(
    monkeypatch,
) -> None:
    """The same rejection, with no nested verdicts left to the parse: the
    boundary's fork is not retried, and the document goes to the gated engine
    — the predictive engine's answer before retries, never a wrong one."""
    monkeypatch.setattr(admission, "PARSE_NESTING", 0)
    compiled, product = parity_helpers.built(SECTIONS, "verdicts-sections")
    with pytest.raises(ProbeFork):
        pda_model(product.pda, ";aaaa!", compiled.product.executor)


def _open_rank(
    monkeypatch: pytest.MonkeyPatch,
    decide: Decider,
    length: int,
    ends: tuple[int, int] = (3, PENDING),
    at: int = 4,
) -> tuple[int, list[int]]:
    """``_kept_open`` at a convergence at ``at`` of two steps ``ends``, one
    still open, over a text of ``length``: its verdict, and the open step's
    end at each rank it asked."""
    kern = _boundary(decide=decide)
    kern.text = "x" * length
    real = vars(Verdicts)["_kept"]
    open_side = ends.index(PENDING)
    asked: list[int] = []

    def counted(self: PdaKernel, stop: tuple[int, ...], take: tuple[int, ...]) -> int:
        asked.append((stop, take)[open_side][0])
        return real(self, stop, take)

    monkeypatch.setattr(Verdicts, "_kept", counted)
    return vars(Verdicts)["_kept_open"](kern, ends, at), asked


def test_an_open_step_under_leftmost_longest_is_ranked_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every end from the convergence on is past the closed step, and
    leftmost-longest's slot is the end itself, so the first end answers for
    all of them: one rank, whatever the text's length."""
    assert _open_rank(monkeypatch, LEFTMOST_LONGEST, 10_000) == (TAKE, [4])


def test_an_open_step_under_another_decider_is_ranked_end_by_end(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Another decider's order is asked at every end the step can reach; the
    shortest keeps the closed step against each of them."""
    verdict, asked = _open_rank(monkeypatch, _Shortest(frozenset()), 20)
    assert verdict == STOP_FORCED
    assert sorted(asked) == list(range(4, 21))


def test_an_open_step_with_many_ends_is_still_answered_on_the_pda(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """However many ends the step can reach, another decider's order is asked
    at each of them and answered here: which carving to keep is the decider's
    question, settled on the predictive engine, never sent to Earley."""
    verdict, asked = _open_rank(monkeypatch, _Shortest(frozenset()), 500)
    assert verdict == STOP_FORCED
    assert sorted(asked) == list(range(4, 501))


def test_an_open_stop_step_under_leftmost_longest_is_ranked_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The stop side's step still open, the take side's closed at 3: the open
    one ends at the convergence or later, past 3, so leftmost-longest keeps
    the stop side, asking once."""
    assert _open_rank(monkeypatch, LEFTMOST_LONGEST, 10_000, (PENDING, 3)) == (
        STOP_FORCED,
        [4],
    )


@pytest.mark.parametrize("open_side", [0, 1])
@pytest.mark.parametrize(("closed", "at", "length"), [(0, 1, 1), (2, 3, 9), (3, 7, 12)])
def test_leftmost_longests_one_rank_answers_as_every_end_would(
    monkeypatch: pytest.MonkeyPatch, open_side: int, closed: int, at: int, length: int
) -> None:
    """The single rank at the convergence gives what ranking every reachable
    end gives — leftmost-longest's slot is the end, so they all rank alike."""
    ends = (PENDING, closed) if open_side == 0 else (closed, PENDING)
    kept = vars(Verdicts)["_kept"]
    kern = _boundary()
    every = {
        kept(kern, *((end if end != PENDING else reach,) for end in ends))
        for reach in range(at, length + 1)
    }
    one, asked = _open_rank(monkeypatch, LEFTMOST_LONGEST, length, ends, at)
    assert asked == [at]
    assert every == {one}
