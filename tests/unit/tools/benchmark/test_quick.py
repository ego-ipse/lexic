"""Tests for the local tier — its budget, its priority rule and its promise.

Three things are this tier's whole contract. The rows come from the diff, so a
run never measures what the change cannot reach and never quietly measures less
than it selected. The budget is pairs, stated before anything starts, and a row
it cannot afford is REPORTED rather than dropped. And no row is ever left
saying nothing: an unresolved row carries the count that would settle it, which
is the difference between "cannot tell" and "not at this budget".

The words are the gate's, deliberately, because the rule is the gate's. What is
tested here is that they stay the gate's — a tier that invented a softer word
for `slower` would be a second gate wearing a disguise.
"""

from __future__ import annotations

import ast
import math
from pathlib import Path

import pytest

from tools.benchmark import compare, quick
from tools.benchmark.cases.grammars import BENCHES
from tools.benchmark.execution.isolation import Job
from tools.benchmark.measurement.contract import (
    CLOCKS,
    PROTOCOL,
    Observation,
    RowContract,
    RowResult,
)

BASE = Path("/tmp/base")
HEAD = Path("/tmp/head")

CONTRACT = RowContract(
    PROTOCOL,
    "lexic-pda",
    "json",
    "abc123",
    (),
    (),
    "def456",
    2403,
    "corpus",
    "typed model",
    1,
    True,
    CLOCKS,
)
"""One row contract, identical on both arms, so every pair is comparable."""

OBSERVED = Observation(1.0, 1.0, "text", "shape", "accepted", None, "plan", 1)
"""One observation; the tests overwrite the two clocks and keep the rest."""

ROSTER = (
    ("csv", "lexic-pda"),
    ("csv", "lexic-mt"),
    ("json", "lexic-pda"),
    ("json", "lexic-lex"),
    ("json", "lexic-mt"),
    ("json", "lexic-earley"),
    ("vyx", "lexic-pda"),
)
"""A small roster with both schedules in it, claimed by both trees."""

PDA_REACH = frozenset({"lexic-pda", "lexic-lex", "lexic-mt"})
"""What a change under the predictive runtime reaches, within this roster."""


def _pairing(candidate: list[float], control: list[float]) -> compare.Pairing:
    """A row's paired log ratios; the slot readings follow the control's."""
    return compare.Pairing(tuple(candidate), tuple(control), tuple(control))


def _result(reading: float) -> RowResult:
    """One worker's whole answer at a given reading on both clocks."""
    return RowResult(CONTRACT, (OBSERVED._replace(wall=reading, cpu=reading),), None)


def _unresolved(row: str = "g/r", pairs: int = 6) -> quick.Reading:
    """A row the gate genuinely cannot settle — one real row's statistics.

    Built from the numbers an actual unresolved roster row produced, because a
    hand-picked pair of lists is easy to get accidentally decidable and a test
    that thinks it is exercising the unresolved path while exercising ``ok``
    proves nothing.
    """
    pairing = _spread_pairing(0.0249, 0.0302, 0.0012, 0.0253, pairs)
    verdict = compare.decide(row, pairing, "cpu")
    assert verdict.status == "unresolved", verdict
    return quick.Reading(verdict, pairing, None)


def _reading(row: str, candidate: list[float], control: list[float]) -> quick.Reading:
    """One judged row, built from stated log ratios."""
    pairing = _pairing(candidate, control)
    return quick.Reading(compare.decide(row, pairing, "cpu"), pairing, None)


def _spread_pairing(
    mean: float, sigma: float, control_mean: float, control_sigma: float, pairs: int
) -> compare.Pairing:
    """A pairing whose sample mean and sample deviation ARE the ones asked for.

    Built rather than drawn, so a projection test states its own inputs instead
    of depending on a generator's luck. The half-step is scaled by
    ``sqrt((n-1)/n)`` because the sample deviation divides by ``n - 1``.
    """

    def arm(centre: float, deviation: float) -> tuple[float, ...]:
        half = deviation * math.sqrt((pairs - 1) / pairs)
        return tuple(
            centre + (half if index % 2 == 0 else -half) for index in range(pairs)
        )

    return compare.Pairing(
        arm(mean, sigma), arm(control_mean, control_sigma), (0.0,) * pairs
    )


def _one(_job: Job) -> RowResult:
    """Every worker reads exactly the same, on both arms."""
    return _result(1.0)


def _both_trees_claim(_base: Path, _head: Path) -> tuple[tuple[str, str], ...]:
    """Both trees claim the same small roster."""
    return ROSTER


def _stub_digest(_root: Path) -> str:
    """A benchmark digest for a tree that is not on disk."""
    return "0000000000000000"


def _reaches_the_pda(_paths) -> frozenset[str]:
    """Stand in for the diff: a change under the predictive runtime."""
    return PDA_REACH


def _one_changed_path(_base: str, _root: Path) -> tuple[str, ...]:
    """Stand in for git: one file changed."""
    return ("src/lexic/parsing/pda/runtime/admission.py",)


def _quiet_run(monkeypatch: pytest.MonkeyPatch) -> None:
    """Wire main() to a roster and a worker that need no disk and no git."""
    monkeypatch.setattr(quick, "rosters", _both_trees_claim)
    monkeypatch.setattr(quick, "digest", _stub_digest)
    monkeypatch.setattr(quick, "changed_paths", _one_changed_path)
    monkeypatch.setattr(quick, "seats_for", _reaches_the_pda)
    monkeypatch.setattr(compare, "run_job", _one)


# ---------------------------------------------------------------- the words

GATE_WORDS = frozenset({"ok", "slower", "faster", "unresolved"})
"""What the gate says — and what this tier says, because the rule is the gate's."""


def test_every_verdict_this_tier_publishes_is_spelled_the_gate_s_way() -> None:
    """The tier judges by the gate's rule, so it must not invent a vocabulary.

    An earlier tier deliberately spelled its outcomes differently, because it
    decided on a DIFFERENT rule and a reader had to be unable to mistake the
    two. This one uses ``decide`` itself, so the opposite is now true: a word
    of its own would claim a distinction that no longer exists.
    """
    for candidate, control in (
        ([0.1] * 6, [0.0] * 6),
        ([-0.1] * 6, [0.0] * 6),
        ([0.001] * 6, [0.05, -0.05] * 3),
        ([0.0] * 6, [0.0] * 6),
    ):
        verdict = compare.decide("g/r", _pairing(candidate, control), "cpu")
        assert verdict.status in GATE_WORDS


def test_no_preliminary_vocabulary_survives_in_the_module() -> None:
    """The old tier's words are gone, not merely unused.

    They described a weaker rule. Leaving one spelled anywhere in the file
    would let a reader think this tier still hedges, and would let a future
    edit reach for it.
    """
    text = Path(quick.__file__).read_text(encoding="utf-8")
    for word in ("PRELIMINARY", "leans-slower", "leans-faster", "inconclusive"):
        assert word not in text, word


def test_a_slower_row_fails_the_run() -> None:
    """The one verdict that is a decision rather than a reading."""
    slower = _reading("g/r", [0.2] * 6, [0.0] * 6)
    assert slower.verdict.status == "slower"
    assert quick.exit_code([slower]) == 1


def test_an_unresolved_row_never_fails_the_run() -> None:
    """It measured no slowdown — only that this host could not separate them.

    Failing on it would make the answer depend on how quiet the machine was,
    and the only move that leaves is to rerun until the noise cooperates.
    """
    assert quick.exit_code([_unresolved()]) == 0


def test_a_run_with_nothing_slower_passes() -> None:
    """Every other outcome is a reading, and a reading does not block."""
    assert quick.exit_code([_reading("g/r", [0.0] * 6, [0.0] * 6)]) == 0


# --------------------------------------------------------------- the budget


def test_the_floor_cost_is_the_gate_s_minimum_for_every_selected_row() -> None:
    """Below the gate's floor nothing is decided, so that IS the price."""
    assert quick.floor_cost(ROSTER) == compare.MIN_PAIRS * len(ROSTER)
    assert quick.floor_cost(()) == 0


def test_the_selection_s_cost_is_printed_before_any_process_starts(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A caller declines a long run only if told before it begins."""
    order: list[str] = []

    def run(job: Job) -> RowResult:
        order.append(job.label)
        return _result(1.0)

    _quiet_run(monkeypatch)
    monkeypatch.setattr(compare, "run_job", run)
    quick.main(["--base-root", str(BASE), "--grammars", "json"])

    printed = capsys.readouterr().out
    assert f"pairs to measure them all at the gate's floor of {compare.MIN_PAIRS}" in (
        printed
    )
    assert printed.index("row(s) selected") < printed.index("json/lexic")
    assert order


def test_the_default_budget_is_exactly_the_floor_cost(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A default run measures every selected row at the gate's own minimum."""
    _quiet_run(monkeypatch)
    quick.main(["--base-root", str(BASE), "--grammars", "json"])

    printed = capsys.readouterr().out
    rows = [row for row in ROSTER if row[0] == "json" and row[1] in PDA_REACH]
    sequential = [row for row in rows if row[1] not in compare.MT_ROWS]
    assert f"budget {quick.floor_cost(sequential)} pairs" in printed
    assert "not measured" not in printed


def test_a_budget_below_the_floor_reports_the_rows_it_could_not_afford(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The failure this tool must never have is a silent omission.

    A row missing from the table reads as a row that did not matter, and the
    whole point of deriving the selection from the diff is that every row in it
    matters. So an unaffordable row is printed with zero pairs and the reason.
    """
    _quiet_run(monkeypatch)
    quick.main(["--base-root", str(BASE), "--budget", str(compare.MIN_PAIRS)])

    printed = capsys.readouterr().out
    assert "selected row(s) not measured" in printed
    assert f"0 pairs — {quick.NO_BUDGET}" in printed


def test_a_budget_of_zero_measures_nothing_and_says_so(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Zero is a real budget, and its run is a list of what it could not do."""
    _quiet_run(monkeypatch)
    assert quick.main(["--base-root", str(BASE), "--budget", "0"]) == 0

    printed = capsys.readouterr().out
    assert "0 pairs" in printed
    assert "selected row(s) not measured" in printed


def test_the_floor_funds_rows_in_roster_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Deterministic, not cheapest-first.

    Cheapest-first would measure more rows per second, and make WHICH rows a
    run covers depend on how fast the host happened to be that morning. A
    reader comparing two runs needs the same rows in both.
    """
    monkeypatch.setattr(compare, "run_job", _one)
    rows = (("csv", "lexic-pda"), ("json", "lexic-pda"), ("vyx", "lexic-pda"))
    readings, unfunded, left = quick.fund_floor(
        compare.Arms(BASE, HEAD, 4), rows, 2 * compare.MIN_PAIRS, 1
    )

    assert {r.verdict.row for r in readings} == {"csv/lexic-pda", "json/lexic-pda"}
    assert [row.row for row in unfunded] == ["vyx/lexic-pda"]
    assert left == 0


def test_the_floor_never_measures_a_row_at_less_than_the_gate_s_minimum(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A row measured at less could not be judged at all, so it is not judged."""
    monkeypatch.setattr(compare, "run_job", _one)
    readings, unfunded, left = quick.fund_floor(
        compare.Arms(BASE, HEAD, 4),
        (("json", "lexic-pda"),),
        compare.MIN_PAIRS - 1,
        1,
    )

    assert not readings
    assert len(unfunded) == 1
    assert left == compare.MIN_PAIRS - 1


# ------------------------------------------------------- where spare pairs go


def test_the_spare_budget_queues_the_rows_furthest_from_one_first() -> None:
    """The row most likely to be a regression is the one that looks most like one."""
    near, middle, far = (_unresolved(name) for name in ("g/near", "g/middle", "g/far"))
    near = near._replace(verdict=near.verdict._replace(ratio=1.005))
    middle = middle._replace(verdict=middle.verdict._replace(ratio=0.97))
    far = far._replace(verdict=far.verdict._replace(ratio=1.06))

    queued = quick.growth_order([near, far, middle])
    assert [r.verdict.row for r in queued] == ["g/far", "g/middle", "g/near"]


def test_a_settled_row_never_takes_a_pair_of_the_spare_budget() -> None:
    """Growth is for rows that have not answered; the rest have."""
    settled = _reading("g/ok", [0.0] * 6, [0.0] * 6)
    assert settled.verdict.status != "unresolved"
    assert not quick.growth_order([settled])


def test_a_row_whose_projection_fits_the_budget_is_grown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Spare pairs go where they buy an answer."""
    grew: list[int] = []

    def grow(_arms, reading: quick.Reading, pairs: int) -> quick.Reading:
        grew.append(pairs)
        return _reading(reading.verdict.row, [0.2] * 16, [0.0] * 16)

    monkeypatch.setattr(quick, "extend", grow)
    monkeypatch.setattr(quick, "separation", lambda _pairing: 10)

    readings, left = quick.fund_growth(compare.Arms(BASE, HEAD, 4), [_unresolved()], 20)
    assert grew == [10 - compare.MIN_PAIRS]
    assert left == 20 - (10 - compare.MIN_PAIRS)
    assert readings[0].verdict.status == "slower"


def test_a_row_needing_more_than_the_budget_keeps_its_projection_instead(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The whole difference between "cannot tell" and "not at this budget".

    Funding a row that cannot separate inside what remains spends the budget
    the other rows needed and still answers nothing — which is the behaviour
    this tier was rebuilt to stop.
    """

    def refuse(_arms, _reading, _pairs):
        raise AssertionError("grew a row the budget cannot settle")

    monkeypatch.setattr(quick, "extend", refuse)
    monkeypatch.setattr(quick, "separation", lambda _pairing: 40)

    readings, left = quick.fund_growth(compare.Arms(BASE, HEAD, 4), [_unresolved()], 4)
    assert left == 4
    assert readings[0].projection == 40
    assert readings[0].verdict.status == "unresolved"


def test_growth_never_takes_a_row_past_the_gate_s_own_ceiling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Above the ceiling the gate declares the evidence unresolved rather than
    forcing it into a median; a cheaper tier may not spend more than that."""
    grew: list[int] = []

    def grow(_arms, reading: quick.Reading, pairs: int) -> quick.Reading:
        grew.append(pairs)
        return reading

    monkeypatch.setattr(quick, "extend", grow)
    monkeypatch.setattr(quick, "separation", lambda _pairing: 300)

    quick.fund_growth(compare.Arms(BASE, HEAD, 4), [_unresolved()], 1000)
    assert grew == [compare.MAX_PAIRS - compare.MIN_PAIRS]


def test_every_row_keeps_its_place_in_the_table_after_growth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Funding order is not reporting order; a reader compares runs by row."""
    monkeypatch.setattr(quick, "separation", lambda _pairing: None)
    rows = [
        _reading("g/a", [0.0] * 6, [0.0] * 6),
        _unresolved("g/b"),
        _reading("g/c", [0.0] * 6, [0.0] * 6),
    ]
    readings, _left = quick.fund_growth(compare.Arms(BASE, HEAD, 4), rows, 100)
    assert [r.verdict.row for r in readings] == ["g/a", "g/b", "g/c"]


# ----------------------------------------------------- no row says nothing


def test_an_unresolved_row_is_reported_with_what_would_settle_it(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The sentence this tier exists to replace "cannot tell" with."""
    quick.report_projections([_unresolved()._replace(projection=42)])
    assert "about 42 pairs would settle it" in capsys.readouterr().out


def test_a_row_no_count_can_separate_says_that_instead(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The tie: the candidate's mean sits exactly on the control's own band."""
    quick.report_projections([_unresolved()._replace(projection=None)])
    assert "no pair count separates it" in capsys.readouterr().out


def test_a_settled_row_is_not_listed_among_the_unresolved(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Only rows without an answer need the projection printed."""
    quick.report_projections([_reading("g/r", [0.0] * 6, [0.0] * 6)])
    assert not capsys.readouterr().out


# -------------------------------------------------------------- the selection


def test_a_caller_may_narrow_the_selection() -> None:
    """Fewer seats and fewer grammars are both the caller's to ask for."""
    assert quick.narrowed(ROSTER, PDA_REACH, ["lexic-pda"], ["json"]) == (
        ("json", "lexic-pda"),
    )


def test_a_caller_may_not_widen_the_selection() -> None:
    """A reading on a row the change cannot reach answers nobody's question,
    with budget the reachable rows needed."""
    with pytest.raises(ValueError, match="does not reach"):
        quick.narrowed(ROSTER, PDA_REACH, ["lexic-earley"], None)


def test_a_misspelt_name_is_refused_rather_than_selecting_nothing() -> None:
    """A typo would otherwise read as a fast, clean run over no rows."""
    with pytest.raises(ValueError, match="no such benchmark seat or grammar"):
        quick.narrowed(ROSTER, PDA_REACH, None, ["jsonn"])


def test_an_unasked_axis_means_everything_the_change_reaches() -> None:
    """The default is the diff's own answer, not the whole roster."""
    chosen = quick.narrowed(ROSTER, PDA_REACH, None, None)
    assert {row[1] for row in chosen} <= PDA_REACH


def test_a_diff_that_reaches_nothing_measures_nothing_and_exits_zero(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A documentation change has no row to report, and that is not a failure."""
    _quiet_run(monkeypatch)
    monkeypatch.setattr(quick, "seats_for", lambda _paths: frozenset())

    assert quick.main(["--base-root", str(BASE)]) == 0
    assert "no row to measure" in capsys.readouterr().out


def test_the_run_names_which_paths_selected_which_seats(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A selection a reader cannot check is a selection they must trust."""
    _quiet_run(monkeypatch)
    quick.main(["--base-root", str(BASE), "--grammars", "json"])

    printed = capsys.readouterr().out
    assert "changed path(s) reach" in printed
    assert "lexic-pda" in printed


ROSTER_GRAMMARS = tuple(bench.name for bench in BENCHES)
"""Every grammar the benchmark roster carries; none may be named in the tier.

DERIVED, never listed. A hand-written copy goes stale silently and the guard
below then checks LESS than it reads as checking: a name absent from the copy
could be hardcoded in the tier and still pass. Reading the roster means a row
added anywhere is guarded here the day it lands.
"""


def test_no_grammar_name_is_written_into_this_module() -> None:
    """The selection is a fact about a change, so no language is privileged.

    A default grammar list in the code would measure that language's rows
    whatever the change touched. Read off the string CONSTANTS rather than the
    text, so that the module importing the standard library's `json` cannot
    hide a `"json"` written beside it.
    """
    tree = ast.parse(Path(quick.__file__).read_text(encoding="utf-8"))
    literals = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }

    assert not literals & set(ROSTER_GRAMMARS)


# --------------------------------------------------------------- the schedule


def test_threaded_rows_are_separated_from_sequential_ones() -> None:
    """A wall-clock row cannot share the machine with anything."""
    shared, alone = quick.by_schedule(ROSTER)
    assert not {row[1] for row in shared} & compare.MT_ROWS
    assert {row[1] for row in alone} <= compare.MT_ROWS
    assert len(shared) + len(alone) == len(ROSTER)


@pytest.mark.parametrize("grammar,row", ROSTER)
def test_every_threaded_row_in_the_roster_is_judged_on_wall(
    grammar: str, row: str
) -> None:
    """A threaded row's result IS latency; CPU would hide the whole effect."""
    expected = "wall" if row in compare.MT_ROWS else "cpu"
    assert quick.clock_for(f"{grammar}/{row}") == expected


def test_threaded_rows_that_the_change_reaches_are_still_opt_in(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The expensive half is a choice, and skipping it is said out loud."""
    _quiet_run(monkeypatch)
    quick.main(["--base-root", str(BASE), "--grammars", "csv"])

    printed = capsys.readouterr().out
    assert "csv/lexic-mt:" not in printed
    assert "--mt" in printed


def test_lanes_change_how_many_rows_run_not_how_a_row_is_measured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Concurrency is a schedule, never a change to a row's own protocol."""
    monkeypatch.setattr(compare, "run_job", _one)
    rows = (("csv", "lexic-pda"), ("json", "lexic-pda"))
    arms = compare.Arms(BASE, HEAD, 4)

    one = {r.verdict.row: r.verdict.pairs for r in quick.run_rows(arms, rows, 1)}
    two = {r.verdict.row: r.verdict.pairs for r in quick.run_rows(arms, rows, 2)}
    assert one == two
    assert set(one) == {"csv/lexic-pda", "json/lexic-pda"}


def test_an_empty_group_costs_no_processes(monkeypatch: pytest.MonkeyPatch) -> None:
    """No rows means no worker, not a pool started to run nothing."""

    def refuse(_job: Job) -> RowResult:
        raise AssertionError("started a worker for an empty group")

    monkeypatch.setattr(compare, "run_job", refuse)
    assert not quick.run_rows(compare.Arms(BASE, HEAD, 4), (), 4)


def test_the_default_lane_count_is_the_gate_s_own_schedule() -> None:
    """A wider envelope than the gate's would unresolve rows the gate settles.

    The calibration meant to raise this failed on its own declared statistic —
    0.2464, 0.0892 and 0.0918 at one, two and four lanes against the gate's
    0.0249, with ONE lane the worst arm, which is the gate's own schedule. So
    the question is open, and the default stays where the rule it borrows is.
    """
    assert quick.LANES == 1


# ------------------------------------------------------------- the null floor


def test_the_null_floor_reports_the_control_arm_that_ran_beside_the_rows() -> None:
    """The floor IS the null arm, not a separate run."""
    readings = [
        _reading("g/a", [0.0] * 6, [0.01] * 6),
        _reading("g/b", [0.0] * 6, [0.03] * 6),
    ]
    floor = quick.floor_of("sequential", readings, 2)
    assert floor.rows == 2
    assert floor.lanes == 2
    assert floor.control == pytest.approx(math.exp(0.02))


def test_a_noisier_control_widens_the_reported_floor() -> None:
    """A run that kept loud company has to say so in its own numbers."""
    quiet = quick.floor_of("sequential", [_reading("g/a", [0.0] * 6, [0.0] * 6)], 1)
    loud = quick.floor_of(
        "sequential", [_reading("g/a", [0.0] * 6, [0.2, -0.2] * 3)], 1
    )
    assert loud.envelope > quiet.envelope


def test_an_empty_schedule_reports_a_floor_of_no_rows() -> None:
    """A run without threaded rows still prints a threaded floor, honestly."""
    floor = quick.floor_of("threaded", (), 1)
    assert floor.rows == 0
    assert floor.control == pytest.approx(1.0)


# -------------------------------------------- what a row would cost to settle


def test_the_projection_agrees_with_the_gate_at_the_count_that_was_run() -> None:
    """The anti-drift pin: two ways of asking the same question.

    ``separation`` rescales the same three comparisons ``decide`` makes, so at
    the count a row was ACTUALLY measured at the two must give the same answer.
    If they ever disagree, the projection has stopped describing the rule it is
    projecting and every number it prints is about a different gate.
    """
    cases = (
        (math.log(1.10), 0.005, 0.0, 0.005),
        (0.0249, 0.0302, 0.0012, 0.0253),
        (0.0, 0.02, 0.0, 0.02),
        (-math.log(1.20), 0.004, 0.0, 0.004),
    )
    for mean, sigma, control_mean, control_sigma in cases:
        pairing = _spread_pairing(mean, sigma, control_mean, control_sigma, 4)
        decided = compare.decide("g/r", pairing, "cpu").status != "unresolved"
        assert quick.decided_at(pairing, 4) is decided, (mean, sigma)


def test_a_clean_effect_needs_no_pairs_beyond_the_ones_it_has() -> None:
    """A large effect against a quiet control has already answered."""
    pairing = _spread_pairing(math.log(1.10), 0.005, 0.0, 0.005, 4)
    assert quick.separation(pairing) == 4


def test_a_projection_never_names_a_count_below_the_one_already_spent() -> None:
    """The two tests are not monotone in the pair count.

    The envelope narrows as the control gains pairs, so a row can read ``ok``
    at six and ``unresolved`` at sixteen. A search from zero would then answer
    an unresolved row with a count it has already passed — "needs eight pairs"
    after sixteen were spent, which is the search's artefact and not advice.
    """
    pairing = _spread_pairing(0.0058, 0.0180, 0.0007, 0.0250, 16)
    assert compare.decide("g/r", pairing, "cpu").status == "unresolved"
    assert quick.decided_at(pairing, 6)
    projected = quick.separation(pairing)
    assert projected is None or projected > 16


def test_a_projected_count_is_always_even() -> None:
    """Odd counts carry the first-slot bias the gate's bounds exist to remove."""
    for sigma in (0.01, 0.02, 0.03, 0.04, 0.05):
        pairing = _spread_pairing(0.02, sigma, 0.001, sigma, 6)
        projected = quick.separation(pairing)
        assert projected is None or projected % 2 == 0, sigma


def test_a_row_can_need_more_pairs_than_the_gate_itself_will_spend() -> None:
    """The sentence the tier exists to replace "cannot tell" with.

    These are one real unresolved row's statistics. It does not settle at the
    gate's own ceiling of sixteen pairs — the landing gate would not answer it
    either — and the projection says what would: about twenty-two. That is a
    number someone can act on, where a bare `unresolved` is not.
    """
    pairing = _spread_pairing(0.0249, 0.0302, 0.0012, 0.0253, 4)
    assert compare.decide("g/r", pairing, "cpu").status == "unresolved"
    assert not quick.decided_at(pairing, compare.MAX_PAIRS)
    projected = quick.separation(pairing)
    assert projected is not None
    assert compare.MAX_PAIRS < projected <= 24


def test_the_projection_never_promises_what_the_current_count_already_denies() -> None:
    """A row that has settled projects the count it settled at or lower."""
    pairing = _spread_pairing(math.log(1.30), 0.004, 0.0, 0.004, 6)
    assert compare.decide("g/r", pairing, "cpu").status == "slower"
    assert quick.separation(pairing) == 6


def test_a_projection_reads_the_per_pair_spread_not_the_pair_count() -> None:
    """The same per-pair noise projects the same count from any sample size.

    The quantity has to be per-pair: a standard error already carries the count
    it was taken at, and projecting from one would answer the question with its
    own premise.
    """
    small = _spread_pairing(0.02, 0.03, 0.001, 0.02, 4)
    large = _spread_pairing(0.02, 0.03, 0.001, 0.02, 16)
    assert quick.separation(small) == quick.separation(large)
