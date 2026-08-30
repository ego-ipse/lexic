# Prototype 14 — real operation laws, a constructive infinite-SCC pair, resolver scope, the tokenizer's last three lanes, and the bugfix baselines

The final investigation round before implementation review. No production
source, test, harness or wiki file was changed — `git status --short -- src
tests pyproject.toml .wiki` is empty and `git diff --stat -- src tests
pyproject.toml` is empty. Every executable artefact is under this effort's
`proto/`. No commit, no push, no worktree. No multithreaded row was run at any
point in this round, and no two measurements overlapped.

Three new prototypes, two revised ones:

| File | Round-14 role |
|---|---|
| `proto/operation_slot_laws.py` | new — lowers every shipped operation declaration to the cyclic slot algebra through one open table, differentials it, and refuses the rest by name |
| `proto/scc_resolver_pair.py` | new — constructs two complete derivations with different requested-root meanings for an infinite zero-width component |
| `proto/tokenizer_validation_lanes.py` | new — inventories all five fixtures for the three open lanes and executes the recommended contract against an independent oracle |
| `proto/resolver_pair.py` | revised — engine pair scope, multi-island and nested occurrence identity, the no-shadow question, per-scope cost |
| `proto/nullable_quantifier_ambiguity.py` | revised — pinned pre-fix baselines, a strengthened Leo readout proof, alternating timings, and the post-fix differential specification |

---

## 1 — Facts conclusively established by real source and fixture evidence

### 1.1 Every shipped operation declaration reaches a class or a named refusal

`operation_slot_laws.py` classifies the argument slots of every action
declared by the shipped GBNF, ABNF, EBNF and JSON reducers, plus the emit-side
action tables, plus the four contribution policies in `lexic.ir.reduction`.

The classification is **structural**. One `IrTypeMap` maps an *operation type*
to the law it declares; resolution is `IrTypeMap.resolve`'s own concrete-first
`__mro__` walk — the dispatcher lexic uses everywhere — and the table
deliberately carries **no `IR_DEFAULT` row**, so an unregistered type reaches a
raising default naming the operation and the slot. An expression's law is the
composition of its sub-expressions' laws under those rows. Nothing reads an
operation's name, samples values to guess, keys on a Python callable, or runs
an `isinstance` cascade **that decides a law**. The module does contain
`isinstance` tests — narrowing a dispatched node to the type its row is written
for (`_as`), reading an argument expression's shape in `positions`, and walking
a body in `_width` — but none of them selects a class; every class comes from
the table.

```text
uv run python proto/operation_slot_laws.py

operation-census  lane=completion  sites=192  slots=282  expressions=1159
                  resolutions=1308
                  classes={'const': 52, 'finite': 6, 'grow': 58, 'ident': 62,
                           'refused': 104}
                  refusals_by_operation={'IrJoin': 47, 'IrBuild': 33,
                           'YIELD': 12, 'IrTypeMap': 5, 'IrUnradix': 3,
                           'IrArg(-1)': 2, 'IrBuild(IrChr)': 2}
                  cpu=0.040712
operation-census  lane=emit-unscheduled  slots=44
                  classes={'const': 8, 'finite': 12, 'refused': 24}
                  undeclared_families={'IrGroup': 7, 'IrDocJoin': 6,
                           'IrEscapePoint': 4, 'IrDocConcat': 3,
                           'IrEscape': 2, 'IrJoin': 1, 'IrSpellable': 1}
```

Two things about those numbers. The channel width comes from each rule's widest
arm counted in **contributing** items — references to rules the reducer does not
drop — over the same normalized grammar the carrier lane reads, so both lanes of
the module share one coordinate system. It is still an upper bound (hoisted
groups and quantified repeats can make the real width vary per input), and the
over-approximation biases toward **carrying**, not toward `const`: a splatted
channel reports one identity position whatever the slot index, so a phantom slot
classifies like a real retained one. The census over-reports carrying slots
rather than hiding them.

The two lanes are separated on purpose. The **completion** lane is what the
product schedules and where a law is mandatory. The **emit** lane builds
layout documents and flavour spellings; no completion runs through it, and a
law nothing differentials would be exactly the unproved claim this module
exists to refuse — so those families are reported as declaration obligations,
not declared.

The proof obligation an authored operation must supply is one row stating,
for an argument whose value varies:

- `const` — the result does not depend on that argument at all;
- `ident` — the result IS that argument;
- `finite` — the result ranges over a declared, explicitly bounded image;
- `grow` — the result retains that argument as a proper sub-value, so the
  operation is injective in it and strictly increases value size.

A construction target additionally declares, in `CONSTRUCTOR_LAWS`, whether it
retains its arguments, bounds them, or decodes them. `IrTuple` covers the whole
record spine — a record IS its field tuple, so construction stores each
argument at depth one — and `IrScalar` covers the value leaves, whose
constructors consume a payload instead of retaining it.

### 1.2 The categories the design schedules are covered, one by one

```text
category  … rows reordered for reading; `bound=` elided; the run prints the
          YIELD default first …
category  record construction     site=gbnf:rule    slot=0  class=grow
category  record construction     site=gbnf:item    slot=1  class=grow
category  sequence accumulation   site=json:array   slot=0  class=grow
category  keyed accumulation      site=json:object  slot=0  class=grow
category  joint retain/ignore     site=gbnf:group   slot=0  class=ident
category  joint retain/ignore     site=gbnf:group   slot=1  class=const
category  joint retain/ignore     site=abnf:option  slot=0  class=grow
category  joint retain/ignore     site=abnf:option  slot=2  class=const
category  validation refusal      site=json:frac    slot=0  class=finite
category  validation refusal      site=abnf:prose   slot=0  class=finite
category  default action (YIELD)  site=json:<default> slot=0
                                  class=refused-without-a-span-proof
category  scalar decode           slots_with_no_law=53

category-execution  … 4 of the run's 10 rows; `bound=` elided throughout …
category-execution  record construction  site=gbnf:rule[0]    executed_on_probes=True
                    agrees=True  detail=injective=True grew=True
category-execution  keyed accumulation   site=json:object[0]  executed_on_probes=True
                    agrees=True  detail=injective=True grew=True
category-execution  joint retain/ignore  site=gbnf:group[0]   executed_on_probes=True
                    agrees=True  detail=returns its own argument: True
category-execution  validation refusal   site=json:frac[0]    executed_on_probes=False
                    agrees=True  detail=under two executable probes:
                    UnsupportedConstructError('json: fractional numbers have no
                    IR value (no float leaf)')

retaining-constructor  IrBuild(IrTuple)  slot=0  class=grow  channels=7  agrees=True
retaining-constructor  IrBuild(IrRule)   slot=0  class=grow  channels=3  agrees=True
retaining-constructor  IrBuild(IrMap)    slot=1  class=grow  channels=3  agrees=True
retaining-constructor  IrMerge()         slot=0  class=grow  channels=3  agrees=True
partial-operation  IrBuild(IrMap)  refuses=IrMap: duplicate key IrStr('k')

contribution-policies  DROP_slots=0 class=const   KEEP_RAW_slots=1
                       carries_child=True class=ident   KEEP_REDUCED_slots=1
                       class=ident   YIELD_on_empty_span=IrStr('')
                       YIELD_on_one_char=IrStr('x')
                       YIELD_on_a_wider_span=IrStr('xy')
                       YIELD_is_span_sensitive=True
```

Four results here are load-bearing and were not obvious:

- **A scalar decode over a slot-carrying value has no law.** `IrUnradix`,
  `IrJoin`/`IrConcat` over a carrying part, and `IrBuild(IrChr, …)` all take a
  value and produce a scalar that neither retains it nor has a declared finite
  image. `IrUnradix("01") == IrUnradix("1")` and `"a"+"bc" == "ab"+"c"` are
  genuine non-injectivities, not conservatism. 53 completion-lane slots are in
  this class and refuse by name.
- **`YIELD` gets no `const` licence, and refuses by default.** It reads the
  focus's *drop-aware* text. Two families of one equal-span component cover the
  same span but can drop different subtrees of it, so the text view is a
  function of the derivation — exactly what varies. `Env.span_fixed` is the
  only licence: `const` where the caller has PROVED nothing reachable below the
  focus is dropped, refusal otherwise. Since `YIELD` is also the reducer default
  for every rule with no explicit action, that refusal is the single largest
  entry in both censuses, which is the honest picture rather than a comfortable
  one. `prove_contribution_policies` executes the counterexample: `YIELD` on
  `""` and on `"xy"` differ.
- **The showcased categories now execute, not just classify.** `IrBuild(IrRule)`,
  `IrBuild(IrMap)` and `IrMerge()` cannot run on a general probe domain — a
  record constructor raises on a channel of the wrong shape — so
  `RETAINING_PROBES` supplies a channel each one accepts and varies exactly one
  position. All four agree with their `grow` law. The two validation refusals
  deliberately do NOT execute: they raise on every input, which IS the
  `finite(0)` law being claimed.
- **Partiality needs no fifth class.** `IrBuild(IrMap)` refuses a repeated key.
  Where an operation raises it produces no value, which is the `finite(0)`
  bottom `IrRaise` already names, and an absent value cannot make a requested
  root mean two things. The law is stated over the operation's domain.

### 1.3 The slots that can actually sit in a zero-width component

Carrier edges come from `cyclic_meaning.carrier_edges` on each surface's
normalized self-grammar — a child that can cover its parent's entire span.

```text
slot-alignment  gbnf  edges=92  reference_coordinates_match_cyclic_meaning=True
                      channel_differs_from_reference=0
slot-alignment  abnf  edges=80  reference_coordinates_match_cyclic_meaning=True
                      channel_differs_from_reference=0
slot-alignment  ebnf  edges=46  reference_coordinates_match_cyclic_meaning=True
                      channel_differs_from_reference=1
                      examples=['grammar->rule ref_slot=1 channel_slot=0']
slot-alignment  json  edges=28  reference_coordinates_match_cyclic_meaning=True
                      channel_differs_from_reference=1
                      examples=['json-text->value ref_slot=1 channel_slot=0']

zero-width-slots  gbnf  rules=104  carrier_edges=92  dropped_child_edges=3
                  empty_span_capable=4
                  classes={'const': 13, 'grow': 6, 'ident': 63}  refused=10
                  refusals_by_operation={'YIELD': 7, 'IrTypeMap': 2, 'IrJoin': 1}
zero-width-slots  abnf  rules=101  carrier_edges=80  dropped_child_edges=16
                  empty_span_capable=5
                  classes={'const': 35, 'finite': 1, 'grow': 4, 'ident': 23}
                  refused=17
                  refusals_by_operation={'IrJoin': 9, 'YIELD': 4,
                                         'IrArg(-1)': 2, 'IrBuild': 2}
zero-width-slots  ebnf  rules=61   carrier_edges=46  dropped_child_edges=2
                  empty_span_capable=1
                  classes={'const': 5, 'grow': 4, 'ident': 30}  refused=7
                  refusals_by_operation={'YIELD': 4, 'IrBuild': 1,
                                         'IrBuild(IrChr)': 1, 'IrJoin': 1}
zero-width-slots  json  rules=51   carrier_edges=28  dropped_child_edges=0
                  empty_span_capable=1
                  classes={'const': 9, 'ident': 8}  refused=11
                  refusals_by_operation={'YIELD': 7, 'IrJoin': 2,
                                         'IrBuild': 1, 'IrMap': 1}
```

**Two coordinate systems, held against each other.** `cyclic_meaning`'s
`carrier_edges` numbers a slot among ALL reference items; the argument channel
numbers only the contributing ones, because a dropped child never reaches the
channel at all. `prove_slot_alignment` computes both and names the
disagreements: the reference coordinates match `cyclic_meaning` edge for edge on
all four surfaces, and the channel index differs from the reference index on
exactly two shipped edges — `ebnf:grammar->rule` and `json:json-text->value`,
both because a noise reference precedes the carrier. Reporting one number as the
other is the failure that row exists to catch.

So the four shipped self-grammars are **not** clean: 45 of their 246 carrier
slots have no law under the declared algebra. Four refusal shapes account for
all of them, each with a named example:

- `n[0]`, `ws[0]` — the reducer's `YIELD` default over a focus with a dropped
  rule below it (22 edges, the largest group).
- `cc-item[0]` — an `IrTypeMap` whose arms classify `grow` and `ident`; which
  arm runs is settled by a value the expression cannot see. A production
  classifier can be sharper here **per arm**, because a packed family names one
  arm; that refinement is recorded, not assumed.
- `repeat-num[0]`, `number[1]` — an `IrBuild` where no position carries the slot
  and one has no law; `cvbody[0]` — an `IrArg(-1)` whose real position is
  input-dependent.
- `count[0]` — a text join over a carrying value.

Two of the 45 fall outside those four headings — one `IrBuild(IrChr)` scalar
decode in EBNF and one `IrMap` value-keyed lookup in JSON — and both are named
in the `refusals_by_operation` field above rather than folded into a shape.

These are refusals of the *analysis*, not of the shipped grammars: a refusal
only becomes a binding refusal when the carrier edge is on a real cycle, and
none of these self-grammars has one under its own reducer. What the numbers
establish is that the production classifier will meet these shapes on real,
shipped input and must answer each deliberately. Note also
`empty_span_capable`: only 11 of 246 carrier edges have a nullable child, so
"equal span" is the component condition and "empty span" is a much rarer one —
which is precisely why `YIELD` cannot be licensed from the component alone.

### 1.4 The derived classes agree with direct evaluation, and misdeclarations are caught

```text
differential  classified_slots=178  executable_on_probes=155  agreed=155
              not_executable=23  every executable row agrees with direct
              evaluation
misdeclaration  IrJoin declared retaining        caught_at=gbnf:decits[0]
                                                 injective=True grew=False
misdeclaration  IrArg declared constant          caught_at=gbnf:arm[0] distinct=7
misdeclaration  IrArgs declared constant         caught_at=gbnf:decits[0] distinct=4
misdeclaration  IrPipe declared focus-preserving caught_at=gbnf:q-between-t[0] distinct=2
misdeclaration  IrUnradix declared identity      caught_at=abnf:d-range[0]
                                                 returns its own argument: False
misdeclaration  IrScalar target declared retaining
                                                 caught_at=IrBuild(IrChr)[0]
                                                 injective=True grew=False
unknown-operation  body=operation 'FutureOperation' declares no slot law (slot 0)
unknown-operation  foldkit=operation 'IrNamed' declares no slot law (slot 0)
unknown-operation  target=construction target 'FutureOperation' declares no law
```

The differential runs each classified slot's real body against a seven-value
probe domain and judges the observed behaviour: `const` ⇒ one distinct result,
`ident` ⇒ the argument object returned, `finite(n)` ⇒ at most `n` distinct
results, `grow` ⇒ pairwise distinct results each strictly larger than its probe
under a size measure that counts BOTH retaining tiers — a record's field tuple
and a mapping's dyads (counting only tuples made `IrBuild(IrMap)` read as size
one and fail its own law). `178 − 155 = 23` rows are not executable on the
general probe domain, because the body needs a shaped channel or a real focus;
those are reported, never counted as agreement, and the retaining constructors
among them are then differentialled on channels they accept.

`foldkit.IrNamed` — the shared authored-fold vocabulary — reaches the raising
default. That is a real finding: `first_rest`, `passthrough` and `int` resolve
through a Python registry and cannot be classified structurally, so each must
carry a declared law before the product compiler may schedule it.

### 1.5 The real classes decide the existing cyclic witnesses identically

`binding_verdict` re-runs `cyclic_meaning`'s own component decision with the
per-edge class coming from `Classifier.law` over an authored IR body instead of
the toy policy table. Same graph, same reachability lanes, same verdict:

```text
cyclic-parity  real-grow-injective-root  kinds=('cyclic-infinite', 'acyclic')  refused=False
cyclic-parity  real-identity-cycle       kinds=('cyclic-bounded', 'acyclic')   refused=False
cyclic-parity  real-dropping-root        kinds=('cyclic-opaque', 'acyclic')    refused=False
cyclic-parity  real-bounded-consumer     kinds=('cyclic-unrepresentable', 'acyclic')  refused=True
```

The last row is a real `IrCompare(IrArg(0), IrOp("=="), IrStr("x"))` root over
a real `IrBuild(IrTuple)` cycle: a declared finite image consuming an injective
growing family, refused at binding.

### 1.6 Bounds

```text
bounds  operations=236  slots=326  expression_visits=1159  table_resolutions=1308
        gbnf_carrier_edges=92  cpu=0.001619
```

`operations`/`slots` count both lanes (192 + 44 sites, 282 + 44 slots).
Classification is one pass per `(operation, slot)` over the body tree —
`O(Σ_operations width × |body|)` time, `O(depth)` stack, and `O(1)` retained
per slot: a `SlotLaw` is two ints and nothing is memoised across slots. The
component decision it feeds is `O(V + E)` in both time and memory over the
chart's completed nodes and family edges — the chart's `resolveds`, `edges` and
`children` maps, plus one exact value set per node, whose live and peak sizes
`cyclic_meaning` already measures and prints as `retained` and `max_live` per
witness. There is no enumeration over assignments anywhere in either half.

### 1.7 A resolver pair for an infinite component is constructible, structurally

`scc_resolver_pair.py` builds two complete derivations of one document whose
complete requested-root meanings differ, for a component the classification
calls `cyclic-infinite`:

1. take the accepting derivation the real `FastTree` already builds — this IS
   the pair's first element, the same thing the shipped `resolve(tree, witness)`
   call sites pass as their first argument;
2. certify the component and find a carrier that both lies on a growing closed
   walk of the component's own carrying edges and stands in that derivation —
   **every** carrier is tried, in packed-handle order;
3. select one **closed walk** through it, built as
   `shortest(start→u) + (u,v) + shortest(v→start)` for the first `grow` edge
   whose two halves exist;
4. splice exactly that traversal at the addressed occurrence, path-copying only
   the spine above it.

```text
uv run python proto/scc_resolver_pair.py

pair  unary-unit-cycle  carrier=a  carriers_tried=1  walk_edges=2
      walk=['a->b@0', 'b->a@0']  occurrence_path=[0]
      occurrences_of_rule_and_span=1  first_is_engine_derivation=True
      changed_positions=1  meanings_differ=True  both_in_oracle=True
      oracle_set=4  deterministic_repeat=True  cpu=0.000350
pair  two-key-multi-node-cycle  carrier=s  carriers_tried=1  walk_edges=3
      walk=['s->t@0', 't->u@0', 'u->s@0']  occurrence_path=[0]
      first_is_engine_derivation=True  changed_positions=1
      meanings_differ=True  oracle_set=3  deterministic_repeat=True
pair  sibling-accepting-roots  carrier=c  carriers_tried=1  walk_edges=2
      occurrence_path=[0, 0]  first_is_engine_derivation=True
      changed_positions=1  meanings_differ=True  oracle_set=6
pair  upstream-carrier-off-cycle  carrier=a  carriers_tried=2  walk_edges=2
      occurrence_path=[0, 0]  first_is_engine_derivation=True
      changed_positions=1  meanings_differ=True  oracle_set=5
pair  grow-edge-on-side-cycle  carrier=x  carriers_tried=1  walk_edges=4
      walk=['x->y@0', 'y->z@0', 'z->y@0', 'y->x@0']  occurrence_path=[0]
      first_is_engine_derivation=True  changed_positions=1  meanings_differ=True
pair  nested-island-source  carrier=c  walk_edges=2  delegated_leaves=1
      occurrences_of_rule_and_span=1  changed_positions=1  meanings_differ=True
pair  deep-stack-safe  chars=2001  carrier=c  walk_edges=2  changed_positions=1
      meanings_differ=True  cpu=0.126042
pair  deep-stack-safe  chars=8001  carrier=c  walk_edges=2  changed_positions=1
      meanings_differ=True  cpu=0.582525
```

**The first element is the engine's own derivation.** `first_is_engine_derivation`
compares the pair's first element against `FastTree(kernel, {}).build(root)` and
is `True` on every witness. That is what makes §B compose with §C's ordering
rule: a `resolve=lambda first, other: first` returns exactly what the parse
would have returned without a resolver.

**Two witnesses exist because committing to one carrier and to a SIMPLE cycle
was wrong.** `UPSTREAM_CARRIER` is a real GBNF grammar whose carrier closure
reaches a node off the growing cycle — `cyclic_meaning._carriers` returns the
`ident`/`grow` upward closure, and a member of it need not lie on any closed
carrying walk. The previous constructor took the lowest-handle carrier and
refused the grammar outright with a message blaming the classification.
`carriers_tried=2` on that row is the fix being load-bearing. `SIDE_CYCLE` is
the second shape: its only `grow` edge sits on a side cycle, so the four-edge
walk `x→y→z→y→x` is not simple and a simple-cycle search would have missed it.

**Termination and cost are structural.** The walk is two breadth-first shortest
paths plus one edge, so the construction is `O(E × (V + E))` — a *simple* cycle
through a given vertex carrying a given edge is the directed two-disjoint-paths
problem, and requiring one was both exponential in the search and wrong in the
answer. There is no lap count, no depth ladder, and nothing parameterised by a
number a reviewer could move.

**Occurrence identity is addressed and measured.** A completed handle encodes
its own span and a derivation's sibling spans are disjoint, so a rule over a
fixed span stands at at most one position; `occurrences_of` returns them all and
every witness reports `occurrences_of_rule_and_span=1` rather than assuming it.
`difference_count` short-circuits on structural equality, so the splice's own
path-copied spine is not miscounted — `changed_positions=1` is the measurement
that exactly one position differs.

**Independent validation.** Both trees' yields equal the document; every node
instantiates a real arm of the normalized grammar, character-class membership
included (`valid_derivation` reads the grammar and the tree only, never the
chart); and both meanings appear in `cyclic_meaning`'s bounded-depth
enumeration. That oracle is independent in its **derivation enumeration** only —
it shares `apply_policy`, the meaning algebra — and the termination argument is
the walk, not the ladder. The traversal is also checked to preserve the consumed
width, which is what converts "a carrier edge's siblings consume nothing" from a
docstring claim into an executed check.

**The refusal boundary is stated, witnessed, and no longer overclaimed:**

```text
decline  dropping-root-opaque    classification=cyclic-opaque   root_meanings=1
decline  identity-cycle-bounded  classification=cyclic-bounded  root_meanings=1
decline  acyclic-twin            classification=acyclic         root_meanings=1
refusal-boundary  no_growing_walk=resolver pair: no closed carrying walk through
                  this carrier reaches a grow edge and returns...
                  no_occurrence=resolver pair: no occurrence of 'nowhere' over
                  (0, 1) stands in the accepting derivation...
```

The three `decline` rows all stop at `certify`. Two of the constructor's own
refusals — a carrier with no growing walk, and a rule/span the derivation does
not hold — are reachable (the first is exactly what `UPSTREAM_CARRIER` produced
before the fix), so each gets its own direct witness rather than a claim. A
`cyclic-unrepresentable` component never reaches the constructor at all; binding
already declined.

There is a **third** refusal, and it has no witness: `construct_pair` compares
the two complete meanings it built and refuses by name if they are equal. That
cannot happen if the certificate's reasoning holds, but that reasoning is prose
— so the check is executed rather than asserted in a caller, the refusal is
named rather than an `AssertionError`, and §4 carries the class as an open
obligation instead of claiming it empty.

### 1.8 The two engines already present different resolver pair scopes

This is new and it matters for the §8 decision.

```text
uv run python proto/resolver_pair.py

engine-pair-scope  pda     resolver_called=True  pair_root=t     other_root=t
                   take_first_returned_the_first_element=True
                   take_second_returned_the_second_element=True
engine-pair-scope  earley  resolver_called=True  pair_root=root  other_root=root
                   take_first_returned_the_first_element=True
                   take_second_returned_the_second_element=True
engine-pair-scope  verdict pda_root=t  earley_root=root
```

Same grammar, same document `"(xy)z"`, resolver recorded on both forced routes.
The ordering claim is **measured, not printed**: each route runs twice, once
with a take-first resolver and once with a take-second one, and the returned
model is matched against what each element of the pair folds to. The match is a
containment test — an island-scoped pair folds to a subtree's model, not the
document model the route returns — so it is weak on its own; what makes it
discriminate is the asserted CROSSED negative control, that neither returned
model matches the derivation it did not keep (`crossed_match=False` on both
routes). Both routes
return the first element under take-first and the second under take-second, so
the **ordering rule already matches** — both hand over *(the derivation in
hand, the first differing one)*. The
**scopes do not**: the PDA's island gate is rooted at the island rule, Earley's
document gate at the start rule. A context-sensitive resolver can therefore
already observe which engine ran, which is exactly what the public-equivalence
invariant forbids. The scope decision is not a new divergence to avoid; it is
an existing one to close.

### 1.8b A THIRD shipped defect, pinned

`Resolver`'s own contract says "both engines given the same pair answer the
same way". They are not given the same pair, and they do not even refuse with
the same words:

```text
third-defect-baseline
  pda_refusal="parsing: island 't' derives the same text two ways that mean
               different things — supply a resolver to choose between them"
  earley_refusal='parsing: ambiguous input — two derivations that mean
                  different things; supply a resolver to choose between them'
  messages_differ=True   pair_roots=pda=t earley=root
```

`CURRENT_BUG_REPORT.md` records two defects; this is a third, established this
round on the shipped engines with no prototype in the path. It is pinned as an
asserted baseline in `resolver_pair.THIRD_DEFECT_BASELINE` so the source phase
has an uncontaminated reference. This report does not edit active planning
documents, so the coordinator folds it in. That is a body edit, not a counter
edit: `CURRENT_BUG_REPORT.md` is structured one `## BUG N` section per defect,
so this needs its own **`## BUG 3`**. Alongside it, every passage that counts
two has to change —
`CURRENT_BUG_REPORT.md`'s opening "Two defects … Neither is deferred work and
neither is introduced" and its "**Both** were verified through the public
API"; its closing "Neither is fixed" and "**Both** reproductions above run
against the current tip"; `INDEX.md`'s authority map, which calls that file
"the two shipped ambiguity defects"; `INDEX.md`'s history-table row "scopes
**both** shipped ambiguity defects"; and `LEDGER.md`'s "pre-fix baselines for
**both** shipped defects". The defect also needs an owner — `parsing/pda/runtime/islands.py`
(`island_parse`, which decides island-locally), `parsing/earley/engine.py`
(the document gate) and `parsing/products.py` (which emits the byte-identical
document-gate refusal), against `ambiguity.Resolver`'s own declared contract.

### 1.9 Occurrence identity across islands and nesting

**Provenance.** The two rows below drive delegation through
`island_alternate_seed`'s re-implementation — `harness.outer_run`,
`harness._delegates`, `harness.island_product` — not through the shipped
`islands.island_parse`. The COUNTS are harness output. The fact they
illustrate is checkable in source without them:
`src/lexic/parsing/earley/kernel/loop/kernel.py` injects one `PayloadLeaf` per
delegated completion, so one occurrence owns one leaf object by construction.
Read the rows as an illustration of a source fact, not as its proof.

```text
multi-island-occurrence  seeds=2  delegated_leaves=2  distinct_leaf_objects=True
                         occurrences_per_leaf=[1, 1]
                         splice_left_keeps_right_leaf=True
                         splice_right_keeps_left_leaf=True  document_reparses=0
nested-island-occurrence outer_leaves=1  island_leaves=1
                         opaque_leaves_after_two_splices=0  document_reparses=0
```

The kernel injects one `PayloadLeaf` **per delegated occurrence**, and each
stands at exactly one position in the outer derivation. An object-addressed
splice is therefore occurrence-exact by construction: replacing one island's
interior provably leaves the other's leaf in place. Nested delegation is the
same operation once per delegation level, innermost first; after two splices no
opaque leaf remains.

### 1.10 Neither scope needs a shadow on the unambiguous path

```text
no-shadow  PROTOTYPE-HARNESS ROW: the seed and reparse counts come from
           island_alternate_seed's own delegated re-implementation, not from
           src; only the resolver-call count is from the public API
           unambiguous_island_seeds=0  document_reparses=0
           resolver_calls_on_an_AMBIGUOUS_document=1
pda-document-scope  pda_model_cpu=0.000213  document_parse_tree=None
document-pair-scaling  chars=5    cold_recognition_cpu=0.000059
document-pair-scaling  chars=80   cold_recognition_cpu=0.000574
document-pair-scaling  chars=640  cold_recognition_cpu=0.004555
island-refusal-inline  call_order=['resolver(t)', 'document_model(Root)']
                       resolver_ran_before_the_document_model=True
scope-changes-the-question  PROTOTYPE-HARNESS ROW under a TOY policy
                  kept             island_local_second_meanings=1
                  document_root_differs=True   the_two_questions_agree=True
scope-changes-the-question  PROTOTYPE-HARNESS ROW under a TOY policy
                  dropping-parent  island_local_second_meanings=1
                  document_root_differs=False  the_two_questions_agree=False
```

Both caveats above are the prototypes' OWN output, not annotations added here:
`no-shadow` and `scope-changes-the-question` each print their provenance label
as a field. An earlier draft wrote the second caveat into the quoted block by
hand — a fabricated line inside a block presented as verbatim run output — and
the fix was to make the label real rather than to keep annotating.

Both scopes build the pair **after** inequality is proven, and nothing is
retained ahead of time on the unambiguous path — that answer is **no** for both
engines. But two of the earlier claims around it were wrong and are corrected
here:

- **"from state the parse already holds" is false for the island derivations.**
  `islands.island_parse` calls `another_meaning` and then either
  `policy.resolve` or a refusal **inline**, returns only `(tree, end)`, and lets
  the island kernel die. The `call_order` row shows the resolver running before
  the document model exists. A document-rooted pair therefore has to **defer**
  that decision and carry per-occurrence state to the root — a real retained-
  state cost, not a free re-use.
- **Document scope changes the question, not only the pair's root.** Under a
  dropping parent the island has a second meaning and the document root does
  not, so the two scopes disagree on *whether to refuse at all*. Whichever
  scope is ruled therefore also decides what the engines refuse.
  **That row is harness output under a toy policy** — `{"mid": "drop"}` stands
  in for a reducer's `DROP`, and `harness.cone_verdict` derives `differs`
  through the harness's own meaning folder, not through a shipped fold. What it
  establishes is that a dropping parent CAN make the two questions disagree,
  which is a property of the two scopes and not evidence about how often a
  shipped grammar does it.

The zero-extra-recognition half of the earlier claim still holds; the
"retained / free re-use" half does not, and it is the half the scope
recommendation's cost line rested on. Five active documents still carry the
superseded framing, for the coordinator to fold:

| Document | Passage |
|---|---|
| `TODO.md` | the ticked `[x] PLANNING REQUIRED BEFORE §8 — RESOLVER MECHANISM PART CLOSED` gate — "occurrence replacement splices the **retained island derivation** into a structurally identical complete pair with no recognition" |
| `DESIGN.md` | §8 — "replacing the payload leaf with the **retained** island derivation creates the complete pair without another recognition" |
| `context.md` | §"Earley and ambiguity" — "replacing the delegated payload leaf with the retained island derivation produces the complete pair without another recognition" |
| `goal.md` | "an Earley-delegated one-island tree can splice the **retained** island derivation without another recognition" |
| `LEDGER.md` | "Complete resolver pairs and a **zero-recognition one-island Earley splice** are feasible" — the same superseded claim, in wording neither "retained" nor "another recognition" matches, which is why a phrase search missed it |

This list was rebuilt by searching for the CLAIM rather than the phrase. Two
audits reported the earlier, phrase-derived list complete; it was not, and the
fifth carrier surfaced only once the search stopped keying on wording. The
equal-root passages (`TODO.md`'s single-seed gate, `DESIGN.md`'s "equal root
meanings keep the predictive result") are deliberately NOT on this list: that
half still holds.

The cold recognition a document-scoped PDA pair costs is **linear in the
document** — the very cost PDA-first composition exists to avoid — so it is
quoted at three sizes rather than at five characters.

### 1.11 The tokenizer's three lanes, from all five real fixtures

Scanned sequentially, one fixture at a time, with the stdlib json decoder —
the question is what the FORMAT contains, not how lexic parses it, and this
INVENTORY builds no Qwen-scale `IrMap` and runs no historical reduce path.
(§3.4's `fixture-contract` rows do build full indexes over every fixture,
because there the construction is the thing being validated.)

```text
uv run python proto/tokenizer_validation_lanes.py --fixtures

fixture  hf_bpe   bytes=818       scan_cpu=0.000458  scan_peak_bytes=42773
fixture  gpt2     bytes=1355256   scan_cpu=0.223018  scan_peak_bytes=24775074
fixture  smollm2  bytes=2104556   scan_cpu=0.199903  scan_peak_bytes=23978510
fixture  qwen3    bytes=11422654  scan_cpu=0.631639  scan_peak_bytes=82257031
fixture  gemma4   bytes=33384568  scan_cpu=1.966292  scan_peak_bytes=293575488
```

**Lane 1 — ordinals.** Every fixture is dense `0 .. n-1`; not one has a
negative, repeated, sparse or above-count ordinal, and not one declares
`model.vocab_size`:

| fixture | entries | distinct | lowest | highest | negative | repeated | dense | gaps | declared size |
|---|---:|---:|---:|---:|---:|---:|:--|---:|---:|
| hf_bpe | 7 | 7 | 0 | 6 | 0 | 0 | yes | 0 | absent |
| gpt2 | 50257 | 50257 | 0 | 50256 | 0 | 0 | yes | 0 | absent |
| smollm2 | 49152 | 49152 | 0 | 49151 | 0 | 0 | yes | 0 | absent |
| qwen3 | 151643 | 151643 | 0 | 151642 | 0 | 0 | yes | 0 | absent |
| gemma4 | 262144 | 262144 | 0 | 262143 | 0 | 0 | yes | 0 | absent |

**Lane 2 — merges.** Both encodings occur and no dyad names a spelling outside
the vocabulary:

| fixture | merges | array form | string form | left absent | right absent | joined absent |
|---|---:|---:|---:|---:|---:|---:|
| hf_bpe | 2 | 0 | 2 | 0 | 0 | 0 |
| gpt2 | 50000 | 0 | 50000 | 0 | 0 | 0 |
| smollm2 | 48900 | 0 | 48900 | 0 | 0 | 0 |
| qwen3 | 151387 | 151387 | 0 | 0 | 0 | 0 |
| gemma4 | 514906 | 514906 | 0 | 0 | 0 | 0 |

**Lane 3 — pipeline spellings.**

| fixture | byte_fallback | fallback in vocab | unk | unk in vocab | fuse_unk | added | added absent from `model.vocab` | added id conflicts | remap chars absent |
|---|:--|---:|---|:--|:--|---:|---:|---:|---:|
| hf_bpe | no | 0/256 | — | — | no | 2 | 0 | 0 | 253/256 |
| gpt2 | no | 0/256 | — | — | no | 1 | 0 | 0 | 0/256 |
| smollm2 | no | 0/256 | — | — | no | 17 | 0 | 0 | 21/256 |
| qwen3 | no | 0/256 | — | — | no | 26 | **26** | 0 | 0/256 |
| gemma4 | **yes** | **256/256** | `<unk>` | yes | **yes** | 6415 | **1** | 0 | 3/256 |

Three facts decide the contract:

- Qwen lists **all 26** of its specials only under `added_tokens`; an index
  built from `model.vocab` alone cannot spell them, so a
  special-membership check against `model.vocab` would refuse the file.
- Gemma is the only fixture declaring `byte_fallback`, and it covers all 256
  spellings. The others' `0/256` is not a gap: they do not declare the table.
- SmolLM2 (21), gemma4 (3) and hf_bpe (253) have byte-level working-alphabet
  characters absent from the vocabulary — the `IrTokenizer.carries` case. A
  contract that required remap coverage would refuse three of five fixtures.

### 1.12 The shipped-bug baselines are pinned

```text
uv run python proto/nullable_quantifier_ambiguity.py

quantifier  star-ref          effective_differing_non_arm=1  public=Root(Pad('x'), List(()))
quantifier  plus-ref          effective_differing_non_arm=1  public=Root(Pad('x'), List((Gap(),)))
quantifier  optional-ref      raw_differing_non_arm=1        public=Root(Pad('x'), List(Gap()))
                                                             raw_earley=Root(Pad('x'), List())
quantifier  bounded-zero-two  effective_differing_non_arm=1
quantifier  bounded-one-two   effective_differing_non_arm=1
quantifier  exact-two         effective_differing_non_arm=0
quantifier  star-group        effective_differing_non_arm=1
quantifier  star-empty-rule   effective_differing_non_arm=1
leo-readout  deferred_before_any_tree=1  points_before_expansion=0
             points_after_expansion=2    points_after_a_tree_build=2
             no tree was built between the run and the first read

corpus  stage=canonical  grammars=15  quantified_nullable_sites=0
corpus  stage=codegen    grammars=15  quantified_nullable_sites=71
        per_grammar={'arithmetic.gbnf': 5, 'json.abnf': 14, 'json.ebnf': 14,
                     'json.gbnf': 14, 'json_arr.gbnf': 13, 'json_ws.gbnf': 11}
        atoms=['ws']

corpus-exposure  json.gbnf  chars=21  lift_on_points=1  lift_on_differing_points=0
                 lift_off_points=17  lift_off_arm_choice=0
                 lift_off_differing_points=14  lift_off_differing_families=14
corpus-exposure  json.abnf  chars=21  lift_off_points=17
                 lift_off_differing_points=14  lift_off_differing_families=14
corpus-exposure  json.ebnf  chars=21  lift_off_points=17
                 lift_off_differing_points=14  lift_off_differing_families=14
corpus-exposure  json_ws.gbnf   chars=21  lift_off_points=12
                 lift_off_differing_points=9   lift_off_differing_families=9
corpus-exposure  json_arr.gbnf  chars=7   lift_off_points=6
                 lift_off_differing_points=4   lift_off_differing_families=4
corpus-exposure  arithmetic.gbnf chars=4  lift_off_points=3
                 lift_off_differing_points=3   lift_off_differing_families=3

exposure-scaling  json.gbnf  chars=10   lift_on_points=0  lift_off_points=11
                  lift_off_differing_points=11  lift_off_differing_families=11
exposure-scaling  json.gbnf  chars=80   lift_on_points=7  lift_off_points=74
                  lift_off_differing_points=53  lift_off_differing_families=53
exposure-scaling  json.gbnf  chars=640  lift_on_points=63 lift_off_points=578
                  lift_off_differing_points=389 lift_off_differing_families=389
```

**The corpus is the exposure, not the control.** An earlier draft of this
report said the 15 shipped ground-truth grammars contain zero
quantified-nullable sites. That measured the **canonical** grammar. The parser
runs `codegen_grammar`, and the `@non-semantic` pass relaxes a required
reference to a nullable noise rule to `min=0` — which MAKES a
quantified-nullable site out of a rule that had none. At that stage there are
**71** of them, across `arithmetic.gbnf`, all three JSON formulations,
`json_arr.gbnf` and `json_ws.gbnf`; every one is a reference to `ws`.

And `ws` is a **bound model field**: `{"a": 1}` folds to
`JsonText(Object(BeginObject(Ws(''), Ws('')), …), Ws(''), Ws(''))`. So an
absent versus a present-but-empty `ws` is a difference the public model shows.
With `lift_optional_nullables` removed — which §5 requires — **14 of 17
ambiguity points** on a 21-character JSON document have an alternate family
that builds a *different* model, and **389 of 578** do at 640 characters. The
prototype counts differing POINTS and differing (point, family) PAIRS
separately, because a point can pack more than two families and a ratio mixing
the two denominators is a fact about neither. On these documents every point
packs exactly two families, so the two counts coincide — which is a
measurement, printed as both, not an assumption. A fix that only un-exempts quantifier
helpers would therefore **refuse ordinary JSON on every shipped JSON
formulation**, and the un-exempted point population grows linearly with the
document while `another_meaning` pays a whole-handle tree build and fold per
family at each point it does not skip.

**This reopens a gate the packet marks closed, and narrows the escape route.**
`TODO.md`'s `PLANNING REQUIRED BEFORE §8 — SEMANTIC FAMILY UNIVERSE` gate is
ticked `[x]`, and its own text rests on the falsified premise. Worse, the
obvious way out — excluding directive-created optionality from the count-family
universe — is already forbidden: `goal.md` rules that "Every family capable of
changing the requested target meaning enters this relation even when
normalization generated it", and these 71 families are exactly
normalization-generated and do change the model. So the remaining options are
narrower than "either/or":

1. keep a value-preserving normalization for exactly the directive-created
   relaxation — which is what `lift_optional_nullables` does today, except that
   it makes *present* win rather than preserving both, so it would have to be
   replaced by something that genuinely preserves the value; or
2. accept that the shipped JSON formulations become ambiguous under the fix and
   require a resolver, which changes what those grammars mean to every caller;
   or
3. rule that `goal.md`'s "even when normalization generated it" does not extend
   to a directive-driven `min=0` relaxation — a change to a settled decision,
   and the user's to make.

**USER DECISION REQUIRED**, and the `[x]` gate must be reopened before §8.

**The falsified "zero sites" statement survives in seven passages across five
active documents.**
This report does not edit active planning documents, so the coordinator folds
the correction into all seven passages below:

| Document | Passage |
|---|---|
| `CURRENT_BUG_REPORT.md` | §"Established scope" — "contain zero quantified-nullable sites, so no corpus dependency argues for silently choosing one count" |
| `TODO.md` | the `[x] PLANNING REQUIRED BEFORE §8 — SEMANTIC FAMILY UNIVERSE CLOSED` gate — "have zero such sites"; **this one also has to lose its tick** |
| `context.md` | §"Earley and ambiguity" — "All shipped GBNF, ABNF, and EBNF ground-truth grammars currently contain zero such sites" |
| `LEDGER.md` | the "Prototype 12 correction" section, carrying the same count |
| `INDEX.md` | the current-state paragraph — "The quantified-nullable semantic family and Leo-complete readout plans are now closed"; the family half is reopened here |
| `INDEX.md` | the packet list — `PROTOTYPE_13.md` is called "authoritative … plus the shipped quantified-nullable and Leo-readout scope". That scope is exactly what §1.12 falsifies, so folding the rows above while leaving this line enthrones the falsified source as the packet's authority on this very question |
| `INDEX.md` | the history table's `PROTOTYPE_13.md` row — "scopes both shipped ambiguity defects" — now wrong in both its scope and its count (§1.8b) |

The `BASELINE` table in that prototype now **asserts** the exact pre-fix
`(public, pda, earley, raw_earley)` answer of every case, so the source phase
cannot silently redefine what it compares against. The Leo proof is
strengthened: the deferred count and the first `ambiguity_points` read both
happen immediately after `.run()`, with the `0 → 2` transition and the
post-tree-build `2` recorded on the same kernel object.

Unchanged public parsing on each witness and on a **matched control** — the
same grammar shape with a non-nullable quantified atom, so the same quantifier
helper, fold and public entry are exercised — measured in-process, alternating,
minimum of five rounds of 2000 parses, with no other benchmark alive:

| case | affected CPU/parse | control CPU/parse |
|---|---:|---:|
| star-ref | 0.000085953 | 0.000010528 |
| plus-ref | 0.000110006 | 0.000010666 |
| optional-ref | 0.000008953 | 0.000010452 |
| bounded-zero-two | 0.000102518 | 0.000010467 |
| bounded-one-two | 0.000010849 | 0.000010296 |
| exact-two | 0.000012299 | 0.000011177 |
| star-group | 0.000084710 | 0.000010478 |
| star-empty-rule | 0.000082994 | 0.000007732 |

These are the pre-fix references, not a target, and they are **two absolute
numbers, never a ratio**: the two lanes cannot parse the same document (a
non-nullable `gap+` does not accept `"x"`), so the control does strictly more
scanning. What separates the fast rows from the slow ones is the **island
escape**, not the ambiguity check — `star-ref`, `plus-ref`,
`bounded-zero-two`, `star-group` and `star-empty-rule` island on `list` and pay
a full Earley sub-parse; `optional-ref`, `bounded-one-two` and `exact-two` do
not island and sit at or below their controls.

That island split is also a gap in the placement below:

```text
island-placement  star-ref          pda_islands=['list']  reaches_earley_tables=True
island-placement  optional-ref      pda_islands=[]        reaches_earley_tables=False
island-placement  bounded-one-two   pda_islands=[]        reaches_earley_tables=False
island-placement  exact-two         pda_islands=[]        reaches_earley_tables=False
```

`code_choices` is an Earley table the predictive runtime never consults. Three
of the eight witnesses are answered purely predictively, so nothing in
`code_choices` can make `pda_model` refuse them; a PDA-side placement in
`pda/analysis/gates/` is required and its cost is not measured here.

---

## 2 — The resolver-scope user decision

**USER DECISION REQUIRED.** Nothing below selects it. Feasibility is closed for
both candidates; the choice is a public contract and is the user's.

| Question | Island-local pair (today) | Complete-document pair |
|---|---|---|
| Public `Resolver` signature | unchanged | unchanged — both hand over two `ParseTree`s and take one back |
| Public *contract* | pair rooted at the island rule | pair rooted at the start rule — a deliberate pre-alpha contract change an existing resolver observes |
| Deterministic ordering | `(in hand, first differing)` — measured on both routes | same rule, same order; §B's constructor puts the engine's own derivation first |
| Both engines present the same pair? | **no today** — PDA gives `t`, Earley gives `root` | yes, by construction: one scope for both |
| Occurrence identity, ≥2 islands | not addressed — the pair never leaves the island | the delegated leaf object, one per occurrence, exactly one position each |
| Nested delegated regions | not addressed | one addressed splice per delegation level, innermost first; zero opaque leaves remain |
| Fused PDA with no document tree | nothing extra — it already has the island kernel | one cold Earley recognition + two tree builds, after inequality *and* an actual `resolve=` |
| Extra recognitions | 0 | 0 on the Earley-delegated path (splice); 1 on the fused PDA path |
| Extra tree builds | 2, from the island kernel already in hand | 2 island builds + 2 addressed splices, or 2 document builds |
| Shadow model/tree on the unambiguous path | none | **none** — the pair is built post hoc, from state already held |
| Retained state | the island kernel the sub-parse already holds, decided and discarded inline | the outer chart **plus a deferred decision and its derivations per ambiguous island occurrence** — today's island decides inline, so this is new retained state, not re-use |
| What is being decided | inequality at the island span | inequality at the document root — a **different question**: under a dropping parent the island differs and the root does not (harness row under a toy policy, §1.10) |
| Measured cold construction | 0.000074 s CPU (5-char witness) | 0.000009 s CPU splice; the PDA path's cold recognition is linear — 0.000059 / 0.000574 / 0.004555 s CPU at 5 / 80 / 640 characters |
| Context-sensitive resolver can tell the scopes apart | yes — retained witness: `scope-divergence` | yes, and it would see a different pair root |

The retained divergence witness, from `prove_scope_divergence`:

```text
scope-divergence  island_local_choice=('t', ('pair', ('onetwo',)))
                  complete_choice_island_part=('t', ('pair', ('one',), ('two',)))
                  diverges=True
```

One deterministic resolver, two scopes, two different chosen island
derivations. **It diverges by construction**: `context_sensitive` branches on
`str(first.symbol) == "root"` and inverts its preference, so this is a
*visibility* proof — it shows the pair's root is something a resolver can read
and act on — not evidence that a naturally written resolver would diverge. That
is enough for the decision at hand, because a contract a resolver can observe
is a contract that changes behaviour; it is not evidence about how often.

**Recommendation, with its cost stated — and with what it does NOT settle.**
The complete-document scope is the one that can satisfy the PDA/Earley
public-equivalence invariant, because the two engines demonstrably do not
present the same pair today and the island-local scope cannot be given to
Earley's document gate without narrowing what that gate is allowed to refuse.
Its costs are cold but not free: zero extra recognitions on the Earley
delegated path, one **document-linear** recognition on the fused PDA path, no
shadow on the unambiguous path, an addressed splice per delegation level, and
— newly established this round — a **deferred island decision with
per-occurrence retained state**, because today's island decides and discards
inline. Its price is a deliberate pre-alpha contract change: same signature,
different pair root, and a different *question* (a dropping parent makes the
island-local and document-root answers disagree on whether to refuse at all —
a harness row under a toy policy, §1.10), which existing island-local resolvers
would silently see. Choosing it also
obliges the implementation to re-scope the refusal, which nothing here prices.
The user rules.

---

## 3 — Mechanisms ready for production implementation

1. **Real-operation slot classification.** One open `IrTypeMap` of declared
   laws, composed over the authored expression trees, with a raising default
   naming operation and slot. Production adds rows for the emit families and
   for the product operations listed in §4, and holds every row against
   `differential_law` — on a channel the operation accepts, per
   `RETAINING_PROBES` — before scheduling it.
2. **The constructive infinite-SCC pair.** Certify → try every carrier → one
   growing closed walk → one addressed splice onto the engine's own derivation.
   No numeric parameter anywhere, and `O(E × (V + E))`.
3. **Occurrence-addressed splicing** for delegated interiors, at every
   delegation level, keyed on the `PayloadLeaf` object the kernel already
   injects per occurrence.
4. **The tokenizer's final validation contract** (§1.11 evidence), with its
   ordered verdicts:

   1. duplicate spelling in the encode index — *streaming*;
   2. negative ordinal — *streaming*;
   3. duplicate ordinal in the **encode** index — *streaming*;
   4. duplicate ordinal in the **decode** index — *streaming*;
   5. duplicate merge dyad — *streaming*;
   6. encode/decode bijection — *root cross-field*;
   7. contiguous ranks `0 .. n-1` — *root cross-field*;
   8. every pipeline special is a vocabulary spelling, checked **after** the
      added-token merge — *root cross-field*;
   9. segmenter consistency with the rank index — *root cross-field*.

   Every streaming-decidable lane precedes every root cross-field one. That is
   not cosmetic: `TODO.md` pins the tokenizer failure order as "full lower
   syntax first; earliest ordered semantic verdict second; **root
   missing/cross-field checks last**", and an earlier draft of this contract
   put the bijection check ahead of the duplicate-dyad check, which contradicts
   it. The order was changed to match, and the eight adjacent-boundary
   witnesses were re-pinned against the new order — `lane-1-before-lane-2`
   through `lane-8-before-lane-9`, each setting two adjacent lanes failing at
   once so the reported one is the pinned fact. That claim is itself CHECKED:
   `prove_boundary_witnesses` computes which of the nine lanes each witness
   actually offends and asserts both named lanes are among them.

   ```text
   boundary-witness  lane-1-before-lane-2  lanes_fired=[1, 2]        both_named_lanes_fire=True
   boundary-witness  lane-2-before-lane-3  lanes_fired=[2, 3, 4]     both_named_lanes_fire=True
   boundary-witness  lane-3-before-lane-4  lanes_fired=[3, 4, 6]     both_named_lanes_fire=True
   boundary-witness  lane-4-before-lane-5  lanes_fired=[4, 5, 6]     both_named_lanes_fire=True
   boundary-witness  lane-5-before-lane-6  lanes_fired=[5, 6]        both_named_lanes_fire=True
   boundary-witness  lane-6-before-lane-7  lanes_fired=[6, 7]        both_named_lanes_fire=True
   boundary-witness  lane-7-before-lane-8  lanes_fired=[7, 8]        both_named_lanes_fire=True
   boundary-witness  lane-8-before-lane-9  lanes_fired=[8, 9]        both_named_lanes_fire=True
   ```

   Two audits accepted the eight-boundary claim on the strength of the row
   NAMES; the third measured the inputs and found `lane-3-before-lane-4` made
   only lane 3 fire, so a swap of lanes 3 and 4 would have passed the suite.
   Lanes 3 and 4 also emitted byte-identical refusal text, which made them
   indistinguishable to a caller as well as to the suite. Both are fixed: each
   now names the index it refuses, the witness makes both fire, and the check
   above is mechanical rather than nominal.

   **The reported verdict is the first offending LANE, not the first offending
   ENTRY.** `_indexes((('a', -1), ('a', 0)))` reports the duplicate spelling
   (lane 1) even though an insertion-time validator would have refused entry 0's
   negative ordinal (lane 2) first. That is the choice, and it is deliberate: an
   entry-order verdict makes the refusal depend on the order a document happens
   to list its vocabulary in, which is not a property of the tokenizer being
   described. Streaming *decides* lanes 1 through 5 — each needs only the
   entries seen so far — and lanes 6 through 9 read two indexes and run only
   at the root; an accumulator records every lane it hits and the root reports
   the lowest-numbered one. The counterexample is executed
   (`prove_lane_order_contract`), and `WITNESSES` now pins every adjacent lane
   boundary separately, because the independent oracle deliberately shares the
   order and so cannot catch a reordering by itself.

   Accepted deliberately, because real fixtures need it: sparse and
   above-count non-negative ordinals; merge dyads whose parts are outside the
   vocabulary; a declared byte-fallback table or unknown spelling the
   vocabulary does not cover; byte-level remap characters outside the
   vocabulary; and added tokens absent from `model.vocab`, which are merged
   with their declared ids. An added token whose id **contradicts** the
   vocabulary is refused — two ids for one spelling cannot be resolved by
   preferring either.

   ```text
   uv run python proto/tokenizer_validation_lanes.py
   contract  sparse-accepted                     verdict=None  oracle_agrees=True
   contract  above-count-accepted                verdict=None  oracle_agrees=True
   contract  negative-refused                    verdict=tokenizer: ordinal -1 is not a token id
   contract  repeated-ordinal-refused            verdict=tokenizer: duplicate ordinal 3 in the encode index
   contract  merge-parts-outside-vocab-accepted  verdict=None
   contract  duplicate-dyad-refused              verdict=tokenizer: duplicate merge dyad ('a', 'b')
   contract  non-contiguous-rank-refused         verdict=tokenizer: merge ranks are not contiguous from 0
   contract  special-outside-vocab-refused       verdict=tokenizer: special '<|end|>' is not in the vocab
   contract  broken-bijection-refused            verdict=tokenizer: encode and decode are not inverse
   contract  segmenter-disagrees-refused         verdict=tokenizer: segmenter disagrees with the ranks
   contract  lane-1-before-lane-2  verdict=tokenizer: duplicate spelling 'a'
   contract  lane-2-before-lane-3  verdict=tokenizer: ordinal -1 is not a token id
   contract  lane-3-before-lane-4  verdict=tokenizer: duplicate ordinal 3 in the encode index
   contract  lane-4-before-lane-5  verdict=tokenizer: duplicate ordinal 0 in the decode index
   contract  lane-5-before-lane-6  verdict=tokenizer: duplicate merge dyad ('a', 'b')
   contract  lane-6-before-lane-7  verdict=tokenizer: encode and decode are not inverse
   contract  lane-7-before-lane-8  verdict=tokenizer: merge ranks are not contiguous from 0
   contract  lane-8-before-lane-9  verdict=tokenizer: special '<|end|>' is not in the vocab
   contract  exhaustive-pairs  ordered_pairs=441
             twin_equals_eager_construction_per_witness=21  distinct_verdicts=10
   added-merge  added-outside-model-vocab-merged   merged_entries=4  refusal=
   added-merge  added-agreeing-with-vocab-accepted merged_entries=3  refusal=
   added-merge  added-contradicting-vocab-refused  refusal=tokenizer: added token 'ab'
                claims id 9 but the vocabulary spells it 2
   admission  qwen3  admitted=True  needs_added_tokens_outside_model_vocab=True
   admission  gemma4 admitted=True  needs_added_tokens_outside_model_vocab=True

   uv run python proto/tokenizer_validation_lanes.py --fixtures
   fixture-contract  hf_bpe   merged_entries=7       merge_dyads=2
                     specials=2      all_nine_lanes_verdict=None  cpu=0.000121
   fixture-contract  gpt2     merged_entries=50257   merge_dyads=50000
                     specials=1      all_nine_lanes_verdict=None  cpu=0.548963
   fixture-contract  smollm2  merged_entries=49152   merge_dyads=48900
                     specials=17     all_nine_lanes_verdict=None  cpu=0.406940
   fixture-contract  qwen3    merged_entries=151669  merge_dyads=151387
                     specials=26     all_nine_lanes_verdict=None  cpu=1.356092
   fixture-contract  gemma4   merged_entries=262145  merge_dyads=514906
                     specials=6415   all_nine_lanes_verdict=None  cpu=3.920601
   ```

   All **nine** lanes run on every real fixture's merged indexes — the
   document-level twin, the independently written oracle and the eager
   construction all agreeing — not three of nine read off the inventory. Qwen's
   26 specials and Gemma's 6415 go through `merged_encode` at full scale, which
   is where that mechanism actually has to work.

   The document-level twin is held against two things, not one. Per witness it
   must equal what the CONSTRUCTOR really decided (`None`, or its refusal
   message) — the load-bearing comparison, since twin-versus-oracle alone would
   be near-tautological once both are pinned to the same expected verdict. Then
   across all 441 ordered pairs of the 21 witnesses the twin, the oracle and
   the eager construction must agree on whether two documents are
   interchangeable. The oracle rebuilds each lane from primitive counts and
   carries its own missing-special search rather than sharing the twin's, so a
   shared helper cannot make them agree on the lane being checked. It does share
   the ORDER, because the order is the contract.

5. **BUG 2 — complete Leo readout** in `ambiguity_points`, expanding every
   deferred key before walking the links. Its cost is in §4, not here.

**Deliberately NOT listed as ready: the quantified-nullable classification
(BUG 1).** Its Earley-side placement is understood (below), but two of its
preconditions are open — the family universe is a `USER DECISION REQUIRED`
(§1.12) and its PDA-side placement is unpriced (§4) — so it belongs to the
blocked column, not this one. The placement is recorded here because it is
settled *given* those two answers:
   - the quantified-nullable family classification belongs in `code_choices`
     (`parsing/earley/kernel/tables/records.py`), which already derives
     `code → authored choice identity` at **table-compilation** time: a
     quantifier helper keeps its shared negative identity only when its atom is
     non-nullable or its quantifier admits exactly one count, and takes distinct
     arm ids otherwise. The nullability it reads is a grammar property the
     analysis already computes (`GrammarAnalysis.atom_nullable`). The paid loop
     never reads `code_choice` — only the forest readers do — so a correct fix
     cannot touch the kernel's inner loop. No per-character check, no dynamic
     classification, no instrumentation for tests. It does NOT reach the three
     witnesses the predictive runtime answers without an Earley chart.

---

## 3b — Fold obligations this round cannot discharge itself

`PROMPT_14.md` forbids editing the active planning documents, so the following
corrections are handed over rather than made. Each is a fact this round
established against the shipped tree; leaving any of them unfolded would let
§8 proceed on a premise the evidence disproved.

| Obligation | Where | Why |
|---|---|---|
| The "zero quantified-nullable sites" claim is false at the codegen stage (71 sites, 6 grammars) — seven passages, including the two `INDEX.md` lines that make `PROTOTYPE_13.md` authoritative on that scope | `CURRENT_BUG_REPORT.md`, `TODO.md`, `context.md`, `LEDGER.md`, `INDEX.md` (×3) | §1.12 |
| The `[x] PLANNING REQUIRED BEFORE §8 — SEMANTIC FAMILY UNIVERSE CLOSED` gate must be **reopened** | `TODO.md` | its text rests on the falsified premise, and the remaining options are a `USER DECISION REQUIRED` (§1.12) |
| A third shipped defect (engine pair scope + refusal message) must be recorded, counted and owned — a new `## BUG 3` section plus every passage counting two | `CURRENT_BUG_REPORT.md` (opening, both "Both …" sentences, closing), `INDEX.md` (authority map and history table), `LEDGER.md` ("both shipped defects") | §1.8b |
| "the retained island derivation … without another recognition" is only half true — the recognition count holds, the free re-use does not | `TODO.md` (inside the ticked `[x] RESOLVER MECHANISM PART CLOSED` gate), `DESIGN.md`, `context.md`, `goal.md`, `LEDGER.md` ("zero-recognition one-island Earley splice") | §1.10 |
| The tokenizer lane order was changed to put every streaming-decidable lane before every root cross-field one, matching `TODO.md`'s pinned failure order | none — the change is in this round's prototype; the row is here so the coordinator sees the alignment was deliberate | §3.4 |
| The packet inventory and the chronology do not yet list `PROTOTYPE_14.md`, `P14_ADVERSARIAL.md`, the three new prototypes, or `resolver_pair.py`'s widened scope (it now pins the third defect's baseline) | `INDEX.md`, `LEDGER.md` | routine folding |

## 4 — Implementation-time proofs still required

- **Product operations that do not exist yet.** Collection finish, root
  finalization, meaning comparison and keyed-accumulation finish are
  target-supplied and absent from `src` today. Each must add a law row and pass
  `differential_law` before the compiler may schedule it; until then they are
  unaudited by construction, and an undeclared one meets the raising default
  (executed in `prove_unknown_operation_refuses`).
- **`foldkit`'s named ctors** (`first_rest`, `passthrough`, `int`) must declare
  laws or leave the completion path.
- **Emit-family laws**, if any target ever emits through `IrDocConcat`,
  `IrDocJoin`, `IrGroup`, `IrNest`, `IrLine`, `IrEscape`, `IrEscapePoint` or
  `IrSpellable`.
- **Per-arm classification.** The `IrTypeMap` refusal shape (`cc-item[0]`) is
  decidable at completion time, where the packed family names one arm. Whether
  production takes that refinement is an implementation decision with its own
  proof.
- **The infinite-SCC pair's residual class.** `construct_pair` certifies the
  component, splices, and then CHECKS that the two complete meanings differ,
  raising a named `PairRefusal` when they do not. The argument that they always
  will — the difference travels up the same carrying edges the carrier closure
  was built from, and from there injectively to a requested root — is prose,
  not a proof, and no witness among these grammars exercises the refusal. A
  production implementation either proves that class empty or keeps the check
  and the refusal.
- **A `YIELD` span proof.** What is executed today is span sensitivity — three
  views, three texts. The sharper premise the refusal rests on, that two
  families of ONE equal-span component can drop different subtrees and spell
  that span two ways, is NOT executed: building a real drop-aware view for two
  families needs the compile pipeline's fold. Refusing is the conservative
  direction, so the unexecuted premise can only over-refuse, but it is an
  obligation and not a result. 22 of the 45 refused carrier slots are the
  reducer's `YIELD` default over a focus with a dropped rule below it. The
  prototype's licence — nothing reachable below the focus is dropped — is sound
  but coarse; a production classifier that wants those slots must prove
  something sharper (for instance, that no *reachable and nullable* rule is
  dropped) and hold it against a differential of its own.
- **The exact channel index.** This module numbers the channel by contributing
  references over the normalized grammar. The real channel is the binding
  view's `fields_of`, which also splices hoisted groups and quantified repeats;
  `prove_slot_alignment` names the two edges where the coordinate systems
  already disagree, and production must read the real one.
- **Parse-performance.** Every number in this report is an external prototype
  measurement. None of them is production throughput. The structural comparison
  the bugfix needs is specified in §5 and has not been run.
- **The complete Leo readout is not free.** `ambiguity_points` runs on every
  parse, and the deferred-key population is linear in the document — 2 / 17 /
  129 / 513 keys at 10 / 160 / 1280 / 5120 characters on `json.gbnf` — so eager
  expansion on the unambiguous path reverses part of what Leo buys and must be
  measured under §5's cross-process discipline.
- **A PDA-side placement** for the quantified-nullable classification, for the
  witnesses the predictive runtime answers without an Earley chart.
- **Integrated ambiguity memory**, completion-time dense numbering and
  family-aware dependency edges, production custom-completion traffic and
  paid-loop neutrality — all unchanged from `PROTOTYPE_13.md`.
- **The fused-product zero-allocation control** still cannot be proved until
  landed factories are wired to a refusing control; the protocol stands, the
  result does not.

---

## 5 — The post-fix differentials and the regression comparison

Recorded executably in `nullable_quantifier_ambiguity.py`:

- every case except `exact-two` must **refuse** under `compiled.parse(text)`
  with no resolver, on the public route, forced `pda_model` and forced
  `earley_model` alike, naming the rule and the occurrence counts;
- `exact-two` must still return `Root(Pad('x'), List((Gap(), Gap())))`;
- with a resolver, all three routes must return its choice and be handed the
  same pair under whichever scope §2 rules;
- `optional-ref` must agree between the raw and lifted routes — today they
  return `List(Gap())` and `List()`, so `lift_optional_nullables` is removed or
  replaced, never kept beside the fix;
- the six exposed ground-truth grammars (`arithmetic.gbnf`, `json.gbnf`,
  `json.abnf`, `json.ebnf`, `json_arr.gbnf`, `json_ws.gbnf`) must still parse
  ordinary documents. Today they do only because `lift_optional_nullables`
  hides the family; with the lift removed and no further condition they refuse.
  The other nine must reparse to byte-identical models and round-trip;
- `ambiguity_points` returns 2 on the Leo witness with no intervening tree
  build, and the same 2 afterwards;
- `cyclic_meaning`'s witnesses keep their verdicts — the quantified-nullable
  family is a separate universe.

Regression comparison: the classification is present on every parse, so it is a
**structural** change — two trees, **cross-process**, alternating, with a
byte-identical control tree through the same harness to read the floor. Rows:
the 15 ground-truth grammars under their own flavours, the generic catalog
witness, and the Qwen document; sequential first, then `cores=AUTO`, never two
multithreaded rows at once; process CPU and wall reported separately with the
floor beside them. **No parse regression is accepted by this report.** The user
gives the final go-ahead after isolated attribution, even for a bugfix.

---

## 6 — Rejected candidates, and why they stay rejected

| Candidate | Why it is still rejected |
|---|---|
| Numeric family-census or semantic-lap caps | arbitrary; `ring-depth3` and the two-key witness disprove any fixed lap count, and the §1.7 construction needs none |
| One-lap `FastTree` enumeration as the exact relation | unsound — `ring-depth3-one-lap-misses` and `two-key-cycle-bounded` both differ exactly, and the one-lap lane does not |
| Chart-wide Cartesian assignment enumeration | `2^k` in reachable arm points; the mechanism is `O(V+E)` plus per-node option products |
| "Unroll the cycle twice" for a `resolve=` pair | a numeric parameter standing in for a proof; replaced by one closed walk of the component's own edges |
| Requiring a SIMPLE cycle through the certified carrier | deciding whether one exists is the directed two-disjoint-paths problem, and the search was exponential; it also refused `UPSTREAM_CARRIER` and would have missed `SIDE_CYCLE`, both real GBNF grammars with a real pair |
| Committing to the first certified carrier | `_carriers` returns an upward closure, and a member of it need not lie on any closed carrying walk; every carrier is tried instead |
| Building the pair from the carrier's own derivation and its one-lap extension | neither element was then the derivation the parse produced, so a take-first resolver would have silently changed the answer |
| A blanket `const` licence for `YIELD` on an equal-span component | two families of one span can drop different subtrees, so the text view is a function of the derivation; only a proved span-fixed focus licences `const` |
| Classifying an operation by name, sample values or callable identity | none of the three survives a renamed or re-authored operation; the table keys on the type and composes declared rows |
| A silent `IR_DEFAULT` catch-all in the law table | it is exactly the failure the table exists to prevent; an unregistered operation must raise |
| Declaring emit-family laws now | nothing differentials them; an unproved law is worse than a named refusal |
| A caller-side "materialize the forest first" precondition on `ambiguity_points` | order-dependent by construction; the `0 → 2` readout is the counterexample |
| `lift_optional_nullables` as an ambiguity solution | it erases the absent/present family and changes which model wins — `List(Gap())` lifted versus `List()` raw |
| An entry-order tokenizer verdict | it makes the refusal depend on the order a document lists its vocabulary in, which is not a property of the tokenizer; the lane order is the contract, and the counterexample is executed |
| Reporting the corpus census from the CANONICAL grammar | the parser runs `codegen_grammar`, where the `@non-semantic` relaxation creates 71 quantified-nullable sites; the canonical number said zero and inverted the conclusion |
| A quantified-nullable fix placed only in `code_choices` | three of eight witnesses never reach an Earley table; the predictive runtime answers them without a chart |
| Quoting the document-scoped PDA pair's cold cost at one document size | that recognition is linear in the document, and the user is ruling on a public contract |
| Requiring dense `0 .. n-1` tokenizer ordinals | no fixture declares `vocab_size`; density is an observation about five files, not a format law, and refusing sparsity would refuse a legal file for no gain |
| Requiring merge parts to be in the vocabulary | zero occurrences in five fixtures, and the ranked-merge rewrite never needs the parts to be tokens |
| Checking specials against `model.vocab` | Qwen's 26 specials live only in `added_tokens`; the check runs after the merge |
| Requiring byte-fallback or remap coverage | gemma4 is the only fixture declaring fallback; remap gaps are the documented `carries()` case in three of five fixtures |
| Retaining a shadow model or tree for a document-scope pair | unnecessary — §1.10 shows the pair is built post hoc from state already held |

---

## 7 — Commands and provenance

Every row below ran sequentially in this repository, one process at a time, on
a machine with no other benchmark, pool or agent alive. Exit codes are the
unpiped process status.

```text
uv run python proto/operation_slot_laws.py             exit 0
uv run python proto/scc_resolver_pair.py               exit 0
uv run python proto/resolver_pair.py                   exit 0
uv run python proto/tokenizer_validation_lanes.py      exit 0
uv run python proto/tokenizer_validation_lanes.py --fixtures   exit 0
uv run python proto/nullable_quantifier_ambiguity.py   exit 0
uv run python proto/cyclic_meaning.py                  exit 0
uv run python proto/ambiguity_interaction.py           exit 0
uv run python proto/keyed_product_rows.py              exit 0

uv run ruff format  <the five files>   All formatted
uv run isort        <the five files>   All sorted
uv run ruff check   <the five files>   All checks passed
uv run pyright      <the five files>   0 errors, 0 warnings

git status --short -- zzz_current_work   two revised .py, one ruff-cache entry
```

**Working-tree footprint, unscoped.** Two revised prototypes
(`nullable_quantifier_ambiguity.py`, `resolver_pair.py`), three new untracked
prototypes, this report and the adversarial record. Two intermediate actions
touched files this effort does not own, and both were undone rather than
described:

- a `ruff format` over the whole `proto/` directory reflowed 28 untouched
  prototypes — **reverted with `git checkout`**, because a formatting change to
  a prototype nobody re-ran is not evidence of anything;
- a `find … -name __pycache__ -exec rm -rf` cleanup deleted **22 tracked**
  `proto/__pycache__/*.pyc` files. An earlier draft of the adversarial record
  called those deletions pre-existing; they were not, they were this round's,
  and all 22 have been **restored with `git checkout`**. `git status --
  proto/__pycache__` is now empty.

The tracked `proto/.ruff_cache/` entry is modified because every `ruff`
invocation writes to it — the investigator's and every reviewer's alike. An
earlier `git status -- proto/*.py` line is deliberately replaced above: a glob
over `.py` cannot see a deleted `.pyc`, which is precisely how the deletion
went unnoticed.

`keyed_product_rows.py` is rerun because `tokenizer_validation_lanes.py`
imports its `Indexes` record and its duplicate-detection helpers; nothing in it
was changed.

Forbidden-construct search over the five touched files found no
`eval`/`exec` builtin call, no `Any`, no `cast`, no `-> object`, and no
`# type: ignore`, `# noqa` or `# pylint: disable`. The only `.eval(` hits are
the IR action-body protocol method lexic itself defines.

The fixture inventory is the only row that touches a large file. It was run
once, in its own process, sequentially, and reports bytes, process CPU, wall
and peak traced memory per fixture separately (§1.11). It is a format
inventory, not a parser benchmark, and no number in it may be read as one.
