"""Measure combined impact of mapping8 swap + EAFP resolve.

Strategy: apply the swap + monkey-patch IrTypeMap.resolve in mapping8 to use EAFP,
then time the ABNF self-host parse.
"""

from __future__ import annotations

import gc
import statistics
import time

# Establish baseline FIRST (original mapping.py)
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
    print(f"  {label:<70} median={med:7.1f}ms  stdev={stdev:5.2f}ms")
    return med


g = normalize(ABNF_GRAMMAR)
text = str(ABNF_FLAVOUR.apply(ABNF_GRAMMAR))
print(f"ABNF text length: {len(text)} chars")

print("\n== Baseline (original mapping.py) ==")
r0 = bench("recognize(g, text)", lambda: recognize(g, text))
p0 = bench("parse(g, text)", lambda: parse(g, text))

from lexic.exceptions import IrKeyError

# Now apply EAFP resolve patch to IrTypeMap IN mapping8 (since the engine uses mapping)
# We patch the actual class being used by the engine
from lexic.ir import mapping as _mapping_module
from lexic.ir.mapping import IrTypeMap


def _eafp_resolve(self, n):
    """EAFP resolve: table[type(n)] instead of table.get(type(n))."""
    table = self._index  # OLD mapping uses _index
    t = type(n)
    dyad = table.get(t)
    if dyad is not None:
        return dyad[1]
    for base in t.__mro__:
        dyad = table.get(base)
        if dyad is not None:
            return dyad[1]
    dyad = table.get(_mapping_module.IR_DEFAULT)
    if dyad is not None:
        return dyad[1]
    raise IrKeyError(f"{type(self).__name__}: no entry for {type(n).__name__}")


# Apply to the current (old) IrTypeMap
_orig_resolve = IrTypeMap.resolve
IrTypeMap.resolve = _eafp_resolve

# Invalidate cached instances

# Force re-import of engine to rebuild dispatch tables

print("\n== With EAFP resolve on old IrTypeMap ==")
r1 = bench("recognize(g, text) + EAFP resolve", lambda: recognize(g, text))
p1 = bench("parse(g, text) + EAFP resolve", lambda: parse(g, text))

IrTypeMap.resolve = _orig_resolve
print(f"\n  EAFP resolve: recognize {r0:.1f}→{r1:.1f}ms ({(r0 - r1) / r0 * 100:+.1f}%)")
print(f"  EAFP resolve: parse     {p0:.1f}→{p1:.1f}ms ({(p0 - p1) / p0 * 100:+.1f}%)")
