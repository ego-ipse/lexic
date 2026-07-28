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
- **Refuse ambiguity, on every route.** A span whose derivations build two different models raises rather than a parser quietly picking one. The test is about VALUES, not derivation counts: a grammar routinely derives one text several ways without meaning anything by it, so a *split* — one production carved two ways, same arm, different boundary — has a defined answer and is never refused. Only an *arm* choice is. The opt-out is a **resolver, not a flag**: `parse(text, resolve=...)` hands both derivations to a deterministic callable of yours, and reaches whichever engine ends up choosing.
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
| `ex06_token_grammar.py` | Token grammars: parse token-granular, round-trip, next-token mask. |
| `ex07_constrained_generation.py` | A generation loop: mask → pick → `push` until `accepts()`. |
| `ex08_twin_module.py` | Export an importable twin; lexic parses its own export back. |
| `ex09_json_reducer.py` | `parse_reduced` + the JSON reducer kit — values, not model classes. |
| `ex10_templating.py` | `template(...)`: extract selected paths, skip the rest as raw spans. |
| `ex11_hf_tokenizer.py` | Load an HF `tokenizer.json` with lexic's own JSON + `IrTokenizer`. |

## Two products: models and pure IR

The `compile/` package compiles grammar text into **either or both** of:

- **Compiled models** — classes synthesized at runtime on an immutable record spine (`IrNamedTuple`) via `type(name, bases, ns)`. No source emit, no import, no file write; a model *is* a walkable IR record. Files are written only on the explicit `export_module` path.

  Because those classes are built at runtime, a type checker cannot see their fields: `model.item` works, but reads as unknown (the repo spells this `getattr(model, "item")` to say so). When you want *statically typed* field access, export the twin module — `export_module` writes a real `.py` with real annotations, and lexic parses its own export back to verify it.
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
| GBNF | `.gbnf` | Production (character-level, plus llama.cpp token terminals — see §Tokens) |
| ABNF | `.abnf` | Production (RFC 5234 + 7405, incl. `%d`/`%b`/`%x` sequences, case markers, the B.1 core-rules prelude) |
| EBNF | `.ebnf` | Production (ISO-family: `=`/`;` rules, `{}`/`[]`, `n * x` repetition, `(* *)` comments) |

GBNF's token-level terminals (`<token>`, `<[id]>`, `<[lo-hi]>`, `!<…>`, `.`) are supported — see §Tokens. EBNF has no native character-class or negation syntax: classes emit as quoted alternations where finite, and constructs EBNF cannot spell (negation, open-bounded counted repetition) are refused explicitly rather than approximated.

A *flavour* is the grammar notation, carried entirely as data: a self-grammar (authored as `IrAst`), a `Reducer` (reduction bodies + a noise policy derived from the grammar's own `semantic=False` flags), an `EscapeCodec`, optional core rules (ABNF's RFC prelude), and emit actions — an `IrFlavour` with **zero parsing methods**. Add one either as a flat `grammars/<name>.py` module or as a **text manifest** loaded with `load_flavour`. See [`.wiki/lexic/flavour-system.md`](.wiki/lexic/flavour-system.md).

## Tokens

Lexic parses character streams by default, and **token streams** when a
grammar's terminals name tokens instead of characters. Both run on the same
engine and the same pipeline.

An **encoding** gives a character class's ordinals their meaning. `IrUnicode`
is the default — ordinals *are* code points. An `IrTokenizer` is a peer, not a
special case: its ordinals are vocab ids. A grammar's token terminals name an
encoding, and `compile_text(..., tokenizer=)` binds it.

```gbnf
root     ::= <think> thinking </think> .*
thinking ::= !</think>*
```

`<think>` is the token whose spelling **is** `<think>` — the angle brackets are
part of the token's text. That is llama.cpp's GBNF semantics; lexic describes
the format rather than prescribing to it. Content between tokens is expressed
with negation (`!</think>*`). `<[7]>` names a token by id, `<[3-9]>` an id
range, `!<…>` any token except one, and `.` any token at all.

```python
tok = IrTokenizer.from_vocab("tokens", {"<think>": 0, "</think>": 1, "hi": 2})
compiled = compile_text(GRAMMAR, tokenizer=tok)

model = compiled.parse("<think>hi</think>")   # parse token-granular
model.to_text()                               # → char-exact round-trip

cursor = compiled.constrain()                 # constrain generation
cursor.mask()                                 # → admissible next-token ids
cursor.push(0)                                # advance; accepts() tests the end
```

Three capabilities, independent of each other: read/emit token grammars with
**no** tokenizer at all; parse instances with one; and constrain generation
token by token. The generation cursor holds a single live chart — `push` grows
it rather than reparsing the prefix, so `mask()` costs the candidate's spelling,
not the history.

An `IrTokenizer` is built from a vocab (longest-match) or from a vocab plus
ordered merges (exact ranked-merge BPE), with specials matched atomically. It
carries its own segmentation pipeline — byte-level remapping, normalizers,
pre-token splitters, byte fallback — every field of it **derived from a
document's own sections**, never fitted to one family.

Reading a `tokenizer.json` is `lexic.api.json_tokenizer`, which takes the
grammar+reducer that parse the document as *parameters*, so it privileges no
formulation (`ex11`, `ex12`). Fetching one is `ext/API/`, outside the shipped
package. `lexic.ir` models the tokenizer and knows neither — a format that
merely happens to be hosted somewhere does not belong to that host.

A vocabulary is per-deployment, not per-grammar: `compiled.bind(tok)` returns
a new artefact against another vocabulary without recompiling.

**Boundary:** token spans are char-aligned. Under a byte-level pipeline a token
can end mid-code-point; `tokenize()` still returns its id, but that token gets
no character span, so `boundaries()` — and therefore token-granular *parsing* —
covers char-aligned segmentations. This is the documented limit, not a bug to
route around.

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

## Performance, and how to read it

`tools/benchmark/` races lexic's two engines against **Lark** (LALR + Earley),
**parsimonious**, **pyparsing** and **ANTLR** — the last on both its Java target
and its Python runtime.

**Every engine gets the same grammar.** Each competitor's grammar is derived
mechanically from the one `IrAst` lexic compiles; nobody gets a hand-tuned
variant. An earlier version of this benchmark did give each tool its own
hand-written grammar, and its headline number was meaningless as a result. The
translations are gated by a differential in *both* directions — every emitted
grammar must accept what lexic accepts **and refuse what lexic refuses** — because
a grammar that accepts everything passes an accept-only check. That gate has
caught five real emitter bugs that would otherwise have printed as "this tool
cannot express the grammar".

µs/char, lower is faster; medians of interleaved rounds, noise floor 0.6–2.6%:

| grammar | antlr *(Java)* | lark-lalr | parsimonious | lexic-pda | antlr-py | pyparsing | lexic-earley | lark-earley |
|---|---|---|---|---|---|---|---|---|
| arithmetic | **0.28** | 2.7 | 2.8 | 3.2 | 7.8 | 22.0 | 62.9 | 44.8 |
| csv | **0.08** | 0.7 | 1.2 | 0.9 | 2.1 | 3.7 | 13.7 | 12.0 |
| json | **0.34** | 3.5 | 2.1 | 2.2 | 9.5 | 11.6 | 36.2 | 40.8 |
| gbnf-meta | **0.51** | refuses | refuses | *island* | 11.7 | refuses | 66.1 | 186.5 |
| abnf-meta | **0.26** | refuses | 3.9 | *island* | 13.0 | 92.8 | 63.0 | 131.9 |
| vyx | **0.33** | refuses | 2.8 | 59.0 | 10.1 | 29.7 | 51.2 | 98.8 |

**ANTLR's Java target is the fastest thing here, by an order of magnitude, on
every grammar.** That is the honest result and it is not close. It is also a
*tool+runtime* comparison rather than an algorithmic one — that row is Java and
every other row is Python — which is exactly the question "what parses this
grammar fastest" asks. `antlr-py` is the same generated parser on
`antlr4-python3-runtime`, a pure-Python ATN simulator; the gap between the two
ANTLR rows is the runtime, not the tool.

Three things the table does not say on its own:

- **The engines do not build the same thing.** lexic returns a *typed model* the
  source is recoverable from; Lark returns a generic `Tree`, parsimonious a
  `Node` tree, pyparsing a `ParseResults`, ANTLR a `ParserRuleContext`. Model
  construction is real work inside lexic's numbers that the others do not pay.
- **lexic's PDA declines both meta-grammars.** `gbnf-meta` and `abnf-meta` mark
  their start rules as islands, so the predictive path does not run at all and
  Earley is the whole parse. Where a fast path does not apply, it is reported —
  never silently swapped for a different measurement.
- **`lark-lalr` refuses three of six.** Genuine reduce/reduce and lookahead
  conflicts, not a harness artefact: the meta-grammars' rulename↔ruleref overlap
  needs unbounded lookahead, and vyx is not LALR(1). A refusal is a result and is
  printed as one.

Run it yourself: `uv run python -m tools.benchmark.bench --rounds 3`, or
`--only json vyx` for a subset. ANTLR needs a JDK; the Java row builds a parser
and holds a JVM open across the run, warmed until its timings settle, taking one
round per line on stdin and reporting `System.nanoTime()` around the parse alone
— so it interleaves with every other column instead of degrading into a separate
run.

## Development

Lexic uses [uv](https://docs.astral.sh/uv/). Always prefix commands with `uv run` — never run `pytest` or `ruff` bare.

```bash
uv sync                                  # install deps (dev-only; no runtime deps)
uv run pytest tests/ -q                  # full suite (~2880 tests)
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

Lexic is pre-1.0 and actively developed. One IR-native pipeline drives everything: a native Earley/PDA engine (no third-party parser), a canonical `IrAst` that all flavours converge on, runtime class synthesis on the record spine, width-aware cross-flavour emission, and self-verifying module export — all off the same action-driven IR substrate.

Where it stands honestly: correctness and fidelity are the strengths — one grammar compiles to typed classes that round-trip exactly, in any flavour, with ambiguity refused rather than guessed at. Raw throughput is not: a mature generated parser in a JIT'd runtime is an order of magnitude faster, and the benchmark above says so rather than choosing inputs that hide it. Public invariants live in [CLAUDE.md](CLAUDE.md) §Key invariants; architecture and design decisions live in the [wiki](.wiki/).

## License

Licenced under [LGPL](LICENSE)
