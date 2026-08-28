# Context — target-shaped parsing

Read this before `DESIGN.md`, `goal.md`, or `TODO.md`. It describes the current
tree and the evidence which forced the redesign. It is deliberately concrete so
an implementer does not have to rediscover the pipeline by tracing imports.

## The product problem

Lexic currently pays for several isomorphic or covariant representations of one
parse:

```text
text
  -> parse a generated GrammarModel
  -> ReduceFold into the reducer's IR value
  -> inspect/convert that IR value in a consumer
  -> build the consumer's final value
```

For `tokenizer.json`, the final two steps are a full JSON `IrMap` followed by
`tokenizer_of`, which builds `IrTokenizer`. The expensive vocabulary and merge
data are parsed into generated models, folded into JSON IR, traversed again,
and finally rebuilt into tokenizer tables. The final tokenizer needs nearly all
of those bytes, but it does not need the intermediate representations.

The replacement is target-shaped parsing: compile grammar + reducer semantics
+ optional upper schema + target algebra into one parser product, then construct
only the requested codomain. The codomain may be the reducer's default IR, a
Python JSON tree, a certified extent, or an `IrTokenizer`. An arbitrary custom
Python result is optional and lands only if §6 proves immutable,
eviction-stable constructor lowering without a public callback/factory field.

Performance depends on the codomain. Extent capture, a full Python tree, a full
IR tree, and a schema-layered tokenizer retain different information and pay
different decoding/allocation costs. Do not transfer a measured multiplier from
one target to another without a cost account.

For the 11,422,654-byte / 10,635,788-character local Qwen3 witness, the target
objectives are a pursued less-than-0.100 s wall for the complete reduced Python
mapping/list value and a gated less-than-1.000 s wall for a ready `IrTokenizer`, with
the ready tokenizer still pursuing roughly 105x against its like-for-like
current scenario. That multiplier is not a universal gate for every reduction;
each codomain reports current versus projected performance separately. These
are layered product goals, not a license for JSON or Qwen cases in generic
parsing.

Existing parsing performance is non-negotiable and measured separately from
reduction/final construction. No downstream speedup offsets a parse regression.
Even when a correctness bugfix necessarily changes cost, only the user's
explicit final approval can accept that regression after isolated attribution.

## Review-pass-2 mechanisms

`reports/REVIEW_2.md` found three missing mechanisms and five implementation
obligations. Focused prototypes now provide the design input; they remain
mechanism witnesses, not source integration or performance evidence:

- `proto/route_continuation.py` lowers the real JSON mapping key/value sequence
  into a PDA producer route lane and a sparse Earley
  `(waiting contextual code, route) -> successor contextual code` transition.
  The existing packed Earley successor code carries route and occurrence
  identity; ordinary items and their advance path are unchanged. Decoded plain
  and escaped-equivalent keys select the same child.
- `proto/cache_lifetime.py` separates recursively immutable public declaration
  data from a private compiler/artifact registry, then uses real
  `CompiledGrammar` identities to prove single-build concurrent binding,
  artefact-bounded weak memo lifetime, and validity of a pool-retained bound
  program after source release.
- `proto/suspended_fragment.py` exercises the current routed split planner over
  a real routed witness, replaces its generated-model shell with an explicit
  suspended product continuation, and proves grouping-independent carry,
  duplicate-state, and stable-verdict joins.
- `proto/product_types.py` now uses constant-size transaction marks with
  mutation-proportional undo and a checked single completion-range index over
  separate expression/fused tables. Its earlier live-state `fork` proof has
  been removed: alternate and island products start from fresh state and carry
  only finished values/verdicts across the boundary.
- `proto/selection_contract.py` fixes the finite nested-mapping selection
  semantics, including declaration order, absence, value identity, discarded
  extensions, decoded duplicates, shape verdicts, and syntax-first failure.

The remaining high proof obligations belong at the source phase gates: execute
real reducer operands rather than treating node inventory as lowering, run one
real tiny grammar through both engines, measure transaction and paid-loop cost,
and attribute the final tokenizer constructor. The actual route producer must
decode at recognition time without invoking a general reducer/model path, and
the generated-model specialization must allocate no otherwise-unused product
state. None licenses a model-shaped bridge or an alternate executor.

`reports/REVIEW_4.md` closed the declaration/cache blocker, and the fresh
independent `reports/REVIEW_5.md` also gives GO for §2 and ABI/lifecycle §3.
Both require §3 to demonstrate occurrence-keyed recognition-time routing in
the actual PDA/Earley/island paths, verify every physical completion table,
integrate the repository cache-owner protocol, and measure rollback plus fresh
alternate-state cost before §4 opens.

`reports/REVIEW_7.md` exposed performance-evidence and ambiguity gaps;
`REVIEW_8.md` then caught an unsound child-local ruling, an unscheduled
value-string specialization, and an insufficient authoritative regular proof.
`PROTOTYPE_5.md` and `PROTOTYPE_6.md` are the earlier bounded evidence.
`PROTOTYPE_7.md` supplies the current corrections: root-equivalent incremental
ambiguity replay, a conservative possessive-boundary proof, signature-derived
regions including a non-JSON witness, an in-process interpreted/capture row,
declaration-only morphisms, raw route continuation, a transparent-synthetic DAG
witness, and an even-order collector comparison. These remain mechanism
witnesses, not production throughput proof.

## Current source state

The branch was returned to the pre-direct-carrier implementation. The current
committed tip contains the remote fork-safety fix and the external profiler,
not the rejected direct-reduction architecture.

The untracked `src/lexic/parsing/parallel/stitch/carrier.py` from the rejected
attempt was deleted by the user. It is not design input and must not be
reconstructed.

The later “Option 2” and direct-carrier sections in
`zzz_current_work/260821-one-path/reports/i24_report.md` are historical records
of work which was subsequently nuked. Their failures remain useful evidence;
their claimed source surfaces are not present in the current tree and must not
be reconstructed.

## Current reduction path

Start at `src/lexic/compile/artifact.py`:

- `CompiledGrammar.parse` calls the generated-model product, first through
  `split_model` when eligible and otherwise through `parse_model` or
  `token_model`.
- `CompiledGrammar.reduce` calls `_reduce_entry`, parses
  `_ReduceEntry.variant` into a `GrammarModel`, then calls
  `_ReduceEntry.fold.reduce`.
- `_reduce_entry` derives and caches the reducer-specific variant.
- `_variant_artifact` rebuilds compilation moments, generated classes, and a
  `ModelFold` for the variant.
- `_sub_run` constructs the escape parse/fold for poisoned lexical runs.

`src/lexic/compile/reduction.py` performs reducer-derived shape work:

- `derive_reduction` computes `ReduceDerivation`.
- `RunSpec`, `SubRun`, and `FoldPlan` describe the current run escape and fold
  arrangement.
- `_analyze`, `_text_equiv`, `_conditional`, `_hoist_runs`, and related helpers
  derive language-preserving lexical/run shortcuts.
- `sub_grammar` and group naming support poisoned-run sub-parses.
- the lower half derives the binding/channel tables used by `ReduceFold`.

`src/lexic/compile/reduce/variant.py` owns `reachable_rules` and
`elide_subtrees`, the current recognition-only clone/elision mechanism.

`src/lexic/compile/reduce/fold.py` is the second full semantic walk:

- `ReduceFold.reduce` partitions or walks a generated model.
- `channel`, `_fill_channels`, `_channel_once`, and `contribute` reconstruct
  reducer channels.
- `apply` executes the reducer body.
- `_splice_run` re-parses poisoned run interiors.
- `fold_subtree` supports the existing parallel fold.

The final implementation deletes this model-then-fold route. `ReduceFold` may
be used only as an uncommitted differential oracle while replacing it.

The real reducer bodies are expression programs, not single constructors. A
prototype traversal reaches 174 flat expression nodes for GBNF, 162 for ABNF,
98 for EBNF, and 44 for JSON. The common product therefore needs a typed
reducer-expression lowering in addition to its capture/collection completion
operations. For the default IR product that expression range preserves the
authored reducer. A fused upper target replaces it with one direct target range
where composition proves equivalence; it must never run both ranges.

## The shared fold vocabulary is not disposable

`src/lexic/compile/foldkit.py` is not merely reduction machinery. `IrNamed`,
`seq`, `model_fold`, and its helpers are shared authored-fold vocabulary used
by notation and generated self-grammar code. It must migrate to the common
product-operation vocabulary with its users; deleting `ReduceFold` does not
license deleting `foldkit` blindly.

Search all callers before changing it:

```bash
rg -n "foldkit|model_fold|IrNamed|\bseq\(" src tests
```

## Current parser product boundary

`src/lexic/parsing/fold.py` makes generated models the engine's privileged
product:

- `FieldFold` names one captured model field.
- `FastCtor` grants the PDA a positional validation-skip constructor.
- `RuleFold` is the flat per-rule model recipe.
- `ModelBody` is the authored IR form and bakes to `RuleFold`.
- `ModelFold.apply` folds an Earley `ParseTree` into generated models.
- `ModelFold.baked` is the PDA clone compiler's build input.

`src/lexic/parsing/products.py` joins the two engines:

- `earley_model` parses a forest/tree and calls `ModelFold.apply`.
- `_ModelProduct` caches parser tables and PDA state for grammar + fold.
- `parse_model` tries PDA and completes/falls back through Earley.
- `token_model` is the segmented-input counterpart.

The replacement makes generated-model construction one
`ProductProgram[Carry, Result]` specialization rather than the universal engine
contract. `parse()` still returns generated models; it simply uses the same
engine-neutral product ABI as other codomains.

## Current PDA build path

Read these files in order:

1. `src/lexic/parsing/pda/compiler/specs.py`
   - `CloneSpec.fold` carries `RuleFold | None`.
2. `src/lexic/parsing/pda/compiler/clones.py`
   - `PdaCompiler` receives a fold config and attaches it to contextual clones.
   - `compile_pda` is the compiler entry.
3. `src/lexic/parsing/pda/compiler/program/lower.py`
   - `_bake_build` turns `RuleFold` fields/fast constructors into `FlatClone`
     capture/build data.
   - `_build_plan` emits positional model-field instructions.
   - `flatten_program` produces the runtime program.
4. `src/lexic/parsing/pda/compiler/program/flatten.py`
   - `FlatClone` and `PdaProgram` carry the model-shaped build payload.
   - `vstr_model` directly constructs one value-string model.
5. `src/lexic/parsing/pda/runtime/build.py`
   - frame slots `F_*` carry ends and child sinks.
   - `build_sequence`, `fast_values`, `build_validated`, and `build_vstr`
     construct generated models.
6. `src/lexic/parsing/pda/runtime/kernel/execution.py`
   - `_run_leaf`, `_complete`, `_island`, and `_delegate_run` call the model
     build path at runtime.

The new product ABI must be baked at these same compile/completion boundaries.
It must not add target selection to character matching, item iteration, or
terminal admission.

Speculative PDA attempts, failed islands, and delegated parses can roll back.
Any new mutable collection builder therefore needs the transactional
mark/commit/rollback lifecycle defined in `DESIGN.md`; a parse-global mutable
vocab or map is incorrect.

## Earley and ambiguity

Earley owns the general chart/forest and fallback path under
`src/lexic/parsing/earley/`. The important construction seam is
`ModelFold.apply(ParseTree)` in `parsing/fold.py`.

Ambiguity support is under:

- `src/lexic/parsing/earley/kernel/forest/forest.py`;
- `src/lexic/parsing/earley/kernel/forest/support/ambiguity.py`;
- their mirrored tests under
  `tests/unit/lexic/parsing/earley/kernel/forest/`.

The discarded direct-carrier attempt tried to retain model-shaped witnesses to
the root. That recreated the representation the optimization was meant to
remove. The new product declares a typed root-product meaning. Earley reuses
the already-built baseline meanings and replays only the changed packed
family's ancestor continuation to the root. This preserves the observable
root-value relation without another whole-document semantic replay. The
fold-body prototype does not price eager-container rebuilding; built-in
products therefore retain exact persistent contribution meanings, share
unchanged branches, and materialize only the chosen eager result. Competing
work uses isolated product state, and the unambiguous hot path retains no
witness graph.

## Current templating path

`src/lexic/compile/output/templating.py` contains useful prior art and a
separate architecture which must not survive as a second parser:

- `MapShape` describes the current map entry/section shape.
- `_resolve_shape` and `_section_for` infer that shape from binding/grammar.
- `_entry_clone`, `_clone_body`, `_span_fold`, and `spanify` build
  occurrence-sensitive span and skip twins.
- `Template.run`, `_parse_step`, and `_collect_kept` parse/extract retained
  values through additional steps.

Keep the proof: one shared lower rule may need different behavior by
occurrence. Replace the separate run-time path with demand composition.
Signature-bearing `select` uses `TargetSchema`; reducer-free `select_raw` uses a
private binding-derived mapping shape and `GrammarMorphism`. The derivation
moves to `compile/product/shape.py`; the public `MapShape` export disappears
with templating. Do not stack templating on top of a completed general parse.

## Current parallel boundary

`src/lexic/parsing/parallel/orchestrate.py` owns structural split planning and
execution:

- `Request` carries text, `ModelFold`, and resolver.
- `split_plan`/`_split_plans` derive grammar-structural plans.
- `_split_parse`, `_attempt`, `_speculate`, and the region routes parse worker
  pieces.
- workers use `worker_replicas` and return generated models.

The stitch layer is model-shaped:

- `parallel/stitch/model.py` derives generated classes and field slots, then
  rebuilds model shells;
- `parallel/stitch/tasks.py`, `interior.py`, and `merge.py` manipulate those
  models for the supported split families.

Keep certification, worker policy, replicas, and the 2 KiB per-worker floor.
Generic structural discovery remains for products which require its region
model, but the composed target fast path cannot pay it unconditionally: Qwen's
exact all-region pass alone measures 0.392020 s and duplicates the later
capture. A compiled lower/upper route anchor instead proposes the shell and
O(workers) entry cuts. Before submission, a typed-hole shell checks prefix,
interstitial syntax, suffix, and exact lower/upper/route states through the same
composed product; fragment execution certifies each proposed entry and exit.
Unsupported or false proposals decline before submission to the same direct
target sequentially. The representation/control prototype performs its fuller
stdlib stand-in check over the 6,098-character Qwen shell in 0.001864 s; that
number is a budget, not the production Lexic timing.

Replace the assumption that every product is stitched by generated model
fields. A direct product engages MT only through a derived `FragmentProduct`
carrying explicit lower-rule and upper-schema entry/exit states plus an
associative ordered join. Concurrent regex-backed fragment programs must own
physically distinct patterns: equal calls to `re.compile` return one cached
mortal pattern and reproduce the free-threaded refcount ceiling.

Do not run two multithreaded benchmarks concurrently. Their measurements are
spurious.

## Current tokenizer reader and final carrier

`src/lexic/api/json_tokenizer.py` currently performs:

```text
read
  -> compile_ast(...).reduce(...)
  -> IrMap.ensure
  -> tokenizer_of
  -> IrTokenizer.from_merges
```

Important consumer behavior:

- `read` and `read_from_path` are the parse-and-build entry points.
- `tokenizer_of` remains useful when a caller already owns a reduced `IrMap`;
  it is not the future fallback for `read`.
- `_vocab` reads `model.vocab` plus missing added tokens.
- `_dyad` accepts both array and space-separated merge forms.
- `_pipeline`, `_normalizers`, `_steps`, `_spec`, and `_split` construct and
  validate the pipeline.
- `_refuse_unsupported_model` and `_refuse_unsupported_specials` define current
  format checks which the new tokenizer schema must deliberately retain,
  revise, or replace.

`src/lexic/ir/text/tokenizer.py` owns the final representation:

- `_vocab_map` builds the forward `IrMap`;
- `_rank_map` builds merge ranks;
- `IrTokenizer.from_merges` selects ranked-merge segmentation;
- `IrTokenizer._build` validates specials and derives the inverse map.

The target streams directly into tokenizer-native encode/decode/rank and
pipeline accumulators and constructs each final index once through
`IrTokenizer.from_indexes`. The three tokenizer-index roles are immutable
dict-backed IR mappings whose private payloads are primitive spellings, ids,
dyads, and ranks. Encode/decode are canonical by id and merges by rank; a direct
canonical builder validates and freezes without sorting, while noncanonical
public/readback input is ordered once. They do not pay `IrMap`'s repr-key sort.
The target does not ask `from_merges` to derive inverse vocabulary or re-index
merges already built. The current GC-enabled composed feasibility row is
0.700274 s process CPU and 0.130779 s wall for both dominant regions through
native capture, joins, canonical index freeze, and an actual tokenizer record.
The earlier 0.138739 s GC-disabled component decomposition is provenance only.
Per-entry IR leaves instead cost 0.346817 s and are rejected. The 0.001864 s
shell row remains a stdlib control, not production typed-hole certification.

`src/lexic/ir/action/mapping.py` matters because `_indexed` supplies decoded
duplicate-key refusal and `IrMap.from_table` canonicalizes. I9 proved that
searching reducer bodies only for `IrRaise` misses this behavior. The new
tokenizer index must preserve explicit duplicate refusal without weakening or
special-casing the existing `IrMap` invariant.

## Measurements and reports to read

Read these before changing source:

1. `zzz_current_work/260826-target-shaped-parse/reports/REVIEW_8.md` and
   `PROTOTYPE_7.md` — the latest review and its corrected ambiguity, regular,
   routing, typing, DAG, and measurement mechanisms. Read `REVIEW_7.md`,
   `PROTOTYPE_5.md`, and `PROTOTYPE_6.md` for provenance only.
2. `zzz_current_work/260826-target-shaped-parse/reports/PROTOTYPE.md` — typed
   carrier/builder separation, real formulation binding, real reducer-action
   coverage, public-surface inference, and plain-int opcode evidence.
3. `zzz_current_work/260821-one-path/reports/i23_report.md` — uncontaminated
   external attribution and measurement discipline.
4. `zzz_current_work/260821-one-path/reports/i9_report.md` — demand size,
   duplicate-key discovery, and the double-representation conclusion.
5. `zzz_current_work/260821-one-path/reports/i24_report.md` — why spans alone do
   not prove semantic validity or ambiguity, and why model-shaped carriers/MT
   stitching were rejected.
6. `zzz_current_work/260821-one-path/DEMAND_PROJECTION.md` —
   occurrence-sensitive demand, dynamic keys, and validation dimensions. Treat
   its suggested incremental old-template route as superseded by this design.

The I23 Qwen3 witness is 11,422,654 bytes. External observation measured:

| Stage | Median wall |
|---|---:|
| parse | 8.573111 s |
| fold | 7.629870 s |
| tokenizer build | 0.961806 s |
| resident setup/parse/fold/tokenizer build | 17.203148 s |
| path-inclusive read/reduce/build total | 17.416359 s |
| checked projection | 6.691667 s |
| sidecar + render | 18.021945 s |
| final validate/write/byte-compile | 13.124459 s |
| complete cold path | 55.311169 s |

The parse and fold process-CPU numbers are aggregate core-seconds, not
sequential duration: about 33.10 and 71.93 core-seconds respectively. Never use
them as wall time or divide them into a claim without naming the active-core
interpretation.

I9 found that `model.vocab` + `model.merges` cover 99.8–100% of the tokenizer
fixtures. That refutes path omission as the main tokenizer lever. It supports
direct representation fusion: demanded data should be built once in its final
form.

The 13.14 s → about 0.13 s extent-construction result establishes the scale of
work removable by target shaping. The concrete local goals are now a pursued
less-than-0.100 s for the reduced recursive Python product, a gated less-than-1.000 s for the
resident-text ready tokenizer, and continued optimization of the Qwen tokenizer
scenario toward roughly 105x. Resident, cold-path, and warm-path tokenizer rows
remain separate. An isolated source-read probe measured 0.046713 s first-read
and 0.019701 s median, versus the historical observed-stage 0.213211 s; only a
controlled alternating path measurement resolves that difference. Each target
must be earned against its own recognition + decode + final-allocation account,
and none licenses a base parse regression.

## Constraints that shape the implementation

- Grammar is ground truth. With an upper schema, lower + upper composition is
  ground truth for that target product.
- Generic parsing contains no JSON, tokenizer, rule-name, or benchmark grammar
  cases.
- `parsing` remains a leaf with respect to `compile` and `grammars`.
- No `eval`, `exec`, new `Any`, new `object`, suppression, or ignore directive.
- No opaque target callback in frequently completed rules or the character/item
  loop.
- Mutable builders are parse-local, occurrence-owned, transactional, and
  worker-isolated.
- Whole lower syntax remains checked according to the target's declared failure
  order.
- MT keeps the 2 KiB floor and engages only with a proved fragment contract.
- No permanent fallback, compatibility adapter, deprecated alias, or retained
  old implementation. Lexic is pre-0.1.
- Instrumentation never touches `src`.
- Prototypes live only in
  `zzz_current_work/260826-target-shaped-parse/proto/`.
- Terra source work, external profiling, Luna test/lint work, and coordinator
  review happen sequentially.

## Existing tests are oracles, not the final layout

Reduction parity currently lives primarily in:

- `tests/property/lexic/test_reduce_differential*.py`;
- `tests/integration/lexic/parity/test_reduce_directives.py`;
- `tests/integration/lexic/parity/test_fold_refusals.py`;
- `tests/unit/lexic/compile/test_reduction.py`;
- `tests/unit/lexic/compile/reduce/test_fold.py` and `test_variant.py`.

Tokenizer behavior lives in:

- `tests/unit/lexic/api/test_json_tokenizer.py`;
- `tests/integration/lexic/tokens/test_hf_tokenizer.py`;
- the real tokenizer tests and corpora under
  `tests/integration/lexic/tokens/`.

Templating, PDA, ambiguity, and parallel tests mirror their source packages.
Port assertions when symbols move. Delete only tests whose exact obsolete
surface disappears; preserve the behavior they defended in the new product's
tests.
