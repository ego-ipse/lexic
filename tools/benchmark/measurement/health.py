"""Same-tree execution health — what splitting does, per core count, HERE.

This is a DIFFERENT question from the A/B, and mixing them is what let a
pre-existing parallel loss read as a change. Change attribution asks "is head
slower than base"; execution health asks "does this tree's AUTO policy pick well
among the core counts it was measured against". A row can pass the first and
fail the second, and both facts matter.

Every core count parses ONE identical full document, one complete process at a
time, so the numbers share an axis exactly. There is no per-character
normalisation across two documents.

    uv run python -m tools.benchmark.measurement.health
    uv run python -m tools.benchmark.measurement.health --only json csv

If AUTO loses after a clean run, the answer is to fix policy, planning, parsing
or stitch duplication. It is not to raise the chunk floor or drop the row.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path
from typing import NamedTuple

from tools.benchmark.execution.isolation import Job, RowRequest, run_job, run_roster

CORE_COUNTS = (1, 2, 4, 8, 16)
"""The requested worker counts, beside AUTO."""

AUTO = 0
"""Lexic's own spelling for "decide the worker count yourself"."""

ROUNDS = 5
"""Inner passes reduced to one process-level observation."""

MT_ROW = "lexic-mt"
"""The row whose whole subject is whether splitting one document pays."""


class Reading(NamedTuple):
    """One core count's answer on one grammar.

    :ivar cores: What was requested; 0 is AUTO.
    :ivar wall: Seconds of latency — the result a split is claimed for.
    :ivar cpu: Aggregate process CPU seconds across workers.
    :ivar engaged: Whether the split actually ran.
    :ivar effective: Workers it occupied.
    :ivar document_bytes: The one document every row here parsed.
    """

    cores: int
    wall: float
    cpu: float
    engaged: bool | None
    effective: int
    document_bytes: int


def _read(root: Path, grammar: str, cores: int) -> Reading:
    """Measure one grammar at one core count, in a process of its own."""
    job = Job(
        f"{grammar}/{MT_ROW}/cores-{cores}",
        RowRequest(grammar, MT_ROW, ROUNDS, cores, True),
        root,
    )
    result = run_job(job)
    if result.refusal is not None or result.contract is None:
        raise ValueError(f"{grammar} at cores={cores}: {result.refusal}")
    observation = result.observations[0]
    return Reading(
        cores,
        observation.wall,
        observation.cpu,
        observation.engaged,
        observation.effective_workers,
        result.contract.document_bytes,
    )


def _table(grammar: str, readings: Sequence[Reading]) -> None:
    """Print one grammar's core-count table, speedups relative to one worker."""
    single = next((r for r in readings if r.cores == 1), None)
    print(f"\n─── {grammar} · {readings[0].document_bytes} bytes · one document")
    print(
        f"{'cores':>6}  {'wall ms':>9}  {'cpu ms':>9}  {'cpu/byte ns':>11}  "
        f"{'speedup':>7}  engaged"
    )
    for reading in readings:
        label = "AUTO" if reading.cores == AUTO else str(reading.cores)
        speedup = single.wall / reading.wall if single and reading.wall else 0.0
        engaged = "-" if reading.engaged is None else str(reading.engaged).lower()
        print(
            f"{label:>6}  {reading.wall * 1e3:9.3f}  {reading.cpu * 1e3:9.3f}  "
            f"{reading.cpu / reading.document_bytes * 1e9:11.1f}  "
            f"{speedup:7.2f}  {engaged}"
        )


CPU_TOLERANCE = 1.2
"""How much more total CPU AUTO may spend than the best fixed count.

Threading buys latency with CPU, so some overhead is the price of the win. Well
past that, a policy is buying nothing: the same document finishes no sooner and
the machine does half as much other work. Twenty percent is the line.
"""


def verdict(grammar: str, readings: Sequence[Reading]) -> str | None:
    """Whether AUTO earned its threading on this grammar, or why not.

    Beating ONE worker is not the bar. The core counts are all measured, so the
    question AUTO has to answer is whether it picked well among them — a policy
    that takes every logical CPU and pays 1.8x the CPU of half as many, for no
    latency, has lost even though it beat the sequential row.
    """
    single = next((r for r in readings if r.cores == 1), None)
    auto = next((r for r in readings if r.cores == AUTO), None)
    if single is None or auto is None:
        return f"{grammar}: no single-worker or AUTO reading to compare"
    if auto.engaged is False:
        return None
    if auto.wall >= single.wall:
        return (
            f"{grammar}: AUTO is not faster than one worker "
            f"({auto.wall * 1e3:.3f} ms vs {single.wall * 1e3:.3f} ms) "
            f"while spending {auto.cpu / single.cpu:.2f}x the CPU"
        )
    fixed = [reading for reading in readings if reading.cores != AUTO]
    best = min(fixed, key=lambda reading: reading.wall)
    if auto.wall > best.wall and auto.cpu > best.cpu * CPU_TOLERANCE:
        return (
            f"{grammar}: AUTO is slower than cores={best.cores} "
            f"({auto.wall * 1e3:.3f} ms vs {best.wall * 1e3:.3f} ms) AND spends "
            f"{auto.cpu / best.cpu:.2f}x its CPU "
            f"({auto.cpu / auto.document_bytes * 1e9:.0f} vs "
            f"{best.cpu / best.document_bytes * 1e9:.0f} ns/byte)"
        )
    return None


def main(argv: Sequence[str] | None = None) -> int:
    """Report execution health for every eligible split shape."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--only", nargs="*")
    args = parser.parse_args(argv)

    grammars = sorted({grammar for grammar, _row in run_roster(args.root)})
    if args.only:
        grammars = [name for name in grammars if name in set(args.only)]
    print(
        f"same-tree execution health: {len(grammars)} grammars, "
        f"cores {'/'.join(str(n) for n in CORE_COUNTS)}/AUTO, "
        f"one process at a time, one identical full document"
    )
    losses: list[str] = []
    for grammar in grammars:
        readings = [_read(args.root, grammar, cores) for cores in (*CORE_COUNTS, AUTO)]
        _table(grammar, readings)
        loss = verdict(grammar, readings)
        if loss is not None:
            losses.append(loss)
    if losses:
        print(f"\n{len(losses)} grammar(s) where AUTO does not pay:")
        for loss in losses:
            print(f"  {loss}")
        return 1
    print("\nAUTO pays, or honestly declines, on every eligible shape")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
