"""Barrier-started thread races, and the witness that makes one count.

A concurrency test's characteristic failure is passing without ever having
raced: threads that ran end to end, a window too narrow to hit, an assertion
that holds either way. Two devices here answer that. Every race records the
most workers it ever had in flight at once, and :func:`clean` refuses a result
whose peak says the work was effectively sequential. And a wedged worker is a
failure, not a hang — threads are daemons joined with a deadline, so a
deadlock reports itself instead of taking the suite down with it.
"""

from __future__ import annotations

import sys
import threading
from collections.abc import Callable, Sequence
from concurrent.futures import Future, ThreadPoolExecutor, wait
from functools import partial
from typing import NamedTuple

TIMEOUT = 120.0
"""Deadline for one race, in seconds. Generous — it is a deadlock detector,
not a performance gate, and a loaded machine must not trip it."""


def _free_threaded() -> bool:
    """Whether this interpreter runs without the GIL right now.

    A free-threading BUILD still runs WITH the GIL under ``PYTHON_GIL=1``,
    which is how the weak witness is obtained — so the runtime question is the
    one worth asking, not the build's.
    """
    gil_enabled = getattr(sys, "_is_gil_enabled", None)
    return gil_enabled is not None and not gil_enabled()


FREE_THREADED = _free_threaded()
"""Whether the GIL is off for this run."""

OVERLAP = 2 if FREE_THREADED else 1
"""The overlap :func:`clean` demands by default.

Two workers genuinely in flight at once is the free-threaded bar. Under the
GIL it is unreachable for short CPU-bound work — a worker can finish inside a
single interpreter slice, so "in flight together" is not a property that build
can offer, and demanding it would fail every test for the wrong reason. This is
what makes the GIL build the WEAK witness: it re-runs the same assertions about
results, having proven less about how they were produced. A test that needs
true simultaneity on both builds forces it with a barrier inside the work and
passes ``least`` explicitly.
"""


class Outcome[T](NamedTuple):
    """What one worker produced: a value, or the exception it raised.

    :ivar value: The worker's return, or ``None`` when it raised.
    :ivar error: The exception it raised, or ``None`` when it returned.
    """

    value: T | None
    error: Exception | None


class RaceResult[T](NamedTuple):
    """Every worker's outcome, plus the evidence that they overlapped.

    :ivar outcomes: One per worker, in worker order.
    :ivar peak: The most workers observed in flight simultaneously. A peak of
        1 means the race never happened and whatever it proved is worthless.
    """

    outcomes: list[Outcome[T]]
    peak: int

    @property
    def raised(self) -> list[Exception]:
        """Every exception any worker raised, in worker order."""
        return [out.error for out in self.outcomes if out.error is not None]


class Flight:
    """Live-worker counter and its high-water mark — the overlap witness.

    The counter takes a lock, the guarded work does not: serialising two
    integer updates around the entry and exit of a parse cannot serialise the
    parse, so measuring the overlap does not destroy it.
    """

    def __init__(self) -> None:
        """Start empty."""
        self._lock = threading.Lock()
        self.live = 0
        self.peak = 0

    def enter(self) -> None:
        """Record one more worker in flight."""
        with self._lock:
            self.live += 1
            self.peak = max(self.peak, self.live)

    def leave(self) -> None:
        """Record one worker leaving."""
        with self._lock:
            self.live -= 1


def _run_one[T](
    work: Callable[[], T],
    start: threading.Barrier,
    counted: threading.Barrier,
    flight: Flight,
) -> T:
    """One worker: wait for the start gun, register, wait for every worker to
    have registered too, THEN run inside the flight count.

    A single gate is not enough: a worker released from ``start`` can be
    descheduled before it reaches ``flight.enter()``, so an unlucky worker can
    finish its own ``enter``/``work``/``leave`` cycle before a slower sibling
    ever calls ``enter`` — ``peak`` then reads 1 despite every worker having
    been released together, which is a deschedule the counting missed, not an
    absence of concurrency. The second barrier closes that gap structurally:
    no worker may proceed to ``work()`` until every worker has already called
    ``flight.enter()``, so ``peak`` reaches the full worker count by
    construction rather than by scheduling luck.

    Exceptions are not caught here. The worker runs on a future, which carries
    whatever it raised back to :func:`race` — so the harness records a failure
    without ever standing between an exception and the caller.
    """
    start.wait()
    flight.enter()
    counted.wait()
    try:
        return work()
    finally:
        flight.leave()


def _outcome[T](future: Future[T]) -> Outcome[T]:
    """One finished future as a value-or-error pair."""
    error = future.exception()
    if error is not None:
        assert isinstance(error, Exception)
        return Outcome(None, error)
    return Outcome(future.result(), None)


def race[T](
    works: Sequence[Callable[[], T]], *, timeout: float = TIMEOUT
) -> RaceResult[T]:
    """Run every callable on its own thread, released together from one gate.

    :param works: One zero-argument callable per worker.
    :param timeout: Seconds to wait for all workers before failing.
    :returns: Each worker's outcome and the peak overlap observed.
    :raises AssertionError: A worker was still running at the deadline.
    """
    start = threading.Barrier(len(works))
    counted = threading.Barrier(len(works))
    flight = Flight()
    pool = ThreadPoolExecutor(max_workers=len(works))
    try:
        futures = [
            pool.submit(_run_one, work, start, counted, flight) for work in works
        ]
        pending = wait(futures, timeout=timeout)[1]
        assert not pending, (
            f"{len(pending)} of {len(works)} workers still running after "
            f"{timeout}s — deadlock"
        )
        return RaceResult([_outcome(future) for future in futures], flight.peak)
    finally:
        # Never block on shutdown: a wedged worker must fail the assertion
        # above, not hang the suite behind a join that will never return.
        pool.shutdown(wait=False)


def parallel[T](
    work: Callable[[int], T], count: int, *, timeout: float = TIMEOUT
) -> RaceResult[T]:
    """Race ``count`` workers over one indexed callable.

    :param work: Called with the worker's own index.
    :param count: How many workers to start.
    :param timeout: Seconds to wait for all workers before failing.
    :returns: Each worker's outcome and the peak overlap observed.
    """
    return race([partial(work, index) for index in range(count)], timeout=timeout)


def clean[T](result: RaceResult[T], *, least: int = OVERLAP) -> list[T]:
    """Every worker's value, once the race is proven clean AND non-vacuous.

    :param result: What :func:`race` or :func:`parallel` returned.
    :param least: The overlap the caller needs to have happened. Passing 1
        waives the witness and must be justified where it is written.
    :returns: One value per worker, in worker order.
    :raises Exception: The first worker exception, with its own traceback.
    :raises AssertionError: The workers never overlapped that far.
    """
    if result.raised:
        raise result.raised[0]
    assert result.peak >= least, (
        f"workers never overlapped ({result.peak} at peak, needed {least}) — "
        "this race proved nothing"
    )
    values = [out.value for out in result.outcomes]
    assert all(value is not None for value in values), "a worker recorded nothing"
    return [value for value in values if value is not None]
