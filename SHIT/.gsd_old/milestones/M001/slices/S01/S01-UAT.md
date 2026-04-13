# S01: GBNF to Pydantic Model Generator — UAT

**Milestone:** M001
**Written:** 2026-04-12T18:32:06.356Z

# S01: GBNF to Pydantic Model Generator — UAT

**Milestone:** M001
**Written:** 2026-04-12

## UAT Type

- UAT mode: artifact-driven
- Why this mode is sufficient: S01 produces class objects, not a running service. Correctness is fully provable by asserting `__bases__`, `model_fields`, and `__module__` on the returned dict.

## Preconditions

- Working directory: `/home/mika/projects/vyx_2`
- `uv` available and `.venv` populated (`uv sync`)
- `resources/ground_truth/` contains at least: `json_ws.gbnf`, `arithmetic.gbnf`, `c.gbnf`, `chess.gbnf`, `japanese.gbnf`, `list.gbnf`

## Smoke Test

```bash
uv run python -c "from src.codegen import build; mods = build('resources/ground_truth/json_ws.gbnf'); print(mods['ObjectValue'].__bases__)"
```
Expected output: `(<class 'src.generated.json_ws.Value'>,)`

## Test Cases

### 1. SOLID inheritance: ObjectValue and ArrayValue are subclasses of Value

```bash
uv run python -c "
from src.codegen import build
mods = build('resources/ground_truth/json_ws.gbnf')
assert mods['ObjectValue'].__bases__ == (mods['Value'],), mods['ObjectValue'].__bases__
assert mods['ArrayValue'].__bases__ == (mods['Value'],), mods['ArrayValue'].__bases__
print('PASS')
"
```
**Expected:** exits 0, prints `PASS`

### 2. Root is a subclass of Object

```bash
uv run python -c "
from src.codegen import build
mods = build('resources/ground_truth/json_ws.gbnf')
assert issubclass(mods['Root'], mods['Object']), mods['Root'].__bases__
print('PASS')
"
```
**Expected:** exits 0, prints `PASS`

### 3. All 6 ground-truth grammars parse without error

```bash
uv run python -c "
from pathlib import Path
from src.codegen import build
from pydantic import BaseModel
for p in sorted(Path('resources/ground_truth').glob('*.gbnf*')):
    mods = build(p)
    assert mods, f'Empty result for {p.name}'
    assert all(issubclass(v, BaseModel) for v in mods.values()), f'Non-BaseModel in {p.name}'
    print('OK', p.name, sorted(mods.keys())[:3])
"
```
**Expected:** exits 0, prints `OK <grammar> [...]` for each of the 6 grammars

### 4. Module naming is correct

```bash
uv run python -c "
from src.codegen import build
mods = build('resources/ground_truth/json_ws.gbnf')
for name, cls in mods.items():
    assert cls.__module__ == 'src.generated.json_ws', f'{name}.__module__ == {cls.__module__}'
print('PASS')
"
```
**Expected:** exits 0, prints `PASS`

### 5. Abstract base Value has no required fields

```bash
uv run python -c "
from src.codegen import build
mods = build('resources/ground_truth/json_ws.gbnf')
required = {k: v for k, v in mods['Value'].model_fields.items() if v.is_required()}
assert not required, f'Value has required fields: {required}'
print('PASS: Value has no required fields')
"
```
**Expected:** exits 0, prints `PASS: Value has no required fields`

### 6. Full pytest suite

```bash
uv run pytest tests/test_codegen.py -v
```
**Expected:** `12 passed` in < 1s

## Edge Cases

### Single-alternative AlternativeNode treated as SequenceNode

Grammars where a rule has exactly one alternative should produce a class with fields, not an abstract base. No test grammar isolates this case exactly, but `list.gbnf` exercises it implicitly — `build('resources/ground_truth/list.gbnf')` must return a non-empty dict with BaseModel subclasses.

### Grammar with no alternation rules (all sequences)

`arithmetic.gbnf` has no top-level alternation rules. `build('resources/ground_truth/arithmetic.gbnf')` must succeed and contain `'Root'`.

## Failure Signals

- `AssertionError` with `__bases__` in the message → inheritance mapping broken
- `NameError` in exec → forward reference not resolved; check `from __future__ import annotations` is first line
- `PydanticUserError` about model_rebuild → `model_rebuild()` calls emitted before all classes defined
- `KeyError: 'root'` → `resolve()` rename reversal missing

## Not Proven By This UAT

- Parsing grammar-constrained text into model instances (S02)
- Round-trip serialization back to grammar text (S03)
- Constrained LLM generation (S04)
- Correctness of field types beyond `model_fields` existence checks

## Notes for Tester

The `json_arr.gbnbf` file referenced in some task descriptions is absent from `resources/ground_truth/` — only 6 grammars exist. `glob('*.gbnf*')` correctly collects whatever is present. The typo filename (`gbnbf`) is a known upstream issue not in scope for this slice.
