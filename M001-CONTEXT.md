# M001: VYX Core Library

**Gathered:** 2026-04-13
**Status:** Ready for planning

## Project Description

A Python library that turns any GBNF grammar into a typed, end-to-end pipeline: grammar → Pydantic models → constrained LLM generation → parsed instances → round-trip serialization → cross-grammar translation. Must work generically across all grammars — no hardcoded grammar logic anywhere.

## Why This Milestone

This IS the product. There are no prior milestones. The full library ships in one milestone.

## User-Visible Outcome

### When this milestone is complete, the user can:

- Call `codegen(grammar_path)` and get a hierarchy of typed Pydantic classes written to `src/generated/<name>.py`
- Call `parse(text, grammar_path)` and get a Pydantic model instance back
- Call `instance.to_text()` and get back text that parses to the same data structure
- Call `generate(prompt, grammar_path, model_path)` and get a typed Pydantic instance from LLM output
- Call `translate(instance_A, grammar_B_models)` to convert instances across grammars

### Entry point / environment

- Entry point: Python imports (`from src.codegen import codegen`, etc.)
- Environment: local dev, Python ≥ 3.10
- Live dependencies involved: llama_cpp model at caller-supplied path (generation only)

## Completion Class

- Contract complete means: all 7 ground-truth grammars produce correct codegen output; round-trip parse→to_text→parse gives identical structure; tests pass
- Integration complete means: generate() produces a parsed instance using the real gguf model; translation produces correct to_text() output across grammar pairs
- Operational complete means: none (no daemon, no service)

## Scope

### In Scope

- `src/codegen.py` — GBNF AST walking, `pydantic.create_model()`, writes `src/generated/*.py`
- `src/parser.py` — Lark Earley + Transformer subclass, returns Pydantic instances
- `src/base.py` — shared abstract base with `to_text()` and `to_json()` contract
- `src/generate.py` — `generate(prompt, grammar_path, model_path) -> BaseModel`, Approach B loop
- `src/translate.py` — `translate(instance_A, grammar_B_models) -> instance_B`
- `tests/` — written first, thorough, covers all 7 grammars
- `src/generated/*.py` — codegen output files, written to disk (not eval)

### Out of Scope / Non-Goals

- CLI or web interface
- Any hardcoded grammar-specific logic
- Verbatim reuse of SHIT/ code
- `vyx.gbnf` (broken, not a test target)

## Architectural Decisions

### `to_text()` is baked into each generated class

**Decision:** `to_text()` is emitted as a method body during codegen. Grammar literals (punctuation, whitespace, delimiters) are compiled into the method. Callers call `instance.to_text()` with no arguments — no grammar dependency at runtime.

**Rationale:** Translating data is passing the data, not the typographic rules. Each class knows its own grammar structure. This enforces the separation between data (model fields) and layout (grammar rules).

**Alternatives Considered:**
- Grammar-coupled walker at runtime — rejected: forces grammar to travel with data; breaks translation use case
- Generic base-class walker — rejected: can't know grammar literals without grammar present

---

### `pydantic.create_model()` over string assembly + exec

**Decision:** Use `pydantic.create_model()` to build classes in-memory, then write them to disk as real Python source files. No `exec()`, no string-assembled class bodies.

**Rationale:** No eval is a hard requirement from the user. `create_model()` builds real classes from field spec dicts — no topo-sort needed (Pydantic handles forward refs). Writing to disk is then a serialization step, not the mechanism.

**Alternatives Considered:**
- String assembly + exec (SHIT/ approach) — rejected: user explicitly said no eval
- Write-only (no in-memory classes) — rejected: generation of method bodies still needs the in-memory representation

---

### Lark Transformer over manual tree walker

**Decision:** Use a `Transformer` subclass to map grammar rule names to Pydantic model constructors. Lark dispatches via method name; no manual dispatch logic needed.

**Rationale:** SHIT/src/parser.py's `_transform_impl` reimplements what Lark's Transformer already does. Transformer dispatch is cleaner, less code, and more maintainable. The complex parts (nullable handling, regex merging) are Lark-specific and remain — that complexity is legitimate.

**Alternatives Considered:**
- Manual tree walker (SHIT/ approach) — rejected: duplicates Lark's built-in dispatch mechanism

---

### Translation via `model_dump()` → target constructor

**Decision:** `translate(instance_A, grammar_B_models)` calls `instance_A.model_dump()` and passes the resulting dict to grammar B's root model constructor. Fails loudly (raises `TranslationError`) if B cannot accommodate A's data shape.

**Rationale:** Data transfer, not grammar transfer. Grammar B's typographic rules stay in grammar B's classes. Structural mismatch is unrecoverable — no silent partial maps.

**Alternatives Considered:**
- Field-name matching heuristic — rejected: too fragile, not semantically meaningful
- JSON-as-pivot (via to_text → parse) — rejected: introduces format-dependency in the translation path

---

### Generation API: `generate(prompt, grammar_path, model_path) -> BaseModel`

**Decision:** Model path is a caller-supplied parameter. API matches the working Approach B pattern from `quick_tst2.py` lines 101–149.

**Rationale:** Model path changes per deployment. Baking it in would make the library non-portable.

**Alternatives Considered:**
- Environment variable for model path — deferred to later if needed

## Error Handling Strategy

- `ParseError` — raised when Lark Earley cannot parse the input under the grammar
- `TranslationError` — raised when grammar B cannot accommodate grammar A's data shape
- `CodegenError` — raised when the GBNF AST contains structures the codegen cannot handle
- Generation failures propagate from `llguidance` / `llama_cpp` unchanged
- No silent partial failures anywhere — all errors are loud and typed

## Risks and Unknowns

- `to_text()` codegen complexity — grammar literals must be reconstructed from the AST. The SHIT reference didn't implement this, so the AST walk for emitting method bodies is unproven. Retire in S02.
- Nullable rule handling in Lark — SHIT/src/parser.py has non-trivial fixes for Lark's handling of nullable rules. Must be understood and re-implemented correctly. Retire in S02.
- `pydantic.create_model()` for abstract base classes — `create_model()` builds concrete models; abstract base + subclass hierarchy needs explicit class body wiring. Approach needs verification. Retire in S01.

## Existing Codebase / Prior Art

- `SHIT/src/codegen.py` — prior codegen; walk logic and `_sem_name` approach are useful references. `_ClassDef` string assembly is NOT reused.
- `SHIT/src/parser.py` — prior parser; nullable handling and regex merging are non-obvious, must be understood. Transformer dispatch structure is NOT reused verbatim.
- `SHIT/tests/test_codegen.py` — locks specific naming contracts (`ObjectValue`, `ArrayValue`, `TermExpr`, `SingleLineCommentStatement`). New tests must satisfy the same contracts.
- `quick_tst2.py` lines 101–149 — the Approach B generation loop. `generate()` wraps this directly.
- `resources/ground_truth/` — 7 authoritative test grammars.

## Relevant Requirements

- R001, R002 — Codegen + naming (S01)
- R003, R004 — Parser + serialization (S02)
- R005 — Generation API (S03)
- R006 — Translation (S04)
- R007, R008 — Cross-grammar coverage + tests-first discipline (spans all slices)

## Testing Requirements

Tests written before implementation for every slice. Must cover:
- All 7 ground-truth grammars for codegen (S01)
- Round-trip parse → to_text → parse for representative inputs (S02)
- generate() with real gguf model (S03) — model at `/home/mika/gemma-4-26B-A4B-it-Q4_K_M.gguf`
- Translation across grammar pairs including failure cases (S04)
- Complex nested structures, not just simple happy paths

## Acceptance Criteria

- **S01:** `codegen(grammar_path)` produces a `src/generated/<name>.py` file with correct abstract base + subclass hierarchy for all 7 grammars. Semantic naming matches SHIT/tests/test_codegen.py contracts. Tests pass before implementation written.
- **S02:** `parse(text, grammar_path)` returns correct Pydantic instances. `instance.to_text()` produces text that re-parses to identical structure (round-trip). All 7 grammars.
- **S03:** `generate(prompt, grammar_path, model_path)` returns a typed Pydantic instance. Integration test uses real gguf model.
- **S04:** `translate(instance_A, grammar_B_models)` produces correct instance_B for compatible grammars; raises `TranslationError` for incompatible shapes.
- **S05:** End-to-end: grammar → codegen → generate → parse → to_text → translate, full pipeline across at least 3 grammar pairs.

## Open Questions

- How does `pydantic.create_model()` handle abstract base classes and subclass registration? Needs spike in S01. — Current thinking: use a factory that creates both the ABC and subclasses, registers them via `__subclasses__`, and wires Pydantic discriminated unions.
- For `to_text()` in generated files: should the method bodies be emitted as raw Python source (written when writing the .py file), or should the in-memory classes carry lambdas that get serialized? — Current thinking: emit raw Python method bodies when writing the .py file; the in-memory class carries the live method.
