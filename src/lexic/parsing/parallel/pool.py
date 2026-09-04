"""Warm executors for split phases and independent document parses.

``WorkPool`` lets one document reuse its executor for differently typed scan,
piece-parse, and fallback phases. ``ParsePool`` binds one callable for callers
mapping whole documents repeatedly. Both admit work from completion order so
uneven work does not strand workers, bound pending futures, and own
deterministic shutdown through a context manager.

``cores`` reads as it does everywhere: 0 (the default) is as many as the
machine allows, 1 is sequential, N is that many — see :mod:`.policy`.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from itertools import count
from threading import Lock, local
from types import TracebackType
from typing import Self, cast

from lexic.parsing.parallel.policy import AUTO, doc_workers


class WorkPool:
    """One executor reused by differently typed phases of a split parse."""

    def __init__(self, cores: int = AUTO) -> None:
        """Resolve the worker ceiling and create the lazy executor."""
        self.workers = doc_workers(cores)
        self._pool = ThreadPoolExecutor(max_workers=self.workers)
        self._slots = local()
        self._taken = count()
        self._slot_lock = Lock()

    def slot(self) -> int:
        """The calling WORKER thread's own index in ``range(self.workers)``.

        Numbered by the pool because the pool owns the threads, and stable for
        the thread's whole life — which is what lets a per-worker artefact stay
        with one thread across documents. Indexing such an artefact by the task
        instead moves a worker onto a different one almost every document, and
        under free threading a read of an object another thread allocated is an
        atomic reference count rather than a local one.

        The executor never runs more than ``workers`` threads, so the modulo is
        a bound and not a wrap: two live workers cannot share a slot.
        """
        mine = getattr(self._slots, "at", None)
        if mine is None:
            with self._slot_lock:
                mine = next(self._taken) % self.workers
            self._slots.at = mine
        return mine

    def map[T, M](self, work: Callable[[T], M], items: Sequence[T]) -> list[M]:
        """Keep a bounded ready queue, return in order, and isolate failure."""
        results: list[M | None] = [None] * len(items)
        futures: dict[Future[M], int] = {}
        failures: dict[int, BaseException] = {}
        next_item = 0
        try:
            while next_item < len(items) or futures:
                while next_item < len(items) and len(futures) < 4 * self.workers:
                    future = self._pool.submit(work, items[next_item])
                    futures[future] = next_item
                    next_item += 1
                completed = wait(futures, return_when=FIRST_COMPLETED)[0]
                for future in sorted(completed, key=futures.__getitem__):
                    index = futures.pop(future)
                    try:
                        results[index] = future.result()
                    except BaseException as error:  # pylint: disable=broad-exception-caught
                        # Drain the phase even for process-control exceptions.
                        failures[index] = error
                if failures:
                    failed_at = min(failures)
                    for future, index in futures.items():
                        if index > failed_at:
                            future.cancel()
                    wait(futures)
                    for future, index in futures.items():
                        if future.cancelled():
                            continue
                        try:
                            results[index] = future.result()
                        except BaseException as error:  # pylint: disable=broad-exception-caught
                            # Preserve the earliest input's original failure.
                            failures[index] = error
                    raise failures[min(failures)]
        except BaseException:
            for future in futures:
                future.cancel()
            wait(futures)
            raise
        return cast(list[M], results)

    def close(self) -> None:
        """Shut the executor down after every submitted phase completes."""
        self._pool.shutdown()

    def __enter__(self) -> Self:
        """Return this pool for a bounded multi-phase lifetime."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Close the executor on success or failure."""
        self.close()


class ParsePool[T, M]:
    """A warm worker pool binding one callable for repeated maps.

    Generic in both ends: ``ParsePool[str, GrammarModel]`` parses documents,
    ``ParsePool[tuple[int, int], Window]`` scans windows. The item type is
    the caller's, which is what keeps the pool from being a document-only
    thing that a second kind of work would have to duplicate.

    :ivar workers: The resolved worker count.
    """

    def __init__(self, work: Callable[[T], M], cores: int = AUTO) -> None:
        """Size the pool by policy and start its workers.

        :param work: The per-item callable (thread-safe: one shared
            compiled artefact, per-parse state constructed per call).
        :param cores: 0 = auto, 1 = sequential, N = that many.
        """
        self._work = work
        self._pool = WorkPool(cores)
        self.workers = self._pool.workers

    def map(self, items: Sequence[T]) -> list[M]:
        """Apply the callable to every item, up to ``workers`` in flight.

        :param items: The work items, in the order results are wanted.
        :returns: One result per item, in input order.
        :raises Exception: The first failing item's own exception — a pool
            changes WHEN work runs, never what a failure means.
        """
        return self._pool.map(self._work, items)

    def close(self) -> None:
        """Shut the workers down; the pool is not reusable afterwards."""
        self._pool.close()

    def __enter__(self) -> Self:
        """Return this pool for repeated maps within one owned lifetime."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Close the executor on success or failure."""
        self.close()


RETAINED = 2
"""Idle pools kept per worker count.

A split parse borrows one pool and returns it, so a caller parsing document
after document pays the executor's build and shutdown once rather than every
time — measured at 308, 562 and 598 microseconds for 2, 8 and 16 workers, which
is a tenth of a small document's entire parse. Two is enough for a second
concurrent call to find one warm without retaining threads a workload never
asks for again.
"""

_IDLE: dict[int, list[WorkPool]] = {}
_IDLE_LOCK = Lock()


class PoolLease:
    """A pool borrowed from the warm cache for one split, then returned.

    Returned only on a clean exit. A phase that raised may have left work in
    flight that :meth:`WorkPool.map` is still draining, and a pool of unknown
    state is not worth the microseconds it saves — that one is closed.

    Ownership is explicit: every pool is either lent to exactly one caller or
    idle in :data:`_IDLE`, and :func:`reset_pools` empties the cache.
    """

    def __init__(self, cores: int = AUTO) -> None:
        """Resolve the worker ceiling this lease needs."""
        self.workers = doc_workers(cores)
        self._pool: WorkPool | None = None

    def __enter__(self) -> WorkPool:
        """Take a warm pool of the right width, or start one."""
        with _IDLE_LOCK:
            waiting = _IDLE.get(self.workers)
            self._pool = waiting.pop() if waiting else None
        if self._pool is None:
            self._pool = WorkPool(self.workers)
        return self._pool

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Return the pool to the cache, or close it."""
        pool, self._pool = self._pool, None
        if pool is None:
            return
        if exc_type is not None:
            pool.close()
            return
        with _IDLE_LOCK:
            waiting = _IDLE.setdefault(self.workers, [])
            spare = len(waiting) < RETAINED
            if spare:
                waiting.append(pool)
        if not spare:
            pool.close()


def reset_pools() -> None:
    """Close every idle pool — the deterministic seam tests and callers use."""
    with _IDLE_LOCK:
        idle = [pool for waiting in _IDLE.values() for pool in waiting]
        _IDLE.clear()
    for pool in idle:
        pool.close()
