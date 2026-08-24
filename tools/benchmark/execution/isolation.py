"""Parent-side protocol for isolated benchmark worker processes."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Sequence
from contextlib import ExitStack
from pathlib import Path
from typing import Any, NamedTuple, cast


class IsolatedRow(NamedTuple):
    """One exact row's samples and reporting metadata."""

    samples: list[float]
    refusal: str | None
    mt_reason: str | None
    warmed: tuple[int, bool] | None
    cold_us_per_char: float | None
    charstream_share: float


class RowRequest(NamedTuple):
    """Independent dimensions of one exact isolated row request."""

    grammar: str
    engine: str
    rounds: int
    cores: int | None
    full: bool


class Job(NamedTuple):
    """A uniquely labelled exact-row request, optionally against another tree."""

    label: str
    request: RowRequest
    source_root: Path | None = None


_PREPARE_WIDTH = min(os.cpu_count() or 1, 16)
"""Maximum untimed row preparations allowed to overlap."""


def _command(request: RowRequest) -> list[str]:
    """Build the reviewable command for one exact row worker."""
    command = [
        sys.executable,
        "-m",
        "tools.benchmark.execution.worker",
        "--grammar",
        request.grammar,
        "--engine",
        request.engine,
        "--rounds",
        str(request.rounds),
    ]
    if request.cores is not None:
        command.extend(("--cores", str(request.cores)))
    if request.full:
        command.append("--full")
    return command


def _environment(request: RowRequest, source_root: Path | None) -> dict[str, str]:
    """Restrict worker grammar construction and optionally select a source tree."""
    environment = dict(os.environ)
    environment["LEXIC_BENCHMARK_GRAMMAR"] = request.grammar
    if source_root is not None:
        inherited = environment.get("PYTHONPATH")
        environment["PYTHONPATH"] = str(source_root) + (
            os.pathsep + inherited if inherited else ""
        )
    return environment


def _decode(output: str, request: RowRequest) -> dict[str, Any]:
    """Decode the final JSON line written by a worker."""
    lines = [line for line in output.splitlines() if line.strip()]
    if not lines:
        raise RuntimeError(
            f"isolated benchmark worker returned nothing for "
            f"{request.grammar}/{request.engine}"
        )
    decoded = json.loads(lines[-1])
    if not isinstance(decoded, dict):
        raise RuntimeError(
            f"isolated benchmark worker returned invalid JSON: {decoded!r}"
        )
    return cast(dict[str, Any], decoded)


def _payload(
    request: RowRequest,
    *,
    noise: bool = False,
    source_root: Path | None = None,
) -> dict[str, Any]:
    """Execute one grammar worker and decode its final JSON line."""
    command = _command(request)
    if noise:
        command.append("--noise")
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
        env=_environment(request, source_root),
    )
    if completed.returncode:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise RuntimeError(
            f"isolated benchmark worker failed for "
            f"{request.grammar}/{request.engine}: {detail}"
        )
    return _decode(completed.stdout, request)


def _row(payload: dict[str, Any]) -> IsolatedRow:
    """Decode one row payload into the stable parent-side representation."""
    refusal = payload.get("refusal")
    if refusal is not None:
        return IsolatedRow([], str(refusal), None, None, None, 0.0)
    warmed = payload.get("warmed")
    return IsolatedRow(
        [float(value) for value in payload["samples"]],
        None,
        str(payload["mt_reason"]) if payload.get("mt_reason") else None,
        (int(warmed[0]), bool(warmed[1])) if warmed is not None else None,
        float(payload["cold_us_per_char"])
        if payload.get("cold_us_per_char") is not None
        else None,
        float(payload["charstream_share"]),
    )


def _prepared(jobs: Sequence[Job]) -> dict[str, IsolatedRow]:
    """Prepare one bounded cohort concurrently, then time it serially."""
    with ExitStack() as owned:
        processes: list[tuple[Job, subprocess.Popen[str]]] = []
        for job in jobs:
            process = owned.enter_context(
                subprocess.Popen(
                    [*_command(job.request), "--wait"],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    env=_environment(job.request, job.source_root),
                )
            )
            processes.append((job, process))
        for job, process in processes:
            ready = process.stdout.readline() if process.stdout is not None else ""
            if ready.strip() != '{"ready":true}':
                _output, error = process.communicate()
                detail = error.strip() or ready.strip()
                raise RuntimeError(
                    f"benchmark worker failed preparing {job.label}: {detail}"
                )
        measured: dict[str, IsolatedRow] = {}
        for job, process in processes:
            output, error = process.communicate("run\n")
            if process.returncode:
                detail = error.strip() or output.strip()
                raise RuntimeError(
                    f"benchmark worker failed timing {job.label}: {detail}"
                )
            measured[job.label] = _row(_decode(output, job.request))
        return measured


def run_jobs(jobs: Sequence[Job]) -> dict[str, IsolatedRow]:
    """Run exact rows with parallel preparation and uncontended measurement."""
    labels = [job.label for job in jobs]
    if len(set(labels)) != len(labels):
        raise ValueError("benchmark job labels must be unique")
    measured: dict[str, IsolatedRow] = {}
    for start in range(0, len(jobs), _PREPARE_WIDTH):
        measured.update(_prepared(jobs[start : start + _PREPARE_WIDTH]))
    return measured


def run_row(request: RowRequest, *, source_root: Path | None = None) -> IsolatedRow:
    """Measure one exact row in a fresh interpreter process."""
    return _row(_payload(request, source_root=source_root))


def noise_floor(
    request: RowRequest,
) -> float:
    """Measure the report's same-engine control in its own fresh process."""
    payload = _payload(request, noise=True)
    return float(payload["noise_floor"])
