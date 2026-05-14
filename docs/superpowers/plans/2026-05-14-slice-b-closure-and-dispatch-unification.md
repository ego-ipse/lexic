# Slice B closure + dispatch unification — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close Slice B (positional token reservation + cleanup) while inverting the IR dispatch architecture: intrinsic data lives on the node, all string emission flows through a unified `IrEmitter` hierarchy. Lexic gains `.lark` as a third user-facing grammar format.

**Architecture:** `IrNode` becomes an ABC with structural protocol (`children`, `rebuild`, `emit`). `IrDispatch` gains `IrEmitter` (T=str) as its third canonical instantiation; `Flavour` *is* an `IrEmitter[IrNode]` populated via per-type action tables. `FlavourEmitter` ABC + concrete emitters are deleted. `Quantifier` → `IrQuantifier` (an IrNode leaf). `LarkFlavour` joins `GbnfFlavour` and `AbnfFlavour` as a first-class peer.

**Tech Stack:** Python 3.11+ · Pydantic v2 · Lark (Earley) · uv · pytest · ruff · pylint

**Spec:** `docs/superpowers/specs/2026-05-14-slice-b-closure-and-dispatch-unification-design.md`

---

## File structure

### Created
- `src/lexic/grammars/lark/__init__.py` — package marker, exports `LarkFlavour`
- `src/lexic/grammars/lark/flavour.py` — `LarkFlavour(Flavour)` with action table + quantifier_symbols
- `src/lexic/grammars/lark/meta_grammar.py` — Lark meta-grammar string for parsing `.lark` files
- `src/lexic/grammars/lark/escapes.py` — `LarkEscapes(EscapeCodec)`
- `tests/unit/lexic/grammars/lark/test_init_lark.py`
- `tests/unit/lexic/grammars/lark/test_flavour.py`
- `tests/unit/lexic/grammars/lark/test_escapes.py`
- `tests/integration/test_compile_grammar_lark.py`
- `tests/integration/test_token_reservation.py`
- `resources/ground_truth/arithmetic.lark` (Lark version of `arithmetic.gbnf` for round-trip parity)

### Modified
- `src/lexic/ir/nodes.py` — `IrNode` becomes ABC; `Quantifier` renamed `IrQuantifier`; every concrete node implements `children/rebuild/emit`
- `src/lexic/ir/walk.py` — adds `IrEmitter[_N]` + `IrMetaEmitter`; deletes `_CHILDREN`/`_REBUILD`/`_DUMP`
- `src/lexic/ir/emit.py` — keeps only `render_specs()`; `FlavourEmitter` ABC deleted
- `src/lexic/grammars/flavour.py` — `Flavour` subclasses `IrEmitter[IrNode]`; gains `action`, `quantifier_symbols`, `pre_parse_check`
- `src/lexic/grammars/gbnf/flavour.py` — populates `action` table with renderers; adds `pre_parse_check`
- `src/lexic/grammars/abnf/flavour.py` — populates `action` table with renderers (prefix-quantifier ordering)
- `src/lexic/grammars/__init__.py` — registers `LarkFlavour` alongside the others
- `src/lexic/parsing/lark_builder.py` — collapses to `render_specs(specs, LarkFlavour())`
- `src/lexic/parsing/meta_parser.py` — calls `flavour.pre_parse_check(text)` before Lark parse
- `src/lexic/base.py` — `to_grammar()` switches from importing `GbnfEmitter` to using `GbnfFlavour()`
- `src/lexic/ir/derive.py` — `Quantifier(0, …)` and `Quantifier(1,1)` references → `IrQuantifier(…)`
- `src/lexic/parsing/transformer/build_transformer.py` — `Quantifier(1, 1)` → `IrQuantifier(1, 1)`
- `src/lexic/generate.py` — `Quantifier(1, 1)` → `IrQuantifier(1, 1)`
- `src/lexic/codegen/model_emitter.py` — emits `IrQuantifier(...)` in generated source instead of `Quantifier(...)`
- `src/lexic/codegen/aliases.py` — `bounds_to_quantifier` call sites switch to a small private helper or flavour-based renderer
- `tests/unit/lexic/ir/test_walk.py` — adjusted for protocol-on-node
- `tests/unit/lexic/ir/test_nodes.py` — adds protocol method tests
- `tests/unit/lexic/grammars/test_flavour.py` — adjusts to new Flavour shape
- `tests/integration/test_cross_flavour.py` — adds Lark conversion cases
- `tests/integration/test_layering_invariants.py` — adjusted import-edge assertions
- `.wiki/lexic/architecture.md` · `.wiki/lexic/flavour-system.md` · `.wiki/lexic/ir-shapes.md` · `.wiki/lexic/decisions.md` · `.wiki/log.md`
- `CLAUDE.md` — updated runtime→codegen import-exception list

### Deleted
- `src/lexic/utils/quantifiers.py` + `tests/unit/lexic/utils/test_quantifiers.py`
- `src/lexic/ir/helpers.py` + `tests/unit/lexic/ir/test_helpers.py`
- `src/lexic/grammars/gbnf/emitter.py` + `tests/unit/lexic/grammars/gbnf/test_emitter.py`
- `src/lexic/grammars/abnf/emitter.py` + `tests/unit/lexic/grammars/abnf/test_emitter.py`
- `.wiki/lexic/slice-b-status.md` (slice closes)

---

## Flavour-as-singleton convention

Flavours carry only class-level state (the `action` table, `quantifier_symbols`,
the punctuation constants). Instantiation is `cls()` with no args. To avoid
the class-vs-instance ambiguity that would otherwise dog every call site
(does `LarkFlavour` mean the class or an instance? `flavour.visit(node)`
needs an instance because `visit` uses `self.action`), each flavour module
exports a module-level singleton:

```
src/lexic/grammars/gbnf/flavour.py   exports  GbnfFlavour  AND  GBNF = GbnfFlavour()
src/lexic/grammars/abnf/flavour.py   exports  AbnfFlavour  AND  ABNF = AbnfFlavour()
src/lexic/grammars/lark/flavour.py   exports  LarkFlavour  AND  LARK = LarkFlavour()
src/lexic/grammars/__init__.py       re-exports GBNF, ABNF, LARK
```

Consumers that call `flavour.visit(node)` use the singleton
(base.py.to_grammar, lark_builder.build_lark, cross-flavour transpile
tests, render_specs callers). `CompiledGrammar.flavour` is the singleton
matching the source flavour. Adopt from Task 3.3 onwards; each `action`
dict population task also defines the singleton in the same file.

**Exception — `meta_parser.py` keeps the class form.** Meta-parser uses
only class-level attributes (`flavour.meta_grammar`, `flavour.line_comment`,
`parse_quantifier`/`parse_charclass`/`normalize_literal`/`pre_parse_check`
— all `@classmethod` or `@staticmethod`). It never calls `.visit()`. The
`MetaGrammarParser.for_flavour(flavour_cls)` cache is keyed on the class.
Don't change it; pass the class as before.

---

## Conventions for every task

- Always prefix commands with `uv run` (e.g. `uv run pytest -q`, `uv run ruff check src/ tests/`).
- Before manual fixes after edits: run `tools/auto_fix.sh` first.
- Test mirror rule: `src/lexic/foo/bar.py` ↔ `tests/unit/lexic/foo/test_bar.py`. For `__init__.py` modules, the test file is `test_init_<package>.py`.
- Never include `Co-Authored-By:` in commit messages.
- After every task: `uv run pytest -q` must pass before commit.
- If `ruff` flags `generated/` files, fix the template (`src/lexic/codegen/model_emitter.py`), not the file.

---

## Step 1 — IrNode structural protocol

The current `IrNode` is a `TypeAlias` union. Step 1 promotes it to an ABC with three methods (`children`, `rebuild`, `emit`), then deletes the `_CHILDREN`/`_REBUILD`/`_DUMP` central tables in `walk.py`.

### Task 1.1: Promote `IrNode` to an ABC base class

**Files:**
- Modify: `src/lexic/ir/nodes.py`
- Test: `tests/unit/lexic/ir/test_nodes.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/lexic/ir/test_nodes.py`:

```python
"""Tests for lexic.ir.nodes — structural protocol on IrNode."""

from __future__ import annotations

import pytest

from lexic.ir.nodes import (
    IrAlternation,
    IrAst,
    IrCharClass,
    IrGroup,
    IrItem,
    IrLiteral,
    IrNode,
    IrRule,
    IrRuleRef,
    IrSequence,
    Quantifier,
)


def test_irnode_is_abc_base_class():
    """Every concrete IR node inherits from IrNode."""
    for cls in (
        IrAst, IrRule, IrAlternation, IrSequence, IrItem, IrGroup,
        IrLiteral, IrCharClass, IrRuleRef,
    ):
        assert issubclass(cls, IrNode), f"{cls.__name__} must inherit IrNode"


def test_irnode_default_children_is_empty_tuple():
    """Leaves inherit empty-tuple default."""
    assert IrLiteral("x").children() == ()
    assert IrCharClass("a-z").children() == ()
    assert IrRuleRef("foo").children() == ()


def test_irnode_default_rebuild_is_identity():
    """Leaves inherit identity rebuild."""
    leaf = IrLiteral("x")
    assert leaf.rebuild(()) is leaf
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/lexic/ir/test_nodes.py -v`
Expected: FAIL — `IrNode` is a TypeAlias, not a class.

- [ ] **Step 3: Promote `IrNode` to ABC**

Replace `src/lexic/ir/nodes.py` entirely:

```python
"""IR AST node dataclasses — canonical, frozen, hashable.

Every IR node implements the structural protocol from IrNode:
  - children() -> tuple[IrNode, ...]   children in traversal order
  - rebuild(new_children) -> IrNode    reconstruct under transformation
  - emit(indent=0) -> str              default string rendering (debug)

Flavour-specific rendering bypasses `emit()` via the per-flavour action
dispatch table on `Flavour` (an IrEmitter subclass).
"""

from __future__ import annotations

from abc import ABC
from dataclasses import dataclass, field
from typing import TypeAlias


class IrNode(ABC):
    """Structural protocol every IR node implements."""

    def children(self) -> tuple[IrNode, ...]:
        """Children in traversal order. Default: leaf — no children."""
        return ()

    def rebuild(self, new_children: tuple[IrNode, ...]) -> IrNode:
        """Reconstruct with new children. Default: identity (leaves)."""
        return self

    def emit(self, indent: int = 0) -> str:
        """Default string rendering used by IrMetaEmitter.

        Leaves return repr(self), ignoring indent: they appear inline
        inside a branch's emit() output and must not inject whitespace.
        Branches override to render themselves at `'  ' * indent`, then
        recurse with `indent + 1`. (Matches legacy _DUMP, which fell
        through to repr() for any node type without an entry.) Flavour
        emitters bypass this via their action dispatch table.
        """
        return repr(self)


# ── Leaves ───────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class IrLiteral(IrNode):
    """Literal string. `value` is canonical Python (escapes decoded)."""
    value: str


@dataclass(frozen=True, slots=True)
class IrCharClass(IrNode):
    """Character class. `pattern` is canonical POSIX-style interior."""
    pattern: str
    negated: bool = False


@dataclass(frozen=True, slots=True)
class IrRuleRef(IrNode):
    """Reference to another rule by name."""
    name: str


# ── Quantifier (also a leaf IrNode) ──────────────────────────────────


@dataclass(frozen=True, slots=True)
class Quantifier(IrNode):
    """Repetition bounds. `max=None` means unbounded.

    Will be renamed to IrQuantifier in Task 2.1; staying as Quantifier
    in Task 1.x to keep step 1 a pure protocol-introduction change.
    """
    min: int = 1
    max: int | None = 1


# ── Structure ────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class IrSequence(IrNode):
    """Concatenation of items."""
    items: tuple[IrItem, ...] = ()


@dataclass(frozen=True, slots=True)
class IrAlternation(IrNode):
    """Choice between sequences. Always >= 1 arm."""
    arms: tuple[IrSequence, ...] = ()


@dataclass(frozen=True, slots=True)
class IrGroup(IrNode):
    """Parenthesised group. Body is always an IrAlternation."""
    body: IrAlternation


@dataclass(frozen=True, slots=True)
class IrItem(IrNode):
    """An atom (leaf or group) with a quantifier."""
    atom: IrAtom
    quantifier: Quantifier = field(default_factory=Quantifier)


@dataclass(frozen=True, slots=True)
class IrRule(IrNode):
    """A named rule. Body is always an IrAlternation, even single-arm."""
    name: str
    body: IrAlternation


@dataclass(frozen=True, slots=True)
class IrAst(IrNode):
    """Full grammar: rules + start-rule name."""
    rules: tuple[IrRule, ...] = ()
    start: str = ""


# ── Type aliases (structural unions) ─────────────────────────────────

IrLeaf: TypeAlias = IrLiteral | IrCharClass | IrRuleRef
IrAtom: TypeAlias = IrLeaf | IrGroup
```

- [ ] **Step 4: Run tests to verify it passes**

Run: `uv run pytest tests/unit/lexic/ir/test_nodes.py -v`
Expected: PASS — all three new tests green.

Run: `uv run pytest -q`
Expected: PASS — full suite still green (no behavioural change; `IrNode` is just a base class now).

- [ ] **Step 5: Commit**

```bash
git add src/lexic/ir/nodes.py tests/unit/lexic/ir/test_nodes.py
git commit -m "ir: promote IrNode to ABC with structural protocol

children/rebuild/emit are now methods on IrNode with leaf-friendly
defaults. Concrete nodes will override in subsequent tasks. The
TypeAlias union form is replaced by nominal inheritance."
```

---

### Task 1.2: Add `children()` and `rebuild()` overrides per node type

**Files:**
- Modify: `src/lexic/ir/nodes.py`
- Test: `tests/unit/lexic/ir/test_nodes.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/unit/lexic/ir/test_nodes.py`:

```python
def test_iritem_children_returns_atom_and_quantifier():
    item = IrItem(IrLiteral("x"), Quantifier(0, None))
    assert item.children() == (item.atom, item.quantifier)


def test_iritem_rebuild_replaces_both():
    item = IrItem(IrLiteral("x"), Quantifier(0, None))
    new = item.rebuild((IrLiteral("y"), Quantifier(1, 1)))
    assert new == IrItem(IrLiteral("y"), Quantifier(1, 1))


def test_irsequence_children_returns_items():
    a, b = IrItem(IrLiteral("a")), IrItem(IrLiteral("b"))
    seq = IrSequence((a, b))
    assert seq.children() == (a, b)


def test_irsequence_rebuild_replaces_items():
    a, b = IrItem(IrLiteral("a")), IrItem(IrLiteral("b"))
    seq = IrSequence((a,))
    assert seq.rebuild((a, b)) == IrSequence((a, b))


def test_iralternation_children_returns_arms():
    s = IrSequence(())
    alt = IrAlternation((s,))
    assert alt.children() == (s,)


def test_iralternation_rebuild_replaces_arms():
    s1, s2 = IrSequence(()), IrSequence(())
    assert IrAlternation((s1,)).rebuild((s1, s2)) == IrAlternation((s1, s2))


def test_irgroup_children_returns_body():
    body = IrAlternation(())
    grp = IrGroup(body)
    assert grp.children() == (body,)


def test_irgroup_rebuild_replaces_body():
    b1, b2 = IrAlternation(()), IrAlternation((IrSequence(()),))
    assert IrGroup(b1).rebuild((b2,)) == IrGroup(b2)


def test_irrule_children_returns_body():
    body = IrAlternation(())
    rule = IrRule("r", body)
    assert rule.children() == (body,)


def test_irrule_rebuild_replaces_body_preserves_name():
    b1, b2 = IrAlternation(()), IrAlternation((IrSequence(()),))
    assert IrRule("r", b1).rebuild((b2,)) == IrRule("r", b2)


def test_irast_children_returns_rules():
    r = IrRule("x", IrAlternation(()))
    ast = IrAst((r,), "x")
    assert ast.children() == (r,)


def test_irast_rebuild_replaces_rules_preserves_start():
    r1 = IrRule("a", IrAlternation(()))
    r2 = IrRule("b", IrAlternation(()))
    assert IrAst((r1,), "a").rebuild((r1, r2)) == IrAst((r1, r2), "a")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/lexic/ir/test_nodes.py -v`
Expected: FAIL — children/rebuild return defaults from base (empty tuple / identity) but tests assert specific overrides.

- [ ] **Step 3: Add per-type overrides in `src/lexic/ir/nodes.py`**

Add the methods inside the existing dataclasses (edit each):

```python
@dataclass(frozen=True, slots=True)
class IrSequence(IrNode):
    items: tuple[IrItem, ...] = ()

    def children(self) -> tuple[IrNode, ...]:
        return self.items

    def rebuild(self, new_children: tuple[IrNode, ...]) -> IrNode:
        return IrSequence(items=new_children)


@dataclass(frozen=True, slots=True)
class IrAlternation(IrNode):
    arms: tuple[IrSequence, ...] = ()

    def children(self) -> tuple[IrNode, ...]:
        return self.arms

    def rebuild(self, new_children: tuple[IrNode, ...]) -> IrNode:
        return IrAlternation(arms=new_children)


@dataclass(frozen=True, slots=True)
class IrGroup(IrNode):
    body: IrAlternation

    def children(self) -> tuple[IrNode, ...]:
        return (self.body,)

    def rebuild(self, new_children: tuple[IrNode, ...]) -> IrNode:
        return IrGroup(body=new_children[0])


@dataclass(frozen=True, slots=True)
class IrItem(IrNode):
    atom: IrAtom
    quantifier: Quantifier = field(default_factory=Quantifier)

    def children(self) -> tuple[IrNode, ...]:
        # Both atom and quantifier are IrNode subclasses — exposing both
        # makes IrTransformer/IrVisitor walks see the full structure.
        # Required for byte-parity dump tests that recurse over every
        # subnode, and lets future passes rewrite quantifiers via the
        # standard transformer machinery.
        return (self.atom, self.quantifier)

    def rebuild(self, new_children: tuple[IrNode, ...]) -> IrNode:
        return IrItem(atom=new_children[0], quantifier=new_children[1])


@dataclass(frozen=True, slots=True)
class IrRule(IrNode):
    name: str
    body: IrAlternation

    def children(self) -> tuple[IrNode, ...]:
        return (self.body,)

    def rebuild(self, new_children: tuple[IrNode, ...]) -> IrNode:
        return IrRule(name=self.name, body=new_children[0])


@dataclass(frozen=True, slots=True)
class IrAst(IrNode):
    rules: tuple[IrRule, ...] = ()
    start: str = ""

    def children(self) -> tuple[IrNode, ...]:
        return self.rules

    def rebuild(self, new_children: tuple[IrNode, ...]) -> IrNode:
        return IrAst(rules=new_children, start=self.start)
```

Leaves (`IrLiteral`, `IrCharClass`, `IrRuleRef`, `Quantifier`) intentionally inherit defaults — no override needed.

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/unit/lexic/ir/test_nodes.py -v` — PASS.
Run: `uv run pytest -q` — PASS.

- [ ] **Step 5: Commit**

```bash
git add src/lexic/ir/nodes.py tests/unit/lexic/ir/test_nodes.py
git commit -m "ir: add per-type children()/rebuild() overrides on IR nodes

Branches (IrSequence, IrAlternation, IrGroup, IrItem, IrRule, IrAst)
implement structural protocol overrides. Leaves use IrNode defaults."
```

---

### Task 1.3: Add per-type `emit()` overrides matching current dump output

**Files:**
- Modify: `src/lexic/ir/nodes.py`
- Test: `tests/unit/lexic/ir/test_nodes.py`

**Reference current output** (`src/lexic/ir/walk.py:57-84`): the existing `_DUMP` dict produces indented pretty-prints. The new `emit()` methods must match this output byte-for-byte so the suite stays green when `dump()` is rewired in Task 1.5.

- [ ] **Step 1: Write failing tests**

Append to `tests/unit/lexic/ir/test_nodes.py`:

```python
import pytest

from lexic.ir.walk import dump as _legacy_dump


def _sample_tree() -> IrAst:
    """Representative tree exercising every node type."""
    return IrAst(
        rules=(
            IrRule(
                "r",
                IrAlternation((
                    IrSequence((
                        IrItem(IrLiteral("a")),
                        IrItem(IrCharClass("0-9", negated=True), Quantifier(0, None)),
                        IrItem(IrRuleRef("other"), Quantifier(1, 2)),
                        IrItem(IrGroup(IrAlternation((IrSequence(()),))), Quantifier(0, 1)),
                    )),
                    IrSequence(()),
                )),
            ),
            IrRule("empty", IrAlternation(())),
        ),
        start="r",
    )


def _all_subnodes(node):
    yield node
    for child in node.children():
        yield from _all_subnodes(child)


@pytest.mark.parametrize("indent", [0, 1, 3])
def test_emit_matches_legacy_dump_for_every_node(indent):
    """node.emit(i) must equal the old _DUMP[type(node)](node, i) for every
    subnode of a representative tree. This is the byte-parity contract."""
    tree = _sample_tree()
    for sub in _all_subnodes(tree):
        assert sub.emit(indent) == _legacy_dump(sub, indent=indent), (
            f"emit() diverged from _DUMP for {type(sub).__name__} at indent={indent}"
        )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/lexic/ir/test_nodes.py::test_emit_matches_legacy_dump_for_every_node -v`
Expected: FAIL — default `emit()` returns `repr(self)`.

- [ ] **Step 3: Implement `emit()` overrides matching the existing `_DUMP` format**

Add to each IR node class in `src/lexic/ir/nodes.py`. Use the existing `_DUMP` entries in `src/lexic/ir/walk.py:57-84` as the literal spec. For each class:

```python
@dataclass(frozen=True, slots=True)
class IrAst(IrNode):
    ...
    def emit(self, indent: int = 0) -> str:
        pad = '  ' * indent
        return (
            f"{pad}IrAst(start={self.start!r}, rules=[\n"
            + "\n".join(r.emit(indent + 1) for r in self.rules)
            + f"\n{pad}])"
        )


@dataclass(frozen=True, slots=True)
class IrRule(IrNode):
    ...
    def emit(self, indent: int = 0) -> str:
        pad = '  ' * indent
        return f"{pad}IrRule({self.name!r},\n{self.body.emit(indent + 1)}\n{pad})"


@dataclass(frozen=True, slots=True)
class IrAlternation(IrNode):
    ...
    def emit(self, indent: int = 0) -> str:
        pad = '  ' * indent
        if not self.arms:
            return f"{pad}IrAlternation([])"
        return (
            f"{pad}IrAlternation([\n"
            + ",\n".join(a.emit(indent + 1) for a in self.arms)
            + f"\n{pad}])"
        )


@dataclass(frozen=True, slots=True)
class IrSequence(IrNode):
    ...
    def emit(self, indent: int = 0) -> str:
        pad = '  ' * indent
        if not self.items:
            return f"{pad}IrSequence([])"
        return (
            f"{pad}IrSequence([\n"
            + ",\n".join(it.emit(indent + 1) for it in self.items)
            + f"\n{pad}])"
        )


@dataclass(frozen=True, slots=True)
class IrItem(IrNode):
    ...
    def emit(self, indent: int = 0) -> str:
        pad = '  ' * indent
        return f"{pad}IrItem({self.atom.emit(indent + 1)}, q={self.quantifier})"


@dataclass(frozen=True, slots=True)
class IrGroup(IrNode):
    ...
    def emit(self, indent: int = 0) -> str:
        pad = '  ' * indent
        return f"{pad}IrGroup({self.body.emit(indent + 1)})"
```

For leaves (`IrLiteral`, `IrCharClass`, `IrRuleRef`, `Quantifier`), the default `emit()` already returns `f"{pad}{self!r}"` — the same format `_DUMP` falls through to via `repr(node)` for unknown types. Verify with one explicit override only if the existing dump output differs.

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/unit/lexic/ir/test_nodes.py -v` — PASS.
Run: `uv run pytest -q` — PASS.

- [ ] **Step 5: Commit**

```bash
git add src/lexic/ir/nodes.py tests/unit/lexic/ir/test_nodes.py
git commit -m "ir: add emit() overrides matching legacy dump format

Every IR node now renders itself for debug. The output matches the
existing top-level dump() byte-for-byte so consumers can be switched
mechanically in the next task."
```

---

### Task 1.4: Refactor `IrDispatch`/`IrTransformer` to use node methods; delete intrinsic-data dicts

**Files:**
- Modify: `src/lexic/ir/walk.py`
- Test: `tests/unit/lexic/ir/test_walk.py` (existing)

- [ ] **Step 1: Read existing walk tests for context**

Run: `uv run pytest tests/unit/lexic/ir/test_walk.py -v` and confirm green pre-change.

- [ ] **Step 2: Rewrite `src/lexic/ir/walk.py`**

Replace the file:

```python
"""IrDispatch, IrVisitor, IrTransformer, IrEmitter — Python-ast-style traversal.

IrDispatch[_N, _T] is the shared parent. visit() dispatches to
visit_<TypeName> methods; missing types fall to generic_visit which
walks children via node.children() and delegates to _combine
(subclass override). Canonical instantiations:

  IrVisitor[_N]      = IrDispatch[_N, None]   walks for side effects
  IrTransformer[_N]  = IrDispatch[_N, _N]     rewrites via node.rebuild()
  IrEmitter[_N]      = IrDispatch[_N, str]    produces strings (added Task 3.1)

Leaves (IrLiteral, IrCharClass, IrRuleRef, Quantifier) have no children.
Per-node intrinsic data (children layout, rebuild constructor, debug emit)
lives on the node itself — there is no central registry.
"""

from __future__ import annotations

from typing import Callable, TypeAlias, TypeVar

from lexic.exceptions import UnsupportedConstructError
from lexic.ir.nodes import IrNode

_N = TypeVar("_N", bound=IrNode)


class IrDispatch[_N, _T]:
    """Type-name dispatch over IR nodes; parent of IrVisitor and IrTransformer.

    `visit(node)` returns whatever `visit_<TypeName>(node)` returns. If no
    matching method exists, `generic_visit` walks `node.children()`, recurses,
    and combines via `_combine` (subclass override).
    """

    action: dict[type, Callable[..., _T]]

    def visit(self, node: _N) -> _T:
        method = getattr(self, f"visit_{type(node).__name__}", self.generic_visit)
        return method(node)

    def generic_visit(self, node: _N) -> _T:
        old_children = node.children()
        new_children = tuple(self.visit(c) for c in old_children)
        return self._combine(node, old_children, new_children)

    def _combine(self, node: _N, old_children: tuple, new_children: tuple) -> _T:
        try:
            return self.action[type(node)](node, old_children, new_children)
        except KeyError as exc:
            raise UnsupportedConstructError(
                f"no action handler for node type {type(node).__name__!r}"
            ) from exc


class IrVisitor[_N](IrDispatch[_N, None]):
    """Walks the IR for side effects. Subclass + define visit_<TypeName>."""

    def _combine(self, node: _N, old_children: tuple, new_children: tuple) -> None:
        return None


class IrTransformer[_N](IrDispatch[_N, _N]):
    """Rewrites the IR. Each visit_<TypeName> returns a (possibly new) node."""

    def _combine(self, node: _N, old_children: tuple, new_children: tuple) -> _N:
        if not old_children:
            return node
        if all(nc is oc for nc, oc in zip(new_children, old_children)):
            return node
        return node.rebuild(new_children)


def dump(node: IrNode, *, indent: int = 0) -> str:
    """Pretty-print an IR AST node for debugging.

    Thin wrapper over node.emit() for now; will be subsumed by IrMetaEmitter
    in Task 3.x.
    """
    return node.emit(indent)
```

- [ ] **Step 3: Run tests**

Run: `uv run pytest -q`
Expected: PASS — the protocol methods produce the same output as the deleted dicts.

If anything fails, the most likely culprit is an emit() override that doesn't match the legacy _DUMP output. Fix the per-type emit() in nodes.py until parity is restored.

- [ ] **Step 4: Commit**

```bash
git add src/lexic/ir/walk.py
git commit -m "ir: delete _CHILDREN/_REBUILD/_DUMP; route via node methods

IrDispatch.generic_visit calls node.children(); IrTransformer._combine
calls node.rebuild(); the top-level dump() delegates to node.emit().
Central registries on walk.py are gone. New IR node types now plug in
by implementing three methods, no walk.py edits required."
```

---

## Step 2 — IrQuantifier rename + IrNode subclass

`Quantifier` is already an IrNode subclass after Step 1. This step is a pure rename across the codebase.

### Task 2.1: Rename `Quantifier` → `IrQuantifier` everywhere

**Files:**
- Modify: `src/lexic/ir/nodes.py`, `src/lexic/ir/__init__.py`
- Modify (rename references): every site listed below
- Test: existing test suite

**Site list** (verified by `rg "\bQuantifier\b" src/ tests/`):
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
- Any test files in `tests/`

Files deliberately omitted (they get deleted in Task 3.7, no point
renaming first): `src/lexic/grammars/gbnf/emitter.py`,
`src/lexic/grammars/abnf/emitter.py`,
`src/lexic/utils/quantifiers.py`. The `sed` command in Step 3 below
must exclude these paths.

- [ ] **Step 1: Confirm exhaustive list**

Run: `rg "\bQuantifier\b" src/ tests/ --files-with-matches`

Note every file produced. The list above is from the spec; verify nothing has changed.

- [ ] **Step 2: Rename the class definition**

In `src/lexic/ir/nodes.py`, change:

```python
class Quantifier(IrNode):
    ...
```

to:

```python
class IrQuantifier(IrNode):
    ...
```

Also update the `field(default_factory=Quantifier)` on `IrItem` to `field(default_factory=IrQuantifier)`.

- [ ] **Step 3: Rename every other reference**

Run (one site at a time, or via sed if confident), excluding the
soon-to-delete files:

```bash
rg -l "\bQuantifier\b" src/ tests/ \
  | grep -v -E '(grammars/(gbnf|abnf)/emitter\.py|utils/quantifiers\.py)' \
  | xargs sed -i 's/\bQuantifier\b/IrQuantifier/g'
```

⚠️ Verify no false positives. `Quantifier` is a unique identifier, so this should be safe — but inspect the diff before committing.

- [ ] **Step 4: Run mechanical fixes and tests**

```bash
tools/auto_fix.sh
uv run pytest -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "ir: rename Quantifier -> IrQuantifier (IrNode leaf)

Consistency with IrLiteral/IrCharClass/IrRuleRef naming. No semantic
change; mechanical rename across ~30 call sites."
```

---

### Task 2.2: Replace `RuleSpec.items` with `body: IrAlternation`

> ⚠️ **Execute AFTER Task 3.7.** Even though this task is grouped under
> Step 2 for narrative continuity (it's a RuleSpec shape change, close
> in spirit to the IrQuantifier rename), it must run after Task 3.7
> deletes `GbnfEmitter` / `AbnfEmitter`. Those legacy emitters read
> `spec.items` and would break the suite mid-Step-3 otherwise.

`RuleSpec` currently carries `items: list[IrItem | IrAlternation]` — a
flattened union that pre-discriminates rule body shape based on `kind`,
forcing every consumer (and any future projection like `to_ir_rule`) to
dispatch on `kind` + `isinstance` to reconstruct an IrAlternation.

Replace with `body: IrAlternation` taken verbatim from the source
`IrRule.body`. The `kind` discriminator stays — codegen needs it to
choose which Pydantic shape to generate — but body shape becomes
opaque to `RuleSpec` itself and to anything that just wants to render
or walk the rule.

**Files:**
- Modify: `src/lexic/ir/spec.py` (field replacement + `to_ir_rule()`)
- Modify: `src/lexic/ir/derive.py` (no more flattening — store source body directly)
- Modify: `src/lexic/base.py:39` (to_text iteration)
- Modify: `src/lexic/codegen/aliases.py:178`
- Modify: `src/lexic/codegen/model_emitter.py:198,200,268,303` (and any other `spec.items` reads)
- Test mirrors for each, plus any test reading `spec.items`

- [ ] **Step 1: Verify the consumer set**

```bash
rg -n "spec\.items|\.items\b" src/lexic/ tests/ --type py
```

The hit list should match: base.py (1), codegen/aliases.py (1),
codegen/model_emitter.py (~5), plus tests. If a new consumer appears,
include it in this task.

- [ ] **Step 2: Update `RuleSpec`**

Edit `src/lexic/ir/spec.py`:

```python
from lexic.ir.nodes import IrAlternation, IrRule


@dataclass(frozen=True, slots=True)
class RuleSpec:
    rule_name: str
    class_name: str
    parent_class_name: str | None
    kind: Literal["value_str", "sequence", "alternation"]
    body: IrAlternation
    field_map: dict[str, int]
    non_semantic_fields: set[str]

    def to_ir_rule(self) -> IrRule:
        """Canonical projection to IR. Loses codegen metadata
        (class_name, field_map, etc.); keeps the grammar body verbatim.
        Type-blind: knows nothing about IrNode subclasses.

        Task 3.5 introduced this method with a transitional
        `items`-based dispatch. Now that `items` is gone, the body is
        stored canonically and this collapses to one line."""
        return IrRule(self.rule_name, self.body)
```

- [ ] **Step 3: Update `derive_specs`**

In `src/lexic/ir/derive.py`, each of the four per-kind builders
(`_build_value_str`, `_build_sequence`, `_build_alternation`, plus the
single-arm value_str branch) constructs an `IrAlternation` body
appropriate to that kind. This is NOT a single "wrap source body"
operation — the body for an alternation-kind spec is **synthesized**
from arm-name refs, not the original `IrRule.body`. Concretely:

| Kind | `RuleSpec.body` is |
|---|---|
| `value_str` (multi-arm) | the source `rule.body` (it's already an IrAlternation) |
| `value_str` (single-arm) | `IrAlternation((IrSequence(arms[0].items),))` |
| `sequence` | `IrAlternation((IrSequence(arms[0].items),))` |
| `alternation` | `IrAlternation(tuple(IrSequence((IrItem(IrRuleRef(name=arm_name)),)) for arm_name in arm_names))` — synthesized choice of arm refs (the lifted/named arm classes) |

Per-kind construction is the natural place for this — each builder
already knows its kind and has the source IR available. There's no
shared "_build_body" helper with a dispatch table; each branch builds
its own body directly. The result: `RuleSpec` itself holds no body-shape
knowledge, and `to_ir_rule` is `IrRule(self.rule_name, self.body)` —
type-blind.

Classification (deciding `kind`) is a separate, single-purpose function
operating on the source `IrRule.body`. That function legitimately
dispatches on node types because classification IS its job — distinct
from the body shape carried on `RuleSpec`.

- [ ] **Step 4: Update ALL `spec.items` consumers in one commit**

This is a breaking shape change. Every reader of `spec.items` must
update in the same commit or the suite breaks. Sites (verified via
`rg "spec\.items|\.items\b" src/lexic/ tests/`):

- `src/lexic/base.py:39` — `to_text()` iterates positional items (sequence kind)
- `src/lexic/codegen/aliases.py:178`
- `src/lexic/codegen/model_emitter.py:~198, 200, 268, 303`
- any test that constructs `RuleSpec(items=...)`

(`GbnfEmitter` / `AbnfEmitter` are not listed — they were deleted in
Task 3.7, which this task runs after.)

Update map:

| Old read | New read |
|---|---|
| `spec.items` (sequence kind) | `spec.body.arms[0].items` |
| `spec.items` (alternation kind) | `[arm.items[0] for arm in spec.body.arms]` (the synthesized arm-ref IrItems) |
| `spec.items` (value_str multi-arm) | `(spec.body,)` — single-element |
| `spec.items` (value_str single-arm) | `spec.body.arms[0].items` |

The dispatch on `kind` stays in codegen — that's its legitimate
discriminator. The dispatch on `isinstance(item, IrAlternation)` to
detect multi-arm value_str disappears: `kind == "value_str" and
len(spec.body.arms) > 1` is the explicit test.


- [ ] **Step 5: Update tests**

`grep -rn "items=" tests/` for any spec constructions; switch each to
`body=IrAlternation((IrSequence(items),))` or the equivalent. The
flattened form is gone.

- [ ] **Step 6: Run**

```bash
tools/auto_fix.sh
uv run pytest -q
```

PASS expected. If a consumer was missed, it'll surface as an
`AttributeError: 'RuleSpec' object has no attribute 'items'`. Fix the
read site; don't add a backward-compat `items` property.

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "ir/spec: store rule body verbatim as IrAlternation

RuleSpec.items (the flattened IrItem|IrAlternation union) replaced by
RuleSpec.body: IrAlternation — taken straight from the source IrRule.
to_ir_rule() becomes IrRule(name, body), type-blind. Codegen keeps its
kind-based dispatch (legitimate); the closed-world dispatch on body
shape moves out of every read site."
```

---

## Step 3 — IrEmitter, IrMetaEmitter, and unified flavour emit

This is the largest step. The substeps build up `IrEmitter` and `IrMetaEmitter`, then progressively migrate each flavour onto the new dispatch table while keeping the suite green.

### Task 3.1: Add `IrEmitter[_N]` and `IrMetaEmitter` to `walk.py`

**Files:**
- Modify: `src/lexic/ir/walk.py`
- Test: `tests/unit/lexic/ir/test_walk.py`

- [ ] **Step 1: Write failing test**

Append to `tests/unit/lexic/ir/test_walk.py`:

```python
def test_iremit_falls_through_to_node_emit():
    """IrMetaEmitter subclass with empty action dispatches to node.emit()."""
    from lexic.ir.nodes import IrLiteral, IrSequence, IrItem
    from lexic.ir.walk import IrMetaEmitter

    seq = IrSequence((IrItem(IrLiteral("x")),))
    assert IrMetaEmitter().visit(seq) == seq.emit()


def test_iremitter_action_overrides_node_emit():
    """Per-type action entries override the node.emit() fallback."""
    from lexic.ir.nodes import IrLiteral, IrNode
    from lexic.ir.walk import IrEmitter

    class _Upper(IrEmitter[IrNode]):
        action = {IrLiteral: lambda n, _r: n.value.upper()}

    assert _Upper().visit(IrLiteral("hi")) == "HI"


def test_iremitter_recurse_into_children():
    """Action handlers receive a recurse fn that calls visit() on children."""
    from lexic.ir.nodes import IrItem, IrLiteral, IrNode
    from lexic.ir.walk import IrEmitter

    class _Wrap(IrEmitter[IrNode]):
        action = {
            IrLiteral: lambda n, _r: f"[{n.value}]",
            IrItem:    lambda n, r: f"<{r(n.atom)}>",
        }

    assert _Wrap().visit(IrItem(IrLiteral("x"))) == "<[x]>"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/lexic/ir/test_walk.py -v`
Expected: FAIL — `IrEmitter` and `IrMetaEmitter` do not exist.

- [ ] **Step 3: Implement in `src/lexic/ir/walk.py`**

Append at the end of `walk.py`:

```python
class IrEmitter[_N](IrDispatch[_N, str]):
    """String emission. T=str. The base class for every string-producing
    IR walk: flavour emitters, debug dump, anything that turns IR into text.

    Default behaviour when `action` has no entry for a node type: call
    `node.emit()` — the per-node default rendering. Subclasses populate
    `action` to override per-type rendering for a specific target format.

    `action` is a class-level dict by design (every Flavour subclass
    declares its own action table once, at class scope). Instances never
    mutate it — IrEmitter is conceptually stateless. The class-level
    default `{}` is shared but never written to; subclasses always
    shadow it with their own dict.
    """

    action: ClassVar[dict[type, Callable[..., str]]] = {}

    def visit(self, node: _N) -> str:
        handler = self.action.get(type(node))
        if handler is not None:
            return handler(node, self.visit)
        method = getattr(self, f"visit_{type(node).__name__}", None)
        if method is not None:
            return method(node)
        return node.emit()


class IrMetaEmitter(IrEmitter[IrNode]):
    """The trivial emitter: pure fallthrough to each node's emit() method.

    Used for debug output. Equivalent to the top-level dump() but slots
    into the IrEmitter hierarchy so it composes with the mechanism
    flavours use.
    """

    # Empty action — every node falls through to node.emit().
    action: ClassVar[dict[type, Callable[..., str]]] = {}
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/unit/lexic/ir/test_walk.py -v` — PASS.
Run: `uv run pytest -q` — PASS.

- [ ] **Step 5: Commit**

```bash
git add src/lexic/ir/walk.py tests/unit/lexic/ir/test_walk.py
git commit -m "ir: add IrEmitter (T=str) and IrMetaEmitter (debug default)

IrEmitter is the third canonical IrDispatch instantiation, alongside
IrVisitor (T=None) and IrTransformer (T=_N). It falls through to
node.emit() when the action table has no entry, so flavour emitters
override selectively. IrMetaEmitter is the trivial subclass used for debug
dump output."
```

---

### Task 3.2: Add `action`, `quantifier_symbols`, `pre_parse_check` to `Flavour`; subclass `IrEmitter`

**Files:**
- Modify: `src/lexic/grammars/flavour.py`
- Test: `tests/unit/lexic/grammars/test_flavour.py`

- [ ] **Step 1: Read current Flavour file**

Run: `cat src/lexic/grammars/flavour.py`

Confirm shape from spec context (you've already seen it). The `emitter: ClassVar[type[FlavourEmitter]]` attribute will go away after Task 3.7 deletes FlavourEmitter; for now it stays.

- [ ] **Step 2: Write failing test**

Append to `tests/unit/lexic/grammars/test_flavour.py`:

```python
def test_flavour_is_iremitter_subclass():
    from lexic.grammars.flavour import Flavour
    from lexic.ir.walk import IrEmitter
    assert issubclass(Flavour, IrEmitter)


def test_flavour_pre_parse_check_default_noop():
    """Default pre_parse_check is a no-op; subclasses override per flavour."""
    from lexic.grammars.flavour import Flavour
    Flavour.pre_parse_check("anything")  # must not raise
```

- [ ] **Step 3: Modify `Flavour`**

Edit `src/lexic/grammars/flavour.py`:

```python
"""Flavour ABC — the contract every grammar flavour fulfils.

A Flavour is an IrEmitter[IrNode]: emission is the per-flavour `action`
dispatch table inherited from IrDispatch. Flavours also declare parse-side
hooks (parse_quantifier, parse_charclass) and an optional pre_parse_check
for source-text validation that runs before the meta-grammar parser.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable, ClassVar

from lexic.ir.escapes import EscapeCodec
from lexic.ir.nodes import IrGroup, IrLiteral, IrNode, IrQuantifier
from lexic.ir.walk import IrEmitter


class Flavour(IrEmitter[IrNode], ABC):
    """Per-flavour configuration. Subclass and fill in class attributes."""

    name: ClassVar[str]
    extensions: ClassVar[tuple[str, ...]]
    meta_grammar: ClassVar[str]
    escapes: ClassVar[EscapeCodec]
    # NOTE: the `emitter` ClassVar that the legacy ABC declared is dropped
    # here. Concrete subclasses still carry `emitter = GbnfEmitter` etc. as
    # plain class attributes for the duration of Tasks 3.3-3.6 (base.py
    # reads `flavour_cls.emitter`); the lines disappear in Task 3.7
    # alongside FlavourEmitter itself. The ABC annotation is purely
    # informational, so removing it now avoids needing a TYPE_CHECKING
    # forward-reference (which CLAUDE.md forbids).
    line_comment: ClassVar[str] = ""

    # Punctuation (rule_separator, alt_separator, quote_char, group_open,
    # group_close, empty_body, rule_terminator) is NOT carried as ClassVars.
    # Every per-flavour difference lives inside the action lambdas
    # (action[IrRule] knows its own separator, action[IrAlternation] knows
    # its own joiner, action[IrSequence] handles empty bodies via
    # `or '""'`). Adding ClassVars would duplicate state that lives in
    # exactly one place — the action table.

    # Quantifier symbol table: keyed on (min, max). The action[IrQuantifier]
    # renderer consults this first, falls through to {n,m}-style for misses.
    quantifier_symbols: ClassVar[dict[tuple[int, int | None], str]] = {}

    @staticmethod
    @abstractmethod
    def parse_quantifier(text: str) -> IrQuantifier:
        """Parse a flavour-specific quantifier token into canonical bounds."""

    @staticmethod
    @abstractmethod
    def parse_charclass(text: str) -> tuple[str, bool]:
        """Parse a bracket-expression token. Return (canonical_pattern, negated)."""

    @classmethod
    def normalize_literal(cls, decoded: str) -> IrLiteral | IrGroup:
        """Optional sugar-expansion hook. Default: identity."""
        return IrLiteral(decoded)

    @classmethod
    def pre_parse_check(cls, text: str) -> None:
        """Flavour-specific source-text validation, run before the Lark parse.
        Default: no-op. Subclasses override to scan for reserved syntax.
        """
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/unit/lexic/grammars/test_flavour.py -v` — PASS.
Run: `uv run pytest -q` — PASS (existing flavours still work because their `action` attribute hasn't been used yet — the old FlavourEmitter pipeline is still doing the rendering).

- [ ] **Step 5: Commit**

```bash
git add src/lexic/grammars/flavour.py tests/unit/lexic/grammars/test_flavour.py
git commit -m "flavour: subclass IrEmitter; add quantifier_symbols + pre_parse_check

Flavour now inherits IrEmitter[IrNode]; concrete flavours will populate
the action dispatch table in subsequent tasks. quantifier_symbols is
the per-(min,max) symbol map. pre_parse_check is the source-text
validation hook used by Step 5 (token reservation)."
```

---

### Task 3.3: Populate `GbnfFlavour.action` and `quantifier_symbols`

**Files:**
- Modify: `src/lexic/grammars/gbnf/flavour.py`
- Test: `tests/unit/lexic/grammars/gbnf/test_flavour.py`

- [ ] **Step 1: Read the current GbnfFlavour file**

Run: `cat src/lexic/grammars/gbnf/flavour.py`

Note the parse methods and any escape config — they stay unchanged.

- [ ] **Step 2: Write failing test**

Append to `tests/unit/lexic/grammars/gbnf/test_flavour.py` (create file if it doesn't exist following the test-mirror convention):

```python
"""Tests for GbnfFlavour.action and quantifier_symbols."""

from __future__ import annotations

from lexic.grammars.gbnf.flavour import GbnfFlavour
from lexic.ir.nodes import (
    IrAlternation,
    IrAst,
    IrCharClass,
    IrGroup,
    IrItem,
    IrLiteral,
    IrQuantifier,
    IrRule,
    IrRuleRef,
    IrSequence,
)


def test_gbnf_renders_literal():
    out = GbnfFlavour().visit(IrLiteral("hi"))
    assert out == '"hi"'


def test_gbnf_renders_charclass_negated():
    out = GbnfFlavour().visit(IrCharClass("a-z", negated=True))
    assert out == "[^a-z]"


def test_gbnf_renders_quantifier_symbolic():
    assert GbnfFlavour().visit(IrQuantifier(0, 1)) == "?"
    assert GbnfFlavour().visit(IrQuantifier(0, None)) == "*"
    assert GbnfFlavour().visit(IrQuantifier(1, None)) == "+"
    assert GbnfFlavour().visit(IrQuantifier(1, 1)) == ""


def test_gbnf_renders_quantifier_braced():
    assert GbnfFlavour().visit(IrQuantifier(3, 3)) == "{3}"
    assert GbnfFlavour().visit(IrQuantifier(2, 5)) == "{2,5}"
    assert GbnfFlavour().visit(IrQuantifier(2, None)) == "{2,}"


def test_gbnf_renders_item_atom_then_quantifier():
    item = IrItem(IrLiteral("x"), IrQuantifier(0, None))
    assert GbnfFlavour().visit(item) == '"x"*'


def test_gbnf_renders_sequence_space_joined():
    seq = IrSequence((IrItem(IrLiteral("a")), IrItem(IrLiteral("b"))))
    assert GbnfFlavour().visit(seq) == '"a" "b"'


def test_gbnf_renders_alternation_pipe_joined():
    alt = IrAlternation((
        IrSequence((IrItem(IrLiteral("a")),)),
        IrSequence((IrItem(IrLiteral("b")),)),
    ))
    assert GbnfFlavour().visit(alt) == '"a" | "b"'


def test_gbnf_renders_rule():
    rule = IrRule("r", IrAlternation((IrSequence((IrItem(IrLiteral("a")),)),)))
    assert GbnfFlavour().visit(rule) == 'r ::= "a"'
```

- [ ] **Step 3: Implement `GbnfFlavour.action`**

Edit `src/lexic/grammars/gbnf/flavour.py`. Add at module level (above the class):

```python
def _emit_gbnf_quantifier(q, _r):
    key = (q.min, q.max)
    if key in GbnfFlavour.quantifier_symbols:
        return GbnfFlavour.quantifier_symbols[key]
    if q.min == q.max:
        return f"{{{q.min}}}"
    if q.max is None:
        return f"{{{q.min},}}"
    return f"{{{q.min},{q.max}}}"
```

Then add the `action` and `quantifier_symbols` ClassVars to `GbnfFlavour`:

```python
class GbnfFlavour(Flavour):
    ...
    quantifier_symbols = {(1, 1): "", (0, 1): "?", (0, None): "*", (1, None): "+"}

    # IrLiteral: emits the raw atom.value (no escapes.encode) — preserves
    # the existing GbnfEmitter behaviour at src/lexic/grammars/gbnf/emitter.py:40.
    # The escape codec is used only on the decode side (parsing input grammar
    # text into IR), not on emit. Changing this is a round-trip regression risk.
    action = {
        IrLiteral:     lambda n, _r: f'"{n.value}"',
        IrCharClass:   lambda n, _r: f"[{'^' if n.negated else ''}{n.pattern}]",
        IrRuleRef:     lambda n, _r: n.name,
        IrGroup:       lambda n, r:  f"({r(n.body)})",
        IrQuantifier:  _emit_gbnf_quantifier,
        IrItem:        lambda n, r:  f"{r(n.atom)}{r(n.quantifier)}",
        IrSequence:    lambda n, r:  " ".join(r(it) for it in n.items) or '""',
        IrAlternation: lambda n, r:  " | ".join(r(arm) for arm in n.arms) or '""',
        IrRule:        lambda n, r:  f"{n.name} ::= {r(n.body)}",
        IrAst:         lambda n, r:  "\n".join(r(rule) for rule in n.rules) + "\n",
    }
```

Verify against `src/lexic/grammars/gbnf/emitter.py:40` — the existing emitter does NOT encode literals on the way out. The plan deliberately omits `escapes.encode` to preserve byte-equal round-trip. If a future slice wants symmetric encoding, that's a separate design.

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/unit/lexic/grammars/gbnf/test_flavour.py -v` — PASS.
Run: `uv run pytest -q` — PASS (old `GbnfEmitter` still in use elsewhere).

- [ ] **Step 5: Commit**

```bash
git add src/lexic/grammars/gbnf/flavour.py tests/unit/lexic/grammars/gbnf/test_flavour.py
git commit -m "gbnf: populate Flavour.action with per-IR-node renderers

The action table now renders every IR node type. Consumers (base.py,
render_specs) will switch to GbnfFlavour().visit(node) in subsequent
tasks; for now both pipelines coexist."
```

---

### Task 3.4: Populate `AbnfFlavour.action` and `quantifier_symbols`

**Files:**
- Modify: `src/lexic/grammars/abnf/flavour.py`
- Test: `tests/unit/lexic/grammars/abnf/test_flavour.py`

The structure mirrors Task 3.3 but with ABNF prefix-placement on `IrItem` and a different quantifier format.

- [ ] **Step 1: Read current AbnfFlavour and AbnfEmitter**

Run: `cat src/lexic/grammars/abnf/flavour.py src/lexic/grammars/abnf/emitter.py`

Note the existing `format_quantifier` and `place_quantifier` overrides — the new `action[IrQuantifier]` and `action[IrItem]` absorb them.

- [ ] **Step 2: Write failing tests**

Append to `tests/unit/lexic/grammars/abnf/test_flavour.py`:

```python
"""Tests for AbnfFlavour.action — ABNF prefix-quantifier placement."""

from __future__ import annotations

from lexic.grammars.abnf.flavour import AbnfFlavour
from lexic.ir.nodes import IrItem, IrLiteral, IrQuantifier


def test_abnf_renders_quantifier_prefix_form():
    # ABNF: *foo (zero or more), 1*foo (one or more), 3foo (exactly 3),
    # 2*5foo (2 to 5), *3foo (up to 3).
    assert AbnfFlavour().visit(IrQuantifier(0, None)) == "*"
    assert AbnfFlavour().visit(IrQuantifier(1, None)) == "1*"
    assert AbnfFlavour().visit(IrQuantifier(3, 3)) == "3"
    assert AbnfFlavour().visit(IrQuantifier(2, 5)) == "2*5"
    assert AbnfFlavour().visit(IrQuantifier(0, 3)) == "*3"
    assert AbnfFlavour().visit(IrQuantifier(1, 1)) == ""


def test_abnf_renders_item_prefix_order():
    # Quantifier comes BEFORE atom in ABNF.
    item = IrItem(IrLiteral("x"), IrQuantifier(0, None))
    assert AbnfFlavour().visit(item) == '*"x"'
```

- [ ] **Step 3: Implement `AbnfFlavour.action`**

Add to `src/lexic/grammars/abnf/flavour.py`:

Port the existing `_hex_range_segment`, `_split_charclass_segments`, and
`render_charclass` helpers from `src/lexic/grammars/abnf/emitter.py:22-86`
into module-level functions in `abnf/flavour.py`. Then:

```python
def _hex_range_segment(seg: str) -> str:
    """Convert one POSIX range segment ('a-z' or single char) to ABNF hex.
    Ported from grammars/abnf/emitter.py — keep byte-equal."""
    if len(seg) == 3 and seg[1] == "-":
        lo, hi = seg[0], seg[2]
        return f"%x{ord(lo):02X}-{ord(hi):02X}"
    if len(seg) == 1:
        return f"%x{ord(seg):02X}"
    return " / ".join(f"%x{ord(c):02X}" for c in seg)


def _split_charclass_segments(pattern: str) -> list[str]:
    """Split a POSIX bracket interior into 3-char ranges and 1-char literals.
    Ported from grammars/abnf/emitter.py — keep byte-equal."""
    segments: list[str] = []
    i = 0
    while i < len(pattern):
        if i + 2 < len(pattern) and pattern[i + 1] == "-":
            segments.append(pattern[i : i + 3])
            i += 3
        else:
            segments.append(pattern[i])
            i += 1
    return segments


def _render_abnf_charclass(n, _r):
    """Match the existing AbnfEmitter.render_charclass output:
    single segment → bare; multiple → '(' / joined ')'."""
    segments = _split_charclass_segments(n.pattern)
    rendered = [_hex_range_segment(s) for s in segments]
    if len(rendered) == 1:
        return rendered[0]
    return "(" + " / ".join(rendered) + ")"


def _emit_abnf_quantifier(q, _r):
    if q.min == 1 and q.max == 1:
        return ""
    if q.min == q.max:
        return str(q.min)
    lo = "" if q.min == 0 else str(q.min)
    hi = "" if q.max is None else str(q.max)
    return f"{lo}*{hi}"


class AbnfFlavour(Flavour):
    ...
    # No punctuation ClassVars — each per-flavour difference lives in the
    # action lambda for the relevant IR node type (action[IrRule] uses
    # "=" as separator, action[IrAlternation] uses " / " as joiner).
    quantifier_symbols = {}  # ABNF uses generic form for all; no symbolic shortcuts

    # IrLiteral: raw value, no encode (mirrors GBNF rationale — existing
    # AbnfEmitter does not encode on emit).
    action = {
        IrLiteral:     lambda n, _r: f'"{n.value}"',
        IrCharClass:   _render_abnf_charclass,
        IrRuleRef:     lambda n, _r: n.name,
        IrGroup:       lambda n, r:  f"({r(n.body)})",
        IrQuantifier:  _emit_abnf_quantifier,
        # PREFIX placement: quantifier first, then atom.
        IrItem:        lambda n, r:  f"{r(n.quantifier)}{r(n.atom)}",
        IrSequence:    lambda n, r:  " ".join(r(it) for it in n.items) or '""',
        IrAlternation: lambda n, r:  " / ".join(r(arm) for arm in n.arms) or '""',
        IrRule:        lambda n, r:  f"{n.name} = {r(n.body)}",
        IrAst:         lambda n, r:  "\n".join(r(rule) for rule in n.rules) + "\n",
    }
```

⚠️ The two helpers and `_render_abnf_charclass` must reproduce the existing
`AbnfEmitter.render_charclass` output byte-for-byte. The existing
`tests/unit/lexic/grammars/abnf/test_emitter.py` is the contract — those
assertions migrate to `test_flavour.py` (Task 3.4 test list above) verbatim.

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/unit/lexic/grammars/abnf/test_flavour.py -v` — PASS.
Run: `uv run pytest -q` — PASS.

- [ ] **Step 5: Commit**

```bash
git add src/lexic/grammars/abnf/flavour.py tests/unit/lexic/grammars/abnf/test_flavour.py
git commit -m "abnf: populate Flavour.action with prefix-quantifier renderers

ABNF places quantifiers before atoms (1*foo, *5bar, 2*5baz). The
action[IrItem] lambda owns that ordering directly; the place_quantifier
decorator from FlavourEmitter is no longer needed."
```

---

### Task 3.5: Add `render_specs()` to `ir/emit.py`

**Files:**
- Modify: `src/lexic/ir/emit.py`
- Test: `tests/unit/lexic/ir/test_emit.py`

- [ ] **Step 1: Read current ir/emit.py**

Run: `cat src/lexic/ir/emit.py`

This is the FlavourEmitter ABC — substantial code (~150 lines). It stays for now; we add `render_specs` alongside it. Deletion happens in Task 3.7.

- [ ] **Step 2: Write failing test**

Create or append `tests/unit/lexic/ir/test_emit.py`:

```python
def test_render_specs_round_trips_gbnf_simple_rule():
    from lexic.grammars.gbnf.flavour import GbnfFlavour
    from lexic.ir.emit import render_specs
    from lexic.ir.nodes import (
        IrAlternation, IrItem, IrLiteral, IrSequence, IrQuantifier,
    )
    from lexic.ir.spec import RuleSpec

    body = IrAlternation((IrSequence((IrItem(IrLiteral("x"), IrQuantifier(1, 1)),)),))
    spec = RuleSpec(
        rule_name="r",
        class_name="R",
        parent_class_name=None,
        kind="value_str",
        body=body,
        field_map={},
        non_semantic_fields=set(),
    )
    out = render_specs([spec], GbnfFlavour())
    assert 'r ::= "x"' in out
```

- [ ] **Step 3a: Add `RuleSpec.to_ir_rule()` (legacy items-based)**

`render_specs` calls `spec.to_ir_rule()` to get an `IrRule` to hand to
the flavour. Until Task 2.2 (which runs after Task 3.7) replaces
`RuleSpec.items` with `RuleSpec.body`, the method has to dispatch on
the legacy `items` shape:

```python
# In src/lexic/ir/spec.py:

from lexic.ir.nodes import IrAlternation, IrItem, IrRule, IrSequence


@dataclass(...)
class RuleSpec:
    ...
    def to_ir_rule(self) -> IrRule:
        """Canonical IR projection for grammar rendering.

        Transitional implementation (legacy `items` shape). Task 2.2
        replaces `items` with `body: IrAlternation` post-Task-3.7;
        at that point this method collapses to
        `IrRule(self.rule_name, self.body)`.
        """
        if self.kind == "alternation":
            arms = tuple(IrSequence((it,)) for it in self.items if isinstance(it, IrItem))
            return IrRule(self.rule_name, IrAlternation(arms))
        if self.items and isinstance(self.items[0], IrAlternation):
            return IrRule(self.rule_name, self.items[0])
        items = tuple(it for it in self.items if isinstance(it, IrItem))
        return IrRule(self.rule_name, IrAlternation((IrSequence(items),)))
```

The closed-world dispatch here is temporary — Task 2.2 deletes it
along with the `items` field.

- [ ] **Step 3b: Implement `render_specs`**

Append to `src/lexic/ir/emit.py`:

```python
from typing import Callable


def render_specs(specs, flavour, *, rule_prefix=None):
    """Render a list of RuleSpecs as a grammar string.

    Trivial composition over Flavour and RuleSpec.to_ir_rule():

      - `flavour` is either a Flavour instance (used uniformly) or a
        picker `spec -> Flavour` (per-spec dispatch — Lark uses this).
      - `rule_prefix` is an optional `spec -> str` hook; only Lark uses
        it, to apply `!` to value_str rules.

    Knows nothing about IR node types or spec body shape — that lives
    on RuleSpec.to_ir_rule() and the Flavour's action table. Duck-typed
    on `flavour`: any object with a callable `.visit(node)` works.
    """
    pick = flavour if callable(flavour) else (lambda _spec: flavour)
    prefix = rule_prefix or (lambda _spec: "")
    parts = [
        f"{prefix(s)}{pick(s).visit(s.to_ir_rule())}" for s in specs
    ]
    return "\n".join(parts) + "\n"
```

Imports at top of `ir/emit.py`:

```python
from typing import Callable
# That's it. No Flavour import — duck-typed. No IrAlternation/IrItem —
# the type-aware work happens in RuleSpec.to_ir_rule() and the flavour's
# action table, neither of which lives here.
```

R1 (the `TYPE_CHECKING`-or-duck-typing question) dissolves: `render_specs`
no longer needs to know that `flavour` is a `Flavour`. It calls
`flavour.visit(rule)` and that's the entire contract.

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/unit/lexic/ir/test_emit.py -v` — PASS.
Run: `uv run pytest -q` — PASS.

- [ ] **Step 5: Commit**

```bash
git add src/lexic/ir/emit.py tests/unit/lexic/ir/test_emit.py src/lexic/grammars/flavour.py
git commit -m "ir/emit: add render_specs() driving flavour.visit()

Stateless function that renders a list of RuleSpecs to grammar text
using the per-flavour action dispatch table. FlavourEmitter ABC stays
in place for now; consumers migrate in Task 3.6 and the ABC deletes
in Task 3.7."
```

---

### Task 3.6: Migrate consumers — `base.py` and `lark_builder.py`

**Files:**
- Modify: `src/lexic/base.py`
- Modify: `src/lexic/parsing/lark_builder.py` (partial — Lark migration completes in Step 4)

- [ ] **Step 1: Find consumers of GbnfEmitter / AbnfEmitter / FlavourEmitter**

Run: `rg "GbnfEmitter|AbnfEmitter|FlavourEmitter|emitter\(" src/`

Likely consumers: `src/lexic/base.py` (calls `GbnfEmitter` for `to_grammar`), `src/lexic/codegen/aliases.py` (calls `bounds_to_quantifier`), `src/lexic/codegen/model_emitter.py` (generates code using `bounds_to_quantifier`).

- [ ] **Step 2: Write failing test for base.py path**

```python
# tests/unit/lexic/test_base.py — verify to_grammar via Flavour, not FlavourEmitter
def test_to_grammar_uses_flavour_action():
    # smoke test: round-trip a small GrammarModel
    from lexic.compile import compile_text
    g = compile_text('root ::= "x"', flavour="gbnf")
    instance = g.parse("x")
    assert instance.to_grammar(flavour=g.flavour) == 'root ::= "x"\n'
```

- [ ] **Step 3: Modify `src/lexic/base.py`**

Find the `to_grammar` (or equivalent) method that imports `GbnfEmitter`. Replace:

```python
from lexic.grammars.gbnf.emitter import GbnfEmitter
...
return GbnfEmitter(escapes).emit(specs)
```

with:

```python
from lexic.grammars.gbnf.flavour import GbnfFlavour
from lexic.ir.emit import render_specs
...
return render_specs(specs, GbnfFlavour())
```

If `to_grammar(flavour=...)` accepts a flavour parameter, accept any Flavour and use it directly: `return render_specs(specs, flavour)`.

- [ ] **Step 4: Run tests**

Run: `uv run pytest -q` — PASS.

- [ ] **Step 5: Commit**

```bash
git add src/lexic/base.py tests/unit/lexic/test_base.py
git commit -m "base: route to_grammar through Flavour.visit (render_specs)

base.py no longer imports GbnfEmitter; the GBNF rendering is driven by
GbnfFlavour.action via render_specs. The runtime->codegen import edge
documented in CLAUDE.md now points at GbnfFlavour, not GbnfEmitter."
```

---

### Task 3.7: Delete `FlavourEmitter`, `GbnfEmitter`, `AbnfEmitter`, `utils/quantifiers.py`

**Files:**
- Delete: `src/lexic/ir/emit.py` — the FlavourEmitter class only; keep `render_specs`. Refactor module so it's only the new helpers.
- Delete: `src/lexic/grammars/gbnf/emitter.py`, `tests/unit/lexic/grammars/gbnf/test_emitter.py`
- Delete: `src/lexic/grammars/abnf/emitter.py`, `tests/unit/lexic/grammars/abnf/test_emitter.py`
- Delete: `src/lexic/utils/quantifiers.py`, `tests/unit/lexic/utils/test_quantifiers.py`
- Modify: any remaining `bounds_to_quantifier` callers in `codegen/aliases.py`, `codegen/model_emitter.py`

- [ ] **Step 1: Find remaining bounds_to_quantifier callers**

Run: `rg "bounds_to_quantifier|quantifier_to_bounds" src/`

For each call site outside `utils/quantifiers.py`, decide:
- If it's a flavour emit context → use `flavour.visit(quantifier)` instead
- If it's `codegen/aliases.py` or `codegen/model_emitter.py` → inline a tiny private helper or have it call `GbnfFlavour().visit(quantifier)` (Lark-friendly suffix syntax)

- [ ] **Step 2: Replace `bounds_to_quantifier(q.min, q.max)` call sites**

In `src/lexic/codegen/aliases.py:36+`: replace the `from lexic.utils.quantifiers import bounds_to_quantifier` import and call site. Use:

```python
from lexic.grammars.gbnf.flavour import GbnfFlavour

_GBNF = GbnfFlavour()

def _format_quantifier(q):
    return _GBNF.visit(q)
```

Or just inline the small `(min, max) → str` logic if codegen needs it without a flavour dependency:

```python
def _suffix_quantifier(q):
    if q.min == 1 and q.max == 1: return ""
    if q.min == 0 and q.max == 1: return "?"
    if q.min == 0 and q.max is None: return "*"
    if q.min == 1 and q.max is None: return "+"
    if q.min == q.max: return f"{{{q.min}}}"
    if q.max is None: return f"{{{q.min},}}"
    return f"{{{q.min},{q.max}}}"
```

- [ ] **Step 3: Replace `quantifier_to_bounds(text)` callers**

In `src/lexic/grammars/gbnf/flavour.py` and `src/lexic/grammars/abnf/flavour.py`: the `parse_quantifier` method currently calls `quantifier_to_bounds`. Inline the parse logic directly. For GBNF:

```python
@staticmethod
def parse_quantifier(text: str) -> IrQuantifier:
    if not text or text == "":
        return IrQuantifier(1, 1)
    if text == "?": return IrQuantifier(0, 1)
    if text == "*": return IrQuantifier(0, None)
    if text == "+": return IrQuantifier(1, None)
    inner = text[1:-1]
    if "," in inner:
        lo_str, hi_str = inner.split(",", 1)
        lo = int(lo_str)
        hi = int(hi_str) if hi_str else None
        return IrQuantifier(lo, hi)
    n = int(inner)
    return IrQuantifier(n, n)
```

ABNF version (ported from the existing `abnf/flavour.py:31-43`):

```python
@staticmethod
def parse_quantifier(text: str) -> IrQuantifier:
    # ABNF forms: '*', '*N', 'N*', 'N*M', 'N'
    if text == "*":
        return IrQuantifier(0, None)
    if text.startswith("*"):
        return IrQuantifier(0, int(text[1:]))
    if "*" in text:
        lo_str, hi_str = text.split("*", 1)
        lo = int(lo_str)
        hi = int(hi_str) if hi_str else None
        return IrQuantifier(lo, hi)
    n = int(text)
    return IrQuantifier(n, n)
```

Same algorithm as today; only the class rename (`Quantifier` →
`IrQuantifier`) changes. No `quantifier_to_bounds` import.

- [ ] **Step 4: Delete files**

```bash
rm src/lexic/grammars/gbnf/emitter.py
rm src/lexic/grammars/abnf/emitter.py
rm src/lexic/utils/quantifiers.py
rm tests/unit/lexic/grammars/gbnf/test_emitter.py
rm tests/unit/lexic/grammars/abnf/test_emitter.py
rm tests/unit/lexic/utils/test_quantifiers.py
```

Edit `src/lexic/ir/emit.py` to remove `FlavourEmitter` class entirely, leaving only `render_specs`. The `emitter` ClassVar on `Flavour` should be removed too.

- [ ] **Step 5: Edit `Flavour` to drop `emitter` ClassVar**

In `src/lexic/grammars/flavour.py`, remove:
```python
if TYPE_CHECKING:
    from lexic.ir.emit import FlavourEmitter
...
emitter: ClassVar[type["FlavourEmitter"]]
```

In each concrete flavour (`GbnfFlavour`, `AbnfFlavour`), remove the `emitter = GbnfEmitter` / `emitter = AbnfEmitter` line.

- [ ] **Step 6: Run tests**

```bash
tools/auto_fix.sh
uv run pytest -q
```

Expected: PASS. If any test imports the deleted modules, update the import.

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "delete FlavourEmitter hierarchy and utils/quantifiers

FlavourEmitter ABC + GbnfEmitter + AbnfEmitter are replaced by the
unified per-flavour action dispatch tables introduced in Tasks 3.3-3.4.
utils/quantifiers.py is absorbed: parse logic inlined in each flavour's
parse_quantifier; emit logic inlined in each flavour's action table."
```

---

### Task 3.8: Switch top-level `dump()` to `IrMetaEmitter().visit()`

**Files:**
- Modify: `src/lexic/ir/walk.py`
- Test: `tests/unit/lexic/ir/test_walk.py`

- [ ] **Step 1: Update `dump()`**

Replace the shim in `walk.py`:

```python
def dump(node: IrNode, *, indent: int = 0) -> str:
    """Pretty-print an IR AST node for debugging via IrMetaEmitter."""
    if indent == 0:
        return IrMetaEmitter().visit(node)
    return node.emit(indent)
```

(The `indent` kwarg is preserved for callers that pass a non-zero base indent.)

- [ ] **Step 2: Run full suite**

Run: `uv run pytest -q` — PASS.

- [ ] **Step 3: Commit**

```bash
git add src/lexic/ir/walk.py
git commit -m "ir: route dump() through IrMetaEmitter().visit()

The free-standing dump() function now uses the IrEmitter machinery.
Future debug renderers extend IrMetaEmitter instead of editing dump()."
```

---

## Step 4 — Promote LarkFlavour to a full peer

### Task 4.1: Create `LarkEscapes`

**Files:**
- Create: `src/lexic/grammars/lark/__init__.py`
- Create: `src/lexic/grammars/lark/escapes.py`
- Create: `tests/unit/lexic/grammars/lark/__init__.py` (empty)
- Create: `tests/unit/lexic/grammars/lark/test_init_lark.py`
- Create: `tests/unit/lexic/grammars/lark/test_escapes.py`

- [ ] **Step 1: Write failing test**

`tests/unit/lexic/grammars/lark/test_escapes.py`:

```python
"""Tests for LarkEscapes — encode/decode for Lark string literals."""

from __future__ import annotations

from lexic.grammars.lark.escapes import LarkEscapes


def test_lark_escapes_newline():
    assert LarkEscapes.encode("\n") == "\\n"
    assert LarkEscapes.decode("\\n") == "\n"


def test_lark_escapes_quote():
    assert LarkEscapes.encode('"') == '\\"'
    assert LarkEscapes.decode('\\"') == '"'


def test_lark_escapes_backslash():
    assert LarkEscapes.encode("\\") == "\\\\"
    assert LarkEscapes.decode("\\\\") == "\\"
```

- [ ] **Step 2: Implement `LarkEscapes`**

`src/lexic/grammars/lark/escapes.py`:

```python
"""LarkEscapes — escape codec for Lark string literals.

Lark accepts standard Python-like escapes inside "..." terminals.
"""

from __future__ import annotations

from lexic.ir.escapes import EscapeCodec


class LarkEscapes(EscapeCodec):
    SHORT_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\"}
```

`src/lexic/grammars/lark/__init__.py`:

```python
"""Lark grammar flavour — first-class peer of GbnfFlavour and AbnfFlavour."""

from __future__ import annotations

from lexic.grammars.lark.flavour import LarkFlavour

__all__ = ["LarkFlavour"]
```

`tests/unit/lexic/grammars/lark/test_init_lark.py`:

```python
def test_lark_init_exports_flavour():
    from lexic.grammars.lark import LarkFlavour
    assert LarkFlavour.name == "lark"
```

`__init__.py` will fail until Task 4.3 lands `flavour.py`. Skip the `test_init_lark.py` for now if pytest collects it eagerly; add `@pytest.mark.skip(reason="awaits Task 4.3")` to it for the moment.

- [ ] **Step 3: Run tests**

Run: `uv run pytest tests/unit/lexic/grammars/lark/test_escapes.py -v` — PASS.

- [ ] **Step 4: Commit**

```bash
git add src/lexic/grammars/lark/ tests/unit/lexic/grammars/lark/
git commit -m "lark: scaffold grammars/lark/ package + LarkEscapes

Empty flavour stub for the LarkFlavour promotion. Escape codec lands
first since it's the lowest-dependency piece."
```

---

### Task 4.2: Write the Lark meta-grammar for parsing `.lark` files

**Files:**
- Create: `src/lexic/grammars/lark/meta_grammar.py`
- Test: deferred to Task 4.3 (testing the meta-grammar requires a Flavour to drive `MetaGrammarParser`)

- [ ] **Step 1: Study existing meta-grammars**

Read: `src/lexic/grammars/gbnf/meta_grammar.py` and `src/lexic/grammars/abnf/meta_grammar.py`. Note the canonical `ir_*` tag names (`ir_rule`, `ir_alternation`, `ir_sequence`, `ir_item`, `ir_literal`, `ir_charclass`, `ir_ruleref`, `ir_group`, `ir_quantifier`). These are required by `MetaGrammarParser` regardless of source flavour.

- [ ] **Step 2: Author `meta_grammar.py`**

`src/lexic/grammars/lark/meta_grammar.py`:

```python
"""Lark meta-grammar — parses user-written .lark files into IrAst.

Supports the Lark grammar subset that maps cleanly onto IrNode types:
  - rule_name : body
  - alternation with '|'
  - sequences (space-separated)
  - quantifiers ?, *, +
  - "literal" strings
  - /regex/ char-class-style terminals (limited: bracket forms only)
  - rule references (NAME)
  - grouping ()
  - // line comments

Out of scope (raise UnsupportedConstructError at meta_parser boundary):
  - %declare / %ignore / %import directives
  - templates / parameterised rules
  - tree shaping operators ([], !, ?inline)
  - regex flags
"""

META_GRAMMAR = r"""
start: ir_rule+

// A rule definition. The LHS NAME may be lowercase (a regular rule) or
// uppercase (a Lark terminal). Both produce the same IrRule shape; the
// uppercase/terminal distinction is a Lark-side parser concern that does
// not surface in the IR. Terminal bodies are typically a single
// /regex/ form — represented as an IrCharClass + quantifier.
ir_rule: NAME ":" ir_alternation

ir_alternation: ir_sequence ("|" ir_sequence)*

ir_sequence: ir_item+

ir_item: ir_atom IR_QUANTIFIER?
       | ir_atom

ir_atom: ir_literal
       | ir_charclass
       | ir_ruleref
       | ir_group

ir_literal: ESCAPED_STRING
// /[chars]<quant>?/ — a regex terminal. The body must be a single
// bracketed char-class optionally followed by an internal quantifier,
// which lifts onto the surrounding IrItem. Out-of-scope regex features
// (anchors, lookaround, groups inside the slashes) trip
// UnsupportedConstructError at the meta_parser boundary.
ir_charclass: "/" CHARCLASS_INTERIOR INTERNAL_QUANTIFIER? "/"
ir_ruleref: NAME
ir_group: "(" ir_alternation ")"

IR_QUANTIFIER: "?" | "*" | "+"
// Internal quantifier inside a regex terminal: + * ? {n} {n,} {n,m}.
// Lifted onto the IrItem during meta-parsing.
INTERNAL_QUANTIFIER: /[+*?]|\{[0-9]+(,[0-9]*)?\}/

NAME: /[a-zA-Z_][a-zA-Z0-9_]*/
ESCAPED_STRING: /"([^"\\]|\\.)*"/
CHARCLASS_INTERIOR: /\[[^\/\n]+\]/

COMMENT: /\/\/[^\n]*/
%ignore COMMENT
%ignore /[ \t\n\r]+/   // wholesale whitespace incl. blank lines between rules — matches GBNF meta-grammar convention
"""
```

**Meta-grammar extension rationale (D1-B decision).** Beyond the minimal
subset, this meta-grammar accepts:

1. **Uppercase NAME on the LHS** (Lark terminal definitions like
   `NUMBER:`). The IrRule shape is identical to a lowercase-named rule;
   the Lark-side terminal-vs-rule distinction is reconstructed at codegen
   time from the case of `spec.rule_name`.

2. **Internal quantifier inside `/regex/`** (e.g. `/[0-9]+/`). Lifted onto
   the surrounding `IrItem.quantifier` during meta-parsing. So
   `NUMBER: /[0-9]+/` becomes an `IrRule` whose body is
   `IrItem(IrCharClass("0-9"), IrQuantifier(1, None))`.

⚠️ **Still out of scope** (trip `UnsupportedConstructError` at the
meta_parser boundary): `~n..m` quantifier, multi-char regex bodies
(anything beyond a single bracketed char class), regex anchors / groups
/ lookaround, `[...]` tree-shaping operators, templates, `%declare` /
`%ignore` / `%import` directives.

- [ ] **Step 3: Wire INTERNAL_QUANTIFIER lifting in `MetaGrammarParser`**

The meta-grammar captures `INTERNAL_QUANTIFIER` inside `ir_charclass`, but
the IR shape attaches quantifiers to the surrounding `IrItem`, not to the
`IrCharClass` leaf. The meta-parser's transformer (in
`src/lexic/parsing/meta_parser.py`) handles `ir_item` construction; that
code needs a Lark-specific branch: when an `ir_charclass` token carries
an `INTERNAL_QUANTIFIER`, parse the quantifier via
`flavour.parse_quantifier(text)` and apply it to the constructed
`IrItem`. If the surrounding `ir_item` *also* declares an outer
quantifier (e.g. `/[0-9]+/*`), reject with `UnsupportedConstructError` —
double quantification is not a meaningful shape.

Verify with a test for `NUMBER: /[0-9]+/` parsing into
`IrRule("NUMBER", IrAlternation((IrSequence((IrItem(IrCharClass("0-9"), IrQuantifier(1, None)),)),)))`.

- [ ] **Step 4: Commit (no test yet)**

```bash
git add src/lexic/grammars/lark/meta_grammar.py
git commit -m "lark: minimal Lark meta-grammar (rules, alts, seqs, quants, literals)

Subset covering what we need to express the ground-truth grammars in
Lark form. Tighter than full Lark — out-of-scope features (%declare,
templates, ~n..m) trip MetaGrammarParser's UnsupportedConstructError
fallthrough."
```

---

### Task 4.3: Implement `LarkFlavour`

**Files:**
- Create: `src/lexic/grammars/lark/flavour.py`
- Test: `tests/unit/lexic/grammars/lark/test_flavour.py`

- [ ] **Step 1: Read current `parsing/lark_builder.py`**

Already reviewed during planning. The non-value_str helpers
(`_atom_to_lark`, `_seq_to_lark`, `_regex_terminal`, `_bracket`,
including the literal-only-group coercion at line 76-85) move into
`LarkFlavour.action`. The value_str helpers (`_atom_to_lark_regex`,
`_seq_to_lark_regex`) are not ported — Task 4.5 replaces them with
Lark's `!` rule prefix.

- [ ] **Step 2: Write failing test**

`tests/unit/lexic/grammars/lark/test_flavour.py`:

```python
"""Tests for LarkFlavour — emit dispatch table and parse hooks."""

from __future__ import annotations

from lexic.grammars.lark.flavour import LarkFlavour
from lexic.ir.nodes import (
    IrAlternation, IrCharClass, IrItem, IrLiteral, IrQuantifier,
    IrRule, IrSequence,
)


def test_lark_renders_quantifier_symbolic():
    assert LarkFlavour().visit(IrQuantifier(0, 1)) == "?"
    assert LarkFlavour().visit(IrQuantifier(0, None)) == "*"
    assert LarkFlavour().visit(IrQuantifier(1, None)) == "+"
    assert LarkFlavour().visit(IrQuantifier(1, 1)) == ""


def test_lark_renders_literal_as_string():
    assert LarkFlavour().visit(IrLiteral("x")) == '"x"'


def test_lark_renders_charclass_as_regex_terminal():
    out = LarkFlavour().visit(IrCharClass("a-z"))
    assert out == "/[a-z]/"


def test_lark_renders_rule_with_colon_separator():
    rule = IrRule("r", IrAlternation((IrSequence((IrItem(IrLiteral("x")),)),)))
    assert LarkFlavour().visit(rule) == 'r: "x"'


def test_lark_parse_quantifier_simple():
    assert LarkFlavour.parse_quantifier("?") == IrQuantifier(0, 1)
    assert LarkFlavour.parse_quantifier("*") == IrQuantifier(0, None)
    assert LarkFlavour.parse_quantifier("+") == IrQuantifier(1, None)
    assert LarkFlavour.parse_quantifier("") == IrQuantifier(1, 1)
```

- [ ] **Step 3: Implement `LarkFlavour`**

`src/lexic/grammars/lark/flavour.py`:

```python
"""LarkFlavour — emits and parses Lark grammar syntax.

Lark is a first-class peer of GBNF and ABNF. The same LarkFlavour drives
both the user-facing .lark file format and the internal codegen target
used by parsing/lark_builder.py to construct the runtime Lark parser.
"""

from __future__ import annotations

from lexic.exceptions import UnsupportedConstructError
from lexic.grammars.flavour import Flavour
from lexic.grammars.lark.escapes import LarkEscapes
from lexic.grammars.lark.meta_grammar import META_GRAMMAR
from lexic.ir.nodes import (
    IrAlternation, IrAst, IrCharClass, IrGroup, IrItem, IrLiteral,
    IrQuantifier, IrRule, IrRuleRef, IrSequence,
)
from lexic.utils.names import to_lark_name


_LARK_TERMINAL_QUANTS = frozenset({"", "?", "*", "+"})


def _emit_lark_quantifier(q, _r):
    """Render a quantifier in Lark suffix-syntax. Matches the existing
    bounds_to_quantifier output in utils/quantifiers.py — preserves
    byte-equality with the legacy lark_builder. (Lark's `~n..m` form is
    accepted parse-side but never produced on emit.)
    """
    key = (q.min, q.max)
    if key in LarkFlavour.quantifier_symbols:
        return LarkFlavour.quantifier_symbols[key]
    if q.max is None:
        return f"{{{q.min},}}"
    if q.min == q.max:
        return f"{{{q.min}}}"
    return f"{{{q.min},{q.max}}}"


def _bracket(pattern, negated):
    """Lark bracket form for a char-class, with `/` escaped (Lark regex delim)."""
    return f"[{'^' if negated else ''}{pattern.replace('/', chr(92) + '/')}]"


def _bounds_to_regex(q):
    """{n}/{n,}/{n,m} form for embedding inside a regex."""
    if q.min == q.max:
        return f"{{{q.min}}}"
    if q.max is None:
        return f"{{{q.min},}}"
    return f"{{{q.min},{q.max}}}"


def _regex_terminal(pattern, q):
    """Render a Lark regex terminal `/pattern/<quantifier>` with zero-width fix.

    Ported from src/lexic/parsing/lark_builder.py:47-60. Lark only allows
    ?/*/+ as *external* quantifiers; bounded forms must embed inside the
    regex. Q(0,n) with finite n would produce `/pattern{0,n}/` which is
    zero-width — rejected by Lark's dynamic Earley. Rewrite to
    `/pattern{1,n}/?` (same language).
    """
    if q.min == 1 and q.max == 1:
        return f"/{pattern}/"
    if q.min == 0 and q.max == 1:
        return f"/{pattern}/?"
    if q.min == 0 and q.max is None:
        return f"/{pattern}/*"
    if q.min == 1 and q.max is None:
        return f"/{pattern}/+"
    if q.min == 0 and q.max is not None:
        return f"/{pattern}{_bounds_to_regex(IrQuantifier(1, q.max))}/?"
    return f"/{pattern}{_bounds_to_regex(q)}/"


def _is_literal_only_group(group):
    """True if every atom under the group is an IrLiteral. Lark drops
    anonymous string terminals — these need regex-form rendering."""
    return all(
        isinstance(sub.atom, IrLiteral)
        for arm in group.body.arms
        for sub in arm.items
        if isinstance(sub, IrItem)
    )


def _emit_lark_item(item, recurse):
    """Render an IrItem. Ports lark_builder._atom_to_lark including:
    - LarkEscapes.encode on literal values
    - slash-escape inside char classes
    - literal-only-group → regex form coercion
    - zero-width fix for Q(0, finite)
    """
    atom = item.atom
    q = item.quantifier
    q_str = recurse(q)
    if isinstance(atom, IrLiteral):
        return f'"{LarkEscapes.encode(atom.value)}"{q_str}'
    if isinstance(atom, IrCharClass):
        return _regex_terminal(_bracket(atom.pattern, atom.negated), q)
    if isinstance(atom, IrRuleRef):
        return f"{recurse(atom)}{q_str}"
    if isinstance(atom, IrGroup):
        if _is_literal_only_group(atom):
            return _emit_literal_group_as_regex(atom, q)
        body = recurse(atom.body)
        return f"({body}){q_str}"
    raise UnsupportedConstructError(
        f"LarkFlavour: no renderer for atom type {type(atom).__name__!r}"
    )


def _emit_literal_group_as_regex(group, q):
    """A group whose arms are all literals must render via regex so Lark
    preserves the matched token in children. Used inside non-value_str
    rules — value_str rules instead use the `!` rule prefix (Task 4.5)
    which preserves anonymous tokens rule-wide. Ports the literal-only
    branch of the legacy _atom_to_lark (lark_builder.py:76-85)."""
    from lexic.ir.regex_portable import literal_to_regex_pattern
    arm_patterns = []
    for arm in group.body.arms:
        parts = []
        for sub in arm.items:
            if isinstance(sub, IrItem) and isinstance(sub.atom, IrLiteral):
                parts.append(literal_to_regex_pattern(sub.atom.value))
        arm_patterns.append("".join(parts))
    pattern = "|".join(arm_patterns)
    return _regex_terminal(f"({pattern})", q)


class LarkFlavour(Flavour):
    name = "lark"
    extensions = (".lark",)
    meta_grammar = META_GRAMMAR
    escapes = LarkEscapes
    line_comment = "//"

    # No punctuation ClassVars — `action[IrRule]` below uses ":" as the
    # rule separator; `action[IrAlternation]` uses " | " as the joiner;
    # the empty-body sentinel `""` lives in `action[IrSequence]`'s
    # `or '""'` fallthrough.

    quantifier_symbols = {(1, 1): "", (0, 1): "?", (0, None): "*", (1, None): "+"}

    # Note: IrRuleRef and IrRule names go through to_lark_name() — Lark
    # rejects hyphens in rule names, while GBNF/ABNF allow them. This is
    # a Lark-specific normalisation, not a general IR concern.
    action = {
        IrLiteral:     lambda n, _r: f'"{LarkEscapes.encode(n.value)}"',
        IrCharClass:   lambda n, _r: f"/[{'^' if n.negated else ''}{n.pattern}]/",
        IrRuleRef:     lambda n, _r: to_lark_name(n.name),
        IrGroup:       lambda n, r:  f"({r(n.body)})",
        IrQuantifier:  _emit_lark_quantifier,
        IrItem:        _emit_lark_item,
        IrSequence:    lambda n, r:  " ".join(r(it) for it in n.items) or '""',
        IrAlternation: lambda n, r:  " | ".join(r(arm) for arm in n.arms) or '""',
        IrRule:        lambda n, r:  f"{to_lark_name(n.name)}: {r(n.body)}",
        IrAst:         lambda n, r:  "\n".join(r(rule) for rule in n.rules) + "\n",
    }

    @staticmethod
    def parse_quantifier(text: str) -> IrQuantifier:
        if not text or text == "":
            return IrQuantifier(1, 1)
        if text == "?": return IrQuantifier(0, 1)
        if text == "*": return IrQuantifier(0, None)
        if text == "+": return IrQuantifier(1, None)
        # ~n or ~n..m
        if text.startswith("~"):
            inner = text[1:]
            if ".." in inner:
                lo_str, hi_str = inner.split("..", 1)
                lo = int(lo_str)
                hi = int(hi_str) if hi_str else None
                return IrQuantifier(lo, hi)
            n = int(inner)
            return IrQuantifier(n, n)
        raise UnsupportedConstructError(f"Lark quantifier {text!r} not recognised")

    @staticmethod
    def parse_charclass(text: str) -> tuple[str, bool]:
        # Lark embeds char classes inside /.../ as regex; the meta-grammar
        # CHARCLASS_INTERIOR captures the bracketed [...] portion.
        inner = text.strip("[]")
        negated = inner.startswith("^")
        if negated:
            inner = inner[1:]
        return inner, negated
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/unit/lexic/grammars/lark/test_flavour.py -v` — PASS.

- [ ] **Step 5: Remove the `test_init_lark.py` skip**

Edit `tests/unit/lexic/grammars/lark/test_init_lark.py` to remove the skip marker.
Run: `uv run pytest tests/unit/lexic/grammars/lark/ -v` — PASS.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "lark: implement LarkFlavour with action table + parse hooks

Emits Lark grammar syntax (colon separator, /regex/ terminals, ~n..m
quantifiers). Parses the symbolic and ~-style quantifiers. Char-classes
embed inside /.../."
```

---

### Task 4.4: Register `LarkFlavour` in `grammars/__init__.py`

**Files:**
- Modify: `src/lexic/grammars/__init__.py`
- Test: `tests/unit/lexic/grammars/test_init_grammars.py`

- [ ] **Step 1: Write failing test**

Append to `tests/unit/lexic/grammars/test_init_grammars.py` (or create per mirror convention):

```python
def test_lark_flavour_registered():
    from lexic.grammars import get_flavour, flavour_for_extension
    from lexic.grammars.lark.flavour import LarkFlavour

    assert get_flavour("lark") is LarkFlavour
    assert flavour_for_extension(".lark") is LarkFlavour
```

- [ ] **Step 2: Modify `grammars/__init__.py`**

Add the LarkFlavour registration. Read the current file first to see how GBNF/ABNF are registered, then mirror:

```python
from lexic.grammars.lark.flavour import LarkFlavour

register_flavour(LarkFlavour)
```

- [ ] **Step 3: Run tests**

Run: `uv run pytest tests/unit/lexic/grammars/test_init_grammars.py -v` — PASS.

- [ ] **Step 4: Commit**

```bash
git add src/lexic/grammars/__init__.py tests/unit/lexic/grammars/test_init_grammars.py
git commit -m "grammars: register LarkFlavour for .lark extension"
```

---

### Task 4.5: Migrate `parsing/lark_builder.py` to use `LarkFlavour`

**Files:**
- Modify: `src/lexic/parsing/lark_builder.py`
- Test: existing integration suite

- [ ] **Step 1: Read current `lark_builder.py` and confirm what stays**

The non-value_str helpers (`_atom_to_lark`, `_seq_to_lark`, `_regex_terminal`,
`_bracket`) become dispatch entries on `LarkFlavour` (covered in Task 4.3).
The value_str regex-coercion path (`_atom_to_lark_regex`, `_seq_to_lark_regex`)
is **deleted entirely** — replaced by Lark's `!` rule-prefix.

**Why `!` instead of regex coercion** (empirically verified 2026-05-14):

Lark's `!` rule prefix keeps every matched token (including anonymous
string literals) in the rule's `children` list. A `value_str` rule
contains only literals, char classes, and groups of those (no rule
refs per CLAUDE.md). Under `!`:

  - Literal `"+"` → `Token('PLUS', '+')` child.
  - Char class `/[0-9]/+` → one `Token('__ANON_X', d)` per matched char.
  - Group `("+"|"-")` → one Token for whichever arm matched.

The existing `_build_value_str` transformer at
`src/lexic/parsing/transformer/build_transformer.py:105` already
joins child Token values: `"".join(str(c) for c in children)`.
Works unchanged under `!`. No transformer edit needed.

Net effect: drop `_atom_to_lark_regex`, `_seq_to_lark_regex`, and the
`if spec.kind == "value_str"` regex branch in `_emit_rule`. The
`_is_literal_only_group` coercion in `_atom_to_lark` (for non-value_str
rules with literal-only groups) **stays** — `!` is per-rule, not
per-atom; non-value_str rules can't use it without changing the
transformer's position-based field binding.

- [ ] **Step 2: Rewrite `parsing/lark_builder.py`**

```python
"""lark_builder — RuleSpec list → Lark grammar + Transformer.

Thin orchestrator over render_specs() with the single LARK singleton.
value_str rules get the Lark `!` rule prefix so their matched literal
tokens survive Lark's anonymous-terminal filter.
"""

from __future__ import annotations

import lark

from lexic.grammars.lark.flavour import LARK
from lexic.ir.emit import render_specs
from lexic.ir.spec import RuleSpec
from lexic.parsing.transformer.build_transformer import build_transformer
from lexic.utils.names import to_lark_name


def _lark_rule_prefix(spec: RuleSpec) -> str:
    """`!` keeps anonymous tokens; value_str rules need it so the
    transformer's child-joining recovers the matched string."""
    return "!" if spec.kind == "value_str" else ""


def build_lark(
    specs: list[RuleSpec], classes: dict[str, type], start_rule: str
) -> tuple[str, lark.Lark, lark.Transformer]:
    """One-call helper for compile.py: specs → (grammar_str, parser, transformer)."""
    grammar_str = render_specs(specs, LARK, rule_prefix=_lark_rule_prefix)
    parser = lark.Lark(
        grammar_str,
        parser="earley",
        ambiguity="resolve",
        start=to_lark_name(start_rule),
    )
    transformer = build_transformer(specs, classes)
    return grammar_str, parser, transformer
```

This requires `render_specs` (defined in Task 3.5) to already accept the
`rule_prefix=` kwarg. Task 3.5's signature already covers this — no
rewrite needed here. `render_specs` itself stays the 4-line composition;
all per-flavour punctuation lives inside the action lambdas. Lark is the
only consumer that passes `rule_prefix`; GBNF/ABNF pass `None`.

Name normalisation note: `render_specs` calls `flavour.visit(spec.to_ir_rule())`,
which routes through `action[IrRule]`. LarkFlavour's `action[IrRule]` runs
the rule name through `to_lark_name`. So Lark output is hyphen-free at
the action layer, not at the render_specs layer. No name-transform hook
on `render_specs` is needed.

- [ ] **Step 3: Run tests**

```bash
tools/auto_fix.sh
uv run pytest -q
```

Expected: PASS. The runtime parser construction now goes through `LARK` +
`!` prefix instead of the regex-coercion path.

If integration tests fail, the most likely cause is a subtle rendering mismatch (e.g. char-class form, escape encoding). Compare the produced grammar string against what the old `lark_builder.py` produced for the same input.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "parsing: route lark_builder through LARK + ! prefix for value_str

Single LarkFlavour singleton drives all Lark codegen. value_str rules
get Lark's '!' rule prefix, which keeps anonymous-literal tokens in
the parse tree — the existing transformer joins child Token values
without changes. The legacy regex-coercion path (_atom_to_lark_regex,
_seq_to_lark_regex) is deleted; LarkRegexFlavour is not created."
```

---

### Task 4.6: Integration test — `.lark` file round-trip

**Files:**
- Create: `resources/ground_truth/arithmetic.lark`
- Create: `tests/integration/test_compile_grammar_lark.py`

- [ ] **Step 1: Author `arithmetic.lark`**

Read `resources/ground_truth/arithmetic.gbnf` first to see the structure.

`resources/ground_truth/arithmetic.lark`:

```lark
// arithmetic.lark — Lark equivalent of arithmetic.gbnf
start: expr
expr: term (("+" | "-") term)*
term: factor (("*" | "/") factor)*
factor: NUMBER | "(" expr ")"
NUMBER: /[0-9]+/
```

(Or simpler — match the exact arithmetic.gbnf if it's smaller. Read it to verify.)

- [ ] **Step 2: Write failing test**

`tests/integration/test_compile_grammar_lark.py`:

```python
"""Integration: compile a .lark file end-to-end."""

from __future__ import annotations

from pathlib import Path

from lexic.compile import compile_from_path


def test_compile_arithmetic_lark():
    path = Path(__file__).parent.parent.parent / "resources" / "ground_truth" / "arithmetic.lark"
    g = compile_from_path(path)
    # Smoke: a valid arithmetic expression parses.
    instance = g.parse("1+2")
    assert instance is not None
    # Round-trip: to_text matches input shape.
    assert instance.to_text() == "1+2"
```

- [ ] **Step 3: Run test**

Run: `uv run pytest tests/integration/test_compile_grammar_lark.py -v`

If failures occur, iterate on the Lark meta-grammar in `src/lexic/grammars/lark/meta_grammar.py` (Task 4.2) — add the smallest meta-grammar feature needed to parse `arithmetic.lark`. Repeat until green.

- [ ] **Step 4: Commit**

```bash
git add resources/ground_truth/arithmetic.lark tests/integration/test_compile_grammar_lark.py
git commit -m "lark: end-to-end integration test for .lark file compilation"
```

---

### Task 4.6b: Extend `test_full_round_trip.py` to cover `.lark`

**Files:**
- Modify: `tests/integration/test_full_round_trip.py`

The existing round-trip suite parametrises over the seven `.gbnf` files
in `resources/ground_truth/`. The "every ground-truth round-trips
byte-equal" invariant (spec §Invariants) needs explicit Lark coverage
now that LarkFlavour is a peer.

- [ ] **Step 1: Add `arithmetic.lark` to the parametrize list**

Open `tests/integration/test_full_round_trip.py`, find the
`@pytest.mark.parametrize("filename", [...])` block, and add
`"arithmetic.lark"` alongside the seven `.gbnf` files. Make sure the
fixture/expected-rules table (line ~31, `"arithmetic.gbnf": frozenset(...)`)
gets an entry for `"arithmetic.lark"` — the rule set is the same.

- [ ] **Step 2: Confirm the round-trip helper handles `.lark`**

The helper likely picks the flavour via `flavour_for_extension`. After
Task 4.4 registers `.lark`, this should "just work" — but verify.

- [ ] **Step 3: Run**

```bash
uv run pytest tests/integration/test_full_round_trip.py -q
```

PASS expected. If the Lark byte-equal claim fails, it means the LarkFlavour
emit path is producing a different string than what the Lark meta-parser
read in — typically whitespace, quantifier form, or charclass form. Fix
the emit table, not the test.

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_full_round_trip.py
git commit -m "test: round-trip arithmetic.lark alongside the seven gbnf grammars"
```

---

### Task 4.7: Cross-flavour transpilation tests

**Files:**
- Modify: `tests/integration/test_cross_flavour.py`

- [ ] **Step 1: Read existing cross-flavour tests**

Run: `cat tests/integration/test_cross_flavour.py`

- [ ] **Step 2: Add Lark conversion cases**

Add tests for GBNF → Lark and ABNF → Lark conversions. Pattern: parse a grammar in source flavour, render with target flavour via `flavour.visit(ast)` or `render_specs(specs, flavour)`, compile the result, verify it parses the same strings.

```python
def test_gbnf_to_lark_round_trip():
    from lexic.compile import compile_text
    from lexic.grammars.lark.flavour import LarkFlavour
    from lexic.ir.emit import render_specs

    gbnf_text = 'root ::= "x" | "y"'
    g = compile_text(gbnf_text, flavour="gbnf")
    lark_text = render_specs(g.specs, LarkFlavour())
    assert "root:" in lark_text
    # Compile the converted text and verify it parses 'x'.
    g2 = compile_text(lark_text, flavour="lark")
    assert g2.parse("x") is not None
```

- [ ] **Step 3: Run tests**

Run: `uv run pytest tests/integration/test_cross_flavour.py -v` — PASS.

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_cross_flavour.py
git commit -m "test: extend cross-flavour suite with Lark conversions"
```

---

## Step 5 — Token reservation (positional only)

### Task 5.1: Implement `_check_no_positional_token_syntax` and wire into `GbnfFlavour.pre_parse_check`

**Files:**
- Modify: `src/lexic/grammars/gbnf/flavour.py`
- Test: `tests/integration/test_token_reservation.py`

- [ ] **Step 1: Write failing tests**

`tests/integration/test_token_reservation.py`:

```python
"""Integration: GBNF positional token-reference syntax is rejected."""

from __future__ import annotations

import pytest

from lexic.compile import compile_text
from lexic.exceptions import UnsupportedConstructError


def test_rejects_positional_token_ref():
    with pytest.raises(UnsupportedConstructError, match="token"):
        compile_text('root ::= <think>', flavour="gbnf")


def test_rejects_positional_in_alternation():
    with pytest.raises(UnsupportedConstructError, match="token"):
        compile_text('root ::= "a" | <other>', flavour="gbnf")


def test_quoted_angle_brackets_compile_fine():
    """A literal <think> inside a quoted string must not trip the scanner."""
    g = compile_text('root ::= "<think>"', flavour="gbnf")
    assert g.parse("<think>") is not None


def test_angle_brackets_in_comment_are_ignored():
    """Angle brackets inside # comments must not trip the scanner."""
    src = '# this comment mentions <foo>\nroot ::= "x"'
    g = compile_text(src, flavour="gbnf")
    assert g.parse("x") is not None


def test_indexed_token_not_rejected_in_this_slice():
    """<[N]> stays available — deferred to a future slice with proper negation design."""
    # We don't assert success here (Lark might fail to parse it anyway);
    # we just assert it is NOT raised as UnsupportedConstructError with
    # the positional-token-syntax message.
    try:
        compile_text('root ::= <[0]>', flavour="gbnf")
    except UnsupportedConstructError as exc:
        assert "positional token-reference" not in str(exc)
    except Exception:
        pass  # other failure modes acceptable; the scope here is just the scan


def test_negation_token_not_rejected_by_positional_scanner():
    """!<name> may fail elsewhere (the GBNF meta-grammar parser doesn't
    know it), but must NOT trip the positional-token-reference scanner.
    This test asserts the scanner specifically — the failure mode that
    matters here is which error path fires."""
    from lexic.grammars.gbnf.flavour import _check_no_positional_token_syntax
    # The scanner must accept !<x> without raising.
    _check_no_positional_token_syntax('root ::= !<x>')
    # End-to-end compile may still fail at meta-grammar parse — that's
    # outside this scanner's contract. We only assert the scanner.
```

- [ ] **Step 2: Implement the scanner**

Add to `src/lexic/grammars/gbnf/flavour.py`:

```python
import re

from lexic.exceptions import UnsupportedConstructError


_POSITIONAL_TOKEN = re.compile(r"<([a-zA-Z_][a-zA-Z0-9_]*)>")


def _strip_comments_and_strings(text: str) -> str:
    """Return `text` with # line comments and "..." string literals replaced
    by space characters of the same length (preserves offsets)."""
    out = []
    i = 0
    in_string = False
    while i < len(text):
        ch = text[i]
        if not in_string and ch == "#":
            # consume to end of line
            j = text.find("\n", i)
            if j == -1:
                j = len(text)
            out.append(" " * (j - i))
            i = j
            continue
        if ch == '"':
            in_string = not in_string
            out.append(ch)
            i += 1
            continue
        if in_string:
            out.append(" " if ch != "\n" else ch)
            i += 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def _check_no_positional_token_syntax(text: str) -> None:
    """Reject GBNF positional token-reference syntax <identifier>.

    Scans outside of # line comments and "..." string literals.
    Indexed (<[N]>) and negation (!<name>) refs are NOT checked —
    deferred to a future slice.
    """
    stripped = _strip_comments_and_strings(text)
    # The regex below requires an identifier-start char after `<`, so
    # the indexed form `<[N]>` is structurally excluded (no need for an
    # explicit skip). The negation form `!<name>` does match, so we
    # check the preceding character.
    for match in _POSITIONAL_TOKEN.finditer(stripped):
        start = match.start()
        if start > 0 and stripped[start - 1] == "!":
            continue
        raise UnsupportedConstructError(
            f"GBNF positional token-reference syntax {match.group()!r} is "
            f"reserved for future Vyx use; rename the rule or remove the "
            f"angle brackets"
        )


class GbnfFlavour(Flavour):
    ...

    @classmethod
    def pre_parse_check(cls, text: str) -> None:
        _check_no_positional_token_syntax(text)
```

- [ ] **Step 3: Wire `pre_parse_check` into `MetaGrammarParser.parse`**

In `src/lexic/parsing/meta_parser.py`, find the `parse(self, text)` method and add a call at the top:

```python
def parse(self, text: str) -> IrAst:
    self._flavour.pre_parse_check(text)  # ← add this line
    ...  # existing logic continues
```

If `self._flavour` is the flavour class (not instance), use `self._flavour.pre_parse_check(text)` — `pre_parse_check` is a classmethod. Either form works.

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/integration/test_token_reservation.py -v` — PASS.
Run: `uv run pytest -q` — PASS.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "gbnf: pre-parse scan rejects positional token-reference syntax

<identifier> patterns outside comments and quoted strings raise
UnsupportedConstructError before the Lark parse runs, giving authors
a clear diagnostic. Indexed (<[N]>) and negation (!<name>) refs are
left alone — deferred to a future slice with a proper negation design."
```

---

## Step 6 — Cleanup

### Task 6.1: Delete `ir/helpers.py` and its test

**Files:**
- Delete: `src/lexic/ir/helpers.py`, `tests/unit/lexic/ir/test_helpers.py`
- Modify: `src/lexic/ir/__init__.py`

- [ ] **Step 1: Verify no remaining callers**

Run: `rg "HelperRuleRegistry|from lexic.ir.helpers|ir\.helpers" src/ tests/`

Expected output: only `src/lexic/ir/__init__.py` (export) and the test file. If anything else appears, investigate before deleting.

- [ ] **Step 2: Delete the files**

```bash
rm src/lexic/ir/helpers.py
rm tests/unit/lexic/ir/test_helpers.py
```

- [ ] **Step 3: Remove the export**

Edit `src/lexic/ir/__init__.py`: remove `from lexic.ir.helpers import HelperRuleRegistry` and remove `"HelperRuleRegistry"` from `__all__`.

- [ ] **Step 4: Run tests**

Run: `uv run pytest -q` — PASS.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "ir: delete unused HelperRuleRegistry

Zero production callers since the IrItem cutover. Tests existed but
exercised dead code. Deletion is safe."
```

---

### Task 6.2: (deleted)

Task 4.5 already collapses `LarkBuilder` into `build_lark` with an
inline `build_transformer(specs, classes)` call. Nothing remains for
this task. Skip and renumber if needed.

---

## Step 7 — Wiki + documentation updates

### Task 7.1: Update wiki pages and CLAUDE.md

**Files:**
- Modify: `.wiki/lexic/architecture.md`
- Modify: `.wiki/lexic/flavour-system.md`
- Modify: `.wiki/lexic/ir-shapes.md`
- Modify: `.wiki/lexic/decisions.md` (add new entries)
- Modify: `.wiki/log.md` (append slice-closure entry)
- Delete: `.wiki/lexic/slice-b-status.md`
- Modify: `CLAUDE.md` — update import-exception list

- [ ] **Step 1: Update CLAUDE.md import exceptions AND the slice-b-status reference**

Find the section listing runtime → codegen import edges (around line "The two deliberate exceptions"). The first exception currently reads: `base.py imports lexic.grammars.gbnf.emitter at module scope for to_gbnf()`. Replace the target — `GbnfEmitter` is gone. New text:

> 1. `base.py` imports `lexic.grammars.gbnf.flavour.GbnfFlavour` at module scope for `to_grammar()`. Explicit, eager, one import.

Verify the other exception still applies — `compile.py` → `lexic.codegen` and `lexic.parsing.lark_builder`. That stands.

Also strip the reference to `.wiki/lexic/slice-b-status.md` from CLAUDE.md
("Cutover complete… See `.wiki/lexic/cutover-plan.md` and
`.wiki/lexic/slice-b-status.md`") — slice-b-status retires in Step 7.

- [ ] **Step 2: Update `.wiki/lexic/architecture.md`**

Reflect the new architecture:
- `IrNode` is an ABC with structural protocol methods (children, rebuild, emit)
- `IrDispatch` has three canonical instantiations: `IrVisitor`, `IrTransformer`, `IrEmitter`
- `Flavour` subclasses `IrEmitter[IrNode]`; emission flows through `action` table
- `LarkFlavour` is a first-class peer alongside `GbnfFlavour` and `AbnfFlavour`
- The runtime → codegen exception target has changed (now `GbnfFlavour`, not `GbnfEmitter`)

- [ ] **Step 3: Update `.wiki/lexic/flavour-system.md`**

Reflect:
- `Flavour` is an `IrEmitter` subclass
- `action`, `quantifier_symbols`, `pre_parse_check` are new class attributes
- `FlavourEmitter` ABC and the `emitter` ClassVar are gone
- Step-by-step "adding a new flavour" updated for the action-table pattern
- New entry: LarkFlavour as a worked example

- [ ] **Step 4: Update `.wiki/lexic/ir-shapes.md`**

Reflect:
- `IrNode` structural protocol section (new): `children`, `rebuild`, `emit`
- `Quantifier` → `IrQuantifier` rename
- All node types now inherit from `IrNode` (no more TypeAlias union)

- [ ] **Step 5: Add to `.wiki/lexic/decisions.md`**

Append two new entries:

> ## 2026-05-14 — Intrinsic-on-node IR protocol (P10)
>
> `_CHILDREN`/`_REBUILD`/`_DUMP` central dicts in `walk.py` replaced by methods on `IrNode`. Adding a new IR node type is now a single-file edit. Walk-time logic that varies by caller (flavour emission, codegen passes) stays in external dispatch tables.

> ## 2026-05-14 — `IrEmitter` as the canonical string-producing dispatcher (P11)
>
> All string emission (GBNF, ABNF, Lark, debug dump) is now an `IrEmitter[IrNode]` subclass, the T=str instantiation of `IrDispatch`. `FlavourEmitter` ABC and concrete emitter classes deleted; `Flavour` is itself an `IrEmitter` populated via per-type `action` table. `LarkFlavour` promoted to a first-class peer.

- [ ] **Step 6: Append to `.wiki/log.md`**

```markdown
## 2026-05-14 — Slice B closed; dispatch architecture inverted

- Token reservation (positional only) lands in GbnfFlavour.pre_parse_check
- IrNode promoted to ABC with structural protocol (children/rebuild/emit)
- IrEmitter = IrDispatch[_N, str] added; Flavour subclasses it
- FlavourEmitter ABC + GbnfEmitter + AbnfEmitter deleted
- LarkFlavour promoted to first-class peer; .lark format supported
- utils/quantifiers.py + ir/helpers.py deleted (dead/absorbed)
- See: docs/superpowers/specs/2026-05-14-slice-b-closure-and-dispatch-unification-design.md
```

- [ ] **Step 7: Delete `.wiki/lexic/slice-b-status.md`**

```bash
rm .wiki/lexic/slice-b-status.md
```

Update `.wiki/index.md` to remove the reference to `slice-b-status.md` from the Quick-lookup, Task-routing, and Active-work tables.

- [ ] **Step 8: Verify nothing's broken**

Run: `uv run pytest -q` — PASS (docs changes don't break tests, but rerun anyway).

- [ ] **Step 9: Commit**

```bash
git add -A
git commit -m "wiki + CLAUDE.md: reflect dispatch-unification + slice-B closure

- Architecture page updated for IrNode protocol + IrEmitter hierarchy
- Flavour-system page updated for action dispatch + LarkFlavour
- IR-shapes page updated for IrNode ABC + IrQuantifier rename
- Two new decision entries (P10, P11)
- Log entry for slice closure
- slice-b-status.md retired
- CLAUDE.md runtime->codegen exception target updated"
```

---

## Final verification

- [ ] **Step 1: Full suite + linters**

```bash
uv run pytest -q
uv run ruff check src/ tests/
uv run pylint src/lexic/  # spot-check key modules
```

All green.

- [ ] **Step 2: Ground-truth grammars round-trip**

```bash
uv run pytest tests/integration/ -v
```

Each of the seven ground-truth GBNF grammars must still round-trip byte-equal. The new `arithmetic.lark` must compile and round-trip.

- [ ] **Step 3: Layering invariant test**

```bash
uv run pytest tests/integration/test_layering_invariants.py -v
```

The runtime → codegen edge count is unchanged (two exceptions); only the target of the first exception has moved (from `GbnfEmitter` to `GbnfFlavour`).

- [ ] **Step 4: Confirm cleanup**

```bash
rg "FlavourEmitter|GbnfEmitter|AbnfEmitter|bounds_to_quantifier|quantifier_to_bounds|HelperRuleRegistry" src/ tests/ --type py
```

Expected: no matches.

```bash
test ! -f src/lexic/utils/quantifiers.py
test ! -f src/lexic/ir/helpers.py
test ! -f src/lexic/grammars/gbnf/emitter.py
test ! -f src/lexic/grammars/abnf/emitter.py
test ! -f .wiki/lexic/slice-b-status.md
```

All commands exit zero.

---

## Risk-area mitigations (reminders)

- **Step 1 coverage gap.** If a per-node `emit()` output diverges from the legacy `_DUMP` output, walk.py's `dump()` returns different text. Mitigation: the Task 1.3 tests cover every node type explicitly.
- **Step 3 messiness.** If `FlavourEmitter` deletion (Task 3.7) leaves orphaned imports, `uv run ruff check` catches them.
- **Step 4 Lark meta-grammar coverage.** Start tiny (Task 4.6 uses one `.lark` grammar). Add features incrementally; out-of-scope features must trip `UnsupportedConstructError` cleanly.
- **`base.py` import-edge change.** Task 3.6 makes the swap and Task 7.1 documents it; verify `tests/integration/test_layering_invariants.py` passes after Task 3.6 with the new target.
