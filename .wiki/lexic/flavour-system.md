# Flavour System

**When to load:** adding a new grammar flavour; writing or extending a flavour's emit `actions` or self-grammar/reducer; deciding when to use a procedural `IrLambda` vs pure action algebra.

See also: [[architecture]], [[ir-shapes]]

A *flavour* is a grammar notation — GBNF, ABNF, etc. Adding a flavour means adding one flat module under `grammars/` (`grammars/<name>.py` — no subpackage).

## Singleton convention

Each flavour module exposes:

- A **private** flavour class: `_GbnfFlavour`, `_AbnfFlavour`. Not exported.
- A **public singleton instance**: `GBNF_FLAVOUR`, `ABNF_FLAVOUR`. Imported by `grammars/__init__.py` and registered on import.
- A **private** escape codec class: `_GbnfEscapes`, `_AbnfEscapes`.
- A **public singleton codec**: `GBNF_ESCAPES`, `ABNF_ESCAPES`.

The class-level default `actions: IrTypeMap = GBNF_ACTIONS` means constructing the instance with no args yields the populated singleton.

## `IrFlavour` ABC (`ir/flavour.py`) — R1: zero methods

Post-cutover, `IrFlavour` carries **no methods at all** beyond the inherited `IrEmitter` protocol — only metadata ClassVars, the emit `actions`, and the two parse-side ClassVars (`grammar`, `reducer`):

```python
class IrFlavour(IrEmitter, ABC):
    name: ClassVar[str]
    extensions: ClassVar[tuple[str, ...]]
    escapes: ClassVar[EscapeCodec]        # instance, not class
    line_comment: ClassVar[str] = ""      # empty disables @directive scanning
    grammar: ClassVar[IrAst]              # the flavour's self-grammar, raw/un-normalised
    reducer: ClassVar[IrDispatch]         # a lexic.parsing.reduce.Reducer at runtime
```

**Deleted with the Lark cutover, nothing replaces them as methods:** `parse_quantifier`, `parse_charclass`, `normalize_literal`, `meta_grammar`. Anything a flavour needs for parsing is now IR action algebra + data tables inside `reducer`, never a flavour callback. A dedicated test (`tests/unit/lexic/ir/test_flavour.py`) gates this: the only public names a concrete flavour class may define are `{name, extensions, line_comment, escapes, grammar, reducer, actions}` plus whatever `IrEmitter` already provides.

`escapes` is an `EscapeCodec` **instance** (not a class). `line_comment` is a `str` (empty disables directive parsing).

## Emit `actions` shape — pure algebra, zero `IrLambda`

A flavour's `actions: IrTypeMap` maps each IR-AST node type to a callable IR body — a concrete-first MRO-resolved table (`ir/mapping.py`), not a plain tuple. **Every shipped grammar module (`gbnf.py`, `abnf.py`, `ebnf.py`, `json.py`) carries zero `IrLambda` and zero `def` — emit actions AND reductions alike** (the def-purge that started with reductions, 2026-07-11, reached the emit half; escaping went render-side onto `EscapeCodec` data reached via the dispatcher-codec leaves `IrEscape`/`IrEscapePoint`/`IrSpellable`). A whole flavour is therefore data: it round-trips through the notation (the `.flavour.ir` manifests) and through the payload projection, and the decoded flavour emits and compiles.

The GBNF table's shape (`grammars/gbnf.py`, abridged — see the module for the real thing):

```python
GBNF_ACTIONS = IrTypeMap(
    IrAction(IrLiteral,   IrConcat(parts=IrTuple(IrLiteral('"'), IrEscape(), IrLiteral('"')))),
    IrAction(IrCharClass, IrCond(test=IrField("is_any", IrInt), then_op=IrLiteral("."),
                                 else_op=IrConcat(parts=IrTuple(IrLiteral("["), IrJoin(parts=IrArgs()),
                                                                IrJoin(parts=IrChildren()), IrLiteral("]"))))),
    ...,  # every other node type: IrConcat/IrJoin/IrCond/IrEscapePoint/layout-doc bodies
)
```

ABNF differs in several notable ways (prefix quantifier ordering on `IrItem`, `%xNN` hex char-class rendering, `IrNot` rejection since ABNF has no native negation, RFC 7405 `%s`/`%i` string markers).

## Parse-side: `grammar` + `reducer`

The other half of a flavour — text → `IrAst` — is not a method at all. It is two ClassVar values that the compile artefact drives from the outside:

- **`grammar: IrAst`** — the flavour's own grammar, authored directly as `IrAst` (not parsed from any meta-grammar string; there is no meta-grammar string anymore). `GBNF_GRAMMAR` / `ABNF_GRAMMAR` in `grammars/gbnf.py` / `grammars/abnf.py`. Its structural-noise rules carry `semantic=False` on their own `IrRule`; `<GRAMMAR>.non_semantic` (a derived property) collects their names (see [[ir-shapes]]).
- **`reducer: Reducer`** (`lexic.parsing.reduce.Reducer`, IS-AN `IrDispatch`) — an `IrMap[IrRuleRef, IrSelf]` (`GBNF_REDUCTIONS` / `ABNF_REDUCTIONS`) from a rule's `IrRuleRef` to a body folding that rule's matched children into IR, paired with a noise map (`GBNF_NOISE` / `ABNF_NOISE`) marking which children are structural (whitespace, delimiters, comments) and dropped before a reduction body sees them. The noise map is built *from* `<GRAMMAR>.non_semantic` (the per-rule `semantic=False` flags) — single source of truth (2026-07-03).

`parse_grammar` (`compile/__init__.py`) drives this through `compile_ast(flavour.grammar).reduce(text, flavour.reducer)`. The self-grammar artefact and reducer-derived pruned variant are memoised, and the variant uses the same `parse_model` path as every compiled grammar. No parser class, no `.for_flavour()` factory — a flavour simply supplies the `(IrAst, Reducer)` pair needed to parse *itself*.

R2 (escaping is a rendering feature, not an AST property) still holds: reduction actions decode escapes as render-side data (an `IrMap`/`IrUnradix`-style table), never on the AST node itself; the AST holds neutral, decoded payloads.

## When to use `IrLambda` vs pure algebra

Prefer pure algebra (`IrField`, `IrChild`, `IrChildren`, `IrConcat`, `IrJoin`, `IrCond`) whenever the body is a fixed assembly of attribute reads and string composition. The result is declarative, introspectable, and walks correctly under `IrTransformer`.

In a **grammar module**, never — an `IrLambda`/`def` in `grammars/*.py` is a review-blocking offence with no legacy exemption (the 2026-07-11 ruling; the purge is complete on both halves). What used to justify one now has an algebra home: escape-encoding is `IrEscape`/`IrEscapePoint`/`IrSpellable` over `EscapeCodec` *data*; quantifier/radix arithmetic is `IrRadix`/`IrUnradix`/`IrOrd`/`IrGlyph`/`IrLen`; declarative refusal is an `IrRaise` body (ABNF's `IrNot` action); type-branching is `IrPipe(IrArg, IrTypeMap)`; rule merging is `IrMerge`.

`IrLambda` remains legitimate OUTSIDE grammar modules — engine internals and consumers (e.g. the fold's constructor slot `IrLambda(cls)`). Bodies receive `(d, n, nc)` and return `Ir_co`; keep them small and side-effect-free, and recurse via `d.eval(d, c, ())`.

## Current flavour implementations

| Flavour | Module | Status |
|---|---|---|
| GBNF | `grammars/gbnf.py` (`GBNF_FLAVOUR`) | Production — full `META_GRAMMAR`-equivalent surface (Phase 2 of the Lark cutover) |
| ABNF | `grammars/abnf.py` (`ABNF_FLAVOUR`) | Production — full RFC 5234+7405 surface (Phase 3): `[...]` option, num-seq, comments/line-folding, `%s`/`%i`, `%d`/`%b`, prose-refusal, incremental `=/` |

Both flavours are single flat modules — no `emitter.py`, `escapes.py`, or `meta_grammar.py` submodules, and no `META_GRAMMAR` string anywhere (`gbnf.py`/`abnf.py` are ~1050–1110 lines each: emit actions, self-grammar, reductions, noise map, and the singleton, all in one file).

## Adding a new flavour

1. Create `grammars/<name>.py`.
2. Define a private `_<Name>Escapes(EscapeCodec)` and a public `<NAME>_ESCAPES = _<Name>Escapes()` singleton.
3. Build `<NAME>_ACTIONS: IrTypeMap` covering every grammar AST node type (the emit half).
4. Author `<NAME>_GRAMMAR: IrAst` — the flavour's own grammar, directly as IR (no meta-grammar string; template off the ABNF or GBNF self-grammar).
5. Build `<NAME>_REDUCTIONS: IrMap[IrRuleRef, IrSelf]` + `<NAME>_NOISE` + `<NAME>_REDUCER = Reducer(reductions=..., noise=..., literal=DROP)` (the parse half).
6. Define a private `_<Name>Flavour(IrFlavour)` with all R1 ClassVars set (`actions`, `grammar`, `reducer`, plus metadata) — **no method overrides**.
7. Construct the singleton: `<NAME>_FLAVOUR = _<Name>Flavour()`.
8. Register in `grammars/__init__.py`: import + `register_flavour(<NAME>_FLAVOUR)`.
9. Mirror tests under `tests/unit/lexic/grammars/test_<name>.py`, plus a golden fingerprint integration test (`tests/integration/test_<name>_ir_equivalence.py` — see [[public-api]]). See [[testing]].

No changes to `compile.py`, `lexic.codegen`, or `lexic.parsing` — the engine and the whole IR-native codegen pipeline (`canonical_grammar` → `build_codegen_grammar` → `compute_binding` → `codegen`) are flavour-agnostic.


## Width-aware emission (2026-07-18)

Structure-level emit actions (item/sequence/alternation/rule/ast/rules-tuple)
build layout docs (`lexic.ir.layout`); atoms stay str-tier and lift at the
doc joins. `apply(root, width=88)` renders — `width=None` reproduces the flat
single-line form byte-for-byte. Arms break onto trailing-pipe (GBNF `|`,
EBNF `|`) / trailing-slash (ABNF `/`) continuations at indent 6; each
sequence arm and each wide EBNF class expansion is its own fit group. The
round-trip licence: wrapped emit → parse → canonicalize equals the source
canonical AST (ABNF's wrap is RFC 5234 c-wsp folding).

Three shipped flavours: GBNF, ABNF, EBNF (`grammars/ebnf.py`, ISO-family;
exact repetition spells `n * x` prefix — owned by the item action; open or
bounded counted quantifiers and `IrNot` refuse declaratively). ABNF carries
`ABNF_CORE_RULES` (RFC 5234 B.1) on the new `IrFlavour.core_rules` ClassVar —
consumed by `parse_grammar` as dangling-ref resolution ONLY, to closure,
never overriding a defined name. All three manifests generate from the
shipped singletons (`tools/gen_manifests.py`).
