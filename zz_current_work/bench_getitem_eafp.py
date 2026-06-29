"""Probe IrMap.__getitem__ EAFP vs .get and IrMultiMap.__getitem__ EAFP.

Separate slot-read cost from .get vs [] cost.
"""

from __future__ import annotations

import gc
import statistics
import time

from lexic.exceptions import IrKeyError
from lexic.ir.base import IrStr, IrTuple
from lexic.ir.mapping8 import IrMap, IrMultiMap

TRIALS = 51
N = 5_000
_dyads = tuple(IrTuple(IrStr(f"k{i}"), IrStr(f"v{i}")) for i in range(5))
_m = IrMap(*_dyads)
_rkeys = [IrStr(f"k{i % 5}") for i in range(N)]


def _current_getitem():
    for k in _rkeys:
        _ = _m[k]


# EAFP version of IrMap.__getitem__
def _eafp_getitem(self, key):
    try:
        return self._table[key]
    except KeyError:
        raise IrKeyError(f"{type(self).__name__}: no entry for {key!r}")


_orig_gi = IrMap.__getitem__
IrMap.__getitem__ = _eafp_getitem


def _eafp_gi_call():
    for k in _rkeys:
        _ = _m[k]


IrMap.__getitem__ = _orig_gi


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
    print(f"  {label:<60} median={med:8.1f}us  stdev={stdev:6.1f}us")
    return med


print(f"\n== IrMap.__getitem__: .get vs EAFP (N={N}, 5 keys) ==")

mc = bench("IrMap.__getitem__ current (.get + None check)", _current_getitem)
IrMap.__getitem__ = _eafp_getitem
me = bench("IrMap.__getitem__ EAFP  (table[k] + KeyError)", _eafp_gi_call)
IrMap.__getitem__ = _orig_gi
print(f"  speedup: x{mc / me:.2f}")

# ── IrMultiMap.__getitem__ ─────────────────────────────────────────────
print(f"\n== IrMultiMap.__getitem__: .get vs EAFP (N={N}, 5 keys) ==")
KEYS = [IrStr(f"k{i % 5}") for i in range(N)]
VALUES = [IrStr(f"v{i}") for i in range(N)]
_mm: IrMultiMap = IrMultiMap()
for k, v in zip(KEYS, VALUES):
    _mm += (k, v)

_EMPTY = ()


def _mm_current():
    for k in KEYS:
        _ = _mm[k]


def _mm_eafp(self, key):
    try:
        return self._table[key]
    except KeyError:
        return _EMPTY


_orig_mm_gi = IrMultiMap.__getitem__
IrMultiMap.__getitem__ = _mm_eafp


def _mm_eafp_call():
    for k in KEYS:
        _ = _mm[k]


IrMultiMap.__getitem__ = _orig_mm_gi

mc2 = bench("IrMultiMap.__getitem__ current (.get, ())", _mm_current)
IrMultiMap.__getitem__ = _mm_eafp
me2 = bench("IrMultiMap.__getitem__ EAFP  (try table[k])", _mm_eafp_call)
IrMultiMap.__getitem__ = _orig_mm_gi
print(f"  speedup: x{mc2 / me2:.2f}")

# ── IrMultiMap.__iadd__ EAFP ───────────────────────────────────────────
print(f"\n== IrMultiMap.__iadd__: current vs EAFP (N={N}, 5 keys) ==")


def _iadd_current():
    mm: IrMultiMap = IrMultiMap()
    for k, v in zip(KEYS, VALUES):
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


def _iadd_eafp_call():
    mm: IrMultiMap = IrMultiMap()
    for k, v in zip(KEYS, VALUES):
        mm += (k, v)


IrMultiMap.__iadd__ = _orig_iadd

mc3 = bench("IrMultiMap.__iadd__ current (get+None+assign or append)", _iadd_current)
IrMultiMap.__iadd__ = _iadd_eafp_impl
me3 = bench("IrMultiMap.__iadd__ EAFP   (try .append / except assign)", _iadd_eafp_call)
IrMultiMap.__iadd__ = _orig_iadd
print(f"  speedup: x{mc3 / me3:.2f}")

# ── Quantify slot-read overhead ────────────────────────────────────────
print("\n== Slot read self._table vs hoisted table local ==")
# Both do dict.get, but one reads slot each call vs hoisted once
import timeit


class _Test:
    __slots__ = ("_table",)

    def __init__(self):
        self._table = {"k": "v"}

    def via_slot(self, k):
        return self._table.get(k)

    def via_local(self, k, _t=None):
        return _t.get(k)


t = _Test()

n_rep = 100_000
ts = timeit.timeit(lambda: t.via_slot("k"), number=n_rep) * 1e6 / n_rep


# Hoisting locally in the method body
def hoisted(self, k):
    tbl = self._table
    return tbl.get(k)


th = timeit.timeit(lambda: hoisted(t, "k"), number=n_rep) * 1e6 / n_rep
print(f"  self._table.get(k) per call: {ts:.3f} us")
print(f"  tbl = self._table; tbl.get(k): {th:.3f} us  (ratio: x{ts / th:.2f})")
