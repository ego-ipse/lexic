# M001: Grammar Toolkit — Context

**Gathered:** 2026-04-12
**Status:** Ready for planning

## Project Description

A generic toolkit that takes any GBNF grammar file and produces:
1. Pydantic model classes with SOLID class hierarchies (code generator)
2. A parser: grammar-constrained text → Pydantic instances (Lark Earley at runtime)
3. Round-trip serialization: to_text() and to_json() on every model instance
4. A clean constrained generation interface wrapping Approach A (guidance + llguidance)

The failed attempt in `FAILED_ATTEMPT/` is architecturally wrong and is not a starting point — read it only to understand what not to do.

## Why This Milestone

The existing code is broken in the right ways to learn from:
- `builder.py` has the right GBNF parsing infrastructure (`GrammarParser` + `resolve()`) but wrong model generation (flat Union fields instead of inheritance) and a broken parser generator
- `with_guidance.py` has the right Lark Earley approach (`_gbnf_to_earley_lark()`) and working Approach A generation
- Ground truth grammars are ready and known-correct

## User-Visible Outcome

### When this milestone is complete, the user can:

- Run the model generator on any ground_truth grammar and get importable Pydantic classes with proper inheritance
- Call `parse(text, grammar_path)` to get a typed Pydantic instance from any grammar-valid text
- Call `.to_text()` on any instance to get back the original text
- Call `.to_json()` to get a dict — if the input was JSON (json_ws grammar), the output matches the input exactly
- Call `generate(prompt, grammar_path)` to get a constrained LLM response as a Pydantic instance

### Entry point / environment

- Entry point: `python -c "from src.codegen import build; build('resources/ground_truth/json_ws.gbnf')"` and `python -c "from src.parser import parse; ..."`
- Environment: local dev with `uv run`
- Live dependencies: llama-cpp-python model at `MODEL_PATH` for generation only; parser and codegen work without a model

## Completion Class

- Contract complete means: model generator produces importable classes for all 7 ground_truth grammars; parser round-trips all ground_truth sample texts
- Integration complete means: generate() produces text that parse() accepts and round-trips correctly
- Operational complete means: none (no service lifecycle)

## Final Integrated Acceptance

To call this milestone complete, we must prove:

- `build('resources/ground_truth/json_ws.gbnf')` → importable `Root`, `Value`, `ObjectValue`, `ArrayValue`, `StringValue`, `NumberValue` (etc.) with correct `__bases__`
- `parse('{"city": "Porto"}', json_ws_grammar)` returns an `ObjectValue` instance; `.to_text()` returns `'{"city": "Porto"}'`; `.to_json()` returns `{"city": "Porto"}`
- All 7 ground_truth grammars parse known-good samples without error

## Architectural Decisions

### Parser: Lark Earley at runtime, no generated parser.py

**Decision:** Use `_gbnf_to_earley_lark()` (adapted from `with_guidance.py`) to build a Lark grammar at parse time. Use a Lark Transformer to walk the tree and instantiate Pydantic models.

**Rationale:** Lark Earley handles left-recursion and ambiguity correctly. The generated recursive descent parser in `FAILED_ATTEMPT/builder.py` is complex to generate correctly for arbitrary grammars. No code generation needed for parsing.

**Alternatives Considered:**
- Generated recursive descent parser.py — too complex to get right for all GBNF patterns, proven broken in failed attempt

---

### Model generation: SOLID inheritance for alternation rules

**Decision:** For `X ::= A | B | C`, generate abstract `X(BaseModel)` + concrete `AX(X)`, `BX(X)`, `CX(X)`. For sequences, generate `X(BaseModel)` with typed fields. For single references, generate `X(RefTarget)` as a subclass.

**Rationale:** User explicitly requested SOLID. Union fields collapse type information and prevent isinstance checks. Inheritance is the right pattern for sum types.

**Alternatives Considered:**
- `root: Union[A, B, C]` — rejected, flat, not SOLID

---

### Generation: Approach A (guidance LlamaCpp + lark)

**Decision:** Use Approach A from `with_guidance.py`: `guidance.models.LlamaCpp` + `guidance.lark()`. Pass a pre-created `llama_cpp.Llama` instance to avoid the KV-cache initialization hang.

**Rationale:** Approach A "sort of works". Approach B (raw LLMatcher) produces nonsense due to double-consuming tokens. `tst.py` (LlamaGrammar) is correct but slower.

**Alternatives Considered:**
- Approach B (raw LLMatcher as LogitsProcessor) — double-consume bug, excluded
- LlamaGrammar (tst.py approach) — works but slower than guidance

---

### All code in src/

**Decision:** Write all new code to `src/`. No `built/` output directory.

**Rationale:** User requirement. The `built/` pattern from the failed attempt added unnecessary indirection.

---

### No worktrees

**Decision:** GSD isolation mode is `none` — work directly on the current branch.

**Rationale:** User requirement.

## Error Handling Strategy

ParseError should carry the rule name, position, and a context snippet of the input text around the failure point. Generation failures (model not found, grammar error) should raise with a clear message that includes the grammar path and error details. Never swallow exceptions silently.

## Risks and Unknowns

- Lark transformer ↔ Pydantic model wiring — the transformer must instantiate the correct generated subclass for each tree node; getting this correspondence right for all GBNF patterns is the hardest part
- GBNF features edge cases — character classes with ranges, nested repetition, optional sequences, rule references that cross terminal/non-terminal boundaries; all must work for ground_truth grammars
- Approach A generation — "sort of works" is not "works reliably"; may need tuning of temperature and max_tokens to get consistent constrained output

## Existing Codebase / Prior Art

- `with_guidance.py` — `_gbnf_to_earley_lark()`, `parse_vyx_to_dict()`, `max_gpu_layers()`, Approach A and B implementations. READ THIS before implementing S02 and S04.
- `FAILED_ATTEMPT/builder.py` — `GrammarParser`, `resolve()`, `to_class_name()`, `to_field_name()`, `ast_to_regex()`, `_node_to_type()`. The AST node types (ASTNode, AlternativeNode, SequenceNode, RuleRefNode, RepetitionNode, LiteralNode, RegexNode) are the right inputs. The model generation logic is wrong (use it as a reference for what nodes exist, not for how to generate classes).
- `resources/ground_truth/` — 7 known-correct GBNF grammars. These are the test fixtures.
- `tst.py` — working `max_gpu_layers()` utility and LlamaGrammar generation loop.

## Relevant Requirements

- R001 — SOLID model generation (S01)
- R002 — text-to-Pydantic parser (S02)
- R003 — round-trip serialization (S03)
- R004 — generic over all ground_truth grammars (S04)
- R005 — clean generation interface (S04)

## Scope

### In Scope

- GBNF → Pydantic model generator writing to `src/`
- Lark Earley parser: text + grammar → Pydantic instance
- `to_text()` and `to_json()` on all generated models
- Clean generation interface wrapping Approach A
- Verified against all 7 ground_truth grammars

### Out of Scope / Non-Goals

- Fixing `vyx.gbnf` (deferred)
- Approach B (LLMatcher direct, double-consume bug)
- Generated parser.py (recursive descent code generation)
- `built/` output directory

## Technical Constraints

- Python 3.12+, `uv run` for execution
- Dependencies already in uv.lock: pydantic, lark, llguidance, llama-cpp-python, guidance, numpy, rich
- `src/` is the only output directory for new code
- No worktrees (GSD isolation: none)

## Integration Points

- `llguidance.gbnf_to_lark.GrammarParser` + `resolve()` — GBNF AST parsing
- `lark.Lark` with `parser="earley"` — text parsing
- `llama_cpp.Llama` + `guidance.models.LlamaCpp` — constrained generation
- Model at `MODEL_PATH` env var (only needed for generation, not for codegen/parsing)

## Testing Requirements

Pytest tests for:
- Model generator: generated classes have correct `__bases__` and field types for each ground_truth grammar
- Parser: parse known-good sample texts for each grammar, check isinstance of result
- Round-trip: `parse(instance.to_text()) == instance` for each ground_truth grammar
- JSON round-trip: `parse(json_text, json_ws).to_json() == json.loads(json_text)`

## Open Questions

- None — all key decisions locked.
