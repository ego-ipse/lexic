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


MIN_SCAN = 4 * MIN_CHUNK
"""The least text one SCAN window should own — the scan's own floor.

A window is one C-level sweep per mark spelling plus a Python step per
occurrence: measured at 1.5 ns/char where a document holds a mark every 80
characters and 21 ns/char at its densest (four spellings, a mark every 9). One
pool task costs ~15 µs to hand out, so sixteen windows over a 34 KB document
spent 0.24 ms dispatching between 0.05 and 0.7 ms of work, and three of four
measured grammars scanned faster on one thread than on sixteen.

This is the SCAN's amortization point and not the parse's: :data:`MIN_CHUNK` is
what a 2.6 ms chunk parse amortizes, and scanning is two orders of magnitude
cheaper per byte than parsing. Splitting the document into parse chunks is
untouched by it.
"""

SCAN_DISPATCH_NS = 15_000
"""What handing ONE scan window to the pool costs, in nanoseconds.

The figure :data:`MIN_SCAN` is argued from, stated as a constant so the gate
beside it can do the arithmetic rather than restate the conclusion.
"""

SCAN_NS_PER_CHAR = 1.5
"""The CHEAPEST measured sweep rate, in nanoseconds per character.

The cheapest, deliberately. This is used to ask whether a sweep is worth
dispatching, so under-estimating the work is the conservative direction: a
document that clears the bar at 1.5 ns/char clears it at every denser rate
too, and one that does not is scanned on the driver, where the worst case is
the sweep the caller would have paid for anyway.
"""


def worth_dispatching(size: int, windows: int) -> bool:
    """Whether handing ``windows`` scan windows out beats scanning here.

    :data:`MIN_SCAN` bounds how many windows a document is BIG enough for; this
    asks whether its sweep is EXPENSIVE enough to hand out at all. A document
    can clear the size floor and still have a sweep so cheap that the hand-out
    costs more than the scan — measured at 0.17-0.45 occupancy on the cheap
    grammars, 0.3-1.6 ms of wall dispatched for 0.06-0.7 ms of work.

    Binary, and deliberately so. Shaving the window COUNT keeps every
    hand-out and removes only parallelism, which measured slower on all ten
    rows it was meant to help; the finding is that the map itself is the loss,
    so the answer is to make it or not make it.

    :param size: The document's length in characters.
    :param windows: How many windows the size floor and the worker count allow.
    :returns: Whether the sweep is worth more than its own dispatch.
    """
    return size * SCAN_NS_PER_CHAR >= windows * SCAN_DISPATCH_NS


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
