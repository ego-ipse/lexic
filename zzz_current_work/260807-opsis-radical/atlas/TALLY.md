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
