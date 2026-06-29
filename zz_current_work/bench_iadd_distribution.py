"""IrMultiMap.__iadd__: measure with realistic insert distributions.

Real workload has:
- waiting index: many distinct keys, each getting 1-3 inserts
- links table: many distinct keys (item, end), each getting 1 family (unambiguous)
So the "first insert" path (bucket doesn't exist) is very hot.
"""

from __future__ import annotations

import gc
import statistics
import time

from lexic.ir.base import IrStr
from lexic.ir.mapping8 import IrMultiMap

TRIALS = 51
N = 1_000


def bench(label, fn) -> float:
    times = []
    for _ in range(TRIALS):
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


# Distinct keys (all first-inserts, like the links table)
UNIQUE_KEYS = [IrStr(f"k{i}") for i in range(N)]
VALUES = [IrStr(f"v{i}") for i in range(N)]

# Mixed: 1-3 inserts per bucket (like waiting)
MIXED_KEYS = []
MIXED_VALS = []
for i in range(N // 3):
    for j in range(3):
        MIXED_KEYS.append(IrStr(f"k{i}"))
        MIXED_VALS.append(IrStr(f"v{i}_{j}"))


def _iadd_current_unique():
    mm: IrMultiMap = IrMultiMap()
    for k, v in zip(UNIQUE_KEYS, VALUES):
        mm += (k, v)


def _iadd_current_mixed():
    mm: IrMultiMap = IrMultiMap()
    for k, v in zip(MIXED_KEYS, MIXED_VALS):
        mm += (k, v)


def _iadd_eafp_impl(self, entry):
    key, value = entry
    try:
        self._table[key].append(value)
    except KeyError:
        self._table[key] = [value]
    return self


_orig_iadd = IrMultiMap.__iadd__
IrMultiMap.__iadd__ = _iadd_eafp_impl


def _iadd_eafp_unique():
    mm: IrMultiMap = IrMultiMap()
    for k, v in zip(UNIQUE_KEYS, VALUES):
        mm += (k, v)


def _iadd_eafp_mixed():
    mm: IrMultiMap = IrMultiMap()
    for k, v in zip(MIXED_KEYS, MIXED_VALS):
        mm += (k, v)


IrMultiMap.__iadd__ = _orig_iadd

print(f"\n== IrMultiMap.__iadd__ with N={N} unique keys (all first inserts) ==")
mc1 = bench("current: get+None check (all first inserts)", _iadd_current_unique)
IrMultiMap.__iadd__ = _iadd_eafp_impl
me1 = bench("EAFP: try .append / except (all first inserts)", _iadd_eafp_unique)
IrMultiMap.__iadd__ = _orig_iadd
print(f"  speedup: x{mc1 / me1:.2f}")

print(f"\n== IrMultiMap.__iadd__ with N//3={N // 3} keys, 3 inserts each (mixed) ==")
mc2 = bench("current: get+None check (mixed)", _iadd_current_mixed)
IrMultiMap.__iadd__ = _iadd_eafp_impl
me2 = bench("EAFP: try .append / except (mixed)", _iadd_eafp_mixed)
IrMultiMap.__iadd__ = _orig_iadd
print(f"  speedup: x{mc2 / me2:.2f}")

print(f"\n== Raw inline version (both behaviors) at N={N} unique ==")


def _raw_getcheck():
    table = {}
    for k, v in zip(UNIQUE_KEYS, VALUES):
        bucket = table.get(k)
        if bucket is None:
            table[k] = [v]
        else:
            bucket.append(v)


def _raw_eafp():
    table = {}
    for k, v in zip(UNIQUE_KEYS, VALUES):
        try:
            table[k].append(v)
        except KeyError:
            table[k] = [v]


bench("raw get+None (no method overhead)", _raw_getcheck)
bench("raw EAFP    (no method overhead)", _raw_eafp)
