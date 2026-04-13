# S05: Codegen Rewrite — tests-first — UAT

**Milestone:** M001
**Written:** 2026-04-13T19:01:57.452Z

# S05 UAT: Codegen Rewrite

## Preconditions
- `resources/ground_truth/` contains 6 `.gbnf` files: json_ws, arithmetic, list, chess, japanese, c
- `.venv` activated, `pytest` and `pydantic` available
- `src/codegen.py` is the rewritten version from T02

## Test Cases

### 1. No AltN names in any grammar
```bash
pytest tests/test_codegen.py::test_no_alt_n_names -v
```
**Expected:** 6 PASSED. No class name in any grammar's output dict matches `r'.+Alt\d+$'`.

### 2. Root always present
```bash
pytest tests/test_codegen.py::test_root_present -v
```
**Expected:** 6 PASSED. `build(path)` returns a dict containing key `'Root'` for all 6 grammars.

### 3. json_ws value arm names
```bash
python -c "
from src.codegen import build
m = build('resources/ground_truth/json_ws.gbnf')
for name in ['ObjectValue','ArrayValue','StringValue','NumberValue','ValueLiteral']:
    assert name in m, f'{name} missing from {sorted(m.keys())}'
print('OK:', [k for k in sorted(m) if 'Value' in k])
"
```
**Expected:** prints `OK: ['ArrayValue', 'NumberValue', 'ObjectValue', 'StringValue', 'Value', 'ValueLiteral']`

### 4. json_ws SOLID hierarchy
```bash
python -c "
from src.codegen import build
m = build('resources/ground_truth/json_ws.gbnf')
Value = m['Value']
for arm in ['ObjectValue','ArrayValue','StringValue','NumberValue','ValueLiteral']:
    assert issubclass(m[arm], Value), f'{arm} does not subclass Value'
print('SOLID hierarchy OK')
"
```
**Expected:** prints `SOLID hierarchy OK`

### 5. json_ws field type (no Union)
```bash
python -c "
from src.codegen import build
import typing
m = build('resources/ground_truth/json_ws.gbnf')
ObjectValue = m['ObjectValue']
Object = m['Object']
hints = typing.get_type_hints(ObjectValue)
field_type = hints.get('value') or next(iter(hints.values()))
assert field_type is Object or (hasattr(field_type, '__origin__') == False and field_type is Object), f'Expected Object, got {field_type}'
print('Field type OK:', field_type)
"
```
**Expected:** prints `Field type OK: <class 'src.generated.json_ws.Object'>` (or similar non-Union type)

### 6. arithmetic Term arms with camelCase splitting
```bash
python -c "
from src.codegen import build
m = build('resources/ground_truth/arithmetic.gbnf')
for name in ['IdentTerm','NumTerm','TermExpr']:
    assert name in m, f'{name} missing'
Term = m['Term']
for arm in ['IdentTerm','NumTerm','TermExpr']:
    assert issubclass(m[arm], Term)
print('Arithmetic OK')
"
```
**Expected:** prints `Arithmetic OK`

### 7. c.gbnf Statement arms with camelCase splitting + dedup
```bash
python -c "
from src.codegen import build
m = build('resources/ground_truth/c.gbnf')
expected = ['StatementDataType','StatementIdentifier','StatementIdentifier2',
            'StatementReturn','StatementWhile','StatementFor','StatementIf',
            'SingleLineCommentStatement','MultiLineCommentStatement']
for name in expected:
    assert name in m, f'{name} missing from {sorted(k for k in m if \"Statement\" in k or \"Comment\" in k)}'
print('c.gbnf Statement OK')
"
```
**Expected:** prints `c.gbnf Statement OK`

### 8. c.gbnf for_init arms
```bash
python -c "
from src.codegen import build
m = build('resources/ground_truth/c.gbnf')
for name in ['ForInitDataType','ForInitIdentifier']:
    assert name in m, f'{name} missing'
print('c.gbnf for_init OK')
"
```
**Expected:** prints `c.gbnf for_init OK`

### 9. chess and japanese identical value structure
```bash
python -c "
from src.codegen import build
for grammar in ['chess.gbnf','japanese.gbnf']:
    m = build(f'resources/ground_truth/{grammar}')
    for name in ['ObjectValue','ArrayValue','StringValue','NumberValue','ValueLiteral']:
        assert name in m, f'{grammar}: {name} missing'
    Value = m['Value']
    for arm in ['ObjectValue','ArrayValue','StringValue','NumberValue','ValueLiteral']:
        assert issubclass(m[arm], Value), f'{grammar}: {arm} not subclass of Value'
print('chess + japanese OK')
"
```
**Expected:** prints `chess + japanese OK`

### 10. Full test suite
```bash
pytest tests/test_codegen.py -v
```
**Expected:** `27 passed`

## Edge Cases
- **Cache safety**: calling `build()` twice on the same path returns the same dict (module-level `_BUILD_CACHE`). Run `build('resources/ground_truth/json_ws.gbnf')` twice — second call hits cache, same result.
- **No src.base import**: `python -c "import src.codegen"` must not raise `ModuleNotFoundError: No module named 'src.base'`. (src/base.py does not exist and must not be referenced.)

