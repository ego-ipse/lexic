# ⛔ ROUND-3 CORRECTION — F1 is net-SLOWER on the suite; root cause found (2026-06-26)

**F1 (left-recursive `*`/`+`) was implemented and is measurably slower across the
full suite (3/3 runs).** The round-2 SHIP recommendation below is WRONG for the
real workload. Root cause is established with deterministic counts + one-process
noise-free timing:

**Why.** Left desugaring makes the synthetic repetition rule **nullable AND
self-predicting**:

```
right:  R = "" / unit R      left (F1):  R = "" / R unit
```

Entering a left-recursive repetition pays a fixed tax every time: `R` is nullable,
so predicting it fires the expensive **Aycock-Horspool branch** in `Predict.eval`
(`ops.py:148-160`), and the recursive arm `·R unit` **re-predicts `R` itself** —
a second nullable-predict. Right's arm `·unit R` faces a terminal first, so it
neither self-predicts nor doubles the nullable-predict. This tax is per
repetition-*occurrence*, i.e. **linear in input**, and the O(n²)→O(n) completer
win only repays it once a repetition matches **≥2 elements**.

**Data (one process, deterministic counts + median timing):**

| N matched | right items/compl/nullpred/links | left items/compl/nullpred/links | time left/right |
|---|---|---|---|
| 0 | 4 / 2 / 1 / 1 | 5 / 2 / 2 / 2 | **1.32× slower** |
| 1 | 9 / 5 / 2 / 4 | 8 / 4 / 2 / 5 | 1.03× slower |
| 2 | 15 / 9 / 3 / 8 | 11 / 6 / 2 / 8 | 0.86× (crossover) |
| 4 | 30 / 20 / 5 / 19 | 17 / 10 / 2 / 14 | 0.67× |

Real ABNF self-parse: F1 = **+23% nullable-facing predicts** (3652→4479 at x1),
the single most expensive op (inside the #1 hotspot `Predict.eval`). Reduce tree
is byte-identical (so reduce is unaffected; the round-2 "reduce regressed" came
from a broken `min(parse+reduce)−min(parse)` metric).

```
cost_right ≈ a·L + b·L²     cost_left ≈ a'·L   (a' > a)
```

F1 deletes `b·L²` but **raises the linear coefficient**. The suite is dominated by
repetitions matching 0–2 items (`*WSP`, `1*DIGIT`, short lists), so it pays the
higher base far more often than it collects the quadratic dividend → net slower.

Measurement harnesses (main checkout, untracked): `z_current_work/crossover.py`
(one-process crossover N=0..8), `z_current_work/count_abnf.py` (deterministic
op/nullpred counts), `z_current_work/reduce_isolated.py` (isolated phase timing,
median+stdev). **Do not trust `bench_parsing.py`'s `reduce=` column** (diff of
minimums). ABNF fixpoint (`run_earley` prints `Earley fixpoint == ABNF_GRAMMAR`)
is the correctness canary.

**Round-3 program (two parallel worktree spikes, in progress):**
1. **Lower the base cost** so left-recursion never loses: cheaper AH branch
   (helps both shapes), non-nullable left-rec desugaring for `*`, memoize
   `Expand.eval`, and/or conditional F1. Goal: ≥ right on the suite, keep the
   asymptotic win.
2. **Character-indexed scanning**: memoize char → accepting-terminal subset so
   `ScanColumn` only advances items whose terminal can match the current char,
   instead of calling `Matches` on every item.

The round-2 body below is retained for context but is **superseded** wherever it
recommends F1 as a ship.

---

# Handover — `parsing_2` performance, exploratory round 2 (2026-06-26)

**Status:** four parallel exploratory agents ran (each in an isolated worktree),
prototyping and **measuring** contenders rather than re-deriving the prior plan.
This document is the synthesis, the cross-report reconciliation, and the
sequenced program. Source reports live beside this file:

- `01_f1f2_decision.md` — F1 vs F2(Leo) vs F1+F2 vs F3 vs Marpa, **all prototyped
  and benchmarked across three workloads** (the rewrite; the first attempt only
  re-validated F1 and is superseded).
- `02_remaining_opts.md` — re-validation of F3/F4/F5/scan-guard/#5 on the
  post-SPPF engine.
- `03_new_opts.md` — four NEW micro-findings (A/B/C/D) + one discarded (E).
- `04_radical.md` — radical bets; confirms F1 ceiling, terminal-rep specialization idea.

All work was throwaway (worktree prototypes / monkey-patches); **no production
code was modified.** The full suite is still green at HEAD (1126 passed, ABNF
fixpoint included). Prototype scripts referenced below
(`z_current_work/f1f2_bench.py`, `leo_waiter_analysis.py`, `radical_proto.py`)
live in the agents' worktree branches if you want to re-run them.

---

## TL;DR — the program

| # | Action | Payoff (measured) | Purity | Effort | Status |
|---|--------|-------------------|--------|--------|--------|
| 1 | **F1** — left-recursive `*`/`+` desugaring (`normalize.py`) | O(n²)→O(n); 110× at N=800 on terminal rep; 20% at 14.7 KB ABNF, unbounded asymptotically | ✅ | 2 lines + 2 test updates + docstrings | **SHIP** |
| 2 | **Micro-basket** — C (free), A, B, D/F4, scan-guard | ~11–15% recognize combined (re-measure post-F1) | ✅ (2 need a small public accessor) | small | After F1, re-measure |
| 3 | **F3** — opt-chain / nullable-inflation redesign (`normalize.py`) | ~10% recognize ceiling | ✅ | **large** | Defer; re-profile after F1 |
| — | **F2 (Leo)** | only fix for *hand-authored* right recursion; F1 doesn't touch it | ✅ | **3–4× F1's size** | **Defer, with conditions** |
| — | **F5 predict-dedup** | −6 to −7% (negative) | — | — | **Closed — dead end** |
| — | **#5 dispatch collapse** | 14–18% but destroys "dispatch-table-IS-the-engine" | ❌ | — | **Closed — purity** |
| — | **Marpa / full rewrite** | no payoff beyond F1 | — | huge | **Not recommended** |

**Key correction to the prior round:** the `reduce.py` child-order reversal that
the pre-SPPF reviews insisted F1 needs is **NOT needed** — see below. Shipping it
would *break* the round-trip.

---

## 1. F1 — left-recursive desugaring (SHIP)

**The change** (`src/lexic/parsing_2/normalize.py`, `Expand.eval`, ~lines 172–175):

```python
if lo == 0:    # *  →  X = "" / X unit   (was: "" / unit X)
    body = IrAlternation(IrSequence(), IrSequence(ref, unit))
elif lo == 1:  # +  →  X = unit / X unit (was: unit / unit X)
    body = IrAlternation(IrSequence(unit), IrSequence(ref, unit))
```

`?`, bounded counts, `m*` (lo>1), and `OptChain` are **not** the O(n²) source and
stay unchanged.

**Why it works (measured, report 01):**

| workload | metric | right-rec | left-rec (F1) |
|---|---|---|---|
| terminal rep `1*("A")`, N=400 | max_col | 404 | **3** |
| terminal rep, N=400 | total items | 81,803 | **1,203** (68×) |
| terminal rep, N=800 | parse time | 812 ms | **7.3 ms** (110×) |
| terminal rep scaling | O(n^k) | n^~2.0 | **n^1.0** |
| ABNF self-parse, x8 (7.4 KB) | max_col | 283 | **54** (constant) |
| ABNF self-parse, x16 (14.7 KB) | recognize | 1976 ms | 1648 ms (**20%**, growing) |

The ABNF benchmark shows ~0–1% at 920 chars (the O(n²) term is only ~8% of work
at that size) but the win is asymptotically unbounded and already 20% at 14.7 KB.
Real user grammars passing through `normalize.py` get the full O(n²)→O(n).

### The reducer reversal: NOT needed (resolved)

The three pre-SPPF reviews claimed left recursion reverses child order in
`ParseTree.kids`, requiring `ResolveChildren` (`reduce.py`) to reverse the
synthetic splice. **This is false on the current engine.** The SPPF rewrite
replaced the eager tree builder; `forest.py` `FamilyPrefixes.__iter__` always
assembles kids as `IrSeq(*prefix, child)` — predecessor-prefix first, consumed
child last — i.e. dot-advance (left-to-right source) order *regardless of
recursion direction*.

**Evidence:** two agents ran the actual `parse+reduce` ABNF self-host **fixpoint**
with F1 and no `reduce.py` change → `earley_ir == ABNF_GRAMMAR: True`. The lone
dissent (report 04) asserted the reversal is needed but **only tested
recognition, never parse+reduce** — so it carries no weight against a passing
fixpoint. *Implementer: re-run the fixpoint after the change to confirm; do **not**
add a reversal.*

### Test impact

- 2 failures, both in `tests/unit/lexic/parsing_2/test_normalize.py`
  (`test_desugar_star_second_arm_has_atom_and_self_ref`,
  `test_desugar_plus_second_arm_has_atom_and_self_ref`) — structural checks of
  arm ordering. Update to assert left-recursive order (`items[0]` = self-ref,
  `items[1]` = unit).
- Update docstrings of `Expand` and `DesugarQuantifiers` (they say "right-recursive").
- `tests/performance` rep-grammar baseline flips quadratic→linear; update the
  "O(n²) expected" assertion/comment.
- ABNF fixpoint (`test_abnf_2.py`) stays green.

---

## 2. Micro-win basket (after F1, re-measure)

All purity-preserving. Reports 02 + 03. Standalone deltas on x4 recognize:

| id | finding | standalone | notes |
|---|---|---|---|
| **C** | remove `cast(Sequence[IrSelf], arm)` in `Predict.eval` (`ops.py:130`) — it subscripts `Sequence[IrSelf]` at runtime, hitting `typing._tp_cache` ~46k×/run | **~2.7%** | **pure win, zero risk** — `arm` is already an `IrSequence`; the cast is a runtime no-op. Do this regardless. |
| **A** | hoist the double `ctx.rules.resolve(ref)` in nullable `Predict` (resolve once, reuse `arms`) | **~3.5%** | pure local hoist |
| **B** | `Chart.__getitem__` → raw `_columns[i]` in `Predict`/`Complete` (~162k hot calls; 45ns→32ns) | **~5%** | add a public `Chart.columns` property to avoid private-slot access from `ops.py` |
| **D / F4** | `Complete.eval` reads `waiting[rule]` via `IrMultiMap.__getitem__`, which allocates a fresh `IrSeq` snapshot per completion (now the #1 `IrTuple.__new__` source). Read `_table.get()` + snapshot only when `origin == col` | **~5%** | add `IrMultiMap.get(key) -> tuple` to avoid private `_table` access. Snapshot only needed when `origin == col` (self-completion grows the bucket). |
| **scan-guard** | `ScanColumn` calls `Matches` on rulerefs 67% of the time (no-op); guard `type(atom) is not IrRuleRef` before `MATCHES.eval` | **5–7%** | one-liner, pure |

**Combined:** report 03 measured A+B+C+D = **1.11× recognize / 1.07× parse+reduce**
(fixpoint holds). Report 02 measured F4+scan-guard = 8–10% recognize. Expect the
full basket ≈ 11–15% recognize with overlap.

**Interaction with F1 (must re-measure):** F1 cuts completion count ~80×, so the
`Complete`-path wins (D/F4) shrink; the `Predict`-path wins (A/C) and scan-guard
largely persist. Re-profile after F1 and keep what still pays.

**Discarded:** Finding E (precompute empty-arm set) measured **8% slower** — drop.

---

## 3. F3 — opt-chain / nullable-rule inflation (defer, large)

Normalized ABNF has 53 rules / 88 arms (from 34 / 50); 15 are nullable synthetics
(11 opt-chains `[0,2]`, 4 simple `?`). Aycock-Horspool fires 14,608×/x4 parse
(24% of predicts). Skipping AH for all 15 → **~11.8%** (the upper bound). But:

- The simple-`?` fold (4 rules) is only ~1.7% — not worth a standalone change.
- The opt-chain prize (~10%) needs a real `normalize.py` redesign: unroll `{lo,hi}`
  as `lo` mandatory + `(hi-lo)` optional refs at the *parent* arm, instead of
  minting nullable recursive sub-rules.

F1 doesn't reduce predict overhead, so F3 stays independently useful — but it's a
large change. **Defer; re-profile after F1** (completion count drops, so predict/AH
becomes a larger share — F3's relative value may rise).

---

## F2 (Leo) — defer, with conditions (the real F1/F2 finding)

Report 01 **actually prototyped Leo** and surfaced the nuance the prior round missed:

- The Leo precondition (single deterministic waiter) holds widely — 95–99.5% of
  completions on repetition workloads. But **single-waiter detection ≠ speedup.**
  Leo only helps with the *full transitive-chain* mechanism that skips intermediate
  columns; as prototyped (detection + bookkeeping, no chains) it is **~7% slower**
  and produces **identical item counts** to baseline.
- **What F2 uniquely buys:** Leo fixes *hand-authored* right-recursive user grammars
  (`X = Y X / Y`, workload c), which **F1 cannot touch** — F1 only rewrites the
  `normalize.py` path. Measured: workload (c) is O(n²) today (~3.9×/doubling) and
  neither F1 nor partial-F2 fixes it; only full Leo would.
- **Cost:** full Leo needs per-column transitive items with cross-origin chain
  propagation **plus** SPPF link-decompression in `FamilyPrefixes` — ~3–4× the size
  of F1, with forest-read correctness implications.

**Decision: defer.** Lexic's current workload is machine-generated grammars through
`normalize.py`, which F1 fully fixes. Revisit Leo only if (a) users report O(n²) on
hand-authored right-recursive grammars, or (b) profiling a larger real grammar shows
residual super-linearity from user rules.

---

## Closed / not recommended

- **F5 predict-dedup (per-column already-predicted set):** report 02 measured
  −6 to −7% (careful, two variants); report 04 neutral. `Column.__iadd__`'s `_seen`
  dedup is already cheaper than the set bookkeeping. Report 01's "~1–2% win" claim
  is within noise and outweighed. **Dead end.**
- **#5 full dispatch collapse:** grew to 14–18% post-SPPF (because SPPF removed
  `BuildTree`, so dispatch overhead is a larger share of a smaller total) — but it
  collapses `Predict`/`Complete`/`Scan` into one procedural loop, destroying the
  "dispatch-table-IS-the-engine" invariant. The purity-preserving subset (basket
  item 2) captures ~55–60% of the gain with no design cost. **Do not pursue.**
- **Marpa / full rewrite:** no payoff beyond F1 for the normalize path; huge cost.

---

## Future idea (not scoped here)

Report 04: **terminal-repetition specialization** — detect purely-terminal
repetitions (`1*("A")`) at normalize time and emit them as a char-range scanner
loop rather than Earley items. Potentially 2–4× on terminal-heavy grammars. This
is a semantic extension, not a substrate change. Worth a future spike if terminal
repetition shows up in real profiles.

---

## On the IrSelf substrate ceiling (honest framing, report 04)

After F1, the IrSelf engine runs simple-repetition grammars at ~10 µs/char —
**3× faster than Lark** (~30 µs/char). The substrate is **not** the bottleneck.
The residual ~4–5× gap on *complex* grammars (ABNF self-parse) is the fundamental
cost of general Earley+SPPF in Python vs Lark's C-accelerated LALR, dominated by
per-item churn (`IrTuple.__new__`, `Column.__iadd__`, `EarleyItem.__new__`) across
many columns — not by recursion direction. Closing that fully would require either
the dispatch collapse (rejected on purity) or grammar specialization (future idea).
F1 + the micro-basket is the worthwhile envelope within the constraints.

---

## Constraints (unchanged, apply to all of the above)

- Keep IrSelf purity: eval/dispatch + logic on classes; per-parse mutable state in
  a cursor; prefer making a class an `IrMultiMap` over a `dict` attr. Any deviation
  needs written justification (the #5 collapse is the canonical *not-worth-it* case).
- No `# type: ignore` / `# noqa` / `# pylint: disable`; no `exec`/`eval`.
- Full suite green; ABNF fixpoint is the canary.

## Suggested implementation order

1. **F1** (+ test/docstring updates) — confirm ABNF fixpoint, no `reduce.py` change.
2. **Finding C** (free, zero-risk) — land with or right after F1.
3. **Re-profile** post-F1, then land the surviving micro-basket (A, B via
   `Chart.columns`, D/F4 via `IrMultiMap.get`, scan-guard) — measure each against
   the post-F1 profile, keep what pays.
4. Re-profile; decide on **F3 opt-chain redesign** with fresh numbers.
5. Leave **F2/Marpa/F5/#5** closed unless their named conditions trigger.
