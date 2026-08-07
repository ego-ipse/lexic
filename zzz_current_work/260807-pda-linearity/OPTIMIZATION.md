# The common path — investigation and prototypes

**Status:** investigated and prototyped, **no `src/` changes**. The headline is a
negative result that redirects the effort: the lever everyone (including this
effort's own prior art) expected is not the one that pays.

Target: `bench --only vyx` — the vyx grammar parsing a real 3,461-char packet,
the traffic an agent protocol actually carries. **5.658 µs/char**, against
antlr 0.302 (19×), parsimonious 2.761 (9×), antlr-py 10.4, pyparsing 19.5.
Nothing this effort landed touched that number; the boundary-density work was a
different workload.

## 1 — Where the work is

`probes/hotpath.py`, profiling 20 rounds of the real corpus:

```
 tottime  ncalls/parse  what
   13.2%          2017  _drive            the fused hot loop
    7.7%          5394  _enter            clone entry
    7.0%          4058  vstr_once
    6.8%          1696  _fast_fields
    4.3%          2525  _match_vstr
    4.2%          2432  _complete
```

Nothing dominates. The parse is spread across the driver and the entry/complete
cycle, which is what a flat interpreter loop looks like when it is *structurally*
busy rather than algorithmically wrong.

## 2 — The model census, and the surprise inside it

```
chars                3461
models               3342   (0.966 per char)
distinct objects      561   ← interning already shares 83% of them
single-char value_str 1810   = 54% of all models
```

Two things fall out. **Model allocation is already largely solved** — interning
collapses 3,342 references to 561 objects, so the cost is the per-character
*loop*, not the objects. And **54% of models are one character each**, produced
by rules like `nl-tail ::= [\x21-\x3C…]` referenced as `nl-word ::= nl-tail+`:
a value_str rule under a quantifier builds one model per repetition.

That is exactly the "structural model-count cut" this effort's prior art
nominated as the route to 30–50%. So it was worth pricing.

## 3 — The ceiling prototype, and the negative result

Rewrote the grammar so those single-char rules are inlined as char classes —
same language, different model shape (a text field instead of N models). Not a
proposal; a **bound** on what the model cut can buy:

```
baseline   5.305 µs/char   3342 models
inlined    4.450 µs/char   1789 models
           16% faster      46% fewer models
```

**Cutting 46% of the models buys 16%.** The prior art's expectation does not
survive contact with the measurement: model count is not the dominant cost, and
a structural cut aimed at it has a ceiling well under the 30–50% hoped for.

## 4 — What the time actually tracks

Counting structural work in both variants:

| per char | baseline | inlined | cut |
|---|---|---|---|
| `_enter` (clone entries) | 1.56 | 1.38 | 11% |
| `_complete` | 0.70 | 0.66 | 6% |
| `_match_vstr` | 0.73 | 0.61 | 16% |
| `_run_leaf` | 0.21 | 0.08 | 62% |
| **models** | **0.97** | **0.52** | **46%** |
| **time** | — | — | **16%** |

The 46% model cut moved time 16%; the 11% *entry* cut moved it 16%. **Time
tracks clone entries, not models.** The lever is `_enter` at **1.56 per
character** — every character of vyx traffic passes through more than one rule
frame, because the grammar's lexical layer is built from per-character rules
chained several deep (`nl-text → nl-word → nl-tail → charclass`).

## 5 — The candidate worth prototyping next

**Unit-chain collapse.** `BUILD_DISPATCH` already chases frame-lessly through an
alternation whose every arm is a single unit ruleref, and `OP_VSTR` already runs
terminal-only value_str clones without a frame (which is why `_run_leaf` is only
0.21/char). The gap between those two: a **sequence** clone whose single arm is
one exactly-once ref, whose fold is transparent or pass-through. Entering it
costs a frame push, an item walk and a completion to produce exactly what the
callee produced.

The measurement that sizes it, and the next thing to run: **what fraction of the
5,394 entries per parse are such pass-throughs?** If it is a third, the lever is
worth roughly what the whole model cut was, for no change to the model API —
which the model cut cannot say, since collapsing `nl-tail+` into a text field
changes the generated class surface and is a design decision, not an
optimization.

## 6 — What this says about the 19× gap to antlr

Some of it is not waste. The bench's own header records that lexic returns a
typed model the source is recoverable from, while antlr returns a
`ParserRuleContext` and parsimonious a generic node tree — nobody else gets
semantic actions. The honest read of §4 is that lexic pays ~1.6 rule frames per
character to build that, and the interpreter loop over those frames is the cost.
Closing the gap means fewer frames per character, not a faster frame.

**Do not re-run these:** micro-levers were measured at ~0% here previously;
model-count reduction is now measured at a 16% ceiling for a 46% cut; GC and
operation-count growth were ruled out during the linearity work.
