# HANDOVER — post-leo parallel exploration (2026-06-30)

> **CORRECTION + OUTCOME (2026-07-01).** This document's recurring premise that
> Lark has a "C Earley core" / "builds its forest in C" / "C-backed transformer"
> is **false** — lark 1.3.1 ships zero compiled extensions; its real edge was
> the *dynamic lexer* (C `re` matching of declared tokens ⇒ ~5× fewer Earley
> steps: 182 tokens vs 920 chars on the self-host text). Every "Python-vs-C
> ceiling" argument below is therefore void. The compile/kernel/derived-runs
> rework (`PLAN_obliterate_lark.md`) subsequently took the product metric from
> the 2.22× recorded here to **0.52× — beating Lark ~2×** — in pure Python.
> This file remains as the historical record of the per-item-IrSelf engine.

Synthesis of three parallel Sonnet explorations launched after the `leoparse` commit
(`5af435d`) was dropped and its postmortem written. Goal: **beat Lark on the product
metric** (text → `IrAst`, `e:parse+reduce` vs `lark:full`) and answer the transversal
question **why is parsing super-linear?**

All numbers are data-backed; raw bench outputs are the `EXPLORE_*_*.txt` files in this
folder. Baseline reference: `BASELINE.md`.

---

## Landing progress (live)

Landing on branch `parse_proto_proto`; atomic commits, hook-green, each benchmarked.
Product = `parse+reduce` x4 vs `lark:full`. Baseline before landing: **3.33×**.

| step | commit | product x4 | status |
|---|---|---|---|
| Accept Expl-1 (port `test_ops.py`, 1151 pass) | swept into `88893a6` | 3.33× | ✅ landed |
| Refactor leoparse to pass the hook (typing + complexity, neutral) | `3512e8f` | 3.34× | ✅ landed |
| OPT1 — inline `CloseColumn` dispatch | `fda5a21` | 3.22× | ✅ landed |
| OPT2 — inline `Column.__iadd__` (chart.py only; ops.py `_table` reads dropped — W0212 for marginal gain) | `42b505d` | 3.22× (neutral) | ✅ landed |
| OPT3/4 — fast iterative tree builder (as a `_FastTree` cursor, not free fns; public IrMultiMap API, not `_table`) | `f2f5713` | **2.59×** | ✅ landed |
| OPT5 — str-keyed rules/nullable tables + `predicted: set[str]` (dropped now-dead `ctx.rules`/`ctx.nullable`) | `cab029c` | **2.42×** | ✅ landed |
| OPT-REDUCE — `_FastReduce` iterative fold, replaces the reduce step's `Trampoline`/`ReduceSource`/`ResolveSource` generator walk | uncommitted (staged in `reduce.py`) | **2.22×** | ✅ ready to land |

**Landing complete (through OPT5): product x4 3.33× → 2.42× Lark** (parse-only 1.90×); 1151 pass,
10/10 lint, hook-green, fixpoint True / amb False throughout. Deep right-recursion
parse→tree **0.5× Lark** (beats Lark), no stack overflow at N=1600.

**OPT-REDUCE (2026-07-01) takes it further: 2.42× → 2.22×** — see §Session 2 below.
(Note: this is a distinct optimization from Exploration 2's own internal "OPT6" —
the reverted str-keyed `waiting` attempt referenced below — kept as "OPT-REDUCE" to
avoid a naming collision with that.)

## Post-landing exploration — NEGATIVE result (do not re-try as-is)

Profiled the post-OPT5 build (`bench_parsing.py --profile`). Top costs (parse+reduce,
x4): **`Column.__iadd__` 0.54s** (#1, item dedup), `Predict.eval` 0.47s,
`Complete.eval` 0.23s, reduce/trampoline generators ~0.7s, SppfNode/ParseTree
`__new__` ~0.17s. Pervasive: `dict.get` 1.78M, `len` 2.2M, `isinstance` 1.4M,
`typing.cast` 1.3M.

**Attempted (and reverted): value-id arm intern for item dedup.** Idea: the `_seen`
key re-hashes the item's `IrSequence` arm on every membership test; replace it with
`(rule, arm_value_id, dot, origin)` where a per-parse `id(arm)→value-id` map
(`Chart.arm_value_ids`, built from `rules.values()`) gives a cheap int key.
**Correctness-safe** (value-ids preserve value-dedup; the `id(arm)` shortcut is
*unsafe* for value-equal-but-distinct arms, e.g. `R = "a" | "a"` — must use
value-ids) and rule-compliant (no `_table`, no free fns, no `ir/` change). 1151 pass
incl. property+ambiguity; canaries green.

**Result: REGRESSED 2.42× → 2.60–2.74×** (parse 1.90× → 2.17×). Adding `id(arm)` +
one `dict.get` to *every* insert costs more than the arm-hash it saves — the
duplicate-insert path dominates and the original `item not in _seen` short-circuits
after one hash. **Same lesson that reverted OPT6.** Fully reverted; baseline restored.

**Takeaway / ceiling.** The arm hash is *not* the bottleneck; the floor is per-item
**Python frame overhead** (calls, dict/set ops, `isinstance`, `cast`) across
`__iadd__`/`Predict`/`Complete`. Exploration 3 only beat Lark on *recognition*
(0.91×) by going fully flat — stripping IrSelf/IrDispatch, all-primitive item tuples,
inlined filing — which the "Earley stays an IR construct" rule rules out for the
production engine. **Conclusion: beating Lark on the product metric in pure Python
within the IrSelf architecture is not reachable by micro-opts.** 2.42× is the
IrSelf-pure floor.

### Options to actually beat Lark (architectural, not incremental)
1. **Accept ~2.42× as the IrSelf-pure floor** — banked, validated, hook-green. (Default.)
2. **PyPy** — Exploration 2's report cites 5–10× on the chart hot loops, zero code
   change; highest leverage, respects every rule.
3. **Relax IrSelf-purity for the engine hot loop only** (primitive item tuples +
   inlined ops, à la Exploration 3) — beats Lark on recognition; a deliberate
   decision against "Earley stays an IR construct", not a sneak.
4. **C/Cython extension for `Column`/`Chart`** — the `__iadd__` hotspot in native code.

Recommended: stop the micro-opt hunt; treat "beat Lark on the product" as a choice
among 2–4. Next session should NOT re-attempt per-insert dedup-key changes.

---

## Session 2 (2026-07-01) — options 1–4 tried, then OPT-REDUCE found

User rejected "accept 2.42× as the floor" and asked to actually try options 2–4 first,
then (after those came back weak) to dig for structural wins the profile hadn't named
yet: ditchable classes, data that should be mutable instead of re-instantiated,
memoization gaps, and any purity relaxation actually worth its cost.

### Options 2–4, tried for real (not re-derived from old numbers)

2. **PyPy — dead on arrival, not just slow.** `pyproject.toml` requires
   `>=3.14`, and `ir/nodes.py`/`ir/base.py` use PEP 695 generic syntax
   (`class IrSelf[Iri, Ir_co]`). `uv python install pypy-3.11.13` (the latest available)
   confirmed: it only implements the Python 3.11 grammar — `class Foo[T]: pass` is a
   `SyntaxError` before a single line of the codebase runs. Off the table entirely;
   would need a full PEP-695-to-`TypeVar` rewrite across `ir/` just to attempt it.
3. **Relax purity in the engine hot loop — re-measured against the OPT5 baseline
   (not the stale pre-landing one).** Ported Exploration 3's `fast_engine.py`
   unchanged (its dependencies — `normalize.py`, `ir/nodes.py` — hadn't moved since
   its base commit `6f61fed`) into a throwaway probe and re-ran `bench_fast.py`
   against *today's* dispatch-based engine. `fast3` (integer-interned arms,
   primitive item tuples) still beats: recognize **0.92–0.94×** Lark vs the current
   engine's 1.19–1.26×; parse **1.31–1.43×** vs 1.83–1.91×. Real ~25–30% headroom
   still sitting there — but `fast_engine.py` has no reduce/transform step, so there
   is still no true product-metric number for this path; naive extrapolation puts it
   at "still >1× Lark" even with this relaxation. Probe deleted after measuring
   (throwaway, per its own docstring).
4. **Cython — real but tiny in isolation.** `uv pip install cython` (venv-local, no
   `pyproject.toml`/`uv.lock` change) + a minimal `.pyx` reimplementing
   `Column.__iadd__`'s exact insert logic, replayed against the real captured
   131,527-insert sequence from an x4 parse: **1.84× speedup on that one function**.
   But `__iadd__` alone is only a fraction of total time — compiling just it projects
   to ~5% off the product metric. A real win needs the *entire* hot path
   (`Predict`/`Complete`/`Scan`/`Column`) in Cython — a native-build-step commitment,
   not attempted.

None of 2–4 closes the gap cheaply, confirming the original read. Per user
direction, moved to structural investigation instead of banking the floor.

### The structural find: the reduce step still trampolines every node

OPT3/4 replaced the *tree-build* trampoline with the iterative `_FastTree` cursor,
but never touched the **reduce** step — `ReduceSource`/`ResolveSource` (in
`reduce.py`) still create two generator objects and drive them via `Trampoline.send()`
for every single `ParseTree` node, on every parse. Two things tried:

- **Str-keyed `Reducer.reductions`/`.noise` (OPT5's pattern, applied to a build-once
  table instead of a per-parse one — no insert-cost downside at all, unlike the
  reverted per-item `waiting` attempt).** Implemented via a `ReduceCtx`-hosted str
  mirror; measured via cProfile with a narrow `'__eq__|IrScalar'` filter: only 37,230
  `__eq__` calls total (5 reps) ≈ 4.8ms/rep out of ~257ms — **under 2%, not the
  bottleneck here.** Reverted cleanly (tests green before and after).
- **The trampoline/generator machinery itself.** Quantified the ceiling with a
  throwaway plain-recursive reducer (no trampoline, no generators at all): **1.56×
  faster on the reduce step alone** (55ms → 35ms on x4), output verified
  byte-identical to the trampolined version. As expected it stack-overflows at
  N=1600 on deep right-recursion (confirmed) — proving the win is real but a
  production version needs the same "explicit stack, not the C stack" treatment as
  `_FastTree`, not naive recursion.

### OPT-REDUCE — `_FastReduce`, landed

Built `_FastReduce` in `reduce.py`: an iterative, explicit-stack fold mirroring
`_FastTree`'s design, wired into `Reducer.eval` in place of
`Trampoline(ReduceSource(...))`. Simpler than `_FastTree`: a `ParseTree` here is
already disambiguated (single-derivation by construction), so **no ambiguity
fallback is needed at all** — it always completes. Frames are
`[node, kids, idx, parts, purpose, noise_body]`; `purpose` distinguishes a **REDUCE**
frame (folds `parts` through the node's reduction body, memoises by `id()`) from a
**SPLICE** frame (a synthetic quantifier-group node — flattens straight into its
caller's parts, never itself reduced/memoised, matching the original's behaviour).

Verified:
- 1151/1151 tests pass (incl. the 24 ambiguity tests — `Reducer` never sees an
  ambiguous tree, so this doesn't interact with ambiguity handling at all),
  `ruff check` clean, `pylint` 10.00/10.
- ABNF self-host fixpoint still `True`.
- Deep right-recursion depth-safety **explicitly re-verified past where the naive
  prototype broke**: a structural (non-`YIELD`) reduction over `S = "a"*` reduces
  correctly at **N=60,000** with no `RecursionError`.
- **Product x4: 2.42× → 2.22× Lark** (parse-only unchanged at ~1.90×, since this is
  purely a reduce-step change).

Result: uncommitted, staged in `reduce.py` only (116 insertions / 8 deletions) — user
lands it.

### Side finding — pre-existing bug, NOT fixed, NOT a regression

While stress-testing `_FastReduce`'s depth-safety, found that `Yield.eval` (the
`YIELD` reduction body, used for ABNF's text-yielding rules like `rulename`/
`char-val`) recurses through the **plain Python call stack**
(`self.eval(d, k, ())`), not through any trampoline. It `RecursionError`s around
N=1600 on deep right-recursion. **Confirmed pre-existing** by stashing this
session's changes and re-running the same repro against original `HEAD` — identical
failure at the same N. The ABNF grammar never hits this in practice (`YIELD` only
fires on shallow leaf-ish rules), so it's never been noticed. Not fixed this
session — flagging for whoever next touches `reduce.py`'s `Yield` class; the fix
would be the same "explicit stack instead of Python recursion" treatment applied
here to `_FastReduce`.

### Updated options list (2026-07-01)

1. ~~Accept 2.42× as the floor~~ — superseded; OPT-REDUCE lands at 2.22×.
2. PyPy — **ruled out**, not merely deprioritized (language-version incompatible).
3. Relax engine-loop purity — **~25–30% headroom confirmed, unclaimed.** Would need
   the reduce step folded into the same relaxed representation (fast_engine.py has
   no reduce path) to get an honest product-metric number; not attempted.
4. Cython — **~5% alone (`Column.__iadd__` only); a whole-hot-path port needed for
   real payoff.** Not attempted beyond the POC.
5. **New:** fuse tree-build (`_FastTree`) and reduce (`_FastReduce`) into one pass,
   skipping `ParseTree`/`IrSeq` materialization entirely for the common case —
   flagged in the original TL;DR as a stretch idea, still unscoped.

---

## TL;DR

1. **Parsing is NOT super-linear.** All three explorations confirm independently: the
   leoparse Leo optimization already makes the engine **O(n)** on right-recursion (and
   ABNF is O(n) regardless). Super-linearity only ever appeared on *pathological deep
   right-recursion*, which Leo fixed. The remaining **3.3× gap to Lark is pure
   constant-factor** Python-interpreter overhead vs Lark's C Earley core.

2. **The constant-factor gap is closeable — recognition was BEATEN.** Exploration 3's
   flat engine beats `lark:parse` at **0.88–0.91×** on recognition. Exploration 2,
   working *inside* the IrSelf engine, cut the product metric from **3.37× → 2.34×**
   Lark with the full suite still passing.

3. **One root cause dominates, found independently by 2 and 3:** `IrScalar.__eq__` /
   `IrRuleRef.__eq__` is invoked on **dict/set probes**. Grammar atoms are distinct
   `IrRuleRef` instances with equal string value; a dict lookup hashes, hits a stored
   key, identity check fails, and Python calls `__eq__`. Switching hot-path keys to
   **plain `str`** eliminated ~13× of these calls. This is the central
   **IrSelf-purity-vs-performance tension** (see §Decisions).

---

## The three explorations

### Exploration 1 — drop & reimplement (worktree `agent-ab059933e58dd9159`, base `1df8365`)
Report: `EXPLORE_1_drop_and_reimplement.md`

Reset to pre-leoparse and **cleanly reimplemented Leo-on-parse** — same lazy
deferred-chain design as the dropped commit, but **better**:
- `LEO_ENABLED` flag removed (Leo unconditional), `_sole_candidate` → `sole_candidate`.
- Nullable-cycle guard in `LeoItem.resolve` (lazy `seen` set).
- **`test_ops.py` fully ported → 1151 tests pass** (the dropped commit left the suite
  un-collectable). ABNF fixpoint True, `is_ambiguous` False.

**Perf: identical to leoparse within noise** (product x4 3.33×, right-rec O(n) 0.8× Lark).
Value is *correctness hygiene*, not speed. **This is the right base to build on** — it is
the only variant with a green, collecting suite and the flag removed per the directive.

### Exploration 2 — improve the current build (worktree `agent-ae6e090226fffc47d`, base HEAD)
Report: `EXPLORE_2_improve_current.md` — **biggest mergeable win.**

Five constant-factor optimizations landed *inside the IrSelf engine*:

| # | optimization | product x4 |
|---|---|---|
| — | baseline (leoparse HEAD) | 3.37× |
| OPT1 | inline `CloseColumn` dispatch (singletons `_PREDICT/_COMPLETE/_SCAN`, skip `IrDispatch.eval`) | 3.28× |
| OPT2 | inline `Column.__iadd__` multimap ops (direct `dict` access) | 3.24× |
| OPT3/4 | **fast iterative tree builder** `_build_tree_fast` — replaces the coroutine trampoline for unambiguous parses (all 32k ABNF links are single-link); trampoline kept as ambiguity fallback | **2.47×** |
| OPT5 | **str-keyed `rules_table`/`nullable_table` + `predicted: set[str]`** — kills `IrScalar.__eq__` on the lookup path (469k→36k calls) | **2.34×** |

**Final: product x4 ≈ 2.34× Lark, parse-only 1.87×, recognize ~1.65×, right-rec 0.5×
Lark** (earley beats Lark 2:1 on deep right-recursion). Tried OPT6 (str-keyed `waiting`)
and **reverted it** — `str(symbol)` per-insert cost exceeded the `__eq__` saving (a clean
measured negative; the dominant path is item *insertion*, not lookup). Suite: 1128 pass
(left `test_ops.py` broken — take Exploration 1's port).

### Exploration 3 — go radical (worktree `agent-ae8dcf7d83411e1a1`, base HEAD)
Report: `EXPLORE_3_radical.md` — **proves the ceiling: recognition beats Lark.**

Throwaway flat engine `fast_engine.py`, IrSelf/IrDispatch stripped. Items become
**all-primitive tuples** `(plain_str, int_arm_id, int_dot, int_origin)` (O(1) hash/eq),
plain-str `waiting` keys, inlined filing, pre-allocated columns, persistent char-accept
cache. Leo preserved.

| size | recognize vs `lark:parse` | parse vs `lark:full` |
|---|---|---|
| x1 | **0.91×** | 1.30× |
| x2 | **0.91×** | 1.29× |
| x4 | **0.91×** | 1.32× |

**Recognition beats Lark by ~9%, consistently.** Full parse is still 1.26–1.32× — the
entire residual is **tree-node allocation**: 306k `_SppfNode2.__init__` + 67k
`_ParseTree.__init__` (Lark builds its forest in C). Right-rec recognition 6× faster than
Lark. (Caveat: this throwaway tree builder isn't trampolined — stack-overflows at N≈800
on deep right-recursion; recognition-only there.)

Verdict from the agent: **worth pursuing for real** — port primitive item-tuples +
plain-str keys + inlined filing into the IrSelf engine's Predict/Complete/Scan; the
dispatch *architecture* is not the bottleneck, the per-op Python overhead is.

---

## Why is parsing super-linear? (the transversal answer, with data)

**It isn't — on any realistic grammar.** Evidence converged across all three:

- **ABNF self-host:** items/char and links/char are **flat** across x1/x2/x4 (31.8
  items/char, 8.8 links/char — Exploration 1). `µs/N²` flat-and-decreasing on `--rightrec`.
  The ~4% wall-clock creep x1→x4 is CPU-cache pressure, not algorithm.
- **Deep right-recursion `S="a"*` was** the only super-linear case: pre-Leo the completer
  re-walked the full reduction chain every column → Θ(N²) links (`µs/N²` flat at 0.65,
  blowing to 43× Lark and widening). Leo jumps to the topmost item and records one
  deferred link; the forest rebuilds a touched chain once → Θ(N). Post-Leo `µs/N` is flat
  ~20 and **beats Lark 0.8×**.

So the whole remaining problem is **constant factor**, and the dominant constants are:
1. **`IrScalar.__eq__` on dict/set probes** (the atom-instance-identity issue) — fixed by
   str-keying hot paths.
2. **Per-item Python overhead** in `Column.__iadd__` / `Predict` / `Complete` (set+list+
   tuple-unpack+isinstance per item) — ~700–800 ns/item in Python vs ~10–20 ns in Lark's C.
3. **Trampoline/generator overhead** in forest+reduce (~15%) — replaced for the
   unambiguous case by the iterative tree builder (Exploration 2 OPT3).
4. **Tree-node `__init__` allocation** — the last barrier on the product metric
   (Exploration 3); candidate: bare tuples instead of `_SppfNode`/`_ParseTree` dataclasses.

---

## Recommended path to actually beat Lark on the product metric

A composite none of the three fully assembled. In order:

1. **Base = Exploration 1** (clean Leo reimplement, `test_ops.py` ported, flag removed).
   Green suite, correct.
2. **Land Exploration 2's OPT1–OPT5** on top (inline dispatch, inline `__iadd__`, fast
   iterative tree builder, str-keyed lookup tables). → ~2.34× product, suite green.
3. **Port Exploration 3's primitive item representation** `(str, int_arm_id, int_dot,
   int_origin)` + plain-str `waiting` keys + inlined filing + pre-allocated columns into
   the engine hot loop. Recognition then beats Lark (~0.9×); this targets constant #2.
   (Re-measure OPT6's tradeoff under the new tuple shape — it may flip positive.)
4. **Replace `_SppfNode`/`_ParseTree` dataclasses with bare tuples** to kill the ~47 ms
   tree-build allocation gap (constant #4) — the last barrier between full parse and Lark.

Projected: recognition already < Lark; with steps 3–4 the **product metric has a credible
path to ≤ 1× Lark**. Each step must be validated back-to-back (drift-robust) per the
postmortem's discipline — measure, don't assert.

---

## Decisions the user needs to make (taste / architecture)

1. **IrSelf purity vs the str-keying win.** The single biggest lever (str-keyed
   `rules_table`/`nullable_table`, `predicted: set[str]`) sidesteps `IrScalar.__eq__` by
   *not* using IrSelf leaves as dict keys on the hot path. Exploration 2 added them as
   plain `dict`/`set` attrs on `ParseCtx`/`Column` — i.e. **`dict` attrs, against the
   "prefer the class *being* an `IrMultiMap`" directive.** Justified by a measured 13×
   `__eq__` reduction. **Ruling needed:** accept str-keyed side tables, or insist on an
   `IrMultiMap`-shaped home that still achieves O(1) primitive-keyed probes?

2. **How far to push primitives into the engine.** Exploration 3 shows the IrSelf/
   IrDispatch machinery *is* the constant-factor cost. Its recommended port keeps the
   dispatch architecture but represents Earley items as primitive tuples. **Ruling
   needed:** is a primitive item tuple inside the engine acceptable, or must items remain
   IrSelf-derived (and accept the ~2× ceiling)?

3. **Tree nodes as bare tuples.** Step 4 above trades `_SppfNode`/`_ParseTree` IrSelf-ish
   dataclasses for tuples on the forest hot path. Same purity question, scoped to the forest.

4. **`test_ops.py`:** only Exploration 1 ported it. Any merge of Exploration 2/3 work must
   take that port or the suite won't collect.

---

## Artifacts & worktrees

Reports + raw benches in `zzz_current_work/postleo/`:
- `BASELINE.md`, `bench_{before,after}_leoparse.txt`, `rightrec_{before,after}_leoparse.txt`
- `EXPLORE_1_drop_and_reimplement.md` + `EXPLORE_1_*.txt`
- `EXPLORE_2_improve_current.md` + `EXPLORE_2_*.txt`
- `EXPLORE_3_radical.md` + `EXPLORE_3_*.txt`

The code lives in the (still-present) git worktrees — nothing merged, nothing committed:
- Exploration 1: `.claude/worktrees/agent-ab059933e58dd9159` (branch `worktree-agent-ab059933e58dd9159`, base `1df8365`)
- Exploration 2: `.claude/worktrees/agent-ae6e090226fffc47d` (branch `worktree-agent-ae6e090226fffc47d`)
- Exploration 3: `.claude/worktrees/agent-ae8dcf7d83411e1a1` (branch `worktree-agent-ae8dcf7d83411e1a1`) — `fast_engine.py` is throwaway

Inspect a worktree's diff with `git -C <path> diff HEAD` (or `git diff 1df8365` for #1).
When done choosing, clean up with `git worktree remove <path>`.

## Constraints honoured
No commits made (user lands). No `# type: ignore`/`# noqa`/`exec`/`eval` introduced in the
exploratory code paths claimed as wins. Canaries: ABNF fixpoint True, `is_ambiguous` False
across all three. Tests: 1151 (Expl. 1) / 1128 excl. `test_ops.py` (Expl. 2).
