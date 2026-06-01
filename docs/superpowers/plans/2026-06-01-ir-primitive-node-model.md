# IR Primitive Node Model — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the coercion-based IR node model with one where nodes *are* their payload — str-leaves subclass `str`, variadic collections subclass `tuple`, fixed-arity records are `IrComposite` dataclasses — eliminating `coerce`, the load-bearing `__init__`, and the variance that produced ~174 pyright errors.

**Architecture:** Clean break, one branch, one PR, no compatibility shim (per spec §6). Bottom-up: the self-contained core (`ir/nodes` → `ir/action` → `ir/walk`) is rewritten first with new contract tests that run green in isolation; consumers are then ported layer by layer, gated by `pyright`; the full behavioural suite is the final gate. The spec is the contract — tests are written against documented node shapes.

**Tech Stack:** Python 3.14, PEP 695 generics, `dataclasses`, `pyright`, `pytest`, `uv`.

**Spec:** `docs/superpowers/specs/2026-06-01-ir-primitive-node-model-design.md`

---

## Conventions for every task

- All commands prefixed `uv run` (project rule). Never bare `pytest`/`ruff`/`pyright`.
- Before any manual lint fix: `tools/auto_fix.sh`.
- No `# type: ignore` / `# pyright: ignore` / `# noqa` / `# pylint: disable` without explicit permission — fix the root cause.
- Docstrings: Sphinx style (`:param:`/`:returns:`/`:raises:`).
- Commits carry **no** `Co-Authored-By` line.
- Test mirror rule: a source file's test lives at the mirrored path under `tests/unit/lexic/`; `__init__.py` modules use `test_init_<pkg>.py`.
- **Preserve docstrings.** Porting/rewriting must carry over the original modules' comprehensive Sphinx docstrings (`:param:`/`:returns:`/`:raises:`) and write full docstrings for new constructs. The terse docstrings in this plan's illustrative code blocks are **not** a license to strip documentation — match (or exceed) the density of the file being rewritten.

### Test handling — port, never delete

**Do not delete tests.** Existing tests are the behavioural contract. For every
test file touched:

- **Port** each existing test by fixing only its *construction syntax* to the
  new node shapes (per the rules table in Phases 4–7), keeping every assertion.
  Examples: `IrAlternation(arms=(a, b))` → `IrAlternation(a, b)`;
  `IrLiteral(...).value` → the leaf used directly as `str`; bare `IrNone` →
  `IrNone()`.
- **Add** the new contract tests shown in each task *alongside* the ported ones —
  they are additions, not replacements.
- The **only** tests removed are those whose exact target is a deliberately
  removed API (`IrType`/`coerce`, `_ir_field_types`, the load-bearing
  `IrNode.__init__`, `IrStrLeaf`, `IrCollection`/`_items_attr`). When a task
  removes such a test, it must say so explicitly — the removal is a conscious
  decision tied to a removed symbol, never silent housekeeping.

## Non-green window (read before starting)

This is a clean-break rewrite. Once Task 1 lands, the *old* consumers and their tests are broken until their port tasks complete. Therefore:

- **Phases 1–3 (core)** each run their own new unit tests green *in isolation* — they only import within `ir/`, which is ported first. These are real red→green TDD tasks.
- **Phases 4–7 (consumers)** cannot run the behavioural suite mid-flight. Their per-task gate is **`uv run pyright <file>`** (the file type-checks against the new nodes) plus updating that file's mirror test to the new shapes.
- **Phase 8** is the single full-green gate: `uv run pyright src/ tests/` clean (no suppressions) **and** `uv run pytest tests/ -q` green.

---

## File structure

No files are added or removed by this migration — it is an in-place rewrite of existing modules. Responsibilities are unchanged; only node identities change.

| File | Change |
|---|---|
| `src/lexic/ir/nodes.py` | rewrite: spine + 3 tiers; remove `IrType`/`coerce`/`IrStrLeaf`/`IrCollection`/load-bearing `__init__` |
| `src/lexic/ir/action.py` | rewrite onto new tiers; keep `bound`/`bind` use |
| `src/lexic/ir/walk.py` | rewrite `IrDispatch` + presets as `IrComposite` |
| `src/lexic/ir/spec.py` | port `RuleSpec`/`to_ir_rule()` constructors |
| `src/lexic/ir/derive.py` | port; `.value`→str, variadic construction |
| `src/lexic/ir/naming.py` | port; `.value`→str |
| `src/lexic/ir/charclass.py` | port; `.value`→str |
| `src/lexic/ir/{emit,escapes,directives,topo,regex_portable}.py` | port as needed |
| `src/lexic/grammars/flavour.py`, `grammars/gbnf/flavour.py`, `grammars/abnf/flavour.py` | port action tables / bodies |
| `src/lexic/codegen/{__init__,aliases,model_emitter}.py` | port |
| `src/lexic/parsing/{lark_builder,meta_parser}.py`, `parsing/transformer/build_transformer.py` | port |
| `src/lexic/base.py`, `compile.py`, `parse.py`, `generate.py` | port |
| `tests/unit/lexic/ir/test_nodes.py` + mirrors | new contract tests + port |

---

# PHASE 1 — `ir/nodes.py` core

### Task 1: Spine — `IrSelf`, `IrNode`, `IrLeaf`, `IrAtom`, `IrNone`

**Files:**
- Modify: `src/lexic/ir/nodes.py`
- Test: `tests/unit/lexic/ir/test_nodes.py`

- [ ] **Step 1: Write the failing test**

First **port** the existing `test_nodes.py` tests: fix construction syntax per the rules table (keep every assertion), and remove only tests targeting deleted symbols (`IrType`/`coerce`, `_ir_field_types`, `IrStrLeaf`), noting each removal in the commit. Then **add** the contract tests below.

```python
# tests/unit/lexic/ir/test_nodes.py  (ADD these alongside the ported existing tests)
from typing import get_type_hints
import pytest
from lexic.ir.nodes import IrSelf, IrNode, IrLeaf, IrAtom, IrNone, IrNoneType


def test_irself_identity_call_returns_self():
    class L(IrLeaf):
        __slots__ = ()
    leaf = L()
    assert leaf(IrNone, IrNone, ()) is leaf


def test_irnone_is_final_singleton_and_is_irself():
    assert IrNone is IrNoneType()           # public value IS the singleton instance
    assert isinstance(IrNone, (IrSelf, IrNoneType))
    # NOTE: @final is a STATIC-only guarantee (pyright flags subclassing); we do
    # NOT assert a runtime TypeError on subclassing — there is no runtime guard.


def test_iratom_is_non_generic_marker():
    # IrAtom has no type parameters of its own
    assert getattr(IrAtom, "__type_params__", ()) == ()
    assert issubclass(IrAtom, IrNode)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/lexic/ir/test_nodes.py -q`
Expected: FAIL (import errors / `IrNone` not callable singleton).

- [ ] **Step 3: Write minimal implementation**

```python
# src/lexic/ir/nodes.py  — spine section
from __future__ import annotations

import functools
import typing
from abc import ABC, abstractmethod
from dataclasses import dataclass, fields, replace
from typing import Any, ClassVar, Self, Sequence, TypeVar, cast, final


class IrSelf[Ir_co: "IrSelf"]:
    """Generic identity root and IR-protocol base. ``Ir_co`` is return-position
    only, so PEP 695 infers it covariant.

    :param Ir_co: the return type of ``eval``.
    """

    __slots__ = ()
    _bound: ClassVar[type]

    def __call__(self, _d: IrSelf, _n: IrSelf, _nc: Sequence[IrSelf], /) -> Self:
        """Identity — return ``self`` typed via PEP 673 ``Self``."""
        return self

    def eval(self, d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> Ir_co:
        """Action-body protocol; default delegates to identity ``__call__``."""
        return cast(Ir_co, self(d, n, nc))

    def children(self) -> Sequence[Ir_co]:
        """Default: no children."""
        return ()

    def rebuild(self, _new_children: Sequence[Ir_co]) -> Self:
        """Default: identity rebuild."""
        return self

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if "_bound" in cls.__dict__:          # explicit _bound wins (IrStr/IrTuple)
            return
        params = cls.__dict__.get("__type_params__", ())   # OWN params only — never MRO
        if params and isinstance(params[0], TypeVar) and params[0].__bound__:
            cls._bound = params[0].__bound__

    @property
    def bound(self) -> type[Ir_co]:
        """Concrete type bound to ``Ir_co`` — used by generic action nodes to
        materialise their result (NOT coercion)."""
        return type(self)._bound

    def bind(self, other: Any) -> Ir_co:
        """Return ``other`` if it satisfies the bound, else raise."""
        if isinstance(other, self._bound):
            return other
        raise TypeError(f"Cannot bind {other!r} to {self!r}")


@final
class IrNoneType(IrSelf):
    """Type of the absence singleton — mirrors ``NoneType``/``None``. ``@final``;
    IS-A ``IrSelf`` so the singleton fits every dispatch slot. Public so it can
    be used in ``isinstance`` / annotations; the value is :data:`IrNone`."""

    __slots__ = ()
    _instance: ClassVar[Self | None] = None

    def __new__(cls) -> Self:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance


IrNone = IrNoneType()  # public singleton VALUE — callers pass bare `IrNone`


class IrNode[Ir_co: IrSelf = IrSelf](IrSelf[Ir_co], ABC):
    """ABC marker for all structural IR nodes. ``__repr__`` is codegen."""

    __slots__ = ()

    @abstractmethod
    def __repr__(self) -> str:
        """Reproduce the constructor call (repr-is-codegen)."""


class IrLeaf[Ir_co: IrSelf](IrNode[Ir_co]):
    """Base for leaves: no children, identity rebuild."""

    __slots__ = ()


class IrAtom(IrNode):
    """NON-generic role marker — mixed into atoms by plain inheritance.

    ``IrItem.atom: IrAtom`` accepts any subclass; ``isinstance(x, IrAtom)`` is
    genuine via the MRO at zero cost.
    """

    __slots__ = ()
```

> NOTE: mirrors `None`/`NoneType`. `IrNoneType` is the public `@final` singleton
> class; `IrNone = IrNoneType()` is the value callers pass bare (no parens) —
> matching the existing codebase, **no churn**. Use `IrNoneType` for
> `isinstance`/annotations. Every dispatch slot is typed `IrSelf` and `IrNone`
> IS-A `IrSelf`, so it fits every slot directly.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/lexic/ir/test_nodes.py -q`
Expected: PASS.

- [ ] **Step 5: Verify pyright on the spine**

Run: `uv run pyright src/lexic/ir/nodes.py`
Expected: 0 errors (partial file may reference not-yet-defined tiers; if so, complete Tasks 2–4 before this gate — see Step note).

- [ ] **Step 6: Commit**

```bash
git add src/lexic/ir/nodes.py tests/unit/lexic/ir/test_nodes.py
git commit -m "ir/nodes: new spine (IrSelf covariant, IrNode/IrLeaf/IrAtom, IrNone @final)"
```

### Task 2: `IrStr` primitive + str-leaves

**Files:**
- Modify: `src/lexic/ir/nodes.py`
- Test: `tests/unit/lexic/ir/test_nodes.py`

- [ ] **Step 1: Write the failing test**

```python
from lexic.ir.nodes import IrStr, IrLiteral, IrCharClass, IrRuleRef, IrAtom


def test_str_leaf_is_str_and_atom():
    lit = IrLiteral("x")
    assert isinstance(lit, str) and isinstance(lit, IrAtom)
    assert lit == "x"                       # native str equality
    assert lit.upper() == "X"               # native str methods


def test_str_leaf_new_returns_own_subtype():
    # the -> Self bug guard: must NOT collapse to IrStr
    assert type(IrRuleRef("r")) is IrRuleRef
    assert isinstance(IrRuleRef("r"), IrAtom)


def test_str_leaf_repr_is_codegen():
    assert repr(IrLiteral("x")) == "IrLiteral('x')"
    assert repr(IrCharClass("0-9")) == "IrCharClass('0-9')"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/lexic/ir/test_nodes.py -q`
Expected: FAIL (`IrStr` not defined).

- [ ] **Step 3: Write minimal implementation**

```python
# src/lexic/ir/nodes.py  — primitive str tier
class IrStr(IrLeaf, str):
    """``IrSelf + str``. The node IS the string — no ``value`` field.

    NOTE: ``IrLeaf`` is left unparameterised (``Ir_co`` takes its ``IrSelf``
    default). Do **not** write ``IrLeaf[str]`` — ``str`` violates the
    ``Ir_co: IrSelf`` bound and reignites the attempt-0 "mutually incompatible
    bases" error on every str-leaf.
    """

    __slots__ = ()
    _bound: ClassVar[type[str]] = str

    def __new__(cls, value: str = "") -> Self:
        return super().__new__(cls, value)

    def eval(self, _d: IrSelf, _n: IrSelf, _nc: Sequence[IrSelf], /) -> Self:
        """Return self (the string)."""
        return self

    def __repr__(self) -> str:
        return f"{type(self).__name__}({str.__repr__(self)})"


class IrLiteral(IrStr, IrAtom):
    """Literal string (escapes decoded). The string itself is the payload."""

    __slots__ = ()


class IrCharClass(IrStr, IrAtom):
    """Character class — canonical POSIX-style interior."""

    __slots__ = ()


class IrRuleRef(IrStr, IrAtom):
    """Reference to another rule — the rule name."""

    __slots__ = ()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/lexic/ir/test_nodes.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/lexic/ir/nodes.py tests/unit/lexic/ir/test_nodes.py
git commit -m "ir/nodes: IrStr primitive + str-leaves (IrLiteral/IrCharClass/IrRuleRef)"
```

### Task 3: `IrTuple` primitive + variadic collections

**Files:**
- Modify: `src/lexic/ir/nodes.py`
- Test: `tests/unit/lexic/ir/test_nodes.py`

- [ ] **Step 1: Write the failing test**

```python
from lexic.ir.nodes import IrTuple, IrSequence, IrAlternation, IrNode


def test_tuple_node_is_variadic_and_native_eq():
    seq = IrSequence("a", "b")              # placeholder children; real = IrItems
    assert isinstance(seq, tuple) and isinstance(seq, IrNode)
    assert tuple(seq) == ("a", "b")
    assert IrAlternation("x", "y") == IrAlternation("x", "y")
    assert IrAlternation("x", "y") != IrAlternation("y", "x")   # order is identity


def test_tuple_children_and_rebuild_roundtrip():
    alt = IrAlternation("p", "q")
    assert tuple(alt.children()) == ("p", "q")
    assert alt.rebuild(("r",)) == IrAlternation("r")


def test_tuple_repr_is_codegen():
    assert repr(IrSequence("a")) == "IrSequence('a')"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/lexic/ir/test_nodes.py -q`
Expected: FAIL (`IrTuple` not defined).

- [ ] **Step 3: Write minimal implementation**

```python
# src/lexic/ir/nodes.py  — primitive tuple tier
class IrTuple[T: IrSelf](IrNode, tuple):
    """``IrSelf + tuple``. A variadic node IS its children tuple."""

    __slots__ = ()
    _bound: ClassVar[type[tuple]] = tuple

    def __new__(cls, *items: T) -> Self:
        return super().__new__(cls, items)

    def children(self) -> Sequence[T]:
        return self

    def rebuild(self, new_children: Sequence[IrSelf]) -> Self:
        # base-compatible param (Sequence[IrSelf]); cast for the *items: T ctor
        return type(self)(*cast(Sequence[Any], new_children))

    def eval(self, d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> Self:
        """Dispatch each element via its own ``eval`` and rebuild the tuple."""
        return type(self)(*(p.eval(d, n, nc) for p in self))

    def __repr__(self) -> str:
        return f"{type(self).__name__}({', '.join(map(repr, self))})"


class IrSequence(IrTuple["IrItem"]):
    """Concatenation of items."""

    __slots__ = ()


class IrAlternation(IrTuple["IrSequence"]):
    """Ordered choice between sequences."""

    __slots__ = ()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/lexic/ir/test_nodes.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/lexic/ir/nodes.py tests/unit/lexic/ir/test_nodes.py
git commit -m "ir/nodes: IrTuple primitive + IrSequence/IrAlternation"
```

### Task 4: `IrComposite` base + fixed-arity records

**Files:**
- Modify: `src/lexic/ir/nodes.py`
- Test: `tests/unit/lexic/ir/test_nodes.py`

- [ ] **Step 1: Write the failing test**

```python
from lexic.ir.nodes import (
    IrComposite, IrItem, IrRule, IrQuantifier, IrGroup, IrNot, IrAst,
    IrLiteral, IrAlternation, IrSequence, IrAtom,
)


def test_quantifier_plain_int_fields():
    q = IrQuantifier(0, None)
    assert (q.min, q.max) == (0, None)
    assert IrQuantifier(1, 1) == IrQuantifier(1, 1)   # frozen dataclass eq


def test_item_accepts_atom_subclasses():
    it = IrItem(IrLiteral("x"))               # IrLiteral IS-A IrAtom
    assert it.atom == "x"
    assert isinstance(it.quantifier, IrQuantifier)
    assert tuple(it.children()) == (it.atom, it.quantifier)


def test_group_and_not_are_atoms():
    body = IrAlternation(IrSequence())
    assert isinstance(IrGroup(body), IrAtom)
    assert isinstance(IrNot(IrLiteral("a")), IrAtom)


def test_composite_repr_is_codegen():
    assert repr(IrRule("r", IrAlternation())) == "IrRule(name='r', body=IrAlternation())"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/lexic/ir/test_nodes.py -q`
Expected: FAIL (`IrComposite`/records not defined).

- [ ] **Step 3: Write minimal implementation**

```python
# src/lexic/ir/nodes.py  — composite dataclass tier
class IrComposite[Ir_co: IrSelf = IrSelf](IrNode[Ir_co]):
    """THE dataclass record base. Child slots declared in ``_child_attrs``;
    records with no IR-node children declare ``_child_attrs = ()``.
    """

    __slots__ = ()
    # Declared so pyright accepts ``fields(self)``/``replace(self, …)`` on the
    # base even though IrComposite itself is not @dataclass-decorated (concrete
    # subclasses are). Without this the base errors with "__dataclass_fields__
    # is not present".
    __dataclass_fields__: ClassVar[dict[str, Any]]
    _child_attrs: ClassVar[tuple[str, ...]] = ()

    def children(self) -> Sequence[Ir_co]:
        return tuple(getattr(self, a) for a in self._child_attrs)

    def rebuild(self, new_children: Sequence[Ir_co]) -> Self:
        return replace(self, **dict(zip(self._child_attrs, new_children)))

    def __repr__(self) -> str:
        inner = ", ".join(f"{f.name}={getattr(self, f.name)!r}" for f in fields(self))
        return f"{type(self).__name__}({inner})"


@dataclass(frozen=True, slots=True, repr=False)
class IrQuantifier(IrComposite):
    """Repetition bounds. ``max=None`` means unbounded."""

    min: int = 1
    max: int | None = 1


@dataclass(frozen=True, slots=True, repr=False)
class IrItem(IrComposite):
    """An atom with a quantifier."""

    _child_attrs: ClassVar[tuple[str, ...]] = ("atom", "quantifier")
    atom: IrAtom
    quantifier: IrQuantifier = IrQuantifier()


@dataclass(frozen=True, slots=True, repr=False)
class IrGroup(IrComposite, IrAtom):
    """Parenthesised group; body is always an ``IrAlternation``."""

    _child_attrs: ClassVar[tuple[str, ...]] = ("body",)
    body: IrAlternation


@dataclass(frozen=True, slots=True, repr=False)
class IrNot[Ir_co: IrAtom = IrAtom](IrComposite, IrAtom):
    """Negation; wraps an atom."""

    _child_attrs: ClassVar[tuple[str, ...]] = ("body",)
    body: Ir_co


@dataclass(frozen=True, slots=True, repr=False)
class IrRule(IrComposite):
    """A named rule; body is always an ``IrAlternation``."""

    _child_attrs: ClassVar[tuple[str, ...]] = ("body",)
    name: str
    body: IrAlternation


@dataclass(frozen=True, slots=True, repr=False)
class IrAst(IrComposite):
    """Full grammar: rules + start-rule name."""

    _child_attrs: ClassVar[tuple[str, ...]] = ("rules",)
    rules: IrTuple = IrTuple()
    start: str = ""
```

> NOTE on field/`_child_attrs` ordering: `IrItem` declares `_child_attrs` before
> the dataclass fields so `children()` order matches. `IrRule`/`IrAst` keep
> scalar metadata (`name`/`start`) out of `_child_attrs`. `IrQuantifier` has no
> children.
>
> **G3 shape change — `IrAst.children()`.** Old `IrAst` was an `IrCollection`
> (`_items_attr="rules"`), so `children()` returned the rules tuple directly
> (iterating yielded rules). New `IrComposite` `children()` returns
> `(rules_IrTuple,)` — a 1-tuple *wrapping* the `IrTuple`. Dispatch-based walks
> are unaffected (a transformer/visitor recurses into the wrapping `IrTuple`,
> whose own `eval`/`children` dispatch each rule). But **any code that calls
> `ast.children()` and iterates expecting rules directly must switch to
> `ast.rules`.** Tasks 11–12 must audit `derive.py` (`_HoistTransformer`) and
> `topo.py` for this; the flavours already iterate `n.rules` directly.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/lexic/ir/test_nodes.py -q`
Expected: PASS.

- [ ] **Step 5: pyright the whole new `nodes.py`**

Run: `uv run pyright src/lexic/ir/nodes.py`
Expected: 0 errors.

- [ ] **Step 6: Commit**

```bash
git add src/lexic/ir/nodes.py tests/unit/lexic/ir/test_nodes.py
git commit -m "ir/nodes: IrComposite dataclass base + records (IrItem/IrRule/IrQuantifier/IrGroup/IrNot/IrAst)"
```

---

# PHASE 2 — `ir/action.py`

### Task 5: `IrField`, `IrCallable`, `IrChild`, `IrChildren` (composite record-leaves)

**Files:**
- Modify: `src/lexic/ir/action.py`
- Test: `tests/unit/lexic/ir/test_action.py`

- [ ] **Step 1: Write the failing test**

```python
from lexic.ir.nodes import IrComposite, IrStr, IrRule, IrAlternation, IrNone
from lexic.ir.action import IrField


def test_irfield_reads_scalar_and_wraps_to_irstr():
    f = IrField("name")                       # Ir_co defaults to IrStr
    rule = IrRule("greet", IrAlternation())
    out = f.eval(IrNone, rule, ())            # IrNone IS-A IrSelf — fits the slot
    assert out == "greet" and isinstance(out, IrStr)


def test_irfield_is_composite_no_children():
    assert isinstance(IrField("x"), IrComposite)
    assert IrField("x").children() == ()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/lexic/ir/test_action.py -q`
Expected: FAIL (new `IrField` shape not present).

- [ ] **Step 3: Write minimal implementation**

```python
# src/lexic/ir/action.py — record-leaf actions (each frozen IrComposite, _child_attrs=())
from dataclasses import dataclass
from typing import Callable, ClassVar, Sequence
from lexic.ir.nodes import IrComposite, IrSelf, IrStr, IrTuple


@dataclass(frozen=True, slots=True, repr=False)
class IrField[Ir_co: IrStr = IrStr](IrComposite[Ir_co]):
    """Read attribute ``name`` from the dispatched node and wrap via ``bound``."""

    name: str

    def eval(self, _d: IrSelf, n: IrSelf, _nc: Sequence[IrSelf], /) -> Ir_co:
        return self.bound(getattr(n, self.name))


@dataclass(frozen=True, slots=True, eq=False, repr=False)
class IrCallable[Ir_co: IrSelf](IrComposite[Ir_co]):
    """Procedural escape hatch — ``handler(d, n, nc) -> Ir_co``."""

    handler: Callable[[IrSelf, IrSelf, Sequence[IrSelf]], Ir_co]

    def eval(self, d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> Ir_co:
        return self.handler(d, n, nc)


@dataclass(frozen=True, slots=True, repr=False)
class IrChild[Ir_co: IrSelf](IrComposite[Ir_co]):
    """Single dispatched child by name from ``n``'s ``_child_attrs``."""

    name: str

    def eval(self, d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> Ir_co:
        attrs = getattr(type(n), "_child_attrs", ())
        try:
            idx = attrs.index(self.name)
        except ValueError as exc:
            raise ValueError(
                f"IrChild({self.name!r}): {type(n).__name__} has no such child "
                f"(known: {attrs})"
            ) from exc
        if nc:
            return self.bind(nc[idx])
        return self.bind(d.eval(d, n.children()[idx], IrTuple()))


@dataclass(frozen=True, slots=True, repr=False)
class IrChildren[Ir_co: IrSelf = IrSelf](IrComposite[Ir_co]):
    """Full tuple of dispatched children of ``n`` (reads ``n.children()``)."""

    def eval(self, d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> Ir_co:
        if nc:
            return self.bind(nc)
        return self.bind(IrTuple(*(d.eval(d, c, IrTuple()) for c in n.children())))
```

> **R2 decision: `IrChildren` drops its `name` argument.** With `IrCollection`
> removed there is no `_items_attr` to validate against and `IrChildren` reads
> `n.children()` regardless — the name was inert. Flavour call sites
> (`IrChildren("items")`/`IrChildren("arms")`) become `IrChildren()` (Task 13).
> Veto note: if a name-keyed variant is wanted later, re-add it then.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/lexic/ir/test_action.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/lexic/ir/action.py tests/unit/lexic/ir/test_action.py
git commit -m "ir/action: IrField/IrCallable/IrChild/IrChildren as IrComposite record-leaves"
```

### Task 6: `IrConcat` (IrTuple), `IrJoin`, `IrCond`

**Files:**
- Modify: `src/lexic/ir/action.py`
- Test: `tests/unit/lexic/ir/test_action.py`

- [ ] **Step 1: Write the failing test**

```python
from lexic.ir.nodes import IrComposite, IrStr, IrLiteral, IrTuple, IrNone
from lexic.ir.action import IrConcat


def test_concat_joins_parts():
    c = IrConcat(IrTuple(IrLiteral("a"), IrLiteral("b")))
    assert isinstance(c, IrComposite)
    out = c.eval(IrNone, IrNone, ())
    assert out == "ab" and isinstance(out, IrStr)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/lexic/ir/test_action.py -q`
Expected: FAIL.

- [ ] **Step 3: Write minimal implementation**

```python
# src/lexic/ir/action.py
from lexic.ir.nodes import IrComposite, IrLiteral, IrSelf, IrStr, IrTuple


@dataclass(frozen=True, slots=True, repr=False)
class IrConcat[Ir_co: IrStr = IrStr](IrComposite[Ir_co]):
    """Evaluate ``parts`` in order; join results with the bound's neutral element."""

    _child_attrs: ClassVar[tuple[str, ...]] = ("parts",)
    parts: IrTuple = IrTuple()

    def eval(self, d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> Ir_co:
        return self.bound(self.bound().join(p.eval(d, n, nc) for p in self.parts))


@dataclass(frozen=True, slots=True, repr=False)
class IrJoin[Ir_co: IrStr = IrStr](IrComposite[Ir_co]):
    """Join non-empty evaluated ``parts`` with ``separator``; ``empty`` fallback."""

    _child_attrs: ClassVar[tuple[str, ...]] = ("parts", "separator", "empty")
    parts: IrSelf = IrTuple()
    separator: IrSelf = IrLiteral("")
    empty: IrSelf = IrLiteral("")

    def eval(self, d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> Ir_co:
        rendered = self.parts.eval(d, n, nc)
        if not rendered:
            return self.empty.eval(d, n, nc)
        sep = self.separator.eval(d, n, nc)
        return self.bound(self.bound(sep).join(rendered))


@dataclass(frozen=True, slots=True, repr=False)
class IrCond[Ir_co: IrSelf](IrComposite[Ir_co]):
    """Branch on ``bool(getattr(n, field))``."""

    _child_attrs: ClassVar[tuple[str, ...]] = ("then_op", "else_op")
    field: str
    then_op: IrSelf
    else_op: IrSelf

    def eval(self, d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> Ir_co:
        branch = self.then_op if getattr(n, self.field) else self.else_op
        return branch.eval(d, n, nc)
```

> `IrConcat` is an `IrComposite` holding `parts: IrTuple` (resolved from the
> spec §8 risk). The generic-`+`-`IrTuple`-subclass form is **not** pyright-clean:
> the dual generic lineage (`Ir_co: IrStr` vs inherited `IrTuple[IrSelf]`) breaks
> `bound`, so `self.bound().join(...)` errors with `IrSelf[Unknown]` has no
> `join`. Verified in `after_attempt_0/tst5.py`. Composite form matches `IrJoin`
> and is pyright-clean (same shape as `IrField`).

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/lexic/ir/test_action.py -q`
Expected: PASS.

- [ ] **Step 5: pyright the action module so far**

Run: `uv run pyright src/lexic/ir/action.py`
Expected: 0 errors.

- [ ] **Step 6: Commit**

```bash
git add src/lexic/ir/action.py tests/unit/lexic/ir/test_action.py
git commit -m "ir/action: IrConcat/IrJoin/IrCond as IrComposite"
```

### Task 7: Default bodies, `IrReturn`, `IrAction`

**Files:**
- Modify: `src/lexic/ir/action.py`
- Test: `tests/unit/lexic/ir/test_action.py`

- [ ] **Step 1: Write the failing test**

```python
from lexic.ir.nodes import IrLeaf, IrComposite, IrLiteral
from lexic.ir.action import IrPass, IrWalk, IrEmit, IrRebuild, IrReturn, IrAction
from lexic.ir.nodes import IrNone


def test_default_bodies_are_plain_leaves():
    for body in (IrPass(), IrWalk(), IrEmit(), IrRebuild()):
        assert isinstance(body, IrLeaf)


def test_irpass_returns_irnone():
    assert IrPass().eval(IrNone, IrNone, ()) is IrNone


def test_irreturn_raises_self_and_is_composite():
    r = IrReturn(IrLiteral("v"))
    assert isinstance(r, IrComposite) and isinstance(r, BaseException)
    import pytest
    with pytest.raises(IrReturn):
        r.eval(IrNone, IrNone, ())


def test_iraction_delegates_to_body():
    a = IrAction(IrLiteral, IrEmit())
    assert a.target_type is IrLiteral
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/lexic/ir/test_action.py -q`
Expected: FAIL.

- [ ] **Step 3: Write minimal implementation**

```python
# src/lexic/ir/action.py
from lexic.exceptions import UnsupportedConstructError
from lexic.ir.nodes import IrLeaf, IrLiteral, IrNode, IrNone


class _Return(BaseException):
    """Control-flow exception raised by IrReturn."""

    def __init__(self, value: object) -> None:
        super().__init__()
        self.value = value


class IrPass(IrLeaf[IrSelf]):
    """No-op body — evaluates to IrNone without recursing."""

    __slots__ = ()

    def eval(self, _d: IrSelf, _n: IrSelf, _nc: Sequence[IrSelf], /) -> IrSelf:
        return IrNone

    def __repr__(self) -> str:
        return "IrPass()"


class IrWalk(IrLeaf[IrSelf]):
    """Walk n's children via d for side effects; return IrNone."""

    __slots__ = ()

    def eval(self, d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> IrSelf:
        if not nc:
            for c in n.children():
                d.eval(d, c, ())
        return IrNone

    def __repr__(self) -> str:
        return "IrWalk()"


class IrEmit[Ir_co: IrLiteral](IrLeaf[Ir_co]):
    """Fallback emit — wrap the node's canonical form as an IrLiteral."""

    __slots__ = ()
    _bound: ClassVar[type] = IrLiteral

    def eval(self, _d: IrSelf, n: IrSelf, _nc: Sequence[IrSelf], /) -> Ir_co:
        return self.bound(str(n))

    def __repr__(self) -> str:
        return "IrEmit()"


class IrRebuild(IrLeaf[IrNode]):
    """Walk children via d, then rebuild n with the results."""

    __slots__ = ()

    def eval(self, d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> IrNode:
        if not isinstance(n, IrNode):                     # narrow: only rebuild nodes
            raise UnsupportedConstructError(
                f"IrRebuild: cannot rebuild {type(n).__name__}"
            )
        new_children = nc or IrTuple(*(d.eval(d, c, ()) for c in n.children()))
        return n.rebuild(new_children)

    def __repr__(self) -> str:
        return "IrRebuild()"


@dataclass(frozen=True, slots=True, repr=False)
class IrRaise[Ir_co: IrSelf](IrComposite[Ir_co]):
    """Raise a configured exception when dispatched."""

    exc_type: type[BaseException] = UnsupportedConstructError
    message: str = "{dispatcher}: no action for {node_type!r}"

    def eval(self, d: IrSelf, n: IrSelf, _nc: Sequence[IrSelf], /) -> Ir_co:
        raise self.exc_type(
            self.message.format(dispatcher=type(d).__name__, node_type=type(n).__name__)
        )


@dataclass(frozen=True, slots=True, eq=False, repr=False)
class IrReturn[Ir_co: IrSelf](IrComposite[Ir_co], _Return):
    """Short-circuit IR node that IS-A control-flow exception."""

    value: Ir_co

    def __post_init__(self) -> None:
        BaseException.__init__(self)

    def eval(self, _d: IrSelf, _n: IrSelf, _nc: Sequence[IrSelf], /) -> Ir_co:
        raise self


@dataclass(frozen=True, slots=True, eq=False, repr=False)
class IrAction[Ir_co: IrSelf](IrComposite[Ir_co]):
    """Bind a target IR-node type to a callable body."""

    _child_attrs: ClassVar[tuple[str, ...]] = ("body",)
    target_type: type[IrSelf]
    body: IrSelf

    def eval(self, d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> Ir_co:
        return self.body.eval(d, n, nc)
```

> `IrRebuild` narrows `n` with an explicit `isinstance(n, IrNode)` guard that
> raises `UnsupportedConstructError` — no suppression (matches the codebase's
> "explicit raise in every dispatch path" rule). `IrEmit` uses `str(n)` for its
> fallback — confirm the canonical form is correct now the `_str_name` cascade is
> gone (spec §8); if the fallback is unreachable in practice, assert that with a
> test.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/lexic/ir/test_action.py -q`
Expected: PASS.

- [ ] **Step 5: pyright the action module**

Run: `uv run pyright src/lexic/ir/action.py`
Expected: 0 errors.

- [ ] **Step 6: Commit**

```bash
git add src/lexic/ir/action.py tests/unit/lexic/ir/test_action.py
git commit -m "ir/action: default bodies, IrReturn, IrAction on IrComposite"
```

---

# PHASE 3 — `ir/walk.py`

### Task 8: `IrDispatch` + presets as `IrComposite`

**Files:**
- Modify: `src/lexic/ir/walk.py`
- Test: `tests/unit/lexic/ir/test_walk.py`

- [ ] **Step 1: Write the failing test**

```python
from lexic.ir.nodes import IrComposite, IrLiteral
from lexic.ir.action import IrAction, IrEmit
from lexic.ir.walk import IrDispatch, IrEmitter


def test_dispatch_is_composite_and_resolves_action():
    d = IrDispatch(actions=(IrAction(IrLiteral, IrEmit()),))
    assert isinstance(d, IrComposite)
    assert d.apply(IrLiteral("x")) == "x"


def test_resolve_cache_is_mutable_and_excluded_from_eq():
    a = IrDispatch(actions=())
    b = IrDispatch(actions=())
    assert a == b                       # cache excluded from eq
    a.apply  # cache populates on use; identity unaffected
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/lexic/ir/test_walk.py -q`
Expected: FAIL.

- [ ] **Step 3: Write minimal implementation**

```python
# src/lexic/ir/walk.py
from dataclasses import dataclass, field
from typing import ClassVar, Sequence
from lexic.ir.action import IrAction, IrEmit, IrRaise, IrRebuild, IrReturn, IrWalk
from lexic.ir.nodes import IrComposite, IrLiteral, IrNode, IrSelf, IrTuple


@dataclass(frozen=True, slots=True, repr=False)
class IrDispatch[Ir_co: IrSelf](IrComposite[Ir_co]):
    """Action-driven dispatcher. Resolves the matching IrAction for type(n) via
    concrete-first MRO walk (memoised). Does not walk children itself."""

    actions: tuple[IrAction[Ir_co], ...] = ()
    default: IrSelf = IrRaise()
    _resolve_cache: dict[type, IrAction[Ir_co]] = field(
        default_factory=dict, hash=False, compare=False, repr=False
    )

    def eval(self, d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> Ir_co:
        return self._resolve(type(n)).body.eval(d, n, nc)

    def apply(self, root: IrNode) -> Ir_co:
        try:
            return self.eval(self, root, IrTuple())
        except IrReturn as ret:
            if isinstance(ret.value, self.bound):
                return ret.value
            if isinstance(ret, self.bound):
                return ret
            raise

    def _resolve(self, node_type: type) -> IrAction[Ir_co]:
        cache = self._resolve_cache
        if node_type in cache:
            return cache[node_type]
        for cls in node_type.__mro__:
            for action in self.actions:
                if action.target_type is cls:
                    cache[node_type] = action
                    return action
        action = IrAction[Ir_co](node_type, self.default)
        cache[node_type] = action
        return action


@dataclass(frozen=True, slots=True, repr=False)
class IrVisitor(IrDispatch):
    """Side-effect walker; default IrWalk."""

    default: IrSelf = IrWalk()


@dataclass(frozen=True, slots=True, repr=False)
class IrTransformer(IrDispatch[IrNode]):
    """Tree rewriter; default IrRebuild."""

    default: IrSelf = IrRebuild()


@dataclass(frozen=True, slots=True, repr=False)
class IrEmitter[Ir_co: IrLiteral](IrDispatch[Ir_co]):
    """String emitter; default IrEmit."""

    default: IrSelf = IrEmit()
```

> `IrDispatch` was an `IrCollection` (items=`actions`); it is now an
> `IrComposite`. `actions` is a plain `tuple` field, **not** a child slot
> (`_child_attrs=()` inherited) — the dispatcher is not walked as a grammar node.
> If anything relied on `IrDispatch.children()` returning the actions, re-evaluate.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/lexic/ir/test_walk.py -q`
Expected: PASS.

- [ ] **Step 5: Gate — core packages pyright-clean and unit tests green**

Run: `uv run pyright src/lexic/ir/nodes.py src/lexic/ir/action.py src/lexic/ir/walk.py`
Run: `uv run pytest tests/unit/lexic/ir/test_nodes.py tests/unit/lexic/ir/test_action.py tests/unit/lexic/ir/test_walk.py -q`
Expected: 0 pyright errors; all tests PASS.

- [ ] **Step 6: Commit**

```bash
git add src/lexic/ir/walk.py tests/unit/lexic/ir/test_walk.py
git commit -m "ir/walk: IrDispatch + presets on IrComposite"
```

---

# PHASES 4–7 — Consumer ports

The core is now stable. Remaining modules are **ported** (behaviour preserved),
not redesigned. Each consumer task applies the documented transformation rules,
**ports** the file's mirror test (fix construction, keep every assertion — never
delete; see "Test handling"), and is gated by `uv run pyright <file>`. The
behavioural suite is the Phase 8 gate.

**Transformation rules (apply uniformly):**

| Old pattern | New pattern |
|---|---|
| `leaf.value` (on IrLiteral/IrCharClass/IrRuleRef) | use the node directly — it IS-A `str` |
| `IrLiteral(value=s)` / `IrLiteral(s)` | `IrLiteral(s)` (unchanged) |
| `IrAlternation(arms=IrTuple(a, b))` / `IrAlternation((a, b))` | `IrAlternation(a, b)` |
| `IrSequence(items=...)` | `IrSequence(*items)` |
| `IrAst(rules=..., start=...)` | `IrAst(IrTuple(*rules), start)` |
| `IrRule(name=IrStr(s), ...)` | `IrRule(s, body)` (name is plain `str`) |
| `node._items_attr` / `IrCollection` | gone — use `children()` |
| `.coerce(...)` / `_ir_field_types` | gone — construct the real node |
| `IrField("value")` on a str-leaf action (`IrAction(IrRuleRef, IrField("value"))`) | emit the leaf directly — `IrAction(IrRuleRef, IrEmit())` (the leaf IS its value; `str(n)` is the payload). `IrField` stays only where a node has a *named* field to read (e.g. `IrField("name")` on `IrRule`). |
| `IrChildren("items")` / `IrChildren("arms")` | `IrChildren()` (R2 — no name arg) |

### Task 9: `ir/spec.py` (`RuleSpec`, `to_ir_rule`)

**Files:**
- Modify: `src/lexic/ir/spec.py`
- Test: `tests/unit/lexic/ir/test_spec.py`

- [ ] **Step 1** Update mirror test `tests/unit/lexic/ir/test_spec.py` to construct `RuleSpec` items with the new node shapes (variadic collections, str-leaves, `name: str`). Run it, expect FAIL.
- [ ] **Step 2** Port `RuleSpec` and `to_ir_rule()`: `items: list[IrItem | IrAlternation]` keeps shape; replace any `IrTuple`/`IrStr` wrapper construction and `.value` reads per the rules table. `to_ir_rule()` wraps `items` in `IrAlternation(IrSequence(*items))` using variadic constructors.
- [ ] **Step 3** Run `uv run pytest tests/unit/lexic/ir/test_spec.py -q` — expect PASS.
- [ ] **Step 4** `uv run pyright src/lexic/ir/spec.py` — expect 0 errors.
- [ ] **Step 5** Commit: `git commit -am "ir/spec: port RuleSpec/to_ir_rule to primitive nodes"`

### Task 10: `ir/charclass.py`, `ir/naming.py`

**Files:**
- Modify: `src/lexic/ir/charclass.py`, `src/lexic/ir/naming.py`
- Test: `tests/unit/lexic/ir/test_charclass.py`, `tests/unit/lexic/ir/test_naming.py`

- [ ] **Step 1** Update both mirror tests to new shapes; run, expect FAIL.
- [ ] **Step 2** Port: every `leaf.value` → the leaf used directly as `str`; `_field_map`/`CHARCLASS_NAMES`/`_LITERAL_NAMES` lookups now key on the str-leaf value (the node itself). Quantifier checks use `IrQuantifier(1, 1)` equality.
- [ ] **Step 3** `uv run pytest tests/unit/lexic/ir/test_charclass.py tests/unit/lexic/ir/test_naming.py -q` — expect PASS.
- [ ] **Step 4** `uv run pyright src/lexic/ir/charclass.py src/lexic/ir/naming.py` — expect 0 errors.
- [ ] **Step 5** Commit.

### Task 11: `ir/derive.py`

**Files:**
- Modify: `src/lexic/ir/derive.py`
- Test: `tests/unit/lexic/ir/test_derive.py`

- [ ] **Step 1** Update `tests/unit/lexic/ir/test_derive.py`: the `_EXTRACT_BODY` dispatch returns `IrNone` (the value, not `None`); construction uses variadic collections; `.value`→str. Run, expect FAIL.
- [ ] **Step 2** Port `derive_specs`, `_hoist_item`, `_extract_group`/`_extract_none` (return `IrNone`), `_HoistTransformer` (now an `IrComposite`-based `IrTransformer`). Apply the rules table throughout. **G3 audit:** check `_HoistTransformer` and any walk over an `IrAst` — if it calls `ast.children()` expecting rules, switch to `ast.rules` (new `children()` returns `(rules_IrTuple,)`; dispatch-based recursion is unaffected).
- [ ] **Step 3** `uv run pytest tests/unit/lexic/ir/test_derive.py -q` — expect PASS.
- [ ] **Step 4** `uv run pyright src/lexic/ir/derive.py` — expect 0 errors.
- [ ] **Step 5** Commit.

### Task 12: `ir/{emit,escapes,directives,topo,regex_portable}.py` + `ir/__init__.py`

**Files:**
- Modify: each remaining `ir/` module that references node internals, **and `src/lexic/ir/__init__.py`** (re-exports).
- Test: corresponding mirror tests, incl. `tests/unit/lexic/ir/test_init_ir.py`.

- [ ] **Step 1** For each module, update its mirror test to new shapes; run, expect FAIL where the module touches node internals (some, e.g. `topo`, may be unaffected).
- [ ] **Step 2** Port per the rules table. **`ir/__init__.py` (G2):** drop re-exports of removed symbols (`IrType`, `IrStrLeaf`, `IrCollection`, `IrQuantifier`-facade if any) and add `IrNoneType`; keep the rest. **G3 audit:** confirm `topo.py` iterates `ast.rules` (not `ast.children()`).
- [ ] **Step 3** `uv run pytest tests/unit/lexic/ir/ -q` — expect PASS for the ported modules.
- [ ] **Step 4** `uv run pyright src/lexic/ir/` — expect 0 errors.
- [ ] **Step 5** Commit: `git commit -am "ir: port remaining ir/ consumers to primitive nodes"`

### Task 13: Flavours — `grammars/flavour.py`, `gbnf/flavour.py`, `abnf/flavour.py`

**Files:**
- Modify: `src/lexic/grammars/flavour.py`, `grammars/gbnf/flavour.py`, `grammars/abnf/flavour.py`
- Test: `tests/unit/lexic/grammars/**`

- [ ] **Step 1** Update flavour mirror tests; run, expect FAIL.
- [ ] **Step 2** Port the `*_ACTIONS` tuples and any `IrField`/`IrConcat`/`IrJoin`/`IrCond` bodies to the new shapes. `IrFlavour` IS-AN `IrEmitter` (now `IrComposite`-based). `normalize_literal` returns `IrLiteral | IrGroup` constructed directly. `parse_quantifier` returns `IrQuantifier(min, max)`; `parse_charclass` returns `(pattern, negated)`.
- [ ] **Step 2a (R1)** Replace `IrAction(IrRuleRef, IrField("value"))` (and any `IrField("value")` on a str-leaf) in `gbnf/flavour.py` (~:133) and `abnf/flavour.py` (~:165) with `IrAction(IrRuleRef, IrEmit())` — the ruleref IS its name; `str(n)` yields it. Leave `IrField` in place wherever it reads a genuine named field. Replace `IrChildren("items")`/`IrChildren("arms")` with `IrChildren()` (R2).
- [ ] **Step 2b (R3)** Add a test asserting the emitter's `IrEmit` default is **unreachable** for each registered flavour — i.e. every IR-AST node type has an explicit action — so the `str(n)` fallback (which now yields `repr`-like codegen for composites) can never leak into emitted grammar text. If a type legitimately relies on the default, give it an explicit action instead.
- [ ] **Step 3** `uv run pytest tests/unit/lexic/grammars/ -q` — expect PASS.
- [ ] **Step 4** `uv run pyright src/lexic/grammars/` — expect 0 errors.
- [ ] **Step 5** Commit: `git commit -am "grammars: port flavours to primitive nodes"`

### Task 14: `codegen/` and `parsing/`

**Files:**
- Modify: `src/lexic/codegen/{__init__,aliases,model_emitter}.py`, `src/lexic/parsing/{lark_builder,meta_parser}.py`, `parsing/transformer/build_transformer.py`
- Test: corresponding mirror tests.

- [ ] **Step 1** Update mirror tests; run, expect FAIL.
- [ ] **Step 2** Port. `MetaGrammarParser` builds `IrAst`/`IrRule`/`IrItem`/leaves with variadic + plain-scalar construction. `model_emitter`/`aliases` read str-leaves directly. **Template rule:** if generated output trips ruff, fix `model_emitter.py`, never `generated/`.
- [ ] **Step 3** `uv run pytest tests/unit/lexic/codegen/ tests/unit/lexic/parsing/ -q` — expect PASS.
- [ ] **Step 4** `uv run pyright src/lexic/codegen/ src/lexic/parsing/` — expect 0 errors.
- [ ] **Step 5** Commit: `git commit -am "codegen+parsing: port to primitive nodes"`

### Task 15: Runtime — `base.py`, `compile.py`, `parse.py`, `generate.py`

**Files:**
- Modify: `src/lexic/base.py`, `src/lexic/compile.py`, `src/lexic/parse.py`, `src/lexic/generate.py`
- Test: corresponding mirror tests.

- [ ] **Step 1** Update mirror tests; run, expect FAIL.
- [ ] **Step 2** Port. `base.GrammarModel.to_text()`/`to_grammar()`/`semantic_dump()` read str-leaves directly and use `field_map`. `to_grammar` still calls `flavour.apply(self.__grammar__.to_ir_rule())`. `generate.py` reads `IrQuantifier.min/max` (plain ints) and str-leaves directly.
- [ ] **Step 3** `uv run pytest tests/unit/lexic/test_base.py tests/unit/lexic/test_compile.py tests/unit/lexic/test_parse.py tests/unit/lexic/test_generate.py -q` — expect PASS.
- [ ] **Step 4** `uv run pyright src/lexic/base.py src/lexic/compile.py src/lexic/parse.py src/lexic/generate.py` — expect 0 errors.
- [ ] **Step 5** Commit: `git commit -am "runtime: port base/compile/parse/generate to primitive nodes"`

---

# PHASE 8 — Full-green gate

### Task 16: Whole-tree pyright + suite + lint

**Files:** none (verification + any residual fixes).

- [ ] **Step 1** `tools/auto_fix.sh`
- [ ] **Step 2 — success gate.** Confirm all three, together:
  1. **The mask is gone.** No `*args/**kwargs` load-bearing `IrNode.__init__`, no `IrType.coerce`, no `_ir_field_types` remain anywhere (`grep` to prove). Construction is honest per-field dataclass `__init__` / `__new__`. This is *the* point — standard-mode pyright was already 0 on the old tree only because the `*args` signature hid everything.
  2. **`uv run pyright src/ tests/` → 0 errors, 0 warnings, no suppressions**, in the project's configured (standard) mode. Because (1) removed the mask, this 0 now genuinely means the honest construction sites type-check — not that errors are hidden. (Strict mode is out of scope: it surfaces ~1264 pre-existing untyped-test-helper errors unrelated to this work.)
  3. **`uv run pytest tests/ -q`** — full suite green (baseline: 474 passed).
- [ ] **Step 3** `uv run ruff check src/ tests/` — expect clean.
- [ ] **Step 4** Per-file quality gate on the rewritten core: `uv run pylint src/lexic/ir/nodes.py src/lexic/ir/action.py src/lexic/ir/walk.py` — expect clean (no new disables).
- [ ] **Step 5 (G2 docs)** Update **`CLAUDE.md`** — it documents the *old* API as current (`IrType`, `IrStrLeaf`, `IrCollection`, `_items_attr`, the `_str_name` cascade, the flavour template). Rewrite those sections to the new model (three tiers, `IrComposite` sole dataclass base, `IrNoneType`/`IrNone`, `repr`-is-codegen). Then update `.wiki/` (IR shapes, field naming, decisions) plus a `.wiki/log.md` entry per CLAUDE.md. Remove `after_attempt_0/` (incl. `tst1`–`tst5`) if the owner agrees.
- [ ] **Step 6** Commit: `git commit -am "ir: full migration to primitive node model — pyright clean, suite green"`

---

## Self-review

**Spec coverage:** spine/covariant `Ir_co` (Task 1) · `IrAtom` non-generic marker (Tasks 1,4) · str-leaves (Task 2) · variadic collections (Task 3) · `IrComposite` sole dataclass base + `IrCollection` removed (Tasks 4,8) · action algebra (Tasks 5–7) · dispatch (Task 8) · `bound`/`bind` retained, coercion removed (Tasks 1,5,6) · `repr`-is-codegen (Tasks 2,3,4) · `__new__ -> Self` guard (Task 2) · consumers (Tasks 9–15) · pyright-0 + suite-green gate (Task 16). Set-alternation / `IrInt` / `IrKeyed`-keying explicitly out of scope per spec §2.

**Placeholder scan:** consumer tasks (9–15) intentionally use the shared rules table rather than repeating full file rewrites — this is a documented port, not a placeholder; each task names exact files, the transformation, the test, and the gate. **No `# type: ignore` / suppressions remain** — the two earlier ones are resolved (Task 5 uses bare `IrNone`; Task 7 `IrRebuild` uses an `isinstance` guard + raise).

**Type consistency:** `IrNone` is the value `IrNoneType()`; callers pass bare `IrNone`, `IrNoneType` is used for `isinstance`/annotations (Task 1, no rules-table churn). `_bound` is derived from each class's **own** `__type_params__` (never the MRO), with explicit `_bound` winning (Task 1). `bound`/`_bound`/`bind` signatures match across nodes/action/walk. `_child_attrs` declared on every composite with children. `IrConcat` is an `IrComposite` holding `parts: IrTuple` (Task 6), consistent with `IrJoin`.
