# Testing Conventions

**When to load:** creating or moving a test file; naming a test for an `__init__.py` module; checking which test commands to run before committing; writing a concurrency or timing test; choosing which phase a test belongs to.

See also: [[architecture]]

---

## Mirror rule

`tests/unit/lexic/` is a structural mirror of `src/lexic/`. Every source file has a paired test file.

```
src/lexic/foo/bar.py          →  tests/unit/lexic/foo/test_bar.py
src/lexic/foo/__init__.py     →  tests/unit/lexic/foo/test_init_foo.py
```

**When a source file is created, moved, renamed, or deleted, the test file gets the exact same treatment in the same commit.** Not optional.

---

## `__init__.py` naming rule

Test files for substantive `__init__.py` modules use **`test_init_<package>.py`**, not `test___init__.py`. This avoids filesystem collision when multiple packages have `__init__.py` tests.

Examples:
- `src/lexic/widgets/__init__.py` → `tests/unit/lexic/widgets/test_init_widgets.py`
- `src/lexic/grammars/widgets/__init__.py` → `tests/unit/lexic/grammars/widgets/test_init_widgets.py`

---

## Commands

```bash
uv run pytest tests/ -q                   # full suite (743 tests + 1 xfail)
uv run pytest tests/unit/lexic/ -q        # unit only
uv run pytest tests/integration/ -q       # integration only
uv run ruff check src/ tests/             # lint
uv run pylint src/lexic/path/to/file.py   # per-file quality gate
```

Always prefix with `uv run`. Never bare `pytest` or `ruff`.

---

## Pre-commit gate

Every task must end with **`tools/run_checks.sh` exiting 0** — it runs the suite plus ruff, pylint and pyright, and it is the gate. Check `$?`: it prints a pylint score (`rated at 10.00/10`) even on runs that exit non-zero, so grepping its output for a happy line will tell you a change is clean when it is not.

Run `tools/auto_fix.sh` first to handle format/isort/lint mechanics before touching code by hand. Property tests drive hypothesis, whose harness retains memory proportional to examples explored — run those under `tools/guarded.sh 8G 600 --` so a runaway allocation is OOM-killed instead of taking the host down.

---

## Test layout for new packages

When creating a new package (e.g. `src/lexic/widgets/`):
1. Create `tests/unit/lexic/widgets/__init__.py` (empty)
2. Create `tests/unit/lexic/widgets/test_init_widgets.py` for `__init__.py` exports
3. Create `tests/unit/lexic/widgets/test_<module>.py` for each source module

---

## The engine parity cluster

`tests/integration/lexic/parity/test_pda_parity.py` is where the two engines are held to
each other. Two tests live there, they own different invariants, and neither
subsumes the other — deleting either loses real coverage.

**The wide differential** runs seeded generated samples over every ground-truth
grammar at the *semantic* bar. It owns fallback behaviour (a `PdaFail` dropping
to the Earley completion), round-trip, and the resolver branch.

**`test_both_engines_build_the_same_model_not_just_the_same_meaning`** owns RAW
model equality — field for field, no comparator that drops anything. The
semantic bar passes whether or not the engines agree, so it cannot be the test
for a requirement that they do; at one point it was hiding 47 of 200 json
inputs where the same characters landed in different `Ws` fields.

Two rules govern the stem lists:

- A stem is excluded only with a **written reason**, in the docstring, naming
  what would have to change to re-include it. An exclusion is a debt, not a
  licence.
- `RAW_PARITY_STARTS` exists because a generation start chosen for breadth is
  not always a start that exercises the path under test. `c.gbnf` generates
  from `statement` for the wide matrix, which reaches its islands — but the PDA
  escapes on every sample from there, so the raw bar compared *zero* inputs and
  its own guard fired. Generating from `declaration` compares 200 of 200.

The trap that shape sets: a parity test can pass because it proved something,
or because it compared nothing. Both look identical in the runner. Any parity
test must assert its own compared-count, and any green that arrives first try
is worth asking what it divided.

---

## The three phases

The suite holds three populations with incompatible execution needs, so
`tools/run_tests.sh` runs them as phases — the same script locally and in CI, so
the two cannot drift.

| phase | population | how |
|---|---|---|
| A | the bulk | parallel under `-n auto`; correctness only, no timing |
| B | the concurrency lane | **serial** |
| C | the timing gates | **serial** |

B and C are serial for the same reason from two directions. xdist
process-parallelism oversubscribes a thread storm and lets the threads
serialise, which both hides races and inflates the clock; and a wall-clock bound
on a saturated machine measures scheduler starvation rather than the parse.

The split is **by marker**, and each lane's `conftest.py` applies its own marker
to everything it collects. A test added to a lane is therefore phased correctly
the moment it exists. Note that a directory `conftest`'s
`pytest_collection_modifyitems` still sees every item in the session — the hook
must filter by path, or the marker lands on the whole suite and the phases
partition nothing.

Registering a marker does **not** require touching `pyproject.toml`:
`config.addinivalue_line` in `tests/conftest.py` is pytest's own route.

---

## Both witnesses, and why each asserts its own identity

Concurrency work runs twice: free-threaded (the real witness) and under
`PYTHON_GIL=1` (the weak one). Two environment guards, both of which FAIL the
session rather than skipping:

- `LEXIC_REQUIRE_FREE_THREADED=1` — refuses to run with the GIL on.
- `LEXIC_REQUIRE_GIL=1` — refuses to run with it off.

The second is not symmetry for its own sake. Without it a matrix can silently
collapse into two identical runs, and a weak witness that is secretly the strong
one proves the same thing twice.

`LEXIC_REQUIRE_CORES=<n>` is asked **only when the GIL is off**. With it off,
one usable worker means a genuinely one-core machine and the lane is vacuous.
With it on, `available_workers()` reports 1 by deliberate engine policy, so the
same reading says nothing about the machine — which is also why the lane's
overlap bar degrades to 1 there rather than pretending to a simultaneity that
build cannot offer.

---

## Concurrency tests that can actually fail

A concurrency test's characteristic failure is passing without ever having
raced. Three devices answer that, and a lane test is expected to carry them:

1. **An overlap witness.** Every race records the most workers in flight at
   once and refuses a result whose peak says the work was effectively
   sequential.
2. **Value-carrying payloads.** Each thread's document encodes its own index, so
   a leak between threads is a wrong *string*, not merely a wrong count.
3. **A harness self-test with a guaranteed-failing control** — work that is
   deliberately unsafe, arranged so the lost update is forced rather than lucky.
   Without it, a green lane means nothing.

A wedged worker is a **failure, not a hang**: threads are joined with a deadline
and the timeout is an assertion.

Two traps worth knowing before writing one:

- **Instrumentation can suppress the bug.** Anything that retains the objects
  under test pins them, and pinning stops address reuse — which is the mechanism
  behind a whole class of identity defects. Carry a control showing the symptom
  still reproduces, or the probe is measuring a world without it.
- **`id()` is unique only among objects alive at the same time.** `id(object())`
  names an address that is free again on the next line, and CPython hands it
  straight back. Hold the object.

---

## The guarded runner

`guarded()` runs a callable in a forked child under two bounds:

- **CPU time, not wall.** What these gates catch is runaway or exponential work,
  and that is a CPU property — an exponential enumeration burns any budget
  whatever else the machine is doing, while a merely descheduled process burns
  none. `RLIMIT_CPU` kills with SIGXCPU at the soft limit and SIGKILL a second
  later, so the parent reads both as the same verdict. Wall clock survives only
  as a generous hang backstop.
- **Memory as a BUDGET over the child's inherited size**, not an absolute cap.
  An absolute cap measures the parent's allocation history: a fresh interpreter
  is already over a gigabyte of virtual size, so the cap can be exceeded before
  the guarded work allocates a byte.

It calls `reset_pools()` before forking. A forked child inherits every lock in
whatever state its owning thread left it, and only the forking thread exists on
the other side — so a lock held by a pool worker at fork time is held forever in
the child. Releasing the pools first makes the parent single-threaded at that
moment.
