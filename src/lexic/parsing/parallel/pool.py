"""The document pool — N documents in flight against one parse callable.

Lexic owns the threading for document-level parallelism: a caller hands the
pool its parse entry (typically ``CompiledGrammar.parse``) and maps texts
over it. The pool is warm — workers persist across ``map`` calls — because
thread creation is the one cost that would otherwise recur per batch.

Worker count comes from the policy: auto is the cpu count on a
free-threaded build and 1 under the GIL (where threaded parsing measured a
net loss); an explicit ``cores`` is a decision and is used as given.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor

from lexic.parsing.parallel.policy import doc_workers


class ParsePool[M]:
    """A warm worker pool mapping documents over one parse callable.

    :ivar workers: The resolved worker count (policy auto, or the caller's
        explicit ``cores``).
    """

    def __init__(self, parse: Callable[[str], M], cores: int | None = None) -> None:
        """Size the pool by policy and start its workers.

        :param parse: The per-document parse entry (thread-safe: one shared
            compiled artefact, per-parse state constructed per call).
        :param cores: Explicit worker count; ``None`` selects the policy's
            auto answer.
        """
        self.workers = doc_workers(cores)
        self._parse = parse
        self._pool = ThreadPoolExecutor(max_workers=self.workers)

    def map(self, texts: Sequence[str]) -> list[M]:
        """Parse every text, up to ``workers`` in flight, order preserved.

        :param texts: The documents to parse.
        :returns: One model per text, in input order.
        :raises Exception: The first failing parse's own exception — a pool
            changes WHEN documents parse, never what a failure means.
        """
        return list(self._pool.map(self._parse, texts))

    def close(self) -> None:
        """Shut the workers down; the pool is not reusable afterwards."""
        self._pool.shutdown()
