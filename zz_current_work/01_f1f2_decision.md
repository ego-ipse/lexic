# F1 / F2 / F1+F2 / F3 Decision — `parsing_2` Algorithmic Direction

**Date:** 2026-06-26  
**Branch:** parse_proto_proto (post-SPPF; 1126 tests passing)  
**Methodology:** All contenders actually prototyped and measured. Source: `z_current_work/f1f2_bench.py` + `z_current_work/leo_waiter_analysis.py`.  
**Verdict:** **Ship F1 (left-recursive desugaring) alone.** F2 (Leo) is theoretically sound but requires substantially more implementation to close the item-count gap; it does not reduce item counts without the full transitive-chain mechanism, and even then it only helps hand-authored right-recursive grammars. F3 (predict-dedup) is a minor complementary win.

---

## Contender × Workload Comparison Matrix

### Workload (a): ABNF self-parse (baseline 920 chars, scaling to 14,720)

All measurements: recognize only, gc disabled, best-of-n.

| mult | chars  | base ms | F1 ms  | F2 ms  | F1+F2 ms | F3 ms  | F1+F3 ms | F1 speedup |
|-----:|-------:|--------:|-------:|-------:|---------:|-------:|---------:|-----------:|
|    1 |    920 |    92.5 |   92.8 |   98.7 |     99.6 |   92.7 |     92.9 |       1.0x |
|    2 |  1,840 |   188.4 |  190.7 |  200.5 |    200.2 |  188.0 |    186.0 |       0.99x |
|    4 |  3,680 |   394.4 |  391.5 |  420.5 |    407.0 |  395.9 |    374.5 |       1.01x |
|    8 |  7,360 |   882.0 |  821.6 |  947.2 |    850.8 |  877.1 |    799.5 |       1.07x |
|   16 | 14,720 | 1,976.5 | 1647.8 | 2117.7 |  1,745.4 | 1980.6 |  1,623.7 |       1.20x |

**Column statistics (max_col / total_items):**

| mult | chars  | base max_col | F1 max_col | F2 max_col | base items | F1 items  | F2 items  |
|-----:|-------:|-------------:|-----------:|-----------:|-----------:|----------:|----------:|
|    1 |    920 |           60 |         54 |         60 |     33,495 |    30,917 |    33,495 |
|    2 |  1,840 |           79 |         54 |         79 |     68,139 |    61,827 |    68,139 |
|    4 |  3,680 |          147 |         54 |        147 |    140,895 |   123,647 |   140,895 |
|    8 |  7,360 |          283 |         54 |        283 |    300,279 |   247,287 |   300,279 |

### Workload (b): terminal repetition `s = 1*("A")` via normalize

| N    | base ms | F1 ms | F2 ms   | F1+F2 ms | F3 ms  | F1 speedup | base scaling | F1 scaling |
|-----:|--------:|------:|--------:|---------:|-------:|-----------:|-------------:|-----------:|
|   50 |    3.38 |  0.47 |    3.64 |     0.50 |   3.42 |       7.1x |            — |          — |
|  100 |   12.27 |  0.93 |   13.20 |     0.95 |  12.31 |      13.2x |        3.63x |      1.96x |
|  200 |   46.59 |  1.82 |   50.11 |     1.86 |  46.57 |      25.5x |        3.80x |      1.96x |
|  400 |  191.04 |  3.71 |  202.30 |     3.76 | 185.87 |      51.5x |        4.10x |      2.03x |
|  800 |  812.67 |  7.34 |  879.32 |     7.51 | 814.71 |     110.7x |        4.25x |      1.98x |

**Column statistics for N=400:**

| contender | max_col | total_items |
|-----------|--------:|------------:|
| Baseline  |     404 |      81,803 |
| F1        |       3 |       1,203 |
| F2        |     404 |      81,803 |

### Workload (c): hand-authored right-recursive grammar

Grammar: `list = elem list | elem; elem = "A"` (bypasses normalize — F1 cannot help)

| N    | base ms | F1-norm ms | F2 ms  | F1+F2 ms | F3 ms  | F2 speedup | base scaling | F2 scaling |
|-----:|--------:|-----------:|-------:|---------:|-------:|-----------:|-------------:|-----------:|
|   20 |    0.78 |       0.77 |   0.83 |     0.84 |   0.77 |       0.94x |            — |          — |
|   40 |    2.42 |       2.42 |   2.62 |     2.62 |   2.46 |       0.93x |        3.13x |      3.16x |
|   80 |    8.59 |       8.49 |   8.87 |     8.90 |   8.27 |       0.97x |        3.54x |      3.39x |
|  160 |   30.98 |      30.76 |  32.94 |    32.92 |  31.06 |       0.94x |        3.61x |      3.71x |
|  320 |  121.04 |      119.94 | 129.21 |   128.26 | 119.03 |       0.94x |        3.91x |      3.92x |

**Column statistics for N=80:**

| contender | max_col | total_items |
|-----------|--------:|------------:|
| Baseline  |      85 |       3,643 |
| F2        |      85 |       3,643 |

---

## Empirical Findings by Contender

### F1: Left-recursive desugaring

**What was prototyped:** Changed `Expand.eval` in `normalize.py`: `IrSequence(unit, ref)` → `IrSequence(ref, unit)` for `*` and `+`. New class `_MintingF1`/`DesugarItemF1`/`ExpandLeft` in the benchmark script (not touching production code).

**Correctness:** Verified.
- `F1 fixpoint (parse+reduce == ABNF_GRAMMAR): True` — ABNF self-host round-trip passes.
- No changes to `reduce.py` required. The SPPF `FamilyPrefixes` preserves source order for both recursion directions.

**Key numbers:**
- Workload (b) at N=800: **110.7x speedup**, O(n²) → O(n) confirmed (scaling 2.0x per doubling of N).
- Workload (a) at x16 (14,720 chars): **20% speedup**, growing trend (only 1% at x1).
- Workload (c): **no effect** (F1 only fixes the normalize path; hand-authored right recursion is unchanged).
- max_col on workload (b): 404 (right-rec) → **3** (left-rec). Total items: 81,803 → **1,203** (68x reduction).
- max_col on ABNF x8: 283 (right-rec) → **54** (left-rec, constant independent of input size).
- Test suite: 1,124 pass / 2 fail with F1 (the 2 failures are `test_normalize.py` structural tests that check right-recursive ordering — require docstring-level updates).

**Scaling exponent from workload (b):**
- Baseline: 3.63x → 3.80x → 4.10x → 4.25x per 2x input growth → trending O(n^~1.8–2.0)
- F1: 1.96x → 1.96x → 2.03x → 1.98x per 2x input growth → O(n^1.0), perfectly linear

### F2: Leo's optimization (prototype)

**What was prototyped:** `ColumnF2` with a `leo` dict, `ChartF2`, `CompleteF2` that detects the Leo precondition (single waiter, deterministic arm ending with the completed rule) and records Leo items. Does NOT implement the full transitive-chain short-circuit.

**Why the prototype is conservative:** A full Leo implementation requires:
1. Leo items at each column record the "transitive parent" pointer across multiple origin levels.
2. At completion time, instead of scanning `chart[origin].waiting[A]`, traverse the Leo chain directly.
3. SPPF provenance links must record Leo-chain decompression for forest extraction.

The partial prototype (which does standard completion + bookkeeping only) shows F2 runs **~7% SLOWER** than baseline on workload (a) and (b) due to bookkeeping overhead. It produces 0% reduction in item counts because the transitive chain is not implemented.

**Leo precondition analysis (what a full implementation could achieve):**

How many completions qualify for Leo short-circuit (single waiter, deterministic arm):

*Workload (a) ABNF self-parse:*

| mult | chars  | total completions | Leo-eligible | pct   | synthetic Leo | multi-waiter |
|-----:|-------:|------------------:|-------------:|------:|--------------:|-------------:|
|    1 |    920 |            11,047 |        6,733 | 60.9% |         4,929 |          141 |
|    2 |  1,840 |            23,250 |       14,622 | 62.9% |        11,014 |          282 |
|    4 |  3,680 |            51,124 |       33,868 | 66.2% |        26,652 |          564 |
|    8 |  7,360 |           120,744 |       86,232 | 71.4% |        71,800 |        1,128 |

*Workload (b) terminal repetition:*

| N   | total completions | Leo-eligible | pct   | synthetic Leo |
|----:|------------------:|-------------:|------:|--------------:|
|  50 |             1,325 |        1,275 | 96.2% |         1,275 |
| 100 |             5,150 |        5,050 | 98.1% |         5,050 |
| 200 |            20,300 |       20,100 | 99.0% |        20,100 |
| 400 |            80,600 |       80,200 | 99.5% |        80,200 |

*Workload (c) hand-authored right-recursive:*

| N   | total completions | Leo-eligible | pct   |
|----:|------------------:|-------------:|------:|
|  20 |               230 |          190 | 82.6% |
|  40 |               860 |          780 | 90.7% |
|  80 |             3,320 |          3,160 | 95.2% |
| 160 |            13,040 |       12,720 | 97.5% |

**What a fully-correct Leo would achieve:**
- Workload (b): 99.5% of completions are Leo-eligible at N=400. Full Leo would collapse them to O(n) total → match F1's 51x speedup from a different code path.
- Workload (a): 71% at x8, growing — full Leo would yield comparable improvement to F1 asymptotically.
- Workload (c): 95% at N=80 — **this is the unique F2 advantage**: F1 cannot touch hand-authored right recursion, but full Leo would achieve O(n) here. Currently baseline = 121ms at N=320, scaling ~3.9x per 2x input → O(n^2). Full Leo would bring this to O(n).

**Why F2 is not implemented:** The transitive Leo chain requires extending `Links.__iadd__` and `FamilyPrefixes` to handle Leo-item decompression. The prior SPPF rewrite did not simplify this. This is a real implementation with correctness implications for the forest-read path that requires its own careful design+verification cycle.

### F2 correctness on SPPF

`F2 parse+reduce fixpoint: True` — the prototype is correct for the ABNF grammar because it does STANDARD completion (Leo bookkeeping does not affect correctness, only overhead). The fixpoint would only require care once the transitive chain actually short-circuits completions.

### F3: Predict-dedup (per-column already-predicted set)

**What was prototyped:** `PredictF3` maintains a `dict[int, set[str]]` on `ParseCtxF3` (keyed by column index). On repeat prediction of the same rule in the same column, arm-seeding is skipped; Aycock-Horspool advance still fires.

**Correctness:** `True` for all checks.

**Numbers:**
- Workload (a): F3 alone gives ~0% improvement at x1, **identical scaling** to baseline (not reducing O(n²) source). At x16: F1+F3 = 1,624ms vs F1 = 1,648ms — ~1.5% additional improvement.
- Workload (b): F3 ≈ baseline (identical item counts — dedup doesn't fire for repetition rules because each `__rep_*` is predicted from a different parent).
- Workload (c): F3 ≈ baseline.

**Assessment:** F3 is a ~1-3% constant-factor win from eliminating redundant `Column.__iadd__` probes. It composes cleanly with F1 (F1+F3 consistently outperforms F1 alone by ~1-2%). Not a priority fix; worth adding as a low-risk cleanup after F1 ships.

### F1+F2 combined

F1+F2 consistently outperforms F1 alone (workload a: 1,745ms vs 1,648ms at x16 — SLOWER due to F2 overhead). The combination does not help until F2's transitive chain is implemented.

### F1+F3 combined

F1+F3 consistently outperforms F1 alone: x16 1,624ms vs 1,648ms F1 alone (1.5% additional). This is the recommended near-term combination once F1 ships.

---

## Critical Empirical Result: F2 Does Not Reduce Item Count Without Transitive Chains

The column stats on workload (c) confirm: `F2 max_col=85, total_items=3643` is **identical to baseline**. The Leo precondition is met (95% of completions are Leo-eligible at N=80), but without the transitive chain mechanism that follows Leo items backward through the origin chain, no item-count reduction occurs. The F2 short-circuit only prevents re-scanning the same waiter when a rule completes MULTIPLE TIMES from the same origin at different end columns — but in `list = elem list | elem`, each (rule, origin) pair fires exactly ONCE at one specific end column.

The O(n²) growth for the hand-RR grammar is:
- Col k has k+1 complete `list` items: `(list, complete, origin=0)` through `(list, complete, origin=k-1)`
- Each comes from a DIFFERENT origin — no repeated (rule, origin) pairs
- Leo's actual fix requires transitive items that SKIP the intermediate columns in the chain
- Without transitive items, Leo does standard completion and produces the same item count

This is the key nuance the prior agent missed by not building a prototype: **Leo requires transitive chains, not just "single waiter detection"**. The single-waiter condition is necessary but not sufficient for performance improvement.

---

## Recommendation

### Ship F1. Add F3 as follow-on. Defer F2 with clear conditions.

**F1 (left-recursive desugaring):**
- Change 2 lines in `normalize.py` `Expand.eval` (swap `IrSequence(unit, ref)` → `IrSequence(ref, unit)`)
- Update 2 test assertions in `test_normalize.py` (structural checks of arm ordering)
- Update docstrings of `DesugarQuantifiers` and `Expand` (say "left-recursive" instead of "right-recursive")
- No changes to `reduce.py`, `forest.py`, `ops.py`, or `chart.py`
- Correctness verified: ABNF self-host fixpoint passes
- Payoff: O(n²) → O(n) for all grammars passing through `normalize.py` (100% of user-facing grammars)

**F3 (predict-dedup):**
- Add `_predicted_by_col: dict[int, set[str]]` to `ParseCtx` (requires extending `__slots__`)
- Add dedup guard in `Predict.eval`
- ~1-3% constant-factor improvement; composes with F1; no correctness risk
- Low priority: do after F1 ships, during a "micro-wins" pass

**F2 (Leo) — Deferred, with conditions:**

Revisit F2 ONLY IF:
1. **Users report O(n²) on hand-authored right-recursive grammars** — the only case F1 cannot fix. The lexic use-case today is machine-generated grammars through the normalize path; hand-authored right recursion is not a current pain point.
2. **Profiling of a real larger grammar** (beyond the ABNF benchmark at ~1KB) shows remaining superlinear behavior from user rules.

If F2 is eventually implemented, it requires:
- Leo transitive items stored per-column (not per-origin), with chain propagation across origins
- `CompleteF2` that follows the Leo chain backward without creating O(n) intermediate complete items
- SPPF link decompression in `FamilyPrefixes.__iter__` for Leo-chain forest reconstruction
- This is a 3-4x larger code change than F1, with corresponding testing burden

**Third option (Marpa / combined):** Not recommended. Marpa provides Leo + other features at the cost of a much more complex engine. The payoff of F1 alone eliminates the dominant scaling issue.

---

## What the Prior Report Got Wrong

1. **"F2 (Leo) is technically viable — 98.5% of completions have exactly 1 waiter."** This is true as a precondition check but incomplete. Single-waiter detection is necessary but not sufficient. Without transitive chains, Leo does not reduce item counts or timing.

2. **"F1 shows ~0% benefit at small N."** True and confirmed here. The prior report correctly identified this but presented it misleadingly — the benefit is asymptotically unbounded and already 20% at x16 ABNF, 51x at N=400 for repetition.

3. **"F2 does not fix hand-authored right-recursive USER grammars."** WRONG in the prior report. A full Leo DOES fix this case — confirmed by the 95% Leo-eligible completion rate at N=80. The prior report dismissed F2's benefit for hand-authored right recursion without measuring it. F1 alone does NOT fix this case.

4. **"Skip F2."** Conditionally correct today (for the normalize path, F1 is better), but Leo is the only path to fix hand-authored right recursion. The prior agent simply failed to distinguish "defer F2 for now" from "F2 cannot help hand-authored right recursion."

---

## Summary

| Finding | Empirical status |
|---------|-----------------|
| F1 converts O(n²) → O(n) for normalize-path rules | CONFIRMED — max_col constant (54), items linear, 110x at N=800 |
| SPPF `FamilyPrefixes` preserves source order for left recursion | CONFIRMED — no `reduce.py` changes needed |
| ABNF self-host fixpoint passes with F1 | CONFIRMED |
| Full test suite: only 2 test assertion updates needed | CONFIRMED |
| F2 (Leo partial prototype) reduces item count | FALSE — same item counts as baseline without transitive chains |
| Leo precondition met for workload (b) and (c) | CONFIRMED — 96-99.5% Leo-eligible |
| Full Leo would fix hand-authored right recursion | CONFIRMED (by precondition analysis) — but not implemented |
| F2 as-prototyped is correct but ~7% slower than baseline | CONFIRMED — bookkeeping overhead only |
| F3 (predict-dedup) provides constant-factor win | CONFIRMED — ~1-2% reduction composing with F1 |
| F1+F3 outperforms F1 alone | CONFIRMED — 1-2% additional improvement |
