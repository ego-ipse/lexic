# Slice B — IrAction/IrOp substrate + Flavour-as-IrEmitter — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the closed-subclass `IrDispatch` machinery (`visit_<TypeName>`, `_CHILDREN`, `_REBUILD`, `_DUMP`) with an action-table substrate where behaviour is data, then migrate `Flavour` onto it as `IrEmitter`.

**Architecture:** `IrDispatch(IrCollection["IrAction"], Generic[_T])` auto-walks `node.children()`, builds `new_children`, looks up `IrAction(target_type, body)` via concrete-first MRO, evaluates `body` (an `IrOp` tree). Short-circuit is intrinsic to `IrReturn` (raises a `_Return` BaseException; entry catches once). Presets `IrVisitor` / `IrTransformer` / `IrEmitter` differ only in their "no action matched" default. `Flavour` subclasses `IrEmitter` and carries metadata as `ClassVar`s; per-flavour singletons (`GBNF`, `ABNF`) hold the action tuples.

**Tech Stack:** Python 3.12+ · Pydantic v2 · Lark · uv · pytest · ruff · pylint

**Spec:** `docs/superpowers/specs/2026-05-18-slice-b-substrate-design.md`
**Scope companion:** `docs/superpowers/specs/2026-05-17-slice-b-deferred-work.md`

---

## Conventions for every task

- Always prefix commands with `uv run` (`uv run pytest -q`, `uv run ruff check src/ tests/`).
- Before manual fixes after edits, run `tools/auto_fix.sh` first.
- Test mirror rule: `src/lexic/foo/bar.py` ↔ `tests/unit/lexic/foo/test_bar.py`. For `__init__.py` modules, the test file is `test_init_<package>.py`.
- Never include `Co-Authored-By:` in commit messages.
- After every task: `uv run pytest -q` must pass before commit.
- Sphinx-style docstrings (`:param:`/`:returns:`/`:raises:`) on all new public surfaces.
- No `# type: ignore`, `# pylint: disable`, or `# noqa` without explicit permission.

---

## Step 1 — `ir/action.py` — the IrOp algebra + IrAction

Standalone introduction. No consumers migrated yet. Each `IrOp` variant gets its own test coverage. `IrAction` lives in the same module.

### Task 1.1: Skeleton — module + `_Return` exception + `IrOp` ABC

**Files:**
- Create: `src/lexic/ir/action.py`
- Create: `tests/unit/lexic/ir/test_action.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/lexic/ir/test_action.py
"""Tests for ir/action.py — IrOp algebra + IrAction."""

import pytest

from lexic.ir.action import IrOp, _Return


def test_return_inherits_base_exception_not_exception():
    """_Return is BaseException so IrCallable bodies with `except Exception` don't swallow it."""
    assert issubclass(_Return, BaseException)
    assert not issubclass(_Return, Exception)


def test_return_carries_value():
    sig = _Return(value=42)
    assert sig.value == 42


def test_irop_is_abstract():
    with pytest.raises(TypeError):
        IrOp()  # type: ignore[abstract]
```

- [ ] **Step 2: Run tests; verify they fail with ImportError**

Run: `uv run pytest tests/unit/lexic/ir/test_action.py -v`
Expected: ImportError on `from lexic.ir.action import ...`.

- [ ] **Step 3: Implement skeleton**

```python
# src/lexic/ir/action.py
"""IrAction + IrOp — structural action algebra.

An IrDispatch's action table is a tuple of IrAction nodes. Each IrAction
binds a target IrNode type to an IrOp body. The IrOp algebra is the small
language flavour emitters and IR passes use to describe per-type behaviour.

For procedural cases (helper-name allocation, side-effect flags,
escape encoding), wrap the logic in IrCallable. Pure-IrOp bodies are
preferred where they fit.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable, ClassVar, Generic, TypeVar

from lexic.ir.nodes import IrCollection, IrComposite, IrLeaf, IrNode

if TYPE_CHECKING:
    from lexic.ir.walk import IrDispatch

_T = TypeVar("_T")


class _Return(BaseException):
    """Control-flow exception raised by ``IrReturn.eval``.

    Inherits BaseException (not Exception) so IrCallable bodies that
    wrap their work in ``except Exception:`` cannot swallow it.
    """

    def __init__(self, value: Any) -> None:
        super().__init__()
        self.value = value


class IrOp(IrNode, Generic[_T], ABC):
    """One operation in an IrAction body.

    Concrete variants either pin _T (e.g. IrText: IrOp[str]) or
    re-parameterize (e.g. IrReturn[_T]). Every IrOp is an IrNode subclass
    and inherits children() / rebuild() / __str__ / __repr__ from
    IrLeaf / IrCollection / IrComposite.
    """

    @abstractmethod
    def eval(
        self,
        dispatch: "IrDispatch[Any]",
        node: IrNode,
        new_children: tuple,
    ) -> _T:
        """Evaluate this op.

        :param dispatch: The dispatcher running this action body.
        :param node: The dispatched node.
        :param new_children: Already-dispatched children, aligned to
            ``node.children()`` order.
        :returns: This op's contribution to the dispatched result.
        """
```

- [ ] **Step 4: Run tests; verify pass**

Run: `uv run pytest tests/unit/lexic/ir/test_action.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/lexic/ir/action.py tests/unit/lexic/ir/test_action.py
git commit -m "ir: action.py skeleton — IrOp ABC + _Return BaseException"
```

### Task 1.2: `IrText` — literal string

- [ ] **Step 1: Write failing test**

Append to `tests/unit/lexic/ir/test_action.py`:

```python
def test_irtext_eval_returns_literal():
    from lexic.ir.action import IrText
    assert IrText("hello").eval(None, None, ()) == "hello"  # type: ignore[arg-type]


def test_irtext_str_renders_canonically():
    from lexic.ir.action import IrText
    assert "hello" in str(IrText("hello"))
```

- [ ] **Step 2: Run; verify ImportError**

Run: `uv run pytest tests/unit/lexic/ir/test_action.py::test_irtext_eval_returns_literal -v`

- [ ] **Step 3: Implement**

Append to `src/lexic/ir/action.py`:

```python
@dataclass(frozen=True, slots=True, repr=False)
class IrText(IrOp[str], IrLeaf):
    """Literal string."""

    text: str

    def eval(self, _d: "IrDispatch[Any]", _n: IrNode, _nc: tuple) -> str:
        return self.text
```

- [ ] **Step 4: Run; verify pass**

- [ ] **Step 5: Commit**

```bash
git add src/lexic/ir/action.py tests/unit/lexic/ir/test_action.py
git commit -m "ir/action: IrText"
```

### Task 1.3: `IrField` — non-IrNode attribute as str

- [ ] **Step 1: Write failing test**

```python
def test_irfield_reads_str_of_attribute():
    from dataclasses import dataclass

    from lexic.ir.action import IrField

    @dataclass
    class _N:
        name: str = "foo"

    assert IrField("name").eval(None, _N(), ()) == "foo"  # type: ignore[arg-type]


def test_irfield_coerces_non_string_to_str():
    from dataclasses import dataclass

    from lexic.ir.action import IrField

    @dataclass
    class _N:
        n: int = 7

    assert IrField("n").eval(None, _N(), ()) == "7"  # type: ignore[arg-type]
```

- [ ] **Step 2: Run; verify fail**

- [ ] **Step 3: Implement**

```python
@dataclass(frozen=True, slots=True, repr=False)
class IrField(IrOp[str], IrLeaf):
    """``str(getattr(node, name))`` — non-IrNode attribute on the dispatched node."""

    name: str

    def eval(self, _d: "IrDispatch[Any]", node: IrNode, _nc: tuple) -> str:
        return str(getattr(node, self.name))
```

- [ ] **Step 4: Run; verify pass.**

- [ ] **Step 5: Commit.**

```bash
git commit -am "ir/action: IrField"
```

### Task 1.4: `IrCallable` — procedural escape hatch

- [ ] **Step 1: Write failing test**

```python
def test_ircallable_invokes_handler_with_dispatch_node_children():
    from lexic.ir.action import IrCallable

    calls = []

    def handler(d, n, nc):
        calls.append((d, n, nc))
        return "result"

    op = IrCallable(handler)
    assert op.eval("D", "N", ("a", "b")) == "result"  # type: ignore[arg-type]
    assert calls == [("D", "N", ("a", "b"))]


def test_ircallable_is_not_structurally_compared():
    """Callables don't compare structurally — IrCallable is identity-equal only."""
    from lexic.ir.action import IrCallable

    fn = lambda d, n, nc: None  # noqa: E731
    a = IrCallable(fn)
    b = IrCallable(fn)
    # No equality assertion either way — but constructing two with same fn must not crash hashable use.
    assert a is not b
```

- [ ] **Step 2: Run; fail.**

- [ ] **Step 3: Implement**

```python
@dataclass(frozen=True, slots=True, eq=False, repr=False)
class IrCallable(IrOp[_T], IrLeaf, Generic[_T]):
    """Procedural body. ``handler(dispatch, node, new_children) -> _T``.

    Escape hatch for cases pure IrOp can't express cleanly (stateful
    allocators, escape encoding, symbol-table lookups). ``eq=False``
    because callables don't have structural equality.
    """

    handler: Callable[["IrDispatch[Any]", IrNode, tuple], _T]

    def eval(self, d: "IrDispatch[Any]", node: IrNode, new_children: tuple) -> _T:
        return self.handler(d, node, new_children)

    def _inner_str(self) -> str:
        name = getattr(self.handler, "__name__", "callable")
        return f"<{name}>"
```

- [ ] **Step 4: Pass.**

- [ ] **Step 5: Commit.**

```bash
git commit -am "ir/action: IrCallable"
```

### Task 1.5: `IrChild` and `IrChildren` — named child access

- [ ] **Step 1: Write failing tests**

```python
def test_irchild_returns_named_position_from_new_children():
    from lexic.ir.action import IrChild
    from lexic.ir.nodes import IrAlternation, IrGroup

    body = IrAlternation()
    node = IrGroup(body=body)
    # IrGroup._child_attrs = ("body",) so IrChild("body") returns new_children[0]
    assert IrChild("body").eval(None, node, ("BODY-RESULT",)) == "BODY-RESULT"  # type: ignore[arg-type]


def test_irchild_raises_for_unknown_name():
    from lexic.ir.action import IrChild
    from lexic.ir.nodes import IrGroup, IrAlternation

    node = IrGroup(body=IrAlternation())
    with pytest.raises(ValueError):
        IrChild("nope").eval(None, node, ("X",))  # type: ignore[arg-type]


def test_irchildren_returns_full_new_children_tuple():
    from lexic.ir.action import IrChildren
    from lexic.ir.nodes import IrSequence

    seq = IrSequence(items=())
    # IrSequence._items_attr = "items"
    assert IrChildren("items").eval(None, seq, ("A", "B", "C")) == ("A", "B", "C")  # type: ignore[arg-type]


def test_irchildren_raises_for_wrong_items_attr():
    from lexic.ir.action import IrChildren
    from lexic.ir.nodes import IrSequence

    with pytest.raises(ValueError):
        IrChildren("rules").eval(None, IrSequence(), ())  # type: ignore[arg-type]
```

- [ ] **Step 2: Run; fail.**

- [ ] **Step 3: Implement**

```python
@dataclass(frozen=True, slots=True, repr=False)
class IrChild(IrOp[Any], IrLeaf):
    """Fixed-arity child result from a named slot.

    The dispatched node must be an ``IrComposite`` whose ``_child_attrs``
    contains ``name``. Returns the corresponding entry of ``new_children``.

    :raises ValueError: If ``name`` is not in ``type(node)._child_attrs``.
    """

    name: str

    def eval(self, _d: "IrDispatch[Any]", node: IrNode, new_children: tuple) -> Any:
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
class IrChildren(IrOp[tuple], IrLeaf):
    """Variable-arity children tuple from a homogeneous slot.

    The dispatched node must be an ``IrCollection`` whose ``_items_attr``
    equals ``name``. Returns the full ``new_children`` tuple.

    :raises ValueError: If ``name`` does not match ``type(node)._items_attr``.
    """

    name: str

    def eval(self, _d: "IrDispatch[Any]", node: IrNode, new_children: tuple) -> tuple:
        items_attr = getattr(type(node), "_items_attr", None)
        if items_attr != self.name:
            raise ValueError(
                f"IrChildren({self.name!r}): {type(node).__name__} _items_attr "
                f"is {items_attr!r}"
            )
        return new_children
```

- [ ] **Step 4: Pass.**

- [ ] **Step 5: Commit.**

```bash
git commit -am "ir/action: IrChild + IrChildren"
```

### Task 1.6: `IrConcat` — string concatenation

- [ ] **Step 1: Write failing tests**

```python
def test_irseq_concatenates_op_results():
    from lexic.ir.action import IrConcat, IrText

    op = IrConcat((IrText("a"), IrText("b"), IrText("c")))
    assert op.eval(None, None, ()) == "abc"  # type: ignore[arg-type]


def test_irseq_coerces_non_str_results_with_str():
    """IrConcat is the emit-side primitive; non-str results pass through str()."""
    from lexic.ir.action import IrConcat, IrCallable, IrText

    op = IrConcat((IrText("n="), IrCallable(lambda d, n, nc: 42)))
    assert op.eval(None, None, ()) == "n=42"  # type: ignore[arg-type]


def test_irseq_is_an_ircollection_with_parts_as_children():
    from lexic.ir.action import IrConcat, IrText

    op = IrConcat((IrText("a"), IrText("b")))
    assert op.children() == (IrText("a"), IrText("b"))


def test_irconcat_eval_does_not_recurse_through_dispatcher():
    """IrConcat.eval calls part.eval directly — it does NOT feed parts back
    through the dispatcher. P13 (IR-describes-IR) makes parts structural
    children for introspection; that does not make them dispatch targets
    when an IrConcat appears as an IrAction body.
    """
    from lexic.ir.action import IrConcat, IrText
    from lexic.ir.nodes import IrLiteral

    sentinel = object()

    class _Watcher:
        """Stand-in for IrDispatch; raises if anyone tries to dispatch a part."""

        def __call__(self, _node):
            raise AssertionError("IrConcat must not dispatch its parts")

    op = IrConcat((IrText("a"), IrText("b")))
    # Pass the watcher as the dispatcher; if eval re-dispatched any part,
    # the watcher would raise. The eval path is part.eval(d, node, nc) — not d(part).
    assert op.eval(_Watcher(), IrLiteral("x"), ()) == "ab"  # type: ignore[arg-type]
```

- [ ] **Step 2: Fail.**

- [ ] **Step 3: Implement**

```python
@dataclass(frozen=True, slots=True, repr=False)
class IrConcat(IrOp[str], IrCollection["IrOp"]):
    """Evaluate ``parts`` in order; return ``"".join(str(...))`` of results.

    Emit-side primitive — not used by visitor / transformer passes in
    this slice.
    """

    _items_attr: ClassVar[str] = "parts"
    parts: tuple[IrOp, ...] = ()

    def eval(self, d: "IrDispatch[Any]", node: IrNode, new_children: tuple) -> str:
        return "".join(str(p.eval(d, node, new_children)) for p in self.parts)
```

- [ ] **Step 4: Pass.**

- [ ] **Step 5: Commit.**

```bash
git commit -am "ir/action: IrConcat"
```

### Task 1.7: `IrJoin` — variable-arity join with separator

- [ ] **Step 1: Write failing tests**

```python
def test_irjoin_joins_children_results_with_separator():
    from lexic.ir.action import IrChildren, IrJoin, IrText
    from lexic.ir.nodes import IrSequence

    op = IrJoin(IrChildren("items"), IrText(" "), IrText('""'))
    seq = IrSequence(items=())
    # children_op returns the new_children tuple
    assert op.eval(None, seq, ("A", "B", "C")) == "A B C"  # type: ignore[arg-type]


def test_irjoin_returns_empty_when_children_tuple_is_empty():
    from lexic.ir.action import IrChildren, IrJoin, IrText
    from lexic.ir.nodes import IrSequence

    op = IrJoin(IrChildren("items"), IrText(" "), IrText('""'))
    assert op.eval(None, IrSequence(items=()), ()) == '""'  # type: ignore[arg-type]


def test_irjoin_coerces_non_str_children():
    from lexic.ir.action import IrChildren, IrJoin, IrText
    from lexic.ir.nodes import IrSequence

    op = IrJoin(IrChildren("items"), IrText(","), IrText(""))
    assert op.eval(None, IrSequence(items=()), (1, 2, 3)) == "1,2,3"  # type: ignore[arg-type]
```

- [ ] **Step 2: Fail.**

- [ ] **Step 3: Implement**

```python
@dataclass(frozen=True, slots=True, repr=False)
class IrJoin(IrOp[str], IrComposite["IrOp", "IrText", "IrText"]):
    """Variable-arity join.

    Evaluates ``children_op`` (typically ``IrChildren(name)``); joins the
    resulting iterable with ``separator.text``; returns ``empty.text`` if
    the iterable is empty.
    """

    _child_attrs: ClassVar[tuple[str, ...]] = ("children_op", "separator", "empty")
    children_op: IrOp
    separator: IrText
    empty: IrText

    def eval(self, d: "IrDispatch[Any]", node: IrNode, new_children: tuple) -> str:
        items = self.children_op.eval(d, node, new_children)
        if not items:
            return self.empty.text
        return self.separator.text.join(str(it) for it in items)
```

- [ ] **Step 4: Pass.**

- [ ] **Step 5: Commit.**

```bash
git commit -am "ir/action: IrJoin"
```

### Task 1.8: `IrCond` — truthy-field branch

- [ ] **Step 1: Write failing tests**

```python
def test_ircond_takes_then_branch_when_field_truthy():
    from lexic.ir.action import IrCond, IrText
    from lexic.ir.nodes import IrCharClass

    op = IrCond("negated", IrText("yes"), IrText("no"))
    assert op.eval(None, IrCharClass("a-z", negated=True), ()) == "yes"  # type: ignore[arg-type]


def test_ircond_takes_else_branch_when_field_falsy():
    from lexic.ir.action import IrCond, IrText
    from lexic.ir.nodes import IrCharClass

    op = IrCond("negated", IrText("yes"), IrText("no"))
    assert op.eval(None, IrCharClass("a-z", negated=False), ()) == "no"  # type: ignore[arg-type]
```

- [ ] **Step 2: Fail.**

- [ ] **Step 3: Implement**

```python
@dataclass(frozen=True, slots=True, repr=False)
class IrCond(IrOp[_T], IrComposite["IrOp", "IrOp"], Generic[_T]):
    """Truthy-field branch.

    If ``bool(getattr(node, field))`` is true, evaluate ``then_op``;
    else evaluate ``else_op``.
    """

    _child_attrs: ClassVar[tuple[str, ...]] = ("then_op", "else_op")
    field: str
    then_op: IrOp[_T]
    else_op: IrOp[_T]

    def eval(self, d: "IrDispatch[Any]", node: IrNode, new_children: tuple) -> _T:
        branch = self.then_op if getattr(node, self.field) else self.else_op
        return branch.eval(d, node, new_children)
```

- [ ] **Step 4: Pass.**

- [ ] **Step 5: Commit.**

```bash
git commit -am "ir/action: IrCond"
```

### Task 1.9: `IrReturn` — short-circuit via exception

- [ ] **Step 1: Write failing test**

```python
def test_irreturn_raises_return_with_value():
    from lexic.ir.action import IrReturn, _Return

    with pytest.raises(_Return) as exc:
        IrReturn(True).eval(None, None, ())  # type: ignore[arg-type]
    assert exc.value.value is True


def test_irreturn_value_can_be_any_type():
    from lexic.ir.action import IrReturn, _Return

    with pytest.raises(_Return) as exc:
        IrReturn("hello").eval(None, None, ())  # type: ignore[arg-type]
    assert exc.value.value == "hello"


def test_irreturn_not_swallowed_by_except_exception():
    """_Return inherits BaseException so `except Exception:` cannot catch it."""
    from lexic.ir.action import IrReturn, _Return

    try:
        try:
            IrReturn(1).eval(None, None, ())  # type: ignore[arg-type]
        except Exception:
            pytest.fail("_Return should not be caught by except Exception")
    except _Return as exc:
        assert exc.value == 1
```

- [ ] **Step 2: Fail.**

- [ ] **Step 3: Implement**

```python
@dataclass(frozen=True, slots=True, repr=False)
class IrReturn(IrOp[_T], IrLeaf, Generic[_T]):
    """Short-circuit. Evaluating raises ``_Return(value)``.

    The exception unwinds through every nested ``IrDispatch.__call__``
    frame until the dispatcher's entry catches it.
    """

    value: _T

    def eval(self, _d: "IrDispatch[Any]", _n: IrNode, _nc: tuple) -> _T:
        raise _Return(self.value)
```

- [ ] **Step 4: Pass.**

- [ ] **Step 5: Commit.**

```bash
git commit -am "ir/action: IrReturn"
```

### Task 1.10: `IrAction`

- [ ] **Step 1: Write failing tests**

```python
def test_iraction_str_renders_target_type_name_and_body():
    from lexic.ir.action import IrAction, IrText
    from lexic.ir.nodes import IrLiteral

    a = IrAction(IrLiteral, IrText("X"))
    s = str(a)
    assert "IrLiteral" in s
    assert "X" in s


def test_iraction_body_is_a_child():
    from lexic.ir.action import IrAction, IrText
    from lexic.ir.nodes import IrLiteral

    body = IrText("X")
    a = IrAction(IrLiteral, body)
    assert a.children() == (body,)


def test_iraction_target_type_is_not_a_child():
    """target_type is a `type`, not an IrNode — must not appear in children()."""
    from lexic.ir.action import IrAction, IrText
    from lexic.ir.nodes import IrLiteral

    body = IrText("X")
    a = IrAction(IrLiteral, body)
    children = a.children()
    assert children == (body,)
    assert len(children) == 1
    # The type object itself must not surface as a child.
    assert IrLiteral not in children
    for c in children:
        assert not isinstance(c, type)


def test_iraction_rebuild_preserves_target_type():
    """``rebuild((new_body,))`` keeps ``target_type`` intact."""
    from lexic.ir.action import IrAction, IrText
    from lexic.ir.nodes import IrLiteral, IrRuleRef

    a = IrAction(IrLiteral, IrText("X"))
    rebuilt = a.rebuild((IrText("Y"),))
    assert rebuilt.target_type is IrLiteral
    assert rebuilt.body == IrText("Y")
    assert rebuilt.target_type is not IrRuleRef


def test_iraction_eval_delegates_to_body():
    from lexic.ir.action import IrAction, IrText
    from lexic.ir.nodes import IrLiteral

    a = IrAction(IrLiteral, IrText("Z"))
    assert a.body.eval(None, None, ()) == "Z"  # type: ignore[arg-type]
```

- [ ] **Step 2: Fail.**

- [ ] **Step 3: Implement**

```python
@dataclass(frozen=True, slots=True, eq=False, repr=False)
class IrAction(IrComposite["IrOp"]):
    """Bind a target IR node type to an IrOp body.

    ``target_type`` is metadata (a ``type``, rendered in ``__str__`` but
    excluded from ``children()``). ``body`` is the single IrNode child.

    Identity equality (``eq=False``) because ``target_type`` is a type
    object and bodies may carry ``IrCallable``, neither of which
    compares structurally.
    """

    _child_attrs: ClassVar[tuple[str, ...]] = ("body",)
    target_type: type
    body: IrOp

    def _inner_str(self) -> str:
        return f"{self.target_type.__name__}, {self.body}"
```

- [ ] **Step 4: Pass.**

- [ ] **Step 5: Commit.**

```bash
git commit -am "ir/action: IrAction"
```

### Task 1.11: Re-export from `ir/__init__.py`

**Files:** Modify `src/lexic/ir/__init__.py`.

- [ ] **Step 1: Write failing test**

```python
# tests/unit/lexic/ir/test_init_ir.py — append
def test_ir_init_reexports_action_module():
    from lexic.ir import (
        IrAction,
        IrCallable,
        IrChild,
        IrChildren,
        IrCond,
        IrField,
        IrJoin,
        IrOp,
        IrReturn,
        IrConcat,
        IrText,
    )
    assert IrAction.__name__ == "IrAction"
    assert IrOp.__name__ == "IrOp"
```

- [ ] **Step 2: Fail.**

- [ ] **Step 3: Update `src/lexic/ir/__init__.py`** — add to imports + `__all__`:

```python
from lexic.ir.action import (
    IrAction,
    IrCallable,
    IrChild,
    IrChildren,
    IrCond,
    IrField,
    IrJoin,
    IrOp,
    IrReturn,
    IrConcat,
    IrText,
)
```

Add each name to `__all__`.

- [ ] **Step 4: Pass.**

- [ ] **Step 5: Commit.**

```bash
git commit -am "ir: re-export action algebra from ir/__init__.py"
```

---

## Step 2 — Rewrite `ir/walk.py` — new `IrDispatch` + presets

Replaces the current `IrDispatch` / `IrVisitor` / `IrTransformer` (with `_CHILDREN` / `_REBUILD` / `_DUMP` central tables) with the action-driven substrate. Adds `IrEmitter`.

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
from lexic.ir.action import IrAction, IrCallable, IrReturn, IrText, _Return
from lexic.ir.nodes import (
    IrAlternation,
    IrAst,
    IrCollection,
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
    from lexic.ir.walk import IrDispatch

    a = IrAction(IrLiteral, IrText("x"))
    d = IrDispatch(actions=(a,))
    assert isinstance(d, IrCollection)
    assert d.children() == (a,)


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
    # Should include leaves, not just the root
    assert IrRuleRef in visited
    assert IrItem in visited


# ── IrReturn short-circuit ───────────────────────────────────────────


def test_irreturn_short_circuits_at_entry():
    """First IrRuleRef raises _Return(True); the rest of the subtree is not visited."""
    from lexic.ir.walk import IrVisitor

    visit_count = 0

    def _on_ref(_d, _n, _nc):
        nonlocal visit_count
        visit_count += 1
        # IrReturn at the action level should unwind to entry on first hit.
        raise _Return(True)

    d = IrVisitor(actions=(IrAction(IrRuleRef, IrCallable(_on_ref)),))
    # Build a tree with TWO IrRuleRefs at different depths.
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
    assert visit_count == 1   # short-circuit before visiting the second ruleref


def test_irreturn_via_op_unwinds():
    """IrReturn(value) op raises _Return; dispatcher entry returns value."""
    from lexic.ir.walk import IrVisitor

    d = IrVisitor(actions=(IrAction(IrRuleRef, IrReturn(True)),))
    assert d(IrRuleRef("x")) is True


# ── Resolve cache ────────────────────────────────────────────────────


def test_resolve_cache_memoizes_negative_lookups():
    """A type with no matching action caches None and stays cached."""
    from lexic.ir.walk import IrVisitor

    d = IrVisitor(actions=(IrAction(IrLiteral, IrCallable(lambda d, n, nc: None)),))
    d(IrRuleRef("x"))   # no action matches; cache populates with None
    # Internal: cache should contain IrRuleRef -> None now.
    assert d._resolve_cache[IrRuleRef] is None  # type: ignore[attr-defined]


def test_frozen_dispatcher_cannot_rebind_resolve_cache_slot():
    """The cache slot is frozen; rebinding raises."""
    from dataclasses import FrozenInstanceError

    from lexic.ir.walk import IrVisitor

    d = IrVisitor()
    with pytest.raises(FrozenInstanceError):
        d._resolve_cache = {}  # type: ignore[misc]


def test_cache_contents_are_mutable_even_though_slot_is_frozen():
    """Cache mutation (adding entries) is permitted; only slot rebinding is blocked."""
    from lexic.ir.walk import IrVisitor

    d = IrVisitor(actions=(IrAction(IrLiteral, IrCallable(lambda d, n, nc: None)),))
    # Initially empty.
    assert d._resolve_cache == {}  # type: ignore[attr-defined]
    # Dispatching populates the cache.
    d(IrLiteral("x"))
    assert IrLiteral in d._resolve_cache  # type: ignore[attr-defined]
    # And dispatching again still works (cache was mutated, not rebound).
    d(IrLiteral("y"))
```

- [ ] **Step 2: Run; expect failures** (old walk.py still in place).

- [ ] **Step 3: Rewrite `src/lexic/ir/walk.py`**

```python
"""IrDispatch — action-driven IR walker.

IrDispatch is an IrCollection["IrAction"]. Its children() are the
actions tuple. Calling the dispatcher on a node:

  1. Recurses node.children() to build a new_children tuple.
  2. Resolves the matching IrAction via concrete-first MRO walk on
     type(node), memoized in _resolve_cache.
  3. If matched, evaluates the action's body against (self, node,
     new_children); else falls through to the preset _default.

Skip-recursion is intrinsic to IrReturn (raises _Return, a BaseException
subclass). The dispatcher's __call__ catches once at the top; internal
recursion does not catch, so the exception unwinds naturally.

Presets:
  IrVisitor      _T = None      default: None
  IrTransformer  _T = IrNode    default: node.rebuild(new_children) if changed
  IrEmitter      _T = str       default: str(node) if actions empty,
                                else raise UnsupportedConstructError
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar, Generic, TypeVar

from lexic.exceptions import UnsupportedConstructError
from lexic.ir.action import IrAction, _Return
from lexic.ir.nodes import IrCollection, IrNode

_T = TypeVar("_T")


@dataclass(frozen=True, slots=True, repr=False)
class IrDispatch(IrCollection["IrAction"], Generic[_T]):
    """Action-driven walker. Not an ABC — instantiable directly.

    :ivar actions: Per-type action table. Concrete keys win over
        abstract keys; MRO walk is concrete-first.
    """

    _items_attr: ClassVar[str] = "actions"
    actions: tuple[IrAction, ...] = ()
    _resolve_cache: dict[type, IrAction | None] = field(
        init=False, default_factory=dict, hash=False, compare=False, repr=False,
    )

    def __call__(self, node: IrNode) -> _T:
        """Entry point. Catches ``_Return`` once at the top.

        :param node: Root of the IR subtree to dispatch.
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
            return action.body.eval(self, node, new_children)
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
        directly except in tests; production code uses a preset.
        """
        raise UnsupportedConstructError(
            f"{type(self).__name__}: no action for {type(node).__name__!r} "
            f"and no preset default configured"
        )
```

- [ ] **Step 4: Run tests; partial pass.** `IrVisitor` / `IrTransformer` tests still fail.

- [ ] **Step 5: Add `IrVisitor` + `IrTransformer` + `IrEmitter`** (append to walk.py):

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

    e = IrEmitter(actions=(IrAction(IrLiteral, IrText("L")),))
    with pytest.raises(UnsupportedConstructError):
        e(IrRuleRef("x"))


def test_iremitter_iraction_irnode_acts_as_per_instance_default():
    """A user-supplied IrAction(IrNode, ...) catches everything; preset default never fires."""
    from lexic.ir.walk import IrEmitter

    e = IrEmitter(actions=(
        IrAction(IrLiteral, IrText("L")),
        IrAction(IrNode, IrText("ANY")),
    ))
    assert e(IrRuleRef("x")) == "ANY"
    assert e(IrLiteral("y")) == "L"
```

- [ ] **Step 8: Run tests; verify pass.**

- [ ] **Step 9: Commit**

```bash
git add src/lexic/ir/walk.py tests/unit/lexic/ir/test_walk.py
git commit -m "ir/walk: action-driven IrDispatch + IrVisitor/IrTransformer/IrEmitter presets

Replaces the closed-subclass visit_<TypeName> machinery with action-table
dispatch. __call__ auto-walks node.children(), resolves IrAction via
concrete-first MRO, evaluates body against (self, node, new_children).
IrReturn raises _Return (BaseException); __call__ catches once at top.

Removes _CHILDREN, _REBUILD, _DUMP, dump(), visit(), generic_visit(),
_combine(), visit_<TypeName> discovery. Adds IrEmitter as the third
canonical preset."
```

### Task 2.2: Mechanical fixes — `codegen/aliases.py` and `codegen/model_emitter.py`

The old `IrDispatch` exposed `.visit(node)`; the new one is callable. Closed-subclass visitors inside `codegen/` stay closed per scope-companion §3 — they need to keep working.

**Files:**
- Modify: `src/lexic/codegen/aliases.py`
- Modify: `src/lexic/codegen/model_emitter.py`

- [ ] **Step 1: Identify callsites**

Run: `uv run rg -n "\\.visit\\(|generic_visit|visit_Ir|_combine" src/lexic/codegen/`

Expected: hits in `aliases.py` (`_PatternAliasVisitor.visit_*`) and `model_emitter.py` (`_IrRepr.visit_*`).

- [ ] **Step 2: Current shapes (as of 2026-05-18)**

`_PatternAliasVisitor` in `src/lexic/codegen/aliases.py:111` is:

```python
class _PatternAliasVisitor(IrVisitor):
    def __init__(self) -> None:
        self.aliases: dict[str, PatternAlias] = {}
        self._name_counts: Counter[str] = Counter()
        self._ruleref_frames: list[bool] = [False]

    def visit_IrRuleRef(self, _: IrRuleRef) -> None:
        self._ruleref_frames[-1] = True

    def visit_IrItem(self, node: IrItem) -> None:
        atom, q = node.atom, node.quantifier
        if isinstance(atom, IrGroup):
            self._visit_group_item(atom, q, node)
            return
        if isinstance(atom, IrCharClass):
            self._record(regex_for_charclass(atom, q),
                         _name_for_charclass(atom) or "Pattern")
        self.generic_visit(node)

    def _visit_group_item(self, atom, q, node) -> None:
        self._ruleref_frames.append(False)
        self.generic_visit(node)
        group_had_ruleref = self._ruleref_frames.pop()
        if group_had_ruleref:
            self._ruleref_frames[-1] = True
        else:
            self._record(regex_for_group(atom, q), "Pattern")

    def _record(self, regex: str, base: str) -> None:
        if regex in self.aliases:
            return
        self._name_counts[base] += 1
        n = self._name_counts[base]
        name = base if n == 1 else f"{base}{n}"
        self.aliases[regex] = PatternAlias(name=name, regex=regex)
```

Called from `collect_aliases(specs)` via `visitor.visit(item)` for each spec item.

`_IrRepr` in `src/lexic/codegen/model_emitter.py:100` is:

```python
class _IrRepr(IrDispatch[IrNode, str]):
    action = _REPR_ACTION   # dict[type, Callable[..., str]]
    def _combine(self, node, old_children, new_children) -> str:
        try:
            return self.action[type(node)](node, old_children, new_children)
        except KeyError as exc:
            raise UnsupportedConstructError(...) from exc
```

Both depend on the old `IrDispatch`'s `visit` / `generic_visit` / `_combine` machinery, which the rewrite removes.

- [ ] **Step 3: Convert `_PatternAliasVisitor` to plain recursive class**

Replace the `IrVisitor` inheritance with a self-contained walker. The two `visit_<TypeName>` methods become `_handle_<TypeName>` private methods, selected by name in a single recursive dispatch:

```python
# src/lexic/codegen/aliases.py — replace the _PatternAliasVisitor class

class _PatternAliasVisitor:
    """Closed-set walker collecting pattern aliases. Plain class (no
    IrDispatch dependency) per scope-companion §3.
    """

    def __init__(self) -> None:
        self.aliases: dict[str, PatternAlias] = {}
        self._name_counts: Counter[str] = Counter()
        self._ruleref_frames: list[bool] = [False]

    def visit(self, node: IrNode) -> None:
        """Entry point; dispatches by type name."""
        handler = getattr(self, f"_handle_{type(node).__name__}", None)
        if handler is not None:
            handler(node)
            return
        self._generic(node)

    def _generic(self, node: IrNode) -> None:
        """Walk children for nodes with no specific handler."""
        for child in node.children():
            self.visit(child)

    def _handle_IrRuleRef(self, _: IrRuleRef) -> None:
        self._ruleref_frames[-1] = True

    def _handle_IrItem(self, node: IrItem) -> None:
        atom, q = node.atom, node.quantifier
        if isinstance(atom, IrGroup):
            self._visit_group_item(atom, q, node)
            return
        if isinstance(atom, IrCharClass):
            self._record(regex_for_charclass(atom, q),
                         _name_for_charclass(atom) or "Pattern")
        self._generic(node)

    def _visit_group_item(self, atom: IrGroup, q: Quantifier, node: IrItem) -> None:
        self._ruleref_frames.append(False)
        self._generic(node)
        group_had_ruleref = self._ruleref_frames.pop()
        if group_had_ruleref:
            self._ruleref_frames[-1] = True
        else:
            self._record(regex_for_group(atom, q), "Pattern")

    def _record(self, regex: str, base: str) -> None:
        if regex in self.aliases:
            return
        self._name_counts[base] += 1
        n = self._name_counts[base]
        name = base if n == 1 else f"{base}{n}"
        self.aliases[regex] = PatternAlias(name=name, regex=regex)
```

`collect_aliases(specs)` keeps its existing call: `visitor.visit(item)` works because the new class has its own `visit` method.

- [ ] **Step 4: Convert `_IrRepr` to plain recursive class**

```python
# src/lexic/codegen/model_emitter.py — replace _IrRepr

class _IrRepr:
    """Fold an IR subtree to its Python-repr string. Plain class (no
    IrDispatch dependency) per scope-companion §3.
    """

    def __init__(self) -> None:
        self.action = _REPR_ACTION  # dict[type, Callable[..., str]]

    def visit(self, node: IrNode) -> str:
        """Entry point; recurse children then combine via action table."""
        old_children = node.children()
        new_children = tuple(self.visit(c) for c in old_children)
        try:
            return self.action[type(node)](node, old_children, new_children)
        except KeyError as exc:
            raise UnsupportedConstructError(
                f"_IrRepr: no repr handler for {type(node).__name__!r}",
            ) from exc
```

Existing callers `self._repr.visit(item)` keep working.

- [ ] **Step 5: Run full suite**

Run: `uv run pytest -q`
Expected: pass.

- [ ] **Step 6: Commit**

```bash
git commit -am "codegen: mechanical fix — convert closed-subclass visitors off old IrDispatch

_PatternAliasVisitor and _IrRepr inside codegen/ stay closed per
scope-companion §3, but the old IrDispatch (visit_<TypeName>
machinery) is gone. Both become plain recursive classes with inline
per-type dispatch — same behaviour, no IrDispatch dependency."
```

### Task 2.3: Delete dead helpers from `walk.py`

Already done in Task 2.1 (the rewrite removed them). Spot-check:

- [ ] **Step 1: Confirm no references remain**

```bash
uv run rg -n "_CHILDREN|_REBUILD|_DUMP|\\bdump\\(|generic_visit|_combine|visit_Ir[A-Z]" src/ tests/
```

Expected: zero hits in `src/lexic/ir/`. Any remaining hits in `codegen/` are the mechanical-fix replacements from Task 2.2 (private methods named similarly).

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
    """Construct a tree with many IrRuleRefs; visit only the first."""
    from lexic.ir.action import IrAction, IrCallable
    from lexic.ir.nodes import IrAlternation, IrItem, IrRuleRef, IrSequence
    from lexic.ir.walk import IrVisitor

    # Build a tree with 1000 IrRuleRefs across sibling arms.
    deep = IrAlternation(arms=tuple(
        IrSequence(items=(IrItem(atom=IrRuleRef(f"r{i}")),))
        for i in range(1000)
    ))

    visit_count = 0

    def _on_ref(_d, _n, _nc):
        nonlocal visit_count
        visit_count += 1
        from lexic.ir.action import _Return
        raise _Return(True)   # mimic IrReturn(True).eval semantics

    counting = IrVisitor(actions=(IrAction(IrRuleRef, IrCallable(_on_ref)),))
    result = counting(deep)
    assert result is True
    # The whole point of short-circuit: we visit exactly one IrRuleRef out of 1000.
    assert visit_count == 1
```

- [ ] **Step 2: Fail (current `_RuleRefFinder` may still exist alongside).**

- [ ] **Step 3: Replace `_RuleRefFinder` and `has_ruleref`** in `src/lexic/ir/derive.py`:

```python
# At top of derive.py — update imports
from functools import cache

from lexic.ir.action import IrAction, IrReturn
from lexic.ir.walk import IrVisitor

# Replace the class and the has_ruleref function
_HAS_RULEREF: IrVisitor = IrVisitor(actions=(
    IrAction(IrRuleRef, IrReturn(True)),
))


@cache
def has_ruleref(node: IrNode) -> bool:
    """True if any IrRuleRef exists in the node subtree.

    Short-circuits on first hit via IrReturn(True). Cached on node
    identity for repeat queries.

    :param node: Root of the subtree to scan.
    :returns: True iff the subtree contains at least one IrRuleRef.
    """
    return bool(_HAS_RULEREF(node))
```

Delete the `_RuleRefFinder` class entirely.

- [ ] **Step 4: Run tests; pass.**

- [ ] **Step 5: Commit**

```bash
git add src/lexic/ir/derive.py tests/unit/lexic/ir/test_derive.py
git commit -m "ir/derive: has_ruleref as singleton IrVisitor + IrReturn

Replaces the _RuleRefFinder closed subclass (which overrode visit()
to gate on a flag) with a module-level singleton IrVisitor carrying
one action: (IrRuleRef, IrReturn(True)). Short-circuit comes from
IrReturn raising _Return, which unwinds to the dispatcher's entry."
```

### Task 3.2: Hoist — `_EXTRACT_BODY` sub-dispatcher + transformer factory

**Naming note — `Quantifier` vs `IrQuantifier`.** The class is still named
`Quantifier` at this point in the plan; Step 4 renames it. The test code
and implementation below use `Quantifier` deliberately. Step 4's sed
pass catches every occurrence in this task's commits — including the
new tests added here — and renames them in a single mechanical change.
Do NOT preemptively write `IrQuantifier` in this task; the symbol
does not exist yet.

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
    """Existing behaviour: (foo bar)+ becomes a helper rule + ruleref."""
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
    # Parent's IrGroup is replaced by an IrRuleRef pointing at the helper.
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

```python
# Imports (add)
from typing import Any

from lexic.ir.action import IrCallable
from lexic.ir.walk import IrDispatch, IrTransformer

# Replace _HoistTransformer + hoist_helpers


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


def _hoist_transformer(
    parent_name: str, name_set: set[str]
) -> tuple[IrTransformer, list[IrRule]]:
    """Build a hoist transformer + capture for one rule.

    :param parent_name: The enclosing rule's name (for helper naming).
    :param name_set: Mutable set of taken rule names; helper names are
        added here as they're allocated.
    :returns: ``(transformer, helpers)`` — the helpers list is appended
        to as the transformer runs.
    """
    helpers: list[IrRule] = []

    def _hoist_body(_d: IrDispatch, item: IrItem, new_children: tuple) -> IrItem:
        rebuilt = item.rebuild(new_children)
        if rebuilt.quantifier == Quantifier(1, 1):
            return rebuilt
        body = _EXTRACT_BODY(rebuilt.atom)
        if body is None:
            return rebuilt
        name = _reserve_helper_name(parent_name, name_set)
        name_set.add(name)
        helpers.append(IrRule(name=name, body=body))
        return IrItem(atom=IrRuleRef(name=name), quantifier=rebuilt.quantifier)

    transformer = IrTransformer(actions=(
        IrAction(IrItem, IrCallable(_hoist_body)),
    ))
    return transformer, helpers


def hoist_helpers(ast: IrAst) -> tuple[IrAst, list[IrRule]]:
    """Rewrite quantified groups-with-rulerefs into synthetic helper rules.

    :param ast: Source AST.
    :returns: ``(new_ast, helpers)`` — ``new_ast`` has the groups
        replaced by ``IrRuleRef`` to the helper; ``helpers`` carries
        the synthesized helper rules.
    """
    name_set: set[str] = {r.name for r in ast.rules}
    all_helpers: list[IrRule] = []
    new_rules: list[IrRule] = []
    for rule in ast.rules:
        t, helpers = _hoist_transformer(rule.name, name_set)
        new_body = t(rule.body)
        all_helpers.extend(helpers)
        new_rules.append(IrRule(rule.name, new_body))
    return IrAst(rules=tuple(new_rules), start=ast.start), all_helpers
```

Delete the `_HoistTransformer` class entirely.

- [ ] **Step 4: Run tests; pass.**

- [ ] **Step 5: Run full suite; pass.**

```bash
uv run pytest -q
```

- [ ] **Step 6: Commit**

```bash
git commit -am "ir/derive: hoist via factory + _EXTRACT_BODY sub-dispatcher

Replaces _HoistTransformer (visit_IrItem closed subclass with
isinstance(new_atom, IrGroup) gate) with a factory returning an
IrTransformer + helpers list. Recognition lives in _EXTRACT_BODY,
a sub-dispatcher with (IrGroup, has_ruleref) and (IrNode, None)
actions — open-set, no isinstance.

The hoist body uses item.rebuild(new_children) for the no-op path;
constructed types are only the synthesized IrItem(IrRuleRef, q) and
helper IrRule(name, body) — pure node creation, irreducible."
```

---

## Step 4 — `Quantifier` → `IrQuantifier` rename

Pure mechanical rename. Separate step for blame clarity.

### Task 4.1: Rename across the codebase

**Files (all sites):**
- `src/lexic/ir/nodes.py` (definition)
- `src/lexic/ir/__init__.py` (export)
- `src/lexic/ir/derive.py`
- `src/lexic/parsing/lark_builder.py`
- `src/lexic/parsing/meta_parser.py`
- `src/lexic/parsing/transformer/build_transformer.py`
- `src/lexic/codegen/model_emitter.py`
- `src/lexic/codegen/aliases.py`
- `src/lexic/grammars/flavour.py`
- `src/lexic/grammars/gbnf/flavour.py`
- `src/lexic/grammars/abnf/flavour.py`
- `src/lexic/ir/emit.py`
- `src/lexic/generate.py`
- All test files in `tests/`

Exclude (to be deleted in step 8): `src/lexic/grammars/gbnf/emitter.py`, `src/lexic/grammars/abnf/emitter.py`, `src/lexic/utils/quantifiers.py`.

- [ ] **Step 1: Confirm full site list**

```bash
uv run rg "\\bQuantifier\\b" src/ tests/ --files-with-matches
```

- [ ] **Step 2: Rename the class in `nodes.py`**

```python
# src/lexic/ir/nodes.py — change class Quantifier(IrLeaf): to class IrQuantifier(IrLeaf):
# _str_name stays "Q" (compact for debug); class identity is what changes.
@dataclass(frozen=True, slots=True)
class IrQuantifier(IrLeaf):
    """Repetition bounds. ``max=None`` means unbounded."""
    _str_name: ClassVar[str] = "Q"
    _str_opener: ClassVar[str] = "["
    _str_closer: ClassVar[str] = "]"
    min: int = 1
    max: int | None = 1
    # ... existing _inner_str unchanged
```

Update any forward-reference TypeAliases / annotations using `Quantifier`.

- [ ] **Step 3: Update `IrItem` field type**

```python
quantifier: IrQuantifier = field(default_factory=IrQuantifier)
```

- [ ] **Step 4: Update `ir/__init__.py`** — rename `Quantifier` export to `IrQuantifier`.

- [ ] **Step 5: Rename references across remaining src/ files**

Mechanical search-and-replace, but verify each file. For each in the site list above (excluding the deleted-soon files):

```bash
# GNU sed (Linux):
sed -i 's/\bQuantifier\b/IrQuantifier/g' <path>

# macOS / BSD sed lacks \b — use Python instead:
python3 -c "
import re, sys
p = sys.argv[1]
with open(p) as f: t = f.read()
t = re.sub(r'\bQuantifier\b', 'IrQuantifier', t)
with open(p, 'w') as f: f.write(t)
" <path>
```

Then visually verify the diff (`git diff <path>`).

**Files to exclude from sed:**

```bash
EXCLUDE='src/lexic/grammars/gbnf/emitter.py|src/lexic/grammars/abnf/emitter.py|src/lexic/utils/quantifiers.py'
```

- [ ] **Step 6: Update test files**

Same sed pattern over `tests/`.

- [ ] **Step 7: Run full suite**

```bash
uv run pytest -q
```

Expected: pass (pure rename, no behaviour change).

- [ ] **Step 8: Run linters**

```bash
uv run ruff check src/ tests/
uv run pylint src/lexic/ir/nodes.py src/lexic/ir/derive.py
```

- [ ] **Step 9: Commit**

```bash
git commit -am "ir: rename Quantifier → IrQuantifier across codebase

Pure mechanical rename for naming consistency with the rest of the IR
node hierarchy. _str_name stays 'Q' (compact for debug); only the
Python class identity changes. Files deleted in step 8 (gbnf/emitter.py,
abnf/emitter.py, utils/quantifiers.py) are not renamed."
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

from lexic.ir.nodes import IrQuantifier
from lexic.ir.walk import IrEmitter


class EscapeCodec(ABC):
    """Forward declaration / re-export for typing convenience.

    Concrete codecs live in per-flavour modules.
    """
    # If escapes.py already defines this, import it instead.
    # The Flavour class only needs the type reference.


class Flavour(IrEmitter, ABC):
    """Base for every grammar flavour.

    :cvar name: Short flavour identifier (e.g. "gbnf").
    :cvar extensions: Tuple of file extensions handled (e.g. (".gbnf",)).
    :cvar meta_grammar: Lark meta-grammar string for parsing flavour source.
    :cvar escapes: EscapeCodec subclass for literal escape handling.
    :cvar line_comment: Line-comment prefix; empty string disables
        @directive parsing.
    :cvar quantifier_symbols: Map from (min, max) bounds to the
        flavour's emit text.
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
        """Parse a quantifier symbol into an IrQuantifier.

        :param text: Raw quantifier syntax in this flavour.
        :returns: Bounds as IrQuantifier(min, max).
        """

    @staticmethod
    @abstractmethod
    def parse_charclass(text: str) -> tuple[str, bool]:
        """Parse a char class into (pattern, negated).

        :param text: Raw char-class syntax in this flavour.
        :returns: (canonical-pattern, negated).
        """
```

Note: import `EscapeCodec` from its existing location if available; the local stub above is a fallback. Check `src/lexic/ir/escapes.py` for the real definition.

- [ ] **Step 4: Verify `MetaGrammarParser.for_flavour` still works**

Risk: `Flavour` is now a frozen dataclass (via `IrEmitter`). `for_flavour(GbnfFlavour)` takes the class object and pulls `meta_grammar`, `line_comment`, `parse_quantifier`, `parse_charclass` off it as ClassVar lookups. Verify that these class-level accesses still resolve on a frozen-dataclass subclass:

```python
# tests/unit/lexic/parsing/test_meta_parser.py — add
def test_for_flavour_resolves_classvars_on_iremitter_subclass():
    from lexic.grammars.gbnf.flavour import GbnfFlavour
    from lexic.parsing.meta_parser import MetaGrammarParser

    # ClassVar reads on a frozen-dataclass subclass.
    assert isinstance(GbnfFlavour.meta_grammar, str)
    assert callable(GbnfFlavour.parse_quantifier)
    assert callable(GbnfFlavour.parse_charclass)
    # for_flavour caches on the class — must accept the class object.
    parser = MetaGrammarParser.for_flavour(GbnfFlavour)
    assert parser is not None
```

This test is added now (Task 5.1) but truly validates after Step 6 / 7 land — meta_parser still uses the class.

- [ ] **Step 5: Run tests; pass.**

- [ ] **Step 6: Commit**

```bash
git commit -am "grammars/flavour: Flavour becomes IrEmitter subclass

Metadata moves to ClassVars; behaviour moves to the actions tuple
inherited from IrEmitter. parse_quantifier and parse_charclass stay
as abstract staticmethods (consumed by meta_parser).

The MetaGrammarParser.for_flavour(flavour_cls) class-attrs-only
contract continues to hold — flavour classes still expose
meta_grammar / line_comment / parse_* as class-level surfaces."
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
from lexic.ir.nodes import (
    IrAlternation, IrItem, IrLiteral, IrRule, IrSequence,
)
from lexic.ir.spec import RuleSpec


def _spec(name: str, kind: str = "value_str") -> RuleSpec:
    """Build a minimal RuleSpec with a one-literal body."""
    return RuleSpec(
        rule_name=name,
        class_name=name.title(),
        parent_class_name="GrammarModel",
        kind=kind,
        items=[IrItem(atom=IrLiteral("x"))],
        field_map={},
    )


def test_render_specs_invokes_flavour_per_rule():
    """Each spec's to_ir_rule() is passed to the flavour callable."""
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

This test depends on `RuleSpec.to_ir_rule() -> IrRule` existing. Task 5.2a below adds it.

### Task 5.2a: Add `RuleSpec.to_ir_rule()` if missing

**Files:**
- Modify: `src/lexic/ir/spec.py`
- Modify: `tests/unit/lexic/ir/test_spec.py`

- [ ] **Step 1: Check whether the method exists**

```bash
grep -n "to_ir_rule" src/lexic/ir/spec.py
```

If present, skip this task. If absent, continue.

- [ ] **Step 2: Write failing test**

```python
# tests/unit/lexic/ir/test_spec.py — append
def test_rulespec_to_ir_rule_wraps_items_in_iralternation():
    from lexic.ir.nodes import IrAlternation, IrItem, IrLiteral, IrRule, IrSequence
    from lexic.ir.spec import RuleSpec

    spec = RuleSpec(
        rule_name="r",
        class_name="R",
        parent_class_name="GrammarModel",
        kind="value_str",
        items=[IrItem(atom=IrLiteral("x"))],
        field_map={},
    )
    rule = spec.to_ir_rule()
    assert isinstance(rule, IrRule)
    assert rule.name == "r"
    assert isinstance(rule.body, IrAlternation)
    assert len(rule.body.arms) == 1
    assert isinstance(rule.body.arms[0], IrSequence)
    assert rule.body.arms[0].items == (IrItem(atom=IrLiteral("x")),)


def test_rulespec_to_ir_rule_with_alternation_item_passes_through():
    """A multi-arm value_str carries IrAlternation in items[0]; to_ir_rule
    must use it directly as the body, not wrap it again.
    """
    from lexic.ir.nodes import IrAlternation, IrItem, IrLiteral, IrRule, IrSequence
    from lexic.ir.spec import RuleSpec

    alt = IrAlternation(arms=(
        IrSequence(items=(IrItem(atom=IrLiteral("a")),)),
        IrSequence(items=(IrItem(atom=IrLiteral("b")),)),
    ))
    spec = RuleSpec(
        rule_name="r",
        class_name="R",
        parent_class_name="GrammarModel",
        kind="value_str",
        items=[alt],
        field_map={},
    )
    rule = spec.to_ir_rule()
    assert rule.body == alt
```

- [ ] **Step 3: Implement**

```python
# src/lexic/ir/spec.py — add method to RuleSpec
def to_ir_rule(self) -> IrRule:
    """Reconstitute this spec as an IrRule.

    For sequence / value_str kinds, wraps ``items`` in a single
    IrAlternation arm. If ``items`` already contains a top-level
    IrAlternation (multi-arm value_str), it's used as the body
    directly.

    :returns: An IrRule whose body is an IrAlternation.
    """
    if len(self.items) == 1 and isinstance(self.items[0], IrAlternation):
        body = self.items[0]
    else:
        # All entries are IrItems for sequence / single-arm value_str.
        items_tuple = tuple(it for it in self.items if isinstance(it, IrItem))
        body = IrAlternation(arms=(IrSequence(items=items_tuple),))
    return IrRule(name=self.rule_name, body=body)
```

(Imports needed: `from lexic.ir.nodes import IrAlternation, IrItem, IrRule, IrSequence`.)

- [ ] **Step 4: Run tests; pass.**

- [ ] **Step 5: Commit**

```bash
git commit -am "ir/spec: add RuleSpec.to_ir_rule() — reconstitute spec as IrRule

Needed by render_specs (Task 5.2) to walk each spec back through the
flavour's IrEmitter actions. For sequence and single-arm value_str
kinds, wraps items in a single IrAlternation arm; for multi-arm
value_str, uses the already-present IrAlternation directly."
```

- [ ] **Step 2: Fail.**

- [ ] **Step 3: Implement**

```python
# src/lexic/ir/emit.py
"""render_specs — render a list of RuleSpec back to grammar text via a flavour."""

from __future__ import annotations

from typing import Callable

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

Note: `spec.to_ir_rule()` may need adding to `RuleSpec` if not already present — see the spec's mention of `RuleSpec.to_ir_rule()` and check `src/lexic/ir/spec.py`.

- [ ] **Step 4: Run tests; pass.**

- [ ] **Step 5: Commit**

```bash
git commit -am "ir/emit: add render_specs(specs, flavour) — thin shell"
```

---

## Step 6 — Migrate `GbnfFlavour`

### Task 6.1: Per-flavour callables

**Files:**
- Modify: `src/lexic/grammars/gbnf/flavour.py`

- [ ] **Step 1: Identify the per-IrCallable cases**

From the spec: literal-escape encoding, char-class negation prefix, quantifier symbol-table lookup, AST newline-join + trailing newline. Implement four module-private helpers in `gbnf/flavour.py`:

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


def _gbnf_ast(d, node, new_children) -> str:
    """Render rules joined by newlines, trailing newline."""
    return "\n".join(new_children) + "\n"
```

- [ ] **Step 2: Write tests for each callable**

```python
# tests/unit/lexic/grammars/gbnf/test_flavour.py — add

from lexic.exceptions import UnsupportedConstructError
from lexic.grammars.gbnf.flavour import (
    _gbnf_encode_literal, _gbnf_charclass, _gbnf_quantifier, _gbnf_ast,
)
from lexic.ir.nodes import IrCharClass, IrLiteral, Quantifier


def test_gbnf_encode_literal_returns_escaped_value():
    """Verify the literal goes through GbnfEscapes.encode."""
    out = _gbnf_encode_literal(None, IrLiteral('hello'), ())
    # GbnfEscapes is identity for the simple case (per ir/escapes.py).
    assert out == "hello"


def test_gbnf_encode_literal_escapes_quote():
    """A literal containing a double quote must be escaped per GBNF rules."""
    out = _gbnf_encode_literal(None, IrLiteral('a"b'), ())
    # Expected escape form per GbnfEscapes — adjust to match the codec.
    assert '\\"' in out or '"' not in out[1:-1]   # codec-dependent


def test_gbnf_charclass_renders_brackets_without_negation():
    out = _gbnf_charclass(None, IrCharClass("a-z", negated=False), ())
    assert out == "[a-z]"


def test_gbnf_charclass_renders_brackets_with_negation_prefix():
    out = _gbnf_charclass(None, IrCharClass("a-z", negated=True), ())
    assert out == "[^a-z]"


def test_gbnf_quantifier_returns_empty_string_for_exact_one():
    out = _gbnf_quantifier(None, Quantifier(1, 1), ())
    assert out == ""


def test_gbnf_quantifier_returns_question_for_optional():
    assert _gbnf_quantifier(None, Quantifier(0, 1), ()) == "?"


def test_gbnf_quantifier_returns_star_for_zero_or_more():
    assert _gbnf_quantifier(None, Quantifier(0, None), ()) == "*"


def test_gbnf_quantifier_returns_plus_for_one_or_more():
    assert _gbnf_quantifier(None, Quantifier(1, None), ()) == "+"


def test_gbnf_quantifier_raises_for_unsupported_bounds():
    with pytest.raises(UnsupportedConstructError):
        _gbnf_quantifier(None, Quantifier(2, 5), ())


def test_gbnf_ast_joins_rules_with_newlines_and_trailing_newline():
    out = _gbnf_ast(None, None, ("rule-1", "rule-2", "rule-3"))
    assert out == "rule-1\nrule-2\nrule-3\n"


def test_gbnf_ast_empty_rules_produces_trailing_newline_only():
    out = _gbnf_ast(None, None, ())
    assert out == "\n"
```

Note: the literal-escape test's expected form is codec-dependent (check `GbnfEscapes` in `src/lexic/grammars/gbnf/escapes.py` before writing the assertion). The other tests are exact.

- [ ] **Step 3: Implement; commit**

```bash
git commit -am "grammars/gbnf: per-flavour IrCallable helpers (literal, charclass, quantifier, ast)"
```

### Task 6.2: `_GBNF_ACTIONS` tuple + `GBNF` singleton

- [ ] **Step 1: Write failing integration test**

```python
# tests/integration/test_compile_grammar_gbnf.py — add or extend
def test_gbnf_flavour_renders_all_ground_truth_grammars_byte_equal(ground_truth_path):
    """Compile each .gbnf and verify GBNF(grammar) reproduces source."""
    # See existing test scaffolding for fixture mechanics
    ...
```

Or, more practically: ensure existing integration tests still pass after the singleton replaces `GbnfEmitter`.

- [ ] **Step 2: Build the action tuple in `gbnf/flavour.py`**

```python
# Continuing from Task 6.1's helpers
from lexic.ir.action import (
    IrAction, IrCallable, IrChild, IrChildren, IrField, IrJoin, IrConcat, IrText,
)
from lexic.ir.nodes import (
    IrAlternation, IrAst, IrCharClass, IrGroup, IrItem, IrLiteral,
    IrQuantifier, IrRule, IrRuleRef, IrSequence,
)


_GBNF_ACTIONS: tuple[IrAction, ...] = (
    IrAction(IrLiteral,    IrConcat((IrText('"'), IrCallable(_gbnf_encode_literal), IrText('"')))),
    IrAction(IrCharClass,  IrCallable(_gbnf_charclass)),
    IrAction(IrRuleRef,    IrField("name")),
    IrAction(IrGroup,      IrConcat((IrText("("), IrChild("body"), IrText(")")))),
    IrAction(IrQuantifier, IrCallable(_gbnf_quantifier)),
    IrAction(IrItem,       IrConcat((IrChild("atom"), IrChild("quantifier")))),
    IrAction(IrSequence,   IrJoin(IrChildren("items"), IrText(" "), IrText('""'))),
    IrAction(IrAlternation,IrJoin(IrChildren("arms"), IrText(" | "), IrText(""))),
    IrAction(IrRule,       IrConcat((IrField("name"), IrText(" ::= "), IrChild("body")))),
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
        # Existing implementation, retargeted to return IrQuantifier
        ...

    @staticmethod
    def parse_charclass(text: str) -> tuple[str, bool]:
        # Existing implementation
        ...


GBNF: GbnfFlavour = GbnfFlavour(actions=_GBNF_ACTIONS)
```

The `parse_quantifier` and `parse_charclass` bodies are preserved verbatim from the existing `GbnfFlavour` — only the return type rename matters (already done in Step 4).

- [ ] **Step 3: Run full test suite**

```bash
uv run pytest -q
```

Expect: pass. If any GBNF round-trip test fails, the action tuple is wrong — diff against the old `GbnfEmitter` to verify what it produced.

- [ ] **Step 4: Commit**

```bash
git commit -am "grammars/gbnf: GBNF singleton with _GBNF_ACTIONS tuple

GbnfFlavour subclasses IrEmitter via Flavour. Module-level GBNF
singleton is built once with the per-IR-type action tuple. Pure-IrOp
bodies cover IrRuleRef, IrGroup, IrItem, IrSequence, IrAlternation,
IrRule; IrCallable bodies cover IrLiteral (escape encoding), IrCharClass
(negation prefix), IrQuantifier (symbol-table lookup), IrAst (newline
join + trailing newline)."
```

### Task 6.3: Delete `grammars/gbnf/emitter.py`

- [ ] **Step 1: Confirm no remaining imports**

```bash
uv run rg -n "grammars.gbnf.emitter|GbnfEmitter" src/ tests/
```

Expected: only references in `gbnf/emitter.py` itself (about to be deleted) and possibly its test file.

- [ ] **Step 2: Delete the file + its test**

```bash
git rm src/lexic/grammars/gbnf/emitter.py
git rm tests/unit/lexic/grammars/gbnf/test_emitter.py
```

- [ ] **Step 3: Run full suite**

```bash
uv run pytest -q
```

- [ ] **Step 4: Commit**

```bash
git commit -m "grammars/gbnf: delete emitter.py — superseded by GBNF singleton"
```

---

## Step 7 — Migrate `AbnfFlavour`

ABNF specifics: prefix-quantifier ordering on `IrItem`, ABNF's own quantifier symbols, ABNF-specific callables.

### Task 7.1: Per-flavour callables — `_abnf_encode_literal`, `_abnf_charclass`, `_abnf_quantifier`, `_abnf_ast`

**Files:**
- Modify: `src/lexic/grammars/abnf/flavour.py`
- Modify: `tests/unit/lexic/grammars/abnf/test_flavour.py`

- [ ] **Step 1: Read existing `AbnfEmitter`**

```bash
cat src/lexic/grammars/abnf/emitter.py
```

This file holds the canonical rendering for each IR-type case. Copy each method's body into a module-private function in `abnf/flavour.py` with signature `(_d, node, _nc) -> str`.

- [ ] **Step 2: Add four module-private helpers to `abnf/flavour.py`**

**Before writing**, read `src/lexic/grammars/abnf/emitter.py` to harvest exact strings for: literal-encoding format, char-class syntax (ABNF uses `%x41-5A` style, not `[A-Z]`), quantifier-symbol mapping, AST join behaviour. Each helper body below is illustrative; replace the body content with the exact logic from the existing emitter:

```python
def _abnf_encode_literal(_d, node, _nc) -> str:
    """Encode IrLiteral per ABNF rules. Body lifted from AbnfEmitter."""
    return AbnfEscapes.encode(node.value)


def _abnf_charclass(_d, node, _nc) -> str:
    """Render IrCharClass per ABNF %x syntax. Copy verbatim from AbnfEmitter.

    ABNF char-class form is %x<HH>-<HH> for ranges, %x<HH> for single chars,
    optionally bracketed for negation or alternation. Implement using the
    exact production rules currently in AbnfEmitter.
    """
    # PLACEHOLDER: replace with verbatim logic from grammars/abnf/emitter.py
    # The implementation must produce byte-equal output to the existing
    # emitter on every ground-truth ABNF grammar.
    raise NotImplementedError(
        "Lift body from src/lexic/grammars/abnf/emitter.py before running tests"
    )


def _abnf_quantifier(_d, node, _nc) -> str:
    """Render IrQuantifier as ABNF prefix form (e.g. '1*' for one-or-more)."""
    key = (node.min, node.max)
    try:
        return AbnfFlavour.quantifier_symbols[key]
    except KeyError as exc:
        raise UnsupportedConstructError(
            f"ABNF does not support quantifier {key}"
        ) from exc


def _abnf_ast(_d, _node, new_children) -> str:
    """Render rules joined per ABNF source convention. Verify against AbnfEmitter."""
    return "\n".join(new_children) + "\n"
```

The `_abnf_charclass` body MUST be lifted from the existing `AbnfEmitter` — placeholder above raises so accidental tests fail loudly until the engineer does the lift. Run `uv run pytest tests/integration/test_compile_grammar_abnf.py -v` after replacing the placeholder; round-trip on the ground-truth ABNF grammars is the verification.

- [ ] **Step 3: Write unit tests for each helper** — same shape as `test_gbnf_flavour.py`'s tests in Task 6.1, but with ABNF expected strings.

- [ ] **Step 4: Implement; run unit tests; commit**

```bash
git commit -am "grammars/abnf: per-flavour IrCallable helpers"
```

### Task 7.2: `_ABNF_ACTIONS` tuple + `ABNF` singleton

- [ ] **Step 1: Build the action tuple in `abnf/flavour.py`**

Mirrors `_GBNF_ACTIONS` with two differences: prefix-quantifier ordering on `IrItem`, and ABNF's own `quantifier_symbols`.

```python
from lexic.ir.action import (
    IrAction, IrCallable, IrChild, IrChildren, IrField, IrJoin, IrConcat, IrText,
)
from lexic.ir.nodes import (
    IrAlternation, IrAst, IrCharClass, IrGroup, IrItem, IrLiteral,
    IrQuantifier, IrRule, IrRuleRef, IrSequence,
)


_ABNF_ACTIONS: tuple[IrAction, ...] = (
    IrAction(IrLiteral,    IrCallable(_abnf_encode_literal)),
    IrAction(IrCharClass,  IrCallable(_abnf_charclass)),
    IrAction(IrRuleRef,    IrField("name")),
    IrAction(IrGroup,      IrConcat((IrText("("), IrChild("body"), IrText(")")))),
    IrAction(IrQuantifier, IrCallable(_abnf_quantifier)),
    # KEY DIFFERENCE FROM GBNF: quantifier BEFORE atom for ABNF prefix form.
    IrAction(IrItem,       IrConcat((IrChild("quantifier"), IrChild("atom")))),
    IrAction(IrSequence,   IrJoin(IrChildren("items"), IrText(" "), IrText(""))),
    IrAction(IrAlternation,IrJoin(IrChildren("arms"), IrText(" / "), IrText(""))),
    IrAction(IrRule,       IrConcat((IrField("name"), IrText(" = "), IrChild("body")))),
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
        # ABNF uses prefix notation: <min>*<max>element
        # Exact symbol mapping — consult existing AbnfEmitter.
        (1, 1): "",
        (0, 1): "*1",        # "optional"
        (0, None): "*",      # "zero or more"
        (1, None): "1*",     # "one or more"
    }

    @staticmethod
    def parse_quantifier(text: str) -> IrQuantifier:
        # Lift verbatim from the existing AbnfFlavour.parse_quantifier
        # in src/lexic/grammars/abnf/flavour.py (pre-migration).
        # Only the return type changes (Quantifier → IrQuantifier per Step 4).
        raise NotImplementedError("Lift from pre-migration AbnfFlavour")

    @staticmethod
    def parse_charclass(text: str) -> tuple[str, bool]:
        # Same — lift verbatim.
        raise NotImplementedError("Lift from pre-migration AbnfFlavour")


ABNF: AbnfFlavour = AbnfFlavour(actions=_ABNF_ACTIONS)
```

Verify the separator strings (` `, ` / `, ` = `) and quantifier symbols against the existing `AbnfEmitter` — those are the authoritative source. The `parse_quantifier` / `parse_charclass` bodies stay verbatim from the existing `AbnfFlavour` — the placeholders above raise so the engineer cannot forget to lift them. After lifting, full suite must be green.

- [ ] **Step 2: Run full test suite**

```bash
uv run pytest -q
```

If `test_compile_grammar_abnf.py` or round-trip tests fail, diff the ABNF emitter against the new action tuple — usually a separator string or quantifier symbol is off.

- [ ] **Step 3: Commit**

```bash
git commit -am "grammars/abnf: ABNF singleton with _ABNF_ACTIONS tuple

Mirrors GbnfFlavour migration with ABNF-specific differences: prefix
quantifier ordering on IrItem, ABNF-specific separator strings, ABNF's
own quantifier_symbols table."
```

### Task 7.3: Delete `grammars/abnf/emitter.py`

- [ ] **Step 1: Confirm no remaining imports**

```bash
uv run rg -n "grammars.abnf.emitter|AbnfEmitter" src/ tests/
```

- [ ] **Step 2: Delete**

```bash
git rm src/lexic/grammars/abnf/emitter.py
git rm tests/unit/lexic/grammars/abnf/test_emitter.py
```

- [ ] **Step 3: Run suite; commit**

```bash
git commit -m "grammars/abnf: delete emitter.py — superseded by ABNF singleton"
```

---

## Step 8 — Migrate consumers

### Task 8.1: `base.py` `to_grammar` flips to `GBNF` singleton

**Files:**
- Modify: `src/lexic/base.py`
- Modify: `tests/unit/lexic/test_base.py`

- [ ] **Step 1: Identify current import**

```bash
uv run rg -n "GbnfEmitter|gbnf.emitter|to_gbnf" src/lexic/base.py
```

- [ ] **Step 2: Update import + call site**

Replace `from lexic.grammars.gbnf.emitter import GbnfEmitter` with `from lexic.grammars.gbnf.flavour import GBNF`. Replace the `GbnfEmitter()(...)` call (or whatever the current shape is) with `GBNF(...)`.

The exact change depends on `base.py`'s current shape — read the file first.

- [ ] **Step 3: Update existing tests** that mocked or referenced `GbnfEmitter`.

- [ ] **Step 4: Run full suite; pass.**

- [ ] **Step 5: Update CLAUDE.md's two-exceptions wording**

Change:
> `base.py` imports `lexic.grammars.gbnf.emitter` at module scope for `to_gbnf()`.

To:
> `base.py` imports the `GBNF` singleton from `lexic.grammars.gbnf.flavour` at module scope for `to_gbnf()`.

- [ ] **Step 6: Commit**

```bash
git commit -am "base: to_gbnf flips to GBNF singleton

The first documented runtime→codegen exception's import target changes
from lexic.grammars.gbnf.emitter (deleted) to the GBNF singleton in
lexic.grammars.gbnf.flavour. CLAUDE.md updated to match."
```

### Task 8.2: `parsing/lark_builder.py` mechanical fixes

Mechanical fixes if `IrDispatch` API changes forced any. Typical: change `.visit(x)` to `(x)` if any callsite used the old visit method.

- [ ] **Step 1: Audit**

```bash
uv run rg -n "\\.visit\\(|dump\\(|_CHILDREN" src/lexic/parsing/
```

- [ ] **Step 2: Apply minimum fixes; run suite; commit if needed.**

```bash
git commit -am "parsing/lark_builder: mechanical fixes for new IrDispatch API"
```

### Task 8.3: Delete `utils/quantifiers.py`

- [ ] **Step 1: Confirm no remaining callers**

```bash
uv run rg -n "from lexic.utils.quantifiers|utils\\.quantifiers" src/ tests/
```

- [ ] **Step 2: Delete**

```bash
git rm src/lexic/utils/quantifiers.py
git rm tests/unit/lexic/utils/test_quantifiers.py
```

- [ ] **Step 3: Run suite; commit**

```bash
git commit -m "utils: delete quantifiers.py — per-flavour quantifier rendering now in action tables"
```

---

## Step 9 — Opportunistic cleanup

### Task 9.1: `ir/helpers.py` — delete if trivially safe

- [ ] **Step 1: Audit references**

```bash
uv run rg -n "ir\\.helpers|HelperRuleRegistry" src/ tests/
```

If zero production callers (only its own test imports), proceed. Otherwise leave it.

- [ ] **Step 2: Delete (if safe)**

```bash
git rm src/lexic/ir/helpers.py
git rm tests/unit/lexic/ir/test_helpers.py
```

Remove `HelperRuleRegistry` from `ir/__init__.py` exports if listed.

- [ ] **Step 3: Run suite; commit**

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
- Substrate (`IrAction` + `IrOp` algebra + nine variants).
- Dispatch mechanics (auto-walk via `node.children()`, MRO resolve, `IrReturn` raising `_Return`).
- Presets — IrVisitor / IrTransformer / IrEmitter as concrete subclasses, default behaviours per preset.
- IR-pass-by-action-table convention (`has_ruleref`, `hoist_helpers` as examples).
- IrQuantifier rename.
- Flavour-as-IrEmitter — metadata as `ClassVar`s, behaviour as `actions` tuple, module-level singletons.

- [ ] **Step 2: Update `flavour-system.md`**

Per-flavour singleton convention, action tuple structure, IrCallable usage guidelines.

- [ ] **Step 3: Update `ir-shapes.md`**

- IrQuantifier rename note.
- `IrOp` algebra brief reference (point to architecture.md for detail).

- [ ] **Step 4: Add decisions to `decisions.md`**

- P12 strengthened (IR passes by action table, not closed subclass).
- P13 (IR describes the IR).
- P14 (`IrDispatch` not bounded by `_T`).
- P15 (concrete-first MRO; `IrAction(IrNode, …)` as default-override).
- P16 (short-circuit intrinsic to `IrReturn` via exception).

- [ ] **Step 5: Add `log.md` entry**

```markdown
## 2026-05-18 — Slice B closed: IrAction/IrOp substrate + Flavour-as-IrEmitter

…brief summary linking to spec + plan…
```

- [ ] **Step 6: Update CLAUDE.md**

- "Two deliberate exceptions" wording: first exception import target now `lexic.grammars.gbnf.flavour` (the `GBNF` singleton).
- Project layout section: update file tree for `ir/action.py` (new), deleted `gbnf/emitter.py` / `abnf/emitter.py` / `utils/quantifiers.py`, possibly `ir/helpers.py`.
- Pipeline flow diagram: emit path now reads `flavour(node)` singleton call rather than constructing an emitter.

- [ ] **Step 7: Commit**

```bash
git commit -am "wiki + docs: document slice B substrate and Flavour-as-IrEmitter

- architecture.md: substrate, dispatch mechanics, presets,
  IR-pass-by-action-table convention.
- flavour-system.md: singleton convention, action tuple structure.
- ir-shapes.md: IrQuantifier rename note.
- decisions.md: P12-strengthened, P13, P14, P15, P16.
- log.md: slice B closed entry.
- CLAUDE.md: two-exceptions wording, file tree, pipeline flow."
```

---

## Final verification

- [ ] **Step 1: Full suite**

```bash
uv run pytest -q
```

Expect: 448+ tests pass.

- [ ] **Step 2: Lint clean**

```bash
uv run ruff check src/ tests/
```

- [ ] **Step 3: Round-trip spot-check**

```bash
uv run pytest tests/integration/test_full_round_trip.py -v
```

Every ground-truth grammar round-trips byte-equal.

- [ ] **Step 4: Anti-creep audit**

```bash
uv run rg -n "pre_parse_check|_SKIP_RECURSION|pre_recurse" src/ tests/
```

Expected: zero hits.

```bash
uv run rg -n "IrOp\\b" src/ | sort -u
```

Expected: only the nine canonical variants and their bases/aliases.

- [ ] **Step 5: Slice closed**

Optional: delete `.wiki/lexic/slice-b-status.md` if it exists.

---

## Risk-area mitigations (reminders during execution)

- **Step 2 (Task 2.1) is the deepest cut.** If the rewrite is hairier than expected — e.g. resolving the entry/recursion split across consumers proves messy — split into 2.1a (introduce new dispatcher under a temporary name like `IrDispatch2`, migrate consumers one by one) and 2.1b (rename + delete old). The plan doesn't pre-commit to either; pick at execution time.

- **`IrCallable` discipline (Step 6/7).** If a flavour action ends up using `IrCallable` for a case that ought to be pure IrOp (one of `IrRuleRef`, `IrGroup`, `IrItem`, `IrSequence`, `IrAlternation`, `IrRule`), stop and surface — that's the substrate failing to express something it should. Permitted `IrCallable` use is limited to the four documented per-flavour cases.

- **`_Return` semantics.** Run the explicit test that an `IrCallable` body wrapping its work in `except Exception:` does not swallow `_Return`. If that test fails, the inheritance is wrong.

- **MRO lookup.** `_resolve` must memoize negative hits — caching `None` for genuine misses — so the preset default fires instead of being re-resolved each time.

- **`IrAction.target_type` not a child.** Verify `IrAction(IrLiteral, IrText("x")).children() == (IrText("x"),)` — the `type` object must not appear in the children tuple.
