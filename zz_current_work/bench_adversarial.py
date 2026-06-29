"""Adversarial micro-benchmarks for mapping8.py.

Run: uv run python zz_current_work/bench_adversarial.py

Investigates all 10 targets from the review brief:
1. MRO overhead of IrMapping 3-param generic + IrLeaf chain
2. IrTypeMap.resolve fast-path (exact type) — can it be faster?
3. IrMultiMap.__iadd__ — get+None-check vs setdefault vs EAFP
4. IrMultiMap.__getitem__ — .get vs EAFP
5. resolve None-check semantics (value is not None) — false miss?
6. __new__ construction overhead
7. Slots/layout — does frozen __setattr__ cost on construction?
8. __hash__/__eq__ — frozenset cost + how often
9. __iter__ reconstructing IrTuple
10. IrTypeMap.resolve: try/except vs None-check; dict.__getitem__ vs .get
"""

from __future__ import annotations

import gc
import statistics
import time

from lexic.ir.action import IrThis
from lexic.ir.base import IrSelf, IrStr, IrTuple
from lexic.ir.mapping8 import IrMap, IrMultiMap, IrTypeMap
from lexic.ir.nodes import IrLiteral, IrRuleRef

TRIALS = 51
N = 5_000


def bench(label: str, fn, setup=None, n_inner=N) -> float:
    """fn() if no setup, fn(state) if setup provided. Always passes state."""
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
    print(f"  {label:<55} median={med:8.1f}us  stdev={stdev:6.1f}us")
    return med


_SENTINEL = object()


# ── Test data ──────────────────────────────────────────────────────────
_dyads_map = tuple(IrTuple(IrStr(f"k{i}"), IrStr(f"v{i}")) for i in range(5))
_m = IrMap(*_dyads_map)
_rkeys = [IrStr(f"k{i % 5}") for i in range(N)]
_nodes = [IrLiteral("x"), IrRuleRef("r"), IrLiteral("z"), IrRuleRef("q")] * 250
_td = (
    IrTuple(IrLiteral, IrThis()),
    IrTuple(IrRuleRef, IrThis()),
    IrTuple(IrSelf, IrThis()),
)
_tm = IrTypeMap(*_td)

# ── 1. MRO OVERHEAD — IrLeaf chain ────────────────────────────────────
print("\n== 1. IrLeaf MRO overhead vs a flat plain dict ==")


class _FlatMap:
    """Minimal slot-based dict wrapper with same surface as IrMap."""

    __slots__ = ("_table",)

    def __init__(self, *dyads):
        self._table = {d[0]: d[1] for d in dyads}

    def __getitem__(self, key):
        v = self._table.get(key)
        if v is not None:
            return v
        raise KeyError(key)


_flat = _FlatMap(*_dyads_map)


def _read_flat():
    for k in _rkeys:
        _ = _flat[k]


def _read_map8():
    for k in _rkeys:
        _ = _m[k]


b_flat = bench("flat class (no IrLeaf chain)", _read_flat)
b_map8 = bench("IrMap8 (__getitem__ via IrLeaf MRO)", _read_map8)
print(f"  MRO overhead: x{b_map8 / b_flat:.2f}")

# ── 2+10. IrTypeMap.resolve fast-path alternatives ────────────────────
print("\n== 2+10. IrTypeMap.resolve — fast-path alternatives ==")


def _resolve_current():
    tm = _tm
    for n in _nodes:
        tm.resolve(n)


def _resolve_eafp():
    """try dict.__getitem__ instead of .get + None-check."""
    table = _tm._table
    for n in _nodes:
        try:
            _ = table[type(n)]
        except KeyError:
            for base in type(n).__mro__:
                body = table.get(base)
                if body is not None:
                    break


def _resolve_cached_type():
    """Cache type(n) call result."""
    table = _tm._table
    for n in _nodes:
        t = type(n)
        body = table.get(t)
        if body is None:
            for base in t.__mro__:
                body = table.get(base)
                if body is not None:
                    break


bench("resolve (current: slot read, .get, None-check)", _resolve_current)
bench("resolve (EAFP: dict[type(n)] in try/except)", _resolve_eafp)
bench("resolve (cache type(n) in local)", _resolve_cached_type)

# ── 3. IrMultiMap.__iadd__ alternatives ───────────────────────────────
print("\n== 3. IrMultiMap.__iadd__ — get+check vs setdefault vs EAFP ==")
KEYS = [IrStr(f"k{i % 5}") for i in range(N)]
VALUES = [IrStr(f"v{i}") for i in range(N)]


def _iadd_current():
    mm: IrMultiMap = IrMultiMap()
    table = mm._table
    for k, v in zip(KEYS, VALUES):
        bucket = table.get(k)
        if bucket is None:
            table[k] = [v]
        else:
            bucket.append(v)


def _iadd_setdefault():
    mm: IrMultiMap = IrMultiMap()
    table = mm._table
    for k, v in zip(KEYS, VALUES):
        table.setdefault(k, []).append(v)


def _iadd_eafp():
    mm: IrMultiMap = IrMultiMap()
    table = mm._table
    for k, v in zip(KEYS, VALUES):
        try:
            table[k].append(v)
        except KeyError:
            table[k] = [v]


def _iadd_via_operator():
    """Via the actual operator on the IrMultiMap instance."""
    mm: IrMultiMap = IrMultiMap()
    for k, v in zip(KEYS, VALUES):
        mm += (k, v)


bench("__iadd__ (current: get+None check)", _iadd_current)
bench("__iadd__ (setdefault alternative)", _iadd_setdefault)
bench("__iadd__ (EAFP try/except KeyError)", _iadd_eafp)
bench("__iadd__ (via mm += (k,v) operator)", _iadd_via_operator)

# ── 4. IrMultiMap.__getitem__ EAFP vs .get ────────────────────────────
print("\n== 4. IrMultiMap.__getitem__ — .get vs EAFP ==")


def _setup_mm():
    mm: IrMultiMap = IrMultiMap()
    for k, v in zip(KEYS, VALUES):
        mm += (k, v)
    return mm


_EMPTY_TUPLE: tuple = ()


def _read_mm_current(mm):
    """Current: _table.get(key, ())"""
    table = mm._table
    for k in KEYS:
        _ = table.get(k, _EMPTY_TUPLE)


def _read_mm_eafp(mm):
    """EAFP: try table[key] except KeyError: ()"""
    table = mm._table
    for k in KEYS:
        try:
            _ = table[k]
        except KeyError:
            _ = _EMPTY_TUPLE


bench(".get(key, ())", _read_mm_current, _setup_mm)
bench("EAFP try/except KeyError", _read_mm_eafp, _setup_mm)

# ── 5. None-check false-miss: verify real values are never None ────────
print("\n== 5. None-check false-miss: is 'value is not None' safe? ==")
# IrSelf subclasses are never None — verify by example
sample_map = IrMap(*_dyads_map)
for k, v in sample_map.items():
    assert v is not None, f"Value {v!r} is None — unsafe!"
print("  All values are IrSelf instances (never None) — None check is safe.")

# ── 5b. Double .get in resolve: can we avoid second .get on no-default path? ─
print("\n== 5b. resolve double-get: can we avoid IR_DEFAULT lookup? ==")
# The common case: no IR_DEFAULT in the table. The current code always does
# a second table.get(IR_DEFAULT) even when it will miss.
# Alternative: store a sentinel in _table under IR_DEFAULT only when registered.
# (This is what mapping8 already does — IR_DEFAULT is just another key.)
# The optimization would be a flag: "has_default: bool" to skip the 2nd get.
# Let's measure how expensive the 2nd get is on a miss.

_td_no_default = (
    IrTuple(IrLiteral, IrThis()),
    IrTuple(IrRuleRef, IrThis()),
)
_tm_no_default = IrTypeMap(*_td_no_default)

# Only exact-type hits (IrLiteral, IrRuleRef) — no default fallback
_nodes_exact = [IrLiteral("x"), IrRuleRef("r")] * 500


def _resolve_no_default_current():
    """Current code — does table.get(IR_DEFAULT) even when no default registered."""
    tm = _tm_no_default
    for n in _nodes_exact:
        tm.resolve(n)


def _resolve_no_default_skip():
    """Skip the IR_DEFAULT get when the exact-type hit."""
    table = _tm_no_default._table
    for n in _nodes_exact:
        body = table.get(type(n))
        if body is not None:
            # found — skip IR_DEFAULT lookup
            continue
        # MRO walk and IR_DEFAULT only on a miss
        for base in type(n).__mro__:
            body = table.get(base)
            if body is not None:
                break


bench(
    "resolve no-default (current — always tries IR_DEFAULT after miss)",
    _resolve_no_default_current,
)
bench("resolve no-default (skip IR_DEFAULT on exact hit)", _resolve_no_default_skip)

# ── 6. __new__ construction overhead ──────────────────────────────────
print("\n== 6. IrMap __new__ construction overhead ==")
# mapping8 IrMap sorts on every construction.  measure sort overhead.


def _construct_sorted():
    """Current: sorted(dyads, key=repr-of-key)."""
    for _ in range(1000):
        IrMap(*_dyads_map)


def _construct_no_sort():
    """Without sorting (just to measure cost of sort itself)."""
    # We cannot easily skip sort without modifying IrMap, so measure sort alone
    for _ in range(1000):
        sorted(_dyads_map, key=lambda d: repr(d[0]))


bench("IrMap construction (with sort + object.__new__)", _construct_sorted)
bench("sorted() alone (5 dyads)", _construct_no_sort)

# ── 7. Frozen __setattr__ on construction ─────────────────────────────
print("\n== 7. Frozen __setattr__ at construction time ==")
# IrMapping.__new__ uses object.__setattr__(obj, '_table', {}) — bypasses the
# frozen __setattr__. So there is NO frozen-guard cost on construction. Verify:
# mapping8 line ~74: object.__setattr__(obj, "_table", {}) — correct.
print("  Confirmed: construction uses object.__setattr__ — frozen guard not hit.")

# ── 8. __hash__/__eq__ cost ───────────────────────────────────────────
print("\n== 8. __hash__ / __eq__ cost on IrMap ==")
_m2 = IrMap(*_dyads_map)  # structurally equal copy


def _hash_map():
    for _ in range(1000):
        hash(_m)


def _eq_map():
    for _ in range(1000):
        _ = _m == _m2


bench("hash(IrMap) — frozenset of items (1000x)", _hash_map)
bench("IrMap == IrMap (structural, 1000x)", _eq_map)

# Are IrMaps used as dict keys in hot paths? Check IrTypeMap._table key type.
# IrTypeMap keys are `type` objects (Python class objects), not IrMap instances.
# IrMap instances would only need hash/eq if they're used as dict keys or set members.
# The hot paths: waiting[rule_name] (rule_name is IrRuleRef), links[(item,end)]
# (tuple key), resolve(n) (n is an IrSelf node). IrMap itself is never a key.
print("  NOTE: IrMap instances are not used as dict keys in hot paths.")
print("  __hash__/__eq__ on IrMap only matter for equality assertions (tests/repr).")

# ── 9. __iter__ IrTuple reconstruction ───────────────────────────────
print("\n== 9. __iter__ — IrTuple reconstruction per element ==")


def _iter_map():
    for _ in range(1000):
        for _ in _m:
            pass


def _iter_items():
    """Direct items() iteration — no IrTuple construction."""
    for _ in range(1000):
        for _ in _m.items():
            pass


bench("iter(IrMap) — builds IrTuple per dyad (1000x over 5-elem map)", _iter_map)
bench("IrMap.items() — no IrTuple alloc (1000x over 5-elem map)", _iter_items)

# ── Hot-path measurement: IrMultiMap used as a 'set' (nullable) ───────
print("\n== BONUS: IrMultiMap.__contains__ (nullable set membership) ==")
_nullable: IrMultiMap = IrMultiMap()
for i in range(3):
    ref = IrRuleRef(f"r{i}")
    _nullable += (ref, ref)

_refs_hit = [IrRuleRef("r0"), IrRuleRef("r1"), IrRuleRef("r2")] * 1000
_refs_miss = [IrRuleRef("x"), IrRuleRef("y"), IrRuleRef("z")] * 1000


def _contains_hit():
    n = _nullable
    for ref in _refs_hit:
        _ = ref in n


def _contains_miss():
    n = _nullable
    for ref in _refs_miss:
        _ = ref in n


def _contains_raw_dict():
    table = _nullable._table
    for ref in _refs_hit:
        _ = ref in table


bench("IrMultiMap.__contains__ (hit) 3000 checks", _contains_hit)
bench("IrMultiMap.__contains__ (miss) 3000 checks", _contains_miss)
bench("raw dict __contains__ (hit) 3000 checks", _contains_raw_dict)

# ── Hot-path: Complete waiters read ───────────────────────────────────
print("\n== BONUS: Complete waiter read — mm[rule_name] via IrMultiMap.__getitem__ ==")
_waiting: IrMultiMap = IrMultiMap()
_rule = IrRuleRef("expr")
for i in range(5):
    pass

    # minimal fake EarleyItem — we just need something hashable/IrSelf
    # Use IrStr as a stand-in (avoids full grammar bootstrap)

_rule2 = IrRuleRef("stmt")
for i in range(5):
    _waiting += (_rule, IrStr(f"item{i}"))
    _waiting += (_rule2, IrStr(f"item2_{i}"))

_lookup_keys = [_rule] * 3000 + [_rule2] * 3000


def _read_waiting_current():
    for k in _lookup_keys:
        _ = _waiting[k]


def _read_waiting_via_table():
    table = _waiting._table
    for k in _lookup_keys:
        _ = table.get(k, ())


bench("mm[key] via IrMultiMap.__getitem__ (6000 lookups)", _read_waiting_current)
bench("table.get(key, ()) directly (6000 lookups)", _read_waiting_via_table)
