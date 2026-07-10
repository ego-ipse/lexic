# Public API

**When to load:** writing docs, examples, or integration tests; choosing between `parse`, `compile_text`, `compile_from_path`, `canonical_grammar`, `parse_grammar`; understanding `CompiledGrammar` fields or `GrammarModel` methods.

How callers use Lexic. The stable surface lives in `compile.py`, `parse.py`, and `base.py`. Both grammar-text parsing and generated-instance parsing run on the same native Earley engine (`lexic.parsing`) — there is no Lark and no `RuleSpec` anywhere in the call path.

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

### `compile_text(text, *, cache_key, flavour, out_dir)` — `compile.py`

Compiles a grammar string into a `CompiledGrammar`. Use when you have the grammar in memory.

```python
from lexic.compile import compile_text

cg = compile_text(grammar_text, flavour="gbnf")
model = cg.parse("x=1\n")
```

`flavour` defaults to `"gbnf"`. **Memoised by content by default** (2026-07-04): the default cache key is `(content sha stem, flavour, resolved out_dir)` — compiling the same source in the same flavour to the same output directory returns the cached `CompiledGrammar` and its class objects, no cold recompile. Pass `cache_key=` to override the key outright (an explicit key is used as-is, not augmented with `out_dir`); `reset_cache_for_tests()` clears the cache when a caller needs fresh class objects. The generated module filename is independently `<out_dir>/anon_<sha1-of-text>.py`.

`out_dir` (`str | Path | None = None`) sets where the generated module is written; `None` resolves to the project's `generated/` directory (today's default, unchanged). This is the *only* way to redirect codegen output — no env var, no global config — and it threads through `compile_from_path` and `codegen()` the same way.

---

### `compile_from_path(path, *, flavour, out_dir)` — `compile.py`

Like `compile_text` but reads the file and memoises by `(path, mtime, size, flavour, resolved out_dir)`. Flavour is inferred from the file extension if omitted. Writes `<out_dir>/<stem>.py` where `stem` is the filename without extension (e.g. `arithmetic.gbnf` → `generated/arithmetic.py` by default). **Caution:** two ground-truth grammars that share a stem across flavours (e.g. `json.gbnf` and `json.abnf` both stem to `json`) will overwrite each other's generated module if both are compiled via `compile_from_path` — use `compile_text` (content-hashed stems) when compiling more than one flavour of the "same" grammar in one process, as `tests/integration/test_cross_flavour.py`'s cross-flavour parity test does.

---

### `parse_grammar(text, flavour)` — `compile.py` (re-exported from `lexic`)

The public grammar-text → `IrAst` seam. Takes an `IrFlavour` singleton (e.g. `GBNF_FLAVOUR`): requires `flavour.reducer` to be an actual `Reducer` instance (else `UnsupportedConstructError`), runs `parse_reduced(normalize(flavour.grammar), text, flavour.reducer)` — the normalised self-grammar memoised per flavour name — and verifies the reduction yields an `IrAst` (else `UnsupportedConstructError`). Returns the **raw** parsed `IrAst` — not yet canonicalized. Use it whenever you need the IR of a grammar without compiling classes (e.g. cross-flavour transpilation: `parse_grammar(text, GBNF_FLAVOUR)` then `ABNF_FLAVOUR.apply(ast)` — see `getting_started/ex04_transpile_flavours.py`).

---

### `canonical_grammar(text, flavour, *, non_semantic_rules=None, start=None)` — `compile.py`

The public **front half** of `compile_text`/`compile_from_path`: parse + canonicalize + directive flags. Returns the canonical, semantic-flagged `IrAst` directly — no `RuleSpec`, no generated classes. This is the successor of the retired `compile_grammar` (which returned `(start_name, list[RuleSpec])`); `generate.py` builds on `canonical_grammar` directly (it needs only the grammar's rules-by-name shape, not generated Pydantic classes).

Internally: resolves `(start, non_semantic)` from source comments (the private `_scan_directives` helper in `compile.py`), calls `parse_grammar(text, flavour)` for the raw `IrAst`, runs `canonicalize(ast)` (`ir/canonical.py` — the language-preserving normal form two flavours of the same language converge on), resolves the start rule (precedence below; canonicalize folds names, so directive/arg names fold too), and reconstructs each named rule with `semantic=False`.

Directive/start resolution precedence (highest first):

1. Explicit argument (`start=...`, `non_semantic_rules=...`)
2. `@start` / `@non-semantic` directives in source comments
3. Positional fallback (first rule = start; no non-semantic rules)

---

### `build_codegen_grammar(ast)` — `codegen/passes.py`

```python
build_codegen_grammar(ast: IrAst) -> IrAst
```

Takes the canonical grammar and applies the three codegen-only passes (`hoist_groups` → `hoist_arms` → `relax_non_semantic`) that produce **THE codegen grammar** — the shape every generated class's `__grammar__` and every field's `IrBind` positions are computed against. See [[codegen]].

---

### `compute_binding(codegen_grammar)` — `codegen/binding.py`

```python
compute_binding(ast: IrAst) -> list[RuleBinding]
```

The open-table successor of the retired `derive_specs`'s classify/parents/naming jobs. `RuleBinding(rule_name, class_name, parent_class_name, kind, fields: dict[str, IrBind])`, one per rule, parents before subclasses. See [[codegen]], [[field-naming]].

---

### `codegen(canonical, codegen_grammar, binding, stem, out_dir=None)` — `codegen/__init__.py`

```python
codegen(canonical: IrAst, codegen_grammar: IrAst, binding: list[RuleBinding], stem: str, out_dir: str | Path | None = None) -> dict[str, type]
```

Writes `<out_dir>/<stem>.py` (ruff-formatted) and returns `{class_name: cls}`. **No `flavour` parameter** — codegen is flavour-agnostic (it doesn't even import `lexic.grammars`). `out_dir=None` resolves via `resolve_out_dir()` to the project's `generated/` directory (`_resolve_generated_dir()`'s repo-root search, falling back to a cwd-relative `generated/`); `compile.py` calls `resolve_out_dir()` too, so its memo-key resolution and codegen's write path always agree on where a given `out_dir=None`/explicit value lands.

---

### The instance fold — `parsing/fold.py`

There is no `build_instance_parser`/wrapper-rule bridge anymore (`parsing/models.py` is deleted outright). The **one authored instance-fold** is `ModelFold` (2026-07-06; the name is reclaimed — the retired wrapper-rule `ModelFold` in `parsing/models.py` is unrelated): `compile.py`'s `_compile_core` builds a per-rule **IR body-table** (`IrMap[IrRuleRef, ModelBody]`, from the binding view + generated classes — each `ModelBody` carries its model constructor as an `IrLambda` plus structural metadata `kind`/`n_items`/`fields`/`fast`) and constructs `ModelFold(bodies)`. On construction the fold **bakes** every body to the flat-runtime `config: dict[str, RuleFold]` (`.baked`), the record the PDA clone compiler and the engine-fallback `apply` consume unchanged — byte-for-byte identical to the retired plain-data config. The IR body-table is the *same shape* the grammar-text `Reducer` carries its reductions in (a per-rule `IrMap` to `IrSelf` bodies). The instance grammar is `normalize(lift_optional_nullables(codegen_grammar))` — the *same* codegen grammar `codegen()` emitted classes against, so `kids[i] ↔ items[i]` and field extraction is positional indexing, not a name lookup against a synthetic wrapper grammar. See [[architecture]]'s "positional fold" section.

---

## `CompiledGrammar`

Returned by `compile_text` / `compile_from_path`. Fields:

| Field | Type | Purpose |
|---|---|---|
| `classes` | `dict[str, type]` | Rule name → generated Pydantic class |
| `grammar` | `IrAst` | The **canonical** grammar (what the user's grammar IS — also the generated module's `GRAMMAR` footer) |
| `instance_grammar` | `IrAst` | The Earley-normalised **codegen** grammar (held so the engine's identity-memoised `compile_tables` stays hot across repeated `.parse()` calls) |
| `fold` | `ModelFold` | The one authored instance-fold: an IR body-table (`bodies: IrMap[IrRuleRef, ModelBody]`) that bakes to `config: dict[str, RuleFold]` and folds a `ParseTree` → model-instance positionally over `instance_grammar` (name reclaimed from the retired wrapper-rule bridge) |
| `tables` | `ParserTables` | `instance_grammar`'s run-collapsed tables (every lexical run the fold-config licence proves safe, compiled once at build time) |

`.parse(text)` is the only method callers need. It runs `self.fold.apply(parse_first(self.instance_grammar, text, self.tables))` — `parse_first` is the engine's deterministic-first-derivation entry (some ground-truth instance grammars, e.g. `json_ws`'s `int`, are genuinely ambiguous). If the fold doesn't produce a `GrammarModel` for the start rule, `.parse` raises `UnsupportedConstructError`.

---

## `GrammarModel`

Every generated class subclasses `GrammarModel(BaseModel)` and carries `__grammar__: ClassVar[IrRule]` — its own rule from the codegen grammar — plus every bound field an `IrBind(item, mode, semantic)` in its `Annotated` field metadata.

| Method | Returns | Notes |
|---|---|---|
| `to_text()` | `str` | Lossless round-trip to original source text |
| `to_grammar(flavour="gbnf")` | `str` | Emits the grammar rule for this class — `get_flavour(flavour).apply(self.__grammar__)`, no `RuleSpec` conversion |
| `semantic_dump()` | `dict` | `model_dump()` minus fields whose `IrBind.semantic` is `False` (e.g. `ws`) |

`to_text()` raises `NotImplementedError` on an abstract alternation class (no fields, no binds) — call it on a concrete subclass instance.

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

See `canonical_grammar`'s precedence rules above for how `@start`/`@non-semantic` resolve against explicit arguments.

---

## Grammar-parsing golden gates

`tests/integration/test_gbnf_ir_equivalence.py` and `test_abnf_ir_equivalence.py` used to compare the engine's grammar parse against the (now-deleted) `MetaGrammarParser`/Lark path — they no longer have a second implementation to diff against. Both are now golden fingerprint tests: every ground-truth/fixture grammar must reduce to an `IrAst` with an expected `(start_rule, rule_names)` fingerprint, unambiguously (`is_ambiguous` is false), and re-emitting through the flavour singleton and re-parsing must preserve that fingerprint. `tests/integration/test_cross_flavour.py`'s `test_json_gbnf_and_abnf_compile_to_identical_generated_source` goes further for `json.gbnf`/`json.abnf`: it asserts the full **generated module source** is byte-identical (modulo the docstring's content-hashed stem) — the user-visible form of the canonicalization fixpoint `canonicalize(parse(json.gbnf)) == canonicalize(parse(json.abnf)) == JSON_GRAMMAR`.

---

## Which entry point to use

| Situation | Entry point |
|---|---|
| Parse one string against a file on disk | `parse.parse` |
| Grammar is in memory; parse many strings | `compile_text` → `.parse()` |
| Grammar is a file; parse many strings | `compile_from_path` → `.parse()` |
| Inspect the canonical grammar without generating code | `canonical_grammar` |
| Grammar text → raw (not-yet-canonicalized) `IrAst` only (transpile, inspect, re-emit) | `parse_grammar` |
