# Flavour System

**When to load:** adding a new grammar flavour; writing or extending a flavour's emit `actions` or self-grammar/reducer; deciding when to use a procedural `IrCallable` vs pure action algebra.

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

## Emit `actions` shape

A flavour's `actions: IrTypeMap` maps each IR-AST node type to a callable IR body — a concrete-first MRO-resolved table (`ir/mapping.py`), not a plain tuple. The GBNF table is the canonical example (`grammars/gbnf.py`):

```python
GBNF_ACTIONS = IrTypeMap(
    IrAction(IrLiteral,     IrCallable(_gbnf_encode_literal)),
    IrAction(IrCharClass,   IrCallable(_gbnf_charclass)),
    IrAction(IrNot,         IrCallable(_gbnf_not)),
    IrAction(IrRuleRef,     IrField("value")),
    IrAction(IrQuantifier,  IrCallable(_gbnf_quantifier)),
    IrAction(IrItem,        IrConcat(parts=(IrChild("atom"), IrChild("quantifier")))),
    IrAction(IrSequence,    IrJoin(parts=IrChildren("items"), separator=IrLiteral(" "), empty=IrLiteral('""'))),
    IrAction(IrAlternation, IrJoin(parts=IrChildren("arms"),  separator=IrLiteral(" | "), empty=IrLiteral(""))),
    IrAction(IrRule,        IrConcat(parts=(IrField("name"), IrLiteral(" ::= "), IrChild("body")))),
    IrAction(IrAst,         IrCallable(_gbnf_ast)),
)
```

ABNF differs in several notable ways (prefix quantifier ordering on `IrItem`, `%xNN` hex char-class rendering, `IrNot` rejection since ABNF has no native negation, RFC 7405 `%s`/`%i` string markers).

## Parse-side: `grammar` + `reducer`

The other half of a flavour — text → `IrAst` — is not a method at all. It is two ClassVar values that the engine (`lexic.parsing`) drives from the outside:

- **`grammar: IrAst`** — the flavour's own grammar, authored directly as `IrAst` (not parsed from any meta-grammar string; there is no meta-grammar string anymore). `GBNF_GRAMMAR` / `ABNF_GRAMMAR` in `grammars/gbnf.py` / `grammars/abnf.py`. Its structural-noise rules carry `semantic=False` on their own `IrRule`; `<GRAMMAR>.non_semantic` (a derived property) collects their names (see [[ir-shapes]]).
- **`reducer: Reducer`** (`lexic.parsing.reduce.Reducer`, IS-AN `IrDispatch`) — an `IrMap[IrRuleRef, IrSelf]` (`GBNF_REDUCTIONS` / `ABNF_REDUCTIONS`) from a rule's `IrRuleRef` to a body folding that rule's matched children into IR, paired with a noise map (`GBNF_NOISE` / `ABNF_NOISE`) marking which children are structural (whitespace, delimiters, comments) and dropped before a reduction body sees them. The noise map is built *from* `<GRAMMAR>.non_semantic` (the per-rule `semantic=False` flags) — single source of truth (2026-07-03).

`compile_grammar` (`compile.py`) drives this: `parse_reduced(normalize(flavour.grammar), text, flavour.reducer)` (the normalized self-grammar is memoised once per flavour name so the engine's identity-keyed `compile_tables` stays hot). No parser class, no `.for_flavour()` factory — the engine is a free function over any `(IrAst, Reducer)` pair, and a flavour just happens to supply one for parsing *itself*.

R2 (escaping is a rendering feature, not an AST property) still holds: reduction actions decode escapes as render-side data (an `IrMap`/`IrUnradix`-style table), never on the AST node itself; the AST holds neutral, decoded payloads.

## When to use `IrCallable` vs pure algebra

Prefer pure algebra (`IrField`, `IrChild`, `IrChildren`, `IrConcat`, `IrJoin`, `IrCond`) whenever the body is a fixed assembly of attribute reads and string composition. The result is declarative, introspectable, and walks correctly under `IrTransformer`.

Reach for `IrCallable(handler)` when:

- the result requires a Python-level computation no algebra node expresses (e.g. GBNF `_gbnf_quantifier` maps `(min, max)` pairs through a lookup table);
- escape-encoding the literal value needs the flavour's `EscapeCodec` (`_gbnf_encode_literal` calls `GBNF_ESCAPES.encode`);
- a non-trivial control flow is needed (e.g. ABNF's `IrNot` body raises `UnsupportedConstructError` — ABNF has no negation).

`IrCallable` bodies receive `(d, n, nc)` and return `Ir_co`. They should remain small and side-effect-free; if you need recursion into siblings, call `d.eval(d, c, ())` rather than recursing manually.

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

No changes to `compile.py`, `ir/derive.py`, or `lexic.parsing` — the engine, `compile_grammar`, and `derive_specs` are all flavour-agnostic.
