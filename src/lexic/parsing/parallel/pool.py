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
from types import TracebackType
from typing import Self, cast

from lexic.parsing.parallel.policy import AUTO, doc_workers


class WorkPool:
    """One executor reused by differently typed phases of a split parse."""

    def __init__(self, cores: int = AUTO) -> None:
        """Resolve the worker ceiling and create the lazy executor."""
        self.workers = doc_workers(cores)
        self._pool = ThreadPoolExecutor(max_workers=self.workers)

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
