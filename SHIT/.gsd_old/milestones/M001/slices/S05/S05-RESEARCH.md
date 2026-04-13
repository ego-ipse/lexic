# S05: Codegen Rewrite — tests-first — Research

**Date:** 2026-04-13
**Status:** Ready for planning

## Summary

Check /home/mika/projects/vyx_2/.gsd/milestones/M001/slices/S05/S05-CONTEXT.md for context

The current `src/codegen.py` has two hard failures: (1) it imports `from src.base import GrammarNode` but `src/base.py` does not exist, so `build()` crashes on every call; (2) the `_collect()` function generates `{ClassName}Alt{i}` positional names for any alternation arm that is not a bare `RuleRefNode`. This affects four rules across three grammars: `value` in json_ws/chess/japanese (produces `ValueAlt4`), `term` in arithmetic (produces `TermAlt2`), `statement` and `for_init` in c.gbnf (produce seven `StatementAlt{i}` and two `ForInitAlt{i}` names).

The test file `tests/test_grammar_toolkit.py` conflates codegen, parser, and serialization concerns — it cannot serve as a codegen contract. It must be deleted and replaced with `tests/test_codegen.py` that tests only `build()` and makes specific assertions about class names, `__bases__`, and field types derived from each grammar's structure.

The fix is a targeted rewrite of the `_collect()` function in `src/codegen.py` with a semantic naming algorithm for anonymous arms, plus removing the broken `src.base` import.

## Recommendation

**Write tests first (T01), confirm they fail on the existing broken code (T02), then rewrite `src/codegen.py` (T03).**

The semantic naming algorithm to implement in the rewrite:

1. **`RuleRefNode` arm**: `{RuleClassName}{ParentClassName}` — existing logic, already correct. e.g., `object` arm of `value` → `ObjectValue`.
2. **`SequenceNode` arm — first find alphabetic keyword literal**: scan nodes for the first `LiteralNode` whose value is purely alphabetic (a keyword, not punctuation). Use title-cased as suffix. e.g., `"return" ws expr ";"` → `StatementReturn`; `"while" "(" condition ")"...` → `StatementWhile`.
3. **`SequenceNode` arm — fallback to first non-ws `RuleRefNode`**: if no alpha keyword literal, find the first `RuleRefNode` not in `_WS_NAMES`. e.g., `"(" ws expr ")" ws` (arithmetic term arm 2) → first non-ws rule ref is `expr` → `TermExpr`; `[dataType, identifier, ...]` → `StatementDatatype`; `[identifier, ...]` → `StatementIdentifier`.
4. **`SequenceNode` arm — inline literal group as first node**: if the first substantive node is an `AlternativeNode` of literals (e.g., `("true"|"false"|"null") ws`), extract the first alphabetic literal from it → `ValueTrue`. Alternative: use `ValueLiteral`. **The test-writing task must commit to one of these names — that commits the implementation.**
5. **Duplicate name deduplication**: if two arms produce the same semantic name (e.g., c.gbnf `statement` arms 1 and 2 both map to `StatementIdentifier` via the fallback), disambiguate by including the second distinguishing non-ws element: arm 1 is `[identifier, ws, "=", ...]` → the first literal after identifier/ws is `"="` (not alpha, skip) → or use index suffix `StatementIdentifier2`. **The test must specify which deduplication strategy is used.**
6. **`LiteralNode` arm** (bare literal directly in alternation, rare): title-case the value → `{Parent}{TitleCasedLiteral}`.

## Implementation Landscape

### Key Files

- `src/codegen.py` — the only file to rewrite. The bug is in `_collect()` lines 222–273 (the `isinstance(alt, SequenceNode)` and `else` branches emit `{cname}Alt{i}`). The rest of the file (`ast_to_regex`, `_node_to_type`, `_sequence_fields`, `_topo_sort`, `_build_class_code`, `build`) is largely correct. `_build_class_code()` must also lose the `from src.base import GrammarNode` import and `GrammarNode` usage — top-level classes should inherit `BaseModel` directly.
- `tests/test_grammar_toolkit.py` — DELETE this file. It mixes codegen, parser, and serialization. Use it only as a reference for which grammar classes to assert, then discard.
- `tests/test_codegen.py` — CREATE this file (it does not exist yet). Tests only `build(grammar_path) -> dict[str, type]`. No `parse()`, no `to_text()`, no `to_json()`.
- `src/base.py` — does NOT exist (already deleted or never created). The import in `_build_class_code` must be removed.

### Concrete Bad Names to Fix (per grammar)

| Grammar | Rule | Bad name(s) | Cause |
|---------|------|-------------|-------|
| json_ws, chess, japanese | `value` | `ValueAlt4` | `SequenceNode` arm: `("true"\|"false"\|"null") ws` |
| arithmetic | `term` | `TermAlt2` | `SequenceNode` arm: `"(" ws expr ")" ws` |
| c.gbnf | `statement` | `StatementAlt0`–`StatementAlt6` | 7 `SequenceNode` arms |
| c.gbnf | `for_init` | `ForInitAlt0`, `ForInitAlt1` | 2 `SequenceNode` arms |

### AST Structure of Each Anonymous Arm

**json_ws value[4]**: `SequenceNode([AlternativeNode([Literal("true"), Literal("false"), Literal("null")]), RuleRef(ws)])`
- Strategy: inner `AlternativeNode` of literals, no alpha keyword literal at top level, no non-ws rule ref. Requires special handling.
- Recommended name: `ValueLiteral` (commit in test), with `value: str` field.

**arithmetic term[2]**: `SequenceNode([Literal("("), RuleRef(ws), RuleRef(expr), Literal(")"), RuleRef(ws)])`
- Strategy: first alpha keyword literal = none (`(` is punctuation). First non-ws rule ref = `expr` → `TermExpr`.
- Recommended name: `TermExpr`.

**c.gbnf statement[0]**: `SequenceNode([RuleRef(dataType), RuleRef(identifier), RuleRef(ws), Literal("="), RuleRef(ws), RuleRef(expression), Literal(";")])`
- First alpha keyword = none. First non-ws rule ref = `dataType` → `StatementDatatype`.

**c.gbnf statement[1]**: `SequenceNode([RuleRef(identifier), RuleRef(ws), Literal("="), ...])`
- First non-ws rule ref = `identifier` → `StatementIdentifier`.

**c.gbnf statement[2]**: `SequenceNode([RuleRef(identifier), RuleRef(ws), Literal("("), RepetitionNode, Literal(")"), Literal(";")])`
- First non-ws rule ref = `identifier` → **collision with [1]**. Must disambiguate.
- Options: scan for next distinguishing literal after first rule ref match — `"("` is punctuation, not alpha. Use `StatementIdentifier2` (index suffix on collision) or `StatementIdentifierCall`.

**c.gbnf statement[3–6]**: start with `Literal("return")`, `Literal("while")`, `Literal("for")`, `Literal("if")` → `StatementReturn`, `StatementWhile`, `StatementFor`, `StatementIf`.

**c.gbnf statement[7,8]**: `RuleRef(singleLineComment)`, `RuleRef(multiLineComment)` → `SinglelinecommentStatement`, `MultilinecommentStatement` (note: `to_class_name` splits on `_` and `-` only, not camelCase — `singleLineComment` becomes `Singlelinecomment`).

**c.gbnf for_init[0]**: starts with `RuleRef(dataType)` → `ForInitDatatype`.
**c.gbnf for_init[1]**: starts with `RuleRef(identifier)` → `ForInitIdentifier`. No collision here.

### Build Order

1. **T01 — Write `tests/test_codegen.py`**: Define the naming contract. Start with json_ws (most constrained: `Value`, `ObjectValue`, `ArrayValue`, `StringValue`, `NumberValue`, `ValueLiteral`, `Object`, `Root`, `Array`, `String`, `Number`). Commit to exact expected names. Include: no-AltN assertion (check no class name matches `r'\w+Alt\d+'`), SOLID hierarchy checks, field type checks. Delete `tests/test_grammar_toolkit.py`.
2. **T02 — Confirm tests fail on current code**: Run `pytest tests/test_codegen.py -v`. All tests must fail (current code crashes due to missing `src.base`). This validates the tests are non-trivial.
3. **T03 — Rewrite `src/codegen.py`**: Replace `_collect()` with semantic naming algorithm. Remove `src.base` import. Use `BaseModel` directly for top-level classes.
4. **T04 — Confirm tests pass**: Run `pytest tests/test_codegen.py -v`. All 6 grammars must pass.

### Verification Approach

```bash
# After T01:
pytest tests/test_codegen.py -v  # should fail (src.base missing + wrong names)

# After T03:
pytest tests/test_codegen.py -v  # should all pass
python -c "from src.codegen import build; m = build('resources/ground_truth/json_ws.gbnf'); print(sorted(m.keys()))"
# Expected: ['Array', 'Number', 'Object', 'ObjectValue', 'ArrayValue', 'StringValue', 'NumberValue', 'ValueLiteral', 'Root', 'String', 'Value', ...]
```

## Constraints

- `from __future__ import annotations` must be the first line in exec'd strings (KNOWLEDGE.md).
- `model_rebuild()` must be called after ALL class definitions, not inline (KNOWLEDGE.md).
- `resolve()` renames `root` → `start`; must reverse immediately after calling `resolve()` (KNOWLEDGE.md).
- Only 6 `.gbnf` grammars exist (json_arr.gbnbf is absent — KNOWLEDGE.md). Use `glob('*.gbnf')` not hardcoded count.
- `src/base.py` does not exist. `_build_class_code()` must not emit `from src.base import GrammarNode`. Top-level classes inherit `pydantic.BaseModel` directly.
- Tests use only the public API: `build(grammar_path) -> dict[str, type]`. No internal helpers.

## Common Pitfalls

- **`to_class_name` doesn't split camelCase** — `singleLineComment` → `Singlelinecomment`, not `SingleLineComment`. If this produces ugly class names, consider adding camelCase splitting to `to_class_name`. But only change this if the test specifies the improved form.
- **Duplicate semantic names** — c.gbnf statement arms 1 and 2 both resolve to `StatementIdentifier` under the first-non-ws-rule-ref strategy. The deduplication approach must be specified in the test before implementation. Recommended: collision → append index suffix (`StatementIdentifier2`), but the test locks the choice.
- **Inline literal group** — `("true"|"false"|"null") ws` is a `SequenceNode` whose first node is an `AlternativeNode` — neither a `LiteralNode` nor a `RuleRefNode`. Neither rule 1 nor rule 2 of the naming algorithm applies directly. Needs an explicit case: when first node is `AlternativeNode` of all-`LiteralNode` arms, use `Literal` as suffix → `ValueLiteral`. The test must assert this exact name.
- **`_BUILD_CACHE`** — the module-level cache means if a test imports `build()`, changes to rules won't be reflected in the same process unless the cache is cleared. Tests should use fresh grammar paths or clear the cache between runs. Not a problem if each test uses a unique grammar path, but be aware.
- **chess and japanese are identical to json_ws** — same grammar structure, same class names expected. Tests can reuse json_ws assertions for these.

## Open Risks

- The exact deduplication strategy for c.gbnf statement arms 1/2 may produce ugly names. The test must commit to one approach — if `StatementIdentifier2` looks bad, the implementer can choose a different approach but must update the test first.
- `to_class_name` camelCase handling: if the test requires `SingleLineComment` (not `Singlelinecomment`), the naming utility needs to be upgraded. Evaluate during test-writing.
