"""Compare two revisions on this machine, each running its own benchmark code.

**Row definitions are held constant by NAME; each arm's worker runs from its own
tree.** The older invariant — one harness held constant while Lexic is swapped
underneath it — cannot survive a public rename, because the harness must name
the API it drives. So each revision executes its own worker against its own
`src`, and what is held constant is the ROW: grammar, directives, document,
engine noun, core request. Running a historical revision with its historical
benchmark measures that baseline; it is not support for its API in current Lexic.

This module schedules and judges. It imports neither revision's Lexic nor either
revision's benchmark cases: it asks each tree for its roster and its numbers by
running that tree's code, and refuses two arms whose row contracts differ.

The gate is a paired, alternating comparison against a byte-identical control.
There is no fixed percentage allowance and no baseline exemption: what counts as
noise is measured on this machine, in this session, by running the SAME tree
against itself through the identical protocol.
"""

from __future__ import annotations

import argparse
import json
import math
from collections.abc import Sequence
from pathlib import Path
from statistics import median
from typing import NamedTuple

from tools.benchmark.measurement.contract import Observation, RowContract, RowResult
from tools.benchmark.execution.isolation import Job, RowRequest, run_job, run_roster

MIN_PAIRS = 5
MAX_PAIRS = 15
"""How many independent process pairs a verdict may cost.

Below the minimum nothing is decided. Above the maximum the evidence is
declared unresolved rather than forced into a median — a row that will not
settle is a fact about the measurement, not a licence to pick a number.
"""

CONFIDENCE_Z = 1.96
"""Two-sided 95% normal quantile — the predeclared interval."""

ROUNDS = 5
"""Inner passes reduced to one process-level observation.

Raising this narrows each observation but multiplies the run: at 15 the full
72-row gate did not finish two grammars in ten minutes, against forty for all
seventy-two here. The independent unit is the process either way, so the honest
lever for an unresolved row is a quieter machine, not a longer inner loop.
"""

MT_ROWS = frozenset({"lexic-mt", "lexic-mt-lex-ns"})
"""Rows whose primary clock is wall, because their work is on other threads."""


class Pairing(NamedTuple):
    """One row's paired candidate and control log ratios."""

    candidate: tuple[float, ...]
    control: tuple[float, ...]


class Verdict(NamedTuple):
    """One row's decision and the numbers behind it.

    :ivar row: ``grammar/name``.
    :ivar status: ``ok``, ``slower``, ``faster`` or ``unresolved``.
    :ivar ratio: Median head/base ratio; 1.0 is no change.
    :ivar low: Lower bound of the candidate's confidence interval, as a ratio.
    :ivar high: Upper bound, as a ratio.
    :ivar envelope: The control's upper bound, as a ratio — the noise this
        machine actually produced under the identical protocol.
    :ivar pairs: Independent process pairs behind the interval.
    :ivar clock: Which clock decided, ``cpu`` or ``wall``.
    """

    row: str
    status: str
    ratio: float
    low: float
    high: float
    envelope: float
    pairs: int
    clock: str


def primary_reading(observation: Observation, row: str) -> float:
    """The clock this row is judged on.

    Sequential rows are judged on CPU, which ignores time the process spent
    descheduled. A threaded row's result IS latency, so it is judged on wall —
    and its CPU is reported beside it, because a wall win paid for with far
    more total CPU is a different fact.
    """
    return observation.wall if row in MT_ROWS else observation.cpu


def _interval(ratios: Sequence[float]) -> tuple[float, float, float]:
    """Mean log ratio and its confidence bounds, in log space."""
    count = len(ratios)
    mean = sum(ratios) / count
    if count < 2:
        return mean, mean, mean
    variance = sum((value - mean) ** 2 for value in ratios) / (count - 1)
    error = math.sqrt(variance / count)
    return mean, mean - CONFIDENCE_Z * error, mean + CONFIDENCE_Z * error


def _envelope(control: Sequence[float]) -> float:
    """The control's upper log bound — what this machine calls no change.

    Built from the byte-identical pairs' own spread, so a quiet machine gets a
    tight envelope and a noisy one is honest about being noisy. A fixed
    percentage cannot do either.
    """
    if not control:
        return 0.0
    _mean, low, high = _interval(control)
    return max(abs(low), abs(high))


def decide(row: str, pairing: Pairing, clock: str) -> Verdict:
    """Judge one row's candidate interval against its control envelope."""
    mean, low, high = _interval(pairing.candidate)
    envelope = _envelope(pairing.control)
    verdict = Verdict(
        row,
        "unresolved",
        math.exp(mean),
        math.exp(low),
        math.exp(high),
        math.exp(envelope),
        len(pairing.candidate),
        clock,
    )
    if low > envelope:
        return verdict._replace(status="slower")
    if high < -envelope:
        return verdict._replace(status="faster")
    if high <= envelope and low >= -envelope:
        return verdict._replace(status="ok")
    return verdict


def require(result: RowResult, label: str) -> tuple[RowContract, Observation]:
    """One arm's contract and observation, or a refusal that stops the run."""
    if result.refusal is not None:
        raise ValueError(f"{label}: row refused: {result.refusal}")
    if result.contract is None or not result.observations:
        raise ValueError(f"{label}: row produced no observation")
    return result.contract, result.observations[0]


def agree(base: RowContract, head: RowContract, row: str) -> None:
    """Refuse two arms that did not measure the same row, before timing counts."""
    fields = base.mismatch(head)
    if not fields:
        return
    detail = ", ".join(
        f"{field}: base={getattr(base, field)!r} head={getattr(head, field)!r}"
        for field in fields
    )
    raise ValueError(f"{row}: base and head row contracts differ — {detail}")


def _job(root: Path, grammar: str, row: str, cores: int, side: str) -> Job:
    """One exact-row job against one checkout."""
    return Job(
        f"{grammar}/{row}/{side}",
        RowRequest(grammar, row, ROUNDS, cores if row in MT_ROWS else None, False),
        root,
    )


def _pair(first: Job, second: Job, row: str) -> tuple[float, float]:
    """Run one ordered pair to completion and return both primary readings."""
    results = (run_job(first), run_job(second))
    contracts = tuple(
        require(result, job.label)
        for result, job in zip(results, (first, second), strict=True)
    )
    agree(contracts[0][0], contracts[1][0], row)
    return primary_reading(contracts[0][1], row), primary_reading(contracts[1][1], row)


class Arms(NamedTuple):
    """One row's two checkouts and the core count it is measured at."""

    base: Path
    head: Path
    cores: int


def _ratio(numerator: Job, denominator: Job, numerator_first: bool, row: str) -> float:
    """Log ratio of ``numerator`` over ``denominator``.

    ``numerator_first`` says which of the two processes RUNS first. Flipping it
    between pairs is what stops the first slot's cache and thermal state from
    becoming a fixed advantage for whichever arm always occupies it.
    """
    pair = (numerator, denominator) if numerator_first else (denominator, numerator)
    readings = dict(zip((job.label for job in pair), _pair(*pair, row), strict=True))
    return math.log(readings[numerator.label] / readings[denominator.label])


def sample(arms: Arms, grammar: str, row: str, pairs: int) -> Pairing:
    """Collect ``pairs`` candidate and control ratios for one row.

    Each pair is two complete process lifecycles, one after the other. The
    candidate flips which arm runs first on every pair. The control's two
    processes are the same code, so what flips there is which one is on top of
    the ratio — on its own schedule, so slot drift averages out instead of
    cancelling identically in both and hiding itself.
    """
    candidate: list[float] = []
    control: list[float] = []
    for index in range(pairs):
        head_job = _job(arms.head, grammar, row, arms.cores, "head")
        base_job = _job(arms.base, grammar, row, arms.cores, "base")
        candidate.append(_ratio(head_job, base_job, index % 2 == 0, row))
        left = _job(arms.head, grammar, row, arms.cores, "control-a")
        right = _job(arms.head, grammar, row, arms.cores, "control-b")
        swapped = index % 3 == 2
        control.append(
            _ratio(right, left, True, row)
            if swapped
            else _ratio(left, right, True, row)
        )
    return Pairing(tuple(candidate), tuple(control))


def rosters(base: Path, head: Path) -> tuple[tuple[str, str], ...]:
    """The rows both trees claim, refusing any difference by name."""
    base_rows = frozenset(run_roster(base))
    head_rows = frozenset(run_roster(head))
    if base_rows != head_rows:
        missing = sorted(f"{g}/{r}" for g, r in base_rows ^ head_rows)
        raise ValueError(
            f"the two trees do not define the same benchmark rows: {missing}"
        )
    return tuple(sorted(head_rows))


GROWS = frozenset({"unresolved", "slower"})
"""Verdicts that must be re-earned rather than banked at first sight.

`unresolved` grows for the obvious reason: it has not decided. `slower` grows
because stopping the moment a threshold is first crossed is optional stopping,
and optional stopping manufactures regressions — a row can tip at pair six on
noise and be inside the envelope again by pair fifteen. A measured regression is
the most expensive verdict this gate issues, so it is the one that must survive
the whole pair budget. Growing can only add evidence; it never softens a real
slowdown, which stays slower with a tighter interval.
"""


def grow(arms: Arms, grammar: str, row: str) -> tuple[Verdict, Pairing]:
    """Sample a row until it settles inside the envelope, or the bound runs out."""
    clock = "wall" if row in MT_ROWS else "cpu"
    label = f"{grammar}/{row}"
    pairing = sample(arms, grammar, row, MIN_PAIRS)
    verdict = decide(label, pairing, clock)
    while verdict.status in GROWS and len(pairing.candidate) < MAX_PAIRS:
        extra = sample(arms, grammar, row, 1)
        pairing = Pairing(
            pairing.candidate + extra.candidate, pairing.control + extra.control
        )
        verdict = decide(label, pairing, clock)
    return verdict, pairing


def _report(verdicts: Sequence[Verdict]) -> None:
    """Print every row, its interval, and the envelope it was judged against."""
    width = max(len(verdict.row) for verdict in verdicts)
    print(
        f"{'row':{width}}  {'clock':>5}  {'ratio':>7}  {'ci low':>7}  "
        f"{'ci high':>7}  {'noise':>7}  {'pairs':>5}  status"
    )
    for verdict in sorted(verdicts, key=lambda entry: -entry.ratio):
        print(
            f"{verdict.row:{width}}  {verdict.clock:>5}  {verdict.ratio:7.4f}  "
            f"{verdict.low:7.4f}  {verdict.high:7.4f}  {verdict.envelope:7.4f}  "
            f"{verdict.pairs:5}  {verdict.status}"
        )


def main(argv: Sequence[str] | None = None) -> int:
    """Run the same-machine, per-tree A/B and judge every row."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-root", type=Path, required=True)
    parser.add_argument("--head-root", type=Path, default=Path.cwd())
    parser.add_argument("--cores", type=int, default=4)
    parser.add_argument("--only", nargs="*")
    parser.add_argument("--json", type=Path)
    args = parser.parse_args(argv)

    rows = rosters(args.base_root, args.head_root)
    if args.only:
        wanted = frozenset(args.only)
        rows = tuple(row for row in rows if row[1] in wanted or row[0] in wanted)
    print(
        f"per-tree Lexic A/B: {len(rows)} rows, {MIN_PAIRS}-{MAX_PAIRS} "
        f"process pairs each, one process at a time"
    )
    print(f"base {args.base_root}\nhead {args.head_root}")
    arms = Arms(args.base_root, args.head_root, args.cores)
    verdicts: list[Verdict] = []
    samples: dict[str, Pairing] = {}
    for grammar, row in rows:
        verdict, pairing = grow(arms, grammar, row)
        verdicts.append(verdict)
        samples[verdict.row] = pairing
        print(f"  {verdict.row}: {verdict.status} ({verdict.ratio:.4f}x)", flush=True)
    print()
    _report(verdicts)
    if args.json:
        args.json.write_text(
            json.dumps(
                {
                    "verdicts": [verdict._asdict() for verdict in verdicts],
                    "log_ratios": {
                        row: {
                            "candidate": list(p.candidate),
                            "control": list(p.control),
                        }
                        for row, p in samples.items()
                    },
                },
                indent=1,
            ),
            encoding="utf-8",
        )
    slower = [verdict for verdict in verdicts if verdict.status == "slower"]
    unresolved = [verdict for verdict in verdicts if verdict.status == "unresolved"]
    control = median(
        [value for pairing in samples.values() for value in pairing.control] or [0.0]
    )
    print(f"\ncontrol median log ratio: {math.exp(control):.4f}x")
    if slower:
        print(f"\n{len(slower)} row(s) slower than this machine's noise envelope:")
        for verdict in slower:
            print(f"  {verdict.row}: {verdict.ratio:.4f}x on {verdict.clock}")
        return 1
    if unresolved:
        print(f"\n{len(unresolved)} row(s) unresolved after {MAX_PAIRS} pairs:")
        for verdict in unresolved:
            print(f"  {verdict.row}: {verdict.low:.4f}..{verdict.high:.4f}")
        return 1
    print("\nevery row resolved, and none is slower than this machine's envelope")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
