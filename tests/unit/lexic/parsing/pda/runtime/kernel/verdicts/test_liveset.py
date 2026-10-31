"""Tests for lexic.parsing.pda.runtime.kernel.verdicts.liveset — the readings a
boundary carries forward, pruned, merged and ranked.

A set is driven on a real kernel. Its control flow — which reading steps,
which dies, which two meet — is pinned with the drive stubbed; what a meeting
answers is pinned on readings built by hand; and the set as a whole on real
documents, against the gated engine.
"""

from __future__ import annotations

import pytest

from lexic.exceptions import LexicError
from lexic.ir import IrNamedTuple, IrStr
from lexic.parsing.pda.core.errors import ProbeFork
from lexic.parsing.pda.runtime.admission import Side
from lexic.parsing.pda.runtime.build import Frame
from lexic.parsing.pda.runtime.kernel.kernel import PdaKernel, pda_model
from lexic.parsing.pda.runtime.kernel.verdicts import liveset, sides
from lexic.parsing.pda.runtime.kernel.verdicts.liveset import (
    FORKED,
    STOP_FORCED,
    TAKE,
    Level,
    LiveSet,
    Strand,
)
from lexic.parsing.pda.runtime.kernel.verdicts.sides import UNSEEN, Sides
from lexic.parsing.pda.runtime.kernel.verdicts.verdicts import Verdicts
from tests import parity_helpers
from tests.unit.lexic.parsing.pda.runtime.kernel.verdicts.side_support import (
    ENTRY_AT_THE_START,
    SECTIONS,
    TOP,
    completed_side,
    live_kernel,
    meeting_tally,
)
from tools.benchmark.cases.grammars import BENCHES

VYX_CONVERGES = "!P %P \U000e465b\\n# \\nS:t={y} >\n"
"""A generated vyx packet (seed 221) whose one boundary's two readings meet,
having built values that differ."""


def _vyx():
    """The vyx bench row — the one row whose parses ask boundaries."""
    return next(one for one in BENCHES if one.name == "vyx")


def _raise(why: BaseException) -> None:
    """Raise from inside a lambda, so the patched call stays one expression."""
    raise why


# ── the cost: one stack copy per way, one per split child ──────────────────


def test_a_set_copies_the_stack_once_per_way_and_once_per_split_child(
    monkeypatch,
) -> None:
    """Every reading is one stack copy, made where its way was taken: a set's
    roots, and each split's children. Nothing re-derives a reading — a death
    is pruned, a meeting keeps one of the two, a set the plan answers runs
    nothing — so on the bench row that asks boundaries the copies are exactly
    those, and the row splits at all."""
    counted = {"copies": 0, "ways": 0, "children": 0, "splits": 0}
    copy, settle = sides.frames_copy, vars(LiveSet)["_settled"]
    children = liveset.split_children

    def counting_copy(stack, every_end=False, remap=None):
        counted["copies"] += 1
        return copy(stack, every_end, remap)

    def counting_settle(self, roots, *rest):
        counted["ways"] += len(roots)
        return settle(self, roots, *rest)

    def counting_children(reading, split):
        counted["splits"] += 1
        counted["children"] += len(split.children)
        return children(reading, split)

    monkeypatch.setattr(sides, "frames_copy", counting_copy)
    monkeypatch.setattr(LiveSet, "_settled", counting_settle)
    monkeypatch.setattr(liveset, "split_children", counting_children)
    bench = _vyx()
    bench.compiled.parse(bench.corpus, cores=1)

    assert counted["ways"] and counted["splits"], (
        f"this document no longer splits a reading — it proves nothing: {counted}"
    )
    assert counted["copies"] == counted["ways"] + counted["children"], counted


# ── the set's control flow, on a stubbed drive ─────────────────────────────


def _open(pos: int) -> Side:
    """A reading still open at ``pos``, on a stack of its own."""
    return [Frame(TOP.arm, [], TOP.clone, 0)], pos, None, [], [], [], [TOP], ()


def _stubbed(monkeypatch, dies: list[Side]) -> list[tuple[int, int]]:
    """Readings' drives stubbed: each side in ``dies`` dies on its first
    drive; every other completes at the limit into ``["v"]``. Every open
    stack is a control state of its own, so open readings never meet.
    Returns each drive as ``(from, to)``."""
    drives: list[tuple[int, int]] = []

    def advance(_self, side, limit):
        drives.append((side[1], limit))
        return (
            None if any(side is dead for dead in dies) else completed_side(limit, ["v"])
        )

    monkeypatch.setattr(Sides, "_advance", advance)
    monkeypatch.setattr(liveset, "control_signature", lambda stack, _pos: id(stack))
    return drives


def _decide(kern: PdaKernel, *roots: Side, ahead_first: bool = False) -> int | None:
    """``_decide`` over ``roots`` on ``kern``."""
    builders = [lambda _record, r=r: r for r in roots]
    return vars(LiveSet)["_decide"](kern, builders, ahead_first)


@pytest.mark.parametrize(
    ("dies", "kept", "driven"),
    [([0], 1, 1), ([1], 0, 2), ([0, 1], 1, 1), ([], 1, 2)],
    ids=["stop-dies", "take-dies", "both-would-die", "both-agree"],
)
def test_the_way_whose_readings_survive_is_kept(
    monkeypatch, dies: list[int], kept: int, driven: int
) -> None:
    """Two ways at one position, stepped together, the stop first. A reading
    that dies is pruned, certainly: nothing in a set guesses. The set answers
    as soon as one way is left — the other then needs no drive, whatever it
    would have done — and two that complete alike meet and keep the take."""
    roots = [_open(0), _open(0)]
    drives = _stubbed(monkeypatch, [roots[k] for k in dies])
    assert _decide(live_kernel(), *roots) == kept
    assert drives == [(0, liveset.STEP)] * driven


@pytest.mark.parametrize(
    ("ways", "first"), [([1, 1], 0), ([2, 1], 1)], ids=["even", "smaller-way-first"]
)
def test_a_step_drives_the_smallest_way_first(
    monkeypatch, ways: list[int], first: int
) -> None:
    """Of the readings a step drives, the smallest way's go first: its last
    reading dying decides the set with no other drive."""
    roots = [_open(0) for _ in range(sum(ways))]
    stub = _stubbed(monkeypatch, roots)
    kern = live_kernel()
    readings = [
        Strand(side, (way,), ((),), (Level([], 0, {}),))
        for side, way in zip(roots, [w for w, n in enumerate(ways) for _ in range(n)])
    ]
    survivors = vars(LiveSet)["_driven"](kern, readings, lambda _at: True, 8)
    assert len(stub) == 1 and {reading.path[0] for reading in survivors} == {1 - first}


@pytest.mark.parametrize(
    ("ahead_first", "drives"),
    [(True, [(2, 4)]), (False, [(0, 2), (2, 10)])],
    ids=["ahead-first", "behind-first"],
)
def test_at_a_loop_boundary_the_reading_ahead_steps_first(
    monkeypatch, ahead_first: bool, drives: list[tuple[int, int]]
) -> None:
    """The take, ahead with an iteration the stop has not taken, dies at
    once. Stepped ahead first it dies before the stop is driven at all;
    behind first, the stop is driven to it, and only then on together."""
    stop, take = _open(0), _open(2)
    seen = _stubbed(monkeypatch, [take])
    assert _decide(live_kernel(), stop, take, ahead_first=ahead_first) == 0
    assert seen == drives


def test_a_refusal_in_a_readings_drive_is_its_own_death(monkeypatch) -> None:
    """A reading's drive builds its own values, so a refusal there is a
    verdict about that reading alone: it dies — not a fork — and the other
    way is kept."""
    kern = live_kernel()
    drive = vars(PdaKernel)["_drive"]
    stop, take = _open(0), _open(1)

    def refusing(self, floor=0, limit=-1):
        if self.stack is stop[0]:
            raise LexicError("refused on the stop reading's own values")
        return drive(self, floor, limit)

    advance = vars(Sides)["_advance"]
    monkeypatch.setattr(PdaKernel, "_drive", refusing)
    monkeypatch.setattr(
        Sides,
        "_advance",
        lambda self, side, limit: side if side is take else advance(self, side, limit),
    )
    monkeypatch.setattr(liveset, "control_signature", lambda stack, _pos: id(stack))
    assert _decide(kern, stop, take) == 1


@pytest.mark.parametrize(
    ("one", "other", "meet"),
    [
        (completed_side(3, []), completed_side(3, ["x"]), True),
        (completed_side(3, []), _open(3), False),
        (_open(3), _open(3)[:4] + ([None],) + _open(3)[5:], False),
    ],
    ids=["both-completed", "completed-and-open", "other-sub-runs"],
)
def test_readings_meet_only_where_they_share_a_future(
    monkeypatch, one: Side, other: Side, meet: bool
) -> None:
    """A completed reading meets only another completed one at its position;
    open ones meet in one control state inside the same sub-runs — one still
    inside a floor settles it on the way, the other does not."""
    monkeypatch.setattr(liveset, "control_signature", lambda _stack, pos: pos)
    assert (liveset.meeting(one) == liveset.meeting(other)) is meet


# ── the bounds: each a fork that names itself ──────────────────────────────


def _forks_on_sections(monkeypatch) -> list[str]:
    """Reject-or-fork ``;aaaa!`` under SECTIONS on the PDA; every fork a set
    raised, by its words."""
    raised: list[str] = []
    decide = vars(LiveSet)["_decide"]

    def recording(self, roots, ahead_first):
        try:
            return decide(self, roots, ahead_first)
        except ProbeFork as fork:
            raised.append(str(fork))
            raise

    monkeypatch.setattr(LiveSet, "_decide", recording)
    compiled, product = parity_helpers.built(SECTIONS, "liveset-sections")
    with pytest.raises(ProbeFork):
        pda_model(product.pda, ";aaaa!", compiled.product.executor)
    return raised


@pytest.mark.parametrize(
    ("bound", "value", "words"),
    [
        ("SET_MAX", 2, "readings exceed 2"),
        ("SET_STEPS", 1, "undecided after 1 steps"),
        ("NESTING_DEPTH", 0, "split 0 times"),
    ],
    ids=["readings", "steps", "split-depth"],
)
def test_a_set_past_its_bound_forks_by_name(
    monkeypatch, bound: str, value: int, words: str
) -> None:
    """The document the set rejects within its bounds forks past any one of
    them — the one place a boundary is left undecided — and the fork says
    which bound it met, for the gated engine to answer."""
    monkeypatch.setattr(liveset, bound, value)
    raised = _forks_on_sections(monkeypatch)
    assert any(words in fork for fork in raised), raised


# ── meetings, on real documents ─────────────────────────────────────────────


def test_readings_that_meet_with_equal_values_merge_unranked(monkeypatch) -> None:
    """Two readings at one position, in one control state, inside the same
    sub-runs, that built the same values since their split share their whole
    future: one is kept, the take, and the rank is never asked.

    The vyx packet's readings meet with values that DIFFER, so they are made
    to agree at the one site that reads them."""
    monkeypatch.setattr(liveset, "pending_values", lambda _stack, _shape: ())
    tally = meeting_tally(_vyx().compiled, VYX_CONVERGES, monkeypatch)
    assert tally["meetings"] == 1, f"no longer meets — witnesses nothing: {tally}"
    assert (tally["agree"], tally["took"]) == (1, 1), tally
    assert (tally["ranked"], tally["tie"], tally["drove"]) == (0, 0, 0), tally


def test_readings_that_meet_with_different_values_are_ranked_there(
    monkeypatch,
) -> None:
    """Values DIFFER, which is the question the boundary asks: the decider's
    rank answers it at the meeting. Nothing past the meeting is driven first
    — the two share it, so a death there would be both readings', and the
    parse's, whichever was kept."""
    tally = meeting_tally(_vyx().compiled, VYX_CONVERGES, monkeypatch)
    assert tally["ranked"] == 1, f"no longer meets — witnesses nothing: {tally}"
    assert (tally["agree"], tally["tie"], tally["drove"]) == (0, 0, 0), tally


REOPENING = (
    'root ::= arr\narr ::= "[" pair ("," pair)* "]"\n'
    'pair ::= "(" num ")" "," "(" num ")" | "(" num ")"\nnum ::= [0-9]+\n'
)
"""Pairs that reopen: every set's readings complete and meet, and are ranked."""


@pytest.mark.parametrize(
    ("source", "key", "text", "ranked"),
    [
        (None, "", VYX_CONVERGES, 1),
        (
            REOPENING,
            "liveset-reopening",
            "[" + ",".join(f"({k})" for k in range(8)) + "]",
            4,
        ),
    ],
    ids=["one-set", "every-set"],
)
def test_a_set_keeps_ledgers_only_once_a_meeting_needs_a_rank(
    monkeypatch, source: str | None, key: str, text: str, ranked: int
) -> None:
    """A set runs first keeping no ledgers. The first meeting that needs a
    rank finds none, and its set starts over keeping them; every later set of
    the parse keeps them from the start, so that restart happens once a parse
    however many sets rank."""
    compiled = (
        _vyx().compiled if source is None else parity_helpers.built(source, key)[0]
    )
    tally = meeting_tally(compiled, text, monkeypatch)
    assert tally["unrecorded"] == 1, tally
    assert tally["ranked"] >= ranked, tally


@pytest.mark.parametrize(("verdict", "took"), [(STOP_FORCED, 0), (TAKE, 1)])
def test_a_meeting_keeps_the_reading_its_rank_keeps(
    monkeypatch, verdict: int, took: int
) -> None:
    """Whatever the rank answers is what the meeting keeps — the stop, or
    the take — rather than anything the meeting settles itself."""
    monkeypatch.setattr(Verdicts, "_rank", lambda *_a: verdict)
    tally = meeting_tally(_vyx().compiled, VYX_CONVERGES, monkeypatch)
    assert (tally["ranked"], tally["took"]) == (1, took), tally


# ── meetings, on readings built by hand ─────────────────────────────────────


class _Left(IrNamedTuple[IrStr]):
    """One record class."""

    w: IrStr


class _Right(IrNamedTuple[IrStr]):
    """Another, with the same field and the same value."""

    w: IrStr


_ROOT = Level([], 0, {})
"""The set's own split, on the empty stack a hand-built reading's rank reads."""


def _done(path: tuple[int, ...], root: list[object], *levels: Level) -> Strand:
    """A reading that completed into ``root`` along ``path``."""
    levels = levels or (_ROOT,) * len(path)
    return Strand(completed_side(5, root), path, ((),) * len(path), levels)


def _met(kern: PdaKernel, one: Strand, other: Strand) -> Strand:
    """``_met`` as the set asks it."""
    return vars(LiveSet)["_met"](kern, one, other)


def _ranking(monkeypatch, verdict: int) -> list[int]:
    """``_rank`` answering ``verdict``; the positions it was asked at."""
    asked: list[int] = []

    def rank(self, _stop, _take):
        asked.append(self.pos)
        return verdict

    monkeypatch.setattr(Verdicts, "_rank", rank)
    return asked


def test_readings_whose_records_differ_in_class_are_ranked(monkeypatch) -> None:
    """``_Left('x')`` and ``_Right('x')`` are two meanings with one field
    tuple: read apart, the rank decides; one record class twice merges."""
    kern = live_kernel()
    asked = _ranking(monkeypatch, STOP_FORCED)
    stop, take = _done((0,), [_Left(IrStr("x"))]), _done((1,), [_Right(IrStr("x"))])
    assert _met(kern, take, stop) is stop
    assert asked == [0]
    same = _done((1,), [_Left(IrStr("x"))])
    assert _met(kern, stop, same) is same
    assert asked == [0]


@pytest.mark.parametrize(
    ("root", "verdict", "kept"),
    [
        (["xy"], STOP_FORCED, "stop"),
        (["xy"], TAKE, "take"),
        (["x", "y"], FORKED, "take"),
    ],
    ids=["ranked-stop", "ranked-take", "equal-unranked"],
)
def test_completed_readings_meet_on_their_roots(
    monkeypatch, root: list[object], verdict: int, kept: str
) -> None:
    """Two completed readings hold empty stacks; what they built is in their
    roots. Roots that differ are ranked; equal ones keep the take, the rank
    unasked — a tie it would answer included."""
    kern = live_kernel()
    asked = _ranking(monkeypatch, verdict)
    stop, take = _done((0,), ["x", "y"]), _done((1,), root)
    assert _met(kern, stop, take) is (stop if kept == "stop" else take)
    assert len(asked) == (root != ["x", "y"])


def test_a_tie_the_decider_does_not_separate_forks_by_name(monkeypatch) -> None:
    """Different values the rank cannot separate are the ambiguity they are:
    the meeting raises a fork that says so, and the gated engine answers."""
    _ranking(monkeypatch, FORKED)
    with pytest.raises(ProbeFork, match="does not separate"):
        _met(live_kernel(), _done((0,), ["x", "y"]), _done((1,), ["xy"]))


_ROLLED = Level([TOP], 0, {0: (UNSEEN, TOP)})
"""A split both readings rolled back: its one frame unreadable on both."""


@pytest.mark.parametrize(
    ("there", "asked"), [(3, [3]), (4, None)], ids=["same-split", "other-split"]
)
def test_a_split_both_readings_rolled_back_is_passed_over(
    monkeypatch, there: int, asked: list[int] | None
) -> None:
    """Readings that parted at a split whose frames both dropped stand in one
    state after it: that choice decided nothing, so the next split they part
    at is ranked — if it is the same split on both, at one position in one
    control state; otherwise nothing can rank them, and they fork."""
    kern = live_kernel()
    seen = _ranking(monkeypatch, TAKE)
    stop = _done((0, 0), ["x", "y"], _ROLLED, Level([], 3, {}))
    take = _done((1, 1), ["xy"], _ROLLED, Level([], there, {}))
    if asked is None:
        with pytest.raises(ProbeFork, match="cannot be ranked"):
            _met(kern, stop, take)
        return
    assert _met(kern, stop, take) is take
    assert seen == asked


def test_a_rolled_back_split_is_passed_over_on_a_real_document(monkeypatch) -> None:
    """``root ::= a | b``: the set's boundary sits in entry ``a``, which fails
    at ``.`` on every reading and is replaced by ``b``, where the readings
    split again. Ranking at the first split would read only ``a``'s dropped
    frames; ranked where they part inside ``b``, the predictive engine
    answers with the gated engine's model."""
    passed: list[tuple[int, int]] = []
    ranked_level = liveset.ranked_level

    def recording(one, other, first):
        at = ranked_level(one, other, first)
        passed.append((first, at))
        return at

    monkeypatch.setattr(liveset, "ranked_level", recording)
    predictive, gated = parity_helpers.answers(
        ENTRY_AT_THE_START, "liveset-entry-start", "x #a\nx."
    )
    assert any(at > first for first, at in passed), passed
    assert predictive == gated != parity_helpers.DECLINED


# ── the plan: what a decided set already knows of the boundaries ahead ──────


def _through(path: tuple[int, ...], keys: tuple[str, ...]) -> Strand:
    """A reading along ``path`` through splits keyed ``keys``, the set's own first."""
    levels = tuple(Level([], 0, {}, (key,)) for key in keys)
    return Strand(completed_side(5, []), path, ((),) * len(path), levels)


@pytest.mark.parametrize(
    ("survivors", "plan"),
    [
        ([(1, 0, 1)], [("b", 0), ("c", 1)]),
        ([(1, 0, 1), (1, 0, 1)], [("b", 0), ("c", 1)]),
        ([(1, 0, 1), (1, 0, 0)], [("b", 0)]),
        ([(1, 0, 1), (1, 1, 1)], []),
        ([(1, 0, 1), (1,)], []),
    ],
    ids=["one", "agreeing", "parting-later", "parting-at-once", "one-not-there-yet"],
)
def test_a_decided_sets_survivors_plan_the_boundaries_ahead(
    survivors: list[tuple[int, ...]], plan: list[tuple[str, int]]
) -> None:
    """Past the set's own split, each split every survivor came through the
    same way is planned, in order, until one parts or has not reached it."""
    keys = ("a", "b", "c")
    readings = [_through(path, keys[: len(path)]) for path in survivors]
    assert liveset.planned(readings) == [((key,), way) for key, way in reversed(plan)]


def test_the_live_drive_takes_the_planned_answers_without_a_drive(monkeypatch) -> None:
    """On vyx the first boundary's set splits at the next two boundaries; one
    of them is planned, and the live drive's set there answers with no drive
    and the same way a set would keep. A plan whose key does not match the
    boundary asked is dropped, and that set runs."""
    asked: list[int] = []
    settle, decide = vars(LiveSet)["_settled"], vars(LiveSet)["_decide"]

    def counting_settle(self, *args):
        asked.append(self.pos)
        return settle(self, *args)

    answered: list[int] = []

    def recording(self, roots, ahead_first):
        kept = decide(self, roots, ahead_first)
        answered.append(kept)
        return kept

    monkeypatch.setattr(LiveSet, "_settled", counting_settle)
    monkeypatch.setattr(LiveSet, "_decide", recording)
    bench = _vyx()
    planned_model = bench.compiled.parse(bench.corpus, cores=1)
    assert len(answered) > len(asked), "no boundary was answered from a plan"
    made = [0]
    real_planned = liveset.planned

    def counting_plans(survivors):
        plan = real_planned(survivors)
        made[0] += bool(plan)
        return plan

    unique = iter(range(10**9))
    monkeypatch.setattr(liveset, "planned", counting_plans)
    monkeypatch.setattr(liveset, "control_signature", lambda *_a: (next(unique),))
    asked.clear()
    answered.clear()
    assert bench.compiled.parse(bench.corpus, cores=1) == planned_model
    assert made[0], "no plan was made, so none could be dropped"
    assert len(asked) == len(answered), "a plan that does not match is dropped"


def test_the_reading_ahead_leads_one_step_then_waits(monkeypatch) -> None:
    """At a loop boundary the take steps ahead once, to die early if it will;
    after that the readings behind catch up first. On vyx the take splits at
    its first boundary when it leads; led again it would split at the next
    too, before the stop's death decides the set — so each parse splits
    once."""
    splits = [0]
    children = liveset.split_children

    def counting(reading, split):
        splits[0] += 1
        return children(reading, split)

    monkeypatch.setattr(liveset, "split_children", counting)
    bench = _vyx()
    bench.compiled.parse(bench.corpus, cores=1)
    assert splits[0] == 1, splits
