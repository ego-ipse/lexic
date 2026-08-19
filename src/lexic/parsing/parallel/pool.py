"""The work pool — N independent parses in flight against one callable.

Lexic owns the threading: a caller hands the pool a per-item callable
(typically ``CompiledGrammar.parse``, or a window scan) and maps items over
it. The pool is warm — workers persist across ``map`` calls — because
thread creation is the one cost that would otherwise recur per batch.

``cores`` reads as it does everywhere: 0 (the default) is as many as the
machine allows, 1 is sequential, N is that many — see :mod:`.policy`.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor

from lexic.parsing.parallel.policy import AUTO, doc_workers


class ParsePool[T, M]:
    """A warm worker pool mapping items over one callable.

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
        self.workers = doc_workers(cores)
        self._work = work
        self._pool = ThreadPoolExecutor(max_workers=self.workers)

    def map(self, items: Sequence[T]) -> list[M]:
        """Apply the callable to every item, up to ``workers`` in flight.

        :param items: The work items, in the order results are wanted.
        :returns: One result per item, in input order.
        :raises Exception: The first failing item's own exception — a pool
            changes WHEN work runs, never what a failure means.
        """
        return list(self._pool.map(self._work, items))

    def close(self) -> None:
        """Shut the workers down; the pool is not reusable afterwards."""
        self._pool.shutdown()
