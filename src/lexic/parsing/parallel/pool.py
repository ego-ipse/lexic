"""Warm executors for split phases and independent document parses.

``WorkPool`` lets one document reuse its executor for differently typed scan,
piece-parse, and fallback phases. ``ParsePool`` binds one callable for callers
mapping whole documents repeatedly. Both bound pending submissions to one
buffer per worker and own deterministic shutdown through a context manager.

``cores`` reads as it does everywhere: 0 (the default) is as many as the
machine allows, 1 is sequential, N is that many — see :mod:`.policy`.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from types import TracebackType
from typing import Self

from lexic.parsing.parallel.policy import AUTO, doc_workers


class WorkPool:
    """One executor reused by differently typed phases of a split parse."""

    def __init__(self, cores: int = AUTO) -> None:
        """Resolve the worker ceiling and create the lazy executor."""
        self.workers = doc_workers(cores)
        self._pool = ThreadPoolExecutor(max_workers=self.workers)

    def map[T, M](self, work: Callable[[T], M], items: Sequence[T]) -> list[M]:
        """Apply ``work`` in order with at most one buffer per worker."""
        return list(self._pool.map(work, items, buffersize=self.workers))

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
