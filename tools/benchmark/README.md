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

Both bounds are even, and so is every count between them: the two schedules
alternate on a period of two, so they sample the first slot equally often only
at an even count, and growth therefore adds a whole period at a time and takes
its verdict at the boundary. At an odd count a fixed first-slot cost leaves
+δ/n in the candidate's mean and −δ/n in the control's — harmless to the
verdict, since the envelope is a magnitude and both sides move together, but
not to the ratio that gets published.

**Only a `slower` row fails the run.** An unresolved row has measured no
slowdown; it has measured that this machine, this session, could not separate
the two arms inside the pair bound. Failing on that makes the gate's answer
depend on how quiet the host happened to be, and the only move it leaves is to
rerun until the noise cooperates — optional stopping wearing a different hat.
The rate is measured, not assumed. Run against ITSELF — both roots the same
checkout, so every pair is byte-identical and no row can truly be slower —
twenty-four rows gave twenty-two `ok`, two `unresolved`, and no `slower` at
all. One row in twelve could not be separated from the noise it was made of,
which under the old rule failed the whole run on code that had not changed.
Unresolved rows print in full — ratio, clock, interval, envelope, pair count —
and the summary says how many there were and that they did not block.

`regression.py` is structure, and it is what the pre-commit hook runs. A hook
cannot reserve a quiet machine, so it proves the rows are still the rows and
times nothing.

`competitors_baseline.json` is the one committed artifact the README renders
from — every seat's medians from a whole-roster `bench --json` run, Lexic's own
rows included. It is neither a cross-machine gate nor an approval channel.

Each `(grammar, seat)` cell carries its own record: the date it was taken, the
rounds behind it, the worker request an mt row rode, and which of the case's
documents it read. That is the granularity `--only` and `--seats` update, so a
run that refreshes one cell cannot restate an untouched one as a measurement it
never was. `engines` holds display metadata and nothing else, and the README's
captions and column headers are derived from the records — a column whose cells
disagree on the worker count is refused rather than labelled with one of them.
