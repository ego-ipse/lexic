# Architecture

**When to load:** checking import legality; adding a module or package; understanding pipeline flow; the two deliberate runtime→codegen exceptions; understanding the IR substrate (dispatch / actions / presets).

See also: [[ir-shapes]], [[flavour-system]], [[error-vocabulary]], [[decisions]]

## The one-sentence version

Grammar text → `IrAst` → canonicalize → **THE codegen grammar** → generated Pydantic classes + an instance-parsing fold, all off the *same* canonical `IrAst`. Grammar is the ground truth; classes are its Python representation. Every transformation — canonicalization, codegen, flavour emission — is expressed in the same **action-driven IR substrate**, including grammar parsing itself: `lexic.parsing` is a native Earley engine that parses `IrAst`-shaped grammars, not a wrapper around a third-party parser generator.

## Pipeline (single, post-cutover — no Lark, no RuleSpec)

```
grammar text
  ├─► compile._scan_directives (private helper)   (start, non_semantic) tuple
  └─► parse_reduced(normalize(flavour.grammar),   IrAst
        text, flavour.reducer)                     (lexic.parsing engine + flavour's own self-grammar/reducer)
        └─► canonicalize(ast)                      canonical IrAst
              (ir/canonical.py — language-preserving normal form; two flavours
               of the same language converge on the same tree)
              └─► canonical_grammar()               (compile.py's public front half: parse +
                    │                                 canonicalize + directive flags; start bound,
                    │                                 named rules reconstructed semantic=False)
                    └─► build_codegen_grammar(ast)  THE codegen grammar
                          (lexic.codegen.passes: hoist_groups → hoist_arms →
                           relax_non_semantic)
                          ├─► compute_binding(ast)            list[RuleBinding]
                          │     (lexic.codegen.binding — class/kind/parent/field
                          │      names, open IrDispatch tables)
                          ├─► codegen(canonical, ast, binding, stem)
                          │     → generated/<stem>.py + dict[str, type]
                          ├─► flavour_singleton.apply(node)   → grammar text
                          └─► fold config (plain data) → parsing/fold.py's
                                PositionalFold, over
                                instance_grammar = normalize(lift_optional_nullables(ast))
```

Each flavour (`GBNF_FLAVOUR`, `ABNF_FLAVOUR`) carries its own self-grammar as raw `IrAst` (`flavour.grammar`) and a `Reducer` (`flavour.reducer`) that folds a parse of grammar *text* back into `IrAst`. `parse_grammar` normalizes and memoises `flavour.grammar` once per flavour name (`compile.py`'s `_NORM_GRAMMAR_CACHE`), then calls `lexic.parsing.parse_reduced` — the same Earley engine that later parses *instances* of the codegen grammar.

Entry points in `compile.py`:

- `compile_text(text, *, cache_key=None, flavour="gbnf")` — string-in.
- `compile_from_path(path, *, flavour=None)` — path-in (flavour inferred from extension).
- `canonical_grammar(text, flavour, *, non_semantic_rules=None, start=None)` — the public front half: text → canonical, semantic-flagged `IrAst`. `generate.py` and transpilers (`getting_started/ex04`) build on this directly, without generating classes.

`compile_text` / `compile_from_path` return `CompiledGrammar(classes, grammar, instance_grammar, fold, tables)` — no `lark.Lark` parser, no `lark.Transformer`, no `RuleSpec`. `grammar: IrAst` is the **canonical** grammar (what the user's grammar IS — also the generated module's `GRAMMAR` footer); `instance_grammar: IrAst` is the Earley-normalised codegen grammar (kept so the engine's identity-memoised `compile_tables` stays hot across repeated `.parse()` calls); `fold: PositionalFold` folds a `ParseTree` into model instances directly over that grammar's positions — no intermediate wrapper grammar. `compile_from_path` uses `path.stem` as the generated module name; `compile_text` uses `anon_<sha1-of-text>`. See [[public-api]] for the full `CompiledGrammar` contract.

## The positional fold replaces the wrapper-rule bridge

Before the 2026-07-04 cutover, instance parsing reconstituted `list[RuleSpec]` into a *second*, synthetic `IrAst` with `--f<idx>` wrapper rules carrying field names as grammar symbols, then a `ModelFold` walked that wrapper tree. That whole bridge (`parsing/models.py`) is gone. `normalize()` (`parsing/normalize.py`) replaces each grammar item **in place** when desugaring to classical Earley-shaped rules, so an original item is always exactly one symbol slot in the normalized arm: for a rule's `ParseTree` node, `kids[i] ↔ items[i]`. Field extraction is therefore **positional indexing** against the *real* codegen grammar — `parsing/fold.py`'s `PositionalFold`, configured by plain-data `RuleFold`/`FieldFold` records built by `compile.py` from the binding view + generated classes. No wrapper rules, no field-name-as-grammar-symbol protocol.

## The IR substrate

Every node — grammar AST, action algebra, dispatcher, and the Earley engine's own state objects — descends from `IrSelf`. Every node is callable: `node(d, n, nc) -> Ir_co`. The substrate has four pieces.

### 1. `IrSelf` mixin + `IrNode` generic (`ir/base.py`)

`IrSelf[Iri, Ir_co]` is the identity mixin. It supplies a default `__call__` that returns `self` (PEP 673 `Self`) and an `eval(d, n, nc) -> Ir_co` protocol method. Value-producing nodes override `eval`. `IrNode` is a generic ABC: every grammar AST node and every action node descends from it. Fixed-arity records are `IrNamedTuple` subclasses (the node IS a tuple with named field accessors) — there is no `IrComposite`/frozen-dataclass tier. See [[ir-shapes]] for the full tier breakdown.

### 2. Action-algebra nodes (`ir/action.py`)

Operations the AST nodes don't cover:

- **`IrField(name, out=IrStr)`** — read a typed attribute from `n` and wrap via `out` (an open `IrScalar` subtype, default `IrStr`).
- **`IrLambda(handler)`** (`ir/base.py`) — procedural escape hatch; `handler(d, n, nc) -> Ir_co`. (There is no `IrCallable` — that name retired with the primitive-node migration.)
- **`IrChild(name)` / `IrChildren()`** — sibling lookup. Hybrid behaviour: when `nc` is populated (caller pre-walked), index/return it directly; when `nc` is empty, the lookup is lazy — `IrChild` resolves the named child from `n` and dispatches via `d.eval(d, child, ())`; `IrChildren` dispatches every item in `n.children()`.
- **`IrConcat(parts)`** — evaluate `parts` in order, join via the bound's neutral element.
- **`IrJoin(parts, separator, empty)`** — variable-arity join with separator and empty-fallback.
- **`IrCond(test, then_op, else_op)`** — branch on `test.eval(d, n, nc)` (truthy → `then_op`).
- **`IrAction(target_type, body)`** — binds an IR-node type to a callable IR body. `target_type` is metadata excluded from `_child_attrs`; `body` is the dispatched child.

Default bodies: `IrPass` (no-op → `IrNone`), `IrWalk` (visit children, discard), `IrRaise` (raise on unmatched), `IrEmit` (`IrLiteral(str(n))`), `IrRebuild` (walk + reconstruct).

### 3. Dispatcher (`ir/walk.py`)

`IrDispatch[Iri, Ir_co]` is an `IrCachingTuple` of `(actions: IrTypeMap, default: IrSelf)` — an `IrMap`-family type→`IrAction` table with concrete-first MRO resolution (`ir/mapping.py`), no per-instance cache (every resolution is a live dict/MRO walk). Two seams:

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

`src/lexic/parsing/` is a single native Earley engine (SPPF-based, Scott 2008) that both paths share — there is no Lark anywhere, and no separate meta-grammar-parser layer:

- **Grammar parsing:** `flavour.grammar` (an `IrAst` authored directly, not derived from any string grammar) + `flavour.reducer` (a `Reducer`) go through `parse_reduced` to recover the `IrAst` of the grammar being compiled.
- **Instance parsing:** the codegen grammar (the *same* `IrAst` shape, post `build_codegen_grammar`) is normalized (`lift_optional_nullables` then `normalize`) and parsed by the same engine; `parsing/fold.py`'s `PositionalFold` (not `ModelFold` — that class died with `parsing/models.py`) folds a `ParseTree` into generated Pydantic model instances by positional indexing, not by a wrapper-rule name protocol.

See `src/lexic/parsing/__init__.py`'s module docstring for the full engine module map (`tables`, `kernel`, `chart`, `engine`, `forest`, `reduce`, `normalize`, `fold`) and public API (`recognize`, `parse`, `parse_first`, `parse_reduced`, `parse_forest`, `derivations`, `is_ambiguous`).

## IR is passed by action table, not closed subclass

A pass is an `IrTypeMap` of `IrAction`s — not a closed subclass of `IrDispatch`. Flavours, transformers and emitters all extend the system by **constructing an instance** with a different `actions` table. New IR types don't require touching the dispatcher: just add an entry to the table. `codegen/binding.py` and `codegen/passes.py` pioneered this discipline for codegen's classify/naming/mode logic; `generate.py`, `codegen/model_emitter.py`, and `codegen/aliases.py` have since landed the same open `IrDispatch`/`IrTypeMap` treatment (2026-07-04) — every atom-type consumer in the tree is now an open table with a raising default. See [[ir-shapes]]'s open-set note.

## `IrLiteral` dual role

`IrLiteral` carries both grammar-literal and action-constant roles — see [[ir-shapes]] for the eval-time distinction.

## Flavour as `IrEmitter` + `Reducer`

`IrFlavour` IS-AN `IrEmitter` with **zero methods** beyond the inherited emitter protocol (R1 — see [[flavour-system]]). Each flavour exposes a **private** class (`_GbnfFlavour`, `_AbnfFlavour`) and a **public singleton** (`GBNF_FLAVOUR`, `ABNF_FLAVOUR`) in a single flat module (`grammars/gbnf.py`, `grammars/abnf.py` — no subpackages). `apply(root)` walks an IR tree to a flavour string (the emit half); `flavour.grammar` + `flavour.reducer` drive parsing the other direction (the text→IR half).

Escape codecs follow the same pattern: `_GbnfEscapes` / `_AbnfEscapes` (private) → `GBNF_ESCAPES` / `ABNF_ESCAPES` (singleton instances), `ClassVar[EscapeCodec]` — an instance, not a class.

## Package layers

```
lexic.ir          Pure data + substrate. Imports nothing from the rest of lexic.
lexic.grammars    Flavour layer (IrFlavour subclasses + singletons; owns each flavour's self-grammar + reducer).
lexic.parsing     The Earley engine. Reads/writes IR only; imports neither grammars nor codegen.
lexic.codegen     Build-time. IR-native — imports from lexic.ir only, NOT lexic.grammars (codegen needs no flavour adapters).
lexic (runtime)   Imports from lexic.ir + lexic.grammars (flavour singleton, base.py only) + lexic.codegen + lexic.parsing (compile.py seam only).
```

## Layering rules — review-blocking offences

```
lexic.ir       ←  lexic.grammars
lexic.ir       ←  lexic.parsing
lexic.ir       ←  lexic.codegen
lexic.ir       ←  lexic (runtime)
lexic.codegen  ✗  lexic.grammars                  (codegen is IR-native; no flavour adapters needed)
lexic.parsing  ✗  lexic.grammars, lexic.codegen   (the engine is a leaf w.r.t. both)
lexic runtime  ✗  lexic.codegen, lexic.parsing    (forbidden, with two exceptions)
```

**The two deliberate exceptions:**

1. `base.py` imports `get_flavour` from `lexic.grammars` to drive `to_grammar()` (`get_flavour(flavour).apply(self.__grammar__)` — `__grammar__` is already an `IrRule`, no intermediate conversion). The GBNF singleton is `lexic.grammars.gbnf.GBNF_FLAVOUR`.
2. `compile.py` is the single runtime seam onto both `lexic.codegen` (`codegen`, `build_codegen_grammar`, `compute_binding`) and the engine (`lexic.parsing` — `parse_first`, `parse_reduced`; `lexic.parsing.fold` — `PositionalFold`, `RuleFold`, `FieldFold`, `collapsed_fold_tables`, `lift_optional_nullables`; `lexic.parsing.normalize.normalize`; `lexic.parsing.reduce.Reducer`). All public, all explicit.

No `TYPE_CHECKING` dodges. No lazy intra-function imports. `tests/integration/test_layering_invariants.py` enforces all of the above by static grep, including `test_engine_package_does_not_import_grammars_or_codegen`, `test_codegen_does_not_import_grammars_or_parsing`, and `test_engine_imported_by_runtime_only_via_compile_seam` (only `compile.py` may `from lexic.parsing import ...` among top-level runtime modules); `test_engine_fold_seam_is_plain_data` additionally asserts the engine (fold.py included) never imports pydantic or `lexic.ir.spec` (which no longer exists at all).

## Module ownership

| Package | Owns |
|---|---|
| `lexic.ir` | IR substrate: nodes, action algebra, dispatcher + presets, mapping, canonicalization, rule ordering, field binding marker (`IrBind`), escapes, flavour ABC. |
| `lexic.grammars` | Flavour singletons. Each flavour module (`gbnf.py`, `abnf.py`) bundles an `EscapeCodec` instance, emit `actions`, a self-grammar `IrAst`, and a parse `Reducer` in one file. `json.py` is a third, flavour-neutral module: the JSON grammar authored directly as `IrAst` (RFC 8259), not parsed from any source text — the canonical target both front-ends reduce to. |
| `lexic.parsing` | The Earley engine (grammar-agnostic): compiled tables, kernel, chart/SPPF, forest, reduction, normalization, and the instance-parsing bridge (`fold.py` — a generic positional fold, no codegen/pydantic knowledge). |
| `lexic.codegen` | Build-time generic pipeline, IR-native: grammar→grammar passes (`passes.py`), the binding view (`binding.py`), the emitter (`model_emitter.py`), alias collection (`aliases.py`). |
| `lexic` (root) | Runtime: `GrammarModel`, `parse`, `compile_text`/`compile_from_path`/`canonical_grammar`, `generate`. |

## File tree (abbreviated)

```
src/lexic/
  base.py, compile.py, parse.py, generate.py, exceptions.py
  ir/
    base.py      IrSelf / IrNode / typed bases (IrStr, IrInt, IrTuple, IrSeq,
                 IrNamedTuple, IrCachingTuple) / IrNone / IrLambda
    nodes.py     Grammar-AST node types (IrLiteral, IrCharClass, IrRuleRef, IrItem,
                 IrQuantifier, IrRange, IrRule, IrAst, ...)
    operators.py IrOp, IrNot, IrEq, IrAnd (+ Monadic/Dyadic/VariadicOp bases)
    action.py    Action-algebra nodes + default bodies
    mapping.py   IrMapping/IrMap/IrTypeMap/IrMultiMap — concrete-first MRO type-keyed tables
    walk.py      IrDispatch + IrVisitor / IrTransformer / IrEmitter presets
    flavour.py   IrFlavour ABC (extends IrEmitter) + IrEscape
    canonical.py canonicalize(ast) — language-preserving normal form
    bind.py      IrBind + BIND_MODES — the field-binding marker
    order.py     RuleOrder — start-first ordering over a supplied edge relation
    meta.py, escapes.py
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
    fold.py      PositionalFold / RuleFold / FieldFold / lift_optional_nullables /
                 collapsed_fold_tables — the codegen-grammar → model-instance bridge
    lexruns.py, trampoline.py
  codegen/
    __init__.py    codegen(canonical, codegen_grammar, binding, stem) -> dict[str, type]
    passes.py      hoist_groups / hoist_arms / relax_non_semantic / build_codegen_grammar
    binding.py     compute_binding -> list[RuleBinding]; CHARCLASS_NAMES/LITERAL_NAMES;
                   class_name_for; has_ruleref
    model_emitter.py, aliases.py
```

`src/lexic/parsing/` (Lark: `meta_parser.py`, `lark_builder.py`, `transformer/`) is **gone outright** — no `parsing_legacy`/`parsing_old` shim. `lark` is removed from `pyproject.toml`; it survives only as `tools/benchmark/parse_bench.py`'s fixed reference baseline (pure Lark, zero lexic machinery, raced against the native engine — not imported by `src/`).

`ir/derive.py`, `ir/spec.py` (`RuleSpec`), `ir/emit.py`, `ir/naming.py`, `ir/topo.py`, `parsing/models.py`, and the whole `utils/` package are **also gone outright** (2026-07-04 RuleSpec→IR-native codegen cutover) — no RuleSpec shim of any kind. `IrText` never existed — `IrLiteral` carries both grammar-literal and action-constant roles.
