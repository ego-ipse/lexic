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
- **USER OVERRIDE (2026-08-07): start with PLAN items 4 and 5**, siding with the
  reviewer's note 4 ("items 4-5 first, regardless of the split") over my own
  ordering, which had put the quadratic first. Both landed, gates green.
- **ITEM 4 DONE** (`171ab83`): `FlatClone` gained a `name` slot. Set at all
  three construction sites — the per-key shells from `CloneSpec.name`, an
  inline group to `""` (it stands for no rule the grammar named), and an
  attempt sub-clone to its parent's (it stands for the parent's rule). Two
  tests pin what the name SAYS, not just that the slot exists; the pinned
  `__slots__` test updated. This removes the layering inversion the trial probe
  had to commit (runtime → `compute_binding` for a rule name) and is the
  runtime-island climb's prerequisite.
- **ITEM 5, FIRST HALF DONE** (`8d1ffc2`): `PdaFail(message, pos)` with a
  structured `.pos`; `ProbeFork` inherits it. Every raise site that knows a
  position now passes it (25 sites across islands/kernel/matchers/decisions/
  flatten); the four with no position report -1 rather than inventing one.
  atlas dropped its `FRONTIER` regex and reads `fail.pos` — its three censuses
  still pass. **A finding worth keeping:** `.pos` is the offset the failing
  construct was attempted FROM, not the deepest character matched — a literal
  mismatch reports the literal's start, and the optimizer merges adjacent
  exactly-once literals into one run, so `"abc" "def"` against `abcXef` reports
  0, not 3. My first test assumed the other contract and failed; both halves are
  now pinned. The SECOND half of item 5 (the fuller readout record with
  expected-next) waits for a consumer — rung 2's engine clocks are the likely
  one.
- Gates for both: run_checks exit 0, suite **3783 passed** / 8 skipped (from
  3776 — five new tests), check_generated CLEAN, run_examples exit 0.
- Next per PLAN.md: item 1 (scope the quadratic — corpus-wide probe counts, and
  the STOP_FORCED reachability argument), then item 2 (lockstep convergence).
- **ITEM 5 SECOND HALF DONE** (`948879b`) — the user corrected my scope
  narrowing ("I did not say to only half"), rightly: I had deferred it on a
  consumer-wait argument I made up. `UnsupportedConstructError.readout` now
  carries a `Refusal` (pos, rule, expected, negated, undecidable) on a refused
  parse. `PdaFail` carries the facts; the product seam attaches them when the
  gated engine ALSO declines, so the message and the verdict are untouched —
  additive. `Refusal` is primitives because `exceptions.py` imports nothing
  from lexic. `expected`/`negated` travel as one `wanted` pair because they are
  one fact (the engine's own `(chars, negated)` shape) — that came out of a
  pylint too-many-arguments finding which was a real design smell, not noise.
  New `flatten.arm_expected` supplies the set at no-arm refusals. atlas now
  reads the frontier off the PUBLIC surface (`e048242`) and no longer reaches
  past the product into the engine floor — the lexic ask is closed end to end.
  Gates: run_checks 0, suite 3787 passed, check_generated CLEAN, examples 0.
  Wiki: `error-vocabulary.md` gains "The refusal readout"; `log.md` an entry.
- **ITEM 1, FIRST HALF ANSWERED — and it reframes everything.** Tallying which
  RULE pays the run-to-EOF probes (possible only because item 4 gave FlatClone
  a name): **`ws` pays 4,736 of 5,027 fork verdicts — 94%.** vyx's pipe-lists
  are 6. So the quadratic is NOT vyx-shaped, it is whitespace-shaped: any
  grammar with a noise rule in a repeated position pays it, and vyx merely had
  a document long enough to make it visible. Item 2 is a lexic priority, not a
  vyx footnote, and the prize is larger than the 73s figure implied. Caveat
  recorded: this counts verdicts, not cost — `probes/probecount.py` was written
  for the cost half but `lexic.generate`'s depth budget yields 3-43 char
  inputs, so it needs per-grammar growth templates first.
- Next: the STOP_FORCED reachability argument (item 1's second half, could halve
  item 2), then lockstep convergence.
