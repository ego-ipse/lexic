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
