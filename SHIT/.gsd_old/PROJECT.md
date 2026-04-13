# Project: vyx_2 — GBNF Grammar Toolkit

## What This Is

A Python toolkit that takes any valid GBNF grammar file and produces:
1. A **model generator** — reads the GBNF, emits Pydantic model classes with proper SOLID class hierarchies (alternation rules become abstract base + concrete subclasses, not `root: Union[...]`)
2. A **parser** — given grammar-constrained text and a GBNF, parses the text into those Pydantic instances using Lark Earley
3. A **generation interface** — wraps llama-cpp-python with grammar-constrained sampling (Approach A via guidance + llguidance) to produce text that can be immediately parsed into the model

## Core Value

Given a GBNF grammar and any text valid under that grammar, produce a typed Pydantic object hierarchy that can be serialized back to the original text (round-trip) or to JSON.

## Current State

**M001/S02 complete.** `src/parser.py` implements `parse(text, grammar_path) -> BaseModel` — the Lark Earley parser that converts grammar-valid text into typed Pydantic instances. 33/33 pytest tests pass (12 codegen + 21 parser).

- `src/codegen.py` — `build(grammar_path)` returns live Pydantic class dict; `build_file()` is the file-writing variant
- `src/parser.py` — `parse(text, grammar_path)` returns typed Root instance using Lark Earley at runtime
- `tests/test_codegen.py` — 12-test pytest suite for all 6 grammars (S01)
- `tests/test_parser.py` — 21-test pytest suite for all 6 grammars (S02)
- `FAILED_ATTEMPT/` — previous broken attempt (flat Union approach), kept for reference

Ground truth grammars in `resources/ground_truth/`: `json_ws.gbnf`, `arithmetic.gbnf`, `list.gbnf`, `chess.gbnf`, `japanese.gbnf`, `c.gbnf` (6 files — `json_arr.gbnbf` is absent).

`with_guidance.py` contains working prototypes:
- `_gbnf_to_earley_lark()` — GBNF → Lark Earley grammar (used by src/parser.py)
- `parse_vyx_to_dict()` — Lark Earley parse → dict (reference)
- Approach A (guidance + llguidance) — constrained generation, works

`tst.py` contains a simpler working generation loop using `LlamaGrammar`.

## Architecture / Key Patterns

- All new code goes in `src/`
- GBNF parsing via `llguidance.gbnf_to_lark.GrammarParser` + `resolve()`
- Lark Earley parser for grammar-constrained text parsing at runtime (no generated parser.py)
- Pydantic models with proper class inheritance (SOLID pattern)
- `parse()` always returns `Root` — the top-level grammar rule maps to Root, not a concrete subtype
- `model_construct()` used in _transform() to bypass Pydantic validation for complex field types
- Stack: Python 3.12+, pydantic, lark, llguidance, llama-cpp-python, guidance, numpy, rich

## Key Gotchas (see .gsd/KNOWLEDGE.md for full detail)

- `resolve()` renames 'root' → 'start' in-place; must reverse immediately after calling it
- `from __future__ import annotations` must be first line in exec'd code strings (circular forward refs)
- `model_rebuild()` must be called after ALL class definitions in generated code, not inline
- `parse()` always returns Root — ObjectValue/etc. are nested types, not the top-level result

## Capability Contract

See `.gsd/REQUIREMENTS.md` for the explicit capability contract, requirement status, and coverage mapping.
- R001 (SOLID inheritance) — **validated** by S01
- R002 (Lark Earley parse → typed Pydantic instances) — **validated** by S02

## Milestone Sequence

- [x] M001/S01: GBNF → Pydantic model generator (`build()` returning live class dict)
- [x] M001/S02: Grammar-Aware Parser: Text → Pydantic instances (Lark Earley at runtime)
- [ ] M001/S03: Ground Truth Gauntlet + Round-trip Verification (to_text/to_json)
- [ ] M001/S04: Clean Generation Interface + Integration
