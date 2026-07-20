---
tags: [theory, reference]
related: [lexic/ir-shapes, lexic/architecture]
---

# Parsing Theory

**When to load:** reasoning about grammar semantics and formal language classes; understanding AST vs CST vs IR distinctions; evaluating grammar toolchains; investigating parser algorithm choices (Earley vs LALR); understanding why PEG semantics differ from CFG semantics.

See also: [[lexic/ir-shapes]], [[lexic/architecture]]

---

## Formal language hierarchy (Chomsky)

Lexic operates entirely within **Type 2 — context-free grammars (CFGs)**.

| Type | Grammar class | Recogniser | Examples |
|---|---|---|---|
| 3 | Regular | Finite automaton / regex | character classes, quantifiers |
| 2 | Context-free | Push-down automaton | programming language syntax, GBNF, ABNF |
| 1 | Context-sensitive | Linear-bounded automaton | (irrelevant here) |
| 0 | Unrestricted | Turing machine | (irrelevant here) |

Key CFG property: a non-terminal's production does not depend on surrounding context. This is why grammar-constrained LLM sampling is tractable — the sampler only needs to track one parse stack per live branch.

---

## Abstract Syntax Trees (ASTs)

### AST vs CST

The parser pipeline has two distinct tree types:

- **Concrete Syntax Tree (CST) / Parse Tree** — one node per grammar production; preserves every token including punctuation, whitespace, parentheses.
- **Abstract Syntax Tree (AST)** — elides nodes that carry no semantic content (delimiters, grouping, most punctuation); one node per *meaningful construct*.

Lark produces a CST by default; its `Tree`/`Token` API corresponds to production nodes, and the `Transformer` class converts a CST into whatever AST shape the caller defines. Lexic no longer uses Lark (it did historically, via `MetaGrammarParser._IrTagTransformer` — see [[lexic/architecture]] for the cutover). Lexic's own engine (`lexic.parsing`) produces an SPPF-backed `ParseTree`/`SppfNode` CST; `lexic.parsing.reduce.Reducer` plays the same role as a Lark `Transformer`, folding that CST into `IrAst` via a rule-keyed reduction table instead of visitor methods.

### Compiler pipeline position

```
source text
    │
    ▼  lexical analysis (tokeniser)
token stream
    │
    ▼  syntactic analysis (parser)
CST (parse tree)
    │
    ▼  AST construction (transformer / visitor)
AST
    │
    ▼  semantic analysis / IR lowering
IR
    │
    ▼  code generation / emission
target text / bytecode
```

Lexic's IR sits at the "IR" layer. `IrAst` is the AST; `IrRule`/`IrItem`/`NewRuleSpec` are the lowered IR.

### Visitor vs Transformer patterns

- **Visitor** — traverses the tree, accumulates side effects or a result; does not rebuild the tree. Lexic: `IrVisitor` (`ir/walk.py`), used by `collect_aliases` (Task 8).
- **Transformer** — returns a new tree (or value) from each node bottom-up; Lark's `Transformer` is the canonical example. Lexic: `IrTransformer` (`ir/walk.py`), used by the quantifier/group desugaring transforms in `lexic.parsing.normalize`; `lexic.parsing.reduce.Reducer` is the transformer-shaped seam for forest → `IrAst` reduction specifically.

Both patterns automatically dispatch on node type, avoiding explicit `isinstance` chains.

### AST design invariants

- **Closed union:** every node type that can appear in the tree must be handled in every dispatch table. Unknown types must `raise UnsupportedConstructError`, never silently pass. See [[lexic/error-vocabulary]].
- **Losslessness for round-trip:** the AST must preserve enough information to reconstruct the original grammar text. Lexic enforces this via `to_text()` and `to_gbnf()` on `GrammarModel`. See [[lexic/invariants]].
- **No grammar-specific hardcoding in generic code:** AST traversal code in `ir/` must not reference GBNF or ABNF-specific constructs.

---

## Parsing algorithms

### CFG algorithms

| Algorithm | Class | Ambiguity | Left recursion | Speed | Used in Lexic |
|---|---|---|---|---|---|
| LL(k) | Top-down | Rejects | No | O(n) | No |
| LALR(1) | Bottom-up | Rejects | Yes (preferred) | O(n) | No (Lark-only, historical) |
| Earley | Bottom-up | Handles | Yes | O(n³) worst, O(n) with Leo on right-recursion | `lexic.parsing` — the one and only engine, both for grammar text and for generated instances |
| GLR | Bottom-up | Handles | Yes | O(n³) worst | tree-sitter |

**Earley in Lexic (current, post-Lark-cutover):** `lexic.parsing` is a from-scratch Earley engine (SPPF per Scott 2008) over `IrAst`-shaped grammars — not a wrapper around Lark or any other parser generator. `parse` returns the strict single derivation and raises `UnsupportedConstructError` on no-parse or ambiguity; `parse_first` (used for instance parsing) picks a deterministic first derivation instead of raising, matching the historical Lark path's `ambiguity="resolve"` behaviour. `parse_forest`/`derivations`/`is_ambiguous` expose the full SPPF for callers that need it. The Leo optimisation makes right-recursive quantifier desugaring (`*`/`+`) linear in input length; only large bounded counts (`{lo,hi}`) still unroll to `hi` nested rules. See [[lexic/architecture]].

Historically (pre-2026-07 cutover) Lexic ran two separate Lark parsers — an Earley one (`ambiguity="resolve"`) for grammar text via `gbnf/parser.py`-style modules, and a `MetaGrammarParser` using Lark's LALR mode for the generic meta-grammar layer that superseded it. Both are deleted; `lark` is no longer a Lexic dependency (it remains only as `tools/benchmark/parse_bench.py`'s external reference baseline).

### PEG (Parsing Expression Grammars)

PEGs are a distinct formalism from CFGs, relevant because some grammar toolchains use them.

**Core difference: ordered vs. unordered choice**

- **CFG:** `A | B` — both alternatives are tried; if both match the same input, the grammar is *ambiguous*.
- **PEG:** `A / B` — ordered choice; if A matches, B is never tried. PEGs are by construction *unambiguous*.

This makes PEGs unsuitable as a notation for Lexic's IR: GBNF and ABNF both specify CFG semantics (unordered choice). Forcing PEG semantics would change the language defined by a grammar.

**Lookahead predicates** — PEGs introduce two operators that CFGs lack:

- `&e` — positive lookahead: succeeds if `e` matches the current position but consumes no input.
- `!e` — negative lookahead: succeeds if `e` does *not* match the current position; consumes no input.

These are absent from GBNF and ABNF. Lexic has no `IrNode` type for lookahead predicates; they would require a new leaf type and changes to `ir/nodes.py`, `ir/walk.py`, and all emitters.

**Packrat parsing and memoisation** — a packrat parser evaluates a PEG in O(n) time by memoising every sub-expression result at every input position. Memory usage is O(n × |grammar|). Lark's Earley parser uses SPPF (Shared Packed Parse Forest), a related technique.

**Left recursion** — PEGs (in their original form) do not support left recursion — a top-down recursive descent parser loops infinitely on `A → A α`. Extended PEG implementations (notably in Lark's Earley mode and tree-sitter) use seed-growing algorithms to handle it. LALR parsers prefer left-recursive rules (lower stack usage vs. right-recursive equivalents).

---

## Grammar toolchain comparison

### Lark (Python)

Lexic **used** Lark as its meta-grammar engine historically; it was fully retired in the 2026-07 cutover (see [[lexic/architecture]]) and is no longer a dependency. It survives only as `tools/benchmark/parse_bench.py`'s external reference baseline — pure Lark, zero lexic machinery, timed against the native engine.

| Property | Detail |
|---|---|
| Language | Python (pure, no dependencies) |
| Algorithms | Earley (SPPF), LALR(1) with contextual lexer |
| Grammar format | EBNF-like (W3C-style postfix quantifiers) |
| Ambiguity | Earley handles it; LALR requires disambiguation |
| Output | `Tree` + `Token`; transformable via `Transformer` |
| Left recursion | Supported in Earley mode |
| Use in Lexic | None (historical only) — `lexic.parsing` is a native Earley engine, not a Lark wrapper |

### ANTLR 4

| Property | Detail |
|---|---|
| Language | Java (generates parsers in 10+ target languages) |
| Algorithm | Adaptive LL(\*) — handles most grammars without grammar rewriting |
| Grammar format | `.g4` — EBNF-like with semantic predicates, actions, labels |
| Output | Parse tree + listener/visitor scaffolding |
| Strengths | Huge grammar library; multi-language output; IDE plugins |
| Weaknesses | JVM dependency; grammar actions couple grammar to host language |

Not used by Lexic. Relevant when importing grammars from other ecosystems (e.g. `.g4` → GBNF conversion).

### Tree-sitter

| Property | Detail |
|---|---|
| Language | C (bindings for many languages) |
| Algorithm | GLR-like; incremental |
| Grammar format | JavaScript DSL (defines precedences, conflicts) |
| Output | Concrete syntax tree; efficient diff/update |
| Strengths | Incremental re-parse on edit; excellent error recovery; used by editors |
| Weaknesses | Designed for programming language syntax, not structured data |

Not used by Lexic. Conceptually relevant for error-tolerant parsing but the incremental model is not needed for Lexic's batch compilation use case.

### PEG parsers (pest, nom, pyparsing)

Pure PEG parsers (Rust's `pest`, Python's `pyparsing`, etc.) produce unambiguous deterministic parses. They cannot faithfully represent GBNF/ABNF semantics where unordered choice is intended.

---

## IR design: relevant theory

### Why a separate IR layer

The IR decouples the grammar notation (flavour-specific syntax) from the code generator (model class emission) and the runtime emitter (`to_gbnf()`, `to_abnf()`). Each new flavour adds one parser and one emitter; the IR and codegen are unchanged.

In compiler terms: adding a new *source language* only requires a new front-end (parser → IR); adding a new *target language* only requires a new back-end (IR → emitter).

### Why quantifiers live on `IrItem`, not on leaves

In the old shape, every leaf atom carries `min, max` fields. This couples quantifier information to the leaf type and complicates generic traversal — every visitor must pattern-match on the leaf type to find the quantifier.

The new shape wraps every leaf in `IrItem(atom, quantifier)`. Traversal code handles quantifiers uniformly at the `IrItem` level; leaf types are purely structural. This is the standard compiler IR pattern (analogous to wrapping every expression in a typed node).

See [[lexic/ir-shapes]] for the full type hierarchy.

### Left recursion in GBNF grammars

GBNF grammars may contain left-recursive rules (e.g. a recursive expression grammar). Earley handles these naturally, and Lexic's own engine (`lexic.parsing`) is Earley throughout — for grammar text and for generated instances alike — so this was never actually a risk in the shipped pipeline. (Historically, before the 2026-07 Lark→Earley cutover, the generic meta-grammar layer used Lark's LALR mode; that layer and the LALR-vs-Earley tension it raised are both gone.)

### Ambiguity in grammar compilation vs. LLM sampling

- At *compile time* (Lexic's domain): grammar ambiguity means the IR derivation step (`derive_specs`) may produce overlapping class hierarchies. Lexic resolves this by the `kind` classification — alternation rules produce abstract classes, sequence rules produce concrete classes.
- At *sampling time* (llama.cpp's domain): grammar ambiguity causes multiple valid parse paths in the sampler, increasing memory and CPU cost. Lexic should avoid emitting GBNF grammars with exponential branching (the `x? x? x?` antipattern).

---

## IR / codegen gaps

> [!note]
> These are gaps in what the current IR can represent, irrespective of grammar format.

- **Lookahead predicates** (`&e`, `!e`) — no `IrNode` type; not expressible in any current flavour.
- **Unicode category classes** — `\p{L}`, `\p{N}` etc. are not in the character-class model; `IrCharClass.pattern` is POSIX bracket-expression interior only.
- **Named capture / labeled alternatives** — grammar authors cannot name specific arms of an alternation; field names are derived algorithmically from the IR.
- **Semantic predicates / actions** — grammar rules cannot carry host-language code (deliberate constraint; keeps grammar-as-canonical-truth invariant).
- **Error recovery / partial parse** — `parse()` fails hard on invalid input; no partial-match or error-tolerant mode.
- **Recursive type generation** — self-referential rules produce model classes with forward references; these are not yet handled in the new pipeline's `ModelEmitter`.
