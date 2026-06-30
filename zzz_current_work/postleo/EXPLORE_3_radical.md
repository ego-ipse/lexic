# Exploration 3 — Go Radical: IrSelf-Free Flat Engine

**Status:** DONE. Data first.

---

## 1. The Question

Can we beat Lark's Earley parser with a flat Python implementation that strips all IrSelf/IrDispatch machinery? And if so, on which metric and at what correctness cost?

Starting point from BASELINE.md:
- `e:parse` (chart + ParseTree, no reduce): 2.96x Lark
- `e:parse+reduce` (product metric): 3.32x Lark

---

## 2. Root Cause of Super-Linearity

**Confirmed:** The current earley engine is O(n) on typical ABNF text (not super-linear). The gap is a pure constant-factor problem.

cProfile of the IrSelf engine (5 runs × x4 = 3680 chars):

| Cost | ms | % | Source |
|------|-----|---|--------|
| Trampoline + generator overhead | ~1.1s | 15% | `forest.py`, `trampoline.py` |
| Column dedup (tuple set ops) | ~0.5s | 7% | `IrBase.__eq__` on IrRuleRef in tuples |
| IrDispatch.eval per op | ~0.3s | 4% | `walk.py:eval` |
| Predict overhead | ~0.5s | 7% | item creation + filing |
| IrBase allocations | ~0.2s | 3% | `IrRuleRef` per predicted item |

Total: ~7s/5 runs = 1.4s per x4 parse. Lark does it in 107ms.

The engine is not algorithmically broken — it is constant-factor hobbled by Python machinery.

---

## 3. What Was Built (fast_engine.py)

`src/lexic/parsing_2/fast_engine.py` — throwaway radical exploration. Three versions:

- **v1**: Flat Python loops, no IrDispatch, no trampoline. Items as `(IrRuleRef, arm, dot, origin)` tuples. Atom intern table for stable ids.
- **v2**: Item[0] converted to plain `str`. Char-literal cache. Items as `(str, arm, dot, origin)`.
- **v3 (final)**: Items as `(plain_str, int_arm_id, int_dot, int_origin)` — all primitives, O(1) tuple hash/eq. Persistent `char_accepts` dict on index. `waiting` dict uses plain str keys. `_file_item_v3` inlined into main loop. Columns pre-allocated. Leo optimization preserved.

---

## 4. Benchmark Results

**ABNF self-host, 50 rounds, median:**

### x4 text (3680 chars, definitive)

| Engine | Recognize | vs lark:parse | Parse (no reduce) | vs lark:full |
|--------|-----------|---------------|-------------------|--------------|
| lark:parse | 108.9ms | 1.00x | — | — |
| lark:full | — | — | 113.7ms | 1.00x |
| earley | 152ms | 1.40x | 300ms | 2.64x |
| fast v1 | ~135ms | 1.31x | ~192ms | 1.69x |
| fast v2 | ~127ms | 1.17x | ~175ms | 1.54x |
| **fast v3** | **95.9ms** | **0.88x** | **143.5ms** | **1.26x** |

### All sizes (20 rounds each, final bench run)

| Size | lark:parse | fast3:recognize | ratio | lark:full | fast3:parse | ratio |
|------|-----------|-----------------|-------|-----------|-------------|-------|
| x1 (920 chars) | 25.8ms | 23.4ms | **0.91x** | 26.6ms | 34.5ms | 1.30x |
| x2 (1840 chars) | 51.2ms | 46.7ms | **0.91x** | 52.9ms | 68.2ms | 1.29x |
| x4 (3680 chars) | 103.0ms | 93.9ms | **0.91x** | 107.1ms | 141.9ms | 1.32x |

Raw output: `EXPLORE_3_bench_final.txt`

---

## 5. Right-Recursion (Leo O(n) Verification)

| N | lark:parse | µs/N | earley:parse | µs/N | e/lark | v3:recognize | µs/N | v3/lark |
|---|-----------|------|--------------|------|--------|--------------|------|---------|
| 100 | 2.73ms | 27.3 | 2.34ms | 23.4 | 0.86x | 0.48ms | 4.75 | 0.17x |
| 200 | 5.30ms | 26.5 | 4.57ms | 22.8 | 0.86x | 0.91ms | 4.54 | 0.17x |
| 400 | 10.5ms | 26.1 | 8.30ms | 20.7 | 0.79x | 1.78ms | 4.46 | 0.17x |
| 800 | 20.7ms | 25.9 | 17.9ms | 22.3 | 0.86x | 3.57ms | 4.46 | 0.17x |
| 1600 | 41.0ms | 25.6 | 35.4ms | 22.1 | 0.86x | 7.01ms | 4.38 | 0.17x |

- Leo is O(n): 4.4µs/char constant from N=100 to N=1600. ✓
- v3 recognition is 6x faster than Lark on right-recursion. ✓
- Note: v3 tree reconstruction is not trampolined — stack overflow at N=800. Recognition only for deep recursion.

Raw output: `EXPLORE_3_rightrec.txt`

---

## 6. Final Profile (v3, x4, 5 runs warmed)

| Function | tottime | calls | Source |
|----------|---------|-------|--------|
| `_build_chart_v3` | 1.235s | 5 | main loop (everything inlined) |
| `dict.get` | 0.201s | 1.6M | waiting/scannable/links lookups |
| `isinstance` | 0.100s | 1.0M | `isinstance(atom, IrRuleRef)` |
| `_collect_kids_v3` | 0.098s | 85k | tree building |
| `set.add` | 0.098s | 851k | col_seen dedup |
| `len()` | 0.086s | 1.2M | arm bounds checking |
| `builtins.id` | 0.070s | 811k | atom canonicalization |
| `_build_tree_v3` | 0.068s | 67k | tree wrapper |
| `list.append` | 0.061s | 641k | item queuing |
| `_leo_sole_candidate_v3` | 0.053s | 110k | Leo check |

**IrBase.__eq__ is NOT in the top 20** — all IrRuleRef comparison eliminated.

Profile: `EXPLORE_3_profile_final.txt`

---

## 7. What Actually Fixed It (Optimization Trail)

Starting from v3 at 1.68x (parse), each fix and its measured effect:

### Fix 1: `str(atom)` instead of dict probe for name_intern
- Problem: `name_intern.get(IrRuleRef)` triggered `IrRuleRef.__eq__` on dict probe (hash collision → stored key comparison). Python dict compares stored_key == lookup_key, calling `IrRuleRef.__eq__(str)`.
- Fix: `str(IrRuleRef)` returns plain str via `str.__str__` — no Python-level __eq__
- Eliminated: 580k → 288k IrBase.__eq__ calls

### Fix 2: Plain str keys in `waiting` dict
- Problem: `_file_item_v3` stored `col.waiting[IrRuleRef]` keys. Lookup with plain str done_ref triggered `IrRuleRef.__eq__` as Python dict compared stored IrRuleRef key against plain str lookup.
- Fix: `ref_name = str(atom)` for both filing and lookup
- Eliminated: remaining 284k IrBase.__eq__ calls
- Combined with Fix 1: recognize 1.68x → 0.98x (crossed Lark parity)

### Fix 3: Persistent `char_accepts` cache on `FastGrammarIndexV3`
- Problem: `char_accepts` dict rebuilt per parse, triggering ~11k `_atom_accepts_char` calls per parse (O(unique_chars × canonical_atoms)) with IrLiteral comparisons
- Fix: move dict to index, survives across parses, populated on first parse

### Fix 4: Inline `_file_item_v3` into main loop
- Problem: 585k Python function calls × ~150ns each = ~87ms overhead
- Fix: manual inline at all 6 call sites
- Impact: recognize 0.98x → 0.94x

### Fix 5: Pre-allocate columns
- Problem: `chart[i]` via `_ChartV3.__getitem__` = 337k Python function calls (0.074s)
- Fix: pre-allocate `n+1` columns at chart creation, direct `columns[i]` list access
- Impact: recognize 0.94x → 0.91x

### Fix 6: `arm_id_to_len` pre-computed dict
- Problem: `len(arm)` called 2.77M times
- Fix: pre-compute `arm_id → len(arm)` in index
- Impact: minor (len() on tuple subclass is already C-level fast)

---

## 8. Why Lark Still Beats on Full Parse+Tree

v3 beats Lark on recognition (chart build only: 0.88–0.91x). On parse+tree it is 1.26–1.32x behind. The gap is tree construction:

Real wall-time breakdown at x4:
- v3:recognize: 95.9ms (beats lark:parse 108.9ms)
- v3:parse: 143.5ms = 95.9ms (chart) + 47.6ms (tree building)
- lark:full: 113.7ms

The 47.6ms tree building cost vs Lark's ~5ms extra (113.7 - 108.9) tells the story. Our `_ParseTree`/`_SppfNode2` are Python dataclass instances allocated recursively. 306k `_SppfNode2.__init__` calls + 67k `_ParseTree.__init__` calls. Lark uses C-level forest construction.

**Next tree optimization target**: replace `_SppfNode2(item, end)` with bare `(item, end)` tuples (no Python class, no `__init__` overhead); consider iterative tree construction to avoid recursion.

---

## 9. Correctness

- ABNF self-host: parse returns `_ParseTree` with `symbol='rulelist'` ✓
- Matches earley ParseTree structure ✓
- Leo O(n) right-recursion verified (recognition) ✓
- Tree reconstruction stack overflows at N=800 for right-recursive grammars — not trampolined (known limitation of this exploration; production engine uses trampolined forest walk)

---

## 10. Verdict: Worth Pursuing For Real

**Yes, with a specific plan.**

Recognition **already beats Lark** (0.88–0.91x consistently). Full parse is 1.26–1.32x behind, entirely due to tree-building Python overhead.

Three root causes were confirmed and fixed:
1. `IrRuleRef.__eq__` in set/dict probes — fixed with `str(atom)` conversions
2. Function call overhead for `_file_item_v3` — fixed with inlining
3. `__getitem__` for column access — fixed with pre-allocation

What this exploration proved:
- The 3.35x earley gap was constant-factor, not asymptotic
- Leo already provides O(n) for right-recursion
- All three bottlenecks are fixable in pure Python without C extensions
- The IrSelf/IrDispatch machinery is the cost, not the Earley algorithm itself

**Recommended production port**: adopt `(plain_str, int_arm_id, int_dot, int_origin)` item tuples with plain-str waiting keys and pre-computed arm lengths in the IrSelf engine. Inline the filing logic into Predict/Complete/Scan IrActions. Eliminate the `_file_item` call indirection. This gives the same wins without abandoning the dispatch architecture.

The open-classes consumer rework (flagged in .wiki) is the right vehicle.
