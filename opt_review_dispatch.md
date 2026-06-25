# parsing_2 Optimization Review — Dispatch Overhead Angle

**Scope:** the IR dispatch substrate (`IrDispatch.eval`, `IrTypeMap`/`IrMap`/`IrMultiMap`)
as used by the Earley loop in `src/lexic/parsing_2/`.

**Verdict up front (skeptical):** the dispatch substrate is *not* the dominant
cost. It is already well-tuned — `IrTypeMap.resolve` is a single `dict.get` fast
path, the `try/except IrKeyError` is free on the no-exception path, and the
memoised-subclass machinery is built once at table-construction time, never in the
hot loop. The realistic ceiling for *pure dispatch-substrate* wins, measured by
fully collapsing all three operations into one procedural loop, is **~11%**
(427ms → 381ms on the x4 / 3680-char recognize). Most of that 11% is not
"algorithmic waste in dispatch" — it is the elimination of **Python call frames**.
The 4x gap vs Lark is paid mostly *inside* the operation bodies (chart mutation,
`EarleyItem`/`IrTuple` allocation, `BuildTree`) — not in resolving which body to run.

All numbers below are `recognize()` best-of-9 on the x4 input (baseline ~427–442ms,
run-to-run noise ±10ms). I report deltas, not absolutes, and flag where a delta is
within noise.

---

## Measurement baseline

| Stage | x1 (920ch) | x4 (3680ch) |
|---|---|---|
| Lark | 27ms | 111ms |
| e:recognize | 98ms | 432ms |
| e:parse | 99ms | 431ms |
| e:parse+reduce | 109ms | 501ms |

Recognize ≈ parse, so the cost is in **chart construction**, not tree extraction or
reduce. cProfile (x4, parse+reduce, 5 iters, 29.2M calls) top frames by tottime:

```
0.813  ops.py:165 Complete.eval        (255k calls, 3.24s cum)
0.714  ops.py:114 Predict.eval         (302k calls, 2.70s cum)
0.623  chart.py:137 Column.__iadd__    (769k calls)
0.555  forest.py:73 BuildTree.eval     (255k calls)
0.524  engine.py:171 CloseColumn.eval  (18k calls, 7.58s cum)
0.353  walk.py:57  IrDispatch.eval     (704k calls, 6.58s cum)  <-- the dispatch seam
0.273  base.py:421 IrScalar.__eq__     (495k calls)
0.232  engine.py:121 Matches.eval      (449k calls)
0.216  mapping.py:317 IrMultiMap.__getitem__ (255k calls)
0.204  mapping.py:250 IrTypeMap.resolve (704k calls)
0.164  mapping.py:213 IrMap.resolve     (419k calls)
0.162  mapping.py:302 IrMultiMap._table (860k calls)
```

`walk.py:57` has only **0.353s tottime** (its own frame); its 6.58s *cumulative* is
the bodies it calls. So the dispatch seam's *own* cost is ~4% of runtime, and
`IrTypeMap.resolve` adds ~2% more. That bounds the prize.

### Dispatch call distribution (per single recognize, x4)

Instrumented `CloseColumn`: **140,895** dispatches total —

| symbol after dot | op | count | share |
|---|---|---|---|
| `IrRuleRef` | Predict | 60,441 | 43% |
| `IrNoneType` | Complete | 51,124 | 36% |
| `IrCharClass` | Scan (no-op) | 20,334 | 14% |
| `IrLiteral` | Scan (no-op) | 8,996 | 7% |

**21% of all dispatches resolve to `Scan`, which is a pure no-op** — yet skipping
them entirely saved *nothing* measurable (see Finding 4). The dispatch-per-no-op is
genuinely cheap.

---

## Findings, ranked by payoff

### Finding 1 — Collapsing dispatch into one procedural loop: ~11%, but breaks IR purity
**Severity:** ~11% (427ms → 381ms). **This is the measured ceiling for the whole angle.**

**Evidence:** I inlined Predict + Complete + Scan directly into `CloseColumn.eval`
as one `while` loop, branching on `type(symbol) is IrRuleRef` / `dot >= len(arm)`,
reading `ctx.rules._index.get(...)` and `waiting._table.get(...)` directly, and
dropping the `IrSeq` snapshot. Result: **381ms vs 427ms baseline**, fixpoint still
holds.

**Proposed change:** none recommended as-is. This is the diagnostic that tells us
the upper bound, not a prescription.

**Constraint impact:** **VIOLATES IrSelf purity.** It removes per-symbol dispatch
(`d.eval(d, symbol, nc)` → `EARLEY_OPS`) entirely, folding `Predict`/`Complete`/
`Scan` from IrSelf bodies into procedural branches in one method. That is exactly
the "remove dispatch in favour of free functions" move the brief says must be
justified — and **11% does not justify discarding the engine's defining shape**
("the dispatch table IS the engine"). I record it only to bound the prize: even the
maximal, purity-destroying rewrite buys 11%, so the 4x gap is **not** a dispatch
problem. Do not pursue.

---

### Finding 2 — `IrMultiMap.__getitem__` allocates a fresh `IrSeq` snapshot per `Complete`: ~2–5%
**Severity:** ~2–5% (borderline; 5% in one combined run, ~2% isolated — partly noise).

**Evidence:** `mapping.py:317` (`IrMultiMap.__getitem__`, 255k calls) builds
`IrSeq(*self._table.get(key, ()))` on every read. `Complete` (`ops.py:176`) reads
`chart[done.origin].waiting[done.rule_name]` once per completion — 51k times — and
the snapshot exists only so the reader may iterate safely while the live bucket
grows (the `origin == col` case). The snapshot triggers `IrSeq.__new__` →
`IrTuple.__new__` (`base.py:581`, 981k calls overall) plus a fresh tuple. Replacing
the read with a plain `list(bucket)` over the backing `_table` dropped recognize to
~410–424ms.

**Proposed change (keeps purity):** in `ops.py:176`, the completer can read the live
bucket and take a cheap snapshot itself instead of round-tripping through the
value-returning `IrSeq` override. Two options, both IR-pure:
- Keep `waiting[rule_name]` but make `IrSeq` construction cheaper for the snapshot
  path, **or**
- Give `IrMultiMap` a `snapshot(key) -> tuple` dunder/read that returns a plain
  tuple (still a method on an IrSelf, no free function), and have `Complete` iterate
  that. The `IrSeq` wrapper buys nothing here — the completer only iterates it.

**Constraint impact:** keeps IrSelf purity. `IrMultiMap` stays an `IrSelf`; the read
stays a dunder/method on it. Only the *result wrapper* changes from `IrSeq` to a
plain snapshot, which `Complete` already throws away after iterating.

---

### Finding 3 — `ScanColumn` calls `Matches.eval` on ruleref / completed items that can never match: ~3–4%
**Severity:** ~3–4% (442ms → 426ms).

**Evidence:** `engine.py:203-205` loops *every* item in the column and calls
`MATCHES.eval(d, item.arm[item.dot].atom, char_nc)` whenever `dot < len(arm)`. For a
ruleref atom, `Matches.eval` (`engine.py:121`, **449k calls**, 0.23s tottime) runs
two `isinstance` checks and returns `_NO_MATCH`. Rulerefs are ~43% of advanceable
symbols, so a large fraction of those 449k calls are guaranteed misses. Guarding
with `type(atom) is not IrRuleRef` before the call dropped recognize 442 → 426ms.

**Proposed change (keeps purity):** in `ScanColumn.eval` (`engine.py:203`), skip
items whose dot faces an `IrRuleRef` before invoking `MATCHES.eval`:
```python
atom = item.arm[item.dot].atom
if type(atom) is not IrRuleRef and MATCHES.eval(d, atom, char_nc):
    ...
```
`Matches` stays the IR op; this is a guard, not a removal. (Symmetry note: this is
the scan-side mirror of the predict/complete split the close loop already makes.)

**Constraint impact:** keeps IrSelf purity fully. `Matches` is still the dispatched
terminal-match op; we only avoid calling it where the answer is statically 0.

---

### Finding 4 — Skipping the `Scan` no-op dispatch entirely: ~0% (do NOT do)
**Severity:** 0% (433.7 vs 434.3ms — noise).

**Evidence:** 21% of all 140k dispatches resolve to `Scan`, a no-op. I hypothesised
skipping them in `CloseColumn` (continue on terminal symbols) would help. It did
not: 434.3 → 433.7ms. The dispatch-to-no-op (`resolve` = one `dict.get` hitting the
`IrCharClass`/`IrLiteral` key, then `Scan.eval` returning `IrNone`) is genuinely
~50ns; 29k of them is ~1.5ms, lost in noise.

**Proposed change:** none. This documents that the dispatch *substrate* is not the
bottleneck — even a fifth of all dispatches being pure waste costs nothing. It also
warns against the tempting micro-opt of special-casing terminals in the close loop;
it adds a branch for no gain and muddies the loop.

**Constraint impact:** n/a (rejected).

---

### Finding 5 — Drop the `walk.py:57` frame by resolving in `CloseColumn`: ~2%
**Severity:** ~2% (430 → 421ms).

**Evidence:** Each item dispatch is `CloseColumn` → `d.eval(d, symbol, nc)`
(`walk.py:57`) → `self.actions.resolve(n)` → `body.eval(d, n, nc)`. That is two
Python frames (`IrDispatch.eval` + the resolved body) plus the `try`. Calling
`d.actions.resolve(symbol).eval(d, symbol, nc)` straight from `CloseColumn` removes
the `IrDispatch.eval` frame while **keeping the table-driven resolution**. Measured
430 → 421ms.

**Proposed change (keeps purity):** in `CloseColumn.eval` (`engine.py:181`), replace
`d.eval(d, symbol, nc)` with `d.actions.resolve(symbol).eval(d, symbol, nc)`.
Resolution still goes through `IrTypeMap` (the IrSelf table); only the convenience
wrapper frame is skipped.

**Caveat / tradeoff:** `IrDispatch.eval` also owns the `IrKeyError → default`
fallback. In the Earley loop the symbol type is always one of the five registered
keys (`IrRuleRef`/`IrLiteral`/`IrCharClass`/`IrRange`/`IrNoneType`), so the fallback
never fires — but inlining `resolve()` means a future unregistered symbol type would
raise `IrKeyError` instead of hitting `default`. Since `EARLEY_OPS` has no
`IR_DEFAULT` and `default = IrRaise()`, the observable behaviour (raise on unknown
symbol) is identical; this is safe. Still, this 2% trades a small amount of the
seam's uniformity for speed — marginal, list it as optional.

**Constraint impact:** keeps IrSelf purity. The `IrTypeMap` table is still the
resolver; `Predict`/`Complete`/`Scan` are still IrSelf bodies invoked via `.eval`.
Only `IrDispatch.eval`'s wrapper frame is bypassed at the one hot call site.

---

## What is NOT worth touching (skeptic's list)

- **`IrTypeMap.resolve` MRO walk.** It already fast-paths the exact-type hit with a
  single `dict.get(type(n))` (`mapping.py:260`) before ever materialising
  `__mro__`. Every Earley symbol is a registered concrete type, so the MRO loop and
  `IR_DEFAULT` lookup never execute. No win available here.
- **`IrMap.resolve` for the rule index.** `mapping.py:226` already tries
  `self._index.get(n)` first; the rule ref is always registered, so it is one
  `dict.get` and returns. The `_keys()` + `IR_DEFAULT` fallback never runs. Reading
  `ctx.rules._index.get(ref)` directly (Finding 1) saves only the method frame.
- **Dispatch cache warmth.** There is no per-parse dispatch memo to warm/cold — the
  `IrTypeMap` index is built once when `EARLEY_OPS` is constructed at import and
  read-only thereafter. The brief's mention of "memoisation … warm/cold per parse"
  is stale; current `walk.py` has *no* memo (its docstring says "no memo, no
  per-instance cache"). Nothing to fix.
- **`_table` property indirection (`mapping.py:302`, 860k calls).** Real, but each is
  a trivial `tuple.__getitem__(self, 0)`. Only Finding 1's full inline removes it,
  and that breaks purity.

---

## Recommended set (keeps IrSelf purity), combined expected ~6–9%

Apply **Findings 2, 3, 5** together — all keep the dispatch table and IrSelf bodies:

1. **Finding 3** (skip `Matches` on rulerefs in `ScanColumn`) — ~3–4%, zero risk,
   cleanest win.
2. **Finding 2** (drop the `IrSeq` snapshot wrapper in `Complete`'s waiting read) —
   ~2–5%, low risk.
3. **Finding 5** (resolve in `CloseColumn`, skip the `walk.py:57` frame) — ~2%,
   optional, marginal uniformity tradeoff.

Their effects partially overlap (all shave per-item frame/alloc cost), so expect
the combined recognize to land around **390–405ms (~6–9% off 432ms)**, not the
naive sum.

## The honest conclusion

The dispatch substrate is **not** why parsing_2 is 4x slower than Lark. The maximal
purity-destroying inline buys 11%; the purity-preserving set buys ~6–9%. To close
the 4x gap, the heavy levers are elsewhere and outside this angle's mandate:
**per-item allocation** (`EarleyItem.__new__` 842k, `IrTuple.__new__` 981k,
`IrScalar.__new__` 416k), **`Column.__iadd__`** (769k calls, set+list+waiting-file
each insert), **`IrScalar.__eq__`** (495k, the type-aware equality on every item
dedup / dict probe), and **`BuildTree` eager subtree construction during parse**
(255k calls — building SPPF nodes the recognizer never needs). Those — not dispatch
— are where the 300ms lives. Recommend the dispatch-angle changes above as solid
single-digit wins, and direct the next review at the allocation/equality/chart-insert
hot path.
