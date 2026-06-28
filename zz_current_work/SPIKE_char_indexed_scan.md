# Spike: Char-indexed Scan for Earley `ScanColumn`

**Branch:** `parse_proto_proto` (worktree `agent-a084e690a0ecd5435`)  
**Date:** 2026-06-27  
**Status:** Throwaway prototype. Code left in place; do not merge as-is.

---

## Baseline characterisation

`ScanColumn.eval` iterates ALL items in `chart[i]`, guards on `item.dot < len(item.arm)`, then calls `MATCHES.eval` on every non-complete item. Ruleref-facing items reach `MATCHES` only to return 0 immediately.

At x1 ABNF (920 chars, after column-close):

| category | count | % of scan-iterable |
|---|---|---|
| RuleRef-facing items reaching MATCHES | 15,109 | 67% |
| Terminal-facing — Literal | 2,249 | 10% |
| Terminal-facing — CharClass | 5,083 | 23% |
| **Total MATCHES.eval calls** | **22,441** | |
| Terminal items that actually advance | 940 | 4.2% |

87% of terminal MATCHES calls reject the current char (6,392 of 7,332).

---

## Strategy 2: `Column.scannable` list

**What:** Add `scannable: list[EarleyItem]` to `Column.__slots__`. File terminal-facing items into it at insert time (in the existing `isinstance(symbol, IrRuleRef)` branch). `ScanColumn.eval` iterates `column.scannable` instead of `chart[i]`, dropping the `item.dot < len(item.arm)` guard.

**Files:** `chart.py` (~15 lines), `engine.py` (2 lines).

**MATCHES.eval calls after S2:**

| mult | before | after | reduction |
|---|---|---|---|
| x1 | 22,441 | 7,332 | −67% |
| x2 | 44,882 | 14,664 | −67% |
| x4 | 89,764 | 29,328 | −67% |

**Purity:** `scannable` is engine state on the mutable-chart exception — same pattern as `_items`/`_seen`, already justified by the existing `waiting: IrMultiMap` slot.

---

## Strategy 3: `scannable_by_atom` + lazy `char_accepts` index

**What:** Two additions on top of S2:

1. `Column.scannable_by_atom: IrMultiMap` — filed alongside `scannable` at insert time. Key = terminal atom, bucket = items facing it.
2. `ParseCtx.char_accepts: IrMultiMap` — grammar-level char → accepting atoms, populated lazily on first encounter of each char. Built from `CharAccepts(IrLeaf)` which extracts all terminal atoms from the grammar once per parse.

`ScanColumn.eval` becomes: get `accepting_atoms = char_accepts._table[char]`, then `for atom in accepting_atoms: for item in col.scannable_by_atom._table.get(atom): advance`.

`MATCHES.eval` is never called — atom acceptance is resolved at `char_accepts` population time via `_atom_accepts()`.

**Files:** `chart.py` (+`scannable_by_atom` slot and `__iadd__` update), `engine.py` (`CharAccepts` node, `_atom_accepts` helper, updated `ScanColumn` and `BuildChart`), `ops.py` (`ParseCtx` gets `char_accepts` slot), `tests/unit/.../test_ops.py` (one `ParseCtx` construction updated).

**MATCHES.eval calls after S3:** **0 at all multipliers.**

**IrSelf purity assessment:**

- `scannable_by_atom` IS an `IrMultiMap` slot on `Column` — satisfies the "prefer IrMultiMap over dict attr" constraint. Overhead: `IrMultiMap.__iadd__` is 3.2× slower than a plain `dict.get/setdefault/append` (measured: 1.3ms vs 0.4ms per parse for the 7,334 terminal inserts).
- `char_accepts` IS an `IrMultiMap` on `ParseCtx` — but the hot scan path bypasses `__getitem__` and reads `._table` directly (the IrSeq wrapper costs ~2.5× more than a raw dict lookup). This is a purity compromise in the spike code.
- `CharAccepts(IrLeaf)` extracts terminal atoms — pure IrSelf node.
- `_atom_accepts()` is a free function (factored out of `Matches.eval`) — acceptable helper.

---

## Results

### MATCHES.eval call counts

| mult | baseline | S2 | S3 |
|---|---|---|---|
| x1 | 22,441 | 7,332 (−67%) | 0 (−100%) |
| x2 | 44,882 | 14,664 (−67%) | 0 (−100%) |
| x4 | 89,764 | 29,328 (−67%) | 0 (−100%) |

### Recognize timing — one-process (gc off, 50 iters, median ± stdev)

All three variants measured in the same Python process via class-level patching to eliminate cross-run noise.

| workload | baseline | S2 | S3 |
|---|---|---|---|
| ABNF x1 (920 chars) | 100.7 ± 1.5 ms | 92.2 ± 1.2 ms | **88.4 ± 1.2 ms** |
| ABNF x2 (1840 chars) | 210.4 ± 2.6 ms | 196.3 ± 5.0 ms | **184.8 ± 1.6 ms** |
| ABNF x4 (3680 chars) | 443.1 ± 4.1 ms | 416.5 ± 5.9 ms | **387.5 ± 4.1 ms** |
| vs baseline | — | **+6–8%** | **+12–13%** |

### Charclass-heavy grammar (297 chars, 3 rules, [a-zA-Z]/[0-9]/"-")

| variant | time |
|---|---|
| Baseline | 3.34 ± 0.01 ms |
| S2 | 3.25 ± 0.02 ms (+2.7%) |
| S3 | 3.24 ± 0.06 ms (+3.1%) |

Charclass-heavy grammar shows smaller gains because the grammar is simple (few rules, small columns), so ruleref overhead is proportionally lower.

### Full suite wall-clock (3 warm runs)

| variant | run 1 | run 2 | run 3 |
|---|---|---|---|
| Baseline | 11.27 s | 11.34 s | 11.02 s |
| S2 | 10.84 s | 10.91 s | 10.80 s |
| S3 | 11.10 s | 11.01 s | 11.15 s |

S2 suite gain: ~+3.5%. S3 suite: ~same as baseline — the suite exercises many short parses where S3's `scannable_by_atom` insert overhead dominates over scan savings.

### ABNF fixpoint canary

`ABNF_REDUCER.apply(parse(NORM, text)) == ABNF_GRAMMAR` → **True** for both S2 and S3.

---

## Root cause of S3 suite regression

S3 adds `IrMultiMap.__iadd__` for every terminal-facing item inserted into a column (7,334 per x1 parse). `IrMultiMap.__iadd__` costs 1.3ms/parse at x1 — 3.2× more than a plain dict because it goes through Python-level `setdefault` + the tuple-element indirection (`_table` property). For short parses (the suite is full of them), this insert overhead exceeds the scan savings from skipping `MATCHES.eval`.

The scan savings only materialise on longer inputs where the scan loop is called many times. The crossover is somewhere around 300–500 chars of input.

The hot path `._table` bypass in `ScanColumn.eval` is what makes S3 competitive on ABNF — without it, the `IrMultiMap.__getitem__` → `IrSeq` allocation on every atom/column lookup would add another ~0.8ms.

---

## Recommendation

**Ship S2.** Consistent +6–8% on ABNF, +3.5% suite, zero regression risk, 17 lines changed, no new concepts. Purity is clean.

**Do not ship S3 yet.** The +12% on ABNF is real but the suite regresses because short-parse overhead from `IrMultiMap.__iadd__` (7K per parse) exceeds the scan savings. S3 only pays on inputs >~400 chars.

**To make S3 viable:** the `scannable_by_atom` insert path needs to be as cheap as `list.append`. Options:

1. Override `IrMultiMap.__iadd__` in a `ColumnScanIndex` subclass to use raw `_table` directly (bypassing the tuple-element property on every call). Stays IrSelf-pure.
2. Make `Column` itself a multi-map subclass (per the memory note), folding `scannable_by_atom` into the column's own index. More invasive.
3. Accept a plain dict slot and annotate the purity tradeoff explicitly. The constraint says "prefer IrMultiMap over dict attr" — not "always IrMultiMap regardless of cost."

Option 1 is the cheapest path and worth a focused follow-up spike.

---

## Files changed (throwaway)

- `src/lexic/parsing_2/chart.py` — `Column`: `scannable` + `scannable_by_atom` slots
- `src/lexic/parsing_2/engine.py` — `_atom_accepts`, `Matches`, `CharAccepts`, `ScanColumn`, `BuildChart`, `_CHAR_ACCEPTS_ALL_KEY`, `CHAR_ACCEPTS`
- `src/lexic/parsing_2/ops.py` — `ParseCtx.char_accepts` slot
- `tests/unit/lexic/parsing_2/test_ops.py` — `ParseCtx` construction (ported)
