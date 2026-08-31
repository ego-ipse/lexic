# Review 16 — final closure audit

The `closure audit` reviewer's responses, copied verbatim. A single fresh
`general-purpose` reviewer ran the role, returned NOT READY, and returned READY
on re-check after its three blockers were fixed. Both responses are below in
order. The dispositions are recorded in `reports/P16_ADVERSARIAL.md` §3.

`READY` certifies only that the evidence package is fit for coordinator review.
It does not approve the plan, authorize source implementation, or accept any
parse regression.

---

## Pass 1 — NOT READY

I read CLAUDE.md, docs/STYLE.md, PROMPT_16.md, both prototypes in full at their load-bearing sections, PROTOTYPE_16.md, P16_ADVERSARIAL.md, PROTOTYPE_15.md §11, and the cited production sources; I ran each prototype exactly once (both exit 0) and verified the git record.

## What passes

**(1) Independent oracle — verified.** `proto/shared_occurrence_ambiguity.py:179-321` keys `results` on the full occurrence path, re-resolves families at every occurrence (`:152-166`), never memoizes across occurrences, and dedups via production `same_value` (`:107-117`). Its independence boundary is stated exactly where the code sits (PROTOTYPE_16.md:112-119): it does share `local_choice_keys`/`assignments`/`selected_resolved`. The second claim also holds — `production_enumeration` (`:376-400`) really does drive shipped `forest.DERIVATIONS` over `readout.to_chart`, and my run reproduces `shipped_derivations=2 / wellformed=0 / malformed=2` against `grammar_meanings=4` on duplicate-slot and pending-frame. The mechanism citations check out: `forest.py:195-214` and `:392-402` (open-handle guard emitting the empty prefix), `fasttree.py:113-120` (memo by handle), `records.py:354-384` (`empty_tree` interning), `fold.py:475-491` and `:293-300` (`id(node)` keying).

**(4) Resolver scope unreopened.** No `resolve=`, no pair construction anywhere in either prototype (only the refusal message's "supply a resolver" string, `exact_lane_cost.py:481`). §7.8 restates the settled contract unchanged.

**(5) No parse regression authorized.** PROTOTYPE_16.md:908 states the opposite explicitly; nothing else touches it.

**(6) No writes outside the allowlist — clean.** `git status --short` and `git diff --name-only HEAD -- zzz_current_work/260826-target-shaped-parse` return only `PROMPT_16.md`. All packet documents (`INDEX.md`, `context.md`, `goal.md`, `DESIGN.md`, `TODO.md`, `LEDGER.md`, `SUMMARY.md`, `CURRENT_BUG_REPORT.md`) are **tracked**, so a clean status is real evidence they were not edited. The tracked files under `proto/.ruff_cache/` and `proto/__pycache__/` are unmodified. `--ignored` shows exactly four new files, all allowlisted. 127 files against the recorded 123-file baseline + 4.

## Blockers

**BLOCKER 1 — the withdrawn `Θ(local multiplicity)` claim is still what the artefact prints.**
PROTOTYPE_16.md:425-429 says the claim "was wrong" and "the correction propagates". It did not reach the prototype. My run of `exact_lane_cost.py` prints, as its own headline conclusions:

- `proto/exact_lane_cost.py:1038-1039` (`lower-bound` row): *"the bound is Theta(local multiplicity), and no lever in this round avoids it"*
- `proto/exact_lane_cost.py:1625` (the closing `invariant` line): *"exact settlement is Theta(local multiplicity)"*
- `proto/exact_lane_cost.py:33` (module docstring): *"so exact settlement is Theta(m(h))"*

A second withdrawn claim survives the same way: `proto/exact_lane_cost.py:1011` prints *"the exponential term is one node's own product"*, retracted at PROTOTYPE_16.md:444-446 and directly contradicted 20 lines later in the same run by `:987-992` (`stacked-product conclusion`). One execution emits both. Anyone who runs the artefact rather than reading §B1 gets the disproved claim.

**BLOCKER 2 — §10's coordinator handoff contradicts §7.7 on exactly the classifications Reviewer 2 forced.**
PROTOTYPE_16.md:878 — *"User decisions — four, not one. An earlier draft named only the first and filed the rest as gates"*. PROTOTYPE_16.md:1023 — *"**User decisions.** One new: adopt or decline the §B7 resource refusal, and set its ceiling."* The three reclassified semantic choices (value-identity relation, fully-refusing-node behaviour, adopting the declared-image quotient) are absent from the handoff — the fix recorded at P16_ADVERSARIAL.md:108 is undone in the one section a coordinator acts on. Same defect on gates: PROTOTYPE_16.md:1019 says *"Two new implementation gates"*, while §7.7 lists four new ones — (c) materialising the occurrence triple and (d) the demand-driven family-resolved chart, both created by Reviewer 1's A4 and B2, are missing. On the check as posed, the four user decisions in §7.7 are each genuinely semantic (each changes whether a document parses or raises) and no semantic choice is filed as an implementation gate there — the failure is that the handoff reverts to the pre-review classification.

**BLOCKER 3 — two quoted figures are not what the artefacts produce, and both overstate retention.**
- PROTOTYPE_16.md:465 quotes `full_peak_retained=[8,24,76,272,1044]` for the `law-settled` rung. The artefact prints `full_peak_retained=[4, 16, 64, 256, 1024]`. The report has substituted the application counts for the retention column.
- PROTOTYPE_16.md:515 quotes `peak_retained={full:272, ..., root-stop-only:18}` for `lever-isolation grow k=8`. The artefact prints `peak_retained={'full': 256, 'declared-bound-only': 256, 'root-stop-only': 2, 'both': 2}` — same substitution.
- Consequently PROTOTYPE_16.md:531-532 — *"`declared-bound-only == full` on all eight rows and identical peaks across all four settings"* — is false on the two `grow` rows, where `root-stop-only` drops the peak from 256 to 2. The narrower claim it is used to support (the *quotient* changes no peak) does survive the correct numbers.

This is the same applications-vs-retention conflation that produced Reviewer 2's A7 finding (P16_ADVERSARIAL.md:101), which makes it substantive rather than typographical.

## Minor, non-blocking

PROTOTYPE_16.md:166-183, headed "Every witness, both flavours, all lanes", lists 9 of the 10 `shared-shape` rows the run emits — `synthetic-consumers` (exact 4 / oracle 4 / correlated 4) is absent — so "strictly smaller on six of nine" is six of ten. The omitted row is non-discriminating and answer 1 correctly says "ten witnesses"; no claim moves.

Everything else I checked reproduces exactly: the whole Part A table, `correlation-disproof=6`, `oracle-independence`, `production-enumeration`, `shared-once-differential` (`extra_applications=2 == shared_node_own_families=2`), all four `occurrence-effect` rows (`consumer_body_executions=4` vs `expansions=2`), `partial-guard-boundary`, `fully-refusing-node`, `intra-derivation-sharing`, `stacked-product` (50/40/46%, 98184 comparisons), `applications-are-not-the-cost` (58×/247×/1013×), `oracle-check`, `dedup-climb`, `grow-image` (including `baseline_folds=51`), `lower-bound`, `budget-refusal`, and `static-census`. Timing and CPU-share rows differ run to run (my floor spreads were 1.193/0.360/0.177% against the quoted 0.451/0.194/0.293%, chart share 67.0% against 68.1%), which the report explicitly declines to quote as a fixed band — correct handling, not a finding.

All three blockers are fixable entirely inside the write allowlist (`proto/exact_lane_cost.py`, `reports/PROTOTYPE_16.md`) and require rerunning `exact_lane_cost.py`.

**NOT READY**

---

## Pass 2 — READY

All three fixes verified against the files and against a fresh reproduction run of `exact_lane_cost.py` (exit 0). One run each was used; nothing else ran concurrently; I edited nothing.

**C1 — confirmed fixed.** Grepping the RUN OUTPUT (`/tmp/p16_exact_rerun.txt`) for `Theta(local`, `Theta(m(h))` and `exponential term is one node` returns **0 hits**. The only two surviving `Theta` occurrences are explicit disclaimers: the `lower-bound` row now ends *"applications are Omega(m(h)) here and no lever reduces them. Wall cost is this count times the value-identity work ... so there is no single-unit Theta to quote"*, and the closing `invariant` says *"no single-unit Theta is claimed and no budget may be denominated in applications"*. The module docstring (`proto/exact_lane_cost.py:26-37`) matches. The `multiplicity` row now states its identity is definitional, points at `prove_multiplicity_is_paid_at_every_level`, and ends *"No claim is made that the exponential term sits at one node in general"* — so it no longer contradicts `stacked-product conclusion` four lines later.

**C2 — confirmed fixed.** §10 now reads "Open gates — five new" and enumerates all five with section refs (partial-operation guard §A6; chart-edge occurrence identity §A1; materialising the occurrence triple §A1; demand-driven family-resolved chart §B6; `ForestCtx` suspended-vs-cyclic §A3), and "User decisions — four, all of them semantic" listing refusal adoption+unit+ceiling, authoritative value-identity relation, fully-refusing-node behaviour, and the declared-image quotient. That agrees with §7.7 (PROTOTYPE_16.md:865, :882) rather than reverting past it.

**C3 — confirmed fixed, and the corrected numbers are the artefact's.** Report `full_peak_retained=[4,16,64,256,1024]` with `streaming_peak_retained=[2,2,2,2,2]` matches the run exactly; the lever-isolation row `peak_retained={full:256, declared-bound-only:256, root-stop-only:2, both:2}` matches `{'full': 256, 'declared-bound-only': 256, 'root-stop-only': 2, 'both': 2}`. The narrowed sentence — `declared-bound-only == full` on all eight rows for both applications and peaks, with the 256→2 drop attributed to the root stop — is true on every one of the eight rows I checked.

**Nothing else regressed.** `stacked-product` (50/40/46%, 98184 comparisons), `grow-image` (2 applications, baseline folds 11…51, witnesses s1–s9), `dedup-climb`, `budget-refusal`, `static-census` (104/19/85, 101/1/100, 61/12/49, 51/10/41), `applications-are-not-the-cost` (58×/247×/1013×) and `flavour-neutral` all reproduce the quoted figures. Only the disclosed-as-variable rows moved (unambiguous-path chart share 68.7% this run against the quoted 68.1%, timing spreads), which §B6 point 4 and §B5 already scope.

**Allowlist still clean.** `git status --short` and `git diff --name-only HEAD -- zzz_current_work/260826-target-shaped-parse` return only `PROMPT_16.md`. Since my first pass exactly three files changed — `proto/exact_lane_cost.py`, `reports/PROTOTYPE_16.md`, `reports/P16_ADVERSARIAL.md`, all allowlisted. The tracked `proto/.ruff_cache/0.15.12/13011947814826943830` was rewritten at 13:25:39 and is byte-identical to HEAD (restored, per the round's done gate); `proto/__pycache__` is untouched. Minor note, not a finding: a new untracked-and-ignored `.ruff_cache/` appeared at the effort root (two files, no tracked content, no diff).

Dispositions are recorded accurately in `reports/P16_ADVERSARIAL.md` §3, including the non-blocking "six of nine / six of ten" note left as I scoped it.

**READY** — this verdict certifies only that the evidence package is fit for coordinator review. It does not approve the plan, authorize any source implementation, or accept any parse regression.

---

**Coordinator note.** The auditor's minor observation is actioned: the stray
untracked `.ruff_cache/` it found at the effort root was removed, so the round's
footprint is exactly its five allowlisted files. The single reviewer ran the
closure role twice — once fresh, once on re-check of its own three blockers —
rather than a second fresh reviewer being spawned for three narrow, mechanically
verifiable corrections.
