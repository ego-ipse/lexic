"""Tests for same-run base/head performance comparison."""

from __future__ import annotations

from pathlib import Path

import pytest

from tools.benchmark import compare
from tools.benchmark.regression import save

JSON_PDA: compare.Key = ("json", "lexic-pda")
VYX_LEX: compare.Key = ("vyx", "lexic-lex")


def test_pair_sampler_alternates_which_source_tree_runs_first(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Base/head order cannot become a fixed thermal advantage."""
    base = Path("base/src")
    head = Path("head/src")
    calls: list[tuple[compare.Key, Path]] = []

    def one(key: compare.Key, _rounds: int, source: Path) -> list[float]:
        calls.append((key, source))
        return [1.0 if source == base else 1.1]

    monkeypatch.setattr(compare, "_one", one)
    result = compare.sample_pair(frozenset({JSON_PDA, VYX_LEX}), 7, base, head)

    assert set(result) == {JSON_PDA, VYX_LEX}
    assert [source for _key, source in calls] == [base, head, head, base]


def test_confirmation_aggregates_two_exact_ab_batches_before_deciding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A stable slowdown is confirmed from 14 samples of each source tree."""
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
    ]


def test_baseline_increase_is_the_reviewable_ci_acceptance(tmp_path: Path) -> None:
    """Only a >5% checked-in target increase exempts its exact row."""
    base = tmp_path / "base.json"
    head = tmp_path / "head.json"
    save({JSON_PDA: 2.0, VYX_LEX: 3.0}, base)
    save({JSON_PDA: 2.2, VYX_LEX: 2.8}, head)

    assert compare.accepted_rows(base, head) == frozenset({JSON_PDA})


def test_a_base_without_a_baseline_is_an_explicit_bootstrap(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The first workflow installation has no historical rows to execute."""
    missing = tmp_path / "base.json"

    result = compare.main(["--base-source", "base/src", "--base-record", str(missing)])

    assert result == 0
    assert "base predates the checked-in Lexic baseline" in capsys.readouterr().out
