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
from collections.abc import Iterable

AUTO = 0
"""``cores=AUTO`` — as many workers as the machine and the work allow."""

MIN_CHUNK = 2 * 1024
"""The least text one worker should own — the amortization floor.

Measured (3.14t, 16 cpus; every benchmark-roster row's ``full`` document
parsed with ``cores=1``, default and ``@lexical``/``@non-semantic`` seats):
parsing costs 0.03–39 µs/char, median 0.93, so a 2 KiB chunk parses for
66 µs at the cheapest row and ~1.9 ms at the median. A cold pool's
build+map+close is ~1 ms across its workers — 61 µs each at 16, 564 at 2 —
and handing a leased warm pool one more chunk costs 7–21 µs (``WorkPool.map``
of trivial work, 2–16 workers). A recorded result, not a tunable: if a later
measurement moves the amortization point, this constant moves to what was
measured.
"""


MIN_PIECE = MIN_CHUNK // 2
"""The least text one piece of a split may hold once its cuts have snapped to
marks — how far under :data:`MIN_CHUNK` a piece may fall before the chooser
looks for another mark or takes one worker fewer.

The worker COUNT is what :data:`MIN_CHUNK` caps (:func:`capacity`); a cut then
lands on the mark nearest its even share, so one piece may come out short.
Dropping a worker for that idles a core that would still win: on
:data:`MIN_CHUNK`'s measurement a 1 KiB piece parses for 33 µs at the
cheapest row and ~0.95 ms at the median, against 7–21 µs to hand a warm pool
one more piece. A piece far under this floor is the one worth refusing.
"""


def clears_floor(widths: Iterable[int]) -> bool:
    """Whether every piece a split hands a worker holds :data:`MIN_PIECE`.

    THE per-piece floor: every chooser that cuts a document asks it of the
    pieces it chose, in its own offsets, and declines (or chooses fewer) when
    it fails.

    :param widths: The width of each piece, in characters.
    """
    return all(width >= MIN_PIECE for width in widths)


def capacity(size: int) -> int:
    """How many workers ``size`` characters can feed at :data:`MIN_CHUNK`
    each — the worker COUNT's cap. Not the per-piece floor: a piece clears
    that at :data:`MIN_PIECE` (:func:`clears_floor`)."""
    return size // MIN_CHUNK


MIN_SCAN = 4 * MIN_CHUNK
"""The least text one SCAN window should own — the scan's own floor.

A window is one C-level sweep per mark spelling plus a Python step per
occurrence: measured at 1.5 ns/char where a document holds a mark every 80
characters and 21 ns/char at its densest (four spellings, a mark every 9). One
pool task costs ~15 µs to hand out, so sixteen windows over a 34 KB document
spent 0.24 ms dispatching between 0.05 and 0.7 ms of work, and three of four
measured grammars scanned faster on one thread than on sixteen.

This is the SCAN's amortization point and not the parse's: :data:`MIN_CHUNK` is
what a chunk parse (~1.9 ms at the median) amortizes, and scanning is two
orders of magnitude cheaper per byte than parsing. Splitting the document into
parse chunks is untouched by it.
"""


def free_threaded() -> bool:
    """Whether this interpreter runs without the GIL (free-threaded build)."""
    gil_enabled = getattr(sys, "_is_gil_enabled", None)
    return gil_enabled is not None and not gil_enabled()


def available_workers() -> int:
    """The most workers worth starting here — the meaning of ``cores=AUTO``.

    :returns: The cpu count on a free-threaded build, else 1.
    """
    if not free_threaded():
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
    return max(1, min(requested, capacity(size), chunks))
