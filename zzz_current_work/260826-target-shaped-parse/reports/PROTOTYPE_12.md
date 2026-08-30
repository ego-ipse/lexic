# Prototype 12 — the four surviving mechanism gates

**Phase:** close the four gates `PROMPT_12.md` names. Production source, tests,
`pyproject.toml`, and the active planning documents are untouched
(`git diff --stat -- src tests` empty; `git status --porcelain` lists exactly
the four tracked prototypes of this round). Files: one new prototype
(`proto/cyclic_meaning.py`) and four revised ones (`ambiguity_interaction.py`,
`keyed_product_rows.py`, `ambiguity_rss.py`, `custom_class_target.py`).
`island_alternate_seed.py` and `resolver_pair.py` are unchanged and re-run
green as regression witnesses.

Host: free-threading CPython 3.14.3 (`sys._is_gil_enabled() is False`), 16
cores, collector ENABLED on every row. Every benchmark ran alone and
sequentially; the Qwen-scale and RSS rows each owned a `tools/guarded.sh`
process; process CPU and wall are reported separately in every timed row. No
agent ran while a measurement process was live.

## Conclusions first

1. **The cyclic `2^k` fallback is replaced by an exact terminating mechanism,
   and one lap is executably UNSOUND for the refusal verdict.** A chart cycle
   is always a zero-width strongly connected component, so the loop operations
   around it are classifiable by the closed algebra: `const` (constant in the
   cycle slot), `ident` (returns it unchanged), `finite` (declared finite
   image), `grow` (embeds it as a proper sub-value, hence injective and
   size-increasing). A component terminates **iff no `grow` edge lies on a
   cycle carrying no `const`/`finite` edge** — decided in linear time. It is
   then solved by a monotone Kleene fixpoint over exact deduplicated value
   sets; termination follows from the classification's finite value domain,
   and the iteration asserts the monotonicity that argument rests on rather
   than guarding a lap cap. A surviving `grow` component is judged on its
   CARRIERS — the `ident`/`grow` upward closure of the growing sub-cycle,
   never the whole component: an all-injective path from a carrier to an
   accepting root means the root family is genuinely infinite (refuse, with a
   two-lap witness pair for `resolve=`); no value-carrying carrier means the
   carriers are frozen to a representative while every non-carrier member of
   the component stays exact; anything between reaches a bounded-image
   consumer and is REFUSED AT BINDING with words. Nothing enumerates global
   assignments. The `ring-depth3` and `two-key-cycle-bounded` witnesses show
   the one-lap relation returning `no ambiguity` where the exact relation and
   an independent bounded-depth derivation oracle both refuse — the P11
   fallback was not merely expensive, it was wrong.
2. **The one-lap relation's blindness has a name.** `FastTree` consumes each
   choice key at first visit, so the one-lap set only ever contains unrollings
   up to the number of distinct arm-choice keys the chart happens to hold —
   a chart artefact, not a semantic bound. An operation whose distinction
   first appears one unrolling deeper is invisible to it. That is the whole
   defect, stated as a property rather than as a counterexample.
3. **The tokenizer refusal relation is complete, message for message, and the
   document-level comparison still wins.** Two constructors are modelled: the
   shipped `IrTokenizer.from_merges` (whose reachable precedence — duplicate
   merge dyad < special outside the vocab < duplicate token ordinal — was
   MEASURED, not assumed) and a prototype `from_indexes` with seven ordered
   validations. Every ordered pair of a 20-document exhaustive family agrees
   between the constructed result and the normalized document view for both
   constructors — 400 pairs each (800 in total), including 144 and 169 pairs
   where BOTH sides refuse and 108 / 140 where they refuse with DIFFERENT first
   verdicts. At Qwen scale the tokenizer document-level lane costs
   0.000168–0.118661 s against a cold reconstruction of 0.875860–1.543143 s
   wherever it actually builds a tokenizer (and as little as 0.058491 s on a
   row that refuses early), so the P11 adoption ruling stands with the relation
   now complete. Two `from_merges`/`from_indexes` divergences and three lanes
   neither tail validates are declared, not accidental.
4. **The flat dependency index is dictionary-free and costs 98–112 B/char
   RETAINED.** No handle-to-number map survives the build; the transient build
   peak that does hold one is measured separately (1200–1223 B/char) and
   released before the retained structure is priced. The P11 293–316 B/char
   figure is superseded. Lookup, owner, parent-edge, dirty-cone, cleanup,
   integer-tier and overflow laws are all asserted in-row.
5. **The control cannot reach an ambiguity allocation, by construction.** Every
   ambiguity-only structure in the file — meaning memo, both dependency
   indexes, overlay, seed, trace frame — is built through an allocator object
   and through nothing else; the control installs a subclass whose every
   method raises. The row completing IS the evidence, and the zero counters
   are that same object's census. Ordinary direct product state is reported
   separately and by name.
6. **The frame row is corrected.** One child tuple per completed ancestor,
   shared only among the seeds crossing that completion — the shape
   `island_alternate_seed._record_frames` actually allocates. Across depth
   {128, 1024, 8192} × seeds {1, 2, 4} × arity {1, 2, 4} the cost is
   **144.2–446.4 B per completion** and 96.8–177.7 B per frame. The rejected
   96–98 B/frame figure is not carried forward: at one seed the per-completion
   cost is 144.2–177.7 B, because the child tuple is a per-completion cost the
   earlier row shared across the whole depth.
7. **The custom target survives a real `ParsePool`, and the paid loop is
   neutral.** The bound product is handed to `lexic.parsing.parallel.pool.
   ParsePool`; the source artefact is collected and the registry entry
   released BEFORE the first map; 32 documents plus one beyond-tier document
   are then parsed and constructed through the retained pool on the
   free-threaded interpreter; closing the pool drops the bound product
   (weakref proof). Concurrent maps, constructor failure, eviction and
   shutdown are covered. Constructor traffic is now measured with an external
   counter on a real consumer class AND by running the same completion walk
   under a constructor that raises on any call: 0 on the walk, 1 at the root.
   Three malformed documents and one genuinely ambiguous document all refuse
   with zero constructor calls, so no unchosen result is ever built. The
   default control and the custom target through the same engine shape measure
   0.431578 s and 0.432181 s minimum process CPU (ratio 1.001399) in the run
   quoted in §D; across the round's runs of this row the ratio moved between
   0.995 and 1.008, so its sign is not stable.

---

## A — the exact terminating cyclic mechanism

`proto/cyclic_meaning.py` (new) owns the meaning algebra, the chart-resolution
helpers, and the cyclic mechanism. `proto/ambiguity_interaction.py` now IMPORTS
that algebra instead of carrying a second copy, and its cyclic lane calls the
mechanism; the `2^k` `_one_lap_meanings` fallback is gone from the decision
path and survives only as a named comparison lane.

### The semantic question, stated

A cyclic grammar derives one string in infinitely many ways, so the four things
`PROMPT_12.md` asks to be distinguished are:

- **Infinitely many derivation trees vs. finitely many completed handles.** The
  SPPF is finite; the derivation set is not. A mechanism that answers by
  enumerating derivations therefore cannot be exact, and one that answers by
  enumerating *meanings* cannot terminate when the meaning family is infinite.
- **Deciding `|root meanings| > 1` vs. enumerating them.** The ambiguity
  contract asks only the former. That is what makes an exact answer possible
  on a chart whose meaning family is infinite.
- **Value-growing, value-erasing, idempotent, and choice-bearing zero-width
  SCCs.** A chart cycle forces equal spans (a child's span is contained in its
  parent's), so every cycle is zero-width and its loop operations are
  classifiable per slot: `ident` adds nothing (lfp = base), `const` makes the
  loop map constant (lfp reached in two laps), `finite` bounds the reachable
  value domain by a declared image, `grow` embeds the cycle child as a proper
  sub-value so `f^n(b)` are pairwise distinct.
- **`FastTree`'s consumed-choice behaviour vs. the intended contract.**
  `FastTree` consumes each choice key at first visit, so the derivations it can
  build unroll a cycle at most once per distinct arm-choice key. That bound is
  a property of how many keys the chart happens to carry, not of the language
  or the algebra. It is a TERMINATION device that P11 mistook for a relation.

### The mechanism

Per accepting-root closure, over the family-aware completed-node graph:

1. classify every edge's slot as `const` / `ident` / `finite` / `grow` from the
   parent's lowered operation (`slot_class`, `cyclic_meaning.py`);
2. propagate two boolean lanes from the accepting roots — `visible` (some path
   with no `const` edge) and `injective` (some path with no `const` and no
   `finite` edge);
3. Tarjan SCCs, descendants first, iteratively (a chart is as deep as its
   document);
4. per component: acyclic → one evaluation; every cycle safe → monotone
   Kleene fixpoint to a fixed point; a `grow` edge on an otherwise unbounded
   cycle → compute the component's CARRIERS (the `ident`/`grow` upward closure
   of the growing sub-cycle) and read the two lanes THERE: some carrier
   `injective` means INFINITE (refuse; two laps exhibit the witness pair), no
   carrier `visible` means OPAQUE (freeze the carriers to a representative and
   solve every non-carrier member exactly), else REFUSE AT BINDING;
5. refuse ⟺ the deduplicated union over every accepting root holds more than
   one meaning.

The safety test is one line of graph theory: build the subgraph on
`ident ∪ grow` edges, take its SCCs, and a component is unsafe exactly when a
`grow` edge has both endpoints in one of them. The CARRIER set — which nodes
can actually hold the unbounded family — is the upward closure of those
growing sub-SCCs along the same `ident`/`grow` edges, and it is what the
`injective` and `visible` lanes are read on. Reading them on the whole
strongly connected component instead is wrong, and misclassifies exactly the
charts where a dropping or bounded consumer sits INSIDE the cycle's own
component (`mixed-scc-dropping-consumer`, `mixed-scc-bounded-consumer` below:
both are OPAQUE with a singleton root meaning, and both were misreported as
INFINITE / UNREPRESENTABLE by the first draft of this mechanism).

Complexity: SCC, the carrier closure, and both reachability lanes are
`O(V + E)`; the per-component fixpoint costs
`O(laps × Σ_n families(n) × Π_slot |set|)` operations and retains
`Σ_n |set(n)|` meanings. There is no global assignment enumeration, no cap, no
sampling, no hash, and no recursion-depth limit anywhere in the mechanism.

**Termination is proved by the classification, not by a lap count.** A safe
component's reachable value domain is finite: every cycle inside it either
preserves values exactly (all-`ident`) or passes through an operation whose
image is a declared finite domain. A monotone iteration over a finite lattice
terminates. The one property that argument rests on — that each lap's new set
CONTAINS the old one — is asserted every lap; a violation raises with words,
and it never fires (measured laps 4–16). No a-priori numeric bound is claimed,
because none was proved.

### The independent oracle

`bounded_depth_meanings` enumerates derivations directly: every family
assignment expanded per node, with a handle already on the DFS path re-entered
at most `depth` further times. It uses no SCC analysis, no classification, and
no `FastTree`. The depth ladder is walked to a ceiling and the answer must be
unchanged over the last `QUIET_DEPTHS = 3` steps.

**One quiet step is not enough, and the `ring` witness proves it**: its ladder
is `[1, 1, 1, 1, 2, 2, 2]` — unchanged from depth 0 to depth 3 and then
GROWING at depth 4. That is exactly the phenomenon that makes one lap wrong, so
it also had to be designed out of the oracle's own stabilization test.

For an INFINITE family the oracle cannot stabilize, and its evidence is instead
that the ladder is still rising over that same window.

### Witnesses

```text
cd zzz_current_work/260826-target-shaped-parse/proto && uv run python cyclic_meaning.py

cyclic-case	ring-depth3-one-lap-misses	kind=cyclic-bounded	differs=True	oracle_differs=True	oracle_stable_from=4/7	oracle_ladder=[1, 1, 1, 1, 2, 2, 2]	one_lap_differs=False  <-- ONE-LAP UNSOUND	one_lap_set=1	exact_set=2	components=3	cyclic_components=1	laps=9	ops=38	retained=10	max_live=10	early_ops=34	early_exit=True	alloc_bytes=2682072	cpu=0.001051
cyclic-case	ring-depth1-one-lap-agrees	kind=cyclic-bounded	differs=True	oracle_differs=True	oracle_stable_from=2/7	oracle_ladder=[1, 1, 2, 2, 2, 2, 2]	one_lap_differs=True	one_lap_set=2	exact_set=2	components=3	cyclic_components=1	laps=9	ops=38	retained=10	max_live=10	early_ops=34	early_exit=True	alloc_bytes=9906	cpu=0.000735
cyclic-case	ring-dropped-root	kind=cyclic-bounded	differs=False	oracle_differs=False	oracle_stable_from=0/7	oracle_ladder=[1, 1, 1, 1, 1, 1, 1]	one_lap_differs=False	one_lap_set=1	exact_set=1	components=3	cyclic_components=1	laps=9	ops=38	retained=9	max_live=9	early_ops=38	early_exit=False	alloc_bytes=11448	cpu=0.000716
cyclic-case	unit-cycle-growing	kind=cyclic-infinite	differs=True	oracle_differs=True	oracle_stable_from=4/5	oracle_ladder=[2, 2, 3, 3, 4]	one_lap_differs=True	one_lap_set=3	exact_set=3  (two-lap witnesses of an INFINITE family)	components=3	cyclic_components=1	laps=6	ops=14	retained=8	max_live=8	early_ops=2	early_exit=True	alloc_bytes=12547	cpu=0.000620
cyclic-case	unit-cycle-dropped-root	kind=cyclic-opaque	differs=False	oracle_differs=False	oracle_stable_from=0/7	oracle_ladder=[1, 1, 1, 1, 1, 1, 1]	one_lap_differs=False	one_lap_set=1	exact_set=1	components=3	cyclic_components=1	laps=5	ops=6	retained=4	max_live=4	early_ops=6	early_exit=False	alloc_bytes=11997	cpu=0.000586
cyclic-case	identity-cycle	kind=cyclic-bounded	differs=False	oracle_differs=False	oracle_stable_from=0/7	oracle_ladder=[1, 1, 1, 1, 1, 1, 1]	one_lap_differs=False	one_lap_set=1	exact_set=1	components=3	cyclic_components=1	laps=6	ops=11	retained=4	max_live=4	early_ops=11	early_exit=False	alloc_bytes=12047	cpu=0.000768
cyclic-case	two-key-cycle-bounded	kind=cyclic-bounded	differs=True	oracle_differs=True	oracle_stable_from=6/12	oracle_ladder=[1, 1, 1, 1, 1, 1, 2, 2, 2, 2, 2, 2]	one_lap_differs=False  <-- ONE-LAP UNSOUND	one_lap_set=1	exact_set=2	components=3	cyclic_components=1	laps=9	ops=52	retained=14	max_live=14	early_ops=48	early_exit=True	alloc_bytes=15243	cpu=0.000860
cyclic-case	two-key-cycle-growing	kind=cyclic-infinite	differs=True	oracle_differs=True	oracle_stable_from=3/4	oracle_ladder=[2, 2, 2, 3]	one_lap_differs=True	one_lap_set=3	exact_set=3  (two-lap witnesses of an INFINITE family)	components=3	cyclic_components=1	laps=6	ops=17	retained=10	max_live=10	early_ops=2	early_exit=True	alloc_bytes=15148	cpu=0.000717
cyclic-case	acyclic-twin-of-ring	kind=acyclic	differs=False	oracle_differs=False	oracle_stable_from=0/7	oracle_ladder=[1, 1, 1, 1, 1, 1, 1]	one_lap_differs=False	one_lap_set=1	exact_set=1	components=2	cyclic_components=0	laps=4	ops=4	retained=2	max_live=2	early_ops=4	early_exit=False	alloc_bytes=7493	cpu=0.000250
cyclic-case	nullable-star-collapsed	kind=acyclic	differs=False	oracle_differs=False	oracle_stable_from=0/7	oracle_ladder=[1, 1, 1, 1, 1, 1, 1]	one_lap_differs=False	one_lap_set=1	exact_set=1	components=8	cyclic_components=0	laps=16	ops=16	retained=8	max_live=8	early_ops=16	early_exit=False	alloc_bytes=20536	cpu=0.000841
cyclic-case	sibling-roots-over-cycle	kind=cyclic-infinite	differs=True	oracle_differs=True	oracle_stable_from=2/4	oracle_ladder=[4, 4, 6, 6]	one_lap_differs=True	one_lap_set=6	exact_set=6  (two-lap witnesses of an INFINITE family)	components=6	cyclic_components=1	laps=12	ops=32	retained=17	max_live=17	early_ops=2	early_exit=True	alloc_bytes=19399	cpu=0.000981
cyclic-case	mixed-scc-dropping-consumer	kind=cyclic-opaque	differs=False	oracle_differs=False	oracle_stable_from=0/7	oracle_ladder=[1, 1, 1, 1, 1, 1, 1]	one_lap_differs=False	one_lap_set=1	exact_set=1	components=3	cyclic_components=1	laps=7	ops=14	retained=6	max_live=6	early_ops=14	early_exit=False	alloc_bytes=16311	cpu=0.000954
cyclic-case	mixed-scc-bounded-consumer	kind=cyclic-opaque	differs=False	oracle_differs=False	oracle_stable_from=0/7	oracle_ladder=[1, 1, 1, 1, 1, 1, 1]	one_lap_differs=False	one_lap_set=1	exact_set=1	components=3	cyclic_components=1	laps=7	ops=14	retained=6	max_live=6	early_ops=14	early_exit=False	alloc_bytes=15466	cpu=0.000934
cyclic-case	sibling-roots-over-cycle-dropped	kind=cyclic-opaque	differs=False	oracle_differs=False	oracle_stable_from=0/7	oracle_ladder=[1, 1, 1, 1, 1, 1, 1]	one_lap_differs=False	one_lap_set=1	exact_set=1	components=6	cyclic_components=1	laps=11	ops=14	retained=7	max_live=7	early_ops=14	early_exit=False	alloc_bytes=17379	cpu=0.000963
binding-refusal	refused_at_binding=True	parse_refusal=cyclic meaning: a zero-width cycle builds an unbounded meaning family consumed by a bounded-image operation at 't'	the parse-time refusal is redundant: binding already declined
formulation-independence	renaming every rule preserves the refusal and its component census; respelling and group-hoisting the same formulation preserve the verdict; an ACYCLIC formulation of the same language binds — the refused property is the value-growing zero-width cycle itself, derived generically from the normalized grammar plus the declared operation classes, with no input, rule-name case, or privileged formulation
island-cycle	kind=cyclic-infinite	differs=True	seeds=1	leaf_options=2	oracle_differs=True	ops=28
nested-island-cycle	kind=cyclic-infinite	differs=True	seeds=1	leaf_options=2	oracle_ladder=[4, 4, 6, 6]	ops=28
deep-cycle	chars=2001	kind=cyclic-infinite	differs=True	early_exit=True	ops=8006	components=4004	cpu=0.096275	wall=0.096276
deep-cycle	chars=8001	kind=cyclic-infinite	differs=True	early_exit=True	ops=32006	components=16004	cpu=0.373310	wall=0.373343
deep-cycle	chars=32001	kind=cyclic-infinite	differs=True	early_exit=True	ops=128006	components=64004	cpu=1.523525	wall=1.523680
scaling	arm_points=1	kind=cyclic-infinite	chart_nodes=4	full_ops=14	full_retained=8	full_max_live=8	early_ops=2	early_exit=True	one_lap_assignments=2	one_lap_folds=3	full_cpu=0.000238	early_cpu=0.000160
scaling	arm_points=2	kind=cyclic-infinite	chart_nodes=8	full_ops=28	full_retained=15	full_max_live=15	early_ops=10	early_exit=True	one_lap_assignments=4	one_lap_folds=6	full_cpu=0.000361	early_cpu=0.000310
scaling	arm_points=3	kind=cyclic-infinite	chart_nodes=12	full_ops=48	full_retained=25	full_max_live=25	early_ops=18	early_exit=True	one_lap_assignments=8	one_lap_folds=12	full_cpu=0.000617	early_cpu=0.000522
scaling	arm_points=4	kind=cyclic-infinite	chart_nodes=16	full_ops=80	full_retained=41	full_max_live=41	early_ops=26	early_exit=True	one_lap_assignments=16	one_lap_folds=24	full_cpu=0.001003	early_cpu=0.000935
scaling	arm_points=6	kind=cyclic-infinite	chart_nodes=24	full_ops=240	full_retained=121	full_max_live=121	early_ops=42	early_exit=True	one_lap_assignments=64	one_lap_folds=96	full_cpu=0.003510	early_cpu=0.003339
invariant	a chart cycle is a zero-width SCC; the component terminates iff no grow edge lies on a cycle carrying no const/finite edge; terminating components are solved by a monotone Kleene fixpoint over exact deduplicated value sets, whose termination follows from the classification's finite value domain and whose monotonicity is asserted every lap; a surviving grow component is judged on its CARRIERS — the ident/grow upward closure of the growing sub-cycle, never the whole component — and is INFINITE under an injective path to an accepting root (refuse, two-lap witness pair), OPAQUE when no carrier is value-visible (carriers frozen to a representative, every non-carrier member still exact), and otherwise refused at BINDING with words; the one-lap relation is neither the exact set nor a sound refusal test
```

What the rows establish:

- **`ring-depth3-one-lap-misses`** is the headline: one lap reports ONE root
  meaning (no refusal); the exact mechanism and the independent oracle both
  find two and refuse. **`two-key-cycle-bounded`** repeats it on a three-rule
  cycle with two arm-choice keys.
- **`mixed-scc-dropping-consumer` / `mixed-scc-bounded-consumer`** are the
  carrier-scope witnesses: a `const` consumer sits inside the growing cycle's
  own strongly connected component, so the family never reaches the root. Both
  are OPAQUE with a singleton root meaning that MATCHES the oracle exactly —
  the non-carrier member of the component is still evaluated, so the answer is
  the real value, not a sentinel.
- **Positive ambiguity** (`ring-depth3`, `ring-depth1`, `unit-cycle-growing`,
  `two-key-*`, `sibling-roots-over-cycle`), **equal-meaning**
  (`identity-cycle`, `ring-dropped-root`), **dropped/constant**
  (`unit-cycle-dropped-root`, `sibling-roots-over-cycle-dropped` → opaque),
  **interacting packed families and island-leaf options** (`island-cycle`,
  `nested-island-cycle` — a cyclic outer chart above a delegated island and
  above a NESTED island), **sibling accepting roots** (both directions), and
  **deep stack-safe** (2,001 / 8,001 / 32,001 chars: 0.096275 → 0.373310 →
  1.523525 s CPU, that is 3.88× and 4.08× for 4× and 4× the input) are all
  covered.
- **Non-refusal is catchable, not just refusal**: five cases assert
  `differs=False` against the oracle, so an over-refusing mechanism would fail
  the suite.
- `nullable-star-collapsed` records a fact worth keeping: `list ::= gap*` with
  a nullable `gap` is the textbook infinite-ambiguity shape, and the engine's
  canonicalisation removes it before a chart is built. The binding-time
  analysis still flags the potential carrier cycle — the conservative
  direction — and the assertion in `_check_case` only requires
  chart-cycle ⇒ grammar-cycle, never the converse.

### The refusal, and how conservative it is

`grammar_verdict` runs the SAME classification on the normalized grammar alone
— nullability fixpoint, carrier edges (a child that can cover its parent's
whole span), SCCs, the `grow`-in-`ident ∪ grow`-SCC test, and the two
reachability lanes over the full child graph — so the refusal is decided at
BINDING, before any input. Its formulation-independence is demonstrated three
ways in-row: renaming every rule preserves both the refusal and the component
census; respelling and group-hoisting the same formulation preserve the
verdict; and an ACYCLIC formulation of the same language binds.

**The refusal is honestly conservative and its exact scope is stated.** The
refused witness (`root ::= s; s ::= t | "x"` with `atmost1` at the root, a
wrapping `s`, and a pass-through `t`) actually has a SINGLETON root meaning:
the unbounded family at `s` carries no marker atoms, so `atmost1` maps all of
it to `("verdict", "ok")`. The mechanism cannot see that without abstract
interpretation of the consumer's image, so it declines with words rather than
guessing. The class is precisely: *a value-growing zero-width cycle at least
one of whose CARRIERS is value-visible at an accepting root, with no carrier
reaching a root through an all-injective path.* `mixed-scc-bounded-consumer`
shows the neighbouring shape that does NOT refuse: there the bounded consumer
is `const` in the cycle slot, so no carrier is visible and the component is
OPAQUE. Extending exactness to the refused class is recorded below as a §8
production obligation, not as a closed result.

### The early exit, strengthened

P11 required a `sky` that was a MEET over all parent edges plus choice-freedom.
The correct condition for the refusal direction is weaker and per-edge: if node
`n` holds two meanings and SOME path from `n` to an accepting root is injective
in the carried slot, then fixing that path's families and varying only `n`'s
subderivation yields two root meanings. Choice-freedom is not needed. That is
the `injective` lane above, and it is what P11 recorded as the open "per-EDGE
`choice_free` granularity" residue. With it on, the infinite COMPONENT
itself costs nothing: `early_ops` in the `scaling` rows is 2, 10, 18, 26, 42
for 1, 2, 3, 4 and 6 arm points — linear in decision points and constant per
infinite component — against `one_lap_assignments` of `2^k` (64 at k=6). The
value 2 is the arm_points=1 row alone; the growth above it is the acyclic
sibling folds the early exit does not skip.

`proto/ambiguity_interaction.py` re-runs green with the mechanism wired in. Its
twelve-case chart differential uses the exhaustive `FastTree` enumeration only
on ACYCLIC charts, where it really is exhaustive, and the bounded-depth
derivation oracle on cyclic ones — the deep case borrowing its pad-20 twin's
verdict. Production `another_meaning` is no longer an oracle: it is printed
and pinned as a cross-check on shipped behaviour under default policies, which
removes the last circular-oracle residue P11 recorded.

---

## B — the complete tokenizer meaning and refusal relation

`proto/keyed_product_rows.py`. The P11 conclusions this round preserves: real
carrier costs, exact cold comparison for recursive Python mappings,
document-level normalization for `IrMap`, per-alternate ready-tokenizer
reconstruction rejected.

### The audit

Measured, not assumed (probe in the reproduction log):

| lane | `from_merges` (shipped) | prototype `from_indexes` |
|---|---|---|
| duplicate spelling | UNREACHABLE — `Vocab` is a `Mapping`, so Python last-wins resolved it first | refuses, first |
| duplicate ordinal | refuses, THIRD (`_build` derives `decode` last) | refuses, second |
| encode/decode bijection | derived, so vacuous | checked, third |
| duplicate merge dyad | refuses, FIRST (`_rank_map`, before `_build`) | refuses, fourth |
| contiguous ranks | vacuous — position IS rank | checked, fifth |
| pipeline specials ⊆ vocab | refuses, SECOND | refuses, sixth |
| merge REFERENCES (a dyad naming spellings absent from the vocab) | **NOT checked** | **NOT checked** |
| pipeline byte-fallback / unknown spellings | **NOT checked** | **NOT checked** |
| segmenter | declared by the builder | one-directional check: non-empty ranks require the ranked merge |
| ordinal domain | **NOT checked** — a negative id and a sparse id space both construct | **NOT checked** |

The refusal messages are reproduced exactly, including the fact that `IrMap`
sorts by `repr(key)` before indexing, so the key a refusal NAMES is the
repr-smallest duplicated one rather than the first in document order. The
normalized lane finds duplicates in `O(n)` with a set first and pays the
`repr` pass only when a duplicate actually exists.

Two consequences are recorded as findings rather than fixed here:

- **`from_merges` and `from_indexes` disagree on duplicate spellings** — the
  first silently last-wins, the second refuses. `from_indexes` also orders the
  vocabulary lanes ahead of the merge lane, so ten of the twenty tiny
  documents refuse with a different first verdict under the two tails. Both
  divergences are declared contract; the design already says `from_indexes`
  is the intended tail, and this is what adopting it changes.
- **Three lanes are validated by neither tail**: the ordinal domain (a
  negative id and a sparse id space both construct), merge REFERENCES (a dyad
  naming spellings absent from the vocabulary constructs), and the pipeline's
  byte-fallback table and unknown spelling. All three are exercised
  executably by `prove_unvalidated_lanes`; the 20-document family carries two
  dangling-merge-reference documents so the pair differential covers the lane
  even though both tails accept it. Adding any of these checks would narrow
  accepted tokenizers, so each is a planning question, listed below.

### The differential

```text
uv run python keyed_product_rows.py

exhaustive-pairs	tokenizer-merges	documents=20	pairs=400	both_refuse=144	both_refuse_equal=36	both_refuse_different_first_verdict=108	document-level verdict == constructed-result verdict on every pair
exhaustive-pairs	tokenizer-indexes	documents=20	pairs=400	both_refuse=169	both_refuse_equal=29	both_refuse_different_first_verdict=140	document-level verdict == constructed-result verdict on every pair
index-lane-coverage	validations=7	duplicate spelling, duplicate ordinal, bijection, duplicate dyad, rank contiguity, special membership, segmenter consistency — all refuse; the bijection, contiguity, and segmenter lanes are unreachable from a document and therefore carry no document-level twin
constructor-parity	identical_records=7	acceptance_divergences=['dup-spelling']	verdict_message_divergences=10	from_merges takes a Mapping, so a repeated spelling is resolved by Python last-wins before it; from_indexes streams pairs, refuses it, and orders the vocabulary lanes ahead of the merge lane — both divergences are declared contract, not accident
unvalidated-lanes	three lanes are unchecked by BOTH tails and are declared, not assumed: the ordinal domain (a negative id and a sparse id space both construct), merge REFERENCES (a dyad naming spellings absent from the vocabulary constructs), and the pipeline's byte-fallback table and unknown spelling (an unknown outside the vocabulary constructs); only pipeline SPECIALS are validated
```

The 20-document family covers valid documents (five distinct ones, including
reordered merges and an empty merge list), two dangling-merge-reference
documents, each single defect, and every crossed pair of defects — a duplicate dyad with a bad special, a bad special
with each of two different duplicate ordinals, a duplicate spelling with a bad
special, a duplicate spelling with a duplicate dyad. The reference relation is
the COMPLETE target result: two documents agree exactly when their constructed
results agree AND their ordered verdicts agree, so equal refusals count as
agreement and different first verdicts do not. The crossed pairs are what makes
this a test of PRECEDENCE rather than of the set of problems.

The alternate-kind rows at 128 and 8,192 real parsed catalog entries also
assert document-level == constructed verdict on every row, and now include
`ordinal`, `merge-dup`, and `special` kinds beside the P11 seven.

### The Qwen row

`tools/guarded.sh 8G 1500 -- uv run python proto/keyed_product_rows.py --mode qwen`,
alone; the reader setup is excluded from every structure row:

```text
qwen-reader-setup	cpu=112.996265	wall=17.252224
qwen-doc	entries=151669	merges=151387	pipeline_specials=26
python-last-wins	retained_bytes	carrier=42652984	normalized_view=10792591
irmap	retained_bytes	carrier=26677235	normalized_view=1213711
tokenizer-merges	retained_bytes	carrier=81413480	normalized_view=10792592
tokenizer-indexes	retained_bytes	carrier=102733787	normalized_view=1213832
```

Its 112.996265 s aggregate process CPU against 17.252224 s wall is the reader's
own in-process parallel parse, not a sequential duration.

| product | kind | cold build CPU | cold total CPU | fast-accept CPU | normalize CPU | doc-compare CPU | doc total CPU | equal |
|---|---|---:|---:|---:|---:|---:|---:|---|
| python-last-wins | equal | 0.040077 | 0.054422 | 0.000157 | 0.000002 | 0.000001 | 0.000160 | True (fast accept) |
| python-last-wins | value | 0.040544 | 0.046294 | 0.000056 | 0.050389 | 0.000375 | 0.050819 | False |
| python-last-wins | duplicate | 0.030018 | 0.033801 | 0.000157 | 0.201733 | 0.000417 | 0.202307 | False |
| irmap | equal | 0.170456 | 0.223138 | 0.000163 | 0.000002 | 0.000001 | 0.000166 | True (fast accept) |
| irmap | value | 0.279362 | 0.296487 | 0.000055 | 0.050609 | 0.000051 | 0.050715 | False |
| irmap | merge-dup | 0.279228 | 0.332966 | 0.000332 | 0.048800 | 0.000158 | 0.049291 | True (law-free lane) |
| tokenizer-merges | equal | 0.981177 | 1.212445 | 0.000165 | 0.000002 | 0.000001 | 0.000168 | True (fast accept) |
| tokenizer-merges | value | 1.042064 | 1.060697 | 0.000061 | 0.108524 | 0.001093 | 0.109678 | False |
| tokenizer-merges | ordinal | 1.010652 | 1.010656 | 0.000057 | 0.089850 | 0.000002 | 0.089909 | False (verdict delta) |
| tokenizer-merges | merge-dup | 0.875857 | 0.875860 | 0.000384 | 0.081842 | 0.000002 | 0.082228 | False (verdict delta) |
| tokenizer-merges | special | 0.887105 | 0.887109 | 0.000190 | 0.081352 | 0.000002 | 0.081544 | False (verdict delta) |
| tokenizer-merges | merges | 1.011353 | 1.200703 | 0.000170 | 0.099436 | 0.003437 | 0.103043 | False |
| tokenizer-merges | pipeline | 0.969929 | 1.198460 | 0.000169 | 0.100758 | 0.003497 | 0.104425 | False |
| tokenizer-indexes | equal | 1.299850 | 1.543143 | 0.000168 | 0.000002 | 0.000001 | 0.000172 | True (fast accept) |
| tokenizer-indexes | value | 1.126227 | 1.144913 | 0.000055 | 0.111909 | 0.000053 | 0.112016 | False |
| tokenizer-indexes | merge-dup | 0.117986 | 0.117989 | 0.000327 | 0.095351 | 0.000002 | 0.095679 | False (verdict delta) |

The table above samples sixteen of the forty measured rows; every endpoint the
bands below quote comes from the same run and is exhibited here in full:

| product | doc-lane min | doc-lane max | cold-total min | cold-total max |
|---|---:|---:|---:|---:|
| python-last-wins | 0.000160 (equal) | 0.202307 (duplicate) | 0.030321 (key) | 0.054422 (equal) |
| irmap | 0.000166 (equal) | 0.051107 (ordinal) | 0.196016 (ordinal) | 0.332966 (merge-dup) |
| tokenizer-merges | 0.000168 (equal) | 0.109678 (value) | 0.875860 (merge-dup) | 1.212445 (equal) |
| tokenizer-indexes | 0.000172 (equal) | 0.118661 (pipeline) | 0.058491 (duplicate) | 1.543143 (equal) |

The fast accept is timed as part of the document lane — reviewer 2's F4 —
and costs 0.000055–0.000384 s at Qwen scale, not the milliseconds an O(n)
walk would suggest: the alternate SHARES most of its objects with the base, so
tuple equality short-circuits on identity. The equal rows' ~0.00017 s totals
are therefore what the lane really pays.

Retained bytes at Qwen scale (tracemalloc): python carrier 42,652,984 /
normalized view 10,792,591; `IrMap` carrier 26,677,235 / view 1,213,711;
`tokenizer-merges` carrier 81,413,480 / view 10,792,592; `tokenizer-indexes`
carrier 102,733,787 / view 1,213,832. Chosen-result construction is measured
separately and is one cold build.

The `tokenizer-merges` normalized view is 10.8 MB because that product's law
keeps the vocab lane as `(spelling, ordinal)` pairs while `IrMap`'s law
collapses to sorted unique entries; both are the product's own law, and both
are far below their carriers.

**Adoption per law, unchanged from P11 and now on a complete relation.**
Recursive Python mapping — the cold carrier comparison stands (its document
lane runs to 0.202307 s against a cold total of at most 0.054422 s, so
normalization LOSES). `IrMap` and both tokenizer tails — document-level exact
comparison adopted (`IrMap` 0.000166–0.051107 s against 0.196016–0.332966 s
cold; the tokenizer tails 0.000168–0.118661 s against 0.058491–1.543143 s
cold).

**One row is honest about its margin.** `tokenizer-indexes / merge-dup` costs
0.117989 s cold against 0.095679 s document-level — 1.2×, not the ~10× the
rest of the tail shows. The `from_indexes` tail refuses a duplicate dyad
early, so cold refusal there is cheap. The document lane still wins every
printed row, but on the intended tail's early-refusal rows the margin
collapses to roughly 1.2×. Per-alternate ready-tokenizer reconstruction stays
rejected wherever it really builds one: 0.875860–1.543143 s and 81.4–102.7 MB
each.

---

## C — the flat structures and the honest control

`proto/ambiguity_rss.py`, modes `control` / `ambiguity` / `frames`, each row
alone under `tools/guarded.sh 8G 900`, sequential, collector enabled and
recorded per row. `DISTANT`, `DISTANT_TWO`, and the 2,000 / 8,000 / 32,000 pad
ladder are kept.

### Dictionary-free dense numbering

`FlatGraph` no longer holds a numbering dictionary. Production assigns a
completion its dense number when it creates the completion, so the number
lives in existing completion state; an external prototype has no such state, so
the build uses a TRANSIENT dict which is measured and released before the
retained structure is priced. Nothing in the returned structure references it,
and the retained-bytes row measures a fresh copy of exactly the six arrays.

```text
tools/guarded.sh 8G 900 -- uv run python proto/ambiguity_rss.py --pad 32000 --mode ambiguity

flat-index-detail	nodes=128007	parent_edges=128006	distinct_keys=320014	index_typecode=i	retained_array_bytes=7168340	retained_bytes_per_edge=56.0	retained_bytes_per_char=112.0	transient_build_peak_bytes=78271808	transient_bytes_per_char=1223.0	owner_edges=320014	numbering_cpu=0.077900	numbering_wall=0.077902	csr_build_cpu=5.071319	csr_build_wall=5.072186	laws=lookup+owner+parent-edge laws hold over the DEFAULT derivation's 128007 nodes and 128006 edges; tier 'i' refuses its own ceiling
two-key-parity	keys=2	cone_sizes=[3, 3]	shared_ancestors=2	distinct=True	own_indexes=2
cleanup	released oracle+flat (oracle_parents=128006)	rebuild_traced_bytes=7378948	post_release_residual_bytes=8288	peak RSS is monotonic and cannot show the release; the tracemalloc residual does
counts	baseline_folds=128007	replay_folds=3	replay_cpu=0.000310	replay_wall=0.000307	parity_checked_keys=1	verdict_differs=True
ambiguity-allocations	meaning_memo=1	dependency_index=3	overlay=2	seeds=0	trace_frames=0	two_key_parity_indexes=2	every one is constructed through an allocator; the parity witness owns a separate one so this census describes only the measured row
stage	chart	population=384007	traced_bytes=0	rss_kib=371792
stage	meaning-memo	population=128007	traced_bytes=19272688	rss_kib=403576
stage	dict-of-sets-index[REJECTED oracle]	population=448020	traced_bytes=122247680	rss_kib=574096
stage	flat-csr-index	population=576027	traced_bytes=7168924	rss_kib=682812
stage	alternate-overlay	population=3	traced_bytes=480	rss_kib=690276
totals	wall_seconds=27.170434	cpu_seconds=27.172129	peak_rss_kib=690276
```

| pad (chars) | nodes | tier | retained arrays | retained B/char | transient build peak | transient B/char | oracle | ratio |
|---:|---:|:--|---:|---:|---:|---:|---:|---:|
| 2,000 (4,001) | 8,007 | `H` | 392,300 | 98.1 | 4,802,900 | 1,200.4 | 7,563,812 | 19.3× |
| 8,000 (16,001) | 32,007 | `H` | 1,568,300 | 98.0 | 19,426,824 | 1,214.1 | 30,579,200 | 19.5× |
| 32,000 (64,001) | 128,007 | `i` | 7,168,340 | 112.0 | 78,271,808 | 1,223.0 | 122,247,680 | 17.1× |

The pad-32,000 row is the verbatim block above. The other two pads' rows come
from the same final pass, and their `flat-index-detail` lines are:

```text
flat-index-detail	nodes=8007	parent_edges=8006	distinct_keys=20014	index_typecode=H	retained_array_bytes=392300	retained_bytes_per_edge=49.0	retained_bytes_per_char=98.1	transient_build_peak_bytes=4802900	transient_bytes_per_char=1200.4	owner_edges=20014
flat-index-detail	nodes=32007	parent_edges=32006	distinct_keys=80014	index_typecode=H	retained_array_bytes=1568300	retained_bytes_per_edge=49.0	retained_bytes_per_char=98.0	transient_build_peak_bytes=19426824	transient_bytes_per_char=1214.1	owner_edges=80014
stage	dict-of-sets-index[REJECTED oracle]	population=28020	traced_bytes=7563812
stage	dict-of-sets-index[REJECTED oracle]	population=112020	traced_bytes=30579200
```

The retained figure is now the production-shaped one: **98.0–112.0 B/char**,
17–20× below the rejected dict-of-sets oracle, superseding P11's 293–316 B/char
(that number was the array cost plus a numbering dict which no longer exists).
The step from 98 to 112 B/char is the integer tier widening from `H` to `i` at
65,536 nodes, which the tier law makes explicit.

Laws asserted in-row by `_prove_index_laws`:

- **lookup** — `handles[i]` round-trips against the postorder for every node;
- **owner** — every key an actual completion owns is found by the bisect
  forward-star lookup, and an absent key returns `()`;
- **parent-edge** — every parent→child edge OF THE DEFAULT DERIVATION appears
  in the CSR, and `parent_offsets[n] == len(parent_edges) == that edge count`.
  Scope matters: the index, the dict-of-sets oracle, and this check all read
  `_resolved(kernel, handle, None)`, so the dirty-cone parity proves the two
  encode the same default-derivation graph, not chart completeness. A
  family-aware edge set — which `cyclic_meaning.build_chart` does build — is a
  production obligation, listed below;
- **dirty-cone** — parity with the dict-of-sets oracle at every scale, and on
  a two-key witness whose cones genuinely overlap (sizes `[3, 3]`, 2 shared
  ancestors, distinctness asserted);
- **integer-width / tier** — `tier_code` picks the narrowest of `B` / `H` / `i`
  by node population, the row asserts the chosen tier is the one the law
  selects, and that the tier REFUSES its own ceiling (writing `1 << 16` into
  an `H` array raises `OverflowError`); beyond `1 << 31` `tier_code` refuses
  with words rather than truncating;
- **cleanup** — rebuild and release leaves an 8,288-byte tracemalloc residual
  (peak RSS is monotonic and cannot show a release; stated in-row).

Build and replay are timed in CPU and wall separately, and the owner-edge count
is printed beside the distinct-key count (they coincide on this witness only
because every key is owned once): at pad 32,000, numbering 0.077900 s CPU /
0.077902 s wall, CSR build 5.071319 / 5.072186, alternate replay 0.000310 /
0.000307 over three fold bodies, 320,014 owner edges over 320,014 distinct
keys. The frames rows carry their own build CPU/wall.

Extrapolating the RETAINED structure to the 10,635,788-character Qwen witness
gives ~1.19 GB at the `i` tier, against P11's ~3.1 GB for the dict-bearing
shape. **That per-character rate is grammar-specific**: it embeds this
witness's chart density (2.0 nodes and 5.0 owner edges per character, from the
`item ::= [ab]` per-character filler), and a different grammar has different
ratios. What transfers is the tier — ~21.3 M nodes still fits `i` — and the
conclusion that the §12 bounded-input statement stands under either figure.

### The control cannot reach an ambiguity allocation

Every ambiguity-only structure — the retained meaning memo, both dependency
indexes, the alternate overlay, seed records, and trace frames — is constructed
through ONE `Structures` allocator. The control installs `RefusingStructures`,
whose every method raises. The row REACHING its final print is the evidence;
the zero counters are that same object's census, read afterwards.

```text
tools/guarded.sh 8G 900 -- uv run python proto/ambiguity_rss.py --pad 32000 --mode control

mode	control
pad	32000	chars	64001	gc	enabled
arm_points	0	root	root
ambiguity-allocations	allocator=RefusingStructures	meaning_memo=0	dependency_index=0	overlay=0	seeds=0	trace_frames=0	total=0	every one of these is constructed ONLY through the allocator above, whose control implementation raises — the row completed, so none ran
direct-product-state	fold_bodies=128007	peak_value_table_entries=128007	root_product_value_bytes=8787044	fold_peak_bytes=15358508	fold_cpu=8.296145	fold_wall=8.297320	residual_bytes_after_release=8544	ordinary direct product state, named as such: the value bytes are the root product the fold RETURNS, the peak additionally holds the transient value table the fold clears before returning, and neither is a post-parse meaning memo
totals	wall_seconds=10.893059	cpu_seconds=10.891598	peak_rss_kib=406024	chart_keys=384005
```

The other two pads' `direct-product-state` rows, from the same final pass:

```text
direct-product-state	fold_bodies=8007	peak_value_table_entries=8007	root_product_value_bytes=545600	fold_peak_bytes=842472	fold_cpu=0.482056	fold_wall=0.482087	residual_bytes_after_release=8544
direct-product-state	fold_bodies=32007	peak_value_table_entries=32007	root_product_value_bytes=2241600	fold_peak_bytes=3721152	fold_cpu=2.032118	fold_wall=2.032546	residual_bytes_after_release=8544
```

The executed unambiguous branch is `_direct_fold`, which uses a plain transient
value table, never an `Overlay`, and clears it before returning the root value.
Its cost is reported under its own name and in two parts: the root product the
fold RETURNS (545,600 / 2,241,600 / 8,787,044 bytes at the three pads) and the
window PEAK, which additionally holds the transient value table the fold clears
before returning (842,472 / 3,721,152 / 15,358,508 bytes). Both drop to an
8,544-byte residual after release, and the fold's own CPU/wall are printed
beside them. None of it is claimed as zero. What is claimed as zero is the
ambiguity machinery, and that claim is enforced by construction.

### Frames, corrected

```text
tools/guarded.sh 8G 900 -- uv run python proto/ambiguity_rss.py --mode frames
```

| depth | seeds | arity | child tuples | frames | traced bytes | B/completion | B/frame | build CPU |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 128 | 1 | 1 | 128 | 128 | 19757 | 154.4 | 154.4 | 0.000421 |
| 128 | 1 | 2 | 128 | 128 | 18461 | 144.2 | 144.2 | 0.000360 |
| 128 | 1 | 4 | 128 | 128 | 22749 | 177.7 | 177.7 | 0.000384 |
| 128 | 2 | 1 | 128 | 256 | 24994 | 195.3 | 97.6 | 0.000369 |
| 128 | 2 | 2 | 128 | 256 | 25002 | 195.3 | 97.7 | 0.000383 |
| 128 | 2 | 4 | 128 | 256 | 24938 | 194.8 | 97.4 | 0.000389 |
| 128 | 4 | 1 | 128 | 512 | 49908 | 389.9 | 97.5 | 0.000555 |
| 128 | 4 | 2 | 128 | 512 | 49924 | 390.0 | 97.5 | 0.000541 |
| 128 | 4 | 4 | 128 | 512 | 49796 | 389.0 | 97.3 | 0.000543 |
| 1024 | 1 | 1 | 1024 | 1024 | 149141 | 145.6 | 145.6 | 0.002699 |
| 1024 | 1 | 2 | 1024 | 1024 | 156285 | 152.6 | 152.6 | 0.002930 |
| 1024 | 1 | 4 | 1024 | 1024 | 173109 | 169.1 | 169.1 | 0.004916 |
| 1024 | 2 | 1 | 1024 | 2048 | 255834 | 249.8 | 124.9 | 0.003891 |
| 1024 | 2 | 2 | 1024 | 2048 | 263594 | 257.4 | 128.7 | 0.003568 |
| 1024 | 2 | 4 | 1024 | 2048 | 198186 | 193.5 | 96.8 | 0.003111 |
| 1024 | 4 | 1 | 1024 | 4096 | 396516 | 387.2 | 96.8 | 0.004403 |
| 1024 | 4 | 2 | 1024 | 4096 | 396420 | 387.1 | 96.8 | 0.004276 |
| 1024 | 4 | 4 | 1024 | 4096 | 396292 | 387.0 | 96.8 | 0.004282 |
| 8192 | 1 | 1 | 8192 | 8192 | 1189525 | 145.2 | 145.2 | 0.022303 |
| 8192 | 1 | 2 | 8192 | 8192 | 1246845 | 152.2 | 152.2 | 0.023322 |
| 8192 | 1 | 4 | 8192 | 8192 | 1361725 | 166.2 | 166.2 | 0.023436 |
| 8192 | 2 | 1 | 8192 | 16384 | 1923410 | 234.8 | 117.4 | 0.026406 |
| 8192 | 2 | 2 | 8192 | 16384 | 1981546 | 241.9 | 120.9 | 0.031980 |
| 8192 | 2 | 4 | 8192 | 16384 | 2231850 | 272.4 | 136.2 | 0.030549 |
| 8192 | 4 | 1 | 8192 | 32768 | 3611876 | 440.9 | 110.2 | 0.041178 |
| 8192 | 4 | 2 | 8192 | 32768 | 3549508 | 433.3 | 108.3 | 0.039695 |
| 8192 | 4 | 4 | 8192 | 32768 | 3656860 | 446.4 | 111.6 | 0.045989 |

All 27 rows, printed in full so the band's endpoints are exhibited rather
than quoted. One child tuple is allocated
per completed ancestor and shared only among the seeds crossing that
completion, matching `_record_frames`; the dirty slot varies with the seed
index modulo arity, and is printed per row. Rule names and child meanings come
from pools built outside the window, as production shares interned names and
already-built child meanings. Seed records are real allocations counted by the
same allocator (`counts.frame == frames and counts.seed == seeds` asserted).

**The P11 96–98 B/frame figure is superseded and not carried forward**: it
shared one child tuple across the entire ancestor depth, which understated the
per-completion cost by 1.5–1.8×. The honest per-completion figure is
144.2–446.4 B over the 27 rows and 144.2–177.7 B at one seed, rising with the
number of simultaneously live seeds because each seed adds a frame record
while the child tuple stays shared.

The ambiguous row still asserts the correct target verdict
(`verdict_differs=True`) and exact dirty-cone parity against the independent
dict-of-sets oracle at every scale.

---

## D — custom binding through the real pool and paid loop

`proto/custom_class_target.py`. Everything P11 established is preserved: one
immutable constructor class symbol plus inert field/path data, a homogeneous
result-free cache, identity-plus-pin keys, no class inspection, and a
result-typed bound view retaining derived grammar data and tables. No
factory/callback field, import-path lookup, mutable rebinding registry, custom
executor, or second parse API was added.

```text
uv run python custom_class_target.py

shapes	frozen/validating/generic/unhashable-metaclass classes bind and run; value-keying is impossible for the unhashable one (shown), identity+pin keying carries it
traffic	completions=9	walk_constructor_calls=0	root_constructor_calls=1	the same walk finishes under a constructor that raises on any call, and neither the walk nor the extraction names `constructor` or `declaration` in its code object
executable-lifetime	source artefact collected, registry entry released, and the retained bound view still parsed and constructed successfully
no-traffic-on-refusal	three malformed documents and one genuinely ambiguous document all refuse with constructor_calls=0; the ambiguity refusal happens before any result exists, so no unchosen result is ever constructed
identity-semantics	equal declarations bind separately by design; id-reuse safety is the DOUBLE identity check — the strong pin keeps the declaration alive (its id cannot recycle while the entry lives) and every lookup re-validates `pin is declaration` AND `grammar() is grammar`
shared-tables-retention	equal_distinct_declarations=50 entries_held=50 table_derivations=1 shared_tables=1; all fifty entries (and pins) died with the artefact — retention is artefact-bounded, and the caller idiom is one held declaration object per target
long-document-after-death	doc_chars=6397 parsed over tables recompiled from the retained derived AST; no CompiledGrammar reachable from the bound view (checked over the data-edge gc referent closure)
eviction	release + rebind recomputed an equivalent binding; both views parse to equal results
concurrent-cold-bind	8 threads, 1 build, shared binding
cold-root-failure	validating constructor and class/field mismatch fail at root finalization; declaration-data defects refuse at binding with words
pool-lifecycle	workers=4	documents=32	beyond_tier_chars=6397	source artefact collected and registry entry released BEFORE the first map; the pool's own work binding was the sole owner, and closing the pool dropped the bound product
pool-concurrency	2 concurrent maps x 16 documents through one retained pool agree with the sequential map over the same documents
pool-failure-and-eviction	a failing constructor surfaces as its own exception through ParsePool.map; release + rebind recomputes an equivalent binding whose pooled results are identical; a closed pool refuses work
paid-loop-neutrality	document_chars=6397	rounds=8 x 4 parses	control_min_cpu=0.431578	custom_min_cpu=0.432181	cpu_ratio=1.001399	control_min_wall=0.431630	custom_min_wall=0.432514	same tables, same kernel, same completion walk; the arms differ only in the root finalizer, and the order alternates every round
bound-run	cpu=0.000595	wall=0.000596
PASS: custom classes run through retained derived tables with no class inspection, an identity+pin registry, and cold-root-only constructor traffic
```

### The pool lifecycle

`_pool_owner` binds the target, hands `bound.run` to the ordinary
`ParsePool(work, cores=4)` seam, then deletes the local binding and the source
artefact. Before the first map it asserts: the source weakref is `None`, the
binding-registry entry count has DROPPED by one, and a weakref to the bound
product is still alive — so the pool's own work binding is the sole owner. A
local variable and a registry entry are both provably out of the picture.

Then 32 distinct documents plus one 6,397-character beyond-tier document are
parsed and constructed through that retained pool on the free-threaded
interpreter. Closing the pool and dropping it collects the bound product
(weakref becomes `None`), which is the cleanup proof.

Also covered: two CONCURRENT maps through one retained pool agreeing with the
sequential map over the same documents; a validating constructor's own
`FieldValidationError` surfacing through `ParsePool.map`; registry release plus
rebind giving pooled results identical to the pre-eviction pool; and a closed
pool refusing further work with `RuntimeError`.

### Constructor traffic, measured

The P11 `invocations` list is gone. `BoundRecord.run` is split into `walk`
(recognition + completion; the frequent path) and the root finalization, and
`walk` refuses an ambiguous chart BEFORE building a derivation, so no unchosen
result can exist. Traffic is established two independent ways:

- an **external counter** incremented inside a real consumer class's own
  `__post_init__`, which nothing in the target machinery can bypass: 0 calls
  across the completion walk of a 9-completion document, 1 at the root;
- the **same walk driven through a declaration whose constructor raises on any
  call** — it completes and returns identical values, so the walk demonstrably
  never reaches it.

The structural claim is checked too: neither `_extract.__code__.co_names` nor
`BoundRecord.walk.__code__.co_names` contains `constructor` or `declaration`,
so the frequent path holds no reference and performs no dynamic dispatch to
the consumer class.

`prove_no_traffic_on_refusal` closes the remaining `PROMPT_12.md` §D cases
with the SAME external counter: three malformed documents (truncated,
unparseable, empty) and one genuinely ambiguous document all refuse with
`constructor_calls=0`. The ambiguous witness uses `doc ::= entry entry` rather
than `entry+` because `ambiguity_points` does not surface an arm choice under
a quantifier chain — the completeness of production's refusal PREDICATE is
§8's question, not this gate's, and it is recorded below.

### Paid-loop neutrality

The control is `DefaultProduct`: the same tables, the same kernel, the same
`FastTree` build, and the same `_extract` completion walk, finalized by the
engine's own default codomain instead of a consumer class. Eight alternating
rounds of four parses each over a 6,397-character document, minimum taken:
**0.431578 s control vs 0.432181 s custom minimum process CPU (ratio
1.001399)**, wall 0.431630 vs 0.432514 — the figures in the verbatim block
above, which is the run this report quotes throughout. Across the runs of this
row taken during the round the ratio moved between 0.995 and 1.008; the sign
is not stable, which is what "the arms differ only in the root finalizer, and
that finalizer runs once per document" predicts, and it is why the range is
stated beside the row rather than a single number being read as a result. This is a paid-loop neutrality check on one real engine
shape, not a Qwen benchmark, and it is not evidence about the production
completion path, which does not exist yet.

---

## Gate classification

### Mechanism gates conclusively closed

- **Cyclic ambiguity (A).** The exact terminating decision mechanism, its
  linear-time classification, its carrier-scoped trichotomy, its asserted
  monotonicity invariant, its complexity statement in chart nodes/edges and
  operation-state cardinality, its binding-time twin, and its
  formulation-independence. Differentialled against an independent
  bounded-depth derivation oracle on fourteen chart witnesses plus two island
  witnesses, with positives, equal-meaning negatives, dropped/constant
  negatives, mixed-component consumers, nested interaction, sibling accepting
  roots, and deep stack-safe rows. Two executable witnesses show one lap
  giving the WRONG refusal verdict. The exact replacement contract for
  `another_meaning` is recorded below.
- **Tokenizer refusal relation (B).** Every constructor input and every
  ordered validation outcome for both the shipped `from_merges` tail and the
  intended `from_indexes` tail, differentialled over 800 ordered document pairs
  (400 per tail) including equal and differing refusals, and over ten alternate
  kinds at three scales including the real Qwen fixture. The document-level representation is
  proved exact and priced.
- **Flat ambiguity structures (C).** Dictionary-free retained numbering at
  98–112 B/char with transient build cost separated, all seven laws asserted,
  a control that cannot reach an ambiguity allocation, and a corrected frame
  row with one child tuple per completion.
- **Custom binding through the pool (D).** Real `ParsePool` retention past
  source and registry death, concurrent maps, failure, eviction, tier escape,
  shutdown cleanup, measured constructor traffic, and a paid-loop neutrality
  row against the default control through the same engine shape.

### Mechanisms still requiring production integration measurement

- the cyclic classification wired into the real lowered operation table (the
  prototype classifies a policy-name algebra; production classifies
  `PassOp` / `ConstantOp` / `ValidateOp` / `RecordOp` / … directly), and its
  binding-time twin run over real reducers;
- **exactness for the one refused cyclic class** — a value-growing zero-width
  cycle consumed by a bounded-image operation. The refusal is conservative and
  provably so; extending it needs abstract interpretation of the consumer's
  declared image and is not attempted here;
- dictionary-free dense numbering assigned from real completion state (this
  round proves the RETAINED shape and prices the transient a prototype needs;
  production should have no transient at all);
- document-level meaning lanes wired into the streaming tokenizer
  accumulators, and the `from_indexes` tail itself;
- the exact-set lanes in `ParseState`, and the paid-loop cost of the
  classification on a production chart (§3/§8);
- **family-aware dependency edges.** The flat index, its dict-of-sets oracle,
  and the law check all read the DEFAULT family, so their parity proves they
  encode the same default-derivation graph. `cyclic_meaning.build_chart` shows
  the family-aware shape; production must build the index over it;
- **the completeness of the ambiguity refusal PREDICATE.** `ambiguity_points`
  does not surface an arm choice under a quantifier chain (witnessed while
  building §D's ambiguous document). That is §8's `another_meaning` rewiring,
  not this round's gate, but it is now a recorded observation rather than an
  assumption;
- custom-target neutrality on the production completion path (§4/§6); this
  round's row uses the prototype's own walk.

### User decisions still open

- **Resolver scope** remains the user's call and is untouched by this round;
  `proto/resolver_pair.py` was not modified and re-runs green. `TODO.md` §8
  still carries `DECISION REQUIRED BEFORE §8 — RESOLVER SCOPE`, and this report
  does not rule it.
- **Which of the three unvalidated tokenizer lanes `from_indexes` should
  check** — the ordinal domain, merge references into the vocabulary, and the
  pipeline's byte-fallback table and unknown spelling. All three are
  executably demonstrated to be unchecked by both tails; adding any would
  narrow accepted tokenizers relative to today's reader, and none is decided
  here.
- The standing bugfix-related parse-regression approval remains user-only.

### Failed candidates that stay rejected

- **the `2^k` global-assignment cycle fallback** — now rejected on CORRECTNESS
  as well as cost: `ring-depth3` and `two-key-cycle-bounded` show the one-lap
  relation it computes returning the wrong refusal verdict;
- **one lap as any part of the relation** — its unrolling depth is bounded by
  the chart's arm-choice key count, a chart artefact;
- **the P11 `sky` meet plus choice-freedom as the early-exit condition** —
  superseded by the weaker and correct per-edge injective-path condition,
  which is where `cyclic_meaning` refuses early. `ambiguity_interaction`'s
  acyclic set-fold lane still prints and uses the sky meet: it is strictly
  more conservative, so it can only forgo an early exit, never cause one, and
  it is retained there as the P11 evidence it was. "Superseded" means the
  per-edge rule is the one production takes, not that the meet is unsound;
- **reading the reachability lanes on the whole strongly connected component**
  — this round's own first draft did that, and `mixed-scc-dropping-consumer`
  and `mixed-scc-bounded-consumer` are the witnesses that killed it;
- **an a-priori numeric lap bound for the fixpoint** — nothing proved it, so
  the loop asserts monotonicity instead;
- **production `another_meaning` as a differential oracle on a cyclic chart** —
  the deep case now borrows the bounded-depth oracle's verdict from its
  pad-20 twin;
- unconditional Cartesian propagation, pair-carrying, the dict-of-sets index,
  the incremental treap and ordered trees for keyed laws, the plain-dict cold
  row as a tokenizer proxy, entry-lane-only normalization, value-keyed
  declaration caches for arbitrary classes — all as before;
- **the P11 control row** (it constructed a document-sized `Overlay`) and
  **the P11 frame row** (one child tuple for the whole depth): both superseded
  by the rows above.

---

## Recommended planning-document edits (NOT applied)

1. `DESIGN.md` §State safety and §Earley-and-islands, and `goal.md`
   §State safety: replace "Cyclic charts do not use the prototype's unbounded
   `2^k` one-lap enumeration; their exact terminating representation must be
   settled before §8 implementation begins" with the settled mechanism — the
   zero-width-SCC classification, the `grow`-edge safety test, the Kleene
   fixpoint with an asserted lap bound, the INFINITE / OPAQUE / binding-refusal
   trichotomy, and the statement that the one-lap relation is neither the
   exact set nor a sound refusal test.
2. `DESIGN.md` §State safety: replace the P11 certificate ("choice-free
   continuation which is injective in retained children or constant in dropped
   children", meet over all parent edges) with the corrected per-EDGE rule: a
   node may refuse early as soon as its exact local set exceeds one AND some
   path from it to an accepting root is injective in the carried slot.
   Choice-freedom is not required, and this closes the recorded per-edge
   granularity residue.
3. `TODO.md` §8 `PLANNING REQUIRED BEFORE §8 — CYCLIC INTERACTION`: mark
   CLOSED with the mechanism above, and add as exit gates the witnesses
   `ring-depth3-one-lap-misses`, `two-key-cycle-bounded`, `identity-cycle`,
   `unit-cycle-dropped-root`, `sibling-roots-over-cycle` (both directions),
   `island-cycle`, `nested-island-cycle`, and the deep-cycle ladder. Record the
   ONE refused class and that its refusal is conservative and binding-time.
4. `TODO.md` §8 `PLANNING REQUIRED AT §8 EXIT — TOKENIZER VALIDATION
   RELATION`: mark CLOSED with the measured `from_merges` precedence
   (duplicate merge dyad < missing special < duplicate ordinal), the
   seven-lane `from_indexes` order, the exhaustive-pair differential, and the
   Qwen document-level timings. Add the two declared divergences and the THREE
   unvalidated lanes (ordinal domain, merge references, pipeline
   byte-fallback/unknown) as new `DECISION REQUIRED` items rather than silent
   behaviour.
5. `TODO.md` §12 `PLANNING REQUIRED BEFORE §12`: mark the control, frame, and
   flat-index parts CLOSED. Quote the retained 98–112 B/char with its integer
   tier, the transient build peak as a prototype-only cost, the corrected
   144.2–446.4 B per completion frame figure, and the allocator-refusal control
   protocol. Delete the 112 B/char-vs-293 B/char split — there is now one
   retained figure.
6. `TODO.md` §6 `PLANNING REQUIRED AT §6 EXIT` (pool): mark CLOSED with the
   `ParsePool` lifecycle, the concurrent-map, failure, eviction and shutdown
   rows, the two-way constructor-traffic proof, and the measured paid-loop
   ratio of 1.001 — noting that the ratio's sign is unstable across runs
   (0.995–1.008), that the neutrality row uses the prototype's walk, and that
   the production completion path is still §4/§6 work.
7. `INDEX.md`: add `proto/cyclic_meaning.py` to the prototype inventory, update
   the `ambiguity_interaction.py` / `ambiguity_rss.py` / `keyed_product_rows.py`
   / `custom_class_target.py` one-liners, and add `PROTOTYPE_12.md` to the
   authoritative packet.

---

## Verification

```text
uv run ruff format --check <the five files>        # 5 files already formatted
uv run ruff check  <the five files>                # All checks passed!
uv run pyright     <the five files>                # 0 errors, 0 warnings, 0 informations
grep -rnE "type: *ignore|noqa|pylint: *disable|\beval\(|\bexec\(|: Any|-> Any|Any\]|: object\b|-> object\b|object\]|cast\(" <the five files>
    # no hits (grep exit 1)
git diff --stat -- src tests                       # empty
git status --porcelain                             # exactly the four tracked round files
                                                   # (cyclic_meaning.py is new and ignored by .gitignore:45)

uv run python proto/cyclic_meaning.py                        # exit 0 (verbatim in §A)
uv run python proto/ambiguity_interaction.py                 # exit 0
uv run python proto/keyed_product_rows.py                    # exit 0 (§B generic rows)
uv run python proto/custom_class_target.py                   # exit 0 (verbatim in §D)
uv run python proto/resolver_pair.py                         # exit 0 (unchanged; regression)
uv run python proto/island_alternate_seed.py                 # exit 0 (unchanged; regression)
tools/guarded.sh 8G 1500 -- uv run python proto/keyed_product_rows.py --mode qwen       # exit 0
tools/guarded.sh 8G 900 -- uv run python proto/ambiguity_rss.py --pad {2000,8000,32000} --mode {control,ambiguity}
                                                             # all exit 0
tools/guarded.sh 8G 900 -- uv run python proto/ambiguity_rss.py --mode frames           # exit 0
```

The `from_merges` precedence probe, run before the relation was written:

```text
valid                  OK 2 2 1 IrRankedMerge
dup-ordinal            UnsupportedConstructError IrMap: duplicate key IrChr(0)
dup-merge              UnsupportedConstructError IrMap: duplicate key IrTuple(IrStr('a'), IrStr('b'))
dup-merge+dup-ordinal  UnsupportedConstructError IrMap: duplicate key IrTuple(IrStr('a'), IrStr('b'))
bad-special            UnsupportedConstructError tokenizer: special 'zz' is not in the vocab
bad-special+dup-ordinal UnsupportedConstructError tokenizer: special 'zz' is not in the vocab
bad-special+dup-merge  UnsupportedConstructError IrMap: duplicate key IrTuple(IrStr('a'), IrStr('b'))
empty-merges           OK 2 2 0 IrRankedMerge
```

Two prototype-only affordances are declared rather than hidden:
`BoundRecord.__slots__` gained `"__weakref__"` so the pool-retention proof can
watch the object's lifetime from outside (no field, no behaviour), and
`keyed_product_rows.CONSTRUCT_TOKENIZER` names `IrTokenizer`'s own positional
constructor under a concrete callable type so the call site is typed without a
cast (the shipped `_build` reaches the same constructor).

Every command above was re-run after each round of reviewer fixes; the numbers
quoted throughout come from the last such pass, and every prose figure appears
in one of this report's own verbatim blocks or tables.

---

## Internal adversarial review record

`PROMPT_12.md` §E mandates three sequential internal adversarial reviewers, at
the strongest reasoning model available, read-only, with no benchmark or agent
running concurrently. Each was called through the `Agent` tool as
`general-purpose`, one at a time, with nothing else running. Because §F makes
readiness conditional on the FINAL fresh reviewer returning READY, and the
third returned NOT READY, a fourth fresh closure audit ran after its fixes.

All four returned NOT READY. Every finding — one semantic blocker, two closure
blockers, and twenty-one lesser — is fixed and the affected evidence
re-measured.

**The §F review gate is NOT met, and this report does not claim it is.** §F
makes the round fold-ready only when a final fresh reviewer returns READY, and
no reviewer has returned READY on the current text. Reviewer 4's two blockers
were fixed after it reported, so a fifth fresh audit would be the remaining
step; the user closed the round before it ran (2026-08-30, explicit
instruction: no further subagents). What that leaves outstanding is exactly
one thing — an independent confirmation that reviewer 4's two report-text
corrections landed — and nothing about a mechanism, a measurement, or an
adoption ruling. **Whoever picks this up runs that audit first.**

### Reviewer 1 — adversarial semantic review

Prompt, verbatim as `PROMPT_12.md` §E specifies, plus a context paragraph
naming the repository, the effort directory, the five changed prototypes, and
the read-only boundary:

```text
Read AGENTS.md, docs/STYLE.md, the target-shaped-parse INDEX/context/goal/
DESIGN/TODO, PROMPT_12.md, reports/PROTOTYPE_11.md, every prototype changed by
Prototype 12, and the complete draft reports/PROTOTYPE_12.md. Adversarially
review correctness only. Try to falsify the cyclic ambiguity invariant and
termination argument, tokenizer success/refusal equivalence and verdict order,
flat-index parity/lifetime claims, and custom pool lifecycle/type guarantees.
Look for circular or shared oracles, bounded witnesses presented as proofs,
unstated refusal/language changes, arbitrary-depth or Cartesian explosions,
and claims broader than executable evidence. Do not edit or benchmark. Return
findings ordered by severity with exact file:line evidence; say READY only if
there is no substantive correctness or planning blocker. Ignore prose nits.
```

**Verdict: NOT READY.** Eight findings, all fixed and re-measured:

| # | severity | finding | fix |
|---|---|---|---|
| 1 | BLOCKER | the INFINITE/OPAQUE/UNREPRESENTABLE trichotomy read the `injective`/`visible` lanes over the WHOLE strongly connected component instead of over the nodes that carry the growing family. Falsified executably: `root ::= e; e ::= a; a ::= e \| b \| "x"; b ::= a` with a dropping `e` has a singleton root meaning, and the mechanism returned `cyclic-infinite differs=True` (early lane) or raised its own injectivity-law `CyclicRefusal` (full lane); the `atmost1` variant refused as UNREPRESENTABLE although nothing reached a root | `_carriers` computes the `ident`/`grow` upward closure of the growing sub-SCCs and both lanes are read there, in the chart mechanism AND its binding-time twin. `_solve_component` now freezes only the CARRIERS on an OPAQUE component and solves every non-carrier member exactly, so the OPAQUE lane matches the oracle in VALUE, not just in verdict. Both reviewer shapes are added as cases `mixed-scc-dropping-consumer` and `mixed-scc-bounded-consumer` |
| 2 | MEDIUM | the "every ambiguity structure goes through one allocator" claim was false in the file: `Overlay({})` and the two-key-parity indexes were built directly, so the printed census under-counted | the baseline scratch overlay is routed through the allocator (the census now reads `overlay=2`), and `_two_key_parity` carries its OWN allocator and reports `own_indexes=2`, so the main row's census describes only the main row |
| 3 | MEDIUM | the lap bound `2 + \|S\| × D(S)` was called "proved" with no proof | the numeric bound is deleted. Termination is argued from the classification's finite value domain, and the loop asserts the MONOTONICITY that argument rests on; a violation raises with words |
| 4 | MEDIUM | the "every real parent→child edge" law is scoped to the default derivation, and the oracle shares that edge source | the law string, the docstring, and the report all say DEFAULT derivation; family-aware edge coverage is recorded as a production obligation |
| 5 | LOW | the bounded-depth oracle shares the chart-reading layer (`selected_resolved`, `local_choice_keys`) with the mechanism | recorded in the self-audit below |
| 6 | LOW | `deep-cycle-pad2000` was held against production `another_meaning`, which `PROMPT_12.md` §A forbids as an oracle | the deep case now borrows the bounded-depth oracle's verdict from `deep-cycle-pad20` — the same grammar and policies at a size the oracle handles — and the deep row proves only depth and stack safety. `another_meaning` is no longer an oracle anywhere: it remains a printed and pinned CROSS-CHECK on today's shipped behaviour (`shipped_another_meaning=…`), so a change in shipped behaviour fails the suite rather than passing unnoticed, while the truth source is the declared verdict plus the oracle beside it |
| 7 | LOW | the merge-REFERENCE lane (a dyad naming spellings absent from the vocabulary) was neither differentialled nor declared | two dangling-merge-reference documents added to the family (now 20 documents, 400 pairs each) and the lane added to `prove_unvalidated_lanes` and to the §B audit table |
| 8 | LOW | ambiguity-refusal and unchosen-result constructor traffic were unexercised | `BoundRecord.walk` now refuses an ambiguous chart before building a derivation, and `prove_no_traffic_on_refusal` runs three malformed documents and one genuinely ambiguous document under the external counter: zero constructor calls |

Reviewer 1 also confirmed what survived attack: the gate-B exhaustive-pair
differential and measured precedence, the gate-D pool lifecycle and
constructor-traffic proof, the two one-lap-unsound witnesses, the acyclic
value-set lane, the per-node early exit, the least-fixpoint exactness argument
for bounded components, the frames-row one-child-tuple-per-completion shape,
and the retained/transient byte separation.

Every affected witness and static check was re-run after the fixes (§Verification).

### Reviewer 2 — adversarial performance review

Prompt, verbatim as `PROMPT_12.md` §E specifies, plus the same context
paragraph and an instruction to deliver the review as a file under `/tmp`:

```text
Read AGENTS.md, docs/STYLE.md, the target-shaped-parse INDEX/context/goal/
DESIGN/TODO, PROMPT_12.md, reports/PROTOTYPE_11.md, every prototype changed by
Prototype 12, and the revised reports/PROTOTYPE_12.md. Adversarially review the
representation and performance evidence only. Check that the control cannot
reach ambiguity allocations, dense-numbering transient and retained memory are
separated, real frame child tuples and seeds are allocated, tracemalloc/RSS/GC
claims are honest, custom paid-loop comparison uses the same engine shape, and
no overlapping agent or benchmark activity contaminated timings. Recompute
reported arithmetic and challenge every extrapolation. Do not edit or run
benchmarks. Return findings ordered by severity with exact file:line evidence;
say READY only if no substantive performance-evidence blocker remains. Ignore
formatting and prose nits.
```

**Verdict: NOT READY.** Eight findings, all fixed and re-measured:

| # | severity | finding | fix |
|---|---|---|---|
| 1 | MEDIUM-HIGH | the prompt requires build and replay CPU AND wall for the flat-structure row; only CPU was printed, the replay loop carried no timing at all, the frames rows carried none, and the owner-edge count was never printed as such | `_flat_graph` returns numbering and CSR wall beside CPU, the alternate replay loop is timed in both, `owner_edges` is printed beside `distinct_keys`, and every frames row carries build CPU/wall |
| 2 | MEDIUM | "`early_ops=2` at every scale" is contradicted by the table it cites (2, 10, 18, 26, 42) | restated as what the data shows: linear in decision points, constant per infinite component; the 2 is the arm_points=1 row alone |
| 3 | MEDIUM | five quoted numbers were stale against the report's own "all numbers from the final pass" contract: the deep-cycle CPU triple, "648 ordered pairs" (pre-reviewer-1 18-document family), "eighteen tiny documents", the §B band endpoints, and planning edit 6 quoting the favourable 0.995 endpoint of an unstable ratio | every figure re-derived from the final pass; the pair count is 800 (400 per tail), the family is 20 documents, the bands are the printed extremes, and the planning edit quotes the measured 1.003 with its 0.995–1.008 instability |
| 4 | MEDIUM | the fast-accept equality ran between two timed windows, so the "equal" document-lane totals excluded it | the fast accept is its own timed lane inside the document total. It measures 0.000055–0.000384 s at Qwen scale — the alternate shares most of its objects, so tuple equality short-circuits on identity — so the equal rows move from ~0.000004 s to ~0.00017 s and the ruling is unchanged |
| 5 | LOW | `tokenizer-indexes / merge-dup` wins by 1.2×, not the ~10× the narrative band suggests, and this was not called out | stated explicitly: on the intended tail's early-refusal rows the margin collapses to roughly 1.2× |
| 6 | LOW | the control's `product_and_transient_table_bytes` discarded the tracemalloc peak, so the label overstated what the number held | split into `root_product_value_bytes` (what the fold returns) and `fold_peak_bytes` (which additionally holds the transient table), with the fold's own CPU/wall beside them |
| 7 | LOW | the ~1.19 GB Qwen extrapolation transfers the `DISTANT` witness's chart density | the report now states the density it embeds (2.0 nodes and 5.0 owner edges per character) and that only the tier conclusion transfers |
| 8 | LOW | the frames band's endpoints appeared in none of the sampled corner rows | all 27 rows are printed; the corrected band is 144.2–446.4 B per completion (the 464.9 endpoint was a sampling artefact of the earlier pass) |

Reviewer 2 independently rederived and confirmed: every retained-array byte
figure and the H→i tier step, the oracle ratios and transient rates, the
exhaustive-pair counts from the refusal-class partition, every frames-row
arithmetic, the deep-cycle linearity, the paid-loop ratio, the
transient/retained separation, and that no timing row shows a
CPU-versus-wall divergence indicating contamination. It also recorded, without
severity, that the neutrality document exceeds `BIND_TIER_CHARS` so both arms
pay an identical cold `compile_tables` — honest, and nearly tautological by
construction, which is why the report scopes that row to the prototype's walk.

Every affected witness and static check was re-run after the fixes; §Verification
records the final pass.

### Reviewer 3 — final closure audit

Prompt, verbatim as `PROMPT_12.md` §E specifies, plus the same context
paragraph, pointers to both prior reviews, and the file-delivery instruction:

```text
Perform a final read-only closure audit of PROMPT_12.md, all Prototype 12 code,
and the final reports/PROTOTYPE_12.md against the active target-shaped-parse
INDEX/context/goal/DESIGN/TODO. Confirm that every earlier semantic and
performance finding is actually resolved, that open user decisions remain
open, and that no conditional or unmeasured premise is called closed. Do not
edit or benchmark. Return only substantive blockers followed by READY or NOT
READY, with file:line evidence.
```

**Verdict: NOT READY.** It verified all sixteen earlier findings genuinely
resolved in code — re-running reviewer 1's own falsification probe, which now
returns `cyclic-opaque differs=False` for both variants in both lanes and at
both levels — and confirmed that the open user decisions stay open, that the
planning edits are not applied, and that `src/`, `tests/` and `pyproject.toml`
are untouched. It then found three report-text defects against the round's own
"every number from the final pass" contract:

| # | severity | finding | fix |
|---|---|---|---|
| 1 | BLOCKER | three §B band sentences still quoted endpoints matching no printed row — conclusion 3's `0.078–0.119 s` / `0.87–1.43 s`, the Python adoption sentence's `0.042–0.199` / `0.030–0.052`, and the `IrMap`/tokenizer sentence's `0.118661` / `0.196016`, which are real but came from rows the sampled table omits. Reviewer 2's F3 was declared fixed but was not | a per-product min/max block is printed beside the sampled table so EVERY endpoint any band quotes is exhibited, and all three sentences are re-derived from it |
| 2 | BLOCKER | conclusion 7 and the §D prose still carried the pre-fix `0.431261 / 0.434696 / 1.008` paid-loop numbers while the §D verbatim block printed `0.426310 / 0.427679 / 1.003209` — two passes coexisting in one report | both prose sites now quote the verbatim block's figures, with the 0.995–1.008 instability stated beside them |
| 3 | LESSER | the record claimed "`another_meaning` is used as an oracle nowhere" while `prove_chart_differential`'s docstring still called it "Oracle 2" and the suite asserted agreement with it on every default-policy case | relabelled in both the docstring and the report as a CROSS-CHECK on shipped behaviour, printed as `shipped_another_meaning=…`; the assert is deliberately kept so a change in shipped behaviour fails the suite, and the truth source is the declared verdict plus the oracle beside it |

Its procedural note — that this record was a placeholder — is answered by this
section. No witness, mechanism, or adoption ruling was invalidated by any of
the three; all were report-text corrections against evidence already collected,
plus one docstring and one printed field name.

### Reviewer 4 — final closure audit

§F makes readiness conditional on the FINAL fresh reviewer returning READY, so
a fourth fresh audit ran after reviewer 3's fixes, on the same prompt plus
pointers to all three prior reviews and an instruction to check every quoted
figure against the report's own verbatim blocks — reviewer 3 having caught
exactly the failure mode of a fix being described rather than made.

**Verdict: NOT READY.** It verified all nineteen prior findings genuinely
resolved in code AND report, re-ran reviewer 1's falsification probe (both
shapes OPAQUE with the oracle's exact value, chart and binding, early and full
lanes), re-ran the four cheap witnesses with structural counts matching
exactly, and confirmed the open user decisions and production-integration
items are still open. It then found two more instances of one defect class:

| # | severity | finding | fix |
|---|---|---|---|
| 1 | BLOCKER | recommended planning edit 6 still quoted the paid-loop ratio `1.003` from the pass before reviewer 3's fix, while conclusion 7 and the §D prose had been updated to the final block's `1.001399` | edit 6 quotes 1.001 |
| 2 | BLOCKER | the §C pad-32,000 summary row's transient-peak and oracle cells (`78,284,804` / `1,223.2` / `122,247,716`) came from an earlier run of the same row than the verbatim block beside them (`78,271,808` / `1,223.0` / `122,247,680`) | all three pads' cells re-derived from the final pass, and the pad-2,000 and pad-8,000 `flat-index-detail` lines printed so every table cell is exhibited |
| 3 | LESSER | conclusion 6's one-seed sub-band said 145–178 B while the printed one-seed minimum is 144.2 | corrected to 144.2–177.7 B |
| 4 | LESSER | four pad-2,000/8,000 control fold figures were quoted with no printed row behind them | both `direct-product-state` rows printed |
| 5 | LESSER | "the sky meet is replaced" reads as gone everywhere, while `ambiguity_interaction`'s acyclic lane still prints and uses it | scoped: the per-edge rule is what `cyclic_meaning` takes; the meet is strictly more conservative and is retained in the acyclic lane as the P11 evidence it was |

Nothing numeric moved: 98–112 B/char retained, the 17–20× oracle ratio, the
1200–1223 B/char transient band, and the neutrality conclusion all hold under
either pass. Both blockers were two-line corrections against evidence already
printed in this report. This section is the record its procedural note asked
for.

**Standing caveat on this record.** Three of the four reviewers' blocking
findings were report-text drift — a figure surviving from a superseded run —
and the class recurred after each declared fix. The mechanisms and the
measurement designs were not what kept failing; the transcription was. A
future round should generate every quoted figure from the output files rather
than editing prose, which is the process fix this round did not make.

---

## Self-audit

- The mechanism in §A classifies a POLICY-NAME algebra, not the production
  operation records. The mapping is one-to-one with the ABI's declared
  operations (`PassOp` → `ident`, `ConstantOp`/dropped capture → `const`,
  `ValidateOp` and other declared-finite-image operations → `finite`,
  `RecordOp` and the sequence/mapping builders → `grow`), but that mapping is
  ASSERTED here, not executed. It is listed as production-integration work.
- The `grow` class rests on "the operation embeds the cycle child as a proper
  sub-value, so `f^n(b)` are pairwise distinct". That is a well-foundedness
  argument about finite tuples; it is stated, and the `unit-cycle-growing` and
  `two-key-cycle-growing` oracle ladders exhibit the growth, but no witness
  proves it for an arbitrary future operation. An operation that cannot be
  placed in one of the four classes raises at `slot_class` rather than being
  guessed.
- The bounded-depth oracle is independent of the CLASSIFICATION and the
  FIXPOINT — the load-bearing halves — but it reuses `selected_resolved`,
  `local_choice_keys`, and `assignments` to read the chart. A defect in that
  shared family-resolution layer would fool both sides of the differential
  identically. The acyclic cases carry a second, fully independent oracle
  (`FastTree` enumeration, which is exhaustive on an acyclic chart) and
  production `another_meaning`, so the shared layer is cross-checked there.
- Termination for a safe component is argued, not machine-checked: the report
  claims the reachable value domain is finite because every cycle either
  preserves values or passes a declared-finite-image operation. What the code
  checks is the monotonicity that argument needs; if the argument were wrong
  the loop would not terminate rather than return a wrong answer.
- The refused cyclic class is genuinely over-refusing, and the report says so
  with a witness whose root set is a singleton.
- §B's `from_indexes` is a prototype of an intended constructor. Its
  document-level twin is differentialled against its OWN eager implementation;
  the shipped `from_merges` lane is differentialled against the real
  constructor. Where the two tails disagree, the disagreement is enumerated,
  not averaged away.
- §C's transient build peak is a prototype cost. The claim that production has
  no such transient is an argument about where the dense number lives, not a
  measurement.
- §D's paid-loop row compares two arms of the PROTOTYPE's walk. It says nothing
  about the production completion path, and the report does not claim it does.
- Timings in §A and §D are in-process; §B's Qwen row and every §C row are
  cross-process under `guarded.sh`, one at a time, with the collector enabled
  and its state printed. No agent was running during any measurement.
