"""Worker-count policy — how many parses run beside each other.

``cores`` means the same thing at every entry point that takes it:

- **0 (the default)** — as many as this machine and this work allow. On a
  free-threaded interpreter that is the cpu count; under the GIL it is 1,
  because threaded parsing there measured a net loss (0.82–0.92×).
- **1** — sequential, explicitly. The one way to say "do not thread".
- **N** — at most that many workers. An explicit number chooses the ceiling;
  the measured per-worker document floor still applies because sub-floor
  chunks are overhead rather than useful parallel work.

Splitting ONE document additionally needs enough of it to divide: below
:data:`MIN_CHUNK` per worker the overhead dominates, and there can never be
more useful workers than chunks.
"""

from __future__ import annotations

import os
import sys

AUTO = 0
"""``cores=AUTO`` — as many workers as the machine and the work allow."""

MIN_CHUNK = 2 * 1024
"""The least text one worker should own — the amortization floor.

Measured (3.14t, 16 cpus): a worker's share of ``ParsePool`` build+map+close
is 56–300 µs, the replicas are ≤ 1 µs, and parsing runs ~1.3 µs/char — so a
2 KiB chunk parses for ~2.6 ms and the pool cost stays under ~12% of it.
A recorded result, not a tunable: if a later measurement moves the
amortization point, this constant moves to what was measured.
"""


def _free_threaded() -> bool:
    """Whether this interpreter runs without the GIL (free-threaded build)."""
    gil_enabled = getattr(sys, "_is_gil_enabled", None)
    return gil_enabled is not None and not gil_enabled()


def available_workers() -> int:
    """The most workers worth starting here — the meaning of ``cores=AUTO``.

    :returns: The cpu count on a free-threaded build, else 1.
    """
    if not _free_threaded():
        return 1
    return os.process_cpu_count() or 1


def doc_workers(cores: int = AUTO) -> int:
    """Workers for DOCUMENT-level parallelism — N documents, one artefact.

    No size floor applies: the caller already has whole documents in hand.

    :param cores: 0 = auto, 1 = sequential, N = that many.
    :returns: The worker count, at least 1.
    """
    return available_workers() if cores == AUTO else max(1, cores)


def worker_count(size: int, splits: int, cores: int = AUTO) -> int:
    """Workers for splitting ONE document of ``size`` at ``splits`` points.

    :param size: Document length in characters.
    :param splits: How many split points the scan found — ``splits + 1``
        chunks bound the useful worker count however many cores exist.
    :param cores: 0 = auto, 1 = sequential, N = that ceiling. Every form is
        clamped by the measured chunk floor and the number of available chunks.
    :returns: The worker count, at least 1.
    """
    chunks = splits + 1
    requested = available_workers() if cores == AUTO else cores
    return max(1, min(requested, size // MIN_CHUNK, chunks))
