# Requirements

This file is the explicit capability and coverage contract for the project.

## Active

### R001 — GBNF Grammar to Pydantic Model Codegen
- Class: core-capability
- Status: active
- Description: Given a GBNF grammar file, generate a hierarchy of typed Pydantic model classes where alternation rules become abstract base + typed concrete subclasses (not flat Union fields). Write output to `src/generated/<grammar_name>.py` as real Python files.
- Why it matters: Type-safe model hierarchy is the foundation for parsing, serialization, and translation.
- Source: user
- Primary owning slice: M001/S01
- Supporting slices: none
- Validation: unmapped
- Notes: Use Lark when possible. Consider using jinja2 for the typographic details.
- Notes: Use `pydantic.create_model()` — no string assembly, no exec/eval. Classes built in memory first, then written to disk as real Python.

### R002 — Semantic Naming for Alternation Arms
- Class: core-capability
- Status: active
- Description: Alternation arms must get meaningful names derived from grammar structure (e.g., `ObjectValue`, `ArrayValue`, `TermExpr`), not sequential names like `Alt1`, `Alt2`.
- Why it matters: Tests explicitly lock these names; `Alt{N}` names are explicitly rejected.
- Source: user
- Primary owning slice: M001/S01
- Supporting slices: none
- Validation: unmapped
- Notes: Reference `SHIT/tests/test_codegen.py` for the name contracts that must hold. Tests written first.

### R003 — Lark Earley Runtime Parser
- Class: core-capability
- Status: active
- Description: Parse grammar-constrained text into instances of the generated Pydantic models using Lark Earley and a `Transformer` subclass. Rule names map to model constructors via the Transformer dispatch.
- Why it matters: Earley handles ambiguous grammars; Transformer dispatch replaces manual tree walking.
- Source: user
- Primary owning slice: M001/S02
- Supporting slices: M001/S01
- Validation: unmapped
- Notes: `SHIT/src/parser.py` has real nullable-rule handling and regex merging complexity — understand before rewriting.

### R004 — `to_text()` Round-Trip Serialization
- Class: core-capability
- Status: active
- Description: Every generated model class must implement `to_text()` that produces text parseable back into the exact same data structure. Grammar literals (punctuation, whitespace, delimiters) are baked into the method at codegen time.
- Why it matters: Round-trip fidelity is required; calling code passes no grammar at runtime.
- Source: user
- Primary owning slice: M001/S02
- Supporting slices: M001/S01
- Validation: unmapped
- Notes: `to_text()` is a codegen output — grammar structure informs the method body. Not a generic walker.
- Notes: Jinja2 might serve a purpose here.

### R005 — LLM Constrained Generation API
- Class: primary-user-loop
- Status: active
- Description: `generate(prompt, grammar_path, model_path) -> BaseModel` — runs the Approach B LLInterpreter loop, returns a parsed Pydantic model instance.
- Why it matters: This is the primary end-to-end user-facing entry point of the library.
- Source: user
- Primary owning slice: M001/S03
- Supporting slices: M001/S01, M001/S02
- Validation: unmapped
- Notes: Model path is caller-supplied. Architecture matches `quick_tst2.py` Approach B (lines 101-149).

### R006 — Cross-Grammar Translation
- Class: core-capability
- Status: active
- Description: `translate(instance_A, grammar_B_models) -> instance_B` — passes data from grammar A's model to grammar B's model constructor. Fails loudly if grammar B cannot accommodate grammar A's data shape. JSON output is the special case where grammar B = JSON schema.
- Why it matters: Core library capability; enables grammar interop.
- Source: user
- Primary owning slice: M001/S04
- Supporting slices: M001/S01, M001/S02
- Validation: unmapped
- Notes: Mechanism is `instance_A.model_dump()` → grammar B constructor. No field-name heuristics — structural compatibility or loud exception.

### R007 — Generic Across All 7 Ground-Truth Grammars
- Class: quality-attribute
- Status: active
- Description: All 7 grammars in `resources/ground_truth/` must work without any hardcoded grammar-specific logic.
- Why it matters: Hardcoded logic defeats the library's purpose and prevents future grammar support.
- Source: user
- Primary owning slice: M001/S05
- Supporting slices: M001/S01, M001/S02, M001/S03, M001/S04
- Validation: unmapped
- Notes: arithmetic, c, chess, japanese, json_arr, json_ws, list. `vyx.gbnf` is broken — not a test target.

### R008 — Tests Written Before Implementation
- Class: quality-attribute
- Status: active
- Description: Tests must be written first, must be thorough, and must cover complex edge cases and nested data structures. Test suite must pass for each slice before that slice is complete.
- Why it matters: Non-negotiable process rule from the brief. Failure to follow corrupts agent files.
- Source: user
- Primary owning slice: M001/S01
- Supporting slices: M001/S02, M001/S03, M001/S04, M001/S05
- Validation: unmapped
- Notes: Tests live in `tests/`. `SHIT/tests/test_codegen.py` is reference only — do not copy.

## Deferred

### R009 — CLI Interface
- Class: primary-user-loop
- Status: deferred
- Description: Command-line interface for grammar-to-codegen or generation workflows.
- Why it matters: Would improve developer ergonomics.
- Source: inferred
- Primary owning slice: none
- Supporting slices: none
- Validation: unmapped
- Notes: Explicitly out of scope per brief unless asked.

## Out of Scope

### R010 — Web Interface
- Class: anti-feature
- Status: out-of-scope
- Description: No web UI or HTTP API.
- Why it matters: Prevents scope creep; this is a Python library.
- Source: user
- Primary owning slice: none
- Supporting slices: none
- Validation: n/a
- Notes: Explicitly excluded per brief.

### R011 — Grammar-Specific Hardcoding
- Class: anti-feature
- Status: out-of-scope
- Description: No conditional logic, special cases, or hardcoded handling for specific grammar names or structures.
- Why it matters: Would make the library useless for new grammars.
- Source: user
- Primary owning slice: none
- Supporting slices: none
- Validation: n/a
- Notes: Explicitly excluded per brief.

## Traceability

| ID | Class | Status | Primary owner | Supporting | Proof |
|---|---|---|---|---|---|
| R001 | core-capability | active | M001/S01 | none | unmapped |
| R002 | core-capability | active | M001/S01 | none | unmapped |
| R003 | core-capability | active | M001/S02 | M001/S01 | unmapped |
| R004 | core-capability | active | M001/S02 | M001/S01 | unmapped |
| R005 | primary-user-loop | active | M001/S03 | M001/S01, S02 | unmapped |
| R006 | core-capability | active | M001/S04 | M001/S01, S02 | unmapped |
| R007 | quality-attribute | active | M001/S05 | M001/S01-S04 | unmapped |
| R008 | quality-attribute | active | M001/S01 | M001/S02-S05 | unmapped |
| R009 | primary-user-loop | deferred | none | none | unmapped |
| R010 | anti-feature | out-of-scope | none | none | n/a |
| R011 | anti-feature | out-of-scope | none | none | n/a |

## Coverage Summary

- Active requirements: 8
- Mapped to slices: 8
- Validated: 0
- Unmapped active requirements: 0
