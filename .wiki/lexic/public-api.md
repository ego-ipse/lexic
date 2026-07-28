# Public API

**When to load:** writing docs, examples, or integration tests; choosing between `parse_instance`, `compile_text`, `compile_from_path`, `canonical_grammar`, `parse_grammar`, `export_module`; understanding `CompiledGrammar` fields or `GrammarModel` methods.

How callers use Lexic. The stable surface lives in the `compile/` package and `model.py`. Both grammar-text parsing and generated-instance parsing run on the same engine (`lexic.parsing` — PDA-first, Earley completion); there is no Lark and no `RuleSpec` anywhere in the call path. NOTE: `parse` is the ENGINE's name (`lexic.parsing.parse` → a raw `ParseTree`); the compile-side one-liners are `parse_instance`/`parse_instance_from_path`.

---

## Entry points

### `parse_instance(text, grammar, *, flavour="gbnf")` / `parse_instance_from_path(text, grammar_path, *, flavour=None)` — `compile/__init__.py`

The one-line entries (string-primary: the unqualified name takes grammar SOURCE; the `_from_path` twin infers flavour from the extension). Compile memoised, then parse.

```python
from lexic import parse_instance_from_path

model = parse_instance_from_path("x=1\n", "resources/ground_truth/arithmetic.gbnf")
model.to_text()   # → "x=1\n"
```

Returns a `GrammarModel` instance whose concrete type is the start-rule class. Callers doing repeated parses should hold the `CompiledGrammar` instead (`old lexic.parse.parse` was deleted 2026-07-18 — its name collided with the engine's public `parse`).

---

### `compile_text(text, *, cache_key, flavour, vocabulary, directives)` — `compile/__init__.py`

Compiles a grammar string into a `CompiledGrammar`. Use when you have the grammar in memory.

```python
from lexic.compile import compile_text

cg = compile_text(grammar_text, flavour="gbnf")
model = cg.parse("x=1\n")
```

`vocabulary` is the lens the grammar's terminals are read through — `Vocabulary(tokenizer, registry)`. The two were never separate channels: they compose over a default `unicode` before anything reads a terminal.

`directives` says what the grammar's `@directives` would say, as an argument — `Directives(start, non_semantic)`, exactly what the source-comment scan produces. Given explicitly it OVERRIDES the source. Use it when a caller knows a rule is structural noise and does not want to edit the grammar to say so.

```python
from lexic.compile import Directives, Vocabulary, compile_text

cg = compile_text(text, directives=Directives(non_semantic=frozenset({"ws"})))
cg = compile_text(text, vocabulary=Vocabulary(tokenizer))
```

Both are part of the memo key: one source compiled two ways must not hand back the first.

`flavour` defaults to `"gbnf"`. **Memoised by content by default**: the default cache key is `(content sha stem, flavour)` — compiling the same source in the same flavour returns the cached `CompiledGrammar` and its class objects. Pass `cache_key=` to prepend an extra key prefix; `reset_cache_for_tests()` clears the cache when a caller needs fresh class objects. Classes are synthesized in memory (`type()`) — there is no output directory to key on.

---

### `compile_from_path(path, *, flavour, vocabulary, directives)` — `compile/__init__.py`

Like `compile_text` but reads the file and memoises by `(path, mtime, size, flavour, vocabulary, directives)`, using `path.stem` as the class-module stem. Flavour is inferred from the file extension if omitted. Carries `compile_text`'s whole surface.

---

### `export_value(value, path, *, module=None)` — `compile/payload/__init__.py`

Writes whatever lexic parsed as an importable module: the value's payload as
four flat literals, plus an import of the reader emitted beside it. Returns the
written path, and writes the `.pyc` with it.

Which of the three targets you get — `classes`, `ir`, `plain` — is **not a
parameter**. It follows from the codomain of the reduction that produced the
value, and the exporter reads it off the symbols: a model carries its grammar's
classes, a reduced value carries the spine, plain data carries nothing and so
reads back with zero lexic modules imported.

`module` names where a reader will find symbols whose own module does not
import — which is exactly the synthesized classes a `CompiledGrammar` holds,
since they report a content-tagged module. Passing it also asserts it: if that
module already imports, the export refuses when it cannot supply the symbols, or
supplies them from a different compilation. Anything with a real importable
origin needs no `module` at all.

The value is projected under the fixpoint gate before anything is written, so an
artefact that cannot be read back is never created. See
[[generated-modules]] for the artefact's shape and the checks it runs at import.

---

### `parse_grammar(text, flavour)` — `compile/__init__.py` (re-exported from `lexic`)

The public grammar-text → `IrAst` seam. Takes an `IrFlavour` singleton (e.g. `GBNF_FLAVOUR`): requires `flavour.reducer` to be an actual `Reducer` instance (else `UnsupportedConstructError`), runs `parse_reduced(normalize(flavour.grammar), text, flavour.reducer)` — the normalised self-grammar memoised per flavour name — and verifies the reduction yields an `IrAst` (else `UnsupportedConstructError`). Returns the **raw** parsed `IrAst` — not yet canonicalized. Use it whenever you need the IR of a grammar without compiling classes (e.g. cross-flavour transpilation: `parse_grammar(text, GBNF_FLAVOUR)` then `ABNF_FLAVOUR.apply(ast)` — see `getting_started/ex04_transpile_flavours.py`).

---

### `canonical_grammar(text, flavour, *, non_semantic_rules=None, start=None)` — `compile/__init__.py`

The public **front half** of `compile_text`/`compile_from_path`: parse + canonicalize + directive flags. Returns the canonical, semantic-flagged `IrAst` directly — no `RuleSpec`, no generated classes. This is the successor of the retired `compile_grammar` (which returned `(start_name, list[RuleSpec])`); `generate.py` builds on `canonical_grammar` directly (it needs only the grammar's rules-by-name shape, not generated classes).

Internally: resolves `(start, non_semantic)` from source comments (the private `_scan_directives` helper in the compile package), calls `parse_grammar(text, flavour)` for the raw `IrAst`, runs `canonicalize(ast)` (`ir/canonical.py` — the language-preserving normal form two flavours of the same language converge on), resolves the start rule (precedence below; canonicalize folds names, so directive/arg names fold too), and reconstructs each named rule with `semantic=False`.

Directive/start resolution precedence (highest first):

1. Explicit argument (`start=...`, `non_semantic_rules=...`)
2. `@start` / `@non-semantic` directives in source comments
3. Positional fallback (first rule = start; no non-semantic rules)

---

### `build_codegen_grammar(ast)` — `compile/pipeline/passes.py`

```python
build_codegen_grammar(ast: IrAst) -> IrAst
```

Takes the canonical grammar and applies the three codegen-only passes (`hoist_groups` → `hoist_arms` → `relax_non_semantic`) that produce **THE codegen grammar** — the shape every generated class's `__grammar__` and every field's `IrBind` positions are computed against. See [[generated-modules]] for the exported form.

---

### `compute_binding(codegen_grammar)` — `compile/pipeline/binding.py`

```python
compute_binding(ast: IrAst) -> list[RuleBinding]
```

The open-table successor of the retired `derive_specs`'s classify/parents/naming jobs. `RuleBinding(rule_name, class_name, parent_class_name, kind, fields: dict[str, IrBind])`, one per rule, parents before subclasses. See [[field-naming]].

---

### `synthesize(codegen_grammar, binding, stem)` — `compile/pipeline/synthesis.py`

```python
synthesize(codegen_grammar: IrAst, binding: list[RuleBinding], stem: str) -> dict[str, type]
```

Builds the model classes **at runtime** via `type(name, bases, ns)` and returns `{class_name: cls}` — no source emit, no import, no `model_rebuild`, no file write. Each class gets `__grammar__` (its rule) and `__binds__` (the slot table) written directly into `ns`, with `__module__`/`__qualname__` set explicitly (`type` would otherwise default `__module__` to this module). MI bases in binding order. Flavour-agnostic (it does not import `lexic.grammars`).

---

### The instance fold — `parsing/fold.py`

There is no `build_instance_parser`/wrapper-rule bridge anymore (`parsing/models.py` is deleted outright). The **one authored instance-fold** is `ModelFold` (2026-07-06; the name is reclaimed — the retired wrapper-rule `ModelFold` in `parsing/models.py` is unrelated): the compile package's `_compile_core` builds a per-rule **IR body-table** (`IrMap[IrRuleRef, ModelBody]`, from the binding view + generated classes — each `ModelBody` carries its model constructor as an `IrLambda` plus structural metadata `kind`/`n_items`/`fields`/`fast`) and constructs `ModelFold(bodies)`. On construction the fold **bakes** every body to the flat-runtime `config: dict[str, RuleFold]` (`.baked`), the record the PDA clone compiler and the engine-fallback `apply` consume unchanged — byte-for-byte identical to the retired plain-data config. The IR body-table is the *same shape* the grammar-text `Reducer` carries its reductions in (a per-rule `IrMap` to `IrSelf` bodies). The instance grammar is `normalize(lift_optional_nullables(codegen_grammar))` — the *same* codegen grammar `synthesize()` built classes against, so `kids[i] ↔ items[i]` and field extraction is positional indexing, not a name lookup against a synthetic wrapper grammar. See [[architecture]]'s "positional fold" section.

---

## `CompiledGrammar`

Returned by `compile_text` / `compile_from_path`. Fields:

| Field | Type | Purpose |
|---|---|---|
| `classes` | `dict[str, type]` | Rule name → synthesized model class (`GrammarModel` subclass) |
| `grammar` | `IrAst` | The **canonical** grammar (what the user's grammar IS — the transpile/re-emit source) |
| `codegen_grammar` | `IrAst` | The post-pass grammar the fold binds against — the engine key `.parse` hands to `parse_model` (the engine memoises its lifted/normalised/PDA/run-collapsed compilation per this grammar's identity) |
| `fold` | `ModelFold` | The one authored instance-fold: an IR body-table (`bodies: IrMap[IrRuleRef, ModelBody]`) that bakes to `config: dict[str, RuleFold]` and folds positionally over `codegen_grammar` |
| `flavour` | `str` | The source flavour's name (drives export docstrings) |
| `stem` | `str` | The grammar stem — the exported module's default identity |
| `tokens` | `TokenBinding` | What this grammar knows about tokens (below) |

### `TokenBinding` — three facts, deliberately separate

`tokens.tokenizer` is the bound **vocabulary**; `tokens.segmented` is whether
the GRAMMAR's terminals reference an encoding; `tokens.unresolved` is the
codegen grammar before its alphabets were resolved to ids.

The first two are independent questions and conflating them is a defect:
`.parse` routes on `segmented`, which is a property of the grammar, so
binding a tokenizer to a char grammar cannot turn it into a token parse (the
additivity invariant, [[invariants]]). A char grammar may legitimately carry
a vocabulary — `constrain()` needs one too.

`tokens.unresolved` exists because resolution is lossy: ordinals are baked
and spellings are gone, so a rebind cannot start from `codegen_grammar`.

`.parse` refuses a grammar whose terminals name an encoding when no
vocabulary is bound — reading and emitting such a grammar needs none, so the
refusal belongs at parse rather than at compile.

### `.bind(tokenizer, registry=None)` — one grammar, many vocabularies

Compiling is per-grammar; a vocabulary is per-deployment. `bind` re-resolves
`tokens.unresolved` and returns a **new** artefact, reusing classes, binding
and fold unchanged — they are invariant under which tokenizer is bound,
because field naming dispatches on the atom TYPE (`IrAlphabet`) and
resolution rewrites only the inner ordinals. Roughly an order of magnitude
cheaper than recompiling, and the ratio grows with grammar size.

New artefact, never a mutation: the engine memoises tables per grammar
identity, and a rebound grammar genuinely *is* a different identity.

On explicit request `export_module(compiled, path, *, stem=None, inline_tables=False)` writes an importable twin module (`export_source` is the string-taker it wraps) — see [[generated-modules]]. `bind_module(grammar, namespace)` is the twin modules' module-end binder.

`.parse(text)` is the only method callers need. It runs `parse_model(self.codegen_grammar, text, self.fold)` — the engine's instance product (PDA-first, Earley completion inside the engine, memoised per `(grammar, fold)` identity). If the start rule does not fold to a `GrammarModel`, `.parse` raises `UnsupportedConstructError`.

**Ambiguity is refused, by both engines.** A span whose derivations build two different models raises `UnsupportedConstructError` rather than one engine quietly picking — the PDA's "first" and Earley's "first" are not the same first, and a parser that answers an ambiguous question is not answering the question asked. The test is about VALUES, not derivation counts: a grammar routinely derives one text several ways without meaning anything by it, and a *split* — one production carved two ways, same arm, different boundary — has a defined answer (the first slot owns the text) and is never refused. Only an *arm* choice, two different productions over one span, is a question the grammar left open.

The opt-out is a **resolver, not a flag**: `parse_model(grammar, text, fold, resolve=...)` takes a deterministic `Resolver`, handed the derivation in hand and the witness that differs, and whatever it returns is the parse. Its behaviour is the caller's concern, not the engine's. The same resolver reaches whichever engine ends up choosing, so the answer does not depend on which route ran. `CompiledGrammar.parse(text, resolve=...)` surfaces it too, and reaches the **token** route as well as the char one — the promise does not depend on whether a grammar's terminals happen to name an encoding.

---

## `GrammarModel`

Every synthesized class subclasses `GrammarModel(IrNamedTuple)` — the record spine ([[decisions]]): a model IS an immutable IR record (walkable, dispatchable, hashable; the tuple surface — iteration, `len`, indexing — is part of the API). Each class carries `__grammar__: ClassVar[IrRule]` — its own rule from the codegen grammar — and an explicit `__binds__` ClassVar table mapping each bound item slot to `(field name, IrBind(item, mode, semantic))`, read through the public `bound_fields()`. `synthesize` writes `__binds__` directly (`type()` build) — no `Annotated` resolution, no `model_rebuild`.

| Method | Returns | Notes |
|---|---|---|
| `to_text()` | `str` | Lossless round-trip to original source text (explicit-stack walk, depth-safe) |
| `to_grammar(flavour="gbnf")` | `str` | Emits the grammar rule for this class — `get_flavour(flavour).apply(self.__grammar__)` |
| `dump()` | `dict` | The native dump: RUNTIME-complete (serializes by each value's own type, never a declared schema — no arm-subtree erasure), field-order keys, tuples re-emitted as lists, explicit-stack (depth-safe) |
| `semantic_dump()` | `dict` | `dump()` minus the receiver's OWN fields whose `IrBind.semantic` is `False` (top-level-only exclusion) |
| `bound_fields()` | `dict[int, (name, IrBind)]` | The slot → field map (classmethod) |
| `children()` / `rebuild(kids)` | | Bound-field values in ITEM order — the IrSelf walk/viz payload |
| `fast_construct()` | `(ctor, defaults)` | Always granted — a record build is one C-level tuple construction |

Equality is type-aware (same concrete class + payload; the `IrBounds` pattern) and hash-consistent. Hand construction (`__new__`) runs IR-intrinsic per-field checked construction raising `FieldValidationError` (charclass membership + bounds, `Literal` membership, model/models `isinstance`, required-presence); an unexpected kwarg still raises `TypeError`. Parse paths (fold/PDA) use trusted construction and bypass the checks. `models`-mode lists coerce to tuples at construction. `to_text()` raises `NotImplementedError` on an abstract alternation class (no fields, no binds) — call it on a concrete subclass instance.

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

`tests/integration/lexic/roundtrip/test_gbnf_ir_equivalence.py` and `test_abnf_ir_equivalence.py` used to compare the engine's grammar parse against the (now-deleted) `MetaGrammarParser`/Lark path — they no longer have a second implementation to diff against. Both are now golden fingerprint tests: every ground-truth/fixture grammar must reduce to an `IrAst` with an expected `(start_rule, rule_names)` fingerprint, unambiguously (`is_ambiguous` is false), and re-emitting through the flavour singleton and re-parsing must preserve that fingerprint. `tests/integration/lexic/roundtrip/test_cross_flavour.py`'s `test_json_gbnf_and_abnf_compile_to_identical_generated_source` goes further for `json.gbnf`/`json.abnf`: it asserts the full **generated module source** is byte-identical (modulo the docstring's content-hashed stem) — the user-visible form of the canonicalization fixpoint `canonicalize(parse(json.gbnf)) == canonicalize(parse(json.abnf)) == JSON_GRAMMAR`.

---

## Which entry point to use

| Situation | Entry point |
|---|---|
| Parse one string against a file on disk | `parse.parse` |
| Grammar is in memory; parse many strings | `compile_text` → `.parse()` |
| Grammar is a file; parse many strings | `compile_from_path` → `.parse()` |
| Inspect the canonical grammar without generating code | `canonical_grammar` |
| Grammar text → raw (not-yet-canonicalized) `IrAst` only (transpile, inspect, re-emit) | `parse_grammar` |
| Write a compiled grammar as an importable twin | `export_module` |
| Write a PARSED VALUE as an importable module | `export_value` |
