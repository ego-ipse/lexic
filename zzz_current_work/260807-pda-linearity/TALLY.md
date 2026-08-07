# pda-linearity — work tally (context-recovery ledger)

Split out of `../260807-opsis-radical/gate/` on 2026-08-07. The pre-split
history lives in `../260807-opsis-radical/atlas/TALLY.md` (the entries from
"GATE INVESTIGATION CLOSED" onward) and ends with a pointer here. Newest last.

- **Effort split.** `gate/` moved to its own directory: the engine work had
  outgrown the ergonomics effort that surfaced it, which was that effort's own
  recommendation and its reviewer's. Nothing moved in `src/`. Probe paths fixed
  (`common.py`'s `ROOT` was `parents[4]`, now `parents[3]`; the plugin
  `PYTHONPATH=` lines and `FINDING.md` §9 re-pointed), all four mode-taking
  probes re-run green at the new path. `HANDOVER.md` and this ledger written;
  `260807-opsis-radical`'s HANDOVER and TALLY point here.

## Carried in from before the split — the state that matters

- **LANDED:** `relax_non_semantic` narrowed to `ast.non_semantic &
  nullable_names(ast.rules)`, solved on the INCOMING grammar. It had been
  deleting the GBNF metagrammar's authored maximal-munch discipline, making the
  codegen grammar genuinely ambiguous. vyx 4.451s → 0.029s; all ten
  ground-truth grammars ride the PDA with no resolver. Full account and the
  cost accepted: `FINDING.md` §11. Not committed.
- **BIGGEST OPEN ITEM:** the PDA is quadratic on pipe-heavy vyx packets — no
  fork, no fallback, the predictive runtime succeeding, 73s for 11KB, 92% of it
  inside `_probe` (which runs one side of every boundary to end-of-input).
  Pre-existing; A/B'd as NOT a regression from the relaxation fix, which also
  answered the "gbnf-meta regressed" question (it did not: 5.508 → 5.471
  µs/char, inside the bench's own 2.80% noise floor). `PROBE-QUADRATIC.md`.
- **KILLED BY MEASUREMENT:** the cheap linearity shortcut (skip both probes when
  the boundary class is `_ADMITS`). 4 of 243 `_ADMITS` boundaries genuinely
  FORK — the class is not a sufficient statistic for the verdict, and skipping
  would commit what the engine refuses.
- **DESIGNED, NOT BUILT:** lockstep convergence in `_fork_verdict` (the linear
  fix) and solution D's islanding half (sound, affordable, narrow subject).
  Both specified in their documents with their gates and revert conditions.
- **RESERVED FOR THE USER:** whether real vyx workloads reach 11KB pipe-heavy
  packets soon. If yes, the quadratic outranks everything here.
- Move verified end to end: four mode-taking probes green at the new path, both
  pytest plugins load via `PYTHONPATH=zzz_current_work/260807-pda-linearity`
  (525 passed with `-p forkcount`), `run_all.sh`'s self-documented invocation
  re-pointed, and the atlas instrument's three censuses still pass (its
  `serve.py` docstring reference now points across to `../../260807-pda-
  linearity/FINDING.md`). Also folded in the reviewer's five notes on PLAN.md —
  the load-bearing one is note 1: the step-budget escape does NOT protect the
  convergence predicate, since a too-coarse stack signature would declare false
  convergence and commit what the engine refuses. Signature born conservative,
  cheapened only under the parity gate, with adversarial fixtures of its own
  (identical (pos, shallow-signature) and divergent pending values); the
  "values accumulated before convergence" equivalence is a proof obligation,
  not a refactor.
