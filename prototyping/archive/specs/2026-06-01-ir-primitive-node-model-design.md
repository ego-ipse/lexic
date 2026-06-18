# Design — IR primitive node model (the "nodes are their payload" rewrite)

**Date:** 2026-06-01
**Status:** Approved (design); implementation plan to follow.
**Scope:** Full migration of the IR model — grammar-AST nodes *and* the
action-algebra / dispatch layer — to a new node taxonomy. One PR at the end.
Pure port: **no new features**, set-alternation deferred.

---

## 1. Problem

The current IR model's load-bearing `IrNode.__init__(*args, **kwargs)` **masks
type errors**: because the signature accepts anything, `uv run pyright src/
tests/` reports 0 in the project's standard mode even though construction sites
are never actually checked. The moment the mask is removed — a prior attempt,
commit `6c6c2de`, documented in `after_attempt_0/attempt_0_handover.md` — ~174
real errors surface. That attempt then tried to fix them mechanically with a
`dataclass_transform` `converter=` field-specifier; it drove the str/tuple
buckets to zero but **inflamed** a latent variance problem, taking the total to
184. The handover's load-bearing conclusion: the errors are not independent, and
the root is the **type model**, not missing converters.

There are two roots:

1. **Wrapper-field vs construction-value mismatch.** Leaves carry `value: IrStr`
   and collections carry `items: IrTuple[...]`, but call sites pass raw `str` /
   `tuple`, relying on a load-bearing `IrNode.__init__(*args, **kwargs)` +
   `IrType.coerce` to widen at runtime. The declared field type is the
   *post-coercion* type; the constructor's natural input is the *pre-coercion*
   type. pyright only sees the former. The `*args, **kwargs` signature hid the
   mismatch by erasing all type information — masking errors rather than solving
   them. (155 / 174 errors: 85 `str→IrStr`, 70 `tuple→IrTuple`.)

2. **Generic variance.** `IrSelf[Ir_co]` / `IrAtom[Ir_co]` are invariant. The
   moment strict inference is enforced, `IrLiteral`/`IrCharClass`/`IrRuleRef`
   stop being assignable to `IrItem.atom: IrAtom`, and pyright shows
   `IrAtom[IrSelf[Unknown]]` everywhere. This is the bucket that exploded
   (~4 → 133) when the converter trick tightened inference.

The fix is not "coerce better." It is to make **the node be its payload** so
there is nothing to coerce, and to make the generics **covariant** so the
variance noise disappears.

## 2. Goals / non-goals

**Goals**
- One coherent node model; pyright clean (project standard mode) on `src/` and
  `tests/` with **no** `# type: ignore` / `# pyright: ignore` / `# noqa` /
  `# pylint: disable`. The 0 is meaningful precisely because the masking
  `__init__` is gone — honest per-field signatures, nothing hidden. (Strict mode
  is out of scope: it surfaces ~1264 pre-existing untyped-test-helper errors.)
- Remove the coercion apparatus entirely (`IrType.coerce`, `_ir_field_types`,
  the load-bearing `IrNode.__init__`, `__post_init__` coercion).
- Preserve all behaviour: full test suite green; round-trip fidelity intact.
- Migrate the action-algebra / dispatch layer (`ir/action.py`, `ir/walk.py`)
  onto the same model.

**Non-goals (explicitly deferred)**
- **Set-alternation** (`IrFrozenSet` / `IrSetAlternation`) and its content-hash
  interning. The variadic base is built so it slots in later without rework, but
  it is not built now.
- `IrKeyed`'s content-keying machinery (`key_of` / `keyed`) — only needed by
  set-alternation; deferred with it.
- `IrInt` — no current node needs an int leaf (`IrQuantifier` bounds are plain
  `int` fields on a dataclass).
- Any new emitter/flavour/grammar capability.

## 3. The model

### 3.1 Spine (marker layers — no instance state, `__slots__ = ()`)

```
IrSelf[Ir_co]            generic root. Ir_co is return-position only, so PEP 695
                          infers it COVARIANT — this is the variance fix.
                          Methods: __call__(d,n,nc) -> Self   (identity)
                                   eval(d,n,nc) -> Ir_co       (value protocol)
                                   children() -> Sequence
                                   rebuild(new_children) -> Self
                                   bound / bind                (see 3.4)
 ├ IrNode[Ir_co]          ABC marker; __repr__-is-codegen
 │   ├ IrLeaf[Ir_co]       children()=(); rebuild()=self
 │   │     └ IrStr, plus the zero-field plain classes (IrPass/IrWalk/IrEmit/IrRebuild)
 │   ├ IrTuple[T]          variadic primitive (IrNode, tuple); children() = self
 │   └ IrComposite         THE dataclass base — EVERY dataclass node extends it
 ├ IrAtom                 NON-generic role marker, mixed into atoms
 └ IrNone                 @final absence singleton (IS-A IrSelf)
```

**There is no `IrCollection`.** The variadic-homogeneous role is served
entirely by `IrTuple` subclasses; every fixed-arity dataclass record — whether
it has child nodes or not — extends `IrComposite`. `IrComposite` declares its
child slots via `_child_attrs`; a record with no IR-node children (e.g.
`IrField`, `IrCallable`) declares `_child_attrs = ()` and is effectively a
"record leaf" while still being an `IrComposite`. The only nodes *not* under
`IrComposite` are the C-type primitives (`IrStr`/`IrTuple` subclasses) and the
zero-field plain classes.

- **`IrAtom` is non-generic** and added by plain multiple inheritance. This is
  the whole variance fix for the atom family: `IrItem.atom: IrAtom` accepts any
  `IrAtom` subclass trivially. No `register()`, no `__subclasshook__`, no
  `type: ignore`. `isinstance(lit, IrAtom)` is genuinely true via the MRO at
  zero runtime cost. (Verified: `after_attempt_0/tst1.py`/`tst2.py`/`tst3.py`.)
- **`IrNone`** mirrors `None`/`NoneType`: `IrNoneType` is a public `@final`
  singleton class, and `IrNone = IrNoneType()` is the value callers pass bare.
  It IS-A `IrSelf`, and all dispatch slots (`d`, `n`, `nc`, and `Ir_co`) are
  typed `IrSelf`, so `IrNone` fits every slot without a `| None` union. Use
  `IrNoneType` for `isinstance`/annotations.

### 3.2 The three tiers

> **The rule:** C-type primitives only where there are **no named heterogeneous
> fields**. Everything with named fields is a frozen-slotted `@dataclass`.
> Zero-field nodes are plain `__slots__=()` classes.

| Tier | Nodes | Rationale |
|---|---|---|
| **`IrStr` subclass** (+`IrAtom`) | `IrLiteral`, `IrCharClass`, `IrRuleRef` | one homogeneous payload — the string itself. Native eq/hash. |
| **`IrTuple` subclass** (variadic, no named fields) | `IrSequence`, `IrAlternation` | genuinely *are* a tuple of children. Native eq/hash, `repr`-is-codegen, trivial `children()`/`rebuild()`. (Only the grammar AST collections — action operators are composites.) |
| **frozen-slotted `@dataclass`** (all extend **`IrComposite`**) | `IrItem`, `IrRule`, `IrQuantifier`, `IrGroup`(+`IrAtom`), `IrNot`(+`IrAtom`), `IrAst`, `IrJoin`, `IrCond`, `IrAction`, `IrField`, `IrChild`, `IrChildren`, `IrCallable`, `IrRaise`, `IrReturn`, `IrDispatch` | fixed-arity, named, heterogeneous. Dataclass is the only construct giving **pyright-visible typed named fields** with no boilerplate — and is *leaner* than a tuple for small N (measured 48 B vs 64 B). Every one of these IS-A `IrComposite`. |
| **plain `__slots__=()` class** | `IrPass`, `IrWalk`, `IrEmit`, `IrRebuild`, `IrNone` | zero fields — nothing to store; cheapest of all. |

**`NamedTuple` appears nowhere.** Verified (`after_attempt_0/tst4.py`):
`typing.NamedTuple` can only co-inherit `Generic` (`TypeError: can only inherit
from a NamedTuple type and Generic`), so it can never be an `IrNode`/`IrAtom`;
and the structural-Protocol workaround destroys the `IrAtom` marker (every node
matches a structural marker). The `IrAtom` role only survives nominally.

**Why dataclasses are not a regression to the current model:** dataclass fields
are now **plain Python scalars** (`name: str`, `min: int`, `max: int | None`,
`target_type: type`) and **real child nodes / `IrTuple`s** — never `IrStr` /
`IrTuple[...]` *wrapper* fields. There is nothing to coerce; the generated
`__init__` is honest. The two coercion buckets are absorbed by the primitive
tiers (str-leaves, variadic tuples) at the source.

### 3.3 Removed / retained

**Removed**
- `IrType` / `IrType.coerce` / `IrStr.coerce` / `IrTuple.coerce`
- `IrNode._ir_field_types`
- the load-bearing `IrNode.__init__(*args, **kwargs)` and all `init=False`
- `__post_init__` coercion passes
- `IrStrLeaf` (leaves subclass `IrStr` directly — `.value` is the string itself)
- `IrCollection` (variadic role served by `IrTuple` subclasses; all dataclass
  records extend `IrComposite` instead)
- the debug-string cascade `_str_name` / `_str_opener` / `_str_closer` /
  `_inner_str` / `__str__` → replaced by **`__repr__`-is-codegen**

**Retained**
- `bound` / `_bound` / `bind` — *only* so generic action nodes can materialise
  their `Ir_co` (e.g. `IrField` building an `IrStr` from a raw attribute,
  `IrConcat` seeding a join with the neutral element). `_bound` is still read
  from the TypeVar bound in `__init_subclass__`. This is the legitimate
  surviving use; it is **not** coercion.
- `IrDispatch`'s memoised `_resolve_cache` (mutable dict on a frozen dataclass,
  set via `object.__setattr__`, mutated in place — current behaviour preserved).

### 3.4 Protocol mechanics

- **Construction.** Primitives use `def __new__(cls, …) -> Self: return
  super().__new__(cls, payload)`. The return annotation **must** be `-> Self` —
  a hardcoded concrete return (`-> "IrStr"`) collapses every subclass to the
  base type and strips role membership (this was the `tst1.py` bug). Dataclasses
  use their generated `__init__`.
- **`children()`** — `IrTuple` subclasses return `self`; dataclass composites
  return their `_child_attrs` in order; leaves return `()`.
- **`rebuild(new_children)`** — `IrTuple` → `type(self)(*new_children)`;
  composite → `dataclasses.replace` zipping `_child_attrs`.
- **`eval`** — value-producing nodes override; identity nodes inherit
  `__call__ -> Self`.
- **`__repr__`-is-codegen** — `repr(node)` reproduces its constructor call
  (`IrAlternation(IrSequence(...), ...)`). `str()` of a str-leaf returns the raw
  payload (it IS-A `str`). The old `__str__`-cascade emission path that
  `IrEmit` relied on (`IrLiteral(str(n))`) is re-expressed against `repr` /
  the node's canonical form.

## 4. Node inventory (field shapes)

Grammar AST:

| Node | Tier | Shape |
|---|---|---|
| `IrLiteral` | `IrStr`+`IrAtom` | the decoded literal string |
| `IrCharClass` | `IrStr`+`IrAtom` | the canonical POSIX interior |
| `IrRuleRef` | `IrStr`+`IrAtom` | the rule name |
| `IrSequence` | `IrTuple` | items (`IrItem`s) |
| `IrAlternation` | `IrTuple` | arms (`IrSequence`s) |
| `IrQuantifier` | `IrComposite` | `min: int`, `max: int \| None` |
| `IrAst` | `IrComposite` | `rules: IrTuple`, `start: str` |
| `IrGroup` | `IrComposite`+`IrAtom` | `body: IrAlternation` |
| `IrNot` | `IrComposite`+`IrAtom` | `body: IrAtom` |
| `IrItem` | `IrComposite` | `atom: IrAtom`, `quantifier: IrQuantifier` |
| `IrRule` | `IrComposite` | `name: str`, `body: IrAlternation` |

Action algebra / dispatch:

| Node | Tier | Shape |
|---|---|---|
| `IrField[Ir_co: IrStr]` | `IrComposite` (no children) | `name: str`; `eval` reads `getattr(n,name)`, wraps via `bound` |
| `IrCallable[Ir_co]` | `IrComposite` (no children) | `handler: Callable` (identity eq) |
| `IrChild[Ir_co]` | `IrComposite` (no children) | `name: str` |
| `IrChildren[Ir_co]` | `IrComposite` (no children) | `name: str` |
| `IrConcat[Ir_co: IrStr]` | `IrComposite` | `parts: IrTuple`; `eval` joins via `bound` |
| `IrJoin[Ir_co: IrStr]` | `IrComposite` | `parts: IrTuple`, `separator`, `empty` |
| `IrCond[Ir_co]` | `IrComposite` | `field: str`, `then_op`, `else_op` |
| `IrReturn[Ir_co]` | `IrComposite` + `_Return` | `value` (BaseException — cannot be a tuple) |
| `IrPass`/`IrWalk`/`IrEmit`/`IrRebuild` | plain class | no fields |
| `IrRaise[Ir_co]` | `IrComposite` (no children) | `exc_type: type`, `message: str` |
| `IrAction[Ir_co]` | `IrComposite` | `target_type: type`, `body` |
| `IrDispatch[Ir_co]` (+ `IrVisitor`/`IrTransformer`/`IrEmitter`) | `IrComposite` | `actions: tuple[IrAction,...]`, `default`, mutable `_resolve_cache` |

Note: `IrConcat` is an `IrComposite` holding `parts: IrTuple` (like `IrJoin`),
**not** an `IrTuple` subclass — the generic-`+`-tuple-subclass form is not
pyright-clean (its dual generic lineage breaks `bound`; verified in
`after_attempt_0/tst5.py`). The line is therefore: **only the grammar AST
collections (`IrSequence`, `IrAlternation`) are `IrTuple` subclasses; every
action operator is an `IrComposite`.**

## 5. Consumer impact

The node-identity change ripples through every IR consumer. Characterised, not
yet enumerated to the line (the implementation plan does that):

- **~50 `.value` reads** on str-leaves across `src/lexic` (`base.py`,
  `ir/derive.py`, `ir/naming.py`, `ir/charclass.py`, flavours, codegen). Each
  becomes direct use of the node as a `str` (the leaf IS-A `str`). No `.value`
  accessor is added (one-way-per-task: avoid a redundant property).
- **~53 `arms=` / `items=` / `value=` construction sites** collapse to variadic
  / direct construction: `IrAlternation(seq1, seq2)`, `IrLiteral("x")`,
  `IrSequence(*items)`.
- **`RuleSpec`** (`ir/spec.py`): `items: list[IrItem | IrAlternation]` keeps its
  shape; only the element node identities change. `to_ir_rule()` updates to the
  new constructors.
- **Flavours** (`grammars/flavour.py`, `gbnf`, `abnf`): action tables and any
  `IrField`/`IrConcat`/`IrJoin` bodies move to the new shapes; `IrEmit`'s
  fallback re-expressed against `repr`/canonical form.
- **`codegen/`, `parsing/`, `base.py`**: updated to the new constructors and the
  `.value`→str change.

## 6. Migration plan (Approach 1 — clean break, one PR)

Rejected alternatives: a dual-tree adapter (the adapter *is* a coercion layer —
the exact smell we are removing) and vertical slices by node family (families
interlock; partial states leave mixed-identity trees that don't type-check).

Single working branch, **no compatibility shim**, sequenced bottom-up:

1. **Core** — rewrite `ir/nodes.py` (spine + three tiers), then `ir/action.py`,
   then `ir/walk.py`. The core is cohesive; it is rewritten as one unit.
2. **IR consumers** — `ir/spec.py`, `ir/derive.py`, `ir/naming.py`,
   `ir/charclass.py`, `ir/emit.py`, `ir/escapes.py`, `ir/directives.py`,
   `ir/topo.py`, `ir/regex_portable.py`.
3. **Flavours** — `grammars/flavour.py`, `grammars/gbnf/`, `grammars/abnf/`.
4. **codegen / parsing** — `codegen/`, `parsing/lark_builder.py`,
   `parsing/meta_parser.py`, `parsing/transformer/`.
5. **Runtime** — `base.py`, `compile.py`, `parse.py`, `generate.py`.
6. **Tests** — the structural-mirror test tree (`tests/unit/lexic/` etc.).

Full green (pyright 0 + `uv run pytest tests/ -q`) is re-achieved when core +
consumers land together. Because of the long non-green window, **the spec is the
contract**: tests are written against the documented node shapes and protocol,
so test authoring can proceed (and be handed to subagents) against the contract
rather than against a half-migrated tree.

`mechanical`: run `tools/auto_fix.sh` before any manual lint pass. Template
issues in generated output are fixed in `codegen/model_emitter.py`, never in
`generated/`.

## 7. Testing strategy

- **Structural mirror preserved**: any source file created/moved/renamed/deleted
  gets the identical treatment in `tests/unit/lexic/`.
- **Node-model unit tests** assert the contract directly: tier membership
  (`isinstance(IrLiteral("x"), (str, IrAtom, IrNode))`), variadic construction
  (`IrAlternation(a, b) == IrAlternation(a, b)`, order significant), `__new__ ->
  Self` subtype preservation, `children`/`rebuild` round-trips, `repr`-is-codegen.
- **Variance / pyright** is itself a gate: the migration is not done until
  `uv run pyright src/ tests/` is clean with no suppressions.
- **Behavioural invariants** unchanged: round-trip
  (`parse(text, grammar).to_text() == text`), cross-flavour, full round-trip,
  layering-invariant, property/hypothesis suites all stay green.

## 8. Risks & open questions

- **`repr`-is-codegen for str-leaves vs native `str.__repr__`.** A str subclass'
  default `repr` is `'x'`, not `IrLiteral('x')`. `__repr__` must be defined on
  the str-leaves to reproduce the constructor call; confirm nothing depends on
  the bare-string repr.
- **`IrEmit` fallback.** It currently does `IrLiteral(str(n))` using the
  `_str_name` cascade. With that cascade removed, define the canonical emission
  form it falls back to (likely unreachable in practice since flavours register
  all actions, but must be correct).
- **`IrReturn` as `BaseException` + dataclass.** Confirm the frozen dataclass +
  `BaseException` mix initialises `args` correctly (current `__post_init__`
  calls `BaseException.__init__`); no tuple layout conflict because it is *not* a
  tuple.
- ~~**Generic action nodes as tuple subclasses.**~~ **RESOLVED:** a generic
  `+` `IrTuple`-subclass node is *not* pyright-clean — the dual generic lineage
  (`Ir_co` vs inherited `IrTuple[IrSelf]`) breaks `bound` (`IrSelf[Unknown]` has
  no `join`; verified `tst5.py`). `IrConcat` is therefore an `IrComposite`
  holding `parts: IrTuple`, identical in shape to the pyright-clean `IrField`.
  `_bound` is derived from each class's **own** `__type_params__` (never the MRO
  walk), with an explicit class-level `_bound` taking precedence — also verified
  in `tst5.py`.

## Appendix — evidence trail

In `after_attempt_0/` (untracked; clear before final PR if desired):

- `tst1.py` — reproduces the subtype-collapse bug: `-> "IrStr"` makes
  `IrLiteral("x")` register as `IrStr`, failing `foob: IrAtom = IrLiteral(...)`.
- `tst2.py` — four `__new__` patterns; **all** pyright-clean once annotated
  `-> Self` (including bare `str.__new__`).
- `tst3.py` — named-tuple node feasibility + the memory/eq/hash benchmark
  (tuple 64 B / faster eq+hash; dataclass 48 B / smaller); `IrGroup(IrTuple,
  IrAtom)` MRO works; pyright-clean.
- `tst4.py` — `NamedTuple` cannot inherit `IrNode` (TypeError); structural
  Protocol destroys the `IrAtom` marker. `NamedTuple` ruled out.
- `nodes_v2.py`, `ir_alternation_keyed.py` — the original direction sketches.
