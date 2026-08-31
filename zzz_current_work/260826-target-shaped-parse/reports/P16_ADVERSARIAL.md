# P16 — the sequential adversarial record

Three fresh, read-only reviewers, called synchronously and strictly
sequentially. No other agent or measurement was alive while one ran. All three
are `general-purpose` with `run_in_background: false`; **Fable was not used
anywhere**. Every prompt is recorded verbatim below, with each reviewer's
findings and this round's disposition.

Write allowlist for every fix: `proto/shared_occurrence_ambiguity.py`,
`proto/exact_lane_cost.py`, `reports/PROTOTYPE_16.md`,
`reports/P16_ADVERSARIAL.md`, `reports/REVIEW_16.md`. Findings against the
ACTIVE PLAN are recorded here and not acted on; the plan is read-only this
round.

---

## 0 — state before the reviewers were called

```text
proto/shared_occurrence_ambiguity.py   exit 0
proto/exact_lane_cost.py               exit 0
ruff format --check / ruff check       clean, both files
pyright                                0 errors, 0 warnings, both files
forbidden-construct search             none
baseline: 123 files under the effort dir; git status showed only PROMPT_16.md
          (the user's own replacement of the tasking file, pre-existing)
```

---

## 1 — Reviewer 1: shared occurrences

**Prompt, verbatim:**

```text
Read PROMPT_16.md, its inputs, both Round 16 prototypes, and the draft report.
Try to falsify the oracle's independence and every shared-DAG result. Look for
globally correlated keys, circular controls, node identity mistaken for
occurrence identity, missing nullable or synthetic sharing, and effects run per
node instead of per consumption. Verify the active packet was not edited.
Read-only; no benchmarks. Return substantive file:line findings and READY only
if the evidence is sound. Ignore prose nits.
```

**Verdict: NOT READY**, 14 findings. The reviewer reproduced Part A exactly and
confirmed every production citation. Dispositions below; every fix stayed inside
the write allowlist and both prototypes were rerun after them.

| # | Finding | Disposition |
|---|---|---|
| P1 | The round modified a TRACKED file outside the allowlist: `proto/.ruff_cache/0.15.12/13011947814826943830`, written by this round's `ruff check`. The report claimed "writes only allowlisted files". | **FIXED.** Restored with `git checkout`; `git diff --name-only HEAD` now returns only `PROMPT_16.md`. Restoration is now part of the done gate and is rerun after every Ruff invocation. Repeat of `P15_ADVERSARIAL.md` F10 — recorded as such. |
| A1 | **Blocker.** The oracle's family decomposition is the candidate's: `occurrence_families` is the same `local_choice_keys`/`assignments`/`selected_resolved` triple `build_chart` uses, so `lanes_agree` cross-checks composition only. The report's word "independent" overclaims. | **FIXED, by narrowing the claim AND adding the missing lane.** The report now states the boundary exactly (shares chain-resolution primitives and the reducer; does not share composition, memo policy, dedup key, traversal). Added `production_enumeration`: production's own `DERIVATIONS`/`to_chart` walk, which IS independent in family decomposition — and is unsound here (see A14). The round now states that no lane confirms the family enumeration rather than claiming one does. |
| A2 | **Blocker.** `exact_lane_cost.py` docstring asserted `unrolled_meanings` "shares no code with either settlement lane", while `settle` uses `algebra.build_chart` and calls `shared.add_unique`. | **FIXED.** Docstring rewritten to state what is and is not shared. |
| A3 | The independence pin (`occurrences > chart_nodes`) is not discriminating — it holds whenever any node has two families. | **FIXED.** Replaced with `occurrence_paths_at`, which counts paths expanded **at the shared handle** (2, matching its 2 occurrence edges). |
| A4 | **Blocker.** `Chart.edges` is `(parent, child, slot)` — no family index — and production's `forest/chart.py` has no parent→child edge at all. The report's "the chart already IS the occurrence relation … no new occurrence identity is required" is not what the artefacts hold, and it understates an implementation gate. | **FIXED.** §A1 and answer 3 rewritten with the precise position: derivable, nothing new recorded at recognition time, but not readable off any existing edge; materialising the triple is now implementation gate (c). |
| A5 | The effect rows measure set CARDINALITIES, not executions, while claiming "execute per consumption". | **FIXED.** `UnrolledCounts.apply` attributes each body execution to its rule; the rows now report `consumer_body_executions=4` against `shared_node_occurrence_expansions=2`. |
| A6 | "Transparent synthetic" is not exercised as transparency — the witness shares an authored rule beneath synthetic consumers. | **FIXED as a stated scope limit.** An attempt to build a shared-synthetic witness failed: normalization gives each alternative its own hoisted arm, so two consumers reach two distinct synthetic handles. Added `prove_no_synthetic_node_is_ever_shared`, which executes the absence across all witnesses and labels it NOT COVERED. |
| A7 | `computed_once` cannot fail — `_topological` carries a `seen` set. Presented as one of "two independent checks". | **FIXED.** Relabelled `candidate_order_visits_each_handle_once` and described in the report as a code-path statement, explicitly not a falsifiable check. The falsifiable evidence is now A10's controlled differential. |
| A8 | The sibling-memo negative is a query artefact: `shared=""` makes `shared_nodes` match nothing regardless of the chart. | **FIXED.** Added `all_shared_nodes` (no name filter); every witness reports `every_shared_rule`, and a witness declaring no shared node is asserted to have none at all. |
| A9 | The delegated-island row has no control and cannot support "compose the same way". | **FIXED.** Added the correlated column (2) and stated plainly that the row does not discriminate the relations, because the two consumptions are in different derivations. |
| A10 | The shared-vs-twin differential is uncontrolled — the twin has 13 nodes against 8. | **FIXED.** The assertion is now `twin_products - shared_products == shared_node_own_families` (2 == 2): exactly one more copy of that node's set, not a size difference. |
| A11 | **Blocker.** "Only the operation's own `UnsupportedConstructError` is absorbed" is false — the type is also the dispatch default, so the guard would swallow engine failures. | **FIXED, then SUPERSEDED by §4.1.** The broad catch is gone entirely: absorption is now by explicit per-rule declaration, and `prove_the_required_production_signal` (which replaced `partial-guard-boundary`) states the distinct value-refusal exception production must add. The finding stands; the mechanism it described no longer exists. |
| A12 | **Blocker.** "A node whose whole set comes out empty still raises" happens in neither lane; the two lanes have different partial-operation semantics and agree only because no witness has a fully-refusing subtree. | **SUPERSEDED by §4.1 — and the fix it prompted was WRONG.** Making `_occurrence_set` raise on an empty node image was the opposite of the correct semantics: an empty INTERNAL image must eliminate only the parent families consuming it, and refusal belongs at the requested root alone. The finding correctly identified that the two lanes disagreed; the disposition picked the wrong lane to change. Both now take bottom semantics, with the three witnesses in §A6. |
| A13 | No split-ambiguous shared node anywhere — `is_arm_choice` excludes split families — so "every real shared-DAG shape" is scoped and §8 did not say so. | **FIXED.** Scope stated in §A3 and in answer 1. |
| B1 | `exact_lane_cost`'s oracle cross-check compares a boolean, not a set. | **FIXED.** Added `_materialized_set`; the check is now `same_meaning_set` and the rows print both cardinalities. |
| B2 | "The unambiguous path pays none of it" excludes the family-resolved `build_chart`, which runs before dirtiness is known and is charged by no counter. | **FIXED, and measured.** §B6 now reports `unconditional_chart_build_cpu` against `whole_settle_cpu`: the build is **68.1%** of settle on an unambiguous document. The claim is narrowed to the SET lane, and a demand-driven chart is added as implementation gate (d). |
| A14 | *(New, found while fixing A1.)* Production's `forest.DERIVATIONS` truncates a zero-width node consumed at two slots of one derivation: `ForestCtx.open` cannot distinguish a SUSPENDED shared handle from a cyclic one. Two derivations where the grammar derives four, none well-formed. | **PINNED as a shipped defect.** `prove_production_enumeration_truncates` executes it on three shapes. Listed under "Disproved" in the coordinator handoff, with a note that it is not in `CURRENT_BUG_REPORT.md` and the coordinator should decide whether it becomes a fourth pinned defect. |

**State after the fixes:** both prototypes exit 0; ruff format/check clean;
pyright 0 errors, 0 warnings; forbidden-construct search clean;
`git diff --name-only HEAD` returns only `PROMPT_16.md`.

---

## 2 — Reviewer 2: exact-lane cost

**Prompt, verbatim:**

```text
Read the revised Round 16 evidence. Falsify its bounds, early stops, quotients,
deduplication, and refusal rule. Require collapse-heavy, late-second-value, and
growing-image controls. Reject arbitrary caps, one-flip fallbacks, uncontrolled
timings, and unambiguous-path ambiguity state. Identify semantic choices that
require the user. Verify the settled resolver scope remains fixed. Read-only;
no benchmarks. Return substantive file:line findings and READY only if sound.
Ignore prose nits.
```

**Verdict: NOT READY**, 7 blockers + 6 control findings + 3 misclassified
decisions. The reviewer reproduced the run and confirmed the packet unmodified.
This round's largest correction: the headline cost claim was wrong.

| # | Finding | Disposition |
|---|---|---|
| A1 | **Blocker.** `applications` is not a cost measure, and §B5's own table refutes the `Θ(local multiplicity)` claim: at `k=10` `late-second` and `grow` execute an identical **1044** applications and differ by **~200×** in CPU. The hidden factor is `add_unique`'s linear scan, which is quadratic in a node's image. | **FIXED — the claim was wrong and is withdrawn.** Added `Lane.comparisons` and `prove_applications_are_not_the_cost`: identical application counts with comparison ratios of **58× / 247× / 1013×** at k=6/8/10, asserted against derived bounds (late linear in applications; grow quadratic in its measured peak). The report now states the cost as two factors, withdraws the single-unit `Θ`, keeps only `Ω(m(h))` **applications**, and propagates the correction into §B5, §B7's unit bullet, answer 4, answer 6 and the handoff. |
| A2 | **Blocker.** The levered lane is never set-checked: `_materialized_set` returned the *candidate's* set, which has no levers, while the printed column was labelled `materializing_lane_meanings`. Reviewer 1's B1 disposition was therefore not actually fixed. | **FIXED properly.** `Cost` now carries `values` and a `complete` flag; the oracle check compares `full.values` — `settle`'s own output — via `same_meaning_set`. `_materialized_set` deleted. Column renamed `settle_lane_meanings`. |
| A3 | **Blocker.** The ceiling counts the refusal sentinel: one refusing family plus one real value ends the enumeration at a one-element set, so `settle` reports `equal` on an ambiguous document — settling by exhaustion. | **FIXED.** `_live_count` counts real meanings only; the ceiling test uses it. |
| A4 | **Blocker.** `settle` reports `equal` for a root with no meaning, and `Cost.meanings=0` means both "stopped early" and "settled, empty". | **FIXED.** Added a third verdict `VERDICT_NO_MEANING`, and split the overloaded field into `values` + `complete`. |
| A5 | **Blocker.** The declared-image quotient never fires in any executed row; its cross-slot product composition is unsound in general (`f(i,j)=v_i if i==j else x`) and unvalidated here; §B3 credited it with a peak effect its own isolation row denies; and `bounds_for` had a silent default (`widths.get(rule, 1)`). | **FIXED, mostly by withdrawal.** Silent default replaced with `_width_of`, which refuses. §B3 rewritten: the lever is labelled NOT VALIDATED, the misattributed peak claim is retracted, the composition gap is stated with the reviewer's counterexample, and adopting it is moved to a **user decision**. |
| A6 | **Blocker.** `Certificate.applications` excludes the lane's unconditional full baseline fold — 51 real applications at `k=10`, reported as 2 — the same "counter excludes the work" pattern §B6 admits elsewhere. | **FIXED.** `_baseline_table` now takes the real `Lane`; `Certificate` gains `baseline`; rows print `law_lane_unconditional_baseline_folds`. §B3 states the two-applications figure is not the lane's cost, adds that 2 is a best case with no bound, notes the absent negative control, and records that the executed certificate is plain reachability rather than the family-fixing one its docstring describes. |
| A7 | **Blocker.** `Lane.peak` is a cumulative sum (`live` never decremented), while its docstring and every §B3 retention statement read it as a peak. | **FIXED.** `retain` now tracks a true per-node maximum plus a separate `retained` total; both are reported. |
| B1 | No stacked-product control — "the exponential term is one node's own product" is an artefact of a ladder with one multi-slot consumer. | **FIXED.** Added `stacked_grammar`/`prove_multiplicity_is_paid_at_every_level`: with a retaining consumer at every level the root's share is **50% / 40% / 46%**. The general claim is withdrawn; only the per-node identity is kept. |
| B2 | Six claimed cases over four rungs; "interacting invisible substitutions" has no rung, and the law-shortcut and exponential-image cases are the same rung. | **FIXED by disclosure.** The §B2 table gains a "Distinct?" column naming both re-reads, and the text states the honest count: four rungs, two cost shapes, five distinct configurations plus the new stacked control. |
| B3 | `prove_multiplicity_is_the_cost` is definitional, not a measurement. | **FIXED.** §B1 now says so explicitly and no longer presents it under "Executed". |
| B4 | The floor control does not reproduce (2.6/1.3/2.3% against the quoted 1.7/0.08/0.15%, sign flipping) and the arms are not alternated, contrary to `docs/STYLE.md`. | **FIXED.** `_time_alternating` runs two byte-identical arms alternated in one process. The spread is read PER RUN and is **not** quoted as a fixed band — an earlier version of this row quoted 0.19–0.45% and an independent run measured 0.53/2.37/0.63%, which is the same defect over again. The conclusions the table carries are orders of magnitude apart and survive any of these spreads. |
| B5 | §B6's unambiguous-path account is still incomplete: three more uncharged passes, one allocation per clean node, and the 68% ratio is a 3-node chart with no floor control. | **FIXED by disclosure.** §B6 rewritten as a four-point account naming each omission, including the singleton-per-clean-node allocation and the ratio's own limits. |
| B6 | The certificate's "two applications" is a best case; no negative control; `_carries`/`_injective_nodes` fix no family despite the docstring. | **FIXED by disclosure** — see A6's row. |
| — | Three semantic choices misclassified as implementation gates: value identity, fully-refusing-node behaviour, and adopting the quotient. | **FIXED.** §7's user-decision list goes from one to **four**, each with the sentence explaining why it changes when a document parses or raises. |
| — | `BudgetRefusal(UnsupportedConstructError)` collides with the round's own partial-operation guard, which absorbs that type — a refusal would silently become "equal". | **FIXED.** `BudgetRefusal` now derives from `LexicError`. §B7's "which exception" bullet records the collision and why the type must sit outside the absorbed one. |
| — | Minor: `_materialized_set` took `bounds` and immediately deleted it; `prove_grow_image_is_computed_not_enumerated` claims arithmetic it does not perform. | First is moot (function deleted). Second: the report does not repeat the claim; the function name overstates and is left, noted here. |
| — | Resolver scope verified PRESERVED; no source touched; no parse regression possible. | No action. |

**State after the fixes:** both prototypes exit 0; ruff format/check clean;
pyright 0 errors, 0 warnings; `git diff --name-only HEAD` returns only
`PROMPT_16.md`.

---

## 3 — Reviewer 3: closure

**Prompt, verbatim:**

```text
Audit PROMPT_16.md, its inputs, Prototype 15's limits, every Round 16
deliverable, and the before/after file record. Require an independent
occurrence-unrolled oracle, an honest exact-lane cost policy, correct
classification of open gates and decisions, preserved resolver scope, no
authorized parse regression, and no writes outside the allowlist. READY means
only that the evidence is fit for coordinator review; it does not approve the
plan or authorize implementation. Read-only; no benchmarks. Return substantive
blockers followed by READY or NOT READY. Ignore prose nits.
```

**Verdict, pass 1: NOT READY**, 3 blockers. The auditor verified the allowlist
clean, the oracle's stated independence boundary, resolver scope unreopened, no
authorized regression, and reproduced every Part A figure and most of Part B.

| # | Finding | Disposition |
|---|---|---|
| C1 | **Blocker.** The withdrawn `Θ(local multiplicity)` claim still PRINTS from the artefact — `exact_lane_cost.py:33` (module docstring), `:1038-1039` (`lower-bound` row) and `:1625` (closing invariant) — as does the retracted "the exponential term is one node's own product" at `:1011`, which the same run contradicts 20 lines later in `stacked-product conclusion`. The report said the correction "propagates"; it had not reached the code. | **FIXED.** All four rewritten to the two-factor statement: applications are `Ω(m(h))` and no lever reduces them; wall cost is that count times a non-constant value-identity factor, so no single-unit `Θ` is claimed. The `multiplicity` row now also states its own identity is definitional and points at the stacked control. Verified: `grep` over the RUN OUTPUT returns 0 hits for all three withdrawn strings. |
| C2 | **Blocker.** §10's coordinator handoff reverted to the pre-review classification — "one user decision" against §7.7's four, and "two implementation gates" against §7.7's five — undoing the fix recorded for Reviewer 2 in the one section a coordinator acts on. | **FIXED.** §10 now enumerates all five gates and all four user decisions explicitly, each with its section reference, instead of summarising. |
| C3 | **Blocker.** Two quoted figures substituted application counts for the retention column: `full_peak_retained=[8,24,76,272,1044]` (artefact: `[4,16,64,256,1024]`) and `peak_retained={full:272,…,root-stop-only:18}` (artefact: `{full:256, …, root-stop-only:2}`). The derived sentence "identical peaks across all four settings" was consequently false on the two `grow` rows, where the ROOT STOP drops the peak 256→2. Same applications-vs-retention conflation as Reviewer 2's A7. | **FIXED.** Both figures corrected from the run, `streaming_peak_retained` added, and the quotient sentence narrowed to say the QUOTIENT changes no peak while noting the root stop does. |
| — | Non-blocking: the §A3 witness table lists 9 of 10 `shared-shape` rows (`synthetic-consumers` omitted), so "six of nine" should read "six of ten". | Noted; answer 1 already says ten witnesses and the omitted row is non-discriminating. Left as the auditor scoped it. |

**State after the fixes:** both prototypes exit 0; ruff and pyright clean; the
withdrawn claims are absent from the run output; `git diff --name-only HEAD`
returns only `PROMPT_16.md`.

**Verdict, pass 2 (re-check): READY.** The same auditor verified all three fixes
against the files and a fresh reproduction run: 0 hits for the withdrawn claims
in the RUN OUTPUT, §10 agreeing with §7.7 on five gates and four user decisions,
and both retention figures matching the artefact. It confirmed nothing else
regressed and the allowlist is still clean. Its full response, both passes, is
in `reports/REVIEW_16.md`.

The re-check was sent to the same auditor rather than a fifth fresh reviewer,
because the three blockers were narrow, mechanically verifiable corrections to
figures and classification rather than new evidence — the precedent
`REVIEW_15.md` pass 4 records for the same situation.

**One pattern worth carrying forward.** All three of this auditor's blockers had
the same shape: a claim corrected in the REPORT after a review and left standing
in the ARTEFACT, so running the prototype printed a conclusion the report had
already withdrawn. A withdrawal that reaches only the prose is worse than none,
because the executable is what a later reader trusts. Every future round should
grep the run OUTPUT, not the source or the report, for any claim it retracts.

---

## 4 — coordinator correction pass (round reopened)

The round was reopened as NOT ready to fold. Seven correction groups, all
inside the write allowlist; both prototypes rerun sequentially after each.

| # | Correction | What changed |
|---|---|---|
| 1 | **Partial operations take bottom semantics.** | The `_ABSENT` sentinel is gone. A refusing family contributes no meaning; an empty internal image eliminates only the parent families consuming it; parsing refuses only when no complete requested-root meaning survives. `cyclic_meaning.node_set:657-661` is the production precedent. Three new witnesses: one refusing branch beside a surviving one, every root branch refusing, and the empty-image scope case. Absorption is by explicit per-rule DECLARATION, never by exception type; `prove_the_required_production_signal` states the distinct value-refusal exception production must add first. |
| 2 | **Injective/grow certificate fixed.** | No sentinel can be counted as a meaning. `_local_witness` collects only meanings that exist, so one refusing family plus one live value is not ambiguity. The baseline now comes from the first LIVE family instead of `resolveds[0]`. Two negative controls added: `refusing-family-is-not-ambiguity` and `baseline-past-a-refusing-default`. |
| 3 | **Value identity is not open.** | Production `same_value` is authoritative; both lanes use it. `island_continuation.dedup`'s `repr` is recorded as a prototype shortcut and an implementation task. Removed from the user-decision list. |
| 4 | **Declared-image quotient REJECTED.** | `Settings.quotient` deleted; no lane consults a bound. `prove_the_quotient_is_rejected` records the three grounds — unproved cross-slot composition, zero shipped rules with an image wider than one, and silent narrowing risk. Not carried into the plan. |
| 5 | **No resource ceiling.** | `BudgetRefusal`, `Settings.budget` and the budget proof deleted. §B7 now records the exponential worst case as a property of the current enumeration, explicitly neither a user decision nor an implementation blocker. |
| 6 | **Scope and overclaims.** | The oracle's shared family-decomposition machinery is stated wherever the agreement is claimed, including answer 1. The occurrence triple is described as derivable but carried by no existing structure. The transparent-synthetic case is reported as covered only as a synthetic CONSUMER. The exponential bound is qualified to the current enumeration and slot laws, with future symbolic analysis explicitly not ruled out. The witness table now lists all ten rows and reads "six of the ten". |
| 7 | **Implementation work preserved and classified.** | §7.7 lists eight ordered implementation tasks — ForestCtx defect, bottom semantics, the distinct refusal exception (prerequisite), the live-family baseline, occurrence identity on the ambiguity path only, a demand-driven chart, `same_value`, and unchanged resolver scope — plus four §12 measurement tasks. **Zero user decisions remain.** |

---

## 4.2 — fold-readiness review (fresh, sequential)

**Prompt role:** fold readiness, not "fit for coordinator review". READY only if
no semantic/planning/user decision remains, every conclusion is directly
foldable, remaining items are implementation or measurement only, no unsupported
closure claim remains, and executable output and prose agree exactly.

**Pass 1: NOT READY**, three blockers. All three were the same failure mode the
round had already named and then committed again: a claim corrected in the
REPORT and left standing in the ARTEFACT.

| # | Finding | Disposition |
|---|---|---|
| B1 | **A user decision was still open in a deliverable.** `exact_lane_cost.py`'s module docstring still read "What remains is a refusal contract, and choosing it — and its unit — is the user's", contradicting three places in the report that say no user decision remains and the `Settings` docstring that says no budget is proposed. The budget machinery was deleted; the sentence assigning the choice was not. | **FIXED.** Replaced with §B7's settled position: the exponential is recorded as the current lane's worst case under this enumeration and these slot laws, and is neither a user decision nor an implementation blocker. |
| B2 | **The run OUTPUT asserted the occurrence triple already exists.** Four places — module docstring, `prove_tree_identity_is_not_occurrence_identity`'s docstring, and two PRINTED rows (`tree-versus-occurrence-identity`, the closing `invariant`) — said the triple is "already there" / "which the chart carries". False of the prototype's own `cyclic_meaning.Edge`, and it deletes implementation task 5 for anyone reading the artefact. Reviewer 1's A4 was recorded FIXED but the fix reached only the report. | **FIXED in all four, and verified in the OUTPUT.** Every site now states the triple is DERIVABLE from the forest and recorded by no structure — `Edge` has no family index, production's chart has no parent-to-child edge — so materialising it is production work on the ambiguity path only. `grep` over the run output for the retracted wording returns 0. |
| B3 | **§B3 quoted a `lever-isolation` block the artefact no longer produces**, showing the rejected quotient as a measured lane, thirty lines above the statement that no lane reads a bound. Four further prose survivals inside the artefact described the declared bound as an exact stop, and a dead `bounds`/`name` channel was still threaded into `_ceiling`. | **FIXED.** The block is regenerated from the run (two lanes, not four). The four prose sites are rewritten; `_ceiling` now takes `(handle, roots, settings)` with no bound, so the code cannot re-suggest the lever. The two output rows that named "the declared bound" as a lever were reworded. |
| — | Secondary: `P16_ADVERSARIAL.md` asserted alternated spreads of "0.19–0.45%", which an independent run did not reproduce (0.53/2.37/0.63%). | **FIXED.** The record and §B5 both now state the spread is read per run and is not a fixed band, and name the non-reproducing figures. Only the order-of-magnitude gaps are load-bearing. |

**The pattern, recorded for the last time.** Three separate reviewers have now
caught the same thing: this round corrects prose faster than it corrects code.
The check that catches it is mechanical — grep the RUN OUTPUT, never the source
and never the report, for any claim being withdrawn — and it is the check that
was skipped each time it recurred.

**Pass 2: one blocker remained — the SAME claim, displaced into the report.**

| # | Finding | Disposition |
|---|---|---|
| B4 | §A1's **lead sentence** still read "the forest edge … which `Chart.edges` already carries", contradicting its own bullets four lines below, answer 3, implementation task 5 and the corrected output rows. Reviewer 1's A4 fix rewrote §A1's BODY and never touched the lead; the B2 fix was scoped to four prototype sites and verified by grepping the run output — which cannot see a report-only survival. | **FIXED.** The lead now states the triple is derivable and recorded by no structure, and points at implementation task 5. |
| — | The B3 edit removed a sentence's antecedent, leaving a truncated module docstring at `exact_lane_cost.py:30-31`. | **FIXED.** The `finite`-consumer precondition is restored. |
| — | The 68.1% chart-build ratio was quoted as fixed; an independent run measured 71.7%. | **FIXED, then RE-FIXED in pass 3.** The first fix quoted "68–72% across runs" — a band derived from two samples, which a third run falsified at 64.6%. It is now the §B5 form: §B6 carries the three samples explicitly labelled samples-not-a-band, and the two folded sections (implementation task 6, handoff) carry no digits at all. |
| — | "The dead `bounds`/`name` channel is gone" was one level narrower than true: `settle` still declared and forwarded `bounds`. | **FIXED.** `bounds` is removed from `settle`, `_settled_set`, `_root_multiplicity`, `parse_ladder` and `_refusing_arm_case`. `bounds_for` survives only for the rejection census. |

**The check, corrected.** §4.2's "grep the run OUTPUT" was necessary and NOT
sufficient — it is blind to a report-only survival, which is exactly how B4
lived through it. The sufficient form, now run: grep each withdrawn STRING
across **all four deliverables and both run outputs**. Executed for
`Chart.edges already`, `already there`, `which the chart carries`,
`is the user's`, `Theta(local multiplicity)`, `Theta(m(h))`,
`exponential term is one node`, `declared-bound-only`, `BudgetRefusal`,
`quotient=True`, `_ABSENT` and the later `68-72` band: zero hits in either
prototype source and either run output. The only residuals are THREE lines in
`PROTOTYPE_16.md` that are the report explicitly RECORDING a withdrawal, and
this record, which must retain the history.

**Pass 3: one item — a two-sample range asserted as an across-runs band.**
The chart-build ratio fix over-corrected: quoting "68–72% across runs" turned
two observations into a bounded claim, and a third run measured 64.6%. §B5 had
already solved this shape correctly by quoting no band at all, and §B6 now
follows it — three samples, labelled as samples, with the two folded sections
carrying no digits. The reviewer also counted three legitimate
withdrawal-recording hits in `PROTOTYPE_16.md` where this record said two;
corrected above.

---

## 4.3 — second coordinator reopening: the READY verdict was invalid

The fold-readiness READY was withdrawn. Three substantive blockers, all of
which had been *documented* rather than fixed — the round's recurring failure
in its final form: admitting a gap in prose and folding anyway.

| # | Blocker | Disposition |
|---|---|---|
| 1 | **The shared transparent-synthetic DAG was never covered.** The round tested a synthetic CONSUMER over an authored shared node and reported the real shape as NOT COVERED, narrowing a requirement the active gate makes. Worse, it justified the narrowing with a false structural argument — "normalization gives each alternative its own hoisted arm". | **FIXED, and the argument RETRACTED.** Normalization **dedups identical generated rules**, so one `__rep_1` can be referenced from two slots and carry two occurrence edges on one chart node. Two witnesses now execute: `inter-derivation` (one `b*` written in two rules, ambiguity beneath it) and `intra-derivation` (one `"y"?` written twice in one arm, ambiguity beside it). Both: 2 occurrence edges, no reducer action, `exact == oracle == 2`. §A3 states how a transparent/result-less node composes — it is result-less only to `ModelFold`, and in the meaning relation it is an ordinary node taking the default action whose set is computed once per handle. |
| 2 | **The injective certificate was unsound over families, and the round documented the gap instead of closing it.** `_injective_nodes` walked `chart.edges` — `(parent, child, slot)` with the family collapsed — so a slot of a family that can produce no meaning still propagated the mark. | **FIXED.** `_injective_nodes` is family-aware: a step is admitted only when the parent is marked, the step's family is LIVE (every slot has a non-empty image and its own operation yields a value), and the slot's law is `ident`/`grow`. The rejected walk is kept as `_collapsed_injective_nodes` for the comparison. Required negative control `dead-family-route` executes: the collapsed walk marks the two-valued node, the family-aware walk does not, the certificate reports no ambiguity, and settle and the oracle both answer one meaning. `positive-certificate` re-checks the shortcut at k=4 and k=8 — still 2 applications. |
| 3 | **The cost model asserted a product the evidence does not establish** — "wall cost = application count × value-identity factor". | **FIXED — but the first pass MISSED FIVE SITES**, including one in the run output (`applications-are-not-the-cost conclusion`) and three in the report (§B1, §B4, §B5); a reviewer caught them and they are now corrected. The defensible decomposition is now stated and nothing wider: `reducer evaluation and result construction` (exactly `m(h)` applications under full enumeration, an identity) `+ deduplication comparison count` (image-dependent, counted) `×` the structural cost of one comparison (**unmeasured**). No product of the three is asserted, and no new timing was run to reach this. |

**Two claims this round made and has now retracted outright**, both of which had
been recorded as findings-fixed:

- "No synthetic node is ever itself the shared one" — false; normalization
  dedups generated rules.
- "`_injective_nodes` fixes no family … the gap is real and unclosed" — the gap
  was real; documenting it was not a disposition.

**The pattern, finally named correctly.** Every earlier recurrence was framed
as a synchronisation failure between prose and code. This reopening shows the
deeper one: a claim narrowed to what had been *tested* rather than to what the
gate *required*, and a known-unsound mechanism carried behind an honest-sounding
admission. Grepping outputs would not have caught either. What catches them is
checking each requirement against the gate's wording rather than against the
round's own summary of it.

**Review of §4.3: NOT READY, then corrected.** A fresh reviewer attacked the
three corrections and confirmed 1 and 2 landed, with two substantive residuals:

| # | Finding | Disposition |
|---|---|---|
| R1 | **Correction 3 was not landed.** The retracted multiplicative claim survived at five sites — `prove_applications_are_not_the_cost`'s docstring, its PRINTED conclusion row, and §B1/§B4/§B5 — so the report contradicted itself (§6, §7.4 and the handoff say no product is asserted) and contradicted its own run output in both directions. | **FIXED at all five.** Every site now states the three-term decomposition and says explicitly that no product of the three is asserted. `grep` for the claim form returns zero across both prototypes, both run outputs and the report. |
| R2 | **The certificate had a second hole of the same species, and the round had DELETED the honest admission while it remained.** Liveness was decided on the baseline channel only, but a `grow` body can refuse SELECTIVELY — so a family live at baseline may transmit no second value, and the lane could still false-positive. | **CLOSED, not documented.** `_injective_nodes` now returns the ROUTE (a `Step` per node: consuming handle, live family, kid slot), and `certified` carries two of the witnessing node's values up that route, re-applying each step's own family with the other slots at baseline, certifying only when both reach an accepting item and differ there. That is the constructive argument the docstring always stated, executed. It costs one lift per value per step — the lane is four applications, not two, and every figure was updated. |
| R3 | `shared_occurrence_ambiguity.py`'s intra witness guarded its ambiguity assertion with `or label == "intra-derivation"`, which would have let a vacuous witness pass. | **FIXED.** The assertion is unconditional on both forms. |
| R4 | §A4 cross-references pointed at material living in §A3. | **FIXED** in both files. |
| — | The reviewer observed `INDEX.md` and the `PROMPT_*.md` files changing mid-review. | **Out of scope — the user's own concurrent work in another agent**, not this round's. Round 16 touched neither. |

**What R2 says about this round's method.** §4.3 named the pattern as "narrowing
a requirement to what was tested, and documenting a known-unsound mechanism".
R2 is the second half of that pattern caught again *inside the fix for the first
half*: replacing an honest admission with an unqualified claim that was itself
not quite true. The lesson that generalises is narrower than "check the gate
wording" — it is that a fix which removes an admission must close the gap the
admission described, not just the instance that prompted it.

---

## 5 — final state

```text
proto/shared_occurrence_ambiguity.py   exit 0
proto/exact_lane_cost.py               exit 0
ruff format --check / ruff check       clean, both files
pyright                                0 errors, 0 warnings, both files
forbidden-construct search             clean
git status --short                     only PROMPT_16.md (the user's own
                                       replacement of the tasking file)
git diff --check                       exit 0
```

Baseline 123 files; final 128 — the five allowlisted deliverables and nothing
else. The tracked `proto/.ruff_cache/` entry was restored after every Ruff
invocation; `proto/__pycache__/` was never dirtied (`python -B` throughout); the
stray untracked `.ruff_cache/` the auditor found at the effort root was removed.

No active document was edited. No commit, no push, no worktree. No source or
test file changed, and no parse regression is authorized by this round.
