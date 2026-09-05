"""Tests for fresh-process benchmark row isolation."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

from lexic.compile import compile_text
from tools.benchmark import bench as benchmark
from tools.benchmark import compare
from tools.benchmark.bench import EngineBuild
from tools.benchmark.cases.grammars import Bench
from tools.benchmark.execution import isolation, worker
from tools.benchmark.execution.isolation import RowRequest
from tools.benchmark.measurement import occupancy
from tools.benchmark.measurement.contract import (
    CLOCKS,
    PROTOCOL,
    Observation,
    RowContract,
)

CONTRACT = RowContract(
    PROTOCOL,
    "lexic-mt",
    "json",
    "abc123",
    (),
    (),
    "def456",
    2403,
    "full",
    "typed model",
    8,
    True,
    CLOCKS,
)
"""A well-formed contract for one threaded row."""


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


_LINES = 'root ::= line+\nline ::= [a-z0-9]* nl\nnl ::= "\\n"\n'
"""A terminated repetition whose split engages on any document long enough."""


def _lines(size: int) -> str:
    """A LINES document of at least ``size`` characters."""
    out: list[str] = []
    while sum(map(len, out)) < size:
        out.append(f"line{len(out)}\n")
    return "".join(out)


def test_effective_workers_is_observed_not_the_number_requested() -> None:
    """A request is not an occupancy, and the observation must say so.

    The policy clamps useful workers by document size — 2 KiB each — and cut
    selection can clamp them again, so a document asked for sixteen workers
    that only has room for eight occupies eight. Echoing the request would let
    two arms divide the same document differently and still compare.
    """
    compiled = compile_text(_LINES, cache_key="worker-occupancy")
    document = _lines(16 * 1024)

    seen = occupancy.declined_reason(compiled, document, 16)

    assert seen.declined is None, "the fixture must engage for this to mean anything"
    assert 1 < seen.workers <= len(document) // (2 * 1024)
    assert seen.workers < 16


def test_a_declined_split_reports_one_worker_and_says_why() -> None:
    """The row that did not thread reports the parse that actually ran."""
    compiled = compile_text(_LINES, cache_key="worker-occupancy-declined")

    seen = occupancy.declined_reason(compiled, _lines(64), 16)

    assert seen.declined is not None
    assert seen.workers == 1


def test_the_engagement_probe_reports_what_the_attempt_did(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The worker's observation carries the attempt's answer, not its request."""
    compiled = compile_text(_LINES, cache_key="worker-occupancy-probe")
    document = _lines(16 * 1024)
    built = EngineBuild(
        lambda text: compiled.parse(text, cores=1), document, None, compiled
    )

    seen = worker._engagement("lexic-mt", built, 16)

    assert seen is not None
    engaged, split, workers = worker._split_fields(seen)
    assert engaged is True
    assert split != ""
    assert 1 < workers < 16


def test_the_split_plan_is_stable_where_the_thread_count_is_not() -> None:
    """The identity field must survive the executor's own choices.

    A single attempt's unique-thread count is scheduling: thirty serial
    attempts against one artefact occupied eight workers twenty-eight times
    and seven twice. The carving those threads shared does not move, so it is
    the carving that says two arms did the same work.
    """
    compiled = compile_text(_LINES, cache_key="worker-plan-stability")
    document = _lines(16 * 1024)

    seen = [occupancy.declined_reason(compiled, document, 8) for _ in range(12)]

    assert all(one.declined is None for one in seen), "the fixture must engage"
    assert len({one.plan for one in seen}) == 1, "the derived plan moved"
    assert all(one.workers >= 1 for one in seen)


def test_a_different_carving_of_the_same_document_reports_a_different_plan() -> None:
    """A changed split plan must still be detectable, or the field says nothing.

    Fewer admitted workers is a different division of the same characters —
    exactly the difference the comparator exists to refuse — so it must not
    digest equal to the eight-way carving of the same text.
    """
    compiled = compile_text(_LINES, cache_key="worker-plan-differs")
    document = _lines(16 * 1024)

    wide = occupancy.declined_reason(compiled, document, 8)
    narrow = occupancy.declined_reason(compiled, document, 2)

    assert wide.declined is None and narrow.declined is None
    assert wide.plan != narrow.plan


def test_the_scheduler_alone_cannot_refuse_a_pair(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two arms differing only in observed occupancy still compare.

    This is the same-tree control pair the comparator would have rejected: it
    ran identical code on an identical document and was scheduled differently.
    """
    compiled = compile_text(_LINES, cache_key="worker-scheduling-only")
    document = _lines(16 * 1024)
    built = EngineBuild(
        lambda text: compiled.parse(text, cores=1), document, None, compiled
    )
    engaged, split, workers = worker._split_fields(
        worker._engagement("lexic-mt", built, 8)
    )
    observed = Observation(
        1.0, 1.0, "text", "shape", "accepted", engaged, split, workers
    )
    scheduled = observed._replace(effective_workers=workers - 1)

    assert (
        compare.comparable(
            compare.Arm("json/lexic-mt/base", CONTRACT, observed),
            compare.Arm("json/lexic-mt/head", CONTRACT, scheduled),
            "json/lexic-mt",
        )
        is None
    )

    with pytest.raises(ValueError, match="split_digest"):
        compare.comparable(
            compare.Arm("json/lexic-mt/base", CONTRACT, observed),
            compare.Arm(
                "json/lexic-mt/head", CONTRACT, observed._replace(split_digest="other")
            ),
            "json/lexic-mt",
        )
