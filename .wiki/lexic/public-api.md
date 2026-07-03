# Public API

**When to load:** writing docs, examples, or integration tests; choosing between `parse`, `compile_text`, `compile_from_path`, `compile_grammar`, `parse_grammar`; understanding `CompiledGrammar` fields or `GrammarModel` methods.

How callers use Lexic. The stable surface lives in `compile.py`, `parse.py`, and `base.py`. Both grammar-text parsing and generated-instance parsing run on the same native Earley engine (`lexic.parsing`) — there is no Lark anywhere in the call path.

---

## Entry points

### `parse(text, grammar_path)` — `parse.py`

The simplest path. Compiles the grammar (memoised by path + mtime) and parses `text` in one call.

```python
from lexic.parse import parse

model = parse("x=1\n", "resources/ground_truth/arithmetic.gbnf")
model.to_text()   # → "x=1\n"
```

Returns a `GrammarModel` instance whose concrete type is the start-rule class.

---

### `compile_text(text, *, flavour)` — `compile.py`

Compiles a grammar string into a `CompiledGrammar`. Use when you have the grammar in memory.

```python
from lexic.compile import compile_text

cg = compile_text(grammar_text, flavour="gbnf")
model = cg.parse("x=1\n")
```

`flavour` defaults to `"gbnf"`. Memoised by the caller-supplied `cache_key` argument (`cache_key=None`, the default, means "do not memoize"); the generated module filename is independently `generated/anon_<sha1-of-text>.py`.

---

### `compile_from_path(path, *, flavour)` — `compile.py`

Like `compile_text` but reads the file and memoises by `(path, mtime, size, flavour)`. Flavour is inferred from the file extension if omitted. Writes `generated/<stem>.py` where `stem` is the filename without extension (e.g. `arithmetic.gbnf` → `generated/arithmetic.py`).

---

### `parse_grammar(text, flavour)` — `compile.py` (re-exported from `lexic`)

The public grammar-text → `IrAst` seam. Takes an `IrFlavour` singleton (e.g. `GBNF_FLAVOUR`): requires `flavour.reducer` to be an actual `Reducer` instance (else `UnsupportedConstructError`), runs `parse_reduced(normalize(flavour.grammar), text, flavour.reducer)` — the normalised self-grammar memoised per flavour name — and verifies the reduction yields an `IrAst` (else `UnsupportedConstructError`). Use it whenever you need the IR of a grammar without compiling classes (e.g. cross-flavour transpilation: `parse_grammar(text, GBNF_FLAVOUR)` then `ABNF_FLAVOUR.apply(ast)` — see `getting_started/ex04_transpile_flavours.py`).

---

### `compile_grammar(text, flavour, *, non_semantic_rules, start)` — `compile.py`

Low-level entry point. Returns `(start_name, list[RuleSpec])` — IR specs only, no generated classes and no parser. Called internally by `compile_text` / `compile_from_path`.

Internally: resolves `(start, non_semantic)` from source comments (the private `_scan_directives` helper in `compile.py`), calls `parse_grammar(text, flavour)` for the `IrAst`, resolves the start rule (see precedence below), rebuilds the `IrAst` with the resolved `start` and each named rule reconstructed with `semantic=False`, and calls `derive_specs(ast)` (which reads the derived `ast.non_semantic` property).

---

### `codegen(specs, stem)` — `codegen/__init__.py`

```python
codegen(specs: list[RuleSpec], stem: str) -> dict[str, type]
```

Writes `generated/<stem>.py` (ruff-formatted) and returns `{class_name: cls}`. **No `flavour` parameter** — codegen is flavour-agnostic.

---

### `build_instance_parser(specs, classes, start_rule)` — `parsing/models.py`

```python
build_instance_parser(specs, classes, start_rule) -> tuple[IrAst, ModelFold]
```

Replaces the old `build_lark`. One-call helper used by `compile_text` / `compile_from_path` after `codegen`: reconstitutes the derived `RuleSpec`s into an `IrAst` instance grammar (`specs_to_grammar`) and builds the `ModelFold` that turns a `ParseTree` from that grammar into generated `GrammarModel` instances.

---

## `CompiledGrammar`

Returned by `compile_text` / `compile_from_path`. Fields:

| Field | Type | Purpose |
|---|---|---|
| `classes` | `dict[str, type]` | Rule name → generated Pydantic class |
| `specs` | `dict[str, RuleSpec]` | Rule name → IR spec |
| `grammar` | `IrAst` | The Earley-normalised instance grammar (held so the engine's identity-memoised `compile_tables` stays hot across repeated `.parse()` calls) |
| `fold` | `ModelFold` | `ParseTree` → model-instance fold (replaces the old `lark.Transformer`) |

`.parse(text)` is the only method callers need. It runs `self.fold.apply(parse_first(self.grammar, text))` — `parse_first` is the engine's deterministic-first-derivation entry (parity with the retired Lark path's `ambiguity="resolve"`; some ground-truth instance grammars, e.g. `json_ws`'s `int`, are genuinely ambiguous). If the fold doesn't produce a `GrammarModel` for the start rule, `.parse` raises `UnsupportedConstructError`.

---

## `GrammarModel`

Every generated class subclasses `GrammarModel(BaseModel)` and carries `__grammar__: ClassVar[RuleSpec]`.

| Method | Returns | Notes |
|---|---|---|
| `to_text()` | `str` | Lossless round-trip to original source text |
| `to_grammar(flavour="gbnf")` | `str` | Emits the grammar rule for this class |
| `semantic_dump()` | `dict` | `model_dump()` minus structural/whitespace fields (e.g. `ws`) |

`to_text()` is undefined on alternation (abstract) classes — call it on a concrete subclass.

---

## Grammar format (GBNF)

Rules use `::=` assignment. Character classes in `[...]`, string literals in `"..."`, quantifiers `?` / `*` / `+` / `{m,n}`. Directives go in line comments and are read before the parser runs:

```gbnf
# @non-semantic ws          ← exclude ws refs from semantic_dump()
# @start my_rule            ← override start rule (default: first rule)

root  ::= (expr "=" ws term "\n")+
expr  ::= term ([-+*/] term)*
ws    ::= [ \t\n]*
```

Directive resolution precedence (highest first):

1. Explicit argument to `compile_grammar(start=..., non_semantic_rules=...)`
2. `@start` / `@non-semantic` directives in source comments
3. Positional fallback (first rule = start; no non-semantic rules)

---

## Grammar-parsing golden gates

`tests/integration/test_gbnf_ir_equivalence.py` and `test_abnf_ir_equivalence.py` used to compare the engine's grammar parse against the (now-deleted) `MetaGrammarParser`/Lark path — they no longer have a second implementation to diff against. Both are now golden fingerprint tests: every ground-truth/fixture grammar must reduce to an `IrAst` with an expected `(start_rule, rule_names)` fingerprint, unambiguously (`is_ambiguous` is false), and re-emitting through the flavour singleton and re-parsing must preserve that fingerprint (full-AST round-trip equality is *not* asserted — the GBNF emitter canonicalises some bodies, so `parse(emit(ast)) == ast` does not hold exactly for the json variants, only the rule-set fingerprint is stable).

---

## Which entry point to use

| Situation | Entry point |
|---|---|
| Parse one string against a file on disk | `parse.parse` |
| Grammar is in memory; parse many strings | `compile_text` → `.parse()` |
| Grammar is a file; parse many strings | `compile_from_path` → `.parse()` |
| Inspect IR specs without generating code | `compile_grammar` |
| Grammar text → `IrAst` only (transpile, inspect, re-emit) | `parse_grammar` |
