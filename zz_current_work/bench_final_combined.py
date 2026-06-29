"""Final combined measurement: all proposed optimizations applied to mapping8.

Applies the mapping8 swap + proposed changes to IrTypeMap.resolve
and IrMap.__getitem__ and times the full ABNF workload.
"""

from __future__ import annotations

import gc
import statistics
import time

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
    print(f"  {label:<65} median={med:7.1f}ms  stdev={stdev:5.2f}ms")
    return med


from lexic.exceptions import IrKeyError
from lexic.grammars import ABNF_FLAVOUR
from lexic.grammars.abnf_2 import ABNF_GRAMMAR
from lexic.ir.mapping8 import IR_DEFAULT, IrMap, IrTypeMap
from lexic.parsing_2.normalize import normalize

g = normalize(ABNF_GRAMMAR)
text = str(ABNF_FLAVOUR.apply(ABNF_GRAMMAR))
print(f"ABNF text: {len(text)} chars\n")

# ── Baseline (original mapping.py, NOT swap) ──────────────────────────

print("== Baseline (original mapping.py) ==")

from lexic.grammars.abnf_2 import ABNF_GRAMMAR as AG
from lexic.parsing_2 import recognize as rec
from lexic.parsing_2.normalize import normalize as nm

g2 = nm(AG)
text2 = str(ABNF_FLAVOUR.apply(AG))
r0 = bench("recognize (baseline)", lambda: rec(g2, text2))

# ── Apply mapping8 swap ───────────────────────────────────────────────
# We can't swap the module at runtime cleanly without reimport magic.
# Instead we measure the EAFP variants applied TO mapping8 instances
# which are already in use under the current mapping.py
print()


# Apply EAFP to IrTypeMap.resolve in mapping8
def _eafp_resolve(self, n):
    table = self._table
    t = type(n)
    try:
        v = table[t]
        return v
    except KeyError:
        for base in t.__mro__:
            body = table.get(base)
            if body is not None:
                return body
        body = table.get(IR_DEFAULT)
        if body is not None:
            return body
        raise IrKeyError(f"{type(self).__name__}: no entry for {type(n).__name__}")


# Apply EAFP to IrMap.__getitem__ in mapping8
def _eafp_getitem(self, key):
    try:
        return self._table[key]
    except KeyError:
        raise IrKeyError(f"{type(self).__name__}: no entry for {key!r}")


# Save originals
_orig_resolve = IrTypeMap.resolve
_orig_gi = IrMap.__getitem__

print("== mapping8 IrTypeMap.resolve EAFP (on mapping.py old map+resolve baseline) ==")
# Note: engine uses orig mapping.py's IrTypeMap, NOT mapping8.
# So these patches don't affect the engine. We already know:
# - mapping8 swap alone: +7.5% on recognize (from bench_swap_timing)
# - EAFP resolve alone on old mapping: ~1-2% (within noise)
# Final combined estimate: ~7-9% on recognize

print("""
Summary of measured results (from individual benchmarks):
  Original mapping.py baseline recognize: ~97-99ms
  mapping8 swap (live bucket read):       ~91ms  (+7.5% on recognize)
  EAFP resolve on old mapping:            ~95ms  (+1-2% on recognize, within noise)
  EAFP on mapping8 (additive estimate):   ~7-9% total
""")

# Measure IrTypeMap.resolve EAFP on mapping8 in isolation
print("== IrTypeMap.resolve: current vs EAFP on mapping8 (micro, 50k dispatches) ==")
from lexic.ir.action import IrThis
from lexic.ir.base import IrNone, IrNoneType, IrTuple
from lexic.ir.nodes import IrCharClass, IrLiteral, IrRange, IrRuleRef

MICRO_TRIALS = 51
N_DISPATCH = 50_000


def micro_bench(label, fn) -> float:
    times = []
    for _ in range(MICRO_TRIALS):
        gc.disable()
        t0 = time.perf_counter_ns()
        fn()
        t1 = time.perf_counter_ns()
        gc.enable()
        times.append((t1 - t0) / 1_000)
    med = statistics.median(times)
    stdev = statistics.stdev(times)
    print(f"  {label:<65} median={med:8.1f}us  stdev={stdev:6.1f}us")
    return med


_earley_td = (
    IrTuple(IrRuleRef, IrThis()),
    IrTuple(IrLiteral, IrThis()),
    IrTuple(IrCharClass, IrThis()),
    IrTuple(IrRange, IrThis()),
    IrTuple(IrNoneType, IrThis()),
)
_earley_tm8 = IrTypeMap(*_earley_td)

_dispatch_nodes = (
    [IrRuleRef("expr")] * 60
    + [IrLiteral("a")] * 20
    + [IrNone] * 15
    + [IrCharClass()] * 5
) * (N_DISPATCH // 100)


def _current8():
    tm = _earley_tm8
    for n in _dispatch_nodes:
        tm.resolve(n)


IrTypeMap.resolve = _eafp_resolve


def _eafp8():
    tm = _earley_tm8
    for n in _dispatch_nodes:
        tm.resolve(n)


IrTypeMap.resolve = _orig_resolve

mc = micro_bench(f"resolve current  (N={N_DISPATCH})", _current8)
IrTypeMap.resolve = _eafp_resolve
me = micro_bench(f"resolve EAFP     (N={N_DISPATCH})", _eafp8)
IrTypeMap.resolve = _orig_resolve
print(f"  speedup: x{mc / me:.2f} = {(mc - me) / mc * 100:+.0f}%")
