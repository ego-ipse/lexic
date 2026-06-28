# Handover — round 4 results: two spikes measured, ship set identified (2026-06-27)

Two background Sonnet spikes ran in isolated worktrees (correctly based on
`parse_proto_proto` @ `e0c8c0c`). Both completed green (1126 passed) with the ABNF
self-host fixpoint holding. Full reports:

- `zz_current_work/SPIKE_f1_base_cost.md` (Spike 1)
- `zz_current_work/SPIKE_char_indexed_scan.md` (Spike 2)

Prototype code (throwaway, no source modified) lives in the worktrees:
- Spike 1: `.claude/worktrees/agent-a1174a19a4a3c0738/zz_current_work/strategy1c_precompute_raw.py` (+ s2/s3/s4 + harnesses)
- Spike 2: `.claude/worktrees/agent-a084e690a0ecd5435/` (chart.py / engine.py / ops.py prototypes)

These two worktrees are still on disk so the prototype code can be lifted into
source. Remove them once the ship set is implemented.

---

## TL;DR — the ship set

| # | Change | Measured | Purity | Where | Status |
|---|--------|----------|--------|-------|--------|
| **P1** | **Spike-1 S1(c)** — micro-wins A+B+C+D + precomputed empty-deriving arms (`ExtendedParseCtx`/`IrMultiMap`) | **+13–15% recognize** (x1 82.4 vs 93.6 ms), fixpoint OK | ✅ | `ops.py`, `engine.py` | **SHIP** |
| **P2** | **Spike-2 S2** — `Column.scannable` list; scanner skips ruleref-facing items | **−67% MATCHES; +6–8% ABNF; +3.5% suite**; zero regression | ✅ | `chart.py` (~15 lines), `engine.py` (2) | **SHIP** |
| S3a | Spike-1 S3 — memoize `Expand.eval` (share synthetic rules) | +2–3% + 53→46 rules | ✅ | `normalize.py` | Optional, composable |
| — | Spike-2 S3 — full char→atom scan index | +12–13% ABNF but **regresses short parses** | ✅ | needs `ColumnScanIndex(IrMultiMap)` | **Defer** (follow-up spike) |
| — | Spike-1 S2 — NNLR left-rec `*`/`+` desugar | neutral on suite; ~16% at x4 w/ ~3% N=0 penalty | ✅ | `normalize.py` | **Defer** (only if long-rep workload matters) |
| — | Spike-1 S4 — conditional F1 (terminal-only) | 0 effect (all real reps are ruleref) | — | — | **Discard — dead** |

P1 and P2 hit **different hot paths** (Predict/Complete vs Scan), so they're
expected to be largely additive — but **re-measure once landed together**; don't
sum the headline percentages.

---

## Spike 1 — F1 base cost (`f1-base-cost`)

**The reframed question paid off.** "Get O(n²)→O(n) AND ≥ right-rec at N=0/1" is
**not achievable** with any tested desugaring — left-rec and NNLR both pay ~1.3–1.37×
at N=0 (the AH nullable-predict tax), and the suite is dominated by 0–2-item reps.
So the win is NOT changing recursion direction; it's **making the AH branch cheaper**:

**S1(c) (PRIMARY, ship):** micro-wins A+B+C+D plus precomputed empty-deriving arms.
- A: hoist `ctx.rules.resolve(ref)` in the nullable branch.
- B: raw `ctx.chart._columns[ctx.col]` on the hot path (skip growth-check).
- C: drop `cast(Sequence[IrSelf], arm)` — a runtime no-op hitting `typing._tp_cache` ~46k×/parse.
- D: `_table.get()` + tuple snapshot in `Complete` (avoid per-completion `IrSeq` alloc).
- precompute: per nullable rule, which arms are empty-deriving → `IrMultiMap` on
  `ExtendedParseCtx` (a one-slot `ParseCtx` subclass), keyed by `IrRuleRef`. The
  nullable branch iterates the precomputed list instead of the `all(...)` genexpr.
- **Why the prior "8% slower" precompute failed:** it stored `set[IrSequence]` and
  did `arm in set`, forcing `IrSequence.__hash__` (hash all items). Keying by the
  already-cheap `IrRuleRef` and returning the arm list avoids all arm hashing.
- Result: x1 82.4 ms (1.135×), x2 1.137×, x4 1.143×. Fixpoint correct. Pure.

**Deferred:** NNLR (S2) — only desugaring that helps long reps without left-rec's
exact small-N profile, but still 1.37× at N=0 and adds 2 synthetic rules per `*`.
Pick up only if profiling shows real hand-written/long-repetition super-linearity.
S3 memoize is a free composable 2–3%. S4 conditional is dead (real reps are all
rulerefs, never bare terminals).

---

## Spike 2 — char-indexed scan (`char-indexed-scan`)

Baseline: 67% of `MATCHES.eval` calls are ruleref-facing no-ops; 87% of the
remaining terminal calls reject the char anyway. Only 4.2% of items advance.

**S2 (ship):** add `scannable: list[EarleyItem]` to `Column`; file terminal-facing
items at insert time (same mutable-chart exception as `_items`/`_seen`); scanner
iterates `column.scannable`. −67% MATCHES, +6–8% ABNF, +3.5% suite, 17 lines, zero
regression, fixpoint OK.

**Deferred S3:** full char→accepting-atom index (`ParseCtx.char_accepts` +
`Column.scannable_by_atom`) eliminates `MATCHES` entirely (+12–13% ABNF) but
`IrMultiMap.__iadd__` insert cost (7k/parse, 3.2× a dict) regresses short parses
(crossover ~400 chars). **Make-viable path:** subclass `IrMultiMap` as
`ColumnScanIndex` overriding `__iadd__` to write `_table` directly — one focused
follow-up spike; stays pure.

---

## Constraints (unchanged)

IrSelf purity (behaviour on classes via eval/dunders; per-parse mutable state in a
cursor; prefer a class being an `IrMultiMap` over a `dict` attr). No
`# type: ignore`/`# noqa`/`# pylint: disable`; no `exec`/`eval`. No grammar-specific
hardcoding. Suite stays 1126; ABNF fixpoint is the canary. Never `git commit`
(user lands). Raw `_table`/`_columns` access in P1/P2 are internal sibling-module
shortcuts — flagged, justified by the hot-path numbers.

## Suggested implementation order

1. **P2 (Spike-2 S2)** first — smallest, zero-risk, isolated to `chart.py`/`engine.py`.
2. **P1 (Spike-1 S1(c))** — port from `strategy1c_precompute_raw.py`; confirm fixpoint, no `reduce.py` change.
3. Re-measure P1+P2 together (recognize + suite ×3 warm); keep the combined number honest.
4. Optionally add S3a (Expand memoize).
5. Leave NNLR and the char-index S3 deferred behind their named conditions.

## Operational note (worktree base bug — fixed)

The agent-worktree tool defaulted `worktree.baseRef=fresh`, branching from
`origin/main` (`b24259c`), not the current branch `parse_proto_proto` (`e0c8c0c`,
ahead of main and unmerged) — so spikes initially landed on the wrong base. Fixed
by setting `"worktree": {"baseRef": "head"}` in `.claude/settings.local.json`. Stale
`b24259c` agent worktrees/branches from prior sessions were pruned.
