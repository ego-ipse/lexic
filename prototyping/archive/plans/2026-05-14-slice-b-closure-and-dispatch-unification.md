# Slice B closure + dispatch unification — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close Slice B (positional token reservation + cleanup) while inverting the IR dispatch architecture: intrinsic data lives on the node, all string emission flows through a unified `IrEmitter` hierarchy. Lexic gains `.lark` as a third user-facing grammar format.

**Architecture:** `IrNode` is an ABC with structural protocol (`children`, `rebuild`, plus Python's `__str__` and `__repr__`). `__str__` is the node's intrinsic canonical-form action — what an `IrEmitter` action would do for this node type in the absence of a flavour override; `IrEmitter` falls through to `str(node)` when no action handles the type. `__repr__` is debug raw visualization — `IrStructure` defines a generic indented walk over `children()`; leaves use the dataclass default. No `emit()` method, no `dump()` function. `IrDispatch` is itself an `IrCollection["IrAction"]` — actions are structural IR data, not opaque callables. `IrAction(target_type, body)` carries an `IrOp` body: a small algebra of typesetting / transformation primitives (`IrText`, `IrField`, `IrRecurse`, `IrSeq`, `IrJoin`, `IrCond`) plus `IrCallable` as an escape hatch for procedural cases. Action bodies are walkable IR trees, so a `Flavour` is expressible in IR — the substrate for the long-stated goal of generating Flavour files from a grammar. `IrDispatch.__call__` walks children, evaluates the action body, falls through to `default` on miss. `IrEmitter` (T=str) is the third canonical instantiation; `Flavour` *is* an `IrEmitter[IrNode]` populated via per-type actions. `FlavourEmitter` ABC + concrete emitters are deleted. `Quantifier` → `IrQuantifier` (an IrNode leaf). `LarkFlavour` joins `GbnfFlavour` and `AbnfFlavour` as a first-class peer.

**Open vs. closed.** Flavours are inherently closed — each fixes the syntax of a target grammar format and may not know every node type. The IR is open — new node types are added without touching any flavour or dispatcher. The two meet at the action-table miss falling through to `default`; soft for partial transformers / visitors, loud for closed-world flavour emitters (`IrEmitter.default` raises `UnsupportedConstructError` when its action table is non-empty and the type missed).

**Tech Stack:** Python 3.12+ · Pydantic v2 · Lark (Earley) · uv · pytest · ruff · pylint

**Spec:** `docs/superpowers/specs/2026-05-14-slice-b-closure-and-dispatch-unification-design.md` (revised 2026-05-15).

---

## Status — 2026-05-15

- **Task 1.1** ✅ Committed (`84652f6`). Deviation from literal plan code: `IrNode` was extended into a richer hierarchy — `IrLeaf` (concrete identity defaults), `IrStructure` (abstract branch base, declares `__dataclass_fields__: ClassVar`), `IrCollection[_T]` (homogeneous variable-length children via `_items_attr: ClassVar[str]`), `IrComposite[*_Ts]` (heterogeneous fixed-arity children via `_child_attrs: ClassVar[tuple[str, ...]]`). Concrete leaves inherit from `IrLeaf`; concrete branches inherit from `IrCollection` or `IrComposite`. `IrAtom` remains a TypeAlias `IrLeaf | IrGroup`.
- **Task 1.2** ✅ Committed (`01177e9`, `ebb9d96`, `7b57aa5`). `children()` and `rebuild()` are auto-implemented on `IrCollection` and `IrComposite` via their ClassVar registrations and `dataclasses.replace()`. No per-node overrides. Non-child extras (`IrRule.name`, `IrAst.start`) are preserved on rebuild automatically.
- **Tasks 1.3 and 1.4** — revised in this plan revision (2026-05-15) per the spec's §Revision 2026-05-15. See the new task sections below — they replace the original Task 1.3/1.4 prose.
- **Task 3.1** — kept but `IrMetaEmitter`'s purpose is clarified (canonical-emit walker, not a dump backend).
- **Task 3.8** — deleted (no `dump()` migration; `dump()` no longer exists).

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

### Task 1.3: Template-method `__str__` on IrNode; mechanical `__repr__` on IrStructure; placeholder canonical notation

**Files:**
- Modify: `src/lexic/ir/nodes.py`
- Modify: `tests/unit/lexic/ir/test_nodes.py`

**Scope of the revision (2026-05-15).** The original Task 1.3 had per-node `emit(indent=0)` methods matching the legacy `_DUMP` byte-for-byte. Replaced by Python's dunder protocol with a template-method shape on `IrNode`:

- **`__str__`** — canonical-form rendering, the node's *intrinsic action*. `IrEmitter.__call__` (Task 1.4 / Task 3.1) falls through to `str(node)` when no `IrAction` is registered for the type. Output for now is a placeholder notation (`LITERAL('a')`, `SEQ(...)`, `Q[0..*]`), deliberately not any user grammar syntax. The eventual `IrFlavour` will replace it.
- **`__repr__`** — debug raw visualization. `IrStructure` defines a generic indented multi-line walk over `_extra_reprs()` + `children()`. Leaves use the dataclass default.

The free function `dump()` and the `_DUMP` dict in `walk.py` are deleted in Task 1.4. No `emit()` method exists on `IrNode`.

**Template-method `__str__`.** Every IR node renders as:

```
f"{_str_name}{_str_opener}{_inner_str()}{_str_closer}"
```

The three ClassVars are declared at `IrNode`. Defaults:
- `_str_name` is **auto-derived in `__init_subclass__`** by stripping `Ir` prefix and uppercasing — `IrRule` → `RULE`, `IrItem` → `ITEM`. Subclasses set it explicitly only when the auto-derivation isn't what we want (e.g. `IrRuleRef` → `REF`, `IrSequence` → `SEQ`, `IrAlternation` → `ALT`, `Quantifier` → `Q`).
- `_str_opener` / `_str_closer` default to `(` and `)`. `Quantifier` overrides to `[` and `]` (subscript/bounds notation, distinct from constructor calls).
- `_inner_str(self) -> str` is the only abstract extension point. `IrLeaf` and `IrStructure` provide defaults; concrete classes override only when they need a non-default shape.

`IrLeaf._inner_str` default: `repr(first_dataclass_field)`. Single-field leaves (`IrLiteral`, `IrRuleRef`) get the right output for free. Multi-field leaves (`IrCharClass`, `Quantifier`) override.

`IrStructure._inner_str` default: `", ".join(_extra_str_parts() + [str(c) for c in children()])`. Extras are non-child dataclass fields, computed via each branch base's `_extra_field_names()` (mirrors `_items_attr` / `_child_attrs` from Task 1.2).

Extras rendering differs by branch flavour:
- `IrCollection._extra_str_parts` → `key=repr(val)` for each extra. Used by `IrAst.start` → `AST(start='r', ...)`.
- `IrComposite._extra_str_parts` → positional `repr(val)` (no `key=` prefix). Used by `IrRule.name` → `RULE('r', ...)`.

**Placeholder `__str__` notation (Q4=B).**

| Node | `str(node)` |
|---|---|
| `IrLiteral("a")` | `LITERAL('a')` |
| `IrCharClass("a-z")` | `CHARCLASS('a-z')` |
| `IrCharClass("0-9", negated=True)` | `CHARCLASS('0-9', negated)` |
| `IrRuleRef("expr")` | `REF('expr')` |
| `Quantifier(1, 1)` | `Q[1]` |
| `Quantifier(0, 1)` | `Q[0..1]` |
| `Quantifier(0, None)` | `Q[0..*]` |
| `IrSequence((IrItem(IrLiteral("a")),))` | `SEQ(ITEM(LITERAL('a'), Q[1]))` |
| `IrAlternation((s1, s2))` | `ALT(SEQ(...), SEQ(...))` |
| `IrGroup(body)` | `GROUP(ALT(...))` |
| `IrRule("r", body)` | `RULE('r', ALT(...))` |
| `IrAst((r,), "r")` | `AST(start='r', RULE('r', ALT(...)))` |

- [ ] **Step 1: Write failing tests**

Add to `tests/unit/lexic/ir/test_nodes.py`:

```python
def test_str_irliteral():
    assert str(IrLiteral("a")) == "LITERAL('a')"


def test_str_ircharclass():
    assert str(IrCharClass("a-z")) == "CHARCLASS('a-z')"
    assert str(IrCharClass("0-9", negated=True)) == "CHARCLASS('0-9', negated)"


def test_str_irruleref():
    assert str(IrRuleRef("expr")) == "REF('expr')"


def test_str_quantifier():
    assert str(Quantifier(1, 1)) == "Q[1]"
    assert str(Quantifier(0, 1)) == "Q[0..1]"
    assert str(Quantifier(0, None)) == "Q[0..*]"
    assert str(Quantifier(2, 5)) == "Q[2..5]"


def test_str_irsequence_joins_items():
    seq = IrSequence((IrItem(IrLiteral("a")), IrItem(IrLiteral("b"))))
    assert str(seq) == "SEQ(ITEM(LITERAL('a'), Q[1]), ITEM(LITERAL('b'), Q[1]))"


def test_str_irrule_shows_name_positional():
    rule = IrRule("r", IrAlternation((IrSequence(()),)))
    assert str(rule) == "RULE('r', ALT(SEQ()))"


def test_str_irast_shows_start_keyed():
    ast = IrAst(rules=(IrRule("r", IrAlternation(())),), start="r")
    assert str(ast) == "AST(start='r', RULE('r', ALT()))"


# __repr__ — indented debug walk
def test_repr_leaf_is_dataclass_default():
    assert repr(IrLiteral("a")) == "IrLiteral(value='a')"


def test_repr_irsequence_is_indented_multiline():
    seq = IrSequence((IrItem(IrLiteral("a")),))
    assert repr(seq) == (
        "IrSequence(\n"
        "  IrItem(\n"
        "    IrLiteral(value='a'),\n"
        "    Quantifier(min=1, max=1)\n"
        "  )\n"
        ")"
    )


def test_repr_irrule_shows_non_child_fields_too():
    rule = IrRule("r", IrAlternation(()))
    assert repr(rule) == "IrRule(\n  name='r',\n  IrAlternation()\n)"
```

Run: `uv run pytest tests/unit/lexic/ir/test_nodes.py -v` — should FAIL.

- [ ] **Step 2: Implement the template on `IrNode`**

```python
class IrNode(ABC):
    """..."""

    _str_name: ClassVar[str]
    _str_opener: ClassVar[str] = "("
    _str_closer: ClassVar[str] = ")"

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if "_str_name" in cls.__dict__:
            return
        cls._str_name = cls.__name__.removeprefix("Ir").upper()

    @abstractmethod
    def _inner_str(self) -> str:
        """Content between the brackets in __str__.

        :returns: Inner string content.
        """

    def __str__(self) -> str:
        return f"{self._str_name}{self._str_opener}{self._inner_str()}{self._str_closer}"

    # children() / rebuild() unchanged from Task 1.2
```

- [ ] **Step 3: Defaults on `IrLeaf` and `IrStructure`**

```python
class IrLeaf(IrNode):
    """..."""
    def _inner_str(self) -> str:
        flds = dataclasses.fields(self)
        return repr(getattr(self, flds[0].name))


class IrStructure(IrNode, ABC):
    """..."""
    __dataclass_fields__: ClassVar[dict[str, dataclasses.Field[Any]]]

    @abstractmethod
    def _extra_field_names(self) -> tuple[str, ...]: ...

    def _extra_reprs(self) -> list[str]:
        return [f"{n}={getattr(self, n)!r}" for n in self._extra_field_names()]

    def _extra_str_parts(self) -> list[str]:
        """IrCollection renders extras keyed; IrComposite overrides for positional."""
        return self._extra_reprs()

    def _inner_str(self) -> str:
        return ", ".join(self._extra_str_parts() + [str(c) for c in self.children()])

    def __repr__(self) -> str:
        parts = self._extra_reprs() + [repr(c) for c in self.children()]
        if not parts:
            return f"{type(self).__name__}()"
        body = ",\n".join(parts)
        indented = "  " + body.replace("\n", "\n  ")
        return f"{type(self).__name__}(\n{indented}\n)"


class IrCollection(IrStructure, Generic[_T]):
    _items_attr: ClassVar[str]
    def _extra_field_names(self) -> tuple[str, ...]:
        return tuple(f.name for f in dataclasses.fields(self) if f.name != self._items_attr)
    # children() / rebuild() unchanged


class IrComposite(IrStructure, Generic[*_Ts]):
    _child_attrs: ClassVar[tuple[str, ...]]
    def _extra_field_names(self) -> tuple[str, ...]:
        return tuple(f.name for f in dataclasses.fields(self) if f.name not in self._child_attrs)
    def _extra_str_parts(self) -> list[str]:
        """Positional extras: just repr(val), no key prefix."""
        return [repr(getattr(self, n)) for n in self._extra_field_names()]
    # children() / rebuild() unchanged
```

- [ ] **Step 4: Per-leaf overrides (minimal)**

```python
@dataclass(frozen=True, slots=True)
class IrLiteral(IrLeaf):
    # _str_name auto = "LITERAL"; _inner_str default = repr(value). Nothing to override.
    value: str


@dataclass(frozen=True, slots=True)
class IrCharClass(IrLeaf):
    # _str_name auto = "CHARCLASS"; multi-field → override _inner_str.
    pattern: str
    negated: bool = False
    def _inner_str(self) -> str:
        return f"{self.pattern!r}, negated" if self.negated else repr(self.pattern)


@dataclass(frozen=True, slots=True)
class IrRuleRef(IrLeaf):
    _str_name: ClassVar[str] = "REF"   # auto would be "RULEREF"
    name: str
    # _inner_str default = repr(name)


@dataclass(frozen=True, slots=True)
class Quantifier(IrLeaf):
    _str_name: ClassVar[str] = "Q"
    _str_opener: ClassVar[str] = "["
    _str_closer: ClassVar[str] = "]"
    min: int = 1
    max: int | None = 1
    def _inner_str(self) -> str:
        if self.min == self.max:
            return str(self.min)
        hi = "*" if self.max is None else str(self.max)
        return f"{self.min}..{hi}"
```

- [ ] **Step 5: Structural classes (overrides only for non-default `_str_name`)**

```python
@dataclass(frozen=True, slots=True, repr=False)
class IrSequence(IrCollection["IrItem"]):
    _items_attr: ClassVar[str] = "items"
    _str_name: ClassVar[str] = "SEQ"   # auto would be "SEQUENCE"
    items: tuple[IrItem, ...] = ()


@dataclass(frozen=True, slots=True, repr=False)
class IrAlternation(IrCollection["IrSequence"]):
    _items_attr: ClassVar[str] = "arms"
    _str_name: ClassVar[str] = "ALT"
    arms: tuple[IrSequence, ...] = ()


@dataclass(frozen=True, slots=True, repr=False)
class IrAst(IrCollection["IrRule"]):
    # _str_name auto = "AST"
    _items_attr: ClassVar[str] = "rules"
    rules: tuple[IrRule, ...] = ()
    start: str = ""


@dataclass(frozen=True, slots=True, repr=False)
class IrGroup(IrComposite["IrAlternation"]):
    # _str_name auto = "GROUP"
    _child_attrs: ClassVar[tuple[str, ...]] = ("body",)
    body: IrAlternation


@dataclass(frozen=True, slots=True, repr=False)
class IrItem(IrComposite["IrAtom", "Quantifier"]):
    # _str_name auto = "ITEM"
    _child_attrs: ClassVar[tuple[str, ...]] = ("atom", "quantifier")
    atom: IrAtom
    quantifier: Quantifier = field(default_factory=Quantifier)


@dataclass(frozen=True, slots=True, repr=False)
class IrRule(IrComposite["IrAlternation"]):
    # _str_name auto = "RULE"
    _child_attrs: ClassVar[tuple[str, ...]] = ("body",)
    name: str
    body: IrAlternation
```

`@dataclass(..., repr=False)` is **required** per concrete structural class so the inherited `IrStructure.__repr__` is not shadowed by the dataclass-generated one. (Dataclass runs *after* `__init_subclass__`, so the auto-derived `_str_name` survives.)

- [ ] **Step 6: Run tests**

Run: `uv run pytest tests/unit/lexic/ir/test_nodes.py -v` — PASS.
Run: `uv run pytest -q` — PASS.

- [ ] **Step 7: Commit**

```bash
git add src/lexic/ir/nodes.py tests/unit/lexic/ir/test_nodes.py
git commit -m "ir: template-method __str__ on IrNode; mechanical __repr__ on IrStructure

__str__ is templated at IrNode level as
f'{_str_name}{_str_opener}{_inner_str()}{_str_closer}'. _str_name is
auto-derived in __init_subclass__ from the class name (strip Ir,
uppercase) unless a subclass declares it explicitly. _str_opener and
_str_closer default to () but Quantifier overrides to []. _inner_str
is the only per-class extension point: IrLeaf default returns
repr(first_field); IrStructure default joins extras and children;
IrComposite renders extras positionally, IrCollection keyed.

__repr__ on IrStructure produces an indented multi-line walk over
extras and children. Concrete structural dataclasses use repr=False
so the inherited __repr__ is not shadowed.

No emit() method, no dump() function — Python's dunder protocol is
the API. Output is a placeholder notation; eventual IrFlavour replaces it."
```

---

### Task 1.4: `IrAction` + `IrOp` algebra in `src/lexic/ir/action.py`; `IrDispatch` interprets `IrOp`; delete `_CHILDREN`/`_REBUILD`/`_DUMP`/`dump()`/`visit`/`generic_visit`

**Files:**
- Create: `src/lexic/ir/action.py` (new file — `IrAction` + `IrOp` hierarchy)
- Create: `tests/unit/lexic/ir/test_action.py`
- Modify: `src/lexic/ir/walk.py`
- Modify: `tests/unit/lexic/ir/test_walk.py`
- Modify: `src/lexic/ir/__init__.py` (re-export `IrAction`, `IrOp`, plus the concrete ops users typically build with)
- Migrate: `src/lexic/ir/derive.py`, `src/lexic/codegen/aliases.py`, `src/lexic/codegen/model_emitter.py` (concrete plan in Step 7)

**Scope of the revision (2026-05-15).**

1. **`IrAction` is structural from day one.** `IrAction(IrComposite["IrOp"])` carries `target_type: type` and `body: IrOp`. The body is a tree of typesetting / transformation operations expressible as IR nodes — no opaque callable. Parsable / codegenable: a future `IrFlavour` grammar parses into a tree of `IrAction(IrOp...)`, and a `PyFlavourCodegenRenderer` emits Python flavour file source from that tree. The dispatch system around `IrAction` doesn't have to change to enable that end-game.

2. **`IrOp` algebra.** A small set of typesetting / transformation primitives:
   - `IrText(text)` — literal text
   - `IrField(field_name)` — `str` of a non-IrNode field on the dispatched node
   - `IrRecurse(field_name)` — result of dispatching into a named IrNode child (looked up in already-visited children)
   - `IrSeq(parts)` — concatenate sub-op results in order
   - `IrJoin(field_name, separator, empty="")` — iterate a tuple-of-IrNode field, look up each result, join with separator (or return `empty` when field is empty)
   - `IrCond(field_name, then_op, else_op)` — boolean field guard
   - `IrCallable(handler)` — escape hatch wrapping an opaque `Callable[[IrNode, tuple[_T, ...]], _T]` for procedural cases (`_HoistTransformer`'s rebuild logic, `_RuleRefFinder`'s side-effect flag, complex emitters that can't be expressed structurally yet)

3. **`IrDispatch` becomes structural.** `IrDispatch(IrCollection["IrAction"])` with `_items_attr = "actions"`. Children are the actions; rebuild reconstructs the table.

4. **Dispatch logic collapses.** `visit` + `generic_visit` + `_combine` + `getattr("visit_<TypeName>", ...)` are replaced by `__call__`: walk children first, look up the action for `type(node)`, evaluate its `body` against `(node, new_children)`. One method, one extension point (`default`).

5. **Soft dispatch at the base.** `__call__` always falls through to `default` on table miss. Closed-world strictness is a flavour concern: `IrEmitter.default` (Task 3.1) raises `UnsupportedConstructError` when `self.actions` is truthy and the type missed. Partial transformers / visitors register actions for the types they care about; everything else falls through to `default` and walks identity (`IrTransformer`) or no-ops (`IrVisitor`).

- [ ] **Step 1: Read existing walk tests for context**

Run: `uv run pytest tests/unit/lexic/ir/test_walk.py -v`. Confirm green pre-change.

- [ ] **Step 2: Locate call sites needing migration**

```bash
uv run rg -n "\bdump\(|\.visit\(|IrDispatch\[" src/ tests/
```

Concrete sites (as of 2026-05-15): `src/lexic/ir/derive.py` (`_RuleRefFinder`, `_HoistTransformer`), `src/lexic/codegen/aliases.py` (`_PatternAliasVisitor`), `src/lexic/codegen/model_emitter.py` (`_IrRepr`). Migration plan per file in Step 7.

- [ ] **Step 3: Create `src/lexic/ir/action.py` — `IrOp` algebra + `IrAction`**

```python
"""IrAction + IrOp — structural action algebra.

An IrDispatch's action table is a tuple of IrAction nodes. Each IrAction
maps a target IrNode type to an IrOp body that describes how to handle
nodes of that type. The IrOp algebra is the small language in which
flavour emitters express their per-type rendering rules:

  IrText("|")                                    literal text
  IrField("name")                                str of a non-IrNode field
  IrRecurse("body")                              result of dispatching self.body
  IrSeq((part1, part2, ...))                     concat sub-op results
  IrJoin("arms", " | ")                          join tuple-field children
  IrCond("negated", IrText("^"), IrText(""))     boolean field guard
  IrCallable(fn)                                 escape hatch for procedural ops

Because actions are structural IR data, a Flavour can be parsed from
grammar text and emitted as Python source — actions are IR, not opaque code.

For procedural cases (transformers that do complex rebuild logic, visitors
with side effects, emitter actions not yet expressible structurally), wrap
the logic in IrCallable. Structural ops are preferred where they fit.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable, ClassVar

from lexic.ir.nodes import IrCollection, IrComposite, IrLeaf, IrNode

if TYPE_CHECKING:
    from lexic.ir.walk import IrDispatch


# ── IrOp algebra ──────────────────────────────────────────────────────


class IrOp(IrNode, ABC):
    """A typesetting / transformation operation; the body of an IrAction.

    Each op subclass implements ``eval`` to compute its contribution to
    the dispatched result given the parent dispatcher, the dispatched
    node, and the already-visited children's results.
    """

    @abstractmethod
    def eval(
        self,
        dispatcher: "IrDispatch[Any]",
        node: IrNode,
        new_children: tuple,
    ) -> Any:
        """Evaluate this op.

        :param dispatcher: Parent dispatcher (the IrDispatch whose action
            body this is). Available for ops that need to re-dispatch.
        :param node: The dispatched node.
        :param new_children: Already-visited results for ``node.children()``,
            aligned by position.
        :returns: This op's contribution to the dispatched result.
        """


@dataclass(frozen=True, slots=True)
class IrText(IrOp, IrLeaf):
    """Emit a literal string."""

    text: str

    def eval(self, dispatcher, node, new_children) -> str:
        return self.text


@dataclass(frozen=True, slots=True)
class IrField(IrOp, IrLeaf):
    """Emit ``str(getattr(node, field_name))`` from a non-IrNode field."""

    field_name: str

    def eval(self, dispatcher, node, new_children) -> str:
        return str(getattr(node, self.field_name))


@dataclass(frozen=True, slots=True)
class IrRecurse(IrOp, IrLeaf):
    """Emit the already-visited result for ``self.<field_name>``.

    The field must hold an IrNode that appears in ``node.children()``;
    its result is looked up in ``new_children`` by identity.
    """

    field_name: str

    def eval(self, dispatcher, node, new_children) -> Any:
        target = getattr(node, self.field_name)
        for old, new in zip(node.children(), new_children):
            if old is target:
                return new
        # Fallback: not in children (shouldn't happen for valid usage).
        return dispatcher(target)


@dataclass(frozen=True, slots=True, repr=False)
class IrSeq(IrOp, IrCollection["IrOp"]):
    """Concatenate sub-op results."""

    _items_attr: ClassVar[str] = "parts"
    parts: tuple[IrOp, ...] = ()

    def eval(self, dispatcher, node, new_children) -> str:
        return "".join(op.eval(dispatcher, node, new_children) for op in self.parts)


@dataclass(frozen=True, slots=True)
class IrJoin(IrOp, IrLeaf):
    """Iterate a tuple-of-IrNode field; join already-visited results with separator.

    If the field is empty, returns ``empty`` (typically ``""`` or a sentinel
    like ``'""'`` for GBNF's empty sequence).
    """

    field_name: str
    separator: str
    empty: str = ""

    def eval(self, dispatcher, node, new_children) -> str:
        field_value = getattr(node, self.field_name)
        if not field_value:
            return self.empty
        lookup = {id(old): new for old, new in zip(node.children(), new_children)}
        return self.separator.join(lookup[id(fv)] for fv in field_value)


@dataclass(frozen=True, slots=True, repr=False)
class IrCond(IrOp, IrComposite["IrOp", "IrOp"]):
    """If ``bool(getattr(node, field_name))``, eval ``then_op``; else ``else_op``."""

    _child_attrs: ClassVar[tuple[str, ...]] = ("then_op", "else_op")
    field_name: str
    then_op: IrOp
    else_op: IrOp

    def eval(self, dispatcher, node, new_children) -> Any:
        branch = self.then_op if getattr(node, self.field_name) else self.else_op
        return branch.eval(dispatcher, node, new_children)


@dataclass(frozen=True, slots=True, hash=False, eq=False)
class IrCallable(IrOp, IrLeaf):
    """Escape hatch: wraps an opaque ``Callable[[IrNode, tuple], _T]``.

    For procedural transformers / visitors and any flavour action that
    can't yet be expressed structurally. Once everything has a structural
    form, IrCallable can be deleted.

    Identity semantics (``eq=False, hash=False``) — callables don't have
    structural equality. Same carve-out as IrAction.
    """

    handler: Callable[..., Any]

    def eval(self, dispatcher, node, new_children) -> Any:
        return self.handler(node, new_children)

    def _inner_str(self) -> str:
        name = getattr(self.handler, "__name__", "callable")
        return f"<{name}>"


# ── IrAction ──────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True, hash=False, eq=False, repr=False)
class IrAction(IrComposite["IrOp"]):
    """A dispatch entry: a (target_type, body) pair.

    ``target_type`` is the IrNode subclass this action handles; ``body``
    is the IrOp tree describing what to do with such a node. Identity
    semantics (``eq=False, hash=False``) because ``target_type`` is a
    type object and body may contain IrCallable, neither of which
    compares structurally well.
    """

    _child_attrs: ClassVar[tuple[str, ...]] = ("body",)
    target_type: type
    body: IrOp

    def _inner_str(self) -> str:
        return f"{self.target_type.__name__}, {self.body}"
```

- [ ] **Step 4: Rewrite `src/lexic/ir/walk.py` — `IrDispatch` interprets `IrOp`**

```python
"""IrDispatch, IrVisitor, IrTransformer — generic IR traversal.

IrDispatch is an IrCollection["IrAction"]. Its children() are the
dispatch table; calling the dispatcher walks an IR subtree applying
the actions. Each action's body is an IrOp tree — evaluated by op.eval
against the dispatched node and its already-visited children.

Canonical instantiations:

  IrVisitor       = IrDispatch[None]    walks for side effects
  IrTransformer   = IrDispatch[IrNode]  rewrites via node.rebuild()
  IrEmitter       = IrDispatch[str]     produces strings (Task 3.1);
                                        default = str(node); closed-world
                                        flavours override default to raise
                                        on unhandled types.

Per-node intrinsic data (children layout, rebuild constructor, canonical
form, debug repr) lives on the node itself — there is no central
registry. New IR node types implement __str__/__repr__ and inherit
children/rebuild from IrLeaf/IrCollection/IrComposite.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar, Generic, TypeVar, cast

from lexic.ir.action import IrAction
from lexic.ir.nodes import IrCollection, IrNode

_T = TypeVar("_T")


@dataclass(frozen=True, slots=True, repr=False)
class IrDispatch(IrCollection["IrAction"], Generic[_T]):
    """A tree-walking operation. children() are its IrActions; calling
    the dispatcher walks an IR subtree applying those actions.

    Soft dispatch: a node-type miss falls through to ``default``.
    Strictness (raising on miss) is a per-subclass concern, expressed by
    overriding ``default`` (see IrEmitter in Task 3.1).

    :ivar actions: Tuple of dispatch entries. Each ``IrAction`` carries a
        target node type and an ``IrOp`` body describing the operation.
    """

    _items_attr: ClassVar[str] = "actions"
    actions: tuple[IrAction, ...] = ()

    @property
    def _table(self) -> dict[type, IrAction]:
        # cached_property doesn't combine with frozen dataclasses; recompute
        # is cheap (small dict) and keeps frozen semantics intact.
        return {a.target_type: a for a in self.actions}

    def __call__(self, node: IrNode) -> _T:
        """Walk the subtree: recurse children, then evaluate this node's action.

        :param node: Root of the IR subtree to operate on.
        :returns: Dispatcher-specific result.
        """
        new_children: tuple[_T, ...] = tuple(self(c) for c in node.children())
        action = self._table.get(type(node))
        if action is not None:
            return cast("_T", action.body.eval(self, node, new_children))
        return self.default(node, new_children)

    def default(self, node: IrNode, new_children: tuple[_T, ...]) -> _T:
        """Behaviour when no action is registered for node's type.

        Base passes ``node`` through as ``_T`` — the identity that works
        for IrTransformer's no-op case. IrVisitor and IrEmitter override.
        """
        return cast("_T", node)


@dataclass(frozen=True, slots=True, repr=False)
class IrVisitor(IrDispatch[None]):
    """Side-effect walker. T=None."""

    def default(self, node: IrNode, new_children: tuple[None, ...]) -> None:
        return None


@dataclass(frozen=True, slots=True, repr=False)
class IrTransformer(IrDispatch[IrNode]):
    """Rewrites the IR. Default: pass node through; rebuild on change."""

    def default(self, node: IrNode, new_children: tuple[IrNode, ...]) -> IrNode:
        if any(nc is not oc for nc, oc in zip(new_children, node.children())):
            return node.rebuild(new_children)
        return node


# IrEmitter is added in Task 3.1. Sketch:
#
# @dataclass(frozen=True, slots=True, repr=False)
# class IrEmitter(IrDispatch[str]):
#     def default(self, node: IrNode, new_children: tuple[str, ...]) -> str:
#         if self.actions:
#             raise UnsupportedConstructError(
#                 f"{type(self).__name__} has no action for {type(node).__name__!r}"
#             )
#         return str(node)         # IrMetaEmitter-style: no flavour, intrinsic str()
```

Note: `frozen=True` dataclasses can't use `cached_property` because the descriptor needs to write to an instance attribute on first access. `_table` is a regular `@property` instead; the dict is small (one entry per node type the dispatcher cares about) so per-call construction is negligible.

`_CHILDREN`, `_REBUILD`, `_DUMP`, `dump()`, `visit`, `generic_visit`, `_combine`, and any `visit_<TypeName>` getattr indirection are all gone.

- [ ] **Step 5: Update `src/lexic/ir/__init__.py`**

Re-export `IrAction`, `IrOp`, and the concrete ops most code constructs with:

```python
from lexic.ir.action import (
    IrAction,
    IrCallable,
    IrCond,
    IrField,
    IrJoin,
    IrOp,
    IrRecurse,
    IrSeq,
    IrText,
)
```

Add them to `__all__`.

- [ ] **Step 6: Run tests baseline**

Run: `uv run pytest -q`. Expect failures in `derive.py` / `model_emitter.py` / `aliases.py` callers and in `test_walk.py` (legacy assertions on `_DUMP` etc.). Step 7 fixes them.

- [ ] **Step 7: Migrate the four caller files**

Each subclass becomes a constructor that builds an `IrDispatch` with an `actions` tuple. Per-instance mutable state (helpers, found-flag, alias map) is **hoisted out of the frozen dataclass** into a closure or a caller-owned object — `IrDispatch` itself stays frozen.

**`src/lexic/ir/derive.py` — `_RuleRefFinder` and `_HoistTransformer`:**

Replace both with builder functions that capture mutable state in a closure and bind an `IrCallable` action.

```python
from lexic.ir.action import IrAction, IrCallable
from lexic.ir.walk import IrTransformer, IrVisitor


def _rule_ref_finder() -> tuple[IrVisitor, Callable[[], bool]]:
    """Build a visitor that records whether any IrRuleRef appeared.

    :returns: ``(visitor, was_found)`` — call ``visitor(tree)`` then ``was_found()``.
    """
    state = {"found": False}

    def _on_ruleref(node: IrRuleRef, new_children: tuple) -> None:
        state["found"] = True

    visitor = IrVisitor(actions=(
        IrAction(IrRuleRef, IrCallable(_on_ruleref)),
    ))
    return visitor, lambda: state["found"]


@cache
def has_ruleref(node: IrNode) -> bool:
    visitor, found = _rule_ref_finder()
    visitor(node)
    return found()
```

Note: the original `_RuleRefFinder` overrode `visit` to short-circuit once `found=True`. With soft dispatch and no override hook, we lose that optimization; the visitor walks the whole subtree. Acceptable — the use case (boolean classification) is cached via `@cache`, so the cost is paid once per node identity.

For `_HoistTransformer`:

```python
def _hoist_transformer(parent_name: str, name_set: set[str]) -> tuple[IrTransformer, list[IrRule]]:
    """Build a transformer that hoists quantified groups with rulerefs.

    :returns: ``(transformer, helpers_list)`` — the list is appended to as the
        transformer runs.
    """
    helpers: list[IrRule] = []

    def _on_iritem(node: IrItem, new_children: tuple) -> IrItem:
        new_atom, new_quantifier = new_children
        if not isinstance(new_atom, IrGroup):
            if new_atom is node.atom and new_quantifier is node.quantifier:
                return node
            return IrItem(atom=new_atom, quantifier=new_quantifier)
        is_quantified = new_quantifier != Quantifier(1, 1)
        if is_quantified and has_ruleref(new_atom.body):
            helper_name = _reserve_helper_name(parent_name, name_set)
            name_set.add(helper_name)
            helpers.append(IrRule(name=helper_name, body=new_atom.body))
            return IrItem(atom=IrRuleRef(name=helper_name), quantifier=new_quantifier)
        return IrItem(atom=new_atom, quantifier=new_quantifier)

    transformer = IrTransformer(actions=(
        IrAction(IrItem, IrCallable(_on_iritem)),
    ))
    return transformer, helpers


def hoist_helpers(ast: IrAst) -> tuple[IrAst, list[IrRule]]:
    name_set: set[str] = {r.name for r in ast.rules}
    all_helpers: list[IrRule] = []
    new_rules: list[IrRule] = []
    for rule in ast.rules:
        transformer, helpers = _hoist_transformer(rule.name, name_set)
        new_body = transformer(rule.body)
        all_helpers.extend(helpers)
        new_rules.append(IrRule(rule.name, new_body))
    return IrAst(rules=tuple(new_rules), start=ast.start), all_helpers
```

**`src/lexic/codegen/aliases.py` — `_PatternAliasVisitor`:**

The visitor maintains an alias map and a stack of ruleref-frames. Hoist both into closure state; bind two `IrCallable` actions (`IrRuleRef`, `IrItem`).

```python
def _pattern_alias_collector() -> tuple[IrVisitor, dict[str, PatternAlias]]:
    aliases: dict[str, PatternAlias] = {}
    name_counts: Counter[str] = Counter()
    ruleref_frames: list[bool] = [False]

    def _record(regex: str, name: str) -> None:
        # ... (lifted verbatim from the old class) ...
        ...

    def _on_ruleref(node: IrRuleRef, new_children: tuple) -> None:
        ruleref_frames[-1] = True

    def _on_iritem(node: IrItem, new_children: tuple) -> None:
        atom, q = node.atom, node.quantifier
        if isinstance(atom, IrGroup):
            # ... group handling (push/pop frame, record on clean exit) ...
            ...
            return
        if isinstance(atom, IrCharClass):
            _record(regex_for_charclass(atom, q), _name_for_charclass(atom) or "Pattern")

    visitor = IrVisitor(actions=(
        IrAction(IrRuleRef, IrCallable(_on_ruleref)),
        IrAction(IrItem, IrCallable(_on_iritem)),
    ))
    return visitor, aliases


def collect_aliases(ast: IrAst) -> dict[str, PatternAlias]:
    visitor, aliases = _pattern_alias_collector()
    visitor(ast)
    return aliases
```

**`src/lexic/codegen/model_emitter.py` — `_IrRepr`:**

Each of the seven repr-action lambdas becomes an `IrAction(NodeType, IrCallable(lambda))`. The class collapses to a constructor.

```python
from lexic.ir.action import IrAction, IrCallable
from lexic.ir.walk import IrEmitter   # added in Task 3.1


def _ir_repr() -> IrEmitter:
    return IrEmitter(actions=(
        IrAction(IrLiteral,     IrCallable(lambda n, nc: f"IrLiteral({n.value!r})")),
        IrAction(IrCharClass,   IrCallable(lambda n, nc: f"IrCharClass({n.pattern!r}, negated={n.negated})")),
        IrAction(IrRuleRef,     IrCallable(lambda n, nc: f"IrRuleRef({n.name!r})")),
        IrAction(IrGroup,       IrCallable(lambda n, nc: f"IrGroup({nc[0]})")),
        IrAction(IrAlternation, IrCallable(lambda n, nc: (
            "IrAlternation(arms=())" if not nc else f"IrAlternation(arms=({', '.join(nc)},))"
        ))),
        IrAction(IrSequence,    IrCallable(lambda n, nc: (
            "IrSequence(items=())" if not nc else f"IrSequence(items=({', '.join(nc)},))"
        ))),
        IrAction(IrItem,        IrCallable(lambda n, nc: (
            f"IrItem({nc[0]}, Quantifier({n.quantifier.min}, {n.quantifier.max!r}))"
        ))),
    ))
```

Callers swap `self._repr.visit(item)` for `self._repr(item)` (the dispatcher is callable).

Note: `_IrRepr` predates Task 3.1's `IrEmitter`. Until Task 3.1 lands, `model_emitter.py`'s repr-emitter uses `IrTransformer[str]`... wait, that breaks the type. The clean order is: ship Task 3.1 (`IrEmitter`) before this migration, OR `_IrRepr` uses a custom `IrDispatch[str]` subclass interim. Pick whichever order keeps the suite green at every step. *Decision at execution time: see Step 9.*

- [ ] **Step 8: Update `tests/unit/lexic/ir/test_walk.py`**

Remove tests on `_CHILDREN` / `_REBUILD` / `_DUMP`. Add:

```python
def test_irdispatch_is_an_ircollection_of_actions():
    from lexic.ir.action import IrAction, IrCallable
    from lexic.ir.nodes import IrCollection, IrLiteral
    from lexic.ir.walk import IrTransformer

    a = IrAction(IrLiteral, IrCallable(lambda n, _: n))
    t = IrTransformer(actions=(a,))
    assert isinstance(t, IrCollection)
    assert t.children() == (a,)
    a2 = IrAction(IrLiteral, IrCallable(lambda n, _: n))
    assert t.rebuild((a2,)).actions == (a2,)


def test_irtransformer_empty_actions_is_identity():
    from lexic.ir.nodes import IrItem, IrLiteral, IrSequence
    from lexic.ir.walk import IrTransformer
    seq = IrSequence((IrItem(IrLiteral("a")),))
    assert IrTransformer()(seq) == seq


def test_irdispatch_partial_actions_falls_through_to_default():
    """Miss falls through to default (soft dispatch)."""
    from lexic.ir.action import IrAction, IrCallable
    from lexic.ir.nodes import IrLiteral, IrSequence, IrItem
    from lexic.ir.walk import IrTransformer

    # Action covers IrLiteral only; visiting an IrSequence falls to default
    # (which does identity rebuild). Should not raise.
    t = IrTransformer(actions=(IrAction(IrLiteral, IrCallable(lambda n, _: n)),))
    seq = IrSequence((IrItem(IrLiteral("a")),))
    assert t(seq) == seq
```

And in `tests/unit/lexic/ir/test_action.py`:

```python
def test_iraction_str_uses_target_type_name():
    from lexic.ir.action import IrAction, IrText
    from lexic.ir.nodes import IrLiteral
    a = IrAction(IrLiteral, IrText("hello"))
    assert "IrLiteral" in str(a)


def test_irtext_eval_returns_literal():
    from lexic.ir.action import IrText
    assert IrText("x").eval(None, None, ()) == "x"


def test_irseq_eval_concatenates():
    from lexic.ir.action import IrSeq, IrText
    op = IrSeq((IrText("a"), IrText("b"), IrText("c")))
    assert op.eval(None, None, ()) == "abc"


def test_irfield_eval_reads_str_of_field():
    from dataclasses import dataclass
    from lexic.ir.action import IrField
    @dataclass
    class _N: name: str
    assert IrField("name").eval(None, _N("x"), ()) == "x"


def test_irjoin_eval_joins_children_by_field():
    """IrJoin looks up each item in new_children via identity."""
    from lexic.ir.action import IrJoin
    from lexic.ir.nodes import IrItem, IrLiteral, IrSequence
    a, b = IrItem(IrLiteral("a")), IrItem(IrLiteral("b"))
    seq = IrSequence((a, b))
    # Simulate already-dispatched children with string results.
    assert IrJoin("items", " | ").eval(None, seq, ("A", "B")) == "A | B"
    assert IrJoin("items", " | ", empty='""').eval(None, IrSequence(()), ()) == '""'


def test_ircond_eval_branches_on_field():
    from lexic.ir.action import IrCond, IrText
    from lexic.ir.nodes import IrCharClass
    op = IrCond("negated", IrText("yes"), IrText("no"))
    assert op.eval(None, IrCharClass("a-z", negated=True), ()) == "yes"
    assert op.eval(None, IrCharClass("a-z", negated=False), ()) == "no"


def test_ircallable_eval_invokes_handler():
    from lexic.ir.action import IrCallable
    op = IrCallable(lambda n, nc: ("hit", n, nc))
    assert op.eval(None, "node", ("a", "b")) == ("hit", "node", ("a", "b"))
```

- [ ] **Step 9: Run tests**

Run: `uv run pytest -q` — PASS. Resolve any caller-migration fallout. If `model_emitter.py`'s `_IrRepr` depends on `IrEmitter` not yet introduced, either:
- Land Task 3.1 first (out of order), then come back to migrate `_IrRepr`; or
- Migrate `_IrRepr` to a local `IrDispatch[str]` subclass that overrides `default` to raise (interim shape until Task 3.1 lands).

Pick whichever keeps the suite green at the smallest commit. The order doesn't affect Slice B's end state.

- [ ] **Step 10: Commit**

```bash
git add src/lexic/ir/action.py src/lexic/ir/walk.py src/lexic/ir/__init__.py \
        src/lexic/ir/derive.py src/lexic/codegen/aliases.py src/lexic/codegen/model_emitter.py \
        tests/unit/lexic/ir/test_action.py tests/unit/lexic/ir/test_walk.py
git commit -m "ir: IrAction + IrOp algebra; IrDispatch interprets structural action bodies

IrAction is now an IrComposite[IrOp] with target_type + body. The body
is a tree of structural typesetting / transformation ops — IrText,
IrField, IrRecurse, IrSeq, IrJoin, IrCond — with IrCallable as the
procedural escape hatch. Lives in new src/lexic/ir/action.py alongside
the IrOp hierarchy.

IrDispatch is an IrCollection[IrAction]: children() are the actions,
rebuild() reconstructs from a new action tuple. __call__ walks children,
looks up the action for type(node), evaluates the body's IrOp tree
against (node, new_children). Soft dispatch: a miss falls through to
default. Closed-world strictness moves to IrEmitter.default (Task 3.1).

_CHILDREN/_REBUILD/_DUMP/dump()/visit/generic_visit/_combine and
visit_<TypeName> getattr indirection are gone. Callers in derive.py,
codegen/aliases.py, and codegen/model_emitter.py migrate to action-table
form using IrCallable for their procedural logic; mutable per-instance
state is hoisted out of the frozen dataclasses into closures."
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

### Task 3.1: Add `IrEmitter` to `walk.py`

**Files:**
- Modify: `src/lexic/ir/walk.py`
- Modify: `tests/unit/lexic/ir/test_walk.py`

**Scope (revised 2026-05-15).** Task 1.4 sketched `IrEmitter` in a commented-out block. This task makes it concrete:

- `IrEmitter(IrDispatch[str])`. `default(node, new_children) -> str`: returns `str(node)` (the node's intrinsic canonical-form action from Task 1.3) when `self.actions` is empty; raises `UnsupportedConstructError` when `self.actions` is non-empty (a flavour-emitter declared a closed world and saw a node it doesn't know).
- The trivial canonical-emit walker is just `IrEmitter()` with no actions. No separate `IrMetaEmitter` class is needed — it's a degenerate `IrEmitter`. If a name is convenient at the use site, expose a thin alias / factory in `ir/__init__.py` (`def canonical_emitter() -> IrEmitter: return IrEmitter()`).
- The original `IrMetaEmitter`-as-dump-backend role is gone (dump = `repr(node)` from Task 1.3 / 1.4).

- [ ] **Step 1: Write failing tests**

Append to `tests/unit/lexic/ir/test_walk.py`:

```python
def test_iremitter_empty_actions_returns_intrinsic_str():
    """Empty actions → default returns str(node) (intrinsic __str__ from Task 1.3)."""
    from lexic.ir.nodes import IrLiteral
    from lexic.ir.walk import IrEmitter

    e = IrEmitter()
    assert e(IrLiteral("a")) == str(IrLiteral("a"))  # "LITERAL('a')"


def test_iremitter_truthy_actions_raise_on_miss():
    """Non-empty actions → closed world; miss raises UnsupportedConstructError."""
    from lexic.exceptions import UnsupportedConstructError
    from lexic.ir.action import IrAction, IrText
    from lexic.ir.nodes import IrLiteral, IrSequence
    from lexic.ir.walk import IrEmitter

    # Action covers IrLiteral only; visiting IrSequence has no action → default → raise.
    e = IrEmitter(actions=(IrAction(IrLiteral, IrText("LIT")),))
    with pytest.raises(UnsupportedConstructError):
        e(IrSequence(()))


def test_iremitter_action_overrides_intrinsic():
    """Per-type action entries override the str(node) fallback."""
    from lexic.ir.action import IrAction, IrText
    from lexic.ir.nodes import IrLiteral
    from lexic.ir.walk import IrEmitter

    e = IrEmitter(actions=(IrAction(IrLiteral, IrText("LIT")),))
    assert e(IrLiteral("anything")) == "LIT"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/lexic/ir/test_walk.py -v`
Expected: FAIL — `IrEmitter` is still a commented-out sketch.

- [ ] **Step 3: Implement `IrEmitter` in `src/lexic/ir/walk.py`**

Replace the commented-out sketch from Task 1.4 with:

```python
@dataclass(frozen=True, slots=True, repr=False)
class IrEmitter(IrDispatch[str]):
    """String emission. T=str.

    Empty actions → default returns ``str(node)`` (the intrinsic canonical
    form from Task 1.3). This is the trivial "canonical emit" use case —
    walk a tree and produce its placeholder-notation text.

    Non-empty actions → the dispatcher has declared a closed world.
    A missing handler for a node type means the flavour doesn't support
    that construct; default raises ``UnsupportedConstructError``.
    Flavours (Task 3.2) populate ``actions`` with the node types their
    target grammar covers; users get a loud error on unknown constructs.
    """

    def default(self, node: IrNode, new_children: tuple[str, ...]) -> str:
        if self.actions:
            raise UnsupportedConstructError(
                f"{type(self).__name__} has no action for {type(node).__name__!r}"
            )
        return str(node)
```

Add a convenience function in `src/lexic/ir/__init__.py`:

```python
def canonical_emitter() -> IrEmitter:
    """The trivial IrEmitter: no actions, every node renders via its __str__.

    Equivalent to constructing ``IrEmitter()`` directly; exposed as a named
    factory for documentation at use sites.
    """
    return IrEmitter()
```

(Re-export `IrEmitter` and `canonical_emitter` in `__all__`.)

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/unit/lexic/ir/test_walk.py -v` — PASS.
Run: `uv run pytest -q` — PASS.

- [ ] **Step 5: Commit**

```bash
git add src/lexic/ir/walk.py src/lexic/ir/__init__.py tests/unit/lexic/ir/test_walk.py
git commit -m "ir: add IrEmitter; closed-world strictness via default override

IrEmitter(IrDispatch[str]) makes the sketch from Task 1.4 concrete.
default returns str(node) when actions is empty (the canonical-emit
walker) and raises UnsupportedConstructError when actions is truthy
and the node-type misses (flavour declared a closed world). The
canonical_emitter() factory in ir/__init__.py exposes the empty-actions
case at use sites. IrMetaEmitter from the original spec is retired —
the same role is served by canonical_emitter() / IrEmitter()."
```

---

### Task 3.2: Add `actions`, `quantifier_symbols`, `pre_parse_check` to `Flavour`; subclass `IrEmitter`

**Files:**
- Modify: `src/lexic/grammars/flavour.py`
- Test: `tests/unit/lexic/grammars/test_flavour.py`

**Revision note (2026-05-15).** The original task added `action: dict[type, Callable]` to `Flavour`. With Task 1.4's `IrAction[IrOp]` design, that becomes `actions: tuple[IrAction, ...]` (inherited from `IrEmitter` via `IrDispatch` → `IrCollection[IrAction]`). Each entry is an `IrAction(target_type, body)` where `body` is an `IrOp` tree. The pseudocode below still references the `action` dict — substitute as you implement:
- `action: ClassVar[dict[type[IrNode], Callable]]` → `actions: ClassVar[tuple[IrAction, ...]]` (inherited)
- `Flavour.action[NodeType] = lambda n, r: ...` → `IrAction(NodeType, <IrOp tree>)`
See Task 3.3 / 3.4 for the per-flavour structural action sets.

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

**Revision note (2026-05-15).** Per Task 1.4 the action table is `actions: tuple[IrAction, ...]` where each `IrAction(target_type, body)` carries a structural `IrOp` body. Replace each lambda in the table below with the equivalent `IrOp` tree. The full op set is in `src/lexic/ir/action.py` (Task 1.4); the GBNF translations are:

| Old lambda | New `IrAction` body |
|---|---|
| `IrLiteral: lambda n, _: f'"{escape(n.value)}"'` | `IrAction(IrLiteral, IrCallable(_emit_gbnf_literal))` — encoding requires the flavour-specific escape codec; keep procedural for now |
| `IrCharClass: lambda n, _: f"[{'^' if n.negated else ''}{n.pattern}]"` | `IrAction(IrCharClass, IrSeq((IrText("["), IrCond("negated", IrText("^"), IrText("")), IrField("pattern"), IrText("]"))))` |
| `IrRuleRef: lambda n, _: n.name` | `IrAction(IrRuleRef, IrField("name"))` |
| `IrGroup: lambda n, r: f"({r(n.body)})"` | `IrAction(IrGroup, IrSeq((IrText("("), IrRecurse("body"), IrText(")"))))` |
| `IrQuantifier: _emit_gbnf_quantifier` | `IrAction(Quantifier, IrCallable(_emit_gbnf_quantifier))` — quantifier-symbol lookup is procedural |
| `IrItem: lambda n, r: f"{r(n.atom)}{r(n.quantifier)}"` | `IrAction(IrItem, IrSeq((IrRecurse("atom"), IrRecurse("quantifier"))))` |
| `IrSequence: lambda n, r: " ".join(r(it) for it in n.items) or '""'` | `IrAction(IrSequence, IrJoin("items", " ", empty='""'))` |
| `IrAlternation: lambda n, r: " \| ".join(r(arm) for arm in n.arms)` | `IrAction(IrAlternation, IrJoin("arms", " \| "))` |
| `IrRule: lambda n, r: f"{n.name} ::= {r(n.body)}"` | `IrAction(IrRule, IrSeq((IrField("name"), IrText(" ::= "), IrRecurse("body"))))` |
| `IrAst: lambda n, r: "\n".join(r(rule) for rule in n.rules) + "\n"` | `IrAction(IrAst, IrSeq((IrJoin("rules", "\n"), IrText("\n"))))` |

Two entries stay `IrCallable` because their logic isn't structurally expressible (yet): `IrLiteral` (needs flavour-specific escape codec invocation) and `Quantifier` (consults `quantifier_symbols` dict). The rest become structural — making the GBNF flavour parseable / codegenable from grammar text in the long-term direction.

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

**Revision note (2026-05-15).** Same translation contract as Task 3.3: `actions: tuple[IrAction, ...]`, each `IrAction(target_type, body)` carries an `IrOp` body. ABNF-specific differences from GBNF:
- `IrAction(IrItem, IrSeq((IrRecurse("quantifier"), IrRecurse("atom"))))` — prefix-placed quantifier (vs. GBNF's atom-then-quantifier).
- `IrAction(Quantifier, IrCallable(_emit_abnf_quantifier))` — ABNF's `n*m` form lives in the procedural quantifier renderer.
- `IrAction(IrLiteral, IrCallable(_emit_abnf_literal))` — same flavour-specific escape reason as GBNF.
- The remaining entries (`IrRuleRef`, `IrCharClass`, `IrGroup`, `IrSequence`, `IrAlternation`, `IrRule`, `IrAst`) map to the same `IrOp` shapes as GBNF, modulo separator strings and rule-syntax (`=` instead of `::=`).

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
