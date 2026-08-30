# Investigator prompt 15 — compose cached island continuations and review the packet

Work in `/home/mika/projects/lexic` on
`zzz_current_work/260826-target-shaped-parse/`.

Read the repository instructions and `docs/STYLE.md`, then `INDEX.md`,
`context.md`, `goal.md`, `DESIGN.md`, `TODO.md`, `LEDGER.md`,
`CURRENT_BUG_REPORT.md`, `reports/PROTOTYPE_14.md`, and §5 of
`reports/P14_ADVERSARIAL.md`. Read these prototypes completely:

- `operation_slot_laws.py`;
- `route_continuation.py`;
- `root_meaning_incremental.py`;
- `island_alternate_seed.py`;
- `ambiguity_interaction.py`;
- `resolver_pair.py`.

Also inspect the production seams they model: PDA island execution, contextual
clones and frames; Earley ambiguity/readout; `ModelFold`; product binding/cache
ownership; and compile moments.

Do not edit `src/`, `tests/`, `pyproject.toml`, or `.wiki`. Put prototypes only
in this effort's `proto/`, never `/tmp`. Do not commit, push, create a worktree,
or run concurrent measurements. Use `uv run`. No `eval`, `exec`, `Any`,
`object`, casts, nested helpers, or ignore/suppression directive of any kind.
No grammar-specific branch may enter generic machinery. JSON is not privileged.

Deliver:

- `proto/island_continuation.py`;
- `reports/PROTOTYPE_15.md`;
- `reports/P15_ADVERSARIAL.md`;
- `reports/REVIEW_15.md` containing the final fresh review;
- coherent updates to the active `INDEX.md`, `context.md`, `goal.md`,
  `DESIGN.md`, `TODO.md`, and `LEDGER.md`, but only for conclusions established
  by executable evidence.

## The one missing proof

The mechanisms above exist separately. Prove their composition without
inventing a second architecture.

Compile one immutable island-to-requested-root continuation per contextual
occurrence. Its key and ownership must be explicit: contextual clone, child
slot/occurrence, requested root, and bound product; it is artefact-owned and
contains only flat operation/route data, never parse values or a callback.

Execute real grammar tables and real action/fold operations for these cases:

1. a continuation constant in the island slot: discard the alternate locally;
2. an injectively retaining continuation: prove root inequality locally;
3. a finite or otherwise non-injective continuation: execute the cached
   operation range on the actual alternatives and compare exact root meanings;
4. two interacting island choices where both one-flip comparisons equal the
   baseline but the joint choice differs;
5. multiple sibling islands and nested delegation, with occurrence identity;
6. an unambiguous control allocating no alternate, continuation execution,
   dependency graph, or resolver tree.

Use at least two grammar formulations or flavours. The constant/drop witness
must use a real reducer/action, not the toy policy dictionary from
`island_alternate_seed.py`. Compare every candidate result with independent
complete Earley folds over all small families. Reuse existing prototypes as
oracles; do not copy their implementations into a new monolith.

One-flip reasoning is rejected. Do not discard an alternative merely because
it equals the baseline under the other choices' baseline values. A local
shortcut is valid only under a compiled law/certificate that remains sound for
the complete exact family relation. State that certificate precisely.

The prototype must distinguish semantic settlement from resolver-tree
materialization:

- no full-document recognition is permitted for `const`, proved inequality
  without `resolve=`, or an actual-value comparison;
- complete document `ParseTree`s are constructed only after root inequality
  and an actual resolver;
- the existing `resolver_pair.py` splice/cold-recognition evidence remains the
  oracle for that last step; do not prototype it again.

Report structural counts and process CPU only where they answer a design
question. This is not a tokenizer or MT benchmark. No multithreaded benchmark
is permitted. Clearly separate what the external composition proves from the
production hot-path, memory, and parse-regression gates it cannot prove.

## Questions the report must answer

1. Can static `const` and injective laws settle their cases without propagating
   general ambiguity state?
2. What exact runtime data remains for a non-injective continuation?
3. How are interacting choices composed without Cartesian assignment
   enumeration or unsound one-flip pruning?
4. What is cached once, what is parse-local, and when is each released?
5. Does ordinary island recognition remain local and byte-for-byte outside the
   prototype?
6. After this proof, what precisely remains of the resolver-scope user
   decision? Do not choose that public contract for the user.
7. Is any planning or prototype gate still open before source implementation?

## Mandatory sequential adversarial review

Finish the prototype, report, active-document fold, reruns, Ruff, and Pyright
before calling reviewers. Reviewers are fresh, read-only, synchronous, and
strictly sequential. No benchmark or measurement process may be alive while a
reviewer runs. **Do not use Fable or any `fable` subagent type.**

In Claude Code call the `Agent` tool exactly as follows:

```text
subagent_type: general-purpose
run_in_background: false
description: <role below>
prompt: <complete role prompt below>
```

Use the strongest reasoning model available at high effort if the tool exposes
that choice.

Reviewer 1 — `island semantics adversary`:

```text
Read the repository instructions, STYLE, the complete target-shaped-parse
packet, PROMPT_15.md, every prototype it names, island_continuation.py, and the
draft Prototype 15 report. Try to falsify static continuation settlement,
cache identity/lifetime, exact multi-island composition, occurrence identity,
and the complete-Earley oracle. Look specifically for one-flip reasoning,
baseline-dependent convergence, toy policies presented as real operations,
grammar-specific assumptions, circular oracles, and claims broader than the
executable witness. Read-only; no edits or benchmarks. Return substantive
findings with exact file:line evidence and READY only if none remain. Ignore
prose nits.
```

Wait, fix every substantive finding, rerun affected evidence, and record the
finding and disposition in `P15_ADVERSARIAL.md`.

Reviewer 2 — `island performance and architecture adversary`:

```text
Read the same revised packet. Determine whether the proposal preserves PDA
islands or merely renames whole-document escalation. Challenge every claimed
hot-path absence, allocation count, cache owner, release boundary, resolver
tree cost, and static shortcut. Check that unambiguous parsing receives no new
state or callback and that complete trees are built only for an invoked
resolver after root inequality. Confirm that production measurements remain
open and no external timing is called a source result. Read-only; no edits or
benchmarks. Return substantive file:line findings and READY only if none
remain. Ignore prose nits.
```

Wait, fix and rerun. Then call Reviewer 3 — `final packet closure audit`:

```text
Freshly audit PROMPT_15.md, the complete revised active packet, Prototype 14
and its coordinator correction, all Prototype 15 deliverables, and the current
working-tree diff. Verify that every established claim is executable, every
remaining decision/planning/implementation gate is labelled accurately, no
source or test changed, no parse regression is authorized, and the resolver
scope is not silently selected for the user. Read-only; no edits or benchmarks.
Return only substantive blockers followed by READY or NOT READY, with exact
file:line evidence. Ignore prose nits.
```

Copy Reviewer 3's final response into `reports/REVIEW_15.md`. Record every
review prompt, finding, fix, rerun, and verdict in `P15_ADVERSARIAL.md`.

If the `Agent` tool or `general-purpose` type is unavailable, stop. Write the
three complete prompts to `reports/P15_REVIEWER_PROMPTS.md`; do not substitute
Fable and do not call the packet ready.

## Done gate

Run every changed prototype sequentially. Run Ruff format/check and Pyright
only over changed prototype files. Search touched code for every forbidden
construct. Restore any generated cache or bytecode change. `git diff --check`
must pass, and `git status --short -- src tests pyproject.toml .wiki` must be
empty.

The round is complete only when all substantive reviewer findings are fixed,
Reviewer 3 returns `READY`, the active documents agree, and the report states
exactly what remains for implementation and user decision. `READY` neither
authorizes source implementation nor accepts any parsing regression.
