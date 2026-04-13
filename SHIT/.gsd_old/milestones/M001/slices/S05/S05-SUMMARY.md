---
id: S05
parent: M001
milestone: M001
provides:
  - ["build(grammar_path) -> dict[str, type] with semantic class names and SOLID inheritance for all 6 ground_truth grammars", "tests/test_codegen.py — 27-test contract suite that a broken implementation cannot pass"]
requires:
  []
affects:
  []
key_files:
  - (none)
key_decisions:
  - ["Naming contract for value arms: ValueLiteral for inline literal-group arm (first node is AlternativeNode of all LiteralNodes), semantic rule-ref names for all others", "Case 4 of _sem_name is parent_cname + to_class_name(node.name) — parent prefix first, ref suffix — required by TermExpr/StatementDataType/ForInitDataType test expectations", "Collision dedup via seen dict: append incrementing integer starting at 2 (e.g. StatementIdentifier2)", "SequenceNode children accessed via .nodes not .items"]
patterns_established:
  - ["Semantic arm naming: bare RuleRef → to_class_name(ref)+parent; alpha literal in sequence → parent+literal.title(); inline literal group (alt of all literals) → parent+'Literal'; first non-ws RuleRef → parent+to_class_name(ref)", "camelCase splitting: re.sub(r'([a-z])([A-Z])', r'\\1_\\2', name) before split-on-underscore — applied in to_class_name()", "Tests-first gate: run pytest to confirm zero tests pass before implementation; capture as verification evidence"]
observability_surfaces:
  - none
drill_down_paths:
  []
duration: ""
verification_result: passed
completed_at: 2026-04-13T19:01:57.452Z
blocker_discovered: false
---

# S05: Codegen Rewrite — tests-first

**Rewrote src/codegen.py with semantic class naming (no AltN names) and SOLID inheritance, verified by 27 contract tests written first against all 6 ground_truth grammars.**

## What Happened

S05 broke the co-evolution cycle from S01/S02: tests were written first from grammar contracts, confirmed to fail on the existing broken code, and then the implementation was rewritten to satisfy them.

**T01 — Write tests/test_codegen.py (tests-first)**

Read all 6 ground_truth grammars and the existing codegen.py to understand the AST structure and naming failures. The current code produced `ValueAlt4`, `TermAlt2`, `StatementAlt0..6` etc., and crashed at import time with `ModuleNotFoundError: No module named 'src.base'`.

Wrote 27 contract tests covering:
- `test_no_alt_n_names` (×6 parametrized): no class name matches `r'.+Alt\d+$'`
- `test_root_present` (×6 parametrized): Root always generated
- json_ws exact arm names: ObjectValue, ArrayValue, StringValue, NumberValue, ValueLiteral (arm 4 is SequenceNode whose first node is an AlternativeNode of all LiteralNodes → Literal suffix)
- json_ws SOLID hierarchy: Value is abstract base, all arm classes subclass Value
- json_ws field type: ObjectValue.value typed as Object (not Union)
- json_ws root: Root subclasses Object
- arithmetic Term arms: IdentTerm, NumTerm, TermExpr — Term is abstract base
- c.gbnf Statement: 9 semantic names including collision dedup (StatementIdentifier2) and camelCase splitting (SingleLineCommentStatement, MultiLineCommentStatement, ForInitDataType, ForInitIdentifier)
- chess / japanese: identical value structure → same 5 arm names as json_ws

Deleted tests/test_grammar_toolkit.py (conflated codegen/parser/serialization concerns). All 27 tests fail with ModuleNotFoundError on pre-rewrite code — tests-first gate satisfied.

**T02 — Rewrite src/codegen.py**

Three targeted fixes, leaving all other functions untouched:

1. **`to_class_name()` — camelCase splitting**: added `re.sub(r'([a-z])([A-Z])', r'\1_\2', name)` before the existing split-on-`_`/`-` logic. `singleLineComment` → `SingleLineComment`, `forInit` → `ForInit`, `dataType` → `DataType`.

2. **`_collect()` — `_sem_name()` helper**: replaced `{cname}Alt{i}` positional fallback with content-derived names:
   - Case 1: bare RuleRefNode → `to_class_name(ref.name) + parent_cname`
   - Case 2 (SequenceNode): first purely-alpha LiteralNode → `parent_cname + literal.title()`
   - Case 3 (SequenceNode): first node is AlternativeNode of all LiteralNodes → `parent_cname + 'Literal'`
   - Case 4 (SequenceNode): first non-ws RuleRefNode fallback → `parent_cname + to_class_name(node.name)`
   - Deduplication via `seen` dict: append incrementing integer suffix starting at `2` for collisions (e.g. `StatementIdentifier2`)
   - Notable correction from task plan: Case 4 is `parent_cname + to_class_name(node.name)` not reversed; SequenceNode uses `.nodes` not `.items`

3. **`_build_class_code()` — remove src.base import**: removed `'from src.base import GrammarNode'` line and `GrammarNode` substitution; top-level classes now use `cd.parent` directly (already `BaseModel`).

All 27 tests pass. `build('resources/ground_truth/json_ws.gbnf')` returns keys `['Array', 'ArrayValue', 'NumberValue', 'Object', 'ObjectValue', 'Root', 'StringValue', 'Value', 'ValueLiteral']` — no `ValueAlt4`.

## Verification

pytest tests/test_codegen.py -v — 27 passed in 0.14s across all 6 ground_truth grammars. No class name matches r'.+Alt\d+$'. All alternation rules produce abstract base + concrete subclasses. ValueLiteral present, ValueAlt4 absent. Secondary inline check: python -c "from src.codegen import build; m = build('resources/ground_truth/json_ws.gbnf'); assert 'ValueLiteral' in m; assert 'ValueAlt4' not in m" — exits 0.

## Requirements Advanced

- R001 — build() now generates correct SOLID inheritance with semantic names for all 6 grammars — abstract base + typed concrete subclasses, no Union fields, no AltN names

## Requirements Validated

None.

## New Requirements Surfaced

None.

## Requirements Invalidated or Re-scoped

None.

## Operational Readiness

None.

## Deviations

None.

## Known Limitations

None.

## Follow-ups

None.

## Files Created/Modified

- `tests/test_codegen.py` — New contract test suite: 27 tests for build() public API across all 6 ground_truth grammars — no AltN names, correct arm names, SOLID hierarchy, correct field types
- `tests/test_grammar_toolkit.py` — Deleted — conflated codegen/parser/serialization concerns, not a valid codegen contract
- `src/codegen.py` — Rewritten: camelCase splitting in to_class_name(), _sem_name() helper for semantic arm naming in _collect(), removed src.base import from _build_class_code()
