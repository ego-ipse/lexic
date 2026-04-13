---
estimated_steps: 15
estimated_files: 2
skills_used: []
---

# T01: Write tests/test_codegen.py (tests-first, must fail on current code)

Write the full contract test suite for `build()` before any implementation changes. Tests assert exact class names, `__bases__`, and field types derived from each of the 6 ground_truth grammars. Delete `tests/test_grammar_toolkit.py` (it conflates codegen/parser/serialization concerns and is not a valid contract).

Naming contract locked by this task:
- json_ws `value` arms: `ObjectValue`, `ArrayValue`, `StringValue`, `NumberValue`, `ValueLiteral` (arm 4 is `('true'|'false'|'null') ws` — AlternativeNode of literals as first node → `Literal` suffix)
- arithmetic `term` arm 2: `TermExpr` (first non-ws rule ref = `expr`)
- c.gbnf `statement` arms: `StatementDataType`, `StatementIdentifier`, `StatementIdentifier2` (index dedup on collision), `StatementReturn`, `StatementWhile`, `StatementFor`, `StatementIf`, `SingleLineCommentStatement`, `MultiLineCommentStatement` (camelCase splitting: `singleLineComment` → `SingleLineComment`)
- c.gbnf `for_init` arms: `ForInitDataType`, `ForInitIdentifier` (camelCase splitting: `forInit` → `ForInit`, `dataType` → `DataType`)
- chess and japanese: identical `value` structure to json_ws — same class names expected

Key assertions per test:
1. `no_alt_n_names`: assert no key in `build(path)` matches `re.match(r'.+Alt\d+$', name)`
2. `solid_hierarchy`: for each alternation rule, the base class is abstract (`__abstractmethods__` or no fields), concrete subclasses are in `__subclasses__()`
3. Exact name checks: `assert 'ValueLiteral' in classes` etc. for each grammar
4. Field type checks: `ObjectValue` has field `value: Object` (not `Union[...]`)

Do NOT test `parse()`, `to_text()`, `to_json()` — those belong to S06/S07.
Do NOT call internal helpers — only `build(grammar_path) -> dict[str, type]`.

After writing, run pytest to confirm all tests fail (current code crashes with `ModuleNotFoundError: No module named 'src.base'`). Capture the failure output as evidence.

## Inputs

- `resources/ground_truth/json_ws.gbnf`
- `resources/ground_truth/arithmetic.gbnf`
- `resources/ground_truth/c.gbnf`
- `resources/ground_truth/chess.gbnf`
- `resources/ground_truth/japanese.gbnf`
- `resources/ground_truth/list.gbnf`
- `src/codegen.py`
- `tests/test_grammar_toolkit.py`

## Expected Output

- `tests/test_codegen.py`

## Verification

pytest tests/test_codegen.py -v 2>&1 | grep -E '(FAILED|ERROR|passed|failed)' ; python -c "import re; import subprocess; r = subprocess.run(['pytest','tests/test_codegen.py','--tb=no','-q'], capture_output=True, text=True); assert 'passed' not in r.stdout or int(re.search(r'(\d+) passed', r.stdout).group(1)) == 0, 'Tests must NOT pass on broken code'"
