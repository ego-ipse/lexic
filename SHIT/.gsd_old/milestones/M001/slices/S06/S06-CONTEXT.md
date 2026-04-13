---
id: S06
milestone: M001
status: ready
---

# S06: Parser Rewrite + to_text() — Context

## Goal

Rewrite `src/parser.py` from scratch, tests-first, so that `parse(text, grammar_path)` returns a correctly typed Pydantic instance and every instance's `to_text()` reconstructs a canonical form of the input — using AST field traversal, not raw text replay.

## Why this Slice

S02's parser passes tests that were written to match its bugs. The existing implementation uses `_raw` text span storage for `to_text()`, which bypasses the AST entirely and defeats the purpose of having typed Pydantic models. S05 delivers correct generated classes — this slice delivers the correct parser that populates them and a `to_text()` that proves the AST is actually correct by reconstructing from structure. S07 (cross-grammar printing) and S08 (generation) both depend on a working parser + `to_text()`.

## Scope

### In Scope

- Full rewrite of `src/parser.py` — delete and replace, not patch
- `GrammarNode` base class in `src/base.py` (or equivalent) with `to_text()` — all generated classes inherit from it
- `to_text()` reconstructs by walking model fields (AST reconstruction), not by storing/replaying raw text spans
- Canonical output: `to_text()` reconstructs by emitting what the AST fields hold — no more, no less. If a whitespace token was captured as a field value because the grammar assigns it (e.g. a Python grammar rule that captures indentation or required inter-token space), it is emitted. If whitespace was never part of the parsed structure (e.g. the spaces in `{ "city" : "Porto" }` were not captured as fields), it is not emitted. Canonical form falls out of AST structure, not from a whitespace-suppression heuristic.
- `parse(text, grammar_path) -> Root` public API unchanged
- Tests written first in `tests/test_parser.py` — tests must fail against any naive or broken implementation
- Tests cover all 6 ground-truth grammars: parse known-good inputs, assert correct type hierarchy, assert `to_text()` produces correct canonical output
- Rejection tests: malformed input raises, wrong grammar raises

### Out of Scope

- `to_json()` — belongs to S07 (cross-grammar printing)
- `print_as(grammar_b)` — S07
- Generation — S08
- `src/base.py`'s `_raw` storage approach — removed; `to_text()` must not use it
- Whitespace preservation of accidental input whitespace — `to_text()` does not try to remember what the input looked like
- Whitespace suppression heuristics — do not add logic that strips whitespace; let the AST structure determine what appears in the output

## Constraints

- Tests come before implementation. The test file must be complete and failing before `src/parser.py` is touched.
- `to_text()` must live on `GrammarNode` base class — not per-class codegen output, not per-instance monkey-patching.
- No `_raw` field or raw text span storage anywhere in `GrammarNode` or generated classes.
- All 6 ground-truth grammars must parse and round-trip through `to_text()` — parametrized tests, not one-offs.
- `uv run pytest tests/test_parser.py -v` is the verification gate.

## Integration Points

### Consumes

- `src/codegen.py` — `build(grammar_path) -> dict[str, type]` — live Pydantic class dict produced by S05; parser uses these classes to instantiate typed instances
- `resources/ground_truth/*.gbnf` — 6 known-correct grammars used as test fixtures
- `llguidance.gbnf_to_lark.GrammarParser` + `resolve()` — GBNF → Lark grammar conversion (same as S02, keep what works)
- `lark.Lark` with `parser="earley"` — Earley parser for grammar-constrained text

### Produces

- `src/parser.py` — rewritten `parse(text, grammar_path) -> Root`; internal `_transform()` that instantiates correct typed subclasses
- `src/base.py` — `GrammarNode(BaseModel)` with `to_text()` doing AST field traversal (replaces the `_raw`-based version)
- `tests/test_parser.py` — test suite that must fail against any naive implementation: type hierarchy, canonical `to_text()` round-trip for all 6 grammars, rejection cases

## Open Questions

- Whitespace fidelity vs. AST reconstruction: the whitespace model is "emit what the AST holds." For JSON, spaces between tokens are not captured as fields so canonical output is compact. For Python or similar grammars where indentation/spacing is structurally significant, the grammar would capture those as token values and they would be emitted. The open question is whether any of the 6 ground-truth grammars have mandatory inter-token whitespace that is currently dropped by the tokenizer before the AST is built — if so, those tokens need to be preserved in the model fields. Confirm against each grammar during T01.
