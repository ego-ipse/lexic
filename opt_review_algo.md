# parsing_2 — Algorithmic & Data-Structure Review

**Scope:** the *shape* of the Earley algorithm and its data structures in
`src/lexic/parsing_2/`. Micro-allocation is out of scope (separate review).

**Verdict up front:** the 4–4.5x gap and the *growing* ratio are the **same
defect**. `normalize.py` desugars every `*`/`+`/`?` into a **right-recursive**
synthetic rule, and right recursion is the textbook Earley O(n²) trap. Lark is
linear; parsing_2 is super-linear, so the ratio must grow with input. Fixing the
desugaring shape (or adding Leo's optimization) converts the dominant term from
O(n²) to O(n). Everything else is second-order.

---

## The growing-ratio question, answered with data

Scaling sweep on the benchmark input (`BASE` ABNF source × multiplier),
recognition only, best-of-n:

| mult | chars | lark ms | earley ms | ratio | earley µs/char | lark µs/char |
|-----:|------:|--------:|----------:|------:|---------------:|-------------:|
| 1    |   920 |   27.96 |     99.36 | 3.55  | 108.0          | 30.4         |
| 2    |  1840 |   54.39 |    203.68 | 3.74  | 110.7          | 29.6         |
| 4    |  3680 |  108.30 |    431.28 | 3.98  | 117.2          | 29.4         |
| 8    |  7360 |  215.68 |    985.42 | 4.57  | 133.9          | 29.3         |
| 16   | 14720 |  439.42 |   2265.98 | 5.16  | 153.9          | 29.9         |

**Lark's µs/char is flat (~29.5) — linear. parsing_2's rises 108→154 (×1.4 over
16× input) — super-linear.** The ratio grows *because* of this, not because of a
worse constant alone (the constant is also ~3.6× worse, but that is the
micro-review's problem).

### Isolating the super-linear term

The grammar is fixed (34 rules) regardless of input size, so the per-char rise is
chart-position-dependent work. Instrumenting the chart:

- `max_col` (largest column's item count) grows **linearly with input position**:
  60 → 79 → 147 → 283 → 555 across mult 1→16. A column whose size grows with
  position ⇒ O(n) work per column ⇒ O(n²) total.
- The biggest column (283 items at mult 8) is **271 copies of the same complete
  item `('__rep_1', dot=2, complete)`**, spread across **274 distinct origins**.
  That is one complete `__rep_1` per element matched so far — the right-recursion
  signature.

### Clean confirmation with a pure right-recursive input

A single valid grammar of *N* trivial rules (`r0 = %x41` … one long
`rulelist = 1*(rule …)`, i.e. one right-recursive `__rep_1`):

| N rules | chars | recognize ms | µs/char | max_col |
|--------:|------:|-------------:|--------:|--------:|
| 50      |   590 |        45.40 |  76.9   | 61      |
| 100     |  1190 |        99.69 |  83.8   | 111     |
| 200     |  2490 |       248.42 |  99.8   | 211     |
| 400     |  5090 |       688.02 | 135.2   | 411     |
| 800     | 10290 |      2039.50 | 198.2   | 811     |

`max_col == N` *exactly*. Time grows **45×** for a 16× input — squarely O(n^~1.4)
trending to O(n²). This is the right-recursion quadratic, full stop.

### Why it isn't *worse* than it is

The completer's `waiting` bucket per rule stays **small** (avg ~1 waiter per
completion; `waiter_iters/char` only 12→17 across mult 1→8), and `BuildTree`
chains stay **short** (max length 7, because the completer builds sub-trees
eagerly). So the quadratic is purely in the **count of complete items created**
(`complete_calls`/`subtree_builds` ≈ 11k → 121k for mult 1→8, ratio 2.1→2.36 per
doubling — the tell-tale super-linear growth), not in per-completion fan-out or
chain walking. Those two facts (small buckets, short chains) are good news: they
mean the standard right-recursion fixes apply cleanly.

---

## Findings, ranked by payoff

### F1 — Right-recursive quantifier desugaring is the O(n²) source — **CRITICAL, est. 2–4× on the benchmark, asymptotic win unbounded**

**Evidence:** `normalize.py:163-189` (`Expand.eval`) and `:200-212`
(`OptChain.eval`) mint **right-recursive** rules:

```
*  →  X = "" / elem X        (normalize.py:173)
+  →  X = elem / elem X      (normalize.py:175)
m* →  ... elem (X tail) ...  (normalize.py:177-178)
```

The recursive ref sits **after** the element. In Earley, a right-recursive
non-terminal forces the completer to re-advance a fresh complete item at *every*
position back to the rule's origin — O(n) complete items per closing column,
O(n²) overall. Confirmed: `max_col` scales linearly with the number of repeated
elements (table above), and the dominant column is ~96% identical
`('__rep_1', complete)` items at distinct origins.

**Proposed change — switch to LEFT recursion** in `Expand`/`OptChain`
(`normalize.py:173-189`, `:206-211`):

```
*  →  X = "" / X elem
+  →  X = elem / X elem
```

Earley parses **left** recursion in linear time (the recursive ref is *before*
the dot, so prediction is shared and completion advances exactly one item).

**Measured prototype (throwaway, reverted):** a hand-rolled left-recursive
desugaring of `*`/`+` on the same pure-right-recursion input flips the curve
completely:

| N rules | chars | recognize ms | max_col |
|--------:|------:|-------------:|--------:|
| 50      |   590 |         1.71 | **22**  |
| 100     |  1190 |         3.08 | **22**  |
| 200     |  2490 |         6.14 | **22**  |
| 400     |  5090 |        12.08 | **22**  |
| 800     | 10290 |        25.20 | **22**  |

`max_col` becomes **constant**; time becomes **perfectly linear** (14.7× for a
16× input vs 45× before). This is the O(n²)→O(n) conversion, ~80× faster at
N=800.

**Caveat — not free, do not ship blind.** Left recursion **reverses the
derivation order** of the matched elements. The reducer
(`reduce.py:ResolveChildren`) and the synthetic-rule splicing
(`reduce.py:105`, keyed on `SYNTHETIC_PREFIX`) assume the right-recursive shape
where `kids` come out in source order. A left-recursive `__rep` yields kids in
reverse nesting; `ResolveChildren`'s flat-map splice would need to reverse the
spliced run for synthetic rep-rules (or the rep-rule body must be tagged so the
splicer knows to reverse). My prototype deliberately skipped this (recognition
`ok=False` for the full ABNF self-parse) — it proves the **scaling thesis** but
*not* drop-in correctness. The required follow-up is a small, contained reversal
in the splice path, gated by the synthetic-rep marker. The `?` case (`X = "" /
elem`) and bounded counts are not recursive and need no change.

**Constraint impact:** **keeps IrSelf purity fully.** The change is entirely
inside `Expand.eval`/`OptChain.eval` bodies (already `IrSelf` `eval` nodes) — it
swaps `IrSequence(unit, ref)` for `IrSequence(ref, unit)`. No new free functions,
no new mutable state. The reducer fix is also a body edit. This is the
recommended primary fix.

---

### F2 — If left recursion's reduction cost is unacceptable, add Leo's optimization instead — **CRITICAL alternative, same asymptotic win, higher engine complexity**

**Evidence:** same as F1. Leo (1991) is the canonical fix that keeps right
recursion *and* gets O(n) on right/RR grammars: when a completion would advance a
**single** deterministic ("topmost") item, it installs a *transitive* (Leo) item
that short-circuits the whole completion chain, so a closing column gets one
item, not N.

**Why it's viable here specifically:** the data shows the completer buckets are
**already nearly deterministic** — avg ~1 waiter per completion (instrumented:
`snap_total ≈ complete_calls`). Deterministic reduction is *exactly* Leo's
precondition, so almost every `__rep` completion qualifies for a Leo item. The
payoff would track F1's ~80×.

**Proposed change:** add a `leo` index to `Column` (`chart.py:120` slots) mapping
a rule-name → its transitive (Leo) item, populated when `Complete.eval`
(`ops.py:165`) detects a unique waiter whose own post-dot symbol is the
just-completed rule; `Complete.eval` then advances the Leo item directly instead
of the chain. `BuildTree` (`forest.py:73`) needs Leo-item link expansion on
reconstruction (a known, contained complication).

**Constraint impact:** keeps IrSelf purity — `leo` is another dunder-surface
index on `Column` (same mutable-chart exception already documented at
`chart.py:6`), and the logic lives in `Complete.eval`'s body. **Tradeoff vs F1:**
more engine code and a trickier `BuildTree`, but **no reduction-order change** —
derivations stay source-ordered, so `reduce.py` is untouched. **Recommendation:**
prefer F1 (simpler, smaller, reduction fix is local); fall back to F2 only if the
reducer reversal proves messy.

---

### F3 — `?` and bounded-count desugaring also right-recurse and inflate nullable rules — **MODERATE, est. 5–15%**

**Evidence:** `normalize.py:181` (`?  → X = "" / unit`) and `OptChain`
(`:200-212`) build nested-optional chains; `Expand` for `m*`/`{lo,hi}`
(`:177-187`) chains right-recursive sub-rules. Each `*`/`?` introduces a
**nullable** rule (confirmed: `__rep_2..__rep_19` mostly have an empty arm). The
normalized ABNF grows 34 → 53 rules and 50 → 88 arms — every extra nullable rule
adds predictor work and an Aycock-Horspool null-advance per prediction
(`ops.py:127-134`).

**Proposed change:** (a) fold `?` directly at the *item* level where the parent
arm can host an optional-skip rather than minting a nullable rule, eliminating a
predict/complete cycle per `?`; (b) for bounded `{lo,hi}`, prefer iterative
unrolling without the right-recursive `OptChain` tail (the chain is the same
right-recursion trap at small scale). Lower priority — these are not the hot
path in the ABNF benchmark (the `1*(rule)` `__rep_1` dominates), but they
compound F1.

**Constraint impact:** keeps IrSelf purity — all inside the normalize `eval`
bodies. No new abstractions.

---

### F4 — `IrMultiMap.__getitem__` allocates a fresh `IrSeq` snapshot per completion — **MINOR, est. 3–6%**

**Evidence:** `Complete.eval` (`ops.py:176`) calls
`chart[done.origin].waiting[done.rule_name]`, which hits
`IrMultiMap.__getitem__` (`mapping.py:317`) — **255k calls** in the profile, each
building a brand-new `IrSeq(*bucket)` tuple even when the bucket has 0–1 entries.
The snapshot exists only to be safe against the live bucket growing when
`origin == col`.

**Proposed change:** the snapshot is only needed when `done.origin == ctx.col`
(self-completion can append to the bucket being iterated). For the common
`origin < col` case the bucket is frozen and can be iterated in place. Add a
read-the-live-list dunder used when `origin < col`, snapshot only when
`origin == col`. Alternatively iterate by index over a length captured up front.

**Constraint impact:** keeps IrSelf purity — a dunder on `IrMultiMap`
(`mapping.py`), no free function. Caveat: under F1/F2 the completion count drops
~80×, so this finding mostly evaporates; only worth doing if F1/F2 are deferred.

---

### F5 — `Predict.eval` re-predicts already-predicted rules — **MINOR, est. 5–10% of predict time, but predict is 302k calls**

**Evidence:** `Predict.eval` (`ops.py:114-135`) adds a dot-0 item per arm of the
target rule on **every** prediction of that rule in a column. The `Column.__iadd__`
dedup (`chart.py:148`) drops the duplicate, but only *after* constructing the
`EarleyItem`, hashing it, and probing `_seen` — 302k predict calls, and
`Column.__iadd__` is 769k calls / 0.62s tottime in the profile. The same
non-terminal is predicted once per waiting item in a column.

**Proposed change:** keep a per-column `set[IrRuleRef]` of "already predicted"
rules (another dunder-surface index on `Column`, like `waiting`); `Predict.eval`
early-returns if the rule was predicted in this column already (the dot-0 arms are
identical and origin is always the current column, so re-prediction is pure waste).
This skips arm-item construction + dedup probes entirely for repeat predictions.

**Constraint impact:** keeps IrSelf purity — a membership index on `Column`
maintained in `__iadd__`/a new dunder, logic stays in `Predict.eval`. Composes
with F1 (predict count also drops once columns shrink, but the per-column
re-prediction waste is independent of recursion direction).

---

### F6 — Per-column full re-scan in `CloseColumn` is fine; the driver has no redundant passes — **NO ACTION (verified)**

**Evidence:** `CloseColumn.eval` (`engine.py:171-182`) walks the column with a
single advancing cursor and processes newly-appended items in the same pass (no
separate worklist, no re-scan). `BuildChart` (`engine.py:240-245`) does exactly
one close + one scan per position. `ScanColumn` (`engine.py:195-213`) scans each
item once. **No redundant driver passes exist** — the loop structure is already
optimal. The cost is purely the *number of items* the loop must visit, which F1
addresses. Recorded so the next reviewer doesn't re-investigate the driver.

---

## Summary ranking

| # | Finding | Severity / payoff | Keeps IrSelf purity? |
|---|---------|-------------------|----------------------|
| F1 | Left-recursive desugaring (the fix) | **CRITICAL — O(n²)→O(n), ~80× at N=800, 2–4× on benchmark** | Yes (body edit + local reducer reversal) |
| F2 | Leo's optimization (alternative) | **CRITICAL — same asymptotics, more code** | Yes (new `Column.leo` index, body logic) |
| F3 | `?`/bounded right-recursion + nullable inflation | Moderate — 5–15% | Yes |
| F4 | `IrMultiMap` snapshot per completion | Minor — 3–6% (evaporates under F1/F2) | Yes |
| F5 | Redundant re-prediction per column | Minor — 5–10% | Yes |
| F6 | Driver loop (verified clean) | None | n/a |

**Recommendation:** ship **F1** (left recursion) as the primary fix — it is the
smallest change with the largest payoff and stays inside existing `eval` bodies.
Pair it with the reducer reversal for synthetic rep-rules. Hold **F2** (Leo) as
the fallback if the reduction-order change proves too invasive. F3/F5 are
worthwhile cleanups that compose with either; F4 only matters if F1/F2 are
deferred.

*All measurements: best-of-n, gc disabled, on the benchmark harness
(`bench_parsing.py`) plus throwaway scaling/instrumentation scripts (since
deleted). No production code was modified.*
