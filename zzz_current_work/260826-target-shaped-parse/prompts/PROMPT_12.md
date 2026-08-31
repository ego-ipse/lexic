# Investigator prompt 12 — close the four surviving mechanism gates

Work in `/home/mika/projects/lexic` on the active effort
`zzz_current_work/260826-target-shaped-parse/`.

Read, in order:

1. `AGENTS.md`/the supplied repository instructions and `docs/STYLE.md`;
2. the effort's `INDEX.md`, `context.md`, `goal.md`, `DESIGN.md`, and `TODO.md`;
3. `prompts/PROMPT_11.md`, `reports/PROTOTYPE_11.md`, and
   `reports/P11_ADVERSARIAL.md`;
4. the Prototype 11 files named below and every production seam they import.

The design remains green. This round closes four precise mechanism gates left
open by the Prototype 11 evidence fold. It is not production implementation.
Do not edit `src/`, `tests/`, `pyproject.toml`, or the active planning
documents. Revise or add prototypes only under this effort's `proto/`; never
use `/tmp` for prototypes. Deliver one factual report at
`reports/PROTOTYPE_12.md`. Do not commit or push.

Strict constraints: no `eval`, `exec`, `Any`, `object`, cast-based erasure,
ignore/suppression directive of any kind, grammar-specific branch in generic
machinery, external model library, or second parse API. Use `uv run` for Python
tools. Run no benchmarks concurrently; run each multithreaded or Qwen-scale row
alone. Report process CPU and wall separately. Do not modify production code to
instrument it. Do not re-open conclusions which the active documents mark
closed.

## A. Replace the cyclic ambiguity fallback exactly

`proto/ambiguity_interaction.py` proves that one-flip replay is unsound and
establishes exact per-node value-set propagation on an acyclic completed-node
graph. Its cyclic fallback is not accepted: it enumerates every global
assignment in `2^k`, where reachable `k` is unbounded, and calls a one-lap
relation exact. The cycle oracle shares that fallback and therefore does not
validate it independently.

First state the actual semantic question for a cyclic packed forest under the
planned closed product-operation algebra. Distinguish:

- infinitely many derivation trees from finitely many completed handles;
- deciding whether more than one distinct requested-root meaning exists from
  enumerating every meaning;
- value-growing, value-erasing, idempotent, and choice-bearing zero-width SCCs;
- the current `FastTree` consumed-choice behavior from the intended language
  and ambiguity contract.

Produce executable witnesses which require revisiting the same cyclic choice
on two or more laps, or prove from the closed operation laws that one lap is
complete for a precisely stated class. The proof must cover interacting packed
families and island-leaf options, not just one unary wrapper. Do not treat
agreement with production `another_meaning` as an oracle: its arbitrary-build
single-flip contract is already disproven.

Prototype an exact terminating decision mechanism. Investigate SCC-local
fixed-point/partition refinement, operation-law certificates, or a conservative
compile-time refusal for SCCs whose semantic relation cannot be represented
finitely. The final architecture must have a stated complexity bound in chart
nodes/edges and operation-state cardinality. No global Cartesian assignment
enumeration, arbitrary choice cap, sampling, hash-as-proof, recursion-depth
limit, or undocumented one-lap semantics is admissible. If exact support for a
cyclic class is impossible under the planned algebra, refuse that class during
binding with words and prove that the refusal is formulation-independent.

Differential the mechanism against an independent bounded-depth exhaustive
oracle on small SCCs, increasing the depth until the result stabilizes or the
mechanism intentionally refuses. Include positive ambiguity, equal-meaning,
dropped/constant, nested interaction, sibling accepting roots, and deep
stack-safe witnesses. Report retained state, operation executions, maximum live
state, and asymptotic bounds. Record the exact replacement contract for
production `another_meaning`; pre-alpha carries no obligation to preserve that
helper.

## B. Complete the tokenizer meaning and refusal relation

`proto/keyed_product_rows.py` establishes the real carrier costs, the Python
cold-comparison decision, and the `IrMap` document-level decision. Preserve
those conclusions. Its tokenizer normalizer is incomplete: real construction
can refuse duplicate token ordinals and duplicate merge keys, while the
normalized document reports both as valid. Audit every validation and derived
field in the intended final `IrTokenizer.from_indexes` path and the current
`from_merges` witness, including encode/decode bijection, ordinal constraints,
merge/rank identity and order, pipeline, segmenter, root record, and ordered
verdict precedence.

Revise the tokenizer candidate so its meaning contains every constructor input
and every ordered validation outcome without constructing the discarded ready
tokenizer. Differential it against real construction over:

- equal and changed valid documents;
- changed values, keys, key sets, dropped material, merge order, and pipeline;
- duplicate spellings, duplicate ordinals, duplicate merge keys, invalid
  ranks/references, and combinations where two derivations refuse equally or
  with different first verdicts;
- small exhaustive/generated documents and the real Qwen fixture.

The reference comparison is the complete target result relation, including
ordered refusal, not merely success-versus-failure. If exact document-level
normalization duplicates enough constructor work that cold construction wins,
select the cold fallback honestly. Otherwise prove and price the normalized
representation. Measure semantic replay, validation/normalization, exact
comparison, retained memory, and chosen-result construction separately. Run
the Qwen row once, alone and guarded; do not rerun unrelated parser benchmarks.

## C. Finish the flat ambiguity structures and honest controls

Keep `DISTANT`, `DISTANT_TWO`, and the pad 2,000/8,000/32,000 ladder in
`proto/ambiguity_rss.py`. The CSR/forward-star parent/owner layout and its
dirty-cone parity are established. The array-only 112 B-per-character figure
is not yet a production result because the retained prototype costs 293–316 B
per character with its numbering dictionary.

Prototype production-shaped dense numbering assigned as completed handles
become available. No handle-to-number dictionary may remain in the measured
candidate. If an external prototype needs a transient lookup which production
would store in existing completion state, measure and report the transient
build peak separately, then release it before measuring retained structure.
Prove lookup, owner, parent-edge, dirty-cone, cleanup, integer-width/tier, and
overflow laws. Report nodes, ambiguity keys, owner edges, parent edges, array
bytes, transient bytes, retained bytes, build CPU/wall, replay CPU/wall, and
peak RSS separately.

Correct the control rather than relabeling it. The executed unambiguous branch
must return before constructing any ambiguity meaning memo, dependency index,
overlay, seed, or trace. Instrument the actual factories/constructors with
external allocation counters and assert zero calls; detached empty containers
and clearing an allocated overlay afterward are not evidence. Ordinary direct
product state may be reported separately, but a post-parse full-tree meaning
memo is not the unambiguous target-shaped product.

Correct the frame allocation row. Allocate one child tuple per completed
ancestor and share that tuple only among seeds which cross that same
completion, matching `_record_frames` in `proto/island_alternate_seed.py`.
Vary ancestor depth, simultaneous seed count, child arity, and dirty slot.
Allocate real seed records and frames, pool rule names outside the measurement
window, and report total bytes plus bytes per completion and per seed/frame.
Do not carry forward the rejected 96–98 B figure.

The ambiguous row must still assert the correct target verdict and exact parity
with an independent oracle. Keep chart expansion outside named structure
windows, processes isolated, GC state explicit, and `tracemalloc` versus RSS
attribution honest.

## D. Prove custom binding through the real pool and paid loop

Preserve the public and binding decisions in
`proto/custom_class_target.py`: one immutable constructor class symbol plus
inert field/path data, a homogeneous result-free cache, identity-plus-pin keys,
no class inspection, and a result-typed bound view retaining derived grammar
data/tables. Do not add a factory/callback field, import-path lookup, mutable
rebinding registry, custom executor, or second parse API.

Exercise the actual `lexic.parsing.parallel.pool.ParsePool` lifecycle. Bind the
custom target, give the standard pool seam ownership of that bound product,
release and collect the source artefact and binding-registry entry, then parse
and construct multiple documents through the retained pool on the
free-threaded interpreter. Close the pool and prove cleanup. Using the existing
pool's ordinary work binding is not permission to place a callable in the
public declaration or introduce another executor.

Measure constructor/callback traffic on a production-shaped completion walk,
not with a list which merely documents the known call site. The frequent path
must have no reference or dynamic dispatch to the consumer constructor; the
constructor runs exactly once at successful root finalization and never on
syntax failure, failed speculation, ambiguity refusal, or an unchosen result.
Cover concurrent pool maps, constructor failure, tier escape after source
death, equivalent recomputation after eviction, and pool shutdown. Report
process CPU/wall for the default control and custom target through the same
real engine shape; this is a paid-loop neutrality check, not a Qwen benchmark.

## E. Mandatory internal adversarial review loop

Do not rely on your own self-review. After all prototype work, measurements,
checks, and the first complete draft of `reports/PROTOTYPE_12.md` are finished,
call two fresh internal adversarial reviewers **sequentially**. Do not run an
agent while any benchmark or measurement process is live, and do not run the
two reviewers concurrently.

In Claude Code, call each reviewer through the `Agent` tool with:

```text
subagent_type: general-purpose
run_in_background: false
description: <short review role below>
prompt: <the complete role prompt below>
```

If the tool exposes a model/effort choice, use the strongest reasoning model
available at high effort. Give each reviewer a fresh context: point it to the
repository and files instead of summarizing away the evidence. Reviewers are
read-only. They must not edit files, run Qwen/MT benchmarks, commit, or push.

Call reviewer 1 with description `adversarial semantic review` and this prompt:

```text
Read AGENTS.md, docs/STYLE.md, the target-shaped-parse INDEX/context/goal/
DESIGN/TODO, prompts/PROMPT_12.md, reports/PROTOTYPE_11.md, every prototype changed by
Prototype 12, and the complete draft reports/PROTOTYPE_12.md. Adversarially
review correctness only. Try to falsify the cyclic ambiguity invariant and
termination argument, tokenizer success/refusal equivalence and verdict order,
flat-index parity/lifetime claims, and custom pool lifecycle/type guarantees.
Look for circular or shared oracles, bounded witnesses presented as proofs,
unstated refusal/language changes, arbitrary-depth or Cartesian explosions,
and claims broader than executable evidence. Do not edit or benchmark. Return
findings ordered by severity with exact file:line evidence; say READY only if
there is no substantive correctness or planning blocker. Ignore prose nits.
```

Wait for reviewer 1. Fix every substantive finding, rerun the affected witness
and static checks, and update the report before calling reviewer 2. Call
reviewer 2 with description `adversarial performance review` and this prompt:

```text
Read AGENTS.md, docs/STYLE.md, the target-shaped-parse INDEX/context/goal/
DESIGN/TODO, prompts/PROMPT_12.md, reports/PROTOTYPE_11.md, every prototype changed by
Prototype 12, and the revised reports/PROTOTYPE_12.md. Adversarially review the
representation and performance evidence only. Check that the control cannot
reach ambiguity allocations, dense-numbering transient and retained memory are
separated, real frame child tuples and seeds are allocated, tracemalloc/RSS/GC
claims are honest, custom paid-loop comparison uses the same engine shape, and
no overlapping agent or benchmark activity contaminated timings. Recompute
reported arithmetic and challenge every extrapolation. Do not edit or run
benchmarks. Return findings ordered by severity with exact file:line evidence;
say READY only if no substantive performance-evidence blocker remains. Ignore
formatting and prose nits.
```

Wait for reviewer 2. Fix every substantive finding and rerun affected evidence.
Then call a **fresh third** `general-purpose` reviewer, also synchronously and
at high effort, with description `final closure audit` and this prompt:

```text
Perform a final read-only closure audit of prompts/PROMPT_12.md, all Prototype 12 code,
and the final reports/PROTOTYPE_12.md against the active target-shaped-parse
INDEX/context/goal/DESIGN/TODO. Confirm that every earlier semantic and
performance finding is actually resolved, that open user decisions remain
open, and that no conditional or unmeasured premise is called closed. Do not
edit or benchmark. Return only substantive blockers followed by READY or NOT
READY, with file:line evidence.
```

Record all three reviewer prompts, findings, fixes, and final verdict in the
report. A reviewer saying READY is evidence about the packet, not authority to
weaken a gate. If the `Agent` tool is unavailable, **stop**: write the three
complete prompts to `reports/P12_REVIEWER_PROMPTS.md`, state that internal
review could not be run, and do not call the round ready for implementation.

## F. Scope and deliverable discipline

Resolver-pair construction and the one-island Earley splice are already
established. Resolver scope remains a user decision. Do not declare either
island-local or complete-document pairs accepted, and do not spend this round
rewriting `proto/resolver_pair.py` unless a new finding invalidates its
feasibility result.

`reports/PROTOTYPE_12.md` must distinguish:

- mechanism gates conclusively closed;
- mechanisms which still require production integration measurement;
- user decisions still open;
- failed candidates and why they stay rejected.

Do not call a gate closed conditionally while leaving its correctness premise
unproven. Include exact commands and complete relevant outputs. Run Ruff
format, Ruff check, and Pyright over every prototype added or changed, plus each
executable witness. Search the touched files for all forbidden constructs.
Finish with the mandatory internal-review record above plus your own
adversarial self-audit, and list exact recommended planning-document edits
without applying them. The round is ready to fold only when the final fresh
reviewer returns READY.
