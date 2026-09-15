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

On the remote the gate runs as one `compare.py` job per grammar, each
uploading its `--json` verdicts; `aggregate.py` reads them back, applies the
same rule, and writes the job summary — a grammar whose job never reported
and every `slower` row come first, every row in one table below them.

`regression.py` is structure, and it is what the pre-commit hook runs. A hook
cannot reserve a quiet machine, so it proves the rows are still the rows and
times nothing.

## The local tier

`quick.py` answers one question — did this change move anything on a paid path
it can reach? — and it answers it for every row it selects. It is not a cheaper
sweep of the roster. It is the gate's own rule, over the gate's own control
envelope, applied to a smaller set of rows and a stated budget.

```bash
uv run python -m tools.benchmark.quick --base-root ../base --base-rev HEAD~1
```

**The rows come from the diff.** `git` says what changed — tracked files and
untracked ones, because a module written and not yet added is exactly the
change whose rows most need measuring — and `scope/paths.py` maps each changed
path to the seats whose paid path it sits on. A change under `parsing/pda/`
selects the predictive seats and the two folding variants that are also the
PDA; one under `parsing/parallel/` selects the threaded seats; one under `ir/`
or `compile/` selects everything. A path under the package that the table does
not name selects everything too, which is the safe direction: minutes are
cheaper than a regression nobody saw. A change outside the package selects
nothing, and the run says so and exits 0.

`--only` and `--grammars` **narrow** that selection. Widening it is refused: a
reading on a row the change cannot reach answers nobody's question, with budget
the reachable rows needed.

**The budget is process pairs, and the run prints what the selection costs
before it starts.** The default budget is exactly that cost — `MIN_PAIRS` for
every selected row — so a default run measures every row at the count below
which the gate decides nothing. `--budget` caps it, and a row the cap cannot
afford is printed with zero pairs and the reason rather than dropped from the
table; a row missing from a table reads as a row that did not matter.

**Spare budget goes where it can buy an answer.** Unresolved rows are funded in
descending distance from 1.0 — the row most likely to be a regression is the
one that looks most like one — but only where the pairs the row would need fit
what remains. A row needing more than that keeps its projection instead.

**No row is left saying nothing.** Every unresolved row is reported with the
pair count that would settle it, projected from its own per-pair spread. That
is the difference between "cannot tell" and "not at this budget, and here is
the count that would": one is a dead end, the other says whether to reserve a
quiet machine or to stop looking. A row needing about forty pairs is worth
another run; one needing four hundred has an effect smaller than the host can
see, and no amount of rerunning changes that.

**The words are the gate's** — `ok`, `slower`, `faster`, `unresolved` — because
the rule is the gate's, and a run exits 1 on `slower` exactly as `compare.py`
does. An unresolved row never blocks: it has measured no slowdown, only that
this host could not separate the arms within the pairs it was given.

The threaded seats stay opt-in behind `--mt`. They cannot share the machine, so
their processes run end to end; a run without the flag says how many reachable
threaded rows it left out.

What does not change is the observation: the same worker, the same rounds, the
same row contract, and the same byte-identical control beside every candidate
pair. That control IS the null arm, and its median is printed per schedule
beside the median row envelope.
