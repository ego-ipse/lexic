# Investigator prompt 16 — shared occurrences and exact-lane cost

Work in `zzz_current_work/260826-target-shaped-parse/`. This is an evidence
round. Do not edit or approve the active plan.

## Scope and authority

Read the repository instructions, `docs/STYLE.md`, the active packet, the three
Round 15 reports, and these prototypes in full: `island_continuation.py`,
`shared_forest_refold.py`, `ambiguity_interaction.py`, `cyclic_meaning.py`,
`operation_slot_laws.py`, and `root_meaning_incremental.py`. Inspect the
production Earley forest, ambiguity readout, fold, completion tables, and PDA
island seams they model.

The active packet, `src/`, `tests/`, `pyproject.toml`, `.wiki`, and all earlier
prototypes and reports are read-only. Record their initial status before work.
You may write only:

- `proto/shared_occurrence_ambiguity.py`;
- `proto/exact_lane_cost.py`;
- `reports/PROTOTYPE_16.md`;
- `reports/P16_ADVERSARIAL.md`;
- `reports/REVIEW_16.md`;
- `reports/P16_REVIEWER_PROMPTS.md` if reviewers cannot be called.

Do not commit, push, or create a worktree. Keep prototypes in this effort's
`proto/`, never `/tmp`. Use `uv run`. Run no concurrent measurements. No
`eval`, `exec`, `Any`, `object`, casts, nested helpers, or suppression
directives. Generic machinery may contain no grammar-specific branch. JSON is
not privileged.

Resolver scope is settled: `resolve=` receives complete-document pairs under
both engines. Construct no pair during semantic settlement. Construct pairs
only after requested-root meanings differ and the resolver is invoked. The
fused PDA may then perform one cold Earley recognition; refusal and equal-root
paths do not. Ordinary PDA island recognition remains local. Do not reopen
this decision.

Parsing performance may not regress. Only the user may approve a measured
regression, including one caused by a bug fix. This round authorizes no source
implementation.

## A — shared-occurrence composition

Prototype 15's oracle fixes one choice per packed key and excludes shared
completed nodes. Replace that control with an independent, occurrence-unrolled
complete-derivation oracle.

Exercise all real shapes in `shared_forest_refold.py`: duplicate slot, pending
frame, sibling memo, and transparent synthetic node. Put semantic ambiguity
beneath each. Include a case where independent occurrence choices differ from
globally key-correlated choices. Cover an internal packed family and, where the
engine permits it, a delegated island option.

The oracle must give each consuming occurrence its own decision. It may not
call the candidate relation, reuse its deduplication, or key choices globally.
Fold real authored reducer operations over real derivations.

Establish whether:

- one shared node's meaning set can be computed once while each consuming slot
  ranges over it independently;
- append, insert, verdict, and duplicate effects execute per consumption;
- shared and non-shared choices compose exactly;
- unambiguous sharing allocates no ambiguity-only state;
- separate accepting roots remain separate meanings.

Do not weaken semantics to match `FastTree` identity. If the forest lacks a
required occurrence edge, identify it and leave the gate open.

## B — exact-lane cost

The dirty cone bounds visited nodes, not multiplicity within a node. Define
that multiplicity from real packed families, child meaning sets, island
options, deduplication, and sibling accepting items.

Measure controlled cases covering collapsed derivations, early and late second
root values, interacting invisible substitutions, operation-law shortcuts,
and a genuinely exponential image. Investigate streaming early stop, exact
finite quotients, structural sharing, compile-time refusal, and runtime
resource refusal.

An arbitrary cap is rejected. If exponential exact settlement is unavoidable,
demonstrate it and recommend the narrowest honest refusal contract: what is
counted, when it refuses, which exception it uses, and what requires a user
decision. Exhaustion must never mean unambiguous, select a derivation, or fall
back to one-flip reasoning.

Keep ambiguity machinery off the unambiguous path. Measure one process at a
time using process CPU and an appropriate control. Do not run an MT benchmark.

## Report

`PROTOTYPE_16.md` must answer:

1. Does the candidate agree with the occurrence-unrolled oracle on every
   shared shape?
2. What identifies each consumption of a shared value?
3. Does the current forest retain enough information?
4. What is exact-lane cost in terms of real option lanes?
5. Which laws avoid enumeration without changing semantics?
6. Is exponential work unavoidable, and what refusal is recommended?
7. What remains an implementation gate, measurement gate, or user decision?
8. Does anything obstruct the settled resolver contract?

End with a short coordinator handoff: proved conclusions, disproved claims,
open gates, user decisions, and active-plan claims that should change. Do not
edit those active documents yourself.

## Sequential adversarial review

Finish and check the prototypes and draft report first. Call fresh, read-only
reviewers synchronously and sequentially. No other agent or measurement may be
active. **Do not use Fable.** In Claude Code use:

```text
subagent_type: general-purpose
run_in_background: false
description: <role>
prompt: <prompt below>
```

Use the strongest available reasoning model at high effort.

Reviewer 1 — shared occurrences:

```text
Read PROMPT_16.md, its inputs, both Round 16 prototypes, and the draft report.
Try to falsify the oracle's independence and every shared-DAG result. Look for
globally correlated keys, circular controls, node identity mistaken for
occurrence identity, missing nullable or synthetic sharing, and effects run per
node instead of per consumption. Verify the active packet was not edited.
Read-only; no benchmarks. Return substantive file:line findings and READY only
if the evidence is sound. Ignore prose nits.
```

Fix findings within the write allowlist, rerun, and record dispositions in
`P16_ADVERSARIAL.md`. Record active-plan findings without editing the plan.

Reviewer 2 — exact-lane cost:

```text
Read the revised Round 16 evidence. Falsify its bounds, early stops, quotients,
deduplication, and refusal rule. Require collapse-heavy, late-second-value, and
growing-image controls. Reject arbitrary caps, one-flip fallbacks, uncontrolled
timings, and unambiguous-path ambiguity state. Identify semantic choices that
require the user. Verify the settled resolver scope remains fixed. Read-only;
no benchmarks. Return substantive file:line findings and READY only if sound.
Ignore prose nits.
```

Fix, rerun, and record. Then call Reviewer 3 — closure:

```text
Audit PROMPT_16.md, its inputs, Prototype 15's limits, every Round 16
deliverable, and the before/after file record. Require an independent
occurrence-unrolled oracle, an honest exact-lane cost policy, correct
classification of open gates and decisions, preserved resolver scope, no
authorized parse regression, and no writes outside the allowlist. READY means
only that the evidence is fit for coordinator review; it does not approve the
plan or authorize implementation. Read-only; no benchmarks. Return substantive
blockers followed by READY or NOT READY. Ignore prose nits.
```

Copy Reviewer 3 verbatim to `REVIEW_16.md`. Record all prompts, findings,
fixes, reruns, and verdicts in `P16_ADVERSARIAL.md`. If the required Agent tool
is unavailable, write the prompts to `P16_REVIEWER_PROMPTS.md` and stop; do not
substitute Fable.

## Done

Run both prototypes sequentially. Run Ruff format/check and Pyright only on
them. Search for forbidden constructs, restore cache or bytecode changes, and
run `git diff --check`. Compare final state with the recorded baseline: the
round may change only its allowlisted files.

Reviewer 3 must return `READY`. That verdict approves only the evidence
package. It does not modify the plan, authorize source work, or accept a parse
regression.
