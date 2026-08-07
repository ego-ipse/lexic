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
