# Benchmark tools

The public report, the row-contract gate, and the same-machine A/B comparison
live here. Supporting concerns are split by responsibility so benchmark code
obeys the same size and folder limits as production source.

## The invariant

**Row definitions are held constant by NAME. Each arm's worker code is its own
tree's.**

The older invariant was that one harness stays fixed while `lexic` is swapped
underneath it. That cannot survive a public rename, by construction: the harness
has to name the API it drives, so the moment a release renames one, the harness
can only run against one of the two trees. Adding a fallback would make every
future measurement a comparison of two code paths.

So each revision runs its own `tools/benchmark` against its own `src`, from its
own checkout root. What is held constant is the ROW — grammar, declared
directives, document, engine noun, core request — and the comparator refuses two
arms whose row contracts differ before it times anything.

Running a historical revision with its historical benchmark measures that
baseline. It is not support for that revision's API in current Lexic.

Both arms still get the corrected measurement protocol, because comparing a
corrected arm against an uncorrected one measures the harness rather than Lexic.
`measurement/copy.py` installs it and rewrites the one name the rename moved; each
copy keeps only its native reference and neither `src` tree is touched.

## What a number here costs

- **One process per observation, start to exit.** No preparation cohort. A
  worker that is merely "not yet timed" still compiles grammars, runs fidelity
  parses and holds artefacts, and doing that beside a timed parse contaminates
  cache, allocator and thermal state.
- **The collector stays enabled** during every timed pass, and the contract
  records that it did. Production does not disable it.
- **Both clocks, always.** Sequential rows are judged on process CPU; threaded
  rows are judged on wall and report aggregate CPU beside it, because a latency
  win paid for with far more total CPU is a different fact.
- **Directives are declared per case**, never derived from what the engine
  finds eligible or fast. A licence that drops marks until a row stops
  regressing hides the regression the row exists to expose.

## The gate

`compare.py` is acceptance. It runs alternating base/head process pairs against
a byte-identical control whose order flips independently, then compares the
candidate's paired log-ratio interval to the control's envelope. There is no
fixed percentage allowance: what counts as noise is what this machine produced,
this session, under the identical protocol. A row that will not settle within
the pair bound is reported unresolved rather than forced into a median.

`regression.py` is structure, and it is what the pre-commit hook runs. A hook
cannot reserve a quiet machine, so it proves the rows are still the rows and
times nothing.

`lexic_baseline.json` is fingerprinted trend data for the rendered README. It is
neither a cross-machine gate nor an approval channel.
