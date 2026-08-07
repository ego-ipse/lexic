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
- **THE RESIDUAL IS GONE — the parse is LINEAR** (`81cc106`). Chased the ~n^1.3
  left over after item 2, and the discipline paid twice: two hypotheses killed
  by measurement before the third landed.
  · KILLED — "the number of operations grows superlinearly": every counted
    component grows EXACTLY ×4.0 for ×4 input (frames copied, `_attempt_run`,
    `_lockstep_verdict`, `_advance`, `pending_values` calls and top-level
    elements walked). Operation count was never the problem.
  · KILLED — "it is the garbage collector" (a classic cause of apparent
    superlinearity in allocation-heavy Python, and the bench harness disables
    gc, which made it a live suspect): identical timings with `gc.disable()`.
  · FOUND — profiling at two sizes: **92% of the parse in `values_agree`, its
    calls growing ×63 for ×8 input** (145K → 9.2M). The snapshot was linear but
    it was re-walked IN FULL at every convergence, and convergences grow with
    the input.
  FIX: both sides of a boundary are copies of ONE live stack, so everything
  already in a container at fork time is identical between them by
  construction — only appends after can differ. `value_shape()` takes that
  watermark; `pending_values(stack, shape)` compares the delta past it.
  Conservative where the premise fails: a container that came back SHORTER was
  replaced, not appended to, so it is compared whole; frames pushed after the
  boundary have no watermark and are compared in full. Three tests pin exactly
  those three cases.
  MEASURED: 512-line packet 4.08s → **0.49s**, and growth is now flat —
  **44 µs/char from 719c to 11,281c**, ×1.98 time for ×2 input (was ×2.6 rising
  to ×3.6). Against where this effort started on that input: **73.4s → 0.49s**.
  Gates: run_checks 0, suite **3799 passed**, check_generated CLEAN, examples 0.
- Real-workload check: `bench --only vyx` (the vyx grammar on a real packet,
  NOT the metagrammar route) reads 5.658 µs/char at a 1.44% noise floor —
  unmoved, as expected: a 3,461c corpus of ordinary traffic has few both-viable
  boundaries, so it never paid the cost this removes. The synthetic pipe-heavy
  body is ~44 µs/char, ~8× denser in boundaries than real traffic. Worth saying
  plainly: **this effort's wins are on boundary-dense inputs; ordinary vyx
  traffic was already fine and is unchanged.** What changed is that the bad
  case is no longer catastrophic — and no longer superlinear, so it cannot
  become catastrophic at scale.
- **DOCS APPLIED** (`1824a93`). `decisions.md` had gone STALE at line 176 — it
  still said a both-viable boundary is "resolved by probing both sides to
  end-of-input", which the lockstep verdict retired. Corrected, and a full entry
  added: why the old shape was quadratic (with the ws-pays-94% finding, so it
  does not read as one grammar's quirk), why convergence is sound, the three
  things the predicate must get right, why only the delta since the boundary is
  compared, and what was ruled out on the way (operation counts, the GC). The
  honest limit is in there too: ordinary traffic was always fine and is unmoved.
  `log.md` carries the short version. This mattered because the reasoning lived
  ONLY in this gitignored folder, which committed docs may not cite.
- **SRC WORK FOR ATLAS RUNG 2 — done** (`0a75c96`). Checked what the two engine
  clocks need. PDA clock: nothing — `PdaKernel` is subclassable and every
  decision point is an overridable method (proven by use: four different
  subclasses this session), and `FlatClone.name` now lets a trace NAME the frame
  it reports, which it could not before item 4. Earley clock: the chart TYPES
  were public but the readout READERS were not, so the instrument would have had
  to deep-import `earley.kernel.forest.readout` — the same layering inversion
  removed on the predictive side. Now exported whole from `lexic.parsing`
  (`to_chart`, `decode_item`, the `accept_*` readers, `start_completion_ends`,
  `root_ambiguous`, `child_node`) with an identity test and an end-to-end one.
  Additive; gates green (run_checks 0, suite **3801 passed**, generated CLEAN).
  **The other agent should have everything it needs on the src side for rung 2.**
- **OPTIMIZATION INVESTIGATION OPENED — `OPTIMIZATION.md`. No src touched.**
  Target is the COMMON path (`bench --only vyx`, 5.658 µs/char on real traffic),
  which nothing this effort landed has moved. Headline is a NEGATIVE result that
  redirects the work:
  · Profile: nothing dominates — `_drive` 13%, `_enter` 7.7%, `vstr_once` 7%,
    `_fast_fields` 6.8%. A structurally busy interpreter loop, not an
    algorithmic error.
  · Model census: 3,342 models for 3,461 chars, but only **561 distinct
    objects** — interning already shares 83%, so allocation is not the cost.
    54% of models are single-char value_str (`nl-word ::= nl-tail+` over a
    char-class rule builds one model per character).
  · **CEILING PROTOTYPE (the decisive one):** inlined those rules grammar-side
    — same language, different model shape — and measured. **46% fewer models
    buys 16% faster.** So this effort's own prior art ("a 30-50% win needs a
    structural model-count cut") does NOT survive measurement: model count is
    not the dominant cost and cutting it has a low ceiling.
  · **What time actually tracks: clone ENTRIES, not models.** The 46% model cut
    moved time 16%; the 11% entry cut in the same variant moved it 16%.
    `_enter` runs **1.56 times per character** — vyx's lexical layer is
    per-character rules chained several deep.
  · NEXT PROTOTYPE, specified: unit-chain collapse. `BUILD_DISPATCH` already
    chases alternations frame-lessly and `OP_VSTR` already runs terminal-only
    value_str clones without a frame; the gap is a SEQUENCE clone whose single
    arm is one exactly-once ref with a transparent/pass-through fold. The
    sizing measurement is "what fraction of the 5,394 entries per parse are
    such pass-throughs?" — and unlike the model cut it needs no change to the
    generated class surface.
  · Recorded as do-not-re-run: micro-levers (~0% previously), model-count
    reduction (16% ceiling for a 46% cut, measured here), GC and
    operation-count growth (ruled out during the linearity work).
- **OPTIMIZATION — the lever is located** (`OPTIMIZATION.md` §7). Entry census
  over the real corpus: of 5,394 entries per parse, **1,396 (25.9%) are
  single-arm alternations over one exactly-once ruleref** — pass-throughs that
  cost a frame push, an item walk and a completion to hand back exactly what the
  callee produced. `_convert_dispatch` exists to make exactly these frame-less
  ("observationally identical to the frame it replaces") and they pass EVERY
  documented guard: checked per entry at runtime, 1,396 of 1,396 report
  "NOTHING — should have converted" (e.g. `body-line`).
  Why it is worth taking: §4's calibration says an 11% entry cut moved time 16%
  while a 46% MODEL cut moved it the same 16% — so a 26% entry cut plausibly
  beats the model route, and unlike it changes nothing about the generated class
  surface.
  **NOT established, deliberately: WHY they stayed BUILD_ALT.** The obvious
  hypothesis (OP_REF1 specialisation pre-empting the shape check) is WRONG —
  `optimize_program` already orders dispatch first and documents that exact
  reason. A reachability probe was inconclusive, not informative:
  `all_clones([program.start])` returned ONE clone here, so either the
  optimizer's set misses them or the probe misread `all_clones`'s contract.
  Next step is diagnostic: find what set `optimize_program` iterates for this
  grammar and whether `_convert_dispatch` is called on that clone at all. Two
  possible shapes (reachability gap vs a shape mismatch at pass time, most
  likely `_unit_ref_target`'s OP_REF-only test) — both small fixes, different
  fixes. No src touched.
- **DIAGNOSED (§8) — and it CORRECTS the previous entry.** Instrumented
  `_convert_dispatch` during a real compile: the pass sees these clones (164
  calls, 118 names), so the reachability hypothesis is dead. Of 21 BUILD_ALT
  clones at pass time, 9 converted and **12 declined for exactly two reasons:
  7 `attempt`, 5 `gated arm is OP_VSTR`**.
  · The OP_VSTR five ARE a real gap: `_inline_value_strs` runs before dispatch
    and `_unit_ref_target` accepts only OP_REF, so an optimization disqualifies
    a clone from a bigger one — the same hazard `optimize_program` documents
    for OP_REF1 but does not guard for OP_VSTR. Worth ~**52 entries (1%)**, not
    26%.
  · **MY EARLIER 26% READ WAS WRONG, and the reason is a method error worth
    keeping:** I checked the guards against each clone's FINAL state, where the
    arms read OP_REF1 — an op-code `_specialize_calls` produces AFTER the
    dispatch pass. At pass time they were OP_REF and declined on `attempt`, not
    on shape. A compile-time pass must be diagnosed AT pass time; reading the
    artefact afterwards shows the state three passes later.
  · STILL OPEN, and it is the engine owner's call: a single-arm attempt clone
    has no arm choice to try, and `_clone_shape` already says so in words — yet
    these seven carry a non-None attempt marker. Something classifies them
    multi-arm at spec time and single-arm at runtime (arm dropping in
    `compile_arms` is the suspect, NOT verified). If the marker is not earning
    anything at that point, 26% of entries collapse; if it carries loop
    licences independent of arm count, this lever is smaller than it looked and
    §4 needs another way to cash out. No src touched.
- **PROPOSAL.md written** — two post-flatten optimizer gaps, handed over for
  review. No src touched.
  · **§1 (the big one): attempt sub-clones never see the optimizer.**
    `flatten_clones` runs `optimize_program` over the shell set, THEN builds
    attempt entries via `_attempt_entries`/`_sub_clone` — so those sub-clones
    are created after the passes and are not in the set. 31 of them exist in
    the vyx program and they take **1,396 entries per parse, 25.9% of all
    5,394** (kv-pair 452, value 444, body-line 330, scope-item 144, bare-val
    26). Every one is BUILD_ALT, one arm, one exactly-once ref — the shape
    `_convert_dispatch` exists for. Needs `_unit_ref_target` to accept OP_REF1
    as well as OP_REF (a sub-clone shares its parent's already-specialised arm);
    that widening is a no-op for the main pass. RISK named: sub-clones are
    entered through the sub-run seam, and whether a frame-less chase composes
    with rollback is the first thing to establish.
  · **§2: `OP_VSTR` disqualifies a bigger optimization.** `_inline_value_strs`
    runs before dispatch and `_unit_ref_target` does not recognise OP_VSTR, so a
    single-arm alternation loses the conversion because it won an inlining —
    the same hazard the pass order already guards for OP_REF1. ~1%; a
    design-correctness fix, not a perf one. May be better fixed by ordering
    than by widening.
  · §3 records the model route as bounded (46% fewer models = 16%, and it costs
    an API change) so nobody re-opens it, and that interning is already
    effective (3,342 refs → 561 objects).
  · **§4 records a FAILED prototype as a warning:** applying `_convert_dispatch`
    post-hoc to the finished program corrupts it (a converted clone's selectors
    hold clone payloads where the driver expects a FlatArm). These passes are
    order-dependent and cannot be applied out of band — a real prototype must
    run inside `flatten_clones`, which is a src change this investigation was
    scoped out of. The proposal is therefore DIAGNOSED, NOT DEMONSTRATED, and
    says so; step one for any implementer is to build that prototype properly
    and measure before believing the sizing.
  · §5 lists what a reviewer should push on, including the weakest link: "16%
    is the floor for an entry cut" rests on ONE calibration point from a
    grammar-side rewrite that moved several things at once.
- **ITERATED — the prototype failed TWICE, and the second failure is the
  answer** (PROPOSAL.md §6). Built §1 properly in-pipeline (patch
  `_attempt_entries`, convert + mark each sub-clone at birth, widen
  `_unit_ref_target` to OP_REF1). Same crash as the out-of-band attempt, which
  rules out "wrong time" — so the cause is real. Reading `_enter`:
  **the dispatch chase runs BEFORE the attempt-entry substitution.** When
  `sole_admitted` picks a single admitted entry, `clone = sole` installs a
  different clone and execution falls through to the GENERIC selector loop,
  which finds a FlatClone where a FlatArm is expected. The converted sub's mode
  is correct and nothing looks at it again.
  So the real change is TWO-PART: (1) compile — optimize the sub-clones where
  they are created; (2) runtime — `_enter` must re-check specialisations after
  `clone = sole`. Part 2 is load-bearing and is why a compile-side prototype
  could not work. Suggested shape: make `_enter`'s head a small loop (chase,
  substitute, re-check) instead of three straight-line tests with exactly one
  ordering that works and no way to say so.
  Recommendation revised: **§2 (OP_VSTR, 1%) is the safe self-contained win,
  take it first**; §1 is worth doing but touches the hottest path in the engine
  and part 2 adds work to EVERY entry to save it on a quarter — a trade the §4
  calibration cannot predict, so measure before believing 26%.
- **PROPOSAL IS NOW AN ACTUAL PROPOSAL — prototyped, working, measured, suite
  green.** Working prototype at `subopt.py` (pytest plugin, both halves by
  monkeypatch; the two patched functions ARE the intended diff).
  · **vyx +7.1%, clone entries 5,394 → 3,727 (−31%).**
  · Correctness: **full suite 3,801 passed** under the prototype (parity
    differentials included); models **structurally identical** on all six bench
    grammars; round-trip holds everywhere.
  · Part 2 (the `_enter` head becoming a chase/substitute/re-check LOOP) is
    REQUIRED — part 1 alone crashes, measured twice. And it is **free**:
    interleaved A/B toggling only `_enter` gives −0.3% / +0.2% / −0.3% on
    json / abnf-meta / vyx. The "taxes every entry to help a quarter" risk is
    measured and does not exist.
  · Scope stated honestly: only grammars WITH attempt sub-clones benefit; vyx is
    the only one in the corpus (though it is the product grammar). And a 31%
    entry cut bought 7.1%, which CORRECTS OPTIMIZATION.md §4's "16% floor for an
    entry cut" — that figure came from a rewrite that moved entries, models and
    _run_leaf together and over-predicts a change that removes only a frame push
    and a completion.
  · §6 keeps the OP_VSTR gap explicitly OUT of the proposal: not prototyped,
    ~1%, and OP_VSTR's runtime semantics differ from OP_REF's. A lead, not a
    recommendation.
  · §7 gives the landing order: part 2 alone first (pure refactor, should be a
    no-op), then part 1 with the `_unit_ref_target` widening; gate on
    run_checks + full suite + parity, then re-run the per-grammar table.
- **LANDED** (`9e6b012` part 2, `a491c46` part 1), per PROPOSAL §7 exactly.
  **vyx 5.118 → 4.819 µs/char, clone entries 5,394 → 3,727.** Gates: run_checks
  0, suite **3,801 passed**, check_generated CLEAN, examples 0; models
  structurally identical on every bench grammar, round-trip holds.
  Two things the landing changed from the prototype, both forced by the repo's
  own gates rather than by taste:
  · Part 2's loop pushed `_enter` to 13 branches (cap 12). Extracted as
    `_settle()` — which is the better home anyway: the termination argument
    (FIRST-position edges, cycles are left recursion, refused at analysis time)
    now lives on the method it defends, as R2 asked.
  · `_convert_dispatch` → `convert_dispatch`. The layering test caught the
    private cross-module import immediately (1 failed, 3,800 passed) — a name
    shared across modules is public at its defining module.
  §7.5's doc updates went in WITH the landing, not deferred: `optimize_program`'s
  ordering note no longer claims the order protects the unit-ref shape check
  (it doesn't, now that OP_REF1 is accepted), and `_unit_ref_target` says why.
- REMAINING from this thread, unchanged: the OP_VSTR gap (~1%, unprototyped,
  PROPOSAL §6 — a lead, not a recommendation).
