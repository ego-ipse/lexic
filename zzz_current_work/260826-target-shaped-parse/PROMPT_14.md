# Investigator prompt 14 — close the last investigable design gates

Work in `/home/mika/projects/lexic` on the active effort
`zzz_current_work/260826-target-shaped-parse/`.

Read, in order:

1. the supplied repository instructions and `docs/STYLE.md`;
2. this effort's `INDEX.md`, `context.md`, `goal.md`, `DESIGN.md`, `TODO.md`,
   `LEDGER.md`, and `CURRENT_BUG_REPORT.md`;
3. `reports/PROTOTYPE_13.md`, then the Prototype 10–12 reports only where
   Prototype 13 points back to evidence in them;
4. the prototypes and production seams named below.

The architecture remains green. This is the final investigation round before
implementation review, not production implementation. Do not edit `src/`,
`tests/`, `pyproject.toml`, the wiki, or the active planning documents. Revise
or add executable evidence only under this effort's `proto/`; never put a
prototype in `/tmp`. Deliver `reports/PROTOTYPE_14.md` and
`reports/P14_ADVERSARIAL.md`. Do not commit or push.

Strict constraints: no `eval`, `exec`, `Any`, `object`, cast-based erasure, or
ignore/suppression directive of any kind. Add no grammar-specific branch to
generic machinery, external model library, callback hot path, compatibility
layer, legacy alternative, or second parse API. Use `uv run` for Python tools.
Do not modify production code for instrumentation. Run one benchmark process
at a time; a multithreaded row owns the machine from preparation through pool
shutdown. JSON and Qwen are witnesses, never privileged clients.

## Established facts — do not reopen without a counterexample

- Complete requested-root meanings, not local trees, decide ambiguity.
- Ordinary same-production text allocation has the defined leftmost answer.
  Quantified-nullable occurrence counts are semantic families and are not that
  split case.
- Acyclic meanings use exact per-node semantic sets. One real family path which
  carries a differing slot injectively to a requested root is a sufficient
  early-refusal certificate; unrelated dropping parents do not invalidate it.
- Cyclic meanings use carrier-scoped zero-width SCCs under the selected
  `const` / `ident` / declared-`finite` / proper-subvalue-`grow` laws. Numeric
  family-census caps, semantic-lap caps, global assignment enumeration, and
  one-lap `FastTree` claims are rejected.
- `ambiguity_points` owns deferred Leo expansion. A caller-side materialize-
  first precondition is rejected.
- `lift_optional_nullables` may not erase an absent/present semantic family.
- The current tokenizer relation is exact only relative to today's two
  constructors. Three final validation lanes remain open.
- External custom-target pool lifetime is closed. Production completion
  traffic and paid-loop neutrality are implementation measurements.
- The external fused-product RSS control is only a protocol. It cannot prove
  zero future ambiguity allocations until landed factories are wired to a
  refusing control.

## A — lower real operations to the cyclic slot algebra

Inspect the actual action/reducer vocabulary and the product operations the
active design schedules. At minimum read:

- `src/lexic/ir/action/` and `src/lexic/ir/reduction.py`;
- `src/lexic/compile/foldkit.py`, `reduction.py`, and `reduce/fold.py`;
- every shipped GBNF, ABNF, EBNF, and JSON reducer/action declaration;
- `proto/ambiguity_interaction.py` and `proto/cyclic_meaning.py`.

Produce an executable, open-dispatch classification prototype over real
operation declarations. For every child slot which can participate in a
zero-width SCC, derive exactly one of:

- constant in that slot;
- identity in that slot;
- a declared finite image with its explicit domain bound;
- injective proper-subvalue growth;
- unsupported, with a binding-time refusal naming the operation and slot.

Do not classify by operation name, sample values, Python callable identity, or
a closed `isinstance` ladder. State the proof obligation each authored
operation must supply and show that an unknown future operation reaches the
raising default. Cover joint operations where one slot is dropped and another
is retained, validation/verdict operations, sequence and keyed accumulation,
scalar decode, record construction, and target-specific root finalization.
Separate facts which can be known from the present source from operations that
do not exist until the product compiler lands; do not invent production code
and call it audited.

Differential the derived classes against direct evaluation on small finite
domains and the existing cyclic witnesses. Try deliberately misdeclared laws
and require the checker or binding refusal to catch them. State time and memory
bounds in operations, slots, SCC nodes, and edges.

## B — construct a real resolver pair for an infinite SCC

`proto/cyclic_meaning.py` now decides an injectively visible growing SCC from
classification alone. That is enough to refuse, but `resolve=` needs two real
complete derivations associated with two different complete target meanings.

Prototype a constructive algorithm over a real finished Earley forest:

1. find a finite accepting base derivation which reaches the certified carrier;
2. select one explicit directed traversal of the growing zero-width SCC;
3. splice exactly that traversal into the base derivation once;
4. carry both alternatives through the certified family path to a requested
   accepting root;
5. evaluate and verify that their complete target meanings differ.

This is structural traversal, not “unroll twice,” a numeric lap count, bounded
search presented as proof, or a fabricated tuple meaning without a real
derivation. Prove termination and occurrence identity. Cover a unary unit
cycle, a multi-node/two-key cycle, a nested island source, sibling accepting
roots, a dropping root which must not request a pair, and a deep stack-safe
witness. If the selected algebra cannot construct a pair for some class it can
nonetheless classify, state the exact binding/runtime refusal boundary instead
of sampling.

Differential both produced trees and their meanings against an independent
bounded-depth oracle on small witnesses. The oracle is supporting evidence,
not the termination argument.

## C — settle every fact needed for the resolver-scope user decision

Do not choose policy on the user's behalf. Establish the consequences of the
two remaining public contracts:

1. today's island-local derivation pair;
2. two complete-document derivations whose requested target meanings differ.

Read the current `Resolver` definition and every PDA, Earley, island, and
`CompiledGrammar` call site. Extend `proto/resolver_pair.py` only as needed to
answer these questions with real structures:

- Can both engines present the same deterministic pair ordering?
- How is occurrence identity preserved with two or more islands and nested
  delegated regions?
- What can the fused PDA product present when it has no document `ParseTree`?
- Does complete-document scope require retaining a shadow model/tree on the
  unambiguous path? The answer must be no; otherwise reject that construction.
- Which scope preserves today's public resolver type, and which would require
  a deliberate pre-alpha API change?
- What extra cold-path work and retained state does each scope require?
- Can a context-sensitive resolver observably choose different results between
  the scopes? Retain a concrete witness.

Return a compact decision table and a recommendation with costs and invariants.
Mark the policy itself `USER DECISION REQUIRED`; evidence may close feasibility
questions but not silently select the API.

## D — author the tokenizer's final three validation lanes from evidence

Inspect all four fetched real fixtures, sequentially and without timing them
concurrently:

- `resources/tokenizers/qwen3.tokenizer.json`;
- `resources/tokenizers/gpt2.tokenizer.json`;
- `resources/tokenizers/smollm2.tokenizer.json`;
- `resources/tokenizers/gemma4.tokenizer.json`;
- the small fixture at
  `tests/integration/lexic/tokens/fixtures/hf_bpe.tokenizer.json`.

Read `src/lexic/api/json_tokenizer.py`,
`src/lexic/ir/text/tokenizer.py`, their tests, and
`proto/keyed_product_rows.py`. Inventory, with exact fixture counts/examples:

1. negative, sparse, repeated, and out-of-range vocabulary ordinals;
2. merge dyads whose spellings are absent from the vocabulary;
3. byte-fallback, unknown, fused-unknown, added-token, and pipeline spellings
   which are absent from or conflict with the vocabulary.

Then recommend the clean final pre-alpha contract. There is no legacy-support
obligation: current reader permissiveness is evidence, not authority. For each
lane state accepted inputs, ordered refusal, derived indexes, and whether the
constraint belongs during streaming accumulation or root cross-field
validation. Update the tokenizer meaning/refusal prototype to cover the chosen
candidate and differential it against a small independent constructor oracle.
Do not construct a full Qwen `IrMap` merely to inspect the format, and do not
run the historical slow tokenizer path.

Measure only work needed to distinguish candidate validation strategies. If a
large-fixture row is necessary, run it once in an isolated process and report
process CPU, wall, bytes scanned, and retained memory separately. Do not turn a
format-contract investigation into a parser benchmark.

## E — pin the two shipped bugfix baselines before source changes

Do not implement either fix. Extend the external evidence so the later source
phase has an uncontaminated reference:

- record current public/PDA/Earley behavior for every quantified-nullable case
  in `proto/nullable_quantifier_ambiguity.py`;
- retain the direct `0 -> 2` Leo readout proof with no intervening tree build;
- retain the census of all 15 shipped GBNF/ABNF/EBNF ground-truth grammars;
- time unchanged public parsing on the affected tiny witnesses and on small
  matched unambiguous controls, in alternating order and isolated from other
  benchmarks;
- specify the exact post-fix correctness differentials and parsing-regression
  comparison. A regression is not accepted by this report: even for a bugfix,
  the user gives the final go-ahead after isolated attribution.

The implementation plan must keep semantic-family classification in compiled
tables or an equally cold derived structure. Do not propose per-character
nullability checks, dynamic family classification, or instrumentation in the
paid loop merely to support tests.

## F — mandatory sequential adversarial review; Fable is forbidden

**Do not use Fable subagents. Do not call any `fable` subagent type, even if it
is available or recommended by a default tool description.** Use only fresh
`general-purpose` internal reviewers, synchronously and one at a time. Do not
start a reviewer while any benchmark, pool, or measurement process is alive.

Finish all prototypes, measurements, static checks, and the first complete
drafts of `reports/PROTOTYPE_14.md` and `reports/P14_ADVERSARIAL.md` yourself.
Then, in Claude Code, call each reviewer through the `Agent` tool with:

```text
subagent_type: general-purpose
run_in_background: false
description: <the review role below>
prompt: <the complete role prompt below>
```

If the tool exposes model or effort selection, use the strongest reasoning
model available at high effort. Each reviewer starts fresh and reads the files
from the repository. Reviewers are read-only: no edits, benchmarks, commits, or
pushes.

Reviewer 1 — description `cyclic semantics adversary`:

```text
Read the repository instructions, docs/STYLE.md, the complete target-shaped-
parse active packet, PROMPT_14.md, CURRENT_BUG_REPORT.md, every Prototype 14
file, and the draft PROTOTYPE_14.md/P14_ADVERSARIAL.md. Try to falsify the real-
operation slot classification, SCC termination/refusal boundary, and the
constructive infinite-SCC resolver pair. Look for name-based classification,
unproved operation laws, hidden numeric bounds, shared/circular oracles,
non-derivation witnesses, missing family/slot edges, nondeterministic pair
ordering, and claims broader than executable evidence. Do not edit or run
benchmarks. Return substantive findings with exact file:line evidence and say
READY only if no correctness or planning blocker remains. Ignore prose nits.
```

Wait for reviewer 1. Fix every substantive finding, rerun affected evidence
and static checks, and update both reports before reviewer 2.

Reviewer 2 — description `contract and performance adversary`:

```text
Read the same repository instructions and complete revised packet. Adversarially
review resolver-scope feasibility, tokenizer validation evidence, and shipped-
bug baselines. Check every real fixture rather than trusting reported counts;
challenge verdict ordering, hidden compatibility assumptions, full-structure
work disguised as streaming, instrumentation in a hot path, contaminated or
concurrent timings, and any parse-regression permission inferred from a
bugfix. Confirm JSON/Qwen are only witnesses and that non-GBNF grammar evidence
is real. Do not edit or run benchmarks. Return substantive findings with exact
file:line evidence and say READY only if no contract, evidence, or performance
blocker remains. Ignore prose nits.
```

Wait for reviewer 2. Fix every substantive finding and rerun affected evidence.
Then call reviewer 3 — description `final implementation-readiness audit`:

```text
Perform a fresh read-only closure audit of PROMPT_14.md, all Prototype 14 code
and reports, CURRENT_BUG_REPORT.md, and the active INDEX/context/goal/DESIGN/
TODO. Verify that established facts remain coherent, every investigable gate is
closed or precisely blocked, the resolver policy is still marked USER DECISION
REQUIRED, source implementation has not started, and no external prototype is
presented as production performance proof. Confirm the record contains all
earlier findings and fixes. Do not edit or benchmark. Return only substantive
blockers followed by READY or NOT READY, with exact file:line evidence.
```

Record every prompt, finding, fix, rerun, and verdict in
`reports/P14_ADVERSARIAL.md`. A `READY` verdict does not authorize production
implementation or accept a parsing regression.

If the `Agent` tool or `general-purpose` reviewer type is unavailable, **stop**.
Write the three complete prompts to `reports/P14_REVIEWER_PROMPTS.md`, record
that review could not run, and do not call the packet ready. **Do not substitute
Fable.**

## G — deliverable and done gate

`reports/PROTOTYPE_14.md` must separate:

- facts conclusively established by real source/fixture evidence;
- the resolver-scope user decision and its decision table;
- mechanisms ready for production implementation;
- implementation-time performance and memory proofs still required;
- rejected candidates and why they remain rejected.

Include exact commands and relevant complete outputs. Run Ruff format, Ruff
check, and Pyright over every prototype added or changed, then execute every
witness sequentially. Search touched code for every forbidden construct. Keep
generated bytecode and caches out of the deliverable. Do not edit active plans;
the coordinator folds accepted results after review.

The round is ready to fold only when all three sequential `general-purpose`
reviewers return `READY`, no substantive finding remains, and every claimed
measurement has a clean isolated provenance. Fable subagents are prohibited.
