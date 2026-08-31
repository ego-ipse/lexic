# Prototype 16 — shared occurrences, and what bounds the exact lane

**Status:** an EVIDENCE round for the two planning questions Prototype 15
opened. It approves nothing and edits no active document. The active packet,
`src/`, `tests/`, `pyproject.toml`, `.wiki`, and every earlier prototype and
report were read-only throughout; §9 records the before/after file comparison.
No commit, no push, no worktree. Every run was sequential, one process at a
time, and no multithreaded row exists anywhere in this round.

| File | Round-16 role |
|---|---|
| `proto/shared_occurrence_ambiguity.py` | new — semantic ambiguity under every real shared-DAG shape, against an independent occurrence-unrolled oracle |
| `proto/exact_lane_cost.py` | new — local multiplicity from real chart data, the lever ladder, and the lower-bound witness |

Mechanisms are reused, not re-derived: `island_continuation.py` supplies the
CANDIDATE per-node relation, the dirty cone, the compiled continuation rows and
the delegated-island seam; `cyclic_meaning.py` the family-aware chart decode;
`operation_slot_laws.py` the real operation classifier; `shared_forest_refold.py`
the four shared shapes; `ambiguity_interaction.py` the one-flip disproof.

**What engine this is.** Everything runs through the real Earley kernel, with
the island witness Earley-delegated via `Kernel(..., delegates=...)`. Nothing
here executes the predictive runtime. §8 carries what that cannot reach.

---

## PART A — shared-occurrence composition

## A1 — the identity question, answered first

A packed forest node is keyed by `(item, end)`. It is a **value**: two
grammatical occurrences of one rule can reach the same handle, and the engine
intends them to. The **occurrence** is the forest edge that reaches it —
`(consuming handle, family index, kid slot)` — which `Chart.edges` already
carries and a built `ParseTree` does not.

```text
tree-versus-occurrence-identity
  chart_shared_tree_objects_at_two_kid_slots=1
  chart_occurrence_edges_on_the_shared_node=2
  empty_tree_interns_one_derivation=True
  interned_twin_chart_shared_nodes=0
  interned_twin_tree_objects_at_two_kid_slots=1
```

Two independent causes make the tree lose the occurrence.
`FastTree._build`/`memo` memoizes a built subtree **by handle**
(`src/lexic/parsing/earley/kernel/forest/fasttree.py:113-120`), so a
chart-shared node is one Python object at two kid slots. And
`ParserTables.empty_tree` **interns** one derivation per unambiguously nullable
rule (`src/lexic/parsing/earley/kernel/tables/records.py:354-384`) — so the
sibling-memo twin, whose chart shares *nothing* (the two spans differ), still
hands the fold one object at two positions. Production `ModelFold.apply` keys
`results` on `id(node)` (`src/lexic/parsing/fold.py:476-491`) and
`fold._tree_offsets` records one start per `id`
(`src/lexic/parsing/fold.py:293-330`, whose own docstring names the zero-width
case it cannot separate).

**Answer to "does the forest carry enough": yes in principle, and NOT as a
ready-made edge.** The correction matters, so it is stated precisely rather than
summarised.

- The occurrence identity that the semantics needs is
  `(consuming handle, family index, kid slot)`.
- `cyclic_meaning.Edge` is `(parent, child, slot)` — **three fields, no family
  index** (`proto/cyclic_meaning.py:366-371`). The prototypes obtain the family
  from `enumerate(families)` at the point of use, not by reading it off an edge,
  and `slot_consumptions` deliberately collapses families to `(parent, slot)`.
- Production is further away still: `forest/chart.py:44-66` is a
  key→families multimap with **no parent→child edge at all**. A kid slot has to
  be recovered by re-resolving the binarised chain
  (`tables/splits.py::leftmost_chain`), and a completion's "family index" is an
  index into an enumerated assignment over that node's own choice keys, produced
  by a fixpoint (`proto/cyclic_meaning.py:322-346`) — not a bucket index.

So the information is derivable from what the forest already holds, and nothing
new must be RECORDED during recognition; but the occurrence triple is not sitting
there to be read, and materialising it is real work. §7 carries that as an
implementation gate rather than, as an earlier draft of this report had it, "no
new occurrence identity is required". What must **not** be adopted is the tree's
object identity.

## A2 — a structural fact the round establishes

```text
intra-derivation-sharing  repeated_children_checked=7
                          distinct_span_widths=[0]
```

A node consumed **twice inside one family** is always zero-width, because a
chart node is keyed by its span and two slots of one arm occupy disjoint spans
unless both are empty. Sharing at a non-empty span is therefore always **across
derivations**, where each derivation consumes the node once. That is why a
delegated island — which must consume the text it recognizes — can only appear
beneath an inter-derivation shared completion, which is the shape §A5
witnesses. An intra-derivation shared island is not a thing the engine can
express, and the reason is structural rather than a missing witness.

## A3 — the three lanes, and the disproof

- **CANDIDATE** — `island_continuation.exact_meanings`: one deduplicated
  meaning set per chart node, each consuming slot ranging over it.
- **ORACLE** — `shared_occurrence_ambiguity.unrolled_meanings`, written this
  round. It re-resolves the binarised chain at **every occurrence**, keys its
  results on the occurrence PATH rather than on the handle, never memoizes
  across occurrences, calls no candidate set function, and deduplicates through
  the production `same_value` rather than the candidate's `repr` key.
- **CONTROL, DISPROVED** — `key_correlated_meanings`: one family per arm-choice
  key across a whole derivation, through real `FastTree` builds. That is
  Prototype 15's own complete-fold oracle.

**The oracle's independence, stated at its real boundary.** It is not total,
and the round does not claim it is. The oracle shares the chain-RESOLUTION
primitives with the candidate — `cyclic_meaning.local_choice_keys` /
`assignments` / `selected_resolved`, which is how any reader gets a family out
of the binarised links — and it shares the real reducer, which it must, because
the reducer IS the semantics both compute. What it does not share is the
composition rule, the memo policy, the dedup key, or the traversal. So
`lanes_agree` cross-checks composition, not family decomposition.

```text
oracle-independence  shared_handle_rule=a
                     occurrence_paths_expanded_at_that_handle=2
                     chart_occurrence_edges_at_that_handle=2
                     shares=[chain resolution primitives, the real reducer]
                     does_not_share=[composition rule, memo policy, dedup key,
                                     traversal]
```

The count is taken **at the shared handle**, so it cannot be satisfied by some
other node carrying two families — an earlier "occurrences exceed nodes" form of
this pin was not discriminating and has been replaced.

**And the one lane that WOULD be independent in its family decomposition is
unsound here — which is itself a finding.** Production's own trampolined
`forest.DERIVATIONS` over `readout.to_chart` walks the decoded `Chart.links`
through `PrefixSource`/`ChildDerivs`, never touches `predecessor_chain`, and is
occurrence-unrolled by construction. It cannot be this round's oracle:

```text
production-enumeration  duplicate-slot  shipped_derivations=2
                        shipped_wellformed_meanings=0
                        shipped_malformed_derivations=2  grammar_meanings=4
production-enumeration  pending-frame   shipped_derivations=2
                        shipped_wellformed_meanings=0
                        shipped_malformed_derivations=2  grammar_meanings=4
production-enumeration  arm-shared      shipped_derivations=4
                        shipped_wellformed_meanings=2    grammar_meanings=2
```

`ForestCtx` guards re-entry on a handle whose prefixes are "mid-production", and
its docstring (`src/lexic/parsing/earley/kernel/forest/forest.py:206-212`) says
an EXHAUSTED handle may be re-entered legitimately because that is sharing.
Under the trampolined lazy walk the distinction does not hold: a zero-width
handle consumed at two slots of ONE derivation is still *suspended* when the
second consumption reaches it, so `PrefixSource`
(`forest.py:396-401`) emits its single empty prefix and builds a `ParseTree`
with no kids under a rule that always has one. On the duplicate-slot and
pending-frame shapes the shipped enumeration therefore yields two derivations
where the grammar derives four, and **not one of them is well-formed**.

That is a shipped defect on exactly this round's shape, and it is why no lane in
the tree independently confirms the family enumeration. The round states that
rather than claiming an independence it does not have.

Every witness, both flavours, all lanes:

```text
uv run python proto/shared_occurrence_ambiguity.py

shape                     witness                  shared  edges exact oracle correlated
duplicate slot            duplicate-slot           a       2     4     4      2  LOSES
duplicate slot            duplicate-slot-abnf      a       2     4     4      2  LOSES
pending frame             pending-frame            a       2     4     4      2  LOSES
sibling memo              sibling-memo             (tree)  0     4     4      4
sibling memo (chart)      arm-shared               s       2     2     2      2
transparent synthetic     transparent-synthetic    b       2     4     4      2  LOSES
duplicate slot + unshared mixed-shared-and-not     a       2     2     2      1  LOSES
two accepting items       sibling-accepting-roots  a       4     8     8      4  LOSES
duplicate slot, 1 family  unambiguous-shared       a       2     1     1      1

correlation-disproof  witnesses_where_the_key_global_control_loses_meanings=6
```

`lanes_agree=True` on **every** row: the candidate per-node relation and the
occurrence-unrolled oracle produce the same meaning set on every real shared-DAG
shape. The key-global control is strictly smaller on six of nine.

**The disproof, stated exactly.** The engine packs a child's arm choice on the
**consuming waiter's** key. So when a rule is written `s ::= p | q` the choice
lands at the parent and a key-global assignment happens to be per-occurrence.
Add one level of indirection — `a ::= b`, `b ::= p | q` — and the choice moves
**inside `a`'s own chain**. Node `a` is then reached by two occurrences whose
mixed choices are observable only jointly, and a relation that fixes one family
per key produces `{(P,P), (Q,Q)}` where the grammar derives
`{(P,P), (P,Q), (Q,P), (Q,Q)}`. Two of the four meanings do not exist under the
correlated relation. That is the exact case Prototype 15's every-witness
assertion (`nodes_with_two_parents=0`, `keys_claimed_twice=0`) excluded, and it
is now executed under three of the four named shapes plus two derived ones.

**The sibling-memo row is the honest negative.** Its sharing is tree-object
only — the two `a` spans differ, so the chart shares nothing — and both
relations agree at 4. That zero is now *checked* rather than produced by the
query: every witness reports `every_shared_rule`, computed WITHOUT a rule-name
filter, and a witness declaring no shared node must have none at all. An earlier
draft filtered by the declared name, so a witness declaring `""` would have
reported `0` whatever the chart shared. `arm-shared` is its chart-shared twin:
node `s` reached by two parents in two different derivations, each of which
consumes it once, where the correlated relation is also right.

**Two scope limits, executed rather than argued away.**

```text
synthetic-sharing-scope  witnesses=10  shared_synthetic_nodes_found=0
```

*No synthetic node is ever itself the shared one.* `shared_forest_refold.py`'s
fourth shape is a transparent synthetic node whose fold repeats because it
stores no result; this round reaches it only as a synthetic *consumer* over a
shared authored rule (`transparent-synthetic`, `synthetic-consumers`).
Normalization gives each alternative its own hoisted arm, so two consumers reach
two distinct synthetic handles. Nothing here depends on the gap — the meaning
relation has no result-less node — but it is a gap, and the row reports it
instead of letting the shape count as covered.

*No split-ambiguous shared node either.* `cyclic_meaning.local_choice_keys`
admits a key only when `is_arm_choice` holds, so split families — two adjacent
nullable slots dividing a non-empty gap, which `support/ambiguity.py` and
`tables/splits.py` both name as routine and *decided* — never enter either
lane's family set. That is consistent with production's split policy, but it
means the agreement below is scoped to **arm-choice families**, and §8 carries
it.

## A4 — the five properties the tasking names, each pinned separately

**A shared node's meaning set can be computed once while each consuming slot
ranges over it independently.** The falsifiable evidence is a CONTROLLED cost
differential against an unshared twin that spells the same language with the two
occurrences given their own rules:

```text
shared-once-differential  shared_meanings=4  twin_meanings=4
                          shared_chart_nodes=8  twin_chart_nodes=13
                          shared_products=6     twin_products=8
                          extra_applications=2  shared_node_own_families=2
                          extra_equals_one_more_copy_of_that_set=True
```

The twin's extra applications are **exactly** the shared node's own family
count — one more copy of that node's set — not merely "more, because the twin is
bigger". An earlier draft asserted only the inequality, which a twin that grew
for any other reason would also satisfy.

Beside it, `candidate_order_visits_each_handle_once` reports that the
candidate's own node order (`island_continuation._topological`) yields each
handle once, and `exact_meanings` calls its per-node set function once per
element of that order. That is a statement about the code path, **not a
falsifiable check** — `_topological` carries a `seen` set and cannot emit a
duplicate for any input — and the report labels it as such rather than counting
it as a second proof.

The "ranges independently" half is what `lanes_agree=True` beside
`correlated < exact` says, on six rows.

**Append, insert, verdict and duplicate effects execute per consumption.** This
is a claim about how often a body RUNS, so it is measured as an execution count
rather than inferred from a set size:

```text
occurrence-effect  append     consumer_body_executions=4  shared_node_expansions=2
                              exact=4  oracle=4  per-node control=2
occurrence-effect  insert     consumer_body_executions=4  shared_node_expansions=2
                              exact=4  oracle=4  per-node control=2
occurrence-effect  verdict    consumer_body_executions=4  shared_node_expansions=2
                              exact=2  oracle=2  per-node control=1
occurrence-effect  duplicate  consumer_body_executions=4  shared_node_expansions=2
                              exact=2  oracle=2  per-node control=0
```

The consumer's body runs **four** times — once per `(slot 0 option, slot 1
option)` tuple — while the shared node it consumes is expanded at exactly its
**two** occurrences and its own set is computed once. That is the execution
property. The meaning columns are reported beside it, and `duplicate` is the
sharpest of them: forcing both slots to one arm makes every derivation insert
the same key twice, so the refusing operation removes the whole image and the
per-node control answers **zero** meanings.

**Shared and non-shared choices compose exactly.** `mixed-shared-and-not` puts a
shared zero-width node beside an unshared choice under a joint predicate: exact
2, oracle 2, correlated 1.

**Unambiguous sharing allocates no ambiguity-only state.**

```text
unambiguous-sharing  most_consumed_node_occurrences=2  chart_nodes=5
                     dirty_nodes=0  set_applications=0
                     multiplicity_nodes=0  baseline_products=5
```

A shared node with one family is outside the dirty cone, so its set is its
baseline.

**Separate accepting roots remain separate meanings.**

```text
separate-accepting-roots  accepting_items=2  meanings_per_root=[4, 4]
                          meanings_together=8
```

Each accepting item is its own complete meaning, and the shared node below both
is still expanded once per occurrence under each.

## A5 — a delegated island option beneath a shared completion

```text
delegated-under-shared  shared_completions=1  occurrence_edges=2
                        delegated_leaves=1    leaf_options=[2]
                        exact_meanings=2      unrolled_oracle=2
                        key_correlated_meanings=2  agree=True
```

The island interior is Earley-delegated through the real
`Kernel(delegates=...)` seam, so the shared completion's children include a real
`PayloadLeaf` carrying two published options rather than a subtree. The option
lane and the packed-family lane compose the same way.

**This row does not discriminate the two relations, and the correlated column is
printed to say so.** The two consumptions of `s` live in *different* derivations
(`m ::= l | r`), so a key-global assignment answers 2 as well. What the row
shows is a delegated option composing beneath a shared completion; only the
intra-derivation rows separate the relations, and per §A2 a delegated island
cannot take that shape.

## A6 — one real defect the shared witnesses expose

```text
partial-family-defect
  unguarded_candidate=IrMap: duplicate key IrStr('P')
  guarded_meanings=2
```

`operation_slot_laws._prove_partial_operation` already **rules** the semantics:
an operation that refuses produces no value at all — the `finite(0)` bottom —
and an absent value cannot make a requested root mean two things.
`island_continuation._node_set` applies the authored body with no guard, so on
the duplicate-key witness the refusal escapes and the **entire settlement dies**
instead of that family dropping out of the image. This is not a new decision; it
is an implementation gap against a ruling that already exists. The prototype
restores the ruling by wrapping the reducer (no candidate file was edited) and
the guarded lane then agrees with the oracle at 2.

**The guard's boundary is NOT narrow, and that is the second half of the
finding.** Two rows say so, because §7 hands this guard to production.

```text
partial-guard-boundary  value_refusal_type=UnsupportedConstructError
                        undeclared_construct_type=UnsupportedConstructError
                        distinguishable_by_type=False
```

The prototype absorbs an exception TYPE, and that type is overloaded:
`UnsupportedConstructError` is also what an open `IrDispatch`/`IrTypeMap` raises
for an undeclared construct — CLAUDE.md's stated default. A guard keyed on the
type alone would turn a genuine engine failure into a silently dropped family.
Absorbing is still the correct *semantics*; the *signal* it needs does not
exist, so **production owes a distinct value-refusal exception before this guard
can land.**

```text
fully-refusing-node  oracle_raises=True  candidate_raises=False
                     candidate_returned_meanings=0
```

And the "empty set still raises" boundary holds in only one lane. The oracle now
raises when every family of a node refuses — no meaning exists, and reporting an
empty lane would let the parent's product silently drop the family. The
candidate under the absorbing wrapper returns an **empty set instead**: its own
empty-lane raise (`island_continuation._slot_options`) is unreachable because
the wrapper hands every slot a sentinel rather than an empty lane. That is a
second production obligation on the same guard — absorbing a refusal must not
make "no meaning" indistinguishable from "settled". An earlier draft of this
report claimed both boundaries held; neither did.

---

## PART B — what bounds the exact lane

## B1 — local multiplicity, and the second factor an application count hides

For a completed node `h` the exact relation APPLIES its authored operation

```text
m(h) = Σ over h's packed families of Π over that family's slots of |set(child)|
```

times, where a slot's lane is a child node's **deduplicated** meaning set, a
delegated island's published **option set**, or one root of the accepting-item
union. `m(h)` is exactly what the dirty cone does not bound: the cone bounds how
many nodes pay, never what one node pays. That identity is **definitional** —
`_settled_set` increments once per element of the same product — and this report
no longer presents it under "Executed"; what is executed is everything below.

**An application count is not a cost, and this round's own timing table is what
proves it.** At `k = 10`, `late-second` streaming and `grow` materializing
perform an *identical* 1044 applications, and their CPU differs by two orders of
magnitude. The hidden factor is value identity: deduplication is a linear scan
comparing each candidate against the meanings collected so far, so a node whose
IMAGE grows pays quadratically in that image, over values that are themselves
growing.

```text
applications-are-not-the-cost
  k=6   applications 76/76      comparisons 70 / 4038        ratio 58x
        peak retained 2 / 64
  k=8   applications 272/272    comparisons 264 / 65288      ratio 247x
        peak retained 2 / 256
  k=10  applications 1044/1044  comparisons 1034 / 1047562   ratio 1013x
        peak retained 2 / 1024
        late_comparisons_linear_in_applications=True
        grow_comparisons_quadratic_in_its_image=True
```

So the exact lane's cost is **applications × the value-identity work each one
triggers**, and the second factor grows with the node's own image. An earlier
draft of this report stated the bound as `Θ(local multiplicity)` three times and
drew no conclusion from the two equal-count rows in its own §B5 table. That was
wrong, and the correction propagates: §B7's budget cannot be denominated in
applications, because on these rows one application buys between ~6.8 µs and
~1.4 ms.

**And the exponential does not sit at one node in general.** The ladder gives
the root the only multi-slot consumer, so its linear residue is a property of
that shape. The missing control is a chain of retaining consumers:

```text
stacked-product  levels=1  total_applications=8    root_multiplicity=4    root_share=50%
                 levels=2  total_applications=40   root_multiplicity=16   root_share=40%
                 levels=3  total_applications=560  root_multiplicity=256  root_share=46%
                           image=256  peak_retained_at_one_node=256  comparisons=98184
```

The root is under half the work; the sum below it grows with the stack. The
round therefore claims only the **per-node identity** — a node's cost is its own
local multiplicity, and the dirty cone bounds neither that nor the total — and
not, as an earlier draft had it, that "the exponential term is one node's own
product".

## B2 — the controlled ladder

One grammar family, `k` independent binary ambiguity points, one document, one
changed thing per rung: the consumer's authored operation.

```text
uv run python proto/exact_lane_cost.py
                                  k = 2, 4, 6, 8, 10

ladder collapse      differs=False full=[8,24,76,272,1044] streaming=[8,24,76,272,1044]
                     law=False law_apps=[0,0,0,0,0]  one_flip=[F,F,F,F,F]
ladder early-second  differs=True  full=[8,24,76,272,1044] streaming=[6,10,14,18,22]
                     law=False law_apps=[0,0,0,0,0]  one_flip=[T,T,T,T,T]
ladder late-second   differs=True  full=[8,24,76,272,1044] streaming=[8,24,76,272,1044]
                     law=False law_apps=[0,0,0,0,0]  one_flip=[F,F,F,F,F]
ladder law-settled   differs=True  full=[8,24,76,272,1044] streaming=[6,10,14,18,22]
                     law=True  law_apps=[2,2,2,2,2]  one_flip=[T,T,T,T,T]
                     full_peak_retained=[4,16,64,256,1024]
                     streaming_peak_retained=[2,2,2,2,2]
```

The cases the tasking asks to be covered, and — stated plainly — how many
*distinct configurations* actually stand behind them:

| Case | Rung | Evidence | Distinct? |
|---|---|---|---|
| collapsed derivations | `collapse` | image 1, `full = streaming = 2^k + 2k` | yes |
| early second root value | `early-second` | `streaming = 2k + 2` against `full = 2^k + 2k` | yes |
| late second root value | `late-second` | `streaming = full = 2^k + 2k` | cost-identical to `collapse` |
| interacting invisible substitutions | — | `one_flip_differs=False`, re-read off `collapse` and `late-second` | **no rung of its own** |
| operation-law shortcut | `law-settled` | law lane 2 applications against 2^k | yes |
| genuinely exponential image | `law-settled` | image `2^k`, all distinct; `full_peak_retained = 2^k` | **same rung as the row above** |

Six named cases rest on **four rungs and two cost shapes**; the `grow`
configuration additionally carries `lever-isolation`, `grow-image`,
`dedup-climb`'s retaining arm, `flavour-neutral` and two timing columns. The
genuinely distinct executed configurations in Part B are five: the four rungs,
plus `dedup-climb`'s collapsing arm — and now the stacked-product control of
§B1, which is the only one with multiplicity anywhere but the root.

Every rung's verdict is held against the occurrence-unrolled oracle from Part A
at the small point counts, where enumerating it is affordable, so no cost lever
can quietly change an answer:

```text
oracle-check  collapse      k=2,4  unrolled=1      materializing=1      same_set=True
oracle-check  early-second  k=2,4  unrolled=2      materializing=2      same_set=True
oracle-check  late-second   k=2,4  unrolled=2      materializing=2      same_set=True
oracle-check  law-settled   k=2,4  unrolled=4, 16  materializing=4, 16  same_set=True
```

The comparison is on **meaning sets**, not on the boolean verdict. An earlier
draft compared only "more than one", which a lever that changed *which* meanings
are produced would have passed.

## B3 — each lever, isolated

Running each lane alone, so no lever is credited with another's saving:

```text
lever-isolation  collapse      k=8  applications={full:272, declared-bound-only:272,
                                                  root-stop-only:272, both:272}
lever-isolation  early-second  k=8  applications={full:272, declared-bound-only:272,
                                                  root-stop-only:18,  both:18}
lever-isolation  late-second   k=8  applications={full:272, declared-bound-only:272,
                                                  root-stop-only:272, both:272}
lever-isolation  grow          k=8  applications={full:272, declared-bound-only:272,
                                                  root-stop-only:18,  both:18}
                                    peak_retained={full:256, declared-bound-only:256,
                                                   root-stop-only:2,  both:2}
```

**Streaming with an immediate stop after a certified second root value — real,
and exact.** It ends the enumeration on its ANSWER, never on exhaustion, and the
incomplete set is reported as zero meanings so it cannot be misread as a set
size. It removes the root's product where the second value appears early
(`2^k → 2`) and is worth nothing where it appears last. Both are measured.

**Exact finite quotients from declared image bounds — NOT VALIDATED, and not
credited with anything.** This lever is the round's weakest and the report now
says so rather than claiming exactness for it.

- *It never fires.* `lever-isolation` shows `declared-bound-only == full` on all
  eight rows — identical applications AND identical peaks on every one. **No
  executed row anywhere shows the quotient truncating a set**, correctly or
  otherwise. (The ROOT STOP does change the peak, 256 to 2 on the `grow` rows;
  that is the other lever, not this one.)
- *Its composition is unproved.* `image_bound` multiplies per-slot bounds across
  distinct slots, and per-slot bounds do not compose by product in general:
  `f(i,j) = v_i if i == j else x` varies over ≤ 2 values in either coordinate
  alone and has an image of `n+1`. `operation_slot_laws.differential_law`
  validates one slot at a time with every other position held at a filler, so it
  never probes the product. Whether the classifier's own `_join`/`_combine`
  structurally prevents the diagonal is plausible and **unestablished here**.
- *Its retention claim was misattributed.* An earlier draft said the quotient is
  "why the predicate rungs' peak stays linear". It is not: those peaks are
  linear because their images are 1 and 2, and the isolation row shows the
  quotient changed no peak anywhere.
- *One silent default fixed.* `bounds_for` used `widths.get(rule, 1)`, so a rule
  missing from the arity table would be examined at slot 0 only and could be
  declared bounded with a carrying slot at index ≥ 1. It now refuses.

What survives is narrow and true: a `finite(b)` law bounds what a node RETAINS,
and it does not cap the work — the collapse rung's streaming lane pays exactly
what the materializing lane pays, because the operation still has to be applied
to find out which combinations collapse. **Adopting this lever at all is a user
decision**, not an implementation detail: an unsoundly composed bound would
silently narrow a meaning set, which is the "unambiguous" wrong answer. The
compile-time census says it would buy nothing today in any case:

```text
static-census  gbnf  rules=104  image_bounds={'bounded=1': 19, 'unbounded': 85}
static-census  abnf  rules=101  image_bounds={'bounded=1': 1,  'unbounded': 100}
static-census  ebnf  rules=61   image_bounds={'bounded=1': 12, 'unbounded': 49}
static-census  json  rules=51   image_bounds={'bounded=1': 10, 'unbounded': 41}
static-census  cpu=0.042403     ONE un-repeated sample, no control, no conclusion
```

Every bounded rule on the shipped surfaces bounds to **one** — they are the
constant actions. No shipped rule has a declared finite image wider than a
constant, so there is nothing there to quotient. The rules that force the
product are the unbounded majority. This census is also a LOWER bound on what a
complete analysis could classify, because `island_continuation.slot_law` refuses
a rule whose canonical and normalized contributing references differ
(`PROTOTYPE_14.md` §4's open channel-index obligation) and `image_bound`
inherits that refusal.

**Structural sharing — real, and already in the per-node form.** Deduplication
at each node is what stops multiplicity climbing:

```text
dedup-climb  k=4  retaining_children_image=16   applications=24
                  collapsing_children_image=1   applications=9
dedup-climb  k=6  retaining_children_image=64   applications=76
                  collapsing_children_image=1   applications=13
dedup-climb  k=8  retaining_children_image=256  applications=272
                  collapsing_children_image=1   applications=17
```

Only the intermediate consumers' authored bodies change. A child whose own set
deduplicates to one value contributes a lane of width one, so the parent's
product does not grow at all. Part A adds the other half: a node **shared** by
several occurrences has its set computed once and reused, measured against the
unshared twin.

**The law lane — the lever that actually removes the exponential, where it
applies.**

```text
grow-image  k=2   full_applications=8     image=4     law_lane_applications=2  witness=s1
grow-image  k=4   full_applications=24    image=16    law_lane_applications=2  witness=s3
grow-image  k=6   full_applications=76    image=64    law_lane_applications=2  witness=s5
grow-image  k=8   full_applications=272   image=256   law_lane_applications=2  witness=s7
grow-image  k=10  full_applications=1044  image=1024  law_lane_applications=2  witness=s9
```

The certificate is existential over real family-aware chart edges: a node is
marked when some realized route to an accepting item has an `ident`/`grow` slot
law at every step. The witness that the marked node really holds two meanings is
**constructive and local** — its own families applied with every child held at
its baseline, which is a lower bound on its true set. Acting only on "yes, two"
keeps that sound: the lane never concludes "one" from it and falls through to
the executing lane instead. So the exact question drops from the ROOT's local
multiplicity to **one witnessing node's family count** — two applications
against `2^k`. Prototype 15 described this lane as "zero executed operations";
it is two.

Four things keep that honest, all of which an earlier draft omitted:

- **The two applications are not the lane's cost.** `certified` runs a full
  baseline fold *unconditionally*, before examining any marked node.
  `law_lane_unconditional_baseline_folds=51` at `k=10`, against the two the
  witness pays. The counter now reports both, because reporting only the two
  states a lane cost that excludes most of the lane's work — the same pattern
  §B6 admits for the chart build.
- **Two is a best case.** `certified` accumulates over marked nodes until the
  first witness; the reproduced witnesses (`s1, s3, s5, s7, s9`) happen to have
  exactly two families each. The general cost is the sum over marked nodes
  examined before the first witness, and chart order decides it. Nothing here
  bounds that.
- **There is no negative control.** No row exercises the case where the
  certificate finds no witness but the truth is "differs" — where the lever
  makes the parse *slower* (certificate cost plus the full lane). The three
  rungs reporting `law_lane_applications=0` are not that case: nothing is marked
  there, so the certificate is inert while still paying the baseline fold above.
- **The executed certificate is weaker than the stated one.** Its docstring
  speaks of "fixing that route's families", but `_injective_nodes` fixes no
  family — it is plain reachability over edges whose slot law carries, and
  `algebra.Edge` has no family index (§A1). The gap between the stated and the
  executed certificate is real and unclosed.

**Compile-time refusal — investigated and NOT recommended.** The census above is
what a compile-time refusal would have to key on, and it refuses the wrong
population: a rule is "unbounded" whenever any slot is `ident`/`grow`, which is
85/104, 100/101, 49/61 and 41/51 of the shipped rules. Refusing those at binding
would refuse essentially every real grammar, and refusing only the `finite`-over-
wide-children *shape* is not a compile-time property at all — whether such a
node is ever dirty depends on the document. So the residual lever has to be a
runtime one; §B7.

Both lanes are flavour-neutral:

```text
flavour-neutral  late-second  gbnf_applications=76  abnf_applications=76  law=False
flavour-neutral  grow         gbnf_applications=76  abnf_applications=76  law=True  2/2
```

## B4 — the lower bound, executed

```text
lower-bound  points=[2, 4, 6, 8, 10]
             streaming_applications=[8, 24, 76, 272, 1044]
             root_local_multiplicity=[4, 16, 64, 256, 1024]
             streaming_equals_the_materializing_lane=[True × 5]
             law_lane_applications=[0, 0, 0, 0, 0]
             one_flip_differs=[False × 5]
```

The consumer's law declares a finite image and says nothing about **which**
combination collapses, so an exact algorithm has to apply the operation. This
operation's second distinct value is its **last** product. Streaming, the
declared bound, deduplication, the shared-node reuse and the dirty cone all
still pay `2^k` applications; the law lane does not fire at all (`0`
applications, no witness) because a `finite` consumer blocks the injective
route.

**The bound, stated in the unit the round can defend.** Exact settlement at a
node requires `Ω(m(h))` operation APPLICATIONS — that much this witness
establishes, and it is a lower bound on the applications, not on the wall cost.
The wall cost is that count multiplied by the value-identity work each
application triggers (§B1), which is itself image-dependent, so the round does
**not** state a single `Θ` in one unit. What it states is: applications are
`Ω(m(h))` here and no lever reduces them; and the per-application factor is not
constant, so any cost or budget expressed in applications alone is unsound.

**Yes, exponential work is unavoidable for an admitted product** under the
declared algebra. The declaration `finite(b)` is exactly the licence to say
nothing about the operation's fibres; sharpening it would mean declaring the
operation's value structure, which is a strictly larger proof obligation than
`operation_slot_laws.differential_law` currently discharges.

## B5 — the timing, with a control

```text
timing  k=6   late_second_streaming=0.001157  floor_control=0.001152  spread=0.451%
              early_second_streaming=0.000780  grow_materialized=0.006613
              grow_law_lane=0.000203
timing  k=8   late_second_streaming=0.002462  floor_control=0.002466  spread=0.194%
              early_second_streaming=0.000978  grow_materialized=0.092588
              grow_law_lane=0.000255
timing  k=10  late_second_streaming=0.007310  floor_control=0.007288  spread=0.293%
              early_second_streaming=0.001201  grow_materialized=1.469995
              grow_law_lane=0.000317
```

Process CPU, one process, five **alternated** in-process pairs, minimum of each
arm. An earlier version ran one arm to completion and then the other; its quoted
spread did not reproduce (an independent run measured 2.6% / 1.3% / 2.3% against
the quoted 1.7% / 0.08% / 0.15%, with the sign of the difference flipping).
`docs/STYLE.md` requires alternation for exactly that reason, and the arms are
now alternated. **The spread is read per run and is not quoted as a fixed noise
band** — it moves, which is what an un-repeated spread is worth.

The conclusions that survive are the ones far outside any of those spreads: the
materializing lane on the retaining rung reaches **1.47 s at ten ambiguity
points** while its law lane answers in 0.32 ms, and the early-second streaming
row is flat in `k` while the late-second row tracks `2^k`.

**What this table does NOT say, and an earlier draft did.** `late-second`
streaming and `grow` materializing have the *same* application count at every
`k` and differ by two orders of magnitude, so these numbers are not "the
application counts translating into time as stated". They are the counts times
the value-identity work of §B1, and the 4500× gap between `grow_materialized`
and `grow_law_lane` at `k=10` is mostly deduplication, not operation
applications. No benchmark of production parsing was run and none is implied.

## B6 — the unambiguous path: what it pays, and what the counters exclude

```text
unambiguous-path  chart_nodes=3  dirty_nodes=0  ambiguity_applications=0
                  peak_retained_meanings=0  baseline_products=3  verdict=equal
                  unconditional_chart_build_cpu=0.000052
                  whole_settle_cpu=0.000077
                  chart_build_share_of_settle=68.1%
```

The **set lane** performs no operation application, retains no meaning, and
makes no value-identity comparison. That is what the counters support, and
combined with §A4's `unambiguous-sharing` row it holds under node sharing too.

**It is not the whole account, and the report states the rest rather than
implying an empty one.**

1. *The chart build.* Both `settle` and `island_continuation.exact_meanings`
   build the family-resolved `cyclic_meaning.build_chart` — a per-node
   `local_choice_keys` fixpoint that re-resolves each handle's chain under every
   assignment — **before dirtiness is known**, and no counter charges it. It is
   **~68%** of the whole settle on this document.
2. *Three more uncharged passes.* `_refuse_cyclic` (a full SCC scan),
   `_topological`, and `_dirty_cone` (a full edge walk) also run on that path.
   The row measures one of the four; the remaining ~32% is undecomposed.
3. *One allocation the "allocates nothing" phrasing missed.* `settle` stores a
   singleton tuple per clean chart node into its `sets` dict. `peak` is 0 only
   because `Lane.retain` is not called for clean nodes.
4. *The ratio's own limits.* It is taken on a **3-node** chart with **no floor
   control**, unlike §B5. On a chart that small it is dominated by fixed costs
   and says nothing about a real document.

So the tasking's "keep ambiguity machinery off the unambiguous path" is **not**
satisfied by an empty dirty cone. A demand-driven chart is an open production
obligation (§7 gate (d)), and a proper unambiguous-path measurement on a real
document is a §12 measurement this round does not make.

## B7 — the refusal contract, recommended and NOT selected

If the user wants a resource ceiling at all, this is the narrowest honest shape,
executed:

```text
budget-refusal  points=8  budget=64
  refusal=parsing: settling ambiguity exactly at 'root' passed the declared
          budget of 64 operation applications; the requested root's meaning set
          is NOT known to be a singleton — raise the budget or supply a resolver
  generous_budget_verdict=differs  generous_budget_applications=272
```

- **What is counted — and this is now an OPEN question, not a settled bullet.**
  The prototype counts ambiguity-lane operation applications. §B1 shows that
  unit is not proportional to work: one application buys between ~6.8 µs and
  ~1.4 ms on this round's own rows, because value-identity cost varies with the
  node's image. A ceiling in applications is therefore not a resource ceiling.
  The honest unit is applications **times** value-identity work — i.e. the
  comparison count this round now reports beside every row — and production must
  pick one and say which. The excluded costs must also be named: the per-node
  baseline fold (the parse's own product) and the unconditional chart build of
  §B6 are both outside the count as written.
- **When it refuses:** when that count passes a declared ceiling, at the node it
  passed at.
- **Which exception — corrected.** `BudgetRefusal` must **not** subclass
  `UnsupportedConstructError`, because the round's own recommended
  partial-operation guard (§A6) absorbs that type. A budget refusal raised
  inside a reducer evaluation would be swallowed into the absent value and the
  family would silently drop — a refusal becoming "equal", the one outcome the
  tasking forbids. The prototype's earlier version had exactly that collision
  and was safe only by where the raise happened to sit, not by type; it now
  derives from `LexicError` instead. Its message says the meaning set is NOT
  known to be a singleton.
- **What it never does:** it does not choose a derivation, does not fall back to
  one-flip evaluation, and does not narrow the meaning set. The lane either
  settles exactly or refuses with words.
- **What requires a user decision: whether to carry it at all, and at what
  ceiling.** It changes public semantics — a document that parses today can
  raise. This round recommends and does not select. The alternative the user may
  prefer is no budget, accepting that a pathological grammar/document pair can
  spend `2^k`; the ladder is what that costs.

A ceiling on its own would be exactly the arbitrary cap the tasking rejects.
What keeps it honest is that it is the LAST lever, reached only after three
exact ones have been applied and measured, and that the refusal is
distinguishable from every other answer.

---

## 7 — the questions the report must answer

**1. Does the candidate agree with the occurrence-unrolled oracle on every
shared shape?** Yes, on all ten witnesses across duplicate slot, pending frame,
sibling memo (both its tree-object-only form and its chart-shared twin),
transparent synthetic, synthetic consumers, a mixed shared/non-shared
interaction, two accepting items, an unambiguous shared node, and a delegated
island option beneath a shared completion — in GBNF and ABNF. **Scoped** two
ways, both executed: to arm-choice families (splits never enter either lane),
and to shapes where a synthetic node is a consumer rather than the shared node
itself. And the agreement is on composition, not on family decomposition — the
two lanes share the chain-resolution primitives, and the one lane that does not
is unsound here.

**2. What identifies each consumption of a shared value?** The forest edge
`(consuming handle, family index, kid slot)`. The value is the packed handle
`(item, end)`. §A1 measures the gap: the derivation tree collapses the second
into the first, by two independent mechanisms.

**3. Does the current forest retain enough information?** Yes in the sense that
matters — nothing new must be RECORDED during recognition — but **not as a
ready-made edge**, and the difference is an implementation gate rather than a
non-issue. `cyclic_meaning.Edge` has no family index; production's
`forest/chart.py` has no parent→child edge at all, so the kid slot must be
recovered by re-resolving the binarised chain and the family index is an index
into an enumerated assignment produced by a fixpoint. Materialising the
occurrence triple is real work. What production must not do is key
occurrence-owned work on `id(ParseTree)`.

**4. What is exact-lane cost in terms of real option lanes?** Two factors, not
one. The APPLICATION count at a node is its local multiplicity
`m(h) = Σ_families Π_slots |set(child)|`. The WALL cost is that count times the
value-identity work each application triggers, which grows with the node's own
image — two rungs with an identical 1044 applications differ by two orders of
magnitude in CPU (§B1). The dirty cone bounds neither factor, and the stacked
control shows the total is not the root's product plus a linear tail.

**5. Which laws avoid enumeration without changing semantics?** `const` (the
occurrence is dropped before any product forms — Prototype 15), and
`ident`/`grow` composing to an accepting item, which reduces the question to one
witnessing node's family count: 2 applications against `2^k`, measured.
`finite(b)` bounds what a node RETAINS exactly and bounds no work; on the shipped
surfaces every bounded rule bounds to one, so it currently buys nothing.

**6. Is exponential work unavoidable, and what refusal is recommended?** An
exponential APPLICATION count is unavoidable — `Ω(m(h))`, with the witness in
§B4 — and no lever in this round reduces it. The recommended contract is §B7,
with two corrections this round had to make to its own first draft: the
exception must not be the type the partial-operation guard absorbs, and the unit
cannot be applications, because one application is not a fixed amount of work.
Adopting it, choosing its unit, and choosing its ceiling are user decisions.

**7. What remains an implementation gate, measurement gate, or user decision?**

- **Implementation gates.** (a) The partial-operation guard, §A6 — which needs a
  DISTINCT value-refusal exception first, and must keep "no meaning" separable
  from "settled". (b) Keying occurrence-owned work on the chart edge rather than
  `id(ParseTree)`, and the offsets pass's zero-width sharing, §A1. (c)
  Materialising the occurrence triple: no new recognition-time record, but the
  family index and kid slot are not readable off any existing edge, §A1. (d) A
  demand-driven family-resolved chart — it is built before dirtiness is known
  and is 68% of settle on an unambiguous document, §B6. (e) `ForestCtx`'s
  suspended-versus-cyclic confusion, §A3, which is a shipped defect rather than
  new work. (f) Carried unchanged from Prototype 15: the dirty-cone lane, the
  deliberate Earley escalation for an EXECUTE verdict on the predictive path,
  the retained island kernel and its release boundary, the exact channel index,
  and cache adoption into `parsing.caches`.
- **Measurement gates.** The exact lane on a production ambiguous input, beside
  the §12 RSS row; how often a real document makes a `finite`-over-wide-children
  node dirty on a shipped grammar; and every parse-performance comparison. None
  is answered here.
- **User decisions — four, not one.** An earlier draft named only the first and
  filed the rest as gates; each of these changes when a document parses or
  raises, which is public semantics.
  1. Whether production carries the §B7 resource refusal, in what UNIT (§B1
     shows applications is the wrong one), and at what ceiling.
  2. **Which value-identity relation is authoritative.** The candidate dedups on
     `repr`; this round's oracle uses production `same_value`. Which one holds
     decides when two derivations count as different meanings — i.e. when
     `parse()` refuses. They agree on every witness here; neither is costed.
  3. **Whether a fully-refusing node raises or yields no meaning.** §A6 shows the
     two lanes answering differently today. It decides whether such a document
     parses or raises.
  4. **Whether to adopt the declared-image quotient at all.** Per §B3 its
     composition is unvalidated, and a misdeclared or unsoundly composed bound
     silently narrows a meaning set — the "unambiguous" wrong answer. It
     currently buys nothing on the shipped surfaces, so declining it is free.

**8. Does anything obstruct the settled resolver contract?** No. This round
constructs no resolver pair, invokes no `resolve=`, and touches neither the
pair's scope nor its construction point. `resolve=` receives complete-document
pairs under both engines, built only after root inequality and an actual
invocation — unchanged, and preserved.

---

## 8 — what this round does not prove

- **The PDA path.** Nothing here executes the predictive runtime or
  `islands.island_parse`. Everything is Earley or Earley-delegated.
- **Parse performance.** No throughput measurement, no opcode stream, no frame
  shape, no allocation count, no RSS row. No parse regression is authorized.
- **The exact channel index.** `PROTOTYPE_14.md` §4's obligation is untouched and
  still load-bearing; §B3 states how it biases the static census.
- **A cyclic chart.** Both new modules refuse one by name to
  `cyclic_meaning.exact_meanings`. Shared occurrences inside a zero-width SCC are
  not exercised.
- **A shared node under the PDA's own occurrence identity.** The chart edge is
  the Earley occurrence; turning the PDA's `(arm, opcode index)` into a channel
  slot is the same coordinate join the channel-index obligation refuses.
- **Streaming below the root.** The streaming lane stops the ROOT's enumeration
  at a certified second meaning; a fully demand-driven variant that also stops a
  child's enumeration early is neither implemented nor claimed.
- **The declared-image quotient.** Never observed truncating a set, and its
  cross-slot product composition is unvalidated (§B3). Nothing in this round
  depends on it.
- **A negative control for the law lane.** No row exercises a marked node with
  no witness, where the certificate costs and then falls through.
- **The value-identity primitive.** §B1 measures the comparison COUNT; it does
  not cost a comparison, compare `repr` against `same_value`, or price a hashed
  alternative. Which relation is authoritative is user decision 2.
- **A real unambiguous-path measurement.** §B6's ratio is a 3-node chart with no
  floor control.
- **Value identity.** The candidate deduplicates on `repr` and this round's
  oracle on the production `same_value`; the two agree on every witness here,
  but neither is costed and production still owes a stated value-identity
  primitive with a stated cost.
- **The budget's ceiling.** §B7 executes the mechanism at a demonstration
  budget; no ceiling is proposed, because proposing one is the user decision.
- **Whether the shipped grammars reach the lower bound in practice.** The static
  census says most shipped rules are unbounded, which is where the product
  grows; it does not say how often a real document makes such a node dirty.

---

## 9 — commands and provenance

Sequential, one process at a time, no other benchmark, pool or agent alive.
Exit codes are the unpiped process status.

```text
uv run python proto/shared_occurrence_ambiguity.py    exit 0
uv run python proto/exact_lane_cost.py                exit 0

uv run ruff format / ruff check  (both new files)     clean
uv run pyright                   (both new files)     0 errors, 0 warnings
```

**Before/after file record.** Baseline taken before any write: 123 files under
`zzz_current_work/260826-target-shaped-parse/`, `git status --short` showing
only `PROMPT_16.md` (this round's tasking, replaced by the user before the round
began), and none of the six allowlisted targets present. The round writes only
allowlisted files; §10 of `P16_ADVERSARIAL.md` records the final comparison.

Forbidden-construct search over both new files found no builtin `eval`/`exec`
call, no `Any`, no `object` annotation, no `cast`, no `-> object`, no nested
`def` (every indented `def` is a class method: `__init__`, `retain`, `body`,
`eval`), no thread or multiprocessing import, and no `# type: ignore`, `# noqa`
or `# pylint: disable`. The only `.eval(` uses are the IR action-body protocol
method lexic itself defines — which is the point: the meanings here are produced
by the real authored operations.

---

## 10 — coordinator handoff

This round edits no active document. The following is for the coordinator to
apply, reject, or defer.

**Proved.**

- Occurrence-unrolled semantics is the meaning relation, and the candidate
  per-node relation already implements it: a shared value's set is computed
  once, each consuming slot ranges over it independently, occurrence-owned
  effects run per slot consumption (measured as body executions, 4 against 2
  expansions). Ten witnesses, two flavours, against an oracle independent in
  composition, memo policy, dedup and traversal — scoped to arm-choice families
  and to synthetic consumers rather than shared synthetic nodes.
- The occurrence identity is `(consuming handle, family index, kid slot)`. It is
  derivable from what the forest already holds — nothing new need be recorded
  during recognition — but it is not readable off any existing edge.
- A node consumed twice within one derivation is necessarily zero-width.
- The exact lane's APPLICATION count at one node is its local multiplicity.
  Its wall cost is that count times value-identity work, which is image-
  dependent — so an application count is not a cost, and a budget in that unit
  is unsound. The dirty cone bounds neither, and with a retaining consumer at
  every level the root is under half the total.
- Three exact levers: the `const` discard, the `ident`/`grow` certificate
  (question drops to one node's family count), and the certified-second-value
  stop. A declared finite image bounds retention, not work.
- Exponential exact APPLICATION counts are unavoidable for an admitted
  product: `Ω(m(h))`, with the late-second witness.
- The unambiguous path performs no application, retains no meaning and makes
  no value comparison — but it is NOT free: the family-resolved chart build is
  ~68% of settle there, and three more passes are uncharged.

**Disproved.**

- Prototype 15's key-global complete-fold oracle is not a valid control for a
  shared node whose own family choice sits inside its own chain: it loses
  meanings on six of nine witnesses.
- Prototype 15's description of the injective lane as costing "zero executed
  operations" is off by the local witness: it is two applications, measured.
- A compile-time refusal keyed on the declared image bound is not viable — it
  would refuse 82–99% of shipped rules.
- **A shipped defect:** `forest.ForestCtx`'s open-handle guard cannot tell a
  SUSPENDED shared handle from a cyclic one, so `forest.DERIVATIONS` truncates a
  zero-width node consumed at two slots of one derivation. On the duplicate-slot
  and pending-frame shapes it yields two derivations where the grammar derives
  four, and none of them is well-formed. Not in `CURRENT_BUG_REPORT.md`; the
  coordinator should decide whether it becomes a fourth pinned defect.

**Open gates — five new, and they must match §7.7 rather than summarise it.**

1. The partial-operation guard, which needs a DISTINCT value-refusal exception
   first and must keep "no meaning" separable from "settled" (§A6).
2. Chart-edge occurrence identity in `ModelFold.apply` and `fold._tree_offsets`,
   never `id(ParseTree)` (§A1).
3. Materialising the occurrence triple: nothing new need be recorded at
   recognition time, but the family index and kid slot are not readable off any
   existing edge (§A1).
4. A demand-driven family-resolved chart — it is built before dirtiness is known
   and is ~68% of settle on an unambiguous document (§B6).
5. `ForestCtx`'s suspended-versus-cyclic confusion (§A3) — a shipped defect
   rather than new work.

All Prototype 15 gates carry unchanged. Measurement gates are listed in §7.7.

**User decisions — four, all of them semantic.** Each changes when a document
parses or raises, so none is the investigator's to settle:

1. Whether production carries the §B7 resource refusal, **in what unit** (§B1
   shows applications is the wrong one), and at what ceiling.
2. Which value-identity relation is authoritative — the candidate's `repr` or
   production `same_value`. It decides when two derivations count as different
   meanings.
3. Whether a fully-refusing node raises or yields no meaning; the two lanes
   answer differently today (§A6).
4. Whether to adopt the declared-image quotient at all — its composition is
   unvalidated and a wrong bound narrows a meaning set silently (§B3).

Resolver scope is untouched and remains settled.

**Active-plan claims that should change** — listed for the coordinator, not
edited here:

| Document | Claim as it stands | What the evidence says |
|---|---|---|
| `TODO.md` §8 | `PLANNING REQUIRED BEFORE §8 — SHARED-OCCURRENCE COMPOSITION` unchecked | Closed by Part A; two new implementation items fall out |
| `TODO.md` §8 | `PLANNING REQUIRED BEFORE THE EXACT LANE LANDS — EXACT-LANE COST BOUND` unchecked, "state the bound" | Bound determined in Part B; what remains is the user decision in §B7, not a planning gate |
| `context.md` | "an occurrence-unrolled derivation oracle must verify … before the general composition claim closes" | The oracle exists and every shape agrees |
| `INDEX.md` | "Shared-occurrence composition is therefore an open planning gate" | Closed |
| `DESIGN.md` | dirty-cone paragraph states exactness is exponential without a bound | The bound is `m(h)`; the three exact levers and the lower bound are now measured |
| `goal.md` | "Occurrence-owned effects ride the parent's slot consumption" | Correct, and now executed; worth adding that the occurrence is the chart edge and never `id(ParseTree)` |
