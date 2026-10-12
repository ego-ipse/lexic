"""Tests for lexic.parsing.pda.runtime.kernel.sides — the stacks a boundary
verdict is asked on.

A side is driven on a real kernel, so its seams are exercised there: the
``_advance`` exception contract, the floors a side recovers from the stack and
settles as their live callers would, and the replays that recovery reads,
pinned against what the live parse actually did.
"""

from __future__ import annotations

import pytest

from lexic.compile import compile_text
from lexic.parsing.pda.compiler.program.flatten import FlatClone
from lexic.parsing.pda.compiler.program.opcodes import (
    BUILD_TRANSPARENT,
    GATE_ATTEMPT,
    OP_GRP,
    OP_REF,
    OP_REF1,
)
from lexic.parsing.pda.core.errors import PdaFail, ProbeFork
from lexic.parsing.pda.runtime.admission import Floor, Side
from lexic.parsing.pda.runtime.build import Frame
from lexic.parsing.pda.runtime.kernel import sides
from lexic.parsing.pda.runtime.kernel.decisions import Attempting
from lexic.parsing.pda.runtime.kernel.kernel import PdaKernel
from lexic.parsing.pda.runtime.kernel.sides import (
    Sides,
    descending,
    entered,
    iterating,
    landing,
)
from lexic.parsing.pda.runtime.kernel.verdicts import (
    Verdicts,
)
from tests import parity_helpers
from tests.unit.lexic.parsing.pda.runtime.flat_support import flat_arm, flat_clone
from tests.unit.lexic.parsing.pda.runtime.kernel.side_support import (
    NOISE_RUNS,
    TOP,
    completed_side,
    converged_tally,
    live_kernel,
)
from tools.benchmark.cases.grammars import BENCHES


def _raise(why: BaseException) -> None:
    """Raise from inside a lambda, so the patched drive stays one expression."""
    raise why


def _side(kern: PdaKernel) -> Side:
    """The lockstep side ``_advance`` swaps in — the cursor triple, as a value.

    The reach is the subject, not an accident of testing: ``_routes`` is
    private because nothing outside the kernel may steer it, and a test of
    that seam's exception contract has to stand exactly where the seam does.
    The three tests below reach through here, so the reach is stated once.
    """
    routes = kern._routes  # pylint: disable=protected-access
    return kern.stack, kern.pos, routes, [], [], [], [TOP], ()


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
    died. The lockstep answers :data:`TAKE` on a dead STOP side, so a
    swallowed fork would commit a take the gated engine never got to refuse.

    Injected at the seam deliberately: the contract under test is the
    EXCEPTION's, and a grammar that happens to fork here would test the
    grammar as much as the handler.
    """
    kern = live_kernel()
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
    kern = live_kernel()
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
    kern = live_kernel()
    side = _side(kern)
    monkeypatch.setattr(
        PdaKernel, "_drive", lambda *_a, **_k: _raise(PdaFail("dead", 0))
    )
    assert _advance(kern, side) is None


# ── a fork inside an attempt sub-run settles it, as the live parse would ────


def _floors_seen(compiled, text: str, monkeypatch) -> list[list[str]]:
    """Parse ``text`` and name the caller of every floor each side was built
    with — ``loop``, ``entry`` or ``audit`` — recorded at :meth:`_side_floors`."""
    real = vars(Sides)["_side_floors"]
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

    monkeypatch.setattr(Sides, "_side_floors", recording)
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
    tally = converged_tally(bench.compiled, text, monkeypatch)
    monkeypatch.undo()
    seen = _floors_seen(bench.compiled, text, monkeypatch)
    predictive, _gated = parity_helpers.answers(bench.source, "verdicts-gbnf", text)

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
    predictive, gated = parity_helpers.answers(bench.source, "verdicts-vyx", text)

    assert ["entry"] in seen, f"no side was forked inside an attempt entry: {seen}"
    assert predictive == gated


ENTRY_AT_THE_START = (
    "# @non-semantic n m\n"
    "root ::= a | b\n"
    'a ::= item n? m? item ";"\n'
    'b ::= item n? m? item "."\n' + NOISE_RUNS
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
        vars(Sides)["_side_floors"],
        vars(Verdicts)["_converged"],
    )
    bottoms: list[bool] = []
    roots: list[tuple[int, int]] = []

    def floors(self, forked):
        root, found = real_floors(self, forked)
        bottoms.extend(root is f[5][1] for f in found if f[0] == 0)
        return root, found

    def converged(self, left, right, *rest):
        roots.append((len(left[3]), len(right[3])))
        return real_converged(self, left, right, *rest)

    monkeypatch.setattr(Sides, "_side_floors", floors)
    monkeypatch.setattr(Verdicts, "_converged", converged)
    predictive, gated = parity_helpers.answers(
        ENTRY_AT_THE_START, "verdicts-entry-start", "x #a\nx."
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
    compiled = compile_text(ENTRY_AT_THE_START, cache_key="verdicts-entry-start")
    seen = _floors_seen(compiled, "x #a\nx;", monkeypatch)
    predictive, gated = parity_helpers.answers(
        ENTRY_AT_THE_START, "verdicts-entry-start", "x #a\nx;"
    )
    assert any("audit" in floors for floors in seen), seen
    assert (
        predictive
        == gated
        == "A(Item('x'), Item('x'), N((NunitArm1(' '), Cl('#a\\n'))))"
    )


def _stacked(*frames: Frame[str], text: str = "x") -> PdaKernel:
    """A kernel standing on ``frames``, as a fork would find it."""
    kern = live_kernel(text)
    kern.stack = list(frames)
    return kern


def _floors_of(kern: PdaKernel) -> tuple[list[str], list[Floor]]:
    """What :meth:`_side_floors` reads off ``kern``'s stack."""
    return vars(Sides)["_side_floors"](kern, sides.frames_copy(kern.stack))


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
    kern = live_kernel("")
    kern.stack = [Frame(flat_arm(1), [], flat_clone(), 0)]
    floor = (1, 0, [], [], None, None)
    settled: list[bool] = []
    drives = iter([PdaFail("dead above the floor", 0)])

    def drive(self, floor_depth: int = 0, _limit: int = -1) -> None:
        failure = next(drives, None)
        if failure is not None:
            raise failure
        del self.stack[floor_depth:]

    def settle(self, settling, derived: bool) -> None:
        settled.append(derived)
        del self.stack[settling[0] :]

    monkeypatch.setattr(PdaKernel, "_drive", drive)
    monkeypatch.setattr(Sides, "_settle_floor", settle)
    ledger = [-1, -1]
    vars(Sides)["_drive_floors"](kern, [floor], ledger, -1)
    assert settled == [False]
    assert kern.stack == []
    assert ledger == [0, -2]  # the frame's own end; the failed sub-run unseen


def test_a_side_that_drains_short_of_the_end_is_dead(monkeypatch) -> None:
    """With no floor left, an empty stack before the end is trailing input:
    the side is dead, and a side that drained AT the end completed."""
    kern = live_kernel("ab")
    monkeypatch.setattr(PdaKernel, "_drive", lambda *_a, **_k: None)
    advance = vars(Sides)["_advance"]
    assert advance(kern, completed_side(1, []), -1) == (None, False)
    done, _sampled = advance(kern, completed_side(2, ["r"]), -1)
    assert done is not None and done[1] == 2 and done[3] == ["r"]


def test_the_recovery_restates_what_the_live_parse_did(monkeypatch) -> None:
    """A fork reads the stack with side-effect-free restatements of what the
    live parse decided, so on every corpus that attempts: each push is the
    clone ``landing`` names, each attempted iteration's frame is one
    ``iterating`` admits, each descent's item is one ``descending`` names, each
    suspended frame is read at an item one of those two names, and each frame a
    sub-run marked is on a clone flagged ``sub_root`` — audit
    roots included."""
    real_enter = next(
        vars(c)["_enter"] for c in PdaKernel.__mro__ if "_enter" in vars(c)
    )
    real_drive = next(
        vars(c)["_drive"] for c in PdaKernel.__mro__ if "_drive" in vars(c)
    )
    real_iteration = Attempting.attempt_iteration
    names = ("pushed", "iterated", "descended", "suspended", "marked", "audits")
    seen = dict.fromkeys(names, 0)

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
        for frame in self.stack[:-1]:
            # `_beyond_class`'s reading of a suspended frame, restated
            at = frame.i
            if at and frame.count == 0 and frame.arm.kinds[at - 1] == OP_REF1:
                at -= 1
            assert at in descending(frame) or (iterating(frame) and at == frame.i)
            seen["suspended"] += 1
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
