# Prototype report — review-pass-2 mechanisms

**Date:** 2026-08-27  
**Tree:** branch `targeter`, source baseline `0faa7289`; all executable work is
under this effort's `proto/`, with no `src` changes.

## Review findings addressed

`REVIEW_2.md` blocked source work on routing the child after a decoded
discriminator, cache lifetime, and routed/shell fragment composition. It also
required representable exclusive completion ranges, exact selection semantics,
and a bounded transaction layout before their source phases.

### Following-child route continuation

`proto/route_continuation.py` derives the real JSON mapping producer and
following-value position from the shipped grammar and reducer. A compiled
continuation carries producer completion, consumer position, route slot, and
finite route table.

- PDA completion publishes a plain-integer route in a dedicated frame lane;
  the following reference consumes it before child entry, and rollback restores
  the lane.
- Earley uses a sparse `(waiting contextual code, route) -> successor
  contextual code` table only at routed producer completion. The existing
  packed successor code carries route/occurrence identity, so differently
  routed children do not collapse and ordinary item layout/advance is unchanged.
- Real reducer decoding makes `"model"` and `"m\u006fdel"` enter the same
  specialized child while an extension enters its declared route.

The mechanism contains no target callback or grammar-name branch in runtime
state.

### Artefact-bounded target binding

`proto/cache_lifetime.py` binds real `CompiledGrammar` clones through a public
`MorphismDeclaration` containing only recursively immutable signature and
algebra values. A distinct private `ArtifactBindings` owner contains the
factory, lock, and hidden entries. Its typed entry weakly references the
source, strongly retains immutable declaration/reducer identities and a
result-only bound program, and removes itself when the source expires.

Eight simultaneous first binders construct once and receive the same bound
program. Warm lookup is lock-free; cold construction is double-checked under a
lock. Collecting the real source clone removes the private registry entry while
an explicitly retained pool-owned bound program remains runnable. The public
declaration exposes no cache, entry dictionary, lock, factory, executor, or
instance dictionary. The bound factory contract prevents the result from
retaining the source. Production still must adopt derived parser caches into
`parsing.caches.track/adopt/release`.

### Suspended routed fragment

`proto/suspended_fragment.py` uses the repository's routed-plan fixture and the
real `locate`/`divide` planning path over a 700-line witness. The coordinator
owns a `ShellSuspension` with exact lower, upper, route, capture, extent, and
resume state. Workers return direct typed carries; no `GrammarModel` is used.

Fragment merge carries boundary decoded-key state and stable verdict keys.
Three-fragment regrouping proves carry, duplicate detection, and verdict order
independent of join grouping. The coordinator attaches the joined carry,
resumes the same product suffix, and finalizes once.

### Completion exclusivity and transactions

`proto/product_types.py` now gives each contextual rule one index into
`CompletionRange(kind, start, length)`. Expression instructions and
fused/recovery/delegate instructions occupy separate tables. Verification
rejects absent, empty, unknown-kind, mismatched, and out-of-bounds ranges. One
rule cannot encode both alternatives.

`ProductMark` is constant-size. Sequence append and successful mapping insert
write reversible slot mutations only while speculation is live. Rollback walks
only mutations after the mark and removes exact keys without reconstructing a
retained key set. Nested marks are LIFO and successful outer commit clears the
log without copying builders. The prototype contains no builder/state clone:
Earley alternatives and island children start fresh, and only finished carries
and verdicts cross their boundary. Source work still owes the required cost
measurement under valid and failed large-builder speculation.

### Selection contract

`proto/selection_contract.py` defines `select` as a finite nested-mapping
semantic morphism. Its result is a declaration-ordered
`dict[tuple[str, ...], IrSelf]`. Missing paths are absent; `KEEP` retains the
exact reducer semantic value; unselected routes construct no semantic value;
repeated decoded keys refuse; a nested non-mapping records a shape verdict;
and syntax failure precedes semantic refusal. Array traversal and predicates
are not beginner syntax. An incompatible semantic signature refuses at bind.

## Validation

The repository Pyright environment reports zero errors, warnings, and
information messages over all prototype files. Sequential executable runs
report:

```text
PASS: typed products, transactions, fragments, and public overloads
PASS: decoded route controls the following PDA/Earley child
PASS: typed binding is single-build and artefact-bounded
PASS: suspended routed shell and lawful fragment joins
PASS: finite nested-mapping selection semantics
```

The structural reducer inventory remains 174 GBNF, 162 ABNF, 98 EBNF, and 44
JSON nodes. That is class reachability only, not operand lowering or executable
semantic coverage.

## Remaining implementation gates

These prototypes remove the architectural blockers; they do not justify broad
performance claims. Source phases must still:

- lower real reducer operands for every shipped reducer, notation, and
  generated-self-grammar caller with a raising unknown-action default;
- execute a real small grammar product through PDA and Earley before migrating
  the generated-model product broadly;
- run the completion-range verifier over every actual execution site;
- integrate product lifetime with explicit parser cache release;
- measure transaction behavior and generated-model paid-loop changes;
- attribute final vocabulary, inverse-vocabulary, rank, and pipeline
  construction before claiming the Qwen result.

No source implementation, semantic differential, or tokenizer benchmark is
claimed by this report.
