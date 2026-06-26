# Handover — `parsing_2` performance optimizations

> ## Update (2026-06-26) — SPPF fully CLOSED; F1 is unblocked and is the next piece
>
> `HANDOVER_SPPF.md` is **CLOSED**. Beyond the recogniser/forest/API work, the two
> deferred robustness items also landed: the forest *read* path is now **lazy**
> (`IrStream`, `ForestCtx`-as-`IrMultiMap`, `FamilyPrefixes`/`DerivationTrees`
> source nodes) and `parse()`/`is_ambiguous()` **short-circuit** at the 2nd
> derivation. Suite green (**1126 passed**, ABNF fixpoint canary included; pyright
> clean; pylint 9.99 from a test-only `duplicate-code`, non-gating).
>
> **This does NOT touch F1's path.** Laziness is the forest *read*; F1 is the chart
> *build* (`normalize.py` right-recursion → O(n²)). They are orthogonal — F1's plan
> and the reducer child-order follow-up below are unchanged.
>
> **Benchmark baselines captured for F1 comparison** (new suite `tests/performance/`,
> marker `performance`; run `uv run python bench_parsing.py` *and*
> `uv run pytest tests/performance -m performance -s -v`):
> - **`rep_grammar` (right-recursive `list = elem list / elem`, the O(n²) baseline F1
>   targets), parse time:** n=50 → 0.0054 s, 100 → 0.0261 s, 200 → 0.0653 s,
>   400 → 0.2322 s. Super-linear today; F1 should flatten this toward linear.
>   *(Hand-built IrAst, not the `normalize.py` pipeline — representative shape.)*
> - **Lazy short-circuit (proves the read path is no longer the bottleneck):**
>   `parse(s=ss/a, 'a'*40)` raises ambiguous in ~18 ms; `is_ambiguous` → 1 in ~17 ms;
>   eager `derivations('a'*30)` OOMs at 1 GiB (guarded). Short-circuit scaling on
>   sss: n=10 → 1.1 ms, 20 → 3.1 ms, 40 → 17 ms, 80 → 145 ms.
> - Re-baseline `bench_parsing.py` (Lark vs `parsing_2`) before starting F1 — numbers
>   in the report below predate the SPPF rewrite.
>
> ---

> ## Update (2026-06-25) — SPPF has landed; this is now the next piece
>
> The prerequisite is satisfied: the SPPF ambiguity work in `HANDOVER_SPPF.md` is
> **complete and green** (`bash tools/run_checks.sh` + `uv run pytest tests/ -q`,
> including the ABNF self-host fixpoint). Deltas relevant to the findings below:
>
> - **Finding #3 (defer eager subtree build in `Complete`) — confirmed landed.**
>   `Complete.eval` now records a shared `SppfNode(done, col)`, not an eager
>   `ParseTree`/`BUILD_TREE`. **Re-measure** to confirm the ~36%-on-recognize win
>   materialised and didn't just move downstream into forest enumeration.
> - **Finding #4 `IrMultiMap.__getitem__` snapshot — surface widened.** `Links` is
>   now an `IrMultiMap` subclass (chart.py), so `chart.links[key]` *and* the
>   `waiting` index both snapshot a fresh `IrSeq` per read. The optimisation
>   (iterate the live bucket in place when `origin == col`) now potentially applies
>   to links too — but, as noted, this mostly **evaporates once F1 cuts completion
>   count ~80×**, so leave it until after F1 and re-profile.
> - **Numbers below predate the SPPF rewrite — re-baseline before starting.** The
>   *shape* is unchanged (`normalize.py` is still right-recursive ⇒ O(n²)), but the
>   absolute µs/char and the cProfile breakdown should be re-measured on the current
>   engine. The harness still works; `bench_parsing.py` imports were repointed to
>   `from lexic.parsing_2 import parse, recognize` (the public API now lives in
>   `__init__.py`).
> - **Engine shape moved (no perf impact, but the entry points changed).** The
>   public API (`parse`/`recognize`/`parse_forest`/`derivations`/`is_ambiguous`) is
>   now thin wrappers in `parsing_2/__init__.py` over on-node orchestration in
>   `engine.py` (`Accepting`/`Parse`/…). `BuildChart`/`CloseColumn`/`ScanColumn` —
>   the hot loops F1 and the micro-wins touch — are unchanged.
> - **One deferred SPPF item touches a *different* path:** lazy forest enumeration +
>   strict-`parse` short-circuit (SPPF handover "Remaining work"). That's the forest
>   *read* path; F1 and the micro-wins here are the chart *build* path. Independent —
>   either order is fine.
> - **F1's required follow-up is unchanged:** the reducer child-order reversal for
>   left-recursive rep-rules (below) still applies; `reduce.py` was left untouched by
>   the SPPF work, so the splice logic is exactly as the review found it.

**Status:** reviewed, not yet implemented. Three parallel review reports exist at
repo root; this doc is the synthesis, ranking, and sequencing. The SPPF precondition
(below this update) is now **satisfied** — several findings overlapped the forest
path the SPPF rewrite touched, and finding #3 was absorbed by it.

**Source reports (read for full evidence/measurements):**
- `opt_review_algo.md` — algorithmic & data-structure (the big one).
- `opt_review_alloc.md` — allocation / object-churn in the hot loops.
- `opt_review_dispatch.md` — dispatch-substrate overhead (mostly a *negative* result).

**Benchmark harness:** `bench_parsing.py` at repo root.
`uv run python bench_parsing.py` (timing table) / `--profile` (cProfile). It compares
`parsing/` (Lark) vs `parsing_2/` on the same ABNF-source→IrAst task.

---

## The measured problem

`parsing_2` is ~**4–4.5× slower than Lark**, and the ratio **grows with input size**
(4.0× → 5.2× from 920 → 14,720 chars). Lark is linear (~29.5 µs/char); `parsing_2`
is super-linear (108 → 154 µs/char). cProfile shows the cost is per-item overhead /
item count, not a single hot line. Reduce is only ~17%; chart construction dominates.

---

## Findings, ranked

### 1. 🔴 CRITICAL — Right-recursive quantifier desugaring is an O(n²) trap (`opt_review_algo.md` F1)
`normalize.py` desugars every `*`/`+` into a **right-recursive** synthetic rule
(`X = elem / elem X`). Right recursion is the textbook Earley quadratic. **This is
the cause of the growing ratio** (proven: `max_col` grows linearly with input; the
dominant column is ~96% identical complete `__rep_1` items at distinct origins).

**Fix:** switch the desugaring to **left recursion** (`X = X elem / elem`). A
throwaway prototype made `max_col` *constant* and time *perfectly linear* (~80× at
N=800). O(n²)→O(n).

**Caveats / interactions:**
- **Reducer child-order:** left recursion reverses the order matched elements are
  recovered. `reduce.py`'s synthetic-rule splice (`ResolveChildren`, keyed on
  `SYNTHETIC_PREFIX`) must reverse the spliced run for synthetic rep-rules, or the
  round-trip / fixpoint breaks. The prototype skipped this (proved scaling, not
  correctness). **This is the required follow-up to make F1 ship.**
- **Idempotency / power:** power-neutral — left/right recursion recognise the same
  language, and the synthetic rep-rule is not where user-grammar ambiguity lives. The
  round-trip stays idempotent **iff** the reducer reversal is implemented. Compatible
  with the SPPF work (Scott's SPPF handles left recursion).
- **Nullable-element repetition** (`elem` nullable) is inherently ambiguous — a
  pre-existing concern that belongs to the ambiguity work, not introduced by F1.

### 2. 🔴 Alternative to #1 — Leo's optimization (`opt_review_algo.md` F2) — DEFER
Keeps right recursion, short-circuits the completion chain via transitive items;
same O(n²)→O(n). The data says completer buckets are already nearly deterministic
(~1 waiter), Leo's precondition.

**Why defer (not pick over F1):** Leo's reconstruction lives in the **same forest /
`BuildTree` code the SPPF work is rewriting**, and Leo + ambiguous-SPPF needs
Marpa-style care (it only fires on deterministic reductions, but the unrolling must
cooperate with packed nodes). Doing Leo now means designing that twice. **Prefer F1**
(simpler, local reducer fix, doesn't touch the forest). Revisit Leo only if F1's
reducer reversal proves intractable, and only after SPPF is stable.

### 3. 🟡 Defer eager subtree build in `Complete` (`opt_review_alloc.md` F1) — ALREADY DONE BY SPPF
The alloc review's top finding: `Complete.eval` built a `ParseTree` per completion
*even during `recognize`* (~36% on recognize). **The in-flight SPPF change already
replaces that eager `BUILD_TREE` with a shared `SppfNode(done, col)`** — so this win
is landing as part of SPPF. Re-measure once SPPF is green to confirm the gain
materialised (and that the new lazy enumeration didn't move the cost downstream).

### 4. 🟡 MINOR, purity-preserving micro-wins (compose with the above)
- **`ScanColumn` calls `Matches` on rulerefs** (`opt_review_dispatch.md` F3, ~3–4%):
  449k no-op calls; guard with `type(atom) is not IrRuleRef` before the match.
- **`IrMultiMap.__getitem__` snapshots a fresh `IrSeq` per completion**
  (algo F4 / alloc F3 / dispatch F2, ~2–6%): only needed when `origin == col`;
  iterate the live bucket in place otherwise. **Note:** this finding mostly
  *evaporates* once F1 cuts completion count ~80×.
- **Re-prediction per column** (`opt_review_algo.md` F5, ~5–10% of predict): a
  per-column "already predicted" `set[IrRuleRef]` on `Column` skips rebuilding +
  dedup-probing identical dot-0 arms.

### 5. ⚫ NEGATIVE RESULT — dispatch overhead is NOT the bottleneck (`opt_review_dispatch.md`)
Fully collapsing all three Earley ops into one procedural loop (which **destroys**
IrSelf purity) bought only ~11%. `IrTypeMap.resolve` is already a single `dict.get`.
**Do not** trade purity for dispatch speed — the win isn't there. Recorded so nobody
retries it. (Also rejected and recorded: `id(arm)`-based `EarleyItem` hash — came out
~20% *slower*; a per-column predicted-ref skip set as a *neutral* idea — but see #4,
where the *prediction* skip is a real, separate win.)

---

## Recommended sequencing

1. **Land SPPF ambiguity work first** (`HANDOVER_SPPF.md`) — it rewrites the forest
   path and already absorbs finding #3. Don't optimise a path that's being rewritten.
2. **F1 left-recursion + the reducer child-order reversal** — the one change that
   fixes the *scaling* (everything else is constant-factor). Validate the ABNF
   fixpoint stays green.
3. **Micro-wins #4** — cheap, stack cleanly; but re-measure, since F1 changes the
   profile (several "minor" findings shrink once completion count drops).
4. **Skip #5** (dispatch collapse) and hold **#2 (Leo)** unless F1's reducer fix
   proves intractable.

## Constraints (apply to all of the above)
- Keep IrSelf purity: eval/dispatch + logic on classes; per-parse mutable state in a
  cursor (`ParseCtx`), not free functions/NamedTuples. Any deviation needs explicit
  written justification (the dispatch-collapse #5 is the canonical example of a
  deviation that is **not** worth it).
- No `# type: ignore` / `# noqa` / `# pylint: disable`; no `exec`/`eval` builtins.
- Keep the full suite green; ABNF fixpoint is the canary.

