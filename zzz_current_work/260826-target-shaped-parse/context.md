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
Python JSON tree, a certified extent, an `IrTokenizer`, or an arbitrary custom
Python result. The external prototype proves pool-retained, eviction-stable
constructor lowering without a public callback/factory field; §6 still must
prove the landed completion path has no frequent constructor traffic.

Performance depends on the codomain. Extent capture, a full Python tree, a full
IR tree, and a schema-layered tokenizer retain different information and pay
different decoding/allocation costs. Do not transfer a measured multiplier from
one target to another without a cost account.

For the 11,422,654-byte / 10,635,788-character local Qwen3 witness, the target
objectives are a pursued less-than-0.100 s wall for the complete reduced Python
mapping/list value and a gated less-than-1.000 s wall for a ready `IrTokenizer`,
with the ready tokenizer still pursuing roughly 105x against its like-for-like
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
  identity; ordinary items and their advance path are unchanged. A second
  witness carries the route through an intervening contextual clone, so the
  producer and consumer need not be siblings. Decoded plain and
  escaped-equivalent keys select the same child.
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
witnesses, not production throughput proof. `PROTOTYPE_8.md` supplies the exact
starting-tree RSS matrix and the persistent exact-meaning representation which
separates dirty-cone semantic work from eager-result materialization.
`REVIEW_9.md` found two missing possessive conditions, island-local ambiguity
settlement, a sibling-only route witness, target callables in the prototype's
frequent-completion operand tables, and five plan/accounting gaps.
`PROTOTYPE_9.md` records the corrected proof, non-sibling contextual route, and
closed-operation ABI. An ambiguous PDA island remains part of the predictive
product: it publishes a cold alternate-meaning seed which is replayed through
the enclosing product continuation to the requested root. The island span does
not decide final equality, and the complete document is not reparsed merely
because the parent may discard the difference.

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

`PROTOTYPE_11.md` proves the interaction defect on a real two-point chart:
production `another_meaning` can miss a jointly observable result when every
single flip is equal to the baseline. Per-node semantic value sets over packed
families, island-leaf options, and sibling accepting items are the exact
reference relation on an acyclic completed-node graph. A compiler certificate
may refuse early when some path from the differing node to a requested root is
injective in the carried slot. `PROTOTYPE_12.md`, corrected by
`PROTOTYPE_13.md`, replaces the cyclic `2^k` one-lap fallback with a
carrier-scoped zero-width-SCC classification and exact fixpoints over finitely
representable components. The prototype has no numeric census or semantic-lap
cap. `PROTOTYPE_14.md` completes the plan with an open type-keyed operation/slot
law table, multiplicative finite-image composition, and a constructive
infinite-SCC pair: the engine's accepting derivation plus one addressed growing
closed-walk splice, trying every carrier in `O(E × (V + E))`.

The current ambiguity-point universe is itself incomplete. A quantifier which
admits more than one count over a nullable atom creates same-span families with
different occurrence counts. `*`, `+`, `{0,2}`, `{1,2}`, grouped nullable atoms,
and directly empty rules all produce different public models which both PDA
and Earley silently choose between. `lift_optional_nullables` hides the same
defect for `?` and changes which model wins. These are semantic count families,
not ordinary text-allocation splits; they must reach complete target-meaning
comparison. The 15 canonical ground-truth grammars contain zero such sites,
but `@non-semantic` relaxation manufactures 71 optional nullable `ws`
references across six codegen grammars. The parser must recognize the armed
pre-relaxation grammar while binding and synthesis retain the relaxed grammar
for constructor ergonomics. On all six exposed fixtures the current lifted
relaxed grammar equals armed, and parsing armed with the existing fold returns
the current public model. A token-bound artefact concretizes armed separately.
`lift_optional_nullables` and the canceling relax-then-lift parser route leave;
authored optional nullable sites already in armed remain semantic families.

`ambiguity_points` also undercounts a finished chart until deferred Leo
provenance is expanded. A standalone precheck therefore owns complete Leo
readout; callers do not carry an implicit materialize-first precondition.

The island's alternate seed and the enclosing continuation now compose through
one compiled artefact. For each bound product (grammar identity, reducer
identity, requested root) one immutable row per contextual occurrence —
consuming clone, channel slot, requested root, product — carries the slot's
class under the real operation algebra and two grammar-level reachability
lanes, and nothing else: the rows are ints and declaration strings, so the
table cannot retain a kernel, a derivation, a meaning or a callable. A row
whose slot is `const`, or whose consumer no non-`const` path reaches, discards
that occurrence's alternates universally; where that holds at every occurrence
of an island rule, the island reads it before enumerating and never builds
them. Two refusals keep the rows sound: a rule whose pre- and
post-normalization contributing references differ has no law, because a hoisted
group or quantified repeat splices the parent channel input-dependently and the
authored `IrArg` index is then not the chart's chain slot; and a `grow` derived
by retaining a mapped focus has no law, because it is not injective over an
empty focus. Both reach the exact executed relation, and on the recursive
shipped grammars they leave the shortcut a small minority of rows until
production reads the binding view's real `fields_of`. The exact relation runs
over the dirty cone of a family-aware chart beside the per-node baseline fold
that is the parse's own product. The predictive path holds no such chart, so
ambiguity not eliminated by a universal constant certificate escalates
deliberately to Earley.

An `ident`/`grow` law is only a candidate existential certificate. The exact
lane builds two local meanings and carries both through one live realized route
before concluding requested-root inequality. This operation-executing check
replaces Prototype 15's zero-operation claim. Full enumeration applies once per
local family product and deduplicates with `same_value`; its current worst case
is exponential in local multiplicity. No arbitrary ceiling or resource refusal
is accepted. The chart is demand-driven, and production reuses cached baseline-
family outcomes across liveness and route work. Partial operations use bottom
semantics and require a distinct value-refusal exception.

Retaining the island's kernel while an occurrence has an unsettled alternate is
what lets a resolver pair be spliced without re-recognizing anything. A
constant certificate removes an occurrence before its product forms.
Everything else runs the exact per-node relation; propagation is removed, the
local product where multiplicitous children meet is not. Production reads the
occurrence key off the island's entry frame or waiter code.

Forest sharing is representation sharing. A shared node's meaning set is
computed once; every `(consuming handle, family index, kid slot)` occurrence
ranges over it independently, and occurrence-owned work executes per
consumption. `proto/shared_occurrence_ambiguity.py` agrees with an occurrence-
unrolled oracle across the known shared-DAG and transparent-synthetic shapes.
It disproves Prototype 15's packed-key-global oracle, which correlates
independent occurrences and loses meanings.

The same round produced one executable member of `goal.md` §5's enumerated
divergence set: a document whose two derivations build different generated
models but the same reducer value, which the shipped `reduce` refuses and the
definitive root-value relation accepts. That is the declared successor
relation, not a fourth shipped defect.

The resolver prototype now constructs both real complete-document trees,
associates them with their target meanings, and proves that island-local and
complete-document resolvers can choose differently. On its one-island Earley
witness, constructing both island derivations and replacing the delegated
payload leaf produces the complete pair without another document recognition.
Today's island gate decides inline and discards its kernel, so complete scope
requires new deferred state rather than reusing a retained pair. This closes
feasibility for the ruled public contract: both engines supply complete-
document pairs. A multi-island splice needs occurrence identity, and the fused
PDA path has no document `ParseTree` to splice, so it performs one cold Earley
recognition only after root inequality and an actual `resolve=` invocation.
Refusal and equal meanings do not perform that work.

For meanings, ordered persistent contribution trees remain sequence-only.
They are wrong for order-insensitive mappings, and the incremental hash treap
is rejected on both construction cost and collision correctness. Real rows now
price recursive Python dictionaries under all declared duplicate policies,
canonical `IrMap`, and ready `IrTokenizer` construction including vocab,
decode, ranks, merges, and pipeline. Python's exact cold comparison remains
cheaper than normalized document comparison at the measured medium scale.
`IrMap`'s document-level key normalization matches its exercised carrier laws.
The tokenizer document-level candidate now matches duplicate spelling,
ordinal, merge-key, bijection, rank, atomic-added-token, pipeline, and
segmenter outcomes for both currently specified constructors. Prototype 14
closes the three final-contract questions from five real fixtures: token ids
are any unique nonnegative integers; merge parts need not be vocabulary
spellings; declared fallback, unknown, fused-unknown, byte remap, and atomic
added-token payloads survive final construction even when vocabulary coverage
is partial. The tokenizer-format `special` flag remains a distinct schema
input; the internal `pipeline.specials` field contains every atomic added token.

The dict-of-sets dependency index remains rejected at roughly 1.9 KiB per
character. A flat CSR/forward-star candidate retains 98–112 B per character in
arrays after releasing its external prototype's 1200–1223 B-per-character
numbering/build transient. Production must assign dense numbers as completions
are created, include every required family edge, and measure the integrated
shape. The corrected control runs the existing fused PDA product and carries
no ParseTree or completed-handle meaning table. The corrected frame row
allocates one child tuple per completion and shares it only among seeds crossing
that completion. Those establish the protocol and representation, not future
source wiring. Recursive meaning equality is already known to fail on the
retained deep witness and must become iterative.

Custom classes remain in scope. The revised prototype proves a reflection-free
bound executable which retains derived tables, parses after its source
artefact and registry entry die, recompiles a larger tier from retained derived
grammar data, tolerates unhashable constructor classes through an identity-plus-
pin cache, cold-binds once under the free-threaded interpreter, and remains
executable when a real `ParsePool` is its sole owner after source and registry
death. Concurrent maps, failure, eviction, tier escape, shutdown, and cleanup
are covered. Its timed walk still builds and extracts a `ParseTree`; production
completion traffic and paid-loop neutrality therefore remain the §6 exit gate.

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

1. `zzz_current_work/260826-target-shaped-parse/reports/REVIEW_9.md`,
   `PROTOTYPE_9.md`, `PROTOTYPE_8.md`, and `PROTOTYPE_7.md` — the latest review,
   its proof/routing/ABI corrections, persistent exact meanings, and the exact
   §0 memory/consumer baseline. Read `REVIEW_8.md`, `REVIEW_7.md`,
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
- No opaque target callback in any frequently completed rule or the
  character/item loop. Scalar decode, validation, insertion, and record
  construction are engine-owned closed operations selected by plain integers;
  target-supplied callables are restricted to collection finish, root
  finalization, and meaning comparison.
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
