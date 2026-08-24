"""Parent-side protocol for one-row benchmark worker processes."""

from __future__ import annotations

import json
import os
import subprocess
import sys
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


def _payload(
    grammar: str,
    engine: str,
    rounds: int,
    cores: int | None,
    full: bool,
    *,
    noise: bool = False,
    source_root: Path | None = None,
) -> dict[str, Any]:
    """Execute one worker and decode its final JSON line."""
    command = [
        sys.executable,
        "-m",
        "tools.benchmark.worker",
        "--grammar",
        grammar,
        "--engine",
        engine,
        "--rounds",
        str(rounds),
    ]
    if cores is not None:
        command.extend(("--cores", str(cores)))
    if full:
        command.append("--full")
    if noise:
        command.append("--noise")
    environment = dict(os.environ)
    environment["LEXIC_BENCHMARK_GRAMMAR"] = grammar
    if source_root is not None:
        inherited = environment.get("PYTHONPATH")
        environment["PYTHONPATH"] = str(source_root) + (
            os.pathsep + inherited if inherited else ""
        )
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
        env=environment,
    )
    if completed.returncode:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise RuntimeError(
            f"isolated benchmark worker failed for {grammar}/{engine}: {detail}"
        )
    lines = [line for line in completed.stdout.splitlines() if line.strip()]
    if not lines:
        raise RuntimeError(f"isolated benchmark worker returned nothing for {engine}")
    decoded = json.loads(lines[-1])
    if not isinstance(decoded, dict):
        raise RuntimeError(
            f"isolated benchmark worker returned invalid JSON: {decoded!r}"
        )
    return cast(dict[str, Any], decoded)


def run_row(
    grammar: str,
    engine: str,
    rounds: int,
    cores: int | None,
    full: bool,
    *,
    source_root: Path | None = None,
) -> IsolatedRow:
    """Measure one row in a fresh interpreter process."""
    payload = _payload(
        grammar,
        engine,
        rounds,
        cores,
        full,
        source_root=source_root,
    )
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


def noise_floor(
    grammar: str,
    engine: str,
    rounds: int,
    cores: int | None,
    full: bool,
) -> float:
    """Measure the report's same-engine control in its own fresh process."""
    payload = _payload(grammar, engine, rounds, cores, full, noise=True)
    return float(payload["noise_floor"])
