"""Tests for fresh-process benchmark row isolation."""

from __future__ import annotations

import json
import subprocess
from types import SimpleNamespace
from typing import cast

import pytest

from tools.benchmark import bench as benchmark
from tools.benchmark import isolation, worker
from tools.benchmark.bench import EngineBuild
from tools.benchmark.grammars import Bench


def test_one_engine_requests_only_the_exact_lexic_variant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Filtering happens before construction, not after neighbouring rows run."""
    bench = cast(Bench, SimpleNamespace(name="json", corpus="small", full="large"))
    seen: list[frozenset[str] | None] = []

    def parse(_text: str) -> object:
        return object()

    def lexic(
        _bench: object, _cores: int | None, only: frozenset[str] | None = None
    ) -> tuple[dict[str, object], dict[str, object]]:
        seen.append(only)
        return {"lexic-lex-ns": parse}, {}

    monkeypatch.setattr(benchmark, "_lexic", lexic)
    monkeypatch.setattr(benchmark, "unfaithful", lambda *_args: None)

    built = benchmark._one_engine(bench, "lexic-lex-ns", 8, False)

    assert built.parse is parse
    assert built.document == "small"
    assert seen == [frozenset({"lexic-lex-ns"})]


def test_worker_samples_only_the_build_it_was_given(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The worker protocol cannot silently expand one row into a roster."""

    def parse(_text: str) -> object:
        return object()

    bench = SimpleNamespace(name="json", full="full")
    monkeypatch.setattr(worker, "BENCHES", (bench,))
    monkeypatch.setattr(
        worker,
        "_one_engine",
        lambda *_args: EngineBuild(parse, "corpus", None, None),
    )

    def timed(
        engines: dict[str, object], texts: dict[str, str], rounds: int
    ) -> dict[str, list[float]]:
        assert engines == {"lexic-pda": parse}
        assert texts == {"lexic-pda": "corpus"}
        assert rounds == 3
        return {"lexic-pda": [1.0, 1.1, 0.9]}

    monkeypatch.setattr(worker, "_interleaved", timed)

    result = worker.execute("json", "lexic-pda", 3, 8, False)

    assert result["samples"] == [1.0, 1.1, 0.9]


def test_parent_launches_a_fresh_worker_for_the_exact_pair(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The parent passes one grammar and one engine over the process boundary."""
    seen: list[list[str]] = []

    def run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        seen.append(command)
        environment = kwargs["env"]
        assert isinstance(environment, dict)
        assert environment["LEXIC_BENCHMARK_GRAMMAR"] == "vyx"
        payload = {
            "samples": [1.2],
            "mt_reason": None,
            "warmed": None,
            "cold_us_per_char": None,
            "charstream_share": 0.0,
        }
        return subprocess.CompletedProcess(command, 0, json.dumps(payload), "")

    monkeypatch.setattr(isolation.subprocess, "run", run)

    result = isolation.run_row("vyx", "lexic-mt", 7, 8, False)

    assert result.samples == [1.2]
    command = seen[0]
    assert command[command.index("--grammar") + 1] == "vyx"
    assert command[command.index("--engine") + 1] == "lexic-mt"
    assert command[command.index("--rounds") + 1] == "7"
    assert command[command.index("--cores") + 1] == "8"
