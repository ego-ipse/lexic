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
- **ITEM 1 CLOSED — both questions answered.** (a) GENERALITY: the quadratic is
  `ws`-shaped, not vyx-shaped — 4,736 of 5,027 fork verdicts are paid by a
  whitespace rule (above). (b) STOP_FORCED: hunted a counterexample instead of
  arguing (`probes/stopforced.py`, six loop shapes) — none of them reaches a
  fork verdict at all, because those loops are settled by stop-set/k-window
  gates and never enter the attempt path. The structural finding that explains
  the corpus's zero: by the time `_fork_verdict` runs the iteration has ALREADY
  parsed (a failing iteration closes the loop earlier), so the take side dies
  only if the remainder fails after a successful iteration while stopping
  completes — and the corpus's attempt-gated loops are noise loops, where one
  more iteration steals nothing anyone needs. Reachable in principle (gbnf-meta's
  terminator theft WAS it; the relaxation fix removed the subject, not the
  shape), so **the probe stays** — a constant is cheap insurance on a soundness
  check. And the question is moot anyway: lockstep makes BOTH probes O(1), so
  the halving was only ever a constant-factor shortcut. Nothing about item 2
  changes.
- NEXT: item 2, lockstep convergence in `_fork_verdict`. Design is
  PROBE-QUADRATIC.md's last section; the shape of the implementation is now
  clear from reading `_drive`: it needs (1) a bounded drive — a position limit
  checked at the OUTER frame-boundary loop only, so the per-item hot path is
  untouched; (2) each side keeping its own (stack, pos) and being swapped in and
  out per round, which `_probe` already does once; (3) a control-state
  signature — (pos, per-frame (arm identity, item index, count)) and explicitly
  NOT the accumulated values, since those differing is the thing being measured;
  (4) the budget escape falling back to today's run-to-EOF. Gate: the parity
  differentials, plus adversarial fixtures for the convergence predicate
  (identical control state, divergent pending values) per the reviewer's note 1.
- **ITEM 2 DONE (`21f36bd`) — the lockstep verdict, and the quadratic is gone.**
  `_fork_verdict` now settles a both-viable boundary by CONVERGENCE: both sides
  driven in step until one dies (forced, as before), or both stand at the same
  position with the same control state — at which point the stack IS the
  continuation, so the futures are identical and the verdict reduces to the
  values built on the way there. Agreeing values → TAKE (the common case, O(1)).
  Differing values → the COMMON remainder runs ONCE, not twice: completing makes
  it a real fork, dying means neither completes, which was already TAKE. No
  convergence inside the budget → falls through to the untouched EOF comparison,
  so the worst case is exactly what shipped before.
  MEASURED: vyx pipe-heavy whole parse 128 lines **4.63s → 0.34s**, 512 lines
  (11,281c) **73.4s → 4.12s**; probe calls over that parse **512 → 2**.
  Gates: run_checks 0, suite **3796 passed** / 8 skipped, check_generated CLEAN,
  examples 0 — parity differentials included in the suite.
- TWO BUGS FOUND BY MEASURING, both of which silently disabled the whole thing
  while every test still passed — worth remembering, because "green" would have
  shipped a no-op:
  (a) **Counts must be normalised in the signature.** The take side has taken an
  iteration the stop side has not, so raw `F_COUNT` differs FOREVER and no two
  states ever match. Past its mandatory floor with no ceiling to run into, a
  count cannot constrain the future and is not part of the state (`_count_key`).
  (b) **The bound must be a PARAMETER, not a cursor field.** Moved onto the
  cursor to satisfy a pylint locals cap, it leaked into nested attempt sub-runs,
  which stopped early and never converged — 64 of 66 boundaries went back to the
  slow path and the quadratic returned in full (88s). The bound belongs to one
  call; a nested drive must be unbounded. The locals cap was paid instead by
  reading `frame[F_ENDS]` directly rather than aliasing it.
- Residual, NOT claimed as fixed: the parse is still mildly superlinear
  (191c→0.008s, 11,281c→4.12s is ~n^1.7, not n). The `_probe` quadratic is gone;
  something else scales. That is a fresh finding and wants its own measurement
  before anyone guesses.
- PLAN items 1, 2, 4, 5 are all done. Remaining: item 3 (re-measure — partly
  done above; `probes/economics.py` and the benchmark row still want a rerun),
  item 6 (D-half-2 islanding, only if item 3 still shows it paying).
- **ITEM 3 DONE — re-measured, and it closes item 6.**
  · corpus: all ten ground-truth grammars still ride the PDA, no resolver,
    round-trip holding (vyx 9,417c in 0.029s) — unchanged, as intended.
  · `bench --only gbnf-meta`: lexic-pda **5.386 µs/char** against 5.471 before
    the lockstep and 5.508 pre-relaxation-fix, at a 0.50% noise floor. Flat:
    the meta row's reduce path has no both-viable boundaries to settle, so it
    neither gains nor pays. No regression from any of this effort's changes.
  · forkcount over the suite: **ProbeFork 9 → 3, and one of those three is our
    own unit test constructing one.** So TWO real forks remain in 3,796 tests,
    both `dict-def`. The six pipe-list forks are gone — lockstep settles those
    boundaries by convergence instead of bailing, which was an unlooked-for
    second win: fewer whole-document Earley fallbacks, not just cheaper probes.
  · economics: pipe-heavy still "no fork"; dict-heavy still BAILS at every size.
- **ITEM 6 (D-half-2 islanding): CLOSED AS NOT WORTH BUILDING.** Its own revert
  condition ("if scaling does not move, revert") is now moot in the stronger
  direction — the subject evaporated. The only live forks left are the two
  dict-defs, and islanding BAILS on exactly those, so the change would buy
  nothing and cost an island attempt on every one. The design in
  D-ISLANDING.md stays valid and is worth keeping for whenever a fork
  population reappears; it simply has no population now. Not a rejection of the
  design — a measurement of its subject.
- RESIDUAL, now characterised: the PDA is ~**n^1.3**, not linear
  (719c→0.044s, 1,424c→0.116s ×2.6, 2,832c→0.345s ×3.0, 5,648c→1.142s ×3.3,
  11,281c→4.076s ×3.6 — the per-doubling factor is still creeping up). The
  `_probe` quadratic is gone; the remaining growth is elsewhere and is a fresh
  question, not a leftover of this one. Whoever takes it should profile before
  theorising — that discipline is what found both of the last two.
- PLAN items 1-6 are now all closed (2, 4, 5 built; 1, 3 measured; 6 measured
  and declined). Deferred still: D-half-1 (per-site licences, needs the
  clone-identity trade priced) and `nullable_names` → `ir/grammar/`.
- **LABEL CORRECTION (user caught it).** Throughout this ledger, "vyx 4.451s →
  0.029s" and "vyx 9,417c in 0.029s" mean **the GBNF METAGRAMMAR reading
  vyx.gbnf as grammar SOURCE TEXT** — not the vyx grammar parsing a vyx packet.
  The numbers are right; the shorthand was misleading, and it invites exactly
  the comparison that exposed it: 9,417c/0.029s reads as 3.1 µs/char, while
  `bench --only vyx` reports lexic-pda at 5.724 µs/char.
  Both reproduce in-process, side by side, so the methodology agrees with the
  benchmark and the gap is workload:
      bench vyx corpus (vyx grammar → a vyx packet)   3,461c  5.305 µs/char
      metagrammar → vyx.gbnf source                   9,417c  2.925 µs/char
  Read every "vyx" in the entries above as "the metagrammar reading vyx.gbnf"
  unless it says packet. The pipe-heavy/dict-heavy packet measurements ARE the
  vyx grammar on instances — those are labelled and are the other workload.
  NOT measured, so not claimed: WHY a packet costs ~1.8× more per char than
  grammar text. The plausible reason is model density (a packet builds more
  models per character than grammar source, which is mostly literals and char
  classes), but nobody has counted, and this effort's rule is that a cause is
  measured before it is asserted.
