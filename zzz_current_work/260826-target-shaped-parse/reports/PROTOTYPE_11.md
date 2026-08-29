# Prototype 11 — interaction-exact ambiguity, real product rows, real pairs

**Phase:** close the five REVIEW_10 findings per `PROMPT_11.md`. Production
source, tests, and the planning documents are untouched (`git diff --stat --
src tests` empty; the four earlier report files an interim pass had
whitespace-modified are restored to HEAD byte-for-byte). Files: three new
prototypes (`ambiguity_interaction.py`, `keyed_product_rows.py`,
`resolver_pair.py`) and two rewritten ones (`ambiguity_rss.py`,
`custom_class_target.py`). `island_alternate_seed.py` is imported as the
shared real-kernel harness, unchanged.

This report was revised across THREE adversarial pre-delivery passes
(`reports/P11_ADVERSARIAL.md`). Pass 1's three blockers and both highs,
pass 2's two blockers (sibling accepting roots invisible to the set walk;
non-termination on cyclic charts), and pass 3's blocker (the cycle fallback's
tree fold was recursive and died at pad 2,000) are all FIXED IN CODE and
re-measured, together with every medium/low correction. Where a number
changed, the corrected number is the one quoted.

## Conclusions first

1. **One-flip replay is disproven; the exact replacement now handles packed
   families.** On a real two-point chart, production `another_meaning`
   returns `None` for a pure threshold `build` whose joint double-flip
   derivation means something else — a violation of its own documented
   "proven, not sampled" contract. The replacement (per-node value sets with
   semantic dedup) now enumerates **the node's own packed arm-choice
   families**, island leaf option sets, AND every sibling accepting item
   (a many-production start symbol's alternatives live in accepting ITEMS,
   not the link table — the union is unconditional, with no name-based
   routing). The cycle rule: a back edge switches the walk to one-lap
   enumeration through `FastTree`, whose consumed choices dict is
   production's TERMINATION mechanism verbatim — the RELATION computed is
   deliberately broader (interaction-exact combinations where production
   flips singly; on a cyclic interacting chart they provably diverge, and by
   this round's own thesis the divergence is the correction). On cyclic
   charts the invariant is one-lap-bounded — a cyclic chart has infinitely
   many derivations, and both production and this fallback answer over the
   one-lap set. The fallback is the rejected general architecture accepted
   ONLY as this bounded cycle path, priced executably at 2^k tree builds
   over k reachable arm points (4/10/20 ops for k=1/2/3). The eleven-case
   differential covers both sibling-root shapes, two same-meaning NEGATIVES
   (against an independent exhaustive-enumeration oracle), a unit cycle AND
   a pad-2,000 deep cycle (the tree folds are iterative — the standing
   iterative-equality ruling applies to the fallback too), and two
   shared-node charts; `another_meaning` cross-checks every default-policy
   case INCLUDING the cycles, which breaks the one circularity pass 3
   found (on cycle cases the enumeration oracle shares the fallback's
   implementation; the independent check there is `another_meaning`).
2. **Scope of the production defect, stated precisely.** No public entry
   accepts a caller-supplied `build` today (`parse` takes `resolve=` only;
   every production `build` is `fold.apply`), so this is a violated INTERNAL
   function contract, not a broken public API. The shipped model product is
   safe for a reason the earlier draft mis-stated: model fold operations are
   injective in their RETAINED children and **constant** in everything they
   drop (`value_str`'s span text is fixed by the input), and constancy —
   not joint injectivity — is what prevents interactions through dropped
   material. That corrected condition is the certificate the compiler must
   check; wording it as bare joint injectivity would force set propagation
   through every `value_str` rule.
3. **The certificate is now a meet over the family-aware DAG.** `sky[n]`
   holds only when EVERY parent edge — discovered under every family
   assignment, not just the default derivation — leads to a parent with an
   injective operation, no local arm-choice key, and a true sky, computed on
   a real topological order. A node under a true sky refuses early; local
   family multiplicity is always evaluated and deduplicated (two arms CAN
   collide on equal children), while child/leaf-sourced multiplicity under a
   single family refuses before enumeration (sound by injectivity in
   children); a cyclic parent graph simply yields no certificate (missing
   sky entries read as False), and under sibling accepting roots the
   certificate is skipped entirely — sound, since it only ever forgoes an
   early exit. Shared-node (multi-parent) charts are now
   differential witnesses, positives and negatives. Honest scope: an
   arm-choice key is owned by the PARENT completion's chain, so `choice_free`
   is false at the parent and the certificate is inert below any packed arm
   choice — the early exit survives on choice-free charts (island-sourced
   multiplicity), and per-EDGE `choice_free` granularity is the recorded §8
   fix for charts with alternations.
4. **Real keyed products, all lanes.** The comparison law is now over EVERY
   constructor input (vocab entries, merge sequence, pipeline): the
   merge-order alternate — pass 1's counterexample — AND a pipeline-differing
   alternate are executed kinds at every scale; the tokenizer refuses both
   while the merge/pipeline-free products accept them, asserted against the
   constructed carriers row by row. Verdicts stand with
   corrected numbers: cold carrier reconstruction per alternate at Qwen scale
   is 0.029–0.061 s (python dict), 0.16–0.23 s (`IrMap`), **1.18–1.46 s and
   81.4 MB retained (ready `IrTokenizer` with the real pipeline)**; the exact
   document-level comparison decides identically at 0.0002–0.075 s. Python
   dict keeps the cold fallback; `IrMap`/tokenizer adopt document-level
   comparison; per-alternate tokenizer reconstruction stays rejected.
5. **Resolver pairs: the splice makes the accepted ruling cheap.** Both
   complete-document trees are constructed and exactly associated with the
   replayed root meanings; a context-sensitive resolver provably chooses
   differently per pair scope; today's public island scope is local (real
   `parse` witness). NEW: splicing the island kernel's own derivations into
   the delegated outer tree produces trees **structurally identical** to the
   un-delegated pair at zero recognitions (9 µs) — so the user-accepted
   complete-document scope costs a splice on the Earley-delegated path, and
   one recognition only on the fused PDA path, which has no document-level
   ParseTree at all. (The prototype splice replaces one leaf; a multi-island
   document needs a leaf-identified splice — noted for the planning text.)
6. **Flat dependency index, both figures.** The CSR/forward-star arrays cost
   112 B/char; the **structure as retained** — including its
   handle-to-dense-number dict — costs 293 B/char (18.76 MB at 64 k chars),
   6.5× below the dict-of-sets oracle, with dirty-cone parity at every scale
   and on a two-key witness whose cones genuinely overlap without coinciding
   (sizes [3, 3], 2 shared ancestors, asserted distinct). Dictionary-free dense
   numbering (numbers assigned at completion time) is a REQUIREMENT on the
   production build, not an achieved measurement; the Qwen-scale
   extrapolation of the measured structure is ~3.1 GB, so the §12 bounded-
   input statement stands regardless. Cleanup is measured (8.3 KB tracemalloc
   residual after release), the control row's zero-structure counters are
   real container lengths, and frames/seeds are real allocations at
   96.2–98.2 B/frame with shared rule names.
7. **The custom-class mechanism, finished and lifecycle-bounded.** The bound
   view executes over retained derived tables after source-artefact death —
   including documents BEYOND its bind tier, recompiled cold from the
   retained derived AST; a data-edge gc-closure check proves no
   `CompiledGrammar` is reachable from it. The retention rule is explicit
   and measured: N equal-but-distinct declarations hold N pinned entries but
   ONE shared table derivation, and everything dies with the weakly
   referenced artefact (or explicit release, which recomputes equivalently
   and now drops the shared derivation too). One dependency stated plainly:
   PUBLIC artefacts from `compile_text`/`compile_ast` are memoised for the
   process, so "dies with the artefact" means process-lifetime there — the
   caller idiom (hold ONE declaration object per target) is a requirement,
   not a suggestion. Zero constructor traffic in completions is a STRUCTURAL
   property (the walk holds no reference to the constructor; the single call
   site follows it), stated as such rather than as a runtime count. Id-reuse
   safety is the double identity check — the strong pin keeps the
   declaration's id unrecyclable while its entry lives, every lookup
   re-validates `pin is declaration and grammar() is grammar`, the shared
   table memo re-validates its stored weakref the same way, and both death
   callbacks pop only the entry belonging to THEIR dead weakref, under the
   lock. The gc-closure proof now walks function closure cells and defaults
   (the exact lazy-retention shape it exists to rule out) while stopping at
   types/modules/code.

## A — multiple and nested ambiguity, exact

`proto/ambiguity_interaction.py`. Complete verbatim output:

```text
cd zzz_current_work/260826-target-shaped-parse/proto && uv run python ambiguity_interaction.py

production-another_meaning	UNSOUND for a pure threshold build: single flips equal, joint differs, and another_meaning returns None on a real two-point chart
chart-differential	two-point	value_sets=True	enumeration_oracle=True	another_meaning=True	AGREE
chart-differential	simple-arm	value_sets=True	enumeration_oracle=True	another_meaning=True	AGREE
chart-differential	outer-choice-shape	value_sets=True	enumeration_oracle=True	another_meaning=True	AGREE
chart-differential	sibling-roots-shared-child	value_sets=True	enumeration_oracle=True	another_meaning=True	AGREE
chart-differential	sibling-roots-two-prods	value_sets=True	enumeration_oracle=True	another_meaning=True	AGREE
chart-differential	NEGATIVE-simple-arm-dropped	value_sets=False	enumeration_oracle=False	AGREE
chart-differential	NEGATIVE-sibling-roots-dropped	value_sets=False	enumeration_oracle=False	AGREE
chart-differential	unit-cycle	value_sets=True	enumeration_oracle=True	another_meaning=True	AGREE
chart-differential	deep-cycle-pad2000	value_sets=True	enumeration_oracle=True	another_meaning=True	AGREE
chart-differential	shared-node-kept	value_sets=True	enumeration_oracle=True	another_meaning=True	AGREE
chart-differential	NEGATIVE-shared-node-dropped	value_sets=False	enumeration_oracle=False	AGREE
cycle-fallback-pricing	arm_points=1	one_lap_ops=4	retained=3	growth is 2^k in reachable arm points — the rejected general architecture, accepted only as the bounded cycle fallback
cycle-fallback-pricing	arm_points=2	one_lap_ops=10	retained=8	growth is 2^k in reachable arm points — the rejected general architecture, accepted only as the bounded cycle fallback
cycle-fallback-pricing	arm_points=3	one_lap_ops=20	retained=16	growth is 2^k in reachable arm points — the rejected general architecture, accepted only as the bounded cycle fallback
independent-injective	exact_differs=True	one_flip_differs=True	seed_enum_ops=8	set_ops=4	set_retained=4	set_max_live=4	set+hybrid_alloc_bytes=880	hybrid_ops=0	hybrid_retained=0	cartesian_root_combos=4
interacting-validation	exact_differs=True	one_flip_differs=False  <-- UNSOUND	seed_enum_ops=8	set_ops=4	set_retained=2	set_max_live=2	set+hybrid_alloc_bytes=880	hybrid_ops=4	hybrid_retained=2	cartesian_root_combos=4
interacting-conditional	exact_differs=True	one_flip_differs=True	seed_enum_ops=8	set_ops=4	set_retained=2	set_max_live=2	set+hybrid_alloc_bytes=880	hybrid_ops=4	hybrid_retained=2	cartesian_root_combos=4
dropped-parent	exact_differs=False	one_flip_differs=False	seed_enum_ops=8	set_ops=4	set_retained=1	set_max_live=1	set+hybrid_alloc_bytes=880	hybrid_ops=4	hybrid_retained=1	cartesian_root_combos=4
equal-islands	exact_differs=False	one_flip_differs=False	seed_enum_ops=8	set_ops=1	set_retained=1	set_max_live=1	set+hybrid_alloc_bytes=880	hybrid_ops=1	hybrid_retained=1	cartesian_root_combos=1
nested-two-source-island	exact_differs=True	one_flip_differs=False  <-- UNSOUND	seed_enum_ops=12	set_ops=4	set_retained=4	set_max_live=4	set+hybrid_alloc_bytes=880	hybrid_ops=0	hybrid_retained=0	cartesian_root_combos=2
separate-roots-dropping	exact_differs=False	one_flip_differs=False	seed_enum_ops=4	set_ops=6	set_retained=4	set_max_live=2	set+hybrid_alloc_bytes=760	hybrid_ops=6	hybrid_retained=4	cartesian_root_combos=2
keyed-duplicate-interaction	exact_differs=True	one_flip_differs=False  <-- UNSOUND	seed_enum_ops=8	set_ops=4	set_retained=2	set_max_live=2	set+hybrid_alloc_bytes=880	hybrid_ops=4	hybrid_retained=2	cartesian_root_combos=4
outer-arm-choice	exact_differs=True	one_flip_differs=False  <-- outer-chart scope (no seeds; production owns this shape)	seed_enum_ops=1	set_ops=6	set_retained=6	set_max_live=6	set+hybrid_alloc_bytes=1264	hybrid_ops=6	hybrid_retained=6	cartesian_root_combos=1
outer-arm-choice-dropped	exact_differs=False	one_flip_differs=False	seed_enum_ops=1	set_ops=6	set_retained=5	set_max_live=5	set+hybrid_alloc_bytes=1264	hybrid_ops=6	hybrid_retained=5	cartesian_root_combos=1
invariant	node set == exact distinct meanings over the node's OWN packed families x leaf options, unioned across accepting items; refuse iff |root set| > 1; on a CYCLIC chart the relation is one-lap-bounded (both here and in production) and computed by the consumed-choices enumeration, which is interaction-exact and therefore strictly broader than production's single flips; a node may refuse early only under a choice-free all-injective sky (meet over ALL family-aware parent edges; skipped under sibling accepting roots)
```

What the rows establish:

- **`outer-arm-choice`** (pass-2 blocker witness: one interior arm choice
  above an unambiguous island): the family-aware walk refuses correctly; the
  P10 seed lane is marked "outer-chart scope" rather than UNSOUND there,
  because it never claimed outer-chart ambiguity — production
  `another_meaning` owns that shape today and gets it right.
- **`chart-differential`** (ten cases): `value_sets` against an INDEPENDENT
  exhaustive-enumeration oracle (every family assignment through `FastTree`
  across every accepting item, folded and deduplicated) on every case, and
  against production `another_meaning` where its one-flip is sound. Cases
  include both sibling-accepting-root shapes (pass-2 blocker), two
  same-meaning NEGATIVES under dropping policies (so over-refusal is
  catchable, not just under-refusal), a unit cycle (pass-2 blocker: the walk
  detects the back edge and switches to the one-lap enumeration whose
  consumed choices dict is production's own termination rule), and two
  shared-node charts with 1–2 genuinely multi-parent nodes (positives and
  the dropping negatives) — closing the DAG-meet residue.
- **`interacting-validation` / `nested-two-source-island` /
  `keyed-duplicate-interaction`**: the three shapes where the accepted
  single-seed one-flip lane IS unsound — two sibling seeds under an
  at-most-one validation, two sources inside one island, and two islands
  whose entries collide into one decoded key only jointly.
- `set+hybrid_alloc_bytes` is the per-witness tracemalloc allocation figure;
  one-flip verdicts come from genuinely one-flip seeds (a separate delegated
  run), not from the exact sets.
- `apply_policy` refuses span (`atom`) policies in the set lanes explicitly,
  so the two algebras cannot silently diverge.

**Mechanism verdicts (revised).** Value-set propagation with semantic dedup
is the reference semantics — packed families, leaf option sets, and sibling
accepting items unioned unconditionally, with production's one-lap unroll as
the stated cycle rule (a `ChartCycle` back-edge detection switches to
consumed-choices `FastTree` enumeration). The certificate is the corrected
sky rule quoted in the invariant line, with the sound single-family
child-multiplicity precheck restoring `hybrid_ops=0` on injective skies; its
honest scope is choice-free charts, because an arm-choice key is owned by
the parent's chain — per-edge `choice_free` is the recorded §8 granularity
fix. Unconditional Cartesian and pair-carrying stay rejected (4 root combos
vs 2 retained at every interacting merge). The production correction required for
`another_meaning` (recorded, not applied): either verify a separability
certificate for `build` — injective in retained children AND constant in
dropped ones — before trusting single flips, or enumerate interacting-point
combinations with dedup; its docstring's compositionality inference is the
disproven step. No public seam supplies a non-separable `build` today, so
shipped `parse` behavior is unaffected.

**Real-machinery facts recorded for §8:** the chain walk CONSUMES its
choices dict (fresh copy per resolve); family indices and key populations
settle only at a census fixpoint under lazy Leo expansion; island meaning
sets must include sibling accepting items and nested leaf options; the sky
meet needs a real topological order over ALL parent edges, and charts with
genuinely shared nodes remain to be exercised on production shapes.

## B — the real keyed products, every constructor input

`proto/keyed_product_rows.py` (rewritten across both adversarial passes).
SEVEN alternate kinds per product — equal, value, key, duplicate,
projected(-away), **merges** (merge-order), and **pipeline** — at 128 and
8,192 real parsed catalog entries and at Qwen scale with the reader's REAL
pipeline (26 specials). The document `AltDoc(entries, merges, pipeline)`
carries every constructor input; the document-level comparison covers the
vocab lane (key-sorted, duplicate policy applied), the merge lane
(order-preserved: rank = position), the pipeline lane (record equality),
and the verdict lane; the fast accept is a full-input O(n) equality over
that whole document (sound because construction is a deterministic function
of ALL its inputs — never used to prove inequality). Every row asserts
document-level verdict == constructed-carrier verdict.

Qwen rows (`tools/guarded.sh 8G 600 -- uv run python
proto/keyed_product_rows.py --mode qwen`; reader setup 112.3 s aggregate CPU
/ 17.0 s wall, excluded from every structure row; 151,669 entries, 151,387
merges):

| product | kind | cold build CPU | cold total CPU | document-level CPU | equal |
|---|---|---:|---:|---:|---|
| python-last-wins | equal | 0.045 | 0.061 | 0.0002 (fast accept) | True |
| python-last-wins | value | 0.025 | 0.029 | 0.050 | False |
| python-last-wins | merges | 0.031 | 0.045 | 0.047 | True (merge-free law) |
| irmap | equal | 0.174 | 0.228 | 0.0002 (fast accept) | True |
| irmap | value | 0.164 | 0.181 | 0.059 | False |
| irmap | merges | 0.175 | 0.229 | 0.061 | True (merge-free law) |
| tokenizer | equal | 1.226 | 1.457 | 0.0002 (fast accept) | True |
| tokenizer | value | 1.163 | 1.182 | 0.066 | False |
| tokenizer | duplicate | 0.177 | 0.177 | 0.065 | False (verdict delta) |
| tokenizer | **merges** | 1.195 | 1.384 | 0.074 | **False** |
| tokenizer | **pipeline** | 1.157 | 1.382 | 0.073 | **False** |
| python/irmap | pipeline | 0.028 / 0.172 | 0.042 / 0.225 | 0.050 / 0.067 | True (pipeline-free laws) |
| tokenizer | projected | 1.174 | 1.402 | 0.002 (fast accept) | True |

Retained carrier bytes per alternate at Qwen scale (tracemalloc): python
42.7 MB, `IrMap` 26.7 MB, **tokenizer 81.4 MB** — the memory half of why
per-alternate tokenizer reconstruction is rejected. The `key` and
`duplicate` kinds now run at Qwen scale too (duplicate refusal parity with
the real `IrMap.from_table` inside the tokenizer's vocab construction). The
`projected` row is named for what it measures — a projection cancelling the
difference on both sides — distinct from §A's dropping-parent semantics.

**Adoption per law (revised wording):** recursive Python mapping — cold
carrier comparison stands; `IrMap` and `IrTokenizer` — document-level exact
comparison over all constructor inputs adopted; per-alternate tokenizer
carrier reconstruction rejected (~1.2–1.5 s + 81 MB each). No universal
multiplier exists.

## C — resolver handoff, real pairs and the splice

`proto/resolver_pair.py`, verbatim output:

```text
missing-information       outer_tree_island_child=PayloadLeaf(text='xy')  island_interior_completions_in_outer_chart=0  a complete pair therefore needs either a splice of the retained island derivation or one un-delegated recognition
complete-pair-cost        recognition_cpu=0.000062  recognition_wall=0.000061  tree_construction_cpu=0.000144  tree_construction_wall=0.000144
selection-correspondence  take-first/take-second materialize exactly their returned derivation's replayed root meaning
scope-divergence          island_local_choice=('t', ('pair', ('onetwo',)))  complete_choice_island_part=('t', ('pair', ('one',), ('two',)))  diverges=True  local_pair_construction_cpu=0.000067
splice-alternative        recognitions=0  construction_cpu=0.000009  construction_wall=0.000009  structurally_identical_to_undelegated_pair=True  NOTE: available on the Earley-delegated path only — the fused PDA runtime builds models with no document-level ParseTree, so the PDA path still requires one recognition to produce a complete pair
no-reparse-refusal        differs=True   document_reparses=0
no-reparse-equal-root     differs=False  document_reparses=0
public-scope-today        resolver saw pair roots ['t'] — island-local, not the document root
conclusion                complete pairs are constructible and associable after inequality is proven; the delegated chart provably lacks the interior; one pair scope must be chosen for engine parity, and today's public island scope is local
```

The splice answers the adversary's alternative directly: replacing the
delegated `PayloadLeaf` with the island kernel's own derivation yields trees
`==`-identical to the un-delegated pair at zero recognitions. The prototype
splice targets ONE leaf; a multi-island document needs a leaf-identified
splice (noted in planning edit #4). The stronger argument for when
recognition IS needed is the PDA one: the fused runtime has no
document-level `ParseTree` to splice into.

**The user's ruling (2026-08-29): complete-document pairs for both
engines — accepted.** The splice result improves its cost profile: on the
Earley-delegated path the complete pair is a 9 µs splice; only the fused PDA
path pays one recognition, and only after root inequality is proven with
`resolve=` supplied. The island-local behavior change remains an enumerated
pre-0.1 divergence. Refusal and equal-root paths reparse nothing (asserted).

## D — the real ambiguity structures, both figures

`proto/ambiguity_rss.py`, modes `control` / `ambiguity` / `frames`, each row
alone under `tools/guarded.sh`, sequential.

Flat index at pad 32,000 (64,001 chars), BOTH figures:

```text
flat-index-detail  nodes=128007  parent_edges=128006  distinct_keys=320014  array_bytes=7168340  bytes_per_edge=56.0  bytes_per_char=112.0  numbering_cpu=0.069948  csr_build_cpu=4.916546
stage  dict-of-sets-index[REJECTED oracle]  population=448020  traced_bytes=122247716
stage  flat-csr-index                       population=576027  traced_bytes=18762596
cleanup  released oracle+flat (oracle_parents=128006)  rebuild_held_bytes=18748980  post_release_residual_bytes=8328
two-key-parity  keys=2  cone_sizes=[3, 3]  shared_ancestors=2  distinct=True
```

| pad (chars) | arrays only | structure retained (incl. numbering dict) | B/char retained | oracle | ratio |
|---:|---:|---:|---:|---:|---:|
| 2,000 (4,001) | 448,340 | 1,265,820 | 316.4 | 7,545,992 | 6.0× |
| 8,000 (16,001) | 1,792,340 | 4,785,812 | 299.1 | 30,579,136 | 6.4× |
| 32,000 (64,001) | 7,168,340 | 18,762,596 | 293.2 | 122,247,716 | 6.5× |

The array-only 112 B/char is what the arrays cost; the structure the
prototype actually retains costs **293–316 B/char (6.0–6.5× below the
oracle)** because the handle→dense-number dict rides along. Dictionary-free
numbering — dense numbers assigned at completion time, no side dict — is
therefore a REQUIREMENT on the production build (which would land near the
112 B/char array figure), not something this round measured. Extrapolating
the measured structure to the 10.6 M-char Qwen witness gives ~3.1 GB, so
§12's bounded-input statement stands under either figure. The CSR build CPU
(0.31–4.92 s) remains an upper bound dominated by this prototype's chain
re-resolution; dense numbering itself is 3–70 ms. Dirty-cone parity against
the dict-of-sets oracle holds at every scale, and now also on a two-key
witness whose cones share an ancestor. Cleanup is measured: rebuilding and
releasing the flat structure leaves an 8,328-byte tracemalloc residual
(peak RSS is monotonic and cannot show a release; stated in-row). The
two-key parity witness nests its second choice under a distinct subtree so
the cones overlap without coinciding (sizes [3, 3], 2 shared ancestors,
distinctness asserted in-row).

The control row's five zero-structure counters are now **real container
lengths** — the containers exist, the ambiguous branch that would populate
them is provably unreachable (zero arm-choice keys, asserted), and the row
separates the root product value's own bytes (563 KB at pad 2,000 — every
parse pays its product) from the post-release residual (259 KB of interned
names and allocator noise).

Frames (`--mode frames`) allocate real `TraceFrame`s AND seed records, with
rule names from a pool built outside the window (production shares interned
names): **96.2–98.2 B/frame** across depth {128, 1024, 8192} × seeds
{1, 2, 4} — the earlier 165 B figure included a fresh f-string per frame and
is superseded.

## E — the custom-class mechanism, executable and bounded

`proto/custom_class_target.py` (revised), verbatim output:

```text
shapes                    frozen/validating/generic/unhashable-metaclass classes bind and run; value-keying is impossible for the unhashable one (shown), identity+pin keying carries it
traffic                   completions=9  constructor_calls=1
executable-lifetime       source artefact collected, registry entry released, and the retained bound view still parsed and constructed successfully
identity-semantics        equal declarations bind separately by design; id-reuse safety is the DOUBLE identity check — the strong pin keeps the declaration alive (its id cannot recycle while the entry lives) and every lookup re-validates `pin is declaration` AND `grammar() is grammar`
shared-tables-retention   equal_distinct_declarations=50 entries_held=50 table_derivations=1 shared_tables=1; all fifty entries (and pins) died with the artefact — retention is artefact-bounded, and the caller idiom is one held declaration object per target
long-document-after-death doc_chars=6397 parsed over tables recompiled from the retained derived AST; no CompiledGrammar reachable from the bound view (checked over the data-edge gc referent closure)
eviction                  release + rebind recomputed an equivalent binding; both views parse to equal results
concurrent-cold-bind      8 threads, 1 build, shared binding
cold-root-failure         validating constructor and class/field mismatch fail at root finalization; declaration-data defects refuse at binding with words
bound-run                 cpu=0.000580  wall=0.000579
PASS: custom classes run through retained derived tables with no class inspection, an identity+pin registry, and cold-root-only constructor traffic
```

Adversarial findings closed in code:

- **Retention rule (was unstated, and every bind re-derived tables):** the
  registry now shares ONE derived (AST, tables) pair per live artefact — 50
  equal-but-distinct declarations hold 50 pinned entries and 1 table
  derivation, and everything (entries, pins, shared derivation) dies with
  the weakly referenced artefact or on explicit `release` (which also drops
  the shared derivation so eviction stays equivalent-recomputation). The
  shared-derivation memo re-validates its stored weakref on every read —
  the same id-reuse rule as the entries, a trap this revision itself hit
  and fixed. The stated caller idiom: hold one declaration object per
  target; a bind is a cold table compilation only once per artefact.
- **Tier limit (was silent):** the binding retains the DERIVED normalized
  AST; a document beyond the base tier recompiles tables cold from that
  retained AST — proven by parsing a 6,397-char document AFTER the source
  artefact was collected. The §6 decision text should carry this shape
  (retained derived AST + per-tier recompile) explicitly.
- **Lifetime proof strength (was a shallow-copy artefact check):** a
  data-edge gc referent closure walk (stopping at types/modules/functions/
  code, which reach ambient compile caches from ANY class) proves no
  `CompiledGrammar` is reachable from the bound view.
- **Structural, stated as such:** the zero-constructor-traffic property is
  that the completion walk holds no reference to the constructor and the
  single call site follows the walk (the shared `invocations` list documents
  the call site; it is not claimed as a runtime count of calls nothing else
  could make). The vacuous id-reuse assertion is replaced with the direct
  pin-content check; safety is attributed to the double identity check.
- **The closure proof sees the shape it targets (pass 2):** the gc walk now
  traverses function closure cells and defaults — the exact lazy-retention
  shape REVIEW_10 §5 worried about — plus the class-attribute values of any
  non-builtin type (a registry hanging off a class is a data retention
  shape), with unset closure cells skipped, while stopping at
  modules/code/builtin types (which reach ambient compile caches).
- **Retention dependency stated (pass 2):** entries die with the weakly
  referenced artefact, and PUBLIC artefacts are process-memoised — so
  against a `compile_text` artefact the bound-entry table lives for the
  process, and the one-declaration-per-target caller idiom is a requirement.
  Both death callbacks now validate that the entry they pop belongs to THEIR
  dead weakref, under the lock, so a recycled id can never evict a live
  successor's entry.

## Gate classification

**Conclusively closed (mechanism level):**

- one-flip multi-source replay is unsound — production witness plus four
  island-level counterexamples (sibling validation, conditional, nested
  two-source, keyed-duplicate); Cartesian and pair-carrying stay rejected;
- the exact replacement semantics: per-node value sets with semantic dedup
  over packed families × leaf options, unioned over every accepting item,
  with production's one-lap unroll as the cycle rule — checked against an
  independent exhaustive-enumeration oracle on eleven charts (siblings,
  negatives, a unit cycle, a pad-2,000 deep cycle, shared nodes) and against
  `another_meaning` where its one-flip is sound; refusal ⟺ |root set| > 1;
- the per-product keyed-meaning ruling on real carriers over ALL constructor
  inputs: python dict cold; `IrMap`/tokenizer document-level; per-alternate
  tokenizer reconstruction rejected (1.2–1.5 s + 81 MB);
- complete resolver pairs: constructible, exactly associated, and — on the
  Earley-delegated path — obtainable by a structurally-identical splice at
  zero recognitions; refusal/equal paths reparse nothing;
- dict-of-sets replacement: flat CSR/forward-star with parity (incl. a
  two-key shared-ancestor witness), both byte figures reported, measured
  cleanup, real frame/seed allocations, and an honest control row;
- the custom-class mechanism: executable past source death including
  beyond-tier documents, zero class inspection, artefact-bounded retention
  with shared table derivations, unhashable-class-capable identity+pin
  registry, and structurally single-call-site cold-root-only constructor
  traffic.

**Proven but still requiring production integration measurement:**

- the corrected model-fold condition (injective in retained children +
  constant in dropped ones) at lowering; per-EDGE `choice_free` granularity
  so the certificate is not inert below packed arm choices; set lanes in
  `ParseState`; paid-loop cost (§3/§8);
- dictionary-free dense numbering for the flat index (a production build
  requirement; the measured structure is 293 B/char WITH the dict);
- document-level meaning lanes wired into the streaming accumulators (§8);
- custom-class paid-loop neutrality on the real engine (§4/§6).

**User decisions — RULED 2026-08-29:**

- resolver pair scope: **complete-document pairs for both engines** —
  accepted; the splice result makes the Earley-side cost a 9 µs tree
  operation, the PDA side one post-inequality recognition; island-local
  behavior change enumerated as a pre-0.1 divergence.
- custom classes: **kept, "accepted for now"**, under the constructor-symbol
  contract amendment; this round adds the retention rule and tier-escape
  shape to the §6 decision text.
- the standing bugfix-related parse-regression approval remains user-only.

**Failed candidates that stay rejected:** one-flip as the general law;
unconditional Cartesian propagation as the general architecture (accepted
solely as the bounded, 2^k-priced cycle fallback); pair-carrying; the tree-shaped sky
propagation (last-write over one derivation — replaced by the DAG meet);
dict-of-sets index; incremental treap and ordered trees for keyed laws; the
plain-dict cold row as a tokenizer proxy; entry-lane-only normalization for
merge-sensitive products (the adversary's counterexample — replaced by
all-input document-level comparison); value-keyed declaration caches for
arbitrary classes.

## Recommended planning-document edits (not applied)

1. `DESIGN.md` §State safety / §Earley-and-islands: replace the one-flip
   claim with the family-aware set invariant (union over packed families,
   leaf options, AND sibling accepting items; production's one-lap unroll as
   the cycle rule) and the corrected certificate (injective in retained
   children AND constant in dropped ones; sky as a meet over all
   family-aware parent edges; local families always evaluated and
   deduplicated; per-edge `choice_free` so the certificate is not inert
   below alternations). Record that `another_meaning` violates its own
   contract for non-separable internal `build`s, that no public seam
   supplies one today, and that §8's rewiring corrects it with this
   mechanism.
2. `TODO.md` §8: add the interaction witnesses (sibling validation, nested
   two-source, keyed-duplicate, outer-arm-choice, sibling accepting roots,
   the unit cycle, and the shared-node charts) as exit gates; add the
   machinery footguns (choices-dict consumption; census fixpoint; sky
   topological order degrading to no-certificate on cycles).
3. `TODO.md` §8 DECISION (keyed meanings): record the measured ruling with
   the ALL-inputs law — document-level comparison for `IrMap`/tokenizer
   (vocab lane sorted, merge lane order-preserved, pipeline compared), cold
   carriers for Python mappings, per-alternate tokenizer reconstruction
   forbidden; the fast accept is full-input equality over
   entries+merges+pipeline, sound for acceptance only.
4. `goal.md`/`DESIGN.md` resolver text: record the ruled complete-document
   scope, the splice mechanism (Earley-delegated path: zero recognitions;
   structurally identical pair; a multi-island document needs a
   leaf-identified splice), and the PDA no-ParseTree argument for the single
   post-inequality recognition.
5. `TODO.md` §3/§8/§12: the dependency index's production shape is CSR/
   forward-star with completion-time dense numbering (requirement), both
   measured byte figures quoted (112 B/char arrays; 293 B/char with the
   prototype's numbering dict; 6.5× vs oracle); §12 adopts the corrected
   control protocol (real containers, unreachable machinery branch,
   product-value bytes separated).
6. `TODO.md` §6: fold the finished custom-class proof in — identity+pin
   registry with the double identity check, artefact-bounded retention with
   one shared table derivation per artefact, the retained-derived-AST tier
   escape, and the caller idiom (hold one declaration per target).

## Verification

```text
uv run ruff format proto/{ambiguity_interaction,keyed_product_rows,resolver_pair,ambiguity_rss,custom_class_target}.py   # stable after fixes
uv run ruff check  <same five>                                                    # All checks passed!
uv run pyright     <same five>                                                    # 0 errors, 0 warnings, 0 informations
uv run python proto/ambiguity_interaction.py                                      # exit 0 (verbatim output in §A)
uv run python proto/resolver_pair.py                                              # exit 0 (verbatim output in §C)
uv run python proto/custom_class_target.py                                        # exit 0 (verbatim output in §E)
uv run python proto/keyed_product_rows.py                                         # exit 0 (128 + 8192, six kinds)
tools/guarded.sh 8G 600 -- uv run python proto/keyed_product_rows.py --mode qwen  # exit 0 (§B rows)
tools/guarded.sh 8G 900 -- uv run python proto/ambiguity_rss.py --pad {2000,8000,32000} --mode {control,ambiguity}   # all exit 0
tools/guarded.sh 8G 900 -- uv run python proto/ambiguity_rss.py --mode frames     # exit 0
git diff --check                                                                  # clean
git diff --stat -- src tests                                                      # empty
grep -rnE "type: *ignore|noqa|pylint: *disable|\beval\(|\bexec\(|: Any|-> Any|Any\]|: object\b|-> object\b|object\]|cast\(|__qualname__" <the five files>
    # one hit: a docstring sentence STATING that __qualname__ was removed; no construct
```

Every benchmark row ran alone, sequentially; Qwen-scale and RSS rows each
owned their guarded process; process CPU and wall are reported separately in
every timed row. The four earlier report files carrying incidental
whitespace edits (`PROTOTYPE.md`, `PROTOTYPE_2.md`, `PROTOTYPE_3.md`,
`REVIEW_6.md`) were restored to HEAD byte-for-byte, including the staged
copy of the first; a pass-2 `ruff format` glob that reformatted twenty
earlier committed prototypes was likewise reverted file-by-file, leaving
exactly the five files of this round modified.
