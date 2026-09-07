"""How one pass is TIMED, and how several are reduced to one number.

The sampling protocol, kept apart from what a row is and how it is built: a
figure only means something with the state it was taken in stated beside it —
the collector left enabled, the engine primed, one untimed pass of the row
immediately before its timed one, and the median of independent passes rather
than the fastest.
"""

from __future__ import annotations

import gc
import random
import time
from collections.abc import Callable
from typing import NamedTuple

Parse = Callable[[str], object]
"""One engine's parse entry point — text in, whatever that engine builds out."""


class Pass(NamedTuple):
    """One timed pass on both clocks, in seconds.

    :ivar wall: ``perf_counter`` — latency, and the only honest clock for a row
        whose work happens on other threads.
    :ivar cpu: ``process_time`` — total work this process did, summed across
        its threads. A parallel path that wins on wall while burning far more
        CPU per byte is a real finding, and one clock cannot show it.
    """

    wall: float
    cpu: float


def timed(parse: Parse, corpus: str) -> Pass:
    """One pass with the collector LEFT ENABLED, on both clocks.

    Production parsing does not disable the collector, so a row that does is
    not measuring production: it hides allocation and cycle-creation cost and,
    if the parse raises, used to leave the collector off for everything after.

    An engine that measured the pass ITSELF is believed over the wall clock: the
    Java row runs in a live JVM, and a `perf_counter` around it would charge
    ANTLR for the pipe carrying the input across.
    """
    cpu_start = time.process_time()
    wall_start = time.perf_counter()
    parse(corpus)
    wall = time.perf_counter() - wall_start
    cpu = time.process_time() - cpu_start
    inner = getattr(parse, "measured_us", None)
    return Pass(inner() / 1e6 if inner else wall, cpu)


def once(parse: Parse, corpus: str) -> float:
    """Microseconds per input character for one timed pass — the report's cell."""
    return timed(parse, corpus).wall * 1e6 / len(corpus)


def prime(parse: Parse, corpus: str) -> None:
    """Bring one engine to steady state before any round counts.

    A JIT-compiled engine's first parses are not the engine — the Java row's
    first is ~20x its settled cost. `warm` parses a budget that clears the JIT's
    last step down; an engine without one gets the single pass it always got.
    """
    warm = getattr(parse, "warm", None)
    if warm is None:
        parse(corpus)
        return
    warm(corpus)


def interleaved(
    engines: dict[str, Parse], texts: dict[str, str], rounds: int
) -> dict[str, list[float]]:
    """Low-level sampler used inside one isolated worker.

    ``texts`` names each row's document: the mt rows always read the full
    corpus, everyone else reads whatever the ``--full`` decision assigned.

    Each pass is followed by an UNTIMED ``gc.collect()``. The collector stays
    ENABLED inside the timed pass, so a row pays its own allocation cost; the
    collect afterwards only stops one sample's garbage landing in the next.
    The same operation is applied to every row, so it cannot favour an arm.

    Immediately before its timed pass, each row gets one untimed pass of ITSELF.
    This keeps every sample in the same hot-parse state even after allocator or
    collection work. The reported noun remains ONE timed parse and the
    statistic remains the median — no batching or fastest-run selection.
    """
    for name, parse in engines.items():
        prime(parse, texts[name])
    samples: dict[str, list[float]] = {name: [] for name in engines}
    seats = list(engines.items())
    rng = random.Random(0x5EA75)
    for _ in range(rounds):
        rng.shuffle(seats)
        for name, parse in seats:
            parse(texts[name])
            samples[name].append(once(parse, texts[name]))
            gc.collect()
    return samples


def medians(samples: dict[str, list[float]]) -> dict[str, float]:
    """Each row's reported figure: the median of its per-round passes."""
    return {name: sorted(runs)[len(runs) // 2] for name, runs in samples.items()}


def noise_spread(parse: Parse, corpus: str, rounds: int) -> float:
    """Spread between two timings of the SAME engine, as a percentage.

    Anything below this is not a result. Printing it is what stops a 2%
    difference being read as a finding.
    """
    first = medians(interleaved({"a": parse}, {"a": corpus}, rounds))["a"]
    second = medians(interleaved({"a": parse}, {"a": corpus}, rounds))["a"]
    return abs(first - second) / max(first, second, 1e-9) * 100
