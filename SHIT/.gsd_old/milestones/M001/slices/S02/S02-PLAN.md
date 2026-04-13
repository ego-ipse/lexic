# S02: Grammar-Aware Parser: Text to Pydantic

**Goal:** Implement parse(text, grammar_path) -> BaseModel that converts grammar-valid text into typed Pydantic model instances using Lark Earley at runtime, driven by the same GBNF grammar used in build().
**Demo:** python -c "from src.parser import parse; from pathlib import Path; obj = parse('{\"city\": \"Porto\"}', Path('resources/ground_truth/json_ws.gbnf')); print(type(obj).__name__)" prints ObjectValue

## Must-Haves

- uv run pytest tests/ -v produces 33/33 passed (12 S01 + 21 S02). Demo command: python -c "from src.parser import parse; from pathlib import Path; obj = parse('{\"city\": \"Porto\"}', Path('resources/ground_truth/json_ws.gbnf')); print(type(obj).__name__)" prints ObjectValue.

## Proof Level

- This slice proves: integration — real Lark Earley parse at runtime; no mocks

## Integration Closure

Upstream: src/codegen.build() dict[str, type], llguidance GBNF nodes, Lark Earley. New wiring: src/parser.parse() becomes the public parse entry point. What remains: S03 serialization (to_text/to_json), S04 end-to-end LLM loop.

## Verification

- Failure visibility: Lark UnexpectedInput exceptions surface grammar mismatch; transform errors include rule name in message. Inspection: uv run python -c with -v pytest for per-grammar pass/fail.

## Tasks

- [x] **T01: Implement src/parser.py — GBNF-to-Lark grammar converter and Pydantic tree transformer** `est:2h`
  Implement src/parser.py with the full Grammar-Aware Parser. This file may already exist from a research phase — read it first. If it exists and uv run pytest tests/test_parser.py -v passes 21/21, verify the demo command and mark done without changes.

If the file needs to be written or fixed, implement these four components:

**1. _gbnf_to_earley_lark(gbnf_text: str) -> str**
Copied from with_guidance.py lines 255-269 (no model loading). Uses GrammarParser + resolve() from llguidance.gbnf_to_lark. After resolve(), root is renamed to 'start' — do NOT reverse this (unlike build() which does reverse it). The transformer maps tree.data == 'start' to mods.get('Root').

**2. _fix_lark_grammar(lark_g: str, gbnf_text: str) -> str**
Three sequential fixes:
- Fix 1 — quantifier outside regex: regex `r'/([^/]+)/{(\d+,\d+)}'` → replace with `/\1{\2}/` (move quantifier inside regex)
- Fix 2 — adjacent regex merge: regex `r'/([^/]+)/ /([^/]+)/(?![*+?~])'` → merge into `/\1\2/` (negative lookahead prevents merging when second regex is followed by Lark quantifier)
- Fix 3 — nullable rule detection: scan gbnf_text for rules with empty-string alternatives (SequenceNode with no children after resolve()). Replace entire rule with `/[ \t\n]+/?` and add `?` to all references to that rule name in lark_g.

**3. _transform(tree, mods, gbnf_rules, text) -> Any**
Recursive tree walker (NOT Lark Transformer class) mapping Lark Tree nodes to Pydantic instances via model_construct().

Four rule body types:
- Terminal rules (r.rule_is_terminal == True): if Tree has Token children, join them → str. If no Tokens (literal-only rule), use text[tree.meta.start_pos:tree.meta.end_pos].rstrip() — requires propagate_positions=True in Lark.
- AlternativeNode rules (abstract bases like Value): if no non-ws subtrees → literal match (true/false/null) → text span → find XAltN subclass. If has subtree → check child rule name against RuleRefNode alternatives → find XY concrete subclass. If no RuleRefNode match → compare child rule names against _seq_rule_refs(alt) for each SequenceNode alternative → instantiate XAltN subclass.
- RuleRefNode body (subclass rules like Root(Object)): if terminal ref → value: str field. If non-terminal → copy fields from child instance.
- SequenceNode / default (Object, Declaration etc): transform all non-ws children → flat list. Consume using _build_for_annotation(annotation, queue) for each field.

**4. _build_for_annotation(annotation, queue: deque) -> Any**
Consumes from child value queue to satisfy a Pydantic field annotation:
- str → pop one str
- BaseModel subclass → pop one instance
- Optional[T] → if _can_consume(T, queue), recurse; else None
- list[T] → consume while _can_consume(T, queue) → collect
- tuple[A, B, C] → consume one per type arg

_can_consume for tuples: count only non-list args as required (list args can produce []). Without this, Optional[tuple[str, Value, list[...]]] with 2 items would fail because 2 < 3.

**5. parse(text: str, grammar_path: Path) -> BaseModel**
Public API: reads grammar_path, calls _gbnf_to_earley_lark, _fix_lark_grammar, builds Lark(grammar, parser='earley', propagate_positions=True), calls build(grammar_path) to get mods, parses text, calls _transform on root tree.

**Critical constraints:**
- Use model_construct() everywhere (bypasses Pydantic validation — required for complex field types like Optional[tuple[str, Value, list[...]]])
- Import from src.codegen: build, to_class_name, _sequence_fields
- Do NOT import with_guidance.py — triggers model load
- Use deque (collections.deque) for the queue in _build_for_annotation
  - Files: `src/parser.py`, `src/codegen.py`
  - Verify: uv run python -c "from src.parser import parse; from pathlib import Path; obj = parse('{\"city\": \"Porto\"}', Path('resources/ground_truth/json_ws.gbnf')); print(type(obj).__name__)" | grep -q ObjectValue && echo PASS

- [x] **T02: Implement tests/test_parser.py and verify 33/33 tests pass** `est:45m`
  Implement tests/test_parser.py with a 21-test suite covering all 6 ground-truth grammars. This file may already exist from a research phase — read it first. If it exists and uv run pytest tests/ -v passes 33/33, mark done without changes.

If the file needs to be written or fixed, implement these test groups:

**Group 1 — parametrized smoke tests (12 tests: 6 grammars × 2 assertions)**
```python
@pytest.mark.parametrize('grammar,text', [
    ('json_ws.gbnf', '{"city": "Porto"}'),
    ('arithmetic.gbnf', 'x = 1\n'),
    ('list.gbnf', '- hello\n- world\n'),
    ('chess.gbnf', '{"move": "e4"}'),
    ('japanese.gbnf', '{"name": "Tokyo"}'),
    ('c.gbnf', 'int f(){return 1;}'),
])
def test_parse_returns_basemodel(grammar, text): ...
def test_parse_result_class_is_root(grammar, text): ...
```
test_parse_returns_basemodel: assert isinstance(result, BaseModel)
test_parse_result_class_is_root: assert type(result).__name__ == 'Root'

**Group 2 — json_ws structural assertions (6 tests)**
- test_json_ws_root_is_subclass_of_object: assert issubclass(type(obj), mods['Object'])
- test_json_ws_parse_simple_object: parse '{"city": "Porto"}', assert obj.strings[0] == 'city', obj.strings[1].__class__.__name__ in ('StringValue', 'ObjectValue', 'ArrayValue', ...)
- test_json_ws_parse_empty_object: parse '{}', result is Root instance
- test_json_ws_parse_multiple_keys: parse '{"a": "1", "b": "2"}', check obj.strings is not None
- test_json_ws_parse_true_false_null: parse '{"flag": true}', result is Root
- test_json_ws_value_isinstance_hierarchy: parse '{"x": 1}', check result is instance of Object

**Group 3 — per-grammar structural assertions (3 tests)**
- test_arithmetic_parse_result_has_items: parse 'x = 1\n', assert hasattr(root, 'items') or hasattr(root, 'expr') or isinstance(root, BaseModel)
- test_list_parse_result_has_str_items: parse '- hello\n- world\n', assert isinstance(root, BaseModel)
- test_c_parse_declaration_fields: parse 'int f(){return 1;}', assert isinstance(root, BaseModel), hasattr(root, '__class__')

**Import pattern:**
```python
from pathlib import Path
import pytest
from pydantic import BaseModel
from src.parser import parse
from src.codegen import build

GRAMMAR_DIR = Path('resources/ground_truth')
```

**Constraint:** Use GRAMMAR_DIR variable (not hardcoded path string) per project feedback.

After writing/verifying, run the full suite: uv run pytest tests/ -v
  - Files: `tests/test_parser.py`
  - Verify: uv run pytest tests/ -v 2>&1 | tail -5 | grep -q '33 passed'

## Files Likely Touched

- src/parser.py
- src/codegen.py
- tests/test_parser.py
