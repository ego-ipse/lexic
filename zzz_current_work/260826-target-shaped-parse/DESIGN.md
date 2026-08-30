# Target-shaped parsing

**Status:** substantive review passes 4 and 5 approved §2 and ABI/lifecycle §3.
The later prototype rounds establish the exact acyclic meaning relation,
carrier-scoped cyclic refusal decision, current tokenizer relation, retained
flat dependency layout, real trace-frame shape, fused control protocol, and
custom binding through a real retained pool. The remaining pre-implementation
decisions are real-operation cyclic lowering, construction of an infinite-SCC
resolver pair, resolver scope, and the tokenizer's final three validation
lanes. A final fresh reviewer has not returned `READY`. Production source has
not started. This document is not an implementation checklist.

## Decision

Parsing and reduction must become one compiled product. The parser should
recognize the grammar while constructing the selected codomain; it should not
first construct a `GrammarModel`, then traverse that model into an `IrMap`, then
traverse the map into a Python or tokenizer product.

The public seam remains one operation:

```python
compiled.reduce(text, reducer, into=target, resolve=resolver, cores=cores)
```

The standing 11,422,654-byte / 10,635,788-character Qwen3 witness sets two
distinct target envelopes: a pursued less-than-0.100 s wall for its complete
reduced recursive Python mapping/list value, and a gated less-than-1.000 s wall
for a ready resident-text `IrTokenizer` while continuing toward roughly 105x
for the Qwen tokenizer scenario. Resident, cold-path, and warm-path comparisons
are separate;
the multiplier is not a universal gate for every reduction. The former is a
shape-preserving target; the latter is a stricter layered grammar with a
narrower language but heavier retained final tables. Neither target privileges
JSON in generic compile or parser code.

Omitting `into` selects the reducer's existing IR codomain and preserves its
current behavior. A supplied target is a declared `ReductionMorphism[T]` whose
result type `T` is not erased: the core targets include IR, recursive Python
values, selection, certified extents, and format-specific products such as
`IrTokenizer`. Lexic never guesses a class schema, inspects downstream Python,
executes a sample, or uses `eval`/`exec`.

`into=` is therefore not a final conversion callback. It participates in
compilation and determines what each grammar occurrence captures, checks,
constructs, accumulates, or discards.

The beginner selection surface is a small declaration over decoded semantic
keys:

```python
fields = select({"version": KEEP, "model": {"type": KEEP}})
values = compiled.reduce(text, reducer, into=fields, cores=cores)
```

`select` returns a real `ReductionMorphism[Selection]`; it is not a second
executor. It needs neither grammar rule names nor `MapShape`, and its paths use
decoded keys rather than raw surface spellings. An advanced target authors the
same morphism contract instead of entering a different API.

The beginner contract is deliberately finite nested mappings, not a second
schema language. `Selection` is `dict[tuple[str, ...], IrSelf]`; entries appear
in declaration order, a missing path is absent, and a `KEEP` leaf owns the
reducer semantic value for that occurrence without rebuilding its containing
mapping. Every traversed mapping decodes keys and refuses repeated decoded
keys, including escape-equivalent spellings. Unselected values are recognized
through the lower signature without being constructed or inheriting unrelated
target validation. A nested declaration encountering a non-mapping records a
target-shape verdict; lower syntax failure still wins. Array traversal and
predicates are advanced morphism work, not silently inferred selection syntax.
A reducer/signature unable to supply decoded mapping/value events is refused at
binding.

Reducer-free extraction is the other source contract, not a fake reducer. A
`GrammarMorphism[T]` binds from the compiled grammar and its binding view alone:

```python
raw = select_raw("entry", {'"version"': KEEP})
values = compiled.reduce(text, into=raw, resolve=resolver, cores=cores)
```

`select_raw` is available only when the named entry has the compatible
key/value mapping shape derivable from binding data. Its paths are raw grammar
spellings, so escape-equivalent keys remain distinct. The default capture is a
round-trippable `GrammarModel`; `capture=EXTENT` selects the statically
model-free certified-extent codomain. These are typed declaration values, not a
boolean execution mode, and one declaration has one exact result type.

The static result surface is exact:

```python
@overload
def reduce(
    self,
    text: str,
    reducer: Reducer,
    *,
    resolve: Resolver | None = None,
    cores: int = AUTO,
) -> IrSelf: ...

@overload
def reduce[Result](
    self,
    text: str,
    reducer: Reducer,
    *,
    into: ReductionMorphism[Result],
    resolve: Resolver | None = None,
    cores: int = AUTO,
) -> Result: ...

@overload
def reduce[Result](
    self,
    text: str,
    *,
    into: GrammarMorphism[Result],
    resolve: Resolver | None = None,
    cores: int = AUTO,
) -> Result: ...
```

These overloads exist only for static inference. Runtime selects one cached
bound product before entering either engine. Repeated-document pools retain
that bound product directly, so signature verification and target lowering are
not repeated per document. There is no public `Template.run` execution path
beside `reduce`.

## The algebra being fused

Let `D` be a successful grammatical derivation, `R(D)` the reducer's semantic
product, and `M` a known morphism into another representation. The current path
materializes each term in:

```text
D -> GrammarModel -> R(D) -> M(R(D))
```

The desired path compiles the composite algebra and evaluates it during the
parse:

```text
D -> (M o R)(D)
```

The compiler may fuse the path only where the target declares the applicable
construction and validation laws. It does not infer them from a Python
consumer. For a shape-preserving target, the proof obligation is ordinary fold
fusion: constructing the target from child target values must equal constructing
the current reference value and then mapping it. For a projection, the obligation also
states which successful values and which semantic checks remain observable.

This distinguishes the important target relationships:

- A recursive Python JSON tree and an IR JSON tree have the same map/list/scalar
  shape with different constructors and domain policies.
- `IrTokenizer` is covariant with the demanded part of that JSON shape. It
  consumes selected scalar and collection occurrences but does not need the
  containing JSON tree.
- A parser-certified extent is a reference to recognized source, not an eager
  version of either tree. It is useful where a consumer really wants deferred
  materialization, but its cost and promise must be reported separately.

The lower grammar remains ground truth for text syntax. When a target supplies
an upper grammar, their composition is ground truth for that product's accepted
language. Semantic validity belongs to the selected target. The default IR
target executes the current reducer's complete semantics. A Python JSON target
may support fractions and choose a declared duplicate-key policy. A tokenizer
target may recognize an unrelated fractional field without constructing it,
while still interpreting or refusing a relevant field such as
`model.dropout`. It is incorrect to inherit every strictness of an intermediate
representation that the target does not use.

## Semantic signatures and layered grammars

An upper layer cannot depend on lower rule names or generated model shapes.
Different GBNF, ABNF, EBNF, and native formulations of JSON need to present the
same semantic boundary. That boundary is a compile-owned, immutable
`SemanticSignature`: authored data paired with a reducer which names the
reducer's semantic sorts and operations independently of grammar spelling.

The JSON signature names decoded scalar, array-item/array, object-entry/object,
and completion events. It does not name rules such as `member`, `value`, or
`object`. The compiler verifies and lowers the reducer's action bodies into
those events. A reducer without a declared/lowerable signature still supports
its default codomain, but a target schema cannot pretend to understand it.

A target may declare a `TargetSchema` over a lower semantic signature. The JSON
grammar says how characters form JSON events; a tokenizer schema says which
JSON event shapes form a supported tokenizer. Their compile-time composition
is the actual grammar of the requested product:

```text
characters -- JSON grammar --> JSON events -- tokenizer schema --> tokenizer

characters -- compiled composition ----------------------------> tokenizer
```

The middle event tree is conceptual. The composed parser does not materialize
it. The compiler builds the product of lower occurrence state and upper schema
state. At a known object key, schema state selects a specialized value clone
immediately: vocabulary is a string-to-id map, merges are ordered dyads,
pipeline sections have their declared shapes, and scalar knobs have their
declared domains. A key the schema does not consume either enters the generic
recognition-only JSON value program or refuses, as the schema contract says.

This is more than output pruning. On a valid schema route the upper layer can
remove lower-grammar arm choices, field captures, decoding, constructors, and
semantic checks that cannot occur in the composed language. It also supplies a
generic lower-syntax recovery route for contracts which defer schema failure to
EOF. The result is one specialized valid path plus a cold consuming failure
path, derived without putting a JSON or tokenizer case in generic parsing code.

Layers compose recursively by matching signatures, not names. A Python JSON
morphism is a shape-preserving layer over the JSON signature. A tokenizer
template/schema is a narrower layer over that semantic shape. A custom Python
class may add another declared layer over a named signature. Compilation fuses
all known layers; execution constructs only the final requested codomain.

## Target contract

A morphism declares five things. A reduction morphism names a reducer semantic
signature; a grammar morphism names a compatible grammar/binding shape instead.

### Source signature and schema

A `ReductionMorphism` names the lower `SemanticSignature` it accepts and, when
it narrows that language, supplies a `TargetSchema` over the signature's events.
A `GrammarMorphism` instead declares the binding shape and raw occurrence demand
it requires; it has no reducer identity or semantic signature. Compile refuses
either mismatch with words. Generic parser code sees only contextual state ids
and product operations; it contains no grammar, JSON, or tokenizer names.

### Codomain

The codomain names both its final result and the typed carrier family used by
intermediate rules. The implementation must preserve those types through the
compiler and parser rather than erase them to `Any` or `object`. A recursive
Python target can name a recursive JSON-value union; the IR target uses
`IrSelf`; the tokenizer target uses named accumulator and section records.

One program has one honest named carrier family `Carry`, which may be a
recursive or tagged union when its rules produce heterogeneous values. Semantic
frame slots, Earley result tables, ambiguity operations, completed islands, and
worker fragments are generic in that same `Carry`; they do not widen at a
subsystem boundary.

The public result type and the internal carrier need not be identical.
`ProductProgram[Carry, Result]` owns immutable rule operations and a root
finalizer. `ParseState[Carry]` owns every mutable builder and refusal verdict
for one parse. Internal `BoundProduct[Result]` is the result-typed runner at the
compile/artifact seam; it hides `Carry` only after the concrete morphism has
bound compilation and execution without erasing it. It is not a second public
execution method. `ReductionMorphism[Result]` is recursively immutable public
signature/schema/algebra data only; it contains no cache, lock, mutable factory,
executor, or entry dictionary. A private `_bind` protocol transfers each
declaration into one homogeneous compiler/artifact binding registry for that
declaration kind; a heterogeneous result-erasing registry is forbidden.
Reduction entries key stable
declaration + source grammar + reducer identities; grammar entries key stable
declaration + source grammar identity only. Each entry has
a weak source-artefact reference, strong immutable declaration and reducer
identities, and a result-typed bound program which is forbidden to retain the
source artefact. Cache eviction changes residency only: recompilation from the
same declaration must produce the same binding semantics. Warm identity lookup
is lock-free; a cold miss is double-checked under a lock so concurrent first
binding compiles once. Source collection or explicit release removes the entry,
and production binding adopts every derived product/PDA/Earley/replica cache
entry into the existing `parsing.caches` lifetime protocol. A pool retaining a
bound program is an explicit owner and remains valid after source-cache release.
Mutable builders are never cached or shared between parses or workers.

No second cache of the same reduction `(CompiledGrammar, reducer, morphism)` or
reducer-free `(CompiledGrammar, morphism)` binding exists. The per-kind
registries are the sole owners of their homogeneous entries;
`parsing.products` does not retain a second product memo;
`parsing.caches` owns only parser tables and replicas derived from the bound
program. This keeps residency, derivation, and pool ownership from becoming
three overlapping caches of the same product.

Mutable construction is transactional. `Carry` never widens to include engine
builder handles and semantic values are never put in wrapper records. Sequence
and mapping handles occupy separate typed frame lanes and index
occurrence-owned builder arrays in `ParseState[Carry]`; there is no parse-global
“current map/list.” A collection finish alone produces `Carry`, after which the
value may enter its parent, an Earley meaning, an island result, or a worker
fragment. A child commits only after it succeeds. Every speculative PDA
boundary records a constant-size `ProductMark`: mutation-log length, builder
counts, verdict length, and nesting depth. Sequence appends and successful
decoded-key inserts write reversible `(kind, slot)` mutations only while a mark
is live. Failure walks only mutations after the mark, removing the exact
appended value or key; it never scans all live builders or reconstructs a
retained key set. Nested marks are LIFO. The outer successful commit clears the
log without copying accumulated data.

Earley's default derivation retains immutable completed-handle meanings beside
its final value. One competing packed family is evaluated by marking its
completed owner and ancestor cone dirty, replaying those completion ranges in
a fresh isolated `ParseState`, and reusing every unchanged sibling meaning.
This produces the alternate complete root meaning without cloning live
builders or refolding the document. The memo contains semantic values only,
never builder handles or mutation logs; the unambiguous specialization carries
no dependency index. Separate accepting root items still require one complete
fold each. Island/delegate failure discards its child state. Parallel workers
always own disjoint states and return immutable/owned fragments to the
coordinator. No alternate derivation, failed attempt, or worker can mutate the
state which becomes the final result.

That statement is exact for one alternate substitution. Multiple packed
choices, sibling islands, or nested seeds are not evaluated one flip at a time
unless the compiled completion operations carry a proved separability
certificate. Purity alone is insufficient: two substitutions can be
individually erased and jointly observable. Without that certificate, the
runtime must preserve every jointly observable combination through an exact
mechanism. Per-node semantic value sets over all semantic packed families,
island-leaf options, and sibling accepting items are the reference relation on
an acyclic completed-node graph. Cyclic graphs use carrier-scoped zero-width
SCCs under four per-slot laws: constant, identity, declared-finite image, and
proper-subvalue growth. Safe components reach a monotone exact-set fixpoint;
an invisible growing carrier is opaque, an injectively visible carrier proves
root ambiguity, and the remaining unrepresentable class refuses at binding.
The mechanism contains no numeric census or semantic-lap cap. Production must
still lower real operations to those laws and construct two certified complete
derivations when an infinite component reaches `resolve=`.

The family universe is semantic, not synonymous with authored arm identity. A
quantifier which admits more than one occurrence count over a nullable atom
creates same-span count families. They are not ordinary extent splits and must
reach the target meaning relation. The optional-nullable lift is removed or
replaced because it erases an absent/present model difference. Ordinary
same-production text allocation retains the leftmost split rule. A complete
ambiguity readout expands deferred Leo provenance before reporting points; no
caller relies on prior tree materialization.

The dependency index is proportional to the default derivation and is built
once only after a real semantic-choice family is discovered. It is not
allocated for unambiguous parses or ordinary split-only families. §12 measures it with an
ambiguous-input peak-RSS row rather than folding it into the unambiguous
tokenizer ceiling. `PROTOTYPE_10.md` rejects a Python dict-of-sets index at
about 1.9 KiB per input character. The corrected flat CSR/forward-star
candidate retains 98–112 B per character after releasing its external
numbering/build transient. Production assigns dense numbers when completions
are created, records every required family-aware edge, and measures the
dictionary-free integrated build. The control protocol runs an existing fused
product without a ParseTree or completed-handle meaning table. The final
control must allocate no real ambiguity structure, and trace-frame pricing
includes one child tuple per completion shared only by seeds crossing it.

`ParseState` is not an unconditional engine tax. A product with no mutable
builders, transaction log, or deferred verdict—most importantly the existing
generated-model product—allocates none and does not test transaction state at
completion. Stateful completion records enter their dedicated executor before
the first builder operation. Binding/table verification is cold work and never
runs at a parse completion.

### Construction algebra

The construction declaration provides rule/operation constructors, collection
builders, dynamic-key handling, and root finalization. They lower to a closed,
engine-owned product-operation ABI rather than arbitrary callbacks. Its flat
records cover at least:

- capture nothing, text, extent, one child, or repeated children;
- decode the signature's declared scalar forms;
- classify a decoded discriminator and route to a precompiled contextual child;
- pass, constant, conditional, validate, and record a refusal verdict;
- begin/append/finish a sequence accumulator;
- begin/insert/finish a mapping accumulator with declared key and duplicate
  policy;
- construct a declared IR/record value;
- finish the root result and compute an ambiguity meaning.

The PDA and Earley interpreters consume the same records. Target selection is
baked into clone capture and completion; the character/item loop does not call
a morphism or branch on its Python type. Every frequently completed rule uses
engine-owned closed operations selected by plain integer codes. Scalar decode,
validation, sequence/mapping begin and append/insert, and declared record
construction never come from a target callable table. A target-supplied callable
may appear only at collection finish, root finalization, or meaning comparison;
those typed tables are separate from the closed-operation operands.

The authored completion ABI is a named union of typed operation records:
`PassOp`, `ConstantOp[Carry]`, `DecodeOp`, `RouteOp`, `ValidateOp`,
`BeginSequenceOp`, `AppendSequenceOp`, `FinishSequenceOp`, `BeginMappingOp`,
`InsertMappingOp`, `FinishMappingOp`, `RecordOp[Carry]`,
`MeaningOp[Carry]`, and `RootOp[Carry, Result]`. Begin/append/finish are
different record types because their fields and results differ; one
discriminator record with ignored fields is not an honest contract.
`CaptureSpec` modes are `SKIP`, `TEXT`, `EXTENT`, `ONE`, and `MANY`.

Real reducer bodies need a second *compile-time lowering layer* inside the same
product. A typed `ExprProgram[Carry]` covers the access, build, compute,
control, lookup, refusal, and contribution action algebra. The default IR
product uses it to preserve the reducer exactly. A composed Python or tokenizer
target instead lowers recognized semantic expressions into direct target
completion operations wherever fusion is proved. It does not execute the IR
expression program and then convert its result. Each contextual rule stores one
index into tagged `CompletionRange(kind, start, length)` records. `kind`
selects exactly one of physically separate expression or fused/recovery/
delegate instruction tables. The flat verifier rejects a missing index, empty
range, unknown kind, operand-table mismatch, or out-of-bounds range. A rule has
no parallel expression/fused fields, so it cannot execute both. PDA clones,
Earley completion sites, island delegates, attempt sub-clones, and token tables
must all pass this verifier before execution.

Lowering turns authored records and expression programs into plain-int
per-operation tables and a `RuleProduct[Carry]` containing capture indices plus
one completion range. `IntEnum` may name cold authored values, but no enum
instance enters a PDA/Earley runtime table. The binding verifier audits with
`type(value) is int`, because `isinstance(value, int)` would admit `IntEnum`.
Operands stay in separate typed tables; there is no catch-all operand array
widened to `Any` or `object`.

`RouteOp` maps one semantic-signature discriminator to a finite route id. A
compiled `RouteContinuation` names the unique contextual producer completion,
the descendant consumer reference path, and the finite route-to-contextual-
clone chain. A sibling consumer is the one-link case. For a non-sibling
consumer, each intervening PDA clone and Earley successor code is specialized
by the route, so no descendant dynamically reaches back into an ancestor frame.
A route producer must be non-nullable and produce exactly one discriminator;
compile refuses otherwise.

The discriminator is obtained at producer completion by its compiled scalar
decoder. Routing may not invoke the general reducer-expression evaluator,
construct a temporary model, or wait for forest folding. The bound program
specializes classification by actual cardinality: a uniform dynamic mapping
bypasses classification, a singleton uses one equality test, and a finite set
of two or more decoded discriminators uses a private dictionary lookup. Dense
route ids index child destinations directly. The Qwen-independent cardinality
probe measured dictionary lookup at 28.9–33.5 ns for 2–64 routes versus
121.9–907.8 ns for linear tuple scans; dense destination indexing measured
18.1 ns versus 262.2 ns for a choice scan. Tuple scans are therefore rejected
as a production representation.

Decoded selection routes on the semantic discriminator; reducer-free raw
selection routes on the already-matched surface spelling. Both use this side
table and add zero grammar arms. The route mechanism therefore never consumes
the public `resolve=` channel: a supplied resolver reaches only genuine
authored arm ambiguity after contextual routing is already part of the packed
code.

In the PDA, successful producer completion writes `(consumer path, route)`
into a dedicated parent-frame lane. The following child may read it across its
own internal attempts; the parent clears it only after that occurrence
successfully advances. The parent's transaction mark restores both integers on
rollback, so neither an abandoned attempt nor the next member can inherit it.
The first routed child is chosen from that lane; every deeper child is already
baked into the selected contextual clone chain.

Earley does not widen every packed item with a route tuple. Only a routed
producer completion consults a sparse compiled
`(waiting contextual code, route) -> successor contextual code` table. The
ordinary packed successor item then carries route and occurrence identity in
its existing code bits, so chart deduplication distinguishes routes while
unrouted `_advance_all` keeps its current integer addition and filing path.
This transition happens when the parent continuation is filed, before
prediction; the later forest fold cannot perform routing. For JSON mapping
structure the key completion therefore routes the following value reference
rather than specializing after a generic value has parsed. It classifies
decoded keys as known or `EXTENSION`; inside a vocabulary map it uses one
uniform entry route and retains the decoded key as data. The classifier and
continuation are lowered data, not a target callback or rule-name case.
Escape-equivalent known keys reach the same route.

Compile lowering is an open dispatch over authored action types with a raising
default. Before the old evaluator is removed, every expression and completion
used by the shipped reducers, notation, and generated self-grammar must lower
to this ABI with differential semantics. An unknown action refuses at compile
time; it never enters a runtime evaluator or model/fold fallback.

An arbitrary custom result class is not allowed to weaken this contract and is
not optional. Its inert declaration carries exactly one immutable class object
as the constructor symbol plus its field/path data. A private homogeneous
registry caches only a result-free lowering plan; binding reconstructs the
result-typed view without casts. The class object is invoked only at root
finalization. No bound callable, lambda, factory, executor, mutable rebinding
registry, import-path lookup, or class inspection is admitted. The external
binding witness retains derived grammar data and tables, executes after source
collection and cache eviction, recompiles a larger table tier without the
source artefact, tolerates unhashable constructor classes and identity reuse,
and cold-binds once under the free-threaded interpreter. Before §6 exits, a
real pool must retain and run that bound view after source collection, and the
production frequent-completion path must remain callback-free.

### Demand

Demand is per grammar occurrence, not merely per rule name. One rule may be a
retained value under one parent and recognition-only under another. Demand is a
set of independent capabilities rather than a single tier:

- **recognize** proves that the occurrence belongs to the grammar;
- **validate** runs a target-observable semantic check but drops success;
- **text** retains or decodes the matched spelling;
- **extent** retains parser-certified source bounds;
- **value** constructs a child value for its parent;
- **accumulate** streams repeated/map entries into a target-owned builder;
- **meaning** provides only the information required at a real ambiguity gate.

The compiler propagates these requirements backwards through reducer actions
and target constructors to a fixed point. It creates contextual rule variants
when shared rules receive different occurrence demands. Recognition-only and
validate-only variants are language-equivalent to their source; they do not
weaken the grammar.

Dynamic maps require a two-step plan. The key is recognized and decoded just
far enough to select the value occurrence's demand. Demanded keys select their
specialized value program; unknown keys select recognition-only or
validate-only behavior declared by the target. Raw and escape-equivalent keys
must route identically when the target's key domain is decoded text.

When the target supplies an upper grammar, its state participates in this
routing. Demand propagation and grammar composition are one analysis: the
upper rule both narrows what the lower value may be and says which part of that
value contributes to the final product.

### Validation and composition

The target names its required semantic checks, presence rules, ordering,
decoded-key and duplicate policy, exception vocabulary, and failure order.
Validation never becomes incidental behavior of an intermediate `IrMap` or
builder.

The exception vocabulary is declared here, once, against the existing
`exceptions.py` hierarchy (Luna pins type and message against this list):

- **Binding-time refusals** — signature/morphism mismatch, invalid or
  nullable route producer, an action the lowering cannot express, an
  incompatible `select` source signature — raise `UnsupportedConstructError`,
  the existing "this construct cannot run here" family.
- **Physical-table verification failure** (missing, empty, mixed, or
  out-of-bounds completion range before execution) raises
  `UnsupportedConstructError`: it is a defect of the compiled artefact,
  diagnosed with words before the paid loop starts.
- **Syntax failure** stays `UnsupportedConstructError` exactly as `parse`
  raises it today, and syntax-first precedence means it wins over any
  recorded semantic verdict.
- **Raised semantic target verdicts** — unsupported knob, missing required
  field, repeated decoded key, nested target-shape mismatch, root cross-field
  failure — raise a new `TargetRefusalError(LexicError)` carrying the ordered
  verdict value. The verdict value record is spelled `SemanticVerdict`;
  `compile/verdict.py` already owns the bare name `Verdict` for an unrelated
  concept, so neither the exception nor the record reuses it.
- **`IrTokenizer.from_indexes` validation** — cross-index bijection,
  contiguous ranks, special membership — raises `FieldValidationError`, the
  existing hand-constructed-record contract family.

This intentionally changes tokenizer-reader semantic refusals which currently
surface as `UnsupportedConstructError`: after migration they surface as
`TargetRefusalError`. Pre-0.1 carries no compatibility adapter or alias; §13
pins the new public exception types and messages explicitly.

The default IR target preserves the current full-reduction contract while it is
the parity oracle. The tokenizer target intentionally owns a new explicit
pre-0.1 contract: the complete lower syntax is recognized first; semantic
failures are retained as ordered verdict values rather than raised mid-parse;
if syntax succeeds, the earliest declared semantic verdict is raised, followed
by root cross-field validation. Every object level covered by the tokenizer
schema decodes keys and refuses a repeated decoded key, including
escape-equivalent spellings. An allowed extension value is syntax-checked but
does not inherit unrelated IR scalar refusals. This order is pinned in target
tests rather than copied accidentally from `IrMap` construction or
`tokenizer_of` call order.

`TargetSchema` therefore distinguishes final acceptance from execution state.
An unsupported field, wrong target type, duplicate, or refused knob enters a
poisoned schema state carrying its ordered verdict and a generic lower-signature
recovery route. That route consumes and validates the rest of the lower syntax
through EOF without constructing discarded values. A known valid route remains
specialized. If the recovery route finds malformed lower syntax, syntax wins;
otherwise root finalization raises the earliest semantic verdict. A schema may
declare an immediate structural failure instead, but that is a different
explicit target contract and cannot claim lower-syntax-first behavior.

The target also declares or derives the composition law for every parallel
split shape it supports. Ordered failure verdicts and decoded-key duplicate
state are part of a fragment and its join law. Absence of a proof means that
the same target runs sequentially; it never means “build the old model
product.”

## Compiled target program

Grammar, reducer/signature, schema, and morphism lower to one immutable
`ProductProgram[Carry, Result]`. The program contains:

- a contextual grammar equivalent to the declared lower-plus-upper language;
- composed upper-layer grammar states and their lower-event routes;
- per-occurrence capture requirements;
- one per-rule completion range, either a reducer-expression program or fused
  target operations, plus collection accumulators;
- target-observable validation operations;
- a root finalizer;
- ambiguity meaning operations used only at ambiguity gates;
- parallel fragment and join operations for proved split shapes;
- compiler-derived route-anchor proposals, exact shell/fragment certificates,
  and the cache-distinct worker-recognizer recipe where a target route can
  avoid duplicate generic discovery.

The engine-neutral execution contract is exact: PDA frame completion and Earley
post-order completion invoke the same plain-int completion range over the same
capture layout and `ParseState`; islands return the same `Carry`; ambiguity
compares the program's declared meaning; worker fragments contain the same
accumulator types and compose through the program's declared laws; the root
finalizer alone returns `Result`.

This program is the common input to the predictive and Earley engines. The
parser imports no reducer, tokenizer reader, or custom target. Target-specific
knowledge arrives as compiled operation records and immutable constants,
following the existing direction from `compile` into the `parsing` leaf.

The current contextual mechanisms are prior art, not separate run-time products
to stack. Reducer-derived lexical/elision variants and templating's occurrence
twins should become one contextual specialization and grammar-composition pass.
A document must not be parsed once for validity, again for the upper schema,
again for spans, and again for values.

## Parser consequences

### Shared product vocabulary

`ModelFold`/`RuleFold` currently make the generated model the engine's
privileged construction vocabulary: `value_str`, `sequence`, and
`alternation`, followed by model-field capture. That vocabulary must be
generalized into a typed product program. Building a `GrammarModel` becomes one
product specialization; building the default reduction, a Python JSON value,
or a tokenizer becomes another. There remains one recognition engine and one
completion mechanism.

The generalization must retain specialized model fast paths where their opcode
shape is already optimal. It must not add a target test to the per-character or
per-item paid loop. Target choice is baked into clone entry, capture, and
completion plans. The generated-model specialization retains its current frame
and direct completion shapes unless a measured simplification is faster: no
`ParseState`, transaction check, range verification, generic operation
interpreter, opcode, or frame slot may be added to its paid path merely to make
the abstraction uniform.

Value-string terminal consumption is where the throughput lives. The PDA
program specializer explicitly compiles one exact recognizer consult for an
eligible `value_str` occurrence; ineligible rules retain the existing
per-character program. Eligibility uses the same language-preserving regular
proof as an authoritative region, not the fail-soft scanner licence. The
specialization returns the one matched extent and the ordinary completion range
performs capture/build; it introduces no target callback or per-character
target branch. It has a dedicated generated-model parse non-regression gate.
`PROTOTYPE_7.md` prices the consult-plus-int-ops shape in one order-balanced
alternating process at 0.351784 s minimum CPU versus 0.246319 s for whole-entry
capture, with a 0.001129 s control floor. It omits PDA frames, transactions, driver work,
the merge region, and the remaining document, so it is a lower-bound mechanism
witness—not proof that the complete interpreted product fits `<1.000 s`.

Above that sits the scheduled capturing lowering. `compile/product/compose.py`
derives a repeated region from reducer semantic roles × target demand;
`parsing/product/regular.py` proves its simple closure acyclic, its authored
arms first-disjoint and ordered-exact, and every repetition, nullable atom, and
capture boundary deterministic against the next entry separator or terminator.
A nullable arm must be last. A variable or nullable atom whose first set
overlaps its continuation declines, including a `{1,1}` nullable reference. The
surrounding parser owns the opener and terminator; the delegated interior does
not promote the scanner's fail-soft shell match into an authoritative answer.
An acyclic/simple shape whose possessive atom or ordered arm would steal its
successor declines. A proved region lowers demanded positions to one capturing
recognizer per entry; an unproved region remains on the same interpreted
product from the start. The derivation/proof, a non-JSON catalog witness, and
native/GBNF/ABNF/EBNF JSON identity are in
`proto/regular_region_proof.py`/`regular_region_lowering.py`. The ~105x
objective is contingent on this further lowering. The `<1.000 s` gate applies
to the engaged public `cores=AUTO` row. A sequential route-anchor decline is
reported with attribution rather than treated as the same performance gate.

### Predictive PDA

The PDA clone compiler lowers the target program with the grammar. Each clone
knows which child results it needs, whether it needs item ends, and what it does
at completion.

- Upper-layer state can select a narrower lower clone after a dynamic key or
  discriminator is recognized; impossible lower arms are absent from that
  valid contextual clone, while a schema mismatch selects the generic
  consuming recovery clone.
- Recognition-only clones own no value sink and allocate no target value.
- Text/extent clones retain only the offsets or spelling they consume.
- Value clones capture only the child slots named by their completion plan.
- Accumulating clones append directly to their target builder instead of first
  creating one model per entry.
- Validate-only clones execute their check at the earliest completed boundary
  and release every temporary immediately.

Frame layout should follow these facts. An occurrence that needs no item ends
must not receive an ends array; one that needs no children must not receive
child sink lists. The existing unconditional or model-shaped frame costs are
part of the redesign, not fixed infrastructure that every target must pay.

### Earley and islands

Earley still owns the chart/forest required for general recognition and real
ambiguity. Once it selects or compares a derivation, it folds directly with the
same target program. It must not build a generated model and hand that to a
second reducer. An unambiguous PDA island returns its ordinary local product.
If an island has a second target meaning, it does not settle at the island
handle and does not discard the predictive parse. It returns the baseline value
plus a cold alternate-meaning seed. The enclosing product records the semantic
completion dependency from that occurrence to the root, then replays only that
continuation with the alternate value in isolated state. The same requested-
root ambiguity relation therefore applies without recognizing the document
twice.

The accepted mechanism is baseline-plus-alternates, an Earley leaf dependency
and ancestor cone, and a PDA completion trace recorded only while a seed is
live. Island alternate discovery includes sibling accepting items because a
start-rule choice need not appear in one accepting item's internal points.
Point readout first expands deferred Leo provenance. The mechanism does
not license one-flip evaluation across multiple or nested ambiguity sources;
the interaction rule in State and transaction safety governs those cases.

Ambiguity is orthogonal to ordinary retention but equality is target-dependent.
Every product declares a typed root meaning and equality law over derivations
which survive the composed grammar. The generated-model product reproduces its
current observable model-value semantics. Default IR uses the definitive
reduced root value rather than the temporary variant-model relation; those
migration divergences are enumerated. A narrower schema may reject one
derivation; a projection may identify a discarded difference only when both
complete target products are equal. No generic equality guess is applied to an
arbitrary custom class.

The unambiguous hot path carries no witness graph. At an actual internal
semantic-choice family, the default derivation's completed-handle memo is reused and only
the alternate family's ancestor cone is replayed to the root through a sparse
overlay over the read-only baseline; no alternate copies the completed-handle
table. The verdict is therefore exactly the complete requested value.
Semantic-operation replay is
proportional to the changed subtree plus its continuation rather than document
size; `proto/root_meaning_incremental.py` proves that narrower claim at three
alternate fold bodies versus a 1,207-body baseline. It does not treat fold-body
count as a proxy for eager-container allocation or equality.

Sequence-like built-in accumulators retain an immutable persistent contribution meaning:
unchanged branches are identity-shared, a dirty completion path-copies only its
ancestors, and exact iterative equality skips shared branches. No digest is an
equality proof. The chosen meaning alone is materialized into its eager public
result, once, after ambiguity resolution. `proto/persistent_meaning.py` visits
18 nodes to distinguish one changed leaf and 33 to prove an equal path-copied
leaf over a 65,536-item sequence, then performs one final materialization. Each
map/IR/tokenizer product must separately prove an exact shareable meaning under
its own equality, duplicate, and order law before claiming the same allocation
bound. Ordered contribution trees are rejected for keyed products because
insertion order is not mapping meaning. The incremental hash-priority treap is
also rejected: it costs seconds at Qwen scale and hash collisions make its
claimed canonical shape insertion-order-dependent. Real carrier rows now
select the exact isolated cold comparison for recursive Python dictionaries
and establish document-level normalization for `IrMap`'s
key/value/duplicate law. The ready-tokenizer candidate covers every currently
specified constructor input and ordered refusal. Tokenizer adoption remains
open until the final contract decides ordinal-domain, merge-reference, and
pipeline fallback/unknown constraints from real fixtures. A custom
target without an exact shareable meaning uses the cold comparison; that
limitation
is explicit and never moves a graph, callback, or alternate result onto the
unambiguous path.

The dropping-parent counterexample in `proto/local_meaning_fold.py` rejects
child-local comparison. Completion operations are selected by completed code,
which is also the contextual-clone identity. Split families with a defined
extent remain permitted. Deep meanings and persistent contribution trees use
iterative walks.

Separate accepting items at the document root are not internal packed-family
points. They each construct one complete root meaning; ancestor-cone replay
applies only where roots share an internal packed point. When `resolve=` is
present and meanings differ, the engine supplies the existing complete
derivation pair to that resolver. A predictive ambiguity bails to Earley before
committing target state so the same derivation resolver is used; no shadow
generated model is constructed. The chosen meaning alone is then materialized
as the final target product when the target supplies the proved shareable
representation; otherwise the exact cold whole-result comparison above owns
both temporary results explicitly.

An island seed is not a span-local refusal or syntax error. Equal root meanings
keep the predictive result. Both complete-document derivations are
constructible and exactly associated with their target meanings. On the
one-island Earley-delegated witness, replacing the payload leaf with the
retained island derivation creates the complete pair without another
recognition. The resolver handoff scope remains explicit planning work: today's
island implementation supplies an island-local pair, while the general Earley
path supplies requested-root derivations, and a context-sensitive resolver can
choose differently between them. Before §8, the implementation must decide
which pair makes PDA and Earley expose the same public ambiguity opt-out. A
complete-document design must add occurrence-identified multi-island splicing;
the fused PDA path still needs one cold recognition because it retains no
document `ParseTree`. Any extra work occurs only after root inequality and an
actual `resolve=` invocation; refusal and equality perform none.

Fold execution over the shared packed forest is a separate stated contract
(`proto/shared_forest_refold.py`): the built derivation is a DAG (zero-width
and unit-chain subtrees are shared objects), and the current walk's fold-body
count per shared node is a traversal accident — two executions in two witness
shapes, one in a third, for identical two-slot sharing; a transparent synthetic
node also repeats because it never enters today's value table. The product fold
therefore computes each node's VALUE exactly once using a finished set distinct
from the value table, and
applies occurrence-owned effects (appends, verdicts, duplicate-set entries)
from the parent's slot consumption so effect counts follow occurrences, never
traversal interleaving. All three witness shapes are §3 exit gates through the
Earley fallback.

### Parallel parsing

Cut certification and the 2 KiB floor remain properties of the grammar and
input. Discovery is product-shaped where the composed upper grammar proves a
more specific regular route. The target fast path must not first run complete
generic region discovery and then recognize the same high-volume syntax again.
Instead, compiled lower/upper route anchors propose a shell and O(workers)
entry cuts directly. Before submission, the coordinator runs that shell through
the same composed product with typed holes at the exact lower, upper, and route
states. Prefix, interstitial syntax, suffix, and each proposed hole boundary
must agree; every worker fragment then certifies its own entry and exit. An
unavailable, ambiguous, escaped, reordered, or false anchor declines before
submission to the same sequential direct product. Existing generic discovery
remains available to products and split shapes which need its result; it is not
an unconditional pre-pass.

For a routed-interior or region-shell split, the coordinator first executes the
same product until the certified hole and retains a `ShellSuspension`: exact
lower, upper, and route states; capture/accumulator handles; source extents; and
the program position after the hole. Workers execute only the interior product
and return direct target carries. After the associative join, the coordinator
attaches that carry to the suspended occurrence, resumes the suffix through the
same product, and finalizes once. No generated-model shell or model-field
replacement participates.

Each worker returns a typed partial accumulator plus only the bounded
continuation required by the cut. The target's composition law joins those
fragments once for terminated, separated/envelope, routed-interior, and
region-shell shapes. Fragment state includes lower/upper/route entry and exit,
carry, first decoded-key state for boundary duplicate detection, deferred
validation, and ordered verdicts. Verdicts carry a stable total
source/phase/declaration/serial key assigned independently of worker grouping;
merge is stable ordered merge, not tuple concatenation. Carry join,
duplicate-state join, and verdict join must each be associative. Examples
include sequence concatenation, map insertion under the declared duplicate
policy, and vocabulary/rank accumulator merge.

The compiler licenses a split through an explicit
`FragmentProduct[Carry]`. For that split shape it names the lower-rule entry,
upper-schema entry state, initial capture/accumulator continuation, deferred
validators, allowed exit states, ordered-verdict projection, and associative
join operation. A worker never runs the document root finalizer. The
coordinator joins fragments in document order, checks the exit/next-entry state
chain, then runs deferred/root validation and finalization exactly once.

Schema context is therefore not reconstructed from a fragment's text. A vocab
piece begins in the schema's vocab-entry state; a merges piece begins in its
merge-item state; a generic extension region carries its generic lower state.
If the compiler cannot derive bounded entry/exit state and an associative join
for a certified grammar cut, that target does not engage the split.

Concurrent fragment recognizers are equal but physically worker-owned. Python's
regex compiler caches by source, so compiling the same source once per worker
does not create replicas. Binding gives each worker a cache-distinct compiled
pattern with identical language. The distinction is cold compiled state only;
no worker id or recognizer branch enters the paid loop.

Ownership does not stop at regex patterns. On the free-threaded build, EVERY
per-completion-hot shared object is a refcount-contention candidate — the
`ProductProgram`/`BoundProduct` flat operand and route tables are touched by
every worker at every completion, the exact shape `parallel/replicas.py`
already exists to fix for parser tables. Where measurement shows refcount
traffic on such an object, binding gives each worker its own physically
distinct copy; and the §12 scaling ladder attributes any scaling loss to a
NAMED object rather than reporting an aggregate.

If a target or split shape has no lawful composition, the target runs once on
the whole document. There is no partial direct attempt followed by a complete
superseded model parse, and no shadow model whose only purpose is to reuse the old
stitchers.

## Concrete codomains

### Default IR reduction

The omitted-`into` product is the reducer's reference codomain. It constructs the
reducer's `IrSelf` result directly during parsing and preserves current output,
exception type and message, hoists, drops, `YIELD`, epsilon behavior, poisoned
runs, and ordering. Its ambiguity law is the definitive reduced-value relation
described above, not the superseded variant-model comparison. It constructs neither a
`GrammarModel` nor a subsequent `ReduceFold` channel.

`ReduceFold` must be deleted before landing. During development only, it is a
differential oracle until the direct IR product is identical on the complete
existing reduction suite; it is never a fallback.

### Python JSON

The Python JSON morphism constructs recursive `dict`/`list` and scalar values
at rule completion. Even when the entire JSON value is demanded, it discards
grammar-only structure: punctuation, whitespace, wrapper rules, source
spellings after decoding, and generated model identity. It creates no IR
leaves or maps.

Number and duplicate behavior belong to this morphism. A stdlib-compatible
form can construct `int`/`float`, decoded `str`, `bool`, and `None`, with an
explicit last-key or pair-hook policy. A stricter form is a distinct declared
morphism, not an incidental consequence of `IrMap` construction.

Custom Python classes use the same mechanism: their morphism declares which
occurrences feed one immutable class constructor symbol at root finalization.
The compiler does not privilege JSON names, inspect annotations, infer class
shape, or call arbitrary constructors at frequent completions.

### `IrTokenizer`

The tokenizer morphism lives beside `lexic.api.json_tokenizer`, where the
format knowledge already belongs, and is passed into generic compilation. It
turns the existing reader's implicit template into a tokenizer-shape grammar
plus an explicit occurrence demand. That upper grammar is composed with the
caller-supplied JSON formulation; it is not a privileged JSON parser.

The root needs selected sections such as model kind, vocabulary, merges,
unknown-token and byte-fallback behavior, added tokens, normalizers,
pre-tokenizers, and the knobs whose values change or invalidate segmentation.
Other keys are fully recognized but neither decoded nor retained unless the
target declares a validation for them. The tokenizer schema is closed at each
semantic mapping: a key is consumed, explicitly declared irrelevant and routed
to generic recognition-only JSON, or refused through syntax-first recovery.
Dynamic maps such as vocabulary are the deliberate open case because every
decoded key is data. Existing reader permissiveness is not an oracle or
compatibility obligation. The behavior is declared from `IrTokenizer`'s actual
semantic scope, never inherited from incidental map construction.

The high-volume sections are streamed:

- `model.vocab` entries populate tokenizer-native encode/decode accumulators;
- `model.merges` entries populate the tokenizer-native rank accumulator in
  source order;
- added tokens and pipeline sections populate their small typed builders;
- root finalization resolves cross-section checks and constructs one
  `IrTokenizer`.

JSON object order cannot become a hidden precondition. Section accumulators are
independent until root finalization, so `model`, `added_tokens`, and pipeline
keys may occur in any grammatical order. Escape-equivalent keys route by their
decoded spelling. The tokenizer contract refuses repeated decoded keys at every
schema-covered object level, records semantic failures until full syntax has
been recognized, and checks required sections and cross-section constraints at
root finalization.

The final tokenizer necessarily retains its vocabulary, inverse vocabulary,
merge ranks, and pipeline. Those are the final product, but their existence does
not justify the old construction cost: the composed grammar streams directly
into encode, decode, and rank builders together and constructs each final IR
container once.

Tokenizer runtime tables are three role-specific subclasses of the immutable
dict-backed `IrMapping` base: spelling-to-id, id-to-spelling, and dyad-to-rank.
Their private payloads are exact Python `str`, `int`, and `tuple[str, str]`
values; the index itself is the IR node, so wrapping every internal entry in a
spine scalar/dyad is not required. Encode/decode iteration is canonical token-id
order and ranks iteration is canonical rank order. A direct builder already in
that order is validated and frozen without sorting; a noncanonical public or
payload-readback input is ordered once. Mapping equality and hash are
deliberately order-insensitive, so they cannot certify this invariant: every
constructor validates item order, and tests pin `tuple(items())`, repr,
notation, payload, and generated-module order directly. General `IrMap` keeps
its repr-key invariant for every existing consumer; the tokenizer does not pay
its roughly 0.408 s sort.
`IrTokenizer.from_indexes` is the one final construction tail. It accepts
encode, decode, and rank indexes together, validates pipeline references, and
constructs the record without inverse derivation, rank re-indexing, or dyad
materialization. Existing `from_vocab`/`from_merges` converge on the same tail.
Public `resolve` and `spell` retain the `IrEncoding` return boundary while the
tokenizer's internal lookups use primitives and allocate no temporary IR key.
The composed prototype captures, joins, canonically freezes, and installs all
three dominant Qwen indexes in an actual record at 0.700274 s median process
CPU / 0.130779 s median wall with GC enabled. The earlier 0.138739 s
GC-disabled component decomposition is provenance only. The per-entry IR-leaf
alternative takes 0.346817 s and is rejected.
The eliminated work is generic JSON arm selection where the upper shape already
decides it, the generated JSON model, the full JSON `IrMap`, its tuple dyads and
scalar wrappers, and the second traversal through `tokenizer_of`.

### Certified extents

An extent target returns grammar-certified half-open source bounds for a
declared occurrence. Omitted interiors are still recognized according to the
target contract. Delimiter scans and guessed bounds are never certificates.

Extent capture is valuable when a later consumer genuinely prefers a slice or
deferred parse. It is not evidence that an eager tokenizer can be built for the
same cost: Qwen's vocabulary and merges are almost entirely demanded by the
final tokenizer.

### Reducer-free raw selection

`select_raw(entry, spec)` is a `GrammarMorphism`, not a signature-bearing
reduction target. Binding derives and validates a compatible recursive mapping
shape from the named entry and the grammar binding view, compiles selected
occurrences into contextual demand, and recognizes the document once. The
model capture retains only selected `GrammarModel` values; the extent capture
has a static reachability proof that no model-building rule is reachable.
Selected levels retain raw keys for routing and duplicate refusal; unselected
subtrees are recognition-only. This preserves the grammar-native templating
capability without retaining its spans-then-reparse executor.

## Code ownership after the redesign

The implementation begins with a source review which assigns every current
owner to its final role. Nothing remains merely because it is the old path.

- `ir/reduction.py`: owns the declarative `SemanticSignature` and
  `TargetSchema` vocabulary beside `Reducer`; it does not own execution or
  target-specific JSON/tokenizer declarations.
- a new `compile/product/` package: owns signature verification, lower × upper
  state composition, demand propagation, product-op lowering, bound-product
  caching, `ReductionMorphism`, and reducer-free `GrammarMorphism`.
  `compose.py` derives regular regions from semantic roles × target demand;
  `shape.py` privately owns the binding-derived recursive map-shape analysis
  moved from `MapShape.for_entry`.
- a new `parsing/product/` package: `records.py` owns immutable authored and
  flat ABI records, `state.py` owns parse-local builders and transactions,
  `regular.py` owns the authoritative regular-language proof,
  `verify.py` owns physical-table verification, and `__init__.py` is the sole
  parsing-internal façade. The package imports `lexic.ir` plus the existing
  `parsing/pda/core/` leaves `charsets` and `scanner`; `regular.py` reuses their
  `CharSet`, `build_recognizer`, and `compile_source` rather than implementing a
  second possessive lowering.
- `compile/artifact.py`: `reduce` selects and runs a cached `BoundProduct`.
  `_ReduceEntry`, `_reduce_entry`, the reduction-only `_variant_artifact`, and
  `_sub_run` are removed or replaced by generally named target-program
  compilation; none may retain model-then-fold execution.
- `compile/reduction.py`: reducer analysis moves into semantic-signature and
  product-program lowering. `ReduceDerivation`, `FoldPlan`, `RunSpec`,
  `SubRun`, and run/variant machinery survive only where the new lowering still
  proves a needed language or product transform; old reduction-only records and
  evaluators are deleted.
- `compile/reduce/fold.py`: `ReduceFold` is usable only as an uncommitted
  differential oracle while building the replacement. The module and its tests
  are deleted or ported before landing.
- `compile/reduce/variant.py`: occurrence cloning/elision is generalized into
  contextual lower-plus-upper composition. The reduction-specific surface is
  deleted once its proof machinery has moved.
- `compile/foldkit.py`: this is shared authored-fold vocabulary, not disposable
  reduction code. Its `IrNamed`, `FOLD_SYMBOLS`, `seq`, `model_fold`,
  `first_rest`, `absent_tail`, `ABSENT`, `FIRST_REST`, and `DECODE_INT`
  consumers in notation and generated self-grammar migrate to the common
  product-operation vocabulary while preserving the no-`eval` symbol channel;
  it is simplified or renamed only after those users have one final home.
- `compile/output/templating.py`: its separate parse architecture is removed.
  `select(spec)` becomes the beginner declaration and returns a real
  `ReductionMorphism[Selection]`; `CompiledGrammar.reduce(..., into=selection)`
  remains the only execution seam. The `MapShape` public export disappears;
  its required binding analysis moves privately to `compile/product/shape.py`.
  `Template`, `Template.run`,
  `spanify`, and their span/skip folds are deleted. Their reducer-free raw-key
  capability moves to `select_raw`, a `GrammarMorphism` through the same
  `CompiledGrammar.reduce` execution seam. Advanced schema/morphism authoring
  uses the same target contract.
- `parsing/fold.py`: model-only `FOLD_KINDS`, `FieldFold`, `FastCtor`,
  `RuleFold`, `ModelBody`, and `ModelFold` are deleted after callers move.
  Generated-model synthesis lowers directly to `CaptureSpec`,
  `RuleProduct[GrammarModel]`, a typed constructor operand table, and one
  `ProductProgram[GrammarModel, GrammarModel]`; the concrete start class is
  synthesized at runtime, while the static result never widens beyond
  `GrammarModel`. Public `parse()` still has that
  legitimate generated-model product, not a privileged engine implementation
  beside the target product.
- `parsing/pda/compiler`, its flat-program records/opcodes, and
  `parsing/pda/runtime/build.py`: model capture/build becomes the model
  specialization of the product ABI; superseded model-only modes and helpers
  are deleted after all callers migrate.
- `parsing/parallel/orchestrate.py` and `parallel/stitch`: structural planning
  is separated from product composition. Model reconstruction remains only as
  the generated-model product's composition law. No target copies its code or
  introduces a carrier bridge.
- `api/json_tokenizer.py`: `read` uses the tokenizer signature/schema/morphism;
  `tokenizer_of` remains because consuming an already-built `IrMap` is a
  different task, not a fallback for `read`.
- `grammars/json.py`: declares the JSON semantic signature with the JSON
  reducer. `api/json_tokenizer.py` declares the tokenizer schema and target
  algebra against that signature. Neither declaration is imported by generic
  parsing code.

The rejected `parallel/stitch/carrier.py` is never adopted. Every obsolete
symbol, import, test fixture, wiki statement, README example, and package-map
entry is removed or rewritten in the same effort. Lexic is pre-0.1; there is no
deprecated alias, compatibility adapter, feature flag, alternate old route, or
“legacy” implementation in the landed tree.

No production instrumentation belongs in these modules. All timing observation
stays in `tools/`, `zzz_current_work/260826-target-shaped-parse/proto/`, or an
external process.

## Delivery sequence

This is one architectural replacement even though it has an internal build
order. No incomplete alternate public path is landed.

First, Terra reviews the named ownership seams and implements the typed target
program plus the sequential PDA/Earley execution. The generated-model product
must retain behavior and may not regress parsing performance while it is recast
as one specialization. No reduction, tokenizer, memory, or MT gain offsets a
parse regression. If a correctness bugfix necessarily changes that cost, the
coordinator isolates and attributes it and stops for the user's explicit final
approval. The direct default IR product then establishes exact
differential parity against the current oracle; Python JSON and tokenizer
morphisms exercise shape-preserving and
layered/narrowing targets. Parallel fragment composition comes last, after the
sequential algebra is fixed, so it cannot dictate a model-shaped carrier.

After Terra's source side is complete, the coordinator profiles it externally
before handing it to Luna. Only one multithreaded benchmark runs at a time.
Luna then writes the differential, adversarial, integration, and performance
tests and runs formatting, lint, type checking, and the repository gates. The
coordinator reviews the complete diff before any commit.

The current reduction oracle and every superseded templating/model-stitch path
are deleted before the implementation lands. There is no “decline to model plus
fold” compatibility branch in the final tree.

## Proof obligations

The design is complete only when the following claims are demonstrated:

1. The lower grammar recognizes the complete document, and an upper grammar
   narrows acceptance only where its declaration says. Construction shortcuts
   do not alter that composed language or its failures.
2. Two formulations exposing the same semantic signature compile the same
   target schema without rule-name or generated-class knowledge.
3. The default IR target is exactly differential with current reduction for
   values and ordinary refusals; ambiguity compares complete root products.
   Differences caused solely by the definitive reduced-root relation replacing
   variant-model comparison are enumerated and reviewed; child-local scope is
   forbidden.
4. Python JSON is differential with its declared reference semantics on nested
   values, fractions, escapes, duplicates, empty values, and malformed input.
5. Layer composition accepts exactly the intersection declared by the lower
   grammar and upper target grammar; it does not merely construct less after a
   broader parse.
6. The tokenizer target is differential with the supported tokenizer-format
   contract across real fixtures, reordered object keys, missing/duplicate
   fields, escape-equivalent keys, unsupported knobs, special-token flags,
   malformed discarded values, pipeline variants, and pinned syntax/semantic
   failure order.
7. A discarded occurrence creates no model or target value. A validate-only
   occurrence releases successful temporaries at its completion boundary.
8. PDA, Earley fallback, sequential execution, and every engaged parallel split
   return or refuse identically for the same target. An unambiguous island
   splices locally; an ambiguous island carries an alternate seed through the
   enclosing product continuation and is decided at the requested root, never
   by span-local target equality or unconditional whole-document reparsing.
9. PDA and Earley execute the same flat product operations and capture layouts;
   each contextual rule executes either its differential reducer-expression
   range or its fused target range exactly once, every paid opcode/capture mode
   is a plain integer, and a target-specific callback cannot appear in any
   frequently completed rule.
10. Every parse-local builder is isolated by parse and worker. Public morphisms
    expose only recursively immutable declaration data; private artifact-owned
    caches retain typed programs without erasing `Carry` or `Result`, cannot
    retain expired source artefacts, and cannot change semantics by eviction.
11. Failed PDA attempts and islands roll back all accumulator, duplicate, and
    verdict mutations; Earley alternatives cannot contaminate one another.
12. A tokenizer schema mismatch consumes the remaining lower syntax through
    its recovery state, so later malformed syntax wins over recorded semantics.
13. Every parallel worker starts and ends in a compiler-proved fragment schema
    state; only the coordinator validates and finalizes the document root.
14. Parallel workers compose typed target fragments once; no run performs both
    direct and superseded model/fold construction.
15. The implementation introduces no `Any`, `object`, suppression, grammar-name
    special case, or per-character target dispatch.
16. The landed tree contains no `ReduceFold`, old reduction entry, separate
    templating parser, target carrier bridge, deprecated alias, or old-path
    fallback.

## Measurement contract

Instrumentation remains external and the measured `src` tree remains
untouched. Structural changes use alternating cross-process trees with a
byte-identical control row. Process CPU is reported as aggregate core-seconds,
not sequential wall time. Peak RSS and constructed product counts accompany
time.

Baseline and candidate workers are prepared, warmed, timed, and closed one
whole process at a time. The general benchmark comparator's concurrently
prepared cohorts are not used for this effort's MT rows because preparation
itself performs real parses. Alternation changes process order, never overlaps
workers. Timing passes carry no allocation tracer, constructor spy, or call
profiler; those observations run separately and are not timing evidence.

Every row records its garbage-collector state; only rows with equal GC state
compare, and production/acceptance rows run with the collector enabled (`src`
never touches collector state). The even, order-balanced eight-pair carrier
probe records +0.004562 s median process CPU and -0.002075 s wall; the wall sign
is noise, not a benefit claim (`reports/PROTOTYPE_7.md`). Earlier fixed-order
and odd-round deltas are rejected. Quoted historical constants are provenance,
not denominators: the §12 comparison re-measures the `0faa7289` baseline in the
same alternating session as the candidate, per §0's own rule.

The pinned §0 memory references are 633,000 KiB for a first resident-text ready
tokenizer, 632,888 KiB for a first cold path call, and 838,120 KiB at the second
path call in one retained warm process (`reports/PROTOTYPE_8.md`). The warm
process had already reached 634,592 KiB after its first call; the subsequent
203,528 KiB increase is a monotonic high-water delta, not a live-retention
diagnosis. Candidate RSS is compared to the matching lifecycle scenario in
fresh alternating processes. A cold result cannot excuse a warm retained
regression, and a close one-sample RSS result is rerun rather than declared.

Parsing is a hard non-regression gate of its own. Generated-model and
token-segmented parse rows are compared independently of reduction and final
target construction, and no aggregate end-to-end improvement can conceal a
slower parse row. A bugfix-related exception is not automatic: it requires
isolated attribution and the user's explicit final approval before landing.

Measure these products separately on `resources/tokenizers/qwen3.tokenizer.json`
and on non-JSON GBNF, ABNF, and EBNF witnesses:

- general JSON recognition versus composed tokenizer-schema recognition, both
  with no eager product;
- default direct IR reduction versus model plus `ReduceFold`;
- Python JSON versus the current IR path and `json.loads` as a representation
  lower-bound witness;
- direct `IrTokenizer` versus full `IrMap` plus `tokenizer_of`;
- resident `json_tokenizer.read(text, ...)` separately from cold and warm
  `read_from_path`, each against its like-for-like current route;
- each supported parallel split shape at 1, 2, 4, 8, and 16 workers;
- target-route proposal/certification separately from generic all-region
  discovery, proving the target path performs no duplicate whole-region scan;
- shared versus physically worker-owned compiled recognizers;
- cold setup, parse/construction, finalization, total wall, process CPU, and
  peak RSS.

Performance expectations are codomain-dependent:

| Codomain | Work that remains | Governing comparison |
|---|---|---|
| certified extent | recognition plus source bounds | measured 13.14 s → about 0.13 s construction result |
| Python JSON | decode every retained scalar and allocate the complete recursive tree | pursue less than 0.100 s on the 11,422,654-byte Qwen3 witness; gate the multiplier versus the remeasured old IR route, with `json.loads` as a lower-bound witness |
| default IR | construct the complete reducer codomain with IR validation/order | direct product versus model plus `ReduceFold` |
| `IrTokenizer` | recognize the composed tokenizer language; decode demanded fields; allocate final encode/decode/rank/pipeline tables | less than 1.000 s for resident text; compare with the baseline remeasured in the same alternating session and continue toward 105x for this scenario; report cold/warm `read_from_path` separately (historical 17.203148 s / 17.416359 s are provenance only) |

The selected feasibility shape measures the two dominant Qwen sections through
native capture, joins, canonical tokenizer-index freeze, and an actual tokenizer
record at 0.700274 s median process CPU / 0.130779 s median wall with GC enabled
on eight retained workers. The older 0.121197 s capture/join, 0.017504 s index
finalization, and 0.000032 s construction decomposition was GC-disabled and is
provenance only. Fresh single-run carriers increased peak RSS by about
79–82 MiB. A 6,098-character
shell-control prototype costs 0.001864 s for its stdlib stand-in; production
must replace it with the corresponding typed-hole check through the composed
product. Small fields, production shell execution, target bind/setup,
pipeline/root validation, and the ready result remain unmeasured. These figures
constrain implementation; they are not additive proof of a complete 105x
tokenizer.

The current tokenizer references are 17.203148 s with source text resident and
17.416359 s for the historical path-inclusive row. An isolated source-read
probe measured 0.046713 s on its first read and 0.019701 s median, but does not
replace the historical 0.213211 s observed stage. Final reports measure the
complete resident and path operations rather than adding independent medians.

The measured extent result establishes the scale of removable work. The
standing concrete goals are a pursued less-than-0.100 s for the reduced
recursive Python value and a gated less-than-1.000 s for the resident-text ready tokenizer, with
continued optimization toward roughly 105x for the Qwen tokenizer scenario.
That multiplier is not a universal gate on every reduction. The tokenizer's
upper grammar is far narrower than general JSON and can remove generic choices
and every intermediate representation. It must still pay demanded decoding and
final-table construction, so those costs are measured and optimized directly
rather than used to lower the target in advance.

Every target therefore gets a cost account:

```text
recognition + demanded decoding + final allocation/finalization
```

Recognition is not held constant: upper-grammar specialization should reduce
generic branching too. If direct tokenizer construction misses 105x, the report
identifies the exact remaining constructor, decoded byte population, allocation
count, and RSS, then optimizes that final representation instead of invoking an
assumed floor or falling back to the old path.
