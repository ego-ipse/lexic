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
