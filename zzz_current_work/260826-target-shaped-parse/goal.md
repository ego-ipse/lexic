# Goal — one parse, final codomain

## Final outcome

Lexic compiles a grammar, reducer semantic signature, optional upper target
schema, and target construction algebra into one immutable parser product. One
document recognition constructs only the requested final codomain.

For the standing Qwen witness, `json_tokenizer.read_from_path(...)` returns a
ready `IrTokenizer` without constructing a generated JSON model, a complete
JSON `IrMap`, reduction channels, sidecar carrier tuples, or a second
`tokenizer_of` traversal.

On the 11,422,654-byte / 10,635,788-character local Qwen3 witness, the explicit
target envelopes are:

- reduced recursive Python mappings/lists in less than 0.100 s wall — a
  PURSUED objective, not a pass/fail gate (see the performance-acceptance
  ruling: `json.loads`, single-threaded C, measures 0.084940 s on this
  witness, so the number is a language-implementation frontier);
- a ready `IrTokenizer` in less than 1.000 s wall for resident text — a GATE,
  measured at the public `cores=AUTO` engaged shape on the witness host, with
  the sequential row and aggregate process CPU per byte reported beside it —
  with cold and warm `read_from_path` totals reported separately, while
  continuing toward roughly 105x for the Qwen tokenizer scenario.

Both rows include recognition, demanded decode, final
encode/decode/rank/pipeline allocation, validation, and root finalization. The
105x figure is not a universal acceptance threshold for every reduction: each
codomain is compared with the current path producing the same result. They are
optimization goals for products derived from arbitrary compatible grammars,
never permission for a JSON-specific parser.

**Two-regime ruling (revised after REVIEW_8).** The interpreted envelope
requires an explicit generic specialization: one exact compiled-recognizer
consult per eligible value-string rule occurrence, followed by flat int
completion operations. It is a scheduled paid-loop task, not a property of the
current engine. `reports/PROTOTYPE_7.md` measures that mechanism against fused
whole-entry capture in one order-balanced alternating process: 0.351784 s versus
0.246319 s minimum process CPU, **1.428162x**, with a 0.001129 s control floor. Both are
microkernels omitting the driver, frames, transactions, merge region, and the
remaining document; neither proves the complete `<1.000 s` gate.

The roughly 105x objective is explicitly contingent on the further capturing
regular-region lowering. Its compiler proof covers acyclic simple closure,
ordered arm exactness, repetition/nullable-atom continuation ownership, and
deterministic capture boundaries. A nullable arm is permitted only last; a
variable or nullable atom whose first set overlaps its continuation declines.
Three distinct acyclic possessive hazards decline. Region programs are derived
from reducer semantic roles × target demand, including a non-JSON witness, not
from JSON locators. These mechanisms are prototyped in
`proto/regular_region_proof.py` and `proto/regular_region_lowering.py` and are
scheduled as gated tasks.

This is a replacement architecture, not an optimized branch beside the current
one.

## Public surface

There remains one reduction operation:

```python
compiled.reduce(text, reducer, resolve=resolver, cores=cores)
compiled.reduce(text, reducer, into=target, resolve=resolver, cores=cores)
compiled.reduce(text, into=grammar_target, resolve=resolver, cores=cores)
```

- Omitting `into` returns the reducer's current IR codomain.
- `resolve=` is the same caller-supplied ambiguity resolver `parse` takes —
  `CLAUDE.md` names the resolver as THE ambiguity opt-out, and it reaches
  whichever engine chooses; target products are not exempt. All overloads
  carry it.
- A supplied `ReductionMorphism[T]` or `GrammarMorphism[T]` returns its exact
  result type `T`.
- `select({"key": KEEP, "nested": {"key": KEEP}})` is the beginner
  selection declaration. It returns a real morphism over decoded semantic
  keys and runs only through `reduce`; there is no `Template.run` twin. Its
  result is a declaration-ordered path-to-`IrSelf` mapping: missing paths are
  absent, repeated decoded keys refuse, unselected values are recognition-only,
  and nested non-mappings produce a target-shape verdict after syntax succeeds.
  The beginner declaration traverses finite nested mappings only.
- `select_raw(entry, spec)` is the reducer-free twin over RAW-span keys. It is a
  `GrammarMorphism` and binds against a compiled grammar alone when the named
  entry has the compatible mapping shape derivable from binding data; no
  reducer or signature exists on its path. It returns declaration-ordered
  round-trippable `GrammarModel`s by default; `capture=EXTENT` returns
  parser-certified extents with a distinct exact result type. Both are built
  during the same single parse that
  recognizes the document. Raw keys mean escape-equivalent spellings are
  DISTINCT and raw duplicates refuse at selected levels; that declared
  difference is why `select` remains the beginner surface where a
  signature-bearing reducer exists. It runs only through `reduce`; these are
  two declared semantics, not two APIs for one task.
- Raw and decoded route selection is compiled into finite PDA/Earley
  continuation tables and adds no grammar arm. It never consumes `resolve=`;
  that channel remains solely the caller's answer to genuine authored grammar
  ambiguity.
- The target may produce IR, recursive Python values, a certified extent,
  `IrTokenizer`, and an authored custom Python class. The custom product cannot
  pass §6 until the landed completion path proves cold-root-only constructor
  traffic and paid-loop neutrality; external pool retention is already proven.
- A custom result never introduces a callback-only alternate parse API. Lexic
  does not infer class shape or inspect consumer code. If an arbitrary class
  cannot lower from immutable declaration data through a private write-once
  constructor binding, that optional surface is omitted.
- `cores` selects sequential or proved split execution for the same product.
  Unsupported product composition runs that product sequentially.

`CompiledGrammar.parse` remains the one generated-model operation. It uses the
same product ABI internally; generated models are no longer the parser's
privileged universal representation.

`json_tokenizer.read` and `read_from_path` use the direct tokenizer morphism.
`tokenizer_of` remains only for callers who already possess an `IrMap`; the
reader never calls it as a fallback.

## Semantic architecture

### Lower signature

Each reducer which supports upper composition exposes a formulation-independent
`SemanticSignature`. The JSON signature describes decoded scalar, array, entry,
object, and completion events. It contains no grammar rule names or generated
class knowledge.

Native, GBNF, ABNF, and EBNF formulations which implement the same semantic
signature can run the same target morphism. Compile verifies the reducer's
authored actions against the signature and refuses an unlowerable mismatch.

Reducer-free `GrammarMorphism`s are the separate source contract: they bind
against a compatible grammar/binding shape and carry no reducer or signature
identity. Both lower to the same engine-neutral product ABI after binding.

### Upper schema

A `TargetSchema` is a finite grammar/state machine over lower semantic events.
The tokenizer schema narrows JSON values to the supported tokenizer structure,
routes decoded keys/discriminators, states required and extension fields, and
declares semantic checks and failure order.

Compilation builds lower-occurrence × upper-schema contextual states. Valid
known routes use specialized children. A target-semantic mismatch enters a
poisoned state which records its verdict and consumes the remaining lower
syntax through a recognition-only recovery route when the contract requires
syntax-first failure.

### Product program

All engines execute one typed `ProductProgram[Carry, Result]`:

- a closed capture/completion ABI plus a typed reducer-expression program;
- typed per-target `Carry` values, with sequence/mapping handles in separate
  frame lanes and occurrence-owned builders in parse-local state;
- one parse-local transactional state;
- a root finalizer;
- a declared ambiguity meaning/equality law;
- optional compiler-proved fragment programs and joins.

The authored operation vocabulary lowers to flat int-coded records. Generic
parsing code contains no target names and invokes no arbitrary target callback
in any frequently completed rule. Scalar decode, validation, mapping insertion,
and declared record construction are engine-owned closed operations selected by
plain integers. Target-supplied callables are admitted only at collection
finish, root finalization, and meaning comparison. The character and item loops
do not test which codomain is active.

Every contextual rule executes one lowered completion range. The default IR
range may evaluate the reducer's typed expression program; a fused target range
constructs its target directly. No rule evaluates the former and then converts
through the latter. One flat range index selects one tagged expression,
fused/recovery, or delegate table range; verification rejects a missing, empty,
mixed, or out-of-bounds completion before execution. Cold authored enums are
lowered to real integers before the program reaches either engine.

PDA completion, Earley post-order folding, islands, ambiguity comparisons, and
parallel fragments consume the same capture layouts and completion operations.

### State safety

Mutable accumulators belong to one collection occurrence. Speculative PDA work
uses mark/commit/rollback. Failed islands discard child state. Earley's default
derivation leaves a memo of completed-handle meanings. For one packed-family
alternate, a dependency index marks only that family's completed owner and its
ancestors dirty; unchanged sibling meanings are reused and the target program
replays the dirty continuation to the root in an isolated sparse overlay over
the read-only baseline. It does not copy the document-sized memo. This preserves
the existing observable root-value relation, including a parent which drops
the differing child, without another whole-document semantic replay
(`reports/PROTOTYPE_7.md` §1). Completion ranges are selected by completed code,
so occurrence clones retain their own meaning program. Sequence-like built-in
accumulators represent ambiguity meanings as immutable persistent contribution
trees:
unchanged branches are identity-shared, dirty ancestors are path-copied, exact
iterative equality skips shared branches, and the chosen eager result is
materialized once. No hash or digest stands in for exact equality. Map, IR, and
tokenizer products earn that representation separately against their equality,
duplicate, and order law; otherwise they use an exact full cold comparison.
Ordered contribution trees and the incremental hash-priority treap are rejected
for keyed products. Real carrier rows select exact cold comparison for
recursive Python dictionaries and establish document-level normalization for
`IrMap`'s key/value/duplicate law. The tokenizer candidate covers every
currently specified constructor input and ordered refusal. Its final adoption
waits for the tokenizer contract to decide ordinal-domain, merge-reference,
and pipeline fallback/unknown constraints from real fixtures. A custom target
unable to supply an exact shareable meaning uses the same fallback, but adds
nothing to the unambiguous hot path.

Multiple packed choices and multiple or nested island seeds preserve the full
requested-root meaning relation. They may use linear one-flip replay only where
the compiled completion operations prove that alternatives are separable.
Purity alone is not that proof: a real two-point chart demonstrates two
individually invisible substitutions whose joint value differs. On an acyclic
completed-node graph, the reference semantics propagates exact deduplicated
meaning sets over every packed family, island-leaf option, and sibling
accepting item. A node may refuse early once some compiled path from that node
to a requested root is injective in the carried slot. Cyclic charts use the
carrier-scoped zero-width-SCC classification: finitely representable
components reach an exact monotone fixpoint, an invisible growing carrier is
opaque, an injectively visible growing carrier proves root ambiguity, and an
unrepresentable consumer class refuses at binding. Numeric census and semantic
lap caps are forbidden. Production adoption still requires real-operation slot
classification and constructive complete derivations for `resolve=`.

Every family capable of changing the requested target meaning enters this
relation even when normalization generated it. A variable-count quantifier
over a nullable atom creates occurrence-count families, not text-allocation
splits. `*`, `+`, bounded variable counts, groups, empty rules, and `?` are
covered. `lift_optional_nullables` may not erase the absent/present family.
It is deleted. Recognition uses the armed grammar before `@non-semantic`
relaxation; binding and synthesis use the relaxed grammar for constructor
ergonomics. Compiler-manufactured optional constructor fields are therefore not
parser families, while authored optionality already present in armed remains
observable. Token-bound artefacts concretize armed into their own parse-ready
moment. Ordinary same-production extent allocation keeps its defined leftmost
answer. The final refusal still depends on complete root meanings, so a parent
which drops the different count remains accepted.

Ambiguity readout is complete on a finished kernel without caller preparation:
deferred Leo provenance is expanded before points are reported. No fast path
may infer unambiguity from the current pre-expansion link table.

The dependency index is itself proportional to the default derivation. It is
built once only after a real semantic-choice family is found, never on an
unambiguous or ordinary split-only parse, and its peak memory is measured with an
ambiguous-input RSS row. A dict-of-sets representation is forbidden by the
measured memory result. The flat CSR/forward-star candidate retains 98–112 B
per character after its external numbering/build transient is released.
Production assigns dense numbers during completion, includes the required
family-aware edges, and proves the integrated dictionary-free build/RSS cost
before ambiguity work lands. A genuinely unambiguous path
allocates no ambiguity memo, dependency index, overlay, seed, or trace;
clearing one afterward does not satisfy this rule.

Side-effecting completion work over a shared forest node executes exactly once
per node through a finished set distinct from the value table; transparent
synthetic nodes are included. Occurrence-owned effects ride the parent's slot
consumption. Separate accepting root items each construct one complete meaning
because no shared internal packed point contains their choice. When root
meanings differ and `resolve=` is supplied, PDA may use Earley to obtain the
resolver pair required by the handoff scope settled before §8; only the chosen
meaning materializes the final target product. Complete-document pairs are
constructible, and an Earley-delegated one-island tree can construct both
island derivations and splice them without another document recognition.
Today's island gate decides inline and discards its kernel, so complete scope
requires new deferred state rather than free reuse. This establishes
feasibility, not the still-open choice between today's island-local resolver
pair and complete-document pairs for both engines. An island never settles
target ambiguity at its own accepting span. It returns its baseline value plus
a cold alternate-meaning seed; the enclosing product records and replays only
the semantic continuation from that occurrence to the requested root. Equal
root meanings keep the predictive result without reparsing the document. The
ordinary unambiguous island splice remains unchanged. A differing root with
`resolve=` may perform extra derivation construction only under the resolver
handoff scope settled before §8, never to discover the root meaning again.
Island alternate discovery includes sibling accepting items.
For a target using the exact whole-result fallback, the discarded cold
comparison result is explicit instead of being mislabeled as a shareable
meaning.
Workers own disjoint states. Failed or unchosen work cannot contaminate the
result, duplicate set, or ordered semantic verdict.

Products without mutable builders or deferred verdicts allocate no
`ParseState`. The generated-model specialization retains direct completion and
its current paid frame shape; it does not pay transaction checks, table
verification, or a generic operation interpreter for the sake of uniformity.

Marks are constant-size. Mutations are logged only while speculation is live;
rollback is proportional to mutations after the mark, not to retained builder
size, and successful outer commit is copy-free. In PDA, a routed discriminator
writes its descendant consumer path and finite route into a rollback-owned
parent lane until the first routed occurrence advances; deeper route identity
is baked into the selected contextual clone chain. In Earley, a sparse routed-advance table
selects a distinct existing packed successor code; unrelated items keep their
current representation and hot advance path.

Reusable morphisms are recursively immutable signature/schema/algebra data and
contain no cache, lock, factory, or executor. Their private `_bind` protocol
enters one homogeneous compiler/artifact binding registry per declaration kind;
there is no heterogeneous result-erasing registry. Each registry weakly
references source artefacts, serializes cold first binding, and participates in
the parser cache release protocol. No second cache of the same binding exists.
Eviction only
causes equivalent recomputation; it cannot change declared semantics. Pools
retain a bound program only as an explicit lifetime owner, and that retained
program remains valid after the source cache releases it.

## Target semantics

The work required and the validity contract depend on the target.

### Default IR

The default product directly constructs the reducer's complete `IrSelf` result.
It is differential with the current output, refusal type/message, contribution
order, `DROP`, `YIELD`, epsilon, and run behavior. This parity is a migration
proof; the old implementation is deleted before landing.

**Ambiguity relation ruling (corrected after REVIEW_8).** The product judges
ambiguity by the complete requested root value, not by the temporary variant
model and not by an isolated child's value. The value relation supersedes the
variant-model relation, but its scope remains the observable root product.
Child-local comparison is rejected because the dropping-parent witness would
refuse two derivations whose final value is equal. The §5 differential compares
values and ordinary refusals exactly; only differences caused by replacing the
variant-model relation with the definitive root-value relation are enumerated
and reviewed. The accepted language is not deliberately narrowed. The
persistent internal meaning is an execution representation of that same root
value, not a weaker digest relation or a second public codomain.

### Python JSON

The Python target builds recursive Python scalars, `list`, and `dict` directly.
It constructs no generated or IR JSON nodes. Its fraction and duplicate-key
behavior is explicitly declared; a stdlib-compatible target and a stricter
target are distinct morphisms, not incidental consequences of IR limits.

### Tokenizer

The tokenizer target accepts exactly the lower JSON syntax plus its declared
tokenizer schema and validation contract.

- Known keys route by decoded spelling; escape-equivalent spellings are equal.
- Repeated decoded keys at schema-covered object levels refuse.
- Each schema-controlled mapping is closed: every key is consumed, explicitly
  declared irrelevant and syntax-only, or refused after lower syntax succeeds.
  Dynamic maps such as vocabulary are intentionally open because their keys
  are semantic data. Existing reader permissiveness is not a compatibility
  oracle.
- Unsupported model knobs, special-token flags, normalizer/pre-tokenizer
  shapes, missing fields, and cross-section constraints produce ordered target
  verdicts.
- Syntax failure wins over a recorded semantic verdict; root cross-field checks
  run only after syntax succeeds.
- Object key order is irrelevant.
- Vocabulary entries stream as primitive spelling/id payloads into
  tokenizer-native encode/decode indexes.
- Token ids are unique nonnegative integers; sparse and above-entry-count ids
  are valid. Dense numbering is not a format requirement.
- Merge entries stream as primitive spelling dyads and ranks into a
  tokenizer-native rank index. Dyad parts need not be vocabulary spellings;
  ranks remain contiguous in document order.
- Pipeline sections use small typed accumulators. Declared byte fallback,
  byte remap, unknown/fused-unknown behavior, and atomic added tokens survive
  final construction without requiring complete vocabulary coverage. Added
  tokens merge before atomic-spelling membership is checked; a contradictory
  id refuses. The tokenizer-format `special` flag remains a separate schema
  input—`pipeline.specials` names every atomic added token, including entries
  whose flag is false.
- Root finalization passes those indexes through one
  `IrTokenizer.from_indexes` constructor. Tokenizer indexes are immutable
  role-specific subclasses of `IrMapping` with tokenizer-native primitive
  tables and duplicate refusal. Encode/decode order is canonical token-id order
  and merge order is canonical rank order. Equality and hashing remain
  order-insensitive, so canonical order is validated at every constructor and
  pinned through direct item-order plus repr/notation/payload round trips; it is
  never inferred from equality. A direct builder already in order is frozen;
  noncanonical public/readback input is ordered once. The constructor neither
  derives inverse vocabulary nor re-indexes merges, and constructs one ready
  tokenizer.

### Extent

An extent product returns parser-certified half-open source bounds and its
declared validity guarantee. It never guesses delimiters. Deferred
materialization is chosen by the caller; it is not hidden inside an eager
target.

### Custom classes

Arbitrary result classes remain in scope without weakening the core. Their
declaration carries one immutable class object as a constructor symbol plus
inert field/path data. A homogeneous private cache stores a result-free plan;
binding reconstructs a result-typed view without casts. The bound view retains
derived grammar data and tables rather than its source artefact; source death,
registry eviction, larger-tier recompilation, unhashable constructor classes,
identity-reuse safety, equivalent recomputation, concurrent cold binding, and
real-pool ownership after source death are proven externally. The class is
invoked only at cold root finalization.
Bound callables, factories, mutable rebinding registries, reflection, and a
second executor are forbidden. §6 must still prove on the production completion
executor that frequent completions contain no constructor traffic and that the
custom target does not regress the paid loop.

## Parallel result

Grammar structural discovery, cut certification, worker policy, replicas, and
the 2 KiB floor remain generic.

Each engaged target split has a compiler-derived `FragmentProduct` specifying:

- lower-rule and upper-schema entry state;
- initial capture/accumulator continuation;
- permitted exit states;
- ordered verdict and deferred-validation state;
- an associative document-order join.

Routed and shell fragments also carry a concrete suspended product
continuation: lower/upper/route state, capture and accumulator handles, source
extents, and the resume position. Their duplicate and verdict joins use stable
source-derived keys and remain associative independently of worker completion
or merge grouping. The coordinator attaches the joined direct carry and
resumes/finalizes once; it never parses or splices a generated-model shell.

Workers do not finalize document roots. The coordinator validates the state
chain, joins once, and finalizes once. No worker returns a shadow generated
model or a target-specific copy of the model stitchers.

## Finished source tree

The landed tree has one product architecture and no retained old route.

Present:

- declarative semantic-signature/schema vocabulary in the IR layer;
- compile-owned signature verification, state composition, demand analysis,
  product lowering, and typed binding/cache;
- parsing-owned engine-neutral product ABI and state lifecycle;
- generated-model, default-IR, Python JSON, extent, and tokenizer products;
- one structural parallel orchestrator with product-specific proved fragment
  laws;
- `tokenizer_of` only as the separate already-reduced-data entry.

Absent:

- `ReduceFold` and `compile/reduce/fold.py`;
- `_ReduceEntry`, `_reduce_entry`, and model-then-fold reduction;
- reduction-only carrier, channel cache, run fold, or fallback adapter;
- a separate templating parser/extraction execution path;
- `MapShape`, `Template`, `Template.run`, `spanify`, or any separate
  parse/extract execution path (the raw-span capability itself survives as
  the `select_raw` morphism through `reduce`);
- target copies of model stitching;
- `DirectCarrier`, `CarrierComposition`, or
  `parallel/stitch/carrier.py`;
- deprecated aliases, feature flags, old/new mode switches, or hidden retries
  through the superseded product;
- production profiling hooks.

Shared `foldkit` behavior remains only after it and all notation/generated
self-grammar users have migrated to the final product vocabulary. Public
generated-model parsing remains as one legitimate product, not old reduction
infrastructure.

## Correctness acceptance

The implementation is accepted only when:

1. default IR is fully differential across current unit, integration, property,
   and ground-truth formulation suites;
2. lower-signature/upper-schema composition is formulation-independent and
   accepts/refuses its declared language exactly;
3. Python JSON and tokenizer targets match their written contracts on nested
   values, fractions, decoded/escaped keys, duplicates, field order, missing
   fields, extension data, malformed discarded values, and unsupported
   features;
4. PDA, Earley, ambiguity, sequential, and every engaged parallel shape agree;
   island alternatives replay through their enclosing product to the same root
   relation without an unconditional document reparse;
5. attempt rollback, alternate isolation, worker isolation, verdict ordering,
   and root finalization are pinned adversarially;
6. no discarded value/model is constructed, no target engages both direct and
   superseded work, and no mutable builder leaks into a reusable program;
7. the existing model and token-segmented parse products have no performance
   regression after migration; no downstream speedup may offset one. A
   correctness bugfix-related regression is accepted only after isolated
   attribution and the user's explicit final approval;
8. the full suite, examples, generated-twin checks, lint, format, and pyright
   done-gate pass.

## Performance acceptance

Performance is reported per codomain as:

```text
recognition + demanded decoding + final allocation/finalization
```

The Qwen3 witness is
`resources/tokenizers/qwen3.tokenizer.json`. The uncontaminated current
path-inclusive read/reduce/build wall is 17.416359 s: 0.213211 s historical
source read, 8.573111 s parse, 7.629870 s fold, 0.961806 s tokenizer
construction, and setup. The corresponding resident-text reference is
17.203148 s.

The final tokenizer path must:

- remove fold and `tokenizer_of` as separate full-data traversals;
- reduce generic JSON recognition where the composed schema decides the shape;
- build only final tokenizer tables and small validation state;
- complete the resident-text operation in less than 1.000 s wall at the public
  `cores=AUTO` engaged shape on the witness host, with the sequential row and
  aggregate process CPU per byte reported beside it in every row (an MT row
  cannot pass by burning cores unreported);
- when route anchors decline and AUTO runs sequentially, report that row with
  CPU-per-byte and named attribution; it is diagnostic, not a `<1.000 s` gate.
  The public engaged `cores=AUTO` row remains the performance gate, and decline
  cannot hide submitted work or a base-parse regression;
- not raise peak RSS above the scenario-matched §0 baseline: 633,000 KiB for a
  first resident product, 632,888 KiB for a first cold path product, and
  838,120 KiB for the second product in one retained warm process. These are
  pinned single-run references; §12 alternates and reruns any close result.
  Never compare a warm retained candidate with the cold ceiling;
- report sequential and 1/2/4/8/16-worker results without changing the 2 KiB
  floor or suppressing eligible shapes.

The reduced recursive Python product pursues less than 0.100 s wall on the
same 11,422,654-byte Qwen3 witness. That number is a pursued objective in the
same sense as the 105x figure, not a pass/fail gate: `json.loads` — C,
single-threaded — measures 0.084940 s on this witness, so the gate quantity is
instead the reported multiplier against the current IR route producing the
same value, at the same reported worker shapes and CPU-per-byte contract as
the tokenizer row. The measured 13.14 s → about 0.13 s extent construction
result establishes the scale of removable work. The ready tokenizer must
first fit below 1.000 s for resident text and continue toward roughly 105x
against the like-for-like 17.203148 s resident reference, about 0.164 s —
the capturing regular-region lowering scheduled at §7 is what that objective
is contingent on. Cold and warm path-inclusive totals compare separately with
the 17.416359 s historical path. It must earn every result with its own
recognition, demanded decoding, and final-table work. The 105x objective does
not gate a different codomain which materially improves its own scenario. If a
target is missed, the remaining decoded bytes, constructor time, allocations,
and RSS are identified and optimized rather than treated as an assumed floor.

The selected performance-feasibility prototype runs both dominant Qwen regions
from resident text through native capture, joins, duplicate/rank checks,
canonical immutable indexes, and an actual tokenizer record. The current
GC-enabled eight-worker row is 0.700274 s median process CPU and 0.130779 s
median wall. The earlier 0.138739 s GC-disabled component decomposition is
provenance, not the budget. Observed retained-carrier RSS growth is about
79–82 MiB. The unchanged reader peaks near 633 MiB for its first complete
product and 838,120 KiB by the second call in one retained process
(`PROTOTYPE_8.md`); the latter is a high-water observation, not a leak
diagnosis. Constructing an IR scalar/dyad for every entry instead costs
0.346817 s and is rejected. A 6,098-character stdlib shell control costs
0.001864 s, but does not certify the future composed product. Small fields,
production shell execution, target bind/setup, pipeline/root validation, and a
ready-tokenizer result remain to be measured. These are scenario budgets, not
an already-complete 105x claim.

An isolated `Path.read_text` probe measured 0.046713 s on its first read and
0.019701 s median across seven reads. It does not overwrite the historical
0.213211 s stage; it requires resident, cold-path, and warm-path rows to remain
separate in the final alternating measurement.

`reports/PROTOTYPE_7.md` corrects the interpreted/capture comparison to an
in-process order-balanced alternating measurement with a control: 0.351784 s
versus 0.246319 s minimum process CPU, 1.428162x, with a 0.001129 s control
floor.
This is evidence for the explicitly scheduled exact value-string recognizer
consult, not for today's per-character PDA loop and not a complete-envelope
proof. The balanced eight-pair collector probe reports +0.004562 s process CPU
and -0.002075 s wall; the wall sign is noise. Production runs with the collector
enabled; `src` never manipulates collector state; every measurement row records
its GC state, and comparisons pair rows with equal GC state only.

Python JSON is compared with the current IR route and `json.loads`. Default IR
is compared with model + `ReduceFold` only during development. Extent retains
its own measured contract. Non-JSON GBNF, ABNF, and EBNF witnesses guard against
a privileged benchmark grammar.

All profiling is external. Structural comparisons use alternating processes
and a byte-identical control. Base parsing must remain equally fast or become
faster while target-shaped tokenizer construction pursues the roughly 105x
goal; neither result compensates for failure of the other. Only one
multithreaded benchmark process exists at a time, including preparation and
warm-up—a comparator which starts several waiting workers concurrently is not
used for these rows.

## Documentation acceptance

After the source architecture and source cleanup are final, README and
documentation receive a general architecture pass rather than isolated
search/replace edits. The public API,
pipeline diagrams, package maps, parser product model, reduction semantics,
target schemas, tokenizer reader, parallel composition, examples, and deletion
of old packages must all describe the final tree. `.wiki/log.md` records the
significant knowledge change, and doc-drift tests pass in both directions.
