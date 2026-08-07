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
