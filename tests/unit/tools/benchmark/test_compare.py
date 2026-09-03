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


def _result(cpu: float) -> RowResult:
    """One worker's whole answer at a given CPU reading."""
    return RowResult(CONTRACT, (Observation(cpu, cpu, "d", "accepted", None, 1),), None)


def _pairing(candidate: list[float], control: list[float]) -> compare.Pairing:
    """A row's paired log ratios."""
    return compare.Pairing(tuple(candidate), tuple(control))


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
    compare.sample(compare.Arms(BASE, HEAD, 4), "json", "lexic-pda", 2)

    candidate = [root for root, label in seen if label.endswith(("/base", "/head"))]
    assert candidate == [HEAD, BASE, BASE, HEAD]


def test_control_order_flips_on_its_own_schedule(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An ordering artefact must not cancel identically in both arms."""
    seen: list[str] = []

    def run(job: Job) -> RowResult:
        seen.append(job.label.rsplit("/", 1)[1])
        return _result(1.0)

    monkeypatch.setattr(compare, "run_job", run)
    compare.sample(compare.Arms(BASE, HEAD, 4), "json", "lexic-pda", 3)

    controls = [name for name in seen if name.startswith("control")]
    assert controls[:2] == ["control-a", "control-b"]
    assert controls[4:] == ["control-b", "control-a"]


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
        _arms: compare.Arms, _grammar: str, _row: str, pairs: int
    ) -> compare.Pairing:
        asked.append(pairs)
        return _pairing([-0.1, 0.1] * pairs, [0.0] * (2 * pairs))

    monkeypatch.setattr(compare, "sample", sample)
    verdict, pairing = compare.grow(compare.Arms(BASE, HEAD, 4), "json", "lexic-pda")

    assert verdict.status == "unresolved"
    assert asked[0] == compare.MIN_PAIRS
    assert len(pairing.candidate) >= compare.MAX_PAIRS


def test_a_threaded_row_is_judged_on_wall_and_a_sequential_one_on_cpu() -> None:
    """A split's result is latency; a sequential row's is work done."""
    observation = Observation(2.0, 9.0, "digest", "accepted", True, 4)

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


def test_an_unresolved_row_blocks_the_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Inconclusive evidence is not a pass."""
    assert _gate(monkeypatch, ["ok", "unresolved"]) == 1


def test_a_slower_row_blocks_the_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    """A confirmed regression fails, with no percentage allowance to hide in."""
    assert _gate(monkeypatch, ["slower"]) == 1


def test_every_row_resolved_and_none_slower_passes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The only way through is every row decided, and none of them slower."""
    assert _gate(monkeypatch, ["ok", "faster"]) == 0


def test_a_slower_verdict_must_survive_the_whole_pair_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Stopping the moment a threshold is first crossed manufactures regressions."""
    asked: list[int] = []

    def sample(
        _arms: compare.Arms, _grammar: str, _row: str, pairs: int
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
        _arms: compare.Arms, _grammar: str, _row: str, pairs: int
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
