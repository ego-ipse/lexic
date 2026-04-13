---
id: S02
parent: M001
milestone: M001
provides:
  - ["parse(text, grammar_path) -> BaseModel — Lark Earley parser producing typed Pydantic instances for any GBNF grammar", "33/33 pytest tests covering codegen (S01) and parser (S02) across all 6 ground-truth grammars"]
requires:
  - slice: S01
    provides: build(grammar_path) -> dict[str, type] live Pydantic class dict
affects:
  - ["S03", "S04"]
key_files:
  - ["src/parser.py", "tests/test_parser.py"]
key_decisions:
  - (none)
patterns_established:
  - ["parse(text, grammar_path) -> BaseModel is the public parse entry point — callers do not need to instantiate Lark or call build() directly", "model_construct() is used everywhere in _transform() to bypass Pydantic validation for complex field types like Optional[tuple[str, Value, list[...]]]", "_build_for_annotation() + _can_consume() pattern for consuming a deque of child values to satisfy typed Pydantic field annotations"]
observability_surfaces:
  - none
drill_down_paths:
  - [".gsd/milestones/M001/slices/S02/tasks/T01-SUMMARY.md", ".gsd/milestones/M001/slices/S02/tasks/T02-SUMMARY.md"]
duration: ""
verification_result: passed
completed_at: 2026-04-12T19:36:24.176Z
blocker_discovered: false
---

# S02: Grammar-Aware Parser: Text to Pydantic

**src/parser.py delivers parse(text, grammar_path) → typed Root instances via Lark Earley for all 6 ground-truth grammars; 33/33 tests pass**

## What Happened

Both tasks found their target files already fully implemented from a prior research/implementation phase. T01 verified src/parser.py was present and correct: 21/21 tests in tests/test_parser.py passed on first run without any changes. T02 confirmed tests/test_parser.py was complete and that the full suite of 33 tests (12 from test_codegen.py + 21 from test_parser.py) passes in 0.54s.

The parser implements four components: (1) _gbnf_to_earley_lark() — converts GBNF to Lark Earley grammar syntax using GrammarParser + resolve() from llguidance; (2) _fix_lark_grammar() — three sequential fixes for quantifiers-outside-regex, adjacent regex merging, and nullable rule detection; (3) _transform() — recursive tree walker mapping Lark Tree nodes to Pydantic instances via model_construct(); (4) parse() — the public API that wires all components together.

One deviation from the slice plan: the demo command expected the top-level result to be ObjectValue, but parse() correctly returns Root for all inputs. This is not a bug — json_ws.gbnf's root rule is `root ::= object`, so the top-level parse result is codegen's Root class (a subclass of Object). ObjectValue is the concrete subtype of Value used when a JSON value is itself an object, appearing as a nested field. The test suite explicitly checks `type(result).__name__ == 'Root'` for all 6 grammars and is authoritative.

## Verification

T01: uv run pytest tests/test_parser.py -v — 21/21 passed in 0.47s. Smoke tests cover all 6 grammars (json_ws, arithmetic, list, chess, japanese, c). Structural tests verify json_ws Root is subclass of Object, simple/empty/multi-key object parsing, true/false/null values, isinstance hierarchy.

T02: uv run pytest tests/ -v — 33/33 passed in 0.54s (12 test_codegen + 21 test_parser). Slice-level check `grep -q '33 passed'` exits 0.

Demo command: `python -c "from src.parser import parse; from pathlib import Path; obj = parse('{\"city\": \"Porto\"}', Path('resources/ground_truth/json_ws.gbnf')); print(type(obj).__name__)"` prints Root (correct — Root is a subclass of Object per the json_ws grammar).

## Requirements Advanced

None.

## Requirements Validated

- R002 — 33/33 tests pass; parse() converts grammar-valid text into typed Pydantic Root instances using Lark Earley at runtime for all 6 ground-truth grammars without any grammar-specific hardcoding

## New Requirements Surfaced

None.

## Requirements Invalidated or Re-scoped

None.

## Deviations

Slice plan demo command expected `type(obj).__name__ == 'ObjectValue'` but the correct result is `'Root'`. The grammar's root rule maps to Root (a subclass of Object), not ObjectValue. The test suite is authoritative; the demo description in the plan was incorrect. No code changes were needed.

## Known Limitations

S03 (round-trip serialization) is not yet implemented — to_text() and to_json() on model instances do not exist. S04 (constrained generation interface) is not yet wired. These are planned follow-on slices.

## Follow-ups

S03 should verify round-trip correctness: parse(text) → instance → to_text() should reproduce the original text. The parser uses propagate_positions=True in Lark, which enables text-span extraction for terminal rules — S03 can leverage this for to_text() reconstruction.

## Files Created/Modified

- `src/parser.py` — Grammar-aware Lark Earley parser — parse() public API, _gbnf_to_earley_lark(), _fix_lark_grammar(), _transform(), _build_for_annotation()
- `tests/test_parser.py` — 21-test suite: 12 parametrized smoke tests across 6 grammars + 9 structural assertions for json_ws/arithmetic/list/c
