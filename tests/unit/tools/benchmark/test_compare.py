"""Tests for same-run base/head performance comparison."""

from __future__ import annotations

from pathlib import Path

import pytest

from tools.benchmark import compare
from tools.benchmark.execution.isolation import IsolatedRow, Job
from tools.benchmark.regression import save

JSON_PDA: compare.Key = ("json", "lexic-pda")
VYX_LEX: compare.Key = ("vyx", "lexic-lex")


def test_pair_sampler_alternates_which_source_tree_runs_first(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Base/head order cannot become a fixed thermal advantage."""
    base = Path("base/src")
    head = Path("head/src")
    seen: list[Job] = []

    def jobs(requests: list[Job]) -> dict[str, IsolatedRow]:
        seen.extend(requests)
        return {
            job.label: IsolatedRow(
                [1.0 if job.source_root == base else 1.1],
                None,
                None,
                None,
                None,
                0.0,
            )
            for job in requests
        }

    monkeypatch.setattr(compare, "run_jobs", jobs)
    result = compare.sample_pair(frozenset({JSON_PDA, VYX_LEX}), 7, base, head)

    assert set(result) == {JSON_PDA, VYX_LEX}
    assert [job.source_root for job in seen] == [base, head, head, base]


def test_confirmation_aggregates_three_exact_ab_batches_before_deciding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A stable slowdown is confirmed from 21 samples of each source tree."""
    calls: list[tuple[frozenset[compare.Key], int, bool]] = []

    def paired(
        keys: frozenset[compare.Key],
        rounds: int,
        _base: Path,
        _head: Path,
        *,
        flip: bool = False,
    ) -> compare.Pairs:
        calls.append((keys, rounds, flip))
        return {key: compare.Pair([2.0] * rounds, [2.2] * rounds) for key in keys}

    monkeypatch.setattr(compare, "sample_pair", paired)
    result = compare.confirm(frozenset({JSON_PDA}), Path("base/src"), Path("head/src"))

    assert result == {JSON_PDA: (2.0, 2.2)}
    assert calls == [
        (frozenset({JSON_PDA}), 7, False),
        (frozenset({JSON_PDA}), 7, True),
        (frozenset({JSON_PDA}), 7, False),
    ]


def test_baseline_increase_is_the_reviewable_ci_acceptance(tmp_path: Path) -> None:
    """Only a >5% checked-in target increase exempts its exact row."""
    base = tmp_path / "base.json"
    head = tmp_path / "head.json"
    save({JSON_PDA: 2.0, VYX_LEX: 3.0}, base)
    save({JSON_PDA: 2.2, VYX_LEX: 2.8}, head)

    assert compare.accepted_rows(base, head) == frozenset({JSON_PDA})


def test_a_base_without_a_record_still_runs_source_comparison(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A first-install PR has no exemptions, but its source is still measurable."""
    missing = tmp_path / "base.json"
    monkeypatch.setattr(compare, "_active_keys", lambda: frozenset({JSON_PDA}))
    monkeypatch.setattr(
        compare, "sample_pair", lambda *_args: {JSON_PDA: compare.Pair([2.0], [2.0])}
    )

    result = compare.main(["--base-source", "base/src", "--base-record", str(missing)])

    assert result == 0
