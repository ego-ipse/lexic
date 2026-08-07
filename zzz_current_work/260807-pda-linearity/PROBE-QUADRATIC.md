# The PDA is quadratic on pipe-heavy vyx packets — 73 s for 11 KB

Found while pricing solution D's economics (`probes/economics.py`). Unrelated to
D, bigger than D, and **pre-existing** — not caused by the relaxation fix.

## The measurement

A valid vyx packet whose body is repeated `deps=^ref tags=|a|b|c` lines. No
fork, no fallback, no resolver — this is the **predictive runtime succeeding**:

```
   8 lines     191c   PDA ok   0.020s
  32 lines     719c   PDA ok   0.294s     ×3.8 chars → ×15 time
 128 lines    2832c   PDA ok   4.632s     ×3.9 chars → ×16 time
 512 lines   11281c   PDA ok  73.393s
```

×4 input → ×16 time. That is n², in the engine whose whole purpose is to be
linear.

## The cause

`_probe` — "one side of a boundary, run to end-of-input on a copied stack"
(`kernel/decisions.py`). Counting calls and their share of wall clock:

```
   8 lines    total   0.022s   _probe calls   34   in probes  0.019s (86%)
  32 lines    total   0.308s   _probe calls  130   in probes  0.280s (91%)
 128 lines    total   4.828s   _probe calls  514   in probes  4.455s (92%)
```

**Probe count grows linearly with input (~1 per pipe line) and each probe runs
to end-of-input.** Linear probes × linear cost each = quadratic, and 92% of the
run is inside them. The mechanism is doing exactly what it is documented to do;
the cost model is what nobody priced.

## Not a regression

A/B against the pre-fix relaxation (`variants.apply("unconditional")`, injected
via `sitecustomize` so it lands before anything imports lexic):

| | pre-fix | post-fix |
|---|---|---|
| vyx pipe-heavy, 128 lines | 4.635 s | 4.632 s |
| `tools.benchmark.bench --only gbnf-meta`, lexic-pda | 5.508 µs/char | 5.471 µs/char |

Identical within the benchmark's own 2.80% noise floor, and the small difference
runs the *wrong way* for a regression. The relaxation fix neither caused this
nor moved the meta row.

## Why this outranks solution D

D buys a bounded ×7–8 on forked constructs. This is an unbounded n² on the
product grammar's own common syntax, on the path that already works. An 11 KB
packet — not a large one for an agent protocol — costs 73 seconds.

Two things to check before treating the diagnosis as complete:

- **Is the probe's end-of-input run necessary?** Its stated reason is that a
  boundary's viability can depend on an enclosing frame's continuation (the
  severed form mis-resolved gbnf-meta's rule terminator, per `_attempt_run`'s
  note). That argues the probe must see the *true* continuation — not that it
  must run it to EOF. A bounded window with a soundness argument, or a memo
  keyed on something that is actually sound, is the obvious direction.
- **Which grammars pay it.** vyx pipe-lists are one shape; `forkcount.py` and a
  probe-counter across the corpus would show whether this is vyx-specific or
  general to any repeated attempt-gated construct.

## Bearing on D

`probes/economics.py` also settled D's economics, and narrowed its subject:

```
  pipe-heavy   512 lines  11281c   parse 73.393s   island attempt 0.000s   no fork
  dict-heavy   512 lines   7696c   parse  0.403s   island attempt 0.000s ( 0.1%)  BAILS
```

- **Dict-heavy: islanding is essentially free even when it bails** — 0.1% of the
  parse at size, against the 33% seen on a 135-char toy. The review's note-3
  worry does not survive contact with real sizes; the bail case is affordable.
- **Pipe-heavy packets do not fork at all.** The pipe-list forks measured in
  §6 were at `@start value`, parsing a bare value. Inside a packet the
  construct rides the PDA — slowly, per above, but without forking. So D's live
  subject is narrower than the line-level trial implied.

D remains sound and now has affordable economics. It is simply no longer the
most valuable thing in this area.

---

## Can it be made linear? — one route measured dead, one route open

### The cheap shortcut: measured, FALSIFIED

Every verdict on the pipe-heavy input is `TAKE` (66 of 66), which invites the
obvious shortcut: Earley decides split-vs-arm-choice *structurally*
(`is_arm_choice` — families naming ONE arm over different spans are a split with
a defined answer; only families naming DIFFERENT arms are refusable), and the
PDA already computes a structural classification in `_beyond_class`. So:
**are `_ADMITS` boundaries (optional-item viability only) always splits, settled
by "the first slot owns the text", making both probes waste?**

`verdictcensus.py` over the whole suite says no:

```
  3586  ADMITS_HARD (terminator)   → TAKE
   239  ADMITS (optional only)     → TAKE
     4  ADMITS (optional only)     → FORKED      ← falsifies it
  FALSIFIED
```

Four `_ADMITS` boundaries are genuine forks. Skipping the probes there would
commit what the engine currently refuses — the one failure mode this repo does
not accept. The class is not a sufficient statistic for the verdict.

**Side observation, not yet actionable:** `STOP_FORCED` occurs **zero** times in
3,829 verdicts. The stop-probe exists for the gbnf-meta "terminator theft", and
that grammar stopped forking when `relax_non_semantic` was narrowed — so its only
known subject may have been removed. If `STOP_FORCED` is genuinely unreachable
the stop-probe could go, halving the constant (not the asymptotics). "Never
observed in one suite" is weak evidence for "cannot happen"; this wants a
grammar-level argument before anyone deletes a soundness check.

### The route that does work: lockstep with convergence detection

The two probe sides differ **only** in the boundary decision. After a short
distance they reconverge — for a pipe-list, within one element. So:

Drive both sides in lockstep rather than each to EOF, and stop at the first of:

1. **one side dies** → the verdict is forced, exactly as today;
2. **both reach an identical `(pos, stack signature)`** → converged. The stack IS
   the continuation, so identical state at identical position means identical
   future: both complete or neither does, and the verdict reduces to the values
   accumulated *before* convergence. This is an invariant, not a heuristic;
3. **a step budget is exhausted** → fall back to today's run-to-EOF comparison.

Escape (3) is what makes it safe to land incrementally: worst case is exactly
today's behaviour and today's answer, so correctness cannot regress — only the
budget's tuning is at stake. With convergence typically a few characters away,
each boundary becomes O(1) amortised and the whole parse linear.

What it needs, and why it is not a small change: `_drive()` runs to completion,
so lockstep needs a step-wise or bounded drive; convergence needs a cheap stack
signature (frames' item indices, counts and sink lengths — not a deep compare);
and the value comparison moves from "root values at EOF" to "values accumulated
to the convergence point", which must be shown equivalent. Gate is the parity
differentials, as ever.

---

## Item 1, first answer: it is NOT vyx-shaped — it is `ws`-shaped

`verdictcensus.py`, extended to tally which RULE pays the two run-to-EOF probes
(answerable now that `FlatClone` carries its name — PLAN item 4), over the whole
suite:

```
── which rules pay the run-to-EOF probes ──
  4736  ws
   237  envelope
    48  m-imports
     6  pipe-list-item3
```

**A whitespace rule pays 94% of them.** Not vyx's pipe-lists — those are 6 of
5,027. `ws` is the most ordinary construct a grammar can have, and it appears in
five of the ten ground-truth grammars.

That reverses the framing this document opened with. The quadratic is not a vyx
curiosity reachable only by an 11 KB pipe-heavy packet; it is what any grammar
with a noise rule in a repeated position pays, and vyx merely had a document
long enough to make it visible. The pipe-heavy measurement was the symptom that
happened to be measurable, not the cause worth fixing.

**Consequences for the plan:**

- The generality question in PLAN item 1 is answered: **general**. The lockstep
  fix (item 2) is a lexic priority, not a vyx footnote.
- The prize is larger than the 73 s figure suggested, because it is paid by
  every grammar with whitespace — just usually on inputs too short to notice.
- The second half of item 1 (the `STOP_FORCED` reachability argument, which
  could halve the work) is now MORE worth doing before item 2, not less.

**Caveat, stated:** this counts fork *verdicts*, not their cost, and the suite's
inputs are short. It establishes which rules reach the expensive path and how
often — not how much each one costs at size. `probes/probecount.py` was written
to measure cost per grammar but `lexic.generate`'s depth budget produces inputs
of 3–43 characters, far too short to show growth; it needs per-grammar growth
templates (the `scaling.py` shape) before it can answer the cost half.
