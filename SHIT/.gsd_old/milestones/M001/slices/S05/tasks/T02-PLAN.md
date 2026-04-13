---
estimated_steps: 53
estimated_files: 1
skills_used: []
---

# T02: Rewrite src/codegen.py: semantic naming + fix src.base crash

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

## Inputs

- `src/codegen.py`
- `tests/test_codegen.py`
- `resources/ground_truth/json_ws.gbnf`
- `resources/ground_truth/arithmetic.gbnf`
- `resources/ground_truth/c.gbnf`
- `resources/ground_truth/chess.gbnf`
- `resources/ground_truth/japanese.gbnf`
- `resources/ground_truth/list.gbnf`

## Expected Output

- `src/codegen.py`

## Verification

pytest tests/test_codegen.py -v && python -c "from src.codegen import build; m = build('resources/ground_truth/json_ws.gbnf'); assert 'ValueLiteral' in m, f'ValueLiteral missing, got: {sorted(m.keys())}'; assert 'ValueAlt4' not in m, 'ValueAlt4 still present'; print('OK:', sorted(m.keys()))"
