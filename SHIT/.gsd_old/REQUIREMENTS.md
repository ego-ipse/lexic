# Requirements

This file is the explicit capability and coverage contract for the project.

## Active

### R001 — GBNF to Pydantic model generator with SOLID inheritance
- Class: core-capability
- Status: active
- Description: Given any valid GBNF file, generate Pydantic model classes where alternation rules become abstract base classes with concrete subclasses, not flat `root: Union[...]` fields
- Why it matters: Proper inheritance makes the model type-safe, extensible, and suitable for transformation. The failed attempt's Union approach collapsed all type information.
- Source: user
- Primary owning slice: M001/S01
- Supporting slices: none
- Validation: unmapped
- Notes: `value ::= object | array | string ...` → abstract `Value(BaseModel)` + `ObjectValue(Value)`, `ArrayValue(Value)`, `StringValue(Value)`, etc.

### R002 — Text-to-Pydantic parser using grammar
- Class: primary-user-loop
- Status: active
- Description: Given a GBNF grammar and text valid under that grammar, parse the text into the corresponding Pydantic model instances using Lark Earley at runtime
- Why it matters: This is the core consumption pattern — take constrained LLM output and turn it into typed structured data
- Source: user
- Primary owning slice: M001/S02
- Supporting slices: M001/S01
- Validation: unmapped
- Notes: No generated parser.py — Lark Earley handles this at runtime. Builds on `_gbnf_to_earley_lark()` from with_guidance.py.

### R003 — Round-trip serialization: to_text() and to_json()
- Class: core-capability
- Status: active
- Description: Every Pydantic model instance can serialize back to the original grammar text (to_text()) and to a JSON-compatible dict (to_json()). Parse-serialize-parse is lossless.
- Why it matters: The model is only useful if you can get data out. Round-trip correctness is the definition of a complete parse cycle.
- Source: user
- Primary owning slice: M001/S03
- Supporting slices: M001/S01, M001/S02
- Validation: unmapped
- Notes: JSON round-trip: parse JSON text with json_ws grammar → Pydantic → to_json() reproduces the same JSON. In other grammar pairings (input grammar ≠ output grammar), to_json() is a translation.

### R004 — Works for any valid GBNF (genericity)
- Class: quality-attribute
- Status: active
- Description: The generator and parser must work for all 7 ground_truth grammars without hardcoding grammar-specific logic
- Why it matters: The whole point is a generic tool, not a vyx-specific one. Vyx grammar is broken and not a test target.
- Source: user
- Primary owning slice: M001/S04
- Supporting slices: M001/S01, M001/S02
- Validation: unmapped
- Notes: Ground truth grammars: json_ws, arithmetic, list, chess, japanese, json_arr, c

### R005 — Clean grammar-constrained generation interface
- Class: primary-user-loop
- Status: active
- Description: A clean API that takes a GBNF grammar and a prompt, runs constrained LLM generation (Approach A), and returns a parsed Pydantic instance
- Why it matters: Closes the loop: grammar → constrained generation → parsed model
- Source: user
- Primary owning slice: M001/S04
- Supporting slices: M001/S01, M001/S02
- Validation: unmapped
- Notes: Based on Approach A from with_guidance.py (works). Approach B (LLMatcher direct) produces nonsense due to double-consume — excluded from scope.

## Deferred

### R006 — Fix vyx.gbnf
- Class: core-capability
- Status: deferred
- Description: Fix vyx.gbnf which is fundamentally broken (doesn't terminate, produces invalid output, doesn't produce intended output)
- Why it matters: Vyx is the eventual target grammar, but it's not usable as a test surface right now
- Source: user
- Primary owning slice: none
- Supporting slices: none
- Validation: unmapped
- Notes: Deferred until the toolkit is proven on ground_truth grammars. vyx.gbnf is treated as intention, not ground truth.

## Out of Scope

### R007 — Approach B (raw LLMatcher logits processor)
- Class: anti-feature
- Status: out-of-scope
- Description: The raw llguidance LLMatcher as a LogitsProcessor (Approach B in with_guidance.py)
- Why it matters: Prevents effort on a dead end — it produces nonsense due to double-consuming tokens in the logits processor
- Source: user
- Primary owning slice: none
- Supporting slices: none
- Validation: n/a
- Notes: Approach A is the generation path. Approach B is excluded.

### R008 — Generated parser.py (hand-rolled recursive descent)
- Class: anti-feature
- Status: out-of-scope
- Description: Code-generate a parser.py with recursive descent parse functions for each grammar rule
- Why it matters: Prevents rebuilding the wrong thing — Lark Earley at runtime is more correct and requires no generated code
- Source: user
- Primary owning slice: none
- Supporting slices: none
- Validation: n/a
- Notes: The FAILED_ATTEMPT approach. Lark Earley handles parsing without generated code.

## Traceability

| ID | Class | Status | Primary owner | Supporting | Proof |
|---|---|---|---|---|---|
| R001 | core-capability | active | M001/S01 | none | unmapped |
| R002 | primary-user-loop | active | M001/S02 | M001/S01 | unmapped |
| R003 | core-capability | active | M001/S03 | M001/S01, M001/S02 | unmapped |
| R004 | quality-attribute | active | M001/S04 | M001/S01, M001/S02 | unmapped |
| R005 | primary-user-loop | active | M001/S04 | M001/S01, M001/S02 | unmapped |
| R006 | core-capability | deferred | none | none | unmapped |
| R007 | anti-feature | out-of-scope | none | none | n/a |
| R008 | anti-feature | out-of-scope | none | none | n/a |

## Coverage Summary

- Active requirements: 5
- Mapped to slices: 5
- Validated: 0
- Unmapped active requirements: 0
