"""Worker-count policy — how many parses run beside each other.

The measured constraints (one shared artefact, real cores): a GIL build
LOSES from splitting (0.82–0.92×), so auto mode gates on the free-threaded
interpreter; chunks below ~64 KiB drown in overhead; SMT past the physical
cores added little. An explicit caller override is respected — clamped only
by the structural bound (one worker more than there are split points) —
because an explicit ask is a decision, not a request for the heuristics.
"""

from __future__ import annotations

import os
import sys

MIN_CHUNK = 64 * 1024
"""The floor a chunk must clear for splitting to pay — measured 50–100 KB."""


def _free_threaded() -> bool:
    """Whether this interpreter runs without the GIL (free-threaded build)."""
    gil_enabled = getattr(sys, "_is_gil_enabled", None)
    return gil_enabled is not None and not gil_enabled()


def doc_workers(cores: int | None = None) -> int:
    """The worker count for DOCUMENT-level parallelism (no chunk floor).

    :param cores: Explicit override, used as given (floored at 1). ``None``
        selects auto: 1 on a GIL build, else the cpu count.
    :returns: The worker count, at least 1.
    """
    if cores is not None:
        return max(1, cores)
    if not _free_threaded():
        return 1
    return os.process_cpu_count() or 1


def worker_count(size: int, splits: int, cores: int | None = None) -> int:
    """The number of workers a document of ``size`` chars should get.

    :param size: Document length in characters.
    :param splits: How many split points the scan found (``splits + 1``
        chunks bound the useful worker count).
    :param cores: Explicit override — used as given, clamped to the
        structural bound only. ``None`` selects auto: 1 on a GIL build,
        else ``min(cpus, size // MIN_CHUNK, splits + 1)``.
    :returns: The worker count, at least 1.
    """
    if cores is not None:
        return max(1, min(cores, splits + 1))
    if not _free_threaded():
        return 1
    cpus = os.process_cpu_count() or 1
    return max(1, min(cpus, size // MIN_CHUNK, splits + 1))
