"""Tests for lexic.parsing.pda.runtime.kernel.verdicts.floors — attempt sub-runs
settled where their frames drain back to.

Each member is driven on a real kernel with its collaborators stubbed at the
seam, so a test reads what the floor code itself decides: which stop the drive
takes next, what a settle hands its caller, when a miss asks the island, and
what a catch puts back.
"""

from __future__ import annotations

import pytest

from lexic.exceptions import LexicError
from lexic.ir import IrRuleRef, IrSeq
from lexic.parsing.earley.kernel.forest.forest import ParseTree
from lexic.parsing.pda.core.errors import IslandRefusal, PdaFail, ProbeFork, Suspended
from lexic.parsing.pda.runtime.admission import KernelCaches
from lexic.parsing.pda.runtime.build import Frame
from lexic.parsing.pda.runtime.islands import IslandEnds
from lexic.parsing.pda.runtime.kernel.kernel import PdaKernel
from lexic.parsing.pda.runtime.kernel.verdicts.floors import (
    PENDING,
    UNSEEN,
    Floors,
    pending,
)
from tests.unit.lexic.parsing.pda.runtime.flat_support import flat_arm, flat_clone
from tests.unit.lexic.parsing.pda.runtime.kernel.verdicts.side_support import (
    live_kernel,
)

DRIVE_FLOORS = vars(Floors)["_drive_floors"]
SETTLE_FLOOR = vars(Floors)["_settle_floor"]
MISSED_AT = vars(Floors)["_missed_at"]
CATCH = vars(Floors)["_catch"]
TAKEN = vars(Floors)["_taken"]
RESUME_AUDIT = vars(Floors)["_resume_audit"]
"""The members under test, as the class DEFINES them — reached the way
``test_sides`` reaches its own, so a stub on the kernel never stands in."""


def _frames(n: int) -> list[Frame[object]]:
    """A stack ``n`` frames deep, each a frame of its own."""
    return [Frame(flat_arm(1), [], flat_clone(), 0) for _ in range(n)]


def _kernel(
    monkeypatch, depth: int = 2, pos: int = 0
) -> tuple[PdaKernel, KernelCaches]:
    """A live kernel ``depth`` frames deep at ``pos``, its caches the test's own."""
    kern = live_kernel("abcdefgh")
    kern.stack = _frames(depth)
    kern.pos = pos
    caches: KernelCaches = KernelCaches()
    monkeypatch.setattr(kern, "_caches", caches)
    return kern, caches


def _entry_clone(sub: object) -> object:
    """An attempt clone whose one entry runs ``sub``."""
    return flat_clone(attempt=(None, ((frozenset("a"), False, None, None, sub),)))


def _draining(calls: list[tuple[int, int]], ends: dict[int, int] | None = None):
    """A ``_drive`` that records each call and drains the stack to its floor,
    leaving the cursor where ``ends`` says that floor's frames ended. Past
    32 calls, more than any drive here makes, it raises: a loop fails by name."""

    def drive(self, floor: int = 0, limit: int = -1) -> None:
        if len(calls) >= 32:
            raise AssertionError(f"_drive called more than 32 times: {calls[:8]}")
        calls.append((floor, limit))
        del self.stack[floor:]
        if ends and floor in ends:
            self.pos = ends[floor]

    return drive


def _raise(why: BaseException) -> None:
    """Raise from inside a lambda."""
    raise why


# ── the ledger's sentinels ──────────────────────────────────────────────────


def test_the_sentinels_are_no_position() -> None:
    """A ledger entry is a position or one of the two sentinels, so both must
    be negative and tell apart."""
    assert PENDING < 0 and UNSEEN < 0
    assert PENDING != UNSEEN


@pytest.mark.parametrize(
    ("ledger", "expected"),
    [
        ([], 0),
        ([PENDING, PENDING, PENDING], 3),
        ([PENDING, PENDING, 4, PENDING], 2),
        ([0, PENDING, PENDING], 0),
        ([UNSEEN, PENDING], 0),
        ([PENDING, UNSEEN, PENDING], 1),
    ],
    ids=["empty", "all", "prefix", "none-first", "unseen-first", "unseen-stops"],
)
def test_pending_counts_the_prefix_only(ledger: list[int], expected: int) -> None:
    """Copied frames complete deepest first, so only the leading run of
    ``PENDING`` is still on the stack: a pending entry past a recorded one or
    an unseen one is not counted."""
    assert pending(ledger) == expected


# ── the drive ───────────────────────────────────────────────────────────────


def test_a_drive_with_no_floor_dies_on_its_own_failure(monkeypatch) -> None:
    """With no sub-run to fail instead, a failure is the drive's."""
    kern, _caches = _kernel(monkeypatch)
    monkeypatch.setattr(PdaKernel, "_drive", lambda *_a, **_k: _raise(PdaFail("x", 3)))
    with pytest.raises(PdaFail):
        DRIVE_FLOORS(kern, [], None, -1)


def test_a_drive_with_no_floor_drives_once_to_its_base(monkeypatch) -> None:
    """No stop: one drive down to ``base``, with the limit passed through."""
    kern, _caches = _kernel(monkeypatch, depth=3)
    calls: list[tuple[int, int]] = []
    monkeypatch.setattr(PdaKernel, "_drive", _draining(calls))
    DRIVE_FLOORS(kern, [], None, 7, 1)
    assert calls == [(1, 7)]
    assert len(kern.stack) == 1


def test_a_live_floor_settles_on_its_live_prefix_then_its_holder(monkeypatch) -> None:
    """At its floor the sub-run is settled on what its root derived: the live
    list's prefix first, then the values its root reported, ending where the
    drive left the cursor. Then the drive goes on to the base."""
    kern, _caches = _kernel(monkeypatch, depth=3)
    calls: list[tuple[int, int]] = []
    settled: list[tuple[object, object]] = []
    monkeypatch.setattr(PdaKernel, "_drive", _draining(calls, {1: 5}))
    monkeypatch.setattr(
        PdaKernel, "_settle_floor", lambda _s, floor, got: settled.append((floor, got))
    )
    floor = (1, 2, ["held"], ["live"], None, None)
    floors = [floor]
    DRIVE_FLOORS(kern, floors, None, -1, 0, True)
    assert settled == [(floor, (5, ["live", "held"]))]
    assert calls == [(1, -1), (0, -1)]
    assert not floors


def test_suspended_floors_settle_innermost_first(monkeypatch) -> None:
    """A sub-run that suspends inside the drive leaves its floors innermost
    first; the drive stops at the innermost one and works outwards."""
    kern, _caches = _kernel(monkeypatch, depth=4)
    calls: list[tuple[int, int]] = []
    plain = _draining(calls)
    raised = iter([True])

    def drive(self, floor: int = 0, limit: int = -1) -> None:
        if next(raised, False):
            up = Suspended()
            up.floors.extend([(3, 0, [], [], None, None), (2, 0, [], [], None, None)])
            raise up
        plain(self, floor, limit)

    settled: list[int] = []
    monkeypatch.setattr(PdaKernel, "_drive", drive)
    monkeypatch.setattr(
        PdaKernel, "_settle_floor", lambda _s, floor, _got: settled.append(floor[0])
    )
    DRIVE_FLOORS(kern, [], None, -1, 0, True)
    assert settled == [3, 2]
    assert calls == [(3, -1), (2, -1), (0, -1)]


def test_a_side_ledger_records_an_unreadable_settle_as_unseen(monkeypatch) -> None:
    """A side keeping a ledger stops at each copied depth: a frame drained to
    records where it ended, and a floor whose settle leaves nothing ending at
    the cursor (a closed loop, a replaced entry) is unseen."""
    kern, _caches = _kernel(monkeypatch, depth=2)
    calls: list[tuple[int, int]] = []
    monkeypatch.setattr(PdaKernel, "_drive", _draining(calls, {1: 4, 0: 6}))
    monkeypatch.setattr(PdaKernel, "_settle_floor", lambda *_a: False)
    ledger = [PENDING, PENDING]
    DRIVE_FLOORS(kern, [(1, 0, [], [], None, None)], ledger, -1)
    assert ledger == [6, UNSEEN]
    assert calls == [(1, -1), (0, -1), (0, -1)]


def _side_drive(monkeypatch, floors, ledger, ends: dict[int, int]):
    """A side's drive three frames deep over ``floors`` and ``ledger``, each
    drain ending where ``ends`` says and every floor settling: the drive's
    calls, and each settled floor's depth and start."""
    kern, _caches = _kernel(monkeypatch, depth=3)
    calls: list[tuple[int, int]] = []
    settled: list[tuple[int, int]] = []
    monkeypatch.setattr(PdaKernel, "_drive", _draining(calls, ends))
    monkeypatch.setattr(
        PdaKernel, "_settle_floor", lambda _s, f, _got: settled.append(f[:2]) or True
    )
    DRIVE_FLOORS(kern, floors, ledger, -1)
    return calls, settled


def test_a_side_ledger_settles_both_floors_rooted_at_one_depth(monkeypatch) -> None:
    """An attempted iteration and the entry its payload runs root at one
    depth. A side keeping a ledger settles the inner floor, then the outer at
    the same depth, before it steps out a copied frame — and still records
    every copied frame and settles the floor further out. Stepped out after
    the inner, the outer floor was left behind, deeper than the stack."""
    floors = [(0, 0, [], [], None, None), (2, 0, [], [], None, None)]
    floors.append((2, 1, [], [], None, None))
    ledger = [PENDING, PENDING, PENDING]
    calls, settled = _side_drive(monkeypatch, floors, ledger, {2: 4, 1: 5, 0: 6})
    assert settled == [(2, 1), (2, 0), (0, 0)]
    assert ledger == [6, 5, 4]
    assert calls == [(2, -1), (2, -1), (1, -1), (0, -1), (0, -1)]
    assert not floors


def test_a_side_ledger_steps_out_each_copied_frame_to_a_floor_further_out(
    monkeypatch,
) -> None:
    """With its one floor two copied frames out, a side keeping a ledger stops
    at each copied frame on the way and records where it ended, then settles
    the floor where the drive reaches its depth."""
    floors, ledger = [(0, 0, [], [], None, None)], [PENDING, PENDING, PENDING]
    calls, settled = _side_drive(monkeypatch, floors, ledger, {2: 4, 1: 5, 0: 6})
    assert settled == [(0, 0)]
    assert ledger == [6, 5, 4]
    assert calls == [(2, -1), (1, -1), (0, -1), (0, -1)]


def test_a_side_keeping_no_ledger_stops_only_at_its_floors(monkeypatch) -> None:
    """A side keeping no ledger records nothing, so it stops only where a
    floor stands, the innermost first."""
    floors = [(0, 0, [], [], None, None), (2, 0, [], [], None, None)]
    calls, settled = _side_drive(monkeypatch, floors, None, {2: 4, 0: 6})
    assert settled == [(2, 0), (0, 0)]
    assert calls == [(2, -1), (0, -1), (0, -1)]


def _failing_once(calls: list[tuple[int, int]], why: Exception, ends=None):
    """A ``_drive`` that raises ``why`` on its first call, then drains as
    :func:`_draining` does; every call is recorded."""
    plain = _draining(calls, ends)
    raised = iter([why])

    def drive(self, floor: int = 0, limit: int = -1) -> None:
        failure = next(raised, None)
        if failure is None:
            plain(self, floor, limit)
            return
        calls.append((floor, limit))
        raise failure

    return drive


@pytest.mark.parametrize(
    ("reads", "at_floor"), [(True, 5), (False, UNSEEN)], ids=["reads", "unreadable"]
)
def test_a_failed_sub_run_unseens_its_frames_and_records_its_settle(
    monkeypatch, reads: bool, at_floor: int
) -> None:
    """A failure above a side's floor fails that sub-run, not the side: every
    copied frame from the floor up completed nowhere the ledger can read, the
    floor's own entry is where the settle ends when what it settled on ends at
    the cursor, and the side drives on outward."""
    kern, _caches = _kernel(monkeypatch, depth=3)
    calls: list[tuple[int, int]] = []
    settled: list[object] = []
    monkeypatch.setattr(
        PdaKernel, "_drive", _failing_once(calls, PdaFail("dead", 4), {0: 6})
    )

    def settle(self, floor, got) -> bool:
        settled.append(got)
        assert len(self.stack) == floor[0] and self.pos == floor[1]
        self.pos = 5
        return reads

    monkeypatch.setattr(PdaKernel, "_settle_floor", settle)
    ledger = [PENDING, PENDING, PENDING]
    DRIVE_FLOORS(kern, [(1, 2, [], [], None, None)], ledger, -1)
    assert settled == [None], "a side's miss: no outcome, no island"
    assert ledger == [6, at_floor, UNSEEN]
    assert calls == [(2, -1), (0, -1), (0, -1)]


def test_island_ends_with_a_floor_held_settle_that_floor(monkeypatch) -> None:
    """Ends raised above a live floor are the floor's to settle: an attempted
    iteration they are the whole outcome of takes them, and the drive goes
    on rather than raising them."""
    kern, _caches = _kernel(monkeypatch, depth=3)
    sub = flat_clone()
    loop = Frame(flat_arm(1, payloads=(sub,)), [], flat_clone(), 0)
    calls: list[tuple[int, int]] = []
    settled: list[object] = []
    asked = _asking(monkeypatch, object(), (7, ["stolen"]))
    monkeypatch.setattr(PdaKernel, "_drive", _failing_once(calls, _ends(2, sub)))
    monkeypatch.setattr(PdaKernel, "_iteration_ends", lambda *_a: (5, ["end"]))
    monkeypatch.setattr(
        PdaKernel, "_settle_floor", lambda _s, _floor, got: settled.append(got)
    )
    floors = [(1, 2, [], [], loop, None)]
    DRIVE_FLOORS(kern, floors, None, -1, 0, True)
    assert settled == [(5, ["end"])]
    assert not asked, "ends are no miss: the island is not asked"
    assert not floors
    assert calls == [(1, -1), (0, -1)]


@pytest.mark.parametrize(
    "why",
    [ProbeFork("undecidable", 0), IslandRefusal("two ways")],
    ids=["plain-fork", "island-refusal"],
)
def test_a_fork_or_refusal_with_a_floor_held_is_raised(monkeypatch, why) -> None:
    """Only an island's ends are a floor's to settle: any other fork is the
    gated engine's question, and an island refusing its text as meaning two
    things is no sub-run's miss. Either leaves the drive."""
    kern, _caches = _kernel(monkeypatch, depth=3)
    settled: list[object] = []
    monkeypatch.setattr(PdaKernel, "_drive", _failing_once([], why))
    monkeypatch.setattr(PdaKernel, "_settle_floor", lambda *a: settled.append(a))
    with pytest.raises(type(why)):
        DRIVE_FLOORS(kern, [(1, 2, [], [], None, None)], None, -1, 0, True)
    assert not settled


# ── a settle, as the live caller would ──────────────────────────────────────


def test_a_floor_no_caller_settles_reads_nothing(monkeypatch) -> None:
    """With no loop and no entry, the settle only unwinds to the floor."""
    kern, _caches = _kernel(monkeypatch, depth=3, pos=6)
    assert SETTLE_FLOOR(kern, (1, 2, [], [], None, None), (6, ["v"])) is False
    assert len(kern.stack) == 1
    assert kern.pos == 2


@pytest.mark.parametrize(
    ("got", "lands", "expected"),
    [((5, ["v"]), 5, True), ((5, ["v"]), 3, False), (None, 2, False)],
    ids=["its-own-run-won", "another-entry-won", "missed"],
)
def test_an_attempt_entry_floor_resumes_the_attempt(
    monkeypatch, got, lands: int, expected: bool
) -> None:
    """The attempt resumes from the next entry with ``got`` as the one that
    ran; the ledger may read the cursor only when the entry's own run is what
    the attempt kept."""
    kern, _caches = _kernel(monkeypatch, depth=3, pos=7)
    clone, out = _entry_clone(flat_clone()), ["before"]
    asked: list[tuple[object, ...]] = []

    def attempt(self, *args) -> None:
        asked.append(args)
        self.pos = lands

    monkeypatch.setattr(PdaKernel, "attempt", attempt)
    floor = (1, 2, [], [], None, (clone, out, 0, None, None))
    assert SETTLE_FLOOR(kern, floor, got) is expected
    assert asked == [(clone, out, 0, got)]
    assert len(kern.stack) == 1


@pytest.mark.parametrize(
    ("moved", "expected"), [(True, True), (False, False)], ids=["committed", "closed"]
)
def test_a_loop_floor_commits_or_closes(
    monkeypatch, moved: bool, expected: bool
) -> None:
    """An attempted iteration settles through its frame's own item, from the
    floor's start: an iteration that moved the cursor committed, one that left
    it at the start closed the loop."""
    kern, _caches = _kernel(monkeypatch, depth=3, pos=7)
    loop = Frame(flat_arm(2), [], flat_clone(), 0)
    loop.i = 1
    asked: list[tuple[object, ...]] = []

    def settle(self, *args) -> int:
        asked.append(args)
        start = args[3]
        self.pos = start + 3 if moved else start
        return 0

    monkeypatch.setattr(PdaKernel, "_attempt_settle", settle)
    assert SETTLE_FLOOR(kern, (1, 2, [], [], loop, None), (5, ["v"])) is expected
    assert asked == [(loop, loop.arm, 1, 2, (5, ["v"]))]


def test_an_audited_entry_floor_resumes_its_audit(monkeypatch) -> None:
    """An entry the attempt was auditing resumes the audit, and what the audit
    commits ends at the cursor."""
    kern, _caches = _kernel(monkeypatch, depth=3)
    resumed: list[tuple[object, object]] = []
    monkeypatch.setattr(
        PdaKernel, "_resume_audit", lambda _s, entry, got: resumed.append((entry, got))
    )
    entry = (_entry_clone(flat_clone()), [], 0, (4, ["won"]), None)
    assert SETTLE_FLOOR(kern, (1, 2, [], [], None, entry), None) is True
    assert resumed == [(entry, None)]


def _auditing(monkeypatch, contested: bool) -> dict[str, list[tuple[object, ...]]]:
    """Stub the audit's collaborators; returns the log of what each was asked."""
    log: dict[str, list[tuple[object, ...]]] = {"contest": [], "audit": [], "arm": []}

    def contest(_self, *args) -> bool:
        log["contest"].append(args)
        return contested

    def audit(_self, *args) -> list[tuple[int, list[str]]]:
        log["audit"].append(args)
        return AUDITED

    monkeypatch.setattr(PdaKernel, "_contest", contest)
    monkeypatch.setattr(PdaKernel, "_attempt_audit", audit)
    monkeypatch.setattr(PdaKernel, "_settle_arm", lambda _s, *a: log["arm"].append(a))
    return log


AUDITED = [(9, ["rival"])]
"""What the stubbed audit returns, so the commit can be seen to receive it."""


@pytest.mark.parametrize(
    ("got", "contested", "rivals"),
    [
        ((5, ["got"]), True, [(3, ["r0"]), (5, ["got"])]),
        ((5, ["got"]), False, [(3, ["r0"])]),
        (None, True, [(3, ["r0"])]),
    ],
    ids=["a-rival", "no-rival", "missed"],
)
def test_a_resumed_audit_contests_the_entry_then_commits(
    monkeypatch, got, contested: bool, rivals
) -> None:
    """The entry's outcome is contested against the winner as the audit would
    have contested it, joins the rivals only as a rival, and the rest of the
    audit runs from that entry before the kept arm commits into ``out``."""
    kern, _caches = _kernel(monkeypatch)
    sub = flat_clone()
    clone, out, won = _entry_clone(sub), ["before"], (4, ["won"])
    log = _auditing(monkeypatch, contested)
    RESUME_AUDIT(kern, (clone, out, 0, won, [(3, ["r0"])]), got)
    assert log["contest"] == ([] if got is None else [(sub, won, got, clone)])
    assert log["audit"] == [(clone, 0, won, rivals)]
    assert log["arm"] == [(won, AUDITED, out)]


def test_a_resumed_audit_that_suspends_names_where_its_arm_splices(
    monkeypatch,
) -> None:
    """The commit may suspend an attempt further in; that sub-run's entry was
    recorded with no list to splice into, and the audit names its own."""
    kern, _caches = _kernel(monkeypatch)
    clone, out = _entry_clone(flat_clone()), ["before"]
    _auditing(monkeypatch, False)
    inner = _entry_clone(flat_clone())
    up = Suspended()
    up.floors.append((3, 2, [], [], None, (inner, None, 0, None, None)))
    monkeypatch.setattr(PdaKernel, "_settle_arm", lambda *_a: _raise(up))
    with pytest.raises(Suspended) as raised:
        RESUME_AUDIT(kern, (clone, out, 0, (4, ["won"]), None), None)
    assert raised.value is up
    assert up.floors == [(3, 2, [], [], None, (inner, out, 0, None, None))]


# ── a miss: only the live drive asks the island ─────────────────────────────


def _asking(monkeypatch, island: object, back: object) -> list[tuple[object, ...]]:
    """Stub the island seam; returns the log of what was asked of it."""
    asked: list[tuple[object, ...]] = []

    def stolen_at(_self, depth: int) -> object:
        asked.append(("at", depth))
        return island

    def stolen_back(_self, *args) -> object:
        asked.append(("back", *args))
        return back

    monkeypatch.setattr(PdaKernel, "_stolen_at", stolen_at)
    monkeypatch.setattr(PdaKernel, "_stolen_back", stolen_back)
    return asked


def test_a_live_miss_takes_the_islands_outcome(monkeypatch) -> None:
    """A live sub-run's miss is its outcome, so its rule's island is asked at
    the floor, for the entry's own sub-clone from the sub-run's start."""
    kern, _caches = _kernel(monkeypatch, depth=3, pos=6)
    sub, island = flat_clone(), object()
    asked = _asking(monkeypatch, island, (5, ["stolen"]))
    floor = (1, 2, [], [], None, (_entry_clone(sub), [], 0, None, None))
    assert MISSED_AT(kern, floor, PdaFail("x", 6), True) == (5, ["stolen"])
    assert asked == [("at", 1), ("back", island, 2, sub)]
    assert len(kern.stack) == 1 and kern.pos == 2


def test_a_live_miss_with_no_island_reads_nothing(monkeypatch) -> None:
    """No island at the floor: the caller reads a plain miss."""
    kern, _caches = _kernel(monkeypatch, depth=3)
    asked = _asking(monkeypatch, None, (5, ["never"]))
    assert MISSED_AT(kern, (1, 2, [], [], None, None), PdaFail("x", 0), True) is None
    assert asked == [("at", 1)]


def test_a_sides_miss_never_asks_the_island(monkeypatch) -> None:
    """A side's miss is one reading's death inside a sub-run the live parse
    still runs: asked here, the island would answer for the rule beside the
    reading that took the other way."""
    kern, _caches = _kernel(monkeypatch, depth=3, pos=6)
    asked = _asking(monkeypatch, object(), (5, ["stolen"]))
    floor = (1, 2, [], [], None, (_entry_clone(flat_clone()), [], 0, None, None))
    assert MISSED_AT(kern, floor, PdaFail("x", 6), False) is None
    assert not asked
    assert len(kern.stack) == 1 and kern.pos == 2


def test_a_refusal_never_steals(monkeypatch) -> None:
    """A refusing fold fails the arm, as ``_attempt_run`` reads it, even live."""
    kern, _caches = _kernel(monkeypatch, depth=3)
    asked = _asking(monkeypatch, object(), (5, ["stolen"]))
    floor = (1, 2, [], [], None, (_entry_clone(flat_clone()), [], 0, None, None))
    assert MISSED_AT(kern, floor, LexicError("refused"), True) is None
    assert not asked


def _ends(pos: int, root: object) -> IslandEnds:
    """An island's two ends at ``pos``, claimed for the sub-run of ``root``."""
    tree = ParseTree(IrRuleRef("isl"), IrSeq())
    ends = IslandEnds("isl", pos, ((tree, 1, None), (tree, 2, None)))
    ends.root = root
    return ends


def test_ends_an_iteration_is_the_whole_outcome_of_are_taken(monkeypatch) -> None:
    """Ends claimed for the loop item's own sub-run, at its start, are that
    iteration's outcome — and the island is not asked again."""
    kern, _caches = _kernel(monkeypatch, depth=3)
    sub = flat_clone()
    loop = Frame(flat_arm(1, payloads=(sub,)), [], flat_clone(), 0)
    asked = _asking(monkeypatch, object(), (5, ["stolen"]))
    took: list[tuple[object, ...]] = []

    def iteration_ends(_self, two, arm, i, pos):
        took.append((two, arm, i, pos))
        return 9, ["end"]

    monkeypatch.setattr(PdaKernel, "_iteration_ends", iteration_ends)
    two = _ends(2, sub)
    assert MISSED_AT(kern, (1, 2, [], [], loop, None), two, True) == (9, ["end"])
    assert took == [(two, loop.arm, 0, 2)]
    assert not asked


@pytest.mark.parametrize(
    ("root_is_sub", "at"), [(False, 2), (True, 3)], ids=["other-root", "other-start"]
)
def test_ends_no_iteration_takes_are_raised_on(
    monkeypatch, root_is_sub: bool, at: int
) -> None:
    """Ends that are not the iteration's whole outcome at its start are no
    sub-run's: the floor raises them for the next floor out."""
    kern, _caches = _kernel(monkeypatch, depth=3)
    sub = flat_clone()
    loop = Frame(flat_arm(1, payloads=(sub,)), [], flat_clone(), 0)
    two = _ends(at, sub if root_is_sub else flat_clone())
    with pytest.raises(IslandEnds) as raised:
        MISSED_AT(kern, (1, 2, [], [], loop, None), two, True)
    assert raised.value is two


def test_ends_the_island_raises_reach_an_entry_floor_raised(monkeypatch) -> None:
    """The island's own answer may be two ends; with no attempted iteration to
    take them, they are raised on."""
    kern, _caches = _kernel(monkeypatch, depth=3)
    two = _ends(2, None)
    monkeypatch.setattr(PdaKernel, "_stolen_at", lambda _s, _d: object())
    monkeypatch.setattr(PdaKernel, "_stolen_back", lambda *_a: _raise(two))
    floor = (1, 2, [], [], None, (_entry_clone(flat_clone()), [], 0, None, None))
    with pytest.raises(IslandEnds) as raised:
        MISSED_AT(kern, floor, PdaFail("x", 2), True)
    assert raised.value is two


# ── a catch ─────────────────────────────────────────────────────────────────


def test_a_catch_inside_a_catching_drive_suspends(monkeypatch) -> None:
    """Where a drive below at the same probing level already settles sub-runs,
    this one stays pushed for it: nothing is driven here."""
    kern, caches = _kernel(monkeypatch)
    caches.scope.catching = caches.probing + 1
    calls: list[tuple[int, int]] = []
    monkeypatch.setattr(PdaKernel, "_drive", _draining(calls))
    with pytest.raises(Suspended):
        CATCH(kern, 1)
    assert not calls
    assert caches.scope.catching == 1


def test_a_sides_drive_catches_on_its_own_level(monkeypatch) -> None:
    """A side's drive is a probing level of its own: a catch the live drive
    holds does not make a side's sub-run suspend."""
    kern, caches = _kernel(monkeypatch, depth=3)
    caches.scope.catching = 1
    caches.probing = 1
    seen: list[int] = []
    plain = _draining([])

    def drive(self, floor: int = 0, limit: int = -1) -> None:
        seen.append(caches.scope.catching)
        plain(self, floor, limit)

    monkeypatch.setattr(PdaKernel, "_drive", drive)
    CATCH(kern, 1)
    assert seen == [2]
    assert caches.scope.catching == 1


@pytest.mark.parametrize("fails", [False, True], ids=["returns", "dies"])
def test_a_catch_holds_the_scope_and_puts_it_back(monkeypatch, fails: bool) -> None:
    """The catch marks its level for the drive, drives to its floor, and puts
    the scope back whether the drive returned or died."""
    kern, caches = _kernel(monkeypatch, depth=3)
    seen: list[tuple[int, int]] = []
    plain = _draining([])

    def drive(self, floor: int = 0, limit: int = -1) -> None:
        seen.append((floor, caches.scope.catching))
        if fails:
            raise PdaFail("dead", 0)
        plain(self, floor, limit)

    monkeypatch.setattr(PdaKernel, "_drive", drive)
    if fails:
        with pytest.raises(PdaFail):
            CATCH(kern, 1)
    else:
        CATCH(kern, 1)
        assert len(kern.stack) == 1
    assert seen == [(1, 1)]
    assert caches.scope.catching == 0


def test_a_catch_that_dies_with_floors_held_drops_their_audits(monkeypatch) -> None:
    """A sub-run suspended inside the catch is abandoned with it when the drive
    dies: its audited entry's record goes with it, as its call's would have,
    and an outer record stays."""
    kern, caches = _kernel(monkeypatch, depth=3)
    clone = _entry_clone(flat_clone())
    outer = (0, clone, 1, 0, (3, ["o"]), None)
    caches.audits.extend([outer, (2, clone, 0, 2, (4, ["won"]), None)])
    up = Suspended()
    up.floors.append((2, 2, [], [], None, (clone, [], 0, (4, ["won"]), None)))
    raises = iter([up, ProbeFork("undecidable", 0)])
    monkeypatch.setattr(PdaKernel, "_drive", lambda *_a: _raise(next(raises)))
    with pytest.raises(ProbeFork):
        CATCH(kern, 1)
    assert caches.audits == [outer]
    assert caches.scope.catching == 0


# ── a live floor taken off ──────────────────────────────────────────────────


def test_taking_an_audited_floor_drops_its_own_audit_record(monkeypatch) -> None:
    """An audited entry's call pops its audit record on returning; taking its
    floor off must too — and only the record that is its own."""
    kern, caches = _kernel(monkeypatch)
    clone = _entry_clone(flat_clone())
    entry = (clone, [], 0, (4, ["won"]), None)
    outer = (0, clone, 1, 0, (3, ["o"]), None)
    caches.audits.extend([outer, (1, clone, 0, 2, (4, ["won"]), None)])
    floor = (1, 2, [], [], None, entry)
    floors = [floor]
    assert TAKEN(kern, floors) is floor
    assert not floors
    assert caches.audits == [outer]


@pytest.mark.parametrize(
    "entry_won", [None, (4, ["won"])], ids=["not-audited", "audited-other-record"]
)
def test_taking_a_floor_keeps_records_not_its_own(monkeypatch, entry_won) -> None:
    """A floor not audited, or whose audit record is not the innermost, leaves
    the audit records as they are."""
    kern, caches = _kernel(monkeypatch)
    clone = _entry_clone(flat_clone())
    other = (1, clone, 1, 2, (4, ["won"]), None)
    caches.audits.append(other)
    TAKEN(kern, [(1, 2, [], [], None, (clone, [], 0, entry_won, None))])
    assert caches.audits == [other]
