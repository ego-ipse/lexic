"""Parent-side protocol for isolated benchmark worker processes.

**A job names a CHECKOUT ROOT, not a source directory.** Each revision's own
worker runs from that revision's tree, with its own ``tools`` and ``src`` first
on the path. This is what lets a cross-version A/B survive a public rename: the
row definition is held constant by NAME, and each arm's code is its own. Running
a historical revision with its historical benchmark measures that baseline; it
is not support for that revision's API in current Lexic.

**One process owns the machine for its complete lifecycle** — start, build,
validate, warm, time, close, exit — before the next one starts. There is no
preparation cohort. A worker that is merely "not yet timed" still compiles
grammars, runs fidelity parses and holds artefacts and pools, and doing that
beside a timed parse contaminates cache, allocator and thermal state. There is
no exemption for untimed benchmark work.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import NamedTuple

from tools.benchmark.measurement.contract import Json, RowResult, read_result


class RowRequest(NamedTuple):
    """Independent dimensions of one exact isolated row request."""

    grammar: str
    engine: str
    rounds: int
    cores: int | None
    full: bool


class Job(NamedTuple):
    """A uniquely labelled exact-row request against one checkout.

    :ivar label: The unique name this job's result is filed under.
    :ivar request: What to measure.
    :ivar root: The checkout root the worker runs from. Its ``tools`` and
        ``src`` are what the worker imports.
    """

    label: str
    request: RowRequest
    root: Path


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


def _environment(request: RowRequest, root: Path) -> dict[str, str]:
    """Put this checkout's own ``tools`` and ``src`` first on the path.

    The root itself carries the ``tools`` package; ``root/src`` carries
    ``lexic``. Nothing of the parent's tree may precede them, or the worker
    would measure one revision's engine through another's harness.
    """
    environment = dict(os.environ)
    environment["LEXIC_BENCHMARK_GRAMMAR"] = request.grammar
    environment["PYTHONPATH"] = os.pathsep.join(
        (str(root / "src"), str(root), environment.get("PYTHONPATH", ""))
    ).rstrip(os.pathsep)
    return environment


def _decode(output: str, job: Job) -> Mapping[str, Json]:
    """Decode the final JSON line written by a worker."""
    lines = [line for line in output.splitlines() if line.strip()]
    if not lines:
        raise RuntimeError(f"benchmark worker returned nothing for {job.label}")
    decoded = json.loads(lines[-1])
    if not isinstance(decoded, dict):
        raise RuntimeError(f"benchmark worker wrote invalid JSON: {decoded!r}")
    return decoded


def run_job(job: Job) -> RowResult:
    """Run one worker to completion, alone, and decode its whole answer.

    The process starts, does everything it was asked, and exits before this
    function returns. No other benchmark process is running meanwhile.
    """
    completed = subprocess.run(
        _command(job.request),
        capture_output=True,
        text=True,
        check=False,
        cwd=str(job.root),
        env=_environment(job.request, job.root),
    )
    if completed.returncode:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise RuntimeError(f"benchmark worker failed for {job.label}: {detail}")
    return read_result(_decode(completed.stdout, job))


class ReportRow(NamedTuple):
    """One row's presentation payload — the cross-engine report's cell.

    The report and the acceptance gate ask different questions, so they carry
    different payloads. This one is for reading: many per-character samples, the
    warm-up account, and why a seat refused. It is never a gate.
    """

    samples: list[float]
    refusal: str | None
    mt_reason: str | None
    warmed: tuple[int, bool] | None
    cold_us_per_char: float | None
    charstream_share: float


def _numbers(value: Json) -> list[float]:
    """A JSON list of numbers, or a refusal — the report's sample vector."""
    if isinstance(value, str) or not isinstance(value, Sequence):
        raise RuntimeError(f"benchmark worker wrote no sample list: {value!r}")
    return [float(str(entry)) for entry in value]


def _warmed(value: Json) -> tuple[int, bool] | None:
    """The warm-up account a report row may carry, or ``None``."""
    if value is None:
        return None
    if isinstance(value, str) or not isinstance(value, Sequence):
        raise RuntimeError(f"benchmark worker wrote no warm-up pair: {value!r}")
    count, hit = value
    return int(str(count)), bool(hit)


def _report_row(payload: Mapping[str, Json]) -> ReportRow:
    """Decode one row's presentation payload."""
    refusal = payload.get("refusal")
    if refusal is not None:
        return ReportRow([], str(refusal), None, None, None, 0.0)
    cold = payload.get("cold_us_per_char")
    reason = payload.get("mt_reason")
    return ReportRow(
        _numbers(payload["samples"]),
        None,
        str(reason) if reason else None,
        _warmed(payload.get("warmed")),
        float(str(cold)) if cold is not None else None,
        float(str(payload["charstream_share"])),
    )


def run_report_row(
    request: RowRequest, root: Path, *, noise: bool = False
) -> ReportRow:
    """Measure one presentation row in a fresh process that owns the machine."""
    command = [*_command(request), "--report"]
    if noise:
        command.append("--noise")
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
        cwd=str(root),
        env=_environment(request, root),
    )
    if completed.returncode:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise RuntimeError(
            f"benchmark worker failed for {request.grammar}/{request.engine}: {detail}"
        )
    lines = [line for line in completed.stdout.splitlines() if line.strip()]
    if not lines:
        raise RuntimeError(
            f"benchmark worker returned nothing for {request.grammar}/{request.engine}"
        )
    return _report_row(json.loads(lines[-1]))


def noise_floor(request: RowRequest, root: Path) -> float:
    """The report's same-engine control, in its own fresh process."""
    command = [*_command(request), "--report", "--noise"]
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
        cwd=str(root),
        env=_environment(request, root),
    )
    if completed.returncode:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise RuntimeError(f"benchmark noise floor failed: {detail}")
    lines = [line for line in completed.stdout.splitlines() if line.strip()]
    return float(json.loads(lines[-1])["noise_floor"])


def _path_environment(root: Path) -> dict[str, str]:
    """This checkout's own ``tools`` and ``src`` first, with no row selected."""
    environment = dict(os.environ)
    environment.pop("LEXIC_BENCHMARK_GRAMMAR", None)
    environment["PYTHONPATH"] = os.pathsep.join(
        (str(root / "src"), str(root), environment.get("PYTHONPATH", ""))
    ).rstrip(os.pathsep)
    return environment


def run_roster(root: Path) -> tuple[tuple[str, str], ...]:
    """Ask one checkout which rows it can measure, in its own process.

    :param root: The checkout root to interrogate.
    :returns: Its ``(grammar, row)`` pairs.
    :raises RuntimeError: If that tree cannot report a roster at all.
    """
    completed = subprocess.run(
        [sys.executable, "-m", "tools.benchmark.execution.roster"],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(root),
        env=_path_environment(root),
    )
    if completed.returncode:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise RuntimeError(f"benchmark roster failed for {root}: {detail}")
    lines = [line for line in completed.stdout.splitlines() if line.strip()]
    payload = json.loads(lines[-1])
    rows = payload["rows"]
    return tuple((str(grammar), str(row)) for grammar, row in rows)


def run_jobs(jobs: tuple[Job, ...]) -> dict[str, RowResult]:
    """Run every job strictly one at a time, in the order given.

    The order is the caller's, because alternation is a measurement decision:
    which arm goes first must flip between pairs, and the control's order must
    flip independently of the candidate's.
    """
    labels = [job.label for job in jobs]
    if len(set(labels)) != len(labels):
        raise ValueError("benchmark job labels must be unique")
    return {job.label: run_job(job) for job in jobs}
