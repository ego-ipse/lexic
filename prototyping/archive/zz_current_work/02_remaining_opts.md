# Remaining Optimizations — Re-validation on Post-SPPF Engine

**Date:** 2026-06-26
**Engine state:** SPPF closed and green (1126 tests pass, ABNF fixpoint holds).
**Baseline re-measured on this session** — numbers below are fresh.

---

## New Baseline (post-SPPF engine)

All measurements: `uv run python z_current_work/bench_parsing.py`, best-of-N, gc disabled.

| size | chars | lark best | e:recognize | e:parse | e:parse+red | ratio |
|-----:|------:|----------:|------------:|--------:|------------:|------:|
| x1   |   920 |   27.5 ms |     95.6 ms | 121.7 ms |  131.3 ms |  4.78x |
| x2   |  1840 |   54.5 ms |    207.5 ms | 263.7 ms |  286.3 ms |  5.25x |
| x4   |  3680 |  111.4 ms |    441.3 ms | 551.7 ms |  613.5 ms |  5.50x |

**Key shift vs pre-SPPF baseline:** recognize is now SLOWER than parse on the old
numbers (pre-SPPF: x4 recognize 431ms, parse 418ms — they were ~equal). Post-SPPF,
parse costs more than recognize because the SPPF forest traversal (`SppfNode` +
`FamilyPrefixes` / `DerivationTrees`) adds overhead on the parse path that doesn't
exist during recognize. The recognize path is essentially unchanged in shape; the
absolute numbers moved slightly due to system load. The super-linear trend remains.

**cProfile top frames (x4, 5 runs parse+reduce, sorted tottime):**

```
1024530  1.515  base.py:581       IrTuple.__new__      (← #1, up from #6 pre-SPPF)
 302205  0.976  ops.py:130        Predict.eval
 255620  0.642  ops.py:195        Complete.eval        (← halved vs 0.848 pre-SPPF)
 842520  0.638  chart.py:161      Column.__iadd__
  18405  0.522  engine.py:200     CloseColumn.eval
 151405  0.415  forest.py:362     (SPPF forest node)   (← new, SPPF cost)
  704475  0.371  walk.py:57       IrDispatch.eval
  340520  0.297  mapping.py:337   IrMultiMap.__getitem__
  448820  0.237  engine.py:128    Matches.eval
```

Notable shift: `BuildTree` (forest.py:73, 255k calls, 0.555s cumtime) is GONE
from the pre-SPPF top. In its place `IrTuple.__new__` has become the dominant
allocation (1.025M calls, 1.515s tottime) — driven by `IrSeq` snapshot allocations
in `IrMultiMap.__getitem__`. `Complete.eval` tottime dropped from 0.848 to 0.642
(confirming SPPF removed the eager-subtree build from the hot path).

---

## Instrumentation Counts (single x4 parse)

| metric | value |
|--------|-------|
| `Predict.eval` calls | 60,441 |
| `Complete.eval` calls | 255,620 |
| `IrMultiMap.__getitem__` calls | 68,104 |
| Empty bucket reads | 136 |
| Avg bucket size (non-empty) | 1.01 items |
| `Matches.eval` calls (ScanColumn) | 89,764 |
| Matches calls on IrRuleRef (no-op) | 60,436 (67.3%) |
| AH (Aycock-Horspool) firings | 14,608 (24.2% of predicts) |
| Redundant predicts (would skip via set) | 6,773 (11.2% of predicts) |

---

## F3 — `?`/bounded-count desugaring right-recurses + nullable-rule inflation

**Previous estimate:** 5–15%.

### Evidence on current engine

The normalized ABNF grammar has 53 rules (vs 34 original) and 88 arms (vs 50).
All 19 synthetic rules use right-recursion for `*`/`+` and nested optionals for `?`:

- 4 non-nullable `+`/`*` rules (sizes `[1]`/`[1,2]`)
- 4 simple `?` rules (sizes `[0,1]`) — `__rep_11/12/13/19`
- 11 opt-chain rules (sizes `[0,2]`) — `__rep_2..9, 15,16,17`
- Total nullable synthetic rules: 15

AH fires 14,608 times per x4 parse (24.2% of all predicts), each checking ~1.9 arms.

**Measured costs (x4, 9 runs best-of):**

| experiment | recognize | delta |
|-----------|-----------|-------|
| Baseline x4 | 415–427 ms | — |
| Skip AH for 4 simple `?` rules only | ~410 ms | ~1.7% |
| Skip AH for ALL 15 synthetic nullable rules | ~377 ms | **~11.8%** |

The **upper bound for F3** (if all opt-chain/? rules were eliminated entirely) is
~12% on recognize. In practice, only the `?` cases can be folded inline at the
item level; opt-chains (`{lo,hi}` unrolling) require either unrolling-at-parent
or a different desugaring strategy.

**The simple-? fold** (4 rules, ~1.7%) is cheap to implement but low-value.
**The opt-chain elimination** (11 rules, remainder of the ~12%) is the real prize
but requires redesigning `OptChain.eval` to unroll without nullable synthetics.

### F3 verdict on current engine

**MODERATE — holds at ~5–12% depending on depth.** The upper bound confirmed.
The simple-`?` portion (~2%) is not worth a standalone change. The opt-chain
portion (~10%) is real but requires a non-trivial `normalize.py` redesign:
instead of `X = "" | unit inner`, unroll the optional tail inline in the parent
arm as a sequence of optional refs, or represent `{lo,hi}` as `lo` mandatory
items + `(hi-lo)` optional suffixes at the PARENT arm level (no recursive rule).

**Interaction with F1:** F1 cuts completion count ~80× for `*`/`+` rules. After
F1 the remaining cost from `?`/opt-chain is prediction overhead, not completion
overhead. F3 remains independently useful. The 15 nullable rules also make F1's
left-recursion benefit more pronounced (nullable arms increase item count further).

**Priority: LOW-MEDIUM.** Implement only after F1; measure residual cost post-F1
before deciding whether to tackle the opt-chain redesign.

---

## F4 — `IrMultiMap.__getitem__` snapshot per completion

**Previous estimate:** 2–6% (noted: evaporates under F1).

### Evidence on current engine

68,104 `IrMultiMap.__getitem__` calls per x4 parse (vs 51,124 pre-SPPF — up
~33% because `Links` is now also an `IrMultiMap` subclass, widening the surface).
Each call builds a fresh `IrSeq(*bucket)`, which triggers `IrTuple.__new__` (now
the #1 tottime frame at 1.515s). Average bucket size: 1.01 items — almost always
a 1-element snapshot.

**The snapshot is only needed when `done.origin == ctx.col`** (self-completion
can grow the bucket being iterated). For the ~99%+ case of `origin < col`, the
bucket is frozen and can be iterated directly.

**Patch:** in `Complete.eval`, replace `chart[done.origin].waiting[done.rule_name]`
(which goes through `IrMultiMap.__getitem__` → `IrSeq`) with a direct
`_table.get(done.rule_name)` + conditional `tuple(bucket)` snapshot only when
`done.origin == ctx.col`.

**Measured (x4, 12 runs, best-of):**

| variant | recognize | parse | delta recognize |
|---------|-----------|-------|-----------------|
| Baseline | 415 ms | 521 ms | — |
| F4 only | 400–406 ms | 507 ms | **4–5%** |
| F4 at x1 | 92 ms vs 99 ms baseline | — | **~7%** |

At x1 the delta is ~7%, suggesting F4 is slightly more impactful on smaller inputs
where the column iteration overhead dominates.

### F4 verdict on current engine

**HOLDS — now 4–7% on recognize (up from 2–6%).** The SPPF rewrite widened the
`IrMultiMap.__getitem__` call surface and made `IrTuple.__new__` the top
bottleneck, so this finding is MORE valuable post-SPPF, not less.

**Interaction with F1:** F1 cuts the completion count ~80×, so `Complete.eval` fires
far less often. Under F1 this optimization largely evaporates. Do it only if F1 is
deferred, or as a cheap cleanup after F1.

**Implementation note:** the fix reads `waiting._table` directly from `ops.py`
(poking the backing dict). Cleaner option: add a `raw(key)` method or a read-only
dunder to `IrMultiMap` returning a plain-list reference when `origin < col`, keeping
`ops.py` from knowing the internal layout. Both keep IrSelf purity.

**Priority: LOW (after F1) / MEDIUM (if F1 deferred).**

---

## F5 — `Predict.eval` re-predicts already-predicted rules

**Previous estimate:** 5–10% of predict time.

### Evidence on current engine

6,773 out of 60,441 predict calls (11.2%) would be skipped if a per-column
"already predicted" set were maintained. That is the arm-seeding fraction;
Aycock-Horspool (AH) must still fire per predicting item because each `it` (the
predecessor) differs and produces a different `Link`.

**Patch tested (two variants):**

1. Global `dict` keyed by `(id(ctx), col_idx)` → `set[str]`; skip arm-seeding
   for already-predicted refs; always run AH.
2. Per-column `_predicted` attribute (monkeypatched via `Column.__init__`); same
   logic.

**Measured (x4, 9 runs best-of):**

| variant | recognize | delta |
|---------|-----------|-------|
| Baseline | 410–424 ms | — |
| F5 variant 1 (global dict) | 420–437 ms | **−6 to −7% (SLOWER)** |
| F5 variant 2 (per-column attr) | 420–427 ms | **0 to −3% (neutral/slower)** |

**The overhead of the dict/set lookup and membership cost more than the arm
seeding it avoids.** The arms-already-seeded items are deduped cheaply by
`Column.__iadd__`'s `_seen` set (a single `in self._seen` probe + no
`list.append`). The saved work (constructing `EarleyItem` + probing `_seen` for
a dup) is smaller than the set-maintenance cost.

### F5 verdict on current engine

**EVAPORATED → NEGATIVE.** The measurement is consistently negative (−6 to −7%
slower in the dict variant). This is a stronger failure than the prior "neutral"
result (`alloc F7`). The extra set-maintenance bookkeeping costs more than the
12% arm-seeding it saves.

**Interaction with F1:** Under F1, predict count drops proportionally. The
set-maintenance cost stays constant per predict call, so the ratio likely stays
negative.

**Priority: DROP. Confirmed dead end.**

---

## ScanColumn Matches Guard (dispatch finding F3)

**Previous estimate:** ~3–4%.

### Evidence on current engine

89,764 `Matches.eval` calls per x4 parse, of which 60,436 (67.3%) are on
`IrRuleRef` atoms — which always return `_NO_MATCH` immediately but still pay
two `isinstance` checks. The ruleref fraction is UP from ~43% in the old profile
(the distribution shifted post-SPPF, possibly because SPPF changed how items
are distributed across columns; the grammar is unchanged).

**Patch:** in `ScanColumn.eval` (`engine.py:233`), guard with
`type(atom) is not IrRuleRef` before calling `MATCHES.eval`. `Matches` stays the
dispatch IR op; only the guaranteed-zero call is avoided.

```python
if item.dot < len(item.arm):
    atom = item.arm[item.dot].atom
    if type(atom) is not IrRuleRef and MATCHES.eval(d, atom, char_nc):
        ...
```

**Measured (x4, 9–12 runs, best-of):**

| variant | recognize | parse | delta recognize |
|---------|-----------|-------|-----------------|
| Baseline | 415–427 ms | 521–533 ms | — |
| Scan guard only | 385–401 ms | 499–515 ms | **5–7%** |

The scan guard is now **5–7% on recognize** (up from 3–4% pre-SPPF). The
ruleref fraction rose from 43% to 67%, so the guard skips nearly 2/3 of all
Matches calls — a proportionally larger win.

### Combined F4 + Scan guard

| variant | recognize | parse | delta rec | delta parse |
|---------|-----------|-------|-----------|-------------|
| Baseline | 415 ms | 521 ms | — | — |
| F4 + guard (x4) | 373–391 ms | 474–508 ms | **8–10%** | **7–9%** |
| F4 + guard (x1) | 89 ms vs 99 ms | 119 ms vs 122 ms | **~10%** | **~3%** |
| F4 + guard (x2) | 183 ms vs 199 ms | 240 ms vs 254 ms | **~8%** | **~6%** |

The two patches partially overlap (both reduce per-item overhead in the hot loop)
but together deliver a clean 8–10% on recognize and 7–9% on parse.

### Scan guard verdict on current engine

**HOLDS — stronger than pre-SPPF (~5–7% vs ~3–4%).** The ruleref share grew
from 43% to 67% post-SPPF. The guard is a one-liner with zero design risk and
full IrSelf purity.

**Interaction with F1:** Under F1, column item counts drop ~80×. ScanColumn
visits each column's items regardless; with fewer items the absolute savings
shrink but per-item ratio stays. Post-F1 this likely remains a ~5% win.

**Priority: HIGH — easiest win, ships anytime, composes cleanly with F1.**

---

## #5 Dispatch Collapse — Re-verify NEGATIVE Result

**Previous finding:** ~11%, breaks IrSelf purity — do not pursue.

### Current engine measurement

Full collapse of `CloseColumn.eval` into a procedural loop (inline predict +
complete + guard for terminals, read `waiting._table` directly, bypass all
`IrDispatch.eval` + `IrTypeMap.resolve` round-trips):

**Measured (x4, 9–15 runs, best-of):**

| variant | recognize | delta |
|---------|-----------|-------|
| Baseline | 415–428 ms | — |
| Full procedural collapse | 339–365 ms | **14–18% faster** |

**The win GREW from ~11% to ~14–18% post-SPPF.** The cProfile shows `IrTuple.__new__`
is now the top frame (driven largely by `IrSeq` snapshot allocations, which the
collapsed version also bypasses directly). The full collapse inlines both F4
(no `IrSeq` snapshot) AND the dispatch-frame elimination AND removes `ctx.item`
assignment from the loop.

### Why the win grew (but the verdict doesn't change)

Pre-SPPF, `BuildTree` dominated; the dispatch tax was ~4% of a larger total.
Post-SPPF, `BuildTree` is gone from `recognize`, so the dispatch + allocation
overhead is a larger share of a smaller total. The incremental gains are real.

The verdict is unchanged: this fully collapses `Predict`/`Complete`/`Scan` from
IrSelf dispatch bodies into inline branches in one method. That destroys the
"dispatch table IS the engine" shape that is an explicit project invariant.

**However: the purity-preserving subset of these gains IS available** through:
- F4 (bypassing `IrSeq` snapshot in Complete) — 4–7%
- Scan guard — 5–7%
- Combined F4 + guard — 8–10%

That gets ~55–60% of the purity-destroying rewrite's gain without breaking anything.

### #5 verdict on current engine

**STILL NEGATIVE AS A STANDALONE. Purity-preserving subset (F4 + guard) captures
8–10% with no design risk.** Do not pursue the full collapse.

---

## Priority Ranking and Sequencing

| rank | finding | measured gain | purity | effort |
|------|---------|---------------|--------|--------|
| **1** | **F1 left recursion** (`normalize.py`) | **~2–4× benchmark, O(n²)→O(n)** | Yes | Medium |
| **2** | **Scan guard** (`engine.py:ScanColumn`) | **5–7% recognize** | Yes | Trivial |
| **3** | **F4 snapshot bypass** (`ops.py:Complete`) | **4–7% recognize** | Yes (minor) | Small |
| **4** | **F3 opt-chain redesign** (`normalize.py`) | ~10% recognize (upper bound) | Yes | Large |
| **5** | **F3 simple-? fold** (`normalize.py`) | ~2% recognize | Yes | Small |
| ~~6~~ | ~~F5 predict-skip~~ | ~~−6 to −7% (NEGATIVE)~~ | — | — |
| ~~7~~ | ~~#5 dispatch collapse~~ | ~~14–18% (up from 11%)~~ | **No** | — |

F2 (Leo) remains deferred per the handover.

### Recommended program (after SPPF)

1. **Land F1** (left recursion in `normalize.py` + reducer child-order reversal).
   Everything else is second-order until this is in.

2. **Scan guard** — one-liner, ships immediately or alongside F1; no conflict.

3. **F4** — `Complete.eval` waiting-bucket bypass. Cheap cleanup after F1; primary
   value is if F1 is deferred.

4. **Re-profile after F1** — the opt-chain/? inflation (F3) may be proportionally
   larger post-F1 (completion count drops; predict overhead becomes a bigger share).
   Measure then decide whether the opt-chain redesign is worth it.

5. **F5 and #5 are closed** — do not revisit.

---

## Interaction Matrix with F1

| finding | post-F1 impact |
|---------|---------------|
| Scan guard | Column item count drops; absolute savings shrink proportionally. Per-item ratio stays ~5%. **Worth doing.** |
| F4 (snapshot bypass) | ~80× fewer completions → 80× fewer snapshots → evaporates. **Only do if F1 deferred.** |
| F3 (opt-chain nullable) | Prediction overhead stays; F1 doesn't reduce predict count. **Remains ~10% ceiling.** |
| F5 (predict-skip) | Predict count also drops post-F1; set overhead stays per predict call. Likely still negative. **Closed.** |
| #5 (collapse) | Purity-preserving subset (F4+guard) gets 8–10% anyway. **Closed.** |

---

## Suite Canary

`uv run pytest tests/ -q` — **1126 passed** (ABNF fixpoint green).
No code was modified; all patches are throwaway monkeypatches in isolated scripts.
All benchmarks run on `/home/mika/projects/lexic` (main checkout, `parse_proto_proto` branch).
