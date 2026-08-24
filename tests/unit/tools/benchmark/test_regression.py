"""Tests for the checked-in Lexic benchmark regression guard."""

from __future__ import annotations

import pytest

from tools.benchmark import regression
from tools.benchmark.isolation import IsolatedRow
from tools.benchmark.regression import Confirmed, assess

JSON_PDA: regression.Key = ("json", "lexic-pda")
VYX_LEX: regression.Key = ("vyx", "lexic-lex")


def test_faster_values_and_new_rows_ratchet_from_confirmation() -> None:
    """Only the aggregate confirmation may establish a stored target."""
    baseline: regression.Values = {JSON_PDA: 2.0}
    first: regression.Values = {JSON_PDA: 1.8, VYX_LEX: 2.5}
    asked: list[frozenset[tuple[str, str]]] = []

    def repeat(keys: frozenset[tuple[str, str]]) -> Confirmed:
        asked.append(keys)
        return Confirmed({JSON_PDA: 1.82, VYX_LEX: 2.45}, frozenset())

    outcome = assess(baseline, first, repeat)

    assert asked == [frozenset(first)]
    assert outcome.baseline == {JSON_PDA: 1.82, VYX_LEX: 2.45}
    assert outcome.regressions == {}
    assert outcome.inconclusive == frozenset()


def test_noise_sized_change_is_not_repeated_or_stored() -> None:
    """Noise-sized movement does not drag the ratchet toward an outlier."""
    baseline: regression.Values = {JSON_PDA: 2.0}
    outcome = assess(
        baseline,
        {JSON_PDA: 1.92},
        lambda _keys: pytest.fail("a noise-sized change was repeated"),
    )
    assert outcome.baseline == baseline


def test_recovered_short_pass_does_not_move_the_record() -> None:
    """A seven-round anomaly is harmless when aggregate confirmation clears it."""
    baseline: regression.Values = {JSON_PDA: 2.0}
    outcome = assess(
        baseline,
        {JSON_PDA: 2.2},
        lambda _keys: Confirmed({JSON_PDA: 2.09}, frozenset()),
    )
    assert outcome.baseline == baseline
    assert outcome.regressions == {}


def test_accept_regression_raises_only_confirmed_slowdowns() -> None:
    """Acceptance cannot raise a target that confirmation cleared."""
    vyx_pda = ("vyx", "lexic-pda")
    baseline: regression.Values = {JSON_PDA: 2.0, vyx_pda: 3.0}
    first: regression.Values = {JSON_PDA: 2.2, vyx_pda: 3.2}
    repeated = Confirmed({JSON_PDA: 2.16, vyx_pda: 3.1}, frozenset())

    rejected = assess(baseline, first, lambda _keys: repeated)
    accepted = assess(
        baseline,
        first,
        lambda _keys: repeated,
        accept_regression=True,
    )

    assert rejected.regressions == {JSON_PDA: (2.0, 2.16)}
    assert rejected.baseline == baseline
    assert accepted.baseline == {JSON_PDA: 2.16, vyx_pda: 3.0}


def test_inconclusive_confirmation_never_changes_the_record() -> None:
    """A boundary-crossing interval cannot be accepted as a regression."""
    baseline: regression.Values = {JSON_PDA: 2.0}
    outcome = assess(
        baseline,
        {JSON_PDA: 2.2},
        lambda _keys: Confirmed({}, frozenset({JSON_PDA})),
        accept_regression=True,
    )
    assert outcome.baseline == baseline
    assert outcome.regressions == {}
    assert outcome.inconclusive == frozenset({JSON_PDA})


def test_targeted_sample_launches_only_the_exact_requested_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A repeat constructs neither third-party parsers nor neighbouring Lexic rows."""
    seen: list[tuple[str, str, int, int | None, bool]] = []
    monkeypatch.setattr(regression, "_active_keys", lambda: frozenset({JSON_PDA}))
    monkeypatch.setattr(regression, "_mt_cores", lambda _asked: 4)

    def run_row(
        grammar: str, row: str, rounds: int, cores: int | None, full: bool
    ) -> IsolatedRow:
        seen.append((grammar, row, rounds, cores, full))
        return IsolatedRow([2.0, 1.8, 1.9], None, None, None, None, 0.0)

    monkeypatch.setattr(regression, "run_row", run_row)

    assert regression.measure(frozenset({JSON_PDA}), 3) == {JSON_PDA: 1.9}
    assert seen == [("json", "lexic-pda", 3, 4, False)]


def test_confirmation_resolves_stable_rows_after_fourteen_aggregate_rounds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Stable recovery and regression use all 14 samples, not a lucky batch."""
    vyx_pda = ("vyx", "lexic-pda")
    keys = frozenset({JSON_PDA, vyx_pda})
    calls: list[tuple[frozenset[tuple[str, str]], int]] = []

    def sampled(
        selected: frozenset[tuple[str, str]] | None, rounds: int
    ) -> dict[tuple[str, str], list[float]]:
        assert selected is not None and len(selected) == 1
        calls.append((selected, rounds))
        key = next(iter(selected))
        value = 2.0 if key == JSON_PDA else 3.3
        return {key: [value] * rounds}

    monkeypatch.setattr(regression, "sample", sampled)
    result = regression.confirmation(keys, {JSON_PDA: 2.0, vyx_pda: 3.0})

    assert result == Confirmed({JSON_PDA: 2.0, vyx_pda: 3.3}, frozenset())
    assert sum(rounds for selected, rounds in calls if JSON_PDA in selected) == 14
    assert sum(rounds for selected, rounds in calls if vyx_pda in selected) == 14


def test_confirmation_aggregates_every_batch_before_bounded_decision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """More rounds cannot manufacture success by choosing a favorable batch."""
    calls: list[int] = []

    def sampled(
        selected: frozenset[tuple[str, str]] | None, rounds: int
    ) -> dict[tuple[str, str], list[float]]:
        assert selected == frozenset({JSON_PDA})
        calls.append(rounds)
        # The aggregate median stays at the boundary, but its robust sigma is
        # far too wide to trust even at the bounded maximum.
        values = [1.2, 1.5, 1.8, 2.1, 2.4, 2.7, 3.0]
        return {JSON_PDA: values[:rounds]}

    monkeypatch.setattr(regression, "sample", sampled)
    result = regression.confirmation(frozenset({JSON_PDA}), {JSON_PDA: 2.0})

    assert result == Confirmed({JSON_PDA: 2.1}, frozenset())
    assert calls == [7, 7, 7, 7, 7]
    assert sum(calls) == regression.CONFIRM_MAX_ROUNDS == 35


def test_more_rounds_reduce_sigma_before_classifying_an_anomaly() -> None:
    """A noisy median is deferred at 14 and trusted after its error shrinks."""
    batch = [1.72, 1.86, 1.99, 2.12, 2.25, 2.38, 2.52]

    assert regression._state(2.0, batch * 2, 5.0) is None
    assert regression._state(2.0, batch * 5, 5.0) == "regression"


def test_new_row_gets_the_full_bounded_measurement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A newly benchmarked grammar/row starts with a robust stored number."""
    calls: list[int] = []

    def sampled(
        selected: frozenset[tuple[str, str]] | None, rounds: int
    ) -> dict[tuple[str, str], list[float]]:
        assert selected == frozenset({VYX_LEX})
        calls.append(rounds)
        return {VYX_LEX: [1.5] * rounds}

    monkeypatch.setattr(regression, "sample", sampled)
    result = regression.confirmation(frozenset({VYX_LEX}), {})

    assert result == Confirmed({VYX_LEX: 1.5}, frozenset())
    assert calls == [35]
