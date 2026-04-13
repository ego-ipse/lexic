---
id: T01
parent: S01
milestone: M001
key_files:
  - src/codegen.py
  - tests/test_codegen.py
key_decisions:
  - Renamed old build() to build_file() to preserve file-writing functionality, making the API change backward-compatible for callers that need file output
duration: 
verification_result: passed
completed_at: 2026-04-12T18:08:49.225Z
blocker_discovered: false
---

# T01: Changed build() to return dict[str, type] of live Pydantic classes (SOLID inheritance pattern) and renamed file-writing variant to build_file()

**Changed build() to return dict[str, type] of live Pydantic classes (SOLID inheritance pattern) and renamed file-writing variant to build_file()**

## What Happened

src/codegen.py already contained the full SOLID inheritance generator but with mismatched public API: build() wrote to a file and returned Path, while load() executed and returned live classes. The task contract requires build() -> dict[str, type]. Changed build() to do what load() did (exec generated code, return class dict), renamed the old file-writing build() to build_file(), and removed load() as a separate function. Updated tests/test_codegen.py to use the new names: all load() calls → build(), the file-write test → build_file(), and updated the import line accordingly. The underlying SOLID code generator (_build_class_code, _topo_sort_rules, generate, _parse_grammar) was already correct and required no changes.

## Verification

Ran the slice verification command: `uv run python -c \"from src.codegen import build; mods = build('resources/ground_truth/json_ws.gbnf'); assert mods['ObjectValue'].__bases__ == (mods['Value'],); assert issubclass(mods['Root'], mods['Object']); print('PASS:', sorted(mods.keys()))\"` — printed PASS with 9 classes. Ran full pytest suite: 14 passed in 0.16s.

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | `uv run python -c "from src.codegen import build; mods = build('resources/ground_truth/json_ws.gbnf'); assert mods['ObjectValue'].__bases__ == (mods['Value'],), mods['ObjectValue'].__bases__; assert issubclass(mods['Root'], mods['Object']), mods['Root'].__bases__; print('PASS:', sorted(mods.keys()))"` | 0 | ✅ pass | 800ms |
| 2 | `uv run pytest tests/ -q` | 0 | ✅ pass | 1200ms |

## Deviations

The task plan described implementing build() from scratch; in reality src/codegen.py already existed with the correct SOLID generator logic but wrong public API. Adapted by doing a targeted API rename rather than a full rewrite.

## Known Issues

none

## Files Created/Modified

- `src/codegen.py`
- `tests/test_codegen.py`
