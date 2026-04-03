# Design: Generic GBNF → Bidirectional Pipeline

**Date:** 2026-03-31
**Project:** vyx_2
**Source:** `way_fwd.md`

---

## Goal

Given ANY valid GBNF grammar file and a Vyx-format spec document composed from it, produce:

1. A set of Pydantic `BaseModel` subclasses — one per grammar rule
2. A bidirectional pipeline: `text ↔ Pydantic model instances ↔ JSON`

The system does not generate Vyx. It round-trips existing text in any language whose grammar is expressed in GBNF and whose semantics are expressed in a Vyx-format spec.

---

## Architecture

Two layers compose into one pipeline:

```
GBNF file
    │
    ▼ gbnf.py (exists)
GBNFNode IR
    │
    ├──► builder.py (refactor)
    │         └── Pydantic BaseModel subclasses (one per grammar rule)
    │                   │
    │         ◄──────── validation: model_json_schema()
    │                              → pydantic_models_to_grammar.py
    │                              → compare to original GBNF
    │
    └──► interpreter.py (new: PEG over GBNFNode IR)
              │
    ┌─────────┤
    │         │
    │    Spec doc (Vyx format)
    │         │
    │         ▼ spec/extractor.py
    │    (section_id, body_text) pairs
    │         │
    │         ▼ spec/compiler.py  [uses interpreter]
    │    DSection models
    │         │
    │         ▼ spec/enricher.py
    │    Validators + constraints applied to grammar models
    │
    ▼
text ──► interpreter.py ──► model instances ──► model_dump() ──► JSON
text ◄── emitter.py ◄────── model instances ◄── model_validate() ◄── JSON
```

---

## Layer 1 — Grammar

### `gbnf.py` (exists, unchanged)

Parses GBNF text into `GBNFNode` IR. Pure Python, no dependencies. Exports:
`GBNFParser`, `GBNFNode` subtypes, `first_terminal`, `dispatch_table`, `_unescape`.

### `builder.py` (refactor)

**In:** `dict[str, GBNFNode]`
**Out:** `dict[str, type[BaseModel]]`

One `BaseModel` subclass per grammar rule. Field names and types derived from rule
structure. No `VyxBase`, no sigil registry, no Vyx-specific knowledge.

Field type derivation (unchanged from current logic):
- `GBNFLiteral` all-terminal → `Literal[values]`
- `GBNFAlternation` mixed → `Union` of types
- `GBNFSequence` → model with typed fields
- `GBNFRepetition(min=1)` → `list` with `Field(min_length=1)`
- `GBNFOptional` → `type | None`
- `GBNFReference` → the model for that rule
- `GBNFCharClass` → `str`

The refactor removes: `VyxBase` as base, `SIGIL` class var, `_sigil_registry`,
`_children` / `_append_child`, and the re-export of `dispatch_table` (it remains in
`gbnf.py`; `builder.py` no longer wraps it).

### `interpreter.py` (new)

PEG interpreter. Walks `GBNFNode` IR to parse arbitrary text into model instances.

```
parse(rules, rule_name, text, pos) → (instance, new_pos) | None
```

Node handling:
- `GBNFLiteral` → match string literal at pos
- `GBNFCharClass` → match character class (regex)
- `GBNFSequence` → match each element in order; build field dict; instantiate model
- `GBNFAlternation` → try each arm in order (PEG: first match wins); return first success
- `GBNFRepetition(min=0/1)` → greedy; collect list; fail if count < min
- `GBNFOptional` → try; return None on no match (never fails)
- `GBNFReference` → recurse into named rule

Constraint: no Vyx knowledge. Works for any grammar whose rules are in the IR.

### `emitter.py` (new)

Walks a model instance tree and emits text. Driven by the same `GBNFNode` IR.

```
emit(rules, rule_name, instance) → str
```

Round-trip invariant: `parse(emit(instance)) == instance` (structural identity).

---

## Layer 2 — Spec

### `spec/extractor.py` (new)

Reads a markdown file. Finds Vyx fences (`` ```@:section_id `` ... `` ``` ``).

**Out:** `list[tuple[str, str]]` — `(section_id, body_text)` per section.

No semantic knowledge. No Vyx parsing. Pure string extraction.

### `spec/models.py` (new)

Pydantic models for compiled spec output:

```python
class ErrorCode(BaseModel):
    condition: str
    severity: Literal["soft", "hard", "fatal"]

class GrammarBlock(BaseModel):
    rules: dict[str, str]
    terminals: dict[str, str]
    deps: list[str]

class DSection(BaseModel):
    id: str
    full: str
    fields: dict[str, Any]       # KV data from spec body
    tables: dict[str, list[Any]] # named tables ($TAG rows)
    grammar: GrammarBlock | None
    errors: dict[str, ErrorCode]
```

### `spec/compiler.py` (new)

Uses `interpreter.py` to parse each `body_text` (from extractor) against the Vyx grammar.
Walks the resulting model instances to populate `DSection` fields.

**In:** `list[tuple[str, str]]` from extractor + Vyx `GBNFNode` rules (from `gbnf.py`
parsing `grammar.gbnf`)
**Out:** `dict[str, DSection]`

Bootstrapping: Layer 1 provides enough structural parsing to read the spec without
semantic validation. The spec is well-formed by construction.

### `spec/enricher.py` (new)

Reads `DSection` models. Derives validators and constraints. Applies them to the
grammar-derived `BaseModel` subclasses via `model_rebuild()`.

Examples of enrichment derived from spec data:
- `key: max=32` → `Field(max_length=32)` on the `key` field
- `id: min=1 max=12` → `Field(min_length=1, max_length=12)`
- `merge-op: context="o:meta only"` → `model_validator` (mode="before") added via `model_rebuild()`
- `errors: DANGLING_REF severity=soft` → registered post-parse hook

Nothing hardcoded. All enrichment is data-driven from `DSection.fields` and
`DSection.errors`.

---

## Validation

**GBNF → Pydantic → GBNF roundtrip:**

1. Run `builder.py` on a grammar → get Pydantic model classes
2. Call `model_json_schema()` on the classes
3. Feed through `pydantic_models_to_grammar.py` (llama.cpp)
4. Compare output GBNF to input GBNF

This validates Goal 1 (`gbnf <-> pydantic model`) structurally. Semantic enrichments
from the spec are validated separately via the round-trip invariant on parsed instances.

---

## Implementation Phases

| Phase | File | Deliverable | Test |
|-------|------|-------------|------|
| P0 | `gbnf.py` | Unchanged | Existing tests pass |
| P1 | `builder.py` | Refactored — `BaseModel` not `VyxBase` | Every model is a `BaseModel` subclass; `dispatch_table` removed |
| P2 | `interpreter.py` | PEG parse + instantiate | Round-trips D.13 packet structurally |
| P3 | `emitter.py` | Text emission | `parse(emit(x)) == x` for all D sections |
| P4 | `spec/extractor.py` | Markdown → body_text pairs | Extracts D.1–D.17; none empty |
| P5 | `spec/compiler.py` + `spec/models.py` | DSection per section | D.3 grammar.rules correct; errors compiled |
| P6 | `spec/enricher.py` | Constraints on models | `key` field rejects len > 32; error codes registered |

---

## Invariants

1. `grammar.gbnf` is the only place target-language structure is defined
2. No Python file hardcodes a grammar rule name, sigil character, or field constraint
3. Generated models are plain `BaseModel` subclasses — no Vyx-specific base
4. Other grammars may have their own structural patterns; none are assumed here
5. `parse(emit(instance)) == instance` — structural round-trip, not string identity
6. Spec enrichment is data-driven from `DSection`; no enrichment logic is Vyx-specific
7. `interpreter.py` and `emitter.py` have zero knowledge of any target language

---

## Dependencies

- `pydantic` — accepted
- `pydantic-ai` — accepted (for LLM integration layer, not core pipeline)
- `llama-cpp-python` — accepted (for validation and constrained generation)
- No others without explicit approval
