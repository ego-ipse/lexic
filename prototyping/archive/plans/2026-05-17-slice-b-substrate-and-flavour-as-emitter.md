# Slice B — IrAction/IrOp substrate + Flavour-as-IrEmitter — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land the IrAction/IrOp substrate, rewrite `IrDispatch` as an action-driven, MRO-resolving, frozen-IrNode dataclass, migrate every IR-internal closed-subclass pass (`_HoistTransformer`, `_RuleRefFinder`) and the one forced codegen consumer (`_PatternAliasVisitor`) onto the substrate, rename `Quantifier` → `IrQuantifier`, refactor `Flavour` as an `IrEmitter` singleton (GBNF + ABNF), and remove `FlavourEmitter` / `GbnfEmitter` / `AbnfEmitter` / `utils/quantifiers.py`.

**Architecture:** Every IR pass becomes an `IrDispatch` instance loaded with an `actions: tuple[IrAction, ...]` table; lookup walks `type(node).__mro__` concrete-first so ABC-keyed actions provide hierarchy-level defaults. `IrDispatch` is itself a frozen-slotted `IrNode` (the actions are its children); per-pass mutable scratch lives in closures captured by `IrCallable` handlers and the optional `pre_recurse` hook field. `IrAction`, every `IrOp` variant, and `IrDispatch` itself satisfy the IrNode protocol — `repr(GBNF)` dumps the entire dispatch tree. `Flavour` is a frozen-dataclass `IrEmitter` whose instance fields are `actions` (and optionally `pre_recurse`); per-flavour metadata is `ClassVar`. Concrete flavours ship as module-level singletons.

**Tech Stack:** Python 3.13 dataclasses (frozen, slots), `lark` (already in tree). No new external dependencies.

**Spec:** `docs/superpowers/specs/2026-05-17-slice-b-substrate-and-flavour-as-emitter-design.md`
**Scope companion (what's NOT in this plan):** `docs/superpowers/specs/2026-05-17-slice-b-deferred-work.md`

---

## File structure

### Created

```
src/lexic/ir/action.py                       IrOp ABC, 7 op variants, IrAction
tests/unit/lexic/ir/test_action.py           Op eval semantics + IrAction binding
tests/unit/lexic/ir/test_dispatch_mro.py     MRO-walk lookup + pre_recurse short-circuit
tests/unit/lexic/ir/test_dispatch_presets.py Preset default() behaviour + repr smoke test
```

### Modified

```
src/lexic/ir/walk.py                          IrDispatch rewritten action-driven (frozen
                                              dataclass, IrNode); IrTransformer/IrVisitor/
                                              IrEmitter presets; legacy _CHILDREN/_REBUILD/
                                              _DUMP/dump/visit/generic_visit removed.
src/lexic/ir/derive.py                        _HoistTransformer / _RuleRefFinder rewritten
                                              as factory functions returning loaded
                                              IrTransformer / IrVisitor instances; closure
                                              state, no per-instance mutable scratch.
src/lexic/ir/nodes.py                         Quantifier → IrQuantifier rename.
src/lexic/ir/__init__.py                      Export IrQuantifier, IrAction, IrOp variants;
                                              drop dump.
src/lexic/codegen/aliases.py                  _PatternAliasVisitor rewritten as factory
                                              returning a loaded IrVisitor with
                                              pre_recurse hook for IrGroup frame mgmt.
src/lexic/codegen/model_emitter.py            Quantifier → IrQuantifier; otherwise unchanged.
src/lexic/generate.py                         Quantifier → IrQuantifier.
src/lexic/parsing/meta_parser.py              Quantifier → IrQuantifier.
src/lexic/parsing/transformer/build_transformer.py
                                              Quantifier → IrQuantifier; closed-subclass
                                              visitor (if any) gets mechanical fix.
src/lexic/parsing/lark_builder.py             Quantifier → IrQuantifier; absorbs the
                                              previously-utility quantifier helpers.
src/lexic/grammars/flavour.py                 Flavour(IrEmitter, ABC); ClassVar metadata;
                                              no pre_parse_check.
src/lexic/grammars/gbnf/flavour.py            Module-level GBNF singleton + action tuple.
src/lexic/grammars/abnf/flavour.py            Module-level ABNF singleton + action tuple.
src/lexic/grammars/__init__.py                Re-export GBNF / ABNF singletons.
src/lexic/ir/emit.py                          render_specs(specs, flavour) — thin shell.
src/lexic/base.py                             Import target flips to GBNF singleton.
CLAUDE.md                                     Update "two deliberate exceptions" wording.
.wiki/lexic/architecture.md                   Substrate, IR-pass-by-action-table convention.
.wiki/lexic/flavour-system.md                 Flavour-as-IrEmitter; singleton convention.
.wiki/lexic/ir-shapes.md                      IrQuantifier; IrAction/IrOp types.
.wiki/lexic/decisions.md                      P13, P14, P15, P16, P17 entries.
.wiki/lexic/log.md                            Entry summarizing slice landing.
.wiki/lexic/slice-b-status.md                 Slice closed.
```

### Deleted

```
src/lexic/grammars/gbnf/emitter.py
src/lexic/grammars/abnf/emitter.py
src/lexic/utils/quantifiers.py
tests/unit/lexic/grammars/gbnf/test_emitter.py
tests/unit/lexic/grammars/abnf/test_emitter.py
tests/unit/lexic/utils/test_quantifiers.py
src/lexic/ir/helpers.py                       (opportunistic — see Step 8)
tests/unit/lexic/ir/test_helpers.py           (opportunistic — see Step 8)
```

---

## Conventions for every task

- **Always prefix commands with `uv run`.** Never bare `pytest` or `ruff`.
- **TDD order:** failing test → confirm failure → minimal implementation → confirm pass → ruff/auto_fix → commit.
- **Mechanical fixes first:** run `tools/auto_fix.sh` before manual lint cleanup.
- **Docstrings:** Sphinx style — `:param:`, `:returns:`, `:raises:`.
- **No `Co-Authored-By` line on commits.**
- **No `# type: ignore` / `# pylint: disable` / `# noqa`** without explicit prior permission. Fix the root cause.
- **Test naming for `__init__.py` modules:** `test_init_<package>.py`.
- **After each task: full suite must be green.** `uv run pytest tests/ -q`. The slice's load-bearing invariant. The only exception is Step 5 (Flavour-as-IrEmitter), an atomic group that commits sub-tasks individually but only runs the suite at the end.
- **Ask before each task** whether to dispatch a subagent or implement manually.

---

## Step 1 — `ir/action.py` introduces IrAction + IrOp algebra

The substrate's data layer. Every variant is an `IrNode` subclass — mechanical `children()` / `rebuild()` / `__str__` / `__repr__` via the existing hierarchy.

### Task 1.1: Module skeleton, `IrOp` ABC, `IrText`

**Files:**
- Create: `src/lexic/ir/action.py`
- Create: `tests/unit/lexic/ir/test_action.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/lexic/ir/test_action.py
from lexic.ir.action import IrText
from lexic.ir.nodes import IrLeaf, IrLiteral, IrNode


def test_irtext_eval_returns_text_literal():
    op = IrText("hello")
    assert op.eval(None, IrLiteral("x"), ()) == "hello"


def test_irtext_is_irnode_and_irleaf():
    assert issubclass(IrText, IrNode)
    assert issubclass(IrText, IrLeaf)


def test_irtext_str_uses_canonical_form():
    assert str(IrText("hi")) == "TEXT('hi')"
```

- [ ] **Step 2: Confirm failure**

```
uv run pytest tests/unit/lexic/ir/test_action.py -v
```
Expected: ImportError (`lexic.ir.action` does not exist).

- [ ] **Step 3: Implement**

```python
# src/lexic/ir/action.py
"""IrAction + IrOp algebra — the substrate for action-driven IrDispatch.

Every op is an :class:`IrNode` subclass; the IR describes its own behaviour.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, ClassVar

from lexic.ir.nodes import IrCollection, IrComposite, IrLeaf, IrNode

if TYPE_CHECKING:
    from lexic.ir.walk import IrDispatch


class IrOp(IrNode, ABC):
    """One operation in an action body.

    Subclasses implement :meth:`eval`. Children, rebuild, str, repr are
    inherited from the appropriate :class:`IrLeaf` / :class:`IrCollection`
    / :class:`IrComposite` mixin.
    """

    @abstractmethod
    def eval(
        self,
        dispatch: IrDispatch | None,
        node: IrNode | None,
        new_children: tuple,
        /,
    ) -> object:
        """Evaluate this op against ``node`` in the context of ``dispatch``.

        :param dispatch: The dispatcher invoking the action (may be ``None``
            for isolated unit tests of leaf ops).
        :param node: The IR node currently being dispatched on.
        :param new_children: Already-recursed children of ``node``.
        :returns: The op's value — type depends on the variant.
        """


@dataclass(frozen=True, slots=True, repr=False)
class IrText(IrLeaf, IrOp):
    """A constant string literal in an action body."""

    text: str
    _str_name: ClassVar[str] = "TEXT"

    def eval(self, dispatch, node, new_children, /):
        """Return the literal text."""
        return self.text
```

- [ ] **Step 4: Confirm pass; full suite; lint; commit**

```
uv run pytest tests/unit/lexic/ir/test_action.py -v
uv run pytest tests/ -q
tools/auto_fix.sh
uv run pylint src/lexic/ir/action.py
git add src/lexic/ir/action.py tests/unit/lexic/ir/test_action.py
git commit -m "ir/action: add IrOp ABC and IrText leaf op"
```

### Task 1.2: `IrField` and `IrRecurse`

**Files:**
- Modify: `src/lexic/ir/action.py`
- Modify: `tests/unit/lexic/ir/test_action.py`

- [ ] **Step 1: Failing tests**

```python
# Append to tests/unit/lexic/ir/test_action.py
from dataclasses import dataclass

from lexic.ir.action import IrField, IrRecurse


def test_irfield_returns_named_attribute_raw():
    assert IrField("value").eval(None, IrLiteral("abc"), ()) == "abc"


def test_irfield_str():
    assert str(IrField("name")) == "FIELD('name')"


class _StubDispatch:
    """Test-only dispatcher; records visits, returns a string for any node."""

    def __init__(self):
        self.seen: list = []

    def __call__(self, node):
        self.seen.append(node)
        return f"<{type(node).__name__}>"


def test_irrecurse_dispatches_named_child():
    @dataclass(frozen=True, slots=True)
    class _Wrapper(IrNode):
        body: IrNode
        def children(self): return (self.body,)
        def rebuild(self, ch): return _Wrapper(body=ch[0])
        def _inner_str(self): return str(self.body)

    inner = IrLiteral("x")
    wrapper = _Wrapper(body=inner)
    dispatch = _StubDispatch()
    IrRecurse("body").eval(dispatch, wrapper, (inner,))
    assert dispatch.seen == [inner]
```

- [ ] **Step 2: Confirm failure**

- [ ] **Step 3: Implement**

```python
# Append to src/lexic/ir/action.py
@dataclass(frozen=True, slots=True, repr=False)
class IrField(IrLeaf, IrOp):
    """Read a named attribute of the dispatched node, raw (no recursion)."""

    field_name: str
    _str_name: ClassVar[str] = "FIELD"

    def eval(self, dispatch, node, new_children, /):
        """Return ``getattr(node, self.field_name)`` unchanged."""
        return getattr(node, self.field_name)


@dataclass(frozen=True, slots=True, repr=False)
class IrRecurse(IrLeaf, IrOp):
    """Re-dispatch on a named child of the current node."""

    field_name: str
    _str_name: ClassVar[str] = "RECURSE"

    def eval(self, dispatch, node, new_children, /):
        """Invoke ``dispatch`` on ``getattr(node, self.field_name)``."""
        return dispatch(getattr(node, self.field_name))
```

- [ ] **Step 4: Confirm pass; full suite; lint; commit**

```
uv run pytest tests/ -q
tools/auto_fix.sh
git add -p
git commit -m "ir/action: add IrField and IrRecurse"
```

### Task 1.3: `IrSeq`

**Files:**
- Modify: `src/lexic/ir/action.py`
- Modify: `tests/unit/lexic/ir/test_action.py`

- [ ] **Step 1: Failing tests**

```python
from lexic.ir.action import IrSeq


def test_irseq_concatenates_string_parts():
    assert IrSeq((IrText("a"), IrText("b"), IrText("c"))).eval(None, None, ()) == "abc"


def test_irseq_str():
    assert str(IrSeq((IrText("a"), IrText("b")))) == "SEQ(TEXT('a'), TEXT('b'))"


def test_irseq_children_and_rebuild():
    op = IrSeq((IrText("a"),))
    assert op.children() == (IrText("a"),)
    assert op.rebuild((IrText("z"),)) == IrSeq((IrText("z"),))
```

- [ ] **Step 2: Confirm failure**

- [ ] **Step 3: Implement**

```python
@dataclass(frozen=True, slots=True, repr=False)
class IrSeq(IrCollection["IrOp"], IrOp):
    """Evaluate ops in order; return their str-concatenated results."""

    parts: tuple[IrOp, ...]
    _items_attr: ClassVar[str] = "parts"
    _str_name: ClassVar[str] = "SEQ"

    def eval(self, dispatch, node, new_children, /):
        """Concatenate ``str(p.eval(...))`` over each part."""
        return "".join(str(p.eval(dispatch, node, new_children)) for p in self.parts)
```

- [ ] **Step 4: Confirm pass; full suite; lint; commit**

```
git commit -m "ir/action: add IrSeq"
```

### Task 1.4: `IrJoin`

**Files:**
- Modify: `src/lexic/ir/action.py`
- Modify: `tests/unit/lexic/ir/test_action.py`

- [ ] **Step 1: Failing tests**

```python
from lexic.ir.action import IrJoin


def test_irjoin_dispatches_each_iterable_element_and_joins():
    @dataclass(frozen=True, slots=True)
    class _ItemsWrapper(IrNode):
        items: tuple[IrLiteral, ...]
        def children(self): return self.items
        def rebuild(self, ch): return _ItemsWrapper(items=ch)
        def _inner_str(self): return ",".join(str(i) for i in self.items)

    items = (IrLiteral("a"), IrLiteral("b"))
    dispatch = _StubDispatch()
    result = IrJoin("items", IrText(" "), IrText("")).eval(
        dispatch, _ItemsWrapper(items=items), (),
    )
    assert result == "<IrLiteral> <IrLiteral>"
    assert dispatch.seen == list(items)


def test_irjoin_empty_iterable_returns_empty_value():
    @dataclass(frozen=True, slots=True)
    class _Empty(IrNode):
        items: tuple[IrLiteral, ...] = ()
        def children(self): return self.items
        def rebuild(self, ch): return _Empty(items=ch)
        def _inner_str(self): return ""

    assert IrJoin("items", IrText(" "), IrText('""')).eval(
        _StubDispatch(), _Empty(), (),
    ) == '""'


def test_irjoin_children_are_separator_and_empty():
    op = IrJoin("items", IrText(" "), IrText('""'))
    assert op.children() == (IrText(" "), IrText('""'))
```

- [ ] **Step 2: Confirm failure**

- [ ] **Step 3: Implement**

```python
@dataclass(frozen=True, slots=True, repr=False)
class IrJoin(IrComposite["IrText", "IrText"], IrOp):
    """Dispatch each element of an iterable attribute; join results with separator.

    ``field_name`` is metadata (a str), not a child. ``separator`` and ``empty``
    are :class:`IrText` children.
    """

    field_name: str
    separator: IrText
    empty: IrText
    _child_attrs: ClassVar[tuple[str, ...]] = ("separator", "empty")
    _extra_field_names: ClassVar[tuple[str, ...]] = ("field_name",)
    _str_name: ClassVar[str] = "JOIN"

    def eval(self, dispatch, node, new_children, /):
        """Render each item via ``dispatch``; join with ``separator``."""
        items = getattr(node, self.field_name)
        rendered = [str(dispatch(it)) for it in items]
        return self.separator.text.join(rendered) if rendered else self.empty.text
```

- [ ] **Step 4: Confirm pass; full suite; lint; commit**

### Task 1.5: `IrCond`

**Files:**
- Modify: `src/lexic/ir/action.py`
- Modify: `tests/unit/lexic/ir/test_action.py`

- [ ] **Step 1: Failing tests**

```python
from lexic.ir.action import IrCond


def test_ircond_truthy_and_falsey_branches():
    @dataclass(frozen=True, slots=True)
    class _Flagged(IrNode):
        flag: bool = True
        def children(self): return ()
        def rebuild(self, ch): return self
        def _inner_str(self): return repr(self.flag)

    op = IrCond("flag", IrText("yes"), IrText("no"))
    assert op.eval(None, _Flagged(True), ()) == "yes"
    assert op.eval(None, _Flagged(False), ()) == "no"


def test_ircond_children_are_then_and_else():
    op = IrCond("flag", IrText("y"), IrText("n"))
    assert op.children() == (IrText("y"), IrText("n"))
```

- [ ] **Step 2: Confirm failure**

- [ ] **Step 3: Implement**

```python
@dataclass(frozen=True, slots=True, repr=False)
class IrCond(IrComposite["IrOp", "IrOp"], IrOp):
    """If ``getattr(node, field_name)`` is truthy, evaluate ``then_op``; else ``else_op``."""

    field_name: str
    then_op: IrOp
    else_op: IrOp
    _child_attrs: ClassVar[tuple[str, ...]] = ("then_op", "else_op")
    _extra_field_names: ClassVar[tuple[str, ...]] = ("field_name",)
    _str_name: ClassVar[str] = "COND"

    def eval(self, dispatch, node, new_children, /):
        branch = self.then_op if getattr(node, self.field_name) else self.else_op
        return branch.eval(dispatch, node, new_children)
```

- [ ] **Step 4: Confirm pass; full suite; lint; commit**

### Task 1.6: `IrCallable`

**Files:**
- Modify: `src/lexic/ir/action.py`
- Modify: `tests/unit/lexic/ir/test_action.py`

- [ ] **Step 1: Failing tests**

```python
from lexic.ir.action import IrCallable


def test_ircallable_invokes_handler_with_three_args():
    captured = {}
    def _h(d, node, nc):
        captured["args"] = (d, node, nc)
        return "handled"

    assert IrCallable(_h).eval("D", IrLiteral("x"), ("C",)) == "handled"
    assert captured["args"] == ("D", IrLiteral("x"), ("C",))


def test_ircallable_str_shows_handler_qualname():
    def _h(d, n, c):
        return None
    s = str(IrCallable(_h))
    assert s.startswith("CALLABLE")
    assert "_h" in s
```

- [ ] **Step 2: Confirm failure**

- [ ] **Step 3: Implement**

```python
@dataclass(frozen=True, slots=True, repr=False)
class IrCallable(IrLeaf, IrOp):
    """Procedural escape hatch — the body is an opaque Python callable.

    Used where pure IrOp doesn't fit: stateful allocators, side-effect
    collectors, symbol-table lookups. Future slices may migrate specific
    IrCallable bodies to pure IrOp without touching the surrounding plumbing.
    """

    handler: Callable[[object, IrNode, tuple], object]
    _str_name: ClassVar[str] = "CALLABLE"

    def _inner_str(self) -> str:
        """Use the handler's qualname for human-readable canonical form."""
        return getattr(self.handler, "__qualname__", repr(self.handler))

    def eval(self, dispatch, node, new_children, /):
        """Invoke ``handler(dispatch, node, new_children)``."""
        return self.handler(dispatch, node, new_children)
```

- [ ] **Step 4: Confirm pass; full suite; lint; commit**

### Task 1.7: `IrAction`

**Files:**
- Modify: `src/lexic/ir/action.py`
- Modify: `tests/unit/lexic/ir/test_action.py`

- [ ] **Step 1: Failing tests**

```python
from lexic.ir.action import IrAction


def test_iraction_binds_target_type_and_body():
    action = IrAction(IrLiteral, IrField("value"))
    assert action.target_type is IrLiteral
    assert action.body == IrField("value")


def test_iraction_eval_delegates_to_body():
    assert IrAction(IrLiteral, IrText("X")).eval(None, IrLiteral("y"), ()) == "X"


def test_iraction_target_type_is_not_a_child():
    body = IrText("X")
    assert IrAction(IrLiteral, body).children() == (body,)


def test_iraction_rebuild_preserves_target_type():
    new = IrAction(IrLiteral, IrText("X")).rebuild((IrText("Y"),))
    assert new == IrAction(IrLiteral, IrText("Y"))
    assert new.target_type is IrLiteral


def test_iraction_str_shows_target_and_body():
    s = str(IrAction(IrLiteral, IrText("X")))
    assert "IrLiteral" in s
    assert "TEXT('X')" in s
```

- [ ] **Step 2: Confirm failure**

- [ ] **Step 3: Implement**

```python
@dataclass(frozen=True, slots=True, repr=False)
class IrAction(IrComposite["IrOp"], IrOp):
    """Bind a target IR node type to an op body.

    ``target_type`` is metadata (a Python class object), NOT a child. Only
    ``body`` participates in :meth:`children` / :meth:`rebuild`.
    """

    target_type: type[IrNode]
    body: IrOp
    _child_attrs: ClassVar[tuple[str, ...]] = ("body",)
    _extra_field_names: ClassVar[tuple[str, ...]] = ("target_type",)
    _str_name: ClassVar[str] = "ACTION"

    def eval(self, dispatch, node, new_children, /):
        """Evaluate the bound body. Type matching is the dispatcher's job."""
        return self.body.eval(dispatch, node, new_children)
```

- [ ] **Step 4: Confirm pass; full suite; lint; commit**

```
git commit -m "ir/action: add IrCallable and IrAction; close substrate data layer"
```

---

## Step 2 — Action-driven `IrDispatch` introduced alongside the legacy one

The existing `walk.py` `IrDispatch` (`_CHILDREN`/`_REBUILD`/`_DUMP`/`visit`/`generic_visit`) keeps working through Step 2 so closed-subclass consumers (`_HoistTransformer`, `_RuleRefFinder`, `_PatternAliasVisitor`) drive their tests through the old API. The new substrate lands under a temporary private name (`_NewIrDispatch` and `_NewIrTransformer` / `_NewIrVisitor` / `_NewIrEmitter`), and Step 4 renames them after migrating consumers.

### Task 2.1: Introduce `_NewIrDispatch` with `pre_recurse` + MRO resolution

**Files:**
- Modify: `src/lexic/ir/walk.py`
- Create: `tests/unit/lexic/ir/test_dispatch_mro.py`

- [ ] **Step 1: Failing tests for MRO + short-circuit**

```python
# tests/unit/lexic/ir/test_dispatch_mro.py
"""P15: MRO-walk lookup. P16: pre_recurse short-circuit semantics."""

import pytest

from lexic.exceptions import UnsupportedConstructError
from lexic.ir.action import IrAction, IrCallable, IrText
from lexic.ir.nodes import IrCharClass, IrLeaf, IrLiteral, IrNode
from lexic.ir.walk import _NewIrDispatch


class _StringDispatch(_NewIrDispatch):
    def default(self, node, new_children):
        return "default"


def test_exact_type_match_wins():
    d = _StringDispatch(actions=(
        IrAction(IrLiteral, IrText("literal")),
        IrAction(IrLeaf,    IrText("any-leaf")),
    ))
    assert d(IrLiteral("x")) == "literal"


def test_abc_keyed_action_matches_subclass():
    d = _StringDispatch(actions=(IrAction(IrLeaf, IrText("any-leaf")),))
    assert d(IrLiteral("x")) == "any-leaf"
    assert d(IrCharClass("a-z", False)) == "any-leaf"


def test_concrete_wins_over_abc_regardless_of_order():
    d = _StringDispatch(actions=(
        IrAction(IrLeaf, IrText("any-leaf")),
        IrAction(IrLiteral, IrText("literal")),
    ))
    assert d(IrLiteral("x")) == "literal"


def test_miss_falls_to_default():
    d = _StringDispatch(actions=(IrAction(IrLiteral, IrText("literal")),))
    assert d(IrCharClass("a-z", False)) == "default"


def test_irnode_universal_catchall():
    d = _StringDispatch(actions=(IrAction(IrNode, IrText("universal")),))
    assert d(IrLiteral("x")) == "universal"


def test_resolve_caches_negative_lookups():
    d = _StringDispatch(actions=(IrAction(IrLiteral, IrText("L")),))
    assert d(IrCharClass("a", False)) == "default"
    assert d(IrCharClass("a", False)) == "default"


def test_pre_recurse_skip_sentinel_suppresses_recursion():
    """When pre_recurse returns _SKIP_RECURSION, children are not visited."""
    visit_counts = {"n": 0}

    def _count(d, node, nc):
        visit_counts["n"] += 1
        return "v"

    actions = (IrAction(IrLiteral, IrCallable(_count)),)

    state = {"halt": False}

    def _pre(node):
        return _StringDispatch._SKIP_RECURSION if state["halt"] else None

    d = _StringDispatch(actions=actions, pre_recurse=_pre)
    d(IrLiteral("a"))
    assert visit_counts["n"] == 1
    state["halt"] = True
    d(IrLiteral("b"))
    # Skip-recursion fell through to default; the IrCallable action did not fire.
    assert visit_counts["n"] == 1


def test_resolve_cache_mutation_inside_frozen_slot_works():
    d = _StringDispatch(actions=(IrAction(IrLiteral, IrText("L")),))
    d(IrLiteral("a"))   # populates cache
    assert IrLiteral in d._resolve_cache


def test_rebinding_frozen_slot_raises():
    d = _StringDispatch(actions=())
    import dataclasses
    with pytest.raises(dataclasses.FrozenInstanceError):
        d._resolve_cache = {}
```

- [ ] **Step 2: Confirm failure**

```
uv run pytest tests/unit/lexic/ir/test_dispatch_mro.py -v
```

- [ ] **Step 3: Implement**

```python
# Append to src/lexic/ir/walk.py (do not touch the existing IrDispatch yet)
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Callable, ClassVar

from lexic.exceptions import UnsupportedConstructError
from lexic.ir.action import IrAction
from lexic.ir.nodes import IrCollection, IrNode


@dataclass(frozen=True, slots=True)
class _NewIrDispatch(IrCollection["IrAction"], ABC):
    """Action-driven IR walker. Temporary name; renamed to ``IrDispatch`` in Step 4.

    Frozen-slotted dataclass, hashable by ``(actions, pre_recurse)``. Caches
    are ``init=False`` slot fields opted out of eq/hash/repr — implementation
    detail, not identity. Mutating dict contents inside a frozen slot is
    permitted; only rebinding the slot itself is blocked.
    """

    actions: tuple[IrAction, ...] = ()
    pre_recurse: Callable[[IrNode], object] | None = None
    _exact_table: dict[type, IrAction] = field(
        init=False, hash=False, compare=False, repr=False,
    )
    _resolve_cache: dict[type, IrAction | None] = field(
        init=False, hash=False, compare=False, repr=False,
    )
    _items_attr: ClassVar[str] = "actions"
    _SKIP_RECURSION: ClassVar[object] = object()

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "_exact_table",
            {a.target_type: a for a in self.actions},
        )
        object.__setattr__(self, "_resolve_cache", {})

    def _resolve(self, node_type: type) -> IrAction | None:
        """Concrete-first MRO walk; memoized; misses cached as None."""
        cache = self._resolve_cache
        if node_type in cache:
            return cache[node_type]
        for cls in node_type.__mro__:
            action = self._exact_table.get(cls)
            if action is not None:
                cache[node_type] = action
                return action
        cache[node_type] = None
        return None

    def __call__(self, node: IrNode) -> object:
        """Dispatch on ``node``: optional pre-recurse hook, then recurse children,
        then evaluate matched action or fall through to ``default()``."""
        if self.pre_recurse is not None and \
                self.pre_recurse(node) is self._SKIP_RECURSION:
            return self.default(node, ())
        new_children = tuple(self(c) for c in node.children())
        action = self._resolve(type(node))
        if action is not None:
            return action.eval(self, node, new_children)
        return self.default(node, new_children)

    @abstractmethod
    def default(self, node: IrNode, new_children: tuple) -> object:
        """Subclass fallthrough when no action matches."""
```

- [ ] **Step 4: Run dispatch-mro tests**

```
uv run pytest tests/unit/lexic/ir/test_dispatch_mro.py -v
```
Expected: PASS.

- [ ] **Step 5: Full suite still green (legacy IrDispatch untouched)**

```
uv run pytest tests/ -q
```

- [ ] **Step 6: Lint + commit**

```
tools/auto_fix.sh
uv run pylint src/lexic/ir/walk.py
git add src/lexic/ir/walk.py tests/unit/lexic/ir/test_dispatch_mro.py
git commit -m "ir/walk: add _NewIrDispatch (action-driven, MRO-resolved, IrNode, pre_recurse)"
```

### Task 2.2: Add presets `_NewIrTransformer` / `_NewIrVisitor` / `_NewIrEmitter`

**Files:**
- Modify: `src/lexic/ir/walk.py`
- Create: `tests/unit/lexic/ir/test_dispatch_presets.py`

- [ ] **Step 1: Failing tests**

```python
# tests/unit/lexic/ir/test_dispatch_presets.py
import pytest

from lexic.exceptions import UnsupportedConstructError
from lexic.ir.action import IrAction, IrCallable, IrText
from lexic.ir.nodes import IrItem, IrLiteral, IrSequence
from lexic.ir.walk import _NewIrEmitter, _NewIrTransformer, _NewIrVisitor


def test_transformer_identity_on_miss():
    t = _NewIrTransformer(actions=())
    node = IrSequence(items=(IrItem(atom=IrLiteral("a")),))
    assert t(node) == node


def test_transformer_rebuilds_on_changed_children():
    def _replace_with_y(d, n, nc):
        return IrLiteral("Y")
    t = _NewIrTransformer(actions=(IrAction(IrLiteral, IrCallable(_replace_with_y)),))
    result = t(IrItem(atom=IrLiteral("a")))
    assert isinstance(result, IrItem)
    assert result.atom == IrLiteral("Y")


def test_visitor_returns_none_on_miss():
    assert _NewIrVisitor(actions=())(IrLiteral("a")) is None


def test_emitter_empty_table_falls_through_to_str():
    e = _NewIrEmitter(actions=())
    assert e(IrLiteral("hello")) == str(IrLiteral("hello"))


def test_emitter_nonempty_table_raises_on_miss():
    e = _NewIrEmitter(actions=(IrAction(IrLiteral, IrText("X")),))
    with pytest.raises(UnsupportedConstructError):
        e(IrSequence(items=()))


def test_dispatch_repr_dumps_action_tree():
    """P13: repr(dispatcher) walks its action tree."""
    e = _NewIrEmitter(actions=(
        IrAction(IrLiteral, IrText("L")),
        IrAction(IrSequence, IrText("S")),
    ))
    r = repr(e)
    assert "ACTION" in r and "IrLiteral" in r and "IrSequence" in r and "TEXT('L')" in r
```

- [ ] **Step 2: Confirm failure**

- [ ] **Step 3: Implement**

```python
# Append to src/lexic/ir/walk.py
@dataclass(frozen=True, slots=True)
class _NewIrTransformer(_NewIrDispatch):
    """Rewrite preset: rebuild on changed children, else identity."""

    def default(self, node: IrNode, new_children: tuple) -> IrNode:
        old = node.children()
        if not old or all(nc is oc for nc, oc in zip(new_children, old)):
            return node
        return node.rebuild(new_children)


@dataclass(frozen=True, slots=True)
class _NewIrVisitor(_NewIrDispatch):
    """Side-effect preset: ``None`` on miss."""

    def default(self, node: IrNode, new_children: tuple) -> None:
        return None


@dataclass(frozen=True, slots=True)
class _NewIrEmitter(_NewIrDispatch):
    """String-emission preset.

    Default: ``str(node)`` when the actions table is empty
    (canonical-form fallthrough); raise :class:`UnsupportedConstructError`
    when non-empty (closed-world flavour saw an unknown type).
    """

    def default(self, node: IrNode, new_children: tuple) -> str:
        if not self.actions:
            return str(node)
        raise UnsupportedConstructError(
            f"{type(self).__name__}: no action for node type {type(node).__name__!r}",
        )
```

- [ ] **Step 4: Confirm pass; full suite; lint; commit**

```
git commit -m "ir/walk: add _NewIrTransformer / _NewIrVisitor / _NewIrEmitter presets"
```

---

## Step 3 — Migrate IR-internal closed-subclass passes onto the substrate

`_HoistTransformer`, `_RuleRefFinder` (both in `ir/derive.py`), and `_PatternAliasVisitor` (in `codegen/aliases.py`). Each becomes a factory function returning a loaded preset instance. Per-pass mutable state lives in closures (P17); short-circuit semantics use `pre_recurse` (P16).

### Task 3.1: Replace `_RuleRefFinder` with a factory using `pre_recurse` short-circuit

**Files:**
- Modify: `src/lexic/ir/derive.py`

- [ ] **Step 0: Inspect existing tests**

```
grep -rn "has_ruleref\|_RuleRefFinder" /home/mika/projects/lexic/tests/
```

- [ ] **Step 1: Add explicit short-circuit test**

```python
# Append to tests/unit/lexic/ir/test_derive.py (or test_init_derive.py per
# existing project convention — check which file exists)
from lexic.ir.derive import has_ruleref
from lexic.ir.nodes import IrItem, IrLiteral, IrRuleRef, IrSequence


def test_has_ruleref_true_for_simple_ref():
    assert has_ruleref(IrRuleRef("foo")) is True


def test_has_ruleref_false_for_pure_literal_tree():
    seq = IrSequence(items=(IrItem(atom=IrLiteral("x")),))
    assert has_ruleref(seq) is False


def test_has_ruleref_true_when_ref_buried_deep():
    seq = IrSequence(items=(IrItem(atom=IrRuleRef("y")),))
    assert has_ruleref(seq) is True
```

- [ ] **Step 2: Replace `_RuleRefFinder` with closure-state factory**

In `src/lexic/ir/derive.py`:

```python
# REMOVE the class _RuleRefFinder definition and the @cache has_ruleref body.
# REPLACE with:

from functools import cache

from lexic.ir.action import IrAction, IrCallable
from lexic.ir.walk import _NewIrVisitor    # renamed to IrVisitor in Step 4


@cache
def has_ruleref(node: IrNode) -> bool:
    """Return True iff ``node`` contains any :class:`IrRuleRef`.

    Short-circuit: once an IrRuleRef is seen, ``pre_recurse`` blocks
    further descent for the remainder of the walk.

    :param node: Any IR node.
    :returns: True if at least one IrRuleRef appears in the subtree.
    """
    state = [False]

    def _set_found(_d, _node, _nc):
        state[0] = True
        return None

    def _pre(_node):
        return _NewIrVisitor._SKIP_RECURSION if state[0] else None

    visitor = _NewIrVisitor(
        actions=(IrAction(IrRuleRef, IrCallable(_set_found)),),
        pre_recurse=_pre,
    )
    visitor(node)
    return state[0]
```

Delete `class _RuleRefFinder(IrVisitor): ...` entirely.

- [ ] **Step 3: Full suite green**

```
uv run pytest tests/ -q
```

- [ ] **Step 4: Lint + commit**

```
tools/auto_fix.sh
git add -p
git commit -m "ir/derive: convert _RuleRefFinder to factory (closure state + pre_recurse short-circuit)"
```

### Task 3.2: Replace `_HoistTransformer` with a closure-state factory

**Files:**
- Modify: `src/lexic/ir/derive.py`

- [ ] **Step 0: Inspect existing tests**

```
grep -rn "hoist_helpers\|_HoistTransformer" /home/mika/projects/lexic/tests/
```

- [ ] **Step 1: Replace**

```python
# In src/lexic/ir/derive.py — REPLACE class _HoistTransformer and the body of
# hoist_helpers:

from lexic.ir.walk import _NewIrTransformer    # renamed to IrTransformer in Step 4


def _make_hoist_item_handler(
    parent_name: str,
    name_set: set[str],
    helpers: list[IrRule],
):
    """Build the IrCallable handler closed over per-rule allocation state.

    :param parent_name: The rule name whose body is being walked.
    :param name_set: Mutable set of all rule names; updated when a helper
        is allocated to keep future allocations collision-free.
    :param helpers: Mutable list onto which freshly-built helper rules are
        appended; the caller drains this after the walk.
    :returns: A callable suitable for use as an :class:`IrCallable` body.
    """

    def _handle(dispatch, node: IrItem, new_children: tuple) -> IrItem:
        # new_children mirrors node.children(); for IrItem that's (atom, quantifier)
        # per IrComposite. Post-recursion: the atom has already been walked.
        new_atom = new_children[0]
        new_quant = new_children[1] if len(new_children) > 1 else node.quantifier
        if not isinstance(new_atom, IrGroup):
            if new_atom is node.atom:
                return node
            return IrItem(atom=new_atom, quantifier=new_quant)
        is_quantified = new_quant != Quantifier(1, 1)
        if is_quantified and has_ruleref(new_atom.body):
            helper_name = _reserve_helper_name(parent_name, name_set)
            name_set.add(helper_name)
            helpers.append(IrRule(name=helper_name, body=new_atom.body))
            return IrItem(atom=IrRuleRef(name=helper_name), quantifier=new_quant)
        return IrItem(atom=new_atom, quantifier=new_quant)

    return _handle


def hoist_helpers(ast: IrAst) -> tuple[IrAst, list[IrRule]]:
    """Rewrite quantified groups containing rulerefs into synthetic rules.

    :param ast: The IR AST to rewrite.
    :returns: ``(new_ast, helper_rules)``.
    """
    name_set: set[str] = {r.name for r in ast.rules}
    helpers: list[IrRule] = []
    new_rules: list[IrRule] = []
    for rule in ast.rules:
        handler = _make_hoist_item_handler(rule.name, name_set, helpers)
        transformer = _NewIrTransformer(
            actions=(IrAction(IrItem, IrCallable(handler)),),
        )
        new_body = transformer(rule.body)
        new_rules.append(IrRule(rule.name, new_body))
    return IrAst(rules=tuple(new_rules), start=ast.start), helpers
```

Delete `class _HoistTransformer(IrTransformer): ...` entirely.

- [ ] **Step 2: Full suite green; lint; commit**

```
uv run pytest tests/ -q
tools/auto_fix.sh
git add -p
git commit -m "ir/derive: convert _HoistTransformer to factory (closure state)"
```

### Task 3.3: Replace `_PatternAliasVisitor` with a closure-state factory using `pre_recurse`

The original visitor (codegen/aliases.py:111-160) uses `self.generic_visit(node)` inside `visit_IrItem` to bracket recursion through IrGroup atoms. New design:

- `pre_recurse` pushes a frame stack entry on each IrGroup (before its body is recursed into).
- An IrAction on `IrRuleRef` flips the topmost frame entry.
- An IrAction on `IrItem` pops the frame after auto-recursion and records the alias (or propagates dirty to parent frame).

Per P17, all mutable state lives in a closure-captured object.

**Files:**
- Modify: `src/lexic/codegen/aliases.py`

- [ ] **Step 0: Inspect existing tests**

```
grep -rn "collect_aliases\|PatternAlias\|_PatternAliasVisitor" /home/mika/projects/lexic/tests/
```

- [ ] **Step 1: Replace the class with a factory**

```python
# In src/lexic/codegen/aliases.py — REPLACE class _PatternAliasVisitor and the
# collect_aliases body with:

from collections import Counter
from types import SimpleNamespace

from lexic.ir.action import IrAction, IrCallable
from lexic.ir.walk import _NewIrVisitor    # renamed to IrVisitor in Step 4


def _record_alias(state, regex: str, base: str) -> None:
    """Insert a unique alias into ``state.aliases`` with numeric-suffix dedup."""
    if any(a.regex == regex for a in state.aliases.values()):
        return
    state.name_counts[base] += 1
    suffix = "" if state.name_counts[base] == 1 else str(state.name_counts[base])
    state.aliases[regex] = PatternAlias(name=f"{base}{suffix}", regex=regex)


def _make_alias_visitor():
    """Construct the closure-captured state + the loaded visitor.

    :returns: ``(state, visitor)`` — the caller runs ``visitor`` over each
        rule body, then reads ``state.aliases`` for results.
    """
    state = SimpleNamespace(
        aliases={},
        name_counts=Counter(),
        ruleref_frames=[False],
    )

    def _pre_recurse(node):
        if isinstance(node, IrGroup):
            state.ruleref_frames.append(False)
        return None

    def _on_ruleref(_d, _node, _nc):
        state.ruleref_frames[-1] = True
        return None

    def _on_item(_d, node, _nc):
        atom, q = node.atom, node.quantifier
        if isinstance(atom, IrGroup):
            had_ruleref = state.ruleref_frames.pop()
            if had_ruleref:
                state.ruleref_frames[-1] = True
            else:
                _record_alias(state, regex_for_group(atom, q), "Pattern")
            return None
        if isinstance(atom, IrCharClass):
            _record_alias(
                state,
                regex_for_charclass(atom, q),
                _name_for_charclass(atom) or "Pattern",
            )
        return None

    visitor = _NewIrVisitor(
        actions=(
            IrAction(IrRuleRef, IrCallable(_on_ruleref)),
            IrAction(IrItem,    IrCallable(_on_item)),
        ),
        pre_recurse=_pre_recurse,
    )
    return state, visitor


def collect_aliases(specs: list[RuleSpec]) -> list[PatternAlias]:
    """Walk all rule bodies; collect pattern aliases for module-level hoisting.

    :param specs: The full list of rule specs from ``derive_specs``.
    :returns: Ordered list of pattern aliases (insertion order preserved).
    """
    state, visitor = _make_alias_visitor()
    for spec in specs:
        for item in spec.items:
            visitor(item)
    return list(state.aliases.values())
```

Delete `class _PatternAliasVisitor(IrVisitor): ...` entirely.

**Recursion-order trace** (sanity check the conversion):

1. `visitor(item)` enters. `pre_recurse(item)` — not an IrGroup, no-op. Recurse into children (`atom`, `quantifier`).
2. Recursion enters `atom` (which is an `IrGroup`). `pre_recurse(group)` pushes `False`. Recurse into the group's children (`body`).
3. Recursion reaches an `IrRuleRef` deep in the body. The `_on_ruleref` action fires, setting `frames[-1] = True`.
4. Recursion unwinds back to the `IrGroup` level. No action on `IrGroup`; falls through to `default()` returning None.
5. Recursion unwinds back to the `IrItem` level. The `_on_item` action fires. It sees `atom` is an `IrGroup`, pops the frame (which is `True`), and propagates dirty to `frames[-1]`. No alias recorded.

If the group had been pure-literal, step 3 never fires, the frame stays `False`, and `_on_item` records an alias via `regex_for_group(atom, q)`. Matches the original semantics.

- [ ] **Step 2: Full suite green; lint; commit**

```
uv run pytest tests/ -q
tools/auto_fix.sh
git add -p
git commit -m "codegen/aliases: convert _PatternAliasVisitor to closure-state factory (pre_recurse bracketing)"
```

---

## Step 4 — Delete legacy `IrDispatch` machinery; rename `_New*` → `Ir*`

Every closed-subclass dispatcher consumer is now migrated. The legacy classes, registries, and entry points in `walk.py` are unreferenced.

### Task 4.1: Delete legacy machinery

**Files:**
- Modify: `src/lexic/ir/walk.py`

- [ ] **Step 1: Confirm no remaining consumers**

```
grep -rn "_CHILDREN\|_REBUILD\|_DUMP\|generic_visit\|visit_Ir" /home/mika/projects/lexic/src/
```
Expected: only references inside `walk.py` itself.

Also check explicitly:
```
grep -rn "from lexic.ir.walk import IrDispatch\|from lexic.ir.walk import IrVisitor\|from lexic.ir.walk import IrTransformer\|from lexic.ir.walk import dump" /home/mika/projects/lexic/src/
```
Expected: at most references the migrations already updated (they should now reference `_NewIr*` names).

- [ ] **Step 2: Delete from `src/lexic/ir/walk.py`**

Remove:
- `_CHILDREN`, `_REBUILD`, `_DUMP` module-level dicts.
- The original `class IrDispatch` (the one with `visit()` / `generic_visit()` / `_combine()` / `action: dict[type, ...]`).
- The original `class IrVisitor`.
- The original `class IrTransformer`.
- The `def dump(...)` top-level function.

- [ ] **Step 3: Full suite green**

```
uv run pytest tests/ -q
```

- [ ] **Step 4: Commit**

```
git add src/lexic/ir/walk.py
git commit -m "ir/walk: delete legacy IrDispatch / IrVisitor / IrTransformer / _CHILDREN / _REBUILD / _DUMP / dump()"
```

### Task 4.2: Rename `_NewIr*` → `Ir*`

**Files:**
- Modify: `src/lexic/ir/walk.py`
- Modify: `src/lexic/ir/derive.py`
- Modify: `src/lexic/codegen/aliases.py`
- Modify: `tests/unit/lexic/ir/test_dispatch_mro.py`
- Modify: `tests/unit/lexic/ir/test_dispatch_presets.py`

- [ ] **Step 1: Global rename**

```
git grep -l "_NewIrDispatch\|_NewIrTransformer\|_NewIrVisitor\|_NewIrEmitter" src/ tests/ \
  | xargs sed -i \
    -e 's/_NewIrDispatch/IrDispatch/g' \
    -e 's/_NewIrTransformer/IrTransformer/g' \
    -e 's/_NewIrVisitor/IrVisitor/g' \
    -e 's/_NewIrEmitter/IrEmitter/g'
```

Confirm no false hits:

```
git diff --stat
```

- [ ] **Step 2: Full suite green**

```
uv run pytest tests/ -q
```

- [ ] **Step 3: Update `src/lexic/ir/__init__.py`**

Confirm re-exports: `IrDispatch`, `IrTransformer`, `IrVisitor`, `IrEmitter`, `IrAction`, plus the seven `IrOp` variants. Remove any leftover `dump` re-export.

- [ ] **Step 4: Lint + commit**

```
tools/auto_fix.sh
git add -p
git commit -m "ir/walk: rename _NewIr* → Ir* (substrate is now the only dispatch)"
```

---

## Step 5 — `Flavour` becomes an `IrEmitter` (atomic group)

This step couples three sub-tasks (Flavour ABC + render_specs + GBNF migration + ABNF migration). Intermediate states break the suite because `to_gbnf()` callers depend on either-old-or-new. The atomic group commits each sub-task as a separate commit but runs the suite ONLY at the end of 5.4.

### Task 5.1: Refactor `Flavour` ABC

**Files:**
- Modify: `src/lexic/grammars/flavour.py`
- Create: `tests/unit/lexic/grammars/test_flavour.py`

- [ ] **Step 1: Failing tests**

```python
# tests/unit/lexic/grammars/test_flavour.py
from abc import ABC

from lexic.grammars.flavour import Flavour
from lexic.ir.walk import IrEmitter


def test_flavour_is_iremitter_subclass():
    assert issubclass(Flavour, IrEmitter)


def test_flavour_classvar_metadata_present():
    assert "name" in Flavour.__annotations__
    assert "extensions" in Flavour.__annotations__
    assert "meta_grammar" in Flavour.__annotations__
    assert "escapes" in Flavour.__annotations__
    assert "line_comment" in Flavour.__annotations__
    assert "quantifier_symbols" in Flavour.__annotations__


def test_flavour_has_no_pre_parse_check():
    """pre_parse_check is deferred per scope §2; the hook does not exist."""
    assert not hasattr(Flavour, "pre_parse_check")
```

- [ ] **Step 2: Implement**

```python
# src/lexic/grammars/flavour.py — full replacement of the Flavour ABC
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

from lexic.ir.walk import IrEmitter

if TYPE_CHECKING:
    from lexic.ir.escapes import EscapeCodec
    from lexic.ir.nodes import IrQuantifier


@dataclass(frozen=True, slots=True)
class Flavour(IrEmitter, ABC):
    """Grammar flavour ABC. Concrete subclasses declare metadata as ClassVars
    and provide parse-side static methods. The instance's IR-tree shape is
    the action tuple inherited from :class:`IrEmitter`.

    Concrete flavours are module-level singletons.
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
        """Parse a flavour-specific quantifier token."""

    @staticmethod
    @abstractmethod
    def parse_charclass(text: str) -> tuple[str, bool]:
        """Parse a flavour-specific char-class token; return (pattern, negated)."""
```

- [ ] **Step 3: Defer test run to end of Step 5.4**

- [ ] **Step 4: Commit (suite NOT yet rerun)**

```
git add src/lexic/grammars/flavour.py tests/unit/lexic/grammars/test_flavour.py
git commit -m "grammars/flavour: Flavour(IrEmitter, ABC) ClassVar metadata; no pre_parse_check"
```

### Task 5.2: Add `render_specs` to `ir/emit.py`

**Files:**
- Modify: `src/lexic/ir/emit.py`

- [ ] **Step 1: Parity check against existing `GbnfEmitter.emit_spec` (B6 verification)**

Read the existing emitter to understand exactly what `to_gbnf()` produced for each spec kind:

```
cat src/lexic/grammars/gbnf/emitter.py
```

Document (as a comment block at the top of `_spec_to_irrule`) the parity behaviour:
- `value_str` single-arm: emit body as `IrSequence(items=spec.items)` wrapped in `IrAlternation`.
- `value_str` multi-arm: emit `spec.items[0]` (already an `IrAlternation`).
- `sequence`: emit `IrSequence(items=spec.items)` wrapped in `IrAlternation`.
- `alternation`: emit `IrAlternation(arms=tuple(IrSequence(items=(it,)) for it in spec.items))` — arm names per `arm_names`-built `IrRuleRef`s. Arm bodies are not inlined (they live in sibling specs).

If the existing GbnfEmitter's `emit_spec` produces something different for any of these (e.g. inlines arm bodies for alternation), update `_spec_to_irrule` to match.

- [ ] **Step 2: Implement**

```python
# src/lexic/ir/emit.py
"""Top-level grammar emission entry point.

:func:`render_specs` composes per-rule rendering via a flavour's
:meth:`IrEmitter.__call__`; thin orchestration around the substrate.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from lexic.exceptions import UnsupportedConstructError
from lexic.ir.nodes import IrAlternation, IrItem, IrRule, IrSequence

if TYPE_CHECKING:
    from lexic.grammars.flavour import Flavour
    from lexic.ir.spec import RuleSpec


def render_specs(specs: list[RuleSpec], flavour: Flavour) -> str:
    """Render a list of specs into grammar text using ``flavour``.

    :param specs: The list of rule specs from ``derive_specs``.
    :param flavour: The target flavour singleton (e.g. ``GBNF`` or ``ABNF``).
    :returns: Grammar source text in the flavour's surface syntax.
    """
    parts = [flavour(_spec_to_irrule(spec)) for spec in specs]
    return "\n".join(parts) + "\n"


def _spec_to_irrule(spec: RuleSpec) -> IrRule:
    """Inverse of :func:`derive._build_*`: spec → :class:`IrRule` for re-emission.

    For alternation-kind specs, arms are rendered as ruleref names per the
    arm_names in derive._build_alternation; original arm bodies live in
    sibling specs and are emitted alongside in the surrounding render_specs
    loop.
    """
    if spec.kind == "alternation":
        arms = tuple(IrSequence(items=(it,)) for it in spec.items)
        body = IrAlternation(arms=arms)
    elif spec.kind in {"sequence", "value_str"}:
        if spec.items and isinstance(spec.items[0], IrAlternation):
            body = spec.items[0]
        else:
            body = IrAlternation(arms=(IrSequence(items=tuple(spec.items)),))
    else:
        raise UnsupportedConstructError(f"unknown spec kind: {spec.kind!r}")
    return IrRule(name=spec.rule_name, body=body)
```

- [ ] **Step 3: Defer test run to end of Step 5.4; commit**

```
git add src/lexic/ir/emit.py
git commit -m "ir/emit: add render_specs(specs, flavour) thin shell"
```

### Task 5.3: Migrate `GbnfFlavour` onto the substrate

**Files:**
- Modify: `src/lexic/grammars/gbnf/flavour.py`
- Delete: `src/lexic/grammars/gbnf/emitter.py`
- Delete: `tests/unit/lexic/grammars/gbnf/test_emitter.py`
- Modify: `src/lexic/grammars/__init__.py`

- [ ] **Step 1: Read existing emitter for parity**

```
cat src/lexic/grammars/gbnf/emitter.py
```

Identify every per-type emit branch as the source of truth.

- [ ] **Step 2: Define handlers + action tuple + singleton**

```python
# src/lexic/grammars/gbnf/flavour.py — full replacement
from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from lexic.grammars.flavour import Flavour
from lexic.grammars.gbnf.escapes import GbnfEscapes
from lexic.grammars.gbnf.meta_grammar import GBNF_META_GRAMMAR
from lexic.ir.action import IrAction, IrCallable, IrField, IrJoin, IrRecurse, IrSeq, IrText
from lexic.ir.nodes import (
    IrAlternation, IrAst, IrCharClass, IrGroup, IrItem, IrLiteral,
    IrQuantifier, IrRule, IrRuleRef, IrSequence,
)


def _gbnf_literal(_d, node, _nc) -> str:
    return f'"{GbnfEscapes.encode(node.value)}"'


def _gbnf_charclass(_d, node, _nc) -> str:
    return f"[{'^' if node.negated else ''}{node.pattern}]"


def _gbnf_quantifier(_d, node, _nc) -> str:
    key = (node.min, node.max)
    if key in GbnfFlavour.quantifier_symbols:
        return GbnfFlavour.quantifier_symbols[key]
    if node.min == node.max:
        return f"{{{node.min}}}"
    if node.max is None:
        return f"{{{node.min},}}"
    return f"{{{node.min},{node.max}}}"


def _gbnf_ast(dispatch, node, _nc) -> str:
    return "\n".join(dispatch(r) for r in node.rules) + "\n"


_GBNF_ACTIONS = (
    IrAction(IrLiteral,     IrCallable(_gbnf_literal)),
    IrAction(IrCharClass,   IrCallable(_gbnf_charclass)),
    IrAction(IrRuleRef,     IrField("name")),
    IrAction(IrGroup,       IrSeq(parts=(IrText("("), IrRecurse("body"), IrText(")")))),
    IrAction(IrQuantifier,  IrCallable(_gbnf_quantifier)),
    IrAction(IrItem,        IrSeq(parts=(IrRecurse("atom"), IrRecurse("quantifier")))),
    IrAction(IrSequence,    IrJoin("items", IrText(" "), IrText('""'))),
    IrAction(IrAlternation, IrJoin("arms", IrText(" | "), IrText(""))),
    IrAction(IrRule,        IrSeq(parts=(IrField("name"), IrText(" ::= "), IrRecurse("body")))),
    IrAction(IrAst,         IrCallable(_gbnf_ast)),
)


@dataclass(frozen=True, slots=True)
class GbnfFlavour(Flavour):
    """GBNF flavour. Module-level ``GBNF`` singleton is the only instance."""

    name: ClassVar[str] = "gbnf"
    extensions: ClassVar[tuple[str, ...]] = (".gbnf",)
    meta_grammar: ClassVar[str] = GBNF_META_GRAMMAR
    escapes: ClassVar = GbnfEscapes
    line_comment: ClassVar[str] = "#"
    quantifier_symbols: ClassVar = {
        (1, 1): "", (0, 1): "?", (0, None): "*", (1, None): "+",
    }

    @staticmethod
    def parse_quantifier(text: str) -> IrQuantifier:
        """Parse a GBNF quantifier token (`?`, `*`, `+`, `{n}`, `{n,}`, `{n,m}`)."""
        # LIFT verbatim from the existing src/lexic/grammars/gbnf/flavour.py
        # parse_quantifier body — no change.
        ...

    @staticmethod
    def parse_charclass(text: str) -> tuple[str, bool]:
        """Parse a GBNF char-class token; return (pattern, negated)."""
        # LIFT verbatim from existing parse_charclass body.
        ...


GBNF = GbnfFlavour(actions=_GBNF_ACTIONS)
```

- [ ] **Step 3: Delete `grammars/gbnf/emitter.py` and its test**

```
git rm src/lexic/grammars/gbnf/emitter.py tests/unit/lexic/grammars/gbnf/test_emitter.py
```

- [ ] **Step 4: Update `grammars/__init__.py` to re-export `GBNF`**

```python
# Additions:
from lexic.grammars.gbnf.flavour import GBNF, GbnfFlavour

__all__ = [..., "GBNF", "GbnfFlavour"]
```

- [ ] **Step 5: Defer test run to end of Step 5.4; commit**

```
git add -p
git commit -m "grammars/gbnf: action-tuple flavour; GBNF singleton; delete emitter.py"
```

### Task 5.4: Migrate `AbnfFlavour` and run the suite

**Files:**
- Modify: `src/lexic/grammars/abnf/flavour.py`
- Delete: `src/lexic/grammars/abnf/emitter.py`
- Delete: `tests/unit/lexic/grammars/abnf/test_emitter.py`
- Modify: `src/lexic/grammars/__init__.py`

- [ ] **Step 1: Read existing emitter**

```
cat src/lexic/grammars/abnf/emitter.py
```

ABNF differs from GBNF in:
- Quantifier placement: **prefix** (quantifier before atom on `IrItem`).
- Quantifier symbols + `{n,m}` form.
- Alternation separator: `/` not `|`.
- Rule head: `=` not `::=`.
- Char-class delimiters / escape codec.

- [ ] **Step 2: Define handlers + action tuple + singleton**

```python
# src/lexic/grammars/abnf/flavour.py — full replacement
from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from lexic.grammars.flavour import Flavour
from lexic.grammars.abnf.escapes import AbnfEscapes
from lexic.grammars.abnf.meta_grammar import ABNF_META_GRAMMAR
from lexic.ir.action import IrAction, IrCallable, IrField, IrJoin, IrRecurse, IrSeq, IrText
from lexic.ir.nodes import (
    IrAlternation, IrAst, IrCharClass, IrGroup, IrItem, IrLiteral,
    IrQuantifier, IrRule, IrRuleRef, IrSequence,
)


def _abnf_literal(_d, node, _nc) -> str:
    # LIFT body from existing src/lexic/grammars/abnf/emitter.py for IrLiteral.
    ...


def _abnf_charclass(_d, node, _nc) -> str:
    # LIFT body from existing emitter for IrCharClass.
    ...


def _abnf_quantifier(_d, node, _nc) -> str:
    """Emit an ABNF prefix quantifier."""
    # LIFT from existing emitter.format_quantifier — preserve prefix syntax.
    ...


def _abnf_ast(dispatch, node, _nc) -> str:
    return "\n".join(dispatch(r) for r in node.rules) + "\n"


_ABNF_ACTIONS = (
    IrAction(IrLiteral,     IrCallable(_abnf_literal)),
    IrAction(IrCharClass,   IrCallable(_abnf_charclass)),
    IrAction(IrRuleRef,     IrField("name")),
    IrAction(IrGroup,       IrSeq(parts=(IrText("("), IrRecurse("body"), IrText(")")))),
    IrAction(IrQuantifier,  IrCallable(_abnf_quantifier)),
    # PREFIX: quantifier before atom.
    IrAction(IrItem,        IrSeq(parts=(IrRecurse("quantifier"), IrRecurse("atom")))),
    IrAction(IrSequence,    IrJoin("items", IrText(" "), IrText('""'))),
    IrAction(IrAlternation, IrJoin("arms", IrText(" / "), IrText(""))),
    IrAction(IrRule,        IrSeq(parts=(IrField("name"), IrText(" = "), IrRecurse("body")))),
    IrAction(IrAst,         IrCallable(_abnf_ast)),
)


@dataclass(frozen=True, slots=True)
class AbnfFlavour(Flavour):
    name: ClassVar[str] = "abnf"
    extensions: ClassVar[tuple[str, ...]] = (".abnf",)
    meta_grammar: ClassVar[str] = ABNF_META_GRAMMAR
    escapes: ClassVar = AbnfEscapes
    line_comment: ClassVar[str] = ";"
    quantifier_symbols: ClassVar = {
        # LIFT from existing AbnfFlavour.
        ...
    }

    @staticmethod
    def parse_quantifier(text: str) -> IrQuantifier: ...   # LIFT
    @staticmethod
    def parse_charclass(text: str) -> tuple[str, bool]: ...  # LIFT


ABNF = AbnfFlavour(actions=_ABNF_ACTIONS)
```

- [ ] **Step 3: Delete `grammars/abnf/emitter.py` and its test; update `grammars/__init__.py` to re-export `ABNF`**

- [ ] **Step 4: Full suite — Steps 5.1-5.4 commit individually but run the suite together here**

```
uv run pytest tests/ -q
```
Expected: PASS.

If failures: most likely `to_gbnf()` / `to_abnf()` round-trip mismatches between the new and old emit paths. Inspect the failing test's expected output and adjust the relevant action body until parity. **Do not commit a broken state — bisect across Tasks 5.1-5.4 with `git rebase -i` if needed to keep history clean.**

- [ ] **Step 5: Lint + commit**

```
tools/auto_fix.sh
git add -p
git commit -m "grammars/abnf: action-tuple flavour; ABNF singleton; delete emitter.py"
```

---

## Step 6 — Rename `Quantifier` → `IrQuantifier`

Mechanical rename across every file.

### Task 6.1: Rename in source + tests

**Files:**
- Modify: `src/lexic/ir/nodes.py`
- Modify: `src/lexic/ir/derive.py`
- Modify: `src/lexic/ir/__init__.py`
- Modify: `src/lexic/codegen/aliases.py`
- Modify: `src/lexic/codegen/model_emitter.py`
- Modify: `src/lexic/generate.py`
- Modify: `src/lexic/parsing/meta_parser.py`
- Modify: `src/lexic/parsing/transformer/build_transformer.py`
- Modify: `src/lexic/parsing/lark_builder.py`
- Modify: `src/lexic/grammars/gbnf/flavour.py`
- Modify: `src/lexic/grammars/abnf/flavour.py`
- Modify: `src/lexic/grammars/flavour.py`
- Modify: `src/lexic/utils/quantifiers.py` (deleted in Step 7.2; rename for interim)
- Modify: tests under `tests/`

- [ ] **Step 1: Rename, excluding docs and wiki**

```
git grep -l "\bQuantifier\b" src/ tests/ | xargs sed -i 's/\bQuantifier\b/IrQuantifier/g'
```

Sanity check no false positives in docstrings:

```
git diff | grep -E "^[+-].*[Qq]uantifier" | head -80
```

Verify the diff is purely class-name renames (no string-literal or docstring damage).

- [ ] **Step 2: Full suite green**

```
uv run pytest tests/ -q
```

- [ ] **Step 3: Lint + commit**

```
tools/auto_fix.sh
git add -p
git commit -m "ir: rename Quantifier → IrQuantifier"
```

---

## Step 7 — Migrate consumers; delete `utils/quantifiers.py`

### Task 7.1: Migrate `base.py` to use the `GBNF` singleton; verify B6 parity

**Files:**
- Modify: `src/lexic/base.py`

- [ ] **Step 1: Read existing `to_gbnf` + the deleted emitter's `emit_spec`**

The existing `to_gbnf` in `base.py` calls `GbnfEmitter().emit_spec(self.__grammar__)`. The deleted `emitter.py` (history reachable via `git show HEAD~N:src/lexic/grammars/gbnf/emitter.py`) had a specific `emit_spec` implementation. Check that `render_specs([self.__grammar__], GBNF)` produces byte-identical output.

```
uv run pytest tests/integration/test_full_round_trip.py -v
```

Read failing assertions, if any, to understand the byte-level difference.

- [ ] **Step 2: Replace the import + body**

```python
# In src/lexic/base.py:
# REMOVE:  from lexic.grammars.gbnf.emitter import GbnfEmitter
# ADD:
from lexic.grammars.gbnf.flavour import GBNF
from lexic.ir.emit import render_specs


def to_gbnf(self) -> str:
    """Render this model's :class:`RuleSpec` as GBNF source text.

    :returns: GBNF source for this rule.
    """
    return render_specs([self.__grammar__], GBNF)
```

If `to_gbnf()` historically emitted *only* the single rule (no trailing newline, no spec-list framing) and `render_specs` doesn't match: either adjust `render_specs` to be the spec-list entry while exposing a lower-level `flavour(spec_to_irrule(spec))` shape for single-rule rendering, or wrap inline:

```python
from lexic.ir.emit import _spec_to_irrule

def to_gbnf(self) -> str:
    return GBNF(_spec_to_irrule(self.__grammar__))
```

The second option preserves byte parity exactly.

- [ ] **Step 3: Run integration tests**

```
uv run pytest tests/integration/test_full_round_trip.py -v
```
Expected: PASS.

- [ ] **Step 4: Full suite green; lint; commit**

```
uv run pytest tests/ -q
tools/auto_fix.sh
git add -p
git commit -m "base: to_gbnf flips from GbnfEmitter to GBNF singleton"
```

### Task 7.2: Inline `utils/quantifiers.py` into `lark_builder.py`; delete the module

**Files:**
- Modify: `src/lexic/parsing/lark_builder.py`
- Delete: `src/lexic/utils/quantifiers.py`
- Modify: `tests/unit/lexic/utils/test_quantifiers.py` → re-home

- [ ] **Step 1: Identify remaining callers**

```
grep -rn "utils.quantifiers\|quantifier_to_bounds\|bounds_to_quantifier" /home/mika/projects/lexic/src/ /home/mika/projects/lexic/tests/
```

Expected after Steps 5-6: only `parsing/lark_builder.py` and the test file `tests/unit/lexic/utils/test_quantifiers.py`.

- [ ] **Step 2: Move the helpers**

Copy `bounds_to_quantifier` and `quantifier_to_bounds` (or whatever the exact function names are; verify by reading `utils/quantifiers.py`) into `parsing/lark_builder.py` as module-level helpers (rename to `_bounds_to_quantifier` / `_quantifier_to_bounds` since they're now internal).

Update all references in `lark_builder.py`.

- [ ] **Step 3: Re-home the tests**

Move tests from `tests/unit/lexic/utils/test_quantifiers.py` into `tests/unit/lexic/parsing/test_lark_builder.py`. Adjust imports. Don't lose coverage.

```
git mv tests/unit/lexic/utils/test_quantifiers.py tests/unit/lexic/parsing/test_lark_builder_quantifiers.py
```

Or merge into an existing `test_lark_builder.py` if one exists.

- [ ] **Step 4: Delete `utils/quantifiers.py`**

```
git rm src/lexic/utils/quantifiers.py
```

Verify no remaining import:

```
grep -rn "utils.quantifiers" /home/mika/projects/lexic/
```

- [ ] **Step 5: Full suite green; lint; commit**

```
uv run pytest tests/ -q
tools/auto_fix.sh
git add -p
git commit -m "utils/quantifiers: delete (inlined into parsing/lark_builder.py; tests re-homed)"
```

---

## Step 8 — Opportunistic cleanup

### Task 8.1: Delete `ir/helpers.py` if zero callers

**Files:**
- Delete: `src/lexic/ir/helpers.py`
- Delete: `tests/unit/lexic/ir/test_helpers.py`
- Modify: `src/lexic/ir/__init__.py`

- [ ] **Step 1: Confirm zero callers**

```
grep -rn "HelperRuleRegistry\|ir.helpers\|from lexic.ir import HelperRuleRegistry" /home/mika/projects/lexic/src/
```

If anything turns up: **skip this task** (deferred §9 explicit allowance).

- [ ] **Step 2: Delete**

```
git rm src/lexic/ir/helpers.py tests/unit/lexic/ir/test_helpers.py
```

Remove the export from `ir/__init__.py`.

- [ ] **Step 3: Full suite green; lint; commit**

```
uv run pytest tests/ -q
tools/auto_fix.sh
git add -p
git commit -m "ir: delete unused HelperRuleRegistry"
```

---

## Step 9 — Wiki + docs + CLAUDE.md

### Task 9.1: Update CLAUDE.md "two deliberate exceptions"

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Locate the existing wording**

```
grep -n "two deliberate exceptions\|gbnf.emitter" /home/mika/projects/lexic/CLAUDE.md
```

- [ ] **Step 2: Update**

```markdown
**The two deliberate exceptions:**
1. `base.py` imports the `GBNF` singleton from `lexic.grammars.gbnf.flavour` at module scope for `to_gbnf()`. Explicit, eager, one import.
2. `compile.py` imports `codegen` from `lexic.codegen` and `build_lark` from `lexic.parsing.lark_builder`. Both explicit and public. This is the single runtime seam for compilation.
```

- [ ] **Step 3: Commit**

```
git add CLAUDE.md
git commit -m "CLAUDE.md: runtime→codegen exception #1 retargets to GBNF singleton"
```

### Task 9.2: Update wiki pages

**Files:**
- Modify: `.wiki/lexic/architecture.md`
- Modify: `.wiki/lexic/flavour-system.md`
- Modify: `.wiki/lexic/ir-shapes.md`
- Modify: `.wiki/lexic/decisions.md`
- Modify: `.wiki/lexic/log.md`
- Modify: `.wiki/lexic/slice-b-status.md`

- [ ] **Step 1: `architecture.md`** — substrate (IrAction/IrOp), IR-pass-by-action-table, "IR describes the IR."

- [ ] **Step 2: `flavour-system.md`** — Flavour-as-IrEmitter; singleton convention; action-tuple shape.

- [ ] **Step 3: `ir-shapes.md`** — add `IrQuantifier`; add `IrAction`; add seven `IrOp` variants.

- [ ] **Step 4: `decisions.md`** — append entries for P13, P14, P15, P16, P17 (each one paragraph; refer to spec for full text).

- [ ] **Step 5: `log.md`** — slice-landing entry (date, summary).

- [ ] **Step 6: `slice-b-status.md`** — mark slice closed; reference deferred-work spec for what remains.

- [ ] **Step 7: Commit**

```
git add .wiki/lexic/
git commit -m "wiki: substrate, Flavour-as-IrEmitter, slice-B closure"
```

---

## Final verification

- [ ] **Full suite**

```
uv run pytest tests/ -q
```

- [ ] **Lint clean**

```
uv run ruff check src/ tests/
```

- [ ] **Pylint pass on every modified module**

```
uv run pylint \
  src/lexic/ir/action.py \
  src/lexic/ir/walk.py \
  src/lexic/ir/derive.py \
  src/lexic/ir/emit.py \
  src/lexic/grammars/flavour.py \
  src/lexic/grammars/gbnf/flavour.py \
  src/lexic/grammars/abnf/flavour.py \
  src/lexic/codegen/aliases.py \
  src/lexic/base.py
```

- [ ] **Round-trip integration**

```
uv run pytest tests/integration/test_full_round_trip.py -v
```

- [ ] **`repr(GBNF)` smoke**

```
uv run python -c "from lexic.grammars.gbnf.flavour import GBNF; print(repr(GBNF))"
```
Expected: multi-line tree showing each `IrAction` with target_type and body.

- [ ] **Anti-creep grep**

```
grep -rn "pre_parse_check\|grammars/lark\|LarkFlavour\|_check_no_positional_token_syntax" src/ tests/
```
Expected: zero hits.

- [ ] **`_NewIr` leftover grep**

```
grep -rn "_NewIr" src/ tests/
```
Expected: zero hits.

---

## Risk-area mitigations (reminders)

- **Step 2.1 (`IrDispatch` shape):** if `__post_init__` + `object.__setattr__` on the frozen-slotted dataclass surfaces hairy edge cases (e.g. inheritance ordering with `IrCollection`), pause and ask before reaching for `@dataclass`-decorator tweaks. The shape is non-negotiable: frozen+slots, init=False cache fields, mutation of dict contents inside slots.

- **Step 3.3 (`_PatternAliasVisitor`):** the recursion-order trace in Task 3.3 is the only nontrivial part. If existing alias-collection tests fail after the conversion, **re-walk the trace step by step on a small test grammar** — the failure is almost certainly a frame-stack push/pop ordering issue, not a substrate bug.

- **Step 5 atomic group:** Tasks 5.1-5.4 commit individually but must NOT be merged separately. If execution surfaces a need to bisect, use `git rebase -i` on the slice's commits before final push. The four commits are equivalent to a single squashable atomic unit.

- **Step 5.3/5.4 `IrCallable` discipline:** the GBNF and ABNF action tables MUST express the structurally simple cases (`IrRuleRef`, `IrGroup`, `IrItem`, `IrSequence`, `IrAlternation`, `IrRule`) in pure IrOp. `IrCallable` is permitted for `IrLiteral`, `IrCharClass`, `IrQuantifier`, `IrAst`. Any other `IrCallable` use is a flag-for-discussion item — pause and surface to the user before committing.

- **Step 6 sed pass:** docstrings, comments, and test names may colloquially mention "Quantifier" — review the diff visually before committing. `git diff --stat` first; `git diff` to spot-check.

- **Step 7.1 B6 parity:** `_spec_to_irrule` must match the deleted `GbnfEmitter.emit_spec` byte-for-byte. If `to_gbnf()` round-trip tests fail, adjust `_spec_to_irrule` (or switch `to_gbnf` to call `GBNF(_spec_to_irrule(spec))` directly without the `render_specs` newline-join framing).

- **No worktree.** Work directly on the current branch.
