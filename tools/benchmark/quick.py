"""A bounded, scope-selected PRELIMINARY comparison beside the landing gate.

`compare.py` is acceptance: every row, one process at a time, growing to sixteen
pairs until each row settles. That is what a tree about to land needs, and it
costs a morning. A tree that will change again before it lands needs a
DIRECTION, over the rows the change can reach, in minutes.

Three things separate this tier from the gate, and each one is a deliberate
loss:

- **Scope.** Only the seats and grammars asked for. What makes a row worth
  measuring is a fact about the change, so the caller derives that set and
  passes it in; nothing here knows or may learn which grammars are interesting.
- **Budget.** A fixed :data:`PAIRS`, never grown. A row that will not separate
  at that budget stays `inconclusive` — the gate is where it earns more pairs.
- **Schedule.** Sequential rows are single-threaded processes, so several run at
  once on their own cores. Threaded rows own the machine, one at a time,
  because their reading IS latency and a co-tenant is indistinguishable from a
  regression.

What does NOT change is the observation. The same worker, the same rounds, the
same row contract, the same byte-identical control beside every candidate pair.
Only the budget and the schedule differ, so a quick number and a gate number are
the same measurement taken fewer times and under a stated amount of company.

**The words are deliberately not the gate's.** Nothing here says `ok`, `slower`
or `faster`: a row leans, is flat, or is inconclusive, and PRELIMINARY travels
through the text and the JSON. This tier has no verdict to fail a run with and
always exits 0. What lands is decided by `compare.py`.
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
    MT_ROWS,
    Arms,
    Pairing,
    Verdict,
    judge,
    report_table,
    rosters,
    sample,
)
from tools.benchmark.measurement.copy import digest

PAIRS = 4
"""Process pairs per sequential row — fixed, never grown.

The gate starts at six and grows to sixteen until a row settles; that growth
is what makes it cost a morning. Four is the smallest even count that keeps
the alternation whole and the first-slot artefact out of the published
ratio, and a row that cannot separate at four is reported ``inconclusive``
rather than given more. The gate is where a row earns more pairs.

Even, because the candidate and the control alternate which process goes
first pair by pair, and an odd count leaves one order over-represented — a
fixed first-slot cost then lands in the ratio at 1/N of its size. At four
the two orders are balanced exactly.
"""

MT_PAIRS = 3
"""Process pairs per threaded row — one fewer than :data:`PAIRS`, on purpose.

A threaded row owns the whole machine while it runs, and its worker process
is measured on wall time, so no lane can share it and its cost is paid end
to end. Three pairs is the whole difference between a threaded half a caller
will wait for and one they will not.

Three is odd, so the candidate takes the first process slot twice and the
control once, and a fixed first-slot cost lands in a threaded row's
published ratio at a third of its size. The verdict is unaffected — the
control envelope carries the same artefact — and the run prints the
first-slot reading beside the rows so the reader sees what it actually was,
rather than being left to assume it away. The README states it too.
"""

THREADED_SECONDS = 6.0
"""What one threaded worker process is budgeted at, in seconds, for the announcement.

This is the pessimistic figure — what a whole loaded gate run averaged per
threaded process (6.05 s) — not the idle-machine cost (1.29 s on the
smallest roster grammar, 3.88 s on the largest). ``--mt`` prints its cost
before any threaded row starts, and a caller deciding against a wait should
be given the number that cannot surprise them.
"""

LANES = 1
"""Sequential rows in flight at once, by default.

A lane owns one row for that row's whole sequence, so several rows can be
measured at once on separate cores without changing how any one row is
measured. The concurrency this tier is built for is real: the touched set
of nine grammars over four sequential seats ran in 354 s at four lanes.

The default is nonetheless ONE, because the floor at four was measured and
did not match the gate's. Over 36 rows the control arm's per-pair spread
read 0.0431 at four lanes against the gate's 0.0277 on the same rows run one
at a time. A calibration at one, two and four lanes was then run to settle
the count and did not: the spreads came out 0.2464, 0.0892 and 0.0918
against the gate's 0.0249, with ONE lane the worst arm — and one lane is
the gate's own schedule, so that statistic was reading something other than
concurrency. A few control pairs dominated it, two byte-identical processes
reading as far as 1.84x apart; twenty-four pairs per arm was a quarter of
the proof run's, and the three arms ran in a fixed block order so the
one-lane arm alone paid the cold page cache.

Robust readings (median absolute deviation, drop-one spread) reverse the
ordering and put two and four lanes at or below the gate. They are not
adopted, because choosing the statistic after seeing that the declared one
gave an unusable answer is choosing it to fit the result.

Raising this default takes a measurement that answers: lane counts
interleaved pair by pair rather than run in blocks, more than four pairs per
arm, and a dispersion statistic declared in advance and robust to the
outliers now known to be there. Until then ``--lanes`` is there for a caller
who wants the speed today and will read the floor the run prints.
"""

NOISE_SLACK = 1.5
"""How much wider than the schedule's median row envelope a ``flat`` row may be.

``flat`` needs two things: the interval inside the row's own envelope, AND
that envelope no wider than :func:`ceiling_of` — the schedule's median row
envelope with this multiple applied to its excess over 1.0. A row whose
noise is anomalous for the run has separated nothing, whatever its interval
says; the case that forced the rule was a 1.1763 envelope that swallowed a
0.9672 reading whole and called the row unchanged.

The multiple applies to the NOISE, the envelope's excess over 1.0, so 1.5
against a typical 1.0338 admits up to 1.0507 — not 1.5507, which would
admit everything. A test pins that distinction.

A bare median (a multiple of 1.0) was tried first and replaced: it bars
half the field by construction, since half of any run's rows sit above its
own median, and on the proof run it took ``flat`` from seventeen rows to
three. The rule is for outliers, not for the ordinary upper half; at 1.5 the
same run reads eight flat, and the swallowing envelope is still rejected.
"""

LEANS_SLOWER = "leans-slower"
LEANS_FASTER = "leans-faster"
FLAT = "flat"
INCONCLUSIVE = "inconclusive"

TIER = "PRELIMINARY"
"""The word that travels through every line of text and the JSON this tier writes."""


def preliminary(row: str, pairing: Pairing, clock: str) -> Verdict:
    """Judge what one row can say ON ITS OWN — which is everything but `flat`.

    A lean is a statement about this row against this row's own noise, so it is
    decided here. `flat` is not: calling a row unchanged means its noise was
    ordinary as well as small, and what counts as ordinary is a property of the
    run. :func:`settle` finishes the job once every row has been measured.
    """
    judged = judge(row, pairing, clock, INCONCLUSIVE)
    if judged.low > judged.envelope:
        return judged.verdict._replace(status=LEANS_SLOWER)
    if judged.high < -judged.envelope:
        return judged.verdict._replace(status=LEANS_FASTER)
    return judged.verdict


class Reading(NamedTuple):
    """One row's preliminary verdict and the pairs it was taken from."""

    verdict: Verdict
    pairing: Pairing


def _settled(reading: Reading, ceiling: float) -> Reading:
    """One row's final word, against the noise the run turned out to have."""
    verdict = reading.verdict
    if verdict.status != INCONCLUSIVE or verdict.envelope > ceiling:
        return reading
    judged = judge(verdict.row, reading.pairing, verdict.clock, INCONCLUSIVE)
    if -judged.envelope <= judged.low and judged.high <= judged.envelope:
        return Reading(verdict._replace(status=FLAT), reading.pairing)
    return reading


def ceiling_of(readings: Sequence[Reading]) -> float:
    """The widest envelope this schedule still calls ordinary.

    :data:`NOISE_SLACK` times the median row envelope's excess over 1.0.
    """
    typical = median([reading.verdict.envelope for reading in readings] or [1.0])
    return 1.0 + NOISE_SLACK * (typical - 1.0)


def settle(readings: Sequence[Reading]) -> tuple[Reading, ...]:
    """Decide `flat` against the noise this schedule actually had.

    Two conditions, and the second is why this cannot happen a row at a time.
    The interval must sit inside the row's envelope, AND that envelope must be
    no wider than :func:`ceiling_of` — a row whose noise is anomalous for this
    run has separated nothing, whatever its interval says. The case that forced
    it: a 1.1763 envelope swallowed a 0.9672 reading whole and reported the row
    unchanged.

    Data-relative rather than a fixed percentage, so it keeps the gate's rule
    that what counts as noise is what this machine produced this session.

    The ceiling is taken PER SCHEDULE. A threaded row's envelope runs several
    times a sequential one's, so one median over both would let the threaded
    rows' spread license sequential rows that separated nothing, and hold
    threaded rows to a ceiling no threaded row can meet.
    """
    ceiling = ceiling_of(readings)
    return tuple(_settled(reading, ceiling) for reading in readings)


def budget(row: str) -> int:
    """Pairs this row is worth: a threaded one costs too much to get four."""
    return MT_PAIRS if row in MT_ROWS else PAIRS


def measure(arms: Arms, grammar: str, row: str) -> Reading:
    """One row's whole answer at its fixed budget, in this thread."""
    clock = "wall" if row in MT_ROWS else "cpu"
    pairing = sample(arms, grammar, row, budget(row), 0)
    return Reading(preliminary(f"{grammar}/{row}", pairing, clock), pairing)


def run_rows(
    arms: Arms, rows: Sequence[tuple[str, str]], lanes: int
) -> tuple[Reading, ...]:
    """Measure every row with ``lanes`` of them in flight at once.

    A lane owns one row for that row's whole sequence, so alternation and the
    control's opposite phase stay intact inside it: concurrency changes how many
    rows are being measured, never how one row is measured.
    """
    if not rows:
        return ()
    readings: list[Reading] = []
    with ThreadPoolExecutor(max_workers=lanes) as pool:
        pending = [pool.submit(measure, arms, grammar, row) for grammar, row in rows]
        for future in as_completed(pending):
            reading = future.result()
            # A ratio and no word: `flat` is decided by `settle` once the whole
            # schedule is in, and a word printed early could contradict it.
            print(
                f"  {reading.verdict.row}: {TIER} {reading.verdict.ratio:.4f}x",
                flush=True,
            )
            readings.append(reading)
    return settle(readings)


def by_schedule(
    rows: Sequence[tuple[str, str]],
) -> tuple[tuple[tuple[str, str], ...], tuple[tuple[str, str], ...]]:
    """Split a scope into rows that may share the machine and rows that may not.

    :returns: The sequential rows, then the threaded ones.
    """
    shared = tuple(row for row in rows if row[1] not in MT_ROWS)
    alone = tuple(row for row in rows if row[1] in MT_ROWS)
    return shared, alone


def refuse_unknown(
    rows: Sequence[tuple[str, str]],
    seats: Sequence[str] | None,
    grammars: Sequence[str] | None,
) -> None:
    """Refuse a scope naming a seat or grammar the roster does not carry.

    A misspelt name would otherwise select nothing and read as a fast, clean
    run over rows that were never measured.
    """
    unknown = sorted(
        (frozenset(seats or ()) - {row[1] for row in rows})
        | (frozenset(grammars or ()) - {row[0] for row in rows})
    )
    if unknown:
        raise ValueError(f"no such benchmark seat or grammar: {', '.join(unknown)}")


def scoped(
    rows: Sequence[tuple[str, str]],
    seats: Sequence[str] | None,
    grammars: Sequence[str] | None,
) -> tuple[tuple[str, str], ...]:
    """The rows a caller asked for: seats AND grammars, each empty meaning all.

    Two independent filters intersected, unlike the gate's single ``--only``,
    which matches a seat OR a grammar. The scope this tier is for is a seat list
    crossed with a grammar list, and a union cannot express it.
    """
    chosen = tuple(rows)
    if seats:
        wanted = frozenset(seats)
        chosen = tuple(row for row in chosen if row[1] in wanted)
    if grammars:
        named = frozenset(grammars)
        chosen = tuple(row for row in chosen if row[0] in named)
    return chosen


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
    carries a control pair of the same tree against itself, taken under the same
    company. Reporting its median beside the median envelope is what says
    whether the concurrency cost anything — a floor wider than the gate's is the
    signal to run fewer lanes, and it can only be seen if it is printed.
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


def _report(readings: Sequence[Reading]) -> None:
    """Print the tier banner, then the gate's own table of what was read."""
    print(f"\n{TIER} — not the landing gate; compare.py decides what lands\n")
    report_table([reading.verdict for reading in readings])


def _report_floors(floors: Sequence[Floor]) -> None:
    """Print each schedule's null floor — the price of the company it kept."""
    print()
    for floor in floors:
        print(
            f"null floor, {floor.rows} {floor.schedule} row(s) at {floor.lanes} lane(s): control median "
            f"{floor.control:.4f}x, median row envelope "
            f"{floor.envelope:.4f}x, first-slot {floor.slot:.4f}x"
        )


def _report_arms(base: Path, head: Path) -> None:
    """Print both arms and the benchmark text each one ran.

    The digests come from `measurement.copy`, so they are the same identity the
    gate's report carries. They match when the base is a current measurement
    copy and differ when it is stale — or, legitimately, when that revision
    needed the build-object rename. The tool cannot tell those apart, so it
    prints both rather than refusing on a condition it cannot read.
    """
    print(f"base {base} (benchmark digest {digest(base)})")
    print(f"head {head} (benchmark digest {digest(head)})")


def _write(path: Path, readings: Sequence[Reading], floors: Sequence[Floor]) -> None:
    """Write the run's whole answer, tier included, as JSON."""
    path.write_text(
        json.dumps(
            {
                "tier": TIER,
                "pairs": PAIRS,
                "mt_pairs": MT_PAIRS,
                "floors": [floor._asdict() for floor in floors],
                "verdicts": [reading.verdict._asdict() for reading in readings],
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


def _arguments(argv: Sequence[str] | None) -> argparse.Namespace:
    """Parse this tier's command line."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-root", type=Path, required=True)
    parser.add_argument("--head-root", type=Path, default=Path.cwd())
    parser.add_argument("--cores", type=int, default=4)
    parser.add_argument("--only", nargs="*", help="seat names; default every seat")
    parser.add_argument(
        "--grammars", nargs="*", help="grammar names; default every grammar"
    )
    parser.add_argument("--lanes", type=int, default=LANES)
    parser.add_argument(
        "--mt",
        action="store_true",
        help="also measure the threaded seats, alone and at their own budget",
    )
    parser.add_argument("--json", type=Path)
    return parser.parse_args(argv)


def _announce(
    shared: Sequence[tuple[str, str]],
    alone: Sequence[tuple[str, str]],
    lanes: int,
    wanted: bool,
) -> None:
    """Say what is about to run, and what the threaded half will cost.

    The threaded rows are the expensive half and they are opt-in, so their price
    is stated BEFORE they start rather than discovered by waiting. A caller who
    sees the number and does not want it has lost nothing.
    """
    print(
        f"{TIER} tier: {len(shared)} sequential row(s), {PAIRS} pairs each, "
        f"{lanes} at a time"
    )
    if not alone:
        return
    if not wanted:
        print(
            f"  {len(alone)} threaded row(s) in scope are NOT measured; "
            "pass --mt to include them"
        )
        return
    processes = len(alone) * MT_PAIRS * 4
    print(
        f"  plus {len(alone)} threaded row(s), {MT_PAIRS} pairs each — "
        f"{processes} worker processes one at a time, up to about "
        f"{processes * THREADED_SECONDS / 60:.0f} min"
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Run the scoped, bounded comparison and print what it read.

    :returns: 0, always. A preliminary reading is not a verdict, and a tier that
        could fail a run would be a second gate with a smaller budget.
    """
    args = _arguments(argv)
    rows = rosters(args.base_root, args.head_root)
    refuse_unknown(rows, args.only, args.grammars)
    shared, alone = by_schedule(scoped(rows, args.only, args.grammars))
    if not shared and not alone:
        raise ValueError("the requested scope selects no rows")
    if not shared and not args.mt:
        raise ValueError("the requested scope is threaded rows only; pass --mt")
    _announce(shared, alone, args.lanes, args.mt)
    _report_arms(args.base_root, args.head_root)
    arms = Arms(args.base_root, args.head_root, args.cores)
    started = time.perf_counter()
    sequential = run_rows(arms, shared, args.lanes)
    threaded = run_rows(arms, alone if args.mt else (), 1)
    elapsed = time.perf_counter() - started
    readings = sequential + threaded
    floors = (
        floor_of("sequential", sequential, args.lanes),
        floor_of("threaded", threaded, 1),
    )
    _report(readings)
    _report_floors(floors)
    print(f"\nwall {elapsed:.1f}s for {len(readings)} rows")
    if args.json:
        _write(args.json, readings, floors)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
