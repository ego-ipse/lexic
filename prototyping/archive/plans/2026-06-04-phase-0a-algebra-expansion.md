# Phase 0a — Algebra Expansion (V2 node model) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **Supersedes `2026-05-29-phase-0a-algebra-expansion.md`** (kept as a historical
> artifact). That plan targeted the pre-V2 substrate
> (`IrType`/`coerce`/`IrCollection`/`_items_attr`), which the V2 migration
> (`2026-06-01-ir-primitive-node-model.md`) removed. This plan targets the **real
> landed code**: two-param `IrSelf[Iri, Ir_co]`, `IrComposite` as the sole
> dataclass base, the `IrTuple` variadic tier, and `bound`/`bind` in place of
> `coerce`. See `docs/superpowers/specs/2026-06-04-phase-0-v2-realignment-design.md`
> for the rationale and `docs/superpowers/specs/2026-05-29-phase-0-honest-ir-foundation-design.md`
> §0a for the (realigned) spec.
>
> **Shapes verified empirically (2026-06-04).** The non-obvious type decisions
> below were each applied to `src/`, checked with `uv run pyright src/ tests/` and
> the full suite, then reverted: (1) the cast-free union-`out` `IrField` is
> pyright-clean — **no `cast()` needed**; (2) comparison/branch operand fields
> must be typed **`IrSelf`, not `IrNode`** — `IrNode`'s `Ir_co` is *invariant*
> (it appears in both `children() -> Sequence[Ir_co]` and
> `rebuild(Sequence[Ir_co])`), so an `IrField` typed `IrNode[…, IrScalar]` is not
> assignable to a bare `IrNode` slot; (3) hoisting `eval` to `IrScalar` and
> dropping `IrInt`'s `__new__`/`eval` causes no regression.

**Goal:** Add the value-aware action algebra — an `IrScalar` value-leaf base, `IrInt`, a cast-free `IrField` that reads non-string attributes, `Cmp`/`IrCompare`, `IrAnd`, and a node-valued `IrCond` — that Phase 0b/0c will consume, all in the V2 primitive node model.

**Architecture:** `IrScalar(IrLeaf)` is the value-leaf base; it hosts the one shared behaviour of value leaves — they are self-evaluating (`eval -> Self: return self`). `IrStr` re-parents onto it (dropping its now-duplicate `eval` **and** its ceremonial `__new__`), and `IrInt(IrScalar, int)` is the int-typed sibling (no `__new__`, no `eval` — both inherited; just `_bound` + a codegen `__repr__`). `IrField` becomes non-generic over `IrComposite[IrSelf, IrScalar]` with a runtime `out: type[IrStr] | type[IrInt]` constructor (no casts). `IrCompare`/`IrAnd` produce `IrInt(0/1)` — a truth value is an `IrInt` in `{0,1}`, there is **no `IrBool`**. `IrAnd` is an `IrTuple` subclass, which requires `IrTuple` to gain a result type parameter so a reducer's `eval` returns `IrInt` instead of the inherited rebuild `-> Self`. Comparison/branch operand fields are typed `IrSelf` (see verification note). Ships alone; no flavour or pipeline consumer.

**Tech Stack:** Python 3.14, PEP 695 generics, `dataclasses`, `pyright`, `pytest`, `uv`.

**Spec:** `docs/superpowers/specs/2026-05-29-phase-0-honest-ir-foundation-design.md` §0a (realigned) + `docs/superpowers/specs/2026-06-04-phase-0-v2-realignment-design.md`.

---

## Conventions for every task

- All commands prefixed `uv run` (project rule). Never bare `pytest`/`ruff`/`pyright`.
- Run `tools/auto_fix.sh` before any manual lint fix.
- No `# type: ignore` / `# pyright: ignore` / `# noqa` / `# pylint: disable` without explicit permission — fix the root cause.
- Docstrings: Sphinx style (`:param:`/`:returns:`/`:raises:`). Match the density of the surrounding V2 modules.
- Commits carry **no** `Co-Authored-By` line.
- **Port tests, never delete.** When a node shape changes, fix a test's *construction syntax* and keep its assertions. Remove a test only when its exact target symbol is removed, and say so in the commit.

## `__new__` policy for this plan

- **Remove** `IrStr.__new__` — ceremonial: `str.__new__` already accepts the value and defaults to `""`, and `str` overriding `__new__` lets `object.__init__` tolerate the construction arg. Confirmed by the per-task full-suite gate.
- **Do not add** `IrInt.__new__` — `int.__new__` already accepts the value and defaults to `0`.
- **Keep** `IrTuple.__new__` — **load-bearing**: it adapts varargs (`IrTuple(a, b)`) into the single-iterable `tuple.__new__(cls, (a, b))`. Removing it makes `IrTuple(a, b)` raise *"tuple expected at most 1 argument"*.
- **Keep** `IrNoneType.__new__` — load-bearing (singleton cache).

## Non-green window

None. Every task is additive or self-contained; existing `IrField("name")` callers stay green (default `out=IrStr`); the `IrTuple` result parameter is a typing-only change; the one behaviour-shape change (`IrCond` `field` → `test`) ports its two existing tests in the same commit. Each task ends green: its unit tests pass, `uv run pyright <touched files>` reports 0 errors, and the full suite stays green.

---

## File structure

| File | Change |
|---|---|
| `src/lexic/ir/nodes.py` | add `IrScalar` (hosts `eval -> Self`); re-parent `IrStr` onto it and drop `IrStr.__new__`/`IrStr.eval`; add `IrInt`; give `IrTuple` a result type parameter `R` |
| `src/lexic/ir/action.py` | `IrField` → non-generic cast-free `out`; add `Cmp`, `IrCompare`, `IrAnd`; generalize `IrCond` (`field` → `test`); operand fields typed `IrSelf` |
| `src/lexic/ir/__init__.py` | export `IrScalar`, `IrInt`, `IrCompare`, `IrAnd`, `Cmp` |
| `tests/unit/lexic/ir/test_nodes.py` | `IrScalar`/`IrInt`/`IrTuple`-result-param tests |
| `tests/unit/lexic/ir/test_action.py` | `IrField` `out`, `IrCompare`, `IrAnd` tests; port the two `IrCond` tests |
| `tests/unit/lexic/ir/test_init_ir.py` | assert the new public names import |
| `CLAUDE.md`, `.wiki/` | document the added ops + `.wiki/log.md` entry |

---

# PHASE 1 — value tier (`ir/nodes.py`)

### Task 1: `IrScalar` value-leaf base, `IrStr` re-parent, `IrInt`

**Files:**
- Modify: `src/lexic/ir/nodes.py`
- Test: `tests/unit/lexic/ir/test_nodes.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/unit/lexic/ir/test_nodes.py` (extend the existing `from lexic.ir.nodes import …` block to include `IrScalar`, `IrInt`):

```python
def test_irscalar_is_a_leaf_and_parents_the_value_leaves():
    from lexic.ir.nodes import IrScalar, IrLeaf, IrStr, IrInt

    assert issubclass(IrScalar, IrLeaf)
    assert issubclass(IrStr, IrScalar)
    assert issubclass(IrInt, IrScalar)


def test_irscalar_eval_is_self_for_both_value_leaves():
    from lexic.ir.nodes import IrInt, IrLiteral, IrNone

    assert IrInt(5).eval(IrNone, IrNone, ()) == 5          # inherited from IrScalar
    assert IrLiteral("x").eval(IrNone, IrNone, ()) == "x"  # IrStr leaf, inherited


def test_irint_is_int_and_scalar():
    from lexic.ir.nodes import IrInt, IrScalar

    assert isinstance(IrInt(5), int)
    assert isinstance(IrInt(5), IrScalar)
    assert IrInt(5) == 5          # native int equality
    assert IrInt(5) + 1 == 6      # native int arithmetic


def test_irint_default_is_zero():
    from lexic.ir.nodes import IrInt

    assert IrInt() == 0


def test_irint_bound_is_int():
    from lexic.ir.nodes import IrInt

    assert IrInt.bound_type() is int


def test_irint_repr_is_codegen():
    from lexic.ir.nodes import IrInt

    assert repr(IrInt(5)) == "IrInt(5)"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/lexic/ir/test_nodes.py -k "irscalar or irint" -q`
Expected: FAIL — `cannot import name 'IrScalar'` / `'IrInt'`.

- [ ] **Step 3: Write the implementation**

In `src/lexic/ir/nodes.py`, `# ── Primitive str tier ──` section: insert `IrScalar` **before** `class IrStr`, change `IrStr`'s bases to `(IrScalar, str)`, **delete** `IrStr.__new__` and `IrStr.eval` (now inherited), and add `IrInt` after the str-leaf classes.

```python
class IrScalar(IrLeaf):
    """Value-leaf base: leaves whose payload is a Python scalar.

    Category base for the value-carrying leaves (:class:`IrStr`, :class:`IrInt`).
    It is **not** a revival of the removed ``IrType`` — no coercion, no neutral
    element. It hosts the one shared behaviour of value leaves: they are
    self-evaluating (``eval`` returns ``self``). Behavioural leaves
    (``IrPass``/``IrWalk``/``IrEmit``/``IrThis``/``IrRebuild``) are NOT
    ``IrScalar`` — their ``eval`` does not return self — so this cannot live on
    :class:`IrLeaf`.
    """

    __slots__ = ()

    def eval(self, _d: IrSelf, _n: IrSelf, _nc: Sequence[IrSelf], /) -> Self:
        """Return ``self`` — the node IS the value, no further dispatch needed.

        :param _d: Dispatcher (unused).
        :param _n: Parent node (unused).
        :param _nc: Pre-walked children (unused).
        :returns: ``self``.
        """
        return self
```

```python
class IrStr(IrScalar, str):   # was: class IrStr(IrLeaf, str)
    ...   # KEEP: docstring, _bound, __eq__, __hash__, __repr__.
          # DELETE: __new__ (str.__new__ handles the value + "" default) and
          #         eval (now inherited from IrScalar).
```

```python
class IrInt(IrScalar, int):
    """``IrSelf + int`` value-leaf — the int-typed sibling of :class:`IrStr`.

    The node IS the integer (native comparison and arithmetic). Inherits the
    self-evaluating ``eval`` from :class:`IrScalar`, so an ``IrInt`` is a valid
    operand for :class:`~lexic.ir.action.IrCompare`. Native ``int`` equality and
    hashing — no sibling int-leaf kinds to disambiguate, so the type-aware
    ``__eq__`` that :class:`IrStr` needs is unnecessary. No ``__new__``:
    ``int.__new__`` already accepts the value and defaults to ``0``.

    ``_bound`` is set explicitly to ``int`` (parallel to ``IrStr._bound = str``),
    since ``IrInt`` introduces no PEP 695 type parameters.
    """

    __slots__ = ()
    _bound: ClassVar[type[int]] = int

    def __repr__(self) -> str:
        """Codegen repr: ``IrInt(5)`` (repr-is-codegen invariant).

        :returns: Constructor call reproducing this node.
        """
        return f"{type(self).__name__}({int.__repr__(self)})"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/lexic/ir/test_nodes.py -k "irscalar or irint" -q`
Expected: PASS (6 tests).

- [ ] **Step 5: No regression (proves `IrStr.__new__`/`eval` removal is safe) + pyright**

Run: `uv run pytest tests/unit/lexic/ir/test_nodes.py -q`
Run: `uv run pyright src/lexic/ir/nodes.py`
Expected: all node tests PASS (str-leaf construction/equality/repr still work without `IrStr.__new__`/`eval`); 0 pyright errors.

- [ ] **Step 6: Commit**

```bash
tools/auto_fix.sh
git add src/lexic/ir/nodes.py tests/unit/lexic/ir/test_nodes.py
git commit -m "ir/nodes: IrScalar value-leaf base (hosts eval); IrInt; drop IrStr.__new__/eval"
```

---

# PHASE 2 — attribute reads (`ir/action.py`)

### Task 2: `IrField` reads non-string attributes (cast-free runtime `out`)

**Files:**
- Modify: `src/lexic/ir/action.py`
- Test: `tests/unit/lexic/ir/test_action.py`

- [ ] **Step 1: Write the failing test**

In `tests/unit/lexic/ir/test_action.py`, extend the `from lexic.ir.nodes import …` block to include `IrInt` and `IrQuantifier` (if not already present), then add under the `# ── IrField ──` section:

```python
def test_irfield_out_irint_reads_int_without_stringifying():
    """IrField('min', IrInt) reads an int attribute and wraps it as IrInt."""
    q = IrQuantifier(min=3, max=5)
    result = IrField("min", IrInt).eval(IrNone, q, ())
    assert result == 3
    assert isinstance(result, IrInt)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/lexic/ir/test_action.py -k irfield -q`
Expected: FAIL — current `IrField` takes no second positional arg and wraps via `self.bound` (fixed to `IrStr`), so it would return `IrStr("3")`, not `IrInt(3)`.

- [ ] **Step 3: Rework `IrField` (non-generic, cast-free)**

In `src/lexic/ir/action.py`, add `IrInt` and `IrScalar` to the `from lexic.ir.nodes import (…)` block, then replace the entire `IrField` class with:

```python
@dataclass(frozen=True, slots=True, repr=False)
class IrField(IrComposite[IrSelf, IrScalar]):
    """Read a typed attribute from the dispatched node ``n`` and wrap it.

    The read value is wrapped via the **runtime** constructor ``out`` — one of
    the value-leaf types :class:`~lexic.ir.nodes.IrStr` / :class:`IrInt`
    (default ``IrStr``). A runtime field is required because PEP 695 type
    parameters are erased, so a generic alone could not drive construction. Read
    an int with ``IrField("min", IrInt)``; the default ``out=IrStr`` keeps every
    existing ``IrField("name")`` caller behaving as before.

    Non-generic and cast-free: the ``type[IrStr] | type[IrInt]`` union is
    constructor-callable for pyright, so ``self.out(value)`` type-checks without
    a cast, and the result (``IrStr | IrInt``) is an :class:`IrScalar`.

    A record-leaf: an :class:`IrComposite` with no IR-node children.
    """

    name: str
    out: type[IrStr] | type[IrInt] = IrStr

    def eval(self, _d: IrSelf, n: IrSelf, _nc: Sequence[IrSelf], /) -> IrScalar:
        """Read ``getattr(n, self.name)`` and wrap via ``self.out(value)``.

        :param _d: Dispatcher (unused — no recursion).
        :param n: Node whose attribute to read.
        :param _nc: Pre-walked children (unused).
        :returns: The attribute value wrapped in ``self.out`` (an ``IrScalar``).
        """
        return self.out(getattr(n, self.name))
```

> `IrField` is now non-generic; it no longer uses `self.bound`. `bound`/`bind`
> remain in use by `IrConcat`/`IrJoin`/`IrEmit`, unchanged. (Verified: 0 pyright
> errors, no casts.)

- [ ] **Step 4: Run tests to verify they pass (existing string-field tests too)**

Run: `uv run pytest tests/unit/lexic/ir/test_action.py -k irfield -q`
Expected: PASS — the existing `IrField("name")` tests (default `out=IrStr`) plus the new `IrInt` test.

- [ ] **Step 5: pyright (touched file + a caller, to prove the bound)**

Run: `uv run pyright src/lexic/ir/action.py src/lexic/grammars/gbnf/flavour.py src/lexic/grammars/abnf/flavour.py`
Expected: 0 errors (both flavours' `IrField("name")` calls remain valid).

- [ ] **Step 6: Commit**

```bash
tools/auto_fix.sh
git add src/lexic/ir/action.py tests/unit/lexic/ir/test_action.py
git commit -m "ir/action: IrField reads non-string attrs via cast-free out (default IrStr)"
```

---

### Task 3: `Cmp` enum + `IrCompare`

**Files:**
- Modify: `src/lexic/ir/action.py`
- Test: `tests/unit/lexic/ir/test_action.py`

- [ ] **Step 1: Write the failing tests**

Extend the `from lexic.ir.action import …` block in `test_action.py` to include `IrCompare` and `Cmp`, then add a new section:

```python
# ── IrCompare ─────────────────────────────────────────────────────────


def test_ircompare_eq_true_returns_irint_one():
    result = IrCompare(IrInt(1), Cmp.EQ, IrInt(1)).eval(IrNone, IrNone, ())
    assert result == 1
    assert isinstance(result, IrInt)


def test_ircompare_eq_false_returns_irint_zero():
    assert IrCompare(IrInt(1), Cmp.EQ, IrInt(0)).eval(IrNone, IrNone, ()) == 0


def test_ircompare_lt_and_gt():
    assert IrCompare(IrInt(1), Cmp.LT, IrInt(2)).eval(IrNone, IrNone, ()) == 1
    assert IrCompare(IrInt(2), Cmp.GT, IrInt(1)).eval(IrNone, IrNone, ()) == 1
    assert IrCompare(IrInt(2), Cmp.LT, IrInt(1)).eval(IrNone, IrNone, ()) == 0
    assert IrCompare(IrInt(1), Cmp.GT, IrInt(2)).eval(IrNone, IrNone, ()) == 0


def test_ircompare_reads_field_operand():
    q = IrQuantifier(min=0, max=1)
    cmp = IrCompare(IrField("min", IrInt), Cmp.EQ, IrInt(0))
    assert cmp.eval(IrNone, q, ()) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/lexic/ir/test_action.py -k ircompare -q`
Expected: FAIL — `cannot import name 'IrCompare'` / `'Cmp'`.

- [ ] **Step 3: Implement `Cmp` and `IrCompare`**

At the top of `src/lexic/ir/action.py`, add to the stdlib imports:

```python
import operator
from enum import Enum
```

(`IrSelf`, `IrComposite`, `IrInt`, `ClassVar`, `Sequence` are already imported; `IrInt` was added in Task 2.) Then, after `IrField`, add:

```python
class Cmp(Enum):
    """Closed comparison-operator enum for :class:`IrCompare`."""

    EQ = "=="
    LT = "<"
    GT = ">"


_CMP_OPS = {Cmp.EQ: operator.eq, Cmp.LT: operator.lt, Cmp.GT: operator.gt}


@dataclass(frozen=True, slots=True, repr=False)
class IrCompare[Iri: IrSelf](IrComposite[Iri, IrInt]):
    """Compare two operand nodes; eval to ``IrInt(1)`` (true) or ``IrInt(0)``.

    Both operands are evaluated via ``.eval`` and compared with native builtins
    (``IrInt`` IS-A ``int``). A truth value is an ``IrInt`` in ``{0, 1}`` — there
    is no ``IrBool``. ``op`` is the comparison.

    ``left``/``right`` are typed ``IrSelf`` (not ``IrNode``): ``IrNode``'s
    ``Ir_co`` is invariant, so a value operand like ``IrField`` (an
    ``IrNode[…, IrScalar]``) is not assignable to a bare ``IrNode`` slot. Every
    operand is at least an ``IrSelf`` with ``.eval``.

    :param Iri: the dispatcher input type.
    """

    _child_attrs: ClassVar[tuple[str, ...]] = ("left", "right")
    left: IrSelf
    op: Cmp
    right: IrSelf

    def eval(self, d: Iri, n: Iri, nc: Sequence[Iri], /) -> IrInt:
        """Evaluate both operands and apply ``self.op``.

        :param d: Dispatcher forwarded to each operand's ``eval``.
        :param n: Current node forwarded to each operand's ``eval``.
        :param nc: Pre-walked children forwarded to each operand's ``eval``.
        :returns: ``IrInt(1)`` if the comparison holds, else ``IrInt(0)``.
        """
        left_val = self.left.eval(d, n, nc)
        right_val = self.right.eval(d, n, nc)
        return IrInt(1) if _CMP_OPS[self.op](left_val, right_val) else IrInt(0)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/lexic/ir/test_action.py -k ircompare -q`
Expected: PASS (4 tests).

- [ ] **Step 5: pyright (covers the IrField-as-operand assignability)**

Run: `uv run pyright src/lexic/ir/action.py tests/unit/lexic/ir/test_action.py`
Expected: 0 errors (with `left`/`right` typed `IrSelf`, `IrField("min", IrInt)` and `IrInt(0)` operands are accepted).

- [ ] **Step 6: Commit**

```bash
tools/auto_fix.sh
git add src/lexic/ir/action.py tests/unit/lexic/ir/test_action.py
git commit -m "ir/action: add Cmp enum and IrCompare predicate (-> IrInt 0/1)"
```

---

# PHASE 3 — conjunction (`ir/nodes.py` + `ir/action.py`)

### Task 4: `IrTuple` result type parameter + `IrAnd`

**Files:**
- Modify: `src/lexic/ir/nodes.py` (result param), `src/lexic/ir/action.py` (`IrAnd`)
- Test: `tests/unit/lexic/ir/test_nodes.py`, `tests/unit/lexic/ir/test_action.py`

- [ ] **Step 1: Write the failing tests**

In `tests/unit/lexic/ir/test_nodes.py`, add (the result-param refactor must leave rebuild semantics intact):

```python
def test_irtuple_eval_still_rebuilds_collection_types():
    from lexic.ir.nodes import IrSequence, IrItem, IrLiteral, IrNone

    seq = IrSequence(IrItem(IrLiteral("a")), IrItem(IrLiteral("b")))
    out = seq.eval(IrNone, IrNone, ())
    assert isinstance(out, IrSequence)
    assert out == seq
```

In `tests/unit/lexic/ir/test_action.py`, extend the `from lexic.ir.action import …` block to include `IrAnd` (`IrCallable` is already imported), then add:

```python
# ── IrAnd ─────────────────────────────────────────────────────────────


def test_irand_is_irtuple_subclass():
    from lexic.ir.nodes import IrTuple

    assert isinstance(IrAnd(), tuple)
    assert isinstance(IrAnd(), IrTuple)


def test_irand_all_true():
    a = IrAnd(
        IrCompare(IrInt(1), Cmp.EQ, IrInt(1)),
        IrCompare(IrInt(2), Cmp.GT, IrInt(1)),
    )
    result = a.eval(IrNone, IrNone, ())
    assert result == 1
    assert isinstance(result, IrInt)


def test_irand_one_false_yields_zero():
    a = IrAnd(
        IrCompare(IrInt(1), Cmp.EQ, IrInt(1)),
        IrCompare(IrInt(1), Cmp.EQ, IrInt(0)),
    )
    assert a.eval(IrNone, IrNone, ()) == 0


def test_irand_empty_is_vacuously_true():
    assert IrAnd().eval(IrNone, IrNone, ()) == 1


def test_irand_short_circuits_on_first_false():
    calls: list[int] = []

    def _record(_d, _n, _nc):
        calls.append(1)
        return IrInt(1)

    a = IrAnd(IrCompare(IrInt(1), Cmp.EQ, IrInt(0)), IrCallable(_record))
    assert a.eval(IrNone, IrNone, ()) == 0
    assert calls == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/lexic/ir/test_action.py -k irand -q`
Expected: FAIL — `cannot import name 'IrAnd'`.

- [ ] **Step 3a: Add the result type parameter to `IrTuple`**

In `src/lexic/ir/nodes.py`, change the `IrTuple` signature and `eval`, and update the two collection subclasses. (`cast` is already imported. **Keep `IrTuple.__new__`** — it is the load-bearing varargs→iterable adapter.)

```python
class IrTuple[T: IrSelf, R: IrSelf = IrSelf](IrNode, tuple):
    """``IrSelf + tuple`` primitive tier. A variadic node IS its children.

    ... (existing class docstring body unchanged) ...

    :param T: The element type, bounded by ``IrSelf``.
    :param R: The ``eval`` result type (defaults to ``IrSelf``). Rebuild
        collections (``IrSequence``/``IrAlternation``) set ``R`` to themselves,
        keeping precise eval typing; reducer subclasses (``IrAnd``) set ``R`` to
        their reduced result type (``IrInt``) and override ``eval``.
    """

    __slots__ = ()
    _bound: ClassVar[type[tuple]] = tuple

    # __new__ (varargs adapter — REQUIRED), children, rebuild, __repr__ unchanged

    def eval(self, d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> R:
        """Dispatch each element via its own ``eval`` and rebuild the tuple.

        The runtime result is ``type(self)(...)`` (i.e. ``Self``); the cast to
        ``R`` is sound for rebuild collections, which set ``R`` to their own
        type. Reducer subclasses override this method entirely.

        :param d: Dispatcher forwarded to each element's ``eval``.
        :param n: Parent node forwarded to each element's ``eval``.
        :param nc: Pre-walked children forwarded to each element's ``eval``.
        :returns: New instance containing the evaluated elements, typed ``R``.
        """
        return cast(R, type(self)(*(p.eval(d, n, nc) for p in self)))
```

```python
class IrSequence(IrTuple["IrItem", "IrSequence"]):   # was IrTuple["IrItem"]
    ...                                              # body unchanged


class IrAlternation(IrTuple["IrSequence", "IrAlternation"]):   # was IrTuple["IrSequence"]
    ...                                                        # body unchanged
```

> The `cast(R, …)` is the explicit narrowing from the realignment design §3.4 —
> `type(self)(...)` is `Self`, not provably `R` in the base generic. It is a
> typed cast, **not** a suppression. Unsubscripted `IrTuple` / `IrTuple()`
> defaults (used by `IrAst.rules`, `IrConcat.parts`, etc.) are unaffected — `R`
> defaults to `IrSelf`. `__init_subclass__` reads `__type_params__[-1]` (now `R`)
> but `IrTuple` sets `_bound = tuple` in its own dict, which short-circuits the
> derivation — confirmed `IrSequence.bound_type() is tuple` still holds.

- [ ] **Step 3b: Implement `IrAnd`**

In `src/lexic/ir/action.py` (`IrNode`, `IrInt`, `IrTuple` are already imported), after `IrCompare`, add:

```python
class IrAnd(IrTuple[IrNode, IrInt]):
    """Short-circuit conjunction — an :class:`~lexic.ir.nodes.IrTuple` subclass.

    ``IrAnd`` IS its operand tuple. ``eval`` ANDs the truthiness of each
    evaluated operand, short-circuiting on the first falsy one, and yields
    ``IrInt(1)`` (all truthy / empty / vacuously true) or ``IrInt(0)``. The
    ``IrTuple`` result parameter is ``IrInt``, so this reducer ``eval`` cleanly
    overrides the inherited rebuild ``eval -> Self``.

    Construct variadically: ``IrAnd(pred1, pred2, …)`` where each operand is a
    predicate node (typically :class:`IrCompare`).
    """

    __slots__ = ()
    _bound: ClassVar[type] = IrInt

    def eval(self, d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> IrInt:
        """AND the truthiness of each evaluated operand, short-circuiting.

        :param d: Dispatcher forwarded to each operand's ``eval``.
        :param n: Current node forwarded to each operand's ``eval``.
        :param nc: Pre-walked children forwarded to each operand's ``eval``.
        :returns: ``IrInt(0)`` on the first falsy operand, else ``IrInt(1)``.
        """
        for part in self:
            if not part.eval(d, n, nc):
                return IrInt(0)
        return IrInt(1)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/lexic/ir/test_nodes.py -k irtuple -q`
Run: `uv run pytest tests/unit/lexic/ir/test_action.py -k irand -q`
Expected: PASS (1 node test + 5 action tests).

- [ ] **Step 5: pyright + no regression**

Run: `uv run pyright src/lexic/ir/nodes.py src/lexic/ir/action.py`
Run: `uv run pytest tests/unit/lexic/ir/ -q`
Expected: 0 pyright errors; all `ir/` unit tests PASS (the `IrTuple` signature change must not regress `IrSequence`/`IrAlternation`/`IrAst`).

- [ ] **Step 6: Commit**

```bash
tools/auto_fix.sh
git add src/lexic/ir/nodes.py src/lexic/ir/action.py tests/unit/lexic/ir/test_nodes.py tests/unit/lexic/ir/test_action.py
git commit -m "ir: IrTuple gains result type param; add IrAnd (IrTuple subclass -> IrInt)"
```

---

# PHASE 4 — generalize `IrCond`

### Task 5: `IrCond` `field: str` → `test: IrSelf`

**Files:**
- Modify: `src/lexic/ir/action.py`
- Test: `tests/unit/lexic/ir/test_action.py` (port the two existing `IrCond` tests)

- [ ] **Step 1: Port the existing tests**

In `tests/unit/lexic/ir/test_action.py`, **replace** the two existing tests under `# ── IrCond ──` (`test_ircond_evaluates_then_when_truthy` and `test_ircond_evaluates_else_when_falsy`, which construct `IrCond(field="min", …)`) with the test-node form below. The dispatch-on-`IrQuantifier.min` semantics are preserved; only the construction changes (`field="min"` → `test=IrField("min", IrInt)`). `IrField`/`IrInt` are already imported from Tasks 2–3.

```python
def test_ircond_evaluates_then_when_test_truthy():
    """IrCond picks then_op when the test node evals truthy."""
    node = IrQuantifier(min=1, max=1)
    op = IrCond[IrSelf, IrStr](
        test=IrField("min", IrInt),
        then_op=IrLiteral("yes"),
        else_op=IrLiteral("no"),
    )
    assert op.eval(IrNone, node, ()) == "yes"


def test_ircond_evaluates_else_when_test_falsy():
    """IrCond picks else_op when the test node evals falsy."""
    node = IrQuantifier(min=0, max=1)
    op = IrCond[IrSelf, IrStr](
        test=IrField("min", IrInt),
        then_op=IrLiteral("yes"),
        else_op=IrLiteral("no"),
    )
    assert op.eval(IrNone, node, ()) == "no"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/lexic/ir/test_action.py -k ircond -q`
Expected: FAIL — `IrCond` has no `test` field (still `field`).

- [ ] **Step 3: Reshape `IrCond`**

Replace the `IrCond` class in `src/lexic/ir/action.py` with:

```python
@dataclass(frozen=True, slots=True, repr=False)
class IrCond[Iri: IrSelf, Ir_co: IrSelf](IrComposite[Iri, Ir_co]):
    """If ``test`` evaluates truthy, evaluate ``then_op``; else ``else_op``.

    ``test`` is any node whose ``eval`` yields a truthy/falsy value
    (e.g. :class:`IrCompare`, :class:`IrAnd`). Typed ``IrSelf`` for the same
    reason as :class:`IrCompare`'s operands (``IrNode``'s ``Ir_co`` is
    invariant, which rejects value operands like ``IrField``). Both branches
    share ``Ir_co``.

    :param Ir_co: the shared result type of both branches.
    """

    _child_attrs: ClassVar[tuple[str, ...]] = ("test", "then_op", "else_op")
    test: IrSelf
    then_op: IrSelf
    else_op: IrSelf

    def eval(self, d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> Ir_co:
        """Branch on the truthiness of ``self.test.eval(d, n, nc)``.

        :param d: Dispatcher forwarded to the test and the chosen branch.
        :param n: Current node forwarded to the test and the chosen branch.
        :param nc: Pre-walked children forwarded onward.
        :returns: The chosen branch's result.
        """
        branch = self.then_op if self.test.eval(d, n, nc) else self.else_op
        return branch.eval(d, n, nc)
```

> The old tests referenced `field`, the removed symbol — so this is a port (fix
> construction, keep the then/else assertions), not a deletion. `IrCond` has
> zero callers in `src/` (verified), so no other site changes.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/lexic/ir/test_action.py -k ircond -q`
Expected: PASS (2 tests).

- [ ] **Step 5: pyright + no regression**

Run: `uv run pyright src/lexic/ir/action.py tests/unit/lexic/ir/test_action.py`
Run: `uv run pytest tests/unit/lexic/ir/test_action.py -q`
Expected: 0 pyright errors; all action tests PASS.

- [ ] **Step 6: Commit**

```bash
tools/auto_fix.sh
git add src/lexic/ir/action.py tests/unit/lexic/ir/test_action.py
git commit -m "ir/action: generalize IrCond field:str -> test:IrSelf"
```

---

# PHASE 5 — public surface + docs + gate

### Task 6: Export the new ops

**Files:**
- Modify: `src/lexic/ir/__init__.py`
- Test: `tests/unit/lexic/ir/test_init_ir.py`

- [ ] **Step 1: Write the failing test**

In `tests/unit/lexic/ir/test_init_ir.py`, add:

```python
def test_new_algebra_ops_are_public():
    import lexic.ir as ir

    for name in ("IrScalar", "IrInt", "IrCompare", "IrAnd", "Cmp"):
        assert hasattr(ir, name), name
        assert name in ir.__all__, name
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/lexic/ir/test_init_ir.py -k algebra -q`
Expected: FAIL — names not exported.

- [ ] **Step 3: Add the exports**

In `src/lexic/ir/__init__.py`:
- add `IrAnd`, `IrCompare`, `Cmp` to the `from lexic.ir.action import (…)` block;
- add `IrInt`, `IrScalar` to the `from lexic.ir.nodes import (…)` block;
- add all five names to `__all__`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/lexic/ir/test_init_ir.py -q`
Expected: PASS.

- [ ] **Step 5: pyright**

Run: `uv run pyright src/lexic/ir/__init__.py`
Expected: 0 errors.

- [ ] **Step 6: Commit**

```bash
tools/auto_fix.sh
git add src/lexic/ir/__init__.py tests/unit/lexic/ir/test_init_ir.py
git commit -m "ir: export IrScalar, IrInt, IrCompare, IrAnd, Cmp"
```

---

### Task 7: Living docs + full-tree gate

**Files:**
- Modify: `CLAUDE.md`, `.wiki/` (IR shapes/decisions + `.wiki/log.md`)

- [ ] **Step 1: Update `CLAUDE.md`**

In the `nodes.py` layout line, record the `IrScalar` value-leaf base (hosts `eval`), `IrInt`, and that `IrStr` no longer carries `__new__`/`eval`. In the `action.py` layout line, add `IrCompare`, `IrAnd`, `Cmp`, note `IrField` is `out`-typed (cast-free) and `IrCond` is `test`-valued. In the §IR types prose, record: a truth value is `IrInt ∈ {0,1}` (no `IrBool`); `IrField.out` reads typed attributes; `IrTuple` carries a result type parameter so reducers (`IrAnd`) eval to a non-tuple type; comparison/branch operands are typed `IrSelf` because `IrNode`'s `Ir_co` is invariant.

- [ ] **Step 2: Update the wiki**

Update the IR-shapes / decisions pages with the added ops and the `IrScalar`/`IrInt`/result-param/invariance facts, and append a dated entry to `.wiki/log.md` (per CLAUDE.md) referencing this plan and the realignment design.

- [ ] **Step 3: Mechanical fixes**

Run: `tools/auto_fix.sh`

- [ ] **Step 4: Full-tree gate**

Run: `uv run pyright src/ tests/`
Run: `uv run pytest tests/ -q`
Run: `uv run ruff check src/ tests/`
Run: `uv run pylint src/lexic/ir/nodes.py src/lexic/ir/action.py`
Expected: pyright 0 errors / 0 warnings, no suppressions; full suite green (baseline 474 + the new tests); ruff clean; pylint clean (no new disables).

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md .wiki/
git commit -m "docs: record Phase-0a algebra ops (IrScalar/IrInt/IrCompare/IrAnd/Cmp)"
```

---

## Self-review

**Spec coverage (§0a, realigned):**
- §0a.1 `IrScalar` + `IrInt` → Task 1; `IrCompare` → Task 3; `IrAnd` → Task 4. ✓
- §0a.2 generalized `IrCond` (`field` → `test`) → Task 5. ✓
- §0a.3 `IrField` cast-free runtime `out` → Task 2. ✓
- §0a.4 no `IrBool` (truth = `IrInt(0/1)`) → enforced by `IrCompare`/`IrAnd` returning `IrInt`; `IrRanged`/Y recorded in the spec, built nowhere. ✓
- §0a.5 canonical-op amendment (additions incl. `IrScalar`, `IrTuple` result param) → recorded in Task 7 docs. ✓
- §0a.6 tests → Tasks 1–5. ✓
- Realignment design §3.4 `IrTuple` result type parameter (enables `IrAnd`) → Task 4. ✓
- "`IrNot` stays grammar-only" → no task needed. ✓

**`__new__` handling:** `IrStr.__new__` removed (ceremonial; Task 1, gated by full node-test suite); `IrInt.__new__` never added; `IrTuple.__new__` retained (load-bearing varargs adapter; Task 4); `IrNoneType.__new__` untouched (singleton).

**Empirically verified shapes (2026-06-04, applied→checked→reverted):** cast-free union-`out` `IrField` is pyright-clean (no casts); `IrSelf`-typed operands accept `IrField`/`IrInt` while `IrNode`-typed ones do not (invariant `Ir_co`); `IrScalar` eval-hoist and `IrInt` without `__new__`/`eval` cause no regression; `IrTuple` result param does not regress `IrSequence`/`IrAlternation`/`IrAst`.

**Placeholder scan:** none — every code step has complete code; every run step has an exact command + expected result. The "(existing … unchanged)" notes (IrStr body in Task 1, IrTuple `__new__`/`children`/`rebuild`/`__repr__` in Task 4) are explicit *no-change* markers on already-landed code.

**Type consistency:** `IrScalar` (Task 1) hosts `eval` and parents `IrStr`/`IrInt`; `IrField.out` is `type[IrStr] | type[IrInt]` (Task 2) returning `IrScalar`; `IrInt` is the result of `IrField(out=IrInt)`/`IrCompare`/`IrAnd` and an operand of `IrCompare`/`IrAnd`; operand/branch fields are `IrSelf` across `IrCompare` (Task 3) and `IrCond` (Task 5); `IrTuple[T, R]` (Task 4) is used by `IrSequence`/`IrAlternation` (R = self-type) and `IrAnd` (R = `IrInt`). No removed symbol (`IrType`, `coerce`, `IrCollection`, `_items_attr`, `IrField`'s generic `Ir_co`/`self.bound`, `IrStr.__new__`, `IrCond.field`) is referenced.

**Dependency order:** Task 1 (`IrScalar`/`IrInt`) precedes Tasks 2–4; Task 3 (`IrCompare`) precedes Task 4's `IrAnd` operands and Task 5's `IrCond` test; Task 4's `IrTuple` param is required by its own `IrAnd`. Correct.
