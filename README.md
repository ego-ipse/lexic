# Lexic

> **Status:** experimental, pre-1.0. APIs may change without notice.

Lexic is the grammar engine layer of [Vyx](https://github.com/) — an agent-to-agent protocol. It compiles grammar files (GBNF, ABNF) into typed model classes; instances parse text and round-trip losslessly back to grammar. It has **zero runtime dependencies** — the parser is a native Earley/PDA engine, and model classes are plain Python records.

**Grammar is the ground truth.** Model classes are Python's *view* of a grammar, not the source of truth. Every model has a lossless `to_grammar(flavour)` path back to canonical grammar text.

## What it does

- **Compile** a grammar (`.gbnf` / `.abnf`) into a `CompiledGrammar` — model classes synthesized at runtime + a compiled instance parser.
- **Parse** text against the compiled grammar into a typed model instance.
- **Round-trip** an instance back to its exact source via `to_text()` — whitespace-preserving.
- **Re-emit** the grammar from a model via `to_grammar(flavour)` — across flavours (compile GBNF, emit ABNF, or vice-versa).
- **Strip structural noise** via `semantic_dump()` — `dump()` minus rules marked `@non-semantic` (typically whitespace). Used downstream by Vyx for cross-grammar translation.
- **Load pure IR** — parse a grammar to an `IrAst` without building classes (`parse_grammar`), load IR objects from a neutral text notation (`load_ir`), or load a whole flavour from a text manifest (`load_flavour`).

## Quick start

```python
from lexic.compile import compile_from_path

grammar = compile_from_path("resources/ground_truth/arithmetic.gbnf")

# Parse text → typed model
instance = grammar.parse("x = 1\n")

# Exact reconstruction
assert instance.to_text() == "x = 1\n"

# Emit the grammar back
print(instance.to_grammar())          # GBNF (default)
print(instance.to_grammar("abnf"))    # ABNF

# Dicts: full dump, or semantic-only (no whitespace fields)
instance.dump()
instance.semantic_dump()
```

String-in entry point:

```python
from lexic.compile import compile_text

grammar = compile_text('root ::= "hi"\n', flavour="gbnf")
```

Runnable, commented walkthroughs live in [`getting_started/`](getting_started/):

| Example | Shows |
|---|---|
| `ex01_hello_grammar.py` | Define a grammar inline, compile, parse, round-trip. |
| `ex02_compile_from_file.py` | Compile a bundled `.gbnf` and read fields. |
| `ex03_parse_json.py` | Parse nested JSON; `to_text()` and `semantic_dump()`. |
| `ex04_transpile_flavours.py` | Transpile a grammar GBNF ↔ ABNF via the flavour singletons. |
| `ex05_inspect_ir.py` | Inspect the `__grammar__: IrRule` behind a compiled class. |

## Two products: models and pure IR

The `compile/` package compiles grammar text into **either or both** of:

- **Compiled models** — classes synthesized at runtime on an immutable record spine (`IrNamedTuple`) via `type(name, bases, ns)`. No source emit, no import, no file write; a model *is* a walkable IR record.
- **Pure IR** — an `IrAst` (via `parse_grammar`), real IR objects from a neutral, no-`exec` text notation (`load_ir`), or a full `IrFlavour` from a text manifest (`load_flavour`).

```python
from lexic.compile import parse_grammar, load_ir
from lexic.grammars import GBNF_FLAVOUR

ast = parse_grammar('root ::= "a" | "b"\n', GBNF_FLAVOUR)   # grammar text → IrAst
node = load_ir('IrLiteral("x")')                            # notation text → IR object
```

## Supported flavours

| Flavour | Extension | Status |
|---|---|---|
| GBNF | `.gbnf` | Production |
| ABNF | `.abnf` | Production (RFC 5234 + 7405 subset) |

A *flavour* is the grammar notation. A flavour is pure data — a self-grammar (authored as `IrAst`), a `Reducer` (reductions + noise map), an `EscapeCodec`, and emit actions — carried by an `IrFlavour` with **zero parsing methods**. Add one either as a flat `grammars/<name>.py` module or as a **text manifest** loaded with `load_flavour`. See [`.wiki/lexic/flavour-system.md`](.wiki/lexic/flavour-system.md).

## Architecture

```
grammar text
   │
   ├─► _scan_directives                (start, non_semantic)
   └─► parse_grammar                   IrAst      [native Earley/PDA engine]
            │
            ▼
      canonicalize                     canonical IrAst   [language-preserving
            │                           normal form — two flavours of the same
            │                           language converge on the same tree]
            ▼
   build_codegen_grammar               THE codegen grammar
   (hoist groups, hoist arms,               │
    relax non-semantic refs)                │
   ┌────────┬───────────────┬───────────────┼──────────────────────┐
   ▼        ▼               ▼                                       ▼
compute_binding      synthesize            PositionalFold        flavour.apply
(class/kind/         (type() build:        (instance parsing      (grammar text,
 parent/field        __grammar__ +          over the codegen      either flavour)
 names)              __binds__, no file)    grammar directly)
```

Parsing is a **native engine** (`lexic.parsing`, pure Python, zero parser dependencies): a deterministic predictive **PDA** fast path that builds the typed result *during* the parse, backed by a scannerless **Earley** engine (full SPPF, Scott 2008) as the sound completion. The one engine drives both grammar-text parsing (each flavour carries its own self-grammar as IR) and generated-instance parsing — the latter a positional fold over the real codegen grammar, no intermediate wrapper grammar.

The IR substrate is **action-driven**: every transformation (canonicalization, class synthesis, flavour emission) is expressed as `IrAction(target_type, body)` entries plugged into one dispatcher (`IrDispatch` / `IrVisitor` / `IrTransformer` / `IrEmitter`). New IR node types extend the table; the dispatcher needs no subclassing. Models live on this same spine — a compiled instance is walkable, dispatchable IR.

For the full picture:

- [`.wiki/lexic/architecture.md`](.wiki/lexic/architecture.md) — pipeline, layering, the IR substrate.
- [`.wiki/lexic/ir-shapes.md`](.wiki/lexic/ir-shapes.md) — every IR node + the action algebra.
- [`.wiki/lexic/public-api.md`](.wiki/lexic/public-api.md) — the public surface.
- [`.wiki/lexic/flavour-system.md`](.wiki/lexic/flavour-system.md) — adding flavours.

## Test grammars

`resources/ground_truth/` holds nine `.gbnf` grammars plus two `.abnf` siblings (`arithmetic`, `json`) for cross-flavour compile parity. Property tests round-trip every valid input through them:

`arithmetic` · `c` · `chess` · `japanese` · `json` · `json_arr` · `json_ws` · `list` · `vyx`

## Performance

`lexic.parsing` runs two engines behind one API: the deterministic **PDA** (default fast path, builds the typed model with no intermediate tree) backed by scannerless **Earley** (full SPPF) as the sound completion. Both are pure Python with zero parser dependencies. `tools/benchmark/compare_bench.py` races both against **Lark** (LALR and Earley) on the same inputs.

Representative throughput (µs/char, lower is faster; single machine, 2026):

| input | lark-lalr | lark-earley | earley | **pda** |
|---|---|---|---|---|
| ABNF self-emit *(grammar text)* | — | ~29 | ~16 | **~9** |
| GBNF self-emit *(grammar text)* | — | ~20 | ~18 | **~9** |
| arithmetic *(instance)* | 1.9 | 24 | 14 | **2.6** |
| c *(instance)* | 1.2 | 21 | 8 | **1.1** |
| chess *(instance)* | 1.0 | 10 | 9 | **1.6** |
| json *(instance)* | 0.9 | 14 | 64 | **3.5** |

Reading the numbers fairly: Lark's **LALR** + contextual lexer is genuinely fast — but it yields a *generic parse tree*, while `earley`/`pda` build the **typed model**, so those columns include construction Lark's do not. LALR is not viable for the two meta-grammars (rulename↔ruleref overlap needs unbounded lookahead), so Lark runs Earley there. Lark is measured at its native output, never a second-pass transform; where LALR cannot handle a grammar it is reported, never silently swapped. Compilation itself is fast — building a `CompiledGrammar` is dominated by parsing, with no file I/O or subprocess on the path.

## Development

Lexic uses [uv](https://docs.astral.sh/uv/). Always prefix commands with `uv run` — never run `pytest` or `ruff` bare.

```bash
uv sync                                  # install deps (dev-only; no runtime deps)
uv run pytest tests/ -q                  # full suite (~2570 tests)
uv run pytest tests/unit/lexic/ -q       # unit only
uv run pytest tests/integration/ -q      # integration only
uv run ruff check src/ tests/            # lint
tools/run_checks.sh                       # the done-gate (ruff + pyright + whole-tree pylint)
```

Mechanical lint/format fixes:

```bash
tools/auto_fix.sh   # ruff format → isort → ruff check --fix
```

## Project status

Lexic is pre-1.0 and actively developed. One IR-native pipeline drives everything: a native Earley/PDA engine (no third-party parser), a canonical `IrAst` that both flavours converge on, runtime class synthesis on the record spine, and cross-flavour emission — all off the same action-driven IR substrate. Public invariants live in [CLAUDE.md](CLAUDE.md) §Key invariants; architecture and design decisions live in the [wiki](.wiki/).

## License

LGPL
