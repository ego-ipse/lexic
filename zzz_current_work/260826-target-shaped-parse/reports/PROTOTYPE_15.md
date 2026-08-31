# Prototype 15 — the cached island→root continuation, composed

**Status:** the one missing composition proof, as corrected after Reviewer 1.
`proto/island_continuation.py` compiles one immutable continuation row per
contextual occurrence, lets the island READ that row before it enumerates
anything, settles the constant and injective cases from the row alone, composes
interacting occurrences exactly, and holds every witness — statically settled
ones included — against a control run and an independent complete-Earley-fold
oracle. No production source, test, harness or wiki file was changed:
`git status --short -- src tests pyproject.toml .wiki` is empty. One new
prototype; no other prototype was edited. No commit, no push, no worktree.
Every run was sequential, one process at a time, and no multithreaded row
exists anywhere in this round.

| File | Round-15 role |
|---|---|
| `proto/island_continuation.py` | new — compiles the per-occurrence continuation table, executes the six cases, and oracles every one of them against a full-enumeration control |

The mechanisms it composes are unchanged and are reused, not re-derived:
`operation_slot_laws.py` supplies the real-operation slot classifier and its
tables, `cyclic_meaning.py` supplies the family-aware chart, the component
check and the two reachability lanes, `island_alternate_seed.py` supplies the
real delegated outer run and the windowed island, `ambiguity_interaction.py`
owns the one-flip disproof, `resolver_pair.py` owns the occurrence-addressed
splice, and `route_continuation.py` owns the producer→contextual-child route
whose runtime shape the key mirrors.

---

## 1 — What is compiled, and what it is owned by

One row per **contextual occurrence** — a `(consumer clone, channel slot)`
pair — for one bound product:

```python
ContinuationKey(clone, slot, root, product)
Continuation(key, child, slot_kind, slot_bound, observable, injective, verdict)
```

- `clone` is the consuming contextual identity. Today's engine names a
  contextual identity by its **completed code**, and
  `codes.arm_rule[codes.code_arm[code]]` resolves that code to the rule the
  field spells; under contextual clones two clones of one rule take two codes
  and therefore two rows, without changing the table's shape.
- `slot` is the consumed child's channel slot, and it is load-bearing:
  `slot-discriminating` (§5) is one consumer rule whose slot 0 is dropped and
  whose slot 1 proves inequality. **Which** occurrence at parse time is the
  delegated `PayloadLeaf` object — the kernel injects one per delegated
  occurrence — which is what `resolver_pair.py` already splices on.
- `root` is the requested root; `product` is the bound product's residency
  token.

**The table is flat.**

```text
artefact-flatness  rows=4  flat_leaves=42  every leaf is an int or a
                   declaration string: no ParseTree, no kernel, no meaning, no
                   callable, so the table cannot retain a parse
```

The walk is typed `Flat = int | str | tuple[Flat, ...]`, so a table that ever
held a kernel, a derivation, a meaning or a callable would not type-check and
the walk would raise rather than count it.

**The table is owned, and its pin is deliberate.**

```text
artefact-lifetime  same_object_on_rebind=True
                   eviction_recomputes_equal_rows=True
                   distinct_reducer_gets_a_distinct_product=True
```

`parsing/caches.py` states the rule this registry obeys: a bare `dict` keyed on
`id(...)` must **pin** its key objects to stay correct against address reuse,
and a pinned key is an immortal key. The entry therefore holds the grammar and
the reducer strongly and re-checks identity on every hit; it lives until
`release_continuations` drops it. That is correct and mortal-by-request.

It is **not** the production protocol, and this round does not pretend
otherwise. `parsing.caches`' `memo`/`track` makes an entry die with a
weak-referenceable OWNER — and IR values are not weak-referenceable (`IrAst`
and `Reducer` both refuse `weakref.ref`), so production's owner is the
`CompiledGrammar` artefact, exactly as `cache_lifetime.py` proved. Production
adopts the continuation table into that protocol; §11 carries it as the
obligation it is. Eviction is compared modulo the residency token: the
recompiled rows are equal, which is what "eviction changes residency only"
claims.

---

## 2 — The certificate, stated precisely

Write `law(P, s)` for the class the **real authored body** of rule `P`
declares for its channel slot `s`, derived by `operation_slot_laws.Classifier`
over `OPERATION_LAWS`/`CONSTRUCTOR_LAWS` — the open type-keyed table with a
raising default. Let the **flow graph** be every `(parent, channel slot,
child)` reference edge of the normalized grammar, in channel coordinates (a
dropped child has no slot, which is the same answer as classifying it `const`).

**DROP — universal.** The value at `(P, s)` is unobservable at the requested
root when `law(P, s) == const`, **or** when no path from the root down to `P`
exists whose every edge is non-`const`. Both quantify over EVERY path in the
flow graph, which over-approximates the chart's realizable paths, so
"no grammar path" implies "no realizable path". Every derivation therefore maps
every value in that slot to one root meaning, whatever the other families do.
No baseline is ever inspected — this is not one-flip reasoning.

Its **rule-level** half is readable before any work: when every row into a
rule is unobservable, an island of that rule publishes its baseline and
enumerates nothing.

**INEQUALITY — existential, chart-verified.** When `law(P, s)` is `ident` or
`grow` and SOME flow path from the root to `P` uses only `ident`/`grow` edges,
the composed map from that slot to the root is injective along that path.
A grammar path need not be realized in a given parse, so the existential half
is **verified against the actual chart before it is used**: every realized
route from an accepting item down to THIS leaf object is enumerated and its own
per-step laws are composed. Fixing that route's families and varying only the
occurrence's value then constructs two distinct root meanings.

**EXECUTE — everything else.** The row settles nothing and the exact relation
runs: each node's set is its OWN packed families × its children's
**deduplicated** option sets. No global family assignment is formed.

**The over-approximation directions point opposite ways on purpose** and that
is the whole soundness argument: the drop test needs "no path anywhere", where
adding phantom paths can only withhold the shortcut; the inequality test needs
"one real path", where a phantom path would be unsound — which is why it is the
one lane that consults the chart.

### 2.1 Two refusals the certificate needs, and did not have

Both were added after Reviewer 1 and both are the conservative direction: a
refused law becomes `UNKNOWN`, which blocks the injective lane, does not block
the observable lane, and therefore only ever costs work.

**The channel-coordinate refusal.** The chart's chain slot counts child
completions of the NORMALIZED arm; the authored body's `IrArg(k)` indexes the
binding view's `fields_of`, which additionally splices a hoisted group's
interior and a quantified repeat's ELEMENTS into the parent channel
(`compile/reduce/fold.py::contribute`). Those coordinates disagree exactly
where normalization rewrote an arm, and the disagreement is input-dependent —
under `root ::= a b* c` with the body `IrArg(2)`, the authored index names `c`
at one repeat count and a `b` at another. `PROTOTYPE_14.md` §4 carries reading
the real channel as an open obligation and this round does **not** close it.
What it does instead is refuse: a rule keeps a law only when its canonical and
normalized contributing-reference sequences are identical arm for arm, so
every hoisted group and every quantified reference loses its law and falls to
the exact executed relation. A body that never indexes its channel — a splat,
a constant, a predicate — is splice-invariant and is exempt, because its class
is the same at every width.

**The focus-mapping refusal.** `operation_slot_laws._rule_each` classifies
`IrEach(IrArg(k))` as `grow` because the body carries the slot — but over an
EMPTY focus the result is the empty tuple for every slot value, so it is not
injective, and `differential_law`'s probe domain always supplies a non-empty
focus and cannot catch it. Prototype 14 used `grow` for a census; this module
uses it for a REFUSAL, so a body reaching `IrEach`, `IrChildren`, `IrRebuild`
or `IrAt` now gets no law at all.

§8's census is what those two refusals cost, measured.

---

## 3 — The six cases, executed, each against a control

Real grammar tables, the real windowed `island_run`, the real
`Kernel(delegates=...)` delegation seam, and real authored reducer bodies
evaluated through `IrSelf.eval` under a real `Reducer`.

**Every witness runs twice.** The second run hands the island an empty table,
so it enumerates every alternate the certificate would have skipped or dropped.
Three things are then required of every witness, including the ones the
certificate settles without computing a set:

- the exact per-node lane over the control run equals the control run's
  complete-Earley oracle (`exact_lane_matches_control_oracle`);
- the shortcut run's oracle equals the control run's, so skipping and dropping
  changed nothing observable at the requested root;
- the declared verdict follows from the control oracle's cardinality.

Verbatim run output, with the `flavour` column elided on the GBNF rows and
nothing else removed:

```text
uv run python proto/island_continuation.py

case 1 — a continuation constant in the island slot
  const-consumer   differs=False  reason=no-alternate  dropped_alternates=0
    skipped_enumerations=1  control_root_meanings=1  shortcut_root_meanings=1
    exact_lane_matches_control_oracle=True  one_flip_differs=False
    executed_products=0  multiplicity_nodes=0  chart_nodes=0  row_lookups=0
    descent_steps=0  document_recognitions=1  settlement_trees=0
    seed_trees=1  control_seed_trees=3  one_flip_trees=1  oracle_trees=1
    seeds=0  control_seeds=1
case 2 — an injectively retaining continuation
  injective-consumer  differs=True  reason=injective-route
    dropped_alternates=0  skipped_enumerations=0  control_root_meanings=2
    shortcut_root_meanings=2  exact_lane_matches_control_oracle=True
    one_flip_differs=True  executed_products=0  chart_nodes=0  row_lookups=3
    descent_steps=2  document_recognitions=1  settlement_trees=0
    seed_trees=3  control_seed_trees=3  seeds=1
case 3 — a finite continuation whose alternatives agree at the root
  finite-consumer-equal  differs=False  reason=executed
    control_root_meanings=1  exact_lane_matches_control_oracle=True
    one_flip_differs=False  executed_products=2  multiplicity_nodes=0
    chart_nodes=1  document_recognitions=1  settlement_trees=0  seeds=1
case 3 — a finite continuation whose alternatives differ at the root
  finite-consumer-differs  differs=True  reason=executed
    control_root_meanings=2  exact_lane_matches_control_oracle=True
    one_flip_differs=True  executed_products=2  multiplicity_nodes=1
    chart_nodes=1  document_recognitions=1  settlement_trees=0  seeds=1
case 4 — two island choices, invisible apart and visible together
  interacting-islands  differs=True  reason=executed  one_flip_differs=False
    control_root_meanings=2  exact_lane_matches_control_oracle=True
    executed_products=4  multiplicity_nodes=1  chart_nodes=1
    document_recognitions=1  settlement_trees=0  seeds=2
case 4 — three occurrences, one of them settled by the const row
  interacting-with-a-dropped-third  differs=True  reason=executed
    one_flip_differs=False  dropped_alternates=1  control_root_meanings=2
    exact_lane_matches_control_oracle=True  executed_products=7
    multiplicity_nodes=2  chart_nodes=3  row_lookups=7  descent_steps=9
    document_recognitions=1  settlement_trees=0  seeds=3
case 5 — one consumer rule whose two SLOTS settle differently
  slot-discriminating  differs=True  reason=injective-route
    dropped_alternates=1  control_root_meanings=2
    exact_lane_matches_control_oracle=True  executed_products=0
    chart_nodes=0  row_lookups=3  descent_steps=2  document_recognitions=1
    settlement_trees=0  seeds=2
case 5 — two sibling occurrences and a nested delegation
  sibling-and-nested  differs=True  reason=injective-route
    dropped_alternates=1  control_root_meanings=2
    exact_lane_matches_control_oracle=True  executed_products=0
    chart_nodes=0  row_lookups=4  descent_steps=6  document_recognitions=1
    settlement_trees=0  seeds=2
case 6 — no alternate, no execution, no graph, no tree
  unambiguous-control  differs=False  reason=no-alternate
    dropped_alternates=0  skipped_enumerations=0  control_root_meanings=1
    exact_lane_matches_control_oracle=True  one_flip_differs=False
    executed_products=0  multiplicity_nodes=0  chart_nodes=0  row_lookups=0
    descent_steps=0  document_recognitions=1  settlement_trees=0
    seed_trees=2  one_flip_trees=1  oracle_trees=1  seeds=0  control_seeds=0

  … and the same three cases again under ABNF: const-consumer-abnf
    (skipped_enumerations=1, seed_trees=1 against control_seed_trees=3),
    injective-consumer-abnf, interacting-islands-abnf — identical verdicts,
    identical oracle cardinalities, identical one-flip outcomes.
```

**Every count is attributed to a lane, and every lane has exactly one
producer.** All derivations go through one `build_tree` and all whole-document
recognitions through one `run_document`, so `settlement_trees=0` is a fact
about the code path rather than a counter nobody increments:
`seed_trees` is what publishing the island's seed cost, `one_flip_trees` what
the rejected comparison lane cost, `oracle_trees` what the oracle cost, and
`resolver_trees` what an invoked resolver cost (§6). `document_recognitions=1`
on every row: the document is recognized once, with the island delegated, and
never again.

### 3.1 The constant witness pays for nothing, rather than discarding afterwards

The `const` consumer is `wrap ::= t` with the authored action `IrStr("fixed")`
— the same shape shipped JSON already uses (`escape → IrStr("\\")`,
`true → IrInt(1)`) — classified by the real `IrAction(IrScalar,
LawRule("const"))` row and executed by the same body.

The island reads that row **before** it enumerates. Case 1 records
`skipped_enumerations=1` and `seed_trees=1` against the control's
`control_seed_trees=3`: the two alternate derivations are never built, and the
control confirms the requested-root meaning set is 1 either way. That is the
design's claim — the alternates are not paid for — rather than the weaker one
of discarding them after the fact.

The **occurrence-level** half is separately witnessed, because a rule
observable at one site and constant at another cannot be settled rule-wide:
`slot-discriminating` and `sibling-and-nested` both report
`dropped_alternates=1` with the other occurrence live.

### 3.2 The drop is executed per occurrence, not asserted

```text
drop-differential  const-consumer      occurrences=1  occurrences_the_rows_dropped=1
                   root_meanings_with_the_dropped_alternates_removed=1
                   root_meanings_with_every_alternate_admitted=1  equal=True
drop-differential  sibling-and-nested  occurrences=2  occurrences_the_rows_dropped=1
                   … 2 and 2  equal=True
drop-differential  slot-discriminating occurrences=2  occurrences_the_rows_dropped=1
                   … 2 and 2  equal=True
```

The island runs against the empty table so every alternate really exists, then
the exact lane runs twice: once with the dropped occurrences collapsed to their
baseline and every other occurrence admitted, once with all of them admitted.
An unsound drop shows up here as a set that grew — the failure a boolean
verdict comparison cannot see.

### 3.3 The semantics is the shipped reducer's, on the rows where that is
observable at all

```text
shipped-path  const-consumer       reduce=value  agree=True
              island_value_stands_in_the_shipped_value=False
shipped-path  unambiguous-control  reduce=value  agree=True
              shipped_value=IrTuple(IrTuple(IrStr('one')))
              island_value_stands_in_the_shipped_value=True
shipped-path  const-consumer-abnf  reduce=value  agree=True
              island_value_stands_in_the_shipped_value=False
```

Where the shipped `CompiledGrammar.reduce` returns a value on the same grammar
and the same authored `Reducer`, that value equals the mechanism's baseline —
a differential across two independent executions of one authored semantics (the
shipped path recognizes the whole document with no delegation and folds through
`ReduceFold`; this module folds packed chart handles under delegation). The
`island_value_stands_in_the_shipped_value` column separates a carrying
consumer from a constant one, and it is asserted against the compiled row
rather than merely printed.

**Where this differential is blind, and why it cannot be widened today.** The
shipped gate refuses on the generated MODEL, so any island with two derivations
refuses — even when both derivations mean the same reducer value (§7 is exactly
that case). `CompiledGrammar.reduce` has no `resolve=` channel today; adding it
is `goal.md`'s own public-surface work. So no shipped row can agree on a
document whose island CHOICE is live. That blindness is a property of the
shipped gate, not a missing witness, and §11 carries it.

### 3.4 Two flavours

`const-consumer`, `injective-consumer` and `interacting-islands` are repeated
with the same languages written in **ABNF** and compiled through
`ABNF_FLAVOUR`. Same verdicts, same oracle cardinalities, same one-flip
outcomes, same skip. Nothing in the compile step or the certificate reads a
flavour, a rule name or a grammar spelling.

---

## 4 — Interacting occurrences, without one-flip and without Cartesian
assignments

Case 4's root action is `IrCompare(IrArgs(), IrOp("=="), IrTuple(one, one))` —
a real predicate whose law is `finite(2)`. The island's two arms mean
`IrStr("one")` and `IrStr("two")`; the engine's own derivation makes `"two"`
the baseline at both occurrences. The witness pins that shape so it cannot rot:
the marker the root tests for must be the ALTERNATE at every occurrence, or the
case would collapse into an ordinary one-flip difference.

```text
interaction  one_flip_differs=False  exact_differs=True  root_meanings=2
             seeds=2  dropped_alternates=0  executed_products=4
             rejected_cartesian_assignment_count=4
interaction  … the same, under ABNF
interaction  one_flip_differs=False  exact_differs=True  root_meanings=2
             seeds=3  dropped_alternates=1  executed_products=7
             rejected_cartesian_assignment_count=8
```

Both one-flip comparisons equal the baseline; the joint choice differs; the
exact lane finds it. The one-flip lane is executed here **only** as the
comparison it is — `ambiguity_interaction.py` remains where it is disproven
against the shipped `another_meaning`.

**How the composition avoids enumerating assignments, and where it does not.**
A node's set is its own families × its children's *deduplicated* sets, so a node
every one of whose children is a singleton stays a singleton and costs one
operation. What that removes is **propagation**: multiplicity that meets and
collapses at one node does not multiply again above it. What it does **not**
remove is the local product at a node where k multiplicitous children meet —
that product is `Π` of their set sizes and is inherent to the exact relation,
not an artefact of this mechanism.

The three-occurrence row is where the certificate pays inside the composition:
the `const` row removes one occurrence before the product is formed, so the
meeting node's product is `2 × 1 × 2 = 4` instead of `2 × 2 × 2 = 8`. That is
the structural result, in one unit. The `executed_products` and
`rejected_cartesian_assignment_count` columns count different things — operation
applications and global assignments — and are not compared to each other.

These are structural counts on deliberately tiny charts. They answer a design
question and nothing else; no timing claim is made about any of them.

---

## 5 — Occurrence identity: two slots, two sites, and one nesting level

Three shapes, because the key has two per-occurrence halves and both must be
shown to be load-bearing.

**Two SLOTS of one consumer.** `slot-discriminating` is `root ::= t t` with the
authored action `IrArg(1)`: slot 0 classifies `const` and its occurrence is
dropped, slot 1 classifies `ident` and its occurrence proves inequality. A
table keyed on the consumer RULE alone cannot express that row.

**Two SITES of one island rule.** `sibling-and-nested` puts the same island
rule under `left ::= t` whose action is `IrStr("k")` and `right ::= t` whose
action is `IrBuild(IrTuple)`:

```text
occurrence-identity  outer_delegated_leaves=2  distinct_leaf_objects=True
                     occurrences_per_leaf=[1, 1]
                     distinct_continuation_keys=True
                     verdicts=['drop', 'injective']  outer_seeds_published=2
```

One delegated leaf per occurrence, each standing at exactly one position.

**One nesting level.** The same witness carries a nested delegated region
inside each island: the inner island publishes its own exact seed, the outer
island's enumeration takes it as a leaf option set, and the outer document's
continuation is unchanged. The addressed splice per delegation level is
`resolver_pair.py`'s established evidence and is not re-derived here.

---

## 6 — Semantic settlement versus resolver-tree materialization

Kept apart by construction and by lane counter:

- `const`, proved inequality without `resolve=`, and an actual-value comparison
  all run with `settlement_trees=0` and `document_recognitions=1` — the one
  delegated recognition and nothing more.
- Complete document `ParseTree`s are constructed **only** after root inequality
  and an actual resolver call:

```text
resolver-materialization  injective-consumer
  trees_before_the_resolver=0  trees_after_the_resolver=5
  recognitions_before_the_resolver=1  recognitions_after_the_resolver=1
  resolver_calls=1  chosen_root=root  pair_is_two_distinct_trees=True
```

The pair is spliced from the island kernel already in hand through
`resolver_pair.splice_leaf` and `resolver_pair.payload_leaves`; the recognition
count does not move. That splice, its zero-recognition property, and the
cold-recognition cost of the fused PDA alternative are Prototype 14's evidence
and are cited, not re-measured.

---

## 7 — A `goal.md` §5 divergence, now executable

`finite-consumer-equal` is a document whose two derivations build **different
generated models** but the **same reducer value**. The shipped `reduce`
refuses it; the exact requested-root relation accepts it.

```text
value-relation-divergence  finite-consumer-equal
  shipped_reduce=parsing: ambiguous input — two derivations that mean
    different things; supply a resolver to choose between them
  exact_root_meanings=1  exact_differs=False
```

This is **not** a fourth shipped defect: the shipped gate follows the relation
the engine currently declares (the variant model), and `goal.md` already rules
the definitive reduced-root value relation its successor and requires the
differences to be enumerated at §5. It is one such difference, executed rather
than described.

---

## 8 — What the certificate settles on the shipped grammars

A scale row, deliberately not a claim, and it is the price of §2.1's two
refusals stated honestly:

```text
row-census  gbnf  rows=170  verdicts={'drop': 8, 'execute': 162}
                  slot_classes={'grow': 17, 'ident': 66, 'unknown': 87}
row-census  abnf  rows=138  verdicts={'drop': 6, 'execute': 102, 'injective': 30}
                  slot_classes={'finite': 1, 'grow': 16, 'ident': 29, 'unknown': 92}
row-census  ebnf  rows=90   verdicts={'drop': 4, 'execute': 86}
                  slot_classes={'grow': 12, 'ident': 34, 'unknown': 44}
row-census  json  rows=60   verdicts={'drop': 2, 'execute': 48, 'injective': 10}
                  slot_classes={'finite': 5, 'grow': 4, 'ident': 8, 'unknown': 43}
row-census  cpu=0.045205
```

Read it plainly. `unknown` is the largest column everywhere and it grew when
the channel-coordinate refusal landed: on GBNF the injective verdicts went to
zero, because every rule normalization rewrote lost its law. The `unknown`
population is `PROTOTYPE_14.md` §1.3's — the reducer's `YIELD` default over a
focus with a dropped rule below it, scalar decodes over slot-carrying values,
the `IrArg(-1)`/`IrTypeMap` shapes — plus the two new refusals. Those rows fall
to EXECUTE, which costs work, not correctness.

So: **on the recursive shipped grammars the shortcut is a small minority of
rows, and closing `PROTOTYPE_14.md` §4's "exact channel index" obligation — 
reading the binding view's real `fields_of` — is what would widen it.** What
the census does establish is that the compile step is real, total, and cheap
enough (0.045 s process CPU for all four surfaces) to be artefact-owned rather
than recomputed. It establishes nothing about how often the shortcut fires on a
production document; that is a §12 measurement.

---

## 9 — The oracle, and the precondition it rests on

Every candidate result is compared with **independent complete Earley folds
over all small families**: for every accepting item and every global family
assignment, a real `FastTree` derivation is built and folded over the tree with
the same real reducer, once per delegated-occurrence option combination, and
the deduplicated union is the exact root meaning set. The comparison is
order-free, and it runs on **every** witness through the control run — not only
on the ones the certificate left to the executed lane.

**Independence, scoped.** For the OUTER document the oracle is independent in
traversal (real `ParseTree` versus packed chart handles) and in enumeration
(global assignments versus per-node products). For the ISLAND it is not: the
island's own exact set is enumerated by the same function that publishes the
seed, because that set IS the seed. Computing it incrementally is
`PROTOTYPE_10.md`/`PROTOTYPE_12.md`'s question, not this round's, and its cost
appears in the `seed_trees` column, separate from every other lane.

**The precondition, checked rather than assumed.** The mechanism gives every
OCCURRENCE its own family choice; the oracle fixes one family per KEY across a
whole derivation. Those relations coincide exactly when no node — and so no
arm-choice key — is reachable twice inside one derivation, and that is checked
on every witness:

```text
oracle-precondition  <witness>  chart_nodes=1..3  nodes_with_two_parents=0
                     keys_claimed_twice=0
```

Where it would fail, the per-node relation is the DESIGN's (each occurrence
derives independently) and the global-assignment enumeration is the narrower
one; the oracle would have to change, and no witness here exercises that shape.
§11 carries it.

**The cyclic boundary.** The mechanism refuses a cyclic chart with words and
names `cyclic_meaning.exact_meanings` as its owner. Every witness is acyclic and
the refusal is checked on every run.

---

## 10 — The questions the round had to answer

**1. Can static `const` and injective laws settle their cases without
propagating general ambiguity state?** Yes, with one asymmetry that matters.
`const` is fully static and now settles BEFORE the work it avoids: case 1
records `skipped_enumerations=1` and `seed_trees=1` against a control's 3, with
`chart_nodes=0`, `executed_products=0`, `row_lookups=0` and `descent_steps=0` —
no chart structure, no meaning, no baseline. The injective case is static in
its LAW but needs the realized route, because a grammar path is an
over-approximation: case 2 settles at `executed_products=0`, `chart_nodes=0`,
`settlement_trees=0` after two descent steps. Neither builds a dependency
index, an overlay, a meaning memo or a tree.

**2. What exact runtime data remains for a non-injective continuation?**
Exactly two things, both parse-local: the occurrence's option list (baseline
plus its alternates, published by the island as its cold seed), and one
deduplicated meaning set per chart node on the union of the live continuations.
Nodes outside stay singletons. The largest row is `chart_nodes=3`,
`multiplicity_nodes=2`, `executed_products=7`. Nothing else: no callback, no
witness graph, no retained kernel.

**3. How are interacting choices composed without Cartesian assignment
enumeration or unsound one-flip pruning?** By the per-node product over
deduplicated child sets, described in §4 with its limit stated: propagation is
removed, the local product at a meeting node is not. The certificate reduces
that local product by removing occurrences it can prove unobservable before the
product is formed (`2 × 1 × 2` instead of `2 × 2 × 2`). No alternative is ever
discarded for equalling the baseline under the other choices' baseline values.

**4. What is cached once, what is parse-local, and when is each released?**
Cached once per bound product: the continuation table — flat rows, pinned key,
same object on rebind, equal rows after eviction. Parse-local: the island
seeds, the leaf option lists, the node meaning sets, the route descents, and
(only after inequality and an invoked resolver) the two derivations. They die
with the settlement; the artefact is structurally incapable of holding them.
The table's own mortality is production's `parsing.caches` protocol, which §11
carries.

**5. Does ordinary island recognition remain local and byte-for-byte outside
the prototype?** Yes as far as this round can show it, and no further. `src` is
untouched. The unambiguous control publishes no seed and performs no lookup,
descent, chart walk, execution or tree build, and its shipped-path row returns
the same value the mechanism computes with the island's own meaning standing
inside it. What this does NOT show is the landed runtime's opcode stream:
whether adding the seed lane leaves the unambiguous island splice
byte-for-byte identical is a §4/§8 source measurement against the opcode
comparison `TODO.md` already schedules.

**6. After this proof, what precisely remains of the resolver-scope user
decision?** All of it. This round changes the decision's *inputs* in exactly
one way: semantic settlement — refusal, acceptance, and the discard of an
unobservable alternate — needs **no** derivation pair at any scope, so the
scope question is confined to what an invoked `resolve=` is handed. Everything
Prototype 14 §2 tabulated is unchanged: the pair root, the deferred
per-occurrence state a document-rooted pair needs, the fused PDA's one cold
document-linear recognition, and the fact that the two scopes ask different
questions under a dropping parent. Nothing here selects a scope, and nothing
here should be read as a recommendation.

**7. Is any planning or prototype gate still open before source
implementation?** For the island-continuation composition: no. The mechanism,
its certificate, its two refusals, its ownership, its interaction rule, its
control and its oracle are executable. What §2.1 refuses is not a gate this
round left open — it is `PROTOTYPE_14.md` §4's channel-index obligation, whose
CONSEQUENCE this round makes concrete: until production reads the real channel,
the shortcut does not fire on a rewritten arm. Everything else that was open
stays open and is listed in §11. The resolver-scope USER DECISION remains the
one gate that blocks §8.

---

## 11 — What this round does not prove

Stated separately from the results above, because the composition is external
and cannot reach any of it.

- **The exact channel index.** `PROTOTYPE_14.md` §4's obligation is untouched
  and is now load-bearing: the certificate refuses every rule whose canonical
  and normalized contributing references differ, so hoisted groups and
  quantified repeats get no shortcut at all. Production must read the binding
  view's `fields_of` to widen it, and §8's census is what the refusal costs
  today.
- **Cache mortality.** The registry pins its keys, which is correct and
  immortal-until-released. Adopting the continuation table into
  `parsing.caches`' `memo`/`track`/`release` under the `CompiledGrammar` owner
  is production work; `cache_lifetime.py` proved that protocol and this module
  does not re-derive it.
- **The production hot path.** No opcode stream, no frame shape, no allocation
  count from the landed runtime. "An unambiguous parse allocates no alternate,
  no set, no graph, no tree" is proved of THIS mechanism, not of future source;
  `TODO.md` §8/§12 own that as production evidence.
- **Memory.** No RSS row. The ambiguous-input RSS row, completion-time dense
  numbering, and the integrated flat dependency index remain exactly the
  §8/§12 gates `PROTOTYPE_13.md` left open.
- **Parse performance.** Nothing here is a throughput measurement and no parse
  regression is authorized by this report. The structural comparison the
  quantified-nullable bugfix needs is `PROTOTYPE_14.md` §5's and has not been
  run.
- **Locating the occurrence.** The prototype's root-down descent is a
  stand-in. Production does not search: the island is entered FROM its
  contextual clone, so the key is in hand at island entry — the PDA frame holds
  it and the Earley waiter's packed code is it. The descent is pruned by the
  compiled rows' own reachability, but its counts are not a production cost.
  The prototype's rule-level skip is therefore weaker than production's: an
  Earley delegate does not receive the consumer, so only the rule-wide half can
  fire before enumeration, while production has the per-occurrence row at
  entry.
- **The shipped-value differential's reach.** It can only agree where the
  shipped model gate does not refuse, which excludes every document whose
  island choice is live. Widening it needs `reduce(..., resolve=)`, which is
  `goal.md`'s own public-surface work.
- **The per-node versus per-assignment precondition.** Checked on every witness
  and true on all of them; a chart where a key is reachable twice is not
  exercised, and there the oracle — not the mechanism — is the narrower
  relation.
- **Cyclic charts.** Refused by name and handed to `cyclic_meaning`. The
  composition of an island continuation with a zero-width component is not
  exercised.
- **`YIELD` and the emit families.** Every witness action is checked to be
  focus-free, so the drop-aware text view never arises. Prototype 14's `YIELD`
  span-proof obligation and its emit-family law rows are untouched.
- **Contextual clones.** The key is written for them and the code→rule mapping
  is a source fact, but no contextual clone exists in `src` today, so the
  two-clones-two-rows behaviour is argued from the mapping, not executed.
- **The product operations that do not exist yet.** Collection finish, root
  finalization, meaning comparison and keyed-accumulation finish are still
  target-supplied and still absent; each must add a law row and pass
  `differential_law` before the compiler may schedule it.

---

## 12 — Commands and provenance

Every row ran sequentially in this repository, one process at a time, with no
other benchmark, pool or agent alive. Exit codes are the unpiped process
status.

```text
uv run python proto/island_continuation.py          exit 0

uv run python proto/operation_slot_laws.py          exit 0
uv run python proto/route_continuation.py           exit 0
uv run python proto/root_meaning_incremental.py     exit 0
uv run python proto/island_alternate_seed.py        exit 0
uv run python proto/ambiguity_interaction.py        exit 0
uv run python proto/resolver_pair.py                exit 0

uv run ruff format  proto/island_continuation.py    reformatted
uv run isort        proto/island_continuation.py    sorted
uv run ruff check   proto/island_continuation.py    All checks passed!
uv run pyright      proto/island_continuation.py    0 errors, 0 warnings

git status --short -- src tests pyproject.toml .wiki   empty
git diff --check                                       clean
```

**What the working tree does contain.** `git status --short` is NOT empty and
is not claimed to be. The effort's active documents are tracked and modified,
because they are this round's fold: `INDEX.md`, `context.md`, `goal.md`,
`DESIGN.md`, `TODO.md`, `LEDGER.md`. The round's new files —
`reports/PROTOTYPE_15.md`, `reports/P15_ADVERSARIAL.md`,
`reports/REVIEW_15.md`, `proto/island_continuation.py` — are untracked, since
`zzz_current_work/` is gitignored apart from what was force-added. Nothing
under `src`, `tests`, `pyproject.toml` or `.wiki` changed. Importing
`resolver_pair` regenerates its tracked `__pycache__` entry; it is restored
with `git checkout` at the end of the round, after the last run.

The five named prototypes were rerun for provenance; none was edited.

Forbidden-construct search over the new file found no `eval`/`exec` builtin
call, no `Any`, no `object`, no `cast`, no `-> object`, no nested `def`, and no
`# type: ignore`, `# noqa` or `# pylint: disable`. The only `.eval(` uses are
the IR action-body protocol method lexic itself defines — which is the point:
the meanings in this module are produced by the real authored operations.
