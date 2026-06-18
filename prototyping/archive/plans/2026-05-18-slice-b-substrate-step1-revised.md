# Slice B Substrate — Step 1 REVISED (DRAFT proposal)

> Proposed replacement for `## Step 1` of `2026-05-18-slice-b-substrate.md`. Not yet integrated. Flagged for review per `feedback_plan_review_flag_dont_fix`.

## Summary of changes vs. canonical Step 1

1. **`IrOp` ABC deleted.** "Action body" is a structural protocol: any `IrNode[_T]` whose `__call__(dispatch, node, new_children) -> _T` returns a usable value.
2. **`IrText` deleted.** `IrLiteral` absorbs the "string-constant action primitive" role with an explicit `__call__` returning `self.value`.
3. **`IrNode` becomes generic over return type: `IrNode[_T]`.**
4. **`_T` defaults to `IrNode` via a single module-scope TypeVar declaration** (PEP 696, available via `typing_extensions.TypeVar`):
   ```python
   _T = TypeVar("_T", default="IrNode")
   class IrNode(Generic[_T], ABC): ...
   class IrLeaf(IrNode[_T], Generic[_T]): ...
   class IrCollection(IrStructure, IrNode[_T], Generic[_T]): ...
   class IrComposite(IrStructure, IrNode[_T], Generic[_T]): ...
   ```
   One declaration at module top; threads through the hierarchy. The default fires when a subclass omits the parameter — `class IrCharClass(IrLeaf):` resolves to `IrLeaf[IrNode]`.

   Why not `Self` as default: pyright rejects `Self` as a TypeVar default (`"Self" is not valid in this context`) at both module scope AND inside PEP 695 class headers. Verified by pre-flight. `IrNode` as the default loses precise Self-typing on AST-node calls (the inherited `__call__` is typed `IrNode`, not the concrete subclass) — acceptable because consumers always go through `IrDispatch[_T]` which carries its own precision.
5. **`__call__` signature accepts `None` for `dispatch` and `node`** (`IrDispatch[Any] | None`, `IrNode | None`). Honest at the type level — unit tests that invoke a node outside a dispatch pass `None` without any ignores.
6. **Grammar AST nodes get free `__call__`:** `IrSequence`, `IrAlternation`, `IrAst`, `IrGroup`, `IrItem`, `IrRule`, `IrCharClass`, `IrRuleRef`, `Quantifier` all inherit the default `__call__` (identity for leaves, rebuild-with-called-children for structures). Statically typed `IrNode`; at runtime returns the concrete subclass. No per-class `__call__` needed.
7. **`IrLiteral(IrLeaf[str])`** explicitly overrides — `__call__` returns `self.value`. Keeps `__str__` for debug output (single-purpose).
8. **Action-algebra classes that return `str`** (`IrField`, `IrConcat`, `IrJoin`) parameterize the structural base as `[str]` and override `__call__`.
9. **Action-algebra generics:** `IrChild[_U]`, `IrChildren[_U]`, `IrCallable[_T]`, `IrCond[_T]`, `IrReturn[_T]`. Each parameterizes `_T` / `_U` independently and overrides `__call__`.
10. **`.eval(...)` renamed to `__call__(...)`** throughout. Call sites use `body(d, n, nc)`.
11. **`IrAction.body: IrNode[Any]`** (was `IrOp`). The body must be callable with the dispatch signature.

Trade-off accepted: AST-node `__call__` return type is statically `IrNode` (not the concrete subclass). Consumers that need precise typing go through `IrDispatch[_T]`, which is parameterized correctly. Buys: zero `type: ignore`, no pre-flight check needed, no per-class `__call__` overrides on grammar AST classes, no per-base default-parameter duplication.

---

## Step 1 — `ir/action.py` — action algebra + IrAction (revised)

The substrate is `IrNode[_T]` with an abstract `__call__`; every concrete IR node implements its own. `ir/action.py` adds the action-specific node types (`IrField`, `IrCallable`, `IrChild`, `IrChildren`, `IrConcat`, `IrJoin`, `IrCond`, `IrReturn`, `IrAction`) and the `_Return` short-circuit exception.

### Task 1.1: Generic `IrNode[_T]` + default `__call__` on structural bases + IrLiteral override

**Files:**
- Modify: `src/lexic/ir/nodes.py`
- Modify: `tests/unit/lexic/ir/test_nodes.py`

**Pre-flight already done:** pyright rejects `Self` as a TypeVar default at module scope AND in PEP 695 class headers (`"Self" is not valid in this context`). Confirmed via the PoC in `tst.py`. We use `default=IrNode` instead — a single module-scope `TypeVar` from `typing_extensions` threads through the hierarchy.

- [ ] **Step 1: Write failing tests**

`__call__` signature is `(IrDispatch[Any] | None, IrNode | None, tuple) -> _T`. `None` is accepted at the type level — no test-side ignores. Annotations on `result` use `IrNode` (the default) — runtime `is` / `isinstance` assertions still verify the concrete subclass.

```python
# tests/unit/lexic/ir/test_nodes.py — append

def test_irliteral_call_returns_value_as_str():
    """IrLiteral(IrLeaf[str]) overrides __call__ to return self.value.
    Subsumes the IrText role."""
    from lexic.ir.nodes import IrLiteral
    result: str = IrLiteral("hello")(None, None, ())
    assert result == "hello"


def test_ircharclass_call_inherits_identity_default():
    """IrCharClass(IrLeaf) inherits the default __call__ — returns self.
    Statically typed as IrNode; runtime identity to the concrete instance."""
    from lexic.ir.nodes import IrCharClass
    cc = IrCharClass("a-z")
    result = cc(None, None, ())   # statically IrNode; runtime IrCharClass
    assert result is cc


def test_irruleref_call_inherits_identity_default():
    from lexic.ir.nodes import IrRuleRef
    ref = IrRuleRef("foo")
    assert ref(None, None, ()) is ref


def test_irast_call_inherits_rebuild_default():
    """IrAst(IrCollection) inherits __call__: rebuild with called rules."""
    from lexic.ir.nodes import IrAst
    empty = IrAst(rules=(), start="r")
    result = empty(None, None, ())
    assert isinstance(result, IrAst)
    assert result.rules == ()
    assert result.start == "r"


def test_irgroup_call_inherits_rebuild_default():
    """IrGroup(IrComposite) inherits __call__ via rebuild(called children)."""
    from lexic.ir.nodes import IrGroup, IrAlternation
    g = IrGroup(body=IrAlternation())
    result = g(None, None, ())
    assert isinstance(result, IrGroup)
    assert isinstance(result.body, IrAlternation)
```

- [ ] **Step 2: Run; verify failure** — `TypeError: '<class>' object is not callable` on each.

- [ ] **Step 3: Implement**

In `src/lexic/ir/nodes.py` — module-scope `_T` with `default=IrNode`; `IrNode[_T]` generic; structural bases provide default `__call__`; `IrLiteral` overrides.

```python
from typing import Any, ClassVar
from typing_extensions import TypeVar    # PEP 696 `default=`; stdlib gains it 3.13+

# One TypeVar threads through the hierarchy. Default fires when a subclass
# omits the parameter: `class IrCharClass(IrLeaf):` → `IrLeaf[IrNode]`.
# Forward-ref because IrNode is defined below.
_T = TypeVar("_T", default="IrNode")


class IrNode(Generic[_T], ABC):
    """Structural protocol every IR node implements.

    Generic in ``_T`` — the type returned by ``__call__`` when this node is
    invoked as an action body. Subclasses either pin ``_T`` by parameterizing
    the structural base (``IrLeaf[str]`` for ``IrLiteral``) or accept the
    default (`_T = IrNode`).

    Override ``__call__`` whenever ``_T`` is not ``IrNode`` — the inherited
    default returns ``self`` (or a rebuilt ``self``) which is statically
    typed as the base's ``_T``.
    """

    # ... existing _str_name machinery, children, rebuild — unchanged ...

    @abstractmethod
    def __call__(
        self,
        dispatch: "IrDispatch[Any] | None",
        node: "IrNode | None",
        new_children: tuple,
    ) -> _T:
        """Evaluate this node as an action body.

        :param dispatch: Dispatcher driving the surrounding walk. ``None``
            when this node is invoked outside a dispatch (unit tests or
            pure-data bodies needing no context).
        :param node: The dispatched domain node providing sibling-lookup
            context. ``None`` outside a dispatch.
        :param new_children: The dispatched domain node's already-walked
            children, aligned to ``node.children()`` order.
        :returns: This node's contribution to the surrounding evaluation.
        """
```

Structural bases — share the module-scope `_T`; default `__call__` typechecks because every IrLeaf/IrCollection/IrComposite IS-A IrNode:

```python
class IrLeaf(IrNode[_T], Generic[_T]):
    """Base for all leaf nodes.

    Default ``__call__`` returns ``self``. Statically typed as ``_T`` (which
    defaults to ``IrNode``); runtime returns the concrete subclass.
    Subclasses that re-parameterize (``IrLeaf[str]``) must override.
    """

    __dataclass_fields__: ClassVar[dict[str, dataclasses.Field[Any]]]

    def __call__(self, _d, _n, _nc) -> _T:
        return self  # type-checks: IrLeaf IS-A IrNode (the default for _T)

    # ... existing _inner_str / children / rebuild unchanged ...


class IrCollection(IrStructure, IrNode[_T], Generic[_T]):
    """Branch node with a single variable-length tuple of homogeneous children.

    Default ``__call__`` rebuilds with called children. Subclasses that
    re-parameterize ``_T`` must override.
    """

    _items_attr: ClassVar[str]

    def __call__(self, d, n, nc) -> _T:
        return self.rebuild(tuple(c(d, n, nc) for c in self.children()))

    # ... existing _extra_field_names / children / rebuild unchanged ...


class IrComposite(IrStructure, IrNode[_T], Generic[_T]):
    """Branch node with a fixed, named set of typed children.

    Default ``__call__`` rebuilds with called children. Subclasses that
    re-parameterize ``_T`` must override.
    """

    _child_attrs: ClassVar[tuple[str, ...]]

    def __call__(self, d, n, nc) -> _T:
        return self.rebuild(tuple(c(d, n, nc) for c in self.children()))

    # ... existing implementations unchanged ...
```

Note: the previous draft had `IrCollection[_T, _U]` (two parameters — return type and element type). Drop `_U` — the element type is already pinned per-subclass via existing `_items_attr` machinery and the existing PEP 695 `IrCollection["IrItem"]` style in `nodes.py`. Stick with single `_T`.

`IrLiteral` is the only grammar AST class that overrides:

```python
class IrLiteral(IrLeaf[str]):
    """Literal string. ``value`` is canonical Python (escapes decoded).

    ``__call__`` returns ``self.value`` directly — keeps ``__str__`` free
    for debug output (``LITERAL('foo')``) while ``__call__`` returns the
    string content for emission. Subsumes the ``IrText`` role.
    """

    value: str

    def __call__(self, _d, _n, _nc) -> str:
        return self.value
```

**Every other grammar AST class inherits the default `__call__`** — no `__call__` is written for them. Their *existing* fields, `@dataclass` decorators, `_str_name` overrides, `_inner_str` methods, etc. **all stay unchanged** — the only change to each class is what it inherits from its base. The snippets below show only the lines that change; everything else in `ir/nodes.py` stays as-is.

```python
# All grammar AST classes that don't override _T inherit the default
# (_T = IrNode via the module-scope TypeVar). __call__ inherited; statically
# typed IrNode, runtime returns the concrete instance.

class IrCharClass(IrLeaf): ...     # _T = IrNode
class IrRuleRef(IrLeaf): ...       # _T = IrNode
class Quantifier(IrLeaf): ...      # renamed to IrQuantifier in Step 4

class IrSequence(IrCollection): ...     # _T = IrNode
class IrAlternation(IrCollection): ...  # _T = IrNode

class IrAst(IrCollection):
    _items_attr: ClassVar[str] = "rules"
    rules: tuple["IrRule", ...] = ()
    start: str = ""

class IrGroup(IrComposite): ...    # _T = IrNode
class IrItem(IrComposite): ...     # _T = IrNode
class IrRule(IrComposite): ...     # _T = IrNode
```

No explicit type parameter on any subclass — they all accept the `_T = IrNode` default from the module-scope TypeVar.

- [ ] **Step 4: Run; verify pass.**

- [ ] **Step 5: Commit.**

```bash
git add src/lexic/ir/nodes.py tests/unit/lexic/ir/test_nodes.py
git commit -m "ir/nodes: generic IrNode[_T] with default __call__ on structural bases

IrNode is generic in _T (the action-body return type). One module-scope
TypeVar with default=IrNode threads through IrLeaf, IrCollection,
IrComposite. Default __call__ on each typechecks because every leaf/
collection/composite IS-A IrNode. Grammar AST classes inherit the
default (statically typed IrNode, runtime returns the concrete subclass);
IrLiteral overrides explicitly to return self.value (subsumes the IrText
role). IrText deleted."
```

---

### Task 1.2: Module skeleton — `_Return` exception

**Files:**
- Create: `src/lexic/ir/action.py`
- Create: `tests/unit/lexic/ir/test_action.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/lexic/ir/test_action.py
"""Tests for ir/action.py — action-algebra nodes built on the IrNode substrate."""

import pytest

from lexic.ir.action import _Return


def test_return_inherits_base_exception_not_exception():
    assert issubclass(_Return, BaseException)
    assert not issubclass(_Return, Exception)


def test_return_carries_value():
    sig = _Return(value=42)
    assert sig.value == 42
```

- [ ] **Step 2: Run; verify ImportError.**

- [ ] **Step 3: Implement**

```python
# src/lexic/ir/action.py
"""Action-algebra IrNodes.

Every class here is a plain ``IrNode`` (via ``IrLeaf`` / ``IrCollection`` /
``IrComposite``) with a custom ``__call__``. The action-algebra adds the
operations grammar AST nodes don't cover: sibling lookup, joining,
branching, short-circuit, escape hatches.

For procedural cases (helper-name allocation, escape encoding, symbol
lookups), wrap the logic in :class:`IrCallable`.
"""

from __future__ import annotations

from abc import abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable, ClassVar

from lexic.ir.nodes import IrCollection, IrComposite, IrLeaf, IrNode

if TYPE_CHECKING:
    from lexic.ir.walk import IrDispatch


class _Return(BaseException):
    """Control-flow exception raised by :class:`IrReturn`.

    Inherits ``BaseException`` (not ``Exception``) so :class:`IrCallable`
    bodies that wrap their work in ``except Exception:`` cannot swallow it.
    """

    def __init__(self, value: Any) -> None:
        super().__init__()
        self.value = value
```

- [ ] **Step 4: Pass.**

- [ ] **Step 5: Commit.**

```bash
git add src/lexic/ir/action.py tests/unit/lexic/ir/test_action.py
git commit -m "ir/action: module skeleton + _Return BaseException"
```

---

### Task 1.3: `IrField` — non-IrNode attribute as str

```python
def test_irfield_reads_str_of_attribute():
    """IrField reads any attribute of the dispatched node and stringifies it.
    Uses IrCharClass(pattern, negated) — `negated` is a non-IrNode attribute."""
    from lexic.ir.action import IrField
    from lexic.ir.nodes import IrCharClass

    node = IrCharClass("a-z", negated=True)
    result: str = IrField("negated")(None, node, ())
    assert result == "True"
```

Implementation:

```python
@dataclass(frozen=True, slots=True, repr=False)
class IrField(IrLeaf[str]):
    """``str(getattr(node, name))`` — read a non-IrNode attribute of the dispatched node."""

    name: str

    def __call__(self, _d, node: IrNode, _nc: tuple) -> str:
        return str(getattr(node, self.name))
```

---

### Task 1.4: `IrCallable[_T]` — procedural escape hatch (generic)

```python
@dataclass(frozen=True, slots=True, eq=False, repr=False)
class IrCallable[_T](IrLeaf[_T]):
    """Procedural body. ``handler(dispatch, node, new_children) -> _T``.

    Generic in ``_T``; callers can narrow at construction:
    ``IrCallable[str](my_handler)``.
    """

    handler: Callable[["IrDispatch[Any]", IrNode, tuple], _T]

    def __call__(self, d: "IrDispatch[Any]", node: IrNode, new_children: tuple) -> _T:
        return self.handler(d, node, new_children)

    def _inner_str(self) -> str:
        name = getattr(self.handler, "__name__", "callable")
        return f"<{name}>"
```

---

### Task 1.5: `IrChild[_U]` and `IrChildren[_U]` — sibling lookup (generic)

**Semantic clarification — `_U` is the dispatched result type, not the child node type.** `new_children[idx]` holds whatever the dispatcher returned for that child: `None` under `IrVisitor`, `IrNode` under `IrTransformer`, `str` under `IrEmitter`. So `IrChild[str]("body")` is correct under an `IrEmitter` — the dispatched body-result is a `str`. Parameterizing by the child's *static class* (e.g. `IrChild[IrLiteral]("body")`) gives a misleading return type.

```python
@dataclass(frozen=True, slots=True, repr=False)
class IrChild[_U](IrLeaf[_U]):
    """Single child by name from the dispatched composite's ``_child_attrs``.

    Generic in ``_U`` — the dispatcher's per-child result type, not the
    child's static class. Under ``IrEmitter`` (``_T = str``), each entry of
    ``new_children`` is a ``str``; so ``IrChild[str]("body")`` is the right
    parameterization. Under ``IrTransformer`` (``_T = IrNode``), use
    ``IrChild[IrNode]("body")``.
    """

    name: str

    def __call__(self, _d, node: IrNode, new_children: tuple) -> _U:
        attrs = getattr(type(node), "_child_attrs", ())
        try:
            idx = attrs.index(self.name)
        except ValueError as exc:
            raise ValueError(
                f"IrChild({self.name!r}): {type(node).__name__} has no such child "
                f"(known: {attrs})"
            ) from exc
        return new_children[idx]


@dataclass(frozen=True, slots=True, repr=False)
class IrChildren[_U](IrLeaf[tuple[_U, ...]]):
    """Full tuple of dispatched children from the collection's ``_items_attr``.

    Generic in ``_U`` — same semantics as ``IrChild[_U]``: ``_U`` is the
    dispatcher's per-child result type. Return type is ``tuple[_U, ...]``,
    distinct from ``IrChild[_U]`` at the type level.
    """

    name: str

    def __call__(self, _d, node: IrNode, new_children: tuple) -> tuple[_U, ...]:
        items_attr = getattr(type(node), "_items_attr", None)
        if items_attr != self.name:
            raise ValueError(
                f"IrChildren({self.name!r}): {type(node).__name__} _items_attr "
                f"is {items_attr!r}"
            )
        return new_children
```

The shape distinction (`_U` vs `tuple[_U, ...]`) is visible at every call site. The per-dispatcher type narrowing is opt-in: flavour code that knows its emitter returns `str` writes `IrChild[str]("body")` for full precision; code that doesn't care writes `IrChild[Any]("body")`.

---

### Task 1.6: `IrConcat` — string concatenation

```python
@dataclass(frozen=True, slots=True, repr=False)
class IrConcat(IrCollection[str, IrNode[str]]):
    """Evaluate ``parts`` in order; return ``"".join(...)`` of results.

    ``_T = str`` (call return); ``_U = IrNode[str]`` (element type). Each
    part is ``IrNode[str]`` so the join is type-safe.
    """

    _items_attr: ClassVar[str] = "parts"
    parts: tuple[IrNode[str], ...] = ()

    def __call__(self, d, node: IrNode, new_children: tuple) -> str:
        return "".join(p(d, node, new_children) for p in self.parts)
```

Note: the canonical version's `str()` coercion isn't needed — `IrNode[str]` already guarantees `str` results. If an `IrCallable[int]` or similar is intentionally embedded, wrap it in an `IrCallable[str]` adapter.

---

### Task 1.7: `IrJoin` — variable-arity join with separator

```python
@dataclass(frozen=True, slots=True, repr=False)
class IrJoin(IrComposite[str]):
    """Variable-arity join. ``_T = str`` — overrides the IrNode default.

    Evaluates ``children_op`` (typically ``IrChildren[IrLiteral]("items")``)
    to get a tuple of stringifiable results; joins with ``separator.value``;
    returns ``empty.value`` if the iterable is empty.
    """

    _child_attrs: ClassVar[tuple[str, ...]] = ("children_op", "separator", "empty")
    children_op: IrNode[tuple[Any, ...]]
    separator: IrLiteral
    empty: IrLiteral

    def __call__(self, d, node: IrNode, new_children: tuple) -> str:
        items = self.children_op(d, node, new_children)
        if not items:
            return self.empty.value
        return self.separator.value.join(str(it) for it in items)
```

---

### Task 1.8: `IrCond[_T]` — truthy-field branch (generic)

```python
@dataclass(frozen=True, slots=True, repr=False)
class IrCond[_T](IrComposite[_T]):
    """Truthy-field branch.

    If ``bool(getattr(node, field))`` is true, evaluate ``then_op``;
    else ``else_op``. Both branches must share ``_T``.
    """

    _child_attrs: ClassVar[tuple[str, ...]] = ("then_op", "else_op")
    field: str
    then_op: IrNode[_T]
    else_op: IrNode[_T]

    def __call__(self, d, node: IrNode, new_children: tuple) -> _T:
        branch = self.then_op if getattr(node, self.field) else self.else_op
        return branch(d, node, new_children)
```

---

### Task 1.9: `IrReturn[_T]` — short-circuit via `_Return`

```python
@dataclass(frozen=True, slots=True, repr=False)
class IrReturn[_T](IrLeaf[_T]):
    """Short-circuit. Evaluating raises ``_Return(value)``.

    ``_T`` is the return type the surrounding dispatcher will yield once it
    catches the ``_Return``; ``IrReturn.__call__`` itself never returns
    normally.
    """

    value: _T

    def __call__(self, _d, _n, _nc) -> _T:
        raise _Return(self.value)
```

---

### Task 1.10: `IrAction`

```python
@dataclass(frozen=True, slots=True, eq=False, repr=False)
class IrAction(IrComposite):
    """Bind a target IR node type to a callable IrNode body.

    ``target_type`` is metadata (a ``type``, rendered in ``__str__`` but
    excluded from ``children()``). ``body`` is the single IrNode child;
    it must be callable with the dispatch signature.

    ``IrAction`` is not itself generic — different actions in the same
    table return different types. The dispatcher's ``_T`` constrains
    individual bodies, not the action wrapper.
    """

    _child_attrs: ClassVar[tuple[str, ...]] = ("body",)
    target_type: type
    body: IrNode[Any]

    def _inner_str(self) -> str:
        return f"{self.target_type.__name__}, {self.body}"
```

Test:

```python
def test_iraction_body_is_callable_and_returns_value():
    from lexic.ir.action import IrAction
    from lexic.ir.nodes import IrLiteral

    a = IrAction(IrLiteral, IrLiteral("Z"))
    result: str = a.body(None, None, ())
    assert result == "Z"
```

---

### Task 1.11: Re-export from `ir/__init__.py`

Updated import list — drops `IrOp` and `IrText`:

```python
from lexic.ir.action import (
    IrAction,
    IrCallable,
    IrChild,
    IrChildren,
    IrCond,
    IrConcat,
    IrField,
    IrJoin,
    IrReturn,
)
```

`IrLiteral` is already re-exported from `ir/nodes.py`; nothing to add for it.

---

## Step 2 — Rewrite `ir/walk.py` — new `IrDispatch` + presets

Replaces the current `IrDispatch` / `IrVisitor` / `IrTransformer` (with `_CHILDREN` / `_REBUILD` / `_DUMP` central tables) with the action-driven substrate. Adds `IrEmitter`.

**`IrDispatch` IS an `IrNode`.** Specifically, `IrDispatch[_T](IrCollection[_T, IrAction])` — its children are the actions tuple, exactly as the canonical spec intended. P13 ("IR describes IR") holds end-to-end: action bodies AND the dispatcher itself are IR trees.

Reconciling the signatures: `IrCollection.__call__(self, d, n, nc) -> _T` (the IrNode action-body protocol) and the dispatcher's public `__call__(self, node) -> _T` are reconciled by giving `IrDispatch.__call__` three positional-only parameters where only the first is meaningful. The base `IrCollection` default (`tuple(c(d, n, nc) for c in self.children())`) is overridden with the dispatch engine. Calling `IrVisitor()(root)` passes `root` as the first arg; the other two default to `None` and `()`. The signature is LSP-compatible with the IrNode protocol — no `type: ignore` — but only the first positional arg is read.

In practice, `IrDispatch` is never invoked *as* an action body (it's the engine, not the body), so the unused `(n, nc)` positional slots are vestigial-but-honest: they're the price of structural compatibility with the IrNode protocol, and they make the "IrDispatch is an IrCollection of IrActions" claim hold rigorously.

### Task 2.1: New `IrDispatch` — entry/recursion split + MRO resolve

**Files:**
- Modify: `src/lexic/ir/walk.py` (full rewrite)
- Modify: `tests/unit/lexic/ir/test_walk.py` (full rewrite)

- [ ] **Step 1: Write failing tests** (replace existing test file contents):

```python
# tests/unit/lexic/ir/test_walk.py
"""Tests for ir/walk.py — IrDispatch substrate."""

import pytest

from lexic.exceptions import UnsupportedConstructError
from lexic.ir.action import IrAction, IrCallable, IrReturn, _Return
from lexic.ir.nodes import (
    IrAlternation,
    IrAst,
    IrGroup,
    IrItem,
    IrLeaf,
    IrLiteral,
    IrNode,
    IrRule,
    IrRuleRef,
    IrSequence,
)


def _tiny_ast() -> IrAst:
    """Build a small AST for traversal tests."""
    rule = IrRule(
        name="r",
        body=IrAlternation(arms=(
            IrSequence(items=(IrItem(atom=IrRuleRef(name="r")),)),
        )),
    )
    return IrAst(rules=(rule,), start="r")


# ── IrDispatch fundamentals ──────────────────────────────────────────


def test_irdispatch_is_an_ircollection_of_actions():
    """IrDispatch IS an IrCollection — its children are the actions tuple.
    Preserves P13 (IR describes IR) end-to-end."""
    from lexic.ir.nodes import IrCollection
    from lexic.ir.walk import IrDispatch

    a = IrAction(IrLiteral, IrLiteral("x"))
    d: IrDispatch[str] = IrDispatch(actions=(a,))
    assert isinstance(d, IrCollection)
    assert d.children() == (a,)
    assert d.actions == (a,)


def test_irdispatch_call_signature_is_ircompatible_three_positional_args():
    """IrDispatch.__call__ accepts the IrNode action-body protocol signature
    (3 positional args), but only the first is meaningful as the root."""
    from lexic.ir.walk import IrVisitor

    # Single-arg form (standard entry).
    assert IrVisitor()(IrLiteral("a")) is None
    # Three-arg form (LSP-compatible with IrNode.__call__(d, n, nc)).
    # Second/third are unused; passing anything works.
    assert IrVisitor()(IrLiteral("a"), None, ()) is None


def test_irdispatch_empty_actions_falls_through_to_default():
    """Bare IrDispatch's default is implemented per-preset; test via IrVisitor."""
    from lexic.ir.walk import IrVisitor

    assert IrVisitor()(IrLiteral("x")) is None


def test_irdispatch_resolves_via_mro_concrete_first():
    """A concrete-type action wins over an IrNode-keyed catch-all."""
    from lexic.ir.walk import IrVisitor

    seen: list[str] = []
    leaf_action = IrAction(IrLeaf, IrCallable(lambda d, n, nc: seen.append("leaf")))
    lit_action = IrAction(IrLiteral, IrCallable(lambda d, n, nc: seen.append("lit")))
    d = IrVisitor(actions=(leaf_action, lit_action))
    d(IrLiteral("x"))
    assert seen == ["lit"]


def test_irdispatch_falls_through_to_abstract_action_when_no_concrete_match():
    from lexic.ir.walk import IrVisitor

    seen: list[str] = []
    leaf_action = IrAction(IrLeaf, IrCallable(lambda d, n, nc: seen.append("leaf")))
    d = IrVisitor(actions=(leaf_action,))
    d(IrRuleRef("r"))   # IrRuleRef is an IrLeaf subclass
    assert seen == ["leaf"]


def test_irdispatch_walks_children_automatically():
    """An action on the root sees new_children already dispatched."""
    from lexic.ir.walk import IrVisitor

    visited: list[type] = []

    def _on(_d, n, _nc):
        visited.append(type(n))

    d = IrVisitor(actions=(IrAction(IrNode, IrCallable(_on)),))
    d(_tiny_ast())
    assert IrRuleRef in visited
    assert IrItem in visited


# ── IrReturn short-circuit ───────────────────────────────────────────


def test_irreturn_short_circuits_at_entry():
    """First IrRuleRef raises _Return(True); rest of subtree is not visited."""
    from lexic.ir.walk import IrVisitor

    visit_count = 0

    def _on_ref(_d, _n, _nc):
        nonlocal visit_count
        visit_count += 1
        raise _Return(True)

    d = IrVisitor(actions=(IrAction(IrRuleRef, IrCallable(_on_ref)),))
    ast = IrAst(
        rules=(
            IrRule(
                name="r",
                body=IrAlternation(arms=(
                    IrSequence(items=(
                        IrItem(atom=IrRuleRef(name="a")),
                        IrItem(atom=IrRuleRef(name="b")),
                    )),
                )),
            ),
        ),
        start="r",
    )
    result = d(ast)
    assert result is True
    assert visit_count == 1


def test_irreturn_via_op_unwinds():
    """IrReturn(value) body raises _Return; dispatcher entry returns value."""
    from lexic.ir.walk import IrVisitor

    d = IrVisitor(actions=(IrAction(IrRuleRef, IrReturn(True)),))
    assert d(IrRuleRef("x")) is True


# ── Resolve cache ────────────────────────────────────────────────────


def test_resolve_cache_memoizes_negative_lookups():
    """A type with no matching action caches None and stays cached."""
    from lexic.ir.walk import IrVisitor

    d = IrVisitor(actions=(IrAction(IrLiteral, IrCallable(lambda d, n, nc: None)),))
    d(IrRuleRef("x"))
    assert d._resolve_cache[IrRuleRef] is None


def test_frozen_dispatcher_cannot_rebind_resolve_cache_slot():
    """The cache slot is frozen; rebinding raises."""
    from dataclasses import FrozenInstanceError
    from lexic.ir.walk import IrVisitor

    d = IrVisitor()
    with pytest.raises(FrozenInstanceError):
        d._resolve_cache = {}


def test_cache_contents_are_mutable_even_though_slot_is_frozen():
    """Cache mutation (adding entries) is permitted; only slot rebinding is blocked."""
    from lexic.ir.walk import IrVisitor

    d = IrVisitor(actions=(IrAction(IrLiteral, IrCallable(lambda d, n, nc: None)),))
    assert d._resolve_cache == {}
    d(IrLiteral("x"))
    assert IrLiteral in d._resolve_cache
    d(IrLiteral("y"))  # cache mutated, not rebound
```

Note: the canonical plan's test ignores on `_resolve_cache` are removed. The slot is declared on the dataclass — no attribute-resolution issue. If pyright flags the rebind line (assigning to a frozen-dataclass field for the `FrozenInstanceError` test), the fix is to assign via `object.__setattr__(d, "_resolve_cache", {})` — which raises the same `FrozenInstanceError` at runtime and bypasses the static check.

- [ ] **Step 2: Run; expect failures** (old walk.py still in place).

- [ ] **Step 3: Rewrite `src/lexic/ir/walk.py`**

```python
"""IrDispatch — action-driven IR walker.

IrDispatch[_T] is an IrCollection of IrAction; its children() returns the
actions tuple. P13 (IR describes IR) holds end-to-end: action bodies AND
the dispatcher itself are IR trees.

Calling the dispatcher on a node:

  1. Recurses node.children() to build a new_children tuple.
  2. Resolves the matching IrAction via concrete-first MRO walk on
     type(node), memoized in _resolve_cache.
  3. If matched, calls the action body as ``action.body(self, node,
     new_children)``; else falls through to the preset _default.

Skip-recursion is intrinsic to IrReturn (raises _Return, a BaseException
subclass). The dispatcher's __call__ catches once at the top; internal
recursion does not catch, so the exception unwinds naturally.

Signature compatibility: ``IrDispatch.__call__(root, _n=None, _nc=())``
takes three positional-only args to match the IrNode action-body protocol
(IrCollection's inherited ``__call__(d, n, nc) -> _T``). Only the first
arg is meaningful — it's the dispatched root. The other two are vestigial
slots that preserve LSP. Calling ``IrVisitor()(root)`` works; calling
``IrVisitor()(root, x, y)`` works and ignores x, y.

Presets:
  IrVisitor      _T = None      default: None
  IrTransformer  _T = IrNode    default: node.rebuild(new_children) if changed
  IrEmitter      _T = str       default: str(node) if actions empty,
                                else raise UnsupportedConstructError
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar

from lexic.exceptions import UnsupportedConstructError
from lexic.ir.action import IrAction, _Return
from lexic.ir.nodes import IrCollection, IrNode


@dataclass(frozen=True, slots=True, repr=False)
class IrDispatch[_T](IrCollection[_T, IrAction]):
    """Action-driven walker — an IrCollection of IrActions.

    :ivar actions: Per-type action table. Concrete keys win over
        abstract keys; MRO walk is concrete-first.
    """

    _items_attr: ClassVar[str] = "actions"
    actions: tuple[IrAction, ...] = ()
    _resolve_cache: dict[type, IrAction | None] = field(
        init=False, default_factory=dict, hash=False, compare=False, repr=False,
    )

    def __call__(self, node: IrNode, /, *_unused: object) -> _T:
        """Entry point. Catches ``_Return`` once at the top.

        :param node: Root of the IR subtree to dispatch. Positional-only,
            matching position 0 of ``IrCollection.__call__(d, n, nc)``.
        :param _unused: LSP slack — soaks up the ``n`` and ``new_children``
            positions of the IrNode action-body protocol when ``IrDispatch``
            is held under that protocol's type. ``IrDispatch`` is never
            invoked as an action body in practice; this is purely for
            signature compatibility with ``IrCollection.__call__``.
        :returns: The dispatched value of type ``_T``.
        """
        try:
            return self._walk(node)
        except _Return as ret:
            return ret.value

    def _walk(self, node: IrNode) -> _T:
        """Recursive engine. Does not catch ``_Return``."""
        new_children = tuple(self._walk(c) for c in node.children())
        action = self._resolve(type(node))
        if action is not None:
            return action.body(self, node, new_children)
        return self._default(node, new_children)

    def _resolve(self, node_type: type) -> IrAction | None:
        """Concrete-first MRO walk against ``self.actions``.

        Memoized in ``_resolve_cache``; misses cached as ``None``.
        """
        cache = self._resolve_cache
        if node_type in cache:
            return cache[node_type]
        for cls in node_type.__mro__:
            for action in self.actions:
                if action.target_type is cls:
                    cache[node_type] = action
                    return action
        cache[node_type] = None
        return None

    def _default(self, node: IrNode, new_children: tuple) -> _T:
        """Behaviour when no action matched. Presets override.

        Base default raises — bare ``IrDispatch`` shouldn't be used
        directly in production; production code uses a preset.
        """
        raise UnsupportedConstructError(
            f"{type(self).__name__}: no action for {type(node).__name__!r} "
            f"and no preset default configured"
        )
```

**Signature compatibility note.** The override uses `(node, /, *_unused)` — `node` is positional-only (matching position 0 of the inherited `(d, n, nc)`); `*_unused` absorbs any remaining positional args. Positional-only `/` means the name `node` doesn't conflict with the supertype's `d`. Pyright accepts this pattern as an LSP-compatible override of `IrCollection.__call__(self, d, n, nc) -> _T` because the override signature accepts every call shape the supertype accepts (`disp(root)`, `disp(root, n, nc)`, etc.).

If pyright still flags the override after Task 2.1's tests are written, the fallback is to name the param `d` (matching the base) and document at every entry call site that `d` doubles as "the root node when IrDispatch is invoked as a dispatcher". Less readable, no `type: ignore`.

- [ ] **Step 4: Run tests; partial pass.** `IrVisitor` / `IrTransformer` / `IrEmitter` tests still fail.

- [ ] **Step 5: Add presets** (append to walk.py):

```python
@dataclass(frozen=True, slots=True, repr=False)
class IrVisitor(IrDispatch[None]):
    """Side-effect walker. _T=None; default returns None."""

    def _default(self, _node: IrNode, _new_children: tuple) -> None:
        return None


@dataclass(frozen=True, slots=True, repr=False)
class IrTransformer(IrDispatch[IrNode]):
    """Rewrites the IR. Default: rebuild if any child changed, else identity."""

    def _default(self, node: IrNode, new_children: tuple) -> IrNode:
        old = node.children()
        if not old or all(nc is oc for nc, oc in zip(new_children, old)):
            return node
        return node.rebuild(new_children)


@dataclass(frozen=True, slots=True, repr=False)
class IrEmitter(IrDispatch[str]):
    """Produces strings. Default: ``str(node)`` if empty actions
    (canonical-form fallback); raise ``UnsupportedConstructError`` if
    actions are configured but none match (closed-world flavour).
    """

    def _default(self, node: IrNode, _new_children: tuple) -> str:
        if not self.actions:
            return str(node)
        raise UnsupportedConstructError(
            f"{type(self).__name__}: no action for node type "
            f"{type(node).__name__!r}"
        )
```

- [ ] **Step 6: Run tests; expect pass.** All tests in `test_walk.py` green.

- [ ] **Step 7: Add presets tests**

```python
# Append to tests/unit/lexic/ir/test_walk.py

def test_irtransformer_empty_actions_is_identity():
    from lexic.ir.walk import IrTransformer

    seq = IrSequence(items=(IrItem(atom=IrLiteral("a")),))
    assert IrTransformer()(seq) == seq


def test_irtransformer_rebuilds_on_child_change():
    from lexic.ir.walk import IrTransformer

    def _swap(_d, _n, _nc):
        return IrLiteral("Z")

    t = IrTransformer(actions=(IrAction(IrLiteral, IrCallable(_swap)),))
    item = IrItem(atom=IrLiteral("a"))
    new = t(item)
    assert isinstance(new, IrItem)
    assert new.atom == IrLiteral("Z")


def test_iremitter_empty_actions_falls_back_to_str_node():
    from lexic.ir.walk import IrEmitter

    out = IrEmitter()(IrLiteral("hi"))
    assert "hi" in out


def test_iremitter_with_actions_raises_on_unhandled_type():
    from lexic.ir.walk import IrEmitter

    e = IrEmitter(actions=(IrAction(IrLiteral, IrLiteral("L")),))
    with pytest.raises(UnsupportedConstructError):
        e(IrRuleRef("x"))


def test_iremitter_iraction_irnode_acts_as_per_instance_default():
    """A user-supplied IrAction(IrNode, ...) catches everything; preset default never fires."""
    from lexic.ir.walk import IrEmitter

    e = IrEmitter(actions=(
        IrAction(IrLiteral, IrLiteral("L")),
        IrAction(IrNode, IrLiteral("ANY")),
    ))
    assert e(IrRuleRef("x")) == "ANY"
    assert e(IrLiteral("y")) == "L"
```

- [ ] **Step 8: Run; pass.**

- [ ] **Step 9: Commit**

```bash
git add src/lexic/ir/walk.py tests/unit/lexic/ir/test_walk.py
git commit -m "ir/walk: action-driven IrDispatch + IrVisitor/IrTransformer/IrEmitter presets

Replaces the closed-subclass visit_<TypeName> machinery with action-table
dispatch. __call__ auto-walks node.children(), resolves IrAction via
concrete-first MRO, calls body(self, node, new_children). IrReturn raises
_Return (BaseException); __call__ catches once at top.

Removes _CHILDREN, _REBUILD, _DUMP, dump(), visit(), generic_visit(),
_combine(), visit_<TypeName> discovery. Adds IrEmitter as the third
canonical preset.

IrDispatch IS an IrCollection of IrActions. P13 (IR describes IR) holds
end-to-end. __call__ takes 3 positional-only args (LSP-compatible with
IrCollection's IrNode protocol); only the first (root) is meaningful."
```

### Task 2.2: Mechanical fixes — `codegen/aliases.py` and `codegen/model_emitter.py`

Unchanged from canonical plan. The closed-subclass visitors inside `codegen/` (`_PatternAliasVisitor`, `_IrRepr`) stay closed per scope-companion §3, but the old `IrDispatch`'s `visit` / `generic_visit` / `_combine` machinery is gone, so they convert to plain recursive classes.

The conversion is identical to canonical-plan Task 2.2 — see lines 1213–1389 of `2026-05-18-slice-b-substrate.md`. No substrate-related changes needed; both classes never depended on `IrOp` or `IrText`.

- [ ] **Step 1: Identify callsites** — `uv run rg -n "\.visit\(|generic_visit|visit_Ir|_combine" src/lexic/codegen/`
- [ ] **Step 2: Convert `_PatternAliasVisitor` to plain recursive class** (canonical-plan template).
- [ ] **Step 3: Convert `_IrRepr` to plain recursive class** (canonical-plan template).
- [ ] **Step 4: Run full suite; commit:**

```bash
git commit -am "codegen: convert closed-subclass visitors off old IrDispatch"
```

### Task 2.3: Delete dead helpers from `walk.py`

Already done by Task 2.1's rewrite. Spot-check:

- [ ] **Step 1:** `uv run rg -n "_CHILDREN|_REBUILD|_DUMP|\bdump\(|generic_visit|_combine|visit_Ir[A-Z]" src/ tests/` — expect zero hits in `src/lexic/ir/`.
- [ ] **Step 2: Run full suite; commit if needed.**

---

## Step 3 — Migrate IR-internal passes

### Task 3.1: `has_ruleref` — module-level singleton visitor

**Files:**
- Modify: `src/lexic/ir/derive.py` (replace `_RuleRefFinder` + `has_ruleref`)
- Modify: `tests/unit/lexic/ir/test_derive.py`

- [ ] **Step 1: Write failing test**

```python
# tests/unit/lexic/ir/test_derive.py — add
def test_has_ruleref_returns_true_when_subtree_contains_ruleref():
    from lexic.ir.derive import has_ruleref
    from lexic.ir.nodes import IrAlternation, IrItem, IrRuleRef, IrSequence

    body = IrAlternation(arms=(
        IrSequence(items=(IrItem(atom=IrRuleRef("foo")),)),
    ))
    assert has_ruleref(body) is True


def test_has_ruleref_returns_false_for_subtree_without_ruleref():
    from lexic.ir.derive import has_ruleref
    from lexic.ir.nodes import IrAlternation, IrItem, IrLiteral, IrSequence

    body = IrAlternation(arms=(
        IrSequence(items=(IrItem(atom=IrLiteral("a")),)),
    ))
    assert has_ruleref(body) is False


def test_has_ruleref_short_circuits_after_first_hit():
    """1000 IrRuleRefs across sibling arms — visit only the first."""
    from lexic.ir.action import IrAction, IrCallable, _Return
    from lexic.ir.nodes import IrAlternation, IrItem, IrRuleRef, IrSequence
    from lexic.ir.walk import IrVisitor

    deep = IrAlternation(arms=tuple(
        IrSequence(items=(IrItem(atom=IrRuleRef(f"r{i}")),))
        for i in range(1000)
    ))

    visit_count = 0

    def _on_ref(_d, _n, _nc):
        nonlocal visit_count
        visit_count += 1
        raise _Return(True)

    counting = IrVisitor(actions=(IrAction(IrRuleRef, IrCallable(_on_ref)),))
    result = counting(deep)
    assert result is True
    assert visit_count == 1
```

- [ ] **Step 2: Fail.**

- [ ] **Step 3: Replace `_RuleRefFinder` and `has_ruleref`** in `src/lexic/ir/derive.py`:

```python
from functools import cache

from lexic.ir.action import IrAction, IrReturn
from lexic.ir.walk import IrVisitor


_HAS_RULEREF: IrVisitor = IrVisitor(actions=(
    IrAction(IrRuleRef, IrReturn(True)),
))


@cache
def has_ruleref(node: IrNode) -> bool:
    """True if any IrRuleRef exists in the node subtree.

    Short-circuits on first hit via IrReturn(True). Cached on node
    identity for repeat queries.
    """
    return bool(_HAS_RULEREF(node))
```

Delete the `_RuleRefFinder` class entirely.

- [ ] **Step 4: Run tests; pass.**

- [ ] **Step 5: Commit**

```bash
git commit -am "ir/derive: has_ruleref as singleton IrVisitor + IrReturn

Replaces _RuleRefFinder closed subclass (which overrode visit()
to gate on a flag) with a module-level singleton IrVisitor carrying
one action: (IrRuleRef, IrReturn(True)). Short-circuit comes from
IrReturn raising _Return, which unwinds to the dispatcher's entry."
```

### Task 3.2: Hoist — `_EXTRACT_BODY` sub-dispatcher + transformer factory

**Naming note — `Quantifier` vs `IrQuantifier`.** The class is still named `Quantifier` at this point; Step 4 renames it. Use `Quantifier` here; Step 4's mechanical rename catches it.

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/lexic/ir/test_derive.py — add
def test_extract_body_returns_alternation_for_quantified_group_with_rulerefs():
    from lexic.ir.derive import _EXTRACT_BODY
    from lexic.ir.nodes import IrAlternation, IrGroup, IrItem, IrRuleRef, IrSequence

    body = IrAlternation(arms=(
        IrSequence(items=(IrItem(atom=IrRuleRef("x")),)),
    ))
    g = IrGroup(body=body)
    assert _EXTRACT_BODY(g) == body


def test_extract_body_returns_none_for_pure_literal_group():
    from lexic.ir.derive import _EXTRACT_BODY
    from lexic.ir.nodes import IrAlternation, IrGroup, IrItem, IrLiteral, IrSequence

    body = IrAlternation(arms=(
        IrSequence(items=(IrItem(atom=IrLiteral("x")),)),
    ))
    assert _EXTRACT_BODY(IrGroup(body=body)) is None


def test_extract_body_returns_none_for_non_group_atom():
    from lexic.ir.derive import _EXTRACT_BODY
    from lexic.ir.nodes import IrLiteral, IrRuleRef

    assert _EXTRACT_BODY(IrLiteral("x")) is None
    assert _EXTRACT_BODY(IrRuleRef("y")) is None


def test_hoist_helpers_extracts_quantified_ruleref_groups():
    from lexic.ir.derive import hoist_helpers
    from lexic.ir.nodes import (
        IrAlternation, IrAst, IrGroup, IrItem, IrRule, IrRuleRef, IrSequence, Quantifier,
    )

    inner_body = IrAlternation(arms=(
        IrSequence(items=(
            IrItem(atom=IrRuleRef("foo")),
            IrItem(atom=IrRuleRef("bar")),
        )),
    ))
    rule = IrRule(
        name="parent",
        body=IrAlternation(arms=(
            IrSequence(items=(
                IrItem(atom=IrGroup(body=inner_body), quantifier=Quantifier(1, None)),
            )),
        )),
    )
    ast = IrAst(rules=(rule,), start="parent")
    new_ast, helpers = hoist_helpers(ast)
    assert len(helpers) == 1
    assert helpers[0].body == inner_body
    parent_item = new_ast.rules[0].body.arms[0].items[0]
    assert isinstance(parent_item.atom, IrRuleRef)
    assert parent_item.atom.name == helpers[0].name


def test_hoist_helpers_leaves_pure_literal_group_unchanged():
    from lexic.ir.derive import hoist_helpers
    from lexic.ir.nodes import (
        IrAlternation, IrAst, IrGroup, IrItem, IrLiteral, IrRule, IrSequence, Quantifier,
    )

    inner_body = IrAlternation(arms=(
        IrSequence(items=(IrItem(atom=IrLiteral("a")),)),
    ))
    rule = IrRule(
        name="r",
        body=IrAlternation(arms=(
            IrSequence(items=(
                IrItem(atom=IrGroup(body=inner_body), quantifier=Quantifier(1, None)),
            )),
        )),
    )
    ast = IrAst(rules=(rule,), start="r")
    new_ast, helpers = hoist_helpers(ast)
    assert helpers == []
    assert new_ast == ast
```

- [ ] **Step 2: Fail.**

- [ ] **Step 3: Replace `_HoistTransformer` and `hoist_helpers`** in `src/lexic/ir/derive.py`:

The substrate makes the dispatcher itself an `IrNode` — and a dataclass. We extend `IrTransformer` with the per-pass state directly (parent rule name, name set, helpers list) instead of capturing them in a factory closure. The action body reads state from the dispatcher passed as its first argument.

```python
from dataclasses import dataclass, field

from lexic.ir.action import IrAction, IrCallable
from lexic.ir.walk import IrDispatch, IrTransformer


# ── Recognition: is this atom a hoist candidate? ─────────────────────

def _group_extract(_d: IrDispatch, group: IrGroup, _nc: tuple) -> IrAlternation | None:
    """Return the group body when it should be hoisted, else None."""
    return group.body if has_ruleref(group.body) else None


def _no_extract(_d: IrDispatch, _n: IrNode, _nc: tuple) -> IrAlternation | None:
    """Default override for non-IrGroup atoms — never hoist."""
    return None


_EXTRACT_BODY: IrDispatch[IrAlternation | None] = IrDispatch(actions=(
    IrAction(IrGroup, IrCallable(_group_extract)),
    IrAction(IrNode, IrCallable(_no_extract)),
))


# ── Rewrite: stateful transformer ────────────────────────────────────

@dataclass(frozen=True, slots=True, repr=False)
class _HoistTransformer(IrTransformer):
    """IrTransformer with per-rule hoist state.

    Frozen dataclass; the mutable ``helpers`` list slot is frozen (can't be
    rebound) but its contents are mutable (the action body appends as it
    walks). Same pattern as ``IrDispatch._resolve_cache``.

    :ivar parent_name: Enclosing rule name; used to derive helper names.
    :ivar name_set: Mutable set of taken rule names. The action body adds
        helper names here as it allocates them.
    :ivar helpers: Mutable list. Each emitted helper rule is appended.
    """

    parent_name: str = ""
    name_set: set[str] = field(default_factory=set, hash=False, compare=False)
    helpers: list[IrRule] = field(default_factory=list, hash=False, compare=False)


def _hoist_item(d: _HoistTransformer, item: IrItem, new_children: tuple) -> IrItem:
    """Rewrite ``item`` if it's a quantified hoistable group; else identity."""
    rebuilt = item.rebuild(new_children)
    if rebuilt.quantifier == Quantifier(1, 1):
        return rebuilt
    body = _EXTRACT_BODY(rebuilt.atom)
    if body is None:
        return rebuilt
    name = _reserve_helper_name(d.parent_name, d.name_set)
    d.name_set.add(name)
    d.helpers.append(IrRule(name=name, body=body))
    return IrItem(atom=IrRuleRef(name=name), quantifier=rebuilt.quantifier)


_HOIST_ACTIONS: tuple[IrAction, ...] = (
    IrAction(IrItem, IrCallable(_hoist_item)),
)


def hoist_helpers(ast: IrAst) -> tuple[IrAst, list[IrRule]]:
    """Rewrite quantified groups-with-rulerefs into synthetic helper rules.

    :param ast: Source AST.
    :returns: ``(new_ast, helpers)`` — ``new_ast`` has the groups
        replaced by ``IrRuleRef`` to the helper; ``helpers`` carries
        the synthesized helper rules in emission order.
    """
    name_set: set[str] = {r.name for r in ast.rules}
    all_helpers: list[IrRule] = []
    new_rules: list[IrRule] = []
    for rule in ast.rules:
        t = _HoistTransformer(
            actions=_HOIST_ACTIONS,
            parent_name=rule.name,
            name_set=name_set,
        )
        new_body = t(rule.body)
        all_helpers.extend(t.helpers)
        new_rules.append(IrRule(rule.name, new_body))
    return IrAst(rules=tuple(new_rules), start=ast.start), all_helpers
```

Delete the old `_HoistTransformer` class entirely (the one with `visit_IrItem` closed-subclass dispatch). The new `_HoistTransformer` reuses the name — that's intentional.

Why this is cleaner than canonical-plan Task 3.2's factory pattern:
- No factory function returning `(transformer, captured_list)`. The transformer carries the list.
- No closure capturing `parent_name` / `helpers`. State is on the dataclass.
- Module-level `_HOIST_ACTIONS` — built once, shared across all per-rule dispatchers.
- The action body's `d` parameter is a real, typed `_HoistTransformer` (not a generic `IrDispatch` it can't introspect).

**State-sharing semantics** (intentional, not a leak): `name_set` is the *same set object* across all per-rule dispatchers — that's how helper-name allocation stays unique across rules. `helpers` is *per-rule fresh*: each loop iteration constructs a new `_HoistTransformer` with `field(default_factory=list)`, so its `helpers` list starts empty and collects only that rule's hoisted helpers. The outer `all_helpers` list aggregates them in rule order.

- [ ] **Step 4: Run tests; pass.** **Step 5: Run full suite; pass. Step 6: Commit:**

```bash
git commit -am "ir/derive: hoist via stateful _HoistTransformer subclass + _EXTRACT_BODY sub-dispatcher

Replaces the old _HoistTransformer (visit_IrItem closed subclass with
isinstance(new_atom, IrGroup) gate) with a new _HoistTransformer that
subclasses IrTransformer and carries parent_name, name_set, helpers
as dataclass fields. Action body reads state directly from the dispatcher
passed as its first argument. Recognition lives in _EXTRACT_BODY, a
sub-dispatcher with (IrGroup, has_ruleref) and (IrNode, None) actions —
open-set, no isinstance. name_set is shared across per-rule dispatchers
(global uniqueness); helpers is per-rule fresh."
```

---

## Step 4 — `Quantifier` → `IrQuantifier` rename

Pure mechanical rename. Separate step for blame clarity. **No substrate-level changes — the substrate redesign is independent of this rename.**

### Task 4.1: Rename across the codebase

**Files (all sites):**
- `src/lexic/ir/nodes.py` (definition)
- `src/lexic/ir/__init__.py` (export)
- `src/lexic/ir/derive.py`
- `src/lexic/parsing/lark_builder.py`, `meta_parser.py`, `transformer/build_transformer.py`
- `src/lexic/codegen/model_emitter.py`, `aliases.py`
- `src/lexic/grammars/flavour.py`, `gbnf/flavour.py`, `abnf/flavour.py`
- `src/lexic/ir/emit.py`
- `src/lexic/generate.py`
- All test files in `tests/`

Exclude (to be deleted in Steps 6–8): `src/lexic/grammars/gbnf/emitter.py`, `src/lexic/grammars/abnf/emitter.py`, `src/lexic/utils/quantifiers.py`.

- [ ] **Step 1:** `uv run rg "\bQuantifier\b" src/ tests/ --files-with-matches` — confirm site list.
- [ ] **Step 2: Rename the class in `nodes.py`** — change `class Quantifier(IrLeaf["Quantifier"]):` to `class IrQuantifier(IrLeaf["IrQuantifier"]):`. `_str_name` stays `"Q"` (compact for debug). Update the `__call__` return type to `"IrQuantifier"`.
- [ ] **Step 3: Update `IrItem` field type** — `quantifier: IrQuantifier = field(default_factory=IrQuantifier)`.
- [ ] **Step 4: Update `ir/__init__.py`** export.
- [ ] **Step 5: Rename references across remaining src/ files** — mechanical sed:

```bash
# GNU sed (Linux):
sed -i 's/\bQuantifier\b/IrQuantifier/g' <path>

# macOS / BSD sed lacks \b — use Python:
python3 -c "
import re, sys
p = sys.argv[1]
with open(p) as f: t = f.read()
t = re.sub(r'\bQuantifier\b', 'IrQuantifier', t)
with open(p, 'w') as f: f.write(t)
" <path>
```

Visually verify each diff. Exclude `gbnf/emitter.py`, `abnf/emitter.py`, `utils/quantifiers.py` (deleted in later steps).

- [ ] **Step 6: Update test files** — same sed over `tests/`.
- [ ] **Step 7: Run full suite** — `uv run pytest -q`. Expect pass.
- [ ] **Step 8: Run linters** — `uv run ruff check src/ tests/`.
- [ ] **Step 9: Commit:**

```bash
git commit -am "ir: rename Quantifier → IrQuantifier across codebase

Pure mechanical rename for naming consistency with the rest of the IR
node hierarchy. _str_name stays 'Q' (compact for debug); only the
Python class identity changes. Files deleted in later steps
(gbnf/emitter.py, abnf/emitter.py, utils/quantifiers.py) are not renamed."
```

---

## Step 5 — `Flavour` becomes `IrEmitter` + `render_specs`

### Task 5.1: Refactor `grammars/flavour.py`

**Files:**
- Modify: `src/lexic/grammars/flavour.py` (full rewrite)
- Modify: `tests/unit/lexic/grammars/test_flavour.py`

- [ ] **Step 1: Write failing test**

```python
# tests/unit/lexic/grammars/test_flavour.py — add
def test_flavour_is_subclass_of_iremitter():
    from lexic.grammars.flavour import Flavour
    from lexic.ir.walk import IrEmitter

    assert issubclass(Flavour, IrEmitter)


def test_flavour_requires_parse_quantifier_and_parse_charclass():
    from abc import ABC
    from lexic.grammars.flavour import Flavour

    assert issubclass(Flavour, ABC)
    abstract = Flavour.__abstractmethods__
    assert "parse_quantifier" in abstract
    assert "parse_charclass" in abstract
```

- [ ] **Step 2: Fail.**

- [ ] **Step 3: Rewrite `src/lexic/grammars/flavour.py`**

```python
"""Flavour ABC — config bundle every grammar flavour subclasses.

A Flavour:
- Carries per-flavour metadata as ClassVars (name, extensions, etc.).
- Inherits IrEmitter — its ``actions`` tuple holds the per-IR-type
  rendering rules.
- Declares ``parse_quantifier`` / ``parse_charclass`` as abstract
  staticmethods consumed by the meta-parser.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar

from lexic.ir.escapes import EscapeCodec
from lexic.ir.nodes import IrQuantifier
from lexic.ir.walk import IrEmitter


class Flavour(IrEmitter, ABC):
    """Base for every grammar flavour.

    :cvar name: Short flavour identifier (e.g. "gbnf").
    :cvar extensions: Tuple of file extensions handled.
    :cvar meta_grammar: Lark meta-grammar string for parsing source.
    :cvar escapes: EscapeCodec subclass for literal escape handling.
    :cvar line_comment: Line-comment prefix; empty disables @directive parsing.
    :cvar quantifier_symbols: Map from (min, max) bounds to emit text.
    """

    name: ClassVar[str]
    extensions: ClassVar[tuple[str, ...]]
    meta_grammar: ClassVar[str]
    escapes: ClassVar[type[EscapeCodec]]
    line_comment: ClassVar[str] = ""
    quantifier_symbols: ClassVar[dict[tuple[int, int | None], str]]

    @staticmethod
    @abstractmethod
    def parse_quantifier(text: str) -> IrQuantifier:
        """Parse a quantifier symbol into an IrQuantifier."""

    @staticmethod
    @abstractmethod
    def parse_charclass(text: str) -> tuple[str, bool]:
        """Parse a char class into (pattern, negated)."""
```

- [ ] **Step 4: Verify `MetaGrammarParser.for_flavour` still works**

```python
# tests/unit/lexic/parsing/test_meta_parser.py — add
def test_for_flavour_resolves_classvars_on_iremitter_subclass():
    from lexic.grammars.gbnf.flavour import GbnfFlavour
    from lexic.parsing.meta_parser import MetaGrammarParser

    assert isinstance(GbnfFlavour.meta_grammar, str)
    assert callable(GbnfFlavour.parse_quantifier)
    assert callable(GbnfFlavour.parse_charclass)
    parser = MetaGrammarParser.for_flavour(GbnfFlavour)
    assert parser is not None
```

This test validates after Steps 6/7 land.

- [ ] **Step 5: Run; pass. Step 6: Commit:**

```bash
git commit -am "grammars/flavour: Flavour becomes IrEmitter subclass

Metadata moves to ClassVars; behaviour moves to the actions tuple
inherited from IrEmitter. parse_quantifier and parse_charclass stay
as abstract staticmethods (consumed by meta_parser)."
```

### Task 5.2: Add `render_specs` to `ir/emit.py`

**Files:**
- Modify: `src/lexic/ir/emit.py`
- Modify: `tests/unit/lexic/ir/test_emit.py`

- [ ] **Step 1: Write failing test**

```python
# tests/unit/lexic/ir/test_emit.py
"""Tests for ir/emit.py — render_specs."""

from lexic.ir.emit import render_specs
from lexic.ir.nodes import IrItem, IrLiteral
from lexic.ir.spec import RuleSpec


def _spec(name: str, kind: str = "value_str") -> RuleSpec:
    return RuleSpec(
        rule_name=name,
        class_name=name.title(),
        parent_class_name="GrammarModel",
        kind=kind,
        items=[IrItem(atom=IrLiteral("x"))],
        field_map={},
    )


def test_render_specs_invokes_flavour_per_rule():
    calls: list[str] = []

    def fake_flavour(rule):
        calls.append(rule.name)
        return f"<{rule.name}>"

    out = render_specs([_spec("a"), _spec("b")], fake_flavour)
    assert calls == ["a", "b"]
    assert "<a>" in out
    assert "<b>" in out


def test_render_specs_joins_with_newlines_and_trailing_newline():
    out = render_specs([_spec("a"), _spec("b")], lambda r: "X")
    assert out == "X\nX\n"
```

Depends on `RuleSpec.to_ir_rule() -> IrRule`. Task 5.2a below adds it if missing.

### Task 5.2a: Add `RuleSpec.to_ir_rule()` if missing

Identical to canonical-plan Task 5.2a — see lines 2024–2122 of `2026-05-18-slice-b-substrate.md`. No substrate-related changes.

- [ ] **Step 1:** `grep -n "to_ir_rule" src/lexic/ir/spec.py` — skip if present.
- [ ] **Step 2: Write failing tests** for `test_rulespec_to_ir_rule_wraps_items_in_iralternation` and `test_rulespec_to_ir_rule_with_alternation_item_passes_through`.
- [ ] **Step 3: Implement** `RuleSpec.to_ir_rule` per canonical-plan template.
- [ ] **Step 4: Pass. Step 5: Commit:**

```bash
git commit -am "ir/spec: add RuleSpec.to_ir_rule() — reconstitute spec as IrRule"
```

### Task 5.2 (continued): Implement `render_specs`

- [ ] **Step 3: Implement**

```python
# src/lexic/ir/emit.py
"""render_specs — render a list of RuleSpec back to grammar text via a flavour."""

from __future__ import annotations

from collections.abc import Callable

from lexic.ir.nodes import IrNode


def render_specs(specs: list, flavour: Callable[[IrNode], str]) -> str:
    """Render a list of RuleSpecs to a grammar text string.

    :param specs: Topologically sorted list of RuleSpec instances.
    :param flavour: A flavour singleton (callable from IrEmitter); takes
        an IrNode and returns its rendered string.
    :returns: Newline-joined rule strings.
    """
    rules = [spec.to_ir_rule() for spec in specs]
    return "\n".join(flavour(rule) for rule in rules) + "\n"
```

- [ ] **Step 4: Pass. Step 5: Commit:**

```bash
git commit -am "ir/emit: add render_specs(specs, flavour) — thin shell"
```

---

## Step 6 — Migrate `GbnfFlavour`

### Task 6.1: Per-flavour callables

**Files:** Modify `src/lexic/grammars/gbnf/flavour.py`.

The four IrCallable-warranting cases from the spec: literal-escape encoding, char-class negation prefix, quantifier symbol-table lookup, AST newline-join. Implement four module-private helpers:

```python
def _gbnf_encode_literal(_d, node, _nc) -> str:
    """Escape the literal value per GBNF rules."""
    return GbnfEscapes.encode(node.value)


def _gbnf_charclass(_d, node, _nc) -> str:
    """Render char class with optional negation prefix."""
    prefix = "^" if node.negated else ""
    return f"[{prefix}{node.pattern}]"


def _gbnf_quantifier(_d, node, _nc) -> str:
    """Look up the GBNF quantifier symbol."""
    key = (node.min, node.max)
    try:
        return GbnfFlavour.quantifier_symbols[key]
    except KeyError as exc:
        raise UnsupportedConstructError(
            f"GBNF does not support quantifier {key}"
        ) from exc


def _gbnf_ast(_d, _node, new_children) -> str:
    """Render rules joined by newlines, trailing newline."""
    return "\n".join(new_children) + "\n"
```

- [ ] **Step 2: Write tests** — identical to canonical-plan Task 6.1's tests (`test_gbnf_encode_literal_returns_escaped_value`, `test_gbnf_charclass_renders_brackets_*`, `test_gbnf_quantifier_returns_*`, `test_gbnf_ast_*`). All call helpers as `_helper(None, node, ())` — `__call__` signature accepts `None` so no test ignores.
- [ ] **Step 3: Implement; commit:**

```bash
git commit -am "grammars/gbnf: per-flavour callable helpers"
```

### Task 6.2: `_GBNF_ACTIONS` tuple + `GBNF` singleton

- [ ] **Step 1: Build the action tuple in `gbnf/flavour.py`**

```python
from lexic.ir.action import (
    IrAction, IrCallable, IrChild, IrChildren, IrConcat, IrField, IrJoin,
)
from lexic.ir.nodes import (
    IrAlternation, IrAst, IrCharClass, IrGroup, IrItem, IrLiteral,
    IrQuantifier, IrRule, IrRuleRef, IrSequence,
)


_GBNF_ACTIONS: tuple[IrAction, ...] = (
    IrAction(IrLiteral,    IrConcat((IrLiteral('"'), IrCallable(_gbnf_encode_literal), IrLiteral('"')))),
    IrAction(IrCharClass,  IrCallable(_gbnf_charclass)),
    IrAction(IrRuleRef,    IrField("name")),
    IrAction(IrGroup,      IrConcat((IrLiteral("("), IrChild("body"), IrLiteral(")")))),
    IrAction(IrQuantifier, IrCallable(_gbnf_quantifier)),
    IrAction(IrItem,       IrConcat((IrChild("atom"), IrChild("quantifier")))),
    IrAction(IrSequence,   IrJoin(IrChildren("items"), IrLiteral(" "), IrLiteral('""'))),
    IrAction(IrAlternation,IrJoin(IrChildren("arms"), IrLiteral(" | "), IrLiteral(""))),
    IrAction(IrRule,       IrConcat((IrField("name"), IrLiteral(" ::= "), IrChild("body")))),
    IrAction(IrAst,        IrCallable(_gbnf_ast)),
)


class GbnfFlavour(Flavour):
    """GBNF grammar flavour."""

    name = "gbnf"
    extensions = (".gbnf",)
    meta_grammar = GBNF_META_GRAMMAR
    escapes = GbnfEscapes
    line_comment = "#"
    quantifier_symbols = {
        (1, 1): "",
        (0, 1): "?",
        (0, None): "*",
        (1, None): "+",
    }

    @staticmethod
    def parse_quantifier(text: str) -> IrQuantifier:
        # Lift verbatim from pre-migration GbnfFlavour; return type already IrQuantifier per Step 4.
        ...

    @staticmethod
    def parse_charclass(text: str) -> tuple[str, bool]:
        # Lift verbatim from pre-migration GbnfFlavour.
        ...


GBNF: GbnfFlavour = GbnfFlavour(actions=_GBNF_ACTIONS)
```

**Substrate change vs canonical plan:** all `IrText("...")` → `IrLiteral("...")`. The two are the same constant in the new substrate; `IrLiteral` carries the role.

- [ ] **Step 2: Run full test suite** — `uv run pytest -q`. If any GBNF round-trip test fails, diff against the old `GbnfEmitter`.

- [ ] **Step 3: Commit:**

```bash
git commit -am "grammars/gbnf: GBNF singleton with _GBNF_ACTIONS tuple

GbnfFlavour subclasses IrEmitter via Flavour. Module-level GBNF
singleton built once with the per-IR-type action tuple. Pure action
bodies cover IrRuleRef, IrGroup, IrItem, IrSequence, IrAlternation,
IrRule. IrCallable bodies cover IrLiteral (escape encoding), IrCharClass
(negation prefix), IrQuantifier (symbol-table lookup), IrAst (newline
join + trailing newline). String constants use IrLiteral (which absorbed
the IrText role in the substrate redesign)."
```

### Task 6.3: Delete `grammars/gbnf/emitter.py`

- [ ] **Step 1:** `uv run rg -n "grammars\.gbnf\.emitter|GbnfEmitter" src/ tests/` — expect references only in the file about to be deleted and its test.
- [ ] **Step 2:** `git rm src/lexic/grammars/gbnf/emitter.py tests/unit/lexic/grammars/gbnf/test_emitter.py`.
- [ ] **Step 3: Run suite; commit:**

```bash
git commit -m "grammars/gbnf: delete emitter.py — superseded by GBNF singleton"
```

---

## Step 7 — Migrate `AbnfFlavour`

ABNF specifics: prefix-quantifier ordering on `IrItem`, ABNF's own quantifier symbols.

### Task 7.1: Per-flavour callables

**Files:** Modify `src/lexic/grammars/abnf/flavour.py`.

- [ ] **Step 1: Read existing `AbnfEmitter`** — `cat src/lexic/grammars/abnf/emitter.py`. This file holds the canonical rendering per IR-type case; lift each method's body into a helper with signature `(_d, node, _nc) -> str`.

- [ ] **Step 2: Add four module-private helpers to `abnf/flavour.py`** — `_abnf_encode_literal`, `_abnf_charclass`, `_abnf_quantifier`, `_abnf_ast`. Same signature shape as GBNF. The `_abnf_charclass` body MUST be lifted verbatim from `AbnfEmitter` (ABNF uses `%x41-5A` style, not `[A-Z]`); leave a `NotImplementedError` placeholder if the engineer hasn't lifted yet — fail loudly.

- [ ] **Step 3: Write unit tests** — mirror canonical Task 7.1's test shape; helpers called as `_helper(None, node, ())`.

- [ ] **Step 4: Implement; commit:**

```bash
git commit -am "grammars/abnf: per-flavour callable helpers"
```

### Task 7.2: `_ABNF_ACTIONS` tuple + `ABNF` singleton

- [ ] **Step 1: Build the action tuple in `abnf/flavour.py`** — mirrors `_GBNF_ACTIONS` with two key differences: prefix-quantifier ordering on `IrItem`, and ABNF's own `quantifier_symbols`.

```python
from lexic.ir.action import (
    IrAction, IrCallable, IrChild, IrChildren, IrConcat, IrField, IrJoin,
)
from lexic.ir.nodes import (
    IrAlternation, IrAst, IrCharClass, IrGroup, IrItem, IrLiteral,
    IrQuantifier, IrRule, IrRuleRef, IrSequence,
)


_ABNF_ACTIONS: tuple[IrAction, ...] = (
    IrAction(IrLiteral,    IrCallable(_abnf_encode_literal)),
    IrAction(IrCharClass,  IrCallable(_abnf_charclass)),
    IrAction(IrRuleRef,    IrField("name")),
    IrAction(IrGroup,      IrConcat((IrLiteral("("), IrChild("body"), IrLiteral(")")))),
    IrAction(IrQuantifier, IrCallable(_abnf_quantifier)),
    # KEY DIFFERENCE FROM GBNF: quantifier BEFORE atom for ABNF prefix form.
    IrAction(IrItem,       IrConcat((IrChild("quantifier"), IrChild("atom")))),
    IrAction(IrSequence,   IrJoin(IrChildren("items"), IrLiteral(" "), IrLiteral(""))),
    IrAction(IrAlternation,IrJoin(IrChildren("arms"), IrLiteral(" / "), IrLiteral(""))),
    IrAction(IrRule,       IrConcat((IrField("name"), IrLiteral(" = "), IrChild("body")))),
    IrAction(IrAst,        IrCallable(_abnf_ast)),
)


class AbnfFlavour(Flavour):
    """ABNF grammar flavour."""

    name = "abnf"
    extensions = (".abnf",)
    meta_grammar = ABNF_META_GRAMMAR
    escapes = AbnfEscapes
    line_comment = ";"
    quantifier_symbols = {
        # ABNF uses prefix notation: <min>*<max>element.
        # Verify against existing AbnfEmitter; placeholder values below.
        (1, 1): "",
        (0, 1): "*1",
        (0, None): "*",
        (1, None): "1*",
    }

    @staticmethod
    def parse_quantifier(text: str) -> IrQuantifier:
        # Lift verbatim from pre-migration AbnfFlavour.
        raise NotImplementedError("Lift from pre-migration AbnfFlavour")

    @staticmethod
    def parse_charclass(text: str) -> tuple[str, bool]:
        raise NotImplementedError("Lift from pre-migration AbnfFlavour")


ABNF: AbnfFlavour = AbnfFlavour(actions=_ABNF_ACTIONS)
```

Verify separator strings and quantifier symbols against the existing `AbnfEmitter`. After lifting, full suite must be green.

- [ ] **Step 2: Run full test suite.** **Step 3: Commit:**

```bash
git commit -am "grammars/abnf: ABNF singleton with _ABNF_ACTIONS tuple

Mirrors GbnfFlavour migration with ABNF-specific differences: prefix
quantifier ordering on IrItem, ABNF-specific separator strings, ABNF's
own quantifier_symbols table. String constants use IrLiteral."
```

### Task 7.3: Delete `grammars/abnf/emitter.py`

- [ ] **Step 1:** `uv run rg -n "grammars\.abnf\.emitter|AbnfEmitter" src/ tests/`.
- [ ] **Step 2:** `git rm src/lexic/grammars/abnf/emitter.py tests/unit/lexic/grammars/abnf/test_emitter.py`.
- [ ] **Step 3: Run suite; commit:**

```bash
git commit -m "grammars/abnf: delete emitter.py — superseded by ABNF singleton"
```

---

## Step 8 — Migrate consumers

### Task 8.1: `base.py` `to_grammar` flips to `GBNF` singleton

**Files:** Modify `src/lexic/base.py`, `tests/unit/lexic/test_base.py`.

- [ ] **Step 1:** `uv run rg -n "GbnfEmitter|gbnf\.emitter|to_gbnf" src/lexic/base.py`.
- [ ] **Step 2: Update import + call site** — `from lexic.grammars.gbnf.emitter import GbnfEmitter` → `from lexic.grammars.gbnf.flavour import GBNF`. `GbnfEmitter()(...)` → `GBNF(...)`.
- [ ] **Step 3: Update existing tests** that mocked `GbnfEmitter`.
- [ ] **Step 4: Run full suite; pass.**
- [ ] **Step 5: Update CLAUDE.md** — change the documented exception's import target from `lexic.grammars.gbnf.emitter` to the `GBNF` singleton in `lexic.grammars.gbnf.flavour`.
- [ ] **Step 6: Commit:**

```bash
git commit -am "base: to_gbnf flips to GBNF singleton"
```

### Task 8.2: `parsing/lark_builder.py` mechanical fixes

- [ ] **Step 1: Audit** — `uv run rg -n "\.visit\(|dump\(|_CHILDREN" src/lexic/parsing/`.
- [ ] **Step 2: Apply minimum fixes; commit if needed:**

```bash
git commit -am "parsing/lark_builder: mechanical fixes for new IrDispatch API"
```

### Task 8.3: Delete `utils/quantifiers.py`

- [ ] **Step 1:** `uv run rg -n "from lexic\.utils\.quantifiers|utils\.quantifiers" src/ tests/`.
- [ ] **Step 2:** `git rm src/lexic/utils/quantifiers.py tests/unit/lexic/utils/test_quantifiers.py`.
- [ ] **Step 3: Run suite; commit:**

```bash
git commit -m "utils: delete quantifiers.py — per-flavour quantifier rendering now in action tables"
```

---

## Step 9 — Opportunistic cleanup

### Task 9.1: `ir/helpers.py` — delete if trivially safe

- [ ] **Step 1: Audit** — `uv run rg -n "ir\.helpers|HelperRuleRegistry" src/ tests/`. If zero production callers, proceed.
- [ ] **Step 2: Delete:**

```bash
git rm src/lexic/ir/helpers.py tests/unit/lexic/ir/test_helpers.py
```

Remove `HelperRuleRegistry` from `ir/__init__.py` exports if listed.

- [ ] **Step 3: Run suite; commit:**

```bash
git commit -m "ir: delete helpers.py (HelperRuleRegistry — zero production callers)"
```

---

## Step 10 — Wiki + CLAUDE.md updates

### Task 10.1: Wiki updates

**Files:**
- Modify: `.wiki/lexic/architecture.md`
- Modify: `.wiki/lexic/flavour-system.md`
- Modify: `.wiki/lexic/ir-shapes.md`
- Modify: `.wiki/lexic/decisions.md`
- Modify: `.wiki/log.md`

- [ ] **Step 1: Update `architecture.md`**

Sections to add/update:
- **Substrate** — `IrNode[_T]` generic with `__call__(dispatch, node, new_children) -> _T`. A single module-scope `_T = TypeVar("_T", default="IrNode")` threads through `IrLeaf`, `IrCollection`, `IrComposite`; subclasses without explicit params inherit `_T = IrNode`. `IrAction` binds a target type to a callable IrNode body. Action-algebra nodes (`IrField`, `IrCallable`, `IrChild`, `IrChildren`, `IrConcat`, `IrJoin`, `IrCond`, `IrReturn`).
- **Dispatch mechanics** — auto-walk via `node.children()`, MRO-resolve concrete-first, `IrReturn` raising `_Return`. `IrDispatch[_T]` is an `IrCollection[_T, IrAction]`; its `children()` returns the actions tuple. `__call__` takes 3 positional-only args (LSP-compatible with the IrNode action-body protocol); only the first is meaningful at the entry call site.
- **Presets** — `IrVisitor` / `IrTransformer` / `IrEmitter` as concrete subclasses; default behaviours per preset.
- **IR-pass-by-action-table convention** — `has_ruleref`, `hoist_helpers` as examples.
- **IrQuantifier rename.**
- **Flavour-as-IrEmitter** — metadata as `ClassVar`s, behaviour as `actions` tuple, module-level singletons.
- **`IrText` deleted, `IrLiteral` absorbed the role.** `IrLiteral` carries dual duty: grammar AST literal and action-language string constant. The split lives in usage context, not type.

- [ ] **Step 2: Update `flavour-system.md`** — per-flavour singleton convention, action tuple structure, `IrCallable` usage guidelines (the four warranted cases).

- [ ] **Step 3: Update `ir-shapes.md`**
- `IrNode[_T]` generic; module-scope TypeVar defaults `_T = IrNode` for all bases that don't override.
- `IrQuantifier` rename note.
- `IrLiteral` dual role (grammar literal + string constant).
- Drop any `IrText` or `IrOp` references.

- [ ] **Step 4: Add decisions to `decisions.md`**
- P12 strengthened (IR passes by action table, not closed subclass).
- P13 holds end-to-end: action bodies AND the dispatcher are IR nodes. `IrDispatch[_T]` is an `IrCollection[_T, IrAction]`.
- P14 (`IrDispatch[_T]` is generic in the result type; LSP-compatible `__call__` signature with 3 positional-only args, only the root is read).
- P15 (concrete-first MRO; `IrAction(IrNode, …)` as default-override).
- P16 (short-circuit intrinsic to `IrReturn` via `_Return`).
- P17 (`IrLiteral` absorbs string-constant role; `IrText` deleted).
- P18 (every IR node is callable via `__call__(d, n, nc) -> _T`; `_T` defaults to `IrNode` via a single module-scope TypeVar shared across structural bases).

- [ ] **Step 5: Add `log.md` entry**

```markdown
## 2026-05-18 — Slice B closed: action substrate + Flavour-as-IrEmitter

Replaced the closed-subclass IrDispatch (visit_<TypeName>) with an action-table
substrate. Every IrNode is now callable; module-scope TypeVar defaults _T to
IrNode across IrLeaf / IrCollection / IrComposite. IrText deleted (IrLiteral
absorbs the role). Flavour becomes an IrEmitter;
GBNF and ABNF are now module-level singletons with action tuples. See
spec docs/superpowers/specs/2026-05-18-slice-b-substrate-design.md and
plan docs/superpowers/plans/2026-05-18-slice-b-substrate.md.
```

- [ ] **Step 6: Update CLAUDE.md**
- "Two deliberate exceptions" wording: first exception's import target is now `lexic.grammars.gbnf.flavour` (the `GBNF` singleton).
- Project layout section: `ir/action.py` (new), deleted `gbnf/emitter.py` / `abnf/emitter.py` / `utils/quantifiers.py`, possibly `ir/helpers.py`.
- Pipeline flow diagram: emit path now reads `flavour(node)` singleton call rather than constructing an emitter.
- IR types section: drop `IrText` / `IrOp` references; document `IrLiteral` dual role and `IrNode[_T]` generic.

- [ ] **Step 7: Commit:**

```bash
git commit -am "wiki + docs: document slice B substrate + Flavour-as-IrEmitter

- architecture.md: substrate, dispatch mechanics, presets,
  IR-pass-by-action-table convention, IrLiteral dual role.
- flavour-system.md: singleton convention, action tuple structure.
- ir-shapes.md: IrNode[_T] generic; IrQuantifier rename; IrLiteral
  dual role; IrText/IrOp removed.
- decisions.md: P12 strengthened, P13 (holds end-to-end), P14-P18.
- log.md: slice B closed entry.
- CLAUDE.md: two-exceptions wording, file tree, pipeline flow, IR types."
```

---

## Final verification

- [ ] **Step 1: Full suite** — `uv run pytest -q`. Expect 448+ tests pass.
- [ ] **Step 2: Lint clean** — `uv run ruff check src/ tests/`.
- [ ] **Step 3: Type-check clean** — run the project's type-checker; expect zero `type: ignore` and zero unresolved errors. Module-scope `_T = TypeVar("_T", default="IrNode")` from `typing_extensions` should resolve cleanly under pyright (verified via PoC).
- [ ] **Step 4: Round-trip spot-check** — `uv run pytest tests/integration/test_full_round_trip.py -v`. Every ground-truth grammar round-trips byte-equal.
- [ ] **Step 5: Anti-creep audit**

```bash
uv run rg -n "pre_parse_check|_SKIP_RECURSION|pre_recurse" src/ tests/
```

Expect zero hits.

```bash
uv run rg -n "\bIrOp\b|\bIrText\b" src/ tests/
```

Expect zero hits (both classes deleted).

```bash
uv run rg -n "\.eval\(" src/lexic/ tests/unit/lexic/ir/
```

Expect zero hits in action-related code (every action body call uses `(...)` not `.eval(...)`).

- [ ] **Step 6: Slice closed.** Optional: delete `.wiki/lexic/slice-b-status.md` if it exists.

---

## Risk-area mitigations (reminders during execution)

- **Typing precision loss on grammar AST `__call__`.** With `default=IrNode`, AST-node `__call__` returns are statically typed `IrNode`, not the concrete subclass. Verified acceptable because consumers go through `IrDispatch[_T]` for precision. If a test or call site genuinely needs the concrete return type, add a local `isinstance` narrow or parameterize the base explicitly (`class IrFooThing(IrLeaf["IrFooThing"]):`) at that single site.
- **Step 2 (Task 2.1) is the deepest cut.** If the rewrite is hairier than expected, split into 2.1a (introduce new dispatcher under a temporary name, migrate consumers one by one) and 2.1b (rename + delete old).
- **IrCallable discipline (Steps 6/7).** If a flavour action ends up using `IrCallable` for a case that should be a pure IrNode body (one of `IrRuleRef`, `IrGroup`, `IrItem`, `IrSequence`, `IrAlternation`, `IrRule`), stop and surface — that's the substrate failing to express something it should. Permitted `IrCallable` use is limited to the four documented per-flavour cases.
- **`_Return` semantics.** Run the explicit test that an `IrCallable` body wrapping its work in `except Exception:` does not swallow `_Return`. If that test fails, the inheritance is wrong.
- **MRO lookup.** `_resolve` must memoize negative hits — caching `None` for genuine misses — so the preset default fires instead of being re-resolved.
- **`IrAction.target_type` not a child.** Verify `IrAction(IrLiteral, IrLiteral("x")).children() == (IrLiteral("x"),)` — the `type` object must not appear in the children tuple.
- **IrLiteral dual role — clarify what "dual" means.** It's not "same class, two behaviours". It's the same `__call__ -> self.value` in both contexts, but it's *invoked* differently:
  - **As an action body** (e.g. inside `IrConcat((IrLiteral('"'), …, IrLiteral('"')))`): `IrLiteral.__call__(d, n, nc)` runs and returns `self.value`. Used as a string constant.
  - **As a dispatch target** (e.g. when `GBNF` walks an `IrLiteral` inside a grammar rule): `GBNF._walk` resolves the action for `IrLiteral` (which is `IrConcat((IrLiteral('"'), IrCallable(_gbnf_encode_literal), IrLiteral('"')))`), and calls *that* action body. `IrLiteral.__call__` itself is never invoked in this path; the dispatcher substitutes the action.

  Smoke test: build an `IrConcat((IrLiteral("a"), IrLiteral("b")))` and invoke it directly (`op(None, None, ())`) — expect `"ab"`. Build a grammar rule containing `IrLiteral("a")` and walk it through `GBNF` — expect `'"a"'` (quoted, escape-encoded). Both paths legal; they don't conflict because they activate different code.
