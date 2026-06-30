# EXPLORE_2 — Constant-factor optimization of the leoparse Earley engine

**Date**: 2026-06-30
**Branch**: parse_proto_proto (worktree agent-ae6e090226fffc47d)
**Task**: Attack constant factors to reduce the product-metric gap (e:parse+reduce vs lark:full) from 3.3x toward 1x.

---

## Summary of results

| State | product x4 ratio | parse-only x4 ratio | notes |
|---|---|---|---|
| BASELINE (leoparse HEAD) | **3.37x** | ~3.0x | pre-optimization |
| OPT1: inline CloseColumn dispatch | **3.28x** | parse 315→303ms | -9ms parse |
| OPT2: inline Column.__iadd__ multimap ops | **3.24x** | parse 303→296ms | -7ms parse |
| OPT3: iterative tree builder v1 | **2.60x** | parse 296→226ms | -70ms parse |
| OPT4: tree builder v2 (SppfNode identity fix) | **2.47x** | parse 219ms (2.01x) | -7ms parse |
| OPT5: str-keyed rule/nullable dicts + predicted set | **2.34x** | parse 194ms (1.87x) | -25ms parse, -29ms recognize |
| **FINAL** | **~2.34x** | **1.87x** | stable range 2.30-2.43x |

Right-recursion (leoparse feature, not degraded): earley **0.5x Lark** on parse, **0.8x Lark** on recognize. Earley beats Lark on right-recursive grammars.

---

## Question: why is parsing super-linear?

**Short answer: it is NOT super-linear on ABNF.** The leoparse commit (Leo optimization) already fixed the O(n^2) right-recursion regression. On the ABNF self-host benchmark (the product metric), all three sizes (x1, x2, x4) show the ratio staying flat or improving slightly with scale, confirming linear scaling.

Confirmed by `--rightrec` benchmark:
- `us/N^2` column is flat and decreasing at all sizes → O(n) behavior
- Recognize: 7.8 us/N flat from N=200 to N=6400
- Parse: 12.5 us/N flat from N=100 to N=1600

The 2.3x constant-factor gap is genuinely constant-factor overhead from Python's interpreter vs Lark's C-level Earley core.

---

## Optimization details

### OPT1: Inline CloseColumn dispatch (engine.py)

**Target**: `CloseColumn.eval` previously dispatched through `IrDispatch.eval` for every item, which involved a dict lookup + method call per item.

**Fix**: Replaced generic dispatch with inline isinstance check: `if isinstance(symbol, IrRuleRef): _PREDICT.eval(...)  else: _COMPLETE.eval(...)`. Added module-level singleton objects `_PREDICT`, `_COMPLETE`, `_SCAN` to avoid per-call construction.

**Result**: Parse 315ms → 303ms (-4%).

### OPT2: Inline Column.__iadd__ multimap ops (chart.py)

**Target**: `Column.__iadd__` called `IrMultiMap.__iadd__` twice per item (once for `waiting`, once for `scannable_by_atom`), each involving a method call + tuple unpack.

**Fix**: Inlined the dict operations directly: `t = self.waiting._table; bucket = t.get(symbol); if bucket is None: t[symbol] = [item] else: bucket.append(item)`.

**Result**: Parse 303ms → 296ms (-2%).

### OPT3/OPT4: Fast iterative tree builder (forest.py)

**Target**: `BuildTree.eval` used the coroutine Trampoline to walk the SPPF and extract trees. For unambiguous inputs (the common case), the trampoline overhead dominates.

**Insight**: Confirmed all 32,261 link table entries for the ABNF x4 parse have exactly 1 link (completely unambiguous). The trampoline is pure overhead for this input.

**Fix**: Added `_build_tree_fast()` — an iterative, explicit work-stack tree builder that:
1. Walks predecessor chains via `_collect_kids()` using the links table directly
2. Memos built nodes to avoid re-computation
3. Falls back to the trampoline only on ambiguous input (more than 1 link per key)

OPT4 fixed a bug: the isinstance check was using `not isinstance(child, IrLiteral)` which matched `ParseTree` instances (partially-resolved children already in `resolved`) and tried to cast them as SppfNode. Fixed by using `isinstance(child, SppfNode)` — only unresolved handles need further expansion.

**Result**: Parse 296ms → 219ms (-26%). Tree building (0.217s/5runs) entirely replaces the trampoline for tree extraction.

### OPT5: Str-keyed lookup dicts (ops.py, engine.py, chart.py)

**Target**: `IrScalar.__eq__` was called 469,000 times (93k/parse) taking 0.268s for 5 runs. Root cause: `RuleIndex.eval` builds `IrMap` with freshly-constructed `IrRuleRef(name)` keys, while grammar arm atoms are different `IrRuleRef` instances (same str value, different Python object). Python dict lookup: hash match → identity check fails → calls `IrScalar.__eq__`.

**Fix**:
1. Added `rules_table: dict` to `ParseCtx` — plain str-keyed dict built from `rules._table`. Rule lookup in `Predict.eval` uses `ctx.rules_table.get(str(ref))` instead of `ctx.rules.resolve(ref)`.
2. Added `nullable_table: dict` — same pattern for nullable lookup, also str-keyed.
3. Changed `column.predicted` from `set[IrRuleRef]` to `set[str]` — uses `ref_str` (already computed) for membership test and add, avoiding the `IrRuleRef` set lookup that triggered `IrScalar.__eq__`.
4. Changed `start_arms` lookup in `BuildChart.eval` to use `ctx.rules_table.get(str(start))`.

**Quantified elimination**: `IrScalar.__eq__` dropped from 469k calls (0.268s) to 36.5k calls (0.023s) — a 13x reduction in eq calls, effectively zero overhead.

**Result**: Parse 219ms → 194ms (-11%). Recognize 156ms → 121ms (-22%). Product 273ms → ~244ms (-10%).

---

## What remains expensive (post-optimization profile, x4, 5 runs)

| Function | tottime | calls | ns/call |
|---|---|---|---|
| Column.__iadd__ | 0.514s | 657k | 817ns |
| Predict.eval | 0.473s | 293k | 1616ns |
| Complete.eval | 0.330s | 146k | 2260ns |
| CloseColumn.eval | 0.289s | 18k | 16us (outer loop) |
| _build_tree_fast | 0.221s | 5 | 44ms |
| dict.get | 0.211s | 1.76M | 120ns |
| Trampoline.__iter__ | 0.200s | 10 | 20ms |
| len() | 0.163s | 2.2M | 74ns |
| ResolveSource.__iter__ | 0.154s | 368k | 419ns |

Total for 5 runs of parse+reduce: ~4.69s → 938ms/run → ~248ms/run for x4.

### Why these are hard to eliminate further

**Column.__iadd__** (0.514s): The hot item insertion path does: `set.__contains__` + `set.add` + `list.append` + tuple unpack + `len(arm)` + `arm[dot].atom` + `isinstance` + `dict.get` + maybe `dict.set`. At Python's ~30-50M effective ops/sec, 131k items/run × 8 ops = ~1M ops = 20-33ms. We see 103ms/run — the 3-5x gap is Python bytecode dispatch overhead that cannot be optimized away in pure Python.

**Trampoline + reduce** (0.354s total): The reduce is driven by coroutine generators for depth safety (deep right-recursive ABNF trees). 506k `generator.send()` calls for 5 reduces = 101k sends/reduce. Python generators cost ~200ns/yield. Fundamentally limited by generator overhead; avoiding it requires either a non-generator reduce or accepting stack overflow risk on deep grammars.

**The Python ceiling**: Lark's Earley core is in C. At ~131k items/parse, C processes each item in ~10-20ns; Python requires ~700-800ns. The ~2x gap on pure parse (1.87x Lark) reflects this C-vs-Python constant factor, not algorithmic issues.

---

## OPT6 attempt: str-keyed waiting table (reverted)

Attempted to change `Column.waiting._table` from `IrRuleRef`-keyed to `str`-keyed (matching the `rules_table`/`nullable_table` pattern). This would eliminate remaining `IrScalar.__eq__` calls in `Complete.eval` and `LeoItem.sole_candidate`.

**Result**: 2.48x vs 2.34x — worse. The `str(symbol)` call on every `Column.__iadd__` invocation (131k/run) added overhead exceeding the `IrScalar.__eq__` savings. Reverted.

**Why OPT5 worked but OPT6 did not**: `rules_table` and `nullable_table` are per-parse constants (built once at `ParseCtx` construction). Their lookups happen 58.6k times/parse. The `str(ref)` conversion costs ~42ns and the eliminated `IrScalar.__eq__` saved ~50ns/call. Net positive.

For `waiting._table`: the `str(symbol)` conversion happens on every item insertion (131k/parse) AND every Complete/Leo lookup (51k/parse). Total added: (131k+51k) × 42ns = 7.6ms. `IrScalar.__eq__` savings: 51k × 50ns = 2.6ms. Net negative.

---

## Correctness canaries (all confirmed)

- `earley IrAst == lark IrAst (fixpoint): True` — semantic equivalence
- `is_ambiguous(NORM_GRAMMAR, ABNF_TEXT) == False` — unambiguous parse confirmed
- 1128 tests pass (excluding `test_ops.py` which was broken before this exploration due to `LEO_ENABLED` import)

---

## Files changed in this worktree

- `src/lexic/parsing_2/engine.py`: CloseColumn inline dispatch (OPT1), start rule seed uses rules_table (OPT5)
- `src/lexic/parsing_2/chart.py`: Column.__iadd__ inlined multimap ops (OPT2), predicted: set[str] (OPT5)
- `src/lexic/parsing_2/forest.py`: _collect_kids(), _build_tree_fast(), BuildTree.eval fast path (OPT3/OPT4)
- `src/lexic/parsing_2/ops.py`: _PREDICT/_COMPLETE/_SCAN singletons (OPT1), Predict.eval uses str dicts (OPT5), Complete.eval uses direct _table access (OPT2), ParseCtx.rules_table/nullable_table fields (OPT5)
- `tests/unit/lexic/parsing_2/test_forest.py`: test_build_tree_zero_derivations_raises updated for new fast path

---

## Recommendations for further improvement

1. **PyPy**: The dominant remaining cost is Python bytecode dispatch on the item-processing inner loop. PyPy would give 5-10x speedup on chart building (the C-to-Python gap). No code changes needed.

2. **Direct recursive reduce** (optional, Slice D): Replace the `Trampoline`-driven reduce with direct recursion for non-pathologically-deep trees. Safe up to ~800 rules (Python's default recursion limit is 1000). Would save ~80ms/parse. Requires a recursion-depth check and fallback to Trampoline for deep trees.

3. **C extension for Column/Chart** (optional, later): The `Column.__iadd__` hot path (item insertion + indexing) is the #1 hotspot. A Cython or ctypes wrapper for just this class could give 5-10x speedup on chart operations.

4. **SPPF-free recognition**: The `record_links=False` path (pure recognition) already skips link recording. Recognize at 1.65x Lark. No obvious improvement without changing the algorithm.

5. **Open-set consumer rework** (planned per memory): The derive/codegen consumers carry closed-set `isinstance` ladders. This is the next major structural effort per the project roadmap, and should not block parsing_2 performance work.
