# Handover — `parsing_2` performance optimizations

**Status:** reviewed, not yet implemented. Three parallel review reports exist at
repo root; this doc is the synthesis, ranking, and sequencing. **Do this work
*after* the SPPF ambiguity work lands** (see `HANDOVER_SPPF.md`) — several findings
overlap the forest path the SPPF rewrite touches, and one is already partly done by it.

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

