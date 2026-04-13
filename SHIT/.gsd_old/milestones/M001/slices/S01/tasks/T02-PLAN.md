---
estimated_steps: 30
estimated_files: 3
skills_used: []
---

# T02: Write pytest test suite for all 7 grammars

Create tests/test_codegen.py with a pytest test suite. Set up pytest if not already configured (check for pyproject.toml or pytest.ini; add [tool.pytest.ini_options] to pyproject.toml if needed).

The test suite must cover:

1. test_json_ws_inheritance — json_ws.gbnf SOLID hierarchy:
   - mods['ObjectValue'].__bases__ == (mods['Value'],)
   - mods['ArrayValue'].__bases__ == (mods['Value'],)
   - issubclass(mods['Root'], mods['Object'])
   - 'Value' in mods and 'Object' in mods and 'Array' in mods

2. test_json_ws_field_types — field structure sanity:
   - mods['Object'] has a pydantic model_fields dict with at least one field
   - mods['ObjectValue'] has a field typed to mods['Object'] (check model_fields)

3. test_all_grammars_parse — parametrize over all 7 .gbnf/.gbnbf files in resources/ground_truth/:
   - build(p) returns a non-empty dict
   - All values in the dict are subclasses of BaseModel
   - No exception raised
   Use glob: list(Path('resources/ground_truth').glob('*.gbnf*'))

4. test_arithmetic_structure — arithmetic.gbnf:
   - 'Root' in mods (the grammar's root rule)
   - build succeeds without error

5. test_module_naming — after build(), classes have __module__ == 'src.generated.json_ws'

6. test_abstract_base_has_no_required_fields — Value in json_ws has no required fields (it's a pass-body abstract base); subclasses have fields.

IMPORTANT: The grammar files have two extensions — .gbnf and .gbnbf (json_arr.gbnbf has a typo). Use glob('*.gbnf*') to catch both.

Test file structure:
  from pathlib import Path
  import pytest
  from pydantic import BaseModel
  from src.codegen import build

  GRAMMAR_DIR = Path('resources/ground_truth')
  ALL_GRAMMARS = sorted(GRAMMAR_DIR.glob('*.gbnf*'))

Run with: uv run pytest tests/test_codegen.py -v

Create tests/__init__.py (empty) if it does not exist so pytest discovers the package correctly.

## Inputs

- `src/codegen.py`
- `src/__init__.py`
- `resources/ground_truth/json_ws.gbnf`

## Expected Output

- `tests/test_codegen.py`
- `tests/__init__.py`

## Verification

uv run pytest tests/test_codegen.py -v
