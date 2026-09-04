# Architecture

**When to load:** checking import legality; adding a module or package; understanding pipeline flow; the two deliberate runtime→codegen exceptions; understanding the IR substrate (dispatch / actions / presets).

See also: [[ir-shapes]], [[flavour-system]], [[error-vocabulary]], [[decisions]]

## The one-sentence version

Grammar text → `IrAst` → canonicalize → **THE codegen grammar** → model classes synthesized at runtime (on the `IrNamedTuple` record spine) + an instance-parsing fold, all off the *same* canonical `IrAst`. Grammar is the ground truth; classes are its Python representation. Every transformation — canonicalization, class synthesis, flavour emission — is expressed in the same **action-driven IR substrate**, including grammar parsing itself: `lexic.parsing` is a native Earley engine that parses `IrAst`-shaped grammars, not a wrapper around a third-party parser generator.

## Pipeline (single, post-cutover — no Lark, no RuleSpec)

```
grammar text
  ├─► compile._scan_directives (private helper)   (start, non_semantic) tuple
  └─► compile_ast(flavour.grammar).reduce(        IrAst
        text, flavour.reducer)                     (compiled pruned-model variant + thin reducer fold)
        └─► canonicalize(ast)                      canonical IrAst
              (ir/canonical.py — language-preserving normal form; two flavours
               of the same language converge on the same tree)
              └─► canonical_grammar()               (the compile package's public front half: parse +
                    │                                 canonicalize + directive flags; start bound,
                    │                                 named rules reconstructed semantic=False)
                    └─► build_codegen_grammar(ast)  THE codegen grammar
                          (lexic.compile.pipeline.passes: hoist_groups → hoist_arms →
                           relax_non_semantic)
                          ├─► compute_binding(ast)            list[RuleMap]
                          │     (lexic.compile.pipeline.rulemap — class/kind/parent/field
                          │      names, open IrDispatch tables)
                          ├─► synthesize(ast, binding, stem)
                          │     (lexic.compile.pipeline.synthesis — type() build,
                          │      __grammar__/__binds__, NO file) → dict[str, type]
                          ├─► flavour_singleton.apply(node)   → grammar text
                          └─► register_model(codegen_grammar, view, classes)
                                (lexic.compile.product.registry) → ModelExecutable
                                (lexic.parsing.executable — the product program,
                                lowered once and verified cold at binding), over
                                codegen_grammar = normalize(lift_optional_nullables(ast))
```

Each flavour (`GBNF_FLAVOUR`, `ABNF_FLAVOUR`) carries its own self-grammar as raw `IrAst` (`flavour.grammar`) and a `Reducer` (`flavour.reducer`) that folds a parse of grammar *text* back into `IrAst`. `parse_grammar` compiles that self-grammar like any other artefact and calls `CompiledGrammar.reduce`; the reducer derives a pruned model variant, which runs through the same model engine as ordinary instances before a thin fold rebuilds the requested IR value. Both the self-grammar artefact and its reducer-derived variant are memoised.

Entry points in the `compile/` package:

- `compile_text(text, *, cache_key=None, flavour="gbnf")` — string-in.
- `compile_from_path(path, *, flavour=None)` — path-in (flavour inferred from extension).
- `canonical_grammar(text, flavour, *, non_semantic_rules=None, start=None)` — the public front half: text → canonical, semantic-flagged `IrAst`. `generate.py` and transpilers (`getting_started/ex04`) build on this directly, without generating classes.

`compile_text` / `compile_from_path` return `CompiledGrammar(grammar, product, moments, flavour, stem, tokens, split_analysis)` (`compile/artifact.py`). `grammar: IrAst` is the **canonical** grammar (what the user's grammar IS — also the exported module's `GRAMMAR`); `codegen_grammar` (a read of `moments`) is the post-pass grammar the product binds against and `.parse` hands to `parse_model` (the engine memoises its lifted/normalised/PDA/run-collapsed compilation per this grammar's identity); `product: ModelExecutable[GrammarModel]` is the bound product program both engines execute (immutable after verification; `.executor` is its `ProductExecutor`); `classes` is a read of `moments`; `flavour`/`stem` carry the export identity. `compile_from_path` uses `path.stem` as the stem; `compile_text` uses `anon_<sha1-of-text>`. One-line entries: `parse_instance(text, grammar, *, flavour)` / `parse_instance_from_path(text, path)` — `parse` itself is the ENGINE's name (`lexic.parsing.parse`), never reused. On explicit request `export_module(compiled, path, *, inline_tables=False)` writes an importable twin module — see [[generated-modules]]. See [[public-api]] for the full `CompiledGrammar` contract.

## The positional fold replaces the wrapper-rule bridge

Before the 2026-07-04 cutover, instance parsing reconstituted `list[RuleSpec]` into a *second*, synthetic `IrAst` with `--f<idx>` wrapper rules carrying field names as grammar symbols, then a wrapper-rule fold (the *old* `ModelFold`, `parsing/models.py`) walked that wrapper tree. That whole bridge is gone. `normalize()` (`parsing/normalize.py`) replaces each grammar item **in place** when desugaring to classical Earley-shaped rules, so an original item is always exactly one symbol slot in the normalized arm: for a rule's `ParseTree` node, `kids[i] ↔ items[i]`. Field extraction is therefore **positional indexing** against the *real* codegen grammar — the product program's per-rule captures (`parsing/product/`: `RuleProduct` → verified `RuleRoutine` with one `CaptureRoutine(slot, mode, optional, name)` per bound slot), authored by the compile package from the binding view + generated classes (`compile/product/registry.py`'s `register_model`) and lowered once to flat tables (`parsing/product/lower.py`) that `verify_program` checks cold at binding. (`ModelFold`/`ModelBody`/`RuleFold` — the 2026-07-06 IR body-table — are deleted; see [[decisions]].) No wrapper rules, no field-name-as-grammar-symbol protocol.

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

- **Grammar parsing:** `flavour.grammar` (an `IrAst` authored directly, not derived from any string grammar) is compiled into an artefact; `flavour.reducer` derives a pruned variant whose model is thin-folded to recover the `IrAst` of the grammar being compiled.
- **Instance parsing:** the codegen grammar (the *same* `IrAst` shape, post `build_codegen_grammar`) is normalized (`lift_optional_nullables` then `normalize`) and parsed by the same engine; the bound product (`ModelExecutable`, `parsing/executable.py`) completes each rule through its verified routine — the PDA bakes the routine into its clones (`pda/compiler/program/product.py`), the tree route runs it over the `ParseTree` (`parsing/product/tree.py`'s `complete_product`) — building record-spine model instances (`IrNamedTuple`) by positional indexing, not by a wrapper-rule name protocol.

See `src/lexic/parsing/__init__.py`'s module docstring for the full engine module map (`kernel/tables`, `kernel/loop`, `kernel/forest`, `engine`, `normalize`, `lift`, `product/`, `executable`) and public API (`parse_model`, `earley_model`, `token_model`, `pda_tables`, `recognize`, `parse`, `parse_first`, `parse_forest`, `derivations`, `is_ambiguous`).

## IR is passed by action table, not closed subclass

A pass is an `IrTypeMap` of `IrAction`s — not a closed subclass of `IrDispatch`. Flavours, transformers and emitters all extend the system by **constructing an instance** with a different `actions` table. New IR types don't require touching the dispatcher: just add an entry to the table. `compile/pipeline/rulemap.py` and `compile/pipeline/passes.py` pioneered this discipline for classify/naming/mode logic; `generate.py`, the notation emit half (`notation.py`'s `_EMIT_STEP` — tier-keyed, so a new node type needs no emitter change) and the PDA analysis all carry the same open `IrDispatch`/`IrTypeMap` treatment with raising defaults. See [[ir-shapes]]'s open-set note.

## `IrLiteral` dual role

`IrLiteral` carries both grammar-literal and action-constant roles — see [[ir-shapes]] for the eval-time distinction.

## Flavour as `IrEmitter` + `Reducer`

`IrFlavour` IS-AN `IrEmitter` with **zero methods** beyond the inherited emitter protocol (R1 — see [[flavour-system]]). Each flavour exposes a **private** class (`_GbnfFlavour`, `_AbnfFlavour`) and a **public singleton** (`GBNF_FLAVOUR`, `ABNF_FLAVOUR`) in a single flat module (`grammars/gbnf.py`, `grammars/abnf.py` — no subpackages). `apply(root)` walks an IR tree to a flavour string (the emit half); `flavour.grammar` + `flavour.reducer` drive parsing the other direction (the text→IR half).

Escape codecs follow the same pattern: `_GbnfEscapes` / `_AbnfEscapes` (private) → `GBNF_ESCAPES` / `ABNF_ESCAPES` (singleton instances), `ClassVar[EscapeCodec]` — an instance, not a class.

## Package layers

```
lexic.ir          Pure data + substrate (incl. the layout algebra, ir/layout.py). Imports nothing from the rest of lexic.
lexic.grammars    Flavour layer (IrFlavour subclasses + singletons; owns each flavour's self-grammar + reducer).
lexic.parsing     The Earley engine + predictive PDA. Reads/writes IR only; imports neither grammars nor compile.
lexic.compile     The compilation subsystem (a package): passes, binding, synthesis, export, notation, loader, artifact. The sole runtime seam onto the engine.
lexic.api         Readers for third-party formats. Runtime modules: they reach the engine only through the lexic.compile seam.
lexic (runtime)   model.py (GrammarModel), generate.py, exceptions.py. Imports lexic.ir + lexic.grammars (flavour singleton, model.py only) + lexic.compile.
```

Outside the shipped package, `ext/API/` holds clients that **fetch**
third-party artefacts. The split is deliberate and worth keeping straight:

| | job | ships |
|---|---|---|
| `ext/API/` | **get** the artefact (network, cache) | no |
| `lexic.api` | **read** the format | yes |
| `lexic.ir` | **model** it — knows neither | yes |

A format that merely happens to be hosted somewhere does not belong to that
host, and a network client has no business in a grammar engine's wheel. A
reader takes the grammar+reducer that read its document as **parameters**, so
it privileges no formulation ([[decisions]]) — that is what makes a
third-party format reader legitimate inside `src`.

## Layering rules — review-blocking offences

```
lexic.ir       ←  lexic.grammars
lexic.ir       ←  lexic.parsing
lexic.ir       ←  lexic.compile
lexic.ir       ←  lexic (runtime)
lexic.parsing  ✗  lexic.grammars, lexic.compile   (the engine is a leaf w.r.t. both)
lexic runtime  ↗  lexic.compile, lexic.parsing    (runtime NEVER imports the engine directly — two exceptions)
```

**The two deliberate exceptions:**

1. `model.py` imports `get_flavour` from `lexic.grammars` to drive `to_grammar()` (`get_flavour(flavour).apply(self.__grammar__)` — `__grammar__` is already an `IrRule`, no intermediate conversion). The GBNF singleton is `lexic.grammars.gbnf.GBNF_FLAVOUR`.
2. The `lexic.compile` package is the single runtime seam onto the engine (`lexic.parsing` — `parse_model`; `lexic.parsing.executable`; `lexic.parsing.product`; `lexic.parsing.normalize.normalize`). Only `compile/__init__.py` is importable from outside the package; the pipeline (passes / rulemap / synthesis / moments / naming), product (registry), module (export / attach / selfgrammar / verify / rules), notation, output and artifact submodules live inside it. All public, all explicit.

No `TYPE_CHECKING` dodges. No lazy intra-function imports of the engine. `tests/integration/lexic/invariants/test_layering_invariants.py` enforces all of the above by static grep, including that only the `lexic.compile` package may import `lexic.parsing`, that only `compile/__init__.py` is reachable from outside the package, and that `src/` stays free of any schema-validation framework.

## Module ownership

| Package | Owns |
|---|---|
| `lexic.ir` | IR substrate: nodes, action algebra, dispatcher + presets, mapping, canonicalization, rule ordering, field binding marker (`IrBind`), escapes, flavour ABC, and the layout algebra (`layout.py` — width-aware doc combinators; see [[generated-modules]]). |
| `lexic.grammars` | Flavour singletons. Each flavour module (`gbnf.py`, `abnf.py`) bundles an `EscapeCodec` instance, emit `actions`, a self-grammar `IrAst`, and a parse `Reducer` in one file. `json.py` is a third, flavour-neutral module: the JSON grammar authored directly as `IrAst` (RFC 8259), not parsed from any source text — the canonical target both front-ends reduce to. |
| `lexic.parsing` | The engine (grammar-agnostic): the Earley core (`earley/` — `kernel/` split into `tables` (the compiled grammar), `loop` (what fills the chart) and `forest` (what the filled chart means), plus normalize), the predictive PDA (`pda/` — analysis, model compiler, fused runtime), the `parse_model` product entry (PDA-first with Earley completion; `earley_model` / `token_model` beside it), the product ABI (`product/` — authored operations, their flat int-coded lowering, cold verification, one executable routine per rule for both engines, the tree-route completion, the regular-language proof), the bound product (`executable.py` — `ModelExecutable`, `ProductExecutor`), the optional-nullable lift (`lift.py`), and the parallel layer (`parallel/`). |
| `lexic.compile` | The compilation subsystem: grammar→grammar passes (`pipeline/passes.py`), the binding view (`pipeline/rulemap.py` — `compute_binding`, `RuleMap`), runtime class synthesis (`pipeline/synthesis.py` — `type()`, no file write), the compile moments (`pipeline/moments.py`), the product binding (`product/registry.py` — `register_model`, `ProductRegistry`; the compile half of the product ABI), the artefact (`artifact.py` — `CompiledGrammar`), the importable-twin exporter and its binder (`module/export.py`, `module/attach.py` — see [[generated-modules]]), the IR-constructor notation (`notation/` — `load_ir` parse half + `emit_ir` emit half, the flavour loader), reduction (`reduction.py`, `reduce/`), and the output surfaces (`output/` — presentation, templating, transpile). |
| `lexic` (root) | Runtime: `GrammarModel` (`model.py`), `generate`; re-exports `compile_text`/`compile_from_path`/`parse_grammar`/`parse_instance`/`parse_instance_from_path`. |

## File tree (abbreviated — see CLAUDE.md §Project layout for the full map)

```
src/lexic/
  model.py, generate.py, exceptions.py
  ir/        base, nodes, operators, action, mapping, walk, flavour,
             canonical, bind, order, layout, meta, escapes
  grammars/  __init__ (registry), gbnf, abnf, json
  parsing/   __init__ (products + toolkit), products, executable, lift, caches,
             trace, product/ (abi/, lower, verify, routines, tree, state, regular),
             earley/, pda/, parallel/
  compile/   __init__ (entries + attach_module), artifact, foldkit, reduction,
             verdict, pipeline/ (passes, rulemap, synthesis, moments, naming),
             product/ (registry), module/ (export, attach, selfgrammar, verify,
             rules), notation/, output/, payload/, reduce/
```

`src/lexic/parsing/` (Lark: `meta_parser.py`, `lark_builder.py`, `transformer/`) is **gone outright** — no `parsing_legacy`/`parsing_old` shim. `lark` is not a runtime dependency and `src/` never imports it. It survives as a dev dependency, one competitor among several in `tools/benchmark/` — where its grammar, like every other engine's, is derived mechanically from the one `IrAst` lexic compiles, so a row compares one question rather than several.

`ir/derive.py`, `ir/spec.py` (`RuleSpec`), `ir/emit.py`, `ir/naming.py`, `ir/topo.py`, `parsing/models.py`, and the whole `utils/` package are **also gone outright** (2026-07-04 RuleSpec→IR-native codegen cutover) — no RuleSpec shim of any kind. `IrText` never existed — `IrLiteral` carries both grammar-literal and action-constant roles.
