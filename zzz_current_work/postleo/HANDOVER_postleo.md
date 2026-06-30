# HANDOVER — post-leo parallel exploration (2026-06-30)

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
| OPT3/4 — fast iterative tree builder (as a `_FastTree` cursor, not free fns; public IrMultiMap API, not `_table`) | `pending` | **2.59×** | ✅ landed |
| OPT5 — str-keyed lookup tables | — | — | ⏳ next |

Deep right-recursion after OPT3/4: parse→tree µs/N ~13.5 (was ~20), **0.5× Lark**
(was 0.8×), no stack overflow at N=1600 (explicit-stack cursor).

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
