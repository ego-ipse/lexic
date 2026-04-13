---
id: T02
parent: S05
milestone: M001
key_files:
  - src/codegen.py
key_decisions:
  - Case 4 of _sem_name uses parent_cname + to_class_name(node.name) (not the reversed order in the task plan) — this is required by the TermExpr/StatementDataType/ForInitDataType test expectations
  - Task plan used arm.items but SequenceNode attribute is arm.nodes — corrected without blocker
  - RuleRefNode arms in _collect retain existing logic and register in seen_names for dedup tracking
duration: 
verification_result: passed
completed_at: 2026-04-13T19:00:26.011Z
blocker_discovered: false
---

# T02: Rewrote src/codegen.py with camelCase splitting, semantic arm naming (_sem_name), and removed broken src.base import — all 27 tests pass

**Rewrote src/codegen.py with camelCase splitting, semantic arm naming (_sem_name), and removed broken src.base import — all 27 tests pass**

## What Happened

Three surgical fixes applied to `src/codegen.py`:

**Fix 1 — `to_class_name()` camelCase splitting:** Added `re.sub(r'([a-z])([A-Z])', r'\1_\2', name)` before the existing split. This converts `singleLineComment` → `single_Line_Comment` → `SingleLineComment`, `forInit` → `ForInit`, `dataType` → `DataType`, enabling the c.gbnf `SingleLineCommentStatement`/`MultiLineCommentStatement` and `ForInit*` naming to work correctly.

**Fix 2 — `_sem_name()` semantic naming for alternation arms:** Added new `_sem_name(arm, parent_cname, seen)` helper and `_dedup_name()` utility. The four cases handle: (1) bare `RuleRefNode` → `{RefClass}{Parent}` e.g. `ObjectValue`; (2) first alpha `LiteralNode` in a sequence → `{Parent}{Keyword}` e.g. `StatementReturn`; (3) first node is an all-literal `AlternativeNode` → `{Parent}Literal` e.g. `ValueLiteral`; (4) first non-ws `RuleRefNode` in a sequence → `{Parent}{RefClass}` e.g. `TermExpr`, `StatementDataType`. Deduplication via `_dedup_name()` appends incrementing integers starting at 2 for collisions (e.g. `StatementIdentifier` → `StatementIdentifier2`).

**Task plan correction applied:** The spec had Case 4 as `to_class_name(node.name) + parent_cname` which would produce `ExprTerm`, but tests expect `TermExpr`. Corrected to `parent_cname + to_class_name(node.name)` to match all test expectations.

**Fix 3 — Remove `src.base` crash:** Removed `from src.base import GrammarNode` from the generated code header and removed the `parent = "GrammarNode" if cd.parent == "BaseModel" else cd.parent` substitution. Top-level classes now directly extend `BaseModel` (which they already stored in `cd.parent`). Also removed `GrammarNode` from the `_skip` filter in `build()`.

Note: `arm.items` referenced in task plan is wrong — `SequenceNode` uses `.nodes`. Used correct attribute throughout.

## Verification

Ran `pytest tests/test_codegen.py -v` — 27/27 passed in 0.14s covering all 6 grammars. Also ran the task plan inline check: `ValueLiteral` present, `ValueAlt4` absent, full class list confirmed.

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | `python -m pytest tests/test_codegen.py -v` | 0 | ✅ pass | 140ms |
| 2 | `python -c "from src.codegen import build; m = build('resources/ground_truth/json_ws.gbnf'); assert 'ValueLiteral' in m; assert 'ValueAlt4' not in m; print('OK')"` | 0 | ✅ pass | 95ms |

## Deviations

Task plan Case 4 formula was `to_class_name(node.name) + parent_cname` (produces ExprTerm) but tests require `parent_cname + to_class_name(node.name)` (produces TermExpr). Corrected to match tests. Task plan also referenced `arm.items` but SequenceNode uses `arm.nodes` — fixed. Both are minor local corrections within the execution contract.

## Known Issues

none

## Files Created/Modified

- `src/codegen.py`
