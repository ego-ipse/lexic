# Prototype 10 — island seeds, custom classes, product meanings, ambiguity RSS

**Phase:** investigate the four remaining open design gates before §2 source
work consumes them. Production source is untouched (`git diff --stat -- src
tests` is empty for this pass). Four new prototypes under `proto/`; nothing
else was created or edited by this investigation.

## Conclusions first

1. **Island alternate seed (A) — mechanism proven on real kernels.** An
   ambiguous island keeps its predictive result and publishes a cold
   `IslandSeed(baseline, alternates)`; the enclosing product replays only the
   occurrence-to-root continuation per alternate in isolated overlay state.
   Recognition runs once; refusal of a kept difference needs zero document
   reparses; the dropping-parent case is accepted without one. The
   pair-carrying alternative is measurably Cartesian (4 root meanings for two
   seeds versus 2 linear replays) and is rejected. The ancestor-cone machinery
   generalizes to the Earley-side enclosing run by treating the delegated
   `PayloadLeaf` as a first-class dirty seed; the PDA side needs only an
   O(ancestor-depth) trace lane recorded while a seed is live — the two shapes
   produce identical verdicts on every witness. One new obligation surfaced:
   the island-side alternate search must consult sibling accepting items
   (start-rule arm choices are invisible to `ambiguity_points`), exactly as
   the production `another_meaning` already does via `_sibling_roots`.
2. **Resolver handoff (A) — the design text mis-states today's contract.** The
   production island path already hands the resolver the *island-local* tree
   pair (`islands.py` `_settle_two_meanings`), not complete document
   derivations. The island kernel holds both local trees for free; a complete
   pair genuinely requires one un-delegated whole-document Earley parse, which
   the prototype runs only after root inequality is proven and only when
   `resolve=` is supplied. Recommendation: keep the island resolver pair
   span-local (today's behavior, zero extra parses ever); reserve
   complete-pair Earley for the Earley-root ambiguity where it already exists.
3. **Custom classes (B) — kept, under one precise contract amendment.** An
   arbitrary runtime class is reachable only via the class object itself,
   reflection, or a registry; the latter two are forbidden, and every class
   object is callable — so a literal "no public callable field" is formally
   unsatisfiable for this feature. The smallest change: the declaration may
   carry exactly one **class object as an immutable constructor symbol**
   (never a bound callable/factory/lambda/executor), invoked only at root
   finalization. The typing knot is solved without casts: the private registry
   caches a **result-free `RecordPlan`** (one homogeneous registry for the
   kind), and the result-typed bound view is rebuilt per bind from immutable
   parts. Frozen, validating, and generic classes all bind with exact static
   result types; eviction recomputes equivalently; entries die with the source
   artefact; the keep/omit ruling itself remains the user's (§6 marker).
4. **Product meanings (C) — different products, different verdicts, measured.**
   The ordered contribution tree is *law-incorrect* for keyed products (two
   insertion orders of one equal map compare unequal) — sequence-only, as
   PROTOTYPE_8 suspected. A canonical persistent key tree is law-exact
   (duplicate-refusal parity with `IrMapping.from_table`, order-insensitive
   equality matching `IrMap`), but its incremental build costs 6.7 s at the
   real 151,669-entry Qwen encode table (obtained through the real
   `json_tokenizer.read` reader, added tokens included) versus **0.025 s per
   exact whole-result cold comparison** — so for map, IR-map, and tokenizer
   dynamic maps, **the exact isolated cold comparison earns adoption** at
   realistic alternate counts. The measured contingency: a sorted **balanced
   conversion at first ambiguity** costs 0.164 s once and then 18 path-copied
   nodes + 27 compare visits per value-changed alternate (break-even ≈ 7
   alternates).
5. **Ambiguity RSS (D) — witness built, protocol defined, one red flag.** The
   staged ladder is linear at all three scales and the alternate overlay stays
   O(1) (3 entries at every scale). But the predecessor/parent dependency
   index as dict-of-sets costs ≈ 1.9 KiB **per character** — 2.2× the meaning
   memo itself and ~20 GB extrapolated to the Qwen document. REVIEW_9 M10 is
   quantified: production must lower the index to flat int arrays or the §12
   ambiguous row must state its bounded input size. Also observed live: the
   engine's recursive `same_value` overflows at pad 2000 — §8's
   iterative-equality bullet is mandatory, not stylistic.

## Boundaries

Real Lexic surfaces exercised: `canonical_grammar`/`normalize`/
`compile_tables`/`tier_for`, `Kernel` (including the `delegates=` island seam
and `PayloadLeaf`), `island_run`, `predecessor_chain`/`ChainSpec`/
`is_arm_choice`/`expand_leo`, `ambiguity_points`/`same_value`/`FastTree`,
`compile_text`/`compile_ast`/`CompiledGrammar.parse`/`.reduce`,
`IrMapping.from_table`, `IrMap.from_table`/`__eq__`, `IrTokenizer.from_merges`,
real ground-truth JSON formulations, and the fetched Qwen fixture's real
cardinalities.

Honest toy boundaries, stated per file:

- `island_alternate_seed.py`: meaning programs stand in for lowered completion
  ranges, and the PDA-shaped trace driver replays the real chart's completion
  order through an explicit frame/mark stack — a predictive run retains no
  chart, so the frame mechanics are the irreducible simulated part around the
  real `island_run`/delegate boundary.
- `custom_class_target.py`: value extraction rides the current
  `CompiledGrammar.reduce` route as the direct product's stand-in; the proof
  is declaration/binding/typing/lifecycle, not throughput.
- `product_meaning_structures.py --mode qwen`: the vocabulary comes through
  the real public reader (`json_tokenizer.read` → ready `IrTokenizer`), so the
  pairs are the final product's actual encode table; the reader's own cost is
  reported as a separate setup line (aggregate process CPU) and never enters a
  structure row, and the peak-RSS line is dominated by the reader (≈ the §0
  resident ceiling) — the structure-attributed figure is the tracemalloc
  `tree_bytes` column.
- `ambiguity_rss.py`: the fold is the same toy meaning program as
  `root_meaning_incremental.py`; charts, chains, and ambiguity points are real.

---

## A — island ambiguity without discarding the PDA parse

`proto/island_alternate_seed.py`. The enclosing run is one real Earley kernel
over the whole document with the island rule delegated (`Kernel(delegates=
{rid: delegate})` — the identical injection seam `pda/runtime/islands.py`
feeds); the delegate runs one real windowed `island_run` over real compiled
`ParserTables` and returns `(end, IslandSeed)`; the kernel files the seed as a
`PayloadLeaf` exactly as a PDA island splice does.

**Mechanism.** The island computes its baseline meaning once, then — cold,
only when its own chart holds a real arm choice, a sibling accepting item, or
a nested inner seed — computes each alternate island meaning by the same
ancestor-cone replay used inside the island chart. It settles nothing at its
span. The enclosing product compares at the requested root through two
equivalent continuation shapes:

- **cone** (Earley-side): the outer dependency graph gains one edge kind —
  `parents[id(leaf)]` — so `_dirty(id(leaf))` marks the delegated occurrence's
  ancestors and the replay folds only that cone over a sparse overlay with the
  leaf's meaning overridden;
- **trace** (PDA-side): while a seed is live, each ancestor completion appends
  one `TraceFrame(policy, name, sibling meanings, dirty slot)`; replay folds
  the alternate up those frames only. Sibling meanings are identity-shared
  references, not copies. Frames exist per live seed only; the unambiguous
  path allocates no lane, no trace, no graph (counters prove zero).

Both shapes agree with a full-refold differential oracle on every witness,
including nested `wrap`/`swap` parent transformations.

Command and complete output:

```text
uv run python zzz_current_work/260826-target-shaped-parse/proto/island_alternate_seed.py

kept-difference     differs=True   outer_runs=1  island_runs=1  document_reparses=0  seeds=1  alternates=3  baseline_folds=7  replay_folds=8   trace_frames=2  cones=[4, 2]        pair_shape_root_meanings=2
dropping-parent     differs=False  outer_runs=1  island_runs=1  document_reparses=0  seeds=1  alternates=3  baseline_folds=7  replay_folds=8   trace_frames=2  cones=[4, 2]        pair_shape_root_meanings=2
equal-meanings      differs=False  outer_runs=1  island_runs=1  document_reparses=0  seeds=0  alternates=1  baseline_folds=7  replay_folds=4   trace_frames=0  cones=[4]           pair_shape_root_meanings=1
nested-transforms   differs=True   outer_runs=1  island_runs=1  document_reparses=0  seeds=1  alternates=3  baseline_folds=7  replay_folds=8   trace_frames=2  cones=[4, 2]        pair_shape_root_meanings=2
two-seeds           differs=True   outer_runs=1  island_runs=2  document_reparses=0  seeds=2  alternates=6  baseline_folds=8  replay_folds=12  trace_frames=2  cones=[4, 4, 1, 1]  pair_shape_root_meanings=4
unambiguous-island  differs=False  outer_runs=1  island_runs=1  document_reparses=0  seeds=0  alternates=0  baseline_folds=6  replay_folds=0   trace_frames=0  cones=[]            pair_shape_root_meanings=1
nested-islands      differs=True   outer_runs=1  island_runs=2  document_reparses=0  seeds=1  alternates=4  baseline_folds=7  replay_folds=7   trace_frames=2  cones=[2, 1, 2]     pair_shape_root_meanings=2
resolver-handoff    island_local_pair=free (island kernel already holds both trees)  complete_pair_needs_full_parse=True points=1  refusal_path_reparses=0
rollback            failed parent removed its seed+frames; retained seed, duplicate set, and verdict order untouched
```

Reading the counts: `alternates` aggregates the island-internal flip
evaluations plus one cone replay and one trace replay per alternate (both
enclosing shapes run so they can be compared); `cones` lists overlay sizes —
always the ancestor path, never the document. `document_reparses` is asserted
`0` inside every witness. Every required witness is present: kept difference
(refused with no reparse), dropped difference (accepted with no reparse),
equal-but-differently-derived (no seed published at all — zero outer
machinery), nested transforms, two seeds (2 linear replays where the packed
pair shape materializes 4 root meanings), an unambiguous island (all counters
zero), nested islands (the inner seed replays to the island root and composes
outward as ONE island alternate — linear, not multiplicative), resolver
present/absent, and speculative-parent rollback (constant-size mark; seed and
frames discarded; retained seed, duplicate set, and verdict order untouched).

**Compared shapes.**

| shape | verdict | evidence |
|---|---|---|
| deferred value + completion trace (PDA side) | **adopted** | O(depth) frames per live seed, zero on unambiguous, replay = trace length |
| ancestor cone over the enclosing chart (Earley side) | **adopted** | one added dependency-edge kind (`id(leaf)`); same machinery as `root_meaning_incremental.py` |
| packed/deferred choice carried through parents | **rejected** | root meanings = Cartesian product over seeds (4 vs 2 on `two-seeds`); allocates on every ancestor even when the parent drops the child |
| verbatim reuse of completed-handle machinery for the PDA run | **rejected as stated** | a predictive run has no chart; its minimal equivalent record IS the trace, which the cone shape degenerates to on the spine |

**Multiple/nested seeds rule.** One-flip-at-a-time: alternates are evaluated
against the baseline individually, never in combination. This is exact for
the product ABI because completion operations are pure functions of their
children (the same compositionality `another_meaning` relies on); effects are
occurrence-owned and replay in isolated overlay state. Cost is Σ alternates,
not Π.

**Resolver handoff.** The current `Resolver` contract (`ambiguity.py`) is a
pair of `ParseTree`s. Today's island path already calls it with the
island-local pair. The prototype builds that local pair from the island
kernel at zero extra recognition; producing a complete-document pair provably
requires one un-delegated Earley parse (the delegated outer chart contains
only an opaque leaf for the island interior). The prototype runs that parse
exactly once, only in the resolver-supplied-and-differing branch, and asserts
the equality/refusal paths never do (`refusal_path_reparses=0`).

**Proven:** all thirteen mechanism requirements listed in the tasking, on real
kernels, with structural counts. **Unproven:** integration into the real PDA
frame layout (the trace lane must ride the existing frame/mark vocabulary at
§3/§8), cost on the real paid loop, and the island-side sibling-accepting-item
sweep in `islands.py`'s production replacement.

## B — arbitrary custom result classes

`proto/custom_class_target.py`.

**The impossibility boundary, precisely.** "Arbitrary runtime class" + "no
class object reachable from the declaration" + "no reflection" + "no mutable
registry" is jointly unsatisfiable: a runtime class is reachable only through
those three channels. Since class objects are callable, the literal "no public
callable/factory field" cannot hold for this feature. **Smallest contract
change:** permit exactly one class object on the declaration as an immutable
*constructor symbol* — `RecordSpec[Result].constructor: type[Result]` — with
these teeth kept: no bound callable/lambda/factory/executor field, no mutable
rebinding registry, no reflection (binding never inspects the class; Lexic
still infers no schema), and the symbol is invoked only at root finalization.

**The typing resolution nobody had recorded.** A single registry holding
`BoundProduct[Result]` for varying `Result` is unwritable without erasure. The
split that typechecks with zero casts: the registry caches a **result-free
`RecordPlan`** (field order, paths, qualname — plain data), one homogeneous
`dict[PlanKey, PlanEntry]` for the whole declaration kind; the result-typed
`BoundRecord[Result]` view is reconstructed per `_bind` from the immutable
declaration plus the cached plan. The expensive derived half is write-once and
cached; the typed wrapper is stateless and cache-free, so "no second cache of
the same binding" holds. Two consequences to record: (a) `bound is bound2`
identity across `_bind` calls is NOT promised — semantic equivalence is; (b)
the registry keys by declaration **value** (the spec is a hashable record),
which removes an id-reuse hazard this prototype actually hit (CPython reused a
dead declaration's `id()` and a stale plan answered a warm lookup) and makes
equal declarations share one binding.

Witness matrix, all passing:

- frozen dataclass, validating constructor (refuses at the cold root with its
  own `FieldValidationError`), and a generic `Box[Item]` bound as
  `RecordSpec[Box[str]]` — each with `assert_type`-exact results;
- declaration-data defects (empty fields, duplicate field, empty path) refuse
  with words at binding (`UnsupportedConstructError`);
- a class/field mismatch surfaces at first root finalization (a cold
  `TypeError` from the user's own constructor) — the honest residue of "no
  class inspection", to be pinned as the declared contract;
- two declarations bound concurrently across 8 threads: exactly 2 cold builds;
- explicit eviction → equivalent recomputation (`plan == old, is not old`);
- source-artefact death removes the entry (weakref); a pool-retained
  `BoundRecord` stays valid after both.

```text
uv run python zzz_current_work/260826-target-shaped-parse/proto/custom_class_target.py
PASS: custom classes bind through one immutable constructor symbol, a result-free
homogeneous plan registry, and cold root construction
```

**Ergonomics.** The beginner spelling is one literal:
`RecordSpec(TokenizerInfo, (("version", ("version",)), ("vocab_size",
("model", "size"))))` — a class plus named paths, no parser vocabulary at all.
The advanced morphism form remains for targets that need schema/validation
routing. This is materially simpler than authoring a `ReductionMorphism` and
requires no understanding of completion ranges, captures, or state.

**Rejected alternatives:** import-path strings (reflection channel, and an
`eval`-shaped hazard), a name-keyed registry the user populates (mutable
registry, exactly REVIEW_3's blocker), per-Result registry instances held in a
mutable map (heterogeneous registry of registries), and omission (the user
already rejected dropping the feature; this file shows omission is not
forced). **Unproven:** paid-loop neutrality (nothing here touches a frequent
completion by construction, but §6 must show the closed `RecordOp` path stays
int-selected), and the user's keep/omit ruling itself.

## C — exact persistent meanings for map, IR, and tokenizer products

`proto/product_meaning_structures.py`.

Law witnesses (`--mode laws`), all against real classes:

```text
insertion-order   keyed_tree=EQUAL (canonical shape)  equal_visits=1025  ordered_tree=DIFFERENT (law violation for keyed products — rejected)  IrMap_oracle=EQUAL
duplicates        REFUSE verdict parity with IrMapping.from_table; verdict order is contribution order; LAST_WINS is a distinct declared policy
alternate-costs   items=65536  changed_path_nodes=25  changed_compare_visits=35  equal_compare_visits=51  dropped_compare_visits=1  cold_compare_ops=65536 (plus one full materialization)
deep              depth=4000  visits=12000  iterative equality — no interpreter-stack dependence
tokenizer-order   meaning trees are keyed per index role; the CHOSEN result is ordered once at materialization; canonical id order validated on the real record (decode ids (0, 1, 2))
tokenizer-dirty   vocab_entries=4096  two_index_path_nodes=31  compare_visits=50  dirty work follows the changed semantic dependency across both roles
```

The Qwen-cardinality row (`tools/guarded.sh 8G 360 -- uv run python
proto/product_meaning_structures.py --mode qwen`, run alone, sequential; the
vocabulary is the ready tokenizer's real encode table from the public reader,
whose own cost is the separate setup line):

```text
qwen-scale-entries                 151669
qwen-scale-reader-setup-seconds    110.913215   (aggregate process CPU of the real reader; setup, not a structure row)
qwen-scale-balanced  convert_sort+build_seconds=0.163902  convert_nodes=151669  replace_path_nodes=18  replace+exact_compare_seconds=0.000045  balanced_compare_visits=27
qwen-scale           build_visits=2648908  build_nodes=3134923  build_seconds=6.685655  changed_path_nodes=23  exact_compare_visits=33  compare_seconds=0.000019
                     cold_build+compare_seconds=0.024785  materializations=1  materialize+order_once_seconds=0.076053  ordered_entries=151669
                     flat_dict_bytes=3844984  tree_bytes=22373448  peak_rss_kib=634460
```

The peak-RSS figure is dominated by the reader setup (it matches the §0
resident ceiling); the structure-attributed memory is the tracemalloc column:
22.4 MB tree versus 3.8 MB flat dict.

**Representation comparison.**

| representation | law on keyed products | cost at 151,669 entries | verdict |
|---|---|---|---|
| persistent ORDERED contribution tree | **wrong** — separates equal maps with different insertion orders | n/a | sequence-like products only (PROTOTYPE_8 stands, scoped) |
| canonical key tree, built incrementally (treap, hash placement / exact equality) | exact (canonical shape; duplicate parity; O(log n) alternates) | 6.7 s build, 3.1 M nodes, 22.4 MB vs 3.8 MB flat | **rejected**: the build IS a hidden document-scale cost on every ambiguous parse |
| balanced conversion at first ambiguity + shape-preserving value replacement | exact for value-changed alternates; key-set changes decline to cold | 0.164 s once; then 18 nodes / 27 visits / 45 µs per alternate | contingency; break-even ≈ 7 alternates |
| exact isolated whole-result cold comparison | exact by construction | 0.0248 s build+compare per alternate; zero setup, zero retained bytes | **adopted** for Python-map, IR-map, and tokenizer index products |

Additional facts the law rows pin: duplicate-refusal verdicts carry
contribution order (an *ordered* lane beside any keyed carrier — duplicates
are order-observable even in order-insensitive products); a projection that
drops the changed entry compares in 1 visit (identity); a 4,000-deep nested
meaning compares iteratively (the engine's recursive `same_value` cannot — see
§D); canonical tokenizer order is validated on the real record and restored
exactly once at materialization of the chosen result (0.076 s at Qwen scale),
never inferred from equality; a changed vocab entry dirties encode AND decode
(two path copies — dirty work follows the semantic dependency); `hash` is used
for tree *placement* only, never as an equality proof, and `hash(int)`
degenerates the treap without mixing (measured: 4,106-node path copies on an
id-keyed role) — recorded so no production variant repeats it.

**Verdict per product:** sequences keep PROTOTYPE_8's ordered persistent tree;
Python mapping (both duplicate policies), IR `IrMap`, and all three tokenizer
index roles adopt the exact whole-result cold comparison, with the measured
balanced-conversion contingency recorded for a hypothetical high-alternate
regime; no shared universal carrier exists that preserves the distinct
duplicate/order laws AND wins on cost — and that is a measured conclusion, not
a fallback shrug. Nothing here adds anything to the unambiguous path: the
representation choice happens at fold entry where the chart's ambiguity points
are already known.

## D — ambiguity RSS witness and the §12 protocol

`proto/ambiguity_rss.py` — the `root_meaning_incremental.py` distant grammar
at a parametric pad, staged structure by structure. Verified: the grammar DOES
adequately expose the memo and dependency index (both linear and document-
sized), the sparse overlay (O(1) at every scale), the island-seed lane
(O(depth)), and a same-size sequence contribution tree. All rows sequential,
each alone under `tools/guarded.sh`:

```text
tools/guarded.sh 8G 600 -- uv run python proto/ambiguity_rss.py --pad {2000|8000|32000} --mode {fold|ambiguity}
```

| pad (chars) | mode | chart pop | memo pop / bytes | dep-index pop / bytes | overlay pop | replay folds | peak RSS KiB | wall s |
|---:|---|---:|---|---|---:|---:|---:|---:|
| 2000 (4,001) | fold | 20,009 | 8,007 / 3.54 MB | — | — | 0 | 65,424 | 1.149 |
| 2000 (4,001) | ambiguity | 20,009 | 8,007 / 3.54 MB | 28,020 / 7.56 MB | 3 | 3 | 77,592 | 1.452 |
| 8000 (16,001) | fold | 80,009 | 32,007 / 14.08 MB | — | — | 0 | 139,356 | 3.028 |
| 8000 (16,001) | ambiguity | 80,009 | 32,007 / 14.08 MB | 112,020 / 30.58 MB | 3 | 3 | 182,864 | 4.131 |
| 32000 (64,001) | fold | 320,009 | 128,007 / 55.91 MB | — | — | 0 | 427,340 | 10.573 |
| 32000 (64,001) | ambiguity | 320,009 | 128,007 / 55.91 MB | 448,020 / 122.25 MB | 3 | 3 | 607,868 | 15.041 |

Asymptotics: every population and byte figure scales ×4 with pad ×4 — linear,
as claimed. The alternate overlay and replay-fold count are **constant** (3)
across a 16× document growth — the headline locality claim holds at scale.
The island-seed lane and the 64,001-item sequence tree (5.13 MB, 80 B/item)
are negligible beside the memo.

**The red flag:** the dependency index (dict-of-sets `parents` + `owners`)
costs ~1.9 KiB per character — 2.2× the meaning memo — and dominates the
ambiguity-mode RSS delta (+180 MiB at 64 k chars). Extrapolated to the
10,635,788-character Qwen witness it would be ~20 GB. The prototype's index
shape is therefore a **witness**, not the production representation: §3/§8
must lower it to flat int arrays (one parent-edge array indexed by a dense
handle numbering; an edge is 8–16 B, ~50–100× smaller), or the §12 ambiguous
row must state a bounded input size. Also observed live at pad 2000: the
engine's recursive `same_value` raises `RecursionError` — the §8 iterative
equality walk is a correctness prerequisite for this row, not polish.

**The §12 ambiguous-row protocol (defined now, executed at §12):**

- **witness:** the `DISTANT` grammar above at pad 32,000 (64,001 chars), input
  `"a"*pad + "q" + "b"*pad`, SHA-256 of the input recorded in the row; small
  (2,000) and medium (8,000) rows retained for the linearity check.
- **baseline command:** the `0faa7289` tree parsing the same witness through
  the public route with a take-first resolver, one process, alone:
  `/usr/bin/time -v tools/guarded.sh 8G 600 -- uv run python <ext harness> --mode baseline`;
  the baseline allocates no memo/index (today's `another_meaning` rebuilds
  `FastTree`s), which is exactly why the candidate row exists.
- **candidate command:** the completed implementation running
  `reduce`/`parse` on the same input with the same resolver, same guard, same
  isolation.
- **process isolation:** one whole process per row, prepared/warmed/timed/
  closed before the next starts, alternating baseline/candidate order across
  repeats; no other benchmark, agent, or MT job during any window.
- **GC state:** collector enabled, recorded per row; only equal-GC rows
  compare.
- **semantic witness:** the row asserts verdict `differs=True` (or the
  resolver's chosen value digest) and refuses to report timings on a wrong
  verdict.
- **populations reported beside RSS:** default-meaning memo entries,
  dependency-index entries (and its representation), alternate-overlay
  entries per alternate, island-seed/continuation frames where an island
  witness is included, and persistent-meaning node counts where a sequence
  target is measured.
- **metrics:** peak RSS (`ru_maxrss` / GNU time), wall, aggregate process CPU
  and CPU-per-byte, replay-fold counts.
- **control row:** the same input parsed with ambiguity machinery absent
  (`--mode fold` equivalent) — the unambiguous tax must be zero, and the
  control reads the noise band.
- **failure:** any memo/index/overlay allocation on the control row; overlay
  or replay work scaling with document size instead of cone size; candidate
  peak RSS above baseline on the *same* witness without a named structure
  accounting for it; a verdict mismatch.
- **why separate from the tokenizer ceilings:** the unambiguous §0 rows
  (633,000 / 632,888 / 838,120 KiB) price a parse that never allocates these
  structures; folding a deliberately ambiguous input into those ceilings
  would either hide the index cost (small witness) or fail the ceiling for a
  reason the tokenizer scenario can never exhibit (no arm choice exists in
  the composed tokenizer language). The ambiguous row is its own account.

---

## Recommended DESIGN.md edits (not applied)

1. §Earley-and-islands: replace "may use complete-document Earley only to
   obtain the complete derivation pair required by the existing resolver
   contract" with a recorded choice — the island resolver pair stays
   **island-local** (today's actual `islands.py` contract; zero extra
   recognition), OR name the complete-pair Earley entry as a deliberate
   contract change. State that the island alternate search must include
   sibling accepting items at the island's end column.
2. §State safety: name the island seed record (`baseline + alternates`), the
   PDA trace lane (O(ancestor depth), recorded only while a seed is live,
   rollback-owned), the Earley leaf-dependency edge, and the one-flip
   linearity rule for multiple/nested seeds with its compositionality premise.
3. §State safety / §12: state that the dependency index's production
   representation is flat int arrays over a dense handle numbering, with the
   measured 1.9 KiB/char dict-of-sets figure as the rejected shape.
4. §Custom classes: replace "public callable/factory field ... fails the
   gate" with the amended wording: one class object as an immutable
   constructor symbol is admitted on the declaration; bound callables,
   factories, mutable registries, and reflection remain forbidden; binding
   never inspects the class; class-side mismatch is a declared cold
   first-parse failure. Record the result-free-plan/typed-view split and
   value-keyed registry as the §6 binding shape.
5. §State safety (ambiguity meanings): record the C verdicts — ordered trees
   sequence-only; cold comparison adopted for keyed products with the
   balanced-conversion contingency and its break-even.

## Recommended TODO.md edits (not applied)

1. Mark **PLANNING REQUIRED before §8 (island seed)** closed by this report;
   add three §8 bullets: sibling-accepting-item sweep in the island alternate
   search; the trace lane rides the existing PDA mark/rollback vocabulary; the
   island resolver-pair scope per the DESIGN ruling above.
2. Under the §8 **DECISION REQUIRED** (map/IR/tokenizer meanings): record the
   measured ruling — exact cold comparison for keyed products, persistent
   ordered trees sequence-only, balanced conversion as a contingency with its
   0.164 s / 7-alternate break-even — leaving only the formal closure at §8
   exit.
3. §6 custom-class bullet: point the keep/omit decision at this report's
   contract amendment; the mechanism is proven, the ruling is the user's.
4. **PLANNING REQUIRED before §12**: closed — witness, scales, commands, and
   failure criteria above; add the dependency-index representation bullet to
   §3 or §8 so the 1.9 KiB/char shape never reaches §12.
5. §8: annotate the iterative-equality bullet with the live pad-2000
   `RecursionError` witness (it is a prerequisite for the §12 ambiguous row).

## Gate classification

| open gate | classification |
|---|---|
| island alternate seed / continuation / replay (PLANNING before §8) | **solved conditionally** — mechanism, isolation, rollback, linearity, and counts proven on real kernels; real PDA frame integration and paid-loop cost remain §3/§8 work |
| island resolver handoff scope | **still requires a user decision** — span-local (today's contract, recommended) vs complete-pair; evidence and costs demonstrated |
| map/IR/tokenizer persistent-meaning choice (DECISION at §8) | **solved conditionally** — measured ruling delivered (cold comparison; ordered trees sequence-only; balanced-conversion contingency); formal closure happens at the §8 exit as scheduled |
| custom-class keep/omit (DECISION at §6) | **still requires a user decision** — feasibility proven under the smallest contract amendment (immutable constructor symbol); omission is not forced |
| custom-class paid-loop neutrality | **still requires production measurement** — by construction nothing touches a frequent completion; §4/§6 gates verify it on the real loop |
| ambiguous-input RSS witness + §12 protocol (PLANNING before §12) | **solved** — witness, scales, staged populations, commands, control, and failure criteria defined and exercised |
| dependency-index production representation | **solved conditionally** — dict-of-sets rejected by measurement (~1.9 KiB/char); flat-array lowering is a stated §3/§8 obligation, then re-measured at §12 |
| recursive `same_value` at depth | **blocked by a demonstrated conflict** until §8's iterative walk lands — the §12 ambiguous row crashes without it (observed at pad 2000) |
| bugfix-related parse regression | **still requires a user decision** — untouched, as standing |

## Verification

All commands from the repository root; every prototype run is quoted above.

```text
uv run ruff format proto/island_alternate_seed.py proto/custom_class_target.py \
    proto/product_meaning_structures.py proto/ambiguity_rss.py        # 4 files reformatted
uv run ruff check  <same four files>                                  # All checks passed!
uv run pyright     <same four files>                                  # 0 errors, 0 warnings, 0 informations
uv run python proto/island_alternate_seed.py                          # exit 0 (output quoted in §A)
uv run python proto/custom_class_target.py                            # exit 0 (PASS line quoted in §B)
uv run python proto/product_meaning_structures.py                     # exit 0 (laws output quoted in §C)
tools/guarded.sh 8G 360 -- uv run python proto/product_meaning_structures.py --mode qwen   # exit 0 (real-reader vocabulary)
tools/guarded.sh 8G 600 -- uv run python proto/ambiguity_rss.py --pad 2000  --mode fold       # exit 0
tools/guarded.sh 8G 600 -- uv run python proto/ambiguity_rss.py --pad 2000  --mode ambiguity  # exit 0
tools/guarded.sh 8G 600 -- uv run python proto/ambiguity_rss.py --pad 8000  --mode fold       # exit 0
tools/guarded.sh 8G 600 -- uv run python proto/ambiguity_rss.py --pad 8000  --mode ambiguity  # exit 0
tools/guarded.sh 8G 600 -- uv run python proto/ambiguity_rss.py --pad 32000 --mode fold       # exit 0
tools/guarded.sh 8G 600 -- uv run python proto/ambiguity_rss.py --pad 32000 --mode ambiguity  # exit 0
git diff --check                                                      # clean, exit 0
git diff --stat -- src tests                                          # empty, exit 0
grep -rnE "type: *ignore|noqa|pylint: *disable|\beval\(|\bexec\(|: Any|-> Any|: object|-> object|Any\]|object\]" <the four files>
                                                                      # no matches
```

Benchmark rows ran strictly sequentially, one process at a time; no
multithreaded benchmark exists in this pass. No file under `src/`, `tests/`,
or the authoritative plan documents was modified.
