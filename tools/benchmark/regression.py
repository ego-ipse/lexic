"""Ratchet Lexic's isolated benchmark rows and reject confirmed regressions.

The pre-commit hook measures only Lexic, one exact grammar/engine pair per
fresh interpreter. A value more than five percent from its checked-in record
gets bounded adaptive confirmation. Confirmation aggregates every sample,
starts deciding after 21 rounds, and stops after 35; it never selects a lucky
batch. Sampling continues while the aggregate median's robust sigma error is
larger than the five-percent effect being tested. At the hard bound, the median
of all 35 samples decides; no batch is discarded or selected for its result.

An intentional slowdown is made explicit with::

    uv run python -m tools.benchmark.regression --accept-regression

Only a statistically confirmed slowdown can be accepted. The resulting JSON
diff is the reviewable acceptance.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import NamedTuple

from tools.benchmark.bench import LEXIC_ROWS, MT_ROWS
from tools.benchmark.cases.grammars import BENCHES
from tools.benchmark.cases.variants import variant_marks
from tools.benchmark.presentation.cli import _mt_cores
from tools.benchmark.execution.isolation import Job, RowRequest, run_jobs

DEFAULT_ROUNDS = 7
CONFIRM_BATCH_ROUNDS = DEFAULT_ROUNDS
CONFIRM_MIN_ROUNDS = DEFAULT_ROUNDS * 3
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


class Relation(NamedTuple):
    """A row expected to be faster than its reference row."""

    grammar: str
    faster: str
    reference: str


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
    """Sample exact rows, sharing one startup per requested grammar."""
    selected = _active_keys() if keys is None else keys
    active = _active_keys()
    unavailable = selected - active
    if unavailable:
        raise ValueError(f"benchmark rows are not active: {sorted(unavailable)}")
    cores = _mt_cores(None)
    measured: Samples = {}
    jobs = [
        Job(
            f"{grammar}/{row}",
            RowRequest(grammar, row, rounds, cores, False),
        )
        for grammar, row in sorted(selected)
    ]
    results = run_jobs(jobs)
    for grammar, row in sorted(selected):
        result = results[f"{grammar}/{row}"]
        if result.refusal is not None:
            raise ValueError(f"benchmark row {grammar}/{row} refused: {result.refusal}")
        if not result.samples:
            raise ValueError(f"benchmark row {grammar}/{row} returned no samples")
        if result.mt_reason is not None:
            raise ValueError(
                f"benchmark row {grammar}/{row} did not parallelize: {result.mt_reason}"
            )
        measured[(grammar, row)] = result.samples
    return measured


def _median(values: Sequence[float]) -> float:
    """Return the benchmark's upper median for one row's samples."""
    ordered = sorted(values)
    return ordered[len(ordered) // 2]


def _relative_uncertainty(values: Sequence[float]) -> float:
    """Robust one-sigma error estimate for the median, as a percentage.

    ``1.4826 * MAD`` estimates sigma without letting a timing outlier dominate;
    ``1.2533`` converts a normal sample's mean standard error to the median's.
    The estimate shrinks with every aggregated round, which is the quantity
    adaptive confirmation is meant to improve.
    """
    median = _median(values)
    mad = _median([abs(value - median) for value in values])
    sigma = 1.2533 * 1.4826 * mad / len(values) ** 0.5
    return sigma / max(abs(median), 1e-9) * 100.0


def _relations(active: frozenset[Key] | None = None) -> frozenset[Relation]:
    """Performance ordering promised by Lexic's optimized execution modes."""
    available = _active_keys() if active is None else active
    expected: set[Relation] = set()
    for bench in BENCHES:
        lexical, non_semantic = variant_marks(bench.ast)
        candidates = [
            Relation(bench.name, "lexic-mt", "lexic-pda"),
            Relation(bench.name, "lexic-mt-lex-ns", "lexic-lex-ns"),
        ]
        if lexical:
            candidates.append(Relation(bench.name, "lexic-lex", "lexic-pda"))
            candidates.append(Relation(bench.name, "lexic-mt-lex-ns", "lexic-mt"))
        if non_semantic:
            candidates.append(Relation(bench.name, "lexic-lex-ns", "lexic-lex"))
        expected.update(
            relation
            for relation in candidates
            if (relation.grammar, relation.faster) in available
            and (relation.grammar, relation.reference) in available
        )
    return frozenset(expected)


def relation_failures(
    values: Values,
    relations: frozenset[Relation] | None = None,
    threshold: float = DEFAULT_THRESHOLD,
) -> frozenset[Relation]:
    """Return optimized rows slower than their references by the guard margin."""
    checked = _relations(frozenset(values)) if relations is None else relations
    return frozenset(
        relation
        for relation in checked
        if _above(
            values[(relation.grammar, relation.reference)],
            values[(relation.grammar, relation.faster)],
            threshold,
        )
    )


def _relation_keys(relations: frozenset[Relation]) -> frozenset[Key]:
    """Both measured sides of a set of ordering relations."""
    return frozenset(
        (relation.grammar, row)
        for relation in relations
        for row in (relation.faster, relation.reference)
    )


def _relation_uncertainty(samples: Samples, relation: Relation) -> float:
    """Combined one-sigma uncertainty of one optimized/reference pair."""
    faster = samples[(relation.grammar, relation.faster)]
    reference = samples[(relation.grammar, relation.reference)]
    return (
        _relative_uncertainty(faster) ** 2 + _relative_uncertainty(reference) ** 2
    ) ** 0.5


def confirm_relations(
    relations: frozenset[Relation], threshold: float = DEFAULT_THRESHOLD
) -> tuple[Values, frozenset[Relation]]:
    """Repeat only rows in anomalous order, bounded by their paired sigma."""
    keys = _relation_keys(relations)
    accumulated: Samples = {key: [] for key in keys}
    rounds = 0
    pending = relations
    while pending and rounds < CONFIRM_MAX_ROUNDS:
        batch = min(CONFIRM_BATCH_ROUNDS, CONFIRM_MAX_ROUNDS - rounds)
        observed = sample(_relation_keys(pending), batch)
        for key, values in observed.items():
            accumulated[key].extend(values)
        rounds += batch
        if rounds < CONFIRM_MIN_ROUNDS:
            continue
        pending = frozenset(
            relation
            for relation in pending
            if _relation_uncertainty(accumulated, relation) > threshold
        )
    medians = {key: _median(values) for key, values in accumulated.items() if values}
    return medians, relation_failures(medians, relations, threshold)


def state(target: float, values: Sequence[float], threshold: float) -> str | None:
    """Classify a precise aggregate median, or request another sigma batch."""
    if _relative_uncertainty(values) > threshold:
        return None
    median = _median(values)
    if _above(target, median, threshold):
        return "regression"
    if _below(target, median, threshold):
        return "improvement"
    return "noise"


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
        observed = sample(pending, batch)
        if observed.keys() != pending:
            raise ValueError(
                "confirmation row mismatch: "
                f"expected={sorted(pending)}, observed={sorted(observed)}"
            )
        for key in pending:
            accumulated[key].extend(observed[key])
        rounds += batch
        if rounds < CONFIRM_MIN_ROUNDS:
            continue
        next_pending = set()
        for key in pending:
            classification = state(baseline[key], accumulated[key], threshold)
            if classification is None:
                next_pending.add(key)
            else:
                resolved[key] = _median(accumulated[key])
        pending = frozenset(next_pending)

    # The bound is a decision bound, not a random failure mode. Sigma chooses
    # how many samples the repeat earns; after all 35, their aggregate median
    # is the repeat value in the user's rule ("if on repeat it remains >5%").
    for key in pending:
        resolved[key] = _median(accumulated[key])
    pending = frozenset()

    # New rows have no decision boundary. Give each the full bounded sample so
    # their first stored target is not a seven-round outlier.
    if new:
        observed = sample(frozenset(new), CONFIRM_MAX_ROUNDS)
        if observed.keys() != new:
            raise ValueError(
                "new-row confirmation mismatch: "
                f"expected={sorted(new)}, observed={sorted(observed)}"
            )
        for key in new:
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


def _ordering_is_safe(first: Values) -> bool:
    """Confirm and report first-pass execution-mode ordering anomalies."""
    anomalous = relation_failures(first)
    if not anomalous:
        return True
    labels = ", ".join(
        f"{relation.grammar}/{relation.faster}>{relation.reference}"
        for relation in sorted(anomalous)
    )
    print(
        f"confirming execution-order anomalies only (sigma-adaptive "
        f"{CONFIRM_MIN_ROUNDS}-{CONFIRM_MAX_ROUNDS} aggregate rounds): {labels}"
    )
    repeated, failures = confirm_relations(anomalous)
    for relation in sorted(failures):
        faster = repeated[(relation.grammar, relation.faster)]
        reference = repeated[(relation.grammar, relation.reference)]
        print(
            f"  {relation.grammar}/{relation.faster}: {faster:.6f}; "
            f"expected <= {relation.reference}: {reference:.6f}"
        )
    if failures:
        print("Lexic execution-mode performance regression confirmed")
    return not failures


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
        f"lexic benchmark guard: uncontended first pass "
        f"({DEFAULT_ROUNDS} rounds per row)"
    )
    first = measure(None)
    if not _ordering_is_safe(first):
        return 1

    def confirm(keys: frozenset[Key]) -> Confirmed:
        labels = ", ".join(f"{grammar}/{row}" for grammar, row in sorted(keys))
        print(
            f"confirming new or >{DEFAULT_THRESHOLD:.0f}% change candidates only "
            f"(sigma-adaptive {CONFIRM_MIN_ROUNDS}-{CONFIRM_MAX_ROUNDS} "
            f"aggregate rounds): {labels}"
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
        print(f"benchmark confirmation could not measure rows: {labels}")
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
