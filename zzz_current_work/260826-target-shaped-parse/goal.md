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

**Two-regime ruling (2026-08-28).** The <1.000 s resident envelope is pursued
on the interpreted product ABI: `reports/PROTOTYPE_5.md` measures one
compiled-recognizer consult per lexical rule completion plus flat int-op
dispatch at 0.368907 s sequential over the 3.6 M-char vocab region — 1.40x
the whole-entry capturing recognizer, versus 11.93 s for the current route.
The roughly 105x objective is explicitly contingent on the proved-regular
capturing lowering (repeated entry, acyclic closure, demand-named groups)
scheduled as a gated §7-exit task; its mechanism, genericity, and identity
proof are prototyped in `proto/regular_region_lowering.py`.

This is a replacement architecture, not an optimized branch beside the current
one.

## Public surface

There remains one reduction operation:

```python
compiled.reduce(text, reducer, into=target, resolve=resolver, cores=cores)
```

- Omitting `into` returns the reducer's current IR codomain.
- `resolve=` is the same caller-supplied ambiguity resolver `parse` takes —
  `CLAUDE.md` names the resolver as THE ambiguity opt-out, and it reaches
  whichever engine chooses; target products are not exempt. Both overloads
  carry it.
- A supplied `ReductionMorphism[T]` returns its unbounded result type `T`.
- `select({"key": KEEP, "nested": {"key": KEEP}})` is the beginner
  selection declaration. It returns a real morphism over decoded semantic
  keys and runs only through `reduce`; there is no `Template.run` twin. Its
  result is a declaration-ordered path-to-`IrSelf` mapping: missing paths are
  absent, repeated decoded keys refuse, unselected values are recognition-only,
  and nested non-mappings produce a target-shape verdict after syntax succeeds.
  The beginner declaration traverses finite nested mappings only.
- The target may produce IR, recursive Python values, a certified extent,
  `IrTokenizer`, and—only if the §6 immutability proof succeeds—an authored
  custom Python class.
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
in frequently completed rules. The character and item loops do not test which
codomain is active.

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
uses mark/commit/rollback. Failed islands discard child state. Each actual
competing Earley arm folds from a fresh isolated state; live base builders are
never cloned. Alternate meaning folds are rooted at the ambiguity family's
child subtrees with fresh local state — never a root-rooted whole-document
refold per flipped point. Side-effecting completion work over a shared forest
node executes exactly once per node, guarded at fold entry; occurrence-owned
effects ride the parent's slot consumption (the current walk's count is a
traversal accident — `reports/PROTOTYPE_5.md` §3). Workers own disjoint states and return owned fragments. A failed
or unchosen derivation cannot contaminate the result, duplicate set, or ordered
semantic verdict.

Products without mutable builders or deferred verdicts allocate no
`ParseState`. The generated-model specialization retains direct completion and
its current paid frame shape; it does not pay transaction checks, table
verification, or a generic operation interpreter for the sake of uniformity.

Marks are constant-size. Mutations are logged only while speculation is live;
rollback is proportional to mutations after the mark, not to retained builder
size, and successful outer commit is copy-free. In PDA, a routed discriminator
writes its consumer position and finite route into a rollback-owned parent
lane until that occurrence advances. In Earley, a sparse routed-advance table
selects a distinct existing packed successor code; unrelated items keep their
current representation and hot advance path.

Reusable morphisms are recursively immutable signature/schema/algebra data and
contain no cache, lock, factory, or executor. A private compiler/artifact
binding registry weakly references source artefacts, serializes cold first
binding, and participates in the parser cache release protocol. Eviction only
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

**Ambiguity relation ruling (2026-08-28).** The current route judges ambiguity
by structural comparison of built variant models; the product judges it by the
declared meaning law over reduced values, computed at the ambiguity point. The
value-meaning relation is definitive and supersedes the variant-model relation
— it is the reading `CLAUDE.md`'s "the question is about VALUES" invariant
states, and it is the only relation that can keep a difference a dropping
parent erases (`reports/PROTOTYPE_5.md` §4). The §5 differential therefore
compares values and refusal types exactly, while ambiguity-refusal divergences
between the two relations are enumerated, attributed, and coordinator-reviewed
rather than required to be zero.

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
- Merge entries stream as primitive spelling dyads and ranks into a
  tokenizer-native rank index.
- Pipeline sections use small typed accumulators.
- Root finalization passes those indexes through one
  `IrTokenizer.from_indexes` constructor. Tokenizer indexes are immutable
  dict-backed IR values with tokenizer-native primitive tables. Encode/decode
  order is canonical token-id order and merge order is canonical rank order.
  A direct builder already in that order is validated and frozen; a
  noncanonical public/readback input is ordered once. The indexes do not pay
  `IrMap`'s repr-key sort. The constructor neither derives inverse vocabulary
  nor re-indexes merges, and constructs one ready tokenizer.

### Extent

An extent product returns parser-certified half-open source bounds and its
declared validity guarantee. It never guesses delimiters. Deferred
materialization is chosen by the caller; it is not hidden inside an eager
target.

### Custom classes

An arbitrary result class is conditional, not a reason to weaken the core. §6
must first prove an immutable constructor symbol whose private binding is
write-once and eviction-stable. A public callable/factory field, mutable
rebinding registry, reflection channel, or second executor fails the gate and
removes this optional pre-alpha surface. Any admitted constructor is cold/root
finalization; no custom callback enters a frequent completion.

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
- `MapShape`, `Template`, `Template.run`, `spanify`, or raw-surface selection
  paths;
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
4. PDA, Earley, islands, ambiguity, sequential, and every engaged parallel
   shape agree;
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
- when route anchors decline and AUTO runs sequentially, gate the sequential
  row against the same envelope — the decline case is not exempt;
- not raise peak RSS above the §0-measured baseline of the current resident
  path (the criterion is a number recorded in the §0 matrix, not a direction);
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
canonical immutable indexes, and an actual tokenizer record in 0.138739 s
median on eight retained workers: 0.121197 s capture/join, 0.017504 s index
finalization, and 0.000032 s record construction. Its observed retained-carrier
RSS increase is about 79–82 MiB. Constructing an IR scalar/dyad for every entry
instead costs 0.346817 s and is rejected. A 6,098-character stdlib shell control
costs 0.001864 s, but does not certify the future composed product. Small fields,
production shell execution, target bind/setup, pipeline/root validation, and a
ready-tokenizer result remain to be measured. These are scenario budgets, not
an already-complete 105x claim.

An isolated `Path.read_text` probe measured 0.046713 s on its first read and
0.019701 s median across seven reads. It does not overwrite the historical
0.213211 s stage; it requires resident, cold-path, and warm-path rows to remain
separate in the final alternating measurement.

`reports/PROTOTYPE_5.md` adds the interpreted-ABI and collector rows. One
compiled-recognizer consult per lexical rule completion plus flat int-op
dispatch runs the 3.6 M-char vocab region in 0.368907 s sequential (GC on),
1.40x the 0.262931 s whole-entry capturing recognizer — so the interpreted
product ABI carries the <1.000 s envelope and the capturing lowering carries
the 105x objective. The composed carrier's paired in-process GC delta is
+0.016948 s wall (~11 %): the GC-enabled carrier budget is ~0.170 s in that
session's state. Production runs with the collector enabled; `src` never
manipulates collector state; every measurement row records its GC state, and
comparisons pair rows with equal GC state only.

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
