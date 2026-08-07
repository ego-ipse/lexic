# bench — findings tally

The benchmark-gap mission's ledger. One entry per finding, newest last.
Account of record for what was measured, what was ruled out, and what is
merely suspected. `FINDINGS.md` holds the standing picture; this holds the
history so nothing is re-derived or re-run.

- **BOARD ESTABLISHED** (`--rounds 5`, all grammars, after `3dbe1c8`).
  lexic-pda LOSES in four of six rows against the Python field:
  vyx −1.83× and abnf-meta −1.59× (both to **parsimonious**, a PEG packrat),
  arithmetic −1.26× and csv −1.26× (both to **lark-lalr**). json is a tie
  (1% inside a 1.00% noise floor). gbnf-meta is a win by default — every rival
  refuses that corpus, so it means nothing.
  lexic-earley is the outlier: **12–30× its own PDA**, and it loses to
  lark-earley on arithmetic (1.45×) and csv (1.17×) while beating it on both
  metagrammars. 63.8 µs/char on arithmetic is the worst number lexic posts
  anywhere.
- RULED OUT AS A TARGET, deliberately: the antlr column (Java; its own row
  notes 4–8% of the timed region is CharStream construction). Optimising
  toward it would be optimising toward a different runtime.
- STANDING CAVEAT on every number here: the engines do not build the same
  thing — lexic returns a typed model the source is recoverable from, the
  rivals return generic trees, and nobody else gets semantic actions. The job
  is to measure how much of each gap that accounts for, not to assume it is
  all of it or none of it.
- TARGETS RANKED: (1) lexic-earley on arithmetic — worst absolute number and a
  same-algorithm peer is 1.45× faster, so the gap is not intrinsic;
  (2) vyx / abnf-meta vs parsimonious — largest PDA losses, both
  structure-dense, likely one cause; (3) arithmetic / csv vs lark-lalr —
  smallest gap and the most likely to be "we build more" rather than "we are
  slower", so price it before chasing it.
- **TARGET 1 PROFILED (lexic-earley, arithmetic, 63.8 µs/char) — the time is in
  the FOLD, not the parse.** Of 2.583s over 3 runs:
  · `fold.py:378 apply` cumtime **1.196s = 46%** of the whole run
  · `model.py:275 __new__` 42,456 calls, cumtime 0.764s (30%)
  · `model.py:324 _check_fields` cumtime 0.394s — **field VALIDATION**
  · `records.py:232 __new__` 82,431 calls, 0.322s
  · the Earley loop proper (`splits.py` ~0.19s, ambiguity 0.18s) is a MINORITY
  **The suspicion this raises, not yet confirmed:** `model.py`'s docstring says
  the trusted parse paths (`_from_parts` / `fast_construct`) bypass `__new__`
  and are unchecked — yet `__new__` and `_check_fields` are both hot here. If
  the Earley fold is not taking the fast-construct path while the PDA fold is,
  that would explain a large share of BOTH the 12–30× PDA/Earley gap and the
  lark-earley loss, and it is a fold-side fix rather than an engine one.
  NEXT: confirm by counting fast_construct vs __new__ on both routes over the
  same grammar. If confirmed, prototype the Earley fold taking the same
  licence.
- **CONFIRMED — the two routes construct models differently.** Counting
  `GrammarModel.__new__` over one grammar (arithmetic), same fold, same input:
  **PDA 0 calls. Earley 14,152.** The PDA fold builds through the fast-ctor
  licence entirely; the Earley fold pays validated construction for every model.
  That is a fold-side difference, not an engine one, and it was invisible in
  the bench because both routes are timed as whole parses.
- **BOUNDED (prototype: `_check_fields` stubbed, timing only — NOT a proposal,
  the validation is load-bearing for hand-construction).** Validation alone is
  **18.0% of the Earley parse on arithmetic, 17.6% on json, 7.5% on csv.**
  So it is a real share but NOT the whole 1.45× lark-earley gap: arithmetic
  60.7 → 49.8 µs/char unchecked, still well above lark-earley's 43.9.
  Reading: the fold is ~46% of the Earley run (previous entry), validation is
  ~18 points of that, and the rest is construction proper — `__new__` +
  `records.py.__new__` (82k calls). Removing validation alone does not win the
  row; taking the fast-ctor path (which skips both) might.
- OPEN, and the next prototype: why does the Earley fold not take the licence
  the PDA fold takes? If it is a missing `fast` on the RuleFold for this route
  rather than a semantic reason, the fix is small and the win is the whole
  construction share, not just validation's 18 points. If there IS a semantic
  reason (Earley can present children the fast ctor cannot trust), that reason
  is the finding and the route stays slow by design.
- **TARGET 1 CLOSED — the Earley fold declines the licence BY DESIGN, and the
  reason is written down.** `FastCtor`'s docstring (`parsing/fold.py:96`):
  *"Granted per rule by the compile seam when the model class provably needs no
  per-field validation; the PDA runtime then builds instances through `make`
  instead of the validated constructor. **The engine-side fold ignores it — the
  engine path stays the validated reference.**"* Confirmed by use: only
  `pda/runtime/build.py` reads `clone.fast`; the fold never does.
  So the 14,152 validated constructions are the point, not a defect. The Earley
  route is the **correctness oracle** the parity differentials check the PDA
  against — if both sides took the fast path, per-field validation would run
  nowhere and the gate would be comparing two unchecked builds. Speeding it up
  by taking the licence would delete the property the gate rests on.
  Also: validation is only 18 points of a 46% fold, and arithmetic unchecked is
  49.8 vs lark-earley's 43.9 — so even the unavailable win would not take that
  row. Two reasons to stop, not one.
- **STRATEGIC CONSEQUENCE, and it re-ranks the mission.** The bench's
  `lexic-earley` row measures the *reference* implementation, not the
  production path — the PDA is the default route and Earley runs only when it
  bails, which after this effort's work is rare (2 real ProbeForks in 3,801
  tests). Chasing lark-earley optimises a row no user's parse takes. **The rows
  that matter are the lexic-pda ones**, where lexic loses four of six:
  vyx −1.83× and abnf-meta −1.59× (parsimonious), arithmetic and csv −1.26×
  (lark-lalr). Target 2 is now target 1.
- **THE STANDING CAVEAT IS FALSE, MEASURED.** Stubbed all three model
  constructors (`build_fast`, `build_validated`, `build_vstr`) to return
  ``None`` and re-timed the PDA parse — recognition without the product:

  ```
  vyx        full 4.866  recognition 4.854   build = 0%   rival 2.773  LOSES
  abnf-meta  full 5.969  recognition 6.002   build = 0%   rival 3.913  LOSES
  arithmetic full 3.199  recognition 3.208   build = 0%   rival 2.684  LOSES
  csv        full 0.839  recognition 0.821   build = 2%   rival 0.727  LOSES
  json       full 1.967  recognition 1.951   build = 1%   rival 2.124  WINS
  ```

  **Model building is ~0% of the PDA parse.** Every deviation is inside noise.
  Consistent with the earlier census — interning already collapses 3,342 model
  references to 561 objects, so construction was already almost free.

  So "some of the gap is that lexic builds a typed model and the rivals build
  generic trees" — which `FINDINGS.md` §3 carries as a standing caveat and
  which I have repeated in every summary this mission — **is worth ~0% on the
  PDA route.** It is true of the *Earley* route (46% fold) and I generalised it
  without checking. Retracted.

  **The whole gap is RECOGNITION**: lexic's walk is slower than parsimonious's
  packrat and lark-lalr's table loop, and stripping the product does not close
  any of it. That is a harder problem than the one I thought I had, and it is
  the real one. `FINDINGS.md` §3 must be rewritten, not softened.
- Next: recognition is 1.56 clone entries per char (prior mission). The
  question is no longer "what do we build" but "why does one character cost
  more than one rule frame", and whether that is the grammar's shape (vyx's
  per-character lexical rules) or the engine's.
- **THE COST MODEL — recognition tracks CLONE ENTRIES, and the loss is
  entries/char × ns/entry.** Measured across all six:

  ```
  grammar      µs/char  entries/char  ns/entry   rival   ratio
  csv            0.854         0.228    3743      0.727  1.17x LOSES
  json           1.933         0.605    3193      2.124  0.91x WINS
  arithmetic     3.100         1.025    3024      2.684  1.15x LOSES
  vyx            4.912         1.077    4562      2.773  1.77x LOSES
  abnf-meta      5.929         1.451    4087      3.913  1.52x LOSES
  gbnf-meta      5.109         1.064    4802         —      —
  ```

  µs/char tracks entries/char closely — 0.228→0.854, 0.605→1.933, 1.025→3.100,
  1.451→5.929. **The one row lexic WINS (json) is the second-lowest
  entries/char.** The correlation is the finding.
  But ns/entry is NOT constant: 3,024 (arithmetic) to 4,802 (gbnf-meta), and
  vyx costs 4,562 against arithmetic's 3,024 for near-identical entries/char
  (1.077 vs 1.025). So there are TWO levers, and vyx is bad at both.
  **Caveat on ns/entry, stated because it is easy to over-read:** it is
  total ÷ entries, so it attributes ALL work to entries including terminal
  scanning that happens inside `_drive` without any entry. For csv (0.228
  entries/char) most of the parse is scanning between entries, which inflates
  its ns/entry. The figure is a ratio, not a per-entry cost.
- **TWO LEVERS, both open:**
  (a) **entries/char** — grammar shape. The dispatch-conversion landing already
      cut vyx's from 1.56 to 1.077, worth 5.118→4.815 µs/char.
  (b) **ns/entry** — why does a vyx entry cost 1.5× an arithmetic one at the
      same entries/char? Suspicion, unmeasured: attempt entries run whole
      sub-runs, and vyx is the attempt-heavy grammar. If so, the lever is the
      attempt seam, not the driver.
- NEXT: decompose ns/entry by entry KIND (plain frame push vs attempt sub-run
  vs gated selection) on vyx. That separates lever (b) into something
  actionable or kills it.
- **LEVER (b) LOCATED — the attempt seam is vyx's cost, and it is not close.**
  Decomposing `_enter` by entry kind (times are cumulative, so nested sub-run
  work is counted under the attempt that caused it — the attribution is the
  point, not the absolute ms):

  ```
  vyx        3543 entries, 41.51 ms inside _enter
     699 ×  48712 ns =  34.05 ms  82.0%  ATTEMPT (sub-runs)
    1426 ×   3823 ns =   5.45 ms  13.1%  dispatch chase
     209 ×   6450 ns =   1.35 ms   3.2%  leaf (frame-less)
    1209 ×    550 ns =   0.66 ms   1.6%  plain frame push

  arithmetic 4100 entries, 5.97 ms
    1537 ×   3112 ns =   4.78 ms  80.1%  dispatch chase
    2563 ×    463 ns =   1.19 ms  19.9%  plain frame push
  ```

  **An attempt entry costs 48.7 µs — 88× a plain frame push (550 ns) and 13× a
  dispatch chase.** 699 of 3,543 entries (20%) take 82% of the time.
  **arithmetic has ZERO attempt entries**, which explains the ns/entry spread
  from the previous entry exactly: 3,024 vs 4,562 is attempt density, not a
  mysterious per-entry constant. Lever (b) is real and it has one name.
- What an attempt entry does, for the next iteration: `sole_admitted` already
  short-circuits the single-admitted case without a sub-run, so the 699 that
  reach `attempt()` are the genuinely multi-admitted ones — each tries arms in
  order as rolled-back sub-runs, then AUDITS the remaining admitted arms for a
  second success (the ambiguity check), which is a further sub-run each.
  **Known dead end, do not retry:** `_attempt_run`'s own docstring records that
  memoising sub-runs was tried and measured ZERO hits — a sub-run's outcome
  depends on the enclosing continuation, so `(clone, pos)` is not a sound key.
  The live question is the AUDIT: it is a correctness property (two arms
  matching the same span is the ambiguity refusal), so the target is not
  removing it but establishing whether it can be decided without a second full
  sub-run.
- **THE AUDIT IS NOT THE LEVER — it is 9%.** Timing the attempt seam's parts on
  vyx (cumulative, so nesting is counted under the caller):

  ```
    2005 ×  25.6 µs =  51.28 ms   _attempt_run
     648 ×  55.8 µs =  36.18 ms   attempt
     572 ×   5.8 µs =   3.32 ms   _attempt_audit      ← 9% of attempt
  ```

  So last iteration's "live question" is answered and closed: the second-success
  audit costs 3.3 ms of 36.2 ms. Making it cheaper, even free, buys ~9% of 82%
  of vyx's entry time — a few percent of the row. Not worth the soundness risk
  of touching an ambiguity check.
- **THE REAL COST IS THE NUMBER OF SPECULATIVE SUB-RUNS.** 648 attempt decisions
  produce **2,005 `_attempt_run` calls — 3.1 speculative arm parses per
  decision**, at 25.6 µs each. The seam is doing three full speculative parses
  to settle one arm choice.
- **NEXT PROTOTYPE, and it has existing machinery to borrow.** `sole_admitted`
  filters candidate arms by first char plus a leading-terminal prefix match;
  when exactly one survives it skips the sub-runs entirely (that path is already
  taken and is why only 648 of the attempt entries reach `attempt()`). The
  question is whether a LONGER lookahead collapses more decisions to one
  survivor: the analysis already computes FIRST_k windows
  (`analysis/gates/kwindow.py`) and the runtime already matches them for loop
  and arm gates (`GATE_KWIN`, `kwin_selectors`) — none of that is wired into
  attempt admission.
  Measurement that sizes it, before any change: for each of the 648 decisions,
  count admitted entries under k=1 (today) against k=2/3/4. If a meaningful
  share collapses to one, the lever is admission, not the sub-run.
- **THE LEVER, SIZED — 83% of wasted speculative work dies within 4 characters.**
  Of vyx's 2,005 sub-runs, **784 (39%) FAIL and roll back**. Their failure depth
  (chars consumed before the failure, read off `PdaFail.pos` — which exists
  because this effort put it there):

  ```
  depth  1: 296   cumulative  37.8%
  depth  2:  66              46.2%
  depth  3:  74              55.6%
  depth  4: 218              83.4%   ← k=4 excludes five sixths of the waste
  depth  5:  32              87.5%
  depth  8:  26              96.9%
  depth 11:  14             100.0%   ← deepest failure in the whole parse
  ```

  **Size of the prize:** 784 × 25.6 µs ≈ 20 ms of vyx's ~41 ms of entry time.
  Excluding 83% of them ≈ **16.7 ms, ~40% of entry time**, without touching the
  audit, the driver, or anything the parity gate rests on. vyx at 4.9 µs/char
  would land near parsimonious's 2.773.
- **Why it should work, and why it is sound.** `sole_admitted` admits an arm on
  first char + leading-terminal prefix; an arm that survives that but dies at
  depth 4 was admitted on evidence one character deep. FIRST_k is an
  OVER-approximation of what an arm can begin with, so text matching no k-window
  of an arm proves the arm cannot match — excluding it is sound by construction,
  the same argument the existing `GATE_KWIN` loop and arm gates already run on.
  The machinery exists on both sides: `analysis/gates/kwindow.py` computes the
  windows, `_window_admits` matches them. Neither is wired to attempt admission.
- **NEXT: prototype it.** Compute FIRST_k (k=4) per attempt entry, filter
  candidates with it before the sub-runs, and measure. Watch for: the windows
  are computed per decision point today, not per attempt entry, so the analysis
  may need to be asked a question it does not currently answer — establish that
  before assuming the wiring is free.
- **THE PRIMITIVE EXISTS, AND THE BLOCKER I EXPECTED IS NOT ONE.**
  `KWindowFirst(rules, k).arm_prefixes(arm, k)` (`analysis/gates/kwindow.py`)
  returns the per-arm FIRST_k prefix set — exactly the per-attempt-entry
  question I thought the analysis could not answer.
  The wrapper `arm_gate()` only returns a result when the arms are SEPARABLE
  (pairwise disjoint), and attempt clones overlap by definition — that is why
  they are attempts. So `arm_gate` gives `None` for every one of them, and it
  looked like the analysis had nothing to offer.
  **But separability is a requirement for SELECTION, not for EXCLUSION.** I do
  not need the windows to pick an arm; I need them to prove an arm cannot
  match. Overlapping prefix sets still do that: if the text's k-window is in no
  window of arm A, A cannot match, whatever the other arms admit. The sound
  primitive is `arm_prefixes` directly, bypassing `arm_gate`'s separability
  test — which is a filter over a different question.
- **CAVEAT, unresolved:** `arm_gate`'s signature pins `max_k: int = 3` and its
  docstring says "the largest window to try (`≤ 3`)". The failure-depth data
  wants k=4 (83.4% cumulative); k=3 reaches only 55.6%. Whether the ≤3 bound is
  a cost ceiling on the solver or a correctness limit is NOT established — read
  `KWindowFirst` before assuming k=4 is available. If it is capped at 3, the
  lever is worth ~55% of the waste rather than ~83%, which is still ~11 ms of
  vyx's 41 ms.
- **NEXT (prototype, in this order):** (1) read `KWindowFirst` for the k bound;
  (2) compute `arm_prefixes` per attempt entry at the largest sound k;
  (3) filter candidates in `sole_admitted`'s position before any sub-run;
  (4) measure sub-run count and µs/char on vyx. Success criterion set in
  advance: sub-runs 2,005 → under 1,400, and vyx under 4.0 µs/char.
- **k=4 IS AVAILABLE — the ≤3 bound is a cost ceiling, not a correctness one.**
  `KWindowFirst(rules, k)` is constructed per window width with no cap in the
  class; `max_k: int = 3` is a parameter of the `arm_gate` SEARCH (how far to
  look for a separating k before giving up), and the solver memoises per
  `(rule, budget)`. So the 83.4%-at-depth-4 prize is reachable; k only costs
  compile time, which is memoised and paid once.
- **WHERE THE CHANGE HAS TO LIVE — a real obstacle, found by trying to write
  the prototype.** `arm_prefixes` takes a sequence of `IrItem`; the runtime
  holds `FlatArm`s, which are int-coded and carry no IrItems. So the filter
  CANNOT be computed at runtime from what the kernel has. The windows must be
  computed at COMPILE time, where the `IrAst` arms are still in scope, and
  carried on the attempt entries — exactly as `kwin_selectors` already carries
  them for gated arms.
  Concretely: the attempt entry tuple is `(chars, negated, prefix, sub)` and
  gains a windows field; `PdaCompiler` fills it where it builds the entries
  (the `IrAlternation` arms are in hand there); `sole_admitted` matches it with
  the existing `_window_admits`. Every piece exists; none of them is currently
  connected across that seam.
  **Consequence for scope:** this is not a runtime-only patch. It touches the
  clone compiler, the entry spec, the flat lowering and the admission leaf —
  four files, one seam. Worth it at ~40% of vyx's entry time, but it is not the
  one-line change the "machinery already exists" framing might suggest, and the
  next iteration should size the diff honestly before starting it.
- **CORRECTION TO THE SIZING — my "k=4 excludes 83%" was off by one.**
  Reasoning it through rather than reading the cumulative column off the table:
  an arm that FAILS at depth d had its first d characters ACCEPTED. A FIRST_k
  window describes what can begin the arm, so for k ≤ d the window MATCHES and
  the filter does NOT exclude it. **FIRST_k excludes exactly the arms whose
  failure depth is < k.** Re-reading the same data with the correct offset:

  ```
  k=2  excludes depth 1        296 of 784   37.8%
  k=3  excludes depth ≤2       362          46.2%
  k=4  excludes depth ≤3       436          55.6%
  k=5  excludes depth ≤4       654          83.4%
  ```

  So the prize is **k=4 → ~11 ms of vyx's 41 ms (~27%)**, and the 83% figure
  needs **k=5**, not k=4. Iteration 8 read the cumulative row at depth 4 and
  attributed it to k=4; the window has to be one wider than the failure it
  rules out.
  Revised expectation for the prototype: vyx 4.9 → roughly 4.0–4.3 µs/char at
  k=4, not the ~3.0 the earlier number implied. **The success criterion set in
  iteration 9 (under 4.0 µs/char) was set against the wrong sizing and is
  probably unreachable at k=4** — it stands as written, and if the prototype
  lands at 4.2 that is the lever working as actually sized, not a failure.
- SECOND-ORDER, unresolved and worth stating: failure depth is measured on the
  arms the seam actually tried. An arm excluded by a window is never tried, so
  the excluded set is not guaranteed to be exactly the shallow-failing set —
  the estimate assumes the window is TIGHT at the failure point, and a loose
  window (FIRST_k over-approximates) excludes fewer. So the numbers above are
  an UPPER bound on what k buys, not a prediction. Only the prototype settles
  it.
- **THE WINDOWS ARE COMPACT — one failure mode ruled out, the decisive one not.**
  vyx has **13 attempt rules / 49 arms**. FIRST_k prefix-set sizes:

  ```
  k=2: median 2 windows per arm, max 12
  k=3: median 3,               max 28
  k=4: median 4,               max 77   — none over 1000
  ```

  So the solver neither explodes combinatorially nor poisons the sets with the
  `UNK` cycle marker at k=4. That kills the "the windows will be enormous or
  useless" failure mode, and it means the compile-time cost is trivial.
  **But set size is NOT coverage, and this does not settle tightness.** A prefix
  set is a set of ≤k-length CharSet TUPLES — a single window `(ANY, ANY, ANY,
  ANY)` has size 1 and excludes nothing. Four narrow windows discriminate;
  four wide ones do not. What has been measured is that the sets are small,
  not that they are narrow.
  The decisive question — does the window at the failure position actually
  exclude the arm that fails there — still needs the prototype, and no proxy
  measured so far substitutes for it.
- **STATE FOR THE NEXT ITERATION (the prototype is one full unit of work, and
  the recipe is now complete):**
  1. `GrammarAnalysis(tables.instance_grammar).taxonomy.attempts` → 13 rules.
  2. `KWindowFirst(rules, 4).arm_prefixes(list(arm), 4)` per arm — verified to
     work, compact output.
  3. Map arm → flat attempt entry by ORDER: entries are built from
     `clone.selectors` in attempt order (`AttemptSpec.order`). **This mapping
     is the one unverified step and the place a prototype will silently
     mis-attribute — check it explicitly before trusting a number.**
  4. Patch `kernel.sole_admitted` (bound by name IN kernel.py — patching
     `admission.sole_admitted` does NOT take, learned in iteration 8) to apply
     `_window_admits` before returning.
  5. Measure sub-run count and µs/char. Criterion from iteration 9 stands as
     written, with iteration 11's correction: ~4.0–4.3 is the honest target at
     k=4.
- **THE MAPPING IS CLEAN — the recipe's one unverified step is now verified.**
  For every attempt clone on vyx, the gated-arm count EQUALS the authored
  `rule.body` count, and the stored `AttemptSpec.order` has the same length:

  ```
  body-line     authored 10  gated 10  order 10
  value          7   7   7        bare-val      3  3  3
  scope-item     3   3   3        scope-scalar  3  3  3
  pipe-bare      3   3   3        kv-pair       2  2  2
  0 of the attempt clones have a gated count != authored count
  ```

  `compile_arms` drops arms whose FIRST is empty, which would have shifted the
  index mapping silently — that was the risk. It does not fire here. So
  **entry i ↔ `rule.body[order[i]]`** holds directly, and the prototype can
  map windows onto flat entries by position without a lookup table.
  (Seven attempt CLONES against thirteen attempt RULES in the taxonomy — the
  gap is the single-gated-arm rules, which carry `attempt_follow is None` and
  run as ordinary clones. Consistent with `_clone_shape`, and it means the
  filter only ever has to cover these seven.)
- **PROTOTYPE STATUS: fully de-risked, ready to execute.** Every step of the
  iteration-12 recipe is now verified except the measurement itself: the
  primitive works and is compact (it 12), k=4 is sound and cheap (it 10), the
  seam location is known (it 10), the patch target is known (it 8), the sizing
  is corrected (it 11), and the mapping holds (this one). What remains is one
  full context budget of writing and measuring — not investigation.
- **PROTOTYPE BUILT AND RUN — the lever cashes out in sub-runs and LOSES in
  time.** `bench/kproto.py`, FIRST_4 windows attached to all 31 attempt entries,
  filtering before any speculative sub-run, on vyx:

  ```
  baseline         4.821 µs/char   sub-runs 2005
  FIRST_4 filter   6.119 µs/char   sub-runs 1635      -26.9% SLOWER
  round-trip True  ·  2,354 candidate exclusions
  ```

  **The sizing was right; the economics are not.** 370 sub-runs eliminated
  against iteration 11's prediction of ~436 — the model held. But the parse got
  **27% slower**, because the filter runs far more often than the sub-runs it
  saves: `_window_admits` is a Python loop over windows × positions, executed
  per candidate at every attempt decision (2,354 exclusions plus every
  non-exclusion), to avoid 370 sub-runs at 25.6 µs each. The check is cheap per
  call and ruinous in aggregate.
  This is the failure mode iteration 12 could not rule out by proxy — not
  "windows too loose" (they excluded plenty) but "the exclusion costs more than
  the exclusion saves". Only running it could show that.
- **SALVAGE CANDIDATE, untested:** the prototype filters EVERY admitted
  candidate. The cheap filters (`admits` + `prefix_admits`) already resolve most
  decisions to a single survivor, and those never needed a window at all — the
  window is only decisive when ≥2 candidates survive the cheap pass. Restructure
  to run the cheap pass first, and consult windows ONLY on the multi-survivor
  remainder. That is a strictly smaller number of window checks for the same
  370 sub-runs saved. Whether it is small enough to turn −27% positive is
  unknown and is the next measurement.
- **HONEST STATUS at iteration 14: no optimization delivered.** One lever
  located, sized, de-risked and now prototyped — and the prototype says it loses
  as designed. That is a result, but it is not a win, and the mission's goal
  (beat every parser on every grammar) is not closer than it was at iteration 1.
- **SALVAGE TESTED — also loses (−27.7%), and its premise was wrong.**
  Restructured to run the cheap pass first and consult windows only on the
  multi-survivor remainder:

  ```
  baseline        4.660 µs/char  sub-runs 2005
  FIRST_4 filter  5.951 µs/char  sub-runs 1635      -27.7%
  settled by the cheap pass 2321 · settled BY the window 1210 · exclusions 2354
  ```

  The premise was that the multi-survivor remainder is small. It is not: 2,321
  decisions settle cheaply, but enough reach the window path to run 2,354
  exclusions, and the window genuinely settles **1,210** decisions the cheap
  pass could not. The filter is doing real work and still loses.
- **WHY IT CANNOT WIN AS BUILT — the arithmetic is decisive.** ~4,675 window
  evaluations to avoid 370 sub-runs. Saving is 370 × 25.6 µs ≈ 9.5 ms; the
  filter adds ≈ 13.5 ms, i.e. **~2.9 µs per window check**. That is the right
  order for a Python loop over ≤4 windows × 4 positions with a set membership
  each. **The check is not too loose or too rare — it is too EXPENSIVE per
  call, and no restructuring of when to call it fixes that.**
  For this approach to pay, the admission test itself would have to be compiled
  to something cheap — int-coded, first-char-indexed, or a trie — the way
  terminals already are in the flat program. `_window_admits` as a Python
  interpreter loop cannot be called thousands of times per parse to save
  hundreds of microseconds.
- **DIRECTION THIS RULES OUT:** any attempt-seam optimization whose test runs
  per candidate per decision in Python. The seam's decisions outnumber its
  sub-runs by roughly 6:1 on vyx, so a per-decision test must be ~an order of
  magnitude cheaper than a sub-run to break even, and interpreted set
  membership is not.
- **THE COST CONCENTRATES, AND THEN THE LAST DIRECTION CLOSES.**
  Attempt cost by rule on vyx (648 decisions, 32.04 ms):

  ```
   102 × 164.1 µs = 16.73 ms  52.2%  body-line   (10 arms)
   226 ×  28.3 µs =  6.39 ms  19.9%  kv-pair
   222 ×  23.7 µs =  5.26 ms  16.4%  value       (7 arms)
    72 ×  46.2 µs =  3.33 ms  10.4%  scope-item
  ```

  `body-line` alone is **52%** of attempt cost. Concentration is good news — it
  suggests one targeted fix. And the shape of that fix looked right: convert it
  from an ATTEMPT (speculative, per-candidate) to a k-window GATED SELECTION
  (one check per decision, picks the arm) — which is `arm_gate`'s existing job
  and would have avoided the per-candidate cost that killed the last prototype.
  **It does not separate.** Tested directly, bypassing `arm_gate`'s max_k=3:

  ```
  body-line  10 arms   k=2..6: collide at every k
  kv-pair     2 arms   k=2..6: collide
  value       7 arms   k=2..6: collide
  scope-item  3 arms   k=2..6: collide
  ```

  So raising the search ceiling converts nothing. The attempt classification is
  CORRECT: these arms genuinely require unbounded lookahead to tell apart, which
  is why they are attempted rather than gated.
- **THE ARCHITECTURAL ANSWER to "why does parsimonious beat lexic on vyx" — and
  it is not a tuning gap.** parsimonious is a PEG packrat: ordered choice means
  first-match-wins, and its memo is `(rule, position) → result`, sound because
  the result does not depend on what follows. lexic cannot use that memo —
  `_attempt_run`'s docstring records it was tried and measured zero hits,
  because a sub-run's outcome DOES depend on the enclosing continuation.
  It depends on the continuation because **lexic is deciding something
  parsimonious never decides.** PEG takes the first matching arm and is under no
  obligation to ask whether a later arm also matches; lexic refuses ambiguity,
  so it must check — that is the audit, and it is why the composition matters.
  **The 1.83× is largely the price of ambiguity refusal on a grammar whose arms
  are not separable by any bounded lookahead.** Closing it means changing what
  lexic promises, not how fast it computes it — which is a ruling, not an
  optimization, and it belongs to the user.
- **NEW TARGET OPENED: csv is the purest inner-loop comparison on the board.**
  Isolating `_chase_dispatch`'s SELF time (previous per-kind figures were
  cumulative and included the target's whole subtree — that inflated the chase
  to 3.1 µs and misled me):

  ```
  arithmetic  parse 15.52 ms   1537 chases × 255 ns = 0.39 ms   2.5% of parse
  csv         parse 12.89 ms      0 chases                      0.0%
  ```

  A dispatch chase is **255 ns**, not 3.1 µs — cheap, and 2.5% of arithmetic.
  **csv has ZERO attempt entries and ZERO dispatch chases.** No speculation, no
  ambiguity machinery, no attempt seam — its 12.89 ms is the driver's terminal
  matching plus 2,860 plain frame pushes (0.228 entries/char, the lowest on the
  board). It is lexic's inner loop with everything else stripped away, losing
  1.26× to lark-lalr.
  That makes csv the RIGHT next target and the one that generalises: every
  grammar pays the driver, whereas the attempt seam (now closed as irreducible)
  is vyx's problem alone. It also means the csv gap CANNOT be explained by the
  ambiguity-refusal argument that explains vyx — nothing is being refused there.
- **CORRECTION, recorded because it changed a conclusion:** iteration 6's
  per-kind table attributed 80% of arithmetic's entry time to "dispatch chase".
  That was cumulative time, so it was really the chased target's entire subtree.
  Self time is 2.5%. Anywhere that table was read as "chases are expensive", it
  was read wrong — and I wrote it that way.
- NEXT: decompose csv's 12.89 ms. Entries are 0.228/char and chases are zero, so
  the time is in `_drive`'s per-item terminal path (OP_CC1 / OP_LIT1 / OP_VSTR)
  and the frame push/complete cycle. Measure the split before proposing
  anything — that is the loop lark-lalr beats with a separate lexer.
- **cProfile IS UNRELIABLE AT THIS CALL DENSITY — a methodological finding that
  invalidates a reading I nearly took.** Profiling csv: 414,741 calls in 0.163 s
  profiled, against ~12.9 ms unprofiled — **a 12.6× inflation**. Per-call
  instrumentation overhead dominates, so the profile's proportions skew hard
  toward high-call-count functions.
  Concretely it showed model construction (`_from_parts` 20,910 calls,
  `_fast_fields` / `build_fast` 14,300 each) at ~29% of csv's run. **Iteration 4
  measured the same thing by stubbing the constructors and got 2%.** The stub
  A/B is the trustworthy number — it changes the program and times the whole
  thing, rather than taxing every call. The profile is measuring its own
  overhead on the hottest, smallest functions.
  This matches the repo's standing perf guidance (in-process interleaved A/B;
  cProfile misleads) and I nearly reasoned from the profile anyway. Where
  cProfile HAS been useful this mission is locating a hotspot by NAME
  (`values_agree` at ×63 call growth, the Earley fold at 46%) — the shape, not
  the share.
- **SO WHERE csv's TIME GOES IS STILL OPEN, and the tools so far cannot say.**
  Construction is 2% (stub A/B). Chases are 0. Entries are 0.228/char, the
  lowest on the board. That leaves `_drive`'s per-item terminal path — but it is
  ONE function, so cProfile cannot decompose it and a stub cannot remove it.
  Measuring inside it needs a different technique: counting op-code executions
  per kind (compile-time reachable from the FlatArms), or line-level timing.
  **Next: count OP_CC1 / OP_LIT1 / OP_VSTR / OP_REF1 executions on csv and
  divide the 12.9 ms by op.** That gives a per-op cost to compare against what
  a table-driven LALR loop pays per character.
- **csv's TIME IS PER-CHARACTER SCANNING IN PYTHON — located at last.**
  Item-slot executions on csv: **0.35 per character** (2,639 `vstr`, 1,540
  `ref1`, 221 `ref` — 4,400 slots for 12,539 chars). So the driver dispatches
  roughly one item per three characters; item dispatch is NOT the cost.
  Each `vstr` item then scans a whole run of characters inside `vstr_once`, and
  a char-class quantifier loop advances **one character per Python iteration**
  with a set membership each. At 1.03 µs/char and 0.35 items/char, the time is
  in those scanning loops, not in the frame/item machinery around them.
- **THE STRUCTURAL COMPARISON, and it is a fair fight lexic is losing on tooling
  not on design.** lark-lalr wins csv (0.727 vs 0.917) because it lexes with
  `re` — character scanning in C. lexic scans in a Python `while` loop. For csv
  the parse is essentially lexing (0.228 entries/char, zero attempts, zero
  chases), so the row is close to a direct Python-loop vs C-regex comparison.
  **This is the first gap this mission has found that is neither irreducible nor
  a promise lexic makes** — vyx's is the price of refusing ambiguity, the Earley
  fold's is the oracle by design, but this one is just an implementation choice.
- **OPTIMIZATION CANDIDATE, untested and the strongest one found:** replace the
  per-character Python loops for char-class and value_str runs with a C-level
  scan — a precompiled `re` pattern per CharSet, or `str.translate`-based
  span-finding. Every grammar pays this loop, unlike the attempt seam (vyx only).
  Wants pricing before belief: build a microbenchmark of `while` + set membership
  against `re.match(...).end()` over the corpus's actual run lengths FIRST — if
  the runs are short (2-3 chars), regex call overhead may exceed the loop it
  replaces, which is exactly how the FIRST_k prototype died.
