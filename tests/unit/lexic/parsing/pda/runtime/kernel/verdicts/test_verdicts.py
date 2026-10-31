"""Tests for lexic.parsing.pda.runtime.kernel.verdicts.verdicts — the boundary verdict
``Attempting`` inherits.

A verdict reads the live cursor, so its seams are driven on real kernels: the
way a live set keeps as the boundary's answer, the split a boundary inside a
reading raises instead, and the rank a meeting of two readings asks, pinned
against what the gated engine answers.
"""

from __future__ import annotations

import pytest

from lexic.ir import IrRuleRef, IrSeq
from lexic.parsing.earley.kernel.forest.forest import ParseTree
from lexic.parsing.earley.kernel.forest.support.ambiguity import ParseConfig
from lexic.parsing.earley.kernel.tables.decider import LEFTMOST_LONGEST, Decider
from lexic.parsing.pda.compiler.program.flatten import FlatArm, FlatClone
from lexic.parsing.pda.compiler.program.opcodes import (
    BUILD_DISPATCH,
    OP_REF,
    OP_REF1,
)
from lexic.parsing.pda.core.errors import PdaFail, ProbeFork
from lexic.parsing.pda.runtime import admission
from lexic.parsing.pda.runtime.admission import Side
from lexic.parsing.pda.runtime.build import Frame
from lexic.parsing.pda.runtime.islands import IslandEnds
from lexic.parsing.pda.runtime.kernel.kernel import PdaKernel, pda_model
from lexic.parsing.pda.runtime.kernel.verdicts import verdicts
from lexic.parsing.pda.runtime.kernel.verdicts.liveset import Split
from lexic.parsing.pda.runtime.kernel.verdicts.sides import (
    PENDING,
    UNSEEN,
    Sides,
)
from lexic.parsing.pda.runtime.kernel.verdicts.verdicts import (
    FORKED,
    STOP_FORCED,
    TAKE,
    Verdicts,
)
from lexic.parsing.pda.runtime.matchers import REST_ADMITS, REST_DEAD
from tests import parity_helpers
from tests.paths import GROUND_TRUTH
from tests.unit.lexic.parsing.parsing_helpers import Shortest
from tests.unit.lexic.parsing.pda.runtime.flat_support import flat_arm, flat_clone
from tests.unit.lexic.parsing.pda.runtime.kernel.verdicts.side_support import (
    NOISE_RUNS,
    SECTIONS,
    completed_side,
    live_kernel,
)
from tests.unit.lexic.parsing.pda.runtime.pda_runtime_helpers import compiled_and_pda


def _raise(why: BaseException) -> None:
    """Raise from inside a lambda, so the patched call stays one expression."""
    raise why


# ── a boundary in the live drive, and one inside a reading ──────────────


@pytest.mark.parametrize(
    ("kept", "verdict"), [(0, STOP_FORCED), (1, TAKE)], ids=["stop-kept", "take-kept"]
)
def test_a_loop_boundary_answers_the_way_its_set_keeps(
    monkeypatch, kept: int, verdict: int
) -> None:
    """The set's two ways are the stop, then the take, stepped ahead first:
    the way it keeps is the verdict."""
    asked: list[tuple[int, bool]] = []

    def deciding(_self, roots, ahead_first):
        asked.append((len(roots), ahead_first))
        return kept

    monkeypatch.setattr(Verdicts, "_decide", deciding)
    fork_verdict = vars(Verdicts)["_fork_verdict"]
    assert fork_verdict(live_kernel(), flat_arm(1), 0, 0, (1, [])) == verdict
    assert asked == [(2, True)]


def test_an_island_a_reading_could_not_settle_forks_plainly(monkeypatch) -> None:
    """An island's ends escaping a set are a fork of THIS boundary: raised as a
    plain :class:`ProbeFork`, so no handler outside reads them as its own
    island's ends."""
    tree = ParseTree(IrRuleRef("isle"), IrSeq())
    two = IslandEnds("isle", 0, ((tree, 1, None), (tree, 2, None)))
    monkeypatch.setattr(Verdicts, "_decide", lambda *_a: _raise(two))
    fork_verdict = vars(Verdicts)["_fork_verdict"]
    with pytest.raises(ProbeFork) as fork:
        fork_verdict(live_kernel(), flat_arm(1), 0, 0, (1, []))
    assert not isinstance(fork.value, IslandEnds) and fork.value.__cause__ is two


def _admitting(text: str) -> FlatArm:
    """A one-item arm whose loop admits ``text``'s first character."""
    return flat_arm(1, gate_data=((None, (frozenset(text[:1]), False)),))


@pytest.mark.parametrize(
    ("rest", "dead", "split"),
    [(REST_ADMITS, False, True), (REST_ADMITS, True, False), (REST_DEAD, False, False)],
    ids=["both-viable", "stop-refuted", "stop-dead-by-class"],
)
@pytest.mark.parametrize("recording", [False, True], ids=["unrecorded", "recording"])
def test_a_boundary_inside_a_reading_splits_rather_than_guessing(
    monkeypatch, rest: int, dead: bool, split: bool, recording: bool
) -> None:
    """Inside a reading a both-viable boundary decides nothing: the reading
    splits into its two ways, built where it stands, the stop first, each
    keeping a ledger exactly where the reading keeps one. Where stopping is
    dead — by class, or refuted against the text — taking is forced, and no
    split is needed."""
    kern = live_kernel()
    monkeypatch.setattr(admission.KernelCaches, "probing", 1)
    monkeypatch.setattr(Verdicts, "_beyond_class", lambda *_a: rest)
    monkeypatch.setattr(Verdicts, "_recording", lambda _self: recording)
    monkeypatch.setattr(verdicts, "stop_side_dead", lambda *_a: dead)
    built: list[tuple[int, int] | None] = []

    def side(_self, _arm, _i, pos, taken, record):
        assert record is recording
        built.append(None if taken is None else (pos, taken[0]))
        return completed_side(pos if taken is None else taken[0], [])

    monkeypatch.setattr(Sides, "_side", side)
    choice = vars(Verdicts)["_attempt_choice"]
    if not split:
        assert choice(kern, _admitting(kern.text), 0, 0, (1, [])) is True
        assert not built
        return
    with pytest.raises(Split) as raised:
        choice(kern, _admitting(kern.text), 0, 0, (1, []))
    assert built == [None, (0, 1)]
    assert [child[1] for child in raised.value.children] == [0, 1]
    assert raised.value.pos == 0


def test_a_pick_its_set_cannot_decide_is_left_to_the_caller(monkeypatch) -> None:
    """Several ways one item can end, as a set: the one it keeps, and
    ``None`` where it forks — the caller hands the item to whoever answers."""
    picks: list[tuple[int, list[object]]] = [(1, ["a"]), (2, ["b"])]
    kept_pick = vars(Verdicts)["_kept_pick"]
    kern = live_kernel()

    def side_of(end: int, values: list[object], _record: bool) -> Side:
        """A pick's way, as a completed side."""
        return completed_side(end, values)

    monkeypatch.setattr(Verdicts, "_decide", lambda *_a: 1)
    assert kept_pick(kern, picks, side_of) == (2, ["b"])
    monkeypatch.setattr(Verdicts, "_decide", lambda *_a: _raise(ProbeFork("tie", 0)))
    assert kept_pick(kern, picks, side_of) is None


_LOOP = flat_clone(attempt=None)
"""The clone a loop item's payload names and the frame above stands in."""


def _dispatching(*targets: FlatClone) -> FlatClone:
    """A dispatch clone selecting ``targets``."""
    return flat_clone(
        BUILD_DISPATCH,
        attempt=None,
        wide_selectors=None,
        default=None,
        selectors=tuple((frozenset("x"), False, target) for target in targets),
    )


def _attempting(*subs: FlatClone) -> FlatClone:
    """An attempt clone running ``subs`` as its entries."""
    return flat_clone(
        attempt=((), tuple((None, False, None, None, sub) for sub in subs))
    )


@pytest.mark.parametrize(
    ("first", "named"),
    [
        (flat_clone(attempt=None), [1]),
        (_dispatching(flat_clone(attempt=None)), [1]),
        (_dispatching(_LOOP), [0, 1]),
        (_dispatching(_dispatching(_LOOP)), [0, 1]),
        (_attempting(flat_clone(attempt=None)), [1]),
        (_attempting(_LOOP), [0, 1]),
        (_LOOP, [0, 1]),
    ],
    ids=[
        "plain",
        "dispatching-elsewhere",
        "dispatching-onto-it",
        "dispatching-onto-it-twice-removed",
        "attempting-elsewhere",
        "attempting-into-it",
        "same-clone",
    ],
)
def test_the_item_that_pushed_the_frame_above_is_named_only_where_certain(
    first, named: list[int]
) -> None:
    """A frame past an exactly-once item with a loop next lists both. The
    frame above stands in the loop's clone, so the loop pushed it — unless
    the other item could also land there: a dispatch that chases to it, an
    attempt whose entry is it, or the same clone named twice. Then both stay.
    An item that can only land elsewhere names the loop."""
    kern = live_kernel()
    below = Frame(flat_arm(2, payloads=(first, _LOOP)), [], flat_clone(), 0)
    kern.stack = [below, Frame(flat_arm(1), [], _LOOP, 0)]
    pushed_by = vars(Verdicts)["_pushed_by"]
    assert pushed_by(kern, 0, [0, 1]) == named


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
        ([10, 3], [10, 5], Shortest(frozenset()), STOP_FORCED),
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
    [(LEFTMOST_LONGEST, TAKE), (Shortest(frozenset()), STOP_FORCED)],
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
        (Shortest(frozenset()), 4, FORKED),
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
        ([10, 2], [10, 5], Shortest(frozenset()), STOP_FORCED),
        ([10, 7], [10, 7], Shortest(frozenset()), STOP_FORCED),
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


@pytest.mark.parametrize("text", [";aaaa!", ";aaa;!"])
def test_a_live_set_rejects_what_no_carving_derives(text: str) -> None:
    """No carving derives the text: the trailing ``!`` opens a section no
    ``end`` closes. The first boundary's readings meet an island with two
    ends, and split again inside it, before every reading dies — each death
    certain, since nothing in a set guesses — so the predictive engine
    rejects the document itself rather than declining it."""
    compiled, product = parity_helpers.built(SECTIONS, "verdicts-sections")
    with pytest.raises(PdaFail) as refusal:
        pda_model(product.pda, text, compiled.product.executor)
    assert not isinstance(refusal.value, ProbeFork), refusal.value
    assert parity_helpers.answers(SECTIONS, "verdicts-sections", text)[1] == (
        parity_helpers.REFUSED
    )


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
    verdict, asked = _open_rank(monkeypatch, Shortest(frozenset()), 20)
    assert verdict == STOP_FORCED
    assert sorted(asked) == list(range(4, 21))


def test_an_open_step_with_many_ends_is_still_answered_on_the_pda(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """However many ends the step can reach, another decider's order is asked
    at each of them and answered here: which carving to keep is the decider's
    question, settled on the predictive engine, never sent to Earley."""
    verdict, asked = _open_rank(monkeypatch, Shortest(frozenset()), 500)
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
