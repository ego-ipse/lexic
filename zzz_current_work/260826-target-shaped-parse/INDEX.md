# Index — target-shaped parsing

**Current state (2026-08-29):** `REVIEW_9.md` returned GO for §2.
`PROTOTYPE_10.md` investigated the remaining design gates; `REVIEW_10.md`
accepts its narrow eliminations and requirements while rejecting five
overstated closures. The active documents distinguish those closed facts from
the multiple-seed, resolver, real keyed-product, flat-index/RSS, and custom
executable-lifetime gates. `PROMPT_11.md` tasks the next evidence round.
Production source has not started in this effort.

## Start here

Read these in order before implementation:

1. [`INDEX.md`](INDEX.md) — this inventory and authority map.
2. [`context.md`](context.md) — current code, historical failure modes, and
   evidence boundaries.
3. [`goal.md`](goal.md) — final public behavior, acceptance, performance, and
   deletion conditions.
4. [`DESIGN.md`](DESIGN.md) — the coherent architecture and proof obligations.
5. [`TODO.md`](TODO.md) — executable implementation order and phase gates.
6. [`LEDGER.md`](LEDGER.md) — chronological state and corrections.
7. [`TBD_after.md`](TBD_after.md) — explicitly deferred work; do not mix it
   into this implementation.

`TODO.md` is the implementation queue. `DESIGN.md` explains the choices; it is
not a second checklist. When they appear to disagree, stop and reconcile them
before source work.

## Authoritative review packet

The current packet is:

- [`reports/REVIEW_10.md`](reports/REVIEW_10.md) — closure audit of the latest
  investigation; records which conclusions stand and which gates remain open;
- [`PROMPT_11.md`](PROMPT_11.md) — exact tasking for the next prototype round;
- [`reports/PROTOTYPE_10.md`](reports/PROTOTYPE_10.md) — island, custom-class,
  keyed-meaning, and ambiguity-RSS evidence, constrained by `REVIEW_10.md`;
- [`reports/REVIEW_9.md`](reports/REVIEW_9.md) — latest independent review; GO
  for §2, with corrections required before later consuming phases;
- [`reports/PROTOTYPE_9.md`](reports/PROTOTYPE_9.md) — REVIEW_9 proof, routing,
  and closed-operation ABI corrections plus the remaining planning gates;
- [`reports/PROTOTYPE_8.md`](reports/PROTOTYPE_8.md) — exact §0 source/RSS/
  consumer baseline and persistent exact root meanings;
- [`reports/PROTOTYPE_7.md`](reports/PROTOTYPE_7.md) — root-equivalent
  ambiguity, regular-region derivation, declaration-only morphisms, DAG
  accounting, and controlled timing, as corrected by `PROTOTYPE_9.md`.

Earlier reports are provenance. Their results remain useful only where the
newer reports do not explicitly supersede them.

## Review and evidence history

| File | Role now |
|---|---|
| [`REVIEW_1.md`](reports/REVIEW_1.md) | Initial architecture review; public/type questions. |
| [`PROTOTYPE.md`](reports/PROTOTYPE.md) | Typed product ABI, reducer coverage, opcode evidence. |
| [`REVIEW_2.md`](reports/REVIEW_2.md) | Following-child route, cache, fragment, transaction blockers. |
| [`PROTOTYPE_2.md`](reports/PROTOTYPE_2.md) | Mechanisms answering REVIEW_2. |
| [`REVIEW_3.md`](reports/REVIEW_3.md) | Found public declaration retaining mutable binding state. |
| [`REVIEW_4.md`](reports/REVIEW_4.md) | Focused GO after the declaration/cache ownership correction. |
| [`REVIEW_5.md`](reports/REVIEW_5.md) | Independent scoped GO for §2 and ABI/lifecycle §3. |
| [`PROTOTYPE_3.md`](reports/PROTOTYPE_3.md) | First performance-feasibility evidence; some composition claims superseded. |
| [`REVIEW_6.md`](reports/REVIEW_6.md) | Rejected additive ready-tokenizer budget. |
| [`PROTOTYPE_4.md`](reports/PROTOTYPE_4.md) | Composed carrier, tokenizer-index shape, scenario boundaries. |
| [`REVIEW_7.md`](reports/REVIEW_7.md) | Performance arithmetic, ambiguity, GC, gate-placement audit. |
| [`PROTOTYPE_5.md`](reports/PROTOTYPE_5.md) | REVIEW_7 mechanisms; child-local, route, regular-proof, timing, and GC conclusions are explicitly superseded. |
| [`PROTOTYPE_6.md`](reports/PROTOTYPE_6.md) | First consistency correction; child-local and odd-pair GC rulings are explicitly superseded. |
| [`REVIEW_8.md`](reports/REVIEW_8.md) | Rejected child-local semantics, implicit value-string consult, and weak regular proof. |
| [`PROTOTYPE_7.md`](reports/PROTOTYPE_7.md) | Current root/regular/routing/DAG/measurement correction set. |
| [`PROTOTYPE_8.md`](reports/PROTOTYPE_8.md) | Current §0 RSS/consumer baseline and persistent exact-meaning correction. |
| [`REVIEW_9.md`](reports/REVIEW_9.md) | GO for §2; found nullable possessive, island scope, non-sibling routing, hot-callback, ownership, test, and cost-account gaps. |
| [`PROTOTYPE_9.md`](reports/PROTOTYPE_9.md) | Executes the REVIEW_9 proof/routing/ABI corrections and enumerates the remaining marked planning gates. |
| [`PROTOTYPE_10.md`](reports/PROTOTYPE_10.md) | Investigates island seeds, custom classes, keyed meanings, and ambiguity RSS; use only through REVIEW_10's corrected scope. |
| [`REVIEW_10.md`](reports/REVIEW_10.md) | Accepts the narrow Prototype 10 results and identifies the unsupported interaction, measurement, resolver, RSS, and lifetime claims. |

## Prototype inventory

All prototypes are external to `src`. They are first-class mechanism or
measurement witnesses, never production modules.

| Prototype | One-line purpose |
|---|---|
| [`ambiguity_rss.py`](proto/ambiguity_rss.py) | Establishes the retained ambiguous-memory witness and rejects a dict-of-sets dependency index; its seed-lane/control protocol is incomplete. |
| [`anchored_tokenizer_regions.py`](proto/anchored_tokenizer_regions.py) | Measures one-pass target-region capture from schema route anchors. |
| [`baseline_rss.py`](proto/baseline_rss.py) | Measures unchanged-reader peak RSS for resident, cold-path, and retained warm-path scenarios. |
| [`bulk_lexical_cost.py`](proto/bulk_lexical_cost.py) | Measures grammar-derived bulk lexical recognition across real grammars. |
| [`cache_lifetime.py`](proto/cache_lifetime.py) | Proves typed bound-product cache entries die with their source artefact. |
| [`capture_ownership_cost.py`](proto/capture_ownership_cost.py) | Attributes parallel capture cost to shared mortal inputs. |
| [`capture_phase_profile.py`](proto/capture_phase_profile.py) | Profiles cumulative phases inside grammar-derived parallel capture. |
| [`carrier_gc_cost.py`](proto/carrier_gc_cost.py) | Measures the composed carrier with collector state explicit and order-balanced. |
| [`composed_ir_regions.py`](proto/composed_ir_regions.py) | Measures routed high-volume capture into final tokenizer IR leaves; the leaf-heavy representation is rejected. |
| [`composed_native_tokenizer.py`](proto/composed_native_tokenizer.py) | Measures native target capture through canonical final tokenizer indexes and a ready record. |
| [`custom_class_target.py`](proto/custom_class_target.py) | Proves the constructor-symbol/result-free-plan typing shape; executable lifetime and reflection-free binding remain open. |
| [`demand_selection.py`](proto/demand_selection.py) | Proves reducer-free selection as occurrence demand in one parse; its resolver route stand-in is rejected. |
| [`island_alternate_seed.py`](proto/island_alternate_seed.py) | Proves single-seed cone/trace continuation and sibling-root discovery; its one-flip multiple-seed rule is rejected. |
| [`local_meaning_fold.py`](proto/local_meaning_fold.py) | Supplies the counterexample proving child-local ambiguity is not root-value equivalent. |
| [`opcode_cost.py`](proto/opcode_cost.py) | Checks the CPU cost of enum values leaking into flat opcode tables. |
| [`parallel_lexical_ownership.py`](proto/parallel_lexical_ownership.py) | Measures shared versus private recognizers across non-JSON grammars. |
| [`parallel_merge_region_cost.py`](proto/parallel_merge_region_cost.py) | Measures a grammar-derived repeated-dyad region and direct rank product. |
| [`parallel_region_cost.py`](proto/parallel_region_cost.py) | Measures grammar-derived regular-region fragments over one retained pool. |
| [`persistent_meaning.py`](proto/persistent_meaning.py) | Proves exact identity-sharing equality and one chosen-result materialization for large meanings. |
| [`product_meaning_structures.py`](proto/product_meaning_structures.py) | Rejects ordered keyed meanings and the incremental treap; its plain-dict timing does not decide real keyed products. |
| [`product_types.py`](proto/product_types.py) | Proves typed flat ABI, state, marks, operations, completion ranges, and binding shape. |
| [`python_tree_cost.py`](proto/python_tree_cost.py) | Measures the stdlib recursive-Python lower-bound witness on Qwen. |
| [`qwen_parse_cost.py`](proto/qwen_parse_cost.py) | Measures current Qwen grammar parsing without fold or tokenizer construction. |
| [`reducer_coverage.py`](proto/reducer_coverage.py) | Inventories expression-operation coverage over every shipped reducer. |
| [`reducer_free_surface.py`](proto/reducer_free_surface.py) | Types the reducer-bearing and reducer-free forms of one `reduce` seam with inert public declarations. |
| [`region_discovery_cost.py`](proto/region_discovery_cost.py) | Measures current grammar-derived structural region discovery on Qwen. |
| [`regular_region_lowering.py`](proto/regular_region_lowering.py) | Derives, lowers, differentials, and prices a composed regular region. |
| [`regular_region_proof.py`](proto/regular_region_proof.py) | Conservatively proves possessive regular-region lowering exact or declines it. |
| [`root_meaning_incremental.py`](proto/root_meaning_incremental.py) | Uses the real Earley kernel to replay one ambiguity's completed-handle ancestor cone to the root. |
| [`route_continuation.py`](proto/route_continuation.py) | Proves semantic/raw following-child routing in PDA and Earley with zero added grammar arms. |
| [`route_table_cost.py`](proto/route_table_cost.py) | Compares finite-route representations outside parser source. |
| [`schema_region_cost.py`](proto/schema_region_cost.py) | Measures a grammar-derived repeated mapping region with direct captures. |
| [`schema_shell_cost.py`](proto/schema_shell_cost.py) | Measures pre-submission certification of target-route interior proposals. |
| [`selection_contract.py`](proto/selection_contract.py) | Executes the finite nested-mapping beginner selection contract. |
| [`self_locating_region_cuts.py`](proto/self_locating_region_cuts.py) | Measures schema-derived self-locating cuts without an all-mark sidecar. |
| [`shared_forest_refold.py`](proto/shared_forest_refold.py) | Exposes interleaving-dependent fold execution over shared and transparent-synthetic subtrees. |
| [`source_read_cost.py`](proto/source_read_cost.py) | Measures the path-only boundary excluded from resident-text products. |
| [`suspended_fragment.py`](proto/suspended_fragment.py) | Proves a routed-interior product as a suspended shell plus lawful fragments. |
| [`token_parse_cost.py`](proto/token_parse_cost.py) | Baselines the public token-segmented grammar product in one process. |
| [`tokenizer_index_shape.py`](proto/tokenizer_index_shape.py) | Measures tokenizer-native immutable index shapes over real IR leaves. |
| [`tokenizer_table_cost.py`](proto/tokenizer_table_cost.py) | Measures Qwen-scale final tokenizer-table construction outside `src`. |
| [`tokenizer_table_phases.py`](proto/tokenizer_table_phases.py) | Separates tokenizer-table accumulation from canonical ordering. |
| [`windowed_region_discovery.py`](proto/windowed_region_discovery.py) | Prototypes window-composable discovery through escaped opaque interiors. |

The `.ruff_cache/` and `__pycache__/` directories are local tool artefacts, not
part of the packet.

## Implementation landmarks

- §0 is complete in `TODO.md` / `PROTOTYPE_8.md`.
- §1 type/prototype gate is complete as corrected by `PROTOTYPE_9.md`.
- Production begins at §2, then follows §3–§11 in order.
- Explicit `PLANNING REQUIRED` and `DECISION REQUIRED` markers in `TODO.md`
  are hard entry/exit gates, not implementer discretion.
- §4, §5, §7, §9, and §11 have checkpoint gates.
- §12 is the complete-source external profile.
- §13 is the sequential Luna test/lint handoff.
- §14 is coordinator review/integration under the recorded grant.

No parse-performance regression is admissible without the user's explicit
post-measurement approval, even for a bugfix. No two multithreaded benchmarks
run concurrently. Instrumentation stays outside `src`.
