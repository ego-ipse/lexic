# atlas — work tally (context-recovery ledger)

Forked from `../facets/` at commit 80ede43; the facets-era ledger is
`../facets/TALLY.md` and ends with a pointer here. Newest last.

- atlas/ forked from facets (leaf + serve intact). THINKING.md written:
  topological answers for resize (degrade-by-deriving-less), the 3D rule
  graph (z = derivation distance, name-addressed co-selection), attachments
  as ports (products multiply facets, transpile is a peer edge), the meta
  ring (focus along a lineage edge pointing at yourself), the refusal facet,
  and the iteration ladder (refusal → engines → seams → graph → ports → ring).
- Perf question answered by measurement: PDA fused route 313,593 chars/s vs
  metagrammar Earley+resolver route 1,974 chars/s (159×); resolver invoked
  exactly ONCE on vyx — the cost is the route (ambiguous self-grammar model
  product → probe-fork → Earley + ambiguity audit), not resolution. Lexic-side
  fix: de-ambiguate the GBNF self-grammar's model product (noise attribution).
- Refusal surface measured: UnsupportedConstructError carries words only — no
  position, no expected set. Lexic gap worth a ruling (readout-shaped,
  additive). Recorded in atlas/THINKING.md §5.
- RULED (user, 2026-08-07): both engines as observation — PDA default, Earley
  loaded in the background, visualization switchable once Earley finishes;
  inversion when the PDA fails. No route flag enters the parse API (the
  no-PDA-opt-out ruling stands). Recorded as THINKING.md §6b; inserted into
  the iteration ladder as step 2.
- ITERATION 1 (refusal frontier) IMPLEMENTED in atlas/: PdaFail spells its
  position in prose ("no arm at N") — no attribute carries it (lexic gap
  refined: the position EXISTS, it lives in words). Server reads it via the
  engine floor (PdaKernel + cg.pda_tables() + cg.fold) on the PDA route;
  responds `refuse <pos>\n<words>`; Earley-route fixtures honestly report -1.
  Leaf draws the frontier: red caret + underline at the char, cursor jumps
  there, banner = engine words + frontier statement; ?break=OFF query for
  deterministic demos. Census: long frontier == exact corruption offset
  (7,884/7,884); meta -1 as ruled. Screenshot-verified at ?break=5000: red
  mark at char 5,000, spine of the last good reading at the frontier,
  generation unchanged. Server on :8903 stopped at wrap.
- Edit flow reworked on user verdict (edit box: Enter broken by a
  selectionchange race nulling the snapshot; and a UX killer as a concept).
  The document facet is now an editable text plane (contenteditable
  plaintext): typing marks the session dirty, derived facets go stale (dimmed,
  labelled "last good reading"), Ctrl+Enter re-reads WITHOUT saving, Ctrl+S
  saves AND compiles (write to the document's own file; held-with-reason for
  ground-truth corpus), Esc reverts. Refusal draws the frontier caret inside
  the typed candidate text and scrolls to it. Gutter click sets the cursor
  (dblclick returned to native word-select). Census extended: identity save →
  'saved' on long, 'held' on meta/vyx. Screenshot-verified via ?break=5000:
  § visible in the editable text, red caret beside it, stale facets, contract
  in the status strip. node --check now used as the leaf syntax gate.
- RUNG 2, FIRST HALF: background other-route run per read (daemon thread,
  generation-tagged, stale results discarded); GET /routes; leaf polls and
  renders the strip in the derivation header. PDA-route: explicit Earley via
  normalize(lift_optional_nullables(codegen)) — THE instance-grammar recipe
  (bare normalize refuses on unnormalised quantifiers, and alone reports
  spurious ambiguity); parity verdict drawn (holds: structural == plus
  to_text). Resolver-route: PdaKernel probe-fork position drawn as
  where-the-fast-road-stops (meta 202, vyx 3,306). Census extended; caught my
  own formulation assumption: \x01 mid-document is LEGAL in metagrammar
  comments (cmchar admits controls) — the "garbage" parsed; corruption now
  placed per route. VISION.md + SPEC.md written at the radical root; HANDOVER
  updated (cold start = VISION → SPEC → HANDOVER → TALLY → THINKING).
- MEASURED why vyx costs ~5s: compile is 0.03s (memo-warm); the Earley
  fallback route is SUPERLINEAR on this grammar — 4,281 chars in 0.37s
  (11.5K chars/s) vs 8,750 chars in 3.79s (2.3K chars/s): ×2 input ≈ ×10
  time, ≈ n^3.2. Not a constant-factor gap; chart density compounds. The
  PDA probe-forks at 3,306 (attempt-loop gate undecidable) and the fallback
  is whole-document Earley — the fork does not island. Sharpens the lexic
  asks: decidable self-grammar → PDA route (~30ms), or island the
  undecidable span so only it pays Earley.
- CORRECTED (user caught it: "3306 is the start of the grammar!"): the
  probe-fork is ONE CHAR INTO THE FIRST RULENAME in both fixtures (vyx 3306 =
  'p'▶'acket ::='; json 202 = 'J'▶'SON-text ::='). The PDA consumed the whole
  comment preamble fine — the noise loop is NOT the fork site; the
  undecidable gate is rulename's namechar* (an identifier-tail loop). By
  inspection that loop looks k=1 separable (namechar set vs the n?/"::=" that
  follows — disjoint), yet the compiled attempt-loop gate declares both
  viable — a precise, reproducible engine question. My earlier causal story
  conflated two findings: the route-forcing fork (namechar*, first rulename)
  and the model-product ambiguity (resolver, invoked once, site unknown) are
  SEPARATE. If this one gate becomes decidable the PDA may carry the whole
  metagrammar — the 160x win may hinge on one loop.
- "CAN WE DO IT?" — investigation banked for a fresh session. SOLID: (1)
  ten-char repro on the real metagrammar — `ab ::= "x"\n` probe-forks at pos
  1 (second name char); `a ::= "x"\n` rides the PDA. (2) The forking site is
  gate_take's GATE_ATTEMPT (terminal attempt loop, flatten.py): fork iff char
  ∈ take-set ∩ stored soft-continuation set. (3) FALSIFIED: synthetic
  shapes do NOT reproduce — bare tail loop, ws/noise+literal follows, two
  occurrences with disjoint follows, and even one occurrence with a
  letter-follow all ride the PDA — so the continuation-set pollution is
  specific to the metagrammar's authored formulation (suspects: the
  atom/-nonname machinery, token terminals, semantic flags), NOT generic
  FOLLOW-union conservatism. NEXT SESSION, first move: compile
  GBNF_FLAVOUR.grammar, find the namechar* clone's gate spec (compiler/specs
  vocabulary), print gate[0]/gate[1] char sets, and trace which letters
  entered the continuation and from which occurrence. Fix follows diagnosis;
  full run_checks + parity differentials gate any engine change.
- **GATE INVESTIGATION CLOSED — root cause found, fix measured (not applied).**
  The forking gate is the ONLY attempt-gated item in the whole metagrammar:
  `rulename`'s `namechar*` loop (`AttemptGate(FIRST=[-0-9A-Z_a-z],
  follow=…letters…)`; FIRST ∩ follow = letters + `_`, and NOT digits/`-` —
  confirmed by prediction: `a1 ::= "x"` and `a- ::= "x"` ride the PDA,
  `ab ::= "x"` forks). Chain, each link measured:
  (1) `relax_non_semantic` (compile/pipeline/passes.py) rewrites every
  top-level ref to a `semantic=False` rule to `min=0`. GBNF's `n` is
  non-semantic, so the authored `seq-rest ::= n item` becomes `n? item` and
  `rules-rest ::= n rule` becomes `n? rule` — deleting the maximal-munch
  discipline gbnf.py's own design note declares load-bearing ("adjacent items
  need real noise unless the next atom is non-name (seq-rest), inter-rule
  noise is REQUIRED (rules-rest)").
  (2) The codegen grammar is therefore GENUINELY ambiguous: `a ::= bc` =
  one ruleref or two. Verified — Earley refuses it without a resolver, while
  `ab ::= "x"` (LHS, unambiguous) parses fine.
  (3) Because letters genuinely follow `rulename` at the atom site, the
  namechar* loop cannot be gated → attempt licence filed with the RULE-LEVEL
  union FOLLOW (`beyond_at` → `scope.tail`), and an attemptable rule gets ONE
  canonical clone (`_spec_ruleref`, memo identity) → the union licence applies
  at EVERY site, including the LHS where the continuation is only `n? "::="`.
  So the pos-1 fork is a SPURIOUS probe caused by real ambiguity elsewhere —
  exactly what `beyond_at`'s docstring predicts ("per-SITE precision is the
  honest narrowing"). The two findings banked yesterday as separate are one
  causal chain, and the earlier falsification was right for the right reason:
  no generic conservatism, the metagrammar's authored `n` is what differs.
  COUNTERFACTUAL (monkeypatched, nothing in src touched): with the relaxation
  narrowed to nullable noise rules only, all TEN ground-truth grammars ride
  the PDA with NO resolver and round-trip intact — vyx 4.817s → 0.028s (172×),
  json.gbnf 0.522s → 0.007s. Suite: relax fully off = 8 failed / 3766 passed;
  nullable-only = 3 failed / 3771 passed (two pin the pass's own contract with
  a non-nullable `ws ::= " "+`; one is c.gbnf's pinned clone count, 69 → 75).
  Cost of the narrowing, exact: a NON-nullable noise rule in a mandatory slot
  becomes genuinely mandatory (`root ::= "a" ws "b"`, `ws ::= [ \t]+`: `"ab"`
  accepted today, refused after). c.gbnf is the only corpus grammar with a
  non-nullable `ws`; its own fixtures still pass. FIX NOT APPLIED — awaiting
  the user's ruling on which narrowing (see HANDOVER lexic asks).
- Investigation written up and made reproducible: `../gate/` carries
  `FINDING.md` (the account, four proposed solutions with their costs, the
  recommendation), `variants.py` (the three relaxation bodies, patched in
  place — `src/` never written), five standalone probes under `probes/`
  (repro, gate_dump, shapes, corpus, cost — each takes a variant name), the
  two pytest plugins, and `run_all.sh` (every probe × every variant, then the
  suite under the candidate). Sharper than yesterday's account on one point:
  the pass ALSO relaxes `n ::= nunit+` to `nunit*`, so the noise rule itself
  goes nullable — two independent breakages, not one.
- **FIX LANDED (solution A), all gates green.** External review endorsed A and
  added four amendments, all taken: land with `nullable_names` exported from
  `lexic.parsing` rather than blocking on an `ir/grammar/` move; re-state the
  pinned tests to assert BOTH halves; update CLAUDE.md + wiki (the Directives
  line documented the old behaviour verbatim); keep D unbundled but rank the
  islanding half as constitutional. Shipped: `relax_non_semantic` narrowed to
  `ast.non_semantic & nullable_names(ast.rules)` (solved on the INCOMING
  grammar — the trap is that relaxing `n ::= nunit+` would make `n` nullable
  and license itself); `nullable_names` exported; five `ws` fixtures made
  genuinely nullable (they were passing for the wrong reason); three pass tests
  where one stood, including the load-bearing "a required noise ref keeps its
  bound" that nothing pinned before; c.gbnf clone count 69 → 75; CLAUDE.md,
  `.wiki/lexic/codegen.md`, a `decisions.md` entry ("A codegen pass may not
  overrule an authored quantifier") and a `log.md` entry. Gates: run_checks
  exit 0, suite 3776 passed / 8 skipped, parity + property 141 passed,
  check_generated CLEAN, run_examples exit 0. Measured after landing, same
  run: all ten ground-truth grammars ride the PDA with no resolver, vyx
  **4.451s → 0.029s**. The probe suite stays honest — `gate/variants.py` gained
  `unconditional` (the pre-fix body) so the bug is still reproducible, and
  `relaxnull.py` became `relaxold.py`.
- Atlas caught up to the fix (its own census found it): meta/vyx no longer
  force the `first` resolver — every fixture is PDA-routed now, so every
  frontier is measured and every derivation header shows a real parity verdict
  (Earley agrees on all three). The census's corruption offset moved onto the
  subject as `corrupt_at` with its reason attached (a control char mid-file is
  LEGAL inside a GBNF comment, so metagrammar-read documents corrupt at 0);
  it had been keyed on `resolve`, which stopped meaning anything. All three
  censuses green. Consequence worth noting for rung 2's second half: there is
  no longer any fixture that DEMONSTRATES the inversion — the instrument can
  still display one, but nothing in the corpus produces it.
- Kitty-graphics inline export landed: atlas/inline.py (zero-dep emitter,
  PNG → chunked APC stream, f=100/a=T first chunk, m-only continuations,
  ≤4096/chunk — framing and exact payload round-trip verified byte-level) and
  atlas/shot.sh (one gesture: serve fixture → headless shot at a ?query state
  → inline). `inline.py frame.png > frame.term` freezes a cat-able terminal
  artifact — the terminal-native peer of the HTML export target. Static by
  design: the artifact half, not the instrument. Visual confirmation needs a
  kitty-graphics terminal (ghostty/kitty/wezterm) — the user's gate.
- VISUAL GATE PASSED (user, in ghostty): `cat frame.term` paints. The session
  itself now runs in ghostty — but MEASURED: the agent cannot paint inline
  through its own Bash tool; the harness captures stdout (54.6KB → persisted
  file, ESC bytes stripped in the preview), so APC never reaches the tty.
  Frames-in-conversation therefore work only for USER-initiated commands
  (their shell, or possibly the `!` prefix). The .term artifact is exactly
  the right seam for the agent side: the agent writes files; the human cats
  them wherever kitty graphics is spoken.
- SOLUTION D — premise measured before building, and the answer is NOT NOW.
  New probes: `gate/forkcount.py` (suite-wide ProbeFork/PdaFail tally by raise
  site) and `gate/probes/scaling.py` (the fallback's cost as a vyx packet
  grows). Findings: only NINE ProbeForks survive in the whole 3,776-test suite,
  all of them vyx.gbnf-as-instance-grammar (pipe-lists, dict-defs) at
  runtime/kernel/kernel.py:341/:563 — a different site from the metagrammar's
  flat GATE_ATTEMPT; no other corpus grammar forks at all. And the cost there
  is a FLAT ×7-8 that scales LINEARLY (32 lines/495c: 0.024s vs 0.003s) — the
  ~n^3.2 blowup was specific to the metagrammar's chart density, not a property
  of the fallback. So D's prize is a bounded constant factor on one grammar's
  constructs, against A's 163× superlinear. Recorded as FINDING.md §12 with the
  recommendation: defer; if built, do the ISLANDING half alone first (the
  machinery exists and it does not touch the one-canonical-clone decision,
  which per-site licences would reverse — and that decision is itself measured
  at 60% of sub-runs). Also learned the hard way: a counting subclass of
  PdaFail breaks `except PdaFail` for ProbeFork (sibling types) — 51 tests
  failed until the plugin patched `__init__` on the existing classes instead.
- NEW SESSION (context kept). Option A found landed in the working tree by the
  gate agent (src + tests + CLAUDE.md + atlas/serve.py adapted — theirs to
  commit): vyx reads in 0.07-0.54s, all fixtures PDA-routed, all frontiers
  measurable. TUI SLICE 1 BUILT: atlas/tui.py — the interactive display in
  cells, stdlib-only, third client of the unchanged wire. Document facet as
  styled cells (span shading = background attributes: the weld is free on a
  grid), spine pane, masthead, status readout; mouse hover co-selects, click
  sets the cursor, wheel scrolls, Space plays, arrows step, q quits; spawns
  the server if absent. Census green first run (doc drawn, spine bounded,
  caret styled, hover co-selected); verified by TEXT SCREENSHOT — a TUI frame
  ANSI-stripped is readable by the agent, a native visual channel neither tk
  nor the browser had. UNTESTED BY ME (no tty in harness): live mouse/key
  parsing — the user's hands are the gate. Slice 2: editing (grid editor +
  kitty keyboard protocol for Ctrl+Enter), selection + OSC 52, chart as a
  kitty-graphics placement pane.
- D-half-2 (islanding) DESIGNED, not implemented — `gate/D-ISLANDING.md`. The
  feasibility read overturned the "it is just wiring" assumption and then
  closed it better: islanding a RUNTIME fork is not obviously sound (a
  compile-time island has a decidable boundary; a ProbeFork IS an undecidable
  boundary), but `island_parse` already carries the guard — `policy.follow`
  bails when a shorter completion end could compose, and `island_follow`'s own
  note records that a rule-level (superset) follow can only cause a spurious
  bail, never a wrong commit. So the change is safe by construction and
  degrades to today's fallback on every uncertain outcome. Mechanism: on
  ProbeFork climb to the innermost NAMED-rule frame, roll back to its F_START
  (the `_attempt_run` floor-watermark primitive), island that rule, splice into
  the parent sink; on any island refusal re-raise and fall back as today. One
  thing must be built: PdaTables keeps FOLLOW only for declared islands and
  needs it for every rule (the analysis already has it). Risks logged: the
  climb target, PROBE_DEPTH forks (not boundary questions — keep falling back),
  reduce-path parity, and the real one — a failed island attempt is pure loss
  on top of a fallback, so with the prize at only ×8 the instrument must show
  island-succeeded vs island-attempted before this counts as a win. Stopped
  before touching the kernel's hot loop: it wants to land as one reviewed
  change, gated on the parity differentials.
- TUI SLICE 2 — read-side parity with the browser: THE READER pane (rule
  co-lighting from hover/selection, click-a-rule → violet marks everywhere,
  auto-scroll to the lit rule), THE DERIVATION band (overview density in
  shade glyphs + depth lanes of the visible window, overview scrubs), drag
  selection → smallest covering occurrence, routes strip polled live,
  fidelity verdict in the masthead. Facets degrade by deriving less (reader
  hides <140 cols, chart <34 rows; 'c' toggles). Census grew to nine checks,
  green on vyx and long; verified by a faithful text screenshot that
  RECONSTRUCTS absolute positioning into a character grid (the census's
  earlier reader check searched stripped output where rows don't survive —
  fixed to assert the def line itself). Layout fix: the chart band now starts
  clear of the reader pane (it was drawn under it, burying the overview's
  left quarter and skewing the scrub mapping). Remaining for slice 3: the
  write side — grid editor, kitty-keyboard Ctrl+Enter/Ctrl+S, refusal
  frontier in cells.
- D-half-2 HIT RATE MEASURED (`gate/probes/island_trial.py`, no src change — a
  PdaKernel subclass trials the island at each fork and re-raises): 3 of 5
  settle, and the split is by construct — pipe-lists island cleanly, dict-defs
  always bail through `policy.follow` ("arm choice spans two ends (3,4) and the
  shorter could compose"), which is the guard working, not a defect. So the
  mechanism is sound on live subjects and the open question is purely economic:
  a bail pays the island attempt ON TOP of the fallback, so dict-defs get
  strictly slower. Sample bound stated: 8 forks, one grammar, inputs of tens of
  chars; a dict-entry-heavy packet at size is the adversarial case and nothing
  in the corpus exercises it. Remaining work listed as D-ISLANDING.md §7 — and
  a NEW prerequisite surfaced: neither FlatClone nor RuleFold carries a rule
  name and `flatten_program` discards the CloneKey→FlatClone map, so the probe
  had to recover names via compute_binding, which the kernel cannot do. Probe
  bug worth remembering: dedup by `id(exception)` false-dedups (ids are reused
  after GC) — mark the object instead.
- TUI SLICE 3 — the write side in cells, and the renderings CONVERGE (user
  caught the divergence). Chart semantics now match the browser: lanes follow
  the cursor's viewport, not the doc scroll. Edit mode ('i'): buffer editing
  with caret (insert/backspace/delete/arrows/click), stale facets with the
  last-good-reading note, Ctrl+R re-reads / Ctrl+S saves-and-compiles (the
  terminal's honest stand-ins; Ctrl+Enter needs the kitty keyboard protocol —
  deferred), Esc reverts (lone-Esc settled by the select timeout). Refusal
  keeps the buffer, drops the RED frontier caret on the exact char, moves the
  caret there. Bugs found by the census this round: the uv-run spawn leak
  (killing the wrapper orphans the server — fixed: venv-python spawn,
  new session, process-group kill, fixture-verified reuse that REFUSES a
  mismatched port), frontier cell lost to the caret (precedence swapped), the
  reader check asserting hover's rule while auto-scroll follows selection's
  (now asserts what render_reader promises). Census: sixteen checks per
  fixture, write side driven through the same byte path the terminal uses;
  green on long and vyx. REMAINING structural divergence, named: two leaves
  carry duplicated hand-authored presentation policy — the drift pressure the
  user observed; the eventual seam is policy-as-data over the wire
  (arrangement as a session value, THINKING §1/§4 direction).
- RULED (user: "the fair compromise for now"): one instrument, one policy,
  many surfaces. Browser = flagship (text + scoped 3D + windows + GPU);
  windows = pinned facets only (pane cannot overlap, window can); 3D = the
  rule-graph facet, z = derivation distance, browser only, flat in the TUI;
  TUI = field instrument, pins land as panes; presentation policy moves into
  the wire AFTER pinning + 3D exist (build twice, then the rule); native/GPU
  stays watched. THINKING §7 + ladder rewritten (3 pinning → 4 rule graph →
  5 policy → 6 panes → 7 ports → 8 ring).
- RUNG 3 (pinning) LANDED in the browser leaf: windows exist, as the ruled
  exception only. `p` pins the selection (or hover); cap 3 with the refusal
  in words ("pin only for simultaneity"); windows are movable (header drag),
  resizable (native CSS resize), z-raise on press, closable — and they
  OVERLAP, which is what makes them windows and not panes. Each pin carries
  its occurrence's address (rule · span · depth), its real-text snippet
  (selectable), the field, AND the defining grammar rule's own lines —
  cross-subject deixis inside the window. Hovering a pin co-selects its
  occurrence across every facet; clicking selects it. After a re-read, pins
  from an older generation mark themselves STALE (dimmed, "the document has
  moved on — re-pin or close") instead of dangling silently. ?pin=OFF,OFF
  query for deterministic shots. Screenshot-verified: two overlapping
  windows, occlusion real, pinned 2 of 3 in the masthead, routes strip
  showing PDA 0.53s / Earley 0.54s / parity holds. Pins are leaf-local state
  for now — rung 5 (policy into the wire) makes them session values.
- FABLE REVIEW of D-ISLANDING taken (its §8): endorsed the design, four notes.
  Note 3 (run the economics BEFORE the kernel splice, at production packet
  size) executed as `gate/probes/economics.py` — and it turned up something
  much bigger than D.
- **THE PDA IS QUADRATIC ON PIPE-HEAVY VYX PACKETS** (`gate/PROBE-QUADRATIC.md`).
  No fork, no fallback, no resolver — the PREDICTIVE runtime succeeding, and
  ×4 input → ×16 time: 191c 0.020s / 719c 0.294s / 2,832c 4.632s / 11,281c
  **73.4s**. Cause pinned: `_probe` runs one side of a boundary TO END OF INPUT
  on a copied stack, once per boundary — probe count grows linearly (34/130/514)
  and 92% of wall clock is inside probes. Linear probes × linear cost = n².
  NOT A REGRESSION and not mine: A/B via a sitecustomize-injected
  `unconditional` variant gives 4.635s pre-fix vs 4.632s post-fix, and
  `tools.benchmark.bench --only gbnf-meta` lexic-pda 5.508 pre vs 5.471 post
  µs/char — inside the bench's own 2.80% noise floor, and the wrong way for a
  regression. (This also answers the user's "gbnf meta seems to have regressed"
  note: measured, it did not.)
- D's economics settled as a side effect, and its subject narrowed: dict-heavy
  islanding costs 0.1% of the parse at size (not the 33% a 135-char toy showed)
  so the bail case IS affordable; but pipe-heavy packets do not fork at all —
  the §6 pipe forks were at `@start value`, parsing a bare value, not inside a
  packet. D stays sound with affordable economics; it is just no longer the most
  valuable thing in this area.
- THREE LIVE-DRIVE BUGS (user), fixed and screenshot-verified on the
  short-document repro the user suggested (long fixture edited down to 24
  chars over the wire): (1) `p` fell through to contenteditable when the
  selection focused the document (the check sat after the focus guard) —
  pin is now Ctrl+P everywhere (print suppressed), bare p kept when focus
  is outside; (2) glyph metrics were tab-sized — the probe carried class
  .code whose min-width:100% resolves against the viewport for an
  absolute body child (1720px/40 ≈ 43px per glyph); the probe now copies
  the document's computed font with no layout classes, re-measured each
  boot; (3) the chart on a tiny document collapsed to a 5px-pitch sliver
  with lanes stretched to fill — pitch now adapts (small doc fills the
  width, capped 12px; large doc keeps the 5px window), lane height capped
  at 22px, chart viewport clamped into the document on every draw and
  reset on re-read. The short-doc state is a good standing fixture: edit
  the doc down over the wire, then look.
- "Make it linear?" — one route killed by measurement, one route specified.
  KILLED: the cheap shortcut (skip both probes when `_beyond_class` says
  `_ADMITS`, on the theory that optional-only viability means a split, which
  the split rule settles). `gate/verdictcensus.py` over the whole suite:
  3,586 ADMITS_HARD→TAKE, 239 ADMITS→TAKE, and **4 ADMITS→FORKED** — genuine
  forks, so the shortcut would commit what the engine refuses. The boundary
  class is not a sufficient statistic for the verdict. OPEN AND SPECIFIED:
  lockstep probing with convergence detection — drive both sides together,
  stop when one dies (forced, as today), when both reach an identical
  (pos, stack signature) (the stack IS the continuation, so identical state at
  identical position ⇒ identical future ⇒ verdict reduces to values accumulated
  before convergence), or when a step budget runs out (fall back to today's
  run-to-EOF, which makes correctness unregressable by construction). Sides
  reconverge within one element on pipe-lists → O(1) per boundary → linear.
  Needs a step-wise/bounded `_drive`, a cheap stack signature, and the
  value-comparison equivalence argued. Also banked: STOP_FORCED occurs ZERO
  times in 3,829 verdicts — the stop-probe's only known subject (gbnf-meta
  terminator theft) may have been removed by the relaxation fix, so dropping it
  would halve the constant; weak evidence, wants a grammar-level argument
  before anyone deletes a soundness check.
- Fable review notes 1 and 2 adopted in D-ISLANDING.md (note 3 was executed
  earlier as probes/economics.py; note 4 was priority, now superseded by the
  probe quadratic). Note 1: §1 gains the second half of the soundness argument
  — the follow guard covers differing EXTENTS, the island's own ambiguity gate
  covers EQUAL extents with different values, so nothing is left to a silent
  pick. Note 2: §7 item 2 no longer hedges "either a name slot or the shells
  map" — it recommends the `FlatClone.name` slot, because the probe's
  compute_binding route is runtime reaching into compile's binding view and the
  kernel must not inherit that inversion; the pinned-specs churn is stated as a
  cost, not an objection.
- THE PIN GESTURE, third time right (user: bare p dead when the document has
  focus — which is almost always — and Ctrl+P is every browser's print). The
  gesture is now DRAWN, not typed: select text → a `⌖ pin` chip appears at
  the selection → click pins. Ctrl+P kept as intercepted secondary; bare p
  kept outside document focus; pinning with no target now SPEAKS ("nothing
  to pin — select text, or hover an occurrence first"). Three real bugs
  found en route, each screenshot-diagnosed: (a) the autoplay `else` had
  migrated through patch insertions until it attached to `if (q.has('pin'))`
  — deterministic states animated and scroll events ate the chip; boot now
  autoplays only with NO query params; (b) `addEventListener('scroll',
  hideChip)` passed the Event object as hideChip's `force` parameter —
  truthy — force-hiding the sticky chip on the render's own follow-scroll;
  (c) the ?sel chip placed itself pre-scroll and unclamped, landing
  off-viewport. Chip placement is one geometry path (glyph arithmetic) used
  by both the live selection and the deterministic ?sel state.
- `gate/PLAN.md` written — the ordering argument over everything left open,
  self-contained for a cold start: (1) scope the quadratic cheaply, incl. the
  STOP_FORCED reachability question that could halve it before anyone optimises
  it; (2) lockstep convergence in `_fork_verdict`, behind the budget escape so
  worst case is today's answer; (3) re-measure; (4) FlatClone.name; (5) refusal
  position on the record; (6) D-half-2 only if (3) still shows it paying;
  deferred: D-half-1 and the nullable_names move. Two calls left to the user and
  named as such: the effort split (items 1-3/6 are lexic engine work this
  ergonomics effort merely surfaced — they want their own directory and gate),
  and whether atlas rung 2 preempts the lot (if so the order is 4 → 5 → rung 2
  and the quadratic parks as a filed finding). PLAN.md also carries the
  instrument table so none of this gets re-derived, and the sitecustomize A/B
  recipe. HANDOVER's NEXT SESSION block and the gate/ row now point at it.
- Pin resize cap (user): max-width:460px was meant as a birth size but
  native CSS resize honors it as a ceiling — replaced with an explicit
  birth width (360px) and no maximum; resize is now unbounded above the
  minimum in both axes.
- Pin round three (user): (1) adding a pin no longer resizes the others —
  renderPins now RECONCILES by id (create missing, update stale marks in
  place, remove closed) instead of rebuilding the layer, so hand-set inline
  sizes and body scroll survive; (2) birth width is measured — the snippet's
  longest line via canvas measureText in the pin's own font, clamped
  [280px, 62vw], so pinned text does not wrap when the viewport allows;
  (3) THE CAP IS GONE by user ruling ("let the people have fun") — "pin
  only for simultaneity" survives in THINKING as advice, not enforcement;
  cascade staggers modulo 8 so a pile of pins stays on screen. Screenshot:
  five overlapping pins, the wide rule window unwrapped on one line.
- **`gate/` SPLIT OUT to `../../260807-pda-linearity/`** (user's call, and this
  plan's own recommendation): the engine line — the relaxation fix, the PDA
  quadratic, solution D, the provenance asks — had outgrown an ergonomics
  effort. Every `gate/...` path in the entries above resolves there now; that
  effort carries its own HANDOVER and TALLY, and its `PLAN.md` is the order of
  work. Nothing moved in `src/`. **This ledger continues to own atlas only** —
  the live line here is rung 2's remaining half (the two engine clocks), and
  the two items the engine effort holds for atlas are the refusal position on
  the record (kills atlas's regex-over-prose) and `FlatClone.name`, both ranked
  first in that plan regardless of the split.
- COLLISION LOG: mid-flight, the engine agent executed the effort split
  itself (260807-pda-linearity/, gate/ emptied into it — my duplicate dir
  deleted unborn) AND landed items 4+5 in src under the user's override:
  FlatClone carries its rule name; PdaFail carries pos. Atlas cashed item 5
  immediately: frontier() now reads the attribute; the regex-over-prose is
  deleted. One live src collision observed (errors.py mid-keystroke syntax
  error — the expected-set landing); sequenced around it, no harm.
- RUNG 4 (browser half) LANDED: the 3D rule-graph facet. Server emits
  #EDGES (IrRuleRef walk over the reader AST — 127 edges for the
  metagrammar) and #DEPTHS (BFS derivation distance from the start rule;
  census asserts edges>0 and start depth 0). The reader facet gains a
  text⇄graph toggle ('g' or the header button; ?graph=1 for shots): rule
  chips as real DOM text, canvas edges underneath, manual 3D projection
  with orbit-by-drag, auto-fit to the pane each frame (grammar-size- and
  orbit-independent), depth cues via scale/z-index/near-class. Default view
  looks DOWN the derivation axis so depth descends the portrait pane —
  grammar at top, leaves at the bottom. Co-selection is name-addressed and
  bidirectional: chip hover/click ⇄ violet marking across document, chart,
  readout (drawUnder/drawChart now mark cur.rule OR graphHover). Browser
  scene parser generalized to consume unknown sections safely. Remaining
  half of rung 4: the same facet flat in the TUI.
- LANDINGS CASHED + THREE USER ITEMS: (1) items 4+5 fully landed engine-side —
  retype now reads the public Refusal readout off the caught exception
  directly (pos + "while reading <rule>" + expected/none-of set when
  populated; no second kernel run; frontier() was already rewritten by the
  engine agent to the same surface). (2) 'g' did nothing because it never
  existed: the earlier keyboard patches anchored on an `} else if` shape the
  atlas onKey does not have — str.replace silently no-opped and the heredocs
  printed ok regardless. ALL leaf patches now assert their anchors and print
  per-replace confirmations. p / Ctrl+P / g / [ ] installed on the real
  onKey. (3) graph ergonomics for the user's held feedback: wheel ZOOM
  (per-view, 0.35..5, multiplies the auto-fit), and the graph POPS OUT as a
  pinned window (⧉ window button / ?gpin=1) — multi-view refactor: each view
  carries its own orbit+zoom, shares the one layout and the one co-selection;
  closing the window drops its view; ResizeObserver redraws on window
  resize. Plus [ ]-keyed derivation speed (×0.25..×16, shown in status).
- USER'S GRAPH-AND-TEMPO BATCH, all seven landed: (1) transport BUTTONS in
  the derivation header (− ‹ ▶ › + with live speed word) and the speed floor
  dropped to ×1/512 — slow enough to watch char-by-char as a teaching
  device; ‹ › step exactly one character. (2) The spine wheel-zooms
  (0.6–2.4× font scale). (3) The overview is now also the document's
  minimap: scrubbing it scrolls the text in sync. (4) Rule lighting flows
  from the graph too: hotRule() unifies graph-chip hover with span hover, so
  hovering a chip lights the reader text (when visible), the document, and
  the chart — same address, four facets. (5a) json's start rule connected:
  nodes are now built from the server's name universe (#DEPTHS keys — AST
  canonical names) instead of reader-text spellings, with case-insensitive
  ruleDef() bridging reader lines. (5b) orbit jank fixed: the auto-fit
  lerps (0.22/frame) instead of snapping as bounds degenerate at shallow
  angles. (5c) FOCUS mode (◉ button / ?focus=1): with a rule selected, the
  graph fades everything but its direct parents + full descendant subtree —
  DOM-verified 84 of 90 faded for rulename; spatial-distribution
  experiments remain open for the user's continued critique.
- INCIDENT, recorded for the discipline: the first 14-patch round CRASHED on
  its 15th assert and never wrote — all fourteen "applied" prints were
  in-memory; a follow-up round then landed litRules calling helpers that
  did not exist. Recovery: re-applied atomically, then verified ON DISK
  (grep for function markers) and IN THE DOM (chip-class census) before
  claiming anything. New rule: after every patch round, verify the artifact,
  not the patch log.
- SECOND FEEDBACK ROUND on tempo/zoom/graph: (1) transport relocated to the
  status strip, beside the position readout — playback is global, not the
  derivation facet's furniture. (2) Zoom semantics RULED and implemented:
  text fields zoom with Ctrl+scroll (document+reader share the code-plane
  zoom — LH went dynamic, CSS vars scale, glyph metrics re-measure and the
  canvas welds re-size on every step; spine keeps its own Ctrl+scroll);
  non-text fields zoom with plain scroll (graph as before; the derivation
  chart NEW — wheel scales the lane window's chars-per-pixel, 0.25–8×).
  (5b, the real fix) "explodes off screen" was a CAMERA pole, not a fit
  pole: the perspective divisor f−z+420 could approach zero or flip
  negative behind the camera at some orbits, detonating one node's
  projection and with it the fit bounds — divisor now clamped ≥220: no
  pole, no mirror, mathematically bounded. (5d) the hover-zoom ghost was
  the fit lerp converging 22% per hover-triggered render — smoothing now
  applies only during an active drag; all other draws snap to the fitted
  target.
- Graph chips floated over pinned windows (user): the chips' per-depth
  z-indexes (up to ~1200) competed globally because #graphWrap was not a
  stacking context — z-index: 0 on the wrap scopes depth-ordering locally
  and puts the whole graph layer beneath the windows (pins z≥20 win).
  Pinned-graph windows were already scoped by their own .pin z-index.
- RULED: the graph asks move into rung 5 (layout tunables as policy sliders;
  graph.view switchable depth3d/flat/arcs) and post-5 (the railroad as its
  own iteration, per-rule diagrams in pin windows, facet kind reserved in
  the schema). Rung 5 scope inscribed as THINKING §8, itemized; ladder
  renumbered with DONE marks. Nothing blocks rung 5: zzz-only (no src
  contention with the engine lane), no lexic asks outstanding, TUI flat
  design known. Accepted limitation, named: session policy dies with the
  server process (persistence is not rung 5).
- RUNG 5 LANDED, to review point: presentation policy is session state.
  Server: policy dict on the session, #POLICY in the scene, GET/POST /policy
  (line-oriented, value '-' deletes); census asserts round-trip. Browser is
  an interpreter: boot applies speed/zooms/shares/reader-mode/graph
  camera+tunables/PINS (pins survive reload — the felt gap closed); every
  presentation gesture posts its delta (speed via setSpeed, all three zooms
  debounced, setGraph mode, pin add/close/drag/resize via ResizeObserver,
  facet camera on orbit-end). Seam resize landed as arrange.* — draggable
  facet borders (reader/right columns + chart/spine row) writing shares.
  THE GRAPH ASKS: tunables panel (depth/ring/flat/label sliders → policy),
  graph.view switch button cycling depth3d/flat/arcs — flat = levels as
  columns, no camera; arcs = rules in SOURCE ORDER, forward references
  arcing above, backward below, recursion drawn as self-loop rings, labels
  collapsing to dots except start/hot/marked. Verified: policy POSTed over
  the wire BEFORE page load → browser boots into arcs + wide reader + ×1/4
  speed with zero query params. TUI RE-BASE (the acceptance test): parses
  #POLICY, obeys speed + arrange.reader + reader.mode — the FLAT RULE GRAPH
  IN CELLS (rung 4's remaining half) is just the TUI's interpretation of
  graph.view; census grew three policy checks, nineteen green. One policy,
  two media, proven. NOT yet: browser /policy polling (cross-leaf live
  sync), pin gen-staleness across restarts, railroad (rung 6).

## Round: rung-5 review feedback (seven items) — 2026-08-07

The user's review of rung 5, item by item:

1. **Seams need pixel-hunting** → grip widened to 10px with a hover cursor
   affordance on both axes.
1b. **Facet max size** → share limits widened to `reader/right [0.06, 0.86]`,
   `top [0.12, 0.92]` — near-fullscreen graph is now reachable.
2. **Only the label slider worked in flat/arcs** → `gFlat`/`gArc` layouts had
   constants baked in; `gTune.levelstep/ringscale/flatten` now feed both
   (levelstep = column pitch, ringscale = row spread, flatten = arc lift).
2b. **Sliders dead in 3D** → the orbit pointerdown swallowed them
   (`preventDefault` on everything); events from `#gtune` are now ignored by
   the orbit handler.
2c. **Sliders out of style** → `#gtune` restyled into the register:
   translucent panel (opaque on hover), custom range track/thumb in cool/dim.
2d. **Flat/arcs unhelpful** → two causes. Auto-fit crushed the layout below
   readability (labels piling) — fit now floors at `k ≥ 0.8` for flat/arcs
   and pan explores what doesn't fit. And the untouched camera framed the
   sparse middle of the layout — until the user pans/zooms, flat/arcs now
   frame the start rule's edge (`v.touched` latch; screenshot-verified
   /tmp/flat3.png).
2e. **No pan anywhere** → every view pans: drag pans flat/arcs, Shift+drag
   pans 3D (plain drag still orbits), wheel zoom is cursor-anchored
   (`pan = c - (c - pan) * factor`). Pan persists: `graph.camera` grew to
   5 tokens (`yaw pitch zoom panx pany`) and graph-pin values to 9; both
   parse the old shorter forms.
2f. **Cycling button won't scale to view #4** → replaced by a styled
   `<select id="gview">` — direct travel, one row, grows by option.

Verification: `node --check` clean; screenshots /tmp/flat_tuned.png (exposed
the crush), /tmp/flat2.png (floor fixed scale), /tmp/flat3.png (start-edge
framing); policy round-trip exercised over the wire on the vyx fixture
(port 8933) with `reader.mode graph, graph.view flat, levelstep 200,
ringscale 1.3`.

Trap paid again this round: a 15-patch batch died on an anchor whose indent
(4 spaces) didn't match the file (2 spaces) — crash-before-write, nothing
landed, all fifteen "applied" prints were in-memory. The assert-every-anchor
+ verify-artifact-on-disk rule caught it; re-run landed all fifteen
(`v.pan` ×7 verified on disk).

## Round: view-true sliders + independent pin views — 2026-08-07

The user's two items on the previous round:

1. **The flat slider is useless in flat mode — sliders should change with the
   view** → the tune panel is now per-view (`TUNE_PANEL` map): depth3d shows
   depth/ring/flat/label; flat shows cols/rows/label; arcs shows
   pitch/lift/label. Same four tunables underneath — the panel shows only the
   ones the active layout reads, named for what they do there. Rows toggle by
   inline `display` (the `hidden` attribute loses to the CSS `display: grid`
   — caught on the first screenshot).
2. **Pin windows' view independent of the main one, plus a text view** →
   every graph view resolves its mode through `viewMode(v)`: pins carry
   `p.mode`, the facet follows `graph.view`. Each pin header grew its own
   `<select>` (depth 3d / flat / arcs / text); `text` swaps the canvas for
   the reader's grammar text as real selectable DOM. Mode persists as the
   graph-pin value's 10th token (`view`), legacy 9-token values parse as
   depth3d. Header drag ignores the select; drag semantics (pan vs orbit)
   follow the pin's own mode, not the facet's.

Deferred by the user's own sequencing: sliding the reader share to minimum
and then sliding the derivation sweeps the document **under** — to be
addressed when facets become movable, not before.

Verification: /tmp/pinmodes2.png — main facet flat, pin 1 in text (grammar
text visible, scrollbars live), pin 2 in depth3d, tune panel showing
cols/rows/label only; both pins built FROM policy at boot, so mode
persistence is the same screenshot. Second display-fallback bug in the same
frame: `.gtext`'s inline `''` fell back to the CSS `display:none` — both
fixed with explicit inline display. SPEC §2 policy keys updated (camera 5
tokens, pin graph 10 tokens — was two rounds stale).

## Round: rung 6 — the railroad — 2026-08-07

The seam split follows the house rule. The instrument walks the rule's own
body (`IrAlternation → IrSequence → IrItem(atom, quantifier)`, plus
`IrNot`/`IrAlphabet` wrappers) and ships neutral indented lines over
`GET /rail?rule=` — `<depth> <kind> [payload]`, kinds
alt/seq/many/ref/lit/class/not/alpha/nil/other, single-child containers
collapsed server-side, `other <Type>` named rather than silent. No lexic
name crosses the wire; the leaf owns every pixel.

The leaf renderer (~230 lines): recursive measure (`w/h/cy` per node, entry
line always at cy) then draw — sequence rides the line, alternation splits
into bezier branches, `many` draws the bypass arch (lo=0) and/or the loop
arch (hi≠1) with a `lo..hi` count label when bounded above 1, wrappers get a
dashed enclosure (¬ in red for negation, ⟨encoding⟩ for alphabet-bound
atoms). Terminal registers: refs cool rectangles (clickable — opening THAT
rule's railroad), literals warm rounded, classes violet with labels
truncated at 30 chars. Entry/exit stubs with dot terminals. Windows
auto-size to the measured diagram, fit-scale on resize, hit-testing in
diagram units through the scale transform.

Gestures: `▤ rail` in the reader header pops the marked rule's railroad
(start rule when nothing is marked); refs click through; `?rail=a,b`
deep-links. Policy: `pin.<id> rail <rule> x y w h`; the rail cache is
static per session because the reader grammar never changes across document
re-reads — only documents re-read, the grammar is the ground truth.

Verification: census gains ok_rail (well-formed lines for the start rule,
None for an unknown rule) — meta/long/vyx all exit 0, TUI census untouched
and green. Screenshots: /tmp/rail1.png (rule/item/alternation/cc-first —
sequence, optional bypass, zero-or-more, alternation splits),
/tmp/rail2.png (namechar/lplain violet classes, token-not literal+ref),
/tmp/rail3.png (?rail=grammar,quantifier deep link — the four-arm
quantifier split). The `not`/`alpha` draw paths are code-symmetric with the
verified shapes but no metagrammar rule exercises them visually — noted,
not hidden.

SPEC §2 updated (/rail wire, pin.rail value, deep link); THINKING ladder
rung 6 struck. Rung-5 leftovers still open: browser /policy polling for
cross-leaf sync, pin gen-staleness across restarts.

## Round: rails as a view of its own + the chip gesture + the abnf example — 2026-08-07

The user's three items:

1. **More examples, file loading** → fixture `abnf`: the ABNF metagrammar
   (76 rules) reading `json.abnf` — the second flavour through the same
   pipeline, census-gated like the others (parses via PDA in 0.04s, parity
   holds, rails well-formed). And the file pair: `serve.py <grammar> <doc>
   [port]` compiles any grammar file and reads any document — smoke-tested
   with json.gbnf + the long fixture. `RULE_LINE` widened to the three
   flavour rule-head spellings (`::=`, `=`, `=/`) — the abnf reader went
   from 0 addressable rules to 76.
2. **Rails as a first-class view** → `graph.view rails` (and per-pin
   `rails`): every rule as a railroad, stacked in AST order, chip-labeled,
   pan/zoom like the other views, untouched camera frames the top-left.
   One wire read: `GET /rails` ships all rules' structural lines; cached
   for the session (the reader grammar never changes across re-reads).
   Refs inside any diagram click through to a rail pin. Tune panel gains
   the rails row set (gap/label).
3. **The chip is the gesture** → the `▤ rail` header button is GONE.
   Clicking a rule in the reader text or a rule chip in any graph view
   raises `▤ rail` beside the pointer — the same gesture shape as the text
   pin chip. Violet register, hides on scroll/elsewhere-click.

Two bugs found by the round's own verification:

- **Boot-order: chips never built under policy boot.** `boot()` runs
  `applyPolicy()` → `setGraph` → `buildGraph` whose chip loop iterates
  `gViews` — which was EMPTY because `wireGraph()` ran after boot. Zero
  chips in the DOM on every policy-driven boot (and boot-time
  `graph.camera` silently skipped). Discriminated against the `?graph`
  param path (chips appear), fixed by registering the facet view before
  boot. flat/arcs re-verified by DOM grep.
- **Microtask storm hung the page.** While rails loaded, every draw did
  `fetchRails().then(drawGraph)`; the guarded early-return resolves
  immediately → drawGraph → draw → fetch… a tight microtask loop that
  starved the event loop so the fetch itself never completed —
  chrome-headless hung past 100s. The redraw moved INSIDE fetchRails
  (fires once, when the rails arrive); guarded calls schedule nothing.

Also paid again: a patch script with asserts but NO write call — two
"applied" prints, nothing on disk; and one rep() probe that would have
clobbered its anchor had the script written. The discipline holds: verify
on disk after every batch (`grep -c` before/after).

Verification: /tmp/rails2.png (meta rails, chips labeling every rule),
/tmp/rails_abnf.png (the ABNF metagrammar as rails — rulelist/filler/
defined's `=`/`=/` arms), DOM greps for chips-in-flat and #railchip
presence. All censuses exit 0: meta, long, vyx, abnf, TUI. The chip
gesture's click path is wired and DOM-verified but not headless-clickable —
user-side is the real test. SPEC §1/§2 updated.

## Round: the railroad becomes a navigable space — 2026-08-07

The user's review of the rails round, all three taken:

1. **Scroll, not pan** → in the rails view the wheel scrolls (`pan.y`),
   Ctrl+wheel keeps the cursor-anchored zoom — the same split every text
   plane already uses. Drag still pans.
2. **Refs light like their chips** → hovering a ref box co-selects its
   rule: `graphHover` drives the same light everywhere (chip hot, reader
   line, spans). The ref box itself draws hot (warm fill, field text) when
   its rule is hovered anywhere, violet when marked. Rail pins joined the
   per-frame render (`drawGraph` head) so cross-lighting reaches inside
   windows — hover a chip, the refs in every open railroad light up.
3. **Click descends, the chip forks** → in the rails view a ref click
   scrolls to that rule's diagram (`railsGoto`), marks it, and raises the
   rail chip (pinning stays one more click, never automatic). In a rail
   window a ref click re-targets the window in place; `↩` pops the
   navigation history; `▲ n` in the header lists the rule's referrers
   (from #EDGES) — ascent is a CHOICE because a rule may be referenced
   many times, which is exactly why it's a select and not a button.
   Window drag guards extended so the new header controls survive.

Verification: /tmp/rails_lit.png — one frame showing `?rule=rule` lighting
the `rule` refs violet across the rails view (rules-rest's track) in the
same register as chip/spans, and the alternation rail pin carrying `▲ 2`
(its two referrers). Wheel-scroll, click-descend and history are wired and
code-verified; headless can't drive them — the user's hands are the test.
`node --check` clean; no server change this round.

## Round: per-mode cameras — 2026-08-07

The user's catch: switching graph views carried the old view's coordinates
— scroll to the bottom of rails, switch to depth 3d, and you're panned
into the middle of nowhere. The camera was one shared state across modes.

Fix: `switchViewMode(v, from, to)` — on every view switch (facet select
and pin selects alike) the outgoing mode's camera (yaw/pitch/zoom/pan/
touched) is banked in `v.cams[from]` and the incoming mode's own camera is
restored — or fresh defaults with `touched=false`, so the untouched
framing (start edge / top-left) greets a first visit. Switching back
returns you exactly where you were in THAT view. The fit cache clears on
switch. Policy still persists the current camera only — per-mode cameras
are session memory, the wire schema is unchanged.

Boot sanity DOM-checked; interaction is user-side as usual.

## Round: cross-leaf sync live + rung 7, panes-for-pins — 2026-08-07

Two items: rung 5's last leftover, and rung 7.

**Browser /policy polling.** The leaf polls every 2s, diffs against a
snapshot, and applies the delta — with a 2.5s quiet window after any local
post (the hand on the wheel wins; last-writer-wins across leaves at tick
cadence). Own posts stamp the snapshot so echoes aren't deltas; skipped
polls keep the OLD snapshot so a remote change deferred by the quiet
window still applies on the next tick. Scalars re-apply through one
`applyPolicyKey` (speed, zooms, reader.mode, graph.view with camera
banking, tunables, camera, shares); pins reconcile IN PLACE
(`syncPinsFromPolicy`): new ids build, missing ids remove, existing pins
take geometry/camera/mode/rule nudges without losing their element, view,
tree or history. `parsePinValue` is now the ONE pin parser (boot rebuild
and live sync share it — they had started to drift).

**Rung 7 — TUI panes.** Pins render as a PANES column between document and
spine (≥176 cols; the document facet yields width): span pins show their
rule + span + wrapped text, rail pins their structural lines in the rail
registers (refs cool, literals warm, classes violet, depth as dot-indent),
graph pins name themselves and their view honestly ("lives in the
browser"). The TUI's 2.5s tick now also re-reads /policy (speed, shares,
reader mode, pins) — the browser's gestures land in the terminal live,
and the reverse already held. Census +4: panes drawn, span pane carries
its text, rail pane names the rule, rail structure fetched. All green;
serve census untouched and green.

**Verification honesty.** The live-sync screenshot attempt exposed a
harness limit, not a defect: chrome-headless's --screenshot fires on load
(status bar showed char 0 · paused — before even autoplay's 600ms timer),
so a post 5s later can never appear in the capture. Live browser apply is
code-verified; boot apply is screenshot-proven; the TUI census proves the
same record driving a second leaf. The browser's live tick joins the
gesture list the user's hands verify.

SPEC §2 rewritten for polling + panes; THINKING ladder rung 7 struck.

## Round: the two pin leftovers — 2026-08-07

Closing the audit's items 1 and 3 before rung 8.

1. **Staleness survives a reload.** The span-pin policy value grew its
   10th token: the generation the pin was made against. `parsePinValue`
   reads it back (legacy 9-token values read as current — old policies
   don't false-stale); the existing `p.gen !== generation` marking does
   the rest. Verified end-to-end: pin posted at gen 1 → identity /edit
   bumped the server to gen 2 → fresh browser boot → DOM carries
   "gen 1 — stale" and the `.pin.stale` register.
3. **Remote re-target rebuilds the window.** `syncPinsFromPolicy`'s span
   branch now checks span identity (s/e/d/rule); a changed identity
   updates the record + snippet and drops the element so `renderPins`
   rebuilds header/snip/def, keeping geometry. A bare gen change flips
   staleness without a rebuild. Code-verified (the live-poll harness
   limit, as recorded last round).

SPEC §2 span value updated. Serve + TUI censuses green (legacy 9-token
values still parse — the census's own pin.7 value proves it).

## Round: rung 8 — the engine clocks — 2026-08-07

THINKING §6b, built as ruled: both engines drawn as their OWN time facets
on the shared document coordinate, neither a renamed version of the other.

**Instrument.** `ClockKernel(PdaKernel)` — the zero-hook observation
pattern, third use: `_enter` and `attempt` increment per-position counters
before delegating (`__slots__` required; the IR meta refuses a dict even
on subclasses — measured, fixed). The Earley clock reads the explicit
`Kernel(compile_tables(instance), doc, record_links=False).run().cols` —
items per column, off the kernel's own state; instance tables compiled
once per subject (the grammar never changes across re-reads). Both build
in a background thread per read, generation-guarded like the route.
Wire: `GET /clock` — status/generation/pda_end + sparse `#PDACLOCK`
(`pos enters attempts`) and `#EARLEYCLOCK` (`pos items`).

**Leaf.** THE DERIVATION header grew the clock select (model · pda clock ·
earley clock), policy-persisted as `chart.clock` and live-synced like
every policy key. The lanes region switches: PDA = cool bars (log frame
entries) + warm ticks where the real attempt machinery fired + a red line
at pda_end on refused routes; Earley = violet columns (log items). The
overview strip, viewport, scrub and cursor stay — time is time in every
clock. Pending is a drawn sentence ("the pda clock is running…"), never a
blank; data invalidates on generation.

Measured while verifying (vyx at char 1,200, a comment-heavy region): the
PDA's clock is SPARSE there — comment interiors run frameless (leaf runs),
so whole lines cost a few entries at the line heads — while Earley's
columns stay dense throughout. The two clocks disagree exactly where the
engines differ; that disagreement is the content. Censuses: all four
fixtures gained the clock gate (arrays cover doc+1, totals nonzero) —
meta 1,453/30,981 · vyx 2,635/32,471 · long 8,225/294,262 · abnf
4,994/151,689 (pda enters / earley items). All exit 0; TUI census
untouched and green (chart.clock is browser policy; the TUI ignores it).

Screenshots: /tmp/clock_pda.png, /tmp/clock_earley.png.

## Round: the clocks answer the hand — 2026-08-07

The user's catch on rung 8: the model view's chart answers a hover (span
words in the readout, co-selection everywhere) — the clock views answered
nothing.

Fix, three parts in the same gesture channel the model view uses:

- **Hover hit-test knows clocks.** In a clock view the lanes region
  resolves the hovered CHARACTER (the same math the scrub uses), outlines
  the hovered bar, and co-selects the deepest span at that position — so
  the document highlights, the reader lights, and the span's own words
  arrive exactly as they do in model view. The chart also gained the
  mouseleave clear it never had.
- **The readout speaks the clock's numbers first**: "char 1,204 — the PDA
  entered 5 frames here · 1 real attempt · <span words>", or "frameless —
  a leaf run carried this char" where the fused kernel skipped frames
  (the honest sentence for the comment-interior silence measured last
  round); Earley: "Earley's column holds 41 items".
- Clicking (scrub) already set the cursor in every view, so the spine
  followed — unchanged.

Hover can't be driven headless; sanity boot screenshot clean
(/tmp/clock_hover_sanity.png), hit-test math shared with the proven
scrub. User-side feel test, as usual.

## Round: the clocks, ripped out and rebuilt as the machines — 2026-08-07

The user's verdict on rung 8's first form: "the visualization should be
meaningful. These bars do none of it." Correct — count bars are a
histogram, not a machine. Ripped out (wire sections and all) and rebuilt
from the engines' own objects.

**The PDA clock is now the kernel's own trace.** `ClockKernel` records
every frame the fused kernel pushes — extent (enter position → completion
position), stack depth, clone name — via `_enter`/`_complete` keyed by
frame identity (no LIFO assumption; probe sub-run frames record too:
rolled-back work is real work). Frames still open when a parse dies close
at the failure position — the live stack at death IS the trace's last
column. Drawn exactly like the model lanes (read/active/pending states
against the cursor, violet on the marked rule) — but these are the
ENGINE's frames: frameless leaf runs appear as literal silence, the gaps
between frames. In the vyx comment region the trace is three frames deep
where the model shows d18 — the difference between what the text MEANS
and what the machine DID, side by side on the same coordinate.

**The Earley clock is now the hypothesis field.** Every `(rule, origin)`
the kernel ever held, decoded from its own columns (`decode_item`), drawn
from birth to last column alive — cool when completed, red-outlined when
ABANDONED (considered, never finished: the speculation the grammar
forces). Greedy row packing; the row count is itself a measurement (the
most hypotheses simultaneously alive), stated on the legend. 60k cap with
longest/completed kept and `dropped` counted aloud (long: 2,833 dropped
of 62,833).

Hover now answers with identity, not numbers: `frame comment-line ·
1,198..1,257 · stack depth 2` / `hypothesis kv-pair · 306..391 ·
ABANDONED — considered, never finished`; the hovered extent outlines ink,
its rule co-selects through graphHover (reader lights, graph chips heat).

Census hardened: the root frame must span the whole document; a completed
whole-document hypothesis must exist; every extent ordered and in bounds.
meta 2,543 frames/10,328 hyp · vyx 1,360/8,999 (786 abandoned) · long
6,620/60,000 · abnf 4,539/42,501. All four exit 0.

Screenshots: /tmp/trace_pda.png (the stack breathing over a comment
stretch, spine agreeing), /tmp/trace_earley.png (completed extents over
the dense per-char hypothesis band).

## Round: the clock rethink — a mock, from the developed languages — 2026-08-08

The user's redirect: the clocks need rethinking, and the languages were
already developed — VISION_6's `1-watching-a-parse.html` (the Earley
stepper), opsis-2 visual_2's automaton-level PDA (whose real engine is
`260731-opsis/opsis_proto_0/trace.py`'s TraceKernel), and visual_4's
ambiguity annex — with the ruling that no Earley conversation lives
without the SPPF. Chose (with the user) a mock before implementation:
`clockmock/mockup.py` → self-contained `clockmock.html`, every payload
extracted from live runs, generation IS the census.

**What the mock demonstrates, all real:**
- THE PDA as a stepper: the frame lanes + THE STACK AT t as a sentence
  (7 frames open: json-text ▸ … ▸ value), decision events through the
  TraceKernel seams (all four hooks verified alive in today's kernel),
  owner-colored text. The json walk is honestly deterministic — so the
  decision vocabulary got a live annex: an undecidable arm choice
  (`s ::= xa | xb` over unbounded x's) whose 11 attempt events SHOW the
  re-walk cost. Islands stay a legend note: the nested-leftrec trial
  refused honestly ("arm choice spans two ends"), and a succeeding
  island subject is a rabbit hole this mock didn't need.
- THE EARLEY COLUMN as the watching-mock's read, re-extracted from
  today's kernel via `decode_item`: the item set at t as dotted rules
  (done ● todo, @origin, predict/advance/complete), CAN COME NEXT, the
  hypothesis field demoted to overview. Empty columns are REAL (the
  kernel scans lexical runs past interior columns) and say so.
- THE FOREST from the chart's own links: 6 symbol nodes, the ONE
  ambiguity point (expr 0..5, two families — Scott's definition), family
  edges warm-vs-dashed-red, derivation toggle, exclusive subtrees marked
  "⟵ not in the twin". The refusal doctrine stated on the panel.

Deterministic states: `?t=`, `?fam=`. Screenshots /tmp/clockmock1.png,
/tmp/clockmock_t_20.png (7-deep stack mid-"true"), /tmp/clockmock_t_5_fam_1.png
(the mirrored family choice). Next: the user reads it and rules on the
read; then the atlas integration (wire sections for items/events; the
SPPF panel needs an ambiguous subject, which atlas fixtures by design
are not — the annex-as-subject question is theirs to rule).

## Round: the clock rethink lands on atlas — the automaton, the column, the stack — 2026-08-08

The user's verdict on the mock: worse than useless — toy input, a 2-way
ambiguity toggle that ducks the 100-way question, and a PDA panel that
shrugs "deterministic descent" instead of showing the machine. Mock
deleted (f9f70df). Built directly on atlas at fixture scale.

**The automaton is a reader view.** `GET /automaton` ships the compiled
machine — every clone the runtime can reach (refs, dispatch targets,
attempt sub-clones), mode, decision flags, BFS depth. Nodes are CLONES,
not rules: meta's 90 rules ARE 489 clones / 755 edges (`ws` × 11 context
clones — the FOLLOW-tail cloning made visible); long's machine is 734.
Drawn as depth columns with mode glyphs (■ seq · ● dispatch · violet
value_str · warm ring = attempt clone · violet box = gated) — the
decision STRUCTURE shows even when a walk is deterministic, which is the
honest answer to "the walk was boring": the machine says where decisions
COULD arise. With the pda clock on, the walk lights it: frames carry
their exact clone ids (pda_tables is memoised, identity is stable), so
the stack at t threads a warm path through the machine — verified
matching THE SPINE frame for frame at char 600.

**THE SPINE follows the clock.** model = open spans (unchanged) · pda =
the kernel's own stack at t (22 deep at char 600, real extents) + the
decision events near t, with the none-sentence pointing at the automaton
· earley = the cursor's column as dotted items (`@598 group ::= "("
alternation __rep_1 ● ")" advance`) + CAN COME NEXT chips — fetched per
cursor move over `GET /column?i=` from the retained recognizer kernel
(whole-document item sets never cross the wire; scale-safe by
construction).

**Events, full vocabulary.** ClockKernel now records
attempt/loop/verdict/probe/island through the same seams
opsis_proto_0's TraceKernel proved, capped at 20k. All four fixtures
record ZERO decision events — measured, and now VISIBLE as machine
structure instead of an empty log.

**The SPPF question, put honestly:** atlas subjects parse unambiguously
by constitution (ambiguity is refused by both engines), so a forest with
N families cannot exist in any current fixture. The at-scale SPPF view
(family lists per node, not toggles) needs a subject whose READING keeps
the forest when the model refuses — a structural ruling on Subject
(reading-without-model), flagged to the user rather than half-built.

Censuses all green (meta/long/vyx/abnf + TUI), each asserting: automaton
edges resolve, start depth 0, frames carry valid clone ids, >0 wired.
Screenshots: /tmp/auto1.png (the lit walk + pda spine),
/tmp/auto2.png (earley column spine + CAN COME NEXT).

## Round: the PDA clock earns its name — 2026-08-08

The user's six findings on the automaton round, all landed:

1/3/4. **The pda clock now DOES something everywhere.** The overview band
recontextualizes per clock (stack-depth texture + warm decision marks for
pda; violet hypothesis density + abandoned red for earley) — switching
clocks visibly re-derives the whole facet. The frame lanes stopped being
a colourless copy of the model view: frames colour by their clone's MODE
(grey seq · cool dispatch · violet value_str · amber alt), and rolled-back
probe frames draw RED — the attempt machinery's discarded work, the same
fate register as Earley's abandoned hypotheses.
2. **The overlay bug**: the automaton is canvas-only; stale chips from
the previous view stayed visible over it. Chip layer now shows/hides per
view.
5. **The verdicts, from the older prototypes**: `GET /verdicts` ships
the analysis' per-rule reaction in its own words (attempt / island /
hard / gated / predictive — opsis_proto_0's explainer vocabulary; the
analysis is the oracle). The reader badges every non-predictive rule;
notes ride the title. decide.gbnf shows `choice [attempt]`,
`xs [attempt]`; amb.gbnf shows `expr [island]`.
6. **The observation fixtures.** `decide` — an undecidable arm choice,
393 chars, the attempt machinery fires at every entry: 738 decision
events, 144 rolled-back probe frames. `amb` — a genuinely ambiguous sum
(429 derivations), readable via the `first` resolver (the explicit
opt-out): the route strip states the honest inversion ("start rule
'expr' is an island — no PDA"), the spine's column shows ambiguity AS
ITEMS (four `expr-arm1 ::= expr "+" ● expr` at origins 0/2/4/6, all
alive), and the field carries the abandoned reds.

**The recording bug the fixtures caught:** attempt sub-run frames that
rolled back never `_complete`, so the end-of-run close stamped them to
the document end and they polluted the stack readout. The stack
discipline gives the true fix: a frame popped without completing IS a
rollback — swept at the next push at its depth AND at any shallower
completion (`_sweep`), marked abandoned. Verified: zero leaked extents,
the committed chain reads clean (`entry 145..157 · xa 145..156 · …`),
probes counted separately in the spine.

Census: six fixtures now (meta/long/vyx/abnf/decide/amb) + TUI, all
exit 0; gates route-aware (a positionless island failure is still a
failure; resolver routes measure no frontier). Screenshots:
/tmp/decide4.png (badges, red probe fates, decision band, clean stack),
/tmp/amb1.png (island badge, violet density, ambiguity-as-items).

## Round: legend and badge polish — 2026-08-08

The user's read of the pda-clock round:

1. **Automaton legend** collided with the tune sliders and ran off the
   facet without wrapping → all canvas legends now draw through one
   `drawLegend` at the BOTTOM edge, ellipsis-truncated to the canvas
   width.
3. **Clock legends clipped into the minimap** → same fix; the lanes
   floor rose to make room (y1 = h−18). Legends shortened.
2/2a. **Verdict badges**: right-justified (absolute right on the
   relatively-positioned reader line — float loses inside the pre line)
   and visible ONLY under the pda clock (`body.clock-pda` toggled by one
   `setClock` used by select/boot/poll). On earley/model the reader is
   clean; the machine's reactions appear exactly when the machine's
   clock is telling.
4. Held by the user's word: resolver-passing UI and the SPPF view over
   amb's 429-derivation forest — next.

Verified: /tmp/polish1.png (automaton legend bottom), /tmp/polish2.png
(earley legend bottom, no badges, CAN COME NEXT "a"/"b"/"x" — the
undecidability itself), /tmp/polish4.png (badges right-edge, pda clock).

## Round: the machineless truth + badge coverage — 2026-08-08

Four findings on the polish round:

1. **Badges justified to the text, not the facet** — absolute-in-line
   pins to the LINE's right edge, which lives past the viewport when the
   facet is narrow. Fix: `position: sticky; right; margin-left: auto` —
   the badge rides the visible scrollport edge at any share. Verified at
   reader share 0.2.
2. **Rules without designation** — "silence is the deterministic
   verdict" was too clever; every rule now carries its badge, predictive
   in the dim register. The reader reads as a complete verdict table.
3. **The automaton only lit on the pda clock** — the walk exists
   regardless of which clock the derivation facet tells; lighting now
   loads and applies from the clock data unconditionally.
4. **amb broke both views with nonsense** — the machineless case now
   speaks the engine's own words everywhere, shipped over the wire
   (`pda_words`): the pda lanes and spine say "the PDA never ran — start
   rule 'expr' is an island — no PDA · the reading came from Earley + the
   supplied resolver · the earley clock tells this subject's time";
   DECISIONS says "none — there is no machine to decide"; the automaton
   view states the island honestly and points at the views that still
   apply. All sentences truncate to their facet (truncLine shared with
   the legends).

Censuses green (decide/amb/meta spot + earlier full run). Screenshots:
/tmp/amb_fix.png (the honest machineless subject), /tmp/badge_fix.png
(full badge coverage pinned to a narrow facet's edge).

## Round: the dock — facet presence as nodes — 2026-08-08

The user's ruling at the stable point: facets must move, minimize,
reopen, clone, and pop as windows — WITHOUT becoming windows; the node
philosophy uncompromising; closing stateful things implies a place to
reopen from. Design written as THINKING §9 (the facet set is itself a
node-space); this round built the foundation:

**The dock.** A node rail in the masthead: every facet a chip, lit =
present, dim = minimized, click toggles. Presence is policy
(`facet.<name> on|off`) — it persists, survives reload, and syncs
cross-leaf like every session value. A minimized facet keeps ALL its
state (shares, views, clocks, cameras live in policy already). The grid
REFLOWS: neighbours take the freed share; `arrange.*` restores on
reopen; seams guard hidden neighbours.

Two CSS truths measured on the way: `minmax(220px, 0%)` floors at the
minimum (collapse needs template overrides per off-state), and grid
auto-placement SHIFTS when a section display:nones away — explicit
`grid-column`/`grid-row` per facet was load-bearing (the derivation
swallowed the document's column before it).

Verified: /tmp/dock2.png — reader+spine minimized from policy, document
wide, derivation full-column with the pda clock; dock states correct;
reopen round-trips (body classes clear). Censuses green (meta, decide,
amb, TUI). Named next on §9's build order: move (arrange.order), clone
(`facet.<id> <kind>`), pop for the remaining facet kinds, pin-minimize
into the dock.

## Round: movement + the dock's first design pass — 2026-08-08

The user's read on the dock: the idea works; it will strain as facets
multiply; rethink look and feel while building movement and the rest.

**Slots.** The grid's four regions became first-class: L, C, RT, RB.
Facets map to slots (`facetSlot`), placement is inline per facet, and
every consumer that used facet NAMES for geometry (column collapse,
seams) now asks SLOT OCCUPANCY — facets move without breaking collapse
or resize. Order persists as `arrange.order` ("chart document grammar
spine" = slot order), boot-applied and live-synced like all policy.

**Movement is a dock gesture.** Dock nodes are draggable; dropping one
onto another swaps their slots — the dock IS the facet graph's rail, so
rearranging the graph rearranges the grid. Verified: the derivation
moved to the left column (clock lanes at full height), the reader to
right-top (verdict badges still pinned to its edge — sticky earned its
keep in a new slot), spine right-bottom.

**Dock restyle, first pass.** Chips became node-pills: status dot
(cool = present, dim = minimized), hairline border, grab cursor, violet
target highlight while dragging. Ordered by slot, wrap-safe. The DEEPER
design pass the user called for (scale to many facets: clones, minimized
windows, grouping) is still owed — this is the small pass that came free
with movement.

Still open from §9's build order: clone, pop-as-window for the remaining
facet kinds, pin-minimize into the dock, and the dock scale redesign.
Censuses green (meta spot + earlier full run). Screenshot:
/tmp/move1.png — the rearranged instrument, derivation-first.
