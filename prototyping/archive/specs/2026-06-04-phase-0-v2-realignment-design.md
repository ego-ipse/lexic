# Phase-0 realignment to the V2 primitive node model — design

**Status:** reconciliation design. The V2 primitive-node migration
(`2026-06-01-ir-primitive-node-model.md`) **landed before** the Phase-0a
algebra plan (`2026-05-29-phase-0a-algebra-expansion.md`) was implemented.
The Phase-0a plan and the Phase-0 / umbrella specs were all written against the
pre-V2 node model and now reference removed machinery. This document re-derives
Phase-0a against the **real landed V2 code** and pins the destination changes for
the Phase-0 spec's §0b/§0c, so the three planning documents can be brought back
into agreement.

**This authorizes documentation work only:** rewriting one plan and updating two
specs. No `src/` change is in scope here — the algebra it describes is built
later, by the rewritten Phase-0a plan.

---

## 1. Why realignment is needed

The V2 migration rewrote the node substrate. The Phase-0a plan and the Phase-0
spec assume the old substrate at every turn:

| Old assumption (in the stale docs) | V2 reality (in `src/`) |
|---|---|
| `IrType` base with `coerce` + neutral element | **gone** — primitives are `IrStr(IrLeaf, str)` etc.; type-safety is `bound`/`bind`, not `coerce` |
| `IrInt(IrType, int)` with single-arg `coerce` | would be `IrInt(IrScalar, int)`, no `coerce` |
| `IrField` gains an `out` field of type `type[IrType]` | landed `IrField[Iri, Ir_co: IrStr]` wraps via `self.bound`; needs a corrected `out` (see §3) |
| `IrAnd(IrCollection[IrInt])` + `_items_attr` | `IrCollection`/`_items_attr` **gone** — variadic nodes subclass `IrTuple` |
| `IrCond(field: str)` | still `field: str` in `src/` — generalization stands |
| single-param generics | everything is two-param `IrSelf[Iri: IrSelf, Ir_co]` |
| Task-6 patches specific CLAUDE.md lines | CLAUDE.md was already rewritten for V2 — those targets are gone |

Two facts verified against the landed code, not the V2 plan:

- The landed code drifted **past its own V2 plan**: `IrSelf` carries two type
  parameters (`Iri`, `Ir_co`), and `IrThis` / `IrReturn.lazy_eval` exist. The
  rewrite must target the code, not the V2 plan.
- `IrCond` has **zero callers** in `src/` (only its definition + export). The
  "no back-compat shim" claim still holds. `IrField` is only ever called as
  `IrField("name")` (reads a rule name → `IrStr`); no caller subscripts it for
  non-string output.

---

## 2. Scope — three documents

1. **Rewrite** `docs/superpowers/plans/2026-05-29-phase-0a-algebra-expansion.md`
   in full, against real V2 code (§3 shapes, §5 testing).
2. **Re-derive** `docs/superpowers/specs/2026-05-29-phase-0-honest-ir-foundation-design.md`:
   §0a to the V2 algebra (§3 here); §0b/§0c destinations to V2 vocabulary (§4).
3. **Patch** `docs/superpowers/specs/2026-05-29-lark-full-coverage-umbrella-design.md`:
   stale concrete refs only (`nodes.py:505` line numbers, "exactly 11 node
   types", coercion language). The architecture arc is unchanged.

---

## 3. Re-derived 0a algebra (the node shapes)

### 3.1 Value tier — new `IrScalar` marker

A **pure marker** base (no `coerce`, no neutral element, no behavior) names the
"constructible-from-a-Python-scalar value leaf" category. It is *not* a revival
of `IrType` — `IrType` carried coercion and a neutral element; `IrScalar` carries
nothing. `IrStr` re-parents onto it; `IrInt` is the new sibling.

```python
class IrScalar(IrLeaf):
    __slots__ = ()

class IrStr(IrScalar, str):        # was: IrLeaf, str
    __slots__ = ()
    _bound: ClassVar[type[str]] = str
    # type-aware __eq__ retained (distinct str-leaf kinds never equal)

class IrInt(IrScalar, int):        # new
    __slots__ = ()
    _bound: ClassVar[type[int]] = int

    def eval(self, _d: IrSelf, _n: IrSelf, _nc: Sequence[IrSelf], /) -> Self:
        return self   # self-evaluating constant
```

`IrInt` uses **native int equality** — there are no sibling int-leaf kinds to
disambiguate, so the type-aware `__eq__` that `IrStr` needs is not required here.

### 3.2 `IrField` — revive the runtime `out` field

PEP 695 type parameters are **erased at runtime**: `_bound` is fixed at
class-definition from the declared TypeVar bound (`IrStr`), so a subscript like
`IrField[IrInt]("min")` still constructs `IrStr`. To read a non-string attribute
the output constructor must be a **runtime value**, not a type parameter. The old
plan's `out` field was the correct mechanism; only its type (`type[IrType]`) was
wrong. Corrected to `type[Ir_co]` bounded by `IrScalar`:

```python
@dataclass(frozen=True, slots=True, repr=False)
class IrField[Iri: IrSelf, Ir_co: IrScalar = IrStr](IrComposite[Iri, Ir_co]):
    name: str
    out: type[Ir_co] = IrStr      # runtime constructor; default keeps IrField("name") callers unchanged

    def eval(self, _d: Iri, n: Iri, _nc: Sequence[Iri], /) -> Ir_co:
        return self.out(getattr(n, self.name))   # IrField("min", IrInt) → IrInt(3)
```

`IrField` stops using `self.bound`; `out` supersedes it. `bound`/`bind` remain in
use by `IrConcat`/`IrJoin`/`IrEmit`, unchanged.

### 3.3 `Cmp` enum + `IrCompare`

```python
class Cmp(Enum):
    EQ = "=="; LT = "<"; GT = ">"

_CMP_OPS = {Cmp.EQ: operator.eq, Cmp.LT: operator.lt, Cmp.GT: operator.gt}

@dataclass(frozen=True, slots=True, repr=False)
class IrCompare[Iri: IrSelf](IrComposite[Iri, IrInt]):
    _child_attrs: ClassVar[tuple[str, ...]] = ("left", "right")
    left: IrNode
    op: Cmp
    right: IrNode

    def eval(self, d: Iri, n: Iri, nc: Sequence[Iri], /) -> IrInt:
        l = self.left.eval(d, n, nc)
        r = self.right.eval(d, n, nc)
        return IrInt(1) if _CMP_OPS[self.op](l, r) else IrInt(0)
```

### 3.4 `IrAnd` — an `IrTuple` subclass

`IrAnd` IS its operand tuple ("nodes are payload"). This requires `IrTuple` to
stop over-narrowing `eval`.

**`IrTuple` gains a result type parameter.** The eval protocol on `IrSelf` is
already `-> Ir_co`; `IrTuple` currently *overrides* it to `-> Self` for its
rebuild-collections. Replace that with an explicit result parameter so rebuild
collections keep precise typing while reducers (`IrAnd`) declare their own
result:

```python
class IrTuple[T: IrSelf, R: IrSelf = IrSelf](IrNode, tuple):
    _bound: ClassVar[type[tuple]] = tuple
    def eval(self, d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> R: ...

class IrSequence(IrTuple["IrItem", "IrSequence"]): ...        # R = self-shape (precision kept)
class IrAlternation(IrTuple["IrSequence", "IrAlternation"]): ...
class IrAnd(IrTuple[IrNode, IrInt]):                          # R = IrInt
    __slots__ = ()
    def eval(self, d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> IrInt:
        for part in self:
            if not part.eval(d, n, nc):
                return IrInt(0)
        return IrInt(1)
```

**Implementation nuance for the plan (flagged, not solved here):** the base
`IrTuple.eval` body returns `type(self)(*…)`, which is `Self` — not provably `R`
in the *base* generic. The plan must resolve this cleanly (a narrow cast in the
base, or the rebuild collections re-stating eval) **without** a `# type: ignore`.

### 3.5 `IrCond` — generalize `field: str` → `test: IrNode`

Zero callers, so no shim. `_child_attrs = ("test", "then_op", "else_op")`;
branch on `bool(self.test.eval(d, n, nc))`. The `test` is any node whose `eval`
yields a truthy/falsy value (`IrCompare`, `IrAnd`).

### 3.6 No `IrBool`; deferred `IrRanged`

A truth value is `IrInt` in the domain `{0, 1}` — a type-level fact, no runtime
carrier. `IrOr` / boolean-`NOT` are not built (no Phase-0 consumer). `IrRanged`
(the runtime bounded value: unified complement-negation + Slice-C constraint
codegen) stays a recorded, unbuilt deferral — `IrInt → IrRanged` is a lossless
later upgrade. `IrNot` stays grammar-only in Phase 0.

---

## 4. 0b / 0c destination adjustments (spec text; no plans exist yet)

Both destinations survive the V2 migration and become *more* natural under
"nodes are payload"; only their vocabulary changes.

- **0b — honest `IrQuantifier`.** Destination: arity-encoded
  `IrTuple[IrInt, IrQuantifier]` (arity 1 = `[lo, ∞)`, arity 2 = `[lo, hi]`).
  This **also fixes a V2 inconsistency**: landed `IrQuantifier` still carries
  `max: int | None`, contradicting V2's union-free / `IrNone` ethos. So 0b is
  partly a V2-consistency cleanup, not only a feature. Canonical algebraic
  renderer in `ir/canonical.py` as the original 0b spec described.
- **0c — structured `IrCharClass`.** Destination: an `IrTuple`-of-members
  subclass (the old `IrCollection` is gone), retaining `IrAtom` by
  multi-inheritance. Members: `IrChar` (a scalar/str-style leaf) and `IrRange`
  (an `IrComposite`). `NamedSet` defined-but-unbuilt, negation external via
  `IrNot`, order preserved — all as the original 0c spec described.

---

## 5. Testing / verification (carried into the rewritten plan)

- Per-task red→green TDD, but every test targets **real V2 shapes**.
- **Drop only** tests whose exact target was removed by V2 (`IrInt.coerce`,
  `IrField`-with-`out: type[IrType]`, `IrCollection`/`_items_attr`); note each
  removal explicitly (per the "port tests, never delete" rule).
- Add an `IrTuple` result-param regression: `IrSequence`/`IrAlternation` keep
  precise eval typing; `IrAnd` evals to `IrInt`.
- Final gate: full suite green (baseline 474) **and** `uv run pyright src/ tests/`
  clean — no suppressions.

---

## 6. Invariants preserved

- **Grammar is canonical / round-trip fidelity** — 0a adds algebra only; no
  emit behavior changes until 0b/0c consume it.
- **Arrows go one way** — all new ops live in `ir/`; no new runtime→codegen edge.
- **One way per task** — one field-reader (`IrField` with `out`), one comparison
  (`IrCompare`), one conjunction (`IrAnd`); `IrCallable` remains the sole
  sanctioned escape hatch.
- **No regression** — full suite green after each sub-step.
