# Review 16 — fold-readiness review

> **THE FIRST VERDICT BELOW IS WITHDRAWN.** The coordinator reopened the round after the
> READY below: three substantive blockers remained — the shared
> transparent-synthetic DAG was never covered, the injective certificate was
> unsound over families and the gap had been documented rather than closed, and
> the cost model asserted a product the evidence does not support. The
> corrections are recorded in `reports/P16_ADVERSARIAL.md` §4.3. The response
> below is retained as history; it does NOT certify the current package. The
> CURRENT verdict is the second one, from the reopening reviewer, recorded
> immediately below this banner.

The reopened round's reviewer response, copied verbatim. One fresh
`general-purpose` reviewer ran the FOLD-READINESS role — a strictly higher bar
than the earlier closure audit, which certified only fitness for coordinator
review. It returned NOT READY three times and READY on the fourth pass.

Its READY bar, as set by the tasking: no semantic, planning or user decision
remains open; every conclusion is directly foldable into the active documents;
remaining items are concrete implementation or later measurement tasks; no
unsupported closure claim remains; executable output and prose agree exactly.

Findings and dispositions are recorded in `reports/P16_ADVERSARIAL.md` §4.2.
The earlier closure audit, superseded by this one, is preserved below it.

---

## Current verdict — READY (reopening reviewer, pass 4)

A fresh reviewer was tasked to ATTACK the three corrections of the second
reopening. It returned NOT READY three times — correction 3 not landed at five
sites, a second certificate hole of the same species as the first, then two
stale-figure sweeps — and READY on the fourth pass. Its final response:

All eight sites verified clean. Final gate check passed.

## Verdict: **READY**

Fresh run of both prototypes: `exit 0`, sequential, nothing concurrent. Working tree contains only your three files against the savepoint (`exact_lane_cost.py`, `PROTOTYPE_16.md`, `P16_ADVERSARIAL.md`). I edited nothing.

### The eighth site — closed, including the substantive half

`PROTOTYPE_16.md:669-680` is now "**Four is a best case, for TWO independent reasons**" and gives both. The route-length half is correct and correctly scoped: *"the lift costs one application per value per STEP, so the route half costs 2 only because those witnesses sit ONE step below the accepting item. A witness three steps down costs `2 + 6`."* The arithmetic checks (2 for the local witness + 2 values × 3 steps). §8 (`:1029-1032`) carries it as its own not-proved item. This is the qualification I said was missing everywhere, and it is now stated in both the place that quotes the figure and the place that lists what the round does not prove.

### Verified this pass

- **Figure sweep clean**, including the bare-word form that escaped the pattern sweep. Zero hits for `Two is a best`, `two applications`, `2 applications`, `only the two`, `the two the witness`, `in two applications`, `answers in two`, `law_lane_applications=2`, `applications=[2` across both prototypes, `PROTOTYPE_16.md`, `REVIEW_16.md` and both fresh run outputs. Every `law lane` line in the report that contains a `2` contains it only as `2^k` or `k=2`.
- **The one surviving "Two applications"** — `exact_lane_cost.py:1318` → output line 18 — is the `streaming` row's *per-ambiguity-point* cost for the children's own sets. A different quantity, correct, unrelated to the law lane. Same disposition as last pass.
- **Run output self-consistent:** `law_lane_applications` is `4` in all 9 firing rows and `0` in all 5 non-firing rows. The closing `invariant` prints *"…own family count plus an end-to-end route check, measured at four applications against 2^k…"*.
- **R1 (correction 3) still clean** — zero hits for every multiplicative claim form across sources, report and both fresh outputs.
- **Key rows reproduce:** `dead-family-route … certificate_reports_ambiguity=False settle_meanings=1 unrolled_oracle_meanings=1`; `positive-certificate points=4/8 law_lane_applications=4` (now pinned by `assert … == 4`, so the figure is held by execution); both `shared-transparent-synthetic` rows at `occurrence_edges=2 has_a_reducer_action=False exact_meanings=2 unrolled_oracle=2 agree=True`.
- **R2's mechanism** — soundness, termination, channel coordinates, safe-direction false negatives — re-confirmed unchanged from my full analysis two passes ago.
- **`REVIEW_16.md`'s withdrawal banner** intact; no fold-readiness claim rests on it. **No open user decision** (`:962`, `:1133`).
- **`P16_ADVERSARIAL.md`** records the eighth site and the four-failure meta-lesson without contradicting itself: the R2 row states the seven-site pass, and the paragraph below records that the extended sweep still missed one. Chronological, not conflicting.

### One non-blocking precision note, on the record

§8's new item says *"the law lane's four applications are a floor"*. Four is the floor for a witness that is **not** an accepting item. If the ambiguous node **is** an accepting root, `routes[root] is None`, `_route_transmits_two_values` breaks before any lift, and the lane costs **2**. The over-statement is in the conservative direction — it makes the lever look more expensive than its true best case — and the bullet's actual load-bearing claim ("not a figure to plan against") is right and is the point. Not worth a further pass; flagging so it is not later mistaken for a measured bound.

---

Every blocker raised across the four passes is closed: correction 1 (genuinely chart-shared transparent synthetic, both forms, non-vacuous), correction 2 (family-aware route plus the end-to-end lift, decisive negative control, positive shortcut intact, route length now qualified), correction 3 (three-term decomposition, no product asserted, no new timing), and the two sweep failures that followed. The evidence, the prose and the executable output agree.

**Coordinator note.** The reviewer's non-blocking precision note was ACTED ON
rather than accepted: §8 no longer calls four a floor. It now states the true
range — 2 when the witnessing node is itself an accepting item and there is no
route to lift along, rising by two applications per route step, unbounded here.
Leaving a known-imprecise claim because it errs conservatively is the habit this
round failed on repeatedly; it is not repeated here.

**Coordinator fold note.** `law_lane_applications` counts only local-witness
and route-lift reducer calls. The baseline column counts visited nodes rather
than reducer calls, and family-liveness discovery and `same_value` comparisons
are outside both figures. This does not reopen the semantic mechanism or delay
implementation. The active plan requires production to reuse cached family
baseline outcomes and measure the complete lane; `PROTOTYPE_16.md` no longer
presents four plus the baseline column as a complete cost account.

---

## Superseded verdict — the first fold-readiness review

## Final verdict — READY

## Verdict: **READY**

The falsified band is gone and every open item is closed. This is the fourth reproduction pass; both prototypes exit 0.

### The final fix — verified at all three sites

- **Implementation task 6** (`PROTOTYPE_16.md`): "It DOMINATES settle on an unambiguous document today; the ratio is read per run and no band is quoted (§B6)." No digits.
- **Handoff** (`:1009-1010`): "the chart build DOMINATES settle there. The ratio is read per run; §B6 carries the samples and no band is folded." No digits.
- **§B6 point 1**: "Observed at 68.1%, 71.7% and 64.6% on three separate runs — samples, NOT a band: like the §B5 spreads this ratio is read per run, and what folds is that the build dominates, not the digits."

`grep` for `68–72` / `68-72` returns zero across the report and prototypes. My fourth run measured **64.9%** — which falsifies nothing: the report asserts three observations (all genuinely observed) and explicitly declines to bound the range, and 64.9% is dominant. This is now the `§B5` form, correctly applied. Your own record names the over-correction honestly in the pass-3 paragraph.

### Full verification, this pass

**Withdrawn-string sweep — clean.** Zero hits across both prototype sources and both run outputs for all fourteen strings (`Chart.edges already`, `already carries`, `already there`, `which the chart carries`, `is the user's`, `Theta(local`, `Θ(local`, `exponential term is one node`, `declared-bound-only`, `BudgetRefusal`, `quotient=True`, `_ABSENT`, `68–72`, `68-72`). The only residuals in `PROTOTYPE_16.md` are the three lines that explicitly record a withdrawal (`:462`, `:482`, `:792`); `P16_ADVERSARIAL.md` retains the history, as it must.

**Evidence reproduces.** Part A output is byte-identical across all four of my runs. Every deterministic Part B row — `ladder`, `multiplicity`, `stacked-product`, all eight `oracle-check` rows, `streaming`, `lever-isolation`, `quotient-rejected`, `refusing-family-is-not-ambiguity`, `baseline-past-a-refusing-default`, `grow-image`, `dedup-climb`, `lower-bound`, `flavour-neutral`, `static-census`, `applications-are-not-the-cost` — is identical run to run and matches its quoted block exactly. Only CPU-derived values move, and all three now carry per-run framing with no band folded.

**Classification.** `USER DECISIONS: none` (`:865`), `Open user decisions: NONE` (`:1028`), `§B7` "neither a user decision nor an implementation blocker" (`:814`), eight implementation tasks, four measurement tasks, complete-document resolver scope unchanged, no parse regression authorized.

**Scope.** `git status --short -uall` on the effort dir returns exactly the four allowlisted files at every pass. No active plan document, `src/`, `tests/`, `.wiki` or `pyproject.toml` was touched at any point.

### All seven coordinator corrections, confirmed landed

1. **Bottom semantics** — `apply_or_none` absorbs only by per-rule declaration and re-raises otherwise; `_lanes_or_none` skips the family on an empty child image; `_verdict` adds `VERDICT_NO_MEANING`. Both required witnesses execute (`partial-one-refusing-branch`, `partial-every-branch-refusing`) plus `empty-image-scope` and the `partial-family-defect` contrast; `required-production-signal` states the distinct exception production must add.
2. **Certificate** — `_local_witness` counts only meanings that exist; baseline from the first live family; both negative controls decisive.
3. **Value identity** — production `same_value` authoritative in both lanes; `repr` recorded as a prototype shortcut and implementation task 7; on no decision list.
4. **Quotient rejected** — `_ceiling(handle, roots, settings)` consults no bound; all prose sites rewritten; the dead `bounds` channel fully removed from `settle`, `_settled_set`, `_root_multiplicity`, `parse_ladder`, `_refusing_arm_case`.
5. **No ceiling** — no `BudgetRefusal`, no `Settings.budget`, no policy proposed; worst case recorded as a property of the current enumeration.
6. **Scope and overclaims** — shared family-decomposition machinery stated wherever agreement is claimed; the occurrence triple stated as derivable and recorded by no structure at every one of the five sites (§A1 lead, §A1 bullets, answer 3, both output rows); synthetic case reported NOT COVERED; exponential qualified to the current enumeration and slot laws.
7. **Implementation work** — eight ordered tasks including the `ForestCtx` defect; four measurement tasks.

### Non-blocking

`P16_ADVERSARIAL.md:226-229` reads "except two in `PROTOTYPE_16.md` … (three of them: …, and one more)" — the patched sentence says "two" and "three" in one breath. Prose only, in the history record; the substantive correction is stated cleanly in the pass-3 paragraph.

---

**Fold-ready.** No semantic, planning, or user decision remains open. Every conclusion is directly foldable as written, remaining items are concrete implementation or later measurement tasks only, no unsupported closure claim survives, and executable output and prose agree. The durable lesson this round earned — grep each withdrawn string across *all* deliverables *and* both run outputs, and never fold digits from a noisy measurement — is recorded in `§4.2`.

---

**Coordinator note.** The one non-blocking item — the "two"/"three" contradiction
in `P16_ADVERSARIAL.md`'s sweep sentence — was fixed after this response; the
sentence now says THREE residual lines and names them as withdrawal records.
The four earlier NOT READY responses are summarised with their dispositions in
`reports/P16_ADVERSARIAL.md` §4.2 rather than reproduced here.

`READY` certifies fold readiness: the evidence is foldable into the active
documents as written. It does not itself modify the plan, authorize source
implementation, or accept any parse regression.
