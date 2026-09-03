# Review 17 — §4 implementation and performance gate

> **NO GO — CORRECT THE IMPLEMENTATION AND PERFORMANCE GATE BEFORE LINT.**
>
> This is an actionable checkpoint review. It preserves the implementation
> that is sound, names the remaining failures, and gives a concrete replacement
> for the benchmark and ratchet protocol. It requires no compatibility path:
> Lexic is pre-alpha, and obsolete production APIs and implementations are to be
> deleted rather than retained, wrapped, aliased, or folded.

## Scope

Read-only review refreshed on 2026-09-03 against Savepoint 11 (`c9c72fc6`)
plus the visible Luna and S4D worktree. Comparison anchors remain `0faa7289`
(effort baseline) and `dffa821f` (product-completion restart).

The pass re-read the authored and flat product ABI, lowering, verification,
verified-program readback, model executable, Earley and token completion,
PDA bake, regular-region proof, ambiguity settlement, the current tests, and
the §4 plan and reports. It then reviewed the benchmark row construction,
isolated-worker lifecycle, current/base comparator, checked-in ratchet,
performance workflow, and pre-commit hook. One isolated runtime diagnostic
tested the claimed verification and immutability boundaries. The focused
product, proof, tree, executable, and ambiguity tests pass: 98 passed in
1.47 seconds.

No benchmark was run: the present protocol cannot produce acceptance evidence,
and running it on a non-reserved machine would add noise rather than knowledge.
No source, test, prototype, benchmark, or plan file was changed by this review.
Only this renamed report and its index/reference entries were edited.

## Assessment

The architecture has materially improved since the previous snapshot. Two of
its largest blockers are closed at the root:

- regular-region proof now propagates occurrence-local continuation through
  named references and includes the soft FOLLOW at the eligibility boundary;
- authored rules no longer survive beside the executable. Earley, tokens,
  PDA bake, islands, delegates, stitch, and replicas consume `RuleRoutine`
  records read back from the verified flat program, with construction resolved
  once per rule rather than once per completed node.

The migration should not be discarded. It is not yet ready for the §4
checkpoint. Two current contracts are false under ordinary runtime mutation,
one current completion shape reaches the runtime without having been verified
as executable, and the in-progress duplicate-code cleanup buys lint cleanliness
with avoidable allocations on both ordinary and ambiguous parse paths. The
outstanding erasure boundary also remains outside the user's one explicit
residue ruling.

The current performance gate is also not capable of proving no regression.
It mixes concurrent preparation into a supposedly uncontended run, compares
parallel and sequential modes on different documents, disables the collector
during production acceptance timing, lets implementation behaviour change a
row's directives, and treats a changed machine-specific baseline as approval.
Those are measurement-definition failures. They must be corrected before any
numbers are used to admit §4.

## Current §4 blockers

### High — the verified executable can be changed after verification

`src/lexic/parsing/executable.py:98-115` correctly discards authored
rules and derives routines from the verified `ProductProgram`. It then stores
`codes` and `routines` as ordinary mutable dictionaries. The executor holds
the exact same routine dictionary, and `CompiledGrammar.product` exposes the
`ModelExecutable` publicly. `replica()` at `:149-153` also shares the original
`codes` dictionary by identity.

The isolated diagnostic established all four facts:

```text
types dict dict
executor_alias True
program_rules_after_mutation 1
executor_routines_after_mutation 0
```

Clearing `binding.routines` therefore changes what the parser executes while
leaving the verified program untouched. The authored twin is gone, but an
unverified mutable projection can still diverge from the authority it was read
from. The current test explicitly pins the alias and the mutable container;
it does not pin immutability.

The nested program also needs the same audit. `RecordConstructor.defaults` and
`Construction.defaults` retain caller-provided mappings; model synthesis
supplies mutable dictionaries. `LoweredRoute` instances have writable slots,
and `TableRoute.lookup` retains a mapping. A `NamedTuple` around mutable or
writable descendants is not an immutable program.

This does not require a mapping proxy in a frequent lookup. Worker-local plain
dictionaries may remain the executor's private physical projection where the
measured free-threading design requires them. The contract requires that users
and unrelated consumers cannot mutate those dictionaries after verification,
and that recursively retained declaration/program data is frozen at the cold
binding boundary. The hot reader and the public read-only view need not be the
same object.

### High — verification accepts a completion that cannot execute

The verifier at `src/lexic/parsing/product/verify.py:95-101` checks table
shape, exact integer coding, range bounds, opcode
rows, and several operand-table bounds. It does not verify the semantic
relations the current model executor relies on.

A `ModelExecutable` containing a rule with no captures and `PassOp(0)` binds
successfully. Its verified routine is:

```text
RuleRoutine(completion=0, modes=(), slots=(), n_items=0,
            source=0, construction=None)
```

`product/tree.py::_passed_value` can only discover later, while completing a
parse, that source 0 has no capture. This is not a future generic-operation
gap: PASS is a current §4 model completion, and the invalid form is already in
`tests/unit/lexic/parsing/test_executable.py:30-35`.

Before the program is called verified, the cold gate must validate at least
the current executable relations:

- a PASS source exists and names a single-value capture;
- a RECORD completion's capture count agrees with its names;
- optional indices are in range;
- constructor names, defaults, matched-text ownership, and licensed field
  order are mutually consistent;
- an operation unsupported by the current executor is refused by the binding
  that proposes to execute it, rather than represented as
  `source == -1, construction is None` and rejected on first use.

Decoder vocabulary, route destinations, continuation paths, and later
expression relations still need verification before their owning stages
execute them. They do not excuse the malformed current PASS.

### High — the lint cleanup adds unnecessary allocations to parse paths

The current unstaged ambiguity cleanup correctly centralizes the duplicated
resolver tail in `chosen_meaning`. It also introduces `MeaningPolicy` in
`src/lexic/parsing/earley/kernel/forest/support/ambiguity.py:180-199`, a new
`NamedTuple` constructed by `ModelExecutable.meaning_policy()` at
`src/lexic/parsing/executable.py:117-131` on every Earley and token parse.

The previous path already allocated one `MeaningBuilder`. The new path
allocates that builder and then wraps it with a second tuple solely to carry
`resolve`. The PDA fast route does not pay it, but every Earley fallback and
token-segmented parse does. No semantic need for the wrapper remains once
`chosen_meaning` owns settlement.

Parsing may not regress, and eliminating a lint duplicate is not permission to
add even a small unconditional parse cost. Keep the centralized settlement,
but pass its existing builder and resolver without manufacturing another
policy value, or show a faster measured shape.

The same cleanup also replaces the allocation-free nested alternate loop with
`_flips()`, which eagerly builds a `list[Flip]` containing every non-default
family at every ambiguity point before testing the first one. The old loop
allocated no per-alternate carrier and stopped as soon as it found a differing
meaning. The new form pays O(number of alternate families) temporary tuples
even when the first alternate settles the question. That population is input-
and grammar-dependent and unbounded; it is not an acceptable trade for making
`replayed()` take one fewer scalar parameter.

Keep `chosen_meaning` and the useful extraction of sibling settlement. Remove
both lint-shaped carriers and retain early, allocation-free iteration. This is
structural accounting, not a request for a microbenchmark while the tree is
moving.

### Medium — type cleanup replaces explicit contracts with dynamic scaffolding

`src/lexic/parsing/product/abi/construction.py:168-181` removes the prohibited
cast and its
protocol, but replaces them with `getattr(cls, "fast_construct", None)`. This
makes the type checker stop describing the boundary by making the boundary
dynamic. The call is cold, so this is not a hot-path performance finding; it is
still the wrong resolution of the type-design problem. Licensed and unlicensed
constructor declarations have different capabilities and should be represented
structurally rather than recovered by reflection after a boolean flag grants
the capability.

The test cleanup follows the same pattern.
`tests/unit/lexic/parsing/product_test_helpers.py:65-85`
is an untyped reflective reimplementation of `NamedTuple._replace`, added only
because the current pylint/astroid pair cannot see the inherited method on PEP
695 generic named tuples. It reads `__annotations__`, reconstructs arbitrary
records positionally, and needs its own tests. That is substantial test
infrastructure whose only product is silencing a linter defect.

The shared `Pair`, operand, and two-capture fixtures are reasonable duplication
removal. The reflective replacement machinery is not. STYLE explicitly says
not to contort code around a linter; a linter finding that cannot be removed
without weakening types or inventing a second generic record constructor must
be taken to the user as a tool defect, not converted into architecture.

### High — the no-erasure gate remains open outside the ruled residue

The user explicitly accepted one named `list[Any]` sink residue after its frame
alternative measured no benefit. That ruling is narrow. It does not waive new
`object` boundaries elsewhere in the product architecture.

Current effort additions still include:

- `LoweringOwned.registry: Mapping[str, Callable[..., object]]`;
- `_field_order`'s `tuple[object, Mapping[str, object], ...]` licence shape;
- `_model_defaults(...) -> Mapping[str, object]`;
- `verify_exact_ints(values: Iterable[object], ...)`.

These are precisely the heterogeneous boundaries for which the design requires
named protocols, carrier parameters, or concrete table shapes. They cannot be
declared closed by the separate frame ruling. No ignore directive was found in
the reviewed current product delta.

## Benchmark and ratchet blockers

These findings apply to the existing benchmark infrastructure, not to timed
instrumentation in `src`. Their resolution belongs under `tools/benchmark/`
and the external effort reports. Nothing here licenses touching a production
hot path to observe it.

### High — the current/base comparator runs the current harness against both APIs

`tools/benchmark/compare.py:44-70` gives each job a `source_root`.
`tools/benchmark/execution/isolation.py:68-77` only prepends that directory to
`PYTHONPATH`; `_command` still launches
`tools.benchmark.execution.worker` from the current checkout. The baseline
worker therefore imports the current benchmark modules against the old source
tree. This effort demonstrates the failure concretely: `0faa7289`'s own
benchmark reads `CompiledGrammar.fold` and `ModelFold`, while the current
benchmark reads the replacement executable product. The row cannot start.

Do not add a `fold` alias, a conditional import, an attribute probe, or any
other compatibility seam. Run each revision's own worker from that revision's
tree root, with its own `tools` and `src` first on `PYTHONPATH`. The worker
protocol already exists at all three comparison anchors; only the production
API references differ. Executing a historical revision with its historical
benchmark is measurement of the baseline, not support for that API in current
Lexic. Current source retains only the new architecture.

Apply the protocol/clock corrections to `tools/benchmark` in both measurement
copies while leaving both `src` trees byte-identical to their revisions. Each
copy keeps only its native API reference; neither gains a branch for the other.
The instrumentation patch and its digest belong in the measurement report.

The parent comparator should schedule and validate results; it must not import
either revision's Lexic or benchmark cases. A result must carry an exact row
contract, and base/head timing begins only after those contracts compare equal.

### High — supposedly uncontended preparation overlaps real parses

`tools/benchmark/execution/isolation.py:140-183` starts up to
`_PREPARE_WIDTH` workers
before timing the first. `_PREPARE_WIDTH` is as high as 16. Before a worker says
it is ready, `_build` compiles its grammar and `one_engine` performs fidelity
parses; variant construction can compile and run watched PDA trials. Prepared
workers also remain alive, holding their artefacts and any retained pools,
while another worker is timed.

Serializing only the final `_result` call does not make that run uncontended.
It permits multiple multithreaded parses during preparation and contaminates
cache, allocator, memory, and thermal state before measurement.

Delete the cohort/wait design from acceptance and regression runs. One process
must own the machine for its complete lifecycle: start, build, validate, warm,
time, close, exit. Only then may the next process start. Alternate whether base
or head goes first for successive pairs. A byte-identical control uses the
same lifecycle. There is no special exemption for “untimed” benchmark work.

### High — the execution-mode ratchet compares different documents

`tools/benchmark/regression.py:136-152` always sends `full=False`.
`tools/benchmark/bench.py:513-546` nevertheless
chooses `bench.full` for every MT row and `bench.corpus` for its sequential
reference. `_relations` then requires `lexic-mt <= lexic-pda` and
`lexic-mt-lex-ns <= lexic-lex-ns` by comparing normalized microseconds per
character from those different documents.

That is not a speedup measurement. Fixed costs, document shape, cache state,
and split eligibility differ with scale; normalization cannot make the two
parses the same work.

Execution-mode relations require dedicated paired jobs in which both modes
parse the exact same full document. Their row contract must include the input
digest and byte length, not merely the grammar and display label. Keep the
small-document sequential rows for their own regression history, but never use
them as the denominator for full-document MT claims.

### High — the acceptance clock and collector state do not match production

`tools/benchmark/bench.py:549-563` disables GC around every timed parse and
unconditionally enables
it afterward. Production parsing does not disable the collector, and the active
measurement contract requires collector-enabled acceptance rows. Besides
masking allocation and cycle-creation costs, the current function leaves the
collector disabled if parsing raises.

The worker records only wall microseconds per character. That contradicts both
STYLE's CPU-time rule and this effort's requirement to report MT aggregate
process CPU/core-seconds beside wall. Wall is the primary speedup quantity for
parallel latency; it cannot be allowed to hide a path that burns materially
more total CPU per byte.

Acceptance runs must leave GC enabled, record that fact, and collect outside a
timed observation only when the same operation is applied to both arms. Record
both `process_time` and `perf_counter` for every observation. Sequential
regression uses CPU as its primary clock and reports wall; MT reports wall as
its latency result and aggregate process CPU both absolutely and per byte.
Correctness, engagement/refusal, requested and effective cores, and source and
result digests accompany the timing rather than being inferred later.

### High — a row's directives currently depend on the implementation being measured

`tools/benchmark/bench.py:226-262` starts with grammar-derived marks and then
calls `_licensed_marks` at `:279-307`. That function compiles trial variants
against the current
engine, runs the corpus, counts PDA decisions, and removes marks until the row
is no slower or incapable. Consequently the same row label can denote different
directives in two revisions. It can also hide exactly the regression the row
exists to expose by making the candidate workload easier.

Delete `_licensed_marks`, `_decision_cost`, `variant_marks`, and the generic
noise-name heuristic. Extend each `Bench` case with its exact authored lexical
and non-semantic directive sets. Validate those declarations against the case's
grammar, but never rewrite them in response to engine eligibility or speed.
This is benchmark-case data, not grammar-specific logic in Lexic. A revision
that cannot execute the unchanged row reports a refusal; the harness does not
drop directives, raise the 2 KiB floor, suppress the grammar, or discard any
of the 72 rows to earn a number. If base and head report different directive
sets or source/input digests, the comparator refuses the comparison before
timing it.

### High — the fixed baseline and five-percent rule cannot serve as the gate

`tools/benchmark/regression.py:344-375` compares local results with a
checked-in table that has no
machine or protocol identity. It can automatically lower stored targets, can
raise them through `--accept-regression`, and the A/B comparator's
`accepted_rows` then omits any row whose checked-in value increased. A baseline
diff is not proof that the user approved the measured production regression,
and an approved regression must still appear in the report. The A/B exemption
is at `tools/benchmark/compare.py:144-182`.

The fixed five-percent threshold is also the wrong boundary. It can admit a
stable four-percent parse regression even when the byte-identical control is
far tighter, or reject noise on a machine whose control spread is wider.
`confirmation` compounds the problem by converting every still-uncertain row
at the hard sample bound into a median and declaring uncertainty empty.

Split the responsibilities:

1. The change gate is a same-session, alternating base/head comparison using
   independent fresh-process pairs and a byte-identical two-tree control.
2. For each pair, reduce a few inner parses to one process-level observation;
   do not count many passes in one process as independent structural samples.
3. Compare paired base/head log ratios against the control-ratio envelope with
   a predeclared confidence interval. A slower interval outside the control
   envelope fails. An overlapping interval earns more pairs; exhausting the
   bound is inconclusive and blocks or requests a clean rerun, never a forced
   median verdict.
4. Measure same-tree execution health separately: full-document cores
   1/2/4/8/16/AUTO, one complete process at a time, for every eligible split
   shape. If AUTO loses after a clean run, fix policy, planning, parsing, or
   stitch duplication. Do not raise the 2 KiB floor or hide the row.
5. Retain `lexic_baseline.json`, if useful, only as fingerprinted trend data.
   It is neither a cross-machine gate nor an approval channel. Every A/B
   regression remains measured and printed; only the user's explicit ruling
   can change its disposition.

A pre-commit hook cannot reserve a quiet machine or establish comparable
hardware, so it should enforce the row-contract and benchmark-structure tests,
not run a hardware-specific absolute ratchet. The explicit serial A/B command
and the qualified free-threaded CI runner own performance acceptance.

## Concrete replacement measurement contract

The smallest adequate replacement is:

- `Job` owns a checkout root, not a source directory. Its subprocess runs with
  that root as `cwd` and imports both `tools` and `src` from that checkout.
- A typed `RowContract` travels with every result: protocol version, row and
  grammar identity, grammar-source digest, exact directives, document digest
  and byte length, scale, engine/product noun, requested cores, GC state, and
  clocks. The comparator rejects unequal contracts.
- One fresh worker completes its entire lifecycle and exits before another
  starts. Base/head order flips per pair; control order flips independently.
- One process-level observation carries wall, process CPU, result digest,
  semantic verdict, and MT engagement. Raw observations are retained in the
  report; medians are presentation, not discarded evidence.
- Paired candidate and byte-identical-control ratios determine the noise
  envelope. There is no universal five-percent allowance and no automatic
  baseline exemption. Unresolved evidence stays unresolved.
- Mode-health rows use one identical full document across core counts. Change
  attribution and absolute MT health are reported separately, because a
  pre-existing MT loss and a new regression are different facts.

This redesign is intentionally free to delete the current cohort protocol,
absolute ratchet behaviour, adaptive directive licence, and obsolete flags.
There is no compatibility requirement for them.

## Closed since the previous snapshot

| Earlier finding | Current status |
|---|---|
| Outer FOLLOW applied to every referenced rule | **Closed.** Proof is occurrence-local and its eligibility tail includes soft FOLLOW. |
| Authored rules remained executable beside the flat program | **Closed in representation.** All consumers now use routines read from the program. Post-verification mutability is the narrower blocker above. |
| Construction resolved once per completed Earley/token node | **Closed.** `RuleRoutine` resolves it once at binding. |
| Island absence conflated with a real `None` value | **Closed.** Completion presence is explicit and tested. |
| Fold-era generated-model execution remained | **Closed.** The old fold module and its execution channel are deleted. |
| Physical range and operand bounds were largely unchecked | **Improved.** Bounds are checked; executable cross-row relations remain open above. |

## Later gates that remain open but do not block this §4 source checkpoint

These are real obligations. They belong to their scheduled implementation
stage and should not be mislabeled as defects in the generated-model migration:

- `SymbolExpr` being cold-only is still a prose restriction. §5 must either
  make that placement structural or replace it before general reducer products
  can execute.
- `JSON_EVENTS` still classifies the complete `number` as `integer` and the
  interior `frac` suffix as `fraction`. The complete-number decision must move
  to a formulation-neutral completed semantic boundary before §5 consumes it.
- ambiguity comparison still explores one changed packed choice at a time.
  Interacting and nested choice combinations remain the explicit §8 work; the
  current settlement refactor centralizes the answer but does not solve that
  enumeration problem.
- decoder semantics, route/continuation relations, stateful target operations,
  and symbol-expression execution must join the verifier before §5–§9 execute
  those lanes.
- after the benchmark protocol above is corrected, the clean external
  alternating performance run, examples, full done-gate, remote workflows,
  and final committed-source review remain scheduled. No local informational
  row substitutes for them.

## Pre-checkpoint disposition

No GO yet. Before the §4 checkpoint review can pass:

1. make the verified authority and its exposed projections immutable without
   adding lookup cost to the private worker-local hot reader;
2. reject malformed current model completions at the cold verification/binding
   boundary;
3. keep centralized ambiguity settlement without the new unconditional policy
   allocation or eager per-alternate `Flip` population;
4. close every unruled `object`/`Any` boundary introduced by this effort;
5. replace the dynamic licence and reflective test workaround with honest
   structural typing, or record the underlying linter defect for user ruling;
6. replace the benchmark lifecycle, row contract, clocks, relation rows, and
   ratchet disposition as specified above, with no compatibility branches;
7. run the corrected external alternating gate one process at a time and return
   any source or performance failure to the implementer;
8. only after those corrections, proceed to the scheduled test-authoring,
   lint, examples, full done-gate, remote workflows, and committed-source
   review.

Then re-read the corrected source and measurement report against this review.
`humanotes.md` remains the explicit blocker after the §4
review/performance/correction/checkpoint sequence and before any §5
implementation.
