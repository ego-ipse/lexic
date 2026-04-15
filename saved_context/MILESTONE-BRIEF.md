# Milestone Brief — VYX

This document must be read before any planning begins. It is the authoritative source of truth for what this milestone must build, how it must be built, and what constraints apply.

---

## What This Is

A Python library that:

1. Takes a GBNF grammar file
2. Generates typed Pydantic data models from it (GBNF → Pydantic classes)
3. Constrains an LLM to produce output valid under that grammar
4. Parses the LLM output into instances of those Pydantic models
5. Can serialize those instances back to the original grammar text (`to_text()`)
6. Can convert instances from one grammar's model to another grammar's model, then print to text — JSON output is a specific case of this

---

## Non-Negotiable Process Rules

- **FAILING TO RESPECT THIS WILL RESULT IN HUMAN ACTIVELY CORRUPTING AGENT FILES** This is not a threat, it's a fact.
- **The agent MUST ask questions as it goes. No assumptions without confirmation.**
- **No worktrees.**
- **Tests are written first. Tests must be thorough — complex edge cases, nested data structures.**
- **SOLID principles throughout. Clean, separated code. Not a jumbled mess.**
- **Existing code in `SHIT/` can be referenced but must not be reused verbatim.**

---

## Architecture

### LLM Constrained Generation — Approach B

Use the raw `llguidance` LLInterpreter loop as implemented in `quick_tst2.py` (`approach_b`), not the high-level guidance API (`approach_a`).

The generation loop (from `quick_tst2.py:101-149`):
1. Build `LLInterpreter` from grammar
2. Tokenize and eval the prompt
3. Each step: `compute_mask_into` → read logits via `llama_get_logits` → apply mask → sample → `commit_token`
4. Stop when grammar is accepting or EOS sampled

### Grammar → Pydantic Models

Use **Lark** to parse the GBNF grammar and derive structure. Generate **Pydantic** model classes where:
- Alternation rules become abstract base classes with concrete subclasses (not `root: Union[...]` flat fields)
- Hierarchy preserves type information and makes the model extensible

### Parser

Use **Lark Earley** at runtime to parse grammar-constrained LLM output into instances of the generated Pydantic models.

### Serialization

Every Pydantic model instance must implement:
- `to_text()` — reconstruct the original grammar text by walking the model
- `to_json()` / `model_dump()` — JSON-compatible dict

### Cross-Grammar Translation

Printing a text written in Grammar A in Grammar B:
```
parse(text_A, grammar_A) → instance_A  →  translate(instance_A, grammar_B) → instance_B  →  to_text(instance_B)
```
JSON output is the special case where Grammar B = JSON schema.

---

## Stack

- `lark` — GBNF parsing and runtime text parsing (Earley)
- `pydantic` — data model base
- `llguidance` — grammar-constrained token masking
- `llama_cpp` — LLM inference backend
- `guidance` — only if needed for high-level utilities; primary generation path is Approach B

---

## Ground Truth Test Grammars

All 7 grammars in `resources/ground_truth/` must work without hardcoding grammar-specific logic:

- `arithmetic.gbnf`
- `c.gbnf`
- `chess.gbnf`
- `japanese.gbnf`
- `json_arr.gbnbf`
- `json_ws.gbnf`
- `list.gbnf`

The `vyx.gbnf` in `resources/` is broken — not a test target.

---

## What Exists

- `resources/ground_truth/` — 7 reference grammars
- `resources/vyx.gbnf` — broken, ignore
- `quick_tst2.py` — working proof-of-concept for Approach B generation loop
- `quick_tst.py` — earlier experiment, reference only
- `SHIT/src/codegen.py` — prior codegen implementation (reference only, do not reuse)
- `SHIT/src/parser.py` — prior parser (reference only, do not reuse)
- `SHIT/tests/test_codegen.py` — prior tests (reference only, do not reuse)
- `src/` — currently empty, this is where the new code goes

---

## What Does NOT Exist Yet

- `src/codegen.py`
- `src/parser.py`
- `src/base.py` (or equivalent)
- Any test suite
- Any translation layer

---

## Scope Boundaries

- Do NOT build a CLI or web interface unless explicitly asked
- Do NOT hardcode grammar-specific logic anywhere
- Do NOT use `SHIT/` code verbatim — it is reference material only
- Do NOT make assumptions — ask
