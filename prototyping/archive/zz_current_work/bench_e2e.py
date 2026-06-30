"""End-to-end ABNF self-host benchmark — recognize + parse.

Run AFTER swapping mapping.py -> mapping8 shim + ForestCtx migration.
Measures the real engine workload (the only thing that matters).
"""

from __future__ import annotations

import gc
import statistics
import sys
import time

from lexic.grammars import ABNF_FLAVOUR
from lexic.grammars.abnf_2 import ABNF_GRAMMAR
from lexic.parsing_2 import parse, recognize
from lexic.parsing_2.normalize import normalize

TRIALS = 25

g = normalize(ABNF_GRAMMAR)
text = str(ABNF_FLAVOUR.apply(ABNF_GRAMMAR))


def bench(label: str, fn) -> float:
    fn()  # warm
    times = []
    for _ in range(TRIALS):
        gc.disable()
        t0 = time.perf_counter_ns()
        fn()
        t1 = time.perf_counter_ns()
        gc.enable()
        times.append((t1 - t0) / 1_000_000)
    med = statistics.median(times)
    lo = min(times)
    stdev = statistics.stdev(times)
    print(f"  {label:<30} median={med:7.2f}ms  min={lo:7.2f}ms  stdev={stdev:5.2f}")
    return med


label = sys.argv[1] if len(sys.argv) > 1 else "run"
print(f"== {label}  (ABNF self-host, {len(text)} chars, {TRIALS} trials) ==")
bench("recognize", lambda: recognize(g, text))
bench("parse", lambda: parse(g, text))
