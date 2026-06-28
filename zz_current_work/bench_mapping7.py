"""Benchmark: mapping.py (original) vs mapping7.py (common-ancestor, slot reads).

Run:  uv run python zz_current_work/bench_mapping7.py

gc.disable() per trial; median ± stdev over 31 trials.
- IrMAP READ:    m[key] lookups (immutable map) vs raw dict.get.
- MULTIMAP READ: mm[key] (bucket read) vs raw dict.get  — the live-bucket path.
- INSERT:        mm += (k, v) vs raw dict setdefault/append.
- DISPATCH:      IrTypeMap.resolve over a node-type mix.
- CONSTRUCT:     IrMap construction.
"""

from __future__ import annotations

import gc
import statistics
import time
from typing import Callable

from lexic.ir.action import IrThis
from lexic.ir.base import IrSelf, IrStr, IrTuple
from lexic.ir.mapping import IrMap as IrMapOld
from lexic.ir.mapping import IrMultiMap as IrMultiMapOld
from lexic.ir.mapping import IrTypeMap as IrTypeMapOld
from lexic.ir.mapping7 import IrMap, IrMultiMap, IrTypeMap
from lexic.ir.nodes import IrLiteral, IrRuleRef

N = 5_000
TRIALS = 31
KEYS = [IrStr(f"k{i % 5}") for i in range(N)]
VALUES = [IrStr(f"v{i}") for i in range(N)]


def bench(
    label: str, setup: Callable[[], object], fn: Callable[[object], None]
) -> float:
    times: list[float] = []
    for _ in range(TRIALS):
        state = setup()
        gc.disable()
        t0 = time.perf_counter_ns()
        fn(state)
        t1 = time.perf_counter_ns()
        gc.enable()
        times.append((t1 - t0) / 1_000)
    med = statistics.median(times)
    print(f"  {label:<40} median={med:8.1f}us  stdev={statistics.stdev(times):6.1f}us")
    return med


# ── IrMap READ (immutable, m[key]) ────────────────────────────────────
print("\n== IrMap READ (N=5000 lookups, 5 distinct keys) ==")
_dyads_map = tuple(IrTuple(IrStr(f"k{i}"), IrStr(f"v{i}")) for i in range(5))
_rd = {IrStr(f"k{i}"): IrStr(f"v{i}") for i in range(5)}
_m_old = IrMapOld(*_dyads_map)
_m_new = IrMap(*_dyads_map)
_rkeys = [IrStr(f"k{i % 5}") for i in range(N)]


def _read_dict(_: object) -> None:
    for k in _rkeys:
        _ = _rd.get(k)


def _read_map_old(_: object) -> None:
    for k in _rkeys:
        _ = _m_old[k]


def _read_map_new(_: object) -> None:
    for k in _rkeys:
        _ = _m_new[k]


r0 = bench("raw dict.get", lambda: None, _read_dict)
bench("IrMap   (original)", lambda: None, _read_map_old)
rn = bench("IrMap7  (slots)", lambda: None, _read_map_new)
print(f"  IrMap7 vs dict floor: x{rn / r0:.2f}")

# ── MULTIMAP READ (mm[key]) ───────────────────────────────────────────
print("\n== IrMultiMap READ (N=5000, buckets of ~1000) ==")


def _setup_dict() -> dict:
    d: dict = {}
    for k, v in zip(KEYS, VALUES):
        d.setdefault(k, []).append(v)
    return d


def _setup_mm_old() -> IrMultiMapOld:
    mm: IrMultiMapOld = IrMultiMapOld()
    for k, v in zip(KEYS, VALUES):
        mm += (k, v)
    return mm


def _setup_mm_new() -> IrMultiMap:
    mm: IrMultiMap = IrMultiMap()
    for k, v in zip(KEYS, VALUES):
        mm += (k, v)
    return mm


def _read_mm(mm: object) -> None:
    for k in KEYS:
        _ = mm[k]  # type: ignore[index]


m0 = bench("raw dict.get", _setup_dict, lambda d: [d.get(k, ()) for k in KEYS] and None)
bench("IrMultiMap  (original, IrSeq snapshot)", _setup_mm_old, _read_mm)
mn = bench("IrMultiMap7 (live bucket)", _setup_mm_new, _read_mm)
print(f"  IrMultiMap7 vs dict floor: x{mn / m0:.2f}")

# ── INSERT ────────────────────────────────────────────────────────────
print("\n== INSERT (N=5000, 5 keys) ==")


def _ins_old(_: object) -> None:
    mm: IrMultiMapOld = IrMultiMapOld()
    for k, v in zip(KEYS, VALUES):
        mm += (k, v)


def _ins_new(_: object) -> None:
    mm: IrMultiMap = IrMultiMap()
    for k, v in zip(KEYS, VALUES):
        mm += (k, v)


bench("IrMultiMap  (original)", lambda: None, _ins_old)
bench("IrMultiMap7 (slots)", lambda: None, _ins_new)

# ── DISPATCH ──────────────────────────────────────────────────────────
print("\n== DISPATCH IrTypeMap.resolve (1000 calls/trial) ==")
_nodes = [IrLiteral("x"), IrRuleRef("r"), IrLiteral("z"), IrRuleRef("q")] * 250
_td = (
    IrTuple(IrLiteral, IrThis()),
    IrTuple(IrRuleRef, IrThis()),
    IrTuple(IrSelf, IrThis()),
)
_tm_old = IrTypeMapOld(*_td)
_tm_new = IrTypeMap(*_td)
bench(
    "IrTypeMap  (original)",
    lambda: _tm_old,
    lambda tm: [tm.resolve(n) for n in _nodes] and None,
)
bench(
    "IrTypeMap7 (slots)",
    lambda: _tm_new,
    lambda tm: [tm.resolve(n) for n in _nodes] and None,
)

# ── CONSTRUCT ─────────────────────────────────────────────────────────
print("\n== CONSTRUCT IrMap (1000/trial) ==")
bench(
    "IrMap  (original)",
    lambda: None,
    lambda _: [IrMapOld(*_dyads_map) for _ in range(1000)] and None,
)
bench(
    "IrMap7 (slots)",
    lambda: None,
    lambda _: [IrMap(*_dyads_map) for _ in range(1000)] and None,
)
print()
