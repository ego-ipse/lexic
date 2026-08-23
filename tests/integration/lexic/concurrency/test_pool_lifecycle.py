"""Warm-pool leases, resets and failures, all under contention.

``PoolLease``'s docstring states the ownership rule outright: *every pool is
either lent to exactly one caller or idle in the cache*. That is what a lost
``_IDLE_LOCK`` hand-off would break, and it is testable without timing luck —
a worker registers the pool it holds and asserts on entry that nobody else
already holds it, so a double hand-off is caught the first time it happens
rather than the first time it happens to matter.

The other observables are ``_IDLE`` growing past ``RETAINED`` (a lost return),
a pool used after ``close()`` (``RuntimeError: cannot schedule new futures
after shutdown``), and a deadlock. Deadlocks are made to FAIL rather than
hang: every race here runs under the harness's deadline.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from functools import partial

from lexic.compile import CompiledGrammar, compile_text
from lexic.parsing.parallel import reset_pools
from lexic.parsing.parallel.pool import _IDLE, RETAINED, PoolLease, WorkPool
from tests.integration.lexic.concurrency.concurrency import clean, parallel
from tests.integration.lexic.concurrency.fixtures import SPLITTING, split_doc

WIDTH = 4
"""Pool width every lease in this module asks for."""

ROUNDS = 60
"""Lease take/return cycles per worker."""


class Ledger:
    """Which pools are lent right now — the ownership rule as a live check."""

    def __init__(self) -> None:
        """Start with nothing lent."""
        self._lock = threading.Lock()
        self.lent: set[int] = set()
        self.doubles: list[int] = []
        self.seen = 0

    def take(self, pool: WorkPool) -> None:
        """Record a lease, remembering it if the pool was already lent."""
        with self._lock:
            self.seen += 1
            if id(pool) in self.lent:
                self.doubles.append(id(pool))
            self.lent.add(id(pool))

    def give_back(self, pool: WorkPool) -> None:
        """Record the return."""
        with self._lock:
            self.lent.discard(id(pool))


def _boom(item: int) -> int:
    """Fail for every item — the isolated per-worker failure."""
    raise ValueError(f"item {item}")


def _borrow_repeatedly(index: int, ledger: Ledger) -> int:
    """Take and return a lease over and over, recording every hand-off."""
    del index
    for _ in range(ROUNDS):
        with PoolLease(WIDTH) as pool:
            ledger.take(pool)
            assert pool.map(str, [1, 2, 3]) == ["1", "2", "3"]
            ledger.give_back(pool)
    return ROUNDS


def _fail_inside_a_lease(index: int, ledger: Ledger) -> int:
    """Raise from inside the lease, which must close the pool, not cache it."""
    del index
    failures = 0
    for _ in range(ROUNDS):
        try:
            with PoolLease(WIDTH) as pool:
                ledger.take(pool)
                pool.map(_boom, [1])
        except ValueError:
            failures += 1
    return failures


def _parse_repeatedly(index: int, compiled: CompiledGrammar, text: str) -> int:
    """Keep leases genuinely in flight while somebody resets the cache."""
    del index
    for _ in range(4):
        assert compiled.parse(text, cores=WIDTH).to_text() == text
    return 4


def _reset_repeatedly(index: int, stop: threading.Event) -> int:
    """Empty the idle cache over and over, against live parses."""
    del index
    resets = 0
    while not stop.is_set():
        reset_pools()
        resets += 1
    return resets


def _run_pool_worker(
    index: int, workers: list[Callable[[int], int]], stop: threading.Event
) -> int:
    """Run this index's worker, releasing the reset loop when parsing ends.

    The reset worker spins until every parser has finished, so the two overlap
    for the whole parse rather than meeting at a single instant.
    """
    if index == len(workers) - 1:
        return workers[index](index)
    try:
        return workers[index](index)
    finally:
        stop.set()


def test_a_pool_is_never_lent_to_two_leases_at_once() -> None:
    """The ownership rule, checked on every hand-off rather than inferred."""
    reset_pools()
    ledger = Ledger()
    counts = clean(parallel(partial(_borrow_repeatedly, ledger=ledger), 8))
    assert counts == [ROUNDS] * 8
    assert ledger.seen == ROUNDS * 8, "leases were not all recorded"
    assert not ledger.doubles, f"one pool lent twice at once: {ledger.doubles}"
    assert not ledger.lent, "a lease was never returned"


def test_the_idle_cache_never_exceeds_its_retention_bound() -> None:
    """Contended returns respect ``RETAINED`` — a lost return would not."""
    reset_pools()
    ledger = Ledger()
    clean(parallel(partial(_borrow_repeatedly, ledger=ledger), 8))
    oversized = {
        width: len(waiting)
        for width, waiting in _IDLE.items()
        if len(waiting) > RETAINED
    }
    assert not oversized, f"idle cache past RETAINED={RETAINED}: {oversized}"


def test_a_failing_phase_closes_its_pool_instead_of_returning_it() -> None:
    """Each thread sees its OWN failure, and no failed pool is cached.

    A pool whose phase raised may still be draining work, so the lease closes
    it. Were a failed pool cached instead, a later borrower would find a
    shut-down executor and raise ``RuntimeError`` rather than parsing — which
    is what the second race here would surface.
    """
    reset_pools()
    ledger = Ledger()
    failures = clean(parallel(partial(_fail_inside_a_lease, ledger=ledger), 4))
    assert failures == [ROUNDS] * 4, "a thread lost its own exception"
    after = Ledger()
    clean(parallel(partial(_borrow_repeatedly, ledger=after), 4))
    assert not after.doubles


def test_reset_pools_during_in_flight_parses_neither_corrupts_nor_deadlocks() -> None:
    """``reset_pools`` closes only IDLE pools, so a live lease is untouched.

    That is the obligation this pins, and it is safe by structure rather than
    by luck: a lent pool is unreachable from ``_IDLE`` because the lease holds
    the only reference. The reset thread therefore runs flat out for the whole
    race, every parse must still be exact, and the race must finish inside the
    harness deadline — a reset that closed a lent pool would surface as a
    ``RuntimeError`` or as a worker that never returns.
    """
    compiled = compile_text(SPLITTING, cache_key="concurrency-pools")
    text = split_doc()
    assert compiled.parse(text, cores=1).to_text() == text

    stop = threading.Event()
    parsers = 4
    workers: list[Callable[[int], int]] = [
        partial(_parse_repeatedly, compiled=compiled, text=text)
    ] * parsers
    workers += [partial(_reset_repeatedly, stop=stop)]

    counts = clean(
        parallel(partial(_run_pool_worker, workers=workers, stop=stop), len(workers))
    )
    assert counts[:parsers] == [4] * parsers
    assert counts[-1] > 0, "the reset thread never ran — nothing raced"
