# Lexic

> **Status:** experimental, pre-1.0, WIP. APIs may change without notice.

Lexic is the grammar engine layer of [Vyx](https://github.com/) — an agent-to-agent protocol. It compiles grammar files (GBNF, ABNF) into typed Pydantic model classes; instances parse text and round-trip back to grammar.

**Grammar is the ground truth.** Generated classes are Python's view of a grammar, not the source of truth. Every model has a lossless `to_grammar(flavour)` path back to the canonical text.

## What it does

- **Compile** a grammar file (`.gbnf` / `.abnf`) into a `CompiledGrammar` bundle (Pydantic classes + a Lark parser + transformer).
- **Parse** text against the compiled grammar into a typed model instance.
- **Round-trip** an instance back to its original text via `to_text()` — exact, whitespace-preserving.
- **Re-emit** the grammar from the model via `to_grammar(flavour)` — works across flavours (e.g. compile a GBNF grammar, emit it as ABNF).
- **Strip structural noise** via `semantic_dump()` — `model_dump()` minus rules marked `@non-semantic` (typically whitespace). Used downstream by Vyx for cross-grammar translation.

## Quick start

```python
from lexic.compile import compile_from_path

grammar = compile_from_path("resources/ground_truth/arithmetic.gbnf")

# Parse text → typed Pydantic model
instance = grammar.parse("x = 1\n")

# Exact reconstruction
assert instance.to_text() == "x = 1\n"

# Emit the grammar back (GBNF by default)
print(instance.to_grammar())          # GBNF
print(instance.to_grammar("abnf"))    # ABNF

# Semantic-only dict (no whitespace fields)
instance.semantic_dump()
```

For a string-in entry point, use `compile_text`:

```python
from lexic.compile import compile_text

grammar = compile_text(open("g.gbnf").read(), flavour="gbnf")
```

## Supported flavours

| Flavour | Extension | Status |
|---|---|---|
| GBNF | `.gbnf` | Production |
| ABNF (subset) | `.abnf` | Production |

A *flavour* is the grammar notation. Adding a new one means writing a single `grammars/<name>/flavour.py` module containing:

- a Lark meta-grammar string using canonical `ir_*` tag names,
- an `EscapeCodec` instance,
- a tuple of `IrAction`s mapping each IR-AST node type to a rendering body (pure algebra: `IrConcat`, `IrJoin`, `IrField`, `IrChild`, `IrChildren`; procedural escape hatch: `IrCallable`),
- an `IrFlavour` subclass with `parse_quantifier` / `parse_charclass` static methods.

See [`.wiki/lexic/flavour-system.md`](.wiki/lexic/flavour-system.md) for the step-by-step walkthrough.

## Architecture

```
grammar text
   │
   ├─► parse_directives                Directives(start, non_semantic)
   └─► MetaGrammarParser.for_flavour   IrAst
            │
            ▼
        derive_specs                   list[RuleSpec]
            │
   ┌────────┼────────────────────┬──────────────────────┐
   ▼        ▼                    ▼                      ▼
 codegen  flavour.apply       build_lark            (further passes…)
 (Pydantic) (grammar text)    (Lark parser
                              + transformer)
```

The IR substrate is **action-driven**: every transformation (derive, codegen, flavour emission) is expressed as a tuple of `IrAction(target_type, body)` plugged into a single dispatcher (`IrDispatch` / `IrVisitor` / `IrTransformer` / `IrEmitter`). New IR node types extend the table; the dispatcher needs no subclassing.

For the full architecture, layering rules, and IR substrate documentation, see:

- [`.wiki/lexic/architecture.md`](.wiki/lexic/architecture.md) — pipeline, layering, the IR substrate.
- [`.wiki/lexic/ir-shapes.md`](.wiki/lexic/ir-shapes.md) — every IR node + the action algebra.
- [`.wiki/lexic/flavour-system.md`](.wiki/lexic/flavour-system.md) — adding flavours.

## Test grammars

Seven ground-truth grammars live in `resources/ground_truth/`. Property tests round-trip every valid input through them:

`arithmetic` · `c` · `chess` · `japanese` · `json_arr` · `json_ws` · `list`

## Development

Lexic uses [uv](https://docs.astral.sh/uv/) for dependency management. Always prefix commands with `uv run` — never run `pytest` or `ruff` bare.

```bash
uv sync                                  # install deps
uv run pytest tests/ -q                  # full suite (474 tests)
uv run pytest tests/unit/lexic/ -q       # unit only
uv run pytest tests/integration/ -q      # integration only
uv run ruff check src/ tests/            # lint
uv run pylint src/lexic/path/to/file.py  # per-file quality gate
```

Mechanical lint/format fixes:

```bash
tools/auto_fix.sh   # ruff format → isort → ruff check --fix
```

## Project status

Lexic is pre-1.0 and actively churning. The IrItem-based pipeline cutover landed in May 2026; the action-driven substrate landed in late May 2026 ([[decisions]] P12–P18). Public invariants and roadmap live in `prototyping/next/`:

- [`prototyping/next/1_NORTH_STAR.md`](prototyping/next/1_NORTH_STAR.md) — invariants every change must preserve.
- [`prototyping/next/2_ARCHITECTURE.md`](prototyping/next/2_ARCHITECTURE.md) — target module layout.
- [`prototyping/next/3_ROADMAP.md`](prototyping/next/3_ROADMAP.md) — five slices A–E.

## License

TBD.
