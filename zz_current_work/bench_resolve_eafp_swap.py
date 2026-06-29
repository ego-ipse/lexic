"""Measure EAFP resolve optimization on real workload.

Strategy: patch IrTypeMap.resolve in mapping8 temporarily, then run the ABNF
self-host parse to measure the delta from EAFP alone.

We can't easily swap just resolve without modifying mapping8.py (which we
must not do permanently), so instead we benchmark the dispatch-intensive
recognition loop by wrapping it with patched instances.
"""

from __future__ import annotations

import gc
import statistics
import time

from lexic.grammars import ABNF_FLAVOUR
from lexic.grammars.abnf_2 import ABNF_GRAMMAR
from lexic.ir.mapping8 import IrTypeMap as IrTypeMap8
from lexic.parsing_2 import recognize
from lexic.parsing_2.normalize import normalize

TRIALS = 15
_SENTINEL = object()


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
    print(f"  {label:<60} median={med:7.1f}ms  stdev={stdev:5.2f}ms")
    return med


g = normalize(ABNF_GRAMMAR)
text = str(ABNF_FLAVOUR.apply(ABNF_GRAMMAR))
print(f"ABNF text length: {len(text)} chars")

# ── Baseline ──────────────────────────────────────────────────────────
print("\n== Baseline (original mapping.py) ==")
r0 = bench("recognize(g, text)", lambda: recognize(g, text))

# ── EAFP patch on IrTypeMap8 ──────────────────────────────────────────
# We inject an EAFP resolve into IrTypeMap8, run the parse using mapping8,
# but here we'll just measure the micro-benchmark impact on the dispatch
# table that matters.

from lexic.exceptions import IrKeyError

# To measure EAFP in the hot path cleanly, we directly compare IrTypeMap8
# (current) resolve vs a monkey-patched EAFP version.
from lexic.ir.mapping8 import IR_DEFAULT


def _eafp_resolve(self, n):
    table = self._table
    t = type(n)
    try:
        return table[t]
    except KeyError:
        for base in t.__mro__:
            body = table.get(base)
            if body is not None:
                return body
        body = table.get(IR_DEFAULT)
        if body is not None:
            return body
        raise IrKeyError(f"{type(self).__name__}: no entry for {type(n).__name__}")


# Micro-benchmark: mapping8 resolve (current) vs EAFP
from lexic.ir.action import IrThis
from lexic.ir.base import IrNone, IrNoneType, IrTuple
from lexic.ir.nodes import IrCharClass, IrLiteral, IrRange, IrRuleRef

_earley_td = (
    IrTuple(IrRuleRef, IrThis()),
    IrTuple(IrLiteral, IrThis()),
    IrTuple(IrCharClass, IrThis()),
    IrTuple(IrRange, IrThis()),
    IrTuple(IrNoneType, IrThis()),
)
_earley_tm8 = IrTypeMap8(*_earley_td)

# Realistic dispatch mix
_dispatch_nodes = (
    [IrRuleRef("expr")] * 60
    + [IrLiteral("a")] * 20
    + [IrNone] * 15
    + [IrCharClass()] * 5
) * 100  # 10000 total


MICRO_TRIALS = 51


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
    print(f"  {label:<60} median={med:8.1f}us  stdev={stdev:6.1f}us")
    return med


print(
    f"\n== IrTypeMap.resolve micro: {len(_dispatch_nodes)} dispatches (EARLEY_OPS-like) =="
)


def _current8():
    tm = _earley_tm8
    for n in _dispatch_nodes:
        tm.resolve(n)


# Temporarily patch the resolve method
_orig_resolve = IrTypeMap8.resolve
IrTypeMap8.resolve = _eafp_resolve


def _eafp8():
    tm = _earley_tm8
    for n in _dispatch_nodes:
        tm.resolve(n)


micro_bench("IrTypeMap8.resolve (current: .get + None check)", _current8)
micro_bench("IrTypeMap8.resolve (EAFP: try table[type(n)])", _eafp8)

# Restore
IrTypeMap8.resolve = _orig_resolve
print("  (IrTypeMap8.resolve restored)")
