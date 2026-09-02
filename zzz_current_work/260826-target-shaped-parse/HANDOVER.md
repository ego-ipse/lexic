# HANDOVER — §4 exact current state (2026-09-02)

`TODO.md` is the execution queue. Its checkbox bullets are the only work units.
This handover records the current tree, the rejected review disposition, and the
exact restart point. It does not replace or subdivide any TODO bullet.

## Repository state

- HEAD is `f074ed9b` (`WIP. Savepoint 7. Not verified. User commit`).
- The source tree at HEAD is identical to source at `b6471f48` (Savepoint 6).
- Savepoint 6 and Savepoint 7 are explicitly unverified.
- No subagent is running. `terra_s4_completion_ranges` was killed at the user's
  direction before making source changes. `terra_s4_audit` was also killed, and
  its JSONL was deleted at the user's direction. Neither produced a durable
  report.
- No completion-range, island/delegate/stitch, trace, foldkit, deletion, or
  value-string-specialization source work was performed after the rejected
  source review. There is therefore no later agent work to preserve or accept.

## Review disposition: NEEDS WORK; not accepted

The last source handoff was reviewed and rejected. It must not be treated as an
accepted §4 source result.

The following corrections from that review are present in the current source:

- product completion's final owner is `src/lexic/parsing/product/tree.py`;
- completion uses explicit `Completed[Carry] | EmptyResult`, so a valid Python
  `None` is not confused with absence;
- `PayloadLeaf[Carry]`, `MeaningMemo`, and ambiguity replay remain generic;
- `different_meaning` classifies sibling roots and real authored arm choices
  before allocating the memo; a no-choice parse builds the first tree once;
- `ProductExecutor` caches `wants_spans` once;
- `FlatClone[Carry]` has typed `ctor`, `plan`, `fast`, and `defaults` fields.

The handoff still fails the §4 `Carry` bullet. The PDA runtime frame, output,
and sink path erases `Carry` through positional list frames and
`list[Any]`/`list[list[Any]]` annotations in the runtime kernel, admission,
decisions, and execution path. The suggested replacement with a new slotted
`Frame[Carry]` was not accepted and was not implemented: the repository
instructions explicitly protect the existing hot-path mutable/list shape, and
the TODO bullet forbids an unmeasured frame-representation change. The required
result is honest generic typing through the existing paid path without a cast,
suppression, extra branch, slot, allocation, compatibility wrapper, or
unmeasured representation change.

Any proposed follow-up beyond the current source is discarded. The current
tree is the Savepoint 6 source as committed in Savepoint 7; the later
completion-range agent made no source edits, so there was nothing further to
revert.

## TODO §4 status

Eight §4 bullets are closed in `TODO.md`:

- the regular-proof planning prerequisite;
- authored generated-model `RuleProduct`/`RecordConstructor` construction;
- synthesis/binding authoring of the model product;
- one bound product through PDA and Earley parse entry;
- `CloneSpec`/`PdaCompiler` product carriage and lowering;
- typed `FlatClone` construction operands through `ConstructionTables`;
- ordinary PDA completion through the common product data;
- ordinary Earley/model completion through `ProductExecutor`.

Every unchecked §4 bullet remains open. The production-source bullets still
requiring implementation and review are, in TODO order:

- delete `FOLD_KINDS`, `FieldFold`, `FastCtor`, `RuleFold`, `ModelBody`, and
  `ModelFold` after all callers move;
- rewrite `parsing/trace.py` with its public surface unchanged;
- migrate `compile/foldkit.py`, notation, and generated-self-grammar authoring
  to the final vocabulary;
- give every contextual PDA clone, Earley/token completion, attempt sub-clone,
  island, and delegate exactly one verified tagged completion range;
- carry `Carry` without erasure through PDA frames, outputs, and sinks;
- lower operations to engine-owned data and closed integer dispatch;
- implement the generic regular-proof-backed value-string specialization;
- migrate island/delegate completion and parallel stitch/replica field-layout
  reads to the product construction data;
- compare the generated-model flat programs/opcode streams and explain or
  remove every added paid-loop opcode;
- preserve the existing direct generated-model completion/frame shape as the
  zero-tax baseline unless a measured faster simplification justifies change.

The §4 source-verification bullets are also open: the relevant existing tests,
`uv run python tools/check_generated.py`, and the final TODO/LEDGER evidence
update. External profiling, performance acceptance, commit work, and Luna's
test/lint work have not started and must not start before the user-directed
hold is reached and the user resumes the effort.

## Evidence status

Evidence obtained before the final Savepoint 6 typing edits includes:

- focused syntax compilation: exit 0;
- focused Pyright: exit 0;
- product/fold tests: 87 passed;
- ambiguity support plus PDA fallback/parity and group-attempt tests: 58 passed;
- templating spans, artifact, and parsing-surface tests: 94 passed;
- shared-forest and dirty-cone witnesses: PASS;
- §4 switch differential: PASS for 14 grammars, 107 documents, and 6 expected
  PDA declines.

Those results predate the final Savepoint 6 edits and do not certify the exact
current source. No current-tree full suite, generated-twin check, external
profile, benchmark, or final performance comparison exists.

## Exact restart point

Resume directly from the unchecked §4 TODO bullets. The last reviewed source
is still **NEEDS WORK** because the `Carry` frame/output/sink typing bullet is
unresolved. Complete and review every production-source bullet in §4, updating
the corresponding TODO bullet when its actual state changes. Then run the §4
source-verification bullets, update TODO and LEDGER with the exact evidence,
and hold. Do not begin external profiling, a commit, or Luna's test/lint work
until the user explicitly resumes after that hold.

Any future subagent must write its durable report under this effort before its
work can be handed back for coordinator review.
