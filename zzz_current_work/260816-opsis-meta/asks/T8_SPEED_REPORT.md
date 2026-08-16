# T8 — the per-complete speed lever: measured, implemented, REVERTED

**Negative result, recorded honestly.** The cut I proposed does not pay. Both
shapes of it measured SLOWER than the code they replaced, on every benchmark
grammar, by margins well outside the noise floor. Nothing shipped; the tree is
byte-identical to `ffc9992` for `src/`.

The two things worth keeping from this are the measurements themselves: the
seam is already tight (the mechanism the lead named for value_str **is already
implemented**), and the remaining allocation lever has a measured ceiling of
1-2%.

---

## Baseline (the harness, unmodified, `--rounds 7`, guarded)

`tools/benchmark/bench.py` as-is. Only lexic's own row is reproduced here; the
competitor columns are unchanged and irrelevant to a delta.

| grammar | chars | lexic-pda µs/char | noise floor |
|---|---|---|---|
| arithmetic | 4,000 | 3.381 | 2.58% |
| csv | 12,539 | 0.894 | 2.76% |
| json | 2,403 | 2.161 | 2.59% |
| gbnf-meta | 1,377 | 5.585 | 1.59% |
| abnf-meta | 2,020 | 6.211 | 0.69% |
| vyx | 3,461 | 5.034 | 1.43% |

## What the seam actually does (measured before writing anything)

Intern-memo traffic per input character, and the hit rate, by tier. `record` =
`build_fast`/`build_validated` (a sequence clone), `vstr` = `build_vstr`.

| grammar | lookups/char | hit rate | record hit | record miss | vstr hit | vstr miss |
|---|---|---|---|---|---|---|
| arithmetic | 1.77 | 74.1% | 2,278 | 1,822 | 2,963 | 13 |
| csv | 0.44 | 23.9% | 0 | 2,860 | 1,317 | 1,322 |
| json | 1.21 | 82.5% | 772 | 380 | 1,630 | 129 |
| gbnf-meta | 1.45 | 70.6% | 391 | 449 | 1,012 | 136 |
| abnf-meta | 1.45 | 79.5% | 349 | 485 | 1,978 | 114 |
| vyx | 1.65 | 89.0% | 1,204 | 492 | 3,868 | 134 |

**Finding 0, which reshaped the task: `build_vstr` is already key-first.**
`runtime/build.py:339-365` builds the key `(ctor, span)` from the matched span
and consults the memo BEFORE constructing anything — the parts dict exists only
on a miss. The value_str/noise tier the brief targeted is already exactly what
the brief asked for, and it is also where most of the traffic is (json 1,759
vstr lookups against 1,152 record; vyx 4,002 against 1,696). So the only
available cut was the RECORD tier, whose hits run 0.17-0.57 per char.

## What I implemented, and what it measured

`build_fast` (`build.py:172-203`) walked the fields once, building three things
— the parts dict (seeded from a defaults copy), the supplied-key set, and the
intern key — and only then consulted the memo. On a hit the first two were
thrown away. Two ways to defer them, both implemented and both measured in one
interleaved in-process run (25 and 21 rounds, arms swapped between rounds so
machine state moves them together, product equality asserted per grammar):

- **SPLIT-A** — one pass produces the key plus a values list; a miss assembles
  parts/keys from the values without re-slicing. (This is the one I wrote into
  the tree and then reverted.)
- **SPLIT-B** — a key-only pass; a miss re-runs the original one-pass function.

| grammar | OLD µs/char | SPLIT-A | SPLIT-B | A vs OLD | B vs OLD |
|---|---|---|---|---|---|
| arithmetic | 3.359 | 3.588 | 3.487 | **+6.83%** | **+3.81%** |
| csv | 0.876 | 1.027 | 0.979 | **+17.18%** | **+11.75%** |
| json | 1.973 | 2.039 | 1.998 | **+3.33%** | **+1.28%** |
| gbnf-meta | 5.075 | 5.267 | 5.216 | **+3.79%** | **+2.77%** |
| abnf-meta | 5.976 | 6.159 | 6.165 | **+3.07%** | **+3.16%** |
| vyx | 5.052 | 5.103 | 5.016 | **+1.01%** | −0.71% |

Every cell is a regression except vyx/SPLIT-B at −0.71%, which is inside its
noise floor. `equal=True` on every row: the swap was semantics-preserving, so
what differs is only cost.

**Why it loses, plainly.** `dict(clone.defaults)` and `set()` are single C-level
operations on small containers. Any Python-level bookkeeping that defers them —
an extra list, an extra loop, a `zip` with tuple unpacking, or a second pass —
costs more than the thing it avoids. The miss-heavy case makes it worst: csv
has **zero** record hits, so it pays the deferral on every build and gains
nothing, which is the +17% column.

## Finding #2 (the eager ENDS allocation): measured ceiling 1-2%, not attempted

Every frame push allocates `[0] * arm.n` (`kernel/kernel.py:492, 497, 500`)
though only span-reading clones read it back (measured earlier: 1 of 39 fold
rules on json, 0 of 15 on markdown). I measured the CEILING before building
anything — frame pushes per char × the cost of that allocation at the measured
size mix, against the parse's own µs/char:

| grammar | pushes/char | `[0]*n` ns | µs/char | ENDS ceiling |
|---|---|---|---|---|
| arithmetic | 0.77 | 80.8 | 3.620 | **1.72%** |
| csv | 0.12 | 79.4 | 1.008 | 0.97% |
| json | 0.35 | 82.0 | 2.138 | 1.36% |
| gbnf-meta | 0.99 | 80.3 | 5.355 | 1.48% |
| abnf-meta | 1.37 | 80.5 | 6.173 | **1.79%** |
| vyx | 0.68 | 81.0 | 5.101 | 1.08% |

That is the ceiling if the allocation became FREE, which it cannot — a shared
scratch list still costs a size lookup. Against noise floors of 0.69-2.76% the
whole effect is at or under the floor on four of six rows. The change would
need a new flag on `FlatArm`/`FlatClone`, a shared-scratch correctness argument
(the driver's write must stay branch-free per its own docstring), and an
analysis of `frames_copy`'s probe copies sharing that scratch. **It does not
carry its weight**, so I did not build it.

## Post-change table

`src/` is reverted, so the "post" run is the same tree as the baseline. It is
worth printing anyway, because the difference between two harness runs of an
IDENTICAL tree is the honest measure of what the harness can resolve:

| grammar | baseline | after (same tree) | drift |
|---|---|---|---|
| arithmetic | 3.381 | 3.406 | +0.7% |
| csv | 0.894 | 0.910 | +1.8% |
| json | 2.161 | 2.151 | −0.5% |
| gbnf-meta | 5.585 | 5.516 | −1.2% |
| abnf-meta | 6.211 | 6.256 | +0.7% |
| vyx | 5.034 | 5.219 | +3.7% |

Cross-process drift reaches 3.7% on an unchanged tree — larger than most of the
effects under discussion. That is precisely why the verdict above rests on the
in-process interleaved A/B and not on two harness runs, and it is worth
remembering the next time a 2% harness difference looks like a finding.

## What I did not touch, and why

- **Model count** (the one 30-50%-shaped lever) is out of scope by the brief:
  cutting it changes what a parse returns, and that remains a product decision.
- **Frame pooling / flat-int frames**: unmeasured, large surgery on the hot
  path. Given three measured negatives on the neighbouring seam, I would want a
  ceiling measurement first — the same discipline that killed #2 in ten minutes.
- **The memo key tuple** (`(ctor, key_parts)`, allocated 0.44-1.77 times per
  char): a nested memo would trade a tuple allocation for a dict lookup. Same
  shape of bet as the two that just lost; I did not take it.

## Gates

Tree byte-identical to `ffc9992` for `src/`, `tests/`, `tools/`. The harness was
not modified. No commits, no suppressions, no `pyproject.toml`, no wiki or
CLAUDE.md change (no module added). `tools/run_checks.sh` EXIT=0 and the full
suite green on the reverted tree — the semantic gate never had anything to
catch, because every A/B arm asserted product equality before it was timed.

Probes used and discarded (not in the tree): `/tmp/ab_build.py`, `/tmp/ab2.py`,
and three counting probes run inline.
