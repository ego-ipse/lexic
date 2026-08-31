# Prototype 15 — the cached island→root continuation, composed

**Status:** the one missing composition proof, as corrected after Reviewers 1
and 2. `proto/island_continuation.py` compiles one immutable continuation row
per contextual occurrence, lets the island read the table before it enumerates
anything, settles the constant and injective cases from the rows alone,
composes interacting occurrences exactly over a dirty cone, and holds every
witness — statically settled ones included — against a full-enumeration control
and an independent complete-Earley-fold oracle. No production source, test,
harness or wiki file was changed:
`git status --short -- src tests pyproject.toml .wiki` is empty. One new
prototype; no other prototype was edited. No commit, no push, no worktree.
Every run was sequential, one process at a time, and no multithreaded row
exists anywhere in this round.

| File | Round-15 role |
|---|---|
| `proto/island_continuation.py` | new — compiles the per-occurrence continuation table, executes the cases, and oracles every one against a full-enumeration control |

The mechanisms it composes are reused, not re-derived: `operation_slot_laws.py`
supplies the real-operation slot classifier and its tables, `cyclic_meaning.py`
the family-aware chart and the two reachability lanes,
`island_alternate_seed.py` the real delegated outer run and the windowed
island, `ambiguity_interaction.py` the one-flip disproof, `resolver_pair.py`
the occurrence-addressed splice, and `route_continuation.py` the
producer→contextual-child route whose runtime shape the key mirrors.

**What engine this is.** The outer document runs through the real Earley kernel
with the island **Earley-delegated** (`Kernel(..., delegates=...)`), which is
`island_alternate_seed.py`'s established seam and the same delegation
production uses from the PDA. It is not the PDA island entry
(`pda/runtime/kernel/execution.py::_island` → `islands.island_parse`), and
nothing here executes the predictive runtime. Every claim below is about the
Earley-delegated composition; §11 carries what that cannot reach — including
that `pda/runtime/kernel/kernel.py` records zero measured `OP_ISLAND` steps
across the benchmark, so the PDA island's own frequency is not a thing this
round can speak to.

---

## 1 — What is compiled, and what it is owned by

One row per **contextual occurrence** — a `(consumer clone, channel slot)`
pair — for one bound product:

```python
ContinuationKey(clone, slot, root, product)
Continuation(key, child, slot_kind, slot_bound, observable, injective, verdict)
```

- `clone` is the consuming contextual identity. Today's engine names one by its
  **completed code**, and `codes.arm_rule[codes.code_arm[code]]` resolves that
  code to the rule the field spells; under contextual clones two clones of one
  rule take two codes and therefore two rows.
- `slot` is the consumed child's channel slot, and it is load-bearing:
  `slot-discriminating` (§5) is one consumer rule whose slot 0 is dropped and
  whose slot 1 proves inequality. **Which** occurrence at parse time is the
  delegated `PayloadLeaf` object — one per delegated occurrence.
- `root` is the requested root; `product` is the bound product's residency
  token.

**The table is flat.**

```text
artefact-flatness  rows=4  flat_leaves=42  every leaf is an int or a
                   declaration string: no ParseTree, no kernel, no meaning, no
                   callable, so the table cannot retain a parse
```

The walk is typed `Flat = int | str | tuple[Flat, ...]`, so a table that ever
held a kernel, a derivation, a meaning or a callable would not type-check.

**The table is owned, its pin is deliberate, and its residency is metered.**

```text
artefact-lifetime    same_object_on_rebind=True
                     eviction_recomputes_equal_rows=True
                     distinct_reducer_gets_a_distinct_product=True
registry-residency   entries_after_the_run=13  distinct_bound_products=13
                     entries_after_release=0
```

`parsing/caches.py` states the rule this registry obeys: a bare `dict` keyed on
`id(...)` must **pin** its key objects to stay correct against address reuse,
and a pinned key is an immortal key. The entry holds the grammar and the
reducer strongly and re-checks identity on every hit; it lives until
`release_continuations` drops it. One entry per bound product, thirteen for the
thirteen witnesses, and release drains every one — the same meter
`caches.cached_entries()` exists to provide.

It is **not** the production protocol. `parsing.caches`' `memo`/`track` makes
an entry die with a weak-referenceable OWNER, and IR values are not
weak-referenceable (`IrAst` and `Reducer` both refuse `weakref.ref`), so
production's owner is the `CompiledGrammar` artefact, exactly as
`cache_lifetime.py` proved. Adoption is §11's obligation.

---

## 2 — The certificate, stated precisely

Write `law(P, s)` for the class the **real authored body** of rule `P` declares
for its channel slot `s`, derived by `operation_slot_laws.Classifier` over
`OPERATION_LAWS`/`CONSTRUCTOR_LAWS` — the open type-keyed table with a raising
default. Let the **flow graph** be every `(parent, channel slot, child)`
reference edge of the normalized grammar, in channel coordinates.

**DROP — universal.** The value at `(P, s)` is unobservable at the requested
root when `law(P, s) == const`, **or** when no path from the root down to `P`
exists whose every edge is non-`const`. Both quantify over EVERY path in the
flow graph, which over-approximates the chart's realizable paths, so "no
grammar path" implies "no realizable path". No baseline is ever inspected.

Its **rule-wide** half is readable before any work: when every row into a rule
is unobservable, an island of that rule publishes its baseline and forms no
set. That is the only half a delegate can read, because an Earley delegate is
not told which occurrence invoked it; the per-occurrence half is read at
settlement (§11 carries the gap, and production — entering the island from its
contextual clone — has the per-occurrence row at entry).

**INEQUALITY — existential, chart-verified.** When `law(P, s)` is `ident` or
`grow` and SOME flow path from the root to `P` uses only `ident`/`grow` edges,
the composed map from that slot to the root is injective along that path. A
grammar path need not be realized in a given parse, so the existential half is
**verified against the actual chart before use**: every realized route from an
accepting item down to THIS leaf object is enumerated and its per-step laws
composed.

**EXECUTE — everything else.** The row settles nothing and the exact relation
runs (§3.5).

**The over-approximation directions point opposite ways on purpose** and that
is the soundness argument: the drop test needs "no path anywhere", where
phantom paths can only withhold the shortcut; the inequality test needs "one
real path", where a phantom path would be unsound — which is why it is the one
lane that consults the chart.

### 2.1 Two refusals the certificate needs

Both are the conservative direction: a refused law becomes `UNKNOWN`, which
blocks the injective lane, does not block the observable lane, and so only ever
costs work.

**The channel-coordinate refusal.** The chart's chain slot counts child
completions of the NORMALIZED arm; the authored body's `IrArg(k)` indexes the
binding view's `fields_of`, which additionally splices a hoisted group's
interior and a quantified repeat's ELEMENTS into the parent channel
(`compile/reduce/fold.py::contribute`). Those coordinates disagree exactly
where normalization rewrote an arm, and the disagreement is input-dependent —
under `root ::= a b* c` with the body `IrArg(2)`, the authored index names `c`
at one repeat count and a `b` at another. `PROTOTYPE_14.md` §4 carries reading
the real channel as an open obligation and this round does **not** close it.
It refuses instead: a rule keeps a law only when its canonical and normalized
contributing-reference sequences are identical arm for arm. A body that never
indexes its channel — a splat, a constant, a predicate — is splice-invariant
and exempt.

**The focus-mapping refusal.** `operation_slot_laws._rule_each` classifies
`IrEach(IrArg(k))` as `grow` because the body carries the slot — but over an
EMPTY focus the result is the empty tuple for every slot value, so it is not
injective, and `differential_law`'s probe domain always supplies a non-empty
focus. Prototype 14 used `grow` for a census; this module uses it for a
REFUSAL, so a body reaching `IrEach`, `IrChildren`, `IrRebuild` or `IrAt` gets
no law.

§8 is what those two refusals cost, measured.

---

## 3 — The cases, executed, each against a control

Real grammar tables, the real windowed `island_run`, the real
`Kernel(delegates=...)` delegation seam, and real authored reducer bodies
evaluated through `IrSelf.eval` under a real `Reducer`.

**Every witness runs twice.** The control run hands the island an empty table,
so it forms every alternate the certificate would have skipped or dropped.
Three things are required of every witness, including the ones settled without
computing a set: the exact per-node lane over the control run equals that run's
complete-Earley oracle; the shortcut run's oracle equals the control's; and the
declared verdict follows from the control oracle's cardinality.

Run output. **Columns shown**: `differs`, `reason`, `dropped_alternates`,
`skipped_enumerations`, `control_root_meanings`,
`exact_lane_matches_control_oracle`, `one_flip_differs`, `settlement_products`,
`settlement_chart_nodes`, `settlement_dirty_nodes`, `seed_chart_nodes`,
`seed_products`, `seed_trees`, `settlement_trees`, `document_recognitions`,
`retained_island_kernels`, `seeds`. **Columns elided**: `flavour` on the GBNF
rows, `shortcut_root_meanings` (equal to `control_root_meanings` on every row),
`settlement_baseline_products` (equal to `settlement_chart_nodes` on every
row), `seed_baseline_products` (equal to `seed_chart_nodes`),
`control_seed_trees`/`control_seed_products` (equal to their shortcut twins),
`multiplicity_nodes`, `row_lookups`, `descent_steps`, `one_flip_trees`,
`oracle_trees`, and `control_seeds` — which does differ from the shown `seeds`
on `const-consumer` and `const-consumer-abnf` (1 against 0), in the direction
that UNDERSTATES the skip: the control formed an alternate the shortcut run
never built. The other elided columns —
`multiplicity_nodes`, `row_lookups`, `descent_steps`, `one_flip_trees`,
`oracle_trees` — are cost counters with no equal among the columns shown; none
of them contradicts a shown column, and they are cut for width, not for
flattery. `interacting-with-a-dropped-third` is the row where they are largest:
`row_lookups=7`, `descent_steps=9`, `multiplicity_nodes=2`, `one_flip_trees=4`,
`oracle_trees=1`.

```text
uv run python proto/island_continuation.py

1  const-consumer      differs=False reason=no-alternate      dropped=0 skipped=1
   control_root_meanings=1  exact_lane_matches_control_oracle=True
   one_flip=False  settlement_products=0 settlement_chart_nodes=0 dirty=0
   seed_chart_nodes=0 seed_products=0 seed_trees=1 settlement_trees=0
   document_recognitions=1 retained_island_kernels=0 seeds=0
2  injective-consumer  differs=True  reason=injective-route   dropped=0 skipped=0
   control_root_meanings=2  exact_lane_matches_control_oracle=True
   one_flip=True   settlement_products=0 settlement_chart_nodes=0 dirty=0
   seed_chart_nodes=4 seed_products=0 seed_trees=1 settlement_trees=0
   document_recognitions=1 retained_island_kernels=1 seeds=1
3a finite-consumer-equal    differs=False reason=executed     dropped=0 skipped=0
   control_root_meanings=1  exact_lane_matches_control_oracle=True
   one_flip=False  settlement_products=2 settlement_chart_nodes=1 dirty=1
   seed_chart_nodes=4 seed_products=0 seed_trees=1 settlement_trees=0
   document_recognitions=1 retained_island_kernels=1 seeds=1
3b finite-consumer-differs  differs=True  reason=executed     dropped=0 skipped=0
   control_root_meanings=2  exact_lane_matches_control_oracle=True
   one_flip=True   settlement_products=2 settlement_chart_nodes=1 dirty=1
   seed_chart_nodes=4 seed_products=0 seed_trees=1 settlement_trees=0
   document_recognitions=1 retained_island_kernels=1 seeds=1
3c distant-island           differs=True  reason=executed     dropped=0 skipped=0
   control_root_meanings=2  exact_lane_matches_control_oracle=True
   one_flip=True   settlement_products=2 settlement_chart_nodes=161 dirty=1
   seed_chart_nodes=4 seed_products=0 seed_trees=1 settlement_trees=0
   document_recognitions=1 retained_island_kernels=1 seeds=1
4a interacting-islands      differs=True  reason=executed     dropped=0 skipped=0
   control_root_meanings=2  exact_lane_matches_control_oracle=True
   one_flip=False  settlement_products=4 settlement_chart_nodes=1 dirty=1
   seed_chart_nodes=8 seed_products=0 seed_trees=2 settlement_trees=0
   document_recognitions=1 retained_island_kernels=2 seeds=2
4b interacting-with-a-dropped-third  differs=True reason=executed dropped=1 skipped=0
   control_root_meanings=2  exact_lane_matches_control_oracle=True
   one_flip=False  settlement_products=6 settlement_chart_nodes=3 dirty=2
   seed_chart_nodes=12 seed_products=0 seed_trees=3 settlement_trees=0
   document_recognitions=1 retained_island_kernels=3 seeds=3
5a slot-discriminating      differs=True  reason=injective-route dropped=1 skipped=0
   control_root_meanings=2  exact_lane_matches_control_oracle=True
   one_flip=True   settlement_products=0 settlement_chart_nodes=0 dirty=0
   seed_chart_nodes=8 seed_products=0 seed_trees=2 settlement_trees=0
   document_recognitions=1 retained_island_kernels=2 seeds=2
5b sibling-and-nested       differs=True  reason=injective-route dropped=1 skipped=0
   control_root_meanings=2  exact_lane_matches_control_oracle=True
   one_flip=True   settlement_products=0 settlement_chart_nodes=0 dirty=0
   seed_chart_nodes=10 seed_products=4 seed_trees=4 settlement_trees=0
   document_recognitions=1 retained_island_kernels=4 seeds=2
6  unambiguous-control      differs=False reason=no-alternate dropped=0 skipped=0
   control_root_meanings=1  exact_lane_matches_control_oracle=True
   one_flip=False  settlement_products=0 settlement_chart_nodes=0 dirty=0
   seed_chart_nodes=1 seed_products=0 seed_trees=1 settlement_trees=0
   document_recognitions=1 retained_island_kernels=0 seeds=0

   … and cases 1, 2 and 4a again under ABNF: const-consumer-abnf
     (skipped=1, seed_chart_nodes=0, seed_trees=1),
     injective-consumer-abnf, interacting-islands-abnf — identical verdicts,
     identical oracle cardinalities, identical one-flip outcomes.
```

**Every count is attributed to a lane, and every lane has one producer.** All
derivations go through one `build_tree`, all whole-document recognitions
through one `run_document`, and every meaning application through one
`Counters.product`, so `settlement_trees=0` is a fact about the code path.
`document_recognitions=1` everywhere: the document is recognized once, with the
island delegated, and never again.

### 3.1 The constant witness pays for nothing

The `const` consumer is `wrap ::= t` with the authored action `IrStr("fixed")`
— the same shape shipped JSON already uses (`escape → IrStr("\\")`) —
classified by the real `IrAction(IrScalar, LawRule("const"))` row and executed
by the same body.

The island reads the table **before** it forms a set. Case 1 records
`skipped_enumerations=1`, `seed_chart_nodes=0`, `seed_products=0` and `seeds=0`
against the control run's `control_seeds=1` — the control forms the alternate
and walks the island chart; the shortcut run does neither. Both runs build the
one derivation `islands.island_parse` builds today
(`seed_trees=1` = `control_seed_trees=1`), so what the row saves is the set
work, not a tree.

The **occurrence-level** half is separately witnessed, because a rule
observable at one site and constant at another cannot be settled rule-wide:
`slot-discriminating` and `sibling-and-nested` report `dropped_alternates=1`
with the other occurrence live.

### 3.2 The drop is executed per occurrence, not asserted

```text
drop-differential  const-consumer      occurrences=1 dropped_by_the_rows=1
                   with_dropped_removed=1  with_all_admitted=1  equal=True
drop-differential  sibling-and-nested  occurrences=2 dropped_by_the_rows=1
                   2 and 2  equal=True
drop-differential  slot-discriminating occurrences=2 dropped_by_the_rows=1
                   2 and 2  equal=True
```

The island runs against the empty table so every alternate exists, then the
exact lane runs twice: once with the dropped occurrences collapsed to their
baseline and every other occurrence admitted, once with all admitted. An
unsound drop shows up as a set that grew.

### 3.3 The semantics is the shipped reducer's, where that is observable

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
and reducer, that value equals the mechanism's baseline — a differential across
two independent executions of one authored semantics. The
`island_value_stands_in_the_shipped_value` column separates a carrying consumer
from a constant one and is asserted against the compiled row.

**Where this is blind, and why it cannot be widened today.** The shipped gate
refuses on the generated MODEL, so any island with two derivations refuses —
even when both mean the same reducer value (§7). `reduce` has no `resolve=`
channel today; adding it is `goal.md`'s own public-surface work. So no shipped
row can agree on a document whose island CHOICE is live. §11 carries it.

### 3.4 Two flavours

Cases 1, 2 and 4a repeat with the same languages written in **ABNF** through
`ABNF_FLAVOUR`: same verdicts, same oracle cardinalities, same one-flip
outcomes, same skip. Nothing in the compile step or the certificate reads a
flavour, a rule name or a grammar spelling.

### 3.5 What is document-wide, and what is not

The EXECUTE lane needs the family-aware chart, and building it is document-wide
— `distant-island` reports `settlement_chart_nodes=161` for an 81-character
document. Three separate facts keep that honest:

- **Every node is folded once to its baseline meaning.** That fold IS the
  parse's own product — the value it would build with no ambiguity machinery
  at all — and it is counted in its own lane
  (`settlement_baseline_products=161`, equal to the node count) precisely so it
  is not read as ambiguity cost.
- **The SET lane runs only on the dirty cone** — the upward closure of nodes
  that hold a live occurrence or carry more than one family. Every node outside
  has only non-dirty descendants, so its set is its baseline.
  `distant-island` reports `settlement_dirty_nodes=1` and
  `settlement_products=2`: the ambiguity machinery costs two operation
  applications on a 161-node chart, and pads the document without growing.
- **The chart is Earley's.** A PDA-first parse holds no SPPF
  (`parsing/products.py` reaches Earley only on `PdaFail`), so an EXECUTE
  verdict on the predictive path means escalating to Earley. `DESIGN.md`
  already routes a real predictive ambiguity to Earley; what this round adds is
  that the CONST and INJECTIVE rows settle **without** that chart — cases 1, 2,
  5a and 5b all report `settlement_chart_nodes=0`. §8's census says those rows
  are the minority on shipped grammars, so on those grammars most ambiguous
  spans would escalate. §11 carries it.

---

## 4 — Interacting occurrences, without one-flip and without Cartesian
assignments

Case 4's root action is `IrCompare(IrArgs(), IrOp("=="), IrTuple(one, one))` —
a real predicate whose law is `finite(2)`. The witness pins its own shape: the
marker the root tests for must be the ALTERNATE at every occurrence, or the
case would collapse into an ordinary one-flip difference.

```text
interaction  one_flip_differs=False  exact_differs=True  root_meanings=2
             seeds=2  dropped_alternates=0  executed_products=4
             rejected_cartesian_assignment_count=4
interaction  … the same, under ABNF
interaction  one_flip_differs=False  exact_differs=True  root_meanings=2
             seeds=3  dropped_alternates=1  executed_products=6
             rejected_cartesian_assignment_count=8
```

Both one-flip comparisons equal the baseline; the joint choice differs; the
exact lane finds it. The one-flip lane is executed only as the comparison it is
— `ambiguity_interaction.py` remains where it is disproven against the shipped
`another_meaning`.

**No global family assignment is formed anywhere in the mechanism**, island
included: the island's own exact set comes through the same per-node function
(`seed_products` is that lane's own counter, and it is 0 on every witness whose
island has no nested delegation, 4 on `sibling-and-nested`). The oracle is what
enumerates global assignments, which is what keeps it independent.

**What the per-node lane removes, and what it does not.** A node's set is its
own families × its children's *deduplicated* sets, so multiplicity that meets
and collapses at one node does not multiply again above it. It does **not**
remove the local product at a node where k multiplicitous children meet — that
is `Π` of their set sizes and is inherent to the exact relation. The
three-occurrence row is where the certificate pays inside the composition: the
`const` row removes one occurrence before the product is formed, so the meeting
node's product is `2 × 1 × 2 = 4` instead of `2 × 2 × 2 = 8`. That is the
structural result, in one unit; `executed_products` and
`rejected_cartesian_assignment_count` count different things and are not
compared to each other.

**The asymptotic consequence, stated.** Today's `another_meaning` is
deliberately linear in ambiguity points — its own docstring says so — and case
4 is the counterexample that makes it unsound. Exactness costs that: the
reference relation is a per-node product, exponential in a single node's local
multiplicity, and `cyclic_meaning.build_chart` materializes each node's
families the same way. The certificate and the dirty cone are what claw it
back — they bound how many nodes pay and remove occurrences before products
form — but no bound on the local product is claimed or proved here. §11 carries
it as the round's largest performance consequence.

---

## 5 — Occurrence identity: two slots, two sites, one nesting level

**Two SLOTS of one consumer.** `slot-discriminating` is `root ::= t t` with the
authored action `IrArg(1)`: slot 0 classifies `const` and its occurrence is
dropped, slot 1 classifies `ident` and its occurrence proves inequality. A
rule-granular table cannot express that row.

**Two SITES of one island rule.** `sibling-and-nested` puts the same island
rule under `left ::= t` (action `IrStr("k")`) and `right ::= t` (action
`IrBuild(IrTuple)`):

```text
occurrence-identity  outer_delegated_leaves=2  distinct_leaf_objects=True
                     occurrences_per_leaf=[1, 1]
                     distinct_continuation_keys=True
                     verdicts=['drop', 'injective']  outer_seeds_published=2
```

**One nesting level.** The same witness carries a nested delegated region
inside each island: the inner island publishes its own exact seed, the outer
island takes it as a leaf option set (`seed_products=4` is that composition),
and the document's continuation is unchanged. The addressed splice per
delegation level is `resolver_pair.py`'s evidence and is not re-derived.

---

## 6 — Semantic settlement versus resolver-tree materialization

```text
resolver-materialization  injective-consumer
  complete_document_trees_before_the_resolver=0  trees_after_the_resolver=3
  recognitions_before_the_resolver=1  recognitions_after_the_resolver=1
  island_recognitions_after=1  retained_island_kernels=1
  resolver_calls=1  chosen_root=root  pair_is_two_distinct_trees=True
```

Complete document `ParseTree`s are constructed only after root inequality and
an actual resolver call. The pair is spliced through
`resolver_pair.splice_leaf`/`payload_leaves` from **the kernel the seed
retained**, so neither the document nor the island is recognized again —
`document_recognitions` and `island_runs` are both unchanged across the
resolver call.

**And that retention is the price, stated as a cost rather than a convenience.**
`islands.island_parse` decides inline and lets its kernel die, so a pair
assembled later needs the kernel kept alive: one live island kernel per
**ambiguous** delegated occurrence, from the moment it publishes an alternate
until settlement. An unambiguous island retains `None`
(`retained_island_kernels=0` on cases 1 and 6). This is exactly the deferred
per-occurrence state `PROTOTYPE_14.md` §2 says a document-rooted pair needs —
now with an executable shape and a counter — and its production release
boundary is §11's, not settled here.

The claim "nothing was built before inequality" is scoped to the
**complete-document** tree. The island's own single derivation exists before
it, exactly as it does in production today.

---

## 7 — A `goal.md` §5 divergence, now executable

`finite-consumer-equal` is a document whose two derivations build **different
generated models** but the **same reducer value**. The shipped `reduce` refuses
it; the exact requested-root relation accepts it.

```text
value-relation-divergence  finite-consumer-equal
  shipped_reduce=parsing: ambiguous input — two derivations that mean
    different things; supply a resolver to choose between them
  exact_root_meanings=1  exact_differs=False
```

Not a fourth shipped defect: the shipped gate follows the relation the engine
currently declares (the variant model), and `goal.md` rules the definitive
reduced-root value relation its successor and requires the differences to be
enumerated at §5. This is one, executed.

---

## 8 — What the certificate settles on the shipped grammars

A scale row, and the price of §2.1's refusals stated honestly:

```text
row-census  gbnf  rows=170  verdicts={'drop': 8, 'execute': 162}
                  slot_classes={'grow': 17, 'ident': 66, 'unknown': 87}
row-census  abnf  rows=138  verdicts={'drop': 6, 'execute': 102, 'injective': 30}
                  slot_classes={'finite': 1, 'grow': 16, 'ident': 29, 'unknown': 92}
row-census  ebnf  rows=90   verdicts={'drop': 4, 'execute': 86}
                  slot_classes={'grow': 12, 'ident': 34, 'unknown': 44}
row-census  json  rows=60   verdicts={'drop': 2, 'execute': 48, 'injective': 10}
                  slot_classes={'finite': 5, 'grow': 4, 'ident': 8, 'unknown': 43}
row-census  cpu=0.048225  ONE un-repeated process-CPU sample with no control
                  row: it says the compile step runs, not how much it costs.
                  It is the one figure in this report that does not reproduce
                  exactly — a later run printed 0.049503 — which is what an
                  uncontrolled single sample is worth
```

Read it plainly. `unknown` is the largest column everywhere and it grew when
the channel-coordinate refusal landed: GBNF's injective verdicts went to zero,
because every rule normalization rewrote lost its law. **On the recursive
shipped grammars the shortcut is a small minority of rows** — DROP is under 5%
everywhere (4.7 / 4.3 / 4.4 / 3.3%) and EXECUTE is 73.9–95.6% (162/170,
102/138, 86/90, 48/60), ABNF at the low end because it is the one shipped
grammar where the certificate still yields injective rows, thirty of them — so
on those grammars most ambiguous spans
would take the EXECUTE lane and, on a PDA-first parse, the Earley escalation
§3.5 names. Closing `PROTOTYPE_14.md` §4's exact channel-index obligation is
what would widen the shortcut. What the census establishes is that the compile
step is real and total; the CPU figure carries no conclusion.

---

## 9 — The oracle, and the precondition it rests on

Every candidate result is compared with **independent complete Earley folds
over all small families**: for every accepting item and every global family
assignment, a real `FastTree` derivation is built and folded over the tree with
the same real reducer, once per delegated-occurrence option combination. The
comparison is order-free and runs on **every** witness through the control run.

**Independence.** The oracle differs from the mechanism in traversal (real
`ParseTree` versus packed chart handles) and in enumeration (global assignments
versus per-node products), for the island as well as the document — the island
no longer shares the oracle's per-assignment function. It shares the reducer,
which it must: the reducer IS the semantics both compute.

**The precondition, checked rather than assumed.** The mechanism gives every
OCCURRENCE its own family choice; the oracle fixes one family per KEY across a
derivation. Those coincide exactly when no node — and so no arm-choice key — is
reachable twice inside one derivation, and that is checked on every witness:

```text
oracle-precondition  <witness>  chart_nodes=1..161  nodes_with_two_parents=0
                     keys_claimed_twice=0
```

Where it would fail the per-node relation is the DESIGN's and the
global-assignment enumeration is the narrower one; no witness exercises that
shape. §11 carries it.

**The cyclic boundary.** The mechanism refuses a cyclic chart with words and
names `cyclic_meaning.exact_meanings` as its owner; the refusal is checked on
every run. An empty option lane also raises rather than skipping a family,
because skipping would shrink the meaning set — a wrong acceptance, which is
the one direction a silent default must not take.

---

## 10 — The questions the round had to answer

**1. Can static `const` and injective laws settle their cases without
propagating general ambiguity state?** Yes, with one asymmetry. `const` settles
before the work it avoids: case 1 records `skipped_enumerations=1`,
`seed_chart_nodes=0`, `seed_products=0`, `settlement_chart_nodes=0`,
`row_lookups=0`, `descent_steps=0`. The injective case is static in its LAW but
needs the realized route, because a grammar path is an over-approximation: case
2 settles at `settlement_products=0`, `settlement_chart_nodes=0`,
`settlement_trees=0` after two descent steps. Neither builds a dependency
index, an overlay, a meaning memo or a complete-document tree, and neither
needs the family-aware chart at all.

**2. What exact runtime data remains for a non-injective continuation?** The
occurrence's option list; one deduplicated meaning set per node **on the dirty
cone**; and, per ambiguous occurrence, the retained island kernel a resolver
would need. Beside them, not part of them, is the per-node baseline fold that
is the parse's own product. `distant-island` is the shape: 161 chart nodes, 161
baseline folds, 1 dirty node, 2 set applications.

**3. How are interacting choices composed without Cartesian assignment
enumeration or unsound one-flip pruning?** By the per-node product over
deduplicated child sets, §4, with its limit and its asymptotic cost stated. No
alternative is ever discarded for equalling the baseline under the other
choices' baseline values.

**4. What is cached once, what is parse-local, and when is each released?**
Cached once per bound product: the continuation table — flat rows, pinned key,
same object on rebind, equal rows after eviction, thirteen entries metered and
drained. Parse-local: the island seeds and their retained kernels, the leaf
option lists, the node meaning sets, the route descents, and (only after
inequality and an invoked resolver) the two complete trees. In this prototype
they die with the run; their production release boundary — especially the
retained island kernel's — is §11's, not settled here.

**5. Does ordinary island recognition remain local and byte-for-byte outside
the prototype?** `src` is untouched, and the unambiguous control builds exactly
the one island derivation `islands.island_parse` builds today, retains no
kernel, publishes no seed, and performs no lookup, descent, chart walk, set
application or complete-document tree build. What this does not show is the
landed runtime's opcode stream, or anything about the PDA island entry, which
this round never executes.

**6. After this proof, what precisely remains of the resolver-scope user
decision?** All of it. The round changes the decision's inputs in one way:
semantic settlement needs no derivation pair at any scope, so the scope
question is confined to what an invoked `resolve=` is handed — and it adds one
priced fact to Prototype 14 §2's table, that a pair without re-recognition
costs a retained island kernel per ambiguous occurrence. Nothing here selects a
scope.

**7. Is any planning or prototype gate still open before source
implementation?** The composition's MECHANISM is closed — certificate,
refusals, ownership, interaction rule, control and oracle all executable — but
this round OPENS one planning gate of its own and it is labelled as such in
`TODO.md` §8: **EXACT-LANE COST BOUND.** Exactness replaces a linear one-flip
probe with a per-node product exponential in a single node's local
multiplicity; the certificate and the dirty cone bound how many nodes pay and
neither bounds that product. The gate has two halves at two moments, and
`TODO.md` places them: production STATES the bound it enforces — or the refusal
it raises past it — before the exact lane lands, inside §8; the MEASUREMENT of
that lane on an ambiguous input belongs beside the §12 RSS row. Neither half
substitutes for the other. Discovering that cost after landing would put a
parse regression behind the user's post-measurement approval, which is exactly
what the gate exists to prevent.

What §2.1 refuses is not a gate this round left open — it is
`PROTOTYPE_14.md` §4's channel-index obligation, whose consequence this round
makes concrete. Everything else that was open stays open and is listed in §11.
The resolver-scope USER DECISION remains the one gate that blocks §8.

---

## 11 — What this round does not prove

- **The PDA path.** Nothing here executes the predictive runtime or
  `islands.island_parse`. The composition is Earley-delegated throughout, and
  `pda/runtime/kernel/kernel.py` records zero measured `OP_ISLAND` steps across
  the benchmark, so how often a PDA island exists at all is not something this
  round can speak to.
- **The Earley escalation the EXECUTE lane implies.** A PDA-first parse holds
  no SPPF, so an EXECUTE verdict there means escalating to Earley for the
  chart. §8's census puts EXECUTE at 73.9–95.6% of rows on shipped grammars. What
  the round shows is that CONST and INJECTIVE settle without the chart; how
  often that fires on a production document is a §12 measurement.
- **The asymptotic cost of exactness.** Replacing the linear one-flip probe
  with the exact per-node relation is exponential in a node's own local
  multiplicity, and no bound on it is claimed. The certificate and the dirty
  cone reduce how much of the chart pays; they do not bound the local product.
  This is the round's largest performance consequence and it is unmeasured.
- **The exact channel index.** `PROTOTYPE_14.md` §4's obligation is untouched
  and now load-bearing: the certificate refuses every rule whose canonical and
  normalized contributing references differ. Production must read the binding
  view's `fields_of` to widen it.
- **Cache mortality.** The registry pins its keys — correct, immortal until
  released, metered at 13 entries. Adopting the table into `parsing.caches`'
  `memo`/`track`/`release` under the `CompiledGrammar` owner is production
  work.
- **The retained island kernel's release boundary.** Retaining it is what
  removes the resolver's re-recognition; nothing here measures its residency or
  fixes when production drops it.
- **The production hot path and memory.** No opcode stream, no frame shape, no
  allocation count, no RSS row. The §8/§12 gates `PROTOTYPE_13.md` left open
  are unchanged.
- **Parse performance.** Nothing here is a throughput measurement and no parse
  regression is authorized by this report.
- **Locating the occurrence.** The root-down descent is a stand-in; production
  reads the key off the island's entry frame or waiter code. That argument has
  a dependency worth naming: turning the PDA's `(arm, opcode index)` into a
  CHANNEL slot is the same coordinate join §2.1 refuses, so until the channel
  obligation closes, the descent's cost stays open too. The prototype's
  pre-enumeration skip is likewise only the rule-wide half, because an Earley
  delegate is not told its consumer.
- **The shipped-value differential's reach.** It agrees only where the shipped
  model gate does not refuse, which excludes every document whose island choice
  is live. Widening it needs `reduce(..., resolve=)`.
- **The per-node versus per-assignment precondition.** Checked and true on
  every witness; a chart where a key is reachable twice is not exercised.
- **Value identity.** `dedup` keys on `repr`, deliberately, so a leaf and its
  bare payload cannot collapse. That is a full serialization per candidate per
  node and nothing counts it; production needs a stated value-identity
  primitive with a stated cost.
- **Cyclic charts, `YIELD` and the emit families, contextual clones, and the
  product operations that do not exist yet.** Refused, focus-free, argued from
  the code→rule mapping, and absent respectively — all unchanged from
  Prototype 14.

---

## 12 — Commands and provenance

Sequential, one process at a time, no other benchmark, pool or agent alive.
Exit codes are the unpiped process status.

```text
uv run python proto/island_continuation.py          exit 0

uv run python proto/operation_slot_laws.py          exit 0
uv run python proto/route_continuation.py           exit 0
uv run python proto/root_meaning_incremental.py     exit 0
uv run python proto/island_alternate_seed.py        exit 0
uv run python proto/ambiguity_interaction.py        exit 0
uv run python proto/resolver_pair.py                exit 0

uv run ruff format / isort / ruff check  proto/island_continuation.py   clean
uv run pyright                           proto/island_continuation.py   0 errors

git status --short -- src tests pyproject.toml .wiki   empty
git diff --check                                       clean
```

**Working tree.** Nothing under `src`, `tests`, `pyproject.toml` or `.wiki`
changed. The effort's active documents are tracked and modified because they
are this round's fold; the round's new files are
`reports/PROTOTYPE_15.md`, `reports/P15_ADVERSARIAL.md` and
`proto/island_continuation.py`, joined by `reports/REVIEW_15.md` when the
closure audit returns. Importing `resolver_pair` regenerates its
`__pycache__` entry, and running Ruff rewrites `proto/.ruff_cache/`; both
directories are tracked in this repository, so each was restored with
`git checkout` after the last run.

Forbidden-construct search over the new file found no `eval`/`exec` builtin
call, no `Any`, no `object`, no `cast`, no `-> object`, no nested `def`, and no
`# type: ignore`, `# noqa` or `# pylint: disable`. The only `.eval(` uses are
the IR action-body protocol method lexic itself defines — which is the point:
the meanings here are produced by the real authored operations.
