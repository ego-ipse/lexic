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

from tools.benchmark.execution.isolation import Job, RowRequest, run_job, run_roster
from tools.benchmark.measurement.contract import Observation, RowContract, RowResult

MIN_PAIRS = 6
MAX_PAIRS = 16
"""How many independent process pairs a verdict may cost.

Below the minimum nothing is decided. Above the maximum the evidence is
declared unresolved rather than forced into a median — a row that will not
settle is a fact about the measurement, not a licence to pick a number.

**Both are EVEN, and the parity is the reason, not a coincidence.** The two
schedules in :func:`sample` alternate on a period of two, so they sample the
first slot equally often only at an even count. At an odd one the candidate's
numerator takes the first slot once more than the control's and the control's
once fewer — 3/5 against 2/5 at five pairs, 8/15 against 7/15 at fifteen, the
two counts a row is most likely to stop at. A slot cost δ then leaves +δ/n in
the candidate's mean and −δ/n in the control's. That cancels out of the
VERDICT, because the envelope is a magnitude and both sides of the comparison
move together — but it does not cancel out of the reported RATIO, which is the
number a person reads and quotes. One extra process pair per row buys a
published figure with a known bias removed. Do not make either odd again.

Even bounds are half the statement: the counts BETWEEN them must be even too,
which is what :data:`BLOCK` settles. Their difference is a whole number of
blocks, so growth reaches the ceiling exactly.
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
    """One row's paired candidate and control log ratios.

    :ivar candidate: log(head/base), one per pair.
    :ivar control: log(control-a/control-b), one per pair.
    :ivar slots: log(first/second) for the same control pairs — the ORDERING
        artefact, oriented by which process actually ran first. The control's
        two processes are byte-identical, so this is the first slot's own cost
        and nothing else; it is reported rather than left to widen the envelope
        silently.
    """

    candidate: tuple[float, ...]
    control: tuple[float, ...]
    slots: tuple[float, ...]


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
    """Judge one row's candidate interval against its control envelope.

    The gate is about SLOWDOWNS, so the only edge that can leave a row
    undecided is the envelope's upper one. An interval whose top is inside the
    envelope has already answered the gate's question — it cannot be slower —
    and it passes: as ``faster`` when the whole interval sits below the
    envelope's lower edge, as ``ok`` otherwise. Demanding ``low >= -envelope``
    for ``ok`` as well made a row that is clearly not slower read
    ``unresolved`` merely for being possibly FASTER than the machine's own
    noise, which then blocked the gate and earned it more pairs it could not
    spend.
    """
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
    if high <= envelope:
        return verdict._replace(status="ok")
    return verdict


class Arm(NamedTuple):
    """One process's whole answer, under the label that names which arm it is.

    :ivar label: ``grammar/row/side`` — the job that produced it.
    :ivar contract: What that process measured.
    :ivar observation: What it observed measuring it.
    """

    label: str
    contract: RowContract
    observation: Observation


def require(result: RowResult, label: str) -> Arm:
    """One arm's answer, or a refusal that stops the run."""
    if result.refusal is not None:
        raise ValueError(f"{label}: row refused: {result.refusal}")
    if result.contract is None or not result.observations:
        raise ValueError(f"{label}: row produced no observation")
    return Arm(label, result.contract, result.observations[0])


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


SEMANTIC = (
    "verdict",
    "engaged",
    "split_digest",
    "result_digest",
    "shape_digest",
)
"""What two arms must have DONE identically for their durations to compare.

A pair disagreeing on any of these is not a slow arm and a fast arm; it is two
different workloads. One refused while the other parsed, one split while the
other declined, one carved the document differently, one emitted different
characters, or one built a different tree — each of those makes the ratio
meaningless, so the pair is refused before its duration can reach the estimator.

``effective_workers`` is deliberately NOT here. How many threads picked the
pieces up is the executor's answer, not the workload's: thirty identical
attempts on one artefact occupied eight workers twenty-eight times and seven
twice, so a same-tree control pair would have been refused for being scheduled.
The carving those threads shared is what identifies the work, and that is
``split_digest``; the occupancy travels beside it as evidence to read.
"""


def comparable(one: Arm, other: Arm, row: str) -> None:
    """Refuse two arms that did not produce the same result, by field."""
    fields = tuple(
        field
        for field in SEMANTIC
        if getattr(one.observation, field) != getattr(other.observation, field)
    )
    if not fields:
        return
    detail = ", ".join(
        f"{field}: {one.label}={getattr(one.observation, field)!r} "
        f"{other.label}={getattr(other.observation, field)!r}"
        for field in fields
    )
    raise ValueError(f"{row}: the two arms did not produce the same result — {detail}")


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
    arms = tuple(
        require(result, job.label)
        for result, job in zip(results, (first, second), strict=True)
    )
    agree(arms[0].contract, arms[1].contract, row)
    comparable(arms[0], arms[1], row)
    return primary_reading(arms[0].observation, row), primary_reading(
        arms[1].observation, row
    )


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


def sample(arms: Arms, grammar: str, row: str, pairs: int, first: int) -> Pairing:
    """Collect ``pairs`` candidate and control ratios for one row.

    Each pair is two complete process lifecycles, one after the other. Both
    schedules reverse exactly ONE thing — which process runs first — while the
    ratio's numerator stays the same arm throughout. Reversing both together is
    reversing neither: exchanging the two control jobs AND keeping the numerator
    on whichever ran first made every control divide the first process reading
    by the second, so a permanent slot penalty entered the envelope as noise
    instead of cancelling. A 10% first-slot cost then read as a 1.10 envelope
    and swallowed a true 3% head regression whole.

    The control runs the candidate's period in the OPPOSITE PHASE, which is
    what keeps an ordering artefact visible without letting it accumulate.
    Giving the control a different period (`index % 3 != 2`) made its schedule
    10 forward to 5 reversed at fifteen pairs, so a first-slot cost δ left
    δ·(10−5)/15 = δ/3 in the control's mean instead of cancelling; measured at
    +0.39 % on this host (CI 0.9969–1.0109), that inflated the envelope rather
    than showing as a signal — a more permissive gate, never a false alarm.
    Opposite phase leaves −δ/15, twenty times smaller and converging to zero as
    pairs grow, while still separating the arms: whenever the candidate runs
    head first, the control runs control-b first, so an artefact cannot cancel
    in the same direction in both and hide.

    ``first`` is the pair's ABSOLUTE index in the row's whole sequence, which
    is what makes both schedules continuous across adaptive growth. Restarting
    at zero each call put head first on all ten one-pair growth rounds — thirteen
    of fifteen pairs — and left the control at its unswapped position throughout.

    **Parity is what alternation cannot fix**, which is why :data:`MIN_PAIRS`
    and :data:`MAX_PAIRS` are both even. At an even count the two schedules
    sample the first slot equally often; at an odd one the candidate's
    numerator takes it once more and the control's once fewer — 3/5 against
    2/5 at five pairs, 8/15 against 7/15 at fifteen. A slot cost δ then leaves
    +δ/n in the candidate's mean and −δ/n in the control's. The opposite signs
    keep it out of the VERDICT: the envelope is a magnitude, so both sides of
    ``low > envelope`` and of ``high <= envelope`` move by the same δ/n and it
    cancels exactly. It does not cancel out of the reported RATIO, and that is
    the bias the even bounds remove. Whatever survives is printed by
    :func:`_report_control` rather than left to be inferred.

    :param pairs: How many pairs this call collects.
    :param first: The absolute index of the first of them.
    """
    candidate: list[float] = []
    control: list[float] = []
    slots: list[float] = []
    for index in range(first, first + pairs):
        head_job = _job(arms.head, grammar, row, arms.cores, "head")
        base_job = _job(arms.base, grammar, row, arms.cores, "base")
        candidate.append(_ratio(head_job, base_job, index % 2 == 0, row))
        left = _job(arms.head, grammar, row, arms.cores, "control-a")
        right = _job(arms.head, grammar, row, arms.cores, "control-b")
        a_first = index % 2 == 1
        reading = _ratio(left, right, a_first, row)
        control.append(reading)
        # `_ratio` always divides control-a by control-b; flipping the sign when
        # control-b ran first turns the same reading into first-over-second.
        slots.append(reading if a_first else -reading)
    return Pairing(tuple(candidate), tuple(control), tuple(slots))


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


BLOCK = 2
"""Pairs one growth round adds, and the count a verdict may be taken at.

The period :func:`sample` alternates on. Growth used to add ONE pair and return
the moment it settled, so a row could publish at 7, 9, 11, 13 or 15 — carrying
exactly the first-slot bias :data:`MIN_PAIRS` and :data:`MAX_PAIRS` are even to
remove. Even bounds settle only the two counts a row stops at MOST often; every
count it can stop at has to be even, and that is a property of the growth step.

Both bounds are a whole number of blocks apart, so the ceiling is reached
exactly rather than stepped over.
"""


def grow(arms: Arms, grammar: str, row: str) -> tuple[Verdict, Pairing]:
    """Sample a row until it settles inside the envelope, or the bound runs out.

    A verdict is taken only at a complete :data:`BLOCK` — never after the first
    pair of one — so the two schedules have sampled the first slot equally often
    at whatever count is published. An already balanced result is not grown: the
    floor is itself a complete block, and a row that settles there settles.

    Each round continues the absolute pair index, which is what keeps both
    schedules in phase across the boundary.
    """
    clock = "wall" if row in MT_ROWS else "cpu"
    label = f"{grammar}/{row}"
    pairing = sample(arms, grammar, row, MIN_PAIRS, 0)
    verdict = decide(label, pairing, clock)
    while verdict.status in GROWS and len(pairing.candidate) < MAX_PAIRS:
        extra = sample(arms, grammar, row, BLOCK, len(pairing.candidate))
        pairing = Pairing(
            pairing.candidate + extra.candidate,
            pairing.control + extra.control,
            pairing.slots + extra.slots,
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


def _report_control(samples: dict[str, Pairing]) -> None:
    """Print what the byte-identical arm measured, and the slot inside it.

    Two different statements. The control median says how far apart two
    identical trees read overall; the slot artefact says how much of that is
    merely running first, which the schedule now balances out of the mean
    rather than leaving to widen the envelope.

    :param samples: Every judged row's pairings.
    """
    control = median(
        [value for pairing in samples.values() for value in pairing.control] or [0.0]
    )
    slot = median(
        [value for pairing in samples.values() for value in pairing.slots] or [0.0]
    )
    print(f"\ncontrol median log ratio: {math.exp(control):.4f}x")
    print(f"first-slot artefact: {math.exp(slot):.4f}x (control pairs, first/second)")


def status(verdicts: Sequence[Verdict]) -> int:
    """The run's exit code — decided by ``slower`` rows and nothing else.

    An unresolved row has measured no slowdown. It has measured that this
    machine, this session, could not separate the two arms within the pair
    bound — a fact about the measurement, not about the code. Failing on it
    makes the gate's answer depend on how quiet the host happened to be, and
    the only move it leaves is to rerun until the noise cooperates, which is
    optional stopping wearing a different hat.

    Measured here rather than argued. Run against ITSELF — both roots the same
    checkout, so every pair is byte-identical and no row can truly be slower —
    twenty-four rows produced twenty-two ``ok`` and two ``unresolved``, and no
    ``slower`` at all. One row in twelve could not be separated from the noise
    it was made of, which under the old rule failed the whole run on code that
    had not changed.

    The rows still print in full, with their interval, envelope and pair count
    — an unresolved row is evidence to read, and the summary says how many
    there were and that they did not block.

    :param verdicts: Every judged row.
    :returns: 1 when some row is slower than this machine's envelope, else 0.
    """
    slower = [verdict for verdict in verdicts if verdict.status == "slower"]
    unresolved = [verdict for verdict in verdicts if verdict.status == "unresolved"]
    if unresolved:
        print(
            f"\n{len(unresolved)} row(s) unresolved after {MAX_PAIRS} pairs — "
            f"reported, not blocking:"
        )
        for verdict in unresolved:
            print(
                f"  {verdict.row}: {verdict.ratio:.4f}x on {verdict.clock}, "
                f"ci {verdict.low:.4f}..{verdict.high:.4f}, "
                f"envelope {verdict.envelope:.4f}, {verdict.pairs} pairs"
            )
    if slower:
        print(f"\n{len(slower)} row(s) slower than this machine's noise envelope:")
        for verdict in slower:
            print(
                f"  {verdict.row}: {verdict.ratio:.4f}x on {verdict.clock}, "
                f"ci {verdict.low:.4f}..{verdict.high:.4f}, "
                f"envelope {verdict.envelope:.4f}, {verdict.pairs} pairs"
            )
        return 1
    print("\nno row is slower than this machine's envelope")
    return 0


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
                            "slots": list(p.slots),
                        }
                        for row, p in samples.items()
                    },
                },
                indent=1,
            ),
            encoding="utf-8",
        )
    _report_control(samples)
    return status(verdicts)


if __name__ == "__main__":
    raise SystemExit(main())
