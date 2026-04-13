---
id: S01
parent: M001
milestone: M001
provides:
  - ["build(grammar_path) -> dict[str, type] — live Pydantic class dict with SOLID inheritance hierarchy", "build_file(grammar_path, output_dir) -> Path — file-writing variant for inspection", "SOLID pattern: AlternativeNode rules → abstract BaseModel base + typed concrete subclasses", "SequenceNode rules → Pydantic models with typed fields", "Single-ref rules → subclass or BaseModel with value field", "12-test pytest suite covering all 6 ground-truth grammars"]
requires:
  []
affects:
  []
key_files:
  - ["src/codegen.py", "tests/test_codegen.py", "tests/__init__.py"]
key_decisions:
  - ["build() returns live dict[str, type] (not Path); file-writing variant renamed to build_file() for backward compat"]
patterns_established:
  - ["from __future__ import annotations must be the first line of any exec'd code string — required for forward references in circular dependency graphs (json_ws Value↔Object)", "resolve() from llguidance renames 'root' to 'start' in-place — must be immediately reversed after calling resolve()", "model_rebuild() calls must be emitted after all class definitions in the generated code string, not inline", "Terminal rules (r.rule_is_terminal == True) are skipped; refs to terminals produce str fields"]
observability_surfaces:
  - none
drill_down_paths:
  - [".gsd/milestones/M001/slices/S01/tasks/T01-SUMMARY.md", ".gsd/milestones/M001/slices/S01/tasks/T02-SUMMARY.md"]
duration: ""
verification_result: passed
completed_at: 2026-04-12T18:32:06.356Z
blocker_discovered: false
---

# S01: GBNF to Pydantic Model Generator

**build() delivers live Pydantic class dicts with correct SOLID inheritance for all 6 ground-truth grammars — 12/12 tests pass**

## What Happened

S01 had two tasks: implement `src/codegen.py` with a SOLID Pydantic model generator, and write a pytest suite covering all ground-truth grammars.

**T01** discovered that `src/codegen.py` already contained the complete SOLID inheritance generator (`_build_class_code`, `_topo_sort_rules`, `generate`, `_parse_grammar`) — but the public API was misaligned: `build()` wrote a file and returned a `Path`, while a separate `load()` function executed the generated code and returned live classes. The task contract requires `build() -> dict[str, type]`. Rather than rewriting from scratch, the fix was surgical: swap the function bodies so `build()` does what `load()` did (exec + return class dict), rename the old file-writer to `build_file()`, and drop `load()` entirely. Tests in `tests/test_codegen.py` were updated to match (`load()` → `build()`, file-write test → `build_file()`).

**T02** confirmed the test suite was already complete from T01's execution. Running `uv run pytest tests/test_codegen.py -v` collected 12 tests: json_ws SOLID hierarchy (ObjectValue/ArrayValue bases, Root→Object subclass), field type sanity (Object has pydantic fields, ObjectValue has Object-typed field), parametrized parse of all 6 .gbnf files via `glob('*.gbnf*')`, arithmetic structure (Root key present), module naming (`__module__ == 'src.generated.json_ws'`), and abstract base validation (Value has no required fields). All 12 passed in 0.13s.

Key patterns established: `from __future__ import annotations` must be the first line of any code string passed to `exec()` to handle forward references in circular dependency graphs (e.g., json_ws Value↔Object). `resolve()` from llguidance renames 'root' to 'start' in-place — must be reversed immediately after (`raw_rules['root'] = raw_rules.pop('start'); raw_rules['root'].name = 'root'`). `model_rebuild()` calls must be emitted after all class definitions, not inline, to handle forward refs in pydantic v2.

## Verification

Ran slice demo command: `uv run python -c "from src.codegen import build; mods = build('resources/ground_truth/json_ws.gbnf'); assert mods['ObjectValue'].__bases__ == (mods['Value'],); assert mods['ArrayValue'].__bases__ == (mods['Value'],); assert issubclass(mods['Root'], mods['Object']); print('PASS:', sorted(mods.keys()))"` — exit 0, printed PASS with 9 classes.

Ran full test suite: `uv run pytest tests/test_codegen.py -v` — 12/12 passed in 0.14s across all 6 ground-truth grammars (arithmetic, c, chess, japanese, json_ws, list).

## Requirements Advanced

- R004 — build() processes all 6 ground-truth grammars without any grammar-specific logic — parametrized test confirms this

## Requirements Validated

- R001 — mods['ObjectValue'].__bases__ == (mods['Value'],), mods['ArrayValue'].__bases__ == (mods['Value'],), issubclass(mods['Root'], mods['Object']) — all assert-verified. 12/12 pytest tests pass across all 6 ground-truth grammars. AlternativeNode rules produce abstract base + typed concrete subclasses with correct __bases__.

## New Requirements Surfaced

None.

## Requirements Invalidated or Re-scoped

None.

## Deviations

["T01 found src/codegen.py already had the full SOLID generator; instead of rewriting, made a targeted API swap: build()↔load() bodies, renamed old build() to build_file(), dropped load(). T02 found the test suite already written by T01; confirmed all 12 pass with no additional changes."]

## Known Limitations

["json_arr.gbnbf (typo filename) is absent from resources/ground_truth/ — only 6 of the 7 expected grammars are present; parametrized tests collect whatever is present", "build_file() exists but has no test coverage — only build() is tested"]

## Follow-ups

["S02 should call build() to get model classes before constructing the Lark Earley parser — the dict[str, type] return is designed for this import pattern", "Forward intelligence: see S01-SUMMARY.md Forward Intelligence section for llguidance resolve() gotchas"]

## Files Created/Modified

- `src/codegen.py` — build() returns dict[str, type] of live Pydantic classes; build_file() is the renamed file-writing variant
- `tests/test_codegen.py` — 12-test pytest suite covering SOLID hierarchy, field types, all-grammars parametrize, module naming, abstract base
- `tests/__init__.py` — Empty package marker for pytest discovery
