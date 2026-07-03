# Architecture

**When to load:** checking import legality; adding a module or package; understanding pipeline flow; the two deliberate runtime→codegen exceptions; understanding the IR substrate (dispatch / actions / presets).

See also: [[ir-shapes]], [[flavour-system]], [[error-vocabulary]], [[decisions]]

## The one-sentence version

Grammar text → `IrAst` → `list[RuleSpec]` → generated Pydantic classes. Grammar is the ground truth; classes are its Python representation. Every transformation — parsing, derive, codegen, flavour emission — is expressed in the same **action-driven IR substrate**, including grammar parsing itself: `lexic.parsing` is a native Earley engine that parses `IrAst`-shaped grammars, not a wrapper around a third-party parser generator.

## Pipeline (single, post-cutover — Lark is gone)

```
grammar text
  ├─► compile._scan_directives (private helper)  (start, non_semantic) tuple
  └─► parse_reduced(normalize(flavour.grammar),  IrAst
        text, flavour.reducer)                    (lexic.parsing engine + flavour's own self-grammar/reducer)
        └─► ir/derive.py                         list[RuleSpec]
              ├─► codegen(specs, stem)                    → generated/<stem>.py + dict[str, type]
              ├─► flavour_singleton.apply(node)            → grammar text
              └─► parsing/models.build_instance_parser(specs, classes, start_rule)
                    → (IrAst instance grammar, ModelFold)
```

Each flavour (`GBNF_FLAVOUR`, `ABNF_FLAVOUR`) carries its own self-grammar as raw `IrAst` (`flavour.grammar`) and a `Reducer` (`flavour.reducer`) that folds a parse of grammar *text* back into `IrAst`. `compile_grammar` normalizes and memoises `flavour.grammar` once per flavour name (`compile.py`'s `_NORM_GRAMMAR_CACHE`), then calls `lexic.parsing.parse_reduced` — the same Earley engine that later parses *instances* of the derived grammar.

Entry points in `compile.py`:

- `compile_text(text, *, cache_key=None, flavour="gbnf")` — string-in.
- `compile_from_path(path, *, flavour=None)` — path-in (flavour inferred from extension).
- `compile_grammar(text, flavour, *, non_semantic_rules=None, start=None)` — lower-level: text → `(start_rule, list[RuleSpec])`.

Both `compile_text` / `compile_from_path` return `CompiledGrammar(classes, specs, grammar, fold)` — no `lark.Lark` parser, no `lark.Transformer`. `grammar: IrAst` is the Earley-normalised *instance* grammar (kept so the engine's identity-memoised `compile_tables` stays hot across repeated `.parse()` calls); `fold: ModelFold` folds a `ParseTree` into model instances. `compile_from_path` uses `path.stem` as the generated module name; `compile_text` uses `anon_<sha1>`. See [[public-api]] for the full `CompiledGrammar` contract.

## The IR substrate

Every node — grammar AST, action algebra, dispatcher, and the Earley engine's own state objects — descends from `IrSelf`. Every node is callable: `node(d, n, nc) -> Ir_co`. The substrate has four pieces.

### 1. `IrSelf` mixin + `IrNode` generic (`ir/base.py`)

`IrSelf[Ir_co: IrSelf]` is the identity mixin (moved to `ir/base.py`; `ir/nodes.py` now holds only the grammar-AST node types built on top of it). It supplies a default `__call__` that returns `self` (PEP 673 `Self`) and an `eval(d, n, nc) -> Ir_co` protocol method. Value-producing nodes override `eval`. `IrNode` is a generic, frozen-dataclass ABC: every grammar AST node and every action node descends from it.

### 2. Action-algebra nodes (`ir/action.py`)

Operations the AST nodes don't cover:

- **`IrField(name)`** — read a typed attribute from `n` and wrap via the bound (`IrStr` by default).
- **`IrCallable(handler)`** — procedural escape hatch; `handler(d, n, nc) -> Ir_co`.
- **`IrChild(name)` / `IrChildren(name)`** — sibling lookup. Hybrid behaviour: when `nc` is populated (caller pre-walked), index/return it directly; when `nc` is empty, the lookup is lazy — `IrChild` resolves the named child from `n` and dispatches via `d.eval(d, child, IrTuple())`; `IrChildren` validates the name against `n._items_attr` and dispatches each item.
- **`IrConcat(parts)`** — evaluate `parts` in order, join via the bound's neutral element.
- **`IrJoin(parts, separator, empty)`** — variable-arity join with separator and empty-fallback.
- **`IrCond(test, then_op, else_op)`** — branch on `test.eval(d, n, nc)` (truthy → `then_op`).
- **`IrAction(target_type, body)`** — binds an IR-node type to a callable IR body. `target_type` is metadata excluded from `_child_attrs`; `body` is the dispatched child.

Default bodies: `IrPass` (no-op → `IrNone`), `IrWalk` (visit children, discard), `IrRaise` (raise on unmatched), `IrEmit` (`IrLiteral(str(n))`), `IrRebuild` (walk + reconstruct).

### 3. Dispatcher (`ir/walk.py`)

`IrDispatch[Iri, Ir_co]` carries `actions: IrTypeMap` (an `IrMap`-family type→`IrAction` table with concrete-first MRO resolution, from `ir/mapping.py`) and a `default: IrSelf`. Two seams:

- `dispatcher.eval(d, n, nc)` — protocol-shaped (used internally by action bodies).
- `dispatcher.apply(root)` — friendly entry; seeds `d = self`, `nc = IrTuple()`, and catches `IrReturn` to surface `.value`.

**Critical:** `IrDispatch` does **not** walk children automatically. Action bodies own recursion — typically by calling `d.eval(d, child, ())` themselves or by reading already-dispatched `nc`.

### 4. Presets

Three named subclasses configure the dispatcher's default:

| Preset | `Ir_co` | Default body |
|---|---|---|
| `IrVisitor` | `IrSelf` | `IrWalk()` — side effects, recurses, returns `IrNone` |
| `IrTransformer` | `IrNode` | `IrRebuild()` — walks and reconstructs |
| `IrEmitter[IrLiteral]` | `IrLiteral` | `IrEmit()` — `IrLiteral(str(n))` |

`IrFlavour` (`ir/flavour.py`) IS-AN `IrEmitter` — the emit half of a flavour is exactly this dispatcher; the parse half is a `Reducer` (`lexic.parsing.reduce.Reducer`, IS-AN `IrDispatch`), driven the other direction by the engine.

## Grammar parsing is the same engine as instance parsing

Before the cutover, grammar *text* → `IrAst` ran through Lark (`MetaGrammarParser` + a per-flavour Lark meta-grammar string), and generated-instance parsing ran through a second, separately-built Lark parser + transformer. Both are gone. `src/lexic/parsing/` is a single native Earley engine (SPPF-based, Scott 2008) that both paths share:

- **Grammar parsing:** `flavour.grammar` (an `IrAst` authored directly, not derived from any string grammar) + `flavour.reducer` (a `Reducer`) go through `parse_reduced` to recover the `IrAst` of the grammar being compiled.
- **Instance parsing:** `derive_specs`'s output `list[RuleSpec]` is reconstituted into a second `IrAst` (`lexic.parsing.models.specs_to_grammar`) and parsed by the same engine; `ModelFold` (also in `lexic.parsing.models`) replaces the old `build_transformer`, folding a `ParseTree` into generated Pydantic model instances.

See `src/lexic/parsing/__init__.py`'s module docstring for the full engine module map (`tables`, `kernel`, `chart`, `engine`, `forest`, `reduce`, `normalize`) and public API (`recognize`, `parse`, `parse_first`, `parse_reduced`, `parse_forest`, `derivations`, `is_ambiguous`).

## IR is passed by action table, not closed subclass

A pass is an `IrTypeMap` of `IrAction`s — not a closed subclass of `IrDispatch`. Flavours, transformers and emitters all extend the system by **constructing an instance** with a different `actions` table. New IR types don't require touching the dispatcher: just add an entry to the table.

## `IrLiteral` dual role

`IrLiteral` carries both grammar-literal and action-constant roles — see [[ir-shapes]] for the eval-time distinction.

## Flavour as `IrEmitter` + `Reducer`

`IrFlavour` IS-AN `IrEmitter` with **zero methods** beyond the inherited emitter protocol (R1 — see [[flavour-system]]). Each flavour exposes a **private** class (`_GbnfFlavour`, `_AbnfFlavour`) and a **public singleton** (`GBNF_FLAVOUR`, `ABNF_FLAVOUR`) in a single flat module (`grammars/gbnf.py`, `grammars/abnf.py` — no subpackages). `apply(root)` walks an IR tree to a flavour string (the emit half); `flavour.grammar` + `flavour.reducer` drive parsing the other direction (the text→IR half).

Escape codecs follow the same pattern: `_GbnfEscapes` / `_AbnfEscapes` (private) → `GBNF_ESCAPES` / `ABNF_ESCAPES` (singleton instances), `ClassVar[EscapeCodec]` — an instance, not a class.

## Four package layers

```
lexic.ir          Pure data + substrate. Imports nothing from the rest of lexic.
lexic.grammars    Flavour layer (IrFlavour subclasses + singletons; owns each flavour's self-grammar + reducer).
lexic.parsing     The Earley engine. Reads/writes IR only; imports neither grammars nor codegen.
lexic.codegen     Build-time. Imports from lexic.ir and lexic.grammars.
lexic (runtime)   Imports from lexic.ir + lexic.grammars (flavour singletons) + lexic.codegen + lexic.parsing (compile.py seam only).
```

## Layering rules — review-blocking offences

```
lexic.ir       ←  lexic.grammars
lexic.ir       ←  lexic.parsing
lexic.ir       ←  lexic.codegen
lexic.ir       ←  lexic (runtime)
lexic.grammars ←  lexic.codegen
lexic.parsing  ✗  lexic.grammars, lexic.codegen   (the engine is a leaf w.r.t. both)
lexic runtime  ✗  lexic.codegen, lexic.parsing    (forbidden, with two exceptions)
```

**The two deliberate exceptions:**

1. `base.py` imports `get_flavour` from `lexic.grammars` to drive `to_grammar()`. The GBNF singleton is `lexic.grammars.gbnf.GBNF_FLAVOUR`.
2. `compile.py` is the single runtime seam onto both `lexic.codegen` (`codegen`) and the engine (`lexic.parsing` — `parse_first`, `parse_reduced`; `lexic.parsing.models` — `ModelFold`, `build_instance_parser`; `lexic.parsing.normalize.normalize`; `lexic.parsing.reduce.Reducer`). All public, all explicit.

No `TYPE_CHECKING` dodges. No lazy intra-function imports. `tests/integration/test_layering_invariants.py` enforces all of the above by static grep, including `test_engine_package_does_not_import_grammars_or_codegen` and `test_engine_imported_by_runtime_only_via_compile_seam` (only `compile.py` may `from lexic.parsing import ...` among top-level runtime modules).

## Module ownership

| Package | Owns |
|---|---|
| `lexic.ir` | IR substrate: nodes, action algebra, dispatcher + presets, naming, deriving, escapes, charclass, topo, flavour ABC. |
| `lexic.grammars` | Flavour singletons. Each flavour module (`gbnf.py`, `abnf.py`) bundles an `EscapeCodec` instance, emit `actions`, a self-grammar `IrAst`, and a parse `Reducer` in one file. `json.py` is a third, flavour-neutral module: the JSON grammar authored directly as `IrAst` (RFC 8259), not parsed from any source text — the canonical target both front-ends reduce to. |
| `lexic.parsing` | The Earley engine (grammar-agnostic): compiled tables, kernel, chart/SPPF, forest, reduction, normalization, and the instance-parsing bridge (`models.py`). |
| `lexic.codegen` | Build-time generic pipeline: model-emitter, alias collection. |
| `lexic` (root) | Runtime: `GrammarModel`, `parse`, `compile_text`/`compile_from_path`, `generate`. |

## File tree (abbreviated)

```
src/lexic/
  base.py, compile.py, parse.py, generate.py, exceptions.py
  ir/
    base.py      IrSelf / IrNode / typed bases (IrStr, IrInt, IrTuple) / IrNone
    nodes.py     Grammar-AST node types (IrLiteral, IrCharClass, IrRuleRef, IrItem, IrRule, IrAst, ...)
    operators.py IrNot, IrOp
    action.py    Action-algebra nodes + default bodies
    mapping.py   IrTypeMap / IrMap — concrete-first MRO type-keyed tables
    walk.py      IrDispatch + IrVisitor / IrTransformer / IrEmitter presets
    flavour.py   IrFlavour ABC (extends IrEmitter) + IrEscape
    meta.py, emit.py, escapes.py, spec.py, charclass.py, derive.py,
    naming.py, regex_portable.py, topo.py
  grammars/
    __init__.py  get_flavour / register_flavour / flavour_for_extension
    gbnf.py      GBNF_ACTIONS, GBNF_GRAMMAR, GBNF_REDUCER, GBNF_ESCAPES, GBNF_FLAVOUR
    abnf.py      ABNF_ACTIONS, ABNF_GRAMMAR, ABNF_REDUCER, ABNF_ESCAPES, ABNF_FLAVOUR
    json.py      JSON_GRAMMAR — flavour-neutral IrAst, hand-authored
  parsing/
    __init__.py  Public API: recognize, parse, parse_first, parse_reduced,
                 parse_forest, derivations, is_ambiguous
    tables.py    ParserTables, compile_tables (memoised by IrAst identity)
    kernel.py    Kernel (predict/scan/complete, Leo), FastTree
    chart.py     Chart / Links (decoded SPPF)
    engine.py    Per-capability orchestration nodes behind the public API
    forest.py    ParseTree, SppfNode
    reduce.py    Reducer — forest → IrAst
    normalize.py Desugar IR into classical Earley-shaped rules
    models.py    specs_to_grammar / ModelFold / build_instance_parser /
                 collapsed_instance_tables — RuleSpec → instance-parser bridge
    lexruns.py, trampoline.py
  codegen/
    __init__.py  codegen(specs, stem) -> dict[str, type]
    model_emitter.py, aliases.py
  utils/
    names.py     to_pascal / to_snake (to_lark_name deleted)
    quantifiers.py  bounds_to_quantifier — still consumed by codegen/aliases.py
    charclass.py
```

`src/lexic/parsing/` (Lark: `meta_parser.py`, `lark_builder.py`, `transformer/`) is **gone outright** — no `parsing_legacy`/`parsing_old` shim. `lark` is removed from `pyproject.toml`; it survives only as `tools/benchmark/parse_bench.py`'s fixed reference baseline (pure Lark, zero lexic machinery, raced against the native engine — not imported by `src/`).

`IrText` never existed — `IrLiteral` carries both grammar-literal and action-constant roles.
