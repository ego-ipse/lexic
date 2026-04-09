# Vyx Pipeline Design

**Date:** 2026-04-10  
**Status:** Approved  
**Scope:** Grammar-driven build pipeline — parser, Pydantic models, constrained generation

---

## Problem

The project has three disconnected pieces:
- A hand-edited `spec_built/grammar.gbnf` used for constrained generation
- A hand-written `_gbnf_to_earley_lark` function for parsing (character-granular, broken on complex inputs)
- No Pydantic models, no stable public API

The goal is a single source of truth that drives everything automatically.

---

## Source of Truth

**`project_meta/grammar.gbnf`** is the canonical grammar. Nothing else encodes Vyx structure. All downstream artifacts are generated from it and must not be hand-edited.

The grammar in `spec_built/metameta.md` is out of date and is not used.

**Future (Phase 2):** Once `parse()` works, feed `metameta.md` through it and use the extracted semantic structure to refine or replace the grammar-derived models. This bootstrapping step is out of scope for now.

---

## Architecture

```
project_meta/grammar.gbnf          ← SSOT, never auto-modified
        │
        ▼
   builder.py  (build step — run after any grammar change)
        │
        ├──▶ vyx/models.py          (Pydantic classes, auto-generated)
        └──▶ vyx/parser.py          (recursive descent parser, auto-generated)

   vyx/generate.py                  (Approach B: LLMatcher + llama-cpp-python)
        │ reads grammar.gbnf at runtime for constrained sampling
        └──▶ returns raw Vyx text

   vyx/__init__.py                  (public API: parse, generate)
```

---

## Components

### `builder.py` — GBNF → code generator

The one hand-written piece. Uses `GrammarParser` + `resolve()` from `llguidance.gbnf_to_lark` to parse the GBNF into a rule AST, then walks it to emit Python.

**Rule → Pydantic field mapping:**

| GBNF construct | Generated field |
|---|---|
| sequence `a b c` | one field per named sub-rule |
| alternation `a \| b \| c` | `Union[A, B, C]` or `Literal[...]` for string-only alts |
| repetition `a*` / `a+` | `list[A]` / `list[A]` (with `min_length=1`) |
| optional `a?` | `Optional[A] = None` |
| character class `[a-z]+` | `str` with regex validator |
| literal `"foo"` | omitted (structural marker, not semantic) |

**Rule → parser function mapping:**

Each grammar rule emits a `parse_X(text, pos)` function. Alternations try branches in grammar order; sequences advance `pos` through elements; repetitions loop until no match.

Leaf rules with character-class patterns (`key`, `ref-id`, `agent-id`, etc.) use `re.match` — no recursion needed.

---

### `vyx/models.py` — generated Pydantic models

Top-level hierarchy:

```python
class Packet(BaseModel):
    definitions: list[Definition] = []
    envelope: Envelope
    body: Body | None = None

class Envelope(BaseModel):
    template: str | None = None
    performative: str            # "R", "I", ... or "X:CUSTOM"
    fields: list[EnvField] = []

class EnvField(BaseModel):
    root: Annotated[
        Ontology | Sender | Receiver | MsgLabel | MsgRef | Version | Budget,
        Field(discriminator=...)
    ]

class Body(BaseModel):
    lines: list[BodyLine]

# BodyLine = NlEscape | NlForce | DictDef | TableBlock | SeqItem | ScopeLine | KvLine | NlText
```

Leaf nodes with character-class rules become validated `str` fields rather than separate model classes — the tree stays at a useful semantic depth.

---

### `vyx/parser.py` — generated recursive descent parser

```python
# generated — do not edit; run builder.py to regenerate
def parse_packet(text: str, pos: int = 0) -> tuple[Packet, int]: ...
def parse_envelope(text: str, pos: int) -> tuple[Envelope, int]: ...
def parse_body(text: str, pos: int) -> tuple[Body, int]: ...
# one function per grammar rule
```

- Alternations try branches in grammar order, backtrack on failure
- Leaf string rules use `re.match` against translated character class
- `ParseError(rule, pos, text)` with a context snippet on failure
- File header points back to `project_meta/grammar.gbnf` and the regeneration command

---

### `vyx/generate.py` — constrained generation

Approach B from `with_guidance.py`, extracted into a clean module. `guidance` dependency removed.

```python
def generate(
    model_path: str,
    prompt: str,
    *,
    grammar_path: Path = GRAMMAR_PATH,
    max_new_tokens: int = 200,
    temp: float = 0.8,
    top_k: int = 40,
) -> str:
    """Constrained Vyx generation via LLMatcher. Returns raw Vyx text."""
```

Internals:
- `lltokenizer_from_vocab` built once, cached on the `Llama` instance
- `LLGuidanceLogitsProcessor` wraps `LLMatcher` with `grammar_from("gbnf", ...)`
- Token loop reads `input_ids` diff to detect sampled token, calls `consume_token`
- Stops on EOS, grammar acceptance, or `max_new_tokens`

---

### `vyx/__init__.py` — public API

```python
from vyx import parse, generate

# Parse any Vyx text → Pydantic
packet: Packet = parse("!I o:inv\ncity=Porto temp=22\n>")

# Body-only parse
body: Body = parse("city=Porto temp=22", start="body")

# Constrained generation from a local model
text: str = generate("/path/to/model.gguf", "Write a Vyx inform packet:")
```

---

## Build Workflow

1. Edit `project_meta/grammar.gbnf`
2. Run `uv run builder.py` → regenerates `vyx/models.py` and `vyx/parser.py`
3. Commit both the grammar change and the generated files together

For iterative development, use the ralph loop:
```
/ralph-loop "Run builder.py, fix any generation errors, run tests, repeat until tests pass." --completion-promise "TESTS PASS"
```

---

## Out of Scope

- API-agent fallback (Claude, GPT): grammar + examples as system prompt context, validate + retry. Deferred.
- Phase 2 metameta bootstrapping: parse `spec_built/metameta.md` via `parse()` to extract semantic constraints and refine models. Deferred.
- `guidance` library: removed as a dependency.
