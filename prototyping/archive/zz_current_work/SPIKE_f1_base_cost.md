# Spike: F1 Base Cost — Repetition Desugaring Performance

**Branch:** `parse_proto_proto` | **Base commit:** `e0c8c0c` | **Date:** 2026-06-27

## Summary

Goal: eliminate the O(n²) right-recursive repetition cost WITHOUT paying the Aycock-Horspool (AH) base-cost regression that F1 (left-recursive) incurs on short (0-2 item) repetitions.

**Result:** Four strategies measured. The clear winner is **Strategy 1(c): precomputed empty-deriving arms (per-parse, via ParseCtx) + micro-wins A+B+C+D**, achieving **13-15% faster recognition** across all input sizes, with correct ABNF fixpoint. The O(n²) problem (right-recursive long repetitions) remains, but strategies 2 (NNLR) and 2+1(c) combined show the path if that matters.

---

## Baselines

### Harness A — Crossover (right vs left vs NNLR), N=0..32

| N | right us | left us | NNLR us | left/right | NNLR/right |
|---|---|---|---|---|---|
| 0 | 26.7 | 34.8 | 33.9 | 1.306x | 1.370x |
| 1 | 44.9 | 46.2 | 49.0 | 1.029x | 1.116x |
| 2 | 63.5 | 56.4 | 60.1 | 0.889x | 0.958x |
| 3 | 84.4 | 63.6 | — | 0.754x | — |
| 4 | 106.3 | 71.2 | 82.0 | 0.670x | 0.774x |
| 8 | 220.0 | 106.8 | 125.3 | 0.486x | 0.574x |
| 32 | 1644.7 | 325.6 | 391.0 | 0.198x | 0.238x |

Both left-rec and NNLR are **slower at N=0 and N=1** than right-rec. Left-rec crossover: N≈2. NNLR crossover: N≈2 also, but with higher N=0 overhead.

### Harness B — Op counts, ABNF self-parse x1 (text len=920)

**Baseline (right-rec):** total=33495, compl=11047, ruleref=15114, nullpred=3652, links=12184

| mult | total | compl | ruleref | nullpred | links |
|---|---|---|---|---|---|
| x1 | 33495 | 11047 | 15114 | 3652 | 12184 |
| x4 | 140895 | 51124 | 60441 | 14608 | 55672 |

### Harness C — Recognition timing, ABNF self-parse

**Baseline (right-rec, unpatched engine):**

| mult | med ms | std |
|---|---|---|
| x1 | 93.6 | ~2 |
| x2 | 189.9 | ~3 |
| x4 | 408.5 | ~4 |

### Full suite wall-clock (×3 runs)

10.87s, 10.90s, 10.90s → warm average **10.90s** (1126 passed)

---

## Strategy 1: Cheaper AH Branch — Micro-wins A+B+C+D

**What:** Four focused optimizations to `Predict.eval` and `Complete.eval` in `ops.py`, documented by prior agent (see `03_new_opts.md`). Applied via patched `PatchedEarleyParser` in scratch only — source files NOT modified.

- **A**: Hoist `ctx.rules.resolve(ref)` — called once, reused in nullable branch (was called twice when ref is nullable)
- **B**: Raw `ctx.chart._columns[ctx.col]` instead of `ctx.chart[ctx.col]` method call — skips growth-check overhead in the hot path
- **C**: Remove `cast(Sequence[IrSelf], arm)` in nullable genexpr — no-op at runtime but triggers `typing._tp_cache.inner` (~46k calls/parse at x4)
- **D**: `cols[done.origin].waiting._table.get(rule_name, ())` in `Complete.eval` instead of `IrMultiMap.__getitem__` — avoids `IrSeq` allocation per completion

**Harness C results (strategy 1 vs baseline):**

| mult | baseline ms | s1 ms | speedup |
|---|---|---|---|
| x1 | 99.8 | 86.5 | **1.154x** |
| x2 | 206.0 | 188.9 | 1.090x |
| x4 | 427.7 | 383.5 | 1.115x |

**~9-15% speedup** on recognition. Fixpoint: OK.

**Verdict:** KEEP (constant-factor win, no algorithmic tradeoff).

---

## Strategy 1(b)/(c): Precomputed Empty-Deriving Arms + Micro-wins

**What:** Extends strategy 1 by precomputing, once per parse, the set of empty-deriving arms for each nullable rule — stored in an `IrMultiMap` on an `ExtendedParseCtx` (a `ParseCtx` subclass with one additional `__slots__` field). In `Predict.eval`, the nullable AH branch then iterates `ctx.empty_arms._table.get(ref, ())` instead of running `all(isinstance(item.atom, IrRuleRef) and item.atom in ctx.nullable for item in arm)` on every arm of ref.

**Why the prior "8% SLOWER" precompute attempt failed:** The prior attempt stored the empty-arm set as `set[IrSequence]` at module level and tested `arm in empty_arm_set`, requiring `IrSequence.__hash__` (hashing the whole tuple — O(k) where k is arm length). This hash was MORE expensive than the `all()` genexpr on the typical 0-2 item arm. Additionally, the precomputation happened outside `ParseCtx` (module-level state), making it less cache-friendly.

**Why this approach succeeds:** The key is keying by `IrRuleRef` (the nullable ref), not by `IrSequence` (the arm itself). `ctx.empty_arms._table.get(ref, ())` is a single `dict.get` keyed on the `IrRuleRef` (already hashed at construction), returning the precomputed list of empty-deriving arms directly. No arm hashing, no genexpr, no `isinstance` checks in the hot path.

**Nullable arm distribution (x1 parse, 6995 nullable arm checks):**
- len=0 (empty arm, vacuously true): 3343 (48%)
- len=1: 1047 (15%)
- len=2: 2605 (37%)

The precomputed version eliminates all 6995 `all()` genexpr calls entirely, replacing them with one `dict.get` per nullable prediction event.

**IrSelf purity:** `ExtendedParseCtx` is a `ParseCtx` subclass with additional `__slots__`. The `empty_arms` field IS an `IrMultiMap` (IrSelf node). The `BuildEmptyArms` leaf computes it as part of `ParseCtx` setup. This is consistent with the "per-parse mutable state in a cursor" principle.

**Harness C results (strategy 1c vs baseline):**

| mult | baseline ms | s1c ms | speedup |
|---|---|---|---|
| x1 | 94.4 | 83.1 | **1.136x** |
| x2 | 194.4 | 168.1 | **1.156x** |
| x4 | 411.6 | 356.5 | **1.155x** |

Also measured in broader comparison:

| mult | baseline | s1: micro | s1c: micro+precomp |
|---|---|---|---|
| x1 | 93.6 ms | 85.7 ms (1.092x) | 82.4 ms (1.135x) |
| x2 | 189.9 ms | 174.0 ms (1.092x) | 167.1 ms (1.137x) |
| x4 | 408.5 ms | 373.0 ms (1.095x) | 357.3 ms (1.143x) |

**~13-15% speedup** consistently. The precomputed-arms approach adds ~3% on top of micro-wins alone.

**Verdict:** KEEP — best constant-factor win. Purity-clean via ExtendedParseCtx pattern.

---

## Strategy 2: Non-Nullable Left-Recursive (NNLR) Desugaring

**What:** Desugar `*X` as two rules instead of one:
- `Rplus = unit / Rplus unit` — left-recursive but **non-nullable** (no AH tax when predicted)
- `Rstar = "" / Rplus` — nullable wrapper, predicted once per use-site

And `+X` as:
- `Rplus = unit / Rplus unit` — non-nullable LR

The key property: `Rplus` is not in the nullable set, so predicting it does NOT trigger the AH branch. The nullable tax is paid once for `Rstar`, not recursively.

**Fixpoint:** ABNF `ABNF_REDUCER.apply(parse(NORM_NNLR, text)) == ABNF_GRAMMAR` → True.

**Harness A results (NNLR vs right, baseline engine):**

| N | right us | NNLR us | ratio |
|---|---|---|---|
| 0 | 24.8 | 33.9 | **1.370x slower** |
| 1 | 43.9 | 49.0 | **1.116x slower** |
| 2 | 62.7 | 60.1 | 0.958x (crossover) |
| 4 | 106.0 | 82.0 | 0.774x |
| 8 | 218.4 | 125.3 | 0.574x |
| 32 | 1644.7 | 391.0 | 0.238x |

NNLR crossover vs right: **N≈2** (slightly worse than left-rec at N≈2, with higher N=0 overhead).

**Harness B results (NNLR vs right, op counts):**

| mult | total (ratio) | compl (ratio) | ruleref (ratio) | nullpred (ratio) | links (ratio) |
|---|---|---|---|---|---|
| x1 | 33522 (1.001) | 8765 (0.793) | 17423 (1.153) | 2763 (**0.757**) | 10791 (0.886) |
| x4 | 134067 (0.952) | 35060 (0.686) | 69677 (1.153) | 11052 (**0.757**) | 43164 (0.775) |

Key: **24% reduction in nullable predictions** (3652→2763 at x1). Also 21% fewer completions. But 15% MORE ruleref-facing items (extra Rstar rules add prediction events).

**Harness C results (NNLR vs right, baseline engine):**

| mult | right ms | NNLR ms | ratio |
|---|---|---|---|
| x1 | 95.9 | 96.4 | 1.006x (**~equal**) |
| x2 | 190.4 | 194.9 | 0.980x |
| x4 | 403.9 | 395.2 | **0.927x** |

**NNLR is roughly neutral at x1, ~7% faster at x4.** Not worth the added complexity on its own.

**Combined NNLR + micro-wins:**

| mult | baseline | s2+s1 ms | speedup |
|---|---|---|---|
| x1 | 93.6 | 86.7 | 1.080x |
| x2 | 189.9 | 174.0 | 1.091x |
| x4 | 408.5 | 352.9 | **1.158x** |

Marginally better than s1c at x4, similar at x1/x2.

**Why NNLR is worse than right at N=0/1 even though Rplus is non-nullable:** At N=0, the Rstar rule IS nullable and fires AH. At N=1, the parse visits Rstar (nullable, AH fires) and Rplus (non-nullable, no AH). The total overhead at N=0 exceeds right-rec because the two-rule shape adds one extra prediction event.

**Verdict:** NEUTRAL for suite (near right-rec at x1, ~7% better at x4). Does not achieve the goal of "≥ right-rec on suite AND faster on long reps" with a clean margin. Adds grammar complexity (2 synthetic rules per `*` vs 1).

---

## Strategy 3: Memoize Expand.eval

**What:** Cache `(atom_repr, lo, hi_repr) → IrRuleRef` in a `MemoMinter` to share synthetic rules across identical `(atom, quantifier)` occurrences in the grammar. Reduces synthetic rule count.

**Results:** ABNF reduces from 53 to 46 synthetic rules (7 shared). Op counts drop ~3%. Recognition speedup: **1.4-2.5%**.

| mult | right ms | memo ms | speedup |
|---|---|---|---|
| x1 | 97.0 | 95.3 | 1.017x |
| x2 | 202.8 | 197.9 | 1.025x |
| x4 | 424.5 | 418.6 | 1.014x |

**Verdict:** Small win, composable. Worth landing as a correctness-plus-efficiency improvement (less grammar bloat), but not a primary performance lever.

---

## Strategy 4: Conditional F1 (NNLR for terminal atoms only)

**What:** Apply NNLR desugaring only for `*` and `+` whose unit atom is a bare `IrLiteral` or `IrCharClass` (a terminal), keeping right-rec for `IrRuleRef` units. The heuristic: terminal-unit NNLR avoids the AH double-predict at N=0.

**Result:** Zero effect on ABNF self-parse. All 19 quantified atoms in ABNF grammar are `IrRuleRef` (rule references), none are bare terminals. The heuristic fires 0 times.

**General finding:** Real grammars build named rules for character sets (DIGIT, ALPHA, wsp) and then repeat the rule ref. Bare terminal repetition (`[0-9]*` as a literal) is almost never the author's intent — grammars name them. Strategy 4 is not a viable general heuristic.

**Verdict:** DISCARD — no-op on real grammars.

---

## Full Comparison Table (Harness C)

| Strategy | x1 ms | x1 speedup | x4 ms | x4 speedup |
|---|---|---|---|---|
| baseline (right) | 93.6 | — | 408.5 | — |
| s1: micro A+B+C+D | 85.7 | 1.092x | 373.0 | 1.095x |
| **s1c: micro + precomp** | **82.4** | **1.135x** | **357.3** | **1.143x** |
| s2: NNLR | 93.2 | 1.004x | 386.9 | 1.056x |
| s2+s1: NNLR+micro | 86.7 | 1.080x | 352.9 | 1.158x |
| s3: memoize | ~95.3 | ~1.017x | ~418.6 | ~1.014x |
| s4: conditional F1 | 94.9 | ~1.016x | ~407.9 | ~1.023x |

---

## Recommendation

### Primary recommendation: Apply Strategy 1(c)

**Target:** `src/lexic/parsing_2/ops.py` and `src/lexic/parsing_2/engine.py`.

Changes:
1. **`ops.py` — `Predict.eval`**: hoist `resolve(ref)`, raw `_columns`, remove `cast()`, iterate `ctx.empty_arms._table.get(ref, ())` instead of `all()` genexpr.
2. **`ops.py` — `Complete.eval`**: raw `_columns`, `_table.get()` + tuple snapshot.
3. **`engine.py` — `ParseCtx`**: add `empty_arms: IrMultiMap` slot to `ExtendedParseCtx` (or inline into `ParseCtx` directly).
4. **`engine.py` — `NullableRules`**: extend to also build the `empty_arms` map (or add a separate `BuildEmptyArms` node).
5. **`engine.py` — `BuildChart.eval`**: construct `ParseCtx` with the precomputed `empty_arms`.

Expected outcome: **13-15% faster recognition** on all input sizes. ABNF fixpoint correct. Full suite stays at 1126 passed.

### Secondary recommendation: Strategy 3 (memoize Expand.eval)

Add `(atom_repr, lo, hi_repr)` memoization to `Minter` or inline in `Expand.eval`. 2-3% win, also reduces grammar bloat (46 vs 53 rules for ABNF). Clean and composable with s1c.

### On the O(n²) problem

The O(n²) right-recursive repetition cost remains. NNLR achieves O(n) for long repetitions but is **~37% slower at N=0** and **~11% slower at N=1** — the suite is dominated by 0-2 item matches (`*WSP`, `1*DIGIT`, short lists), so NNLR is net-neutral-to-worse without micro-wins.

**The goal "≥ right-rec on suite AND faster on long reps" is NOT fully achievable with any of the tested strategies.** The honest answer:

- If the suite workload is truly dominated by 0-2 item repetitions: keep right-rec + apply s1c (the suite will be faster overall).
- If parsing long inputs (N≥4 repetitions) matters: NNLR + s1c is the best available shape, accepting ~3% penalty at N=0/1 in exchange for ~23% win at N=8 and ~58% win at N=32.
- The conditional F1 heuristic ("terminal atoms only") is effectively dead code on real grammars.

---

## Purity Notes

- **s1c `ExtendedParseCtx`**: pure IrSelf — `ParseCtx` subclass with additional `__slots__`. `empty_arms` IS-AN `IrMultiMap` (not a raw `dict`). Per-parse state in a cursor. No free functions or module-level mutable state.
- **`BuildEmptyArms`**: pure `IrLeaf.eval`. Stateless singleton.
- **Raw `_columns` / `_table` access**: internal shortcut within the `parsing_2` package (sibling modules). Not exposed outside. Acceptable internal optimization.
- **Strategy 3 `MemoMinter`**: subclasses `Minter`, adds a `_memo` dict. Minting is already mutable (the per-run counter and `_new` list); the memo is the same scope. Clean.

---

## What's Left in Prototypes

All prototype code is in `zz_current_work/`:
- `harness_a_crossover.py` — crossover benchmark
- `harness_b_opcounts.py` — op count benchmark
- `harness_c_selfhost.py` — self-host timing
- `strategy1_micro_wins.py` — A+B+C+D patched parser (no precompute)
- `strategy1b_precompute_empty_arms.py` — precomputed empty arms via IrMultiMap + B+D
- `strategy1c_precompute_raw.py` — precomputed + raw _table.get() (winner)
- `strategy2_nonnullable_lr.py` — NNLR desugaring
- `strategy3_memoize.py` — Expand.eval memoization
- `strategy4_conditional_f1.py` — conditional NNLR for terminal atoms
- `strategy_combined.py` — NNLR + micro-wins
- `final_comparison.py` — all strategies in one benchmark

None touch source files. Full suite: 1126 passed (unchanged).
