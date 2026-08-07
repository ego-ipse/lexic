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

## 4 — Ranked targets

1. **lexic-earley on arithmetic** (63.8 µs/char). The worst absolute number, and
   the one where a peer Earley implementation is 1.45× faster — so the gap is
   not intrinsic to the algorithm.
2. **vyx / abnf-meta against parsimonious.** The largest PDA losses; likely the
   same cause, since both are structure-dense.
3. **arithmetic / csv against lark-lalr.** Smallest gap, and the most likely to
   be "we build more" rather than "we are slower" — worth pricing before
   chasing.

Next: profile target 1, since it is the largest and has a same-algorithm peer to
compare against.
