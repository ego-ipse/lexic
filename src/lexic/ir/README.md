# `lexic.ir` — the IR substrate

`ir` is the single intermediate representation every other package reads and
writes: grammar ASTs, the action algebra, the dispatcher, and the
compiled-model spine all live here. It is a **leaf** — it imports nothing from
`lexic.grammars`, `lexic.parsing`, `lexic.compile`, or the runtime — so the
whole system has exactly one shared vocabulary and one set of node semantics.
The premise: *everything is an `IrSelf`*. A grammar node, an action body, a
dispatcher, and a compiled model instance are all the same kind of thing —
walkable, dispatchable, evaluable — so one substrate carries all of them.

## 1. The primitive-node model — a node IS its payload

There are **no** `.value` / `.items` / `.arms` accessors. Every node subclasses
a Python primitive and *is* that value, across three tiers:

| Tier | Base (subclasses) | Read as | Examples |
|---|---|---|---|
| value-leaves | `IrScalar` → `IrStr`/`IrInt` (`str`/`int`) | the scalar itself | `IrLiteral`, `IrCharClass`, `IrRuleRef`, `IrOp` |
| variadic | `IrTuple`/`IrSeq` (`tuple`) | iterate/index the node | `IrSequence`, `IrAlternation` |
| records | `IrNamedTuple` (fixed-arity) | `rec.field` **or** `rec[i]` | `IrItem`, `IrQuantifier`, `IrRule`, `IrAst` |

Leaves are their string/int (`IrLiteral("x") == "x"`, usable as a dict key);
variadic nodes are their children tuple (`for arm in alt`, `seq[0]`); records
are `dataclass_transform`-decorated named tuples where storage *is* the tuple
and each annotation names a field in declaration order. Construction coerces
(`IrItem(IrLiteral('a'))` lifts to the full shape); reprs are valid codegen
and elide trailing default-valued fields.

**Equality is type-aware.** Distinct leaf kinds never compare equal
(`IrLiteral("x") != IrRuleRef("x")`) so structural tree equality, hashing,
`@cache`, and set/dict keys stay honest — yet a leaf still matches its plain
primitive. `IrRule.__eq__`/`__hash__` exclude `semantic` (compile-channel
metadata), which is what keeps the flavour self-hosting fixpoint.

## 2. Everything is callable and evaluable — the action protocol

Every node carries `eval(d, n, nc) -> Ir_co` and identity `__call__`.
`IrSelf[Iri, Ir_co]` is the generic root: `Iri` the input node type, `Ir_co`
the covariant return; `_bound` is auto-derived from the last own type
parameter. **Absence** is the singleton `IrNone` (of `@final IrNoneType`) —
never Python `None`; it IS-A `IrSelf`, so it fits every dispatch slot and keeps
signatures union-free (`isinstance` against `IrNoneType`, compare `x is
IrNone`). A **truth value is `IrInt ∈ {0, 1}` — there is no `IrBool`.**

The action algebra (`action.py`, `operators.py`) is how transformations are
*written as data*: `IrField` (reads a typed attribute), `IrCompare`/`IrAnd`
(→ `IrInt`), `IrOp` (an infix-operator leaf — no `Cmp` enum), `IrConcat`/
`IrJoin` (build strings), `IrChild`/`IrChildren`, `IrCond` (branch on a test),
`IrThis` (identity), `IrReturn` (short-circuit / find-first), and
`IrAction(target_type, body)` (bind a node type to a body). Default bodies:
`IrPass`/`IrWalk`/`IrRaise`/`IrEmit`/`IrRebuild`. `IrLambda` is the procedural
escape hatch — permitted compile-side, but not in flavour reduction algebra.

## 3. Dispatch (`walk.py`) — one dispatcher, open tables

`IrDispatch[Iri, Ir_co]` is an `IrCachingTuple` of `(actions, default)` —
`actions` an `IrTypeMap` (concrete-first MRO type→`IrAction` table). It does
**not** walk children automatically; action bodies own recursion. Resolution
is one `getattr` per `type(n).__mro__` entry, falling back to `default` only on
a full miss. Entry seams: `eval(d, n, nc)` (protocol) and `apply(root)`
(façade). Presets:

- `IrVisitor` (default `IrWalk`), `IrTransformer` (default `IrRebuild`),
  `IrEmitter` (default `IrEmit`) — the general selective walkers.
- `IrBottomUp` (default `IrThis`) — an **iterative post-order** transformer
  (explicit stack, depth-independent): children transform first, the node
  rebuilds, then its body runs as a pure per-node combiner. Every whole-tree
  normal-form pass runs on it; a body cannot skip a subtree, so selective
  rewrites stay on `IrTransformer`.

New IR node types extend the table; the dispatcher needs no subclassing. Every
per-atom-type table carries an explicit `raise UnsupportedConstructError`
default — never a silent `pass` or bare `None`.

## 4. Canonicalization (`canonical.py`)

`canonicalize(IrAst) → IrAst` is the language-preserving normal form two
flavours of the *same* language converge on: char-class / alternation /
literal-run merges, `IrNot` → positive spans, name folding, canonical rule
order. It runs on `IrBottomUp` and is the mandatory second stage of
`compile.canonical_grammar`.

## 5. Models live here too

`GrammarModel` (in `lexic.base`) is an `IrNamedTuple` — a compiled model IS an
`IrSelf` record: walkable (`children()` = bound fields in item order),
dispatchable (the emit-action `IrTuple` catch-all reaches it), hashable, with
the tuple surface (iteration, `len`, indexing) part of its API. This is why the
visualization layer and the emitters can treat grammar and instances with one
mechanism.

## 6. Package layout

```
ir/
  base.py        IrSelf root; the three-tier spine (IrScalar, IrTuple/IrSeq,
                 IrNamedTuple/IrCachingTuple); IrNone; IrLambda
  nodes.py       grammar-AST nodes: IrLiteral, IrCharClass (intrinsic members()/
                 pattern()/sample()/complement()), IrRuleRef, IrSequence,
                 IrAlternation, IrQuantifier/IrRange, IrItem, IrRule, IrAst
  operators.py   IrOp infix leaf, IrNot, IrEq, IrAnd
  action.py      the action algebra + default bodies (§2)
  mapping.py     IrMap / IrTypeMap (concrete-first MRO) / IrMultiMap
  walk.py        IrDispatch + IrVisitor/IrTransformer/IrEmitter/IrBottomUp (§3)
  canonical.py   canonicalize — the normal form (§4)
  bind.py        IrBind(item, mode, semantic) + BIND_MODES
  flavour.py     IrFlavour ABC — an IrEmitter + ClassVars, zero parsing methods
  order.py       RuleOrder — deterministic start-first ordering
  escapes.py     EscapeCodec ABC + CANONICAL_ESCAPES
  meta.py        IrMeta (dataclass-transform + auto _bound) + singleton metaclasses
```

## 7. Invariants

- **A node is its payload.** No `.value`/`.items`/`.arms`; leaves are
  `str`/`int`, variadic nodes are tuples, records are named tuples.
- **Everything is an `IrSelf`** — grammar, actions, dispatch, and models — so
  one substrate walks all of them.
- **Type-aware equality**, repr-is-codegen, `IrNone` for absence, `IrInt` for
  truth (no `IrBool`).
- **Open dispatch.** Behaviour lives on nodes (intrinsic) or on open
  `IrDispatch`/`IrTypeMap` tables with a raising default; consumers avoid
  closed `isinstance` ladders.
- **`ir` is a leaf.** It imports no other `lexic` package.

See [`.wiki/lexic/ir-shapes.md`](../../../.wiki/lexic/ir-shapes.md),
[`.wiki/lexic/architecture.md`](../../../.wiki/lexic/architecture.md),
[`.wiki/lexic/decisions.md`](../../../.wiki/lexic/decisions.md).
