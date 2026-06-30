# Handover — parsing_2 performance: **beat Lark**

*Clean restart of the perf handover (2026-06-30). The session-by-session history
through the Leo + depth-safe work lives in `HANDOVER_perf.md` — consult it for
detail; this file is the active, goal-focused state.*

## The goal

Surpass Lark on the **product metric**: text → `IrAst`, i.e. `e:parse+reduce` vs
`lark:full`. Everything else (recognize, parse) is a diagnostic stage on the way.

## Honest comparison model (peering)

Lark's pipeline splits in two (`MetaGrammarParser`): `_lark.parse(text)` → `Tree`,
then the transformer → `IrAst`. Compare **like-for-like work**:

| earley stage | work | proper Lark peer | exact? |
|---|---|---|---|
| `e:recognize` | text → bool | `lark:parse` | **no** — builds no tree; Lark has no recognise-only mode. Lower-bound / scaling check only |
| `e:parse` | text → `ParseTree` | `lark:parse` (text → `Tree`) | yes |
| `e:parse+reduce` | text → `IrAst` | `lark:full` (text → `IrAst`) | yes — **the product** |

The old bench compared all three to the full transform — that flattered recognize
and was the bug this rewrite fixes.

## Current standing (committed HEAD, 2026-06-30)

**ABNF self-host (x4, 3680 chars):**

| stage | median | vs peer | verdict |
|---|---|---|---|
| `lark:parse` | 102.8 ms | — | |
| `lark:full` | 106.7 ms | — | transform is ~free (+4%) |
| `e:recognize` | 153.9 ms | 1.50× `lark:parse` | lower bound (does less) |
| `e:parse` | 304.1 ms | **2.96× `lark:parse`** | cut 66% to match |
| `e:parse+reduce` | 355.3 ms | **3.33× `lark:full`** | cut 70% to match — **the number to kill** |

**Asymptotic `S = "a"*` (the algorithmic story):**

| | scaling | µs/N | vs `lark:parse` |
|---|---|---|---|
| `lark:parse` | **O(n)** | ~25 (flat) | — |
| `e:recognize` | **O(n)** (Leo) | ~8.2 (flat) | engine core is fast |
| `e:parse` | **O(n²)** | 69 → 1048 (N=100→1600) | **2.6× → 41× and widening** |

`µs/N²` for `e:parse` is flat ~0.6 across all N — so even the short ABNF reps pay
the quadratic tax; it isn't only a large-input problem.

## Must do next session (carry-over directive)

- **REMOVE the `LEO_ENABLED` flag — Leo becomes unconditional.** It has served its
  purpose (a differential oracle that caught two bugs); it is not to be carried
  forward. Removal scope:
  - `ops.py:205` — delete `LEO_ENABLED = True`.
  - `ops.py:331` — drop the `LEO_ENABLED and` conjunct from the `Complete` gate
    (Leo fires on `not ctx.record_links and len(waiters) == 1`).
  - `tests/unit/lexic/parsing_2/test_ops.py` — remove `test_leo_enabled_is_true`
    and the differential helper that toggles `ops_mod.LEO_ENABLED` (`_recognize_with_leo`
    + the on-vs-off differential test + the "restored to True" test).
  - **Consequence:** the Leo-on-vs-off differential oracle disappears with the flag.
    Replace it with a flag-free correctness check for the Leo+SPPF work — a deep
    right-recursive grammar in the canary battery whose derivations are validated
    against the recursive/Lark reference (not against "Leo off").

## Diagnosis — where we lose

1. **`parse` is O(n²). This is the whole game.** The SPPF completer re-walks the
   right-recursion reduction chain once per column. Leo fixes that — but Leo is
   **recognition-only** by construction: it is gated `not ctx.record_links`
   (`ops.py:331`), because a Leo jump skips the intermediate completions and so
   never records the SPPF provenance links the forest walk needs. So with the SPPF
   on (the parse path), Leo is off and we pay O(n²). The gap to Lark grows without
   bound in N.
2. **`recognize` is already O(n) and ~8 µs/N** — the engine core is healthy. The
   1.50× vs `lark:parse` on ABNF is pure constant factor *and* recognize does
   strictly less than `lark:parse` (no tree), so it is not the front to fight on.
3. **`reduce` adds ~17%** over `parse` (304 → 355 ms) while Lark's transform adds
   ~4%. A secondary constant-factor target once parse is O(n).

## Levers, ranked

### 1. Leo + SPPF (Scott 2008) — make `parse` O(n). **THE lever.**
The only path to beating Lark asymptotically (and most of the constant-factor gap
at ABNF sizes too, since the O(n²) tax is paid even at small N). Record provenance
for the **transitive (topmost) Leo item** so derivations still recover, then let
Leo fire on the parse path (remove the `not ctx.record_links` gate once links are
recorded for Leo jumps). Highest risk: deterministic-reduction detection + SPPF
link bookkeeping for Leo items + nullable/Aycock-Horspool interaction. Validate
with the ABNF fixpoint + ambiguity canaries plus a **deep right-recursive grammar**
whose derivations are checked against the recursive/Lark reference — the flag-free
oracle that replaces `LEO_ENABLED` (which is being removed, see *Must do next
session*). Note this work also retires the `not ctx.record_links` Leo gate.
*Unblocked now:* the depth-safe forest/reduce (this session) means parse no longer
crashes at depth, so Leo+SPPF can be measured and validated at large N.

### 2. Constant-factor on the parse/forest path
Once (1) lands, profile (`--profile`, **measure wall-clock — cProfile
over-attributes to Python frames**) and attack: SPPF link recording in `ScanColumn`
/ `Complete`, `EarleyItem` set/dict ops, per-char scan. The flat profile means the
next wins are these, not algorithm.

### 3. `reduce` constant factors
Trampoline/cogen overhead, `ResolveSource` per-child work, `KEEP_REDUCED` memo
path. Target the ~17% reduce adds vs Lark's ~free transform.

### 4. Micro (from `HANDOVER_perf.md`, verify what's landed)
P2 `Column.scannable`, S3 char→atom scan index, Expand memoize. Small, composable.

## What's already done (brief)

- **Depth-safe forest + reduce (this session, committed).** Replaced the recursive
  forest walk and reducer with an explicit-stack **trampoline**
  (`parsing_2/trampoline.py`); `forest.py` cogens `NodeDerivs`/`PrefixSource`/
  `ChildDerivs` + `ForestCtx` cursor; `reduce.py` `ReduceSource`/`ResolveSource` +
  `ReduceCtx`. Fixed the O(depth) crash (`parse` died ~N=300, `parse+reduce`
  ~N=1000); **perf-neutral** on ABNF. Suite 1152 green.
- **Leo (recognition) → recognize O(n)** (`ops.py`, `LEO_ENABLED`, `Column.leo`).
- Mapping cutover, engine round, char-indexed scan, skip-SPPF-for-recognize,
  plain-tuple engine records. See `HANDOVER_perf.md` sessions 3–6.

## Benchmark guide (`zzz_current_work/bench_parsing.py`)

```
uv run python zzz_current_work/bench_parsing.py "<label>" [--save]
        # ABNF self-host x1/x2/x4 + VERDICT vs lark; --save snapshots medians to
        # bench_baseline.json so the next run prints Δ% per cell (track progress)
uv run python zzz_current_work/bench_parsing.py --rightrec
        # deep S="a"* : e:parse vs lark:parse (exact, O(n²) vs O(n)) + recognize floor
uv run python zzz_current_work/bench_parsing.py --profile
        # cProfile parse+reduce x4 (treat as a hint; trust wall-clock)
```
Interleaved sampling (drift hits all variants alike); reports min/median/stdev and
the **proper-peer** ratio. The `--rightrec` grammar is the asymptotic canary for
Leo+SPPF — a flat `vs lark` ratio there means parse went O(n).

## Constraints / canaries (unchanged)

- IrSelf purity: behaviour on classes via `eval`/dunders; per-parse mutable state
  in a cursor; prefer a class *being* an `IrMultiMap` over a `dict` attr (set-shaped
  state may ride a slot, cf. `Column.predicted`, `ForestCtx.open`).
- No `# type: ignore` / `# noqa` / `# pylint: disable`; no `exec`/`eval`. No
  grammar-specific hardcoding.
- Canaries: ABNF fixpoint True, `is_ambiguous` False, full suite green (1152).
- **Never `git commit`** (the user lands).

## Validation recipe

```
uv run pytest tests/ -q                                       # full suite (1152)
uv run python zzz_current_work/bench_parsing.py "<label>"     # self-host + verdict
uv run python zzz_current_work/bench_parsing.py --rightrec    # asymptotic vs lark
uv run python -c "from lexic.grammars import ABNF_FLAVOUR; \
from lexic.grammars.abnf_2 import ABNF_GRAMMAR; from lexic.parsing_2 import recognize, is_ambiguous; \
from lexic.parsing_2.normalize import normalize; g=normalize(ABNF_GRAMMAR); \
t=str(ABNF_FLAVOUR.apply(ABNF_GRAMMAR)); \
print('rec',bool(recognize(g,t)),'fixpoint',str(ABNF_FLAVOUR.apply(ABNF_GRAMMAR))==t,'amb',bool(is_ambiguous(g,t)))"
```
