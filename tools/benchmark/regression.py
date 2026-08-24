"""Ratchet Lexic's isolated benchmark rows and reject confirmed regressions.

The pre-commit hook measures only Lexic, one exact grammar/engine pair per
fresh interpreter. A value more than five percent from its checked-in record
gets bounded adaptive confirmation. Confirmation aggregates every sample,
starts deciding after 14 rounds, and stops after 35; it never selects a lucky
batch. If the aggregate interval still crosses a decision boundary at the
limit, the check is inconclusive and blocks without changing the record.

An intentional slowdown is made explicit with::

    uv run python -m tools.benchmark.regression --accept-regression

Only a statistically confirmed slowdown can be accepted. The resulting JSON
diff is the reviewable acceptance.
"""

from __future__ import annotations

import argparse
import json
import math
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import NamedTuple

from tools.benchmark.bench import LEXIC_ROWS, MT_ROWS, _mt_cores
from tools.benchmark.grammars import BENCHES
from tools.benchmark.isolation import run_row

DEFAULT_ROUNDS = 7
CONFIRM_BATCH_ROUNDS = DEFAULT_ROUNDS
CONFIRM_MIN_ROUNDS = DEFAULT_ROUNDS * 2
CONFIRM_MAX_ROUNDS = DEFAULT_ROUNDS * 5
"""Bounds for targeted sequential sampling of an anomalous first pass."""

DEFAULT_THRESHOLD = 5.0
BASELINE = Path(__file__).with_name("lexic_baseline.json")

Key = tuple[str, str]
Values = dict[Key, float]
Samples = dict[Key, list[float]]


class Confirmed(NamedTuple):
    """Resolved confirmation medians and rows that exhausted the bound."""

    values: Values
    inconclusive: frozenset[Key]


Repeat = Callable[[frozenset[Key]], Confirmed]


class Outcome(NamedTuple):
    """A proposed baseline and the rows that must block or be accepted."""

    baseline: Values
    regressions: dict[Key, tuple[float, float]]
    inconclusive: frozenset[Key]


def _above(target: float, value: float, threshold: float) -> bool:
    """Whether ``value`` is slower than ``target`` by more than threshold."""
    return value > target * (1.0 + threshold / 100.0)


def _below(target: float, value: float, threshold: float) -> bool:
    """Whether ``value`` is faster than ``target`` by more than threshold."""
    return value < target * (1.0 - threshold / 100.0)


def assess(
    baseline: Values,
    first: Values,
    repeat: Repeat,
    *,
    threshold: float = DEFAULT_THRESHOLD,
    accept_regression: bool = False,
) -> Outcome:
    """Compare the isolated first pass and confirm only changed/new rows."""
    changed = {
        key
        for key, value in first.items()
        if key in baseline
        and (
            _above(baseline[key], value, threshold)
            or _below(baseline[key], value, threshold)
        )
    }
    candidates = frozenset(changed | (first.keys() - baseline.keys()))
    confirmed = repeat(candidates) if candidates else Confirmed({}, frozenset())
    missing = candidates - confirmed.values.keys() - confirmed.inconclusive
    if missing:
        raise ValueError(f"confirmation omitted benchmark rows: {sorted(missing)}")
    overlap = confirmed.values.keys() & confirmed.inconclusive
    if overlap:
        raise ValueError(
            f"confirmation both resolved and omitted rows: {sorted(overlap)}"
        )

    regressions = {
        key: (baseline[key], confirmed.values[key])
        for key in candidates
        if key in baseline
        and key in confirmed.values
        and _above(baseline[key], confirmed.values[key], threshold)
    }
    updated = dict(baseline)
    for key, value in confirmed.values.items():
        if key not in baseline or _below(baseline[key], value, threshold):
            updated[key] = value
    if accept_regression:
        for key, (_old, value) in regressions.items():
            updated[key] = value
    return Outcome(updated, regressions, confirmed.inconclusive)


def _active_keys() -> frozenset[Key]:
    """Every Lexic row runnable on this interpreter; never a competitor row."""
    cores = _mt_cores(None)
    rows = LEXIC_ROWS if cores is not None else LEXIC_ROWS - MT_ROWS
    return frozenset((bench.name, row) for bench in BENCHES for row in rows)


def sample(keys: frozenset[Key] | None, rounds: int) -> Samples:
    """Sample all active Lexic rows, or exactly the requested row processes."""
    selected = _active_keys() if keys is None else keys
    active = _active_keys()
    unavailable = selected - active
    if unavailable:
        raise ValueError(f"benchmark rows are not active: {sorted(unavailable)}")
    cores = _mt_cores(None)
    measured: Samples = {}
    for grammar, row in sorted(selected):
        result = run_row(grammar, row, rounds, cores, False)
        if result.refusal is not None:
            raise ValueError(f"benchmark row {grammar}/{row} refused: {result.refusal}")
        if not result.samples:
            raise ValueError(f"benchmark row {grammar}/{row} returned no samples")
        measured[(grammar, row)] = result.samples
    return measured


def _median(values: Sequence[float]) -> float:
    """Return the benchmark's upper median for one row's samples."""
    ordered = sorted(values)
    return ordered[len(ordered) // 2]


def _median_interval(values: Sequence[float]) -> tuple[float, float]:
    """Approximate a distribution-free 95% interval for the sample median."""
    ordered = sorted(values)
    middle = (len(ordered) - 1) / 2
    radius = math.ceil(0.98 * math.sqrt(len(ordered)))
    lower = max(0, math.floor(middle - radius))
    upper = min(len(ordered) - 1, math.ceil(middle + radius))
    return ordered[lower], ordered[upper]


def _state(target: float, values: Sequence[float], threshold: float) -> str | None:
    """Classify an aggregate interval, or leave a boundary crossing open."""
    lower, upper = _median_interval(values)
    fast_edge = target * (1.0 - threshold / 100.0)
    slow_edge = target * (1.0 + threshold / 100.0)
    if lower > slow_edge:
        return "regression"
    if upper < fast_edge:
        return "improvement"
    if lower >= fast_edge and upper <= slow_edge:
        return "noise"
    return None


def measure(keys: frozenset[Key] | None, rounds: int = DEFAULT_ROUNDS) -> Values:
    """Measure all active Lexic rows, or exactly the requested pairs."""
    return {key: _median(values) for key, values in sample(keys, rounds).items()}


def confirmation(
    keys: frozenset[Key],
    baseline: Values,
    threshold: float = DEFAULT_THRESHOLD,
) -> Confirmed:
    """Aggregate bounded exact-row batches until each interval resolves."""
    existing = keys & baseline.keys()
    new = keys - baseline.keys()
    accumulated: Samples = {key: [] for key in existing}
    resolved: Values = {}
    pending = frozenset(existing)
    rounds = 0
    while pending and rounds < CONFIRM_MAX_ROUNDS:
        batch = min(CONFIRM_BATCH_ROUNDS, CONFIRM_MAX_ROUNDS - rounds)
        for key in sorted(pending):
            observed = sample(frozenset({key}), batch)
            if observed.keys() != {key}:
                raise ValueError(f"confirmation omitted benchmark row: {key}")
            accumulated[key].extend(observed[key])
        rounds += batch
        if rounds < CONFIRM_MIN_ROUNDS:
            continue
        next_pending = set()
        for key in pending:
            state = _state(baseline[key], accumulated[key], threshold)
            if state is None:
                next_pending.add(key)
            else:
                resolved[key] = _median(accumulated[key])
        pending = frozenset(next_pending)

    # New rows have no decision boundary. Give each the full bounded sample so
    # their first stored target is not a seven-round outlier.
    for key in sorted(new):
        observed = sample(frozenset({key}), CONFIRM_MAX_ROUNDS)
        if observed.keys() != {key}:
            raise ValueError(f"confirmation omitted benchmark row: {key}")
        resolved[key] = _median(observed[key])
    return Confirmed(resolved, pending)


def load(path: Path = BASELINE) -> Values:
    """Read the nested checked-in JSON record into flat measurement keys."""
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema") != 1:
        raise ValueError(f"unsupported benchmark baseline schema in {path}")
    return {
        (grammar, row): float(value)
        for grammar, rows in payload["values"].items()
        for row, value in rows.items()
    }


def save(values: Values, path: Path = BASELINE) -> None:
    """Write a deterministic, reviewable nested JSON benchmark record."""
    nested: dict[str, dict[str, float]] = {}
    for (grammar, row), value in sorted(values.items()):
        nested.setdefault(grammar, {})[row] = round(value, 6)
    payload = {
        "schema": 1,
        "unit": "microseconds_per_character",
        "rounds": DEFAULT_ROUNDS,
        "confirmation_rounds": {
            "batch": CONFIRM_BATCH_ROUNDS,
            "minimum": CONFIRM_MIN_ROUNDS,
            "maximum": CONFIRM_MAX_ROUNDS,
        },
        "threshold_percent": DEFAULT_THRESHOLD,
        "values": nested,
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _change(old: float, new: float) -> float:
    """Signed percentage change, where positive means slower."""
    return (new - old) / old * 100.0


def main(argv: Sequence[str] | None = None) -> int:
    """Run the ratchet and return non-zero for unsafe or unresolved rows."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--accept-regression",
        action="store_true",
        help="raise the stored targets to statistically confirmed slower values",
    )
    args = parser.parse_args(argv)

    before = load()
    print(
        f"lexic benchmark guard: isolated first pass ({DEFAULT_ROUNDS} rounds per row)"
    )
    first = measure(None)

    def confirm(keys: frozenset[Key]) -> Confirmed:
        labels = ", ".join(f"{grammar}/{row}" for grammar, row in sorted(keys))
        print(
            f"confirming new or >{DEFAULT_THRESHOLD:.0f}% change candidates only "
            f"(aggregate adaptive {CONFIRM_MIN_ROUNDS}-{CONFIRM_MAX_ROUNDS} "
            f"rounds): {labels}"
        )
        return confirmation(keys, before)

    outcome = assess(
        before,
        first,
        confirm,
        accept_regression=args.accept_regression,
    )
    if outcome.inconclusive:
        labels = ", ".join(
            f"{grammar}/{row}" for grammar, row in sorted(outcome.inconclusive)
        )
        print(
            f"benchmark confirmation remained inconclusive after "
            f"{CONFIRM_MAX_ROUNDS} rounds: {labels}"
        )
        print("record unchanged; rerun when the machine is quieter")
        return 1
    if outcome.regressions:
        for (grammar, row), (old, new) in sorted(outcome.regressions.items()):
            print(
                f"  {grammar}/{row}: {old:.6f} -> {new:.6f} ({_change(old, new):+.2f}%)"
            )
        if not args.accept_regression:
            print(
                "performance regression confirmed; rerun with "
                "--accept-regression only if it is intentional"
            )
            return 1
        print("accepted confirmed regressions in the stored record")
    if outcome.baseline != before:
        save(outcome.baseline)
        print(f"updated {BASELINE.relative_to(Path.cwd())}")
    if not outcome.regressions:
        print("no confirmed Lexic benchmark regressions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
