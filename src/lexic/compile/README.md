# `lexic.compile` — the compilation subsystem

`compile` turns grammar text into one of two first-class products, and is the
**sole runtime seam onto the parse engine** (`lexic.parsing`). The premise: a
canonical `IrAst` already describes everything a grammar is, so compilation is
a chain of `IrAst → IrAst` passes ending in either runtime-built classes or
pure IR — no source generation, no import machinery, no third-party model
library.

**One subsystem, two products:**

- **Compiled models** — `compile_text` / `compile_from_path` return a
  `CompiledGrammar` whose model classes are synthesized **at runtime** on the
  `IrNamedTuple` record spine (`type(name, bases, ns)`). No `.py` is emitted,
  imported, or `model_rebuild`-ed; a model *is* a walkable IR record.
- **Pure IR** — `parse_grammar` (grammar text → `IrAst`), `load_ir` (a neutral
  no-`exec` text notation → real IR objects), and `load_flavour`
  (`compile.loader`) (a text manifest → a whole `IrFlavour`).

Only `compile/__init__.py` is importable from outside the package. Every other
runtime module reaches compile through `from lexic.compile import ...`; the
passes / binding / synthesis / notation / loader / export submodules are
internal. This, and the engine-seam rule, are enforced by
`tests/integration/test_layering_invariants.py`.

```
grammar text
   ├─ _scan_directives ─────────────► (start, non_semantic)          [private helper]
   └─ parse_grammar ───────────────► IrAst
            └─ canonicalize ────────► canonical IrAst                 [ir/canonical.py]
                  = canonical_grammar()   (start bound, noise flagged semantic=False)
                        └─ build_codegen_grammar ─► THE codegen grammar
                              ├─ compute_binding ──► list[RuleMap]
                              ├─ synthesize ───────► dict[str, type]   (type() build, NO file)
                              └─ register_model ───────► the bound product (lowered + verified)
   ⇒ CompiledGrammar(classes, grammar, codegen_grammar, product)
        .parse(text) = parse_model(codegen_grammar, text, product)    [engine product]
```

## 1. Public API (`__init__.py`)

| Callable | Returns | Meaning |
|---|---|---|
| `compile_text(text, *, cache_key=None, flavour="gbnf")` | `CompiledGrammar` | String-in. Content-memoised by `(sha stem, flavour)`; `cache_key` prepends an extra prefix. |
| `compile_from_path(path, *, flavour=None)` | `CompiledGrammar` | Path-in; flavour inferred from the extension. Memoised by `(path, mtime, size, flavour)`, `path.stem` as the class-module stem. |
| `canonical_grammar(text, flavour, *, non_semantic_rules=None, start=None)` | `IrAst` | The **front half**: parse + canonicalize + directive flags → canonical, semantic-flagged `IrAst`. `generate.py` and transpilers build on this without making classes. |
| `parse_grammar(text, flavour)` | `IrAst` | The grammar-text → IR seam; compiles the flavour's self-grammar and calls its artefact's `reduce`. Returns the raw (pre-canonicalize) `IrAst`, with dangling refs into the flavour's `core_rules` prelude resolved. |
| `load_ir(text)` / `load_ir_from_path(path)` | `IrSelf` | Real IR objects from the IR-constructor notation (§4). |
| `reset_cache_for_tests()` | — | Clear the content/path memo when a caller needs fresh class objects. |

`load_flavour(text)` / `load_flavour_from_path(path)` live in
`lexic.compile.notation.loader`; `export_source(compiled)` /
`export_module(compiled, path)` in `lexic.compile.module.export`;
`parse_module` / `verify_module` in `lexic.compile.module.selfgrammar` —
all re-exported at the package root.

`CompiledGrammar(classes, grammar, codegen_grammar, fold)` — `.parse(text)`
runs the engine's sole `parse_model` product and `.reduce(text, reducer)` parses a
reducer-derived pruned variant. The model route is
PDA-first (with Earley completion inside the engine) and returns the start rule's
`GrammarModel`, or raises `UnsupportedConstructError` if the start rule does
not fold to one. `grammar` is the canonical AST (the transpile/re-emit
source); `codegen_grammar` is the post-pass grammar the fold binds against and
the engine memoises its compilation on.

## 2. The design: passes in, classes out, no codegen module

Compilation is `IrAst → IrAst` passes then a `type()` build. **`build_codegen_grammar`**
(`passes.py`) applies three language-preserving passes — `hoist_groups`
(quantified ref-bearing groups → named helper rules), `hoist_arms` (every
non-trivial alternation arm → its own `<rule>-arm<N>` rule, restoring the
single-arm premise the positional fold rests on), and `relax_non_semantic`
(min=0 on refs to `semantic=False` rules) — producing **THE codegen grammar**,
the one `IrAst` every class's `__grammar__` and every field's slot is computed
against. **`synthesize`** (`synthesis.py`) then builds each class with
`type(class_name, bases, ns)`, writing `__grammar__` (its rule) and `__binds__`
(the slot → `(field, IrBind)` table) directly into `ns`, with
`__module__`/`__qualname__` set explicitly and MI bases in binding order. No
annotation resolution runs at runtime; the record spine (`lexic.model`) reads
`__binds__` directly.

## 3. Package layout

```
compile/
  __init__.py    the public API (§1); the engine seam, the memo, the
                 core-rules prelude resolution (parse_grammar appends a
                 flavour core rule iff referenced-but-undefined)
  artifact.py    CompiledGrammar — the parse-ready artefact
  foldkit.py     shared authored-fold vocabulary (ALT, passthrough)
  pipeline/      grammar → classes (see its README)
    passes.py      build_codegen_grammar — hoist_groups → hoist_arms →
                   relax_non_semantic
    binding.py     compute_binding → list[RuleMap]; kind classification;
                   field naming; the open supplied-class contract (§5)
    synthesis.py   synthesize(codegen_grammar, binding, stem) → dict[str, type]
  notation/      the IR-constructor notation (see its README)
    parse.py       load_ir — text → real IR objects (§4)
    emit.py        emit_ir — IR → notation text over the layout algebra
    loader.py      load_flavour — a text manifest → IrFlavour (§6)
  module/        the twin-module surface (see its README)
    export.py      export_source / export_module — the importable twin (§7)
    selfgrammar.py parse_module / verify_module — lexic parses its own exports
```

Layering: the package reads/writes `lexic.ir`, imports `lexic.grammars` (to
resolve flavours) and the engine — `lexic.parsing` (root: `parse_model`,
the fold toolkit) plus the one licensed submodule
`lexic.parsing.earley.reduce` (the `DROP`/`KEEP_REDUCED`/`YIELD` sentinels).
Nothing reaches past that surface.

## 4. The binding view and the open table (`binding.py`)

`compute_binding` returns one `RuleMap(rule_name, class_name,
parent_class_names, kind, fields)` per rule, parents before subclasses.
`classify_rule` derives the `kind` fresh from the codegen grammar:

- **`value_str`** — no `IrRuleRef` anywhere in the body; one implicit `value`
  field (a pure-literal alternation types as `Literal[...]`).
- **`alternation`** — after `hoist_arms`, a field-less pass-through; the
  matched arm's sub-model identifies itself.
- **`sequence`** — concrete; fields come from the single sequence arm, each an
  `IrBind(item, mode, semantic)` (`mode ∈ text/gtext/model/models`).

A rule's construction is authored, not supplied: `model_plan` derives one
`RecordConstructor` per constructing rule from the binding view, naming the
generated class, the keyword each capture fills, which may be absent, and
whether validation may be skipped. There is one channel — an authored surface
writes its own `AuthoredRule` table, and the generated model writes its own
from the view.

Field naming is a three-tier cascade (rule-ref name → pattern library →
positional), and reserved names mangle with a trailing `_`: field names in
`_RESERVED_FIELD_NAMES` (keywords ∪ the record-spine protocol surface ∪
`GrammarModel`'s methods) and class names in `_RESERVED_CLASS_NAMES` (the
names the exporter's header binds), both drift-pinned by tests. See
[`.wiki/lexic/field-naming.md`](../../../.wiki/lexic/field-naming.md).

## 5. The IR-constructor notation (`notation/parse.py`)

`load_ir(text)` parses a neutral text notation into **real IR objects** —
`IrLiteral`, `IrRule`, `IrAst`, … — through the same fold machinery that builds
user models. It is one generic-apply grammar (`value ::= name-call | str |
int`, positional `SYMBOLS[name](*args)`) plus a curated **`SYMBOLS`
whitelist** — every public `IrSelf` subclass, plus fixed extras
(`IrNone`/`YIELD`/`True`/`False`/…). That whitelist **is** the no-`exec`
boundary and the open-vocabulary registry: a new IR node is one entry, zero
grammar change; nothing outside it can be constructed. String decode is
structural (one rule per escape kind), `INTERN` maps `Yield()` to the singleton
`YIELD`, and a `#` line comment is a `semantic=False` noise rule so notation
files (and manifests) get comments for free. The round-trip fixpoint —
`load_ir(repr(node)) == node` over the whole node vocabulary — is the gate.

## 6. The manifest loader (`notation/loader.py`)

`load_flavour(text)` folds a manifest — one notation `IrMap` of seven strict
sections (identity, escapes-as-IR-dyads, grammar, reductions, actions) — into a
synthesized `IrFlavour`. It **derives** the reducer noise map and `literal=DROP`
from the grammar's own `semantic=False` flags (the loader owns reducer policy;
manifests carry no noise section), lowers the escape dyads to an `EscapeCodec`,
and builds the `Reducer`. A flavour whose noise policy is not purely derivable
is not manifest-loadable — a named format rule, rejected with
`UnsupportedConstructError`. Shipped flavours stay authored; the manifests are
their conformance twins.

## 7. The twin-module surface (`module/`)

`export_source(compiled)` renders a compiled grammar as an **importable twin
module** in the record-spine syntax (`GrammarModel` subclasses with typed
defaults-last fields; `GRAMMAR` in the notation via `emit_ir`; a module-end
`attach_module` call, or inline `__grammar__`/`__binds__` ClassVars under
`inline_tables=True`). It reprs only pure grammar-AST records — **never** a
`Reducer` or a flavour's noise map. Formatting is `lexic.ir.layout` — no
`ruff`, no subprocess — and a fresh export is an isort + ruff-format
**fixpoint**. Files are written only on the explicit `export_module` path.
Always-on gates: `ast.parse` + `load_ir(GRAMMAR) == compiled.grammar`.

`selfgrammar.py` closes the loop at file granularity: `parse_module(text)`
parses an exported twin through a grammar of generated modules, and
`verify_module(compiled, text)` cross-checks the parse against the binding
view with the same renderers the exporter used.

## 8. Invariants

- **Grammar is canonical.** Every product derives from the same canonical
  `IrAst`; every model has a lossless `to_grammar(flavour)` path.
- **No source emit on the compile path.** Classes are `type()`-built in
  memory; no file write, no import, no `model_rebuild`, no subprocess —
  `export_module` is the sole, explicit write seam.
- **The package is the sole engine seam.** Only `__init__.py` is importable
  from outside; the engine is reached only through it.
- **No `exec`/`eval`.** The notation's `SYMBOLS` whitelist is the closed
  construction boundary; every dispatch table raises
  `UnsupportedConstructError` on an unknown construct — never a silent
  fallback.

See [`.wiki/lexic/public-api.md`](../../../.wiki/lexic/public-api.md),
[`.wiki/lexic/architecture.md`](../../../.wiki/lexic/architecture.md),
[`.wiki/lexic/field-naming.md`](../../../.wiki/lexic/field-naming.md).
