# Testing Conventions

**When to load:** creating or moving a test file; naming a test for an `__init__.py` module; checking which test commands to run before committing.

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
- `src/lexic/new_codegen/__init__.py` → `tests/unit/lexic/new_codegen/test_init_new_codegen.py`
- `src/lexic/grammars/new_gbnf/__init__.py` → `tests/unit/lexic/grammars/new_gbnf/test_init_new_gbnf.py`

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

When creating a new package (e.g. `src/lexic/new_codegen/`):
1. Create `tests/unit/lexic/new_codegen/__init__.py` (empty)
2. Create `tests/unit/lexic/new_codegen/test_init_new_codegen.py` for `__init__.py` exports
3. Create `tests/unit/lexic/new_codegen/test_<module>.py` for each source module

---

## The engine parity cluster

`tests/integration/test_pda_parity.py` is where the two engines are held to
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

Two things about the stem lists are load-bearing:

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
