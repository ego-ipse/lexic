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
