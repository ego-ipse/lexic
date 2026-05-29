# Phase 0a — Algebra Expansion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the value-aware action ops (`IrInt`, `IrCompare`, `IrAnd`), generalize `IrCond` to a node-valued test, and widen `IrField` to read non-string attributes — the algebra 0b/0c will consume.

**Architecture:** `IrInt` joins `IrStr` as a typed `IrSelf+native` value in `ir/nodes.py`. `ir/action.py` gains `Cmp`/`IrCompare`/`IrAnd`, reshapes `IrCond` (`field:str` → `test:IrNode`), and gives `IrField` an explicit `out` output-type so it can wrap reads as `IrInt`. A truth value is an `IrInt` in `{0,1}` — there is **no `IrBool`** node. Ships alone; no flavour or pipeline consumer.

**Tech Stack:** Python 3.13, dataclasses, `uv run pytest`, `ruff`.

**Spec:** `docs/superpowers/specs/2026-05-29-phase-0-honest-ir-foundation-design.md` §0a.

---

## File Structure

- **Modify** `src/lexic/ir/nodes.py` — add `IrInt(IrType, int)` next to `IrStr`.
- **Modify** `src/lexic/ir/action.py` — add `Cmp`, `IrCompare`, `IrAnd`; reshape `IrCond`; rework `IrField` (`out` field).
- **Modify** `src/lexic/ir/__init__.py` — export `IrInt`, `IrCompare`, `IrAnd`, `Cmp`.
- **Modify** `tests/unit/lexic/ir/test_nodes.py` — `IrInt` tests.
- **Modify** `tests/unit/lexic/ir/test_action.py` — `IrField`/`IrCompare`/`IrAnd` tests; update `IrCond` tests.
- **Modify** `CLAUDE.md` + **append** `.wiki/lexic/log.md` — canonical-op amendment.

**Conventions (from CLAUDE.md):** always `uv run ...`; run `tools/auto_fix.sh` before hand-fixing lint; **never** add `Co-Authored-By` to commits; Sphinx-style docstrings (`:param:`/`:returns:`).

---

## Task 1: `IrInt` typed value

**Files:**
- Modify: `src/lexic/ir/nodes.py` (after `IrStr`, ~line 192)
- Modify: `src/lexic/ir/__init__.py`
- Test: `tests/unit/lexic/ir/test_nodes.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/unit/lexic/ir/test_nodes.py` (extend the existing import from `lexic.ir.nodes` to include `IrInt` and `IrNone`):

```python
def test_irint_holds_value_and_is_int():
    assert IrInt(5) == 5
    assert isinstance(IrInt(5), int)


def test_irint_neutral_singleton_is_zero():
    assert IrInt() == 0


def test_irint_coerce_wraps_and_passes_through():
    assert IrInt.coerce(3) == 3
    assert IrInt.coerce(IrInt(3)) == 3


def test_irint_eval_returns_value_not_neutral():
    # IrInt is a self-evaluating constant — distinct from IrType's neutral eval.
    assert IrInt(5).eval(IrNone, IrNone, ()) == 5
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/lexic/ir/test_nodes.py -k irint -v`
Expected: FAIL — `ImportError` / `cannot import name 'IrInt'`.

- [ ] **Step 3: Implement `IrInt`**

In `src/lexic/ir/nodes.py`, immediately after the `IrStr` class (before `IrTuple`), add:

```python
class IrInt(IrType, int):
    """``IrSelf+int`` typed class. ``IrInt()`` is the zero singleton.

    ``IrInt`` IS-A ``int`` so native comparison/arithmetic work; it IS-A
    ``IrSelf`` so the IR protocol applies. Unlike :class:`IrStr` (whose
    constant role is carried by :class:`IrLiteral`), ``IrInt`` doubles as its
    own int-constant action primitive: ``eval`` returns the value, making it a
    valid self-evaluating operand for ``IrCompare``.
    """

    _bound: ClassVar[type[int]] = int

    def eval(self, _d: IrSelf, _n: IrSelf, _nc: Sequence[IrSelf], /) -> Self:
        """Return the int value itself (a self-evaluating constant).

        :returns: ``self``.
        """
        return self
```

Then export it. In `src/lexic/ir/__init__.py`, add `IrInt` to the import from `lexic.ir.nodes` and to `__all__` (alphabetically near `IrGroup`/`IrItem`).

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/lexic/ir/test_nodes.py -k irint -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
uv run ruff check src/lexic/ir/nodes.py src/lexic/ir/__init__.py
git add src/lexic/ir/nodes.py src/lexic/ir/__init__.py tests/unit/lexic/ir/test_nodes.py
git commit -m "ir/nodes: add IrInt typed value"
```

---

## Task 2: `IrField` reads non-string attributes via `out`

**Files:**
- Modify: `src/lexic/ir/action.py` (`IrField`, ~lines 53-70)
- Test: `tests/unit/lexic/ir/test_action.py`

- [ ] **Step 1: Write the failing test**

In `tests/unit/lexic/ir/test_action.py`, extend imports to include `IrInt` and `IrQuantifier` (from `lexic.ir.nodes`), then add under the `# ── IrField ──` section:

```python
def test_irfield_out_irint_reads_int_without_stringifying():
    q = IrQuantifier(3, 5)  # current shape: .min is the int 3
    result = IrField("min", IrInt).eval(IrNone, q, ())
    assert result == 3
    assert isinstance(result, IrInt)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/lexic/ir/test_action.py::test_irfield_out_irint_reads_int_without_stringifying -v`
Expected: FAIL — `IrField` takes no second arg / returns an `IrStr`.

- [ ] **Step 3: Rework `IrField`**

Replace the entire `IrField` class in `src/lexic/ir/action.py` with:

```python
@dataclass(frozen=True, slots=True, init=False)
class IrField(IrLeaf):
    """Read a typed attribute from the dispatched node ``n``.

    The read value is wrapped in ``out`` (an :class:`IrType` subclass,
    default :class:`IrStr`). Pass ``out=IrInt`` to read integer attributes
    (e.g. quantifier bounds) without stringifying them.

    :ivar name: Attribute name to read from ``n``.
    :ivar out: IrType subclass the value is wrapped in.
    """

    name: str
    out: type[IrType] = IrStr

    def eval(self, _d: IrSelf, n: IrSelf, _nc: Sequence[IrSelf], /) -> IrType:
        """Read ``getattr(n, self.name)`` and wrap via ``self.out(value)``.

        :param n: The dispatched node to read from.
        :returns: The attribute value wrapped as ``out``.
        """
        return self.out(getattr(n, self.name))
```

Add `IrInt` and `IrType` to the existing `from lexic.ir.nodes import (...)` block in `action.py`.

- [ ] **Step 4: Run the full action test file (existing string-field tests must still pass)**

Run: `uv run pytest tests/unit/lexic/ir/test_action.py -k irfield -v`
Expected: PASS — `test_irfield_reads_string_attribute`, `test_irfield_reads_charclass_pattern` (default `out=IrStr`), and the new `IrInt` test.

- [ ] **Step 5: Commit**

```bash
uv run ruff check src/lexic/ir/action.py
git add src/lexic/ir/action.py tests/unit/lexic/ir/test_action.py
git commit -m "ir/action: IrField gains explicit out type (reads IrInt)"
```

---

## Task 3: `Cmp` enum + `IrCompare`

**Files:**
- Modify: `src/lexic/ir/action.py`
- Modify: `src/lexic/ir/__init__.py`
- Test: `tests/unit/lexic/ir/test_action.py`

- [ ] **Step 1: Write the failing tests**

Extend `test_action.py` imports to include `IrCompare` and `Cmp` (from `lexic.ir.action`), then add a new section:

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


def test_ircompare_reads_field_operand():
    q = IrQuantifier(0, 1)  # current shape: .min is 0
    cmp = IrCompare(IrField("min", IrInt), Cmp.EQ, IrInt(0))
    assert cmp.eval(IrNone, q, ()) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/lexic/ir/test_action.py -k ircompare -v`
Expected: FAIL — `cannot import name 'IrCompare'` / `'Cmp'`.

- [ ] **Step 3: Implement `Cmp` and `IrCompare`**

At the top of `src/lexic/ir/action.py`, add to the stdlib imports:

```python
import operator
from enum import Enum
```

Then, after the `IrField` class, add:

```python
class Cmp(Enum):
    """Closed comparison-operator enum for :class:`IrCompare`."""

    EQ = "=="
    LT = "<"
    GT = ">"


_CMP_OPS = {Cmp.EQ: operator.eq, Cmp.LT: operator.lt, Cmp.GT: operator.gt}


@dataclass(frozen=True, slots=True, init=False, repr=False)
class IrCompare(IrComposite[IrInt]):
    """Compare two operand IrNodes; eval to ``IrInt(1)`` (true) or ``IrInt(0)``.

    Operands are evaluated via ``.eval`` and compared with native builtins
    (``IrInt`` IS-A ``int``). A truth value is an ``IrInt`` in the domain
    ``IrQuantifier(0, 1)`` — there is no ``IrBool``.

    :ivar left: Left operand node.
    :ivar op: Comparison operator.
    :ivar right: Right operand node.
    """

    _child_attrs: ClassVar[tuple[str, ...]] = ("left", "right")
    left: IrNode
    op: Cmp
    right: IrNode

    def eval(self, d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> IrInt:
        """Evaluate both operands and apply ``self.op``.

        :returns: ``IrInt(1)`` if the comparison holds, else ``IrInt(0)``.
        """
        left_val = self.left.eval(d, n, nc)
        right_val = self.right.eval(d, n, nc)
        return IrInt(1) if _CMP_OPS[self.op](left_val, right_val) else IrInt(0)
```

Export `IrCompare` and `Cmp` from `src/lexic/ir/__init__.py` (import + `__all__`).

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/lexic/ir/test_action.py -k ircompare -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
uv run ruff check src/lexic/ir/action.py src/lexic/ir/__init__.py
git add src/lexic/ir/action.py src/lexic/ir/__init__.py tests/unit/lexic/ir/test_action.py
git commit -m "ir/action: add Cmp enum and IrCompare predicate"
```

---

## Task 4: `IrAnd` conjunction

**Files:**
- Modify: `src/lexic/ir/action.py`
- Modify: `src/lexic/ir/__init__.py`
- Test: `tests/unit/lexic/ir/test_action.py`

- [ ] **Step 1: Write the failing tests**

Extend `test_action.py` imports to include `IrAnd`, then add:

```python
# ── IrAnd ─────────────────────────────────────────────────────────────


def test_irand_all_true():
    a = IrAnd(
        (
            IrCompare(IrInt(1), Cmp.EQ, IrInt(1)),
            IrCompare(IrInt(2), Cmp.GT, IrInt(1)),
        )
    )
    assert a.eval(IrNone, IrNone, ()) == 1


def test_irand_one_false_short_circuits():
    a = IrAnd(
        (
            IrCompare(IrInt(1), Cmp.EQ, IrInt(1)),
            IrCompare(IrInt(1), Cmp.EQ, IrInt(0)),
        )
    )
    assert a.eval(IrNone, IrNone, ()) == 0


def test_irand_empty_is_vacuously_true():
    assert IrAnd(()).eval(IrNone, IrNone, ()) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/lexic/ir/test_action.py -k irand -v`
Expected: FAIL — `cannot import name 'IrAnd'`.

- [ ] **Step 3: Implement `IrAnd`**

After `IrCompare` in `src/lexic/ir/action.py`, add:

```python
@dataclass(frozen=True, slots=True, init=False, repr=False)
class IrAnd(IrCollection[IrInt]):
    """Short-circuit conjunction; eval to ``IrInt(1)`` iff every part is truthy.

    Empty ``parts`` is vacuously true.

    :ivar parts: Operand predicate nodes.
    """

    _items_attr: ClassVar[str] = "parts"
    parts: IrTuple = IrTuple()

    def eval(self, d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> IrInt:
        """AND the truthiness of each evaluated part, short-circuiting.

        :returns: ``IrInt(0)`` on the first falsy part, else ``IrInt(1)``.
        """
        for part in self.parts:
            if not part.eval(d, n, nc):
                return IrInt(0)
        return IrInt(1)
```

Export `IrAnd` from `src/lexic/ir/__init__.py` (import + `__all__`).

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/lexic/ir/test_action.py -k irand -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
uv run ruff check src/lexic/ir/action.py src/lexic/ir/__init__.py
git add src/lexic/ir/action.py src/lexic/ir/__init__.py tests/unit/lexic/ir/test_action.py
git commit -m "ir/action: add IrAnd conjunction"
```

---

## Task 5: Generalize `IrCond` to a node-valued `test`

**Files:**
- Modify: `src/lexic/ir/action.py` (`IrCond`, ~lines 221-235)
- Test: `tests/unit/lexic/ir/test_action.py` (replace existing `IrCond` tests)

- [ ] **Step 1: Replace the failing tests**

In `tests/unit/lexic/ir/test_action.py`, **replace** the two existing tests
`test_ircond_evaluates_then_when_truthy` and `test_ircond_evaluates_else_when_falsy`
(under `# ── IrCond ──`) with:

```python
def test_ircond_evaluates_then_when_test_truthy():
    op = IrCond[IrStr](
        test=IrCompare(IrInt(1), Cmp.EQ, IrInt(1)),
        then_op=IrLiteral("yes"),
        else_op=IrLiteral("no"),
    )
    assert op.eval(IrNone, IrNone, ()) == "yes"


def test_ircond_evaluates_else_when_test_falsy():
    op = IrCond[IrStr](
        test=IrCompare(IrInt(1), Cmp.EQ, IrInt(0)),
        then_op=IrLiteral("yes"),
        else_op=IrLiteral("no"),
    )
    assert op.eval(IrNone, IrNone, ()) == "no"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/lexic/ir/test_action.py -k ircond -v`
Expected: FAIL — `IrCond` has no `test` field (still `field`).

- [ ] **Step 3: Reshape `IrCond`**

Replace the `IrCond` class in `src/lexic/ir/action.py` with:

```python
@dataclass(frozen=True, slots=True, init=False, repr=False)
class IrCond[Ir_co: IrSelf](IrComposite[Ir_co]):
    """If ``test`` evaluates truthy, eval ``then_op``; else ``else_op``.

    ``test`` is any IrNode whose ``eval`` yields a truthy/falsy value
    (e.g. :class:`IrCompare`, :class:`IrAnd`). Both branches share ``Ir_co``.

    :ivar test: Predicate node evaluated for truthiness.
    :ivar then_op: Branch taken when ``test`` is truthy.
    :ivar else_op: Branch taken when ``test`` is falsy.
    """

    _child_attrs: ClassVar[tuple[str, ...]] = ("test", "then_op", "else_op")
    test: IrNode
    then_op: IrNode[Ir_co]
    else_op: IrNode[Ir_co]

    def eval(self, d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> Ir_co:
        """Branch on the truthiness of ``self.test.eval(d, n, nc)``."""
        branch = self.then_op if self.test.eval(d, n, nc) else self.else_op
        return branch.eval(d, n, nc)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/lexic/ir/test_action.py -k ircond -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Run the full suite (no regressions; zero prior `IrCond` callers in `src/`)**

Run: `uv run pytest tests/ -q`
Expected: PASS — full suite green.

- [ ] **Step 6: Commit**

```bash
uv run ruff check src/lexic/ir/action.py
git add src/lexic/ir/action.py tests/unit/lexic/ir/test_action.py
git commit -m "ir/action: generalize IrCond field:str -> test:IrNode"
```

---

## Task 6: Canonical-op amendment (living docs)

**Files:**
- Modify: `CLAUDE.md`
- Append: `.wiki/lexic/log.md`

- [ ] **Step 1: Update the `nodes.py` line in CLAUDE.md**

In `CLAUDE.md`, find:

```
    nodes.py            IrSelf mixin; IrNode[Ir_co] generic ABC; IrType/IrStr/IrTuple
                        typed bases; IrLeaf/IrStructure/IrCollection/IrComposite;
```

Replace `IrType/IrStr/IrTuple` with `IrType/IrStr/IrInt/IrTuple`.

- [ ] **Step 2: Update the `action.py` line in CLAUDE.md**

Find:

```
    action.py           Action-algebra nodes: IrField, IrCallable, IrChild, IrChildren,
                        IrConcat, IrJoin, IrCond, IrReturn, IrAction; default bodies
                        IrPass, IrWalk, IrRaise, IrEmit, IrRebuild
```

Replace the first two lines with:

```
    action.py           Action-algebra nodes: IrField (out-typed), IrCallable, IrChild,
                        IrChildren, IrConcat, IrJoin, IrCond (test:IrNode), IrCompare,
                        IrAnd, Cmp, IrReturn, IrAction; default bodies
```

- [ ] **Step 3: Record the amendment in the wiki log**

Append to `.wiki/lexic/log.md` (verify the path exists; it is the wiki change log per CLAUDE.md):

```markdown
- 2026-05-29 — Canonical-op amendment (Phase 0a). The frozen op list is corrected
  (`IrLiteral`, not `IrText`) and extended: added `IrInt`, `IrCompare`, `IrAnd`;
  `IrCond` reshaped (`field:str` → `test:IrNode`); `IrField` gains an `out` type
  (default `IrStr`, e.g. `IrInt`). A truth value is `IrInt ∈ IrQuantifier(0,1)` —
  no `IrBool`. `IrRanged` (runtime bounded value) recorded as the deferred home
  for unified complement-negation and Slice-C constraint codegen. `IrCallable`
  remains the sanctioned escape hatch. See
  docs/superpowers/specs/2026-05-29-phase-0-honest-ir-foundation-design.md §0a.
```

- [ ] **Step 4: Verify and commit**

```bash
uv run pytest tests/ -q
git add CLAUDE.md .wiki/lexic/log.md
git commit -m "docs: canonical-op amendment for Phase 0a algebra"
```

---

## Self-Review

**Spec coverage (§0a):**
- §0a.1 `IrInt` → Task 1; `IrCompare` → Task 3; `IrAnd` → Task 4. ✓
- §0a.2 generalized `IrCond` → Task 5. ✓
- §0a.3 `IrField` widening (via `out`) → Task 2. ✓
- §0a.4 no `IrBool` (truth = `IrInt(0/1)`) → enforced by `IrCompare`/`IrAnd` returning `IrInt`; `IrRanged`/Y recorded in Task 6 log, built nowhere. ✓
- §0a.5 canonical-op amendment → Task 6. ✓
- §0a.6 tests → Tasks 1–5. ✓
- "`IrNot` stays grammar-only" → no task needed (no change). ✓

**Placeholder scan:** none — every code step has complete code; every run step has an exact command + expected result.

**Type consistency:** `IrInt` (Task 1) used by `IrField(out=IrInt)` (Task 2), `IrCompare`/`IrAnd` (Tasks 3–4), all returning `IrInt`; `IrCond.test` (Task 5) consumes `IrCompare`/`IrAnd`. `IrField("name", IrInt)` positional form is consistent across Tasks 2–3. No subscript form (`IrField[IrInt]`) is used anywhere after Task 2 drops the generic.

**Dependency order:** Task 1 (IrInt) precedes Tasks 2–4 that use it; Task 5's tests use `IrCompare` from Task 3. Order is correct.
