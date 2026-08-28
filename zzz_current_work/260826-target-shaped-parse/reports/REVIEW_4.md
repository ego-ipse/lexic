# Plan review — target-shaped parsing, pass 4

**Reviewed:** 2026-08-27, limited to the REVIEW_3 cache/declaration blocker,
against the stable `DESIGN.md`, `goal.md`, `context.md`, `TODO.md`, `LEDGER.md`,
`reports/PROTOTYPE_2.md`, `proto/cache_lifetime.py`, and the corresponding
registry/declaration refactor in `proto/product_types.py`.

**Verdict:** **GO — begin §2 and the ABI portion of §3.** There are no remaining
architectural blockers in this review's scope.

The previous blocker is resolved. Public declaration values no longer reach
mutable cache state, locks, factories, executors, or entry dictionaries. Cache
residency is now separated from declaration semantics, and the retained-product
lifetime witness covers the required source-release direction.

---

## Blockers

None.

## Verified

- `MorphismDeclaration` contains only a `frozenset` and tuple of integers;
  `prove_declaration_is_data_only` verifies no cache, entries, factory, lock, or
  instance dictionary is reachable from it
  (`proto/cache_lifetime.py:40-45,204-217`).
- `ArtifactBindings` owns the mutable entries, lock, and cold factory outside
  the declaration (`proto/cache_lifetime.py:77-125`). Its key includes stable
  declaration identity as well as grammar and reducer identity, while the entry
  holds the declaration strongly so address reuse cannot alter a live answer
  (`:32-53,99-124`).
- The actual public-shape prototypes follow the same separation:
  `ReductionMorphism` is only the result-typed bind surface;
  `BindingRegistry` owns mutable state (`proto/product_types.py:662-749`); and
  `SelectionMorphism`, `DefaultIrMorphism`, and `TokenizerMorphism` are
  immutable `NamedTuple` declarations whose `_bind` methods enter private
  registries (`:857-890,1005-1034,1121-1156`). A mutable registry is no longer a
  field of any declaration.
- Eviction is semantics-neutral at the declaration boundary. No public mutation
  can replace a cached product for a declaration; a miss invokes the
  compiler/artifact-owned lowering factory using the same declaration, grammar,
  and reducer. The design now explicitly makes equivalent recompilation the
  cache contract (`DESIGN.md:206-220`; `goal.md:118-124`).
- The lifetime witness binds a real `CompiledGrammar`, retains its returned
  bound product as a pool would, drops the source, forces collection, observes
  registry eviction, and successfully runs the retained product afterward
  (`proto/cache_lifetime.py:182-201`). Concurrent first bind remains
  single-build under the registry lock (`:156-179`).
- The revised context, TODO, ledger, goal, design, and prototype report agree
  on the same ownership split and retain `parsing.caches` adoption as source
  implementation work rather than a second cache design.
- Re-ran `uv run python proto/cache_lifetime.py`,
  `uv run python proto/product_types.py`, and `uv run pyright proto/`: all pass;
  Pyright reports zero errors, warnings, and information messages.

## Phase gates retained

Production must still register product/PDA/Earley/replica derivations with
`parsing.caches.track/adopt/release`, and its lowering factory must retain no
source artefact. Those are explicit §3/§5 implementation gates, not an
architectural reason to delay the declarative signature work or the parsing ABI.
The existing real-engine routing, completion, selection, transaction, parallel,
reducer-lowering, and measurement gates remain as recorded; this review does not
reopen them.

## Start gate

Start §2 and the parsing-owned ABI/transaction/table work in §3. Preserve the
separation verified here: public morphisms are immutable declaration data;
compiler/artifact registries own all mutable binding state; and pools retain
only bound programs. Do not start §4 migration, parallel engagement, or
performance claims before their already-recorded phase gates. This report is the
sole change from this review.
