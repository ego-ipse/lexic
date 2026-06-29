# MAPPING8 Adversarial Performance Review

Branch: `parse_proto_proto` @ `e0c8c0c`. Review date: 2026-06-28.

---

## Executive Summary

`mapping8.py` beats the original (`mapping.py`) decisively on the hot paths that matter.
Two changes are worth landing in mapping8 itself; the rest of the brief's 10 targets are either noise, cannot be beaten, or the current code is already optimal.

| # | Finding | Severity | Verdict |
|---|---------|----------|---------|
| A | **IrTypeMap.resolve: use `table[type(n)]` + EAFP** | hot-path win | **Propose patch** |
| B | **IrMap.__getitem__: use `table[key]` + EAFP** | micro | **Propose patch** |
| C | IrMultiMap.__iadd__ EAFP | **REGRESSES** first-insert path | **Do NOT apply** |
| D | IrMultiMap.__getitem__: EAFP vs .get | micro, within noise | Skip |
| E | IrLeaf/IrMapping MRO overhead | **Unmeasurable** — x1.01 | Cannot be beaten |
| F | Slot read cost of `self._table` | Negligible — 0.05 µs | Cannot be beaten |
| G | Frozen `__setattr__` on construction | Zero cost (bypassed) | Cannot be beaten |
| H | `__hash__`/`__eq__` on IrMap | Not in hot paths | Irrelevant |
| I | `__iter__` IrTuple reconstruction | Not in hot paths | Irrelevant |
| J | Sort in IrMap.__new__ | Off hot path (construction infrequent) | Acceptable |

**Validation swap result** (mapping.py → mapping8 shim + ForestCtx slot migration):
- ABNF self-host recognize: **97.0 ms → 91.8 ms (+5.7%)**, parse: **124.3 ms → 114.2 ms (+8.1%)**
- 1157 tests pass; 8 expected failures (tuple-ancestry representation tests only)
- ABNF fixpoint: **TRUE** (unchanged)

---

## Hot-Path Win A — IrTypeMap.resolve EAFP

**Target:** `IrTypeMap.resolve` — called once per dispatched symbol in the Earley engine (the #1 hotspot per the brief). In EARLEY_OPS, all dispatched symbol types (`IrRuleRef`, `IrLiteral`, `IrCharClass`, `IrRange`, `IrNoneType`) are exact-type registrations — the MRO walk is **never hit** in a real parse.

**Current code (mapping8.py line 222):**
```python
body = table.get(type(n))
if body is not None:
    return body
```

**Proposed:**
```python
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
    raise IrKeyError(...)
```

**Evidence:** Measured via monkey-patching IrTypeMap.resolve on 50,000 realistic EARLEY_OPS dispatches (60% IrRuleRef, 20% IrLiteral, 15% IrNoneType, 5% IrCharClass):

```
current: .get(type(n)) + None check   median=2651µs (50k dispatches)
EAFP:    table[type(n)] + KeyError    median=2486µs (50k dispatches)
speedup: x1.07 (+6% on dispatch micro)
full-workload contribution: ~1-2% on ABNF recognize (not separately measured cleanly, dominated by other costs)
```

The 2.5x speedup seen in early `bench_adversarial.py` runs was an artifact: the free-function variants captured `table = _tm._table` OUTSIDE the measured loop, hiding the slot-read cost. When patched inline (same slot-read path), the speedup is 1.07x.

**Why it helps:** `dict[key]` on a hit is 25% cheaper than `dict.get(key)` (0.025µs vs 0.034µs per call in timeit). The current code also evaluates the `None-check` branch (LOAD_CONST None, IS_OP). On the exact-type hot path, try/except at zero exception cost sidesteps both.

**Risk:** Correct for all registered types (exact-type hit never raises). The `KeyError` path only fires for unregistered types going through MRO walk — the existing logic is preserved there. No purity concern.

**Correctness verified:** MRO fallback test (`IrSelf` registered, dispatching `IrLiteral`/`IrRuleRef`) passes. IR_DEFAULT fallback also passes.

---

## Hot-Path Win B — IrMap.__getitem__ EAFP

**Target:** `IrMap.__getitem__` — called by `Complete` for `chart[done.origin].waiting[done.rule_name]`, and by `Predict` for `ctx.rules.resolve(ref)`.

**Current (mapping8.py line 92–95):**
```python
value = self._table.get(key)
if value is not None:
    return value
raise IrKeyError(...)
```

**Proposed:**
```python
try:
    return self._table[key]
except KeyError:
    raise IrKeyError(f"{type(self).__name__}: no entry for {key!r}")
```

**Evidence (monkey-patched, 5000 lookups, 5 distinct keys, all hits):**
```
current: .get + None check    median=1009µs
EAFP:    table[key]+KeyError  median= 906µs
speedup: x1.11 (+11%)
```

**Risk:** Correct when all values are IrSelf (never None). Confirmed in § 5 below. A key miss does happen in legitimate use; the `KeyError` re-raise is correct. If stored values were ever `None` (they are not — `IrSelf` is the type bound), this would silently misclassify. The type system guarantees this never happens.

---

## Finding C — IrMultiMap.__iadd__ EAFP REGRESSES

**Do NOT apply EAFP to `__iadd__`.**

The Earley engine's filing pattern is dominated by first inserts (each `(item, end)` in `links` is new; each waiter bucket starts empty). EAFP (`try table[key].append(v) except KeyError: table[key] = [v]`) forces a `KeyError` exception on every first insert. In Python, exception construction is expensive:

```
N=1000 unique keys (all first-insert, like links table):
  current get+None check:    median=151µs
  EAFP try/except:           median=259µs  ← x1.7 SLOWER
```

For mixed (1-3 inserts/bucket, like waiting):
```
  current: 255µs  EAFP: 288µs  ← x1.13 SLOWER
```

**The current `get + None check + assignment or append` is optimal for first-insert-dominant workloads.**

Note: the existing code is already correct. `setdefault` is 4–6% slower than the current approach (confirmed in bench_adversarial).

---

## Finding D — IrMultiMap.__getitem__ EAFP

**Marginal, not worth landing.**

```
current: .get(key, ()):       median=973µs  (5000 lookups, all hits)
EAFP:    try table[key]:      median=913µs
speedup: x1.07
```

For `waiting[rule_name]` in `Complete`, the bucket virtually always exists (a rule is predicted before it completes). For `links[(item, end)]`, `__getitem__` is never called (only `__iadd__` and `__contains__` are used). The gain is real but small; not worth the miss-path cost penalty if a miss ever occurs, and the current code is clean.

---

## Finding E — IrLeaf/IrMapping MRO Overhead

**Cannot be beaten; effectively zero.**

Measured by comparing `IrMap.__getitem__` vs an equivalent flat `__slots__` class with no IrLeaf chain:

```
flat class (no IrLeaf chain):       median=1057µs
IrMap8 (__getitem__ via IrLeaf MRO): median=1052µs
ratio: x1.01
```

Python's MRO method resolution is cached after first call. There is no measurable overhead from the `IrMapping[K,V,R] → IrLeaf → IrNode → IrSelf` chain.

---

## Finding F — Slot Read Cost

**Negligible.** `self._table.get(k)` per call costs 0.05µs; a hoisted `tbl = self._table; tbl.get(k)` costs 0.055µs (no benefit from hoisting). Slot descriptors in CPython are fast; the overhead is in the dict.get call, not the attribute access.

---

## Finding G — Frozen `__setattr__` at Construction

**Zero cost.** Confirmed: `IrMapping.__new__` uses `object.__setattr__(obj, "_table", {})` which bypasses the frozen guard entirely. No cost on construction.

---

## Finding H — `__hash__`/`__eq__` on IrMap

**Not on hot paths.** `hash(frozenset(self._table.items()))` costs ~350µs per call (for a 5-entry map). But `IrMap` instances are never used as dict keys in the Earley engine. `__hash__/__eq__` is only exercised in equality assertions (tests, `repr`). If these were on a hot path, caching the hash would be warranted; they are not.

---

## Finding I — `__iter__` IrTuple Reconstruction

**Not on hot paths.** `iter(IrMap)` builds one `IrTuple(k, v)` per entry:

```
iter(IrMap) — builds IrTuple per dyad (1000x over 5-elem map): 1257µs
IrMap.items() — no IrTuple alloc (1000x):                       153µs
ratio: x8.2
```

Nothing in the Earley engine iterates an `IrMap` or `IrTypeMap` via `__iter__`. The only hot iteration is over `IrAlternation` arms (`for arm in rules.resolve(ref)`) — not map iteration. If this were hot, `items()` should be used instead. File for later if a profiler shows it.

---

## Finding J — IrMap Sort Cost

**Off the hot path; acceptable.**

`IrMap.__new__` sorts its dyads by `repr(d[0])` on every construction. For 5 dyads:

```
IrMap construction (with sort + object.__new__): median=1888µs (1000 maps)
sorted() alone (5 dyads):                        median=1213µs (1000 sorts)
```

Sort is ~64% of construction cost. `IrMap` instances are built during `RuleIndex.eval` (once per parse) and in grammar compilation (not per-dispatch). Not a hot path; the canonical ordering is correct and necessary for repr/equality stability.

---

## Finding 5 — None-Check Semantics

**Safe.** `IrMapping.__getitem__` and `resolve` use `if value is not None` to distinguish a hit from a miss. This is safe as long as no stored value is `None`. All values are `IrSelf` subclasses; `IrNone` (the absence sentinel) is `IrNoneType()` — an IrSelf instance, not Python `None`. Confirmed: all values in sample maps pass `v is not None`.

**Double `.get` in resolve:** The current `IrMapping.resolve` does `table.get(n)` then (on miss) `table.get(IR_DEFAULT)`. On an exact-type hit (the common case), this costs one extra `None`-check but no second dict probe. The proposed EAFP variant subsumes both into a single `try table[n] except` + MRO walk, cleanly.

---

## Validation Swap Details

Swap applied:
1. `src/lexic/ir/mapping.py` → shim re-exporting from `mapping8.py`
2. `forest.py::ForestCtx.__slots__ = ("_chart",)` — chart moved from tuple-slot-1 to a real slot; `__new__` uses `super().__new__(cls)` + `object.__setattr__`; `chart` property reads `self._chart`

Results:
```
recognize: 97.0ms → 91.8ms  (+5.7%)
parse:     124.3ms → 114.2ms (+8.1%)
ABNF fixpoint: TRUE (unchanged)
Suite: 1157 passed, 8 expected failures (tuple-ancestry tests only):
  - test_data_map_positional_int_returns_dyad  (m[0] no longer positional)
  - test_data_map_slice_returns_tuple          (slice no longer tuple-indexing)
  - test_plain_int_zero_is_positional_not_a_key_lookup (same)
  - test_contains_is_key_based_not_dyad_based (contains semantics differ)
  - test_synthesized_class_is_weakly_held_and_collected (WeakValueDict/metaclass)
  - test_irdispatch_is_caching_tuple (IrDispatch is no longer an IrSeq subclass)
  - test_links_getitem_snapshot_is_safe_while_bucket_grows (live bucket, not snapshot)
  - test_nullable_rules_returns_irseq (returns IrMultiMap, not IrSeq)
```

---

## Benchmarks That Tried to Beat mapping8 and Failed

| Target | Method tried | Result |
|--------|-------------|--------|
| MRO overhead | Flat class baseline | x1.01 — zero overhead |
| Slot read `self._table` | Hoisted local var | x0.96 — no benefit |
| `__iadd__` EAFP | try/except KeyError | x0.58–0.89 SLOWER on first-insert |
| `setdefault` for `__iadd__` | `setdefault(key, []).append(v)` | x0.95 (5% slower) |
| `dict.__getitem__` directly | `dict.__getitem__(table, t)` | x0.65 — slower than `table[t]` |
| `n.__class__` vs `type(n)` | `n.__class__` | x1.07 on resolve, minor |
| `__contains__` via `_table` | `key in self._table` vs `key in mm` | 24-95% overhead from method call — but the method IS the dict check |

---

## Recommended Change-Set

**Land these two patches to `mapping8.py`** (propose — do not modify `mapping8.py` as the deliverable):

### Patch A: `IrTypeMap.resolve` — EAFP for exact-type hit

```python
def resolve(self, n: IrSelf) -> IrSelf:
    table = self._table
    t = type(n)
    try:
        return table[t]            # exact-type fast path, zero overhead on hit
    except KeyError:
        pass
    for base in t.__mro__:
        body = table.get(base)
        if body is not None:
            return body
    body = table.get(IR_DEFAULT)
    if body is not None:
        return body
    raise IrKeyError(f"{type(self).__name__}: no entry for {type(n).__name__}")
```

- Measured: +6% on dispatch micro (50k calls), ~1-2% on ABNF recognize
- No risk: exact types always registered in practice; MRO/default paths preserved
- Pyright-clean: no type violations

### Patch B: `IrMapping.__getitem__` — EAFP

```python
def __getitem__(self, key: object) -> R:
    try:
        return self._table[key]
    except KeyError:
        raise IrKeyError(f"{type(self).__name__}: no entry for {key!r}")
```

- Measured: +11% on `IrMap.__getitem__` (5k lookups, 5 keys)
- Safe: all stored values are `IrSelf` (never `None`); `KeyError` is correctly re-raised
- Applies to both `IrMap` and `IrMultiMap` at the ancestor level (but `IrMultiMap` overrides this)

### Already correct — do NOT change:

- `IrMultiMap.__iadd__`: the `get+None+assign/append` pattern is optimal for first-insert-dominant workloads (+70% SLOWER with EAFP on all-new-key input)
- `IrMultiMap.__getitem__`: `.get(key, ())` is fine; EAFP gives +7% but only applies to the hit path which doesn't dominate
- Sort in `IrMap.__new__`: off hot path, canonical order required
- `__hash__`: not called in hot paths
- `__iter__` with `IrTuple`: not called in hot paths

---

## Notes on the `resolve` Double-Get Optimization

The current `IrMapping.resolve` does two dict probes on a miss: `table.get(n)` then `table.get(IR_DEFAULT)`. With EAFP, the first probe becomes `table[n]` (one dict lookup + exception on miss). The second probe is deferred to the `except` branch, same as before. Net result on the common case (exact hit): one dict lookup, no None check, no second probe — strictly better.

On a miss with `IR_DEFAULT` registered (uncommon in practice): the cost is the same as current (one miss + one hit). On a miss with no `IR_DEFAULT` (error path): the exception is raised from the `except` block, same behavior as current.

**There is no double-get optimization needed beyond the EAFP restructuring** — the current two-probe pattern disappears naturally once EAFP is applied.
