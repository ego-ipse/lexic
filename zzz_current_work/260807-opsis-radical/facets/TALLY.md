# facets — work tally (context-recovery ledger)

Newest last. One line per meaningful step; enough to resume cold.

- **Position**: facets = the composition answer. One subject (a reading), four
  facets (READER / DOCUMENT / DERIVATION / SPINE), no windows — regions with
  hairline seams. Cursors (t, selection, hover) live on the subject; every
  facet renders them in its own coordinates. The document plane is REAL DOM
  text; native selection drives structural co-selection. Edits are
  re-readings: splice text → lexic parses again → all facets re-derive, or the
  engine refuses in its own words. Grammar is the ground truth.
- **Stack**: Python instrument (serve.py, in-process lexic) ⇄ browser leaf
  (leaf/, real versioned artifacts, not blobs). Wire is line-oriented plain
  text both ways (no JSON anywhere): frames out (`/scene`, length-prefixed
  blocks), gestures in (`/cursor`, `/edit`). Addresses cross; subjects never.
- 2026-08-07: tk-era work (demonstrator/spectacle/wolf + fixtures) moved to
  `../tk/`; its census still green from the new location.
- `leaf/pretext.js` vendored from
  `~/.claude/skills/gstack/design-html/vendor/pretext.js` — **byte-identical
  copy, md5 e04b8d0c6712b291f2b37088999007e0**, full ES module (exports:
  prepare, layout, prepareWithSegments, walkLineRanges, layoutNextLine,
  layoutWithLines, profilePrepare, setLocale, clearCache). NOT yet imported by
  leaf.js — this iteration's document facet is no-wrap monospace, where glyph
  geometry is arithmetic; pretext enters when a facet wraps or flows.
- `serve.py` written: Subject (fixtures long/meta/vyx; meta+vyx read by the
  metagrammar, which spells ITSELF via `GBNF_FLAVOUR.apply(GBNF_FLAVOUR.grammar)`
  — 3,010 chars, 90 rules), fold with authored rule names via
  `type(part).__grammar__.name`, scene emitter, gesture handlers, census.
- `leaf/index.html` + `leaf.css` + `leaf.js` written: facet grid (grammar |
  document | chart+spine), under/over canvases welded to the text plane by
  measured monospace geometry, chart with overview density + depth lanes,
  spine bounded by depth, co-selection engine (hover/select/rule/native
  selection), play/scrub, edit bar, refusal banner. `?t=N` query pins the
  cursor for deterministic screenshots.
- Census green (meta + vyx): fidelity holds, scene integrity holds, identity
  retype re-reads (memo-warm 1.09s → 0.39s on meta), garbage retype refused
  with the engine's words ("input does not derive from 'grammar'"), document
  unchanged after refusal.
- vyx numbers: 9,417 chars · 11,692 spans (nonzero) · 90 reader rules · scene
  222 KB.
- Verification: firefox --headless hung on this machine (killed); switched to
  the gstack browse daemon (`$B goto/console/screenshot`).
- OPEN: browser-side visual verification + polish iterations; pretext wrap
  mode; long-fixture canvas memory (full-content canvases — fine at vyx size,
  heavy at 986 lines); spine/closed virtualization beyond 7 rows.
- Verification path settled: playwright's chrome-headless-shell driven directly
  with --no-sandbox (the browse daemon's chromium cannot sandbox under this
  machine's AppArmor userns policy; firefox --headless hangs).
- leaf.js gained followCursor() (document scrolls to the cursor while playing
  or on a t jump; never fights the user's scroll) and deterministic demo state
  via query params: ?t=N & sel=OFF & rule=NAME.
- Screenshot-verified on vyx at t=4205 sel=4205: caret mid-word in
  `schema-def`, read/unread shading correct, spine d0..d8 with offsets, JUST
  CLOSED showing namechar 'c' 'h' 'e' 'm', chart following — and the READER
  facet co-lit `namechar ::= [\-0-9A-Z_a-z]`, the rule that read the selected
  character: cross-facet deixis on camera.
- Root README run-lines updated for the tk/ move.
- COMMITTED at 80ede43 on opsis_proto ("opsis-radical: the demonstrator line")
  — user's explicit grant; gitignored zzz added with -f; pre-commit gates green.
- Perf question answered by measurement: PDA fused route 313,593 chars/s vs
  metagrammar Earley+resolver route 1,974 chars/s (159×); resolver invoked
  exactly ONCE on vyx — the cost is the route (ambiguous self-grammar model
  product → probe-fork → Earley + ambiguity audit), not resolution. Lexic-side
  fix: de-ambiguate the GBNF self-grammar's model product (noise attribution).
- Refusal surface measured: UnsupportedConstructError carries words only — no
  position, no expected set. Lexic gap worth a ruling (readout-shaped,
  additive). Recorded in atlas/THINKING.md §5.
- atlas/ forked from facets (leaf + serve intact; facets tally frozen there as
  TALLY_facets_fork.md). atlas/THINKING.md written: topological answers for
  resize (degrade-by-deriving-less), the 3D rule graph (z = derivation
  distance, name-addressed co-selection), attachments as ports (products
  multiply facets, transpile is a peer edge), the meta ring (focus along a
  lineage edge pointing at yourself), the refusal facet, and the iteration
  ladder (refusal → seams → graph → ports → ring).
- RULED (user, 2026-08-07): both engines as observation — PDA default, Earley
  loaded in the background, visualization switchable once Earley finishes;
  inversion when the PDA fails. No route flag enters the parse API (the
  no-PDA-opt-out ruling stands). Recorded as THINKING.md §6b; inserted into
  the iteration ladder as step 2.
