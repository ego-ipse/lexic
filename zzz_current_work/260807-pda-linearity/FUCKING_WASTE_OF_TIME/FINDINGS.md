# Where lexic loses — the benchmark gap investigation

**Mission:** find where lexic loses on `tools/benchmark/bench.py` and find
optimizations. Open-ended; no definition of done. **No `src/` changes** until
told.

Baseline run: `--rounds 5`, all grammars, this machine, 2026-08-07 — after the
attempt-sub-clone landing (`3dbe1c8`).

## 1 — The board

`antlr` is Java and in a different league; the honest comparison for lexic is
the Python field. Bold = lexic loses.

| grammar | lexic-pda | best Python rival | verdict |
|---|---|---|---|
| arithmetic | 3.389 | lark-lalr **2.684** | **loses 1.26×** |
| csv | 0.917 | lark-lalr **0.727** | **loses 1.26×** |
| json | 2.097 | parsimonious 2.124 | wins by 1% (inside a 1.00% noise floor — a tie) |
| gbnf-meta | 5.437 | — | wins by default; every rival refuses the corpus |
| abnf-meta | 6.206 | parsimonious **3.913** | **loses 1.59×** |
| vyx | 5.066 | parsimonious **2.773** | **loses 1.83×** |

And the other engine, which is the real outlier:

| grammar | lexic-earley | lark-earley | lexic-pda |
|---|---|---|---|
| arithmetic | **63.789** | 43.855 | 3.389 |
| csv | **13.893** | 11.847 | 0.917 |
| json | 36.414 | 40.220 | 2.097 |
| gbnf-meta | 66.022 | 182.040 | 5.437 |
| abnf-meta | 62.906 | 128.144 | 6.206 |

## 2 — What the board says

**Three losses worth investigating, and they are not the same loss.**

1. **vyx −1.83× and abnf-meta −1.59× against parsimonious.** The largest PDA
   gaps, and both are against a PEG packrat building a generic node tree. These
   are the grammars with the most structure per character.
2. **arithmetic and csv −1.26× against lark-lalr.** A table-driven LALR parser
   with a separate lexer. Different shape of loss: these are small, regular
   grammars where a real lexer wins the character loop outright.
3. **lexic-earley is 12–30× its own PDA** and loses to lark-earley on
   arithmetic (1.45×) and csv (1.17×). It wins on the two metagrammars, so it
   is not uniformly bad — but it is the fallback path, and 63.8 µs/char on
   arithmetic is the single worst number lexic posts anywhere.

**What is NOT a loss, and should not be optimised toward:** the antlr column.
It is Java, and its own row notes 4–8% of the timed region is CharStream
construction. json is a tie, not a win. gbnf-meta and vyx have no rival that
accepts the corpus, so "winning" there means nothing.

## 3 — The product difference costs ~0% on the PDA route (measured; earlier
claim retracted)

The engines do not build the same thing — lexic returns a typed model the source
is recoverable from, the rivals return generic trees, and nobody else gets
semantic actions. This section used to say "some of every gap is that
difference". **On the PDA route that is false, and it is now measured.**

Stubbing all three model constructors and re-timing the parse changes the number
by 0–2%, inside noise, on every grammar. Interning had already collapsed 3,342
model references to 561 objects; construction was almost free before this
mission started.

It remains true of the **Earley** route, where the fold is 46% of the run — and
generalising it from there to the PDA, without checking, is the mistake this
section used to encode.

**So the gap is recognition.** lexic's walk is slower than parsimonious's
packrat and lark-lalr's table loop, and stripping the product closes none of
it.

## 4 — Standing state (consolidated; `TALLY.md` holds the history)

### Closed, with reasons — do not reopen

| line | why it is closed |
|---|---|
| **lexic-earley's 12–30× gap** | The Earley fold declines the fast-ctor licence **by design** — `FastCtor`'s docstring: "the engine path stays the validated reference". Its 14,152 validated constructions are the property the parity differentials rest on. Also insufficient: unchecked arithmetic is 49.8 vs lark-earley's 43.9. |
| **The second-success audit** | 9% of attempt cost (3.32 ms of 36.18 ms). Not worth touching an ambiguity check for. |
| **Sub-run memoisation** | Tried before this mission, measured **zero hits** — a sub-run's outcome depends on the enclosing continuation, so `(clone, pos)` is unsound. In `_attempt_run`'s own docstring. |
| **FIRST_k admission filtering** | Prototyped (`kproto.py`). Cuts 370 sub-runs and runs **27% SLOWER**: ~4,675 window checks at ~2.9 µs to avoid 370 sub-runs at 25.6 µs. Restructuring *when* to check does not fix a cost that is *per call*. |
| **Raising `arm_gate`'s k ceiling** | `body-line`, `kv-pair`, `value`, `scope-item` all **collide at every k from 2 to 6**. The attempt classification is correct; these arms need unbounded lookahead. |
| **csv double-scanning** | Retracted — `vstr_once` calls `match_cc`, so the 189% was nesting reported twice, not redundant work. |

### The architectural answer for vyx (−1.83×)

parsimonious wins because PEG ordered choice takes the first match and memoises
`(rule, position)` soundly. lexic cannot: its sub-run outcome depends on the
enclosing continuation, **because lexic refuses ambiguity and must check whether
a later arm also matches.** The gap is largely the price of that refusal on a
grammar with no bounded-lookahead separation. Closing it means changing what
lexic promises — a ruling, not an optimization.

### The one live candidate

**Replace per-character Python scan loops with a C-level scan** (a `re` pattern
compiled once per CharSet at flatten time, carried on the `FlatArm` beside the
`(chars, negated)` pair it replaces).

- Kill-test **passed**: the Python loop is linear in run length
  (173/267/348/511/909 ns at 1/2/3/5/10 chars); `re.match` is flat at ~185 ns.
  Crossover at length 2; csv's runs average 4.75.
- Honest size: **~5.4% on csv**, against the **21%** needed to pass lark-lalr.
- Design note: keep the loop for length-1 runs (a cheap first-char test recovers
  the crossover loss).

### The bottom line

lexic's PDA loses four of six rows. **vyx and abnf-meta are explained** (the
price of ambiguity refusal, irreducible without changing the promise).
**arithmetic and csv are not** — they have zero attempts, zero chases, the
lowest entries/char on the board, and still lose 1.26× to a table-driven LALR
with a C lexer. That is the real remaining gap, only ~5.4% of it is currently
identified, and "beat every parser on every grammar" is not reachable on the
evidence so far.
