# DISPUTED: perf drop during Lark→Earley cutover — claims to verify

Status: user does not trust the conclusion. Every claim below is falsifiable;
run the commands and check.

## The dispute

Engine product throughput fell ~2× during the cutover (15 → 26–30 µs/char).
User's counter: "if grammar growth explains it, Lark would have slowed too."

## My claims

1. **Engine code did NOT regress (±4%).** Current HEAD engine running the OLD
   subset grammar on the OLD corpus matches the b166912 engine on the same
   work: 15.3 vs 15.0 µs/char product.
2. **The regression is the grammar, not the engine.** Same engine, same text,
   final RFC-full grammar (70 rules/92 normalized) vs old subset (34/46):
   26.3 vs 15.3 µs/char. Most of it comes from the Phase-3 *remainder*
   (c-wsp/c-nl noise model, option, %d/%b element alternatives), NOT the
   checkpoint (checkpoint grammar = 16.4).
3. **Prediction cost, not construct cost:** the test text contains NO
   comments/options/%d/%b/%s/%i/=/ — yet the full grammar is 1.7× slower on
   it. The predictor expands the new alternatives at every position anyway.
4. **Lark stayed flat because Lark's grammar never changed.** Its META_GRAMMAR
   at b166912 already had the full surface (option, =/, %s/%i, numseq, %b/%d,
   prose) AND handles whitespace+comments in the LEXER (`%ignore`), which
   costs nothing at parse time. Lark: 29.9 µs/char then (committed
   bench_baseline.json: 109.9ms x4 product), 30.1 now.
5. **The old 0.56× "win" was an unequal race**: engine-with-subset-grammar vs
   Lark-with-full-grammar. Full-vs-full today is ~parity (engine 26.3 vs lark
   29.9 on the identical old corpus).

## Reproduce (each cell ~30s; scripts also in /tmp from my run)

```bash
# Cell A — old engine + old grammar (b166912 snapshot):
mkdir -p /tmp/lexic_base && git archive b166912 src | tar -x -C /tmp/lexic_base
# run /tmp/lexic_base/cell_a.py with PYTHONPATH=/tmp/lexic_base/src
# (times recognize/parse/parse_reduced on ABNF_FLAVOUR.apply(abnf_2.ABNF_GRAMMAR) x4;
#  writes /tmp/corpus_old.txt — 920 chars/copy, NOT 2008)
cd /tmp/lexic_base && PYTHONPATH=src uv run --project ~/projects/lexic --no-sync python cell_a.py

# Cell B — current engine + current grammar on the SAME text:
uv run python /tmp/cell_b.py
# Cell C — current engine + OLD subset grammar (24dd97f abnf.py, sed parsing_2→parsing):
uv run python /tmp/cell_c.py
# Cell D — current engine + Phase-3-CHECKPOINT grammar (b20749f abnf.py, same sed):
uv run python /tmp/cell_d.py
```

## Measured (x4 = 3680 chars of old-subset self-emit; µs/char; 10 rounds, gc off, warmed)

| cell | grammar (raw/norm rules) | engine  | recognize | parse | product |
|------|--------------------------|---------|-----------|-------|---------|
| A    | subset 34/46             | b166912 | 7.7       | 33.0  | 15.0    |
| C    | subset 34/46             | HEAD    | 7.9       | 34.4  | 15.3    |
| D    | P3-checkpoint 44/60      | HEAD    | 8.2       | 34.8  | 16.4    |
| B    | RFC-full 70/92           | HEAD    | 15.7      | 50.7  | 26.3    |

Historical cross-check: `git show b166912:zzz_current_work/bench_baseline.json`
→ x4 parse+reduce earley 62.1ms / 3680 chars = 16.9 µs/char (matches A);
lark 109.9ms = 29.9 µs/char (matches today's lark ≈ 30.1 → claim 4).

Lark META_GRAMMAR full-surface check:
`git show b166912:src/lexic/grammars/abnf.py | sed -n '/META_GRAMMAR/,/"""/p'`
→ ir_option, ir_rule_inc (=/), CS/CI_STRING, NUMSEQ, NUMVAL (%bdx), PROSE,
`%ignore` ws + `;` comments.

## What would falsify me

- Cell C ≫ Cell A on your machine → engine DID regress; my claim 1 is wrong.
- Cell B ≈ Cell D → the remainder additions aren't the cost; claim 2 wrong.
- A Lark parser fed a grammar with rule-level (non-%ignore) noise staying fast
  → the lexer-vs-parser noise asymmetry (claim 4's mechanism) is wrong.

## If claims hold — the fix direction

Give the engine what `%ignore` gives Lark: handle ws/comment noise below the
chart (lexrun/terminal-level collapse) instead of as predicted grammar rules;
prune nullable predictions. Engine mechanics are intact (recognize on subset
still 7.7 µs/char).
