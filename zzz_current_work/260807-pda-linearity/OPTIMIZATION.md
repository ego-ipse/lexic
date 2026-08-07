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

---

## 7 — The entry census, and a concrete lever

§5 asked what fraction of the 5,394 entries per parse are pass-throughs.
Classifying every one by clone shape:

```
entries per parse: 5394  (1.56/char)

  1905  35.3%  sequence: 1 arm, several items      real work
  1396  25.9%  alternation: 1 arm, 1 unit ref      ← PASS-THROUGH
   638  11.8%  alternation: 2 arms
   551  10.2%  dispatch: 2 arms                    already frame-less
   367   6.8%  alternation: 3 arms
   222   4.1%  alternation: 7 arms
```

**26% of all entries are a single-arm alternation over one exactly-once rule
reference.** A `BUILD_ALT` clone passes its matched arm's sub-model straight
through — with one arm there is not even a choice to make. Entering it costs a
frame push, an item walk and a completion to hand back exactly what the callee
produced.

`_convert_dispatch` exists precisely to make such a clone frame-less, and its
own docstring says the conversion is "observationally identical to the frame it
replaces". Every one of those 1,396 entries passes **every documented guard** —
not window-gated, not noise-peek gated, no empty-arm gate, not an attempt clone,
arm is a unit ref, default is absent or a unit ref. Checked at runtime, per
entry, and the tally is unanimous:

```
  1396  NOTHING — should have converted   e.g. 'body-line'
```

### Why this is the lever worth taking

The calibration from §4: an 11% cut in entries moved time 16%, while a 46% cut
in models moved it the same 16%. If a 26% entry cut scales anywhere near the
first ratio, it is worth substantially more than the model cut — and unlike the
model cut it changes **nothing** about the generated class surface, because a
dispatch conversion is by construction observationally identical.

### What is NOT established

**Why** those clones stayed `BUILD_ALT`. The obvious hypothesis — that
`_specialize_calls` rewrites `OP_REF` to `OP_REF1` before the dispatch pass sees
the shape — is wrong: `optimize_program` already runs dispatch conversion first
and its docstring says why ("which must not pre-empt the dispatch pass's
unit-ref shape check"). Somebody already thought of that.

A reachability probe was inconclusive rather than informative:
`all_clones([program.start])` returned **one** clone on this grammar, so either
the optimizer's clone set does not cover these, or `all_clones` has a contract
this probe misread. Not asserted either way — the cause has not been measured,
and this document's rule is that a cause is measured before it is claimed.

**The next step is therefore diagnostic, not a fix:** determine what set
`optimize_program` actually iterates for this grammar, and whether
`_convert_dispatch` is called on the `body-line` clone at all. The answer is one
of two shapes — the pass never sees them (a reachability gap) or it sees them
and declines for a reason not in its guards (a shape mismatch at pass time, most
likely `_unit_ref_target`'s `OP_REF`-only test meeting something else). Both are
small fixes; they are different fixes.

---

## 8 — Diagnosed: two causes, and the big one is not a bug

Instrumented `_convert_dispatch` during a real compile. The pass **does** see
these clones — 164 calls over 118 names — so the reachability hypothesis is
dead. (`all_clones` following only `OP_GRP` and never clone references, which
made the earlier probe return one clone, is real but irrelevant here:
`optimize_program` is handed EVERY shell as a root.)

Of the 21 clones that were `BUILD_ALT` at pass time, 9 converted and **12
declined**, for exactly two reasons:

```
  7  attempt (arms tried in order)                       e.g. 'scope-scalar'
  5  gated arm not a unit ref: n=1 kind=OP_VSTR lo=1 hi=1  e.g. 'env-field'
```

### The small one is a real gap

`_inline_value_strs` runs BEFORE `_convert_dispatch` and rewrites a
terminal-only ref to `OP_VSTR`; `_unit_ref_target` accepts only `OP_REF`. So a
single-arm alternation over a value_str rule is disqualified by an
optimization — the same class of pass-ordering hazard `optimize_program`'s
docstring already guards against for `OP_REF1`, but unguarded for `OP_VSTR`.
Five clones, and by the runtime census only **52 entries per parse (1%)**.

### The big one is deliberate, and my §7 read was wrong

**Correction to §7.** I reported 1,396 entries (26%) as pass-throughs that
"should have converted", checking the guards against each clone's FINAL state.
That was the wrong state to check: those arms read `OP_REF1`, which
`_specialize_calls` produces AFTER the dispatch pass. At pass time they were
`OP_REF` — and they declined on `attempt`, not on shape. The 1,396 are the
**seven attempt clones**, where dispatch is excluded on purpose: an attempt
clone tries its arms in order with rollback, which a lead-char dispatch cannot
express.

So the honest sizing is: 1% is an ordering gap worth fixing cheaply, and 26% sits
behind a deliberate exclusion.

### What remains genuinely open

A single-arm attempt clone has **no arm choice to try**. `_clone_shape` already
recognises this shape — "a single-gated-arm attempt rule … has no arm choice to
try — its licensed loops carry the whole licence in their gates, so it runs as
an ordinary clone" — yet these seven carry a non-``None`` `attempt`, so
something is classifying them as multi-arm at spec time and single-arm by the
time the program runs (arm dropping in `compile_arms` is the obvious suspect,
and is NOT verified here).

That is the question worth taking next, and it is the engine owner's call
rather than a mechanical fix: **if a clone reaches the runtime with one arm and
an attempt marker, is the marker still earning anything?** If not, 26% of
entries collapse. If it is — if the marker carries loop licences independent of
arm count — then this lever is smaller than it looked and §4's conclusion
(time tracks entries) needs a different way to cash out.

**Method note, since it cost a wrong conclusion:** a compile-time pass must be
diagnosed at pass time. Reading the artefact afterwards shows you the state
three passes later, and every op-code specialisation in between rewrites the
evidence.
