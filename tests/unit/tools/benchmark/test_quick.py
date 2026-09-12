"""Tests for the PRELIMINARY tier — its budget, its scope and its words.

Three things are the tier's whole contract, and each one is here because
breaking it silently turns a cheap reading into something that reads like an
acceptance result: the budget is fixed, the scope is an intersection the caller
states, and no outcome is ever spelled the way the gate spells one.
"""

from __future__ import annotations

import ast
import json
import math
from pathlib import Path

import pytest

from tools.benchmark import compare, quick
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
    ("vyx", "lexic-pda"),
)
"""A small roster with both schedules in it, claimed by both trees."""


def _pairing(candidate: list[float], control: list[float]) -> compare.Pairing:
    """A row's paired log ratios; the slot readings follow the control's."""
    return compare.Pairing(tuple(candidate), tuple(control), tuple(control))


def _result(reading: float) -> RowResult:
    """One worker's whole answer at a given reading on both clocks."""
    return RowResult(CONTRACT, (OBSERVED._replace(wall=reading, cpu=reading),), None)


def _reading(row: str, candidate: list[float], control: list[float]) -> quick.Reading:
    """One judged row, built from stated log ratios."""
    pairing = _pairing(candidate, control)
    return quick.Reading(quick.preliminary(row, pairing, "cpu"), pairing)


def _one(_job: Job) -> RowResult:
    """Every worker reads exactly the same, on both arms."""
    return _result(1.0)


def _both_trees_claim(_base: Path, _head: Path) -> tuple[tuple[str, str], ...]:
    """Both trees claim the same small roster."""
    return ROSTER


def _stub_digest(_root: Path) -> str:
    """A benchmark digest for a tree that is not on disk."""
    return "0000000000000000"


# ---------------------------------------------------------------- the words


GATE_WORDS = frozenset({"ok", "slower", "faster", "unresolved"})
"""What the gate says; nothing the tier says may collide with any of them."""


@pytest.mark.parametrize(
    ("candidate", "control"),
    [
        ([0.1] * 4, [0.0] * 4),
        ([-0.1] * 4, [0.0] * 4),
        ([0.001] * 4, [0.05, -0.05, 0.05, -0.05]),
        ([-0.1, 0.1, -0.1, 0.1], [0.0] * 4),
    ],
)
def test_no_outcome_is_ever_spelled_the_way_the_gate_spells_one(
    candidate: list[float], control: list[float]
) -> None:
    """A quick word read against the gate's rule would be read against the wrong one."""
    verdict = quick.preliminary("json/lexic-pda", _pairing(candidate, control), "cpu")

    assert verdict.status not in GATE_WORDS


def test_a_row_above_the_envelope_only_leans_slower() -> None:
    """Four pairs may indicate a direction; they may not condemn a tree."""
    verdict = quick.preliminary("json/lexic-pda", _pairing([0.1] * 4, [0.0] * 4), "cpu")

    assert verdict.status == quick.LEANS_SLOWER
    assert verdict.ratio == pytest.approx(math.exp(0.1))


def test_a_row_below_the_envelope_only_leans_faster() -> None:
    """The same restraint in the flattering direction."""
    verdict = quick.preliminary(
        "json/lexic-pda", _pairing([-0.1] * 4, [0.0] * 4), "cpu"
    )

    assert verdict.status == quick.LEANS_FASTER


def _flat_group(*pairings: compare.Pairing) -> list[str]:
    """Every row's settled word, judged as one schedule."""
    settled = quick.settle(
        [
            quick.Reading(quick.preliminary(f"row{index}", pairing, "cpu"), pairing)
            for index, pairing in enumerate(pairings)
        ]
    )
    return [reading.verdict.status for reading in settled]


def test_flat_needs_both_edges_inside_the_envelope() -> None:
    """A direction reading is not the gate's one-sided question.

    The gate calls a row `ok` on `high <= envelope` alone, because it asks only
    whether the row is slower. This tier is read for direction, so an interval
    whose lower edge escapes the envelope has not shown one.
    """
    inside = _pairing([0.001] * 4, [0.05, -0.05, 0.05, -0.05])
    # Candidate mean -0.02 with a wide interval: the top edge is inside the
    # 0.02 envelope, the bottom edge is not.
    low_edge_out = _pairing(
        [-0.0465, 0.0065, -0.0465, 0.0065], [0.02, -0.02, 0.02, -0.02]
    )

    assert compare.decide("row", low_edge_out, "cpu").status == "ok"
    assert _flat_group(inside, inside) == [quick.FLAT, quick.FLAT]
    assert _flat_group(low_edge_out, low_edge_out) == [
        quick.INCONCLUSIVE,
        quick.INCONCLUSIVE,
    ]


def test_preliminary_alone_never_says_flat() -> None:
    """A row cannot be called unchanged before the run's own noise is known."""
    inside = _pairing([0.001] * 4, [0.05, -0.05, 0.05, -0.05])

    assert quick.preliminary("row", inside, "cpu").status == quick.INCONCLUSIVE


def test_a_row_noisier_than_the_run_is_not_flat_however_wide_its_interval() -> None:
    """The defect this rule exists for: a huge envelope swallowing a reading.

    One row read 0.9672 with a 1.1763 envelope and was called unchanged, in a
    run whose typical envelope was 1.0338. A row whose noise is anomalous for
    the run has separated nothing, and `flat` is the one word that must not say
    otherwise.
    """
    typical = _pairing([0.001] * 4, [0.01, -0.01, 0.01, -0.01])
    swallowed = _pairing([-0.033] * 4, [0.2, -0.2, 0.2, -0.2])

    assert _flat_group(typical, typical, swallowed) == [
        quick.FLAT,
        quick.FLAT,
        quick.INCONCLUSIVE,
    ]


def test_the_ceiling_is_relative_to_the_run_s_own_noise() -> None:
    """The same row is flat in a noisy run and inconclusive in a quiet one."""
    row = _pairing([0.001] * 4, [0.05, -0.05, 0.05, -0.05])
    quiet = _pairing([0.001] * 4, [0.005, -0.005, 0.005, -0.005])
    loud = _pairing([0.001] * 4, [0.2, -0.2, 0.2, -0.2])

    assert _flat_group(row, loud, loud)[0] == quick.FLAT
    assert _flat_group(row, quiet, quiet)[0] == quick.INCONCLUSIVE


def test_the_ceiling_scales_the_noise_and_not_the_ratio() -> None:
    """1.5 against a 1.0338 envelope means 1.0507, never 1.5507.

    An envelope is a ratio whose whole meaning is its distance from 1.0, so a
    multiple has to be taken of that distance. Multiplying the ratio would put
    the ceiling at 50% and admit anything.
    """
    readings = [_reading(f"row{n}", [0.0] * 4, [0.02, -0.02] * 2) for n in range(3)]
    typical = readings[0].verdict.envelope
    ceiling = quick.ceiling_of(readings)

    assert ceiling == pytest.approx(1.0 + quick.NOISE_SLACK * (typical - 1.0))
    assert ceiling < 1.0 + (typical - 1.0) * 2


def test_an_ordinary_run_is_not_barred_by_the_ceiling() -> None:
    """The property the bare median lacked, and the reason it was replaced.

    A median bars half the field by construction: half of any run's rows sit
    above it. A run whose rows are all quiet and all much of a muchness must
    come out flat, not half flat.
    """
    spread = [0.01, 0.011, 0.012, 0.013, 0.014]
    rows = [_pairing([0.0005] * 4, [width, -width] * 2) for width in spread]

    assert _flat_group(*rows) == [quick.FLAT] * len(spread)


def test_settling_never_touches_a_leaning_row() -> None:
    """A lean is about the row against its own noise; the run cannot revoke it."""
    leaning = _pairing([0.1] * 4, [0.0] * 4)
    quiet = _pairing([0.001] * 4, [0.005, -0.005, 0.005, -0.005])

    assert _flat_group(leaning, quiet, quiet)[0] == quick.LEANS_SLOWER


def test_a_straddling_interval_is_inconclusive_and_earns_nothing() -> None:
    """Where the gate would grow, this tier stops and says so."""
    verdict = quick.preliminary(
        "json/lexic-pda", _pairing([-0.1, 0.1, -0.1, 0.1], [0.0] * 4), "cpu"
    )

    assert verdict.status == quick.INCONCLUSIVE
    assert verdict.pairs == 4


# --------------------------------------------------------------- the budget


def test_a_row_costs_exactly_the_fixed_pair_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No growth: four candidate pairs and four control pairs, always."""
    seen: list[str] = []

    def run(job: Job) -> RowResult:
        seen.append(job.label)
        return _result(1.0 if job.root == BASE else 1.4)

    monkeypatch.setattr(compare, "run_job", run)
    reading = quick.measure(compare.Arms(BASE, HEAD, 4), "json", "lexic-pda")

    assert len(reading.pairing.candidate) == quick.PAIRS
    assert len(reading.pairing.control) == quick.PAIRS
    assert len(seen) == quick.PAIRS * 4
    assert reading.verdict.pairs == quick.PAIRS


def test_a_row_that_will_not_separate_still_costs_the_same(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The unresolved row is exactly the one the gate spends sixteen pairs on."""
    swings = iter([1.2, 0.8] * quick.PAIRS)

    def run(job: Job) -> RowResult:
        if job.label.endswith("head"):
            return _result(next(swings))
        return _result(1.0)

    monkeypatch.setattr(compare, "run_job", run)
    reading = quick.measure(compare.Arms(BASE, HEAD, 4), "json", "lexic-pda")

    assert reading.verdict.status == quick.INCONCLUSIVE
    assert reading.verdict.pairs == quick.PAIRS


def test_the_pair_budget_is_even() -> None:
    """Odd counts leave the first-slot cost in the published ratio."""
    assert quick.PAIRS % 2 == 0


def test_the_default_lane_count_claims_no_unmeasured_concurrency() -> None:
    """A default may not exceed the lane count whose floor was measured.

    Four lanes read a control spread of 0.0431 against the gate's 0.0277 on the
    same rows. The calibration that was meant to settle it measured one, two and
    four lanes and failed on its own declared statistic: 0.2464, 0.0892 and
    0.0918 against the gate's 0.0249, with ONE lane the worst arm — and one lane
    is the gate's own schedule, so that statistic was not reading concurrency.
    Robust measures reverse the ordering, and adopting them after the fact would
    be choosing the statistic to fit the result. Raise this with an experiment
    that answers, not with the one that did not.
    """
    assert quick.LANES == 1


def test_a_threaded_row_gets_its_own_smaller_budget() -> None:
    """Threaded rows may not share the machine, so they cost more and get less."""
    assert quick.budget("lexic-mt") == quick.MT_PAIRS
    assert quick.budget("lexic-pda") == quick.PAIRS
    assert quick.MT_PAIRS < quick.PAIRS


def test_a_threaded_row_costs_exactly_its_own_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The smaller budget has to reach the sampler, not just the constant."""
    seen: list[str] = []

    def run(job: Job) -> RowResult:
        seen.append(job.label)
        return _result(1.0)

    monkeypatch.setattr(compare, "run_job", run)
    reading = quick.measure(compare.Arms(BASE, HEAD, 4), "json", "lexic-mt")

    assert reading.verdict.pairs == quick.MT_PAIRS
    assert len(seen) == quick.MT_PAIRS * 4


# ------------------------------------------------------ the threaded opt-in


def test_threaded_rows_in_scope_are_not_measured_without_the_flag(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The expensive half is a choice, and skipping it is said out loud."""
    monkeypatch.setattr(quick, "rosters", _both_trees_claim)
    monkeypatch.setattr(compare, "run_job", _one)
    monkeypatch.setattr(quick, "digest", _stub_digest)

    quick.main(["--base-root", str(BASE), "--grammars", "csv"])

    printed = capsys.readouterr().out
    assert "--mt" in printed
    assert "lexic-mt" not in printed


def test_the_threaded_cost_is_printed_before_the_threaded_rows_start(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A caller decides against a long run only if told before it begins."""
    order: list[str] = []

    def run(job: Job) -> RowResult:
        order.append(job.label)
        return _result(1.0)

    monkeypatch.setattr(quick, "rosters", _both_trees_claim)
    monkeypatch.setattr(compare, "run_job", run)
    monkeypatch.setattr(quick, "digest", _stub_digest)

    quick.main(["--base-root", str(BASE), "--grammars", "csv", "--mt"])

    printed = capsys.readouterr().out
    announced = printed.index("worker processes one at a time")
    assert announced < printed.index("csv/lexic-mt:")
    assert "min" in printed[announced : announced + 80]
    assert any(label.startswith("csv/lexic-mt") for label in order)


def test_a_threaded_only_scope_without_the_flag_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Silently measuring nothing is the failure this tier must never have."""
    monkeypatch.setattr(quick, "rosters", _both_trees_claim)

    with pytest.raises(ValueError, match="--mt"):
        quick.main(["--base-root", str(BASE), "--only", "lexic-mt"])


# ---------------------------------------------------------------- the scope


def test_the_scope_intersects_seats_with_grammars() -> None:
    """Unlike the gate's union `--only`, a seat list crossed with a grammar list."""
    chosen = quick.scoped(ROSTER, ["lexic-pda"], ["json", "vyx"])

    assert chosen == (("json", "lexic-pda"), ("vyx", "lexic-pda"))


def test_an_empty_list_means_every_name_on_that_axis() -> None:
    """Omitting one axis selects all of it rather than none of it."""
    assert quick.scoped(ROSTER, None, ["csv"]) == (
        ("csv", "lexic-pda"),
        ("csv", "lexic-mt"),
    )
    assert quick.scoped(ROSTER, ["lexic-mt"], None) == (
        ("csv", "lexic-mt"),
        ("json", "lexic-mt"),
    )
    assert quick.scoped(ROSTER, None, None) == ROSTER


def test_a_misspelt_name_is_refused_rather_than_selecting_nothing() -> None:
    """Selecting nothing would read as a fast, clean run over unmeasured rows."""
    with pytest.raises(ValueError, match="jsonn"):
        quick.refuse_unknown(ROSTER, ["lexic-pda"], ["jsonn"])
    with pytest.raises(ValueError, match="lexic-pdaa"):
        quick.refuse_unknown(ROSTER, ["lexic-pdaa"], None)


def test_a_scope_the_roster_carries_is_accepted() -> None:
    """The refusal must not fire on names that are there."""
    assert quick.refuse_unknown(ROSTER, ["lexic-mt"], ["csv", "json"]) is None


ROSTER_GRAMMARS = (
    "abnf-meta",
    "announced",
    "arithmetic",
    "backtrack",
    "csv",
    "gbnf-meta",
    "json",
    "lexruns",
    "markdown",
    "mixedends",
    "nested",
    "vyx",
)
"""Every grammar the benchmark roster carries; none may be named in the tier."""


def test_no_grammar_name_is_written_into_this_module() -> None:
    """The touched set is a fact about a change, so the caller derives it.

    A default grammar list in the code would be a privileged formulation: the
    tier would measure that language's rows whatever the change touched. Read
    off the string CONSTANTS rather than the text, so that the module importing
    the standard library's `json` cannot hide a `"json"` written beside it.
    """
    tree = ast.parse(Path(quick.__file__).read_text(encoding="utf-8"))
    literals = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }

    assert not literals & set(ROSTER_GRAMMARS)


# ------------------------------------------------------------- the schedule


def test_threaded_rows_are_separated_from_sequential_ones() -> None:
    """A wall-clock row cannot share the machine with anything."""
    shared, alone = quick.by_schedule(ROSTER)

    assert alone == (("csv", "lexic-mt"), ("json", "lexic-mt"))
    assert all(row not in compare.MT_ROWS for _grammar, row in shared)
    assert len(shared) + len(alone) == len(ROSTER)


def test_every_threaded_row_in_the_roster_is_judged_on_wall(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The clock follows the row, not the schedule it happened to run under."""
    monkeypatch.setattr(compare, "run_job", _one)
    threaded = quick.measure(compare.Arms(BASE, HEAD, 4), "json", "lexic-mt")
    sequential = quick.measure(compare.Arms(BASE, HEAD, 4), "json", "lexic-pda")

    assert threaded.verdict.clock == "wall"
    assert sequential.verdict.clock == "cpu"


def test_lanes_change_how_many_rows_run_not_how_a_row_is_measured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Alternation lives inside a lane, so concurrency cannot disturb it."""
    seen: list[tuple[str, Path]] = []

    def run(job: Job) -> RowResult:
        seen.append((job.label, job.root))
        return _result(1.0 if job.root == BASE else 1.4)

    monkeypatch.setattr(compare, "run_job", run)
    rows = (("json", "lexic-pda"), ("csv", "lexic-pda"))
    readings = quick.run_rows(compare.Arms(BASE, HEAD, 4), rows, 2)

    assert len(readings) == 2
    for grammar, _row in rows:
        candidate = [
            root
            for label, root in seen
            if label.startswith(grammar) and label.endswith(("/base", "/head"))
        ]
        # The first pair runs head first, the second base first, and so on.
        assert candidate[:4] == [HEAD, BASE, BASE, HEAD]
        assert len(candidate) == quick.PAIRS * 2


def test_an_empty_group_costs_no_processes(monkeypatch: pytest.MonkeyPatch) -> None:
    """A scope with no threaded rows must not start a pool to run none."""

    def run(_job: Job) -> RowResult:
        raise AssertionError("no worker may start for an empty group")

    monkeypatch.setattr(compare, "run_job", run)
    measured = quick.run_rows(compare.Arms(BASE, HEAD, 4), (), 4)

    assert isinstance(measured, tuple)
    assert not measured


# --------------------------------------------------------------- the floor


def test_the_null_floor_reports_the_control_arm_that_ran_beside_the_rows() -> None:
    """The floor is measured, not assumed: it is the control pairs' own median."""
    readings = (
        _reading("json/lexic-pda", [0.01] * 4, [0.02, -0.01, 0.02, -0.01]),
        _reading("csv/lexic-pda", [0.01] * 4, [0.03, -0.01, 0.03, -0.01]),
    )

    floor = quick.floor_of("sequential", readings, 4)

    assert floor.rows == 2
    assert floor.lanes == 4
    assert floor.control == pytest.approx(math.exp(0.005))
    assert floor.envelope > 1.0


def test_a_noisier_control_widens_the_reported_floor() -> None:
    """Concurrency that costs something has to be visible in this number."""
    quiet = quick.floor_of(
        "sequential", (_reading("row", [0.0] * 4, [0.001, -0.001] * 2),), 1
    )
    loud = quick.floor_of(
        "sequential", (_reading("row", [0.0] * 4, [0.2, -0.2] * 2),), 8
    )

    assert loud.envelope > quiet.envelope


# ---------------------------------------------------------------- the run


def test_the_run_exits_zero_even_when_a_row_leans_slower(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A preliminary reading has no verdict to fail a run with."""

    def run(job: Job) -> RowResult:
        return _result(1.0 if job.root == BASE else 1.4)

    monkeypatch.setattr(quick, "rosters", _both_trees_claim)
    monkeypatch.setattr(compare, "run_job", run)
    monkeypatch.setattr(quick, "digest", _stub_digest)
    out = tmp_path / "quick.json"

    code = quick.main(
        [
            "--base-root",
            str(BASE),
            "--head-root",
            str(HEAD),
            "--only",
            "lexic-pda",
            "--grammars",
            "json",
            "--json",
            str(out),
        ]
    )

    written = json.loads(out.read_text(encoding="utf-8"))
    assert code == 0
    assert written["tier"] == "PRELIMINARY"
    assert written["pairs"] == quick.PAIRS
    assert [entry["status"] for entry in written["verdicts"]] == [quick.LEANS_SLOWER]
    assert not {entry["status"] for entry in written["verdicts"]} & GATE_WORDS


def test_the_tier_word_reaches_the_text_output(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A reader who sees only the terminal must still see which tier ran."""
    monkeypatch.setattr(quick, "rosters", _both_trees_claim)
    monkeypatch.setattr(compare, "run_job", _one)
    monkeypatch.setattr(quick, "digest", _stub_digest)

    quick.main(["--base-root", str(BASE), "--only", "lexic-pda", "--grammars", "csv"])

    printed = capsys.readouterr().out
    assert printed.count("PRELIMINARY") >= 2
    assert "compare.py decides what lands" in printed


def test_a_scope_selecting_no_rows_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    """An empty run that prints a clean table is the worst possible answer."""
    monkeypatch.setattr(quick, "rosters", _both_trees_claim)

    with pytest.raises(ValueError, match="no rows"):
        quick.main(
            ["--base-root", str(BASE), "--only", "lexic-lex", "--grammars", "vyx"]
        )
