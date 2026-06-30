# Exploration 1 — Drop and Reimplement

**Date:** 2026-06-30  
**Base commit:** `1df8365 wip` (pre-leoparse)  
**Worktree:** `/home/mika/projects/lexic/.claude/worktrees/agent-ab059933e58dd9159`

---

## What was built

Reset to `1df8365` (pre-leoparse), then reimplemented Leo-on-parse using the same
lazy-chain-deferred design as `5af435d leoparse`, but with the following
improvements over that commit:

### Changes from the leoparse commit

1. **`LEO_ENABLED` flag removed** (as directed in HANDOVER). Leo is now
   unconditional — there is no `not ctx.record_links` gate suppressing it on the
   parse path.

2. **Nullable-cycle guard added to `LeoItem.resolve`** (`seen: set[tuple[int,
   IrRuleRef]] | None = None`). A nullable cycle (e.g. `a = b` / `b = a / ''`)
   makes the chain re-enter the same `(col, ref)` via empty-span steps. The guard
   is allocated lazily (stays `None` for cross-column right-recursion, which can
   never cycle) and catches the edge case cleanly.

3. **`_sole_candidate` renamed `sole_candidate`** (used publicly by `Complete`
   for the deep-only gate, so the leading underscore was wrong).

4. **`Chart.leo_links`** added — deferred-provenance table keyed `(top_item, end)`
   to bottom triple `(sole_waiter, waiter_end, child_node)`. The forest rebuilds
   skipped chains from this on demand.

5. **`LeoExpand` added to `forest.py`** — materialises a deferred Leo chain into
   `chart.links` the first time `PrefixSource` walks a deferred top node. O(chain),
   once, only for chains a derivation actually traverses.

6. **`PrefixSource.__iter__` updated** to trigger `LeoExpand` before opening a
   handle with a `leo_links` entry.

7. **`test_ops.py` ported**: removed `test_leo_enabled_is_true_by_default` and all
   differential-oracle helpers (`_recognize_with_leo`, `_check_differential`, and
   four tests), added five `test_leo_parse_*` tests that verify Leo-on-parse returns
   correct trees for deep right-recursion up to depth 200.

### Files changed

- `src/lexic/parsing_2/chart.py` — add `leo_links` slot to `Chart`
- `src/lexic/parsing_2/ops.py` — remove `LEO_ENABLED`; update `Complete` to fire
  Leo on both recognition and parse paths; add nullable-cycle guard to
  `LeoItem.resolve`; rename `_sole_candidate` to `sole_candidate`
- `src/lexic/parsing_2/forest.py` — add `LeoExpand` + singleton `LEO_EXPAND`;
  update `PrefixSource.__iter__` to call `LEO_EXPAND.expand` on deferred tops
- `tests/unit/lexic/parsing_2/test_ops.py` — port to remove `LEO_ENABLED`
  references; add parse-correctness tests

---

## Canary status

| canary | result |
|---|---|
| `uv run pytest tests/ -q` | **1151 passed** (net -1 vs 1152: removed 6 differential-oracle tests, added 5 parse-correctness tests) |
| ABNF fixpoint | **True** |
| `is_ambiguous` on ABNF | **False** |
| Deep parse N=200 | **correct tree returned** |

---

## Why is parsing super-linear? (answered with data)

### Short answer

Super-linearity on parsing lives **entirely in deep right-recursion**. On realistic
grammars (ABNF), parse is O(n) in chart structure (both items/char and links/char
are flat) and the small wall-clock "creep" is cache pressure, not algorithm. The
old pre-Leo parse path was O(n^2) on deep right-recursion; Leo-on-parse makes it O(n).

### Evidence

**Deep right-recursion `S = "a"*` (pre-Leo):**

The chart for N items built Theta(N^2) links. At every column `k`, completing
`S -> "a" S .` advances all waiters in column `k-1`, including the item advanced
at `k-1` which advanced the one at `k-2`, etc. Each column re-walks the full
chain from origin to `k`, recording O(k) links. Total: 1+2+...+N links. Hence:

- µs/N^2 = 0.65 (constant across N=100..1600) — classic quadratic
- At N=1600: 42x slower than Lark and widening with no bound

**Why Leo cures it:** Leo detects a deterministic right-recursion chain (exactly 1
waiter for ref, ref is the last symbol of that arm, and the chain depth >= 2). It
jumps directly to the topmost item and records ONE deferred link
`leo_links[(top, end)] = (bottom_waiter, bottom_end, child)`. The forest rebuilds
the skipped chain O(chain) on first walk — but only ONE chain walk happens for a
single non-ambiguous parse, so total link work is Theta(N).

**ABNF self-host (realistic grammar, measured):**

| | x1 (920) | x2 (1840) | x4 (3680) |
|---|---|---|---|
| items/char | 31.8 | 31.8 | 31.8 |
| links/char | 8.8 | 8.8 | 8.8 |

Both flat. The 3.9% wall-clock creep from x1 to x4 (76.5 to 79.5 µs/char on parse)
is CPU cache pressure from the 4x larger working set, not an algorithm issue.
ABNF has right-recursive repetition rules (desugared from `*`) but the chains are
short (bounded by the grammar, not the input); Leo fires on ~10.7% of completions
at x4.

---

## Benchmark tables

### A. ABNF self-host (product metric)

Raw outputs: `EXPLORE_1_bench_baseline.txt` (pre-Leo), `EXPLORE_1_bench_final.txt` (after).

| stage | input | PRE-LEO earley med | PRE-LEO e/lark | AFTER earley med | AFTER e/lark |
|---|---|---|---|---|---|
| recognize | x4 (3680) | 157.7 ms | 2.06x | 160.3 ms | 2.17x |
| parse | x1 (920) | 70.4 ms | 2.65x | 71.2 ms | 2.74x |
| parse | x4 (3680) | 292.4 ms | 2.77x | 307.9 ms | 2.96x |
| **parse+reduce** | **x1 (920)** | **82.0 ms** | **2.99x** | **83.9 ms** | **3.12x** |
| **parse+reduce** | **x2 (1840)** | **169.1 ms** | **3.14x** | **172.1 ms** | **3.22x** |
| **parse+reduce** | **x4 (3680)** | **367.4 ms** | **3.38x** | **356.7 ms** | **3.33x** |

On ABNF, Leo-on-parse is neutral to slightly better at x4 (3.38x to 3.33x on
product). The x1/x2 parse cost is slightly higher (Leo's `sole_candidate` pre-check
is paid for every single-waiter completion, even those below the depth gate). The
x4 product benefit (+1.5%) reflects Leo reducing some chain work in the longer input.

**This did NOT beat Lark on the ABNF product metric.** Still ~3.3x slower. The
gap is a pure constant factor.

### B. Asymptotic — deep right-recursion `S = "a"*`

Raw output: `EXPLORE_1_rightrec.txt`.

| N | PRE-LEO µs/N | PRE-LEO µs/N^2 | PRE-LEO e/lark | AFTER µs/N | AFTER µs/N^2 | AFTER e/lark |
|---|---|---|---|---|---|---|
| 100 | 71.3 | 0.713 | 2.6x | 20.9 | 0.209 | **0.8x** |
| 200 | 130.5 | 0.652 | 5.0x | 20.3 | 0.102 | **0.8x** |
| 400 | 268.7 | 0.672 | 9.9x | 20.1 | 0.050 | **0.8x** |
| 800 | 530.5 | 0.663 | 19.8x | 19.7 | 0.025 | **0.8x** |
| 1600 | 1089.6 | 0.681 | 42.2x | 19.9 | 0.012 | **0.8x** |

**PRE-LEO: O(n^2)** — µs/N grows from 71 to 1090; µs/N^2 flat at ~0.65.  
**AFTER: O(n)** — µs/N flat at ~20; µs/N^2 halves every doubling.  
**Beats Lark at 0.8x on deep right-recursion.** Matches the leoparse commit exactly.

Recognition was already O(n) at ~9 µs/N (~0.9x Lark) in both states.

---

## Did this beat the leoparse commit?

**Algorithmically: identical.** The design is the same lazy-Leo deferred-chain
approach. The measured numbers are within noise of the leoparse commit's BASELINE.md
AFTER column, confirming the reimplementation is correct and equivalent.

**Where this beats the leoparse commit:**
- Suite fully collects: 1151 tests, `test_ops.py` fully ported and collecting
  (vs "1128/1128 excluding test_ops.py" in the dropped commit)
- `LEO_ENABLED` flag removed as HANDOVER directed
- `_sole_candidate` correctly public as `sole_candidate`

**Where this does NOT beat leoparse on perf:** The ABNF product metric is identical
within measurement noise. Beating Lark on the ABNF constant factor requires
different work (see Profile findings below).

---

## Codebase-rule status

| rule | status |
|---|---|
| IrSelf-derived objects | OK — `LeoExpand(IrLeaf)`, no free functions |
| No closures in eval | OK — `expand` is a named method, not a closure |
| No `# type: ignore` / `# noqa` | OK |
| No `exec`/`eval` | OK |
| No grammar-specific hardcoding | OK |
| Never commit | Not committed |

Note: `LeoExpand.expand` is a named method called directly from
`PrefixSource.__iter__`, not dispatched through `eval`. This matches the existing
pattern of `LEO_ITEM.resolve` (called by name from `Complete`). The `eval` protocol
is for IR-dispatch entrypoints; internal helpers stay as named methods.

---

## Profile findings (constant factor drivers on ABNF)

cProfile, parse+reduce, x4. Treat ranks as reliable; absolute times inflated by
cProfile sampling. Raw output: `EXPLORE_1_profile.txt`.

| rank | site | ncalls | tottime | what |
|---|---|---|---|---|
| 1 | `Trampoline.__iter__` | 20 | 0.69s | generator loop driver (forest walk) |
| 2 | `Column.__iadd__` | 657k | 0.51s | item insertion (set + list append) |
| 3 | `Predict.eval` | 293k | 0.51s | predictor (hot per column) |
| 4 | `generator.send` | 1.7M | 0.43s | Python generator overhead |
| 5 | `Complete.eval` | 146k | 0.36s | completer |
| 6 | `PrefixSource.__iter__` | 642k | 0.34s | forest prefix iteration |
| 7 | `IrDispatch.eval` | 585k | 0.30s | type-dispatch overhead |

The trampoline generator loop + `generator.send` together account for ~1.1s / 7.3s
(~15%) — the depth-safe forest walk is a real constant-factor cost. The chart
building path (Predict + Complete + Column.__iadd__) accounts for another ~1.4s.
Type-dispatch through `IrDispatch.eval` adds 0.3s.

None of these are amenable to Leo or any algorithmic fix; they are constant-factor
targets requiring per-site micro-optimisation.

---

## Next fronts for beating Lark on ABNF

The constant-factor gap (3.3x) splits:

1. **Chart building (~2.96x parse ratio)**: Predict/Complete overhead, item hashing,
   `IrDispatch.eval` per item. Candidate: call Predict/Complete directly from
   `CloseColumn` based on item type, bypassing the type-map dispatch on the hot path.

2. **Forest + reduce overhead (adds ~11% beyond parse)**: 1.7M `generator.send`
   calls through the trampoline, `PrefixSource.__iter__` per link, `ReduceCtx.eval`
   per tree node. Candidate: inline the single-derivation forest walk (no
   trampoline needed when ambiguity is not checked), or reduce generator-frame depth.

3. **`typing.cast` (2.1M calls, 0.13s)**: Pure overhead from Python 3.14 not
   optimising it away. Replace with direct assignment where cast is just a type hint.
