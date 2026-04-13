---
estimated_steps: 39
estimated_files: 1
skills_used: []
---

# T02: Implement tests/test_parser.py and verify 33/33 tests pass

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

## Inputs

- `src/parser.py`
- `src/codegen.py`
- `resources/ground_truth/json_ws.gbnf`

## Expected Output

- `tests/test_parser.py`

## Verification

uv run pytest tests/ -v 2>&1 | tail -5 | grep -q '33 passed'
