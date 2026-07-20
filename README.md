# Lexic

> **Status:** experimental, pre-1.0. APIs may change without notice.

Lexic compiles grammar files into typed Python object models. Given a grammar, it synthesizes model classes at runtime — named, typed fields derived from the grammar's structure, built with `type()`, no code-generation step and no schema language on the side. Parsing text against the grammar produces instances of those classes; `to_text()` reconstructs the exact source, byte for byte; `to_grammar(flavour)` re-emits the grammar itself, in any supported notation.

**Grammar is the ground truth.** Model classes are Python's *view* of a grammar, not the source of truth. Every model has a lossless `to_grammar(flavour)` path back to canonical grammar text.

Design properties:

- **A native parsing engine.** A scannerless Earley engine (full SPPF, Scott 2008) handles any context-free grammar — ambiguity and left recursion included — fused with a predictive PDA fast path. Every fast-path decision is licensed by static analysis of the grammar at hand; any construct the analysis cannot prove safe is parsed by the Earley engine instead, per rule, automatically. Correctness never depends on the fast path.
- **Zero runtime dependencies.** The engine, the record spine the models live on, and the layout engine that formats emitted text are all part of the package. `pip install` pulls in nothing.
- **Portable grammars.** All notations converge on one canonical IR: a grammar compiled from GBNF re-emits as ABNF or EBNF and vice versa, with reparse-equal results. Emission is width-aware — long rules wrap at arm and item boundaries and reparse to the identical canonical AST (`width=None` gives the flat single-line form).
- **Self-hosting.** The grammar notations are parsed by the same engine, from self-grammars authored as data — a flavour carries no parser code. Exported modules are themselves re-parsed by a grammar of generated modules and cross-checked against the compiler's binding view, so drift between compiler and artifact is a test failure, not a surprise.
- **Tool-clean generated code.** Exported twin modules are importable, fully typed, clean under default-configuration pyright and pylint, and byte-stable under isort + ruff-format — produced by the same layout engine, with no formatter subprocess on the path.
- **Property-tested round-trips.** `parse(text).to_text() == text` holds on every valid input, for every grammar in the corpus, under hypothesis-generated inputs.

Lexic is the grammar engine layer of Vyx, an agent-to-agent protocol that uses grammars, not prose, as the wire contract between agents.

## What it does

- **Compile** a grammar (`.gbnf` / `.abnf` / `.ebnf`) into a `CompiledGrammar` — runtime-synthesized model classes plus a compiled instance parser.
- **Parse** text against the compiled grammar into a typed model instance (`grammar.parse`, or the one-line `parse_instance` / `parse_instance_from_path`).
- **Round-trip** an instance back to its exact source via `to_text()` — whitespace-preserving.
- **Re-emit** the grammar via `to_grammar(flavour)` — in any flavour, width-aware.
- **Export** a compiled grammar as an importable twin module (`export_module`) — the typed, on-disk form of the same classes — and verify any export by parsing it back (`parse_module` / `verify_module`).
- **Strip structural noise** via `semantic_dump()` — `dump()` minus fields bound to rules marked `@non-semantic` (typically whitespace).
- **Work in pure IR** — parse a grammar to an `IrAst` without building classes (`parse_grammar`), construct IR objects from a neutral text notation (`load_ir` / `emit_ir`), or load a whole flavour from a text manifest (`load_flavour`).

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
print(instance.to_grammar("ebnf"))    # EBNF

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
| `ex04_transpile_flavours.py` | Transpile a grammar between flavours via the singletons. |
| `ex05_inspect_ir.py` | Inspect the `__grammar__: IrRule` behind a compiled class. |

## Two products: models and pure IR

The `compile/` package compiles grammar text into **either or both** of:

- **Compiled models** — classes synthesized at runtime on an immutable record spine (`IrNamedTuple`) via `type(name, bases, ns)`. No source emit, no import, no file write; a model *is* a walkable IR record. Files are written only on the explicit `export_module` path.
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
| GBNF | `.gbnf` | Production (character-level; llama.cpp token terminals not supported) |
| ABNF | `.abnf` | Production (RFC 5234 + 7405, incl. `%d`/`%b`/`%x` sequences, case markers, the B.1 core-rules prelude) |
| EBNF | `.ebnf` | Production (ISO-family: `=`/`;` rules, `{}`/`[]`, `n * x` repetition, `(* *)` comments) |

GBNF's llama.cpp token-level terminals (`<[id]>`, `<token>`, `!<…>`) are **not supported** — lexic parses character streams and has no tokenizer vocabulary; a grammar using them fails to parse. EBNF has no native character-class or negation syntax: classes emit as quoted alternations where finite, and constructs EBNF cannot spell (negation, open-bounded counted repetition) are refused explicitly rather than approximated.

A *flavour* is the grammar notation, carried entirely as data: a self-grammar (authored as `IrAst`), a `Reducer` (reduction bodies + a noise policy derived from the grammar's own `semantic=False` flags), an `EscapeCodec`, optional core rules (ABNF's RFC prelude), and emit actions — an `IrFlavour` with **zero parsing methods**. Add one either as a flat `grammars/<name>.py` module or as a **text manifest** loaded with `load_flavour`. See [`.wiki/lexic/flavour-system.md`](.wiki/lexic/flavour-system.md).

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
compute_binding      synthesize            ModelFold             flavour.apply
(class/kind/         (type() build:        (positional instance  (grammar text,
 parent/field        __grammar__ +          fold over the         any flavour,
 names)              __binds__, no file)    codegen grammar)      width-aware)
```

The `compile/` package is organized by role: `pipeline/` (the passes, the binding view, class synthesis), `notation/` (the IR text notation's parse and emit halves, plus the manifest loader), and `module/` (twin-module export and the generated-module self-grammar that parses exports back). It is also the sole seam onto the engine — nothing else in the runtime imports `lexic.parsing`.

Parsing is a **native engine** (`lexic.parsing`, pure Python): a deterministic predictive **PDA** fast path that builds the typed result *during* the parse, backed by the scannerless **Earley** engine as the sound completion. The same engine drives grammar-text parsing (each flavour's self-grammar is data) and instance parsing (a positional fold over the real codegen grammar — no intermediate wrapper grammar).

The IR substrate is **action-driven**: every transformation (canonicalization, class synthesis, flavour emission, width-aware layout) is expressed as `IrAction(target_type, body)` entries in open dispatch tables (`IrDispatch` / `IrVisitor` / `IrTransformer` / `IrEmitter`). New IR node types extend a table; the dispatcher needs no subclassing. Models live on this same spine — a compiled instance is walkable, dispatchable IR.

For the full picture:

- [`.wiki/lexic/architecture.md`](.wiki/lexic/architecture.md) — pipeline, layering, the IR substrate.
- [`.wiki/lexic/ir-shapes.md`](.wiki/lexic/ir-shapes.md) — every IR node + the action algebra.
- [`.wiki/lexic/public-api.md`](.wiki/lexic/public-api.md) — the public surface.
- [`.wiki/lexic/flavour-system.md`](.wiki/lexic/flavour-system.md) — adding flavours.

## Test grammars

`resources/ground_truth/` holds nine `.gbnf` grammars, two `.abnf` siblings and two `.ebnf` siblings (`arithmetic`, `json` each) for cross-flavour compile parity. Property tests round-trip every valid input through them:

`arithmetic` · `c` · `chess` · `japanese` · `json` · `json_arr` · `json_ws` · `list` · `vyx`

## Performance

`lexic.parsing` runs two engines behind one API: the deterministic **PDA** (default fast path, builds the typed model with no intermediate tree) backed by scannerless **Earley** as the sound completion. `tools/benchmark/compare_bench.py` races both — plus the public product entry — against **Lark** (LALR and Earley) on the same inputs, with a cross-engine equality gate before any timing.

Representative throughput (µs/char, lower is faster; single machine, 2026):

| input | lark-lalr | lark-earley | earley | **pda** |
|---|---|---|---|---|
| ABNF self-emit *(grammar text)* | — | ~29 | ~16 | **~9** |
| GBNF self-emit *(grammar text)* | — | ~19 | ~17 | **~22** |
| arithmetic *(instance)* | 1.8 | 24 | 21 | **2.5** |
| c *(instance)* | 1.2 | 21 | 10 | **1.1** |
| chess *(instance)* | 0.9 | 10 | 12 | **1.6** |
| json *(instance)* | 0.9 | 14 | 69 | **3.4** |

> **WIP.** Two rows are under active optimization and will be re-measured:
> the GBNF grammar-text PDA currently degrades on large inputs (island
> sub-parses in the character-class rules; the Earley completion stays
> flat), and the json instance parse allocates one record per grammar rule
> match — ~60% of which are duplicated whitespace/delimiter leaves that a
> planned per-parse intern will share. *(Remove this note when both land.)*

Reading the numbers fairly: Lark's **LALR** + contextual lexer is genuinely fast — but it yields a *generic parse tree*, while `earley`/`pda` build the **typed model**, so those columns include construction Lark's do not. LALR is not viable for the two meta-grammars (rulename↔ruleref overlap needs unbounded lookahead), so Lark runs Earley there. Where LALR cannot handle a grammar it is reported, never silently swapped. Compilation itself is dominated by parsing — no file I/O or subprocess on the path.

## Development

Lexic uses [uv](https://docs.astral.sh/uv/). Always prefix commands with `uv run` — never run `pytest` or `ruff` bare.

```bash
uv sync                                  # install deps (dev-only; no runtime deps)
uv run pytest tests/ -q                  # full suite (~2820 tests)
uv run pytest tests/unit/lexic/ -q       # unit only
uv run pytest tests/integration/ -q      # integration only
uv run ruff check src/ tests/            # lint
uv run python tools/check_generated.py   # generated-twin gate (pyright + pylint
                                         # on every export, both modes)
tools/run_checks.sh                      # the done-gate (ruff + pyright + whole-tree pylint)
```

Mechanical lint/format fixes:

```bash
tools/auto_fix.sh   # ruff format → isort → ruff check --fix
```

## Project status

Lexic is pre-1.0 and actively developed. One IR-native pipeline drives everything: a native Earley/PDA engine (no third-party parser), a canonical `IrAst` that all flavours converge on, runtime class synthesis on the record spine, width-aware cross-flavour emission, and self-verifying module export — all off the same action-driven IR substrate. Public invariants live in [CLAUDE.md](CLAUDE.md) §Key invariants; architecture and design decisions live in the [wiki](.wiki/).

## License

Licenced under [LGPL](LICENSE)
