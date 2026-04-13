# S02: Grammar-Aware Parser: Text to Pydantic — UAT

**Milestone:** M001
**Written:** 2026-04-12T19:36:24.177Z

# S02: Grammar-Aware Parser — UAT

**Milestone:** M001
**Written:** 2026-04-12

## UAT Type

- UAT mode: artifact-driven
- Why this mode is sufficient: The parser is a pure function (text + grammar → Pydantic instance). All behavior is captured by the pytest suite which exercises all 6 grammars with structural assertions. No server, no UI, no runtime state.

## Preconditions

- Working directory: `/home/mika/projects/vyx_2`
- `uv` available and dependencies installed
- `resources/ground_truth/` contains the 6 `.gbnf` files

## Smoke Test

```bash
uv run python -c "
from src.parser import parse
from pathlib import Path
obj = parse('{\"city\": \"Porto\"}', Path('resources/ground_truth/json_ws.gbnf'))
print(type(obj).__name__)  # prints: Root
"
```

Expected: prints `Root`

## Test Cases

### 1. Full test suite passes

```bash
uv run pytest tests/ -v
```

**Expected:** `33 passed` — 12 from test_codegen.py, 21 from test_parser.py. No failures, no errors.

### 2. parse() returns BaseModel for all 6 grammars

```python
from pathlib import Path
from pydantic import BaseModel
from src.parser import parse

cases = [
    ('json_ws.gbnf',    '{"city": "Porto"}'),
    ('arithmetic.gbnf', 'x = 1\n'),
    ('list.gbnf',       '- hello\n- world\n'),
    ('chess.gbnf',      '{"move": "e4"}'),
    ('japanese.gbnf',   '{"name": "Tokyo"}'),
    ('c.gbnf',          'int f(){return 1;}'),
]
for grammar, text in cases:
    result = parse(text, Path('resources/ground_truth') / grammar)
    assert isinstance(result, BaseModel), f"{grammar}: not a BaseModel"
    assert type(result).__name__ == 'Root', f"{grammar}: expected Root, got {type(result).__name__}"
print("All 6 grammars OK")
```

**Expected:** prints `All 6 grammars OK`

### 3. json_ws Root is a subclass of Object

```python
from pathlib import Path
from src.parser import parse
from src.codegen import build

mods = build(Path('resources/ground_truth/json_ws.gbnf'))
obj = parse('{"city": "Porto"}', Path('resources/ground_truth/json_ws.gbnf'))
assert issubclass(type(obj), mods['Object'])
print("Root is subclass of Object: OK")
```

**Expected:** prints `Root is subclass of Object: OK`

### 4. json_ws structural field access

```python
from pathlib import Path
from src.parser import parse

obj = parse('{"city": "Porto"}', Path('resources/ground_truth/json_ws.gbnf'))
assert obj.strings[0] == 'city'
print("Field access OK:", obj.strings)
```

**Expected:** prints field list with `'city'` as first string element

### 5. Empty object parses cleanly

```python
from pathlib import Path
from pydantic import BaseModel
from src.parser import parse

result = parse('{}', Path('resources/ground_truth/json_ws.gbnf'))
assert isinstance(result, BaseModel)
print("Empty object OK:", type(result).__name__)
```

**Expected:** prints `Empty object OK: Root`

### 6. True/false/null values parse without error

```python
from pathlib import Path
from pydantic import BaseModel
from src.parser import parse

result = parse('{"flag": true}', Path('resources/ground_truth/json_ws.gbnf'))
assert isinstance(result, BaseModel)
print("Boolean value OK")
```

**Expected:** prints `Boolean value OK`

## Edge Cases

### Multiple keys

```python
obj = parse('{"a": "1", "b": "2"}', Path('resources/ground_truth/json_ws.gbnf'))
assert obj.strings is not None
print("Multiple keys OK")
```

**Expected:** prints `Multiple keys OK`

### C grammar with function body

```python
result = parse('int f(){return 1;}', Path('resources/ground_truth/c.gbnf'))
assert isinstance(result, BaseModel)
assert hasattr(result, '__class__')
print("C grammar OK:", type(result).__name__)
```

**Expected:** prints `C grammar OK: Root`

## Failure Signals

- `Lark UnexpectedInput` — input text does not conform to the grammar; check the text, not the parser
- `KeyError: 'Root'` in _transform — resolve() reversal bug; see KNOWLEDGE.md entry on 'start' renaming
- `AttributeError` on field access — _build_for_annotation mis-consumed the child queue; add debug prints to _transform
- `33 passed` not in pytest output — check for import errors in src/parser.py or src/codegen.py

## Not Proven By This UAT

- Round-trip correctness: parse → to_text() → parse producing identical instances (deferred to S03)
- Constrained LLM generation producing valid parser inputs (deferred to S04)
- Performance under large inputs or deeply nested grammars
- Error recovery for partially-valid inputs

## Notes for Tester

- `parse()` always returns `Root`, never a concrete subtype like `ObjectValue` — that is correct. The slice plan demo description was wrong about the expected class name.
- The test suite uses `GRAMMAR_DIR = Path('resources/ground_truth')` — tests must be run from the repo root (`/home/mika/projects/vyx_2`), not from a subdirectory.
- `propagate_positions=True` is set in the Lark constructor — this enables text-span extraction for terminal rules in _transform(). S03 should leverage this for to_text() reconstruction.
