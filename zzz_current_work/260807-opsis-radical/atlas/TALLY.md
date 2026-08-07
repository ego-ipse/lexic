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
