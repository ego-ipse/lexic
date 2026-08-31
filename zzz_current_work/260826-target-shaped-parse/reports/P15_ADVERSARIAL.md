# P15 adversarial record

The sequential review loop for `PROMPT_15.md`. Every reviewer is a fresh,
read-only, synchronous `general-purpose` agent, run one at a time with no
benchmark, measurement or other agent alive. **Fable was not used at any
point and was not substituted for any role.**

This file records every review prompt verbatim, every finding, its disposition,
the rerun that verified the fix, and the verdict.

---

## 0 — The investigator's own passes, before any reviewer

Recorded because they changed the deliverable, not to pad the record.

1. **The island grammars had the wrong start rule.** The first draft handed
   each witness the OUTER grammar as its island tables, so `island_run` ran the
   document's start rule inside the island and the island's own meaning was the
   document's. Cases 1 and 2 passed by accident and case 3 published no seed at
   all. Fixed by giving the island its own `t`-rooted grammar; every case then
   published the seed its case needs.
2. **The interaction witness was not an interaction.** The root tested for
   `(two, two)` while the engine's own derivation already made `"two"` the
   baseline at both occurrences, so a single flip was visible and the case
   proved nothing. Fixed by testing for the ALTERNATE at both occurrences, and
   the witness now PINS that: it asserts the marker is not any occurrence's
   baseline and is among its alternates, so the case cannot silently rot back
   into an ordinary one-flip difference.
3. **"every alternate dropped" was reported for a document with no
   alternates.** The unambiguous control took the drop label, which would have
   let a control with a silently missing seed pass as a drop. Split into a
   distinct `no-alternate` reason, and the control now additionally asserts
   zero seeds, zero lookups and zero descent steps.
4. **The set comparison was order-sensitive.** Mechanism and oracle sets were
   compared as ordered lists, which would have failed or passed on dedup order
   rather than on content. Replaced with an order-free multiset comparison.
5. **The occurrence descent walked the whole chart.** The first descent pushed
   every child of every node, which is document-proportional and would have
   made the "no ambiguity state" claim false in cost if not in kind. Pruned by
   the compiled rows' own reachability, so it is bounded by the sub-chart that
   can hold the occurrence — and the report states plainly that production does
   not search at all.
6. **Eviction equality was asserted on the residency token.** Rebinding after
   release mints a new product id, so comparing raw rows compared the token.
   Fixed to compare rows modulo the token, which is what "eviction changes
   residency only" actually claims.
7. **A forbidden `object` annotation.** The flatness walk was typed
   `list[object]`. Replaced with an exhaustive `Flat = int | str | tuple[Flat,
   ...]` alias, which makes the walk's guarantee a type rather than a comment.

Gates before calling any reviewer: `uv run python
proto/island_continuation.py` exit 0; the six named prototypes rerun
sequentially, all exit 0; `ruff format`, `isort`, `ruff check` and `pyright`
clean on the new file; `git status --short -- src tests pyproject.toml .wiki`
empty; `git diff --check` clean. (An earlier draft of this line said
`git status --short` itself was empty. It is not, and it should not be: the
effort's own documents are tracked and modified, because they ARE the
deliverable. Reviewer 1's F10 caught the overstatement.)

---

## 1 — Reviewer 1 — `island semantics adversary`

Prompt, verbatim:

```text
Read the repository instructions, STYLE, the complete target-shaped-parse
packet, PROMPT_15.md, every prototype it names, island_continuation.py, and the
draft Prototype 15 report. Try to falsify static continuation settlement,
cache identity/lifetime, exact multi-island composition, occurrence identity,
and the complete-Earley oracle. Look specifically for one-flip reasoning,
baseline-dependent convergence, toy policies presented as real operations,
grammar-specific assumptions, circular oracles, and claims broader than the
executable witness. Read-only; no edits or benchmarks. Return substantive
findings with exact file:line evidence and READY only if none remain. Ignore
prose nits.
```

**Verdict returned: NOT READY — twelve findings, four blocking.** Every one is
recorded below with its disposition and the rerun that verified it. Nothing was
argued away: each blocking finding changed the executable artefact.

### F1 (blocking) — the DROP certificate indexed the authored body in the wrong channel

The row's slot came from `laws.contributing` over the NORMALIZED arm while the
law came from the AUTHORED body, whose channel is the binding view's
`fields_of` — which splices a hoisted group's interior and a quantified
repeat's ELEMENTS into the parent (`compile/reduce/fold.py::contribute`), so the
real width is input-dependent. Under `root ::= a b* c` with the body
`IrArg(2)`, the authored index names `c` at one repeat count and a `b` at
another; the row would have marked the repeat `const` and dropped an
observable occurrence. `PROTOTYPE_14.md` §4 carried exactly this as an open
obligation and Prototype 15 had promoted the same unclosed coordinate to a
semantic verdict without carrying the obligation forward.

**Disposition: fixed, conservatively, and the obligation is now carried.**
`aligned_rules` compares the canonical and normalized contributing-reference
sequences arm for arm; a rule that disagrees keeps NO law, so every hoisted
group and quantified reference falls to the exact executed relation. A body
that never indexes its channel (a splat, a constant, a predicate) is
splice-invariant and is exempt, because its class is the same at every width.
The report states the refusal in §2.1, prices it in §8 — GBNF's injective
verdicts go from 15 to 0 — and §11 names reading the real `fields_of` as the
production obligation.

### F2 (blocking) — a bare `id()`-keyed registry presented as a safety property

`parsing/caches.py` says a bare `dict` keyed on `id(...)` must PIN its key
objects to stay correct against address reuse. The registry pinned nothing and
the report read the missing reference as a safety property; the hazard was live
inside the prototype, whose per-witness grammars and reducers become
unreachable as soon as `run_witness` returns.

**Disposition: fixed.** The entry now holds the grammar and the reducer
strongly and re-checks identity on every hit, raising by name on a mismatch.
The report says plainly that the pin is correct AND immortal-until-released,
that production's mortal owner is the `CompiledGrammar` artefact through
`parsing.caches`' `memo`/`track` (IR values are not weak-referenceable —
`IrAst` and `Reducer` both refuse `weakref.ref`), and that adopting the table
into that protocol is production work `cache_lifetime.py` already proved.

### F3 (blocking) — counters whose zeros could not fail

`document_recognitions` was never incremented anywhere and `mechanism_trees`
only inside the resolver helper, so the round's headline "no second
recognition, no tree" assertions were unfalsifiable — while every row printed
`oracle_trees >= 4`, several of which the MECHANISM built.

**Disposition: fixed by construction.** Every derivation in the module now goes
through one `build_tree` and every whole-document recognition through one
`run_document`, and each build is attributed to a lane: `seed_trees`,
`one_flip_trees`, `oracle_trees`, `resolver_trees`, `settlement_trees`. The
rows report all of them. `document_recognitions=1` on every witness — the one
delegated recognition — and `settlement_trees=0` is now a statement about a
code path with exactly one producer.

### F4 (blocking) — the `const` shortcut was consulted after the work it avoids

`outer_run` ran first and the island enumerated its complete alternate set
before `settle` ever read a row, so the shortcut could only discard alternates
already built and folded.

**Disposition: fixed, and the saving is now measured.** Binding happens before
recognition and the delegate reads the table FIRST: `unobservable_rule` is the
rule-level half of the DROP certificate, and an island whose every row is
unobservable publishes its baseline and enumerates nothing. Case 1 records
`skipped_enumerations=1`, `seed_chart_nodes=0`, `seed_products=0` and
`seeds=0` against the control run's `control_seeds=1`.

*(Superseded figure, kept so the trail is readable: this originally cited
`seed_trees=1` against `control_seed_trees=3`. Reviewer 2's B1 fix removed the
island's redundant second derivation, so BOTH runs now build one tree and the
saving shows in the chart/product/seed columns instead. Re-run against the
columns above, not against the 3.)* §11 states the prototype's remaining weakness honestly:
an Earley delegate does not receive its consumer, so only the rule-wide half
can fire before enumeration, while production — entering the island from its
contextual clone — has the per-occurrence row at entry.

### F5 — the `slot` half of the key was never load-bearing

Every witness discriminated by consumer RULE.

**Disposition: fixed with a witness.** `slot-discriminating` is `root ::= t t`
with the authored action `IrArg(1)`: slot 0 classifies `const` and its
occurrence is dropped, slot 1 classifies `ident` and its occurrence proves
inequality. A rule-granular table cannot express that row.

### F6 — the oracle checked a SET only on the EXECUTE witnesses

On a statically settled witness the only oracle contact was a boolean the
witness table authored, so an unsound drop would have passed.

**Disposition: fixed.** Every witness now runs twice; the exact per-node lane
over the full-enumeration control is compared with that control's oracle on
every row (`exact_lane_matches_control_oracle`), and the shortcut run's oracle
is compared with the control's. `prove_drop_is_not_a_guess` additionally
collapses ONLY the occurrences the rows drop, leaving every other occurrence
admitted, and requires the two root meaning sets to be equal — an unsound drop
shows up as a set that grew.

### F7 — oracle independence was claimed without its scope

`_all_leaf_meanings` is shared by the seed publisher and the oracle.

**Disposition: fixed in prose.** §9 now states that independence holds for the
OUTER document (traversal and enumeration both differ) and explicitly not for
the island, whose exact set IS the seed, with the cost isolated in the
`seed_trees` lane.

### F8 — the shipped-reducer differential agreed only where the island cannot matter

**Disposition: stated, not papered over.** A shipped row can only agree on a
document the shipped gate does not refuse, and that gate refuses on the
generated MODEL, so any island with two derivations refuses — even when both
mean the same value. `CompiledGrammar.reduce` has no `resolve=` channel today,
so no shipped value exists for a live island choice. The report says so, and
adds what IS checkable: an
`island_value_stands_in_the_shipped_value` column, asserted against the
compiled row, which separates a carrying consumer from a constant one. §11
carries the limit.

### F9 — mechanism and oracle unpack the forest under different derivation semantics

Per-occurrence family choice versus one family per key per derivation; they
coincide only when no key is reachable twice.

**Disposition: fixed by checking the precondition.**
`prove_oracle_precondition` runs on every witness and asserts that no chart
node has two parents and no arm-choice key is claimed twice. §9 states which
relation is the design's where it would fail, and §11 carries it.

### F10 — done-gate provenance was false

`git status --short` was not empty and the tracked `.pyc` was not restored;
`INDEX.md` linked a `REVIEW_15.md` that did not yet exist.

**Disposition: corrected.** §12 now claims only what is true —
`git status --short -- src tests pyproject.toml .wiki` empty and
`git diff --check` clean — and says explicitly that the effort's own tracked
documents ARE modified because they are the deliverable, listing them. The
`.pyc` is restored at the end of the round, after the last run. `REVIEW_15.md`
is written when Reviewer 3 returns.

### F11 — §4 compared two different units

`executed_products` counts operation applications; the Cartesian figure counts
assignments.

**Disposition: fixed.** The 7-versus-8 sentence is gone; §4 keeps the
structural result in one unit (`2 × 1 × 2` instead of `2 × 2 × 2` at the
meeting node) and says the two columns are not compared to each other.

### F12 — `grow` was made load-bearing for a refusal, and one `grow` is not injective

`IrEach(IrArg(k))` classifies `grow` but yields `()` for every slot value over
an empty focus, and the probe domain always supplies a non-empty focus.

**Disposition: fixed by narrowing.** A body reaching `IrEach`, `IrChildren`,
`IrRebuild` or `IrAt` now keeps no law at all, so the injective lane cannot
rest on a retained mapped focus. §2.1 states it.

### What the reviewer could not falsify

Recorded so the fixes are not read as touching them: no one-flip reasoning in
the DROP lane; the over-approximation directions correct and opposite; the
descent's reachability pruning sound rather than merely cheap; composition of
per-step injectivity along one realized route sound; the topological walk and
slot interleaving correct; the typed flatness walk a real static guarantee;
split-versus-arm respected in both lanes; the delegated seam real production;
the interaction witness genuinely pinned; the cyclic refusal real and checked;
the focus-free guard structural.

### Rerun after the fixes

```text
uv run python proto/island_continuation.py   exit 0
uv run ruff format / isort / ruff check      clean
uv run pyright                               0 errors, 0 warnings
```

---

## 2 — Reviewer 2 — `island performance and architecture adversary`

Prompt, verbatim:

```text
Read the same revised packet. Determine whether the proposal preserves PDA
islands or merely renames whole-document escalation. Challenge every claimed
hot-path absence, allocation count, cache owner, release boundary, resolver
tree cost, and static shortcut. Check that unambiguous parsing receives no new
state or callback and that complete trees are built only for an invoked
resolver after root inequality. Confirm that production measurements remain
open and no external timing is called a source result. Read-only; no edits or
benchmarks. Return substantive file:line findings and READY only if none
remain. Ignore prose nits.
```

**Verdict returned: NOT READY — twelve findings, four blocking.** Recorded
below with dispositions and the rerun that verified them.

### A2 (blocking) — the EXECUTE lane needs a whole-document chart, unstated

`exact_root_meanings` built `algebra.build_chart` over the outer kernel and
applied the reducer at EVERY node, so "one set per node on the union of the
live continuations" was true of cardinality only. And a PDA-first parse holds
no SPPF (`parsing/products.py` reaches Earley only on `PdaFail`), so obtaining
that chart is Earley escalation — on the 73.9–95.6% of shipped rows the census puts
in EXECUTE.

**Disposition: reduced where it was reducible, and stated where it was not.**
The lane now folds every node ONCE to its baseline — the parse's own product,
counted in its own `baseline_products` lane — and runs the SET lane only on the
DIRTY CONE: the upward closure of nodes holding a live occurrence or carrying
more than one family. Everything outside has only non-dirty descendants and
takes its baseline. A new `distant-island` witness makes the difference
measurable: 161 chart nodes, 161 baseline folds, **1 dirty node, 2 set
applications** on an 81-character document. What could not be reduced is
stated: §3.5 says the chart is Earley's, that CONST and INJECTIVE settle
without it (`settlement_chart_nodes=0` on cases 1, 2, 5a, 5b), and that on
shipped grammars most ambiguous spans would escalate. §11 carries it.

### B1 (blocking) — the unambiguous island gained work

The island built a baseline derivation AND re-derived it during enumeration, so
an unambiguous island cost two trees where production costs one, while three
documents said "no tree".

**Disposition: fixed.** The island's set now comes from the same per-node lane
the document uses, so it builds exactly one derivation — the engine's own,
which is what `islands.island_parse` builds today. `seed_trees=1` on every
single-island witness. The zero-claims are rescoped to what is true: no
alternate, no node set, no chart walk, no COMPLETE-DOCUMENT tree — and the
module's own closing invariant now says so.

### C3 (blocking) — linear replaced by exponential, unstated

`another_meaning`'s docstring declares itself linear in ambiguity points; the
exact relation is a per-node product.

**Disposition: stated, and partly reduced.** §4 now says it outright — exactness
costs that asymptotic class, the certificate and the dirty cone bound how many
nodes pay but not the local product, and no bound is claimed. §11 lists it as
the round's largest performance consequence. The reduction is real: the island
lane no longer enumerates global assignments at all (C1 with it), so **no
global family assignment is formed anywhere in the mechanism** — only in the
oracle, which is what keeps the oracle independent.

### D3 (blocking) — the resolver re-recognized the island

`_resolver_pair` called `harness.island_run` again, so "spliced from the island
kernel already in hand" was false as executed, and no counter could see it.

**Disposition: fixed, with its price made a counter.** The seed now retains its
island kernel — but only when it published an alternate, so an unambiguous
island retains `None`. The pair is spliced from that kernel and both
`document_recognitions` and `island_runs` are asserted unchanged across the
resolver call. §6 states the retention as the cost it is: one live kernel per
ambiguous delegated occurrence until settlement, which is exactly the deferred
per-occurrence state `PROTOTYPE_14.md` §2 named, now with a shape and a number.
§11 carries its production release boundary.

### The non-blocking findings

- **A1, A4** — §0 of the report now says plainly that this is the Earley
  delegation seam, not the PDA island entry, and that `OP_ISLAND` has zero
  measured occurrences; §11 repeats both.
- **A3** — the `distant-island` witness replaces the tiny-chart numbers where a
  locality claim is made.
- **B2** — `settle` returns before touching `accepting_roots` or
  `rules_reaching` when there is no seed, so the control's zeros are path facts.
- **B3** — §2 scopes the pre-enumeration skip to the rule-wide half explicitly,
  and §8 gives DROP's share (under 5%).
- **C1** — removed: the island uses the per-node lane. **C2** — stated in §4 as
  the exact relation's inherent per-node cost.
- **D1** — the double increment is gone; `trees_after_the_resolver=3` for three
  trees. **D2** — the claim is rescoped to "complete-document tree".
- **E1** — the grammar moments and reducer are memoized per witness, so one
  witness binds ONE table and the registry's hit path is exercised by every
  proof that binds. **E2** — a new `registry-residency` row reports 13 entries
  and drains to 0, the meter `caches.cached_entries()` exists to provide.
  **E3** — §10 Q4 and §11 both say the parse-local release boundary, the
  retained kernel included, is not settled here.
- **F1** — §3.1 now says "rule-wide half". **F2** — §11 names the dependency:
  production's per-occurrence key at island entry needs the same coordinate
  join §2.1 refuses, so the descent's cost stays open with it.
- **G1** — the census CPU row carries its own disclaimer and no conclusion is
  drawn from it.
- **H1** — an empty option lane RAISES instead of skipping the family, because
  skipping shrinks the meaning set: a wrong acceptance, the one direction a
  silent default must not take. **H2** — §11 names the `repr` value-identity
  primitive and its uncounted cost as production work.
- **I1** — §3 now lists the columns shown and the columns elided, and states
  that nothing elided differs from a column shown.
- The dead `text` parameter is gone with `_resolver_pair`'s rewrite.

### What the reviewer confirmed sound

Complete-document trees built only after inequality and an invoked resolver;
`settlement_trees=0` a real code-path fact; the cached table flat and unable to
retain a parse; the DROP over-approximation conservative; no multithreaded row
anywhere; production measurements held open and no external timing presented as
a source result.

### Rerun after the fixes

```text
uv run python proto/island_continuation.py   exit 0  (1.07 s wall, whole file)
uv run ruff format / isort / ruff check      clean
uv run pyright                               0 errors, 0 warnings
```

---

## 3 — Reviewer 3 — `final packet closure audit`

Prompt, verbatim:

```text
Freshly audit PROMPT_15.md, the complete revised active packet, Prototype 14
and its coordinator correction, all Prototype 15 deliverables, and the current
working-tree diff. Verify that every established claim is executable, every
remaining decision/planning/implementation gate is labelled accurately, no
source or test changed, no parse regression is authorized, and the resolver
scope is not silently selected for the user. Read-only; no edits or benchmarks.
Return only substantive blockers followed by READY or NOT READY, with exact
file:line evidence. Ignore prose nits.
```

**Pass 1 verdict: NOT READY — four blockers, all documentation and coherence;
the reviewer verified the executable artefact reproduces exactly and found no
forbidden construct, no source change, no authorized parse regression, and no
silent selection of the resolver scope.** The four are fixed below and the
complete pass-1 response is copied into `reports/REVIEW_15.md`.

### B1 — a deliverable cited a figure the round's own fix superseded

This record's F4 entry quoted `control_seed_trees=3`, which was true before
Reviewer 2's B1 fix removed the island's redundant second derivation. Both runs
now build one tree.

**Disposition: corrected in place**, with the superseded figure kept and
labelled so the trail stays readable, and the saving re-cited to the columns
that still show it — `seeds=0` against `control_seeds=1`, `seed_chart_nodes=0`,
`seed_products=0`.

### B2 — TODO.md and INDEX.md were not folded for Reviewer 2's consequences

The other four active documents took them; the implementation queue and the
inventory did not, so an implementer working from the queue alone would build
the mechanism without them.

**Disposition: folded.** `TODO.md` §8 gains three unchecked items — the exact
lane over the dirty cone with the measured 1-dirty-node/2-application figure,
the deliberate Earley escalation an EXECUTE verdict implies on the predictive
path with the 73.9–95.6% census share, and the retained island kernel per ambiguous
occurrence with its undefined release boundary. `INDEX.md`'s gate sentence now
names all three.

### B3 — two mechanisms for one case, with no precedence

`DESIGN.md` carried both the exact per-node relation over the dirty cone and
the single-alternate ancestor-cone replay through a sparse overlay, and
`TODO.md` prescribed only the second.

**Disposition: precedence stated in both.** The exact per-node relation
GOVERNS; the single-alternate overlay replay is its permitted SPECIALIZATION,
admissible exactly where the compiled completion operations carry the proved
separability certificate — which is the same certificate one-flip evaluation
needs and, absent it, does not have. Where it is absent the per-node relation
governs and no overlay is built.

### B4 — the round's largest performance consequence had no labelled gate

`PROTOTYPE_15.md` recorded the linear→exponential change as unmeasured while Q7
answered that no gate was open, and nothing in `TODO.md` §8 carried it.

**Disposition: the gate exists and is labelled.** `TODO.md` §8 gains
**PLANNING REQUIRED AT §8 EXIT — EXACT-LANE COST BOUND**: production states the
bound it enforces on a node's local multiplicity — or the refusal it raises
past it — and measures the exact lane on an ambiguous input beside the §12 RSS
row, before the mechanism lands. Q7 now names that gate as one this round
OPENED rather than answering "no gate".

### Non-blocking, addressed anyway

`PROTOTYPE_15.md` §3's elision list now names `control_seeds` as a column that
differs from the shown `seeds`, in the direction that understates the round's
own saving; §12 says `REVIEW_15.md` joins the round's files when the closure
audit returns rather than asserting it already exists. The reviewer also noted
that commit `eb205ebe` — the user's own savepoint of this round — carries a
tracked `proto/__pycache__` artefact while `INDEX.md` calls `__pycache__/` a
local tool artefact; that is the user's commit and is left alone.

### Rerun after the fixes

```text
uv run python proto/island_continuation.py   exit 0
uv run python proto/operation_slot_laws.py   exit 0
uv run python proto/route_continuation.py    exit 0
uv run python proto/root_meaning_incremental.py  exit 0
uv run python proto/island_alternate_seed.py exit 0
uv run python proto/ambiguity_interaction.py exit 0
uv run python proto/resolver_pair.py         exit 0
uv run ruff check / pyright                  clean, 0 errors
git status --short -- src tests pyproject.toml .wiki   empty
```

### Pass 2 — NOT READY, two numeric/provenance blockers

The second fresh auditor independently re-verified pass 1's four dispositions
against the artefact rather than the record, ran all seven prototypes (exit 0
each), executed the `weakref.ref` refusal on `IrAst` and `Reducer`, and
confirmed every case figure, the elision-equality claims, the
forbidden-construct scan, the cited production seams, the absence of any
authorized parse regression, and that six separate documents leave the resolver
scope to the user. It then found two things wrong.

**C1 — the EXECUTE census range was quoted as 80–95%; the artefact prints
73.9–95.6%.** ABNF is 102/138 = 73.9%, six points below the stated floor,
because it is the one shipped grammar where the certificate still yields
injective rows (thirty). The figure had been written into `TODO.md`'s unchecked
escalation item, whose whole justification is that share — pass 1's B1 class
exactly, a deliverable stating a figure the artefact contradicts.

**Disposition: corrected in all five places** (`PROTOTYPE_15.md` twice,
`TODO.md`, `LEDGER.md`, this record twice) to `73.9–95.6%` with the four
per-grammar fractions and the reason ABNF sits at the low end. The DROP half —
under 5% everywhere, 4.7 / 4.3 / 4.4 / 3.3% — was correct and is now spelled
out. The substance is unchanged: EXECUTE is still the common path on every
shipped grammar.

**C2 — the ledger recorded two reviewers where three had run**, and headed the
round's substantive changes as Reviewer 2's when three of them are Reviewer 3
pass-1 dispositions: the precedence ruling, the three new `TODO.md` §8 items,
and the `EXACT-LANE COST BOUND` gate.

**Disposition: corrected.** `LEDGER.md` now records three fresh reviewers, the
closure auditor's two passes, which changes came from which, and both of the
pass-2 blockers; it cites `reports/REVIEW_15.md` as the auditor's own record.

**Non-blocking, addressed anyway.** `PROTOTYPE_15.md` §3 no longer claims every
elided column equals a shown one — it names the five cost counters that have no
equal, says none contradicts a shown column, and quotes the row where they are
largest. The census CPU line now says outright that it is the one figure in the
report that does not reproduce exactly (0.048225 against a later 0.049503),
which is what an uncontrolled single sample is worth. `TODO.md`'s
`EXACT-LANE COST BOUND` gate now separates its halves: the STATEMENT of the
bound is the §8 exit, the MEASUREMENT belongs beside the §12 RSS row.

### Rerun after the pass-2 fixes

```text
uv run python proto/island_continuation.py   exit 0
uv run ruff check / pyright                  clean, 0 errors
git status --short -- src tests pyproject.toml .wiki   empty
git diff --check                                       clean
```

### Pass 3 — NOT READY, one blocker: the same superseded figure, one document further

The third fresh auditor re-ran all seven prototypes (exit 0 each), reproduced
every case figure and every elision-equality claim, verified both pass-2
dispositions and all four pass-1 dispositions against the artefact, confirmed
that no run dirtied a tracked `.ruff_cache` or `__pycache__` file, and checked
the resolver-scope and no-parse-regression statements in six documents apiece.

**D1 — `LEDGER.md` still cited "one seed derivation against a control's
three".** That is the third appearance of the class pass 1 called B1 and pass 2
called C1: a number Reviewer 2's own fix invalidated when it removed the
island's redundant second derivation. The two earlier fixes reached
`P15_ADVERSARIAL.md` and `PROTOTYPE_15.md`; the ledger paragraph predates this
round's working diff (it is committed text), so `git diff` never surfaced it.

**Disposition: corrected, and re-cited to the columns that still carry the
claim** — `skipped_enumerations=1`, `seed_chart_nodes=0`, `seed_products=0`,
`seeds=0` against the control's `control_seeds=1` — with the superseded phrase
kept and labelled.

**Non-blocking, addressed anyway.** `PROTOTYPE_15.md` §3.1 no longer cites
`control_seed_trees=1` as something case 1 is measured "against" when both runs
print 1; it names the columns that differ and says outright that both runs
build the one derivation production builds, so what the row saves is set work
rather than a tree. `TODO.md`'s cost-bound gate is relabelled **PLANNING
REQUIRED BEFORE THE EXACT LANE LANDS**, since §8's exit comes after the lane it
gates. `DESIGN.md`'s duplicated opening sentence, an artefact of the pass-1 B3
insertion, is removed. The census CPU spread is now five samples wide
(0.048225 / 0.049503 / 0.050712 / 0.051303 / 0.049550), which the report's own disclaimer covers, and
`reports/REVIEW_15.md` being untracked is the user's call at commit time.

### Rerun after the pass-3 fixes

```text
uv run python proto/island_continuation.py   exit 0
uv run ruff check / pyright                  clean, 0 errors
git status --short -- src tests pyproject.toml .wiki   empty
git diff --check                                       clean
```

### Pass 4 — NOT READY, two provenance/gate-labelling blockers

The fourth auditor re-ran all seven prototypes (exit 0 each), reproduced every
case figure including both ABNF rows and all four elision-equality classes,
re-derived §8's census arithmetic, and confirmed pass 3's D1 fix and its three
prose dispositions. It declined to run Ruff or Pyright because
`proto/.ruff_cache/` is tracked here and invoking Ruff rewrites it — a fact now
recorded in §12 rather than left implicit.

**E1 — the pass-3 gate relabel reached `TODO.md` and nothing else**, so the
packet named one gate's moment three ways: `LEDGER.md` still listed
`PLANNING REQUIRED AT §8 EXIT`, and `PROTOTYPE_15.md` Q7 still required the
MEASUREMENT "before the mechanism lands" where the queue puts it beside the §12
RSS row.

**Disposition: both corrected.** `LEDGER.md` names the current label and states
the split; Q7 now says the gate has two halves at two moments and names both —
the STATEMENT inside §8 before the lane lands, the MEASUREMENT beside the §12
RSS row, neither substituting for the other.

**E2 — `LEDGER.md` recorded two closure-audit passes where three had run**, and
omitted pass 3's blocker and its disposition — pass 2's C2 recurring one pass
later, in the document `INDEX.md` makes the corrections record.

**Disposition: corrected.** The ledger now records three closure passes, states
pass 3's blocker and its re-citation, and attributes the gate relabel to that
pass.

**Non-blocking, addressed anyway.** The census CPU spread is recorded as four
samples wide; `DESIGN.md`'s status paragraph now names Prototype 15 among the
rounds that established the current design; §12 records that Ruff rewrites the
tracked `.ruff_cache` and that both it and `__pycache__` are restored after the
last run.

### Pass 4 re-check — READY

The same auditor re-checked E1 and E2 against the files rather than against the
account, and returned **READY**. It confirmed the gate label and its two
moments now agree word for word between `LEDGER.md` and `TODO.md`, that Q7's
"before the mechanism lands" measurement clause is gone, that the only
surviving instances of the old label are audit-trail text, and that `LEDGER.md`
now records three closure passes with pass 3's blocker and the gate relabel
attributed to it. It re-ran `island_continuation.py` (exit 0, byte-identical to
its previous run except the disclaimed CPU sample), re-verified every case
figure, both ABNF rows, all four elision-equality classes, the census
arithmetic and the round's headline figures, and confirmed that no active
document names a gate or a figure the queue or the artefact does not carry.

**It also caught two fixes this record had claimed and the files did not have.**
The census CPU spread had not been widened and `DESIGN.md`'s status paragraph
did not name Prototype 15; an earlier edit script aborted on a failed anchor
after writing two of its four files, and the round's own summary of that script
was written from intent rather than from the files. Both are now actually
applied — the spread is recorded five samples wide (0.048225 / 0.049503 /
0.050712 / 0.051303 / 0.049550) and `DESIGN.md`'s status paragraph names
Prototype 15's contributions — and the failure is recorded here because it is
the same class the round blocked on four times: a deliverable stating something
the files do not carry. The auditor found it by checking rather than accepting
the account, which is what the role is for.

One claim in `PROTOTYPE_15.md` §12 the final auditor could not verify: it
declined to run Ruff or Pyright because `proto/.ruff_cache/` is tracked in this
repository and a Ruff invocation rewrites it. The coordinator ran both after
every change — clean, 0 errors — and restored the cache; closure passes 2 and 3
verified them independently.

### The review loop stops here, by the user's ruling

Pass 4's blockers were provenance and gate-label accuracy in the deliverables,
not mechanism findings. The user ruled that no fresh agent should be spawned to
re-review documentation nits and directed the re-check to the existing auditor,
which returned `READY` above.

That verdict is therefore from a reviewer that had already audited the packet
once, not from a fifth fresh one. `PROMPT_15.md` asks for a fresh reviewer at
each role; four fresh closure auditors ran, and the final `READY` came from the
fourth on re-check. The distinction is recorded rather than smoothed over.
`READY` neither authorizes source implementation nor accepts any parsing
regression, and the resolver-scope USER DECISION remains open and unselected.

### Rerun after the pass-4 fixes

```text
uv run python proto/island_continuation.py   exit 0
uv run ruff check / pyright                  clean, 0 errors
git status --short -- src tests pyproject.toml .wiki   empty
git diff --check                                       clean
```
