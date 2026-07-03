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

Every task must end with `uv run pytest tests/ -q && uv run ruff check src/ tests/` green before commit. Run `tools/auto_fix.sh` first to handle format/isort/lint mechanics before touching code by hand.

---

## Test layout for new packages

When creating a new package (e.g. `src/lexic/new_codegen/`):
1. Create `tests/unit/lexic/new_codegen/__init__.py` (empty)
2. Create `tests/unit/lexic/new_codegen/test_init_new_codegen.py` for `__init__.py` exports
3. Create `tests/unit/lexic/new_codegen/test_<module>.py` for each source module
