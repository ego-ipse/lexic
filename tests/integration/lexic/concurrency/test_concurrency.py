"""The harness itself — because every other test in this lane trusts it.

The lane's green means something only if the harness can see corruption when
corruption happens. So one test here drives it over work that is deliberately
unsafe, arranged so the lost update is DETERMINISTIC rather than lucky: both
workers read before either writes, forced by a barrier between the read and
the write. If the harness ever stops reporting that, every clean run beside it
is worthless and this test says so first.
"""

from __future__ import annotations

import threading
from functools import partial

import pytest

from tests.integration.lexic.concurrency.concurrency import (
    Flight,
    clean,
    parallel,
    race,
)

WORKERS = 4


def _lost_update(index: int, box: list[int], gate: threading.Barrier) -> int:
    """A read-modify-write split by a barrier — the update is always lost."""
    del index
    seen = box[0]
    gate.wait()
    box[0] = seen + 1
    return box[0]


def _gated_index(index: int, gate: threading.Barrier) -> int:
    """Return the index, but only once every worker has arrived."""
    gate.wait()
    return index


def _reciprocal(index: int) -> float:
    """Divide by the index — worker zero raises, the rest do not."""
    return 1 / index


def _identity(index: int) -> int:
    """Return the index, immediately."""
    return index


def test_the_harness_reports_a_deterministically_lost_update() -> None:
    """The control: N workers increment, the barrier makes N-1 updates vanish.

    This is the harness's own falsifiability check. The work is genuinely
    unsafe and its failure is forced rather than raced — so a harness that
    reported this as fine would be reporting nothing at all.
    """
    box = [0]
    gate = threading.Barrier(WORKERS)
    result = parallel(partial(_lost_update, box=box, gate=gate), WORKERS)
    clean(result, least=WORKERS)
    assert box[0] == 1, "the barrier should have forced every write to see 0"
    assert box[0] != WORKERS, "a correct counter would have reached WORKERS"


def test_a_worker_exception_reaches_the_caller_with_its_own_traceback() -> None:
    """``clean`` re-raises the worker's exception rather than a wrapper."""
    result = parallel(_reciprocal, WORKERS)
    assert len(result.raised) == 1  # only worker zero divides by zero
    with pytest.raises(ZeroDivisionError):
        clean(result)


def test_the_overlap_witness_refuses_a_race_that_never_overlapped() -> None:
    """One worker cannot overlap, so ``clean`` refuses the result outright."""
    result = parallel(_identity, 1)
    assert result.peak == 1
    with pytest.raises(AssertionError, match="proved nothing"):
        clean(result, least=2)  # explicit: the GIL build's default is 1


def test_workers_released_from_the_gate_overlap_to_the_full_width() -> None:
    """A barrier inside the work forces every worker in flight at once."""
    gate = threading.Barrier(WORKERS)
    result = parallel(partial(_gated_index, gate=gate), WORKERS)
    assert clean(result, least=WORKERS) == list(range(WORKERS))


def test_a_wedged_worker_fails_the_race_rather_than_hanging_it() -> None:
    """The deadline turns a deadlock into an assertion, which is the point."""
    forever = threading.Event()
    with pytest.raises(AssertionError, match="deadlock"):
        race([forever.wait, forever.wait], timeout=0.5)
    forever.set()


def test_flight_tracks_its_high_water_mark_not_its_current_depth() -> None:
    """The witness reports the peak, which is what a later assert needs."""
    flight = Flight()
    flight.enter()
    flight.enter()
    flight.leave()
    flight.leave()
    assert flight.live == 0
    assert flight.peak == 2
