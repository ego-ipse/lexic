# Lexic

> **Status:** experimental, pre-1.0, WIP. APIs may change without notice.

Lexic is the grammar engine layer of [Vyx](https://github.com/) — an agent-to-agent protocol. It compiles grammar files (GBNF, ABNF) into typed Pydantic model classes; instances parse text and round-trip back to grammar.

**Grammar is the ground truth.** Generated classes are Python's view of a grammar, not the source of truth. Every model has a lossless `to_grammar(flavour)` path back to the canonical text.

## What it does

- **Compile** a grammar file (`.gbnf` / `.abnf`) into a `CompiledGrammar` bundle (Pydantic classes + a compiled instance grammar + model fold).
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

A *flavour* is the grammar notation. Adding a new one means writing a single flat `grammars/<name>.py` module containing:

- the flavour's own self-grammar, authored directly as an `IrAst` (no meta-grammar string),
- a `Reducer` (reductions + noise map) folding parse forests back into IR,
- an `EscapeCodec` instance,
- emit actions mapping each IR-AST node type to a rendering body (pure algebra: `IrConcat`, `IrJoin`, `IrField`, `IrChild`, `IrChildren`; procedural escape hatch: `IrLambda`),
- an `IrFlavour` subclass carrying all of the above as data — zero parsing methods.

See [`.wiki/lexic/flavour-system.md`](.wiki/lexic/flavour-system.md) for the step-by-step walkthrough.

## Architecture

```
grammar text
   │
   ├─► _scan_directives                (start, non_semantic)
   └─► parse_grammar                   IrAst      [native Earley engine]
            │
            ▼
      canonicalize                     canonical IrAst   [language-preserving
            │                           normal form — two flavours of the same
            │                           language converge on the same tree]
            ▼
   build_codegen_grammar               THE codegen grammar
   (hoist groups, hoist arms,               │
    relax non-semantic refs)                │
            │                               │
   ┌────────┼───────────────┬───────────────┼──────────────────────┐
   ▼        ▼                ▼                                      ▼
compute_binding  codegen (Annotated/IrBind    PositionalFold      flavour.apply
(class/kind/     fields, __grammar__          (instance parsing    (grammar text,
 parent/field    footers → Pydantic)          over the codegen     either flavour)
 names)                                        grammar directly)
```

Parsing is a **native Earley engine** (`lexic.parsing` — SPPF, Scott 2008, pure Python, zero parser dependencies). The same engine drives grammar-text parsing (each flavour carries its own self-grammar as IR) and generated-instance parsing — the latter via a positional fold over the real codegen grammar, no intermediate wrapper grammar.

The IR substrate is **action-driven**: every transformation (canonicalization, codegen, flavour emission) is expressed as a tuple of `IrAction(target_type, body)` plugged into a single dispatcher (`IrDispatch` / `IrVisitor` / `IrTransformer` / `IrEmitter`). New IR node types extend the table; the dispatcher needs no subclassing.

For the full architecture, layering rules, and IR substrate documentation, see:

- [`.wiki/lexic/architecture.md`](.wiki/lexic/architecture.md) — pipeline, layering, the IR substrate.
- [`.wiki/lexic/ir-shapes.md`](.wiki/lexic/ir-shapes.md) — every IR node + the action algebra.
- [`.wiki/lexic/flavour-system.md`](.wiki/lexic/flavour-system.md) — adding flavours.

## Test grammars

Eight ground-truth `.gbnf` grammars live in `resources/ground_truth/`, plus two `.abnf` siblings (`arithmetic`, `json`) used to check cross-flavour compile parity. Property tests round-trip every valid input through them:

`arithmetic` · `c` · `chess` · `japanese` · `json` · `json_arr` · `json_ws` · `list`

## Performance

The engine is pure Python with full SPPF semantics, benchmarked against Lark's Earley mode on grammar-text parsing (`tools/benchmark/parse_bench.py`, baseline JSON alongside). As of July 2026 the text→IR product runs at ~17 µs/char vs Lark's ~30 — about 1.75× faster full-vs-full — via exact (proved, never approximated) lexical-run collapse, seed-pair prediction tables, and FIRST-gated prediction.

## Development

Lexic uses [uv](https://docs.astral.sh/uv/) for dependency management. Always prefix commands with `uv run` — never run `pytest` or `ruff` bare.

```bash
uv sync                                  # install deps
uv run pytest tests/ -q                  # full suite (~1360 tests)
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

Lexic is pre-1.0 and actively churning. The IrItem-based pipeline cutover landed in May 2026; the action-driven substrate landed in late May 2026 ([[decisions]] P12–P18); the Lark→Earley cutover (native engine, Lark removed as a dependency) landed in early July 2026; the RuleSpec→IR-native codegen cutover (one canonical grammar drives codegen, instance parsing, emission, generation and round-trip — no intermediate spec layer) landed in early July 2026. Public invariants live in CLAUDE.md §Key invariants; architecture and decisions live in the wiki.

## License

TBD.
