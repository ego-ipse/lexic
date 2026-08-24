"""Compare base and head Lexic rows on the same machine for CI.

The HEAD benchmark harness and grammar corpus are held constant. Only the
``lexic`` package imported by each exact-row worker changes: once from the base
checkout's ``src`` and once from HEAD's. This makes a GitHub-hosted runner a
same-run A/B instrument instead of comparing its hardware to a laptop record.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path
from typing import NamedTuple

from tools.benchmark.bench import _mt_cores
from tools.benchmark.isolation import run_row
from tools.benchmark.regression import (
    CONFIRM_BATCH_ROUNDS,
    CONFIRM_MAX_ROUNDS,
    CONFIRM_MIN_ROUNDS,
    DEFAULT_ROUNDS,
    DEFAULT_THRESHOLD,
    Key,
    Values,
    _above,
    _active_keys,
    _median,
    _relative_uncertainty,
    load,
)


class Pair(NamedTuple):
    """Base and head samples for one exact grammar/engine pair."""

    base: list[float]
    head: list[float]


Pairs = dict[Key, Pair]


def _one(key: Key, rounds: int, source_root: Path) -> list[float]:
    """Measure one source tree through HEAD's exact-row worker harness."""
    grammar, row = key
    result = run_row(
        grammar,
        row,
        rounds,
        _mt_cores(None),
        False,
        source_root=source_root,
    )
    if result.refusal is not None:
        raise ValueError(f"{source_root}: {grammar}/{row} refused: {result.refusal}")
    if not result.samples:
        raise ValueError(f"{source_root}: {grammar}/{row} returned no samples")
    return result.samples


def sample_pair(
    keys: frozenset[Key],
    rounds: int,
    base_source: Path,
    head_source: Path,
    *,
    flip: bool = False,
) -> Pairs:
    """Measure exact base/head pairs, alternating which tree runs first."""
    measured: Pairs = {}
    for index, key in enumerate(sorted(keys)):
        head_first = bool(index % 2) is not flip
        if head_first:
            head = _one(key, rounds, head_source)
            base = _one(key, rounds, base_source)
        else:
            base = _one(key, rounds, base_source)
            head = _one(key, rounds, head_source)
        measured[key] = Pair(base, head)
    return measured


def medians(pairs: Pairs) -> tuple[Values, Values]:
    """Return base and head medians from paired sample populations."""
    return (
        {key: _median(pair.base) for key, pair in pairs.items()},
        {key: _median(pair.head) for key, pair in pairs.items()},
    )


def _pair_uncertainty(pair: Pair) -> float:
    """One-sigma relative error of a base/head ratio, in percent."""
    base = _relative_uncertainty(pair.base)
    head = _relative_uncertainty(pair.head)
    return (base * base + head * head) ** 0.5


def confirm(
    keys: frozenset[Key],
    base_source: Path,
    head_source: Path,
    threshold: float = DEFAULT_THRESHOLD,
) -> dict[Key, tuple[float, float]]:
    """Bounded adaptive A/B confirmation over every accumulated sample."""
    accumulated: dict[Key, Pair] = {key: Pair([], []) for key in keys}
    pending = keys
    rounds = 0
    batch_index = 0
    while pending and rounds < CONFIRM_MAX_ROUNDS:
        batch = min(CONFIRM_BATCH_ROUNDS, CONFIRM_MAX_ROUNDS - rounds)
        observed = sample_pair(
            pending,
            batch,
            base_source,
            head_source,
            flip=bool(batch_index % 2),
        )
        for key, pair in observed.items():
            accumulated[key].base.extend(pair.base)
            accumulated[key].head.extend(pair.head)
        rounds += batch
        batch_index += 1
        if rounds < CONFIRM_MIN_ROUNDS:
            continue
        pending = frozenset(
            key for key in pending if _pair_uncertainty(accumulated[key]) > threshold
        )

    regressions: dict[Key, tuple[float, float]] = {}
    for key, pair in accumulated.items():
        base = _median(pair.base)
        head = _median(pair.head)
        if _above(base, head, threshold):
            regressions[key] = (base, head)
    return regressions


def accepted_rows(base_record: Path, head_record: Path) -> frozenset[Key]:
    """Rows explicitly raised by ``--accept-regression`` in this change."""
    before = load(base_record)
    after = load(head_record)
    return frozenset(
        key
        for key, value in after.items()
        if key in before and _above(before[key], value, DEFAULT_THRESHOLD)
    )


def _change(base: float, head: float) -> float:
    """Signed percentage change, where positive means HEAD is slower."""
    return (head - base) / base * 100.0


def main(argv: Sequence[str] | None = None) -> int:
    """Run same-machine base/head comparison for every active Lexic row."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-source", type=Path, required=True)
    parser.add_argument("--base-record", type=Path, required=True)
    parser.add_argument("--head-source", type=Path, default=Path("src"))
    parser.add_argument(
        "--head-record",
        type=Path,
        default=Path("tools/benchmark/lexic_baseline.json"),
    )
    args = parser.parse_args(argv)

    keys = _active_keys()
    accepted = accepted_rows(args.base_record, args.head_record)
    print(
        f"same-run Lexic A/B: {len(keys)} rows, "
        f"{DEFAULT_ROUNDS} first-pass rounds per tree"
    )
    first = sample_pair(keys, DEFAULT_ROUNDS, args.base_source, args.head_source)
    base, head = medians(first)
    candidates = frozenset(
        key for key in keys if key not in accepted and _above(base[key], head[key], 5.0)
    )
    if accepted:
        labels = ", ".join(f"{g}/{r}" for g, r in sorted(accepted))
        print(f"explicitly accepted by baseline diff: {labels}")
    if not candidates:
        print("no >5% Lexic regression candidates")
        return 0

    labels = ", ".join(f"{g}/{r}" for g, r in sorted(candidates))
    print(
        f"confirming candidates only (sigma-adaptive "
        f"{CONFIRM_MIN_ROUNDS}-{CONFIRM_MAX_ROUNDS} aggregate A/B rounds): "
        f"{labels}"
    )
    regressions = confirm(candidates, args.base_source, args.head_source)
    if not regressions:
        print("no confirmed Lexic performance regressions")
        return 0
    for (grammar, row), (base_value, head_value) in sorted(regressions.items()):
        print(
            f"  {grammar}/{row}: {base_value:.6f} -> {head_value:.6f} "
            f"({_change(base_value, head_value):+.2f}%)"
        )
    print(
        "performance regression confirmed; accept it locally with "
        "--accept-regression and commit the baseline increase"
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
