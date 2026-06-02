# Handover — pyright "errors galore" attempt (converter/dataclass_transform)

Status: **abandoned, working tree reverted by user.** This documents what was tried,
what actually worked, what failed, and where the real problem lies — so the next
attempt doesn't repeat the thrash.

## The task
`uv run pyright src/ tests/` reported **174 errors**. Goal: bring them down.

Original breakdown (174):
- **85** — `str` not assignable to `IrStr` (construction sites passing raw `str`)
- **70** — `tuple[...]` not assignable to `IrTuple[...]` (raw tuples)
- **~11** — `_IrNoneSentinel` not assignable to `IrNode` (IrNone in IrNode-typed slots)
- **~12** — `IrCallable` handler param contravariance (handlers typed with concrete params)
- **~4** — `IrNode` not narrowed to `IrAtom`/`IrAlternation`/`IrGroup` at construction seams
- **~1** — `IrAction[Ir_co]` invariance

So **155 / 174 (89%) were the str/tuple "raw input vs declared Ir type" bucket.**

## What was attempted: the `converter` field-specifier trick
The 155 str/tuple errors come from coercion: fields are declared `IrStr` / `IrTuple[X]`
but call sites pass raw `str` / `tuple`, relying on runtime coercion (`__post_init__` +
`IrType.coerce` + `_ir_field_types`). pyright only sees the declared narrow type.

The idea (validated in isolation, **it does work for str/tuple**): a `converter=` field
specifier via `typing.dataclass_transform`, so pyright reads the converter's *input*
type for the `__init__` param and the field's *declared* type for reads.

```python
# src/lexic/ir/_dataclass.py  (was created; reverted)
@overload
def ir_field[I, O](*, converter: Callable[[I], O], default: I) -> O: ...
@overload
def ir_field[I, O](*, converter: Callable[[I], O], default_factory: Callable[[], I]) -> O: ...
@overload
def ir_field[I, O](*, converter: Callable[[I], O]) -> O: ...
def ir_field(*, converter, default=MISSING, default_factory=MISSING):
    kwargs = {"metadata": {"ir_converter": converter}}
    ...
    return dataclasses.field(**kwargs)   # pylint E3701 false positive here

@dataclass_transform(field_specifiers=(ir_field, dataclasses.field))
def ir_dataclass[T](**kwargs) -> Callable[[type[T]], type[T]]:
    def decorate(cls): return dataclasses.dataclass(**kwargs)(cls)
    return decorate

def apply_converters(instance: object, fields: Iterable[dataclasses.Field]) -> None:
    for f in fields:
        convert = f.metadata.get("ir_converter")
        if convert is not None:
            object.__setattr__(instance, f.name, convert(getattr(instance, f.name)))
```

Usage: `name: IrStr = ir_field(converter=IrStr)`,
`items: IrTuple[IrItem] = ir_field(converter=IrTuple[IrItem].coerce, default_factory=IrTuple)`.

### Things proven during this attempt
- pyright accepts raw `str`/`tuple` at call sites AND reads stay narrow (`x.name: IrStr`). **0 errors in isolation.**
- Runtime: stdlib `@dataclass` does **not** run converters (PEP 712 rejected), so coercion must be applied by `apply_converters(self, dataclasses.fields(self))` from a `__post_init__`. Typing it honestly requires the loop be where `self` is a known dataclass (no `Any`, no Protocol with R0903 noise).
- `functools.wraps` on a wrapped `__init__` preserves `inspect.signature` — but the `__post_init__` route avoids wrapping entirely and is cleaner.
- pylint **E3701 (invalid-field-call)** fires on any `dataclasses.field()` call inside a factory. It is a genuine false positive for `dataclass_transform` field-specifier factories. Only honest fixes: project-config disable, or a sanctioned inline `# pylint: disable=invalid-field-call` (the user approved the inline disable "for now").
- `IrStrLeaf` was de-genericized from `value: Ir_co` to `value: IrStr` (no leaf ever specialized `Ir_co`), because a converter returning concrete `IrStr` cannot satisfy a TypeVar-typed field.

## Why it FAILED in the full rollout
Rolling the trick across all IR-node dataclasses took pyright **174 → 184 (worse)**.
- str/tuple buckets did go to **0** (the trick worked).
- BUT the `atom` bucket **exploded ~4 → 133.**

**Root cause of the explosion (the thing that actually matters):** the IR type model's
generics are **invariant and fight the checker.** `IrItem.atom: IrAtom` where `IrAtom`
is generic + invariant. The moment strict generic inference is enforced (which
`dataclass_transform` does, and which parameterizing leaves as `IrAtom[IrStr]` also
does), `IrLiteral`/`IrCharClass`/`IrRuleRef` stop being assignable to `IrItem.atom`,
and pyright shows the param as `IrAtom[IrSelf[Unknown]]`. Every `IrItem(atom=IrLiteral(...))`
in the tests then fails.

Two red herrings chased and discarded (do not repeat):
1. "Only put `@ir_dataclass` on converter-bearing classes" — reduces some strictness but
   does **not** fix the atom explosion.
2. Reverting decorators / imports — moved nothing.

## The real problem (per the user — this is the load-bearing insight)
**The pyright pain is the IR type model's generic-variance design, not missing converters.**
`IrSelf[Ir_co]`, `IrAtom[Ir_co]` invariance, the `IrSelf[Unknown]` that shows up
everywhere — these are the actual root. The converter trick only addressed the str/tuple
*surface* errors and, worse, *surfaced* the latent variance errors by tightening inference.

The 155 str/tuple errors and the ~19 variance/narrowing errors are **not independent**:
tightening the former (via dataclass_transform) inflames the latter. So "fix the 155
mechanically" is the wrong frame. The variance/typing model needs to be addressed
**first or instead.**

## Recommended next direction (not yet attempted)
- Treat the **generic variance of the IR node hierarchy** as the primary problem, not the
  str/tuple coercion. Specifically investigate:
  - Whether `IrAtom` / `IrSelf` should be covariant (`Ir_co` is a return-position type —
    likely should be covariant, declared `Ir_co_co = TypeVar(..., covariant=True)` or
    PEP 695 `[Ir_co]` used covariantly), which would make `IrAtom[IrStr]` assignable where
    `IrAtom` is expected and kill the `atom` family.
  - Whether `IrItem.atom: IrAtom` should be `IrAtom[Any]` / non-generic at the field.
  - The `IrNone`-is-`IrSelf`-not-`IrNode` mismatch (the docstring claims `IrNone` is an
    `IrNode`; the class only extends `IrSelf`) — 11–20 errors.
  - The `IrCallable` handler contravariance — handlers should take `IrSelf` params and
    `isinstance`-narrow (the `_extract_group`/`_extract_none` edits already moved that way).
- Only after variance is sane, decide whether the str/tuple coercion even needs the
  converter trick, or whether covariance alone lets the declared types accept the inputs.

## Process notes (what went wrong in execution)
- Two Sonnet subagents were dispatched for the mechanical rollout; both were unreliable
  (one over-applied per a flawed spec, one bailed mid-task). Net: churn and a misleading
  "184" that took several measurements to interpret.
- A bulk `python3 -` rewrite script was attempted and rejected by the user (correctly —
  opaque, hard to review).
- Lesson: for a problem whose root is a **type-model design question**, do not delegate a
  mechanical rollout before the design is proven end-to-end against the *full* error set
  (src **and** tests). The isolated proof (str/tuple → 0) was real but did not predict the
  atom explosion that only showed at scale.

## Files touched during the attempt (all reverted by user)
- `src/lexic/ir/_dataclass.py` (new) + `tests/unit/lexic/ir/test__dataclass.py` (new)
- `src/lexic/ir/nodes.py` (de-generic `IrStrLeaf.value`, decorators, `ir_field` markings)
- `src/lexic/ir/action.py`, `walk.py`, `derive.py`, `codegen/aliases.py`,
  `grammars/{gbnf,abnf}/flavour.py` (decorator swaps)
- `CLAUDE.md` flavour template, `.wiki/lexic/ir-shapes.md`, `.wiki/log.md` (doc updates)
