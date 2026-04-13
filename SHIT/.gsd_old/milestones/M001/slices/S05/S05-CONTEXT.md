---
id: S05
milestone: M001
status: ready
---

# S05: Codegen Rewrite — tests-first — Context

## Goal

Rewrite `src/codegen.py` so that `build(grammar_path)` produces a correct, meaningful Pydantic class dict — SOLID inheritance, semantic class names (never `ValueAlt4`), field types that reflect the grammar structure — verified by tests that are written first and that a bad implementation cannot pass.

## Why this Slice

S01/S02 produced code that passed tests engineered to pass it. The test suite and implementation were co-evolved, which is why the tests are worthless. This slice breaks that cycle: tests are written from the grammar contracts before any implementation exists, so the implementation has to satisfy an external specification. S06 (parser rewrite) and everything after depend on `build()` being correct.

## Scope

### In Scope

- Delete `tests/test_grammar_toolkit.py` (read as reference, then discard — it conflates codegen, parser, and serialization concerns)
- Delete `src/base.py` (the `_raw` approach is wrong — AST reconstruction is the correct mechanism; base class design belongs in S06 when the parser is built)
- Write `tests/test_codegen.py` from scratch — tests only codegen concerns, written before implementation
- Rewrite `src/codegen.py` from scratch — the existing implementation produced `ValueAlt4`-style names, which is a fundamental naming failure
- Anonymous alternation arms must get semantic names derived from content: e.g. `value ::= "true" | "false" | object` → `ValueTrue`, `ValueFalse`, `ObjectValue`
- All 6 ground_truth grammars must produce a correct class dict
- Tests must pass only a correct implementation — a broken implementation (wrong names, wrong bases, missing classes, flat Union fields) must fail the tests

### Out of Scope

- `src/parser.py` — parser rewrite is S06
- `to_text()`, `to_json()` — serialization is S06/S07
- `src/base.py` replacement / new base class design — belongs in S06 when the parser and serialization contract is clear
- `build_file()` — file-writing variant; not tested, not a priority
- `vyx.gbnf` — deferred as before

## Constraints

- Tests are written before any implementation. The implementation task starts only after the test task is complete and the tests are confirmed to fail on the existing broken `src/codegen.py`.
- No `ValueAlt4`, `ValueAlt2`, `RuleAlt3` or any positional/indexed names for alternation arms. Every generated class must have a name derivable from grammar content.
- SOLID inheritance is non-negotiable (D002): AlternativeNode rules → abstract base + typed concrete subclasses. `Union` fields are forbidden.
- Tests use only the public API: `build(grammar_path) -> dict[str, type]`. No testing of internal functions (`_build_class_code`, `_topo_sort_rules`, etc.).
- If a test would require knowing about `to_text()` or `to_json()`, it belongs in S06/S07 — move it there.

## Integration Points

### Consumes

- `resources/ground_truth/` — 6 `.gbnf` grammar files used as test fixtures (arithmetic, c, chess, japanese, json_ws, list)
- `tests/test_grammar_toolkit.py` — read for contract ideas, then deleted
- `llguidance.gbnf_to_lark.GrammarParser` + `resolve()` — GBNF AST parsing (keep this, it works; the naming and class generation logic is what needs replacing)
- `.gsd/KNOWLEDGE.md` — `resolve()` renames 'root'→'start' in-place; `from __future__ import annotations` must be first line in exec'd strings; `model_rebuild()` after all class defs

### Produces

- `tests/test_codegen.py` — contract test suite for `build()`: correct class names, correct `__bases__`, correct field types, all 6 grammars, SOLID hierarchy. Written before implementation.
- `src/codegen.py` (rewritten) — `build(grammar_path) -> dict[str, type]` with semantic naming and correct SOLID hierarchy for all 6 ground_truth grammars

## Open Questions

- **Semantic name derivation for anonymous literal arms**: when an alternation arm is a literal with no rule name (e.g. `"true"`, `"false"`, `"null"`), the class name should be derived from the literal content: `ValueTrue`, `ValueFalse`, `ValueNull`. The exact capitalisation and sanitisation rules (e.g. for literals with special characters) should be resolved during the test-writing task — the test specifies the expected name, which locks the contract.
- **Inline sequence arms**: when an alternation arm is an anonymous sequence (not a single literal), the name should be derived from the sequence content or a summary of it. This is a harder case — if a clean name can't be derived, consider whether the arm should be a subclass with a `value: str` field rather than generating a garbage name. Resolve during test-writing task.
