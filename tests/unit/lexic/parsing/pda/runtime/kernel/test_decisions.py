"""Tests for lexic.parsing.pda.runtime.kernel.decisions — the attempt/probe
decision half of ``PdaKernel``.

``Attempting``'s methods read the live kernel cursor's state (``pos``,
``stack``, ``_caches``) and are exercised end to end through real parses in
``tests/unit/lexic/parsing/pda/test_group_attempt.py`` and the parity suite;
this file targets the module's cursor-free pure helpers directly: the
per-item/per-clone admission tests, the arm-rest walk, FOLLOW composability,
and the loop-close bookkeeping.
"""

from __future__ import annotations

import pytest

from lexic.parsing.pda.core.charsets import CharSet
from lexic.parsing.pda.core.errors import PdaFail, ProbeFork
from lexic.parsing.pda.runtime.admission import Side
from lexic.parsing.pda.runtime.build import Frame
from lexic.parsing.pda.runtime.kernel import decisions
from lexic.parsing.pda.runtime.kernel.decisions import (
    _ADMITS_HARD,
    _ASCEND,
    _DEAD,
    _arm_rest_scan,
    _composes,
    _item_admits,
)
from lexic.parsing.pda.runtime.kernel.kernel import PdaKernel
from tests.paths import GROUND_TRUTH
from tests.unit.lexic.parsing.pda.compiler.test_clones import only_arm, pda_from_text
from tests.unit.lexic.parsing.pda.runtime.flat_support import flat_arm, flat_clone
from tests.unit.lexic.parsing.pda.runtime.pda_runtime_helpers import compiled_and_pda
from tools.benchmark.cases.corpora import meta_corpus
from tools.benchmark.cases.grammars import BENCHES

MIXED = 'root ::= "a"? mid [0-9]\nmid ::= "m"\n'


def test_item_admits_a_literal_only_its_own_character():
    """A literal item admits only its exact character."""
    pda = pda_from_text(MIXED)
    arm = only_arm(pda.program.start)
    assert _item_admits(arm, 0, "a") is True
    assert _item_admits(arm, 0, "z") is False


def test_item_admits_never_admits_the_empty_string():
    """An empty lookahead character never admits, regardless of item kind."""
    pda = pda_from_text(MIXED)
    arm = only_arm(pda.program.start)
    assert _item_admits(arm, 0, "") is False


def test_item_admits_a_charclass_by_membership():
    """A char class item admits by set membership."""
    pda = pda_from_text(MIXED)
    arm = only_arm(pda.program.start)
    assert _item_admits(arm, 2, "5") is True
    assert _item_admits(arm, 2, "x") is False


def test_item_admits_delegates_a_clone_reference_to_clone_admits():
    """A clone-reference item defers to the target clone's own admission."""
    pda = pda_from_text(MIXED)
    arm = only_arm(pda.program.start)
    assert _item_admits(arm, 1, "m") is True
    assert _item_admits(arm, 1, "z") is False


def test_arm_rest_scan_reports_admits_hard_for_a_mandatory_item():
    """From item 0, item 1 (the mandatory ``mid`` clone) admits ``'m'`` —
    settling the walk before item 2 is even reached."""
    pda = pda_from_text(MIXED)
    arm = only_arm(pda.program.start)
    assert _arm_rest_scan(arm, 0, "m") == (_ADMITS_HARD, False)


def test_arm_rest_scan_reports_dead_when_the_mandatory_item_refuses():
    """A mandatory item refusing the char kills the stop side."""
    pda = pda_from_text(MIXED)
    arm = only_arm(pda.program.start)
    assert _arm_rest_scan(arm, 0, "5") == (_DEAD, False)


def test_arm_rest_scan_ascends_past_the_arms_final_item():
    """Scanning past the arm's own end yields _ASCEND for the enclosing frame."""
    pda = pda_from_text(MIXED)
    arm = only_arm(pda.program.start)
    assert _arm_rest_scan(arm, arm.n - 1, "q") == (_ASCEND, False)


def test_composes_is_true_at_end_of_input():
    """End of input always composes — nothing follows to contradict it."""
    follow = CharSet.from_chars("x")
    assert _composes(follow, "abc", 3) is True


def test_composes_checks_the_next_character_against_follow():
    """A next character inside FOLLOW composes; one outside it does not."""
    follow = CharSet.from_chars("x")
    assert _composes(follow, "axb", 1) is True
    assert _composes(follow, "ayb", 1) is False


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
