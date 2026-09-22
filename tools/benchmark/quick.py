"""A local read that is CONCLUSIVE for the rows a change can reach.

`compare.py` is acceptance: every row in the roster, grown to sixteen pairs
until each one settles. That is what a tree about to land needs and it costs a
morning. What a tree still being edited needs is not a cheaper version of the
same sweep — it is the same rule, applied to the rows the change could actually
have moved, and an answer for every one of them.

So this tier differs from the gate in **what it measures**, not in how:

- **The rows come from the DIFF.** ``git`` says what changed, a table says
  which seats those paths sit on the paid path of, and the run measures those
  (:mod:`tools.benchmark.scope`). A caller may narrow the selection; widening
  it is refused, because a row the change cannot reach is a row whose reading
  means nothing.
- **The budget is pairs, and it is stated before anything runs.** Its default
  is exactly what the selection costs at the gate's own floor, so a default run
  measures every selected row at the count below which the gate decides
  nothing. ``--budget`` caps it, and a row the cap cannot afford is reported
  with zero pairs and the reason rather than dropped.
- **Spare budget goes where it can buy an answer.** Unresolved rows are funded
  in descending distance from 1.0 — but only if the pairs they would need fit
  what is left. A row that would need more than the budget has is reported with
  that projection instead of being given pairs that cannot settle it.

**The words ARE the gate's** — ``ok``, ``slower``, ``faster``, ``unresolved`` —
because the rule is the gate's, applied to the same control envelope. A run
exits 1 on ``slower``, exactly as `compare.py` does. What it may not do is
leave a row saying nothing: an unresolved row here carries the count that would
settle it, which is the difference between "cannot tell" and "not at this
budget, and here is the count that would".

The observation is untouched. The same worker, the same rounds, the same row
contract, the same byte-identical control beside every candidate pair.
"""

from __future__ import annotations

import argparse
import json
import math
import time
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from statistics import median
from typing import NamedTuple

from tools.benchmark.compare import (
    BLOCK,
    MAX_PAIRS,
    MIN_PAIRS,
    Arms,
    report_table,
    rosters,
    sample,
)
from tools.benchmark.judging.arithmetic import (
    CONFIDENCE_Z,
    MT_ROWS,
    Pairing,
    Verdict,
    decide,
)
from tools.benchmark.measurement.copy import digest
from tools.benchmark.scope.diff import changed_paths
from tools.benchmark.scope.paths import seats_for

LANES = 1
"""Sequential rows in flight at once.

One, because one is the gate's own schedule and this tier judges by the gate's
rule: a wider envelope than the gate's would make rows unresolved that the gate
would have settled, which is the opposite of what a tool that must be
conclusive wants.

A calibration at one, two and four lanes was run to raise this and did not
settle it. The declared statistic put the spreads at 0.2464, 0.0892 and 0.0918
against the gate's 0.0249, with ONE lane the worst arm — and one lane IS the
gate's schedule, so that reading was about block order and a cold page cache
rather than about concurrency. Robust statistics reversed the ordering and were
not adopted, because choosing the statistic after the declared one gave an
unusable answer is choosing it to fit the result. The honest statement is that
the question is open, not that lanes were measured and rejected.

``--lanes`` is there for a caller who wants the speed and will read the null
floor the run prints.
"""

SEPARATION_CAP = 512
"""Where the projection stops looking, and the guard rather than the answer.

Almost every row separates eventually: as the count grows both intervals
collapse onto their means, so a candidate mean above the control's decides
``slower`` and one at or below it decides ``ok``. What the projection reports
is therefore usually a COUNT — possibly an absurd one, which is itself the
useful answer — and ``None`` only for the tie where the two means coincide and
no count can break it. The cap is far above any budget anyone would spend, so a
number it returns is a real projection and not the cap in disguise.
"""

NO_BUDGET = "budget spent before this row"
"""Why a selected row was never measured — stated, never a silent omission."""


# ── how many pairs a row would need ────────────────────────────────────────


def _spread(values: Sequence[float]) -> tuple[float, float]:
    """A sample's mean and PER-PAIR standard deviation, in log space.

    Per-pair, not the standard error: the error at some other count is what the
    projection computes, and it can only do that from a quantity that does not
    already have this run's pair count baked into it.
    """
    count = len(values)
    mean = sum(values) / count if count else 0.0
    if count < 2:
        return mean, 0.0
    variance = sum((value - mean) ** 2 for value in values) / (count - 1)
    return mean, math.sqrt(variance)


def decided_at(pairing: Pairing, pairs: int) -> bool:
    """Whether :func:`~tools.benchmark.compare.decide` would settle this row at
    ``pairs`` pairs.

    Public because it is the question a report asks directly — would another
    round have helped? — and a caller reaching into a private name for it would
    be the same coupling with less notice.

    The same three comparisons ``decide`` makes, with both intervals rescaled.
    Holding the measured per-pair spreads fixed is the assumption, and it is
    the only one available: what a row's noise will be at a count nobody has
    run is not knowable, only projectable.
    """
    mean, sigma = _spread(pairing.candidate)
    control_mean, control_sigma = _spread(pairing.control)
    reach = CONFIDENCE_Z / math.sqrt(pairs)
    low, high = mean - reach * sigma, mean + reach * sigma
    envelope = abs(control_mean) + reach * control_sigma
    return low > envelope or high < -envelope or high <= envelope


def separation(pairing: Pairing) -> int | None:
    """The smallest EVEN pair count that would settle this row, or ``None``.

    Even, for the reason :data:`~tools.benchmark.compare.MIN_PAIRS` and
    :data:`~tools.benchmark.compare.BLOCK` are: an odd count leaves one process
    slot over-represented and its cost in the published ratio.

    This is what turns "cannot tell" into something a reader can act on. An
    unresolved row that would need forty pairs is a row worth reserving a quiet
    machine for; one that would need four hundred is a row whose effect is
    smaller than this host can see, and no amount of rerunning will change
    that. Both sentences are the same arithmetic, and neither is available from
    the pair count alone.

    Searched from the count the row ALREADY has, never from zero. The two
    tests are not monotone in the count — the envelope narrows as the control
    gains pairs, so a row can read ``ok`` at six and ``unresolved`` at sixteen
    — and a search from zero would answer an unresolved row with a count below
    the one already spent. "Needs eight pairs" after sixteen were spent is not
    a number anyone can act on; it is the search's own artefact.

    Projected under the per-pair spreads this row actually produced. They are
    an estimate from few samples and the real count will differ; what does not
    differ is the ORDER of magnitude, which is the decision the number informs.
    """
    have = len(pairing.candidate)
    start = max(BLOCK, have + (have % BLOCK))
    for pairs in range(start, SEPARATION_CAP + 1, BLOCK):
        if decided_at(pairing, pairs):
            return pairs
    return None


# ── what a run produced ────────────────────────────────────────────────────


class Reading(NamedTuple):
    """One measured row: its verdict, the pairs behind it, what would settle it.

    :ivar verdict: The gate's own record, carrying the gate's own word.
    :ivar pairing: Every log ratio the row was judged from.
    :ivar projection: The pair count that would settle the row, or ``None`` for
        the tie no count breaks. Carried even for a settled row, where it is
        the count that row needed — a reader comparing it with the pairs spent
        can see how much of the budget the answer actually took.
    """

    verdict: Verdict
    pairing: Pairing
    projection: int | None


class Unfunded(NamedTuple):
    """A selected row the budget never reached, and why.

    Reported rather than dropped. A row missing from a table reads as a row
    that did not matter, and the whole point of deriving the selection from the
    diff is that every row in it matters.
    """

    row: str
    reason: str


def clock_for(row: str) -> str:
    """Which clock this row is judged on — wall for threaded, else cpu."""
    return "wall" if row.split("/")[-1] in MT_ROWS else "cpu"


def read_row(arms: Arms, grammar: str, row: str, pairs: int) -> Reading:
    """Measure one row at ``pairs`` pairs and judge it by the gate's rule."""
    label = f"{grammar}/{row}"
    pairing = sample(arms, grammar, row, pairs, 0)
    return Reading(decide(label, pairing, clock_for(label)), pairing, None)


def extend(arms: Arms, reading: Reading, pairs: int) -> Reading:
    """Grow one row by ``pairs`` more, continuing its absolute pair index.

    Continuing the index is what keeps both schedules in phase across the
    boundary: restarting at zero would put the candidate first on every growth
    round and leave the control at its unswapped position throughout.
    """
    grammar, row = reading.verdict.row.split("/", 1)
    extra = sample(arms, grammar, row, pairs, len(reading.pairing.candidate))
    grown = Pairing(
        reading.pairing.candidate + extra.candidate,
        reading.pairing.control + extra.control,
        reading.pairing.slots + extra.slots,
    )
    return Reading(
        decide(reading.verdict.row, grown, reading.verdict.clock), grown, None
    )


def projected(reading: Reading) -> Reading:
    """The same reading, carrying the count that would settle it."""
    return reading._replace(projection=separation(reading.pairing))


# ── the budget, and where the spare goes ───────────────────────────────────


def floor_cost(rows: Sequence[tuple[str, str]]) -> int:
    """What measuring this selection costs at the gate's own floor, in pairs.

    The number printed before anything runs, and the default budget. Below
    :data:`~tools.benchmark.compare.MIN_PAIRS` the gate decides nothing, so a
    run that cannot afford this for a row cannot say anything about it — which
    is why such a row is reported unfunded rather than measured at less.
    """
    return MIN_PAIRS * len(rows)


def fund_floor(
    arms: Arms, rows: Sequence[tuple[str, str]], budget: int, lanes: int
) -> tuple[tuple[Reading, ...], tuple[Unfunded, ...], int]:
    """Measure as many rows at the floor as the budget affords, in order.

    Roster order, which is deterministic and reproducible — not cheapest-first,
    which would measure more rows per second but make WHICH rows a run covers
    depend on how fast the host happened to be that morning.

    :returns: The readings, the rows the budget never reached, and what is left.
    """
    affordable = max(0, min(len(rows), budget // MIN_PAIRS))
    funded, skipped = tuple(rows[:affordable]), tuple(rows[affordable:])
    readings = run_rows(arms, funded, lanes)
    return (
        readings,
        tuple(Unfunded(f"{grammar}/{row}", NO_BUDGET) for grammar, row in skipped),
        budget - MIN_PAIRS * len(funded),
    )


def growth_order(readings: Sequence[Reading]) -> tuple[Reading, ...]:
    """Unresolved rows, furthest from 1.0 first — who gets the spare budget.

    Distance from 1.0 rather than the interval's width, because the question
    the spare budget buys an answer to is "is this row the regression?", and
    the row most likely to be one is the row that looks most like one.
    """
    return tuple(
        sorted(
            (r for r in readings if r.verdict.status == "unresolved"),
            key=lambda reading: -abs(reading.verdict.ratio - 1.0),
        )
    )


def fund_growth(
    arms: Arms, readings: Sequence[Reading], budget: int
) -> tuple[tuple[Reading, ...], int]:
    """Spend what is left on the unresolved rows it can actually settle.

    Funded in :func:`growth_order` — but only where the pairs the row would
    need fit what remains. A row that would need more than the budget has is
    left with its projection rather than given pairs that cannot settle it,
    which is the whole difference between a run reporting "cannot tell" and one
    reporting what it would take.

    :returns: Every row's final reading, in the order given, and what is left.
    """
    final = {
        reading.verdict.row: projected(reading)
        for reading in readings
        if reading.verdict.status != "unresolved"
    }
    for reading in growth_order(readings):
        target = separation(reading.pairing)
        have = len(reading.pairing.candidate)
        need = 0 if target is None else min(target, MAX_PAIRS) - have
        if target is None or need <= 0 or need > budget:
            final[reading.verdict.row] = projected(reading)
            continue
        budget -= need
        final[reading.verdict.row] = projected(extend(arms, reading, need))
    return tuple(final[reading.verdict.row] for reading in readings), budget


# ── running rows ───────────────────────────────────────────────────────────


def run_rows(
    arms: Arms, rows: Sequence[tuple[str, str]], lanes: int
) -> tuple[Reading, ...]:
    """Measure every row at the floor with ``lanes`` of them in flight.

    A lane owns one row for that row's whole sequence, so alternation and the
    control's opposite phase stay intact inside it: concurrency changes how
    many rows are measured at once, never how one row is measured.
    """
    if not rows:
        return ()
    readings: list[Reading] = []
    with ThreadPoolExecutor(max_workers=lanes) as pool:
        pending = [
            pool.submit(read_row, arms, grammar, row, MIN_PAIRS)
            for grammar, row in rows
        ]
        for future in as_completed(pending):
            reading = future.result()
            print(
                f"  {reading.verdict.row}: {reading.verdict.ratio:.4f}x "
                f"({reading.verdict.status})",
                flush=True,
            )
            readings.append(reading)
    return tuple(readings)


def by_schedule(
    rows: Sequence[tuple[str, str]],
) -> tuple[tuple[tuple[str, str], ...], tuple[tuple[str, str], ...]]:
    """Split a selection into rows that may share the machine and rows that may
    not.

    :returns: The sequential rows, then the threaded ones.
    """
    shared = tuple(row for row in rows if row[1] not in MT_ROWS)
    alone = tuple(row for row in rows if row[1] in MT_ROWS)
    return shared, alone


def narrowed(
    rows: Sequence[tuple[str, str]],
    reachable: frozenset[str],
    seats: Sequence[str] | None,
    grammars: Sequence[str] | None,
) -> tuple[tuple[str, str], ...]:
    """The rows this run measures: what the diff reaches, narrowed by request.

    A caller may narrow the selection — fewer seats, fewer grammars — and may
    not widen it. Naming a seat the change cannot reach is refused rather than
    honoured: a reading there answers a question nobody asked, with budget the
    reachable rows needed.

    :raises ValueError: When ``seats`` names a seat outside ``reachable``, or
        either list names something the roster does not carry.
    """
    unknown = sorted(
        (frozenset(seats or ()) - {row[1] for row in rows})
        | (frozenset(grammars or ()) - {row[0] for row in rows})
    )
    if unknown:
        raise ValueError(f"no such benchmark seat or grammar: {', '.join(unknown)}")
    widened = sorted(frozenset(seats or ()) - reachable)
    if widened:
        raise ValueError(
            "the change does not reach these seats, so a reading on them would "
            f"mean nothing: {', '.join(widened)}"
        )
    wanted = frozenset(seats) if seats else reachable
    chosen = tuple(row for row in rows if row[1] in wanted)
    if grammars:
        named = frozenset(grammars)
        chosen = tuple(row for row in chosen if row[0] in named)
    return chosen


# ── what the run says ──────────────────────────────────────────────────────


class Floor(NamedTuple):
    """One schedule's measured null arm — what two identical trees read as.

    :ivar schedule: What was running, in words.
    :ivar lanes: How many rows were in flight while it was measured.
    :ivar rows: How many rows contributed.
    :ivar control: Median control ratio — two byte-identical processes.
    :ivar envelope: Median per-row envelope — the width a verdict is judged on.
    :ivar slot: Median first-over-second reading of the same control pairs.
    """

    schedule: str
    lanes: int
    rows: int
    control: float
    envelope: float
    slot: float


def floor_of(schedule: str, readings: Sequence[Reading], lanes: int) -> Floor:
    """What the byte-identical arm read while ``lanes`` rows were in flight.

    This IS the null arm, not a separate run: every candidate pair already
    carries a control pair of the same tree against itself, taken under the
    same company. Reporting its median beside the median envelope is what says
    whether the concurrency cost anything.
    """
    controls = [value for reading in readings for value in reading.pairing.control]
    slots = [value for reading in readings for value in reading.pairing.slots]
    envelopes = [reading.verdict.envelope for reading in readings]
    return Floor(
        schedule,
        lanes,
        len(readings),
        math.exp(median(controls or [0.0])),
        median(envelopes or [1.0]),
        math.exp(median(slots or [0.0])),
    )


def exit_code(readings: Sequence[Reading]) -> int:
    """1 when some row is slower than this machine's envelope, else 0.

    ``unresolved`` does not block, for the reason `compare.py` gives: it has
    measured no slowdown, only that this host could not separate the arms
    within the pairs it was given. Failing on it would make the answer depend
    on how quiet the machine happened to be, and the only move that leaves is
    to rerun until the noise cooperates.
    """
    return 1 if any(r.verdict.status == "slower" for r in readings) else 0


def report_projections(readings: Sequence[Reading]) -> None:
    """Say, for every unresolved row, what would have settled it."""
    open_rows = [r for r in readings if r.verdict.status == "unresolved"]
    if not open_rows:
        return
    print(f"\n{len(open_rows)} row(s) unresolved — reported, not blocking:")
    for reading in open_rows:
        spent = reading.verdict.pairs
        needs = (
            "no pair count separates it: its mean sits on the envelope"
            if reading.projection is None
            else f"about {reading.projection} pairs would settle it"
        )
        print(f"  {reading.verdict.row}: {spent} pairs spent, {needs}")


def report_unfunded(unfunded: Sequence[Unfunded]) -> None:
    """Name every selected row the run never measured, and why."""
    if not unfunded:
        return
    print(f"\n{len(unfunded)} selected row(s) not measured:")
    for row in unfunded:
        print(f"  {row.row}: 0 pairs — {row.reason}")


def report_floors(floors: Sequence[Floor]) -> None:
    """Print each schedule's null floor — the price of the company it kept."""
    print()
    for floor in floors:
        print(
            f"null floor, {floor.rows} {floor.schedule} row(s) at {floor.lanes} "
            f"lane(s): control median {floor.control:.4f}x, median row envelope "
            f"{floor.envelope:.4f}x, first-slot {floor.slot:.4f}x"
        )


def report_selection(paths: Sequence[str], seats: frozenset[str]) -> None:
    """One line naming what selected what — the run's own provenance."""
    print(
        f"selection: {len(paths)} changed path(s) reach "
        f"{len(seats)} seat(s): {', '.join(sorted(seats)) or 'none'}"
    )


def report_arms(base: Path, head: Path) -> None:
    """Print both arms and the benchmark text each one ran."""
    print(f"base {base} (benchmark digest {digest(base)})")
    print(f"head {head} (benchmark digest {digest(head)})")


def write_json(
    path: Path,
    readings: Sequence[Reading],
    unfunded: Sequence[Unfunded],
    floors: Sequence[Floor],
) -> None:
    """Write the run's whole answer — verdicts, projections and omissions."""
    path.write_text(
        json.dumps(
            {
                "floors": [floor._asdict() for floor in floors],
                "verdicts": [reading.verdict._asdict() for reading in readings],
                "projections": {
                    reading.verdict.row: reading.projection for reading in readings
                },
                "unfunded": [row._asdict() for row in unfunded],
                "log_ratios": {
                    reading.verdict.row: {
                        "candidate": list(reading.pairing.candidate),
                        "control": list(reading.pairing.control),
                        "slots": list(reading.pairing.slots),
                    }
                    for reading in readings
                },
            },
            indent=1,
        ),
        encoding="utf-8",
    )


def arguments(argv: Sequence[str] | None) -> argparse.Namespace:
    """Parse this tier's command line."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-root", type=Path, required=True)
    parser.add_argument("--head-root", type=Path, default=Path.cwd())
    parser.add_argument("--base-rev", default=None, help="revision the diff is against")
    parser.add_argument("--cores", type=int, default=4)
    parser.add_argument("--only", nargs="*", help="narrow to these seats")
    parser.add_argument("--grammars", nargs="*", help="narrow to these grammars")
    parser.add_argument("--lanes", type=int, default=LANES)
    parser.add_argument(
        "--budget", type=int, help="total process pairs; default is the floor cost"
    )
    parser.add_argument(
        "--mt", action="store_true", help="also measure the threaded seats, alone"
    )
    parser.add_argument("--json", type=Path)
    return parser.parse_args(argv)


def announce(
    rows: Sequence[tuple[str, str]],
    skipped: Sequence[tuple[str, str]],
    budget: int,
    lanes: int,
) -> None:
    """Say what the selection costs before a single process starts.

    Including what it is NOT measuring. The threaded rows are the expensive
    half and they are opt-in, so a run that leaves them out says how many it
    left out — a caller who reads a clean table has to know whether the rows
    they were worried about were in it.
    """
    print(
        f"{len(rows)} row(s) selected; {floor_cost(rows)} pairs to measure them "
        f"all at the gate's floor of {MIN_PAIRS}"
    )
    print(f"budget {budget} pairs, {lanes} row(s) at a time")
    if skipped:
        print(
            f"  {len(skipped)} threaded row(s) the change reaches are NOT "
            "measured; pass --mt to include them"
        )


class Run(NamedTuple):
    """Everything one measured run produced, before it is printed.

    :ivar readings: Every measured row, in the order it will be reported.
    :ivar unfunded: Selected rows the budget never reached.
    :ivar left: Pairs the run did not spend.
    :ivar sequential: How many of :attr:`readings` came from the shared
        schedule — the split the two null floors are taken either side of.
    :ivar elapsed: Wall seconds the measuring itself took.
    """

    readings: tuple[Reading, ...]
    unfunded: tuple[Unfunded, ...]
    left: int
    sequential: int
    elapsed: float


def measure(
    arms: Arms,
    shared: Sequence[tuple[str, str]],
    alone: Sequence[tuple[str, str]],
    budget: int,
    lanes: int,
) -> Run:
    """Floor every row the budget affords, then grow what the rest can settle.

    Two phases and not one, because the priority rule needs a ratio to rank by
    and a projection to fund against, and neither exists until the row has been
    measured at the gate's floor.
    """
    started = time.perf_counter()
    floored, unfunded, left = fund_floor(arms, shared, budget, lanes)
    threaded, missed, left = fund_floor(arms, alone, left, 1)
    readings, left = fund_growth(arms, floored + threaded, left)
    return Run(
        readings,
        unfunded + missed,
        left,
        len(floored),
        time.perf_counter() - started,
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Measure the rows this change can reach, and answer for every one.

    :returns: 1 when a row is slower than this machine's envelope, else 0.
    :raises ValueError: When the request widens the selection or names
        something the roster does not carry.
    """
    args = arguments(argv)
    rows = rosters(args.base_root, args.head_root)
    paths = changed_paths(args.base_rev or str(args.base_root), args.head_root)
    reachable = seats_for(paths)
    report_selection(paths, reachable)
    report_arms(args.base_root, args.head_root)
    if not reachable:
        print("\nnothing changed sits on a paid path; no row to measure")
        return 0
    shared, alone = by_schedule(narrowed(rows, reachable, args.only, args.grammars))
    selected = shared + (alone if args.mt else ())
    if not selected:
        print(f"\n{len(alone)} threaded row(s) reached; pass --mt to measure them")
        return 0
    budget = args.budget if args.budget is not None else floor_cost(selected)
    announce(selected, () if args.mt else alone, budget, args.lanes)
    arms = Arms(args.base_root, args.head_root, args.cores)
    run = measure(arms, shared, alone if args.mt else (), budget, args.lanes)
    if run.readings:
        print()
        report_table([reading.verdict for reading in run.readings])
    report_projections(run.readings)
    report_unfunded(run.unfunded)
    floors = (
        floor_of("sequential", run.readings[: run.sequential], args.lanes),
        floor_of("threaded", run.readings[run.sequential :], 1),
    )
    report_floors(floors)
    spent = sum(reading.verdict.pairs for reading in run.readings)
    print(f"\nwall {run.elapsed:.1f}s, {spent} pairs spent, {run.left} unspent")
    if args.json:
        write_json(args.json, run.readings, run.unfunded, floors)
    return exit_code(run.readings)


if __name__ == "__main__":
    raise SystemExit(main())
