# Review 16 — fold-readiness review

> **THIS VERDICT IS WITHDRAWN.** The coordinator reopened the round after the
> READY below: three substantive blockers remained — the shared
> transparent-synthetic DAG was never covered, the injective certificate was
> unsound over families and the gap had been documented rather than closed, and
> the cost model asserted a product the evidence does not support. The
> corrections are recorded in `reports/P16_ADVERSARIAL.md` §4.3. The response
> below is retained as history; it does NOT certify the current package, and
> the round is not fold-ready on its authority.

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
