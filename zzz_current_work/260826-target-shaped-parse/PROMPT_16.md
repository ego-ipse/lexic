# Investigator prompt 16 — shared occurrences and the exact-lane bound

Work in `/home/mika/projects/lexic` on
`zzz_current_work/260826-target-shaped-parse/`.

Read the repository instructions and `docs/STYLE.md`, then `INDEX.md`,
`context.md`, `goal.md`, `DESIGN.md`, `TODO.md`, `LEDGER.md`,
`reports/PROTOTYPE_15.md`, `reports/P15_ADVERSARIAL.md`, and
`reports/REVIEW_15.md`. Read these prototypes completely:

- `island_continuation.py`;
- `shared_forest_refold.py`;
- `ambiguity_interaction.py`;
- `cyclic_meaning.py`;
- `operation_slot_laws.py`;
- `root_meaning_incremental.py`.

Inspect the production Earley forest, `FastTree`, ambiguity readout, fold walk,
and completion tables which those prototypes model.

Do not edit `src/`, `tests/`, `pyproject.toml`, or `.wiki`. Put prototypes only
in this effort's `proto/`, never `/tmp`. Do not commit, push, or create a
worktree. Use `uv run`. No `eval`, `exec`, `Any`, `object`, casts, nested
helpers, or ignore/suppression directive of any kind. No grammar-specific
branch may enter generic machinery. JSON is not privileged.

Deliver:

- `proto/shared_occurrence_ambiguity.py`;
- `proto/exact_lane_cost.py`;
- `reports/PROTOTYPE_16.md`;
- `reports/P16_ADVERSARIAL.md`;
- `reports/REVIEW_16.md` containing the final closure review;
- coherent updates to `INDEX.md`, `context.md`, `goal.md`, `DESIGN.md`,
  `TODO.md`, `LEDGER.md`, and `SUMMARY.md`, limited to conclusions established
  by executable evidence.

## 1 — close shared-occurrence composition

Prototype 15's mechanism gives every grammatical occurrence an independent
family choice, but its complete-fold oracle fixes one choice per packed key.
Every delivered witness asserts that no completed node has two parents and no
choice key is claimed twice. That leaves the exact case the repository already
knows exists: a forest node shared by multiple occurrences.

Start from all four real shapes in `shared_forest_refold.py`:

- duplicate slot;
- pending frame;
- sibling memo;
- transparent synthetic node.

Put semantic ambiguity under each shared shape. At least one witness must make
the independently mixed occurrence choices observable only jointly, so a
globally key-correlated oracle produces a different answer and is explicitly
disproved. Exercise both an internal packed family and, where the real engine
can express it, a delegated island option beneath a shared completion.

The control is an occurrence-unrolled complete-derivation oracle. It must give
each occurrence path its own family decision even when the packed forest reuses
one node or one ambiguity key. It may not call the candidate's per-node set
function, reuse its deduplication, or key choices globally. Fold real authored
reducer operations over real derivations.

Compare the candidate exact relation with that oracle on every witness. Pin all
of these separately:

- a shared node's semantic set is computed once;
- each consuming parent slot ranges over that set independently;
- occurrence-owned append, insert, verdict, and duplicate effects execute per
  slot consumption rather than per shared node;
- interacting shared and non-shared choices remain exact;
- ordinary unambiguous sharing allocates no ambiguity-only state;
- separate accepting root items remain separate complete meanings.

Do not weaken grammar semantics to match `FastTree`'s current object sharing.
If the intended occurrence-unrolled relation cannot be represented by the
current forest, report the precise missing edge or occurrence identity and keep
the planning gate open.

## 2 — decide what bounds the exact lane

Prototype 15 replaces a linear one-flip probe with a local option product. Its
dirty cone bounds the number of nodes visited, not the multiplicity paid at one
node. Determine the exact cost and the strongest sound way to avoid an
unbounded accidental explosion.

Define local multiplicity from real chart data: packed families, child meaning
sets, island options, semantic deduplication, and sibling accepting items.
Build a controlled ladder which separates:

- many derivations collapsing to one requested value;
- the second distinct root value appearing early;
- the second distinct root value appearing only after substantial work;
- interacting children whose individual substitutions are invisible;
- operation laws which settle without enumeration;
- a product whose exact image genuinely grows exponentially.

Investigate, do not assume, these possible levers:

- streaming products with immediate stop after a certified second root value;
- operation-law image bounds and exact finite quotients;
- memoized/persistent target meanings and structural sharing;
- compile-time refusal for an operation whose exact relation is not
  representable;
- runtime resource refusal when exact settlement exceeds a declared budget.

An arbitrary numeric cap is not a solution. If no generic exact algorithm can
avoid exponential work, demonstrate the lower-bound witness and state the
narrowest honest refusal contract: what is counted, when it refuses, which
exception it uses, and whether choosing that resource policy requires the
user's decision. Never turn exhaustion into “unambiguous,” choose a derivation,
or silently fall back to one-flip evaluation.

The resulting production rule must keep all ambiguity machinery off the
unambiguous path. This round does not authorize any base-parse regression.
Measure only prototype mechanisms, one process at a time, with process CPU and
a control wherever a timing carries a conclusion. No multithreaded benchmark
belongs in this round.

## Questions the report must answer

1. Do the per-node relation and an occurrence-unrolled oracle agree on every
   real shared-DAG shape?
2. What identity distinguishes a shared value from its consuming occurrences?
3. Does the current forest carry enough information, or must production retain
   another occurrence edge?
4. What is the exact local-product cost as a function of the real option lanes?
5. Which operation laws avoid enumeration without changing semantics?
6. Is exponential work unavoidable for an admitted product, and if so what
   exact refusal contract is recommended?
7. Which conclusions are architecture, which remain implementation gates, and
   which require an explicit user decision?
8. Does any new evidence threaten the settled complete-document resolver-pair
   scope? Preserve it; do not reopen the public contract.

## Mandatory sequential adversarial review

Finish both prototypes, the report, the active-document fold, reruns, Ruff, and
Pyright before calling reviewers. Reviewers are fresh, read-only, synchronous,
and strictly sequential. No measurement or other agent may be alive while one
runs. **Do not use Fable or any `fable` subagent type.**

In Claude Code call the `Agent` tool exactly as follows:

```text
subagent_type: general-purpose
run_in_background: false
description: <role below>
prompt: <complete role prompt below>
```

Use the strongest available reasoning model at high effort if the tool exposes
that choice.

Reviewer 1 — `shared-forest semantics adversary`:

```text
Read the repository instructions, STYLE, the complete target-shaped-parse
packet, PROMPT_16.md, every prototype it names, and the draft Prototype 16
report. Try to falsify occurrence-unrolled ambiguity semantics on every shared
DAG shape. Look for globally correlated packed-key choices, a circular oracle,
tree-object identity confused with grammatical occurrence identity, missing
nullable or synthetic sharing, duplicated value work, and occurrence effects
executed per node. Read-only; no edits or benchmarks. Return substantive
findings with exact file:line evidence and READY only if none remain. Ignore
prose nits.
```

Wait, fix every substantive finding, rerun affected evidence, and record the
finding and disposition in `P16_ADVERSARIAL.md`.

Reviewer 2 — `exact-lane complexity adversary`:

```text
Read the revised packet and both Round 16 prototypes. Try to falsify every
claimed complexity bound, early stop, quotient, deduplication, and refusal
rule. Demand a worst case where many candidates collapse, a late second value,
and a genuinely growing image. Reject arbitrary caps, one-flip fallbacks,
timings without controls, and any ambiguity allocation on the unambiguous
path. Check whether the proposed refusal changes public semantics and therefore
requires a user ruling. Read-only; no edits or concurrent measurements. Return
substantive findings with exact file:line evidence and READY only if none
remain. Ignore prose nits.
```

Wait, fix and rerun. Then call Reviewer 3 — `final packet closure audit`:

```text
Freshly audit PROMPT_16.md, the complete revised active packet, Prototype 15's
explicit limits, every Round 16 deliverable, and the working-tree diff. Verify
that shared-occurrence composition is closed only if an independent unrolled
oracle proves it, the exact-lane cost policy is stated without hiding a semantic
decision, every remaining planning/user/implementation gate is labelled, no
source or test changed, no parse regression is authorized, and resolver scope
remains the settled complete-document contract. Read-only; no edits or
benchmarks. Return only substantive
blockers followed by READY or NOT READY, with exact file:line evidence. Ignore
prose nits.
```

Copy Reviewer 3's final response into `reports/REVIEW_16.md`. Record every
review prompt, finding, fix, rerun, and verdict in `P16_ADVERSARIAL.md`.

If the `Agent` tool or `general-purpose` type is unavailable, stop. Write the
three complete prompts to `reports/P16_REVIEWER_PROMPTS.md`; do not substitute
Fable and do not call the packet ready.

## Done gate

Run changed prototypes sequentially. Run Ruff format/check and Pyright only on
the changed prototype files. Search them for every forbidden construct. Restore
generated cache or bytecode changes. `git diff --check` must pass, and
`git status --short -- src tests pyproject.toml .wiki` must be empty.

The round is complete only when substantive findings are fixed, Reviewer 3
returns `READY`, and the active documents distinguish established semantics,
remaining implementation work, and user decisions. `READY` neither authorizes
source implementation nor accepts a parsing regression.
