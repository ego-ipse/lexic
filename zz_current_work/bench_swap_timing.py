"""Timing benchmark for the validation swap (mapping8 active via mapping.py shim).

Measures ABNF self-host parse time and full-suite proxy timing.
"""

from __future__ import annotations

import gc
import statistics
import time

from lexic.grammars import ABNF_FLAVOUR
from lexic.grammars.abnf_2 import ABNF_GRAMMAR
from lexic.parsing_2 import parse, recognize
from lexic.parsing_2.normalize import normalize

TRIALS = 15


def bench(label, fn) -> float:
    times = []
    for _ in range(TRIALS):
        gc.disable()
        t0 = time.perf_counter_ns()
        fn()
        t1 = time.perf_counter_ns()
        gc.enable()
        times.append((t1 - t0) / 1_000_000)
    med = statistics.median(times)
    stdev = statistics.stdev(times)
    print(f"  {label:<50} median={med:7.1f}ms  stdev={stdev:5.2f}ms")
    return med


g = normalize(ABNF_GRAMMAR)
text = str(ABNF_FLAVOUR.apply(ABNF_GRAMMAR))

print(f"\nABNF text length: {len(text)} chars")
print(f"\n== ABNF self-host parse (recognize + parse, {TRIALS} trials) ==")

bench("recognize(g, text)", lambda: recognize(g, text))
bench("parse(g, text)", lambda: parse(g, text))
