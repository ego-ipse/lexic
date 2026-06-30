# Handover — parsing_2 performance (2026-06-29)

## Status (session 3, 2026-06-29)

**Done & committed** (recognize median, ABNF self-host, vs pre-P2 baseline):

| step | x1 | x2 | x4 | note |
|---|---|---|---|---|
| baseline | 69.6ms | 146.8ms | 314.0ms | — |
| **P2** scannable | 64.3 | 140.5 | 291.4 | −8% to −7% |
| **S3** char→atom index | 62.2 | 134.8 | 281.8 | −10% / −8% / −10% cumulative; MATCHES 0 calls |
| **S3a** Expand memoize | ~61 | ~132 | ~280 | marginal; rules 53→46; `Expand` carries `IrQuantifier` |
| **P1B** col reuse | 60.0 | 128.4 | 273.0 | −3%; ctx.column stashed, no re-index |

**Session 4 — committed** (recognize median, vs P1B committed HEAD):

| step | x1 | x2 | x4 | note |
|---|---|---|---|---|
| P1B HEAD | 61.5 | 128.9 | 276.5 | (re-measured baseline) |
| + EarleyItem `tuple.__new__` bypass | 58.3 | ~129 | 267 | skip Python `__new__` frame (later superseded by session 5) |
| + **prediction memoization** | 56.3 | 118.9 | 254.7 | `Column.predicted` set; skip re-seeding a predicted ref (dups 16%→9%) |
| + **skip-SPPF for recognize** | **43.7** | **94.2** | **190.2** | `ParseCtx.record_links`; recognition never reads the forest |

Net session 4: **recognize −29%/−27%/−31%** vs P1B HEAD; earley/lark 2.1–2.5× → 1.6–1.7×.
`parse` unchanged then (~78/170/341ms). Bonus: dropped `ParseCtx.col` (`column.index` subsumes it).

**Session 5 — committed: pure-engine records are now plain tuples** (vs session-4 HEAD 43.7/94.2/190.2):

| step | recognize x1/x2/x4 | parse x1/x2/x4 | note |
|---|---|---|---|
| **EarleyItem → plain `tuple`** (D+E) | **36.8 / 78.5 / 164.2** | 68 / 145 / 316 | single-alloc, native C eq/hash |
| + **Link → plain `tuple`** | ~37 / 78 / 167 | **64 / 140 / 300** | parse-path only (recognize skips links) |

Net session 5: **recognize −14…−17%, parse −15…−21%** vs session-4 HEAD; earley/lark recognize **1.34–1.43×**.
The win is *construction* (a tuple subclass is 2-alloc + subclass overhead; a bare tuple is 1-alloc,
2.7× faster on construct+set-ops microbench). Three pieces, **no casts**:
- **(D)** map family layered honestly: `IrMapping`/`IrMultiMap` are unbounded **containers**;
  `resolve`/`eval` (dispatch) moved onto `IrMap`/`IrTypeMap`. Lets containers hold plain tuples.
- **(E)** `AcceptingItem` returns the `SppfNode` (built once) — carries the item across the
  `eval` boundary as an honest `IrSelf`; de-dups re-wrapping in 4 consumers.
- `EarleyItem`/`Link` are plain-tuple aliases (positional fields, documented in `item.py`/`chart.py`).
  `SppfNode`/`ParseTree` **stay `IrSelf`** — they are walked.

**Dead ends (don't re-try):** slotted `IrSelf` item = **3.5× slower** (Python `__init__`/eq/hash
lose to native C tuple). Identity-hashing `EarleyItem` (`id(arm)`) = **+30%**. IR-tuple hash
caching infeasible (tuple subtype can't gain a slot; `__dict__` off the table). **The answer was
the opposite: make the item a *bare* tuple and fix the container typing, not cache on it.**
**Lesson: cProfile over-attributes to Python frames; measure wall-clock.**

**Next plain-tuple candidates:** none obvious left — `SppfNode`/`ParseTree` are walked (must stay
`IrSelf`); `ForestCtx` is a cursor. The two hot pure-engine records are done.

## Session 6 — committed: Leo's optimization (recognition is now O(n))

Right-recursive `*`/`+` synthetic rules made the completer re-walk the reduction chain per
column — confirmed **O(n²)** (`S = "a"*`: ms/N² flat ~0.37; N=1600 = **955 ms**). **Leo (1991)**
jumps a deterministic right-recursive reduction straight to its transitive (topmost) item:

| `S = "a"*` recognize | N=400 | N=1600 | N=6400 | scaling |
|---|---|---|---|---|
| before (O(n²)) | 58 ms | 955 ms | (~3.8 s) | ms/N² flat |
| **Leo (O(n))** | 3.4 ms | **~14 ms** | 59 ms | **µs/N flat ~8.5** |

**46× at N=1600.** No regression on ABNF (recognize 38.6/80.6/164.7 ≈ HEAD) — a cheap inline
gate (`len(waiters)==1 and last-symbol`, `waiters` already in hand) keeps Leo off normal
completions. **Recognition only** (`record_links` False); the `parse` path keeps the correct
SPPF completer untouched.

**IR-pure (the point that got it reverted once):** `LeoItem(IrLeaf)` node — the recursion is its
`resolve(chart, col, ref, cur)` **method** (plain args, no per-call boxing), `eval` the protocol
wrapper; per-column memo is `Column.leo`, an **`IrMultiMap`** (closed columns memoised, current
recomputed → no staleness). Not a free function, not a dict.

**Correctness:** the `_LEO_ENABLED` flag gates Leo so a **differential test** (Leo on vs off,
identical recognize) is possible — it caught two bugs (wrong determinism condition that skipped
non-last waiters → broke ABNF; the boxing regression). Battery: 5 small grammars + ABNF + 7
mutations, all identical. Flag **kept** as a kill-switch for a high-risk optimization. New bench
mode `--rightrec` is the asymptotic canary.

**STILL SUPER-LINEAR — the `parse` path.** Leo is recognition-only, so parsing right-recursion
still builds the O(n²) SPPF *and* its derivation walk recurses O(depth) — measured super-linear
(`S="a"*` parse µs/N 44→70→120) and it **stack-overflows at N≈400** (recursive `forest.__iter__`).
Two separable next steps:
1. **Leo + SPPF** (Scott 2008): record provenance for transitive items so derivations recover —
   makes `parse` O(n) too. The hard one (highest risk).
2. **Iterative forest walk**: convert `forest.py`'s recursive `__iter__`/`eval` to an explicit
   stack so deep `parse` stops crashing (independent of (1); fixes the overflow even before Leo+SPPF).

**Left to do:**
1. **Leo unit tests** — in progress (Sonnet): `LeoItem`/`resolve`/`_sole_candidate`, `Column.leo`,
   and the Leo-on-vs-off differential. Plus the still-pending session-3/4 coverage (`CharAccepts`,
   `ParseCtx.char_accepts`/`column`/`record_links`, `scannable_by_atom`/`predicted`, recognize-skips-SPPF).
2. **`parse`-path super-linearity** — Leo+SPPF and/or the iterative forest walk (above).

---

Continuation of the mapping cutover + engine round. This documents what landed,
what the mapping cutover **unlocks** from `zz_current_work/HANDOVER_round4.md`, and
the next avenues (Leo + Spike-2 S3 chief among them).

Benchmark: **`zzz_current_work/bench_parsing.py`** — Lark (`parsing/`) vs native
Earley (`parsing_2/`) on ABNF self-host at x1/x2/x4, warm-up + **interleaved**
sampling (drift hits all variants equally), min/median/stdev + earley/lark ratio.
Run `uv run python zzz_current_work/bench_parsing.py "<label>"` (or `--profile`).

---

## What landed this session

**1. Mapping cutover (`mapping.py` IS the former `mapping8.py`).** Slot-backed
`IrMapping`/`IrMap`/`IrTypeMap`/`IrMultiMap` over a single `_table` dict; `mapping8.py`
deleted; tests ported. Key property for everything below: **`IrMultiMap.__iadd__` is
now an O(1) direct `dict` write** (`_table.get` + assign/append) and **`__getitem__`
returns the LIVE bucket** (no `IrSeq` snapshot allocation). This is the exact
"make-viable" fix round-4 said S3 needed.

**2. Engine round (`ops.py`, `engine.py`).**
- EarleyItem field access → tuple unpack/index (descriptor `property(itemgetter)` was
  2.5× slower than raw tuple access). Applied in Predict/Complete/Scan/CloseColumn/
  Column.__iadd__.
- `CloseColumn` driver loop → `for item in column` (live list iterator picks up
  mid-pass appends; drops a `__len__`/`__getitem__` call per item).
- **Round-4 P1 (S1c) is essentially done here:** A (hoist `rules.resolve(ref)`, reused
  by nullable branch) ✅, C (drop `cast(Sequence[IrSelf], arm)`) ✅, D (avoid per-completion
  `IrSeq` alloc) ✅ *via the cutover live bucket*, **precompute empty-deriving arms** ✅
  (`NullableRules` now maps nullable `IrRuleRef` → its empty-deriving arms in an
  `IrMultiMap`; `Predict` iterates the precomputed list — exactly round-4's
  "key by the cheap IrRuleRef, return the arm list, no arm hashing").

**Results (ABNF self-host, vs original `mapping.py` baseline 94.3 / 121.0 ms):**

| stage | recognize | parse |
|---|---|---|
| original `mapping.py` | 94.3 ms | 121.0 ms |
| + mapping cutover | ~85 ms | ~110 ms |
| + engine round | **~69.5 ms** | **~95 ms** |
| **total** | **−26%** | **−21.5%** |

Gates: pylint 10.00, pyright 0, ruff clean, **1121 tests pass**, ABNF fixpoint True,
ambiguous=0. Uncommitted src: `engine.py`, `ops.py` (mapping/chart/forest/walk + tests
already committed during the session). Full session log:
`zz_current_work/MAPPING8_PERF_SESSION_2026-06-29.md`.

---

## What the mapping cutover UNLOCKS from round-4

`zz_current_work/HANDOVER_round4.md` + `SPIKE_char_indexed_scan.md` identified a ship
set. Status against the **new** mapping:

| round-4 item | status now |
|---|---|
| **P1 (S1c)** micro-wins A/C/D + precompute | ✅ **DONE** this session (B still open — see below) |
| **P2 (S2)** `Column.scannable` list | ⬜ not landed — ready, +6–8% ABNF, +3.5% suite |
| **Spike-2 S3** char→atom scan index | 🔓 **UNLOCKED** by the cutover — re-measure (was blocked only by slow `IrMultiMap`) |
| S3a Expand memoize (`normalize.py`) | ⬜ optional, +2–3% |
| P1 micro-win **B** (raw `_columns[col]`) | ⬜ not applied (tiny) |
| Spike-1 S2 (NNLR left-rec desugar) | deferred (helps only long reps) |
| Spike-1 S4 (conditional F1) | dead |

**Why S3 is unlocked.** Round-4 deferred S3 because its `scannable_by_atom: IrMultiMap`
did 7k terminal inserts/parse, and the *old* `IrMultiMap.__iadd__` was **3.2× a plain
dict** (Python `setdefault` + the tuple-element `_table` property indirection) — that
insert overhead regressed short parses (crossover ~400 chars). The make-viable path was
literally *"subclass `IrMultiMap` as `ColumnScanIndex` overriding `__iadd__` to write
`_table` directly."* **The cutover already made `__iadd__` a direct `_table` write and
`__getitem__` a live-bucket read (no `IrSeq` alloc).** So the base `IrMultiMap` now does
what `ColumnScanIndex` was going to do by hand — the short-parse regression should be
gone, with no subclass needed.

---

## Next avenues (recommended order)

### 1. P2 — `Column.scannable` (Spike-2 S2)  ·  ready, low risk
Add `scannable: list[EarleyItem]` to `Column.__slots__`; file terminal-facing items at
insert time (in the existing `Column.__iadd__` symbol branch, the `else` of the ruleref
check); `ScanColumn.eval` iterates `column.scannable` and drops the
`dot < len(arm)` guard. ~15 lines `chart.py`, 2 lines `engine.py`. −67% `MATCHES` calls,
**+6–8% ABNF, +3.5% suite**, zero regression. Same mutable-chart purity as `_items`/
`waiting`. Spec: `SPIKE_char_indexed_scan.md` §Strategy 2.

### 2. S3 — char→atom scan index  ·  the unlocked win, re-measure first
Build on P2: `Column.scannable_by_atom: IrMultiMap` (terminal atom → items facing it,
filed at insert) + `ParseCtx.char_accepts: IrMultiMap` (char → accepting atoms, lazily
populated via a `CharAccepts(IrLeaf)` that extracts terminal atoms once/parse).
`ScanColumn` becomes `for atom in char_accepts[char]: for item in
col.scannable_by_atom[atom]: advance` — **`MATCHES.eval` is never called** (0 calls).
+12–13% ABNF in round-4.
- **First step:** lift the spike code, port it onto the NEW `IrMultiMap`, and **re-run
  the full suite wall-clock** (round-4's regression canary). With the cutover's cheap
  `__iadd__`/live `__getitem__`, the short-parse regression should be gone — confirm.
- If a residual hot-path cost remains, the `._table`-direct reads the spike used are now
  the *public* live-bucket `__getitem__` (no `IrSeq` wrapper), so they may no longer be
  needed. Keep the path pure (`IrMultiMap`, not a dict attr).
- Spec: `SPIKE_char_indexed_scan.md` §Strategy 3 + §"To make S3 viable" (option 1 is now
  free). Prototype: worktree `agent-a084e690a0ecd5435` (if still on disk).

### 3. Leo's optimization (Joop Leo, 1991)  ·  the big algorithmic lever
Round-4's Spike-1 concluded the win is **not** changing recursion direction by
desugaring (left-rec/NNLR both pay ~1.3–1.37× at N=0, the AH nullable tax, and the suite
is 0–2-item-rep dominated). **Leo's optimization is the principled alternative:** it makes
right-recursive (and other deterministic-reduction) grammars **O(n) instead of O(n²)**
*without touching the grammar*, by detecting deterministic reductions and storing a single
**transitive (topmost) item** per `(rule, position)` so the completer follows one Leo item
instead of walking a chain of intermediate completions.
- **Where:** the completer (`Complete` in `ops.py`) + a per-column Leo-item index
  (another mutable-chart structure — fits the `IrMultiMap`/slot precedent). Predict/Scan
  largely unchanged.
- **Why now:** right recursion is where the engine is super-linear; the profile is flat,
  so the next step-change is algorithmic, not micro. Pairs naturally with the SPPF (Leo
  items still record provenance — see Scott 2008 §on Leo + SPPF for keeping derivations
  correct).
- **Empirical hook:** `bench_parsing.py` already shows the gap *widening* with size —
  earley/lark goes 2.6→2.9× (recognize) and 3.7→4.2× (parse+reduce) across x1→x4. A
  flat O(n) engine would hold a constant ratio; the climb is the super-linearity Leo
  targets. (Confirm with a deeper right-recursive grammar — ABNF self-host is mild.)
- **Risk:** the highest of these; needs careful correctness work (deterministic-reduction
  detection, SPPF link bookkeeping for Leo items, interaction with nullable AH advances).
  Recommend a dedicated spike with the ABNF fixpoint + ambiguity canaries, and a
  right-recursion-heavy benchmark grammar (the ABNF self-host alone won't show the O(n²)→
  O(n) gap; add a deep right-recursive grammar at N=x1/x2/x4).

### 4. Micro / optional
- **P1 micro-win B:** `Predict`/`Complete` read `ctx.chart._columns[ctx.col]` directly on
  the hot path (skip `Chart.__getitem__`'s growth check) when the column is known to
  exist. Tiny; internal sibling-module shortcut (flag it).
- **S3a (Expand memoize, `normalize.py`):** share synthetic rules across identical
  expansions. +2–3%, 53→46 rules. Composable, pure.
- **Broader (measure-first, likely small):** caching IR-tuple hashes in `ir/base.py`
  (the flat profile is now set/dict ops on EarleyItem + IrScalar.__eq__); the `_table`
  dispatch coupling in `IrDispatch.eval` (+1.4%, soft encapsulation break — see session
  log). Both higher-effort for uncertain payoff.

---

## Rejected this session (don't re-try blindly)
- **`Column.__iadd__` add-first (len-delta) trick** — measured −1.5% (EarleyItem hash is
  cheap; the extra `len()` calls cost more). Same shape as round-4's Finding C / the
  adversarial-review `__iadd__` EAFP rejection. The `in`-then-`add` form is optimal.
- **Option-4 `IrMapping` subclasses `dict`** — elegant (node IS its dict) but ~2.5%
  SLOWER overall: dict-subclassing taxes the hotter `IrMultiMap` ops more than it saves
  on dispatch lookup. Slot-backed design stays. (Detail in the session log.)

---

## Constraints (unchanged, from round-4)
IrSelf purity: behaviour on classes via `eval`/dunders; per-parse mutable state in a
cursor (`ParseCtx`); prefer a class being an `IrMultiMap` over a `dict` attr. No
`# type: ignore` / `# noqa` / `# pylint: disable`; no `exec`/`eval`. No grammar-specific
hardcoding. **ABNF fixpoint + `is_ambiguous` are the canaries.** Suite stays green
(currently 1121). Never `git commit` (user lands). Raw `_table`/`_columns` access is an
internal sibling-module shortcut — flag and justify by hot-path numbers.

## Validation recipe
```
uv run pytest tests/ -q                            # full suite (expect all green)
uv run python zzz_current_work/bench_parsing.py "<label>"   # lark vs earley, x1/x2/x4
# fixpoint + ambiguity canary:
uv run python -c "from lexic.grammars import ABNF_FLAVOUR; \
from lexic.grammars.abnf_2 import ABNF_GRAMMAR; from lexic.parsing_2 import recognize, is_ambiguous; \
from lexic.parsing_2.normalize import normalize; g=normalize(ABNF_GRAMMAR); \
t=str(ABNF_FLAVOUR.apply(ABNF_GRAMMAR)); \
print('rec',recognize(g,t),'fixpoint',str(ABNF_FLAVOUR.apply(ABNF_GRAMMAR))==t,'amb',is_ambiguous(g,t))"
```
For Leo / S3, add a **deep right-recursive** grammar and a **long-input** (x2/x4) sweep —
the ABNF self-host is short-parse-dominated and won't surface the asymptotic wins alone.
```
