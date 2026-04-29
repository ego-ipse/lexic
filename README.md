# Lexic

**Status: WIP**

Lexic is the grammar engine layer of the Vyx agent-to-agent protocol. It turns GBNF grammar files into typed Pydantic model classes and back, enabling structured parsing, exact-fidelity text reconstruction, and (upcoming) cross-grammar translation between agent message formats.

## What it does

Given a GBNF grammar file, Lexon:

1. **Generates** typed Pydantic model classes (`codegen`)
2. **Parses** text into structured model instances (`parse`)
3. **Reconstructs** the original text from an instance (`instance.to_text()`)
4. **Reconstructs** the original GBNF from model classes (`instance.to_gbnf()`)
5. **Dumps** semantic data excluding whitespace fields (`instance.semantic_dump()`) — used for S04 translation

## Quick start

```python
from lexic.codegen import codegen
from lexic.parse import parse

# Generate Pydantic classes from a grammar
codegen("resources/ground_truth/arithmetic.gbnf")

# Parse text into a typed instance
result = parse("x=1\n", "resources/ground_truth/arithmetic.gbnf")

# Reconstruct original text
assert result.to_text() == "x=1\n"

# Cross-grammar-portable data (no whitespace fields)
result.semantic_dump()
```

## Field naming

Field names for character-class atoms are derived automatically from the pattern:

| Pattern | Field name |
|---|---|
| `[0-9]` | `digit` |
| `[a-z]` | `lower` |
| `[a-zA-Z0-9_]` | `alnum` |
| `[+#]` | `annotation` |
| other | sanitized pattern content |

**Planned:** Grammar authors will be able to override field names using inline GBNF
comments (`# @field=captureFile`). This annotation mechanism is not yet implemented.

## Pipeline

```
GBNF text
  ↓  GBNFParser       (codegen/parser.py)
GBNF AST              (codegen/ast.py)
  ↓  IRBuilder        (codegen/ir_builder.py)
RuleSpec IR           (codegen/ir.py)
  ↓  ModelEmitter  →  generated/*.py     (Pydantic classes with __grammar__)
  ↓  GBNFEmitter   →  GBNF text          (reverse direction)
  ↓  LarkBuilder   →  Lark grammar       (drives parse())

Runtime:
  parse(text, grammar)     →  GrammarModel instance
  instance.to_text()       →  original text (exact, whitespace-preserving)
  instance.to_gbnf()       →  GBNF grammar text
  instance.semantic_dump() →  dict excluding ws fields (S04 prep)
```

## Test grammars

Seven GBNF grammars in `resources/ground_truth/` serve as ground truth test targets:

| Grammar | Description |
|---|---|
| `arithmetic` | Identifiers, assignment, arithmetic expressions |
| `list` | Markdown-style bullet lists |
| `json_ws` | JSON with whitespace |
| `json_arr` | JSON arrays |
| `chess` | Algebraic chess notation |
| `japanese` | Hiragana character sequences |
| `c` | C-like declarations |

## Running tests

```bash
uv run pytest tests/ -v
```

312 tests across unit, integration, and property layers covering IR, IRBuilder, ModelEmitter, GrammarModel, LarkBuilder, GBNFEmitter, full parse round-trips, and hypothesis-driven property tests for all 7 grammars.

## Upcoming: S04 Translation

S04 is the cross-grammar translation layer — not yet implemented. It will provide:

```python
from lexic.translate import translate

# Translate a parsed instance from one grammar's format to another
result_b = translate(result_a, TargetClass)
```

`semantic_dump()` is already implemented on every `GrammarModel` instance as S04 prep — it returns `model_dump()` with `ws` fields excluded, producing a grammar-portable dict that S04 translation logic can reason about.

# Note to self.
# Remind me after slice B. Codegen will bee refactored to use ast to generate code dynamically.