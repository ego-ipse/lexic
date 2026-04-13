# S05: Codegen Rewrite — tests-first

**Goal:** Rewrite `src/codegen.py` so that `build(grammar_path)` produces a correct, meaningful Pydantic class dict — SOLID inheritance, semantic class names (never `ValueAlt4`), field types that reflect the grammar structure — verified by tests written first that a broken implementation cannot pass.
**Demo:** pytest tests/test_codegen.py -v — all tests pass; generated classes have correct names (no ValueAlt4), correct __bases__, and correct field types for all 6 ground_truth grammars

## Must-Haves

- pytest tests/test_codegen.py -v passes for all 6 ground_truth grammars; no class name matches r'\w+Alt\d+'; all alternation rules produce abstract base + concrete subclasses (no Union fields); `build('resources/ground_truth/json_ws.gbnf')` returns a dict containing 'Value', 'ObjectValue', 'ArrayValue', 'StringValue', 'NumberValue', 'ValueLiteral', 'Object', 'Array', 'Root', 'String', 'Number'.

## Proof Level

- This slice proves: contract — tests exercise the public API `build(grammar_path) -> dict[str, type]` against 6 real grammar files; no mocks

## Integration Closure

Upstream: `resources/ground_truth/*.gbnf` (6 files), `llguidance.gbnf_to_lark` AST parser. Produces: `tests/test_codegen.py` (contract suite), `src/codegen.py` (rewritten). Remaining before end-to-end: S06 (parser rewrite) consumes `build()` output.

## Verification

- Not provided.

## Tasks

- [x] **T01: Write tests/test_codegen.py (tests-first, must fail on current code)** `est:45m`
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
  - Files: `tests/test_codegen.py`, `tests/test_grammar_toolkit.py`
  - Verify: pytest tests/test_codegen.py -v 2>&1 | grep -E '(FAILED|ERROR|passed|failed)' ; python -c "import re; import subprocess; r = subprocess.run(['pytest','tests/test_codegen.py','--tb=no','-q'], capture_output=True, text=True); assert 'passed' not in r.stdout or int(re.search(r'(\d+) passed', r.stdout).group(1)) == 0, 'Tests must NOT pass on broken code'"

- [x] **T02: Rewrite src/codegen.py: semantic naming + fix src.base crash** `est:90m`
  Rewrite the two broken areas of `src/codegen.py`. All other functions (`ast_to_regex`, `_node_to_type`, `_sequence_fields`, `_topo_sort`, `build`) stay untouched.

### Fix 1: `to_class_name()` — add camelCase splitting
Current: splits only on `_` and `-`. Result: `singleLineComment` → `Singlelinecomment`.
Required: also split on camelCase boundaries. `singleLineComment` → `SingleLineComment`, `forInit` → `ForInit`, `dataType` → `DataType`.
Implement with regex: `re.sub(r'([a-z])([A-Z])', r'\1_\2', name)` before the existing split logic.

### Fix 2: `_collect()` — semantic naming algorithm for alternation arms
Replace the `{cname}Alt{i}` fallback with `_sem_name(arm, cname, seen_names)` helper:

```python
def _sem_name(arm, parent_cname: str, seen: dict[str, int]) -> str:
    # Unwrap single-element SequenceNode → treat as its inner node
    if isinstance(arm, SequenceNode) and len(arm.items) == 1:
        arm = arm.items[0]
    
    # Case 1: bare RuleRefNode
    if isinstance(arm, RuleRefNode):
        return to_class_name(arm.name) + parent_cname
    
    if isinstance(arm, SequenceNode):
        nodes = arm.items
        
        # Case 2: scan for first purely-alpha LiteralNode (keyword)
        for node in nodes:
            if isinstance(node, LiteralNode):
                val = node.value.strip('"\'')
                if val.isalpha():
                    return parent_cname + val.title()
        
        # Case 3: inline-literal-group — first node is AlternativeNode of all LiteralNodes
        if nodes and isinstance(nodes[0], AlternativeNode):
            if all(isinstance(a, LiteralNode) for a in nodes[0].alternatives):
                return parent_cname + 'Literal'
        
        # Case 4: first non-ws RuleRefNode fallback
        _WS = {'ws', 'wsp', 'whitespace', 'sp', ' '}
        for node in nodes:
            if isinstance(node, RuleRefNode) and node.name not in _WS:
                return to_class_name(node.name) + parent_cname
    
    # Final fallback (should not be reached for well-formed grammars)
    return parent_cname + 'Arm'
```

Deduplication: after generating a candidate name, check `seen` dict. If name already used, append incrementing integer suffix starting at `2` (e.g. `StatementIdentifier2`).

### Fix 3: `_build_class_code()` — remove src.base import and GrammarNode substitution
- Remove the line `'from src.base import GrammarNode',` from the generated code lines list
- Remove (or change) `parent = 'GrammarNode' if cd.parent == 'BaseModel' else cd.parent` — just use `cd.parent` directly (top-level classes already have `parent='BaseModel'`)
- `src/base.py` does NOT exist and must not be referenced

### Constraints
- `from __future__ import annotations` must remain the first line in exec'd strings
- `model_rebuild()` must be called after ALL class defs (already correct — don't move it)
- `resolve()` renames `root` → `start`; the existing post-resolve rename back to `root` must stay
- `_BUILD_CACHE` module-level cache is fine — tests use distinct grammar paths so no cache collision
- Do NOT touch `ast_to_regex`, `_node_to_type`, `_sequence_fields`, `_topo_sort`, `build`

After rewriting, run `pytest tests/test_codegen.py -v` — all tests must pass.
  - Files: `src/codegen.py`
  - Verify: pytest tests/test_codegen.py -v && python -c "from src.codegen import build; m = build('resources/ground_truth/json_ws.gbnf'); assert 'ValueLiteral' in m, f'ValueLiteral missing, got: {sorted(m.keys())}'; assert 'ValueAlt4' not in m, 'ValueAlt4 still present'; print('OK:', sorted(m.keys()))"

## Files Likely Touched

- tests/test_codegen.py
- tests/test_grammar_toolkit.py
- src/codegen.py
