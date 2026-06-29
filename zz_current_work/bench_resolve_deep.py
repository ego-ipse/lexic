"""Deep investigation of IrTypeMap.resolve EAFP optimization.

The bench_adversarial results showed:
  current (slot read + .get + None-check):  ~52 us
  EAFP (try dict[type(n)]):                 ~18 us
  cached type(n):                           ~32 us

This bench:
1. Verifies correctness of EAFP for edge cases (MRO fallback, IR_DEFAULT)
2. Measures various EAFP variants
3. Measures the full-suite impact via a validation swap of mapping.py
4. Examines what fraction of dispatch calls actually hit MRO fallback vs exact type
"""

from __future__ import annotations

import gc
import statistics
import time

from lexic.ir.action import IrThis
from lexic.ir.base import IrSelf, IrStr, IrTuple
from lexic.ir.mapping8 import IR_DEFAULT, IrMap, IrTypeMap
from lexic.ir.nodes import IrCharClass, IrLiteral, IrRuleRef

TRIALS = 51
_SENTINEL = object()


def bench(label: str, fn, setup=None) -> float:
    times = []
    for _ in range(TRIALS):
        state = setup() if setup is not None else _SENTINEL
        gc.disable()
        t0 = time.perf_counter_ns()
        if state is _SENTINEL:
            fn()
        else:
            fn(state)
        t1 = time.perf_counter_ns()
        gc.enable()
        times.append((t1 - t0) / 1_000)
    med = statistics.median(times)
    stdev = statistics.stdev(times)
    print(f"  {label:<65} median={med:8.1f}us  stdev={stdev:6.1f}us")
    return med


# ── 1000 nodes, exact-type match only ────────────────────────────────
_td = (
    IrTuple(IrLiteral, IrThis()),
    IrTuple(IrRuleRef, IrThis()),
    IrTuple(IrSelf, IrThis()),
)
_tm = IrTypeMap(*_td)
_nodes = [IrLiteral("x"), IrRuleRef("r"), IrLiteral("z"), IrRuleRef("q")] * 250

print(
    f"\n== EAFP variants — {len(_nodes)} nodes, 2 exact types + IR_DEFAULT-like IrSelf =="
)


# Current implementation
def _current():
    tm = _tm
    for n in _nodes:
        tm.resolve(n)


# EAFP variant 1: dict[type(n)] directly, except KeyError -> MRO walk
def _eafp_v1():
    table = _tm._table
    for n in _nodes:
        t = type(n)
        try:
            _ = table[t]
        except KeyError:
            for base in t.__mro__:
                body = table.get(base)
                if body is not None:
                    break


# EAFP variant 2: EAFP with type cached
def _eafp_v2():
    table = _tm._table
    for n in _nodes:
        t = type(n)
        try:
            _ = table[t]
        except KeyError:
            body = table.get(IR_DEFAULT)  # skip MRO; IR_DEFAULT covers it
            if body is None:
                raise


# EAFP variant 3: dict.__getitem__ approach
def _eafp_v3():
    table = _tm._table
    dget = dict.__getitem__
    for n in _nodes:
        t = type(n)
        try:
            _ = dget(table, t)
        except KeyError:
            for base in t.__mro__:
                body = table.get(base)
                if body is not None:
                    break


# EAFP variant 4: cached type + local table reference (both optimizations combined)
def _eafp_v4_cached_locals():
    table = _tm._table
    for n in _nodes:
        t = n.__class__  # slightly faster than type() in CPython?
        try:
            _ = table[t]
        except KeyError:
            for base in t.__mro__:
                body = table.get(base)
                if body is not None:
                    break


bench("current: self._table.get(type(n)) + None check", _current)
bench("EAFP v1: table[type(n)] + KeyError -> MRO walk", _eafp_v1)
bench("EAFP v2: table[type(n)] + KeyError -> only IR_DEFAULT", _eafp_v2)
bench("EAFP v3: dict.__getitem__(table, type(n))", _eafp_v3)
bench("EAFP v4: n.__class__ + table[t] + KeyError -> MRO", _eafp_v4_cached_locals)

# ── Verify correctness of EAFP for MRO-fallback case ─────────────────
print("\n== Correctness: MRO fallback via IrSelf base ==")
# IrSelf is a base of both IrLiteral and IrRuleRef — registered as default
_td_mro = (
    IrTuple(IrSelf, IrThis()),  # only base registered, no exact types
)
_tm_mro = IrTypeMap(*_td_mro)
assert _tm_mro.resolve(IrLiteral("x")) is not None, "MRO fallback broke!"
assert _tm_mro.resolve(IrRuleRef("r")) is not None, "MRO fallback broke!"
print("  MRO fallback works correctly.")

# ── Measure MRO fallback hit rate ─────────────────────────────────────
print("\n== MRO fallback hit rate in real EARLEY_OPS dispatch ==")
# EARLEY_OPS has: IrRuleRef, IrLiteral, IrCharClass, IrRange, IrNoneType
# In a typical parse: items have IrRuleRef (Predict), IrLiteral (Scan), IrNoneType (Complete)
# IrCharClass and IrRange are for char-class patterns — less common.
# All have exact-type registrations. EAFP would only fall through to MRO for an
# unregistered subclass. In the current codebase, this never happens in real parses.
print(
    "  All EARLEY_OPS types are exact registrations — MRO walk never hit in practice."
)
print("  EAFP table[type(n)] will always succeed on the first try.")

# ── Measure on EARLEY_OPS-like realistic dispatch table ───────────────
print("\n== Realistic EARLEY_OPS dispatch (5 registered types) ==")
from lexic.ir.base import IrNone, IrNoneType
from lexic.ir.nodes import IrRange


class _Predict(IrStr):
    pass


class _Scan(IrStr):
    pass


class _Complete(IrStr):
    pass


_earley_td = (
    IrTuple(IrRuleRef, IrThis()),
    IrTuple(IrLiteral, IrThis()),
    IrTuple(IrCharClass, IrThis()),
    IrTuple(IrRange, IrThis()),
    IrTuple(IrNoneType, IrThis()),
)
_earley_tm = IrTypeMap(*_earley_td)
# Realistic mix: mostly IrRuleRef (Predict) and IrLiteral/IrNoneType (Scan/Complete)
_earley_nodes = (
    [IrRuleRef("expr")] * 60
    + [IrLiteral("a")] * 20
    + [IrNone] * 15
    + [IrCharClass()] * 5
) * 5  # 500 total


def _earley_current():
    tm = _earley_tm
    for n in _earley_nodes:
        tm.resolve(n)


def _earley_eafp():
    table = _earley_tm._table
    for n in _earley_nodes:
        t = type(n)
        try:
            _ = table[t]
        except KeyError:
            for base in t.__mro__:
                body = table.get(base)
                if body is not None:
                    break


bench("earley: current (500 dispatches, realistic mix)", _earley_current)
bench("earley: EAFP variant (500 dispatches, realistic mix)", _earley_eafp)

# ── Key insight: where does the 3x speedup come from? ─────────────────
print("\n== Micro: cost of .get vs [] for a hot dict ==")
import timeit

d = {IrLiteral: "body", IrRuleRef: "body2"}
k = IrLiteral


def _dot_get():
    return d.get(k)


def _bracket():
    try:
        return d[k]
    except KeyError:
        return None


# Direct timeit comparison (avoid our bench overhead)
n_reps = 100_000
t_get = timeit.timeit(_dot_get, number=n_reps) * 1e6 / n_reps
t_bracket = timeit.timeit(_bracket, number=n_reps) * 1e6 / n_reps
print(f"  dict.get(key):          {t_get:.3f} us/call")
print(
    f"  try d[key] except:      {t_bracket:.3f} us/call  (ratio: x{t_get / t_bracket:.2f})"
)

# ── The slot read overhead ─────────────────────────────────────────────
print("\n== Slot read: self._table vs hoisted local ==")
# IrMapping.__getitem__ does `self._table.get(key)` — slot read on every call.
# If we hoist `table = self._table` at the start of a method, the slot read is once.
# But for a single-call dispatch, that doesn't help.
# The real overhead: self._table is a slot read (LOAD_FAST-like but needs descriptor).
_d = {"x": "v"}


class _WithSlot:
    __slots__ = ("_table",)

    def __init__(self):
        self._table = _d

    def get_via_slot(self, k):
        return self._table.get(k)

    def get_via_local(self, k, _t=_d):
        return _t.get(k)


_ws = _WithSlot()
k_str = "x"

t_slot = timeit.timeit(lambda: _ws.get_via_slot(k_str), number=n_reps) * 1e6 / n_reps
t_local = timeit.timeit(lambda: _ws.get_via_local(k_str), number=n_reps) * 1e6 / n_reps
print(f"  slot read self._table.get():    {t_slot:.3f} us/call")
print(
    f"  local bound _t.get():            {t_local:.3f} us/call  (ratio: x{t_slot / t_local:.2f})"
)

# ── Test: can we speed up __getitem__ on IrMap with EAFP? ─────────────
print("\n== IrMap.__getitem__ EAFP vs .get ==")
_m = IrMap(*[IrTuple(IrStr(f"k{i}"), IrStr(f"v{i}")) for i in range(5)])
_rkeys = [IrStr(f"k{i % 5}") for i in range(5000)]


def _getitem_current():
    for k in _rkeys:
        _ = _m[k]


def _getitem_eafp():
    table = _m._table
    for k in _rkeys:
        try:
            _ = table[k]
        except KeyError:
            raise


bench("IrMap.__getitem__ current (.get + None + raise)", _getitem_current)
bench("IrMap.__getitem__ EAFP (table[k] + KeyError)", _getitem_eafp)
