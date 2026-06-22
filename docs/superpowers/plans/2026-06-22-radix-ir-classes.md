# Radix IR Classes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the two new IR nodes (`IrChr`, `IrUnradix`) and reshape the bounds nodes (`IrQuantifier`, `IrRange`, `IrCharClass`) onto a sibling `IrBounds` base with code-point endpoints — the class layer only.

**Architecture:** `IrQuantifier` and `IrRange` stop being a subclass chain and become *siblings* under a new abstract `IrBounds` base that hosts type-aware `__eq__`/`__ne__`/`__hash__` and `__contains__`. `IrRange` endpoints become required `IrChr` code points; `IrCharClass` holds `IrRange | IrChr`. `IrChr` (a value-carrying `IrInt`) and `IrUnradix` (a radix-decode transform) are new leaves. All code is lifted verbatim from the validated prototype `_validate_radix.py`.

**Tech Stack:** Python 3.13 (PEP 695 generics, `dataclass_transform`), pytest, pyright, pylint, `uv`.

---

## Scope & expected fallout (read first)

This plan changes **shared** IR nodes. Per the spec it is deliberately scoped to **the IR class layer only** — it does **not** touch consumers or grammars.

- **In scope:** `src/lexic/ir/base.py` (`IrChr`), `src/lexic/ir/action.py` (`IrUnradix`), `src/lexic/ir/nodes.py` (`IrBounds` + reshaped `IrQuantifier`/`IrRange`/`IrCharClass`), `src/lexic/ir/__init__.py` (exports), and the three mirror test files.
- **Out of scope (separate follow-on plans):** the ABNF-2 reduce migration, grammar restructure, `model_emitter` import, and every construction/consumer site (`grammars/abnf_2.py`, `grammars/json.py`, `parsing/meta_parser.py`, `ir/derive.py`, `codegen/`, `generate.py`, …).
- **Expected red:** after this plan, `uv run pytest tests/` and a repo-wide `pyright` **will** report failures in those out-of-scope modules (they construct `IrRange("a","z")` with `str`, which now mis-types, and some rely on the old shapes). That is anticipated and handled by the follow-on plans. **Verification in this plan is scoped to the three edited source files and their three mirror test files**, listed per task.

**Commit policy:** This project's commits belong entirely to the user. Each task ends with a **Stage** step (`git add`) — do **not** run `git commit`. Suggested commit messages are provided for the user; never add a `Co-Authored-By` line.

---

## File Structure

| File | Responsibility | Change |
|---|---|---|
| `src/lexic/ir/base.py` | IR spine + primitive leaves | **Add** `IrChr` (after `IrInt`) |
| `src/lexic/ir/action.py` | action-algebra nodes | **Add** `IrUnradix` (near `IrField`) |
| `src/lexic/ir/nodes.py` | concrete grammar-AST nodes | **Add** `IrBounds`; **reshape** `IrQuantifier`/`IrRange` as siblings; **retype** `IrCharClass` |
| `src/lexic/ir/__init__.py` | public IR surface | **Export** `IrChr`, `IrUnradix`, `IrBounds` |
| `tests/unit/lexic/ir/test_base.py` | mirror of `ir/base.py` | **Add** `IrChr` tests |
| `tests/unit/lexic/ir/test_action.py` | mirror of `ir/action.py` | **Add** `IrUnradix` tests |
| `tests/unit/lexic/ir/test_nodes.py` | mirror of `ir/nodes.py` | **Port** old-hierarchy tests; **add** sibling/eq/membership tests |

---

## Task 1: `IrChr` value-carrying code point

**Files:**
- Modify: `src/lexic/ir/base.py` (insert after `IrInt`, current line 485)
- Modify: `src/lexic/ir/__init__.py` (base import block + `__all__`)
- Test: `tests/unit/lexic/ir/test_base.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/unit/lexic/ir/test_base.py` (ensure the import line at the top of the file includes `IrChr`, `IrInt`, `IrNone`, `IrStr` from `lexic.ir.base`, `UnsupportedConstructError` from `lexic.exceptions`, and `import pytest`):

```python
def test_irchr_from_glyph_and_int_are_equal():
    assert IrChr("A") == IrChr(0x41)


def test_irchr_str_is_glyph_and_repr_is_codegen():
    assert str(IrChr(0x41)) == "A"
    assert repr(IrChr(0x41)) == "IrChr(65)"


def test_irchr_is_leaf_kind_distinct_from_irint():
    assert IrChr(0x41) != IrInt(0x41)  # distinct leaf kinds never compare equal
    assert IrChr(0x41) == 0x41  # but a leaf still matches its plain int


def test_irchr_eval_returns_glyph_irstr():
    assert IrChr(0x41).eval(IrNone, IrNone, ()) == IrStr("A")


def test_irchr_multichar_glyph_raises():
    with pytest.raises(UnsupportedConstructError):
        IrChr("AB")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/lexic/ir/test_base.py -k irchr -q`
Expected: FAIL / ERROR with `ImportError: cannot import name 'IrChr'`.

- [ ] **Step 3: Implement `IrChr`**

In `src/lexic/ir/base.py`, immediately after the `IrInt` class (current line 485), add:

```python
class IrChr(IrInt):
    """A code point — build from a 1-char glyph or an int; stores the ordinal."""

    def __new__(cls, value: int | str = 0) -> Self:
        """Build from a 1-char glyph or an int.

        :raises UnsupportedConstructError: If a string of length != 1 is given.
        """
        if isinstance(value, str):
            if len(value) != 1:
                msg = f"IrChr expects one glyph, got {value!r}"
                raise UnsupportedConstructError(msg)
            value = ord(value)
        return super().__new__(cls, value)

    def __str__(self) -> str:
        """The glyph for this code point."""
        return chr(int(self))

    def eval(self, _d: IrSelf, _n: IrSelf, _nc: Sequence[IrSelf], /) -> IrStr:
        """Evaluate to the glyph as an ``IrStr`` (emit-side use)."""
        return IrStr(chr(int(self)))
```

- [ ] **Step 4: Export `IrChr`**

In `src/lexic/ir/__init__.py`, add `IrChr` to the `from lexic.ir.base import (...)` block (alphabetical, between `IrAtom` and `IrInt`) and add `"IrChr"` to `__all__`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/unit/lexic/ir/test_base.py -k irchr -q`
Expected: PASS (5 passed).

- [ ] **Step 6: Quality gate**

Run: `uv run pyright src/lexic/ir/base.py && uv run pylint src/lexic/ir/base.py`
Expected: pyright `0 errors`; pylint `10.00/10`.

- [ ] **Step 7: Stage (do not commit)**

```bash
git add src/lexic/ir/base.py src/lexic/ir/__init__.py tests/unit/lexic/ir/test_base.py
```
Suggested commit message (user runs): `feat(ir): add IrChr value-carrying code point`

---

## Task 2: `IrUnradix` radix-decode transform

**Files:**
- Modify: `src/lexic/ir/action.py` (insert after the `IrField` class, current line ~110)
- Modify: `src/lexic/ir/__init__.py` (action import block + `__all__`)
- Test: `tests/unit/lexic/ir/test_action.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/unit/lexic/ir/test_action.py` (ensure imports include `IrUnradix` from `lexic.ir.action`; `IrChr`, `IrInt`, `IrNone`, `IrStr` from `lexic.ir.base`; `UnsupportedConstructError` from `lexic.exceptions`; `import pytest`):

```python
def test_irunradix_decodes_decimal():
    assert IrUnradix(10, IrInt).eval(IrNone, IrStr("12"), ()) == IrInt(12)


def test_irunradix_decodes_hex_to_irchr():
    assert IrUnradix(16, IrChr).eval(IrNone, IrStr("41"), ()) == IrChr(0x41)


def test_irunradix_empty_string_raises():
    with pytest.raises(UnsupportedConstructError):
        IrUnradix(10, IrInt).eval(IrNone, IrStr(""), ())


def test_irunradix_bad_digit_for_base_raises():
    with pytest.raises(UnsupportedConstructError):
        IrUnradix(2, IrInt).eval(IrNone, IrStr("2"), ())  # '2' is out of base 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/lexic/ir/test_action.py -k irunradix -q`
Expected: FAIL / ERROR with `ImportError: cannot import name 'IrUnradix'`.

- [ ] **Step 3: Implement `IrUnradix`**

In `src/lexic/ir/action.py`, after the `IrField` class, add (all required names — `IrInt`, `IrScalar`, `IrNamedTuple`, `IrSelf`, `ClassVar`, `Sequence`, `UnsupportedConstructError` — are already imported in this module):

```python
class IrUnradix(IrNamedTuple[int, type[IrScalar]]):
    """Decode the focus digit string to ``out(value)`` via ord-arithmetic.

    The inverse of the emit-side radix spelling: reads its focus ``n`` as a
    digit string and returns ``out`` (an ``IrScalar`` subtype) of the value.
    """

    _child_attrs: ClassVar[tuple[str, ...]] = ()
    base: int
    out: type[IrScalar] = IrInt

    def eval(self, _d: IrSelf, n: IrSelf, _nc: Sequence[IrSelf], /) -> IrScalar:
        """Decode ``str(n)`` in ``self.base`` and wrap it in ``self.out``.

        :raises UnsupportedConstructError: On an empty string or a bad digit.
        """
        s = str(n)
        if not s:
            raise UnsupportedConstructError("IrUnradix: empty digit string")
        acc = 0
        for c in s:
            v = ord(c) - 0x30 if "0" <= c <= "9" else ord(c.upper()) - 0x41 + 10
            if not 0 <= v < self.base:
                raise UnsupportedConstructError(f"bad digit {c!r} for base {self.base}")
            acc = acc * self.base + v
        return self.out(acc)
```

- [ ] **Step 4: Export `IrUnradix`**

In `src/lexic/ir/__init__.py`, add `IrUnradix` to the `from lexic.ir.action import (...)` block and add `"IrUnradix"` to `__all__`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/unit/lexic/ir/test_action.py -k irunradix -q`
Expected: PASS (4 passed).

- [ ] **Step 6: Quality gate**

Run: `uv run pyright src/lexic/ir/action.py && uv run pylint src/lexic/ir/action.py`
Expected: pyright `0 errors`; pylint `10.00/10`.

- [ ] **Step 7: Stage (do not commit)**

```bash
git add src/lexic/ir/action.py src/lexic/ir/__init__.py tests/unit/lexic/ir/test_action.py
```
Suggested commit message (user runs): `feat(ir): add IrUnradix radix-decode transform`

---

## Task 3: `IrBounds` base + sibling `IrQuantifier`/`IrRange`

**Files:**
- Modify: `src/lexic/ir/nodes.py` (base import; replace `IrRange` class; remove old `IrQuantifier` class)
- Modify: `src/lexic/ir/__init__.py` (nodes import block + `__all__`)
- Test: `tests/unit/lexic/ir/test_nodes.py` (port two old-shape tests; re-spell the `IrRange` tests; add new ones)

- [ ] **Step 1: Port and add the failing tests**

First, **ensure imports** in `tests/unit/lexic/ir/test_nodes.py`: add `IrChr` to the `from lexic.ir.base import (...)` line, add `IrBounds` to the `from lexic.ir.nodes import (...)` line, and ensure `import pytest` is present.

**Port** the existing IrRange tests (current lines 498-520) — keep each assertion's intent, swap `str` endpoints for `IrChr`:

```python
def test_irrange_construction_and_fields():
    """IrRange stores IrChr lo/hi as accessible fields."""
    r = IrRange(IrChr("a"), IrChr("z"))
    assert r.lo == IrChr("a")
    assert r.hi == IrChr("z")


def test_irrange_children_is_empty():
    """IrRange has _child_attrs=() — walkers never descend into bounds."""
    assert not IrRange(IrChr("a"), IrChr("z")).children()


def test_irrange_positional_access():
    """IrRange is a named tuple — positional indexing works."""
    r = IrRange(IrChr("a"), IrChr("z"))
    assert r[0] == IrChr("a")
    assert r[1] == IrChr("z")


def test_irrange_repr_is_codegen():
    """repr(IrRange(...)) reproduces the constructor call over code points."""
    assert repr(IrRange(IrChr("a"), IrChr("z"))) == "IrRange(IrChr(97), IrChr(122))"
```

**Port** `test_irquantifier_is_a_irrange` (current lines 533-536) — the relationship is inverted; replace the whole function with:

```python
def test_irquantifier_and_irrange_are_disjoint_siblings():
    """IrQuantifier and IrRange are siblings under IrBounds — neither IS-A the other."""
    assert not isinstance(IrQuantifier(), IrRange)
    assert not isinstance(IrRange(IrChr("a"), IrChr("z")), IrQuantifier)
    assert not issubclass(IrQuantifier, IrRange)
    assert issubclass(IrQuantifier, IrBounds)
    assert issubclass(IrRange, IrBounds)
```

**Port** `test_irquantifier_equals_irrange_same_payload` (current lines 539-546) — equality is now type-aware; replace the whole function with:

```python
def test_bounds_equality_is_type_aware():
    """A count range and a same-numbered code-point range never compare equal."""
    assert IrQuantifier(65, 90) != IrRange(IrChr(65), IrChr(90))
    assert IrQuantifier(1, 1) == IrQuantifier(1, 1)
    assert IrRange(IrChr("A"), IrChr("Z")) == IrRange(IrChr(0x41), IrChr(0x5A))
```

**Add** these new tests (anywhere in the IrRange/IrQuantifier section):

```python
def test_bounds_are_hashable():
    r = IrRange(IrChr(65), IrChr(90))
    assert r in {r}
    assert hash(IrQuantifier(1, 1)) == hash(IrQuantifier(1, 1))


def test_quantifier_membership():
    assert 5 in IrQuantifier(1, 10)
    assert 11 not in IrQuantifier(1, 10)
    assert 100 in IrQuantifier(1, IrNone)  # open upper bound is unbounded


def test_range_membership():
    assert IrChr(0x42) in IrRange(IrChr(0x41), IrChr(0x5A))
    assert IrChr(0x60) not in IrRange(IrChr(0x41), IrChr(0x5A))


def test_quantifier_defaults_to_one_one():
    assert IrQuantifier() == IrQuantifier(1, 1)


def test_range_requires_endpoints():
    """IrRange endpoints are required — no NUL placeholder default."""
    no_args: list[IrChr] = []
    with pytest.raises(TypeError):
        IrRange(*no_args)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/lexic/ir/test_nodes.py -q`
Expected: FAIL / ERROR — `ImportError: cannot import name 'IrBounds'` (and, once imports resolve, the ported assertions fail against the old shape).

- [ ] **Step 3: Implement the reshape in `src/lexic/ir/nodes.py`**

3a. **Add `IrChr` to the base import.** Change the `from lexic.ir.base import (...)` block to include `IrChr`:

```python
from lexic.ir.base import (
    IrAtom,
    IrChr,
    IrLeaf,
    IrNamedTuple,
    IrNoneType,
    IrSeq,
    IrStr,
)
```

3b. **Replace the entire `IrRange` class** (current lines 103-119) with these **three** classes, in this order:

```python
class IrBounds(IrLeaf, IrNamedTuple[int, "int | IrNoneType"]):
    """Shared ``(lo, hi)`` bounds — type-aware equality plus in-bounds membership.

    Abstract base for :class:`IrQuantifier` (int counts) and :class:`IrRange`
    (code-point spans). The two are siblings, not a chain — neither is
    substitutable for the other. ``lo``/``hi`` are scalar payload, not IR-node
    children, so ``_child_attrs`` is empty.
    """

    _child_attrs: ClassVar[tuple[str, ...]] = ()
    lo: int
    hi: int | IrNoneType

    def __eq__(self, other: object) -> bool:
        """Equal only to the same bounds subtype with equal endpoints."""
        if type(self) is not type(other):
            return False
        return super().__eq__(other)

    def __ne__(self, other: object) -> bool:
        """Negation of :meth:`__eq__` (``tuple`` supplies its own ``__ne__``)."""
        return not self == other

    def __hash__(self) -> int:
        """Hash by endpoint tuple (defining ``__eq__`` nulls the inherited hash)."""
        return super().__hash__()

    def __contains__(self, value: object) -> bool:
        """``lo <= value <= hi``; ``hi=IrNone`` means unbounded above."""
        if not isinstance(value, int):
            return False
        hi = self.hi
        if isinstance(hi, IrNoneType):
            return self.lo <= value
        return self.lo <= value <= hi


class IrQuantifier(IrBounds):
    """Repetition bounds for an ``IrItem`` — int counts; ``hi`` may be ``IrNone``.

    - ``IrQuantifier(1, 1)`` — exactly once (the default; no postfix operator).
    - ``IrQuantifier(0, 1)`` — optional (``?``).
    - ``IrQuantifier(0, IrNone)`` — zero-or-more (``*``).
    - ``IrQuantifier(1, IrNone)`` — one-or-more (``+``).
    - ``IrQuantifier(m, n)`` — between ``m`` and ``n`` times.
    """

    _child_attrs: ClassVar[tuple[str, ...]] = ()
    lo: int = 1
    hi: int | IrNoneType = 1


class IrRange(IrBounds):
    """Inclusive char range — ``IrChr`` code-point endpoints, always closed.

    Endpoints are required (no defaults): a range is always built from explicit
    code points, so there is no placeholder bound.
    """

    _child_attrs: ClassVar[tuple[str, ...]] = ()
    lo: IrChr
    hi: IrChr
```

3c. **Remove the now-duplicate old `IrQuantifier` class** (current lines 141-157 — the one that reads `class IrQuantifier(IrRange):`). It is fully replaced by the definition in 3b.

3d. **Update `__all__`** in `nodes.py` to add `"IrBounds"` (keep `"IrRange"`, `"IrQuantifier"`).

- [ ] **Step 4: Export `IrBounds`**

In `src/lexic/ir/__init__.py`, add `IrBounds` to the `from lexic.ir.nodes import (...)` block and add `"IrBounds"` to `__all__`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/unit/lexic/ir/test_nodes.py -q`
Expected: PASS (all tests in the file, including the ported and new ones).

- [ ] **Step 6: Quality gate**

Run: `uv run pyright src/lexic/ir/nodes.py && uv run pylint src/lexic/ir/nodes.py`
Expected: pyright `0 errors`; pylint `10.00/10`.

- [ ] **Step 7: Stage (do not commit)**

```bash
git add src/lexic/ir/nodes.py src/lexic/ir/__init__.py tests/unit/lexic/ir/test_nodes.py
```
Suggested commit message (user runs): `refactor(ir): sibling IrBounds base for IrQuantifier and IrRange`

---

## Task 4: `IrCharClass` over `IrRange | IrChr`

**Files:**
- Modify: `src/lexic/ir/nodes.py` (`IrCharClass` element type + docstring)
- Test: `tests/unit/lexic/ir/test_nodes.py` (add a code-point element test)

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/lexic/ir/test_nodes.py`:

```python
def test_charclass_holds_codepoints_and_ranges():
    """IrCharClass is the variadic union of IrChr code points and IrRange spans."""
    cc = IrCharClass(IrChr(0x41), IrRange(IrChr(0x30), IrChr(0x39)))
    assert cc[0] == IrChr(0x41)
    assert cc[1] == IrRange(IrChr(0x30), IrChr(0x39))
```

- [ ] **Step 2: Run test to verify it passes at runtime but mis-types**

Run: `uv run pytest tests/unit/lexic/ir/test_nodes.py -k charclass_holds_codepoints -q`
Expected: PASS at runtime (`IrSeq` does not enforce element types at runtime), but `uv run pyright src/lexic/ir/nodes.py` would flag `IrChr` as not assignable to `IrRange | IrStr` — confirming the element type must change.

- [ ] **Step 3: Retype `IrCharClass`**

In `src/lexic/ir/nodes.py`, change the `IrCharClass` declaration (current line 122) and its docstring. Replace the class header and docstring with:

```python
class IrCharClass(IrSeq[IrRange | IrChr], IrAtom):
    """Character class over code points — ``IrRange`` spans and single ``IrChr``.

    The node IS its element tuple: :class:`IrRange` entries for explicit
    ``x-y`` ranges, single :class:`~lexic.ir.base.IrChr` code points otherwise —
    ``[a0-9]`` → ``IrCharClass(IrChr("a"), IrRange(IrChr("0"), IrChr("9")))``.

    Brackets are NOT stored — the flavour renderer emits them. Negation is NOT
    stored — ``[^...]`` parses to ``IrNot(IrCharClass(...))``; the negation hands
    its mark to the class action via the argument channel. Glyph/escape spelling
    happens only at emit time, per flavour.
    """
```

(Leave the `IrCharClass` body — it has none beyond the docstring — and the rest of the file unchanged.)

- [ ] **Step 4: Run test + quality gate**

Run: `uv run pytest tests/unit/lexic/ir/test_nodes.py -q && uv run pyright src/lexic/ir/nodes.py && uv run pylint src/lexic/ir/nodes.py`
Expected: pytest PASS (whole file); pyright `0 errors`; pylint `10.00/10`.

- [ ] **Step 5: Stage (do not commit)**

```bash
git add src/lexic/ir/nodes.py tests/unit/lexic/ir/test_nodes.py
```
Suggested commit message (user runs): `refactor(ir): IrCharClass holds IrRange | IrChr code points`

---

## Final verification (scoped)

- [ ] **Run the three mirror test files together**

Run: `uv run pytest tests/unit/lexic/ir/test_base.py tests/unit/lexic/ir/test_action.py tests/unit/lexic/ir/test_nodes.py -q`
Expected: all PASS.

- [ ] **Quality gate on every edited source file**

Run: `uv run pyright src/lexic/ir/base.py src/lexic/ir/action.py src/lexic/ir/nodes.py src/lexic/ir/__init__.py && uv run pylint src/lexic/ir/base.py src/lexic/ir/action.py src/lexic/ir/nodes.py`
Expected: pyright `0 errors`; pylint `10.00/10`.

- [ ] **Confirm the public surface**

Run: `uv run python -c "from lexic.ir import IrChr, IrUnradix, IrBounds, IrQuantifier, IrRange, IrCharClass; print('ok')"`
Expected: prints `ok`.

> **Reminder:** a repo-wide `uv run pytest tests/` and repo-wide pyright will show failures in out-of-scope modules (consumers/grammars still on the old shapes). That is expected per **Scope & expected fallout** and is addressed by the follow-on consumer-migration and cutover plans — not here.
