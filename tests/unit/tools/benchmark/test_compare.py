"""Tests for the per-tree base/head performance comparison.

The absolute ratchet, its five-percent rule, `accepted_rows` and the batch
`confirm` are gone by ruling, so the tests whose exact subject was one of those
are gone with them. What survived is re-pinned here against the replacement:
per-pair order flipping, row-contract agreement, and the log-ratio verdicts
against a measured control envelope.
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from tools.benchmark import compare
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
"""A well-formed contract for one sequential row."""


OBSERVED = Observation(1.0, 1.0, "text", "shape", "accepted", None, "plan", 1)
"""A well-formed observation of one accepted sequential row."""


def _result(cpu: float) -> RowResult:
    """One worker's whole answer at a given CPU reading."""
    return RowResult(CONTRACT, (OBSERVED._replace(wall=cpu, cpu=cpu),), None)


def _arm(label: str, **fields: object) -> compare.Arm:
    """One arm's answer, differing from the well-formed one as asked."""
    return compare.Arm(label, CONTRACT, OBSERVED._replace(**fields))


def _pairing(
    candidate: list[float], control: list[float], slots: list[float] | None = None
) -> compare.Pairing:
    """A row's paired log ratios; the slot readings default to the control's."""
    return compare.Pairing(
        tuple(candidate), tuple(control), tuple(control if slots is None else slots)
    )


def _verdict(row: str, status: str) -> compare.Verdict:
    """One decided row, for judging the gate's exit code."""
    return compare.Verdict(row, status, 1.0, 0.99, 1.01, 1.02, 5, "cpu")


def test_pairs_alternate_which_tree_runs_first(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Base/head order cannot become a fixed thermal advantage."""
    seen: list[tuple[Path, str]] = []

    def run(job: Job) -> RowResult:
        seen.append((job.root, job.label))
        return _result(1.0 if job.root == BASE else 1.1)

    monkeypatch.setattr(compare, "run_job", run)
    compare.sample(compare.Arms(BASE, HEAD, 4), "json", "lexic-pda", 2, 0)

    candidate = [root for root, label in seen if label.endswith(("/base", "/head"))]
    assert candidate == [HEAD, BASE, BASE, HEAD]


def test_control_order_flips_on_its_own_schedule(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An ordering artefact must not cancel identically in both arms.

    The control runs the candidate's period in the OPPOSITE PHASE: whenever the
    candidate runs head first, the control runs control-b first. That is what
    keeps the artefact from cancelling the same way in both arms — the reason
    the control was given a schedule of its own — while leaving it balanced, so
    it no longer accumulates into the envelope.
    """
    seen: list[str] = []

    def run(job: Job) -> RowResult:
        seen.append(job.label.rsplit("/", 1)[1])
        return _result(1.0)

    monkeypatch.setattr(compare, "run_job", run)
    compare.sample(compare.Arms(BASE, HEAD, 4), "json", "lexic-pda", 4, 0)

    controls = [name for name in seen if name.startswith("control")]
    heads = [name for name in seen if name in {"head", "base"}]
    assert controls[:2] == ["control-b", "control-a"]
    assert controls[2:4] == ["control-a", "control-b"]
    # Opposite phase, stated as the relation rather than as two literals: the
    # candidate leads with head exactly when the control leads with control-b.
    for pair in range(4):
        head_first = heads[2 * pair] == "head"
        control_a_first = controls[2 * pair] == "control-a"
        assert head_first is not control_a_first


def _slot_reading(first: Job, second: Job, row: str) -> tuple[float, float]:
    """A machine whose FIRST process always reads twice the second's.

    Slot-dependent and nothing else: the two jobs are byte-identical code, so
    every non-zero control ratio this produces is the slot, and its sign says
    which way the pair was run.
    """
    return (2.0, 1.0)


def test_a_slot_penalty_reverses_in_the_control_instead_of_accumulating(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The control must reverse the RATIO, not just the labels.

    Reversing which jobs are passed AND keeping the numerator on whichever ran
    first reverses nothing: every control then divides the first process
    reading by the second, and a permanent slot cost is a constant the control
    reports as a fact about the code. The signs are the only place this shows,
    which is why the existing order assertions passed throughout.

    Balance is the second half. On a period of three the schedule was 10
    forward to 5 reversed at fifteen pairs, so a slot cost left a third of
    itself in the control's mean and WIDENED the envelope. Alternating leaves
    the same cost summing to zero, so it is carried by the spread alone.
    """
    monkeypatch.setattr(compare, "_pair", _slot_reading)

    pairing = compare.sample(compare.Arms(BASE, HEAD, 4), "json", "lexic-pda", 6, 0)

    up = math.log(2.0)
    assert list(pairing.control) == [-up, up, -up, up, -up, up]
    assert min(pairing.control) < 0 < max(pairing.control)
    assert sum(pairing.control) == pytest.approx(0.0)
    # The artefact is REPORTED rather than only cancelled: oriented by which
    # process ran first, a constant 2x first-slot penalty reads as a constant.
    assert list(pairing.slots) == [up] * 6


def test_the_two_schedules_sample_the_first_slot_equally_often_at_even_counts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Each ratio's numerator must occupy the first slot as often as the
    other's, or a slot cost enters one mean and not the other."""
    monkeypatch.setattr(compare, "_pair", _slot_reading)

    for pairs in (6, 8, 10):
        pairing = compare.sample(compare.Arms(BASE, HEAD, 4), "json", "x", pairs, 0)
        assert sum(pairing.control) == pytest.approx(0.0), pairs
        assert sum(pairing.candidate) == pytest.approx(0.0), pairs


def test_an_odd_pair_count_leaves_one_slot_in_each_mean_and_they_oppose(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Parity is the one thing alternation cannot fix.

    At an odd count one arm necessarily takes the first slot once more than the
    other, so a slot cost d leaves +d/n in the candidate's mean and -d/n in the
    control's. Opposite signs are what makes it harmless to the VERDICT: the
    envelope is a magnitude, so both sides of ``low > envelope`` and
    ``high <= envelope`` move by the same d/n and it cancels. What it does not
    cancel out of is the reported ratio — which is why the bounds are even.
    """
    monkeypatch.setattr(compare, "_pair", _slot_reading)
    step = math.log(2.0)

    for pairs in (5, 15):
        pairing = compare.sample(compare.Arms(BASE, HEAD, 4), "json", "x", pairs, 0)
        assert sum(pairing.candidate) == pytest.approx(step), pairs
        assert sum(pairing.control) == pytest.approx(-step), pairs
        # The artefact itself is oriented, so it reads as a constant whatever
        # the parity does to the two means.
        assert list(pairing.slots) == [step] * pairs


def test_both_pair_bounds_are_even_so_the_reported_ratio_carries_no_slot_bias(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The bounds' parity is a measurement decision, not a round number.

    A row stops at the floor or exhausts the ceiling far more often than it
    stops anywhere between, so those two counts are the ones whose schedules
    must balance. Making either odd puts a known slot bias back into every
    published ratio, and this is the test that says so before it ships.
    """
    assert compare.MIN_PAIRS % 2 == 0, "an odd floor biases every quick verdict"
    assert compare.MAX_PAIRS % 2 == 0, "an odd ceiling biases every hard one"

    monkeypatch.setattr(compare, "_pair", _slot_reading)
    for pairs in (compare.MIN_PAIRS, compare.MAX_PAIRS):
        pairing = compare.sample(compare.Arms(BASE, HEAD, 4), "json", "x", pairs, 0)
        assert sum(pairing.candidate) == pytest.approx(0.0), pairs
        assert sum(pairing.control) == pytest.approx(0.0), pairs


def test_the_candidate_holds_its_arm_while_reversing_execution_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Head stays the numerator; only which process runs first alternates.

    The control's shape is the candidate's, and this is the half that was
    already right — pinned here so a later edit cannot "fix" the control by
    breaking this one into agreement with it.
    """
    monkeypatch.setattr(compare, "_pair", _slot_reading)

    pairing = compare.sample(compare.Arms(BASE, HEAD, 4), "json", "lexic-pda", 4, 0)

    up = math.log(2.0)
    assert list(pairing.candidate) == [up, -up, up, -up]


def test_the_control_reversal_survives_an_offset_growth_round(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A growth round starting at an absolute index keeps its own phase.

    Index 2 is the swapped position, so a call that begins there must open
    with the reversed ratio rather than restarting the cycle.
    """
    monkeypatch.setattr(compare, "_pair", _slot_reading)

    pairing = compare.sample(compare.Arms(BASE, HEAD, 4), "json", "lexic-pda", 2, 2)

    up = math.log(2.0)
    assert list(pairing.control) == [-up, up]


def _cost_under_a_slot_penalty(slot: float, head_cost: float):
    """A reading function: head costs ``head_cost``, the first process ``slot``."""

    def reading(first: Job, second: Job, row: str) -> tuple[float, float]:
        """Both readings, with the first process paying the slot penalty."""
        return (_tree_cost(first, head_cost) * slot, _tree_cost(second, head_cost))

    return reading


def _tree_cost(job: Job, head_cost: float) -> float:
    """What this job's tree costs, ignoring which slot it ran in."""
    return 1.0 if job.label.endswith("/base") else head_cost


def test_a_true_regression_is_not_swallowed_by_a_permanent_slot_penalty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The review's synthetic machine: 10% first-slot cost, 3% head cost.

    With the control divided first-over-second the envelope was exactly the
    slot penalty, 1.10, and a real 3% regression passed as ``ok``. Reversed,
    the penalty no longer stands as a fact about the code, and the row is no
    longer waved through.
    """
    monkeypatch.setattr(compare, "_pair", _cost_under_a_slot_penalty(1.10, 1.03))

    pairing = compare.sample(compare.Arms(BASE, HEAD, 4), "json", "lexic-pda", 15, 0)
    verdict = compare.decide("json/lexic-pda", pairing, "cpu")

    assert verdict.status != "ok", "a real regression passed inside the envelope"
    assert verdict.envelope < 1.10, "the envelope is still the slot penalty itself"


def test_a_machine_with_no_slot_penalty_still_calls_an_equal_pair_ok(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The control row: reversal must not manufacture an envelope of its own.

    Same-cost arms on an even machine have to keep reading ``ok``, or the
    correction has traded a false pass for a false alarm.
    """
    monkeypatch.setattr(compare, "_pair", _cost_under_a_slot_penalty(1.0, 1.0))

    pairing = compare.sample(compare.Arms(BASE, HEAD, 4), "json", "lexic-pda", 15, 0)
    verdict = compare.decide("json/lexic-pda", pairing, "cpu")

    assert verdict.status == "ok"
    assert all(value == 0.0 for value in pairing.control)


def test_the_two_arms_must_have_measured_the_same_row() -> None:
    """A contract differing in ONE field refuses, naming that field."""
    head = CONTRACT._replace(document_digest="different")

    with pytest.raises(ValueError, match="document_digest"):
        compare.agree(CONTRACT, head, "json/lexic-pda")


def test_agreement_names_every_field_that_differs() -> None:
    """The refusal is diagnosable, not a bare mismatch."""
    head = CONTRACT._replace(lexical=("string",), document_bytes=99)

    with pytest.raises(ValueError) as caught:
        compare.agree(CONTRACT, head, "json/lexic-pda")

    assert "lexical" in str(caught.value)
    assert "document_bytes" in str(caught.value)


def test_a_differing_collector_state_refuses() -> None:
    """Two arms must have run their timed pass under the same collector."""
    with pytest.raises(ValueError, match="gc_enabled"):
        compare.agree(CONTRACT, CONTRACT._replace(gc_enabled=False), "row")


def test_identical_contracts_agree() -> None:
    """Two arms that measured the same row proceed to timing."""
    assert compare.agree(CONTRACT, CONTRACT, "json/lexic-pda") is None


def test_a_refused_row_stops_the_run_rather_than_scoring_zero() -> None:
    """A row that produced nothing is not a fast row."""
    with pytest.raises(ValueError, match="refused"):
        compare.require(RowResult(None, (), "no derivation"), "json/lexic-pda")


def test_a_row_slower_than_the_envelope_is_called_slower() -> None:
    """A candidate interval entirely above the control envelope fails."""
    verdict = compare.decide("json/lexic-pda", _pairing([0.1] * 5, [0.0] * 5), "cpu")

    assert verdict.status == "slower"
    assert verdict.ratio == pytest.approx(math.exp(0.1))


def test_a_row_faster_than_the_envelope_is_called_faster() -> None:
    """A candidate interval entirely below the envelope is a real win."""
    verdict = compare.decide("json/lexic-pda", _pairing([-0.1] * 5, [0.0] * 5), "cpu")

    assert verdict.status == "faster"


def test_a_row_inside_the_envelope_is_called_ok() -> None:
    """A change smaller than this machine's own noise is not a result."""
    verdict = compare.decide(
        "json/lexic-pda", _pairing([0.001] * 5, [0.05, -0.05] * 3), "cpu"
    )

    assert verdict.status == "ok"


def _interval_of(low: float, high: float, envelope: float) -> compare.Verdict:
    """One row decided from a stated interval and a stated noise envelope.

    The candidate pairs are chosen to reproduce the interval exactly, so a row
    observed in a real run can be asked here as the number it was.
    """
    middle = (math.log(low) + math.log(high)) / 2
    spread = (math.log(high) - math.log(low)) / 2
    # Five pairs whose mean is `middle` and whose 95% half-width is `spread`.
    error = spread / compare.CONFIDENCE_Z
    deviation = error * math.sqrt(5) * math.sqrt(4) / 2
    candidate = [middle - deviation, middle + deviation, middle, middle, middle]
    edge = math.log(envelope)
    control = [edge / compare.CONFIDENCE_Z * math.sqrt(5) * x for x in (-1, 1, 0, 0, 0)]
    return compare.decide("row", _pairing(candidate, control), "cpu")


def test_an_interval_wholly_below_the_envelope_is_not_unresolved() -> None:
    """A row that cannot be slower has answered the gate's question.

    Observed on the remote run: abnf-meta/lexic-pda read 0.9947 with an
    interval of 0.9911 to 0.9983 against a 1.0055 envelope, and was called
    unresolved — blocking the gate for being possibly faster than the noise.
    """
    verdict = _interval_of(0.9911, 0.9983, 1.0055)

    assert verdict.high <= verdict.envelope
    assert verdict.status == "ok"


def test_a_clear_win_wider_than_the_envelope_is_still_not_unresolved() -> None:
    """The same edge, a long way from it: announced/lexic-mt, 0.9119."""
    verdict = _interval_of(0.8584, 0.9687, 1.0985)

    assert verdict.status in {"ok", "faster"}
    assert verdict.status != "unresolved"


def test_an_interval_overlapping_the_envelope_is_unresolved() -> None:
    """Straddling the boundary earns more pairs; it does not pick a side."""
    verdict = compare.decide(
        "json/lexic-pda", _pairing([-0.1, 0.1, -0.1, 0.1, 0.0], [0.0] * 5), "cpu"
    )

    assert verdict.status == "unresolved"


def test_the_envelope_widens_with_a_noisy_control() -> None:
    """A noisy machine is honest about being noisy rather than strict."""
    quiet = compare.decide("row", _pairing([0.02] * 5, [0.0] * 5), "cpu")
    noisy = compare.decide(
        "row", _pairing([0.02] * 5, [0.2, -0.2, 0.2, -0.2, 0.0]), "cpu"
    )

    assert quiet.status == "slower"
    assert noisy.envelope > quiet.envelope
    assert noisy.status != "slower"


def test_an_unresolved_row_earns_more_pairs_up_to_the_bound(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Growth stops at the bound rather than forcing a median verdict."""
    asked: list[int] = []

    def sample(
        _arms: compare.Arms, _grammar: str, _row: str, pairs: int, _first: int
    ) -> compare.Pairing:
        asked.append(pairs)
        return _pairing([-0.1, 0.1] * pairs, [0.0] * (2 * pairs))

    monkeypatch.setattr(compare, "sample", sample)
    verdict, pairing = compare.grow(compare.Arms(BASE, HEAD, 4), "json", "lexic-pda")

    assert verdict.status == "unresolved"
    assert asked[0] == compare.MIN_PAIRS
    assert len(pairing.candidate) >= compare.MAX_PAIRS


def test_growth_asks_for_whole_blocks_and_lands_on_the_ceiling_exactly() -> None:
    """Every count growth can reach is even, floor and ceiling included.

    Even bounds settle only the two counts a row stops at most often. A step
    that is not the schedule's own period puts every count between them back in
    play, and half of those are odd.
    """
    assert compare.BLOCK % 2 == 0, "an odd block reintroduces odd stopping points"
    assert (compare.MAX_PAIRS - compare.MIN_PAIRS) % compare.BLOCK == 0
    reachable = range(compare.MIN_PAIRS, compare.MAX_PAIRS + 1, compare.BLOCK)
    assert all(count % 2 == 0 for count in reachable)


def _settling_at_seven():
    """Readings that first fall inside the envelope on the SEVENTH pair.

    The first process costs a fixed ``exp(0.10)``; head costs ``exp(0.01)``
    for six pairs and ``exp(-0.20)`` afterwards; the control's two arms are
    identical. Returns the reading function and its call-counter reset.
    """
    calls = [0]

    def reading(first: Job, second: Job, _row: str) -> tuple[float, float]:
        """Both readings, the first process paying a constant slot cost."""
        calls[0] += 1
        head = math.exp(0.01) if (calls[0] - 1) // 2 < 6 else math.exp(-0.20)
        costs = [
            1.0 if job.label.endswith("/base") or "control" in job.label else head
            for job in (first, second)
        ]
        return costs[0] * math.exp(0.10), costs[1]

    return reading, lambda: calls.__setitem__(0, 0)


def test_a_row_that_settles_mid_block_is_published_at_the_block_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Settling on the first pair of a block publishes at the boundary.

    Adding one pair and returning the moment it settled let a row publish at 7,
    9, 11, 13 or 15. At an odd count the candidate's numerator takes the first
    slot once more than the control's and the control's once fewer, so the
    published ratio keeps exactly the bias the even bounds remove — here the
    control's own log ratios sum to -0.10 at seven pairs instead of zero.
    """
    reading, reset = _settling_at_seven()
    monkeypatch.setattr(compare, "_pair", reading)
    arms = compare.Arms(BASE, HEAD, 4)

    reset()
    at_six = compare.decide("json/x", compare.sample(arms, "json", "x", 6, 0), "cpu")
    reset()
    seven = compare.sample(arms, "json", "x", 7, 0)
    assert at_six.status in compare.GROWS, "the fixture must have to grow"
    assert compare.decide("json/x", seven, "cpu").status == "ok", (
        "the fixture must settle on the first pair of a block"
    )
    assert sum(seven.control) == pytest.approx(-0.10), "the bias it would publish"

    reset()
    verdict, pairing = compare.grow(arms, "json", "x")

    assert (verdict.status, verdict.pairs) == ("ok", 8)
    assert len(pairing.candidate) % 2 == 0
    assert sum(pairing.control) == pytest.approx(0.0), "the block cancels the slot"


def test_an_already_balanced_result_is_not_grown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The floor is a complete block, so a row that settles there settles."""
    asked: list[int] = []

    def sample(
        _arms: compare.Arms, _grammar: str, _row: str, pairs: int, _first: int
    ) -> compare.Pairing:
        asked.append(pairs)
        return _pairing([0.0] * pairs, [0.01, -0.01] * (pairs // 2))

    monkeypatch.setattr(compare, "sample", sample)
    verdict, _settled = compare.grow(compare.Arms(BASE, HEAD, 4), "json", "x")

    assert verdict.status == "ok"
    assert asked == [compare.MIN_PAIRS]


def test_a_threaded_row_is_judged_on_wall_and_a_sequential_one_on_cpu() -> None:
    """A split's result is latency; a sequential row's is work done."""
    observation = Observation(2.0, 9.0, "text", "shape", "accepted", True, "plan", 4)

    assert compare.primary_reading(observation, "lexic-mt") == 2.0
    assert compare.primary_reading(observation, "lexic-pda") == 9.0


def _gate(monkeypatch: pytest.MonkeyPatch, statuses: list[str]) -> int:
    """Run the gate's judgement over a fixed verdict set."""
    verdicts = [_verdict(f"g{index}/lexic-pda", s) for index, s in enumerate(statuses)]
    rows = tuple((f"g{index}", "lexic-pda") for index in range(len(statuses)))
    ordered = iter(verdicts)

    monkeypatch.setattr(compare, "rosters", lambda _base, _head: rows)
    monkeypatch.setattr(
        compare,
        "grow",
        lambda _arms, _grammar, _row: (next(ordered), _pairing([0.0], [0.0])),
    )
    return compare.main(["--base-root", str(BASE), "--head-root", str(HEAD)])


def test_an_unresolved_row_does_not_block_the_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unresolved row has measured no slowdown.

    It has measured that this machine could not separate the two arms inside
    the pair bound, which is a fact about the measurement. Failing on it makes
    the gate's answer depend on how quiet the host happened to be, and the only
    move it leaves is to rerun until the noise cooperates.
    """
    assert _gate(monkeypatch, ["ok", "unresolved"]) == 0


def test_an_unresolved_row_is_still_printed_in_full(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Not blocking is not hiding: the row keeps its interval, its envelope
    and its pair count, and the summary says it did not block."""
    assert _gate(monkeypatch, ["ok", "unresolved"]) == 0
    printed = capsys.readouterr().out

    assert "g1/lexic-pda" in printed
    assert "1 row(s) unresolved" in printed
    assert "not blocking" in printed
    assert "envelope 1.0200" in printed
    assert "5 pairs" in printed


def test_a_slower_row_blocks_the_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    """A confirmed regression fails, with no percentage allowance to hide in."""
    assert _gate(monkeypatch, ["slower"]) == 1


def test_a_mixed_run_fails_for_the_slower_row_alone(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """One unresolved row beside a slower one must not change what failed."""
    assert _gate(monkeypatch, ["ok", "unresolved", "slower"]) == 1
    printed = capsys.readouterr().out

    assert "1 row(s) slower" in printed
    assert "1 row(s) unresolved" in printed
    assert "g2/lexic-pda" in printed.split("slower than this machine")[1]


def test_no_row_slower_passes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The only way to fail is a row this machine could separate AND call
    slower."""
    assert _gate(monkeypatch, ["ok", "faster"]) == 0


def test_a_slower_verdict_must_survive_the_whole_pair_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Stopping the moment a threshold is first crossed manufactures regressions."""
    asked: list[int] = []

    def sample(
        _arms: compare.Arms, _grammar: str, _row: str, pairs: int, _first: int
    ) -> compare.Pairing:
        asked.append(pairs)
        return _pairing([0.1] * pairs, [0.0] * pairs)

    monkeypatch.setattr(compare, "sample", sample)
    verdict, pairing = compare.grow(compare.Arms(BASE, HEAD, 4), "json", "lexic-pda")

    assert verdict.status == "slower"
    assert len(pairing.candidate) >= compare.MAX_PAIRS
    assert sum(asked) >= compare.MAX_PAIRS


def test_a_row_that_tips_on_noise_is_not_banked_as_slower(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """More evidence can take a marginal slowdown back inside the envelope."""
    calls = {"n": 0}

    def sample(
        _arms: compare.Arms, _grammar: str, _row: str, pairs: int, _first: int
    ) -> compare.Pairing:
        calls["n"] += pairs
        if calls["n"] <= compare.MIN_PAIRS:
            return _pairing([0.05] * pairs, [0.0] * pairs)
        return _pairing([-0.05] * pairs, [0.2, -0.2] * pairs)

    monkeypatch.setattr(compare, "sample", sample)
    verdict, _pairing_out = compare.grow(
        compare.Arms(BASE, HEAD, 4), "json", "lexic-pda"
    )

    assert verdict.status != "slower"


SEMANTIC_CASES = (
    ("verdict", "parsing: input does not derive from 'root'"),
    ("engaged", True),
    ("split_digest", "carved-elsewhere"),
    ("result_digest", "other-text"),
    ("shape_digest", "other-shape"),
)
"""One differing field per case — each on its own makes the pair meaningless."""


@pytest.mark.parametrize("field,value", SEMANTIC_CASES)
def test_arms_that_did_not_produce_the_same_result_refuse(
    field: str, value: object
) -> None:
    """A pair is a timing sample only when both arms did the same work."""
    base = _arm("json/lexic-mt/base")
    head = _arm("json/lexic-mt/head", **{field: value})

    with pytest.raises(ValueError, match=field):
        compare.comparable(base, head, "json/lexic-mt")


def test_the_refusal_names_the_two_arms_and_both_values() -> None:
    """The refusal is diagnosable without re-running the pair."""
    base = _arm("json/lexic-mt/base", engaged=True, split_digest="eight-pieces")
    head = _arm("json/lexic-mt/head", engaged=False, split_digest="one-piece")

    with pytest.raises(ValueError) as caught:
        compare.comparable(base, head, "json/lexic-mt")

    detail = str(caught.value)
    assert "engaged" in detail and "split_digest" in detail
    assert "json/lexic-mt/base" in detail and "json/lexic-mt/head" in detail


def test_two_arms_that_built_the_same_product_compare() -> None:
    """Identical observations proceed to timing."""
    assert (
        compare.comparable(
            _arm("json/lexic-pda/base"), _arm("json/lexic-pda/head"), "json/lexic-pda"
        )
        is None
    )


def test_a_different_tree_with_the_same_text_refuses() -> None:
    """The text digest is the input on a round trip; the shape is the product."""
    base = _arm("json/lexic-pda/base")
    head = _arm("json/lexic-pda/head", shape_digest="a different tree")

    assert base.observation.result_digest == head.observation.result_digest
    with pytest.raises(ValueError, match="shape_digest"):
        compare.comparable(base, head, "json/lexic-pda")


def test_a_disagreeing_pair_never_reaches_the_estimator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The refusal happens in the pair, not in a report after the verdict."""

    def run(job: Job) -> RowResult:
        if job.label.endswith("/head"):
            return RowResult(
                CONTRACT, (OBSERVED._replace(shape_digest="elsewhere"),), None
            )
        return _result(1.0)

    monkeypatch.setattr(compare, "run_job", run)

    with pytest.raises(ValueError, match="shape_digest"):
        compare.sample(compare.Arms(BASE, HEAD, 4), "json", "lexic-pda", 1, 0)


def _ordering(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Every process an adaptive run started, in order, by which arm it was."""
    seen: list[str] = []

    def run(job: Job) -> RowResult:
        seen.append(job.label.rsplit("/", 1)[1])
        return _result(1.0 if job.root == BASE else 1.1)

    monkeypatch.setattr(compare, "run_job", run)
    verdict, pairing = compare.grow(compare.Arms(BASE, HEAD, 4), "json", "lexic-pda")
    assert len(pairing.candidate) == compare.MAX_PAIRS
    assert verdict.pairs == compare.MAX_PAIRS
    return seen


def test_alternation_holds_across_every_growth_round(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Growth one pair at a time must not put head first thirteen times.

    The later pairs are the decisive ones, so a schedule that restarts at index
    zero on each growth call gives one arm the first slot for the whole tail of
    the run. Both schedules are asserted in full, over every pair the budget
    allows.
    """
    seen = _ordering(monkeypatch)

    candidate = [side for side in seen if side in ("base", "head")]
    expected = [
        side
        for index in range(compare.MAX_PAIRS)
        for side in (("head", "base") if index % 2 == 0 else ("base", "head"))
    ]
    assert candidate == expected
    assert candidate.count("head") == compare.MAX_PAIRS
    assert [pair for pair in zip(*[iter(candidate)] * 2)].count(("head", "base")) == 8


def test_the_controls_own_schedule_also_survives_growth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The control keeps its opposite phase across a growth round's offset."""
    seen = _ordering(monkeypatch)

    controls = [side for side in seen if side.startswith("control")]
    expected = [
        side
        for index in range(compare.MAX_PAIRS)
        for side in (
            ("control-a", "control-b") if index % 2 == 1 else ("control-b", "control-a")
        )
    ]
    assert controls == expected
    # Pair eight is a growth round, and its phase says control-b leads there.
    assert controls[16:18] == ["control-b", "control-a"]
