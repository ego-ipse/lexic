# Prototype 13 — closure correction and shipped ambiguity scope

Prototype 12 contains useful mechanisms and measurements, but its four-way
"conclusively closed" classification is superseded here. This correction
removes the two arbitrary cyclic caps, replaces the relabelled post-parse
control with an actual fused product, scopes both shipped ambiguity defects,
and separates prototype facts from production gates.

No production source or test was changed. No multithreaded or Qwen benchmark
was run. All executable work in this correction is under `proto/`.

## Decisions and evidence which stand

- The carrier-scoped zero-width-SCC classification is the selected cyclic
  decision candidate under the declared `const` / `ident` / `finite` / `grow`
  slot algebra. Safe components use a monotone exact-set fixpoint. An unsafe
  growing component with an injective path to a requested root establishes
  ambiguity from the classification alone; it is no longer unrolled for an
  arbitrary two laps.
- One-lap `FastTree` enumeration remains disproven by `ring-depth3` and the
  two-key bounded witness.
- The acyclic early-refusal certificate is existential and per slot: one real
  family path carrying a differing node injectively to a requested root is
  sufficient. Unrelated parents which drop that node do not invalidate the
  constructive pair. `ambiguity_interaction.py` now exercises this selected
  rule and retains parity with every exact oracle row.
- The tokenizer document relation is exact for the two constructors as
  currently specified. The intended final `from_indexes` validation contract
  is not closed until ordinal, merge-reference, and pipeline fallback/unknown
  semantics are selected from real tokenizer evidence.
- The retained flat CSR/forward-star representation and corrected frame shape
  stand. Completion-time numbering, family-aware edges, and integrated memory
  remain production obligations.
- The custom binding's real-pool ownership, source-death, eviction, concurrent
  map, failure, tier-escape, and shutdown evidence stand. Production custom
  completion traffic and neutrality remain §4/§6 exit measurements.

## Cyclic correction

`local_choice_keys` and the island family census now iterate to a structural
fixpoint. The previous eight-round guards were arbitrary caps. Termination
comes from a finite chart and idempotent Leo expansion.

An unsafe growing component no longer runs a two-lap value iteration. If its
carrier reaches a requested root through an injective path, the classification
already proves that the root has infinitely many distinct meanings. Exact-set
iteration is reserved for components whose reachable domain is finite.

This closes the **refusal decision** under the prototype algebra. Two items
remain explicit before production adoption:

1. lower the real product operations to the four slot classes and reject an
   operation whose law cannot be proved;
2. when `resolve=` is present, construct two complete derivations from a
   certified base path and one explicit traversal of the growing SCC. A numeric
   runtime lap count is not that construction.

The mechanism still enumerates families local to one completed node and child
option products. Its bound is
`O(V + E + laps × Σ families(node) × Π child-set cardinality)` for finitely
representable components. It never enumerates one chart-wide assignment over
all ambiguity keys.

Focused rerun:

```text
uv run python proto/cyclic_meaning.py

ring-depth3-one-lap-misses: exact differs=True; one-lap differs=False
two-key-cycle-bounded: exact differs=True; one-lap differs=False
unit-cycle-growing: cyclic-infinite; classification decides; exact_set=0
deep-cycle 2,001 / 8,001 / 32,001 chars: 0.094253 / 0.370185 / 1.525590 s CPU
```

The old `nullable-star-collapsed` label was wrong. Its text was `"xa"`, where
the repeated item consumes a character. It is now named
`nullable-star-consuming-item`; the empty-span defect is owned by the dedicated
scope probe below.

## Quantified-nullable ambiguity

`proto/nullable_quantifier_ambiguity.py` runs the public parser, `pda_model`,
and `earley_model` separately, then evaluates every surfaced family through the
real generated-model fold. The significant output is:

```text
quantifier star-ref          effective_differing_non_arm=1  PDA/Earley silently choose List(())
quantifier plus-ref          effective_differing_non_arm=1  PDA/Earley silently choose one Gap
quantifier bounded-zero-two  effective_differing_non_arm=1  PDA/Earley silently choose zero Gaps
quantifier bounded-one-two   effective_differing_non_arm=1  PDA/Earley silently choose one Gap
quantifier star-group        effective_differing_non_arm=1
quantifier star-empty-rule   effective_differing_non_arm=1
quantifier exact-two         effective_differing_non_arm=0
quantifier optional-ref      raw_differing_non_arm=1; lift removes the point
corpus grammars=15 flavours=('abnf', 'ebnf', 'gbnf') quantified_nullable_sites=0
```

The two engines agree on the wrong answer. The structural rule is generic: a
quantified nullable atom whose quantifier admits more than one occurrence
count creates semantic count families. Those are not text-allocation splits.
They enter complete target-meaning comparison; a dropped difference may still
compare equal at the requested root.

`lift_optional_nullables` currently suppresses the `?` family. Raw Earley and
the lifted public path choose different models, proving that the lift is not a
value-preserving ambiguity solution. It must be removed or replaced as part of
the same §8 correction.

## Complete ambiguity readout

The same probe confirms that a finished kernel with one deferred Leo top
reports zero ambiguity points before expansion and two after expansion:

```text
leo-readout  deferred=1  before=0  after=2
```

The selected contract is that the ambiguity readout expands all deferred Leo
provenance itself. A hidden caller precondition would make the planned cheap
precheck order-dependent. `custom_class_target.py` now uses the external
complete-readout helper, so its refusal witness no longer repeats the defect.

## Honest unambiguous control

The former control constructed a complete ParseTree-shaped value after parsing
and retained a document-sized handle-to-meaning table. It was exactly the shape
`PROMPT_12.md` rejected.

The corrected control invokes the existing fused PDA model product. It builds
the model during recognition, constructs no `ParseTree`, and has no
completed-handle meaning table. At pad 2,000:

```text
mode control
pad 2000 chars 4001 gc enabled
ambiguity-instrumentation not-wired; zero-allocation proof waits for landed factories
direct-product-state product_live_bytes=32808 product_peak_bytes=49312 product_cpu=0.004065 product_wall=0.004058 residual_bytes_after_release=256
```

This closes the external **control protocol**, not its zero-allocation result.
The current source has no candidate ambiguity factories to instrument. The
final §12 row must run the landed product with its real factories wired to a
refusing control; an unused prototype allocator cannot prove future source
wiring.

## Verification

All executable rows ran sequentially; no other benchmark or agent was active:

```text
uv run python proto/nullable_quantifier_ambiguity.py  exit 0
uv run python proto/cyclic_meaning.py                 exit 0
uv run python proto/ambiguity_interaction.py          exit 0
uv run python proto/custom_class_target.py            exit 0
uv run python proto/ambiguity_rss.py --mode control --pad 2000
                                                       exit 0
```

The custom-target run retained its real-pool lifecycle result and measured a
`0.998960` prototype-finalizer CPU ratio. The label and output explicitly state
that this is not production completion traffic. Targeted Ruff and Pyright pass
on all five corrected/new prototype files. No source, test, or harness file is
changed.

## Correct gate classification

Closed as prototype mechanisms:

- safe-SCC exact fixpoint and unsafe-SCC refusal decision under the declared
  algebra;
- one-lap unsoundness;
- tokenizer equality/refusal relation for each currently specified
  constructor;
- retained flat array layout, integer tiers, dirty-cone reference parity, and
  real frame allocation shape;
- custom bound-view and real-pool lifecycle;
- fused-product unambiguous-control protocol.

Still requiring a production implementation/proof or a planning decision:

- production semantic-family tagging for quantified-nullable counts and
  removal/replacement of `lift_optional_nullables`;
- production Leo-complete ambiguity readout;
- real-operation slot classification and a constructive resolver pair for an
  infinite SCC;
- the final tokenizer validation contract for the three open lanes;
- completion-time dense numbering and family-aware dependency edges;
- production custom-completion traffic and paid-loop neutrality;
- integrated ambiguity memory and performance.

The final fresh `READY` review required by `PROMPT_12.md` has not occurred.
Prototype 12 therefore remains historical evidence, not implementation
authorization. The active packet now reflects this classification and is ready
for that external review; production implementation remains closed until it
passes.
