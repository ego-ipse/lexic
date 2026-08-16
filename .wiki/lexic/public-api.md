# Public API

**When to load:** writing docs, examples, or integration tests; choosing between `parse_instance`, `compile_text`, `compile_from_path`, `compile_ast`, `canonical_grammar`, `parse_grammar`, `export_module`; understanding `CompiledGrammar` fields or `GrammarModel` methods; reaching the engine floor (`lexic.parsing` root exports).

How callers use Lexic. The stable surface lives in the `compile/` package and `model.py`. Both grammar-text parsing and generated-instance parsing run on the same engine (`lexic.parsing` — PDA-first, Earley completion); there is no Lark and no `RuleSpec` anywhere in the call path. NOTE: `parse` is the ENGINE's name (`lexic.parsing.parse` → a raw `ParseTree`); the compile-side one-liners are `parse_instance`/`parse_instance_from_path`.

**The seam is this page.** Every symbol documented below with a `compile/` home is in `lexic.compile.__all__`, and the heading names the module you IMPORT it from — always `compile/__init__.py`, because outside the package only the root is importable ([[architecture]]). Reachable-but-unlisted was how `export_value` ended up documented as public with a deep import as its only route. `tests/integration/lexic/invariants/test_public_api_drift.py` gates both halves.

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

`flavour` defaults to `"gbnf"` and takes **a name or a live `IrFlavour` instance**. An instance is used directly and never touches the registry: a loaded session manifest (`load_flavour`) compiles without `register_flavour`, and the shipped singleton under the same name is not shadowed. The artefact still records the plain name string (`cg.flavour == type(instance).name`).

**Memoised by content by default**: the default cache key is `(content sha stem, flavour key)` — compiling the same source in the same flavour returns the cached `CompiledGrammar` and its class objects. A flavour NAME keys by itself; an INSTANCE keys by its class object (flavour value equality is not a designed key in either direction; the class object is identity-stable and pinned live by the cache entry, so it can never be reused the way an `id()` can — the cost is that two loads of one manifest compile twice). Pass `cache_key=` to prepend an extra key prefix; `reset_cache_for_tests()` clears the cache when a caller needs fresh class objects. Classes are synthesized in memory (`type()`) — there is no output directory to key on.

---

### `compile_from_path(path, *, flavour, vocabulary, directives)` — `compile/__init__.py`

Like `compile_text` but reads the file and memoises by `(path, mtime, size, flavour key, vocabulary, directives)`, using `path.stem` as the class-module stem. Flavour is inferred from the file extension if omitted, and may be a name or an instance. Carries `compile_text`'s whole surface.

---

### `compile_ast(ast, *, cache_key, vocabulary, directives)` — `compile/__init__.py`

The **IR-born twin** of `compile_text` — the entry for a grammar that never had text: authored natively in IR (`grammars/json.py`'s way), or loaded through the notation (`load_ir`). The text route's front half is skipped, not emulated: emitting IR through a flavour and recompiling that text is **lossy** — `semantic=False` flags vanish with the comments — and can only spell what the chosen flavour can spell.

The given AST need not be canonical; it is canonicalized as it stands and its rules' own `semantic` flags survive. Start and flags resolve from the AST itself with `directives` overriding (the text route's precedence: `directives.start` beats `ast.start` beats first rule; `directives.non_semantic` REPLACES the rules' flags when given, `None` keeps them).

Memoised like the text twin with `repr(ast)` as the content: repr is codegen-exact, so the key distinguishes what AST equality deliberately ignores (the `semantic` flags — two flag-twins that compare `==` get distinct artefacts). The artefact's `flavour` is `"ir"`; `to_grammar` still takes its target flavour explicitly.

```python
from lexic.compile import compile_ast
from lexic.grammars.json import JSON_GRAMMAR

cg = compile_ast(JSON_GRAMMAR)          # no text, no emit round-trip
```

---

### `export_value(value, path, *, module=None)` — `compile/__init__.py`

Imported from `lexic.compile` like every other entry — the package root is the
only route in (implemented in `compile/payload/export.py`; reaching a compile
submodule from outside the package is a layering violation, [[architecture]]).

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

### `transpile(source, target, rules)` — `compile/__init__.py`

Implemented in `compile/transpile.py`, imported from `lexic.compile`.

Builds a retained `Transpiler(source, target, walk)` — a document under grammar A re-expressed under grammar B, on the model plane. `rules: IrMap` keys **A's rule names** to bodies authored in the transpile vocabulary — `Make(rule, args=IrNone)` (IrBuild's contract with the class replaced by a target rule name; bare `Make` splats the transformed children, slot-order-bound through `__binds__`; aimed at a hoisted list rule it grows the chain from a flat tuple), `Spelled()` (the focus's `to_text()` as algebra), `Flat()`/`Split()` (hoisted lists: channel→flat, chain→flat), `Is(rule)` (focus-type test by name) — beside the ordinary ir/ algebra (`IrArg`/`IrPipe`/`IrEach`/`IrCond`/`IrRaise`). The bake resolves names against the two artifacts, so **an authored table contains no class objects**: it is pure data, travels through the notation (repr-fixpoint contract — `Spelled`/`Flat`/`Split` are singletons; `IrThis` etc. remain identity-eq), and one table serves every formulation of the source language (rows name canonical rules — the same table bakes against `json.gbnf` and `json.abnf`).

`Transpiler.cross(text, resolve=None) -> Crossing` is the whole path WITH the correspondences it computed — both sides' addressed emissions (`IrEmission`) and the `IrOrigins` between them — and `run` is that, keeping only `product.text`, so the two cannot drift. The correspondence is **object-level**, because `IrBottomUp` transforms a shared object once and splices: the crossing emits one `IrOrigin` per (built occurrence, source occurrence) pair the object map licenses, so a source value standing in one place gives one entry and one standing in several gives one each. `Crossing.sources_of(address)` returns that set; an empty set means the table BUILT that model inside a body rather than transforming a source node. Nothing is picked from a set — the multiplicity is the answer.

`IrBottomUp` drives (children first, results on `nc`); unnamed rules pass through; every intermediate rebuild threads through checked construction (`FieldValidationError` is the transform's type system). `Transpiler.apply(model)` gates **completeness** (no source class may survive into the product — a hole is refused with the class named); `Transpiler.run(text, resolve=None)` adds **membership and fidelity** (the emitted text parses under the target, back EQUAL to the models the transform built). `getting_started/ex16` (json→yaml, zero functions) and `ex17` (python→c++, exactly one — the declaration pass) are the worked forms; `tests/integration/lexic/roundtrip/test_transpile_documents.py` pins the formulation-independence and the generate-driven bulk witness. The templating precedent's shape: bake once, run many.

---

### `Verdict` — `compile/__init__.py`

Implemented in `compile/verdict.py`. An attempt through this seam ends with a product or a raised `LexicError`, and an exception is not a value — it cannot be held beside three others, compared, or drawn. `Verdict` is that missing half: `accepted: bool`, `words: str` (the engine's message VERBATIM — never re-worded, because a caller comparing two refusals is comparing what the engine said), `readout: Refusal` (a parse refusal's position/expected set; the default `Refusal()` with `pos == -1` is the honest empty), `seconds: float` (what the attempt cost, as its caller measured it).

Two named constructors: `Verdict.accept(seconds)`, and `Verdict.refuse(error, seconds)` — the one from a raised error, lifting the readout when the error carries one. Deliberately absent: the attempt itself, and any notion of WHICH candidates to try, in what order, memoised how. That is caller-side policy, and a registry of "the readers we happen to ship" would privilege the formulations lexic happens to carry.

---

### `present(compiled, rows)` — `compile/__init__.py`

Implemented in `compile/presentation.py`. Bakes a **presentation ceiling**: rows keyed by the grammar's own CANONICAL rule names, bodies of ordinary IR algebra whose product is a `Row(role, address, span, parts)`. `Presentation.apply(model) -> Rows` draws a parsed document — the walk IS `emit_addressed()`'s, so a row and an extent name one occurrence with one record and co-selection needs no translation.

**No geometry, anywhere.** A row says what stands WHERE IN THE DOCUMENT — an `IrAddress` and an `IrSpan`, nothing else. Arranging that on a surface belongs to whatever draws it; a record carrying a width would be lexic guessing at a screen it cannot see.

**Declare one name, derive the rest.** Codegen helper rules (`array-item`, `char-arm2` — minted by `passes.py`, never a contract anyone authored against) carry no rows: their occurrences route to the canonical rule they were hoisted out of, derived by walking the codegen grammar's refs against the canonical one (both are moments of the same compilation, so neither is recomputed to ask).

**Two gates say where a ceiling applies.** *Membership*: every row names a drawable rule. *Completeness*: every drawable rule has a row — the semantic ones that are not pass-through alternations, since noise draws nothing and an alternation's arm is the value that stands. A hole is refused with the missing rules named: a gate-failing table is a refused offer, never a partial ceiling.

**It travels.** Through the notation (`load_ir(repr(table), symbols={"Draw": Draw})`), and across a pure renaming through `IrRenaming.rekeyed(table)` — the alignment witness re-keys any rule-keyed table, so one ceiling serves every renaming of its grammar. A differently-FACTORED grammar is a real difference and refuses. Demonstrated on three languages in `tests/integration/lexic/codegen/test_presentation.py`: `markdown.gbnf`, `json.gbnf`, and `arithmetic.abnf`.

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

### `build_codegen_grammar(ast)` — `compile/__init__.py`

```python
build_codegen_grammar(ast: IrAst) -> IrAst
```

Implemented in `compile/pipeline/moments.py`, imported from `lexic.compile`.

Takes the canonical grammar and applies the three codegen-only passes (`hoist_groups` → `hoist_arms` → `relax_non_semantic`) that produce **THE codegen grammar** — the shape every generated class's `__grammar__` and every field's `IrBind` positions are computed against. It is `GrammarMoments.of(ast).relaxed`: the fused form and the retained one are one composition, so they cannot drift. See [[generated-modules]] for the exported form.

---

### `CompileMoments` / `GrammarMoments` — `compile/__init__.py`

Implemented in `compile/pipeline/moments.py`. The retaining product the compile pipeline itself runs through — `_assemble_core` builds one and reads the artefact out of it, so `CompiledGrammar.moments` is what the compilation DID rather than a re-run of it.

```python
GrammarMoments(canonical, grouped, armed, relaxed, resolved)   # five IrAst states, in order
CompileMoments(grammar, binding, classes)                      # + the binding view and the classes
```

The record IS the sequence, so two adjacent stages are two adjacent fields (`GRAMMAR_MOMENTS` names them in order). `resolved` is `relaxed` itself unless a vocabulary was bound; `binding` reads `resolved` while synthesis reads `relaxed`, because a vocabulary is a lens for matching and a class's own `__grammar__` must not carry baked ordinals.

Retention is a tuple of references to values the pipeline computed anyway — a caller that never asks pays nothing. `CompiledGrammar.bind` rebuilds only the last grammar moment, which is exactly what its invariance argument claims.

**A no-op moment is a fact.** `GrammarMoments.no_ops()` names the stages that ran and changed nothing, because that is grammar-contingent rather than exceptional: `chess.gbnf` has one pass of three that does anything, `c.gbnf` declares `@non-semantic ws` and relaxes nothing (its `ws` is not nullable, and relaxing there would widen the language), and `list.gbnf` passes through the whole pipeline untouched. A consumer draws "this stage did nothing" instead of silently skipping a stage that ran.

---

### `compute_binding(codegen_grammar)` — `compile/__init__.py`

```python
compute_binding(ast: IrAst) -> list[RuleBinding]
```

Implemented in `compile/pipeline/binding.py`, imported from `lexic.compile`.

The open-table successor of the retired `derive_specs`'s classify/parents/naming jobs. `RuleBinding(rule_name, class_name, parent_class_name, kind, fields: dict[str, IrBind])`, one per rule, parents before subclasses — `RuleBinding` is exported beside it, since the returned list cannot be typed without it. See [[field-naming]].

---

### `synthesize(codegen_grammar, binding, stem)` — `compile/__init__.py`

```python
synthesize(codegen_grammar: IrAst, binding: list[RuleBinding], stem: str) -> dict[str, type]
```

Implemented in `compile/pipeline/synthesis.py`, imported from `lexic.compile`.

Builds the model classes **at runtime** via `type(name, bases, ns)` and returns `{class_name: cls}` — no source emit, no import, no `model_rebuild`, no file write. Each class gets `__grammar__` (its rule) and `__binds__` (the slot table) written directly into `ns`, with `__module__`/`__qualname__` set explicitly (`type` would otherwise default `__module__` to this module). MI bases in binding order. Flavour-agnostic (it does not import `lexic.grammars`).

---

### The instance fold — `parsing/fold.py`

There is no `build_instance_parser`/wrapper-rule bridge anymore (`parsing/models.py` is deleted outright). The **one authored instance-fold** is `ModelFold` (2026-07-06; the name is reclaimed — the retired wrapper-rule `ModelFold` in `parsing/models.py` is unrelated): the compile package's `_compile_core` builds a per-rule **IR body-table** (`IrMap[IrRuleRef, ModelBody]`, from the binding view + generated classes — each `ModelBody` carries its model constructor as an `IrLambda` plus structural metadata `kind`/`n_items`/`fields`/`fast`) and constructs `ModelFold(bodies)`. On construction the fold **bakes** every body to the flat-runtime `config: dict[str, RuleFold]` (`.baked`), the record the PDA clone compiler and the engine-fallback `apply` consume unchanged — byte-for-byte identical to the retired plain-data config. The IR body-table is the *same shape* the grammar-text `Reducer` carries its reductions in (a per-rule `IrMap` to `IrSelf` bodies). The instance grammar is `normalize(lift_optional_nullables(codegen_grammar))` — the *same* codegen grammar `synthesize()` built classes against, so `kids[i] ↔ items[i]` and field extraction is positional indexing, not a name lookup against a synthetic wrapper grammar. See [[architecture]]'s "positional fold" section.

---

## `CompiledGrammar`

Returned by `compile_text` / `compile_from_path`. Fields:

| Field | Type | Purpose |
|---|---|---|
| `grammar` | `IrAst` | The **canonical** grammar (what the user's grammar IS — the transpile/re-emit source) |
| `fold` | `ModelFold` | The one authored instance-fold: an IR body-table (`bodies: IrMap[IrRuleRef, ModelBody]`) that bakes to `config: dict[str, RuleFold]` and folds positionally over `codegen_grammar` |
| `moments` | `CompileMoments` | Every stage the compilation passed through (above) — the artefact is BUILT from it, not beside it |
| `classes` | `dict[str, type]` | Rule name → synthesized model class (`GrammarModel` subclass). A read of `moments.classes`: two copies of one answer is a drift surface |
| `codegen_grammar` | `IrAst` | The post-pass grammar the fold binds against — the engine key `.parse` hands to `parse_model` (the engine memoises its lifted/normalised/PDA/run-collapsed compilation per this grammar's identity). A read of `moments.grammar.resolved` |
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

### `.pda_tables()` — the predictive half, memo-hot

Returns the engine's compiled `PdaTables` for `(codegen_grammar, fold)` — the trace substrate a `PdaKernel` subclass runs over. The artefact holds the exact objects the engine's instance-product memo is keyed by (identity), so the tables returned are the very ones `.parse` drives: hot if this grammar has parsed already, compiled once and shared forward if not.

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
| `emit_addressed()` | `IrEmission` | `to_text()`'s text PLUS one `IrExtent` (address ↔ span) per emitted part — the addressed twin, over the same `emit_parts` stream |
| `occurrence(address)` | model / `str` / tuple | The part standing at an address — positional resolution, never by value |
| `to_grammar(flavour="gbnf")` | `str` | Emits the grammar rule for this class — `get_flavour(flavour).apply(self.__grammar__)` |
| `dump()` | `dict` | The native dump: RUNTIME-complete (serializes by each value's own type, never a declared schema — no arm-subtree erasure), field-order keys, tuples re-emitted as lists, explicit-stack (depth-safe) |
| `semantic_dump()` | `dict` | `dump()` minus the receiver's OWN fields whose `IrBind.semantic` is `False` (top-level-only exclusion) |
| `bound_fields()` | `dict[int, (name, IrBind)]` | The slot → field map (classmethod) |
| `children()` / `rebuild(kids)` | | Bound-field values in ITEM order — the IrSelf walk/viz payload |
| `fast_construct()` | `(ctor, defaults)` | Always granted — a record build is one C-level tuple construction |

Equality is type-aware (same concrete class + payload; the `IrBounds` pattern) and hash-consistent. Hand construction (`__new__`) runs IR-intrinsic per-field checked construction raising `FieldValidationError` (charclass membership + bounds, `Literal` membership, model/models `isinstance`, required-presence); an unexpected kwarg still raises `TypeError`. Parse paths (fold/PDA) use trusted construction and bypass the checks. `models`-mode lists coerce to tuples at construction. `to_text()` raises `NotImplementedError` on an abstract alternation class (no fields, no binds) — call it on a concrete subclass instance.

---

## The engine floor — `lexic.parsing` root exports

The engine's public root carries, beside the products (`parse_reduced` / `parse_model` / `token_model`) and the Earley toolkit (`Kernel`, `compile_tables`, `normalize`, `lift_optional_nullables`, the tree/forest readers):

- **`earley_model` / `earley_reduce`** — the per-product Earley completions, public as the route-forcing seam. Forcing an engine route means calling a different product entry, never passing a flag: an engine selector chooses between `parse_model` (PDA-first) and `earley_model` (Earley only).
- **`PdaKernel`** — the fused predictive runtime, subclassable for tracing; `WatchedKernel` is that subclass.
- **`watch(tables, text, fold, *, cap, resolve)` → `WatchedRun`** — the watched run: an ordered `Trace` of `TraceEvent(order, kind, rule, verdict, span)`, where `kind` is one of `TRACE_KINDS` (`scan` / `probe` / `rollback` / `gate`) and `span` is an `IrSpan` — the SAME record an emission's extents carry, so a trace row and a document occurrence co-select without translation. **Pay to watch**: watching re-executes the parse, and the product carries no model precisely so the re-run cannot be confused with the parse a caller already holds. It carries `cap`/`capped` instead (a truncated account says so) and `derived` — a refused predictive run is ordinary (the compile seam retries on the gated engine) and comes back as a stream ending in the refusal rather than as an exception. The unwatched path pays nothing: the instrumentation is a subclass, nothing under `parsing/pda/` imports it, and a unit gate reads `PdaKernel`'s own code objects to prove no method of it so much as names the watch.
- **`GrammarAnalysis`** — the decision taxonomy (verdicts, gate specs) the analysis produces per grammar.
- **`pda_tables(grammar, fold, bits=...)` / `PdaTables`** — the compiled predictive tables, identity-memoised with the parse path; `CompiledGrammar.pda_tables()` is the artefact-side reach onto the same memo entry.

There is deliberately no `lexic.parsing.pda` façade — the PDA names surface at the parsing root beside `Kernel`.

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
| Parse one string, one-off | `parse_instance` / `parse_instance_from_path` |
| Grammar is in memory; parse many strings | `compile_text` → `.parse()` |
| Grammar is a file; parse many strings | `compile_from_path` → `.parse()` |
| Grammar is an `IrAst` (native IR, notation-loaded) | `compile_ast` → `.parse()` |
| Compile with a session flavour, registry-free | `compile_text(..., flavour=<IrFlavour instance>)` |
| Inspect the canonical grammar without generating code | `canonical_grammar` |
| Grammar text → raw (not-yet-canonicalized) `IrAst` only (transpile, inspect, re-emit) | `parse_grammar` |
| Force the Earley route / trace the PDA | `earley_model` / `earley_reduce`; `PdaKernel` over `.pda_tables()` |
| Write a compiled grammar as an importable twin | `export_module` |
| Write a PARSED VALUE as an importable module | `export_value` |
