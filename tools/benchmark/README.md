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

## The preliminary tier

`quick.py` is the gate's cheap neighbour, for a tree that will change again
before it lands. It gives a DIRECTION over the rows a change can reach, in
minutes rather than a morning.

```bash
uv run python -m tools.benchmark.quick \
  --base-root ../base --only lexic-pda lexic-lex --grammars csv json \
  --lanes 4 --json quick.json
```

Three things separate it from the gate, and each is a deliberate loss. **Scope**
— only the seats and grammars asked for, both axes intersected, because what
makes a row worth measuring is a fact about the change and the caller is what
knows it. An omitted axis means all of it; a name the roster does not carry is
refused rather than quietly selecting nothing. **Budget** — four process pairs
per row, never grown, so the cost of a run is known before it starts. **Schedule**
— sequential rows are single-threaded processes and several run at once on their
own cores; threaded rows own the machine one at a time, because their reading IS
latency and a co-tenant is indistinguishable from a regression.

**The threaded seats are opt-in, behind `--mt`.** They are the expensive half by
a wide margin, and they are expensive for a reason no scheduler can remove: they
cannot share the machine, so their processes run end to end. A run without the
flag says how many threaded rows it left out; a run with it prints how many
worker processes they will start and roughly how long that is, before starting
any of them. They also take three pairs rather than four, which is the whole
difference between a threaded half a caller will wait for and one they will not.
Three is odd, so a fixed first-slot cost lands in a threaded row's published
ratio at a third of its size; the run prints that artefact beside the rows
rather than leaving it to be assumed away.

Measured on a sixteen-core host, nine grammars, against a base one commit back:

| Half | Rows | Pairs each | Worker processes | Wall |
|---|---|---|---|---|
| Sequential, `--lanes 4` | 36 | 4 | 576 | 354 s |
| Threaded, alone, `--mt` | 18 | 3 | 216 | up to ~22 min |

The same rows through `compare.py` cost about 39 minutes sequential and about
60 minutes threaded. A worker process itself costs 0.95 s sequential and 1.29 s
threaded on the smallest roster grammar, 3.17 s and 3.88 s on the largest; the
threaded ceiling above is the 6.05 s a whole loaded gate run averages, which is
the number `--mt` prints because a caller deciding against a wait should be
given the one that cannot surprise them.

What does not change is the observation: the same worker, the same rounds, the
same row contract, and the same byte-identical control beside every candidate
pair. That control IS the null arm, taken under whatever company the lanes
created, and its median is printed per schedule beside the median row envelope.
A floor wider than the gate's is the signal to run fewer lanes.

**The default lane count is unsettled, and it is deliberately conservative.**
Four lanes were measured and cost more noise than the gate pays: over 36 rows
the control arm's per-pair spread read 0.0431 against the gate's 0.0277 on the
same rows, run one at a time. A calibration at one, two and four lanes was then
run to settle it and did not: the spreads came out 0.2464, 0.0892 and 0.0918
against the gate's 0.0249, with ONE lane the worst arm — and one lane is the
gate's own schedule, so that statistic was reading something other than
concurrency. A few control pairs dominate it, two byte-identical processes
reading as far as 1.84x apart. So `--lanes` defaults to one, the only count
whose floor is not in question, and the concurrency this tier is built for is
available by asking for it. Settling the default needs lane counts interleaved
pair by pair rather than run in blocks, more than four pairs per arm, and a
dispersion statistic declared in advance and robust to those outliers.

**Its words are not the gate's.** A row leans slower, leans faster, is flat or is
inconclusive; PRELIMINARY travels through the text output and the JSON, and the
run always exits 0. Nothing here decides what lands.

`flat` is a stricter statement than the gate's `ok`, and it carries two
conditions. Both edges of the interval must sit inside the row's envelope — the
gate asks only whether a row is slower, so it passes on its interval's top
alone. And the row's own envelope must be no wider than 1.5 times the schedule's
median row envelope, because a row whose noise is anomalous for the run has
separated nothing whatever its interval says. The multiple applies to the noise,
the envelope's excess over 1.0, so 1.5 against a typical 1.0338 admits up to
1.0507. A bare median would bar half the field by construction, since half of
any run's rows sit above it, and the rule is for outliers rather than for the
ordinary upper half.

That second condition is why `flat` is decided after the whole schedule is
measured rather than a row at a time, and why the progress lines print a ratio
and no word. The ceiling is taken per schedule: a threaded row's envelope runs
several times a sequential one's, so one median over both would license and
condemn the wrong rows.

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

A cell's VALUE is a finite number, `refuses` (this seat cannot take the row's
language) or `unmeasured` (it can, and the run obtained no figure it stands
behind). Those are different facts, so a cell holding either says which in its
record's `note`, and a cell holding a number carries no note at all. The note
is bounded — one Lark reduce/reduce verdict runs to 70 KB of the same
collision restated per terminal, and the head is the reason. `regression.py`
checks that pairing over the whole file: refusals once published the word with
`note: null`, and every per-cell check passed, because none of them read a
value beside its record.
