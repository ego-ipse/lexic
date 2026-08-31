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
`skipped_enumerations=1` and `seed_trees=1` against a control run's
`control_seed_trees=3`. §11 states the prototype's remaining weakness honestly:
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

_Pending._

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

_Pending._
