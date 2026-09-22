"""A row's verdict and the arithmetic that decides it.

Every tier that judges a row — the gate, the quick tier, the aggregate and the
run diff — reads its interval, envelope and status from these records, so their
thresholds and published figures come from one arithmetic. Scheduling the pairs
that feed a verdict is :mod:`tools.benchmark.compare`'s job, not this module's.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import NamedTuple

from tools.benchmark.measurement.contract import Observation

CONFIDENCE_Z = 1.96
"""Two-sided 95% normal quantile — the predeclared interval."""

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
    :ivar head_wall: The head arm's wall clock per byte of its document, in
        nanoseconds, one per candidate pair. Never judged: it is what lets two
        SEATS be compared, which a ratio against the same seat's base cannot.
    :ivar head_cpu: The same pairs on the process clock.
    :ivar document_bytes: The document both arms read — the per-byte
        denominator, taken from the contract the two arms agreed on.
    """

    candidate: tuple[float, ...]
    control: tuple[float, ...]
    slots: tuple[float, ...]
    head_wall: tuple[float, ...] = ()
    head_cpu: tuple[float, ...] = ()
    document_bytes: int = 0


class Verdict(NamedTuple):
    """One row's decision and the numbers behind it.

    :ivar row: ``grammar/name``.
    :ivar status: The judging tier's word for this row. The gate's are ``ok``,
        ``slower``, ``faster`` and ``unresolved``; a tier that decides on a
        different rule must spell its outcomes differently, so that a verdict
        can never be read against the wrong rule.
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


def log_interval(ratios: Sequence[float]) -> tuple[float, float, float]:
    """Mean log ratio and its confidence bounds, in log space."""
    count = len(ratios)
    mean = sum(ratios) / count
    if count < 2:
        return mean, mean, mean
    variance = sum((value - mean) ** 2 for value in ratios) / (count - 1)
    error = math.sqrt(variance / count)
    return mean, mean - CONFIDENCE_Z * error, mean + CONFIDENCE_Z * error


def noise_envelope(control: Sequence[float]) -> float:
    """The control's upper log bound — what this machine calls no change.

    Built from the byte-identical pairs' own spread, so a quiet machine gets a
    tight envelope and a noisy one is honest about being noisy. A fixed
    percentage cannot do either.
    """
    if not control:
        return 0.0
    _mean, low, high = log_interval(control)
    return max(abs(low), abs(high))


class Judged(NamedTuple):
    """One row's numbers in the space they are JUDGED in, beside the verdict.

    A verdict is read as ratios and decided as logs, and the two must not drift
    apart: every tier that judges a row does it from this record, so its
    thresholds and its published figures come from one arithmetic.

    :ivar verdict: The row as a reader sees it, carrying the tier's word for
        an undecided row.
    :ivar low: The candidate interval's lower bound, in log space.
    :ivar high: Its upper bound, in log space.
    :ivar envelope: The control's magnitude, in log space.
    """

    verdict: Verdict
    low: float
    high: float
    envelope: float


def judge(row: str, pairing: Pairing, clock: str, undecided: str) -> Judged:
    """One row's interval against its control envelope, before any rule applies.

    :param undecided: What the judging tier calls a row it has not decided.
    """
    mean, low, high = log_interval(pairing.candidate)
    envelope = noise_envelope(pairing.control)
    return Judged(
        Verdict(
            row,
            undecided,
            math.exp(mean),
            math.exp(low),
            math.exp(high),
            math.exp(envelope),
            len(pairing.candidate),
            clock,
        ),
        low,
        high,
        envelope,
    )


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
    judged = judge(row, pairing, clock, "unresolved")
    if judged.low > judged.envelope:
        return judged.verdict._replace(status="slower")
    if judged.high < -judged.envelope:
        return judged.verdict._replace(status="faster")
    if judged.high <= judged.envelope:
        return judged.verdict._replace(status="ok")
    return judged.verdict
