# Review 10 — Prototype 10 closure audit

**Verdict:** useful partial evidence; the composite island, keyed-meaning,
custom-lifecycle, and ambiguity-RSS gates remain open.

## Conclusions which stand

- An island ambiguity is settled at the requested root, not at the island
  span. A single alternate can ride a cold island seed through an Earley
  ancestor cone or a PDA completion trace without discarding the predictive
  parse.
- Island alternate discovery includes sibling accepting items. A start-rule
  arm choice need not appear in `ambiguity_points`.
- Ordered persistent contribution trees remain valid for sequence products and
  are invalid for order-insensitive mappings.
- The incremental hash-priority treap is rejected. Its measured construction
  cost is unacceptable, and priority collisions also make its claimed
  canonical shape insertion-order-dependent.
- A `dict[int, set[int]]` dependency index is rejected for production. Its
  measured memory growth is unacceptable.
- Meaning equality is iterative. The recursive implementation fails on an
  ordinary deep ambiguity witness.
- Custom result classes remain in scope. The public declaration may retain one
  immutable class object as its constructor symbol; arbitrary factories,
  mutable rebinding registries, and reflection remain forbidden. A homogeneous
  result-free cached plan plus a reconstructed result-typed view resolves the
  heterogeneous-cache typing problem.
- The `DISTANT` grammar at pads 2,000, 8,000, and 32,000 is retained as the
  ambiguity-memory scaling witness.

## Findings which keep gates open

### 1. One-flip replay is not exact for multiple ambiguity sources

`proto/island_alternate_seed.py` evaluates each alternate against the baseline
individually and claims purity makes combinations unnecessary. Purity and
compositionality do not imply separability. A pure parent can return the
baseline for either single substitution and a different result when both are
substituted. Conditional, validation, mapping, and root operations can express
such interactions.

The next investigation must either prove an operation-specific separability
certificate or retain enough combinations to preserve the complete root-value
relation. It must also audit the identical assumption in production
`another_meaning`.

### 2. The keyed-product timing measured only a plain encode dictionary

The reported 0.024785 seconds constructs and compares one `dict[str, int]`
from an already materialized Qwen encode table. It does not construct an
`IrMap`, the tokenizer decode/rank/pipeline roles, or an `IrTokenizer`; nor does
it measure equal, key-set-changing, and duplicate-policy alternatives.

The incremental treap is rejected, but the choice between exact cold eager
comparison and another exact product-specific carrier remains open until the
real products are measured.

### 3. The complete resolver pair was not built

The resolver prototype performs one un-delegated recognition and counts its
ambiguity points. It never constructs the two complete-document `ParseTree`s,
associates the island alternate with its complete derivation, or invokes a
resolver. Local versus complete resolver handoff therefore remains an explicit
decision.

### 4. The RSS row did not allocate the claimed island lane

The island-seed stage records an estimated population and zero bytes; it does
not allocate the proposed trace frames. The `fold` control also allocates the
meaning memo which the proposed protocol says must be absent from its control.
The witness and scales stand, but the control protocol, actual trace-lane
account, and flat dependency representation remain open.

### 5. The custom bound-lifetime proof retains no executable

`BoundRecord.run` still requires the source `CompiledGrammar`. After deleting
that artefact, the witness checks only plan metadata. It also reads
`constructor.__qualname__` despite claiming not to inspect the class. The
constructor-symbol and result-free-plan decisions stand; executable lifetime,
reflection-free lowering, robust cache identity, and paid-loop neutrality
remain §6 gates.

## Required next evidence

The next prototype round must close the five findings above with adversarial
semantic witnesses and real product constructions. It must not edit `src`,
tests, or the active design documents. Its tasking is `PROMPT_11.md`, and its
deliverable is `reports/PROTOTYPE_11.md`.
