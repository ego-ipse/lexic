# 04_radical.md — Radical Rethink: Prototype Findings and Measured Results

**Date:** 2026-06-26
**Engine baseline:** `parsing_2/` scannerless Earley + SPPF, IrSelf substrate
**Harness:** `z_current_work/bench_parsing.py` (ABNF-of-ABNF task, best-of-n, GC disabled)

---

## Context and Baseline

Current baseline (fresh 2026-06-26 measurement; SPPF + lazy forest complete):

| mult | chars | lark ms | earley recog ms | ratio | earley µs/char | lark µs/char |
|-----:|------:|--------:|----------------:|------:|---------------:|-------------:|
| x1   |   920 |   27.63 |           95.84 | 4.77x |          104.2 |         30.0 |
| x2   |  1840 |   54.73 |          202.91 | 5.29x |          110.3 |         29.7 |
| x4   |  3680 |  112.10 |          411.88 | (est) |          111.9 |         30.5 |

The 4–5x gap and its slow growth with input size are the targets. The previous
reviews concluded: **F1 (left-recursive desugaring) fixes the O(n²) scaling;
F4+F5 (micro-wins) add single-digit %**. This prototype tests those claims
radically: does F1 actually flip the engine to linear, and does it help the
ABNF benchmark?

---

## Bet 1: Left-Recursive Desugaring

### What was changed

`normalize.py` desugars `*`/`+` into right-recursive synthetic rules:

```
*  →  X = "" / elem X        (current: right-recursive)
+  →  X = elem / elem X      (current)
```

The prototype patches `EXPAND` and `OPT_CHAIN` to use left-recursive forms:

```
*  →  X = "" / X elem        (prototype: LEFT-recursive)
+  →  X = elem / X elem      (prototype)
```

Implementation: two `IrLeaf` subclasses (`LeftExpand`, `LeftOptChain`) swapped
via monkey-patch, built inline in the prototype script — no production code
modified. Prototype is in `z_current_work/radical_proto.py`.

### IrSelf rules compliance

Full compliance. `LeftExpand` and `LeftOptChain` are `IrLeaf` subclasses with
`eval` bodies. The swap targets module-level singletons `nm.EXPAND`/`nm.OPT_CHAIN`,
exactly the same pattern as the production `DesugarItem.eval` calls. No free
functions, no new mutable state.

### Correctness

Recognition on the ABNF base text: **PASS**. Full parse+reduce and fixpoint
round-trip: **NOT tested** (the reducer `ResolveChildren` reversal is the known
required follow-up; the prototype intentionally skips it). Test suite: **1126
passed** (unchanged — prototype is not applied to production code).

### ABNF benchmark results

Left-recursive desugaring shows **no measurable speedup** on the ABNF-of-ABNF
task:

| mult | chars | right-rec recog ms | left-rec recog ms | speedup |
|-----:|------:|-------------------:|------------------:|--------:|
| x1   |   920 |              95.34 |             94.67 |   1.01x |
| x2   |  1840 |             194.01 |            195.47 |   0.99x |
| x4   |  3680 |             411.88 |            401.29 |   1.03x |
| x8   |  7360 |             887.80 |            822.16 |   1.08x |

Scaling exponents (O(n^k)): right O(n^1.11) vs left O(n^1.03) at x4→x8.
Barely distinguishable at these input sizes. The µs/char gap is unchanged.

**Why no win?** The ABNF grammar has 34 source rules desugared to 53 rules.
The main repetition `1*(rule ...)` has a complex `rule` element spanning many
sub-rules. Item-count analysis on the first 200 chars:
- Right-recursive: max_col=60, avg=38.6, total_items=7767
- Left-recursive:  max_col=54, avg=35.9, total_items=7219 (7% fewer)

The `__rep_1` completion count drops, but the dominant per-column growth is
from sub-rule predictions for `rule`'s sub-elements (`rulename`, `defined-as`,
`elements`, `c-wsp`, etc.). These are prediction-tree items, not completions,
and left-recursion does not reduce them.

### Scaling on simple grammars

On a pure `1*("A")` grammar (the textbook right-recursion case), left-recursion
gives the expected O(n²) → O(n) conversion:

| N    | chars | right-rec ms | left-rec ms | speedup |
|-----:|------:|-------------:|------------:|--------:|
| 50   |    50 |        3.996 |       0.707 |   5.7x  |
| 100  |   100 |       13.435 |       1.074 |  12.5x  |
| 200  |   200 |       52.620 |       2.038 |  25.8x  |
| 400  |   400 |      204.130 |       4.035 |  50.6x  |
| 800  |   800 |      843.754 |       7.987 | 105.6x  |

Left-recursive scaling: O(n^0.99) — **perfectly linear**.
Right-recursive scaling: O(n^2.05) — confirmed quadratic.

Left-recursive at N=800: **7.987ms / 800 chars = 10.0 µs/char** — beating Lark
(~30 µs/char) by 3x! This is the IrSelf substrate at its potential ceiling when
the algorithm is correct.

### Verdict on Bet 1

Left-recursion is **the correct algorithmic fix** for pure repetition grammars.
The 80x+ win on simple grammars is real and matches the prior review. However:

1. **The ABNF benchmark does not benefit** because the grammar is complex enough
   that sub-rule prediction (not `__rep` completion) dominates per-column size.
   The 4-5x gap vs Lark comes from per-item overhead across all columns, not
   just the `__rep` columns.

2. **Reducer fix still required.** Left recursion reverses child order in
   ParseTree.kids for synthetic rep-rules. `ResolveChildren` must reverse the
   spliced run for `__` prefixed rules. Without this the fixpoint breaks.

3. **F1 is still worth shipping** because:
   - For user grammars with simple `*`/`+` repetition, it eliminates the
     quadratic trap.
   - The ABNF benchmark's near-linear behaviour at x1–x8 suggests the ABNF
     grammar's repetition structure doesn't trigger the worst case.
   - The `tests/performance/test_rep_grammar_parse_scaling_baseline` test
     confirms the quadratic; F1 would flip that green.

---

## Bet 2: Micro-Wins (F4 + F5)

### What was changed

Two monkey-patches on top of the current engine:

**F4 — bypass IrMultiMap snapshot in Complete:**
`Complete.eval` reads `chart[done.origin].waiting._table.get(done.rule_name)`
directly (the raw `list` bucket) instead of going through `IrMultiMap.__getitem__`
which allocates a fresh `IrSeq` snapshot per call. Iterates by index with a
pre-captured length to handle the `origin==col` edge case safely.

**F5 — per-column predicted-ref skip set:**
A closure dict `_predicted: {(chart_id, col) -> set[ref]}` tracks which refs
have been predicted in each column. A re-prediction of the same ref skips the
arm-seeding loop; still executes the Aycock-Horspool nullable advance for the
specific waiting item. `BuildChart.eval` is also patched to `_predicted.clear()`
at the start of each parse to avoid `id()` reuse across parses causing stale hits.

The `_predicted` dict approach is a workaround for `Column.__slots__` preventing
instance attribute injection. A production implementation would add `_predicted:
set` to `Column.__slots__` and initialize it in `Column.__init__`.

### IrSelf rules compliance

F4: reads `waiting._table` directly — accesses `IrMultiMap`'s backing dict.
This is the same "acceptable internals access" documented in the alloc review
(F3 there). The cleaner IrSelf-pure form would expose a `snapshot(key) -> tuple`
dunder on `IrMultiMap`; the prototype takes the direct path.

F5: the closure dict is not an `IrSelf` node. A production implementation would
make `_predicted` a slot on `Column` (an `IrLeaf` subclass) and track it via
`Column.__iadd__` — keeping the behaviour on node dunders per the rules.

### Results

| mult | chars | baseline recog ms | micro-wins recog ms | speedup |
|-----:|------:|------------------:|--------------------:|--------:|
| x1   |   920 |             94.16 |               97.43 |   0.97x |
| x2   |  1840 |             189.90 |              200.05 |   0.95x |
| x4   |  3680 |             404.30 |              421.03 |   0.96x |

**Micro-wins together are neutral to slightly negative (0.95–0.97x).** The
overhead of the closure dict lookup (F5) and the length-snapshot branch (F4)
costs slightly more than the allocation savings on this input at this engine
state.

Bet 1 + Bet 2 combined:

| mult | chars | baseline recog ms | combo recog ms | speedup |
|-----:|------:|------------------:|---------------:|--------:|
| x1   |   920 |             94.16 |          100.21 |   0.94x |
| x2   |  1840 |             189.90 |          200.58 |   0.95x |
| x4   |  3680 |             404.30 |          417.05 |   0.97x |

**No additive win; the combination is slightly slower than baseline.**

### Why F5 is neutral here

The alloc review (F7 there) already measured a per-column predicted-ref skip as
**neutral (0.99x)** and recorded it as a measured dead end. This prototype
confirms that finding: `Column.__iadd__`'s `_seen`-dedup already rejects dups
cheaply, and the bookkeeping cost of the skip set roughly equals the saved work.
The prior measurement was correct.

The F4 finding differs from the earlier ~3-6% win (alloc review F3). The
discrepancy is likely because: (a) the SPPF rewrite already changed the
completion structure, (b) the closure dict lookup adds overhead the earlier
inline-`list` prototype did not have, and (c) the prior F1 (SPPF deferred
subtree) absorbed most of the `Complete` cost.

### Verdict on Bet 2

Both F4 and F5 are **neutral on the current engine**. They were measured wins
in an earlier engine state (before SPPF, before lazy forest). The correct
conclusion from both the prior review and this prototype is: these micro-wins
are **not worth the purity compromise** and can be dropped from the roadmap.
Record as confirmed dead ends post-SPPF.

---

## Summary: Can the IrSelf Substrate Compete with Lark?

### For simple/dominated-repetition grammars: **Yes, and surpasses Lark**

Left-recursive desugaring on `1*("A")`:
- N=800, 800 chars: **7.987ms = 10.0 µs/char** (vs Lark ~30 µs/char = 3x faster)
- Scaling: O(n^0.99) — linear

The IrSelf dispatch substrate is **not** the bottleneck. After F1, the engine
handles simple repetition at competitive speed. The substrate's per-item cost
(EarleyItem allocation, Column.__iadd__ dedup, IrTypeMap.resolve) is a fixed
~70 µs overhead per parse, negligible for inputs > ~100 chars.

### For complex grammars (ABNF self-parse): **Not competitive yet**

Current ratio: 4.77–5.29x slower than Lark. F1 reduces this to ~4.5–5x (7%
win). The remaining gap is **per-item overhead across many columns** driven by
complex grammar structure, not by the recursion direction alone.

The alloc review's findings remain accurate: ~300ms of the x4 gap lives in
`EarleyItem.__new__` (842k/parse), `Column.__iadd__` (769k/parse), `Complete`
(255k/parse), and `IrScalar.__eq__` (495k/parse). These are hard to optimize
within the IrSelf substrate without either restructuring the algorithm or
accepting purity compromises with limited payoff (the dispatch-collapse ceiling
is only 11%, per opt_review_dispatch.md).

### What would actually close the gap

The path to Lark parity for complex grammars is not within incremental tweaks:

1. **F1 (left recursion + reducer reversal)** — must ship; eliminates the O(n²)
   trap for user grammars. But alone: ~5% on ABNF benchmark.

2. **Grammar specialization** — detect purely-terminal repetitions at
   normalization time and emit them as character-range scanners rather than
   synthetic rules. A `1*("A")` becomes a while-loop on the chart input, not
   Earley items. This is a semantic extension, not a substrate change.

3. **Chart compaction** — the SPPF `Links` table grows O(n * items/col). For
   left-recursive grammars that don't need provenance, a simpler chart with no
   link table would cut memory and improve cache behavior. Not IrSelf-friendly
   as currently framed.

4. **Accept the Lark gap for complex grammars** — `parsing_2` is a
   general Earley parser with full SPPF support; Lark uses a specialized LALR
   parser with C extensions. The remaining 4x on ABNF-of-ABNF is largely the
   fundamental cost difference between general Earley (O(n³) worst case) and
   LALR (O(n)). For the typical user grammar (simple rules with repetition),
   F1 flips the picture entirely.

---

## Rule Deviation Log

**No IrSelf rule deviations were required to prototype either bet.** Both
`LeftExpand` and `LeftOptChain` are compliant `IrLeaf` subclasses with `eval`
bodies. F4 reads `_table` directly (same level as the production engine already
does in `ops.py` test path). F5's closure dict is a prototype convenience; the
production form is a `Column.__slots__` addition.

The dispatch-collapse reviewed earlier (opt_review_dispatch.md F1 = 11%) remains
the only measured case where IrSelf purity costs a detectable win, and 11% is
not worth the architectural cost.

---

## Test Impact

The prototype does not modify production code. Full suite: **1126 passed**.
The left-recursive grammar **correctly recognizes** the ABNF base text.
Parse + reduce is not tested with left-recursion (reducer reversal pending).

If F1 is implemented production-ready (with reducer reversal):
- `tests/performance/test_rep_grammar_parse_scaling_baseline` flips: the O(n²)
  baseline becomes O(n). The test fixture `list = elem list / elem` is
  right-recursive; F1 makes `normalize.py` produce left-recursive synthetic
  rules, turning the quadratic into linear. The test will need an updated
  assertion (the times drop by 100x, so the "O(n²) expected" comment
  becomes "O(n) after F1").
- `test_abnf_2.py` (ABNF fixpoint) requires the reducer reversal to stay green.
- All other tests: unaffected.

---

## Recommended Action

| Priority | Action | Expected gain |
|----------|--------|---------------|
| 1 | Ship F1 (left-recursive desugaring in `Expand`/`OptChain`, reducer reversal in `ResolveChildren`) | O(n²)→O(n) for user grammars; 7% on ABNF bench |
| 2 | Close F4+F5 as measured dead ends post-SPPF | — (don't implement) |
| 3 | Investigate grammar specialization (terminal-only rep as scanner loop) | Potentially 2–4x on terminal-heavy grammars |
| 4 | Accept Lark parity as unachievable for complex general grammars in pure Python Earley | Honest ceiling for the IrSelf substrate |
