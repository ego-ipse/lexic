"""Tests for fresh-process benchmark row isolation."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

from tools.benchmark import bench as benchmark
from tools.benchmark.bench import EngineBuild
from tools.benchmark.cases.grammars import Bench
from tools.benchmark.execution import isolation, worker
from tools.benchmark.execution.isolation import RowRequest


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

    built = benchmark.one_engine(bench, "lexic-lex-ns", 8, False)

    assert built.parse is parse
    assert built.document == "small"
    assert seen == [frozenset({"lexic-lex-ns"})]


def test_worker_samples_only_the_exact_build_it_was_given(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The worker protocol cannot silently expand one row into a roster."""

    def parse(_text: str) -> object:
        return object()

    bench = cast(
        Bench, SimpleNamespace(name="json", full="full", lexical=(), non_semantic=())
    )
    monkeypatch.setattr(
        worker,
        "one_engine",
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

    result = worker.report_payload(bench, "lexic-pda", 3, 8, False)

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
        assert environment["PYTHONPATH"].split(":", 2)[:2] == ["base/src", "base"]
        assert kwargs["cwd"] == "base"
        payload = {
            "samples": [1.2],
            "mt_reason": None,
            "warmed": None,
            "cold_us_per_char": None,
            "charstream_share": 0.0,
        }
        return subprocess.CompletedProcess(command, 0, json.dumps(payload), "")

    monkeypatch.setattr(isolation.subprocess, "run", run)

    result = isolation.run_report_row(
        RowRequest("vyx", "lexic-mt", 7, 8, False), Path("base")
    )

    assert result.samples == [1.2]
    command = seen[0]
    assert command[command.index("--grammar") + 1] == "vyx"
    assert command[command.index("--engine") + 1] == "lexic-mt"
    assert command[command.index("--rounds") + 1] == "7"
    assert command[command.index("--cores") + 1] == "8"


def test_a_job_runs_from_its_own_checkout_root(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Each revision's worker imports ITS tools and ITS src, not the parent's."""
    seen: dict[str, object] = {}

    def run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        seen.update(kwargs)
        seen["command"] = command
        payload = {"refusal": "not measured here"}
        return subprocess.CompletedProcess(command, 0, json.dumps(payload), "")

    monkeypatch.setattr(isolation.subprocess, "run", run)

    isolation.run_job(
        isolation.Job(
            "vyx/lexic-pda/base",
            RowRequest("vyx", "lexic-pda", 5, None, False),
            Path("/tmp/other-tree"),
        )
    )

    environment = seen["env"]
    assert isinstance(environment, dict)
    assert seen["cwd"] == "/tmp/other-tree"
    assert environment["PYTHONPATH"].split(":", 2)[:2] == [
        "/tmp/other-tree/src",
        "/tmp/other-tree",
    ]
