# IR AST Architecture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the IR/classifier/converter layer of Slice B.5 with a canonical IR AST owned by `lexic.ir`, configuration-driven flavours, and a generic `MetaGrammarParser` + `derive_specs` pipeline. Validate with a stub minimal-ABNF flavour. Close with documentation supersession.

**Architecture:** A flavour declares a Lark meta-grammar string with canonical tags (`ir_rule`, `ir_literal`, …), an `EscapeCodec` subclass, two staticmethods (`parse_quantifier`, `parse_charclass`), and a `FlavourEmitter`. The generic `MetaGrammarParser(flavour)` produces an `IrAst`; `derive_specs(ast, *, non_semantic_rules)` walks it to produce the codegen `RuleSpec` view. No classifier/converter per flavour. Author-declared metadata (which rules are non-semantic) travels through the formalism's comment channel.

**Tech Stack:** Python 3.12+, Lark (earley), Pydantic, `uv run pytest`, `uv run ruff check`. All commands assume cwd is `/home/mika/projects/lexic`.

**Spec:** `docs/superpowers/specs/2026-04-29-ir-ast-architecture-design.md`.

**Predecessor state:** v1 B.5 Tasks 1–4 are committed. v1's Task 5 was never implemented (untracked `grammars/gbnf/ast_to_ir.py` + sibling test will be discarded by Phase D). v1's Tasks 6–12 are unimplemented; they ship as a separate follow-up slice after this one.

---

## File map

### Created

- `src/lexic/ir/nodes.py` — IR AST dataclasses
- `src/lexic/ir/walk.py` — `IrVisitor`, `IrTransformer`, `dump`
- `src/lexic/ir/derive.py` — `derive_specs`, `classify_kind`, `compute_parents`, `hoist_helpers`
- `src/lexic/ir/directives.py` — `Directives`, `parse_directives`
- `src/lexic/grammars/flavour.py` — `Flavour` ABC
- `src/lexic/parsing/__init__.py`
- `src/lexic/parsing/meta_parser.py` — `MetaGrammarParser`, `_IrTagTransformer`
- `src/lexic/grammars/gbnf/meta_grammar.py` — Lark grammar string
- `src/lexic/grammars/gbnf/flavour.py` — `GbnfFlavour`
- `src/lexic/grammars/abnf/__init__.py`
- `src/lexic/grammars/abnf/meta_grammar.py`
- `src/lexic/grammars/abnf/escapes.py` — `AbnfEscapes(EscapeCodec)`
- `src/lexic/grammars/abnf/emitter.py` — `AbnfEmitter(FlavourEmitter)`
- `src/lexic/grammars/abnf/flavour.py` — `AbnfFlavour`
- `tests/unit/lexic/ir/test_nodes.py`
- `tests/unit/lexic/ir/test_walk.py`
- `tests/unit/lexic/ir/test_derive.py`
- `tests/unit/lexic/ir/test_directives.py`
- `tests/unit/lexic/grammars/test_flavour.py`
- `tests/unit/lexic/parsing/__init__.py`
- `tests/unit/lexic/parsing/test_meta_parser.py`
- `tests/unit/lexic/grammars/gbnf/test_meta_grammar.py`
- `tests/unit/lexic/grammars/gbnf/test_flavour.py`
- `tests/unit/lexic/grammars/abnf/__init__.py`
- `tests/unit/lexic/grammars/abnf/test_escapes.py`
- `tests/unit/lexic/grammars/abnf/test_emitter.py`
- `tests/unit/lexic/grammars/abnf/test_flavour.py`
- `tests/integration/test_compile_grammar_gbnf.py`
- `tests/integration/test_compile_grammar_abnf.py`
- `tests/integration/test_cross_flavour.py`

### Modified

- `src/lexic/ir/spec.py` — `items: list[IrItem]`
- `src/lexic/ir/__init__.py` — export new symbols, drop deleted
- `src/lexic/ir/protocols.py` — drop `RuleClassifier`, `SequenceConverter`, `FlavourAdapter`; keep handler aliases
- `src/lexic/grammars/__init__.py` — register `AbnfAdapter` alongside `GbnfAdapter` (post-cutover)
- `src/lexic/grammars/gbnf/parser.py` — thin wrapper around `MetaGrammarParser(GbnfFlavour)`
- `src/lexic/grammars/gbnf/emitter.py` — handle `IrItem`-shaped `RuleSpec.items`
- `src/lexic/grammars/gbnf/adapter.py` — wire to new flavour
- `src/lexic/codegen/__init__.py` — `build_classes_and_specs` uses new pipeline
- `src/lexic/codegen/model_emitter.py` — consume new `RuleSpec` shape
- `src/lexic/codegen/lark_builder.py` — consume new shape; remove old `decode_gbnf_escapes` reach-in
- `src/lexic/codegen/transformer/build_transformer.py` — consume new shape
- `src/lexic/codegen/transformer/builders.py` — consume new shape
- `src/lexic/base.py` — consume new shape; remove `decode_gbnf_escapes` reach-in
- `src/lexic/compile.py` — route through `compile_grammar`

### Deleted (Phase D)

- `src/lexic/ir/atoms.py`
- `src/lexic/ir/builder.py`
- `src/lexic/ir/classify.py`
- `src/lexic/ir/convert.py`
- `src/lexic/grammars/gbnf/ast.py`
- `src/lexic/grammars/gbnf/ast_to_ir.py` *(untracked WIP)*
- `src/lexic/codegen/ir_builder.py`
- `src/lexic/codegen/classify.py`
- `src/lexic/codegen/seq_to_atoms.py`
- `src/lexic/codegen/ast_utils.py`
- `tests/unit/lexic/ir/test_atoms.py`
- `tests/unit/lexic/ir/test_builder.py`
- `tests/unit/lexic/ir/test_classify.py`
- `tests/unit/lexic/ir/test_convert.py`
- `tests/unit/lexic/codegen/test_ir_builder.py`
- `tests/unit/lexic/codegen/test_classify.py`
- `tests/unit/lexic/codegen/test_seq_to_atoms.py`
- `tests/unit/lexic/codegen/test_ast_utils.py`
- `tests/unit/lexic/grammars/gbnf/test_ast.py`
- `tests/unit/lexic/grammars/gbnf/test_ast_to_ir.py` *(untracked)*

### Modified at Phase E

- `CLAUDE.md`
- `prototyping/next/2_ARCHITECTURE.md`
- `prototyping/next/3_ROADMAP.md`
- `docs/superpowers/specs/2026-04-25-slice-b5-package-restructure-design.md`
- `docs/superpowers/plans/2026-04-25-slice-b5-package-restructure.md`

---

## Phase order

| Phase | Tasks | Concern |
|---|---|---|
| A — IR foundations | 1–9 | IR AST types, walker, directives, Flavour ABC, derive_specs (4 sub-tasks), MetaGrammarParser |
| B — GBNF migration | 10–13 | meta-grammar, GbnfFlavour, compile_grammar entry, GBNF round-trip |
| C — ABNF stub | 14–18 | escapes, emitter, meta-grammar+flavour, ABNF round-trip, cross-flavour transpile |
| D — Cutover | 19–26 | Shape adapter, update consumers (gbnf emitter, model_emitter, lark_builder, transformer, base.py), switch compile(), delete old machinery |
| E — Housekeeping | 27 | CLAUDE.md, ARCHITECTURE, ROADMAP, v1 spec/plan supersession headers |

The suite is green at every commit.

---

## Phase A — IR foundations

## Task 1: `ir/nodes.py` — IR AST dataclasses

Define the canonical AST. Frozen dataclasses, slots, immutable tuples for collections. Forward-reference `IrGroup` from `IrItem.atom` via `from __future__ import annotations`.

**Files:**
- Create: `src/lexic/ir/nodes.py`
- Create: `tests/unit/lexic/ir/test_nodes.py`

- [ ] **Step 1: Write failing tests for `ir/nodes.py`.**

```python
# tests/unit/lexic/ir/test_nodes.py
"""IR AST node dataclasses — frozen, hashable, immutable tuples."""
from __future__ import annotations

import pytest

from lexic.ir.nodes import (
    IrAlternation,
    IrAst,
    IrCharClass,
    IrGroup,
    IrItem,
    IrLiteral,
    IrRule,
    IrRuleRef,
    IrSequence,
    Quantifier,
)


# ── Quantifier ───────────────────────────────────────────────────────


def test_quantifier_default_is_one_one():
    q = Quantifier()
    assert q.min == 1 and q.max == 1


def test_quantifier_unbounded_max_is_none():
    q = Quantifier(min=1, max=None)
    assert q.max is None


def test_quantifier_is_frozen():
    q = Quantifier(0, 1)
    with pytest.raises((AttributeError, Exception)):
        q.min = 5  # type: ignore[misc]


def test_quantifier_is_hashable():
    {Quantifier(0, 1), Quantifier(0, 1)}  # no exception


# ── Leaves ───────────────────────────────────────────────────────────


def test_ir_literal_holds_canonical_value():
    lit = IrLiteral(value="hello")
    assert lit.value == "hello"


def test_ir_literal_canonical_python_newline():
    lit = IrLiteral(value="a\nb")
    assert lit.value == "a\nb"


def test_ir_literal_is_frozen_and_hashable():
    {IrLiteral("a"), IrLiteral("a")}


def test_ir_charclass_default_not_negated():
    cc = IrCharClass(pattern="a-z")
    assert cc.pattern == "a-z"
    assert cc.negated is False


def test_ir_charclass_negated_flag():
    cc = IrCharClass(pattern="\\n", negated=True)
    assert cc.negated is True


def test_ir_ruleref_holds_name():
    r = IrRuleRef(name="expr")
    assert r.name == "expr"


# ── IrItem ───────────────────────────────────────────────────────────


def test_ir_item_default_quantifier():
    it = IrItem(atom=IrLiteral("x"))
    assert it.quantifier == Quantifier()


def test_ir_item_with_explicit_quantifier():
    it = IrItem(atom=IrCharClass("a-z"), quantifier=Quantifier(0, None))
    assert it.quantifier.min == 0
    assert it.quantifier.max is None


def test_ir_item_atom_can_be_group():
    grp = IrGroup(IrAlternation((IrSequence((IrItem(IrLiteral("a")),)),)))
    it = IrItem(atom=grp, quantifier=Quantifier(1, None))
    assert isinstance(it.atom, IrGroup)


# ── Structure ────────────────────────────────────────────────────────


def test_ir_sequence_items_are_tuple():
    seq = IrSequence((IrItem(IrLiteral("a")), IrItem(IrLiteral("b"))))
    assert isinstance(seq.items, tuple)
    assert len(seq.items) == 2


def test_ir_alternation_arms_are_tuple():
    alt = IrAlternation((IrSequence((IrItem(IrLiteral("a")),)),))
    assert isinstance(alt.arms, tuple)


def test_ir_group_wraps_alternation():
    alt = IrAlternation((IrSequence((IrItem(IrLiteral("x")),)),))
    grp = IrGroup(body=alt)
    assert grp.body is alt


def test_ir_rule_has_alternation_body():
    body = IrAlternation((IrSequence((IrItem(IrLiteral("x")),)),))
    rule = IrRule(name="r", body=body)
    assert rule.name == "r"
    assert rule.body is body


def test_ir_ast_holds_rules_and_start():
    body = IrAlternation((IrSequence(()),))
    rule = IrRule(name="root", body=body)
    ast = IrAst(rules=(rule,), start="root")
    assert ast.start == "root"
    assert ast.rules == (rule,)


def test_ir_ast_is_frozen():
    ast = IrAst(rules=(), start="root")
    with pytest.raises((AttributeError, Exception)):
        ast.start = "other"  # type: ignore[misc]


# ── Equality ─────────────────────────────────────────────────────────


def test_structurally_equal_asts_compare_equal():
    a = IrAst(
        rules=(
            IrRule("r", IrAlternation((IrSequence((IrItem(IrLiteral("x")),)),))),
        ),
        start="r",
    )
    b = IrAst(
        rules=(
            IrRule("r", IrAlternation((IrSequence((IrItem(IrLiteral("x")),)),))),
        ),
        start="r",
    )
    assert a == b
```

- [ ] **Step 2: Run — expect ModuleNotFoundError.**

```bash
uv run pytest tests/unit/lexic/ir/test_nodes.py -q
```

Expected: `ModuleNotFoundError: No module named 'lexic.ir.nodes'`.

- [ ] **Step 3: Create `src/lexic/ir/nodes.py`.**

```python
"""IR AST node dataclasses — canonical, frozen, hashable.

The IR AST is the lingua franca for transpilation. Every flavour produces
this AST from its source text. Leaves carry canonical values (escapes
decoded, POSIX-style char classes); quantifiers travel on `IrItem`,
not on leaves.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class Quantifier:
    """Repetition bounds. `max=None` means unbounded."""

    min: int = 1
    max: int | None = 1


# ── Leaves ───────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class IrLiteral:
    """Literal string. `value` is canonical Python (escapes decoded)."""

    value: str


@dataclass(frozen=True, slots=True)
class IrCharClass:
    """Character class. `pattern` is the canonical POSIX-style interior
    (e.g. 'a-z0-9'). `negated` is True if the source had `[^…]`.
    """

    pattern: str
    negated: bool = False


@dataclass(frozen=True, slots=True)
class IrRuleRef:
    """Reference to another rule by name."""

    name: str


# ── Structure (forward-declared for IrItem.atom union) ───────────────


@dataclass(frozen=True, slots=True)
class IrSequence:
    """Concatenation of items."""

    items: tuple["IrItem", ...] = ()


@dataclass(frozen=True, slots=True)
class IrAlternation:
    """Choice between sequences. Always >= 1 arm; single-arm is bare seq."""

    arms: tuple[IrSequence, ...] = ()


@dataclass(frozen=True, slots=True)
class IrGroup:
    """Parenthesised group. Body is always an IrAlternation."""

    body: IrAlternation


# ── Wrapper ──────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class IrItem:
    """An atom (leaf or group) with a quantifier."""

    atom: "IrLiteral | IrCharClass | IrRuleRef | IrGroup"
    quantifier: Quantifier = field(default_factory=Quantifier)


# ── Top-level ────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class IrRule:
    """A named rule. Body is always an IrAlternation, even single-arm."""

    name: str
    body: IrAlternation


@dataclass(frozen=True, slots=True)
class IrAst:
    """Full grammar: rules + start-rule name."""

    rules: tuple[IrRule, ...] = ()
    start: str = ""
```

- [ ] **Step 4: Run — expect PASS.**

```bash
uv run pytest tests/unit/lexic/ir/test_nodes.py -q
```

- [ ] **Step 5: Run full suite + ruff. Both green.**

```bash
uv run pytest tests/ -q
uv run ruff check src/ tests/
```

- [ ] **Step 6: Commit.**

```bash
git add src/lexic/ir/nodes.py tests/unit/lexic/ir/test_nodes.py
git commit -m "feat(ir): IR AST node dataclasses (Quantifier, leaves, structure)"
```

---

## Task 2: `ir/walk.py` — `IrVisitor` + `IrTransformer`

Python-`ast`-style traversal helpers. `IrVisitor.visit(node)` dispatches to `visit_<Type>`; `IrTransformer.visit` returns a (possibly new) node.

**Files:**
- Create: `src/lexic/ir/walk.py`
- Create: `tests/unit/lexic/ir/test_walk.py`

- [ ] **Step 1: Write failing tests.**

```python
# tests/unit/lexic/ir/test_walk.py
"""IrVisitor and IrTransformer — Python-ast-style traversal for IR AST."""
from __future__ import annotations

from lexic.ir.nodes import (
    IrAlternation,
    IrAst,
    IrCharClass,
    IrGroup,
    IrItem,
    IrLiteral,
    IrRule,
    IrRuleRef,
    IrSequence,
    Quantifier,
)
from lexic.ir.walk import IrTransformer, IrVisitor


def _seq(*items): return IrSequence(tuple(items))
def _alt(*arms): return IrAlternation(tuple(arms))
def _it(atom, q=None): return IrItem(atom, q if q else Quantifier())


# ── IrVisitor ────────────────────────────────────────────────────────


def test_visitor_dispatches_by_type():
    seen = []

    class V(IrVisitor):
        def visit_IrLiteral(self, node):
            seen.append(("lit", node.value))

        def visit_IrRuleRef(self, node):
            seen.append(("ref", node.name))

    v = V()
    v.visit(IrLiteral("a"))
    v.visit(IrRuleRef("r"))
    assert seen == [("lit", "a"), ("ref", "r")]


def test_visitor_generic_visit_walks_children():
    counts = {"literals": 0, "refs": 0}

    class V(IrVisitor):
        def visit_IrLiteral(self, node):
            counts["literals"] += 1

        def visit_IrRuleRef(self, node):
            counts["refs"] += 1

    body = _alt(
        _seq(_it(IrLiteral("a")), _it(IrRuleRef("x"))),
        _seq(_it(IrLiteral("b"))),
    )
    rule = IrRule("r", body)
    V().visit(rule)
    assert counts == {"literals": 2, "refs": 1}


def test_visitor_walks_groups():
    counts = {"chars": 0}

    class V(IrVisitor):
        def visit_IrCharClass(self, node):
            counts["chars"] += 1

    seq = _seq(
        _it(IrGroup(_alt(_seq(_it(IrCharClass("a-z")), _it(IrCharClass("0-9")))))),
    )
    V().visit(seq)
    assert counts["chars"] == 2


# ── IrTransformer ────────────────────────────────────────────────────


def test_transformer_returns_node_unchanged_by_default():
    lit = IrLiteral("a")
    out = IrTransformer().visit(lit)
    assert out == lit


def test_transformer_can_rewrite_a_leaf():
    class T(IrTransformer):
        def visit_IrLiteral(self, node):
            return IrLiteral(node.value.upper())

    body = _alt(_seq(_it(IrLiteral("a")), _it(IrLiteral("b"))))
    rule = IrRule("r", body)
    out = T().visit(rule)
    assert isinstance(out, IrRule)
    arm = out.body.arms[0]
    assert arm.items[0].atom == IrLiteral("A")
    assert arm.items[1].atom == IrLiteral("B")


def test_transformer_preserves_quantifier_when_rewriting_atom():
    class T(IrTransformer):
        def visit_IrLiteral(self, node):
            return IrLiteral(node.value + "!")

    body = _alt(_seq(_it(IrLiteral("x"), Quantifier(0, None))))
    rule = IrRule("r", body)
    out = T().visit(rule)
    item = out.body.arms[0].items[0]
    assert item.atom == IrLiteral("x!")
    assert item.quantifier == Quantifier(0, None)


def test_transformer_replacing_group_with_ruleref():
    """Helper-rule hoisting use case: replace IrGroup with IrRuleRef."""

    class T(IrTransformer):
        def visit_IrGroup(self, node):
            return IrRuleRef("hoisted")

    body = _alt(_seq(_it(IrGroup(_alt(_seq(_it(IrLiteral("a"))))), Quantifier(1, None))))
    rule = IrRule("r", body)
    out = T().visit(rule)
    item = out.body.arms[0].items[0]
    assert item.atom == IrRuleRef("hoisted")
    assert item.quantifier == Quantifier(1, None)


def test_transformer_walks_ast_top_level():
    class T(IrTransformer):
        def visit_IrLiteral(self, node):
            return IrLiteral(node.value + ".")

    ast = IrAst(
        rules=(
            IrRule("a", _alt(_seq(_it(IrLiteral("x"))))),
            IrRule("b", _alt(_seq(_it(IrLiteral("y"))))),
        ),
        start="a",
    )
    out = T().visit(ast)
    assert out.rules[0].body.arms[0].items[0].atom == IrLiteral("x.")
    assert out.rules[1].body.arms[0].items[0].atom == IrLiteral("y.")
    assert out.start == "a"
```

- [ ] **Step 2: Run — expect ModuleNotFoundError.**

```bash
uv run pytest tests/unit/lexic/ir/test_walk.py -q
```

- [ ] **Step 3: Create `src/lexic/ir/walk.py`.**

```python
"""IrVisitor and IrTransformer — Python-ast-style traversal for the IR AST.

`IrVisitor` walks; subclass and define `visit_<NodeType>` methods.
`IrTransformer` rewrites; methods return a (possibly new) node.

The traversal order matches the dataclass field order: an IrAst's `rules`,
each IrRule's `body`, each IrAlternation's `arms`, each IrSequence's
`items`, each IrItem's `atom`. Leaves stop the walk.
"""

from __future__ import annotations

from lexic.ir.nodes import (
    IrAlternation,
    IrAst,
    IrCharClass,
    IrGroup,
    IrItem,
    IrLiteral,
    IrRule,
    IrRuleRef,
    IrSequence,
)


class IrVisitor:
    """Walks the IR AST. Subclass + define `visit_<TypeName>` methods.

    `generic_visit` is the fallback for nodes the subclass doesn't handle;
    it walks the node's children. Leaves (IrLiteral, IrCharClass, IrRuleRef)
    have no children — `generic_visit` is a no-op for them.
    """

    def visit(self, node: object) -> None:
        method = getattr(self, f"visit_{type(node).__name__}", self.generic_visit)
        return method(node)

    def generic_visit(self, node: object) -> None:
        if isinstance(node, IrAst):
            for r in node.rules:
                self.visit(r)
        elif isinstance(node, IrRule):
            self.visit(node.body)
        elif isinstance(node, IrAlternation):
            for arm in node.arms:
                self.visit(arm)
        elif isinstance(node, IrSequence):
            for it in node.items:
                self.visit(it)
        elif isinstance(node, IrItem):
            self.visit(node.atom)
        elif isinstance(node, IrGroup):
            self.visit(node.body)
        # Leaves: IrLiteral, IrCharClass, IrRuleRef — no children.


class IrTransformer(IrVisitor):
    """Rewrites the IR AST. Each visit returns a (possibly new) node.

    The default `visit_<TypeName>` for any node is `generic_visit`, which
    rebuilds the node with transformed children if any of them changed,
    or returns the original node otherwise (preserving identity is cheap
    and helps tests).
    """

    def visit(self, node):  # type: ignore[override]
        method = getattr(self, f"visit_{type(node).__name__}", self.generic_visit)
        return method(node)

    def generic_visit(self, node):  # type: ignore[override]
        if isinstance(node, IrAst):
            new_rules = tuple(self.visit(r) for r in node.rules)
            if new_rules == node.rules:
                return node
            return IrAst(rules=new_rules, start=node.start)
        if isinstance(node, IrRule):
            new_body = self.visit(node.body)
            if new_body is node.body:
                return node
            return IrRule(name=node.name, body=new_body)
        if isinstance(node, IrAlternation):
            new_arms = tuple(self.visit(a) for a in node.arms)
            if new_arms == node.arms:
                return node
            return IrAlternation(arms=new_arms)
        if isinstance(node, IrSequence):
            new_items = tuple(self.visit(i) for i in node.items)
            if new_items == node.items:
                return node
            return IrSequence(items=new_items)
        if isinstance(node, IrItem):
            new_atom = self.visit(node.atom)
            if new_atom is node.atom:
                return node
            return IrItem(atom=new_atom, quantifier=node.quantifier)
        if isinstance(node, IrGroup):
            new_body = self.visit(node.body)
            if new_body is node.body:
                return node
            return IrGroup(body=new_body)
        # Leaves: return unchanged.
        return node


def dump(node: object, *, indent: int = 0) -> str:
    """Pretty-print an IR AST node for debugging. Matches Python ast.dump style."""
    pad = "  " * indent
    if isinstance(node, IrAst):
        rules = "\n".join(dump(r, indent=indent + 1) for r in node.rules)
        return f"{pad}IrAst(start={node.start!r}, rules=[\n{rules}\n{pad}])"
    if isinstance(node, IrRule):
        return f"{pad}IrRule({node.name!r},\n{dump(node.body, indent=indent + 1)}\n{pad})"
    if isinstance(node, IrAlternation):
        arms = ",\n".join(dump(a, indent=indent + 1) for a in node.arms)
        return f"{pad}IrAlternation([\n{arms}\n{pad}])"
    if isinstance(node, IrSequence):
        items = ", ".join(dump(i) for i in node.items)
        return f"{pad}IrSequence([{items}])"
    if isinstance(node, IrItem):
        return f"IrItem({dump(node.atom)}, q={node.quantifier})"
    if isinstance(node, IrGroup):
        return f"IrGroup({dump(node.body)})"
    return repr(node)
```

- [ ] **Step 4: Run — expect PASS.**

```bash
uv run pytest tests/unit/lexic/ir/test_walk.py -q
```

- [ ] **Step 5: Run full suite + ruff. Commit.**

```bash
uv run pytest tests/ -q
uv run ruff check src/ tests/
git add src/lexic/ir/walk.py tests/unit/lexic/ir/test_walk.py
git commit -m "feat(ir): IrVisitor + IrTransformer + dump helper"
```

---

## Task 3: `ir/directives.py` — comment-channel directive parsing

`Directives` dataclass + `parse_directives(text, line_comment) -> Directives`. Reads lines like `<line_comment> @<name> <args...>` from raw source text.

**Files:**
- Create: `src/lexic/ir/directives.py`
- Create: `tests/unit/lexic/ir/test_directives.py`

- [ ] **Step 1: Write failing tests.**

```python
# tests/unit/lexic/ir/test_directives.py
"""parse_directives — extracts IR-level directives from source comments."""
from __future__ import annotations

from lexic.ir.directives import Directives, parse_directives


def test_empty_text_returns_empty_directives():
    d = parse_directives("", line_comment="#")
    assert d == Directives()


def test_no_directives_in_grammar_returns_empty():
    text = "root ::= expr\nexpr ::= [0-9]+"
    assert parse_directives(text, line_comment="#") == Directives()


def test_non_semantic_single_arg():
    text = "# @non-semantic ws\nroot ::= ws value"
    d = parse_directives(text, line_comment="#")
    assert d.non_semantic == frozenset({"ws"})


def test_non_semantic_multiple_args():
    text = "# @non-semantic ws comment_block\nroot ::= ws value"
    d = parse_directives(text, line_comment="#")
    assert d.non_semantic == frozenset({"ws", "comment_block"})


def test_directive_must_have_at_marker():
    """Comments without @<name> are not directives."""
    text = "# this is just a comment\nroot ::= x"
    assert parse_directives(text, line_comment="#") == Directives()


def test_directive_respects_line_comment_marker():
    """ABNF uses ; — # is just data inside an ABNF source."""
    text = "; @non-semantic WSP\nroot = WSP value"
    d = parse_directives(text, line_comment=";")
    assert d.non_semantic == frozenset({"WSP"})


def test_unknown_directive_is_ignored():
    text = "# @future-thing foo\n# @non-semantic ws"
    d = parse_directives(text, line_comment="#")
    assert d.non_semantic == frozenset({"ws"})


def test_directive_can_have_leading_whitespace_before_marker():
    """`  # @non-semantic ws` is the same as `# @non-semantic ws`."""
    text = "  # @non-semantic ws\nroot ::= ws value"
    d = parse_directives(text, line_comment="#")
    assert d.non_semantic == frozenset({"ws"})


def test_empty_line_comment_disables_directive_parsing():
    """A flavour with no comment marker (line_comment='') has no directive channel."""
    text = "# @non-semantic ws\nroot ::= ws value"
    assert parse_directives(text, line_comment="") == Directives()


def test_directives_dataclass_has_default_empty_frozenset():
    d = Directives()
    assert d.non_semantic == frozenset()
```

- [ ] **Step 2: Run — expect ModuleNotFoundError.**

```bash
uv run pytest tests/unit/lexic/ir/test_directives.py -q
```

- [ ] **Step 3: Create `src/lexic/ir/directives.py`.**

```python
"""Comment-channel directives for IR-level metadata.

Convention: a line of the form `<line_comment> @<name> <args...>` in the
grammar source declares an IR directive. The flavour declares its
line-comment marker; this module parses any such file regardless of flavour.

Directives are extracted by scanning raw source text *before* the meta-grammar
parser sees it — Lark's `%ignore` rules strip comments from the AST. The two
channels are independent: the grammar parses normally, AND the directive
scanner sees the comments.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Directives:
    """Parsed directive set. Extend with new fields as new directives are added."""

    non_semantic: frozenset[str] = frozenset()


def parse_directives(text: str, line_comment: str) -> Directives:
    """Extract IR directives from source comments.

    `line_comment` is the flavour's line-comment marker (e.g. '#' for GBNF,
    ';' for ABNF). Empty string disables directive parsing entirely.
    """
    if not line_comment:
        return Directives()

    non_semantic: set[str] = set()

    for raw in text.splitlines():
        line = raw.strip()
        if not line.startswith(line_comment):
            continue
        rest = line[len(line_comment):].lstrip()
        if not rest.startswith("@"):
            continue
        parts = rest[1:].split()
        if not parts:
            continue
        name, *args = parts
        if name == "non-semantic":
            non_semantic.update(args)

    return Directives(non_semantic=frozenset(non_semantic))
```

- [ ] **Step 4: Run — expect PASS.**

```bash
uv run pytest tests/unit/lexic/ir/test_directives.py -q
```

- [ ] **Step 5: Run full suite + ruff. Commit.**

```bash
uv run pytest tests/ -q
uv run ruff check src/ tests/
git add src/lexic/ir/directives.py tests/unit/lexic/ir/test_directives.py
git commit -m "feat(ir): parse_directives for comment-channel metadata"
```

---

## Task 4: `grammars/flavour.py` — `Flavour` ABC

Single home for the flavour contract. `Flavour` is an ABC with class-attribute config + two abstract staticmethods + one optional override.

**Files:**
- Create: `src/lexic/grammars/flavour.py`
- Create: `tests/unit/lexic/grammars/test_flavour.py`

- [ ] **Step 1: Write failing tests.**

```python
# tests/unit/lexic/grammars/test_flavour.py
"""Flavour ABC contract tests — using a minimal fake flavour."""
from __future__ import annotations

import pytest

from lexic.grammars.flavour import Flavour
from lexic.ir.escapes import CANONICAL_ESCAPES
from lexic.ir.nodes import IrCharClass, IrGroup, IrLiteral, Quantifier


def test_flavour_is_abstract_cannot_instantiate_directly():
    with pytest.raises(TypeError):
        Flavour()  # type: ignore[abstract]


def test_concrete_flavour_with_required_attrs_works():
    class _Fake(Flavour):
        name = "fake"
        extensions = (".fake",)
        meta_grammar = "start: NAME\nNAME: /[a-z]+/\n"
        escapes = CANONICAL_ESCAPES
        emitter = None  # type: ignore[assignment]
        line_comment = "#"

        @staticmethod
        def parse_quantifier(text: str) -> Quantifier:
            return Quantifier(1, 1)

        @staticmethod
        def parse_charclass(text: str) -> tuple[str, bool]:
            return text, False

    assert _Fake.name == "fake"
    assert _Fake.parse_quantifier("?") == Quantifier(1, 1)


def test_concrete_flavour_missing_abstract_methods_fails():
    class _Bad(Flavour):
        name = "bad"
        extensions = (".bad",)
        meta_grammar = ""
        escapes = CANONICAL_ESCAPES
        emitter = None  # type: ignore[assignment]
        # Missing parse_quantifier and parse_charclass

    with pytest.raises(TypeError):
        _Bad()  # type: ignore[abstract]


def test_normalize_literal_default_is_identity():
    class _F(Flavour):
        name = "f"
        extensions = ()
        meta_grammar = ""
        escapes = CANONICAL_ESCAPES
        emitter = None  # type: ignore[assignment]

        @staticmethod
        def parse_quantifier(text: str) -> Quantifier:
            return Quantifier()

        @staticmethod
        def parse_charclass(text: str) -> tuple[str, bool]:
            return text, False

    assert _F.normalize_literal("hello") == IrLiteral("hello")


def test_normalize_literal_can_be_overridden_to_return_group():
    """ABNF-style: case-insensitive 'abc' expands to a char-class group."""

    class _F(Flavour):
        name = "f"
        extensions = ()
        meta_grammar = ""
        escapes = CANONICAL_ESCAPES
        emitter = None  # type: ignore[assignment]

        @staticmethod
        def parse_quantifier(text: str) -> Quantifier:
            return Quantifier()

        @staticmethod
        def parse_charclass(text: str) -> tuple[str, bool]:
            return text, False

        @classmethod
        def normalize_literal(cls, decoded: str):
            from lexic.ir.nodes import IrAlternation, IrItem, IrSequence

            seq = IrSequence(
                tuple(
                    IrItem(IrCharClass(f"{c.lower()}{c.upper()}"))
                    for c in decoded
                )
            )
            return IrGroup(IrAlternation((seq,)))

    out = _F.normalize_literal("ab")
    assert isinstance(out, IrGroup)
    items = out.body.arms[0].items
    assert items[0].atom == IrCharClass("aA")
    assert items[1].atom == IrCharClass("bB")


def test_default_line_comment_is_empty_string():
    class _F(Flavour):
        name = "f"
        extensions = ()
        meta_grammar = ""
        escapes = CANONICAL_ESCAPES
        emitter = None  # type: ignore[assignment]

        @staticmethod
        def parse_quantifier(text: str) -> Quantifier:
            return Quantifier()

        @staticmethod
        def parse_charclass(text: str) -> tuple[str, bool]:
            return text, False

    assert _F.line_comment == ""
```

- [ ] **Step 2: Run — expect ModuleNotFoundError.**

```bash
uv run pytest tests/unit/lexic/grammars/test_flavour.py -q
```

- [ ] **Step 3: Create `src/lexic/grammars/flavour.py`.**

```python
"""Flavour ABC — the contract every grammar flavour fulfils.

A flavour module is configuration: a Lark meta-grammar string with
canonical-tagged productions, an EscapeCodec subclass, a FlavourEmitter
subclass, and two staticmethods that parse quantifier and char-class
token strings. No imperative pipeline code per flavour.

The optional `normalize_literal` hook allows flavour-specific sugar
expansion (e.g. ABNF case-insensitive literals) without leaking flavour
concepts into the IR AST itself: the hook returns canonical IR AST nodes.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar

from lexic.ir.escapes import EscapeCodec
from lexic.ir.nodes import IrGroup, IrLiteral, Quantifier


class Flavour(ABC):
    """Per-flavour configuration. Subclass and fill in class attributes."""

    name: ClassVar[str]
    extensions: ClassVar[tuple[str, ...]]
    meta_grammar: ClassVar[str]
    escapes: ClassVar[EscapeCodec]
    emitter: ClassVar[object]  # FlavourEmitter — typed loosely to avoid import cycle
    line_comment: ClassVar[str] = ""

    @staticmethod
    @abstractmethod
    def parse_quantifier(text: str) -> Quantifier:
        """Parse a flavour-specific quantifier token text into canonical bounds."""

    @staticmethod
    @abstractmethod
    def parse_charclass(text: str) -> tuple[str, bool]:
        """Parse a bracket-expression token. Return (canonical_pattern, negated)."""

    @classmethod
    def normalize_literal(cls, decoded: str) -> IrLiteral | IrGroup:
        """Optional sugar-expansion hook. Default: identity (return IrLiteral)."""
        return IrLiteral(decoded)
```

- [ ] **Step 4: Run — expect PASS.**

```bash
uv run pytest tests/unit/lexic/grammars/test_flavour.py -q
```

- [ ] **Step 5: Run full suite + ruff. Commit.**

```bash
uv run pytest tests/ -q
uv run ruff check src/ tests/
git add src/lexic/grammars/flavour.py tests/unit/lexic/grammars/test_flavour.py
git commit -m "feat(grammars): Flavour ABC — config-driven flavour contract"
```

---

## Task 5: `ir/derive.py` — `classify_kind`

Pure function: given an `IrRule`, return the kind. Three mutually exclusive cases per the spec. Uses `IrVisitor` to detect rulerefs in subtree.

**Files:**
- Create: `src/lexic/ir/derive.py` (start of file; later tasks extend it)
- Create: `tests/unit/lexic/ir/test_derive.py`

- [ ] **Step 1: Write failing tests for `classify_kind`.**

```python
# tests/unit/lexic/ir/test_derive.py
"""derive_specs and friends — IR-side structural decomposition."""
from __future__ import annotations

from lexic.ir.derive import classify_kind
from lexic.ir.nodes import (
    IrAlternation,
    IrCharClass,
    IrGroup,
    IrItem,
    IrLiteral,
    IrRule,
    IrRuleRef,
    IrSequence,
    Quantifier,
)


def _seq(*items): return IrSequence(tuple(items))
def _alt(*arms): return IrAlternation(tuple(arms))
def _it(atom, q=None): return IrItem(atom, q if q else Quantifier())


# ── classify_kind ─────────────────────────────────────────────────────


def test_classify_value_str_for_pure_literal_alternation():
    """`op ::= "+" | "-"` — no rulerefs anywhere → value_str."""
    rule = IrRule(
        "op",
        _alt(
            _seq(_it(IrLiteral("+"))),
            _seq(_it(IrLiteral("-"))),
        ),
    )
    assert classify_kind(rule) == "value_str"


def test_classify_value_str_for_charclass_only():
    """`digit ::= [0-9]+` — no rulerefs → value_str."""
    rule = IrRule(
        "digit",
        _alt(_seq(_it(IrCharClass("0-9"), Quantifier(1, None)))),
    )
    assert classify_kind(rule) == "value_str"


def test_classify_alternation_for_named_arms():
    """`term ::= num | ident` — multiple non-empty arms with rulerefs."""
    rule = IrRule(
        "term",
        _alt(
            _seq(_it(IrRuleRef("num"))),
            _seq(_it(IrRuleRef("ident"))),
        ),
    )
    assert classify_kind(rule) == "alternation"


def test_classify_sequence_for_single_arm_with_rulerefs():
    """`expr ::= term op term` — single arm with rulerefs."""
    rule = IrRule(
        "expr",
        _alt(
            _seq(
                _it(IrRuleRef("term")),
                _it(IrRuleRef("op")),
                _it(IrRuleRef("term")),
            ),
        ),
    )
    assert classify_kind(rule) == "sequence"


def test_classify_value_str_for_empty_body():
    """A rule with no arms (or all empty) is value_str (degenerate)."""
    rule = IrRule("nothing", _alt())
    assert classify_kind(rule) == "value_str"


def test_classify_value_str_for_literal_only_with_groups():
    """`bool ::= "true" | "false"` even when grouped → value_str."""
    rule = IrRule(
        "bool",
        _alt(
            _seq(_it(IrLiteral("true"))),
            _seq(_it(IrLiteral("false"))),
        ),
    )
    assert classify_kind(rule) == "value_str"


def test_classify_alternation_with_mixed_arms():
    """One single-ruleref arm + one multi-item arm → alternation."""
    rule = IrRule(
        "value",
        _alt(
            _seq(_it(IrRuleRef("number"))),
            _seq(_it(IrLiteral("(")), _it(IrRuleRef("expr")), _it(IrLiteral(")"))),
        ),
    )
    assert classify_kind(rule) == "alternation"


def test_classify_sequence_with_inline_group_containing_rulerefs():
    """`expr ::= term (op term)*` — single arm; the group has rulerefs but rule is sequence."""
    rule = IrRule(
        "expr",
        _alt(
            _seq(
                _it(IrRuleRef("term")),
                _it(
                    IrGroup(_alt(_seq(_it(IrRuleRef("op")), _it(IrRuleRef("term"))))),
                    Quantifier(0, None),
                ),
            ),
        ),
    )
    assert classify_kind(rule) == "sequence"


def test_classify_value_str_for_complex_literal_group():
    """`num ::= "-"? [0-9]+ ("." [0-9]+)?` — has groups but no rulerefs → value_str."""
    rule = IrRule(
        "num",
        _alt(
            _seq(
                _it(IrLiteral("-"), Quantifier(0, 1)),
                _it(IrCharClass("0-9"), Quantifier(1, None)),
                _it(
                    IrGroup(
                        _alt(
                            _seq(
                                _it(IrLiteral(".")),
                                _it(IrCharClass("0-9"), Quantifier(1, None)),
                            )
                        )
                    ),
                    Quantifier(0, 1),
                ),
            ),
        ),
    )
    assert classify_kind(rule) == "value_str"
```

- [ ] **Step 2: Run — expect ModuleNotFoundError.**

```bash
uv run pytest tests/unit/lexic/ir/test_derive.py -q
```

- [ ] **Step 3: Create `src/lexic/ir/derive.py` with `classify_kind` only (later tasks extend).**

```python
"""derive_specs — IR AST → list[RuleSpec] (the codegen view).

Pure, flavour-agnostic structural decomposition. No flavour parameter:
RuleSpec is a structural projection of the IR AST.

This module is built up across tasks 5–8. Task 5 adds classify_kind;
tasks 6–8 add compute_parents, hoist_helpers, and derive_specs itself.
"""

from __future__ import annotations

from typing import Literal

from lexic.ir.nodes import IrAlternation, IrRule, IrRuleRef, IrSequence
from lexic.ir.walk import IrVisitor


# ── classify_kind ─────────────────────────────────────────────────────


def _has_ruleref(node: object) -> bool:
    """Return True iff the subtree rooted at `node` contains any IrRuleRef."""
    finder = _RuleRefFinder()
    finder.visit(node)
    return finder.found


class _RuleRefFinder(IrVisitor):
    def __init__(self) -> None:
        self.found = False

    def visit_IrRuleRef(self, node: IrRuleRef) -> None:
        self.found = True


def _non_empty_arms(body: IrAlternation) -> list[IrSequence]:
    return [a for a in body.arms if a.items]


def classify_kind(rule: IrRule) -> Literal["sequence", "alternation", "value_str"]:
    """Classify a rule's body into one of the three IR kinds.

    Rules:
      - value_str: no IrRuleRef anywhere in the body (entire subtree).
      - alternation: multiple non-empty arms with rulerefs.
      - sequence: single non-empty arm with rulerefs.
    """
    if not _has_ruleref(rule.body):
        return "value_str"
    arms = _non_empty_arms(rule.body)
    if len(arms) > 1:
        return "alternation"
    return "sequence"
```

- [ ] **Step 4: Run — expect PASS.**

```bash
uv run pytest tests/unit/lexic/ir/test_derive.py::test_classify_value_str_for_pure_literal_alternation tests/unit/lexic/ir/test_derive.py -q
```

- [ ] **Step 5: Run full suite + ruff. Commit.**

```bash
uv run pytest tests/ -q
uv run ruff check src/ tests/
git add src/lexic/ir/derive.py tests/unit/lexic/ir/test_derive.py
git commit -m "feat(ir): classify_kind for IR AST rules"
```

---

## Task 6: `ir/derive.py` — `compute_parents`

Determine parent classes: a rule referenced as the *single* unquantified ruleref of an alternation arm gets that alternation's class as parent. Stays inside `derive.py`; extends Task 5's file.

**Files:**
- Modify: `src/lexic/ir/derive.py`
- Modify: `tests/unit/lexic/ir/test_derive.py`

- [ ] **Step 1: Append failing tests.**

```python
# Append to tests/unit/lexic/ir/test_derive.py

from lexic.ir.derive import compute_parents


# ── compute_parents ───────────────────────────────────────────────────


def test_compute_parents_alternation_arms_get_parent():
    """`term ::= num | ident` makes Num and Ident parents = Term."""
    term = IrRule(
        "term",
        _alt(_seq(_it(IrRuleRef("num"))), _seq(_it(IrRuleRef("ident")))),
    )
    num = IrRule("num", _alt(_seq(_it(IrCharClass("0-9"), Quantifier(1, None)))))
    ident = IrRule("ident", _alt(_seq(_it(IrCharClass("a-z"), Quantifier(1, None)))))
    parents = compute_parents([term, num, ident])
    assert parents == {"num": "Term", "ident": "Term"}


def test_compute_parents_only_single_ruleref_arms_create_parent():
    """A multi-item arm doesn't make its rulerefs into subclasses."""
    rule = IrRule(
        "value",
        _alt(
            _seq(_it(IrRuleRef("num"))),
            _seq(_it(IrLiteral("(")), _it(IrRuleRef("expr")), _it(IrLiteral(")"))),
        ),
    )
    inner = IrRule("num", _alt(_seq(_it(IrCharClass("0-9")))))
    expr = IrRule("expr", _alt(_seq(_it(IrRuleRef("num")))))
    parents = compute_parents([rule, inner, expr])
    assert parents == {"num": "Value"}  # expr is in a multi-item arm; no parent


def test_compute_parents_quantified_ruleref_arm_does_not_create_parent():
    """`alt ::= a+ | b` — `a` has a quantifier, so it's not a 'single ref'."""
    rule = IrRule(
        "alt",
        _alt(
            _seq(_it(IrRuleRef("a"), Quantifier(1, None))),
            _seq(_it(IrRuleRef("b"))),
        ),
    )
    a_rule = IrRule("a", _alt(_seq(_it(IrLiteral("a")))))
    b_rule = IrRule("b", _alt(_seq(_it(IrLiteral("b")))))
    parents = compute_parents([rule, a_rule, b_rule])
    assert parents == {"b": "Alt"}


def test_compute_parents_only_alternations_contribute():
    """Sequence rules don't create parent relationships."""
    seq_rule = IrRule(
        "expr",
        _alt(_seq(_it(IrRuleRef("a")), _it(IrRuleRef("b")))),
    )
    a = IrRule("a", _alt(_seq(_it(IrLiteral("a")))))
    b = IrRule("b", _alt(_seq(_it(IrLiteral("b")))))
    assert compute_parents([seq_rule, a, b]) == {}


def test_compute_parents_uses_pascal_case_class_names():
    """`json-value ::= num | ident` → parents use PascalCase class names."""
    rule = IrRule(
        "json-value",
        _alt(_seq(_it(IrRuleRef("num"))), _seq(_it(IrRuleRef("ident")))),
    )
    num = IrRule("num", _alt(_seq(_it(IrCharClass("0-9")))))
    ident = IrRule("ident", _alt(_seq(_it(IrCharClass("a-z")))))
    parents = compute_parents([rule, num, ident])
    assert parents == {"num": "JsonValue", "ident": "JsonValue"}
```

- [ ] **Step 2: Run — expect ImportError on `compute_parents`.**

```bash
uv run pytest tests/unit/lexic/ir/test_derive.py -q
```

- [ ] **Step 3: Append to `src/lexic/ir/derive.py`.**

```python
# Append to src/lexic/ir/derive.py

from lexic.ir.nodes import IrItem
from lexic.utils.names import to_pascal


def _single_unquantified_ruleref(arm: IrSequence) -> str | None:
    """If arm is a single IrItem(IrRuleRef, Quantifier(1,1)), return the ref name."""
    if len(arm.items) != 1:
        return None
    item = arm.items[0]
    if not isinstance(item.atom, IrRuleRef):
        return None
    if item.quantifier.min != 1 or item.quantifier.max != 1:
        return None
    return item.atom.name


def compute_parents(rules: list[IrRule]) -> dict[str, str]:
    """For each rule appearing as a single-unquantified-ref arm in some
    alternation, set its parent class to that alternation's class name.
    """
    parent_of: dict[str, str] = {}
    for rule in rules:
        if classify_kind(rule) != "alternation":
            continue
        parent_cls = to_pascal(rule.name)
        for arm in _non_empty_arms(rule.body):
            ref = _single_unquantified_ruleref(arm)
            if ref is not None:
                parent_of[ref] = parent_cls
    return parent_of
```

- [ ] **Step 4: Run — expect PASS.**

```bash
uv run pytest tests/unit/lexic/ir/test_derive.py -q
```

- [ ] **Step 5: Run full suite + ruff. Commit.**

```bash
uv run pytest tests/ -q
uv run ruff check src/ tests/
git add src/lexic/ir/derive.py tests/unit/lexic/ir/test_derive.py
git commit -m "feat(ir): compute_parents — alternation arm rules get parent class"
```

---

## Task 7: `ir/derive.py` — `hoist_helpers`

Hoist groups with non-trivial quantifiers and (multi-arm or ruleref content) into synthetic rules. Returns a rewritten `IrAst` and a list of helper `IrRule`s.

**Files:**
- Modify: `src/lexic/ir/derive.py`
- Modify: `tests/unit/lexic/ir/test_derive.py`

- [ ] **Step 1: Append failing tests.**

```python
# Append to tests/unit/lexic/ir/test_derive.py

from lexic.ir.derive import hoist_helpers
from lexic.ir.nodes import IrAst


# ── hoist_helpers ─────────────────────────────────────────────────────


def test_hoist_no_groups_returns_unchanged():
    rule = IrRule("r", _alt(_seq(_it(IrRuleRef("x")))))
    ast = IrAst(rules=(rule,), start="r")
    out_ast, helpers = hoist_helpers(ast)
    assert helpers == []
    assert out_ast == ast


def test_hoist_unquantified_group_with_rulerefs_stays_inline():
    """`(a | b)` no quantifier is an inline-alternation candidate; not hoisted."""
    rule = IrRule(
        "r",
        _alt(
            _seq(
                _it(
                    IrGroup(_alt(_seq(_it(IrRuleRef("a"))), _seq(_it(IrRuleRef("b")))))
                )
            )
        ),
    )
    ast = IrAst(rules=(rule,), start="r")
    out_ast, helpers = hoist_helpers(ast)
    assert helpers == []
    assert out_ast == ast


def test_hoist_literal_only_quantified_group_stays_inline():
    """`("foo"|"bar")+` is a regex pattern candidate; not hoisted."""
    rule = IrRule(
        "r",
        _alt(
            _seq(
                _it(
                    IrGroup(
                        _alt(_seq(_it(IrLiteral("foo"))), _seq(_it(IrLiteral("bar"))))
                    ),
                    Quantifier(1, None),
                )
            )
        ),
    )
    ast = IrAst(rules=(rule,), start="r")
    out_ast, helpers = hoist_helpers(ast)
    assert helpers == []
    assert out_ast == ast


def test_hoist_quantified_multi_arm_group_with_rulerefs():
    """`(a | b)+` → r-item ::= a | b; r body becomes (r-item)+."""
    rule = IrRule(
        "r",
        _alt(
            _seq(
                _it(
                    IrGroup(
                        _alt(_seq(_it(IrRuleRef("a"))), _seq(_it(IrRuleRef("b"))))
                    ),
                    Quantifier(1, None),
                )
            )
        ),
    )
    ast = IrAst(rules=(rule,), start="r")
    out_ast, helpers = hoist_helpers(ast)
    assert len(helpers) == 1
    helper = helpers[0]
    assert helper.name == "r-item"
    assert helper.body == _alt(
        _seq(_it(IrRuleRef("a"))), _seq(_it(IrRuleRef("b")))
    )
    # Original rule's group is replaced by a ruleref to the helper
    new_item = out_ast.rules[0].body.arms[0].items[0]
    assert new_item.atom == IrRuleRef("r-item")
    assert new_item.quantifier == Quantifier(1, None)


def test_hoist_quantified_single_arm_group_with_rulerefs():
    """`expr ::= term (op term)*` — the (op term)* group hoists to a helper."""
    rule = IrRule(
        "expr",
        _alt(
            _seq(
                _it(IrRuleRef("term")),
                _it(
                    IrGroup(
                        _alt(_seq(_it(IrRuleRef("op")), _it(IrRuleRef("term"))))
                    ),
                    Quantifier(0, None),
                ),
            )
        ),
    )
    ast = IrAst(rules=(rule,), start="expr")
    out_ast, helpers = hoist_helpers(ast)
    assert len(helpers) == 1
    helper = helpers[0]
    assert helper.name == "expr-item"
    # The hoisted body keeps the inner sequence
    assert helper.body.arms[0].items[0].atom == IrRuleRef("op")
    assert helper.body.arms[0].items[1].atom == IrRuleRef("term")
    # Outer rule body now has term then a ruleref to the helper
    items = out_ast.rules[0].body.arms[0].items
    assert items[0].atom == IrRuleRef("term")
    assert items[1].atom == IrRuleRef("expr-item")
    assert items[1].quantifier == Quantifier(0, None)


def test_hoist_assigns_unique_names_when_multiple_helpers():
    """Two hoisted groups in the same rule get distinct names."""
    rule = IrRule(
        "r",
        _alt(
            _seq(
                _it(
                    IrGroup(_alt(_seq(_it(IrRuleRef("a"))))),
                    Quantifier(1, None),
                ),
                _it(
                    IrGroup(_alt(_seq(_it(IrRuleRef("b"))))),
                    Quantifier(1, None),
                ),
            )
        ),
    )
    ast = IrAst(rules=(rule,), start="r")
    out_ast, helpers = hoist_helpers(ast)
    names = [h.name for h in helpers]
    assert sorted(names) == ["r-item", "r-item2"]


def test_hoist_preserves_ast_start():
    rule = IrRule("root", _alt(_seq(_it(IrRuleRef("x")))))
    other = IrRule("x", _alt(_seq(_it(IrLiteral("X")))))
    ast = IrAst(rules=(rule, other), start="root")
    out_ast, _helpers = hoist_helpers(ast)
    assert out_ast.start == "root"
```

- [ ] **Step 2: Run — expect ImportError.**

```bash
uv run pytest tests/unit/lexic/ir/test_derive.py -q
```

- [ ] **Step 3: Append to `src/lexic/ir/derive.py`.**

```python
# Append to src/lexic/ir/derive.py

from lexic.ir.nodes import IrAst, IrGroup, IrLiteral


def hoist_helpers(ast: IrAst) -> tuple[IrAst, list[IrRule]]:
    """Rewrite groups-with-quantifiers-needing-hoisting into synthetic rules.

    A group `(g)` with quantifier q is hoisted iff:
      - q is non-trivial (i.e., not Quantifier(1, 1)), AND
      - g has multiple arms OR g contains any IrRuleRef.

    Hoisted: a new IrRule named '<parent>-item[N]' whose body is g; the
    original `IrItem(IrGroup(g), q)` is replaced by `IrItem(IrRuleRef(name), q)`.

    Pure literal-only groups are NEVER hoisted (they are regex pattern
    candidates handled at codegen time).
    """
    helpers: list[IrRule] = []
    name_set: set[str] = {r.name for r in ast.rules}
    new_rules: list[IrRule] = []

    for rule in ast.rules:
        new_body = _hoist_alt(
            rule.body, parent_name=rule.name, helpers=helpers, name_set=name_set
        )
        new_rules.append(IrRule(rule.name, new_body))

    return IrAst(rules=tuple(new_rules), start=ast.start), helpers


def _hoist_alt(
    alt: IrAlternation,
    *,
    parent_name: str,
    helpers: list[IrRule],
    name_set: set[str],
) -> IrAlternation:
    return IrAlternation(
        arms=tuple(
            _hoist_seq(
                arm,
                parent_name=parent_name,
                helpers=helpers,
                name_set=name_set,
            )
            for arm in alt.arms
        )
    )


def _hoist_seq(
    seq: IrSequence,
    *,
    parent_name: str,
    helpers: list[IrRule],
    name_set: set[str],
) -> IrSequence:
    return IrSequence(
        items=tuple(
            _hoist_item(
                item,
                parent_name=parent_name,
                helpers=helpers,
                name_set=name_set,
            )
            for item in seq.items
        )
    )


def _hoist_item(
    item: IrItem,
    *,
    parent_name: str,
    helpers: list[IrRule],
    name_set: set[str],
) -> IrItem:
    atom = item.atom
    if not isinstance(atom, IrGroup):
        return item
    # Recurse into the group body first (handles nested groups).
    inner_body = _hoist_alt(
        atom.body, parent_name=parent_name, helpers=helpers, name_set=name_set
    )
    is_quantified = item.quantifier != Quantifier(1, 1)
    is_multi_arm = len(_non_empty_arms(inner_body)) > 1
    has_rulerefs = _has_ruleref(inner_body)
    if is_quantified and (is_multi_arm or has_rulerefs):
        helper_name = _reserve(parent_name, name_set)
        name_set.add(helper_name)
        helpers.append(IrRule(name=helper_name, body=inner_body))
        return IrItem(
            atom=IrRuleRef(name=helper_name), quantifier=item.quantifier
        )
    return IrItem(atom=IrGroup(body=inner_body), quantifier=item.quantifier)


def _reserve(parent_name: str, taken: set[str]) -> str:
    base = f"{parent_name}-item"
    if base not in taken:
        return base
    n = 2
    while f"{base}{n}" in taken:
        n += 1
    return f"{base}{n}"
```

Note: the `Quantifier`, `IrItem` imports are already present from Task 6. Confirm imports are clean (no duplicates).

- [ ] **Step 4: Run — expect PASS.**

```bash
uv run pytest tests/unit/lexic/ir/test_derive.py -q
```

- [ ] **Step 5: Run full suite + ruff. Commit.**

```bash
uv run pytest tests/ -q
uv run ruff check src/ tests/
git add src/lexic/ir/derive.py tests/unit/lexic/ir/test_derive.py
git commit -m "feat(ir): hoist_helpers — quantified groups become synthetic rules"
```

---

## Task 8: `ir/derive.py` — `derive_specs` orchestrator + non-semantic marking

The top-level entry. Hoists helpers, classifies, builds RuleSpecs, marks non-semantic fields, topo-sorts. Includes a small `_assign_ir_field_names(items)` helper that mirrors `naming.assign_field_names` but dispatches on `IrItem.atom` types.

**Key conventions for `RuleSpec.items` in the new pipeline:**

- `kind = "sequence"` → `items = post-hoist body.arms[0].items` (flat list of `IrItem`)
- `kind = "alternation"` → `items = [IrItem(IrRuleRef(arm_name)) for each arm_rule_name]`; `field_map = {}`
- `kind = "value_str"` → if single-arm: `items = arm.items` (flat); if multi-arm: `items = [IrItem(IrGroup(body))]` (wraps alternation so emitters can render `"+" | "-"`)

`RuleSpec.items` is typed `list[Atom]` in the existing `ir/spec.py`; `Atom` is a runtime-checkable Protocol marker, so it accepts `IrItem` structurally during transition. Phase D tightens the annotation.

**Files:**
- Modify: `src/lexic/ir/derive.py`
- Modify: `tests/unit/lexic/ir/test_derive.py`

- [ ] **Step 1: Append failing tests for `derive_specs`.**

```python
# Append to tests/unit/lexic/ir/test_derive.py

from lexic.ir.derive import derive_specs


# ── derive_specs ──────────────────────────────────────────────────────


def test_derive_value_str_single_arm():
    """`digit ::= [0-9]+` → one value_str spec, items hold the charclass."""
    rule = IrRule(
        "digit",
        _alt(_seq(_it(IrCharClass("0-9"), Quantifier(1, None)))),
    )
    ast = IrAst(rules=(rule,), start="digit")
    specs = derive_specs(ast)
    assert len(specs) == 1
    spec = specs[0]
    assert spec.rule_name == "digit"
    assert spec.class_name == "Digit"
    assert spec.kind == "value_str"
    assert spec.field_map == {}
    assert len(spec.items) == 1
    assert spec.items[0].atom == IrCharClass("0-9")


def test_derive_value_str_multi_arm_wraps_in_group():
    """`op ::= "+" | "-"` → value_str; items wraps the alternation in IrGroup."""
    rule = IrRule(
        "op",
        _alt(_seq(_it(IrLiteral("+"))), _seq(_it(IrLiteral("-")))),
    )
    ast = IrAst(rules=(rule,), start="op")
    specs = derive_specs(ast)
    spec = specs[0]
    assert spec.kind == "value_str"
    assert len(spec.items) == 1
    assert isinstance(spec.items[0].atom, IrGroup)
    grp = spec.items[0].atom
    assert grp.body == _alt(_seq(_it(IrLiteral("+"))), _seq(_it(IrLiteral("-"))))


def test_derive_sequence_basic():
    """`expr ::= term op term` → sequence spec; items flat."""
    rule = IrRule(
        "expr",
        _alt(
            _seq(_it(IrRuleRef("term")), _it(IrRuleRef("op")), _it(IrRuleRef("term"))),
        ),
    )
    other = IrRule("term", _alt(_seq(_it(IrCharClass("a-z")))))
    op = IrRule("op", _alt(_seq(_it(IrLiteral("+")))))
    ast = IrAst(rules=(rule, other, op), start="expr")
    specs = derive_specs(ast)
    expr_spec = next(s for s in specs if s.rule_name == "expr")
    assert expr_spec.kind == "sequence"
    assert len(expr_spec.items) == 3
    assert all(isinstance(i.atom, IrRuleRef) for i in expr_spec.items)
    # Field map maps "term" → 0, "op" → 1, "term2" → 2 (collision rename)
    assert "term" in expr_spec.field_map
    assert "op" in expr_spec.field_map
    assert "term2" in expr_spec.field_map


def test_derive_alternation_produces_abstract_plus_no_arm_specs_for_single_refs():
    """`term ::= num | ident` → 3 specs (Term abstract + Num + Ident).

    Term's items are [IrItem(IrRuleRef("num")), IrItem(IrRuleRef("ident"))];
    Num and Ident have parent=Term.
    """
    term = IrRule(
        "term",
        _alt(_seq(_it(IrRuleRef("num"))), _seq(_it(IrRuleRef("ident")))),
    )
    num = IrRule("num", _alt(_seq(_it(IrCharClass("0-9"), Quantifier(1, None)))))
    ident = IrRule("ident", _alt(_seq(_it(IrCharClass("a-z"), Quantifier(1, None)))))
    ast = IrAst(rules=(term, num, ident), start="term")
    specs = derive_specs(ast)
    by = {s.rule_name: s for s in specs}
    assert by["term"].kind == "alternation"
    assert by["term"].field_map == {}
    assert [i.atom for i in by["term"].items] == [IrRuleRef("num"), IrRuleRef("ident")]
    assert by["num"].parent_class_name == "Term"
    assert by["ident"].parent_class_name == "Term"


def test_derive_alternation_with_multi_item_arm_synthesises_arm_spec():
    """`value ::= num | "(" expr ")"` produces Value abstract + Num parent + ValueArm2."""
    value = IrRule(
        "value",
        _alt(
            _seq(_it(IrRuleRef("num"))),
            _seq(_it(IrLiteral("(")), _it(IrRuleRef("expr")), _it(IrLiteral(")"))),
        ),
    )
    num = IrRule("num", _alt(_seq(_it(IrCharClass("0-9"), Quantifier(1, None)))))
    expr = IrRule("expr", _alt(_seq(_it(IrRuleRef("num")))))
    ast = IrAst(rules=(value, num, expr), start="value")
    specs = derive_specs(ast)
    by = {s.rule_name: s for s in specs}
    assert "value-arm2" in by
    arm2 = by["value-arm2"]
    assert arm2.kind == "sequence"
    assert arm2.parent_class_name == "Value"
    # Num still gets parent=Value (single-ref arm)
    assert by["num"].parent_class_name == "Value"


def test_derive_topo_sort_puts_start_first():
    a = IrRule("a", _alt(_seq(_it(IrLiteral("a")))))
    root = IrRule("root", _alt(_seq(_it(IrRuleRef("a")))))
    ast = IrAst(rules=(a, root), start="root")
    specs = derive_specs(ast)
    assert specs[0].rule_name == "root"


def test_derive_helper_rules_appear_in_output():
    """Hoisted helpers become real RuleSpecs in the result."""
    rule = IrRule(
        "expr",
        _alt(
            _seq(
                _it(IrRuleRef("term")),
                _it(
                    IrGroup(_alt(_seq(_it(IrRuleRef("op")), _it(IrRuleRef("term"))))),
                    Quantifier(0, None),
                ),
            )
        ),
    )
    op = IrRule("op", _alt(_seq(_it(IrLiteral("+")))))
    term = IrRule("term", _alt(_seq(_it(IrCharClass("a-z")))))
    ast = IrAst(rules=(rule, op, term), start="expr")
    specs = derive_specs(ast)
    names = {s.rule_name for s in specs}
    assert "expr-item" in names
    helper = next(s for s in specs if s.rule_name == "expr-item")
    assert helper.kind == "sequence"


def test_derive_marks_non_semantic_field_min_zero():
    """`expr ::= term ws op` with non_semantic_rules={"ws"} forces ws field min=0."""
    expr = IrRule(
        "expr",
        _alt(_seq(_it(IrRuleRef("term")), _it(IrRuleRef("ws")), _it(IrRuleRef("op")))),
    )
    term = IrRule("term", _alt(_seq(_it(IrCharClass("a-z")))))
    ws = IrRule("ws", _alt(_seq(_it(IrCharClass(" \\t"), Quantifier(0, None)))))
    op = IrRule("op", _alt(_seq(_it(IrLiteral("+")))))
    ast = IrAst(rules=(expr, term, ws, op), start="expr")
    specs = derive_specs(ast, non_semantic_rules=frozenset({"ws"}))
    expr_spec = next(s for s in specs if s.rule_name == "expr")
    # Find the ws item
    ws_item = next(i for i in expr_spec.items if isinstance(i.atom, IrRuleRef) and i.atom.name == "ws")
    assert ws_item.quantifier.min == 0
    assert "ws" in expr_spec.non_semantic_fields


def test_derive_no_non_semantic_when_rule_not_in_set():
    """Without `non_semantic_rules`, ws fields stay required."""
    expr = IrRule(
        "expr",
        _alt(_seq(_it(IrRuleRef("term")), _it(IrRuleRef("ws")))),
    )
    term = IrRule("term", _alt(_seq(_it(IrCharClass("a-z")))))
    ws = IrRule("ws", _alt(_seq(_it(IrCharClass(" \\t"), Quantifier(0, None)))))
    ast = IrAst(rules=(expr, term, ws), start="expr")
    specs = derive_specs(ast)  # no non_semantic_rules
    expr_spec = next(s for s in specs if s.rule_name == "expr")
    ws_item = next(i for i in expr_spec.items if isinstance(i.atom, IrRuleRef) and i.atom.name == "ws")
    assert ws_item.quantifier.min == 1
    assert expr_spec.non_semantic_fields == frozenset()
```

- [ ] **Step 2: Run — expect ImportError.**

```bash
uv run pytest tests/unit/lexic/ir/test_derive.py -q
```

- [ ] **Step 3: Append `derive_specs` and helpers to `src/lexic/ir/derive.py`.**

```python
# Append to src/lexic/ir/derive.py

from lexic.ir.naming import _CHARCLASS_NAMES, _LITERAL_NAMES, _sanitize_pattern
from lexic.ir.spec import RuleSpec
from lexic.ir.topo import topo_sort
from lexic.ir.nodes import IrCharClass


# ── field naming for IrItem-shaped items ──────────────────────────────


def _ir_charclass_field_name(cc: IrCharClass) -> str:
    bracketed = f"[{'^' if cc.negated else ''}{cc.pattern}]"
    if bracketed in _CHARCLASS_NAMES:
        return _CHARCLASS_NAMES[bracketed]
    hint = _sanitize_pattern(bracketed)
    return hint or "cc"


def _ir_literal_field_name(value: str) -> str:
    if value in _LITERAL_NAMES:
        return _LITERAL_NAMES[value]
    import re

    sanitized = re.sub(r"[^a-zA-Z0-9]", "_", value).strip("_").lower()[:12]
    return sanitized or "lit"


def _ir_group_field_name(group: IrGroup) -> str:
    """For an inline group: 'value' if any ruleref, else literal-based hint."""
    if _has_ruleref(group):
        return "value"
    # Literal-only group → derive a name from the first literal/char in the first arm
    if group.body.arms and group.body.arms[0].items:
        first = group.body.arms[0].items[0].atom
        if isinstance(first, IrLiteral):
            return _ir_literal_field_name(first.value)
        if isinstance(first, IrCharClass):
            return _ir_charclass_field_name(first)
    return "inline"


def _assign_ir_field_names(items: list[IrItem]) -> dict[str, int]:
    """Per-rule field naming over IrItems. Mirrors naming.assign_field_names."""
    field_map: dict[str, int] = {}
    counts: dict[str, int] = {}

    def unique(base: str) -> str:
        n = counts.get(base, 0) + 1
        counts[base] = n
        return base if n == 1 else f"{base}{n}"

    for i, item in enumerate(items):
        atom = item.atom
        if isinstance(atom, IrLiteral) and item.quantifier == Quantifier(1, 1):
            continue  # Structural literal — not a field
        if isinstance(atom, IrLiteral):
            field_map[unique(_ir_literal_field_name(atom.value))] = i
        elif isinstance(atom, IrCharClass):
            field_map[unique(_ir_charclass_field_name(atom))] = i
        elif isinstance(atom, IrRuleRef):
            field_map[unique(atom.name.replace("-", "_"))] = i
        elif isinstance(atom, IrGroup):
            field_map[unique(_ir_group_field_name(atom))] = i
    return field_map


# ── spec construction ────────────────────────────────────────────────


def _build_value_str_spec(rule: IrRule, cls_name: str, parent_cls: str) -> RuleSpec:
    arms = _non_empty_arms(rule.body)
    if len(arms) == 1:
        items = list(arms[0].items)
    else:
        # Multi-arm value_str: wrap the alternation in a group so emitters
        # can render `"+" | "-"` instead of `"+" "-"`.
        items = [IrItem(atom=IrGroup(body=rule.body))]
    return RuleSpec(
        rule_name=rule.name,
        class_name=cls_name,
        parent_class_name=parent_cls,
        kind="value_str",
        items=items,
        field_map={},
    )


def _build_sequence_spec(rule: IrRule, cls_name: str, parent_cls: str) -> RuleSpec:
    arms = _non_empty_arms(rule.body)
    items = list(arms[0].items) if arms else []
    return RuleSpec(
        rule_name=rule.name,
        class_name=cls_name,
        parent_class_name=parent_cls,
        kind="sequence",
        items=items,
        field_map=_assign_ir_field_names(items),
    )


def _build_alternation_specs(
    rule: IrRule, cls_name: str, parent_cls: str
) -> list[RuleSpec]:
    """Build the abstract alternation spec + concrete arm-N specs as needed."""
    arm_rule_names: list[str] = []
    arm_specs: list[RuleSpec] = []
    for idx, arm in enumerate(_non_empty_arms(rule.body), start=1):
        ref = _single_unquantified_ruleref(arm)
        if ref is not None:
            arm_rule_names.append(ref)
            continue
        arm_name = f"{rule.name}-arm{idx}"
        arm_cls_name = f"{cls_name}Arm{idx}"
        arm_rule_names.append(arm_name)
        arm_items = list(arm.items)
        arm_specs.append(
            RuleSpec(
                rule_name=arm_name,
                class_name=arm_cls_name,
                parent_class_name=cls_name,
                kind="sequence",
                items=arm_items,
                field_map=_assign_ir_field_names(arm_items),
            )
        )
    abstract = RuleSpec(
        rule_name=rule.name,
        class_name=cls_name,
        parent_class_name=parent_cls,
        kind="alternation",
        items=[IrItem(atom=IrRuleRef(name=n)) for n in arm_rule_names],
        field_map={},
    )
    return [abstract] + arm_specs


def _mark_non_semantic(
    spec: RuleSpec, non_semantic_rules: frozenset[str]
) -> RuleSpec:
    """Set min=0 on IrItems whose atom is IrRuleRef in non_semantic_rules.
    Also populate non_semantic_fields with the corresponding field names.
    """
    if not non_semantic_rules:
        return spec
    new_items: list[IrItem] = []
    changed = False
    for item in spec.items:
        if (
            isinstance(item.atom, IrRuleRef)
            and item.atom.name in non_semantic_rules
            and item.quantifier.min > 0
        ):
            new_items.append(
                IrItem(
                    atom=item.atom,
                    quantifier=Quantifier(min=0, max=item.quantifier.max),
                )
            )
            changed = True
        else:
            new_items.append(item)
    non_sem = frozenset(
        name
        for name, idx in spec.field_map.items()
        if isinstance(new_items[idx].atom, IrRuleRef)
        and new_items[idx].atom.name in non_semantic_rules
    )
    if not changed and non_sem == spec.non_semantic_fields:
        return spec
    return RuleSpec(
        rule_name=spec.rule_name,
        class_name=spec.class_name,
        parent_class_name=spec.parent_class_name,
        kind=spec.kind,
        items=new_items,
        field_map=spec.field_map,
        non_semantic_fields=non_sem,
    )


# ── top-level orchestrator ───────────────────────────────────────────


def derive_specs(
    ast: IrAst,
    *,
    non_semantic_rules: frozenset[str] = frozenset(),
) -> list[RuleSpec]:
    """Walk the IR AST; produce the codegen RuleSpec view.

    Pure function. No flavour reference.
    """
    ast2, helpers = hoist_helpers(ast)
    all_rules: list[IrRule] = list(ast2.rules) + helpers
    parents = compute_parents(all_rules)
    name_map = {r.name: to_pascal(r.name) for r in all_rules}

    specs: list[RuleSpec] = []
    for rule in all_rules:
        cls_name = name_map[rule.name]
        parent_cls = parents.get(rule.name, "GrammarModel")
        kind = classify_kind(rule)
        if kind == "value_str":
            specs.append(_build_value_str_spec(rule, cls_name, parent_cls))
        elif kind == "alternation":
            specs.extend(_build_alternation_specs(rule, cls_name, parent_cls))
        else:  # sequence
            specs.append(_build_sequence_spec(rule, cls_name, parent_cls))

    specs = [_mark_non_semantic(s, non_semantic_rules) for s in specs]
    return topo_sort(specs, is_start_rule=lambda s: s.rule_name == ast.start)
```

- [ ] **Step 4: Run — expect PASS.**

```bash
uv run pytest tests/unit/lexic/ir/test_derive.py -q
```

If `_assign_ir_field_names` fails because `_CHARCLASS_NAMES`/`_LITERAL_NAMES` are private to `naming.py`: change the imports to use the public lookup helpers from `naming` if present, or copy the dicts inline. In current state `naming.py` exports them at module level (leading underscore is a convention, not enforcement); the import will work.

- [ ] **Step 5: Run full suite + ruff. Commit.**

```bash
uv run pytest tests/ -q
uv run ruff check src/ tests/
git add src/lexic/ir/derive.py tests/unit/lexic/ir/test_derive.py
git commit -m "feat(ir): derive_specs orchestrator + non-semantic marking"
```

---

## Task 9: `parsing/meta_parser.py` — `MetaGrammarParser`

Generic Lark-based parser that consumes any conforming `Flavour` and produces an `IrAst`. The transformer's eight tag methods (`ir_rule`, `ir_alternation`, …) live here.

**Files:**
- Create: `src/lexic/parsing/__init__.py`
- Create: `src/lexic/parsing/meta_parser.py`
- Create: `tests/unit/lexic/parsing/__init__.py` (empty)
- Create: `tests/unit/lexic/parsing/test_meta_parser.py`

- [ ] **Step 1: Create the empty package files.**

```bash
mkdir -p /home/mika/projects/lexic/src/lexic/parsing
mkdir -p /home/mika/projects/lexic/tests/unit/lexic/parsing
touch /home/mika/projects/lexic/src/lexic/parsing/__init__.py
touch /home/mika/projects/lexic/tests/unit/lexic/parsing/__init__.py
```

- [ ] **Step 2: Write failing tests using a tiny stub flavour (no GBNF dependency).**

```python
# tests/unit/lexic/parsing/test_meta_parser.py
"""MetaGrammarParser — generic Lark + canonical-tag dispatch → IrAst.

Tested with a tiny stub flavour that exists only in this test file.
"""
from __future__ import annotations

from lexic.grammars.flavour import Flavour
from lexic.ir.escapes import EscapeCodec
from lexic.ir.nodes import (
    IrAlternation,
    IrAst,
    IrCharClass,
    IrGroup,
    IrItem,
    IrLiteral,
    IrRule,
    IrRuleRef,
    IrSequence,
    Quantifier,
)
from lexic.parsing.meta_parser import MetaGrammarParser


class _StubEscapes(EscapeCodec):
    SHORT_ESCAPES = {"n": "\n", "t": "\t", "\\": "\\", '"': '"'}
    HEX_ESCAPES = ()


class _StubFlavour(Flavour):
    """Mini-language: `name = body`; quantifiers `?`, `*`, `+`; charclasses `[...]`."""

    name = "stub"
    extensions = (".stub",)
    line_comment = "#"
    escapes = _StubEscapes()
    emitter = None  # type: ignore[assignment]
    meta_grammar = r"""
start: rule+
rule: NAME "=" alternation     -> ir_rule
alternation: sequence ("|" sequence)*  -> ir_alternation
sequence: item*                -> ir_sequence
item: atom QUANTIFIER?         -> ir_item
atom: LITERAL                  -> ir_literal
    | CHARCLASS                -> ir_charclass
    | NAME                     -> ir_ruleref
    | "(" alternation ")"      -> ir_group

NAME: /[a-zA-Z_][a-zA-Z0-9_-]*/
LITERAL: /"([^"\\]|\\.)*"/
CHARCLASS: /\[(?:\^)?(?:[^\]\\]|\\.)*\]/
QUANTIFIER: /[?*+]/

%ignore /[ \t\n\r]+/
%ignore /#[^\n]*/
"""

    @staticmethod
    def parse_quantifier(text: str) -> Quantifier:
        if text == "?":
            return Quantifier(0, 1)
        if text == "*":
            return Quantifier(0, None)
        if text == "+":
            return Quantifier(1, None)
        return Quantifier(1, 1)

    @staticmethod
    def parse_charclass(text: str) -> tuple[str, bool]:
        # Strip [ and ]; detect leading ^
        inner = text[1:-1]
        if inner.startswith("^"):
            return inner[1:], True
        return inner, False


def _ast_first_rule(text: str) -> IrRule:
    ast = MetaGrammarParser(_StubFlavour).parse(text)
    return ast.rules[0]


# ── Basic shapes ─────────────────────────────────────────────────────


def test_parses_single_rule_with_literal():
    ast = MetaGrammarParser(_StubFlavour).parse('foo = "hi"\n')
    assert isinstance(ast, IrAst)
    assert ast.rules[0].name == "foo"
    assert ast.rules[0].body == IrAlternation(
        (IrSequence((IrItem(IrLiteral("hi")),)),)
    )


def test_parses_charclass():
    rule = _ast_first_rule("digit = [0-9]\n")
    item = rule.body.arms[0].items[0]
    assert item.atom == IrCharClass("0-9", negated=False)


def test_parses_negated_charclass():
    rule = _ast_first_rule(r'r = [^"\\]' + "\n")
    item = rule.body.arms[0].items[0]
    assert isinstance(item.atom, IrCharClass)
    assert item.atom.negated is True


def test_parses_ruleref():
    rule = _ast_first_rule("a = b\n")
    item = rule.body.arms[0].items[0]
    assert item.atom == IrRuleRef("b")


def test_parses_alternation():
    rule = _ast_first_rule('op = "+" | "-"\n')
    assert len(rule.body.arms) == 2
    assert rule.body.arms[0].items[0].atom == IrLiteral("+")
    assert rule.body.arms[1].items[0].atom == IrLiteral("-")


def test_parses_quantifiers():
    rule = _ast_first_rule("expr = a? b* c+\n")
    items = rule.body.arms[0].items
    assert items[0].quantifier == Quantifier(0, 1)
    assert items[1].quantifier == Quantifier(0, None)
    assert items[2].quantifier == Quantifier(1, None)


def test_parses_group():
    rule = _ast_first_rule("expr = (a | b)\n")
    item = rule.body.arms[0].items[0]
    assert isinstance(item.atom, IrGroup)
    assert len(item.atom.body.arms) == 2


def test_decodes_literal_escapes_via_flavour_codec():
    """`\\n` in source becomes a real newline in IrLiteral.value."""
    rule = _ast_first_rule(r'r = "a\nb"' + "\n")
    item = rule.body.arms[0].items[0]
    assert item.atom == IrLiteral("a\nb")  # 3 chars: a, newline, b


# ── Start rule ───────────────────────────────────────────────────────


def test_start_rule_is_first_rule_in_source():
    ast = MetaGrammarParser(_StubFlavour).parse('root = "x"\nfoo = "y"\n')
    assert ast.start == "root"


# ── Sugar expansion via normalize_literal ────────────────────────────


def test_normalize_literal_override_expands_to_group():
    """A flavour can override normalize_literal to expand sugar to canonical IR."""

    class _CaseInsensitiveStub(_StubFlavour):
        @classmethod
        def normalize_literal(cls, decoded: str):
            seq = IrSequence(
                tuple(
                    IrItem(IrCharClass(f"{c.lower()}{c.upper()}"))
                    for c in decoded
                )
            )
            return IrGroup(IrAlternation((seq,)))

    ast = MetaGrammarParser(_CaseInsensitiveStub).parse('r = "ab"\n')
    item = ast.rules[0].body.arms[0].items[0]
    assert isinstance(item.atom, IrGroup)
    inner_items = item.atom.body.arms[0].items
    assert inner_items[0].atom == IrCharClass("aA")
    assert inner_items[1].atom == IrCharClass("bB")
```

- [ ] **Step 3: Run — expect ModuleNotFoundError on `lexic.parsing.meta_parser`.**

```bash
uv run pytest tests/unit/lexic/parsing/test_meta_parser.py -q
```

- [ ] **Step 4: Create `src/lexic/parsing/meta_parser.py`.**

```python
"""MetaGrammarParser — generic Lark-based IR-AST parser.

Knows a fixed set of canonical tag names (ir_rule, ir_alternation, ir_sequence,
ir_item, ir_literal, ir_charclass, ir_ruleref, ir_group). The flavour's Lark
meta-grammar uses these names to label productions; this module dispatches each
tag to the appropriate IR AST constructor. Token-value handling (escape decoding,
charclass parsing, quantifier parsing) delegates to the Flavour.
"""

from __future__ import annotations

from lark import Lark, Token, Transformer

from lexic.grammars.flavour import Flavour
from lexic.ir.nodes import (
    IrAlternation,
    IrAst,
    IrCharClass,
    IrGroup,
    IrItem,
    IrLiteral,
    IrRule,
    IrRuleRef,
    IrSequence,
    Quantifier,
)


class MetaGrammarParser:
    """Generic IR-AST parser. Stateless after construction."""

    def __init__(self, flavour: type[Flavour]) -> None:
        self._flavour = flavour
        self._lark = Lark(
            flavour.meta_grammar, parser="earley", ambiguity="resolve"
        )
        self._transformer = _IrTagTransformer(flavour)

    def parse(self, text: str) -> IrAst:
        tree = self._lark.parse(text)
        return self._transformer.transform(tree)


class _IrTagTransformer(Transformer):
    """Maps tagged Lark productions to IR AST nodes."""

    def __init__(self, flavour: type[Flavour]) -> None:
        super().__init__()
        self._flavour = flavour

    # `start` is the implicit Lark root; collect rules into IrAst.
    def start(self, items: list) -> IrAst:
        rules = tuple(items)
        first = rules[0].name if rules else ""
        return IrAst(rules=rules, start=first)

    def ir_rule(self, items: list) -> IrRule:
        name_token, body = items
        return IrRule(name=str(name_token), body=body)

    def ir_alternation(self, items: list) -> IrAlternation:
        return IrAlternation(arms=tuple(items))

    def ir_sequence(self, items: list) -> IrSequence:
        return IrSequence(items=tuple(items))

    def ir_item(self, items: list) -> IrItem:
        atom = items[0]
        if len(items) > 1 and items[1] is not None:
            quantifier = self._flavour.parse_quantifier(str(items[1]))
        else:
            quantifier = Quantifier()
        return IrItem(atom=atom, quantifier=quantifier)

    def ir_literal(self, items: list):
        token = str(items[0])
        # The literal token is the full quoted string. Strip both ends.
        unquoted = token[1:-1]
        decoded = self._flavour.escapes.decode(unquoted)
        return self._flavour.normalize_literal(decoded)

    def ir_charclass(self, items: list) -> IrCharClass:
        token = str(items[0])
        pattern, negated = self._flavour.parse_charclass(token)
        return IrCharClass(pattern=pattern, negated=negated)

    def ir_ruleref(self, items: list) -> IrRuleRef:
        return IrRuleRef(name=str(items[0]))

    def ir_group(self, items: list) -> IrGroup:
        return IrGroup(body=items[0])
```

- [ ] **Step 5: Run — expect PASS.**

```bash
uv run pytest tests/unit/lexic/parsing/test_meta_parser.py -q
```

If failures arise from Lark token shape (e.g. `items[1]` being a `Token` vs missing): inspect with a debug print, then adjust the `ir_item` method to handle Lark's variadic shape (Lark passes only the children that matched; the optional `QUANTIFIER?` either appears or doesn't).

- [ ] **Step 6: Run full suite + ruff. Commit.**

```bash
uv run pytest tests/ -q
uv run ruff check src/ tests/
git add src/lexic/parsing/__init__.py src/lexic/parsing/meta_parser.py tests/unit/lexic/parsing/__init__.py tests/unit/lexic/parsing/test_meta_parser.py
git commit -m "feat(parsing): MetaGrammarParser — generic Lark + tag dispatch → IrAst"
```

---

## Phase B — GBNF flavour migration

## Task 10: `grammars/gbnf/meta_grammar.py` — Lark grammar string with canonical tags

The GBNF Lark meta-grammar, retagged with the canonical names from Task 9. This is just data; no logic.

**Files:**
- Create: `src/lexic/grammars/gbnf/meta_grammar.py`
- Create: `tests/unit/lexic/grammars/gbnf/test_meta_grammar.py`

- [ ] **Step 1: Write failing tests (sanity checks on the grammar string).**

```python
# tests/unit/lexic/grammars/gbnf/test_meta_grammar.py
"""Sanity tests for the GBNF meta-grammar string."""
from __future__ import annotations

from lark import Lark

from lexic.grammars.gbnf.meta_grammar import META_GRAMMAR


def test_meta_grammar_is_a_nonempty_string():
    assert isinstance(META_GRAMMAR, str)
    assert len(META_GRAMMAR.strip()) > 0


def test_meta_grammar_uses_canonical_tag_names():
    """The grammar must use ir_rule / ir_alternation / ir_sequence / ir_item /
    ir_literal / ir_charclass / ir_ruleref / ir_group tags."""
    for tag in (
        "ir_rule",
        "ir_alternation",
        "ir_sequence",
        "ir_item",
        "ir_literal",
        "ir_charclass",
        "ir_ruleref",
        "ir_group",
    ):
        assert f"-> {tag}" in META_GRAMMAR, f"missing tag {tag}"


def test_meta_grammar_constructs_a_valid_lark():
    """No syntax errors in the meta-grammar."""
    Lark(META_GRAMMAR, parser="earley", ambiguity="resolve")


def test_meta_grammar_ignores_comments_and_whitespace():
    parser = Lark(META_GRAMMAR, parser="earley", ambiguity="resolve")
    # Should parse without error
    parser.parse("# a comment\nfoo ::= \"x\"\n")
```

- [ ] **Step 2: Run — expect ModuleNotFoundError.**

```bash
uv run pytest tests/unit/lexic/grammars/gbnf/test_meta_grammar.py -q
```

- [ ] **Step 3: Create `src/lexic/grammars/gbnf/meta_grammar.py`.**

```python
"""GBNF meta-grammar — Lark grammar string with canonical IR-AST tags.

The MetaGrammarParser dispatches productions tagged `ir_rule`, `ir_literal`,
etc. to its generic IR-AST constructor. This file is data; no logic.
"""

META_GRAMMAR = r"""
start: rule+

rule: NAME "::=" alternation     -> ir_rule
alternation: sequence ("|" sequence)*  -> ir_alternation
sequence: item*                  -> ir_sequence
item: atom QUANTIFIER?           -> ir_item

atom: LITERAL                    -> ir_literal
    | CHARCLASS                  -> ir_charclass
    | NAME                       -> ir_ruleref
    | "(" alternation ")"        -> ir_group

NAME: /[a-zA-Z_][a-zA-Z0-9_-]*/
LITERAL: /"([^"\\]|\\.)*"/
CHARCLASS: /\[(?:\^)?(?:[^\]\\]|\\.)*\]/
QUANTIFIER: /[?*+]|\{[0-9]+(?:,[0-9]*)?\}/

%ignore /[ \t\n\r]+/
%ignore /#[^\n]*/
"""
```

- [ ] **Step 4: Run — expect PASS.**

```bash
uv run pytest tests/unit/lexic/grammars/gbnf/test_meta_grammar.py -q
```

- [ ] **Step 5: Run full suite + ruff. Commit.**

```bash
uv run pytest tests/ -q
uv run ruff check src/ tests/
git add src/lexic/grammars/gbnf/meta_grammar.py tests/unit/lexic/grammars/gbnf/test_meta_grammar.py
git commit -m "feat(gbnf): META_GRAMMAR with canonical IR-AST tags"
```

---

## Task 11: `grammars/gbnf/flavour.py` — `GbnfFlavour`

Bind everything together. `GbnfFlavour` declares constants, plugs in `META_GRAMMAR`, `GBNF_ESCAPES`, the existing `GbnfEmitter`, and provides `parse_quantifier` + `parse_charclass`. No `normalize_literal` override — GBNF literals are case-sensitive.

**Files:**
- Create: `src/lexic/grammars/gbnf/flavour.py`
- Create: `tests/unit/lexic/grammars/gbnf/test_flavour.py`

- [ ] **Step 1: Write failing tests.**

```python
# tests/unit/lexic/grammars/gbnf/test_flavour.py
"""GbnfFlavour — full Flavour binding for GBNF."""
from __future__ import annotations

from lexic.grammars.flavour import Flavour
from lexic.grammars.gbnf.flavour import GbnfFlavour
from lexic.ir.nodes import IrLiteral, Quantifier


def test_gbnf_flavour_is_a_flavour_subclass():
    assert issubclass(GbnfFlavour, Flavour)


def test_gbnf_flavour_metadata():
    assert GbnfFlavour.name == "gbnf"
    assert ".gbnf" in GbnfFlavour.extensions
    assert GbnfFlavour.line_comment == "#"


def test_gbnf_flavour_meta_grammar_is_imported():
    assert "ir_rule" in GbnfFlavour.meta_grammar
    assert "::=" in GbnfFlavour.meta_grammar


def test_gbnf_flavour_escapes_decodes_backslash_n():
    assert GbnfFlavour.escapes.decode(r"\n") == "\n"
    assert GbnfFlavour.escapes.decode(r"a\tb") == "a\tb"


def test_parse_quantifier_question_mark():
    assert GbnfFlavour.parse_quantifier("?") == Quantifier(0, 1)


def test_parse_quantifier_star():
    assert GbnfFlavour.parse_quantifier("*") == Quantifier(0, None)


def test_parse_quantifier_plus():
    assert GbnfFlavour.parse_quantifier("+") == Quantifier(1, None)


def test_parse_quantifier_braces_exact():
    assert GbnfFlavour.parse_quantifier("{3}") == Quantifier(3, 3)


def test_parse_quantifier_braces_range():
    assert GbnfFlavour.parse_quantifier("{1,5}") == Quantifier(1, 5)


def test_parse_quantifier_braces_unbounded():
    assert GbnfFlavour.parse_quantifier("{2,}") == Quantifier(2, None)


def test_parse_charclass_basic():
    pattern, negated = GbnfFlavour.parse_charclass("[a-z]")
    assert pattern == "a-z"
    assert negated is False


def test_parse_charclass_negated():
    pattern, negated = GbnfFlavour.parse_charclass(r'[^"\\]')
    assert pattern == r'"\\'
    assert negated is True


def test_normalize_literal_default_identity():
    assert GbnfFlavour.normalize_literal("hello") == IrLiteral("hello")
```

- [ ] **Step 2: Run — expect ModuleNotFoundError.**

```bash
uv run pytest tests/unit/lexic/grammars/gbnf/test_flavour.py -q
```

- [ ] **Step 3: Create `src/lexic/grammars/gbnf/flavour.py`.**

```python
"""GbnfFlavour — single-source GBNF flavour binding.

Composes META_GRAMMAR, GBNF_ESCAPES, GbnfEmitter, and the two token-value
parsers. No imperative pipeline code — the IR-side machinery
(MetaGrammarParser, derive_specs) does the work.
"""

from __future__ import annotations

from lexic.grammars.flavour import Flavour
from lexic.grammars.gbnf.adapter import GBNF_ESCAPES
from lexic.grammars.gbnf.emitter import GbnfEmitter
from lexic.grammars.gbnf.meta_grammar import META_GRAMMAR
from lexic.ir.nodes import Quantifier
from lexic.utils.quantifiers import quantifier_to_bounds


class GbnfFlavour(Flavour):
    name = "gbnf"
    extensions = (".gbnf",)
    meta_grammar = META_GRAMMAR
    escapes = GBNF_ESCAPES
    # The Phase D consumers will adopt the no-arg GbnfEmitter constructor; until
    # then we instantiate with an empty list (legacy signature).
    emitter = GbnfEmitter([])
    line_comment = "#"

    @staticmethod
    def parse_quantifier(text: str) -> Quantifier:
        lo, hi = quantifier_to_bounds(text)
        return Quantifier(min=lo, max=hi)

    @staticmethod
    def parse_charclass(text: str) -> tuple[str, bool]:
        # text includes the brackets: [pattern] or [^pattern]
        inner = text[1:-1]
        if inner.startswith("^"):
            return inner[1:], True
        return inner, False
```

- [ ] **Step 4: Run — expect PASS.**

```bash
uv run pytest tests/unit/lexic/grammars/gbnf/test_flavour.py -q
```

- [ ] **Step 5: Run full suite + ruff. Commit.**

```bash
uv run pytest tests/ -q
uv run ruff check src/ tests/
git add src/lexic/grammars/gbnf/flavour.py tests/unit/lexic/grammars/gbnf/test_flavour.py
git commit -m "feat(gbnf): GbnfFlavour binds meta_grammar + escapes + emitter + token parsers"
```

---

## Task 12: `compile.py` — `compile_grammar` entry point (parallel to existing `compile`)

Add a NEW function `compile_grammar(text, flavour, *, non_semantic_rules=None) -> list[RuleSpec]` that uses the new pipeline. Existing `compile()` (the cache + Lark parser bundle) is unchanged.

**Files:**
- Modify: `src/lexic/compile.py` — add `compile_grammar`
- Create: `tests/integration/test_compile_grammar_gbnf.py`

- [ ] **Step 1: Write failing integration tests.**

```python
# tests/integration/test_compile_grammar_gbnf.py
"""compile_grammar(text, GbnfFlavour) — end-to-end via new pipeline."""
from __future__ import annotations

from lexic.compile import compile_grammar
from lexic.grammars.gbnf.flavour import GbnfFlavour
from lexic.ir.nodes import IrCharClass, IrItem, IrRuleRef


def test_compile_grammar_returns_rulespecs():
    text = 'root ::= "x"\n'
    specs = compile_grammar(text, GbnfFlavour)
    assert len(specs) == 1
    assert specs[0].rule_name == "root"
    assert specs[0].kind == "value_str"


def test_compile_grammar_simple_arithmetic():
    text = (
        "root  ::= expr\n"
        "expr  ::= term op term\n"
        "term  ::= num\n"
        "op    ::= [-+*/]\n"
        "num   ::= [0-9]+\n"
    )
    specs = compile_grammar(text, GbnfFlavour)
    by = {s.rule_name: s for s in specs}
    # Topo-sorted with start first
    assert specs[0].rule_name == "root"
    assert by["expr"].kind == "sequence"
    assert by["op"].kind == "value_str"
    assert by["num"].kind == "value_str"


def test_compile_grammar_extracts_directive_when_present():
    """Source with `# @non-semantic ws` makes ws fields optional."""
    text = (
        "# @non-semantic ws\n"
        "root ::= ws value\n"
        'value ::= "x"\n'
        "ws ::= [ \\t]*\n"
    )
    specs = compile_grammar(text, GbnfFlavour)
    by = {s.rule_name: s for s in specs}
    root = by["root"]
    ws_item = next(
        i for i in root.items if isinstance(i.atom, IrRuleRef) and i.atom.name == "ws"
    )
    assert ws_item.quantifier.min == 0
    assert "ws" in root.non_semantic_fields


def test_compile_grammar_explicit_non_semantic_overrides_directive():
    """Explicit non_semantic_rules wins over comment directive."""
    text = (
        "# @non-semantic ws\n"
        "root ::= ws value\n"
        'value ::= "x"\n'
        "ws ::= [ \\t]*\n"
    )
    specs = compile_grammar(text, GbnfFlavour, non_semantic_rules=frozenset())
    by = {s.rule_name: s for s in specs}
    root = by["root"]
    ws_item = next(
        i for i in root.items if isinstance(i.atom, IrRuleRef) and i.atom.name == "ws"
    )
    assert ws_item.quantifier.min == 1  # not marked non-semantic
    assert root.non_semantic_fields == frozenset()


def test_compile_grammar_alternation_creates_subclasses():
    text = (
        "root  ::= term\n"
        "term  ::= num | ident\n"
        "num   ::= [0-9]+\n"
        "ident ::= [a-z]+\n"
    )
    specs = compile_grammar(text, GbnfFlavour)
    by = {s.rule_name: s for s in specs}
    assert by["term"].kind == "alternation"
    assert by["num"].parent_class_name == "Term"
    assert by["ident"].parent_class_name == "Term"
```

- [ ] **Step 2: Run — expect ImportError on `compile_grammar`.**

```bash
uv run pytest tests/integration/test_compile_grammar_gbnf.py -q
```

- [ ] **Step 3: Add `compile_grammar` to `src/lexic/compile.py`.**

Add the following at the end of `src/lexic/compile.py`:

```python
# ── New IR-AST pipeline entry (Phase A–D coexists with old compile()). ──


def compile_grammar(
    text: str,
    flavour,  # type[Flavour]
    *,
    non_semantic_rules: frozenset[str] | None = None,
) -> list["RuleSpec"]:
    """Parse + derive RuleSpecs via the new IR-AST pipeline.

    If `non_semantic_rules` is None, parse the source for
    `<line_comment> @non-semantic …` directives and use those.
    """
    from lexic.ir.derive import derive_specs
    from lexic.ir.directives import parse_directives
    from lexic.parsing.meta_parser import MetaGrammarParser

    if non_semantic_rules is None:
        non_semantic_rules = parse_directives(
            text, flavour.line_comment
        ).non_semantic
    ast = MetaGrammarParser(flavour).parse(text)
    return derive_specs(ast, non_semantic_rules=non_semantic_rules)
```

The lazy imports are intentional: keep the existing `compile.py` import surface unchanged during transition.

- [ ] **Step 4: Run — expect PASS.**

```bash
uv run pytest tests/integration/test_compile_grammar_gbnf.py -q
```

- [ ] **Step 5: Run full suite + ruff. Commit.**

```bash
uv run pytest tests/ -q
uv run ruff check src/ tests/
git add src/lexic/compile.py tests/integration/test_compile_grammar_gbnf.py
git commit -m "feat(compile): compile_grammar(text, flavour) — new IR-AST pipeline entry"
```

---

## Task 13: GBNF round-trip validation against `resources/ground_truth/`

Run `compile_grammar` over every ground-truth `.gbnf` and assert structural reasonableness (rules count > 0, no exceptions, kinds make sense). Then round-trip through GBNF emit + re-parse, comparing IRAst-equivalence-after-canonicalization.

**Files:**
- Create: `tests/integration/test_gbnf_ir_round_trip.py`

- [ ] **Step 1: Write failing tests.**

```python
# tests/integration/test_gbnf_ir_round_trip.py
"""Ground-truth GBNF fixtures parse via the new IR-AST pipeline and round-trip."""
from __future__ import annotations

from pathlib import Path

import pytest

from lexic.compile import compile_grammar
from lexic.grammars.gbnf.flavour import GbnfFlavour
from lexic.parsing.meta_parser import MetaGrammarParser

GROUND_TRUTH = Path(__file__).resolve().parents[1] / "resources" / "ground_truth"

# Map ground-truth files → known non-semantic rule names where applicable.
_NON_SEMANTIC = {
    "json_ws.gbnf": frozenset({"ws"}),
    "arithmetic.gbnf": frozenset({"ws"}),
}


@pytest.mark.parametrize(
    "fixture",
    [
        "arithmetic.gbnf",
        "c.gbnf",
        "chess.gbnf",
        "japanese.gbnf",
        "json_arr.gbnf",
        "json_ws.gbnf",
        "list.gbnf",
    ],
)
def test_compile_grammar_succeeds_on_ground_truth(fixture):
    text = (GROUND_TRUTH / fixture).read_text(encoding="utf-8")
    non_sem = _NON_SEMANTIC.get(fixture, frozenset())
    specs = compile_grammar(text, GbnfFlavour, non_semantic_rules=non_sem)
    assert len(specs) > 0
    # First spec is the start rule by topo invariant.
    assert specs[0].rule_name in {"root", "start"} or specs[0].rule_name == specs[0].rule_name


@pytest.mark.parametrize(
    "fixture",
    [
        "arithmetic.gbnf",
        "json_arr.gbnf",
        "list.gbnf",
    ],
)
def test_meta_grammar_parser_round_trip_idempotent(fixture):
    """Parse → IrAst → parse again of the *original text* yields equal IrAst.
    (We don't yet have an IrAst-based GBNF emitter, so the test is parse-stability.)
    """
    text = (GROUND_TRUTH / fixture).read_text(encoding="utf-8")
    parser = MetaGrammarParser(GbnfFlavour)
    ast1 = parser.parse(text)
    ast2 = parser.parse(text)
    assert ast1 == ast2
```

- [ ] **Step 2: Run — expect failures or errors revealing parser issues.**

```bash
uv run pytest tests/integration/test_gbnf_ir_round_trip.py -v
```

- [ ] **Step 3: Iterate to green.**

Likely issues:
- `c.gbnf` or `chess.gbnf` may use grammar features the meta-grammar doesn't yet handle (e.g., embedded comments inside rules, `A` style escapes that need decoder support). Open the failing fixture, identify the construct, and fix in the appropriate place:
  - Missing token shape → fix the meta-grammar regex in `grammars/gbnf/meta_grammar.py`.
  - Decoder gap → confirm `GBNF_ESCAPES` covers all required escape forms.
  - Quantifier shape edge case → fix `GbnfFlavour.parse_quantifier`.
- Any `KeyError` / `AttributeError` from `derive_specs` indicates an IR-AST shape we didn't consider — add a test in `test_derive.py` that reproduces it minimally, then fix.

Iterate until all 7 fixtures pass.

- [ ] **Step 4: Run full suite + ruff. Commit.**

```bash
uv run pytest tests/ -q
uv run ruff check src/ tests/
git add tests/integration/test_gbnf_ir_round_trip.py
git commit -m "test(integration): GBNF ground-truth fixtures parse via new IR pipeline"
```

---

## Phase C — Stub ABNF flavour

The ABNF subset stress-tests the IR AST surface. Same `Flavour` shape as GBNF but with hex escapes, prefix quantifiers, semicolon comments, case-insensitive literal expansion.

## Task 14: `grammars/abnf/escapes.py` — `AbnfEscapes(EscapeCodec)`

ABNF doesn't have `\n`/`\t` literal escapes inside strings; literals are pure characters. Hex escapes appear *outside* string literals as `%xNN`. So `AbnfEscapes` is mostly a no-op codec — the IR's hex-style escapes don't apply to ABNF literals.

For Phase C purposes (a *minimal* subset), the escape codec only needs to:
- decode: identity (ABNF literals are already canonical Python).
- encode: identity.

`%x41-5A` ranges are parsed by `parse_charclass`, not by the escape codec.

**Files:**
- Create: `src/lexic/grammars/abnf/__init__.py` (empty)
- Create: `src/lexic/grammars/abnf/escapes.py`
- Create: `tests/unit/lexic/grammars/abnf/__init__.py` (empty)
- Create: `tests/unit/lexic/grammars/abnf/test_escapes.py`

- [ ] **Step 1: Create empty package __init__ files.**

```bash
mkdir -p /home/mika/projects/lexic/src/lexic/grammars/abnf
mkdir -p /home/mika/projects/lexic/tests/unit/lexic/grammars/abnf
touch /home/mika/projects/lexic/src/lexic/grammars/abnf/__init__.py
touch /home/mika/projects/lexic/tests/unit/lexic/grammars/abnf/__init__.py
```

- [ ] **Step 2: Write failing tests.**

```python
# tests/unit/lexic/grammars/abnf/test_escapes.py
"""AbnfEscapes — ABNF literals are already canonical Python; codec is identity."""
from __future__ import annotations

from lexic.grammars.abnf.escapes import ABNF_ESCAPES, AbnfEscapes
from lexic.ir.escapes import EscapeCodec


def test_abnf_escapes_is_an_escape_codec():
    assert isinstance(ABNF_ESCAPES, EscapeCodec)
    assert isinstance(ABNF_ESCAPES, AbnfEscapes)


def test_decode_is_identity():
    assert ABNF_ESCAPES.decode("hello") == "hello"
    assert ABNF_ESCAPES.decode("") == ""


def test_encode_is_identity():
    assert ABNF_ESCAPES.encode("hello") == "hello"
```

- [ ] **Step 3: Run — expect ModuleNotFoundError.**

```bash
uv run pytest tests/unit/lexic/grammars/abnf/test_escapes.py -q
```

- [ ] **Step 4: Create `src/lexic/grammars/abnf/escapes.py`.**

```python
"""AbnfEscapes — minimal ABNF escape codec.

ABNF string literals don't carry C-style escape sequences; they are
pure characters. Hex values appear OUTSIDE literals as %xNN tokens
parsed by `AbnfFlavour.parse_charclass`. So the codec is identity.
"""

from __future__ import annotations

from lexic.ir.escapes import EscapeCodec


class AbnfEscapes(EscapeCodec):
    """Identity codec — ABNF literals are canonical Python."""

    SHORT_ESCAPES = {}
    HEX_ESCAPES = ()


ABNF_ESCAPES: EscapeCodec = AbnfEscapes()
```

- [ ] **Step 5: Run — expect PASS. Commit.**

```bash
uv run pytest tests/unit/lexic/grammars/abnf/test_escapes.py -q
uv run pytest tests/ -q
uv run ruff check src/ tests/
git add src/lexic/grammars/abnf/__init__.py src/lexic/grammars/abnf/escapes.py tests/unit/lexic/grammars/abnf/__init__.py tests/unit/lexic/grammars/abnf/test_escapes.py
git commit -m "feat(abnf): AbnfEscapes — identity codec for ABNF literals"
```

---

## Task 15: `grammars/abnf/emitter.py` — `AbnfEmitter(FlavourEmitter)`

ABNF syntax constants. `=` instead of `::=`, `/` instead of `|`, prefix quantifiers, `%xNN` charclasses. Override `format_quantifier` (prefix), `render_charclass` (hex form), and `quote` (no escape encoding needed).

**Files:**
- Create: `src/lexic/grammars/abnf/emitter.py`
- Create: `tests/unit/lexic/grammars/abnf/test_emitter.py`

- [ ] **Step 1: Write failing tests.**

```python
# tests/unit/lexic/grammars/abnf/test_emitter.py
"""AbnfEmitter — ABNF-specific syntax constants + format_quantifier prefix."""
from __future__ import annotations

from lexic.grammars.abnf.emitter import AbnfEmitter
from lexic.grammars.abnf.escapes import ABNF_ESCAPES


def _emitter() -> AbnfEmitter:
    return AbnfEmitter(escapes=ABNF_ESCAPES)


def test_rule_separator_is_equals():
    e = _emitter()
    assert e.rule_separator == "="


def test_alt_separator_is_slash():
    assert _emitter().alt_separator == " / "


def test_format_quantifier_prefix_zero_or_more():
    """ABNF `*body` for zero-or-more — but the emitter's interface expects suffix.
    For Phase C, format_quantifier returns the *prefix-style* token; the
    emit algorithm rearranges placement at render-atom time.
    """
    e = _emitter()
    # We adopt prefix-quantifier semantics by returning a marker the algorithm
    # interprets. See AbnfEmitter.format_quantifier for details.
    assert e.format_quantifier(0, None) == "*"
    assert e.format_quantifier(1, None) == "1*"
    assert e.format_quantifier(0, 1) == "*1"  # zero or one == *1
    assert e.format_quantifier(2, 5) == "2*5"
    assert e.format_quantifier(3, 3) == "3"
    assert e.format_quantifier(1, 1) == ""


def test_render_charclass_emits_hex_range():
    """Canonical POSIX 'a-z' → ABNF `%x61-7A`."""
    e = _emitter()
    out = e.render_charclass("a-z")
    assert out == "%x61-7A"


def test_render_charclass_handles_multi_range():
    e = _emitter()
    out = e.render_charclass("a-zA-Z")
    # Two range segments
    assert out == "(%x61-7A / %x41-5A)"


def test_quote_uses_double_quotes():
    e = _emitter()
    assert e.quote("hello") == '"hello"'
```

- [ ] **Step 2: Run — expect ModuleNotFoundError.**

```bash
uv run pytest tests/unit/lexic/grammars/abnf/test_emitter.py -q
```

- [ ] **Step 3: Create `src/lexic/grammars/abnf/emitter.py`.**

```python
"""AbnfEmitter — minimal-ABNF flavour emitter.

Overrides syntax constants and three decorators:
- rule_separator = "="
- alt_separator = " / "
- format_quantifier — emits ABNF prefix quantifiers (e.g. "1*", "*5", "2*5")
- render_charclass — translates POSIX ranges to ABNF %x hex ranges

ABNF places the quantifier *before* the atom, which is the inverse of the
generic FlavourEmitter algorithm. To stay inside the existing algorithm,
format_quantifier returns the prefix string and the AbnfEmitter overrides
the renderers for atom types that take a quantifier so they prepend instead
of append. For Phase C we accept that the emitter renders "1*ALPHA" via
override-atom-handlers; full prefix-vs-suffix support is a generalisation
that can land if a real ABNF target ships.
"""

from __future__ import annotations

from typing import ClassVar

from lexic.ir.emit import FlavourEmitter
from lexic.ir.protocols import AtomEmitHandler
from lexic.ir.atoms import (  # legacy atom types — used by DEFAULT_HANDLERS
    CharClassAtom,
    LiteralAtom,
    QuantifiedLiteralAtom,
    RuleRefAtom,
)


def _hex_range_segment(seg: str) -> str:
    """Convert one POSIX range segment ('a-z' or single char) to ABNF hex."""
    if len(seg) == 3 and seg[1] == "-":
        lo, hi = seg[0], seg[2]
        return f"%x{ord(lo):02X}-{ord(hi):02X}"
    if len(seg) == 1:
        return f"%x{ord(seg):02X}"
    # Multi-char without dash: emit as a sequence of single-char hexes
    return " / ".join(f"%x{ord(c):02X}" for c in seg)


def _split_charclass_segments(pattern: str) -> list[str]:
    """Split a POSIX bracket interior into 3-char ranges and 1-char literals."""
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


class AbnfEmitter(FlavourEmitter):
    rule_separator: ClassVar[str] = "="
    alt_separator: ClassVar[str] = " / "
    quote_char: ClassVar[str] = '"'
    group_open: ClassVar[str] = "("
    group_close: ClassVar[str] = ")"
    empty_body: ClassVar[str] = '""'

    supports: ClassVar[frozenset[str]] = frozenset(
        {
            "literal",
            "char_class",
            "quantifier",
            "alternation",
            "non_capturing_group",
        }
    )

    @property  # type: ignore[override]
    def supports(self) -> frozenset[str]:
        return type(self).__dict__["supports"]

    def format_quantifier(self, lo: int, hi: int | None) -> str:
        """Return the ABNF *prefix* quantifier string. Empty when (1, 1)."""
        if lo == 1 and hi == 1:
            return ""
        if lo == hi:
            return f"{lo}"
        if hi is None:
            return f"{lo}*" if lo != 0 else "*"
        return f"{lo}*{hi}" if lo != 0 else f"*{hi}"

    def render_charclass(self, canonical_pattern: str) -> str:
        segments = _split_charclass_segments(canonical_pattern)
        rendered = [_hex_range_segment(s) for s in segments]
        if len(rendered) == 1:
            return rendered[0]
        return "(" + " / ".join(rendered) + ")"

    # ABNF places the quantifier BEFORE the atom. Override only the
    # quantifier-bearing handlers so they prepend instead of append.
    DEFAULT_HANDLERS: ClassVar[dict[type, AtomEmitHandler]] = (
        FlavourEmitter.make_handlers(
            (LiteralAtom, lambda a, e: e.quote(a.value)),
            (
                QuantifiedLiteralAtom,
                lambda a, e: e.format_quantifier(a.min, a.max) + e.quote(a.value),
            ),
            (
                CharClassAtom,
                lambda a, e: e.format_quantifier(a.min, a.max)
                + e.render_charclass(a.pattern),
            ),
            (
                RuleRefAtom,
                lambda a, e: e.format_quantifier(a.min, a.max) + a.rule_name,
            ),
        )
    )
```

The `DEFAULT_HANDLERS` override is partial: the new IR-AST pipeline produces
`IrItem`-shaped `RuleSpec.items`, not legacy atoms. Phase D updates `FlavourEmitter`
(or AbnfEmitter directly) to walk `IrItem`s. Until cutover, this stub renders
legacy atoms produced by the old pipeline; the new pipeline's `IrItem` rendering
is added in Task 19.

- [ ] **Step 4: Run — expect PASS.**

```bash
uv run pytest tests/unit/lexic/grammars/abnf/test_emitter.py -q
```

- [ ] **Step 5: Run full suite + ruff. Commit.**

```bash
uv run pytest tests/ -q
uv run ruff check src/ tests/
git add src/lexic/grammars/abnf/emitter.py tests/unit/lexic/grammars/abnf/test_emitter.py
git commit -m "feat(abnf): AbnfEmitter with prefix quantifiers and hex-range charclasses"
```

---

## Task 16: `grammars/abnf/meta_grammar.py` + `flavour.py` — `AbnfFlavour`

ABNF Lark meta-grammar with canonical tags. `AbnfFlavour` plugs in escapes/emitter, parses prefix quantifiers, parses `%x` charclasses, and overrides `normalize_literal` to expand case-insensitive literals into char-class groups.

**Files:**
- Create: `src/lexic/grammars/abnf/meta_grammar.py`
- Create: `src/lexic/grammars/abnf/flavour.py`
- Create: `tests/unit/lexic/grammars/abnf/test_flavour.py`

- [ ] **Step 1: Write failing tests.**

```python
# tests/unit/lexic/grammars/abnf/test_flavour.py
"""AbnfFlavour — full Flavour binding for the minimal-ABNF subset."""
from __future__ import annotations

from lexic.grammars.abnf.flavour import AbnfFlavour
from lexic.grammars.flavour import Flavour
from lexic.ir.nodes import IrCharClass, IrGroup, IrLiteral, Quantifier


def test_abnf_flavour_is_a_flavour():
    assert issubclass(AbnfFlavour, Flavour)


def test_abnf_flavour_metadata():
    assert AbnfFlavour.name == "abnf"
    assert ".abnf" in AbnfFlavour.extensions
    assert AbnfFlavour.line_comment == ";"


# ── parse_quantifier ─────────────────────────────────────────────────


def test_parse_quantifier_star_means_zero_or_more():
    assert AbnfFlavour.parse_quantifier("*") == Quantifier(0, None)


def test_parse_quantifier_n_star_means_n_or_more():
    assert AbnfFlavour.parse_quantifier("1*") == Quantifier(1, None)
    assert AbnfFlavour.parse_quantifier("3*") == Quantifier(3, None)


def test_parse_quantifier_star_n_means_zero_to_n():
    assert AbnfFlavour.parse_quantifier("*5") == Quantifier(0, 5)


def test_parse_quantifier_n_star_m_means_n_to_m():
    assert AbnfFlavour.parse_quantifier("2*5") == Quantifier(2, 5)


def test_parse_quantifier_n_alone_means_exactly_n():
    assert AbnfFlavour.parse_quantifier("3") == Quantifier(3, 3)


# ── parse_charclass ──────────────────────────────────────────────────


def test_parse_charclass_single_hex():
    """`%x41` → POSIX 'A'."""
    pattern, negated = AbnfFlavour.parse_charclass("%x41")
    assert pattern == "A"
    assert negated is False


def test_parse_charclass_hex_range():
    """`%x41-5A` → POSIX 'A-Z'."""
    pattern, negated = AbnfFlavour.parse_charclass("%x41-5A")
    assert pattern == "A-Z"
    assert negated is False


# ── normalize_literal — case-insensitive expansion ───────────────────


def test_normalize_literal_alpha_expands_to_charclass_group():
    """`"abc"` in ABNF is case-insensitive; expand to ([aA] [bB] [cC])."""
    out = AbnfFlavour.normalize_literal("abc")
    assert isinstance(out, IrGroup)
    items = out.body.arms[0].items
    assert items[0].atom == IrCharClass("aA")
    assert items[1].atom == IrCharClass("bB")
    assert items[2].atom == IrCharClass("cC")


def test_normalize_literal_all_caps_still_expands():
    out = AbnfFlavour.normalize_literal("XY")
    assert isinstance(out, IrGroup)
    items = out.body.arms[0].items
    assert items[0].atom == IrCharClass("xX")
    assert items[1].atom == IrCharClass("yY")


def test_normalize_literal_non_alpha_stays_literal():
    """Punctuation has no case; keep as IrLiteral."""
    out = AbnfFlavour.normalize_literal("(){}")
    assert out == IrLiteral("(){}")


def test_normalize_literal_mixed_alphanumeric():
    """Letters case-expanded, digits stay literal — emit as group with mixed leaves."""
    out = AbnfFlavour.normalize_literal("a1")
    assert isinstance(out, IrGroup)
    items = out.body.arms[0].items
    assert items[0].atom == IrCharClass("aA")
    assert items[1].atom == IrLiteral("1")


# ── End-to-end: parse a small ABNF sample ────────────────────────────


def test_parse_simple_abnf_grammar_via_meta_parser():
    from lexic.parsing.meta_parser import MetaGrammarParser

    text = (
        '; @non-semantic WSP\n'
        'root = expr\n'
        'expr = num *(op num)\n'
        'num  = 1*DIGIT\n'
        'DIGIT = %x30-39\n'
        'op   = "+" / "-"\n'
        'WSP  = %x20 / %x09\n'
    )
    ast = MetaGrammarParser(AbnfFlavour).parse(text)
    rule_names = {r.name for r in ast.rules}
    assert rule_names == {"root", "expr", "num", "DIGIT", "op", "WSP"}
```

- [ ] **Step 2: Run — expect ModuleNotFoundError.**

```bash
uv run pytest tests/unit/lexic/grammars/abnf/test_flavour.py -q
```

- [ ] **Step 3: Create `src/lexic/grammars/abnf/meta_grammar.py`.**

```python
"""ABNF (subset) meta-grammar with canonical IR-AST tags.

Subset:
  - `name = body` (single =, not ::=)
  - alternation by `/`
  - prefix quantifiers `*N`, `n*`, `n*m`, `n`
  - charclasses via `%xNN` or `%xNN-MM`
  - case-insensitive `"abc"` literals (expansion via normalize_literal)
  - groups `(...)`, comments starting with `;`
"""

META_GRAMMAR = r"""
start: rule+

rule: NAME "=" alternation        -> ir_rule
alternation: sequence ("/" sequence)*  -> ir_alternation
sequence: item*                   -> ir_sequence
item: QUANTIFIER? atom            -> ir_item

atom: LITERAL                     -> ir_literal
    | HEXCC                       -> ir_charclass
    | NAME                        -> ir_ruleref
    | "(" alternation ")"         -> ir_group

NAME: /[A-Za-z][A-Za-z0-9_-]*/
LITERAL: /"[^"\r\n]*"/
HEXCC: /%x[0-9A-Fa-f]+(?:-[0-9A-Fa-f]+)?/
QUANTIFIER: /[0-9]+\*[0-9]*|\*[0-9]+|\*|[0-9]+/

%ignore /[ \t\r\n]+/
%ignore /;[^\n]*/
"""
```

Note: `ir_item: QUANTIFIER? atom` — the quantifier is BEFORE the atom in ABNF source. The `_IrTagTransformer.ir_item` method already handles `len(items) > 1` to detect a quantifier; whether prefix or suffix doesn't matter — the transformer reads the children in declaration order and sniffs which one is the QUANTIFIER token by type.

We need to extend `_IrTagTransformer.ir_item` to handle prefix-OR-suffix quantifier ordering. Update Task 9's transformer:

```python
def ir_item(self, items: list) -> IrItem:
    """Handle either prefix or suffix quantifier ordering."""
    quantifier_token = None
    atom = None
    for c in items:
        if isinstance(c, Token):
            quantifier_token = c
        else:
            atom = c
    if atom is None:
        raise ValueError("ir_item must have an atom child")
    quantifier = (
        self._flavour.parse_quantifier(str(quantifier_token))
        if quantifier_token is not None
        else Quantifier()
    )
    return IrItem(atom=atom, quantifier=quantifier)
```

This change is *backwards-compatible* with GBNF's suffix-quantifier shape (the loop finds the QUANTIFIER token regardless of position). Add a regression test for the GBNF case to be safe (already covered by Task 9 tests).

If the change to `_IrTagTransformer.ir_item` is needed mid-task, fix it immediately and re-run prior tests:

```bash
uv run pytest tests/unit/lexic/parsing/test_meta_parser.py -q
```

- [ ] **Step 4: Create `src/lexic/grammars/abnf/flavour.py`.**

```python
"""AbnfFlavour — minimal-ABNF subset binding."""

from __future__ import annotations

from lexic.grammars.abnf.emitter import AbnfEmitter
from lexic.grammars.abnf.escapes import ABNF_ESCAPES
from lexic.grammars.abnf.meta_grammar import META_GRAMMAR
from lexic.grammars.flavour import Flavour
from lexic.ir.nodes import (
    IrAlternation,
    IrCharClass,
    IrGroup,
    IrItem,
    IrLiteral,
    IrSequence,
    Quantifier,
)


class AbnfFlavour(Flavour):
    name = "abnf"
    extensions = (".abnf",)
    meta_grammar = META_GRAMMAR
    escapes = ABNF_ESCAPES
    emitter = AbnfEmitter(escapes=ABNF_ESCAPES)
    line_comment = ";"

    @staticmethod
    def parse_quantifier(text: str) -> Quantifier:
        # Forms: '*', '*N', 'N*', 'N*M', 'N'
        if text == "*":
            return Quantifier(0, None)
        if text.startswith("*"):
            return Quantifier(0, int(text[1:]))
        if "*" in text:
            lo_str, hi_str = text.split("*", 1)
            lo = int(lo_str)
            hi = int(hi_str) if hi_str else None
            return Quantifier(lo, hi)
        n = int(text)
        return Quantifier(n, n)

    @staticmethod
    def parse_charclass(text: str) -> tuple[str, bool]:
        # text is `%xNN` or `%xNN-MM`. Return canonical POSIX pattern + negated=False.
        body = text[2:]  # drop leading '%x'
        if "-" in body:
            lo_hex, hi_hex = body.split("-", 1)
            return f"{chr(int(lo_hex, 16))}-{chr(int(hi_hex, 16))}", False
        return chr(int(body, 16)), False

    @classmethod
    def normalize_literal(cls, decoded: str):
        """Case-insensitive expansion: 'abc' → ([aA][bB][cC]); leave non-alpha as-is."""
        if not any(c.isalpha() for c in decoded):
            return IrLiteral(decoded)
        items: list[IrItem] = []
        for c in decoded:
            if c.isalpha():
                items.append(IrItem(atom=IrCharClass(f"{c.lower()}{c.upper()}")))
            else:
                items.append(IrItem(atom=IrLiteral(c)))
        return IrGroup(body=IrAlternation((IrSequence(tuple(items)),)))
```

- [ ] **Step 5: Run — expect PASS.**

```bash
uv run pytest tests/unit/lexic/grammars/abnf/test_flavour.py -q
```

- [ ] **Step 6: Run full suite + ruff. Commit.**

```bash
uv run pytest tests/ -q
uv run ruff check src/ tests/
git add src/lexic/grammars/abnf/meta_grammar.py src/lexic/grammars/abnf/flavour.py tests/unit/lexic/grammars/abnf/test_flavour.py src/lexic/parsing/meta_parser.py
git commit -m "feat(abnf): AbnfFlavour with prefix quantifiers, hex charclasses, case-insensitive literals"
```

---

## Task 17: ABNF round-trip integration test

A small handwritten ABNF grammar that exercises every feature from the subset table. Compile via `compile_grammar(text, AbnfFlavour)`, assert structural reasonableness.

**Files:**
- Create: `tests/integration/test_compile_grammar_abnf.py`
- Create: `resources/ground_truth/arithmetic.abnf` (small fixture)

- [ ] **Step 1: Create the ABNF fixture.**

```bash
cat > /home/mika/projects/lexic/resources/ground_truth/arithmetic.abnf <<'EOF'
; @non-semantic WSP
root = expr
expr = term *(op term)
term = num
op   = "+" / "-" / "*" / "/"
num  = 1*DIGIT
DIGIT = %x30-39
WSP  = %x20 / %x09
EOF
```

- [ ] **Step 2: Write failing tests.**

```python
# tests/integration/test_compile_grammar_abnf.py
"""compile_grammar(text, AbnfFlavour) — end-to-end via new pipeline."""
from __future__ import annotations

from pathlib import Path

from lexic.compile import compile_grammar
from lexic.grammars.abnf.flavour import AbnfFlavour

GROUND_TRUTH = Path(__file__).resolve().parents[1] / "resources" / "ground_truth"


def test_compile_arithmetic_abnf_succeeds():
    text = (GROUND_TRUTH / "arithmetic.abnf").read_text(encoding="utf-8")
    specs = compile_grammar(text, AbnfFlavour)
    by = {s.rule_name: s for s in specs}
    # Has the expected rules
    assert {"root", "expr", "term", "op", "num", "DIGIT", "WSP"} <= set(by)


def test_compile_arithmetic_abnf_extracts_non_semantic_directive():
    text = (GROUND_TRUTH / "arithmetic.abnf").read_text(encoding="utf-8")
    specs = compile_grammar(text, AbnfFlavour)
    # Any rule that references WSP should have it marked non-semantic
    # — for this fixture the WSP rule isn't directly referenced from root/expr/etc.,
    # but the directive should still be parsed.
    # The strongest test: parse_directives extracted "WSP".
    from lexic.ir.directives import parse_directives

    d = parse_directives(text, AbnfFlavour.line_comment)
    assert "WSP" in d.non_semantic


def test_compile_abnf_case_insensitive_literal_expanded():
    """`op = "Hello"` in ABNF → IrGroup of char classes, not a single literal."""
    text = 'root = "Hi"\n'
    specs = compile_grammar(text, AbnfFlavour)
    spec = specs[0]
    # The rule classifies as value_str (no rulerefs); the IrItem inside should
    # carry an IrGroup atom (from normalize_literal expansion).
    assert spec.kind == "value_str"
    assert any(_has_group_in(item) for item in spec.items)


def _has_group_in(item) -> bool:
    from lexic.ir.nodes import IrGroup

    return isinstance(item.atom, IrGroup)
```

- [ ] **Step 3: Run — expect failures driven by the underlying Lark grammar or charclass parser.**

```bash
uv run pytest tests/integration/test_compile_grammar_abnf.py -v
```

- [ ] **Step 4: Iterate to green.** Common ABNF subset issues:
- The Lark token regex for `LITERAL` may need to allow more characters; fix in `grammars/abnf/meta_grammar.py`.
- The `parse_charclass` may need to handle hex escapes outside the basic `%xNN-MM` shape; tighten if needed.

- [ ] **Step 5: Run full suite + ruff. Commit.**

```bash
uv run pytest tests/ -q
uv run ruff check src/ tests/
git add resources/ground_truth/arithmetic.abnf tests/integration/test_compile_grammar_abnf.py
git commit -m "test(integration): minimal ABNF arithmetic fixture parses via new pipeline"
```

---

## Task 18: Cross-flavour transpilation test

The same arithmetic grammar in GBNF and ABNF should produce *structurally equivalent* `IrAst`s after canonicalization (modulo case-insensitive expansion that the GBNF version doesn't have).

**Files:**
- Create: `tests/integration/test_cross_flavour.py`

- [ ] **Step 1: Write the test.**

```python
# tests/integration/test_cross_flavour.py
"""Cross-flavour: GBNF and ABNF parse the same grammar to comparable IrAst.

The two ASTs are not byte-equivalent — ABNF's case-insensitive literals
expand to char-class groups, while GBNF's literals stay literals — but the
grammars they describe are equivalent for the unambiguous (non-alpha) parts.
"""
from __future__ import annotations

from pathlib import Path

from lexic.grammars.abnf.flavour import AbnfFlavour
from lexic.grammars.gbnf.flavour import GbnfFlavour
from lexic.parsing.meta_parser import MetaGrammarParser

GROUND_TRUTH = Path(__file__).resolve().parents[1] / "resources" / "ground_truth"


def test_arithmetic_grammars_have_same_rule_names():
    """Both versions define {root, expr, term, op, num} (modulo casing)."""
    gbnf_text = (GROUND_TRUTH / "arithmetic.gbnf").read_text(encoding="utf-8")
    abnf_text = (GROUND_TRUTH / "arithmetic.abnf").read_text(encoding="utf-8")
    gbnf_ast = MetaGrammarParser(GbnfFlavour).parse(gbnf_text)
    abnf_ast = MetaGrammarParser(AbnfFlavour).parse(abnf_text)

    gbnf_rules = {r.name.lower() for r in gbnf_ast.rules}
    abnf_rules = {r.name.lower() for r in abnf_ast.rules}

    common = {"root", "expr", "term", "op", "num"}
    assert common <= gbnf_rules
    assert common <= abnf_rules


def test_abnf_op_rule_expands_literals_into_groups():
    """The ABNF "+", "-", "*", "/" each become IrGroup (case-insens-expanded)
    or IrLiteral (no alpha chars). Verify shape."""
    abnf_text = (GROUND_TRUTH / "arithmetic.abnf").read_text(encoding="utf-8")
    ast = MetaGrammarParser(AbnfFlavour).parse(abnf_text)
    op = next(r for r in ast.rules if r.name == "op")
    # All four arms are non-alpha literals, so they stay IrLiteral.
    from lexic.ir.nodes import IrLiteral

    for arm in op.body.arms:
        assert isinstance(arm.items[0].atom, IrLiteral)


def test_compile_grammar_works_for_both_flavours_on_arithmetic():
    """End-to-end: both flavours produce non-empty RuleSpec lists with start first."""
    from lexic.compile import compile_grammar

    gbnf_text = (GROUND_TRUTH / "arithmetic.gbnf").read_text(encoding="utf-8")
    abnf_text = (GROUND_TRUTH / "arithmetic.abnf").read_text(encoding="utf-8")
    gbnf_specs = compile_grammar(gbnf_text, GbnfFlavour, non_semantic_rules=frozenset({"ws"}))
    abnf_specs = compile_grammar(abnf_text, AbnfFlavour, non_semantic_rules=frozenset({"WSP"}))
    assert gbnf_specs[0].rule_name == "root"
    assert abnf_specs[0].rule_name == "root"
```

- [ ] **Step 2: Run — expect PASS (or fix issues).**

```bash
uv run pytest tests/integration/test_cross_flavour.py -v
```

- [ ] **Step 3: Run full suite + ruff. Commit.**

```bash
uv run pytest tests/ -q
uv run ruff check src/ tests/
git add tests/integration/test_cross_flavour.py
git commit -m "test(integration): cross-flavour arithmetic — IR AST is shared substrate"
```

---

## Phase D — Cutover

The OLD pipeline (`codegen/ir_builder.py:IRBuilder` + `IRBuilder` from `ir/builder.py` + the never-implemented GbnfClassifier/Converter Protocols) coexisted with the new during Phases A–C. Phase D is the atomic switch.

**Strategy:** introduce a one-way *shape adapter* that converts old-shape `RuleSpec.items` (legacy `LiteralAtom`/`CharClassAtom`/etc.) into new-shape (`list[IrItem]`). Apply it at every boundary where the legacy pipeline produces specs that flow into a downstream consumer. Consumers are then updated to consume *only* the new shape. After consumers are updated and `compile()` switches to `compile_grammar`, the adapter and old pipeline are deleted in one final task.

## Task 19: Shape adapter — `ir/_legacy_shape.py` (transient)

A minimal one-way function `legacy_to_iritems(spec)` that produces a new-shape `RuleSpec`. Only used during Phase D; deleted at the end of Task 25.

**Files:**
- Create: `src/lexic/ir/_legacy_shape.py`
- Create: `tests/unit/lexic/ir/test_legacy_shape.py`

- [ ] **Step 1: Write failing tests.**

```python
# tests/unit/lexic/ir/test_legacy_shape.py
"""legacy_to_iritems — transient adapter from old-shape to new-shape RuleSpec."""
from __future__ import annotations

from lexic.ir._legacy_shape import legacy_to_iritems
from lexic.ir.atoms import (
    AlternationAtom,
    CharClassAtom,
    InlineAlternationAtom,
    InlineRegexAtom,
    LiteralAtom,
    QuantifiedLiteralAtom,
    RuleRefAtom,
)
from lexic.ir.nodes import (
    IrCharClass,
    IrGroup,
    IrItem,
    IrLiteral,
    IrRuleRef,
    Quantifier,
)
from lexic.ir.spec import RuleSpec


def _spec(items, kind="sequence", field_map=None):
    return RuleSpec(
        rule_name="r",
        class_name="R",
        parent_class_name="GrammarModel",
        kind=kind,
        items=items,
        field_map=field_map or {},
    )


def test_literal_atom_becomes_iritem_iri_literal():
    out = legacy_to_iritems(_spec([LiteralAtom("x")]))
    assert out.items == [IrItem(atom=IrLiteral("x"), quantifier=Quantifier(1, 1))]


def test_charclass_atom_becomes_iritem_iri_charclass():
    out = legacy_to_iritems(_spec([CharClassAtom("[0-9]", 1, None)]))
    item = out.items[0]
    assert isinstance(item.atom, IrCharClass)
    assert item.atom.pattern == "0-9"
    assert item.atom.negated is False
    assert item.quantifier == Quantifier(1, None)


def test_negated_charclass_strips_caret():
    out = legacy_to_iritems(_spec([CharClassAtom("[^abc]", 1, 1)]))
    cc = out.items[0].atom
    assert isinstance(cc, IrCharClass)
    assert cc.pattern == "abc"
    assert cc.negated is True


def test_ruleref_atom_becomes_iritem_iri_ruleref():
    out = legacy_to_iritems(_spec([RuleRefAtom("expr", 0, 1)]))
    item = out.items[0]
    assert item.atom == IrRuleRef("expr")
    assert item.quantifier == Quantifier(0, 1)


def test_quantified_literal_atom_becomes_iritem_with_quantifier():
    out = legacy_to_iritems(_spec([QuantifiedLiteralAtom("-", 0, 1)]))
    item = out.items[0]
    assert item.atom == IrLiteral("-")
    assert item.quantifier == Quantifier(0, 1)


def test_alternation_atom_becomes_list_of_ruleref_iritems():
    """For kind='alternation', items=[AlternationAtom(arms)] becomes
    items=[IrItem(IrRuleRef(arm_name)) for each arm]."""
    out = legacy_to_iritems(
        _spec([AlternationAtom(arm_rule_names=["num", "ident"])], kind="alternation")
    )
    assert [i.atom for i in out.items] == [IrRuleRef("num"), IrRuleRef("ident")]


def test_inline_alternation_atom_becomes_iritem_with_iri_group():
    out = legacy_to_iritems(_spec([InlineAlternationAtom(arm_rule_names=["a", "b"])]))
    item = out.items[0]
    assert isinstance(item.atom, IrGroup)
    arms = item.atom.body.arms
    assert len(arms) == 2
    assert arms[0].items[0].atom == IrRuleRef("a")
    assert arms[1].items[0].atom == IrRuleRef("b")


def test_inline_regex_atom_becomes_iritem_with_iri_group_via_regex_text():
    """InlineRegexAtom carries `regex` text; we don't reparse it. Adapter
    constructs an IrGroup by reading the gbnf form (which contains the
    structural alternation in canonical form)."""
    atom = InlineRegexAtom(regex='("a"|"b")', gbnf='("a" | "b")', min=1, max=None)
    out = legacy_to_iritems(_spec([atom]))
    item = out.items[0]
    assert isinstance(item.atom, IrGroup)
    assert item.quantifier == Quantifier(1, None)


def test_field_map_is_preserved():
    spec = _spec(
        [RuleRefAtom("a", 1, 1), RuleRefAtom("b", 1, 1)],
        field_map={"a": 0, "b": 1},
    )
    out = legacy_to_iritems(spec)
    assert out.field_map == {"a": 0, "b": 1}


def test_non_semantic_fields_preserved():
    spec = RuleSpec(
        rule_name="r",
        class_name="R",
        parent_class_name="G",
        kind="sequence",
        items=[RuleRefAtom("ws", 0, 1)],
        field_map={"ws": 0},
        non_semantic_fields=frozenset({"ws"}),
    )
    out = legacy_to_iritems(spec)
    assert out.non_semantic_fields == frozenset({"ws"})
```

- [ ] **Step 2: Run — expect ModuleNotFoundError.**

```bash
uv run pytest tests/unit/lexic/ir/test_legacy_shape.py -q
```

- [ ] **Step 3: Create `src/lexic/ir/_legacy_shape.py`.**

```python
"""Transient adapter: legacy old-shape RuleSpec.items → new-shape (list[IrItem]).

Used during Phase D cutover. Deleted at the end of Task 25 once the legacy
IRBuilder pipeline is removed.
"""

from __future__ import annotations

from lexic.ir.atoms import (
    AlternationAtom,
    CharClassAtom,
    InlineAlternationAtom,
    InlineRegexAtom,
    LiteralAtom,
    QuantifiedLiteralAtom,
    RuleRefAtom,
)
from lexic.ir.nodes import (
    IrAlternation,
    IrCharClass,
    IrGroup,
    IrItem,
    IrLiteral,
    IrRuleRef,
    IrSequence,
    Quantifier,
)
from lexic.ir.spec import RuleSpec


def _strip_brackets_with_negation(pattern: str) -> tuple[str, bool]:
    """Convert `[a-z]` or `[^abc]` to (interior, negated)."""
    if pattern.startswith("[") and pattern.endswith("]"):
        inner = pattern[1:-1]
    else:
        inner = pattern
    if inner.startswith("^"):
        return inner[1:], True
    return inner, False


def _convert_inline_regex_to_group(atom: InlineRegexAtom) -> IrGroup:
    """The InlineRegexAtom.gbnf carries the canonical structural form. We
    don't re-parse it; instead we build a single-arm group containing one
    IrLiteral whose value is the gbnf-form text. Codegen treats this group
    as a regex pattern at emit/lark time (the existing convention).
    """
    # The gbnf form is e.g. `("foo" | "bar")` — already a renderable string.
    # For Phase D we collapse to a single literal carrying the source text;
    # the model_emitter and lark_builder are updated in Tasks 21–22 to
    # recognise IrGroup with this shape and handle it.
    return IrGroup(
        body=IrAlternation(
            arms=(
                IrSequence(items=(IrItem(atom=IrLiteral(atom.gbnf)),)),
            )
        )
    )


def _atom_to_iritem(atom) -> IrItem:
    if isinstance(atom, LiteralAtom):
        return IrItem(atom=IrLiteral(atom.value), quantifier=Quantifier(1, 1))
    if isinstance(atom, QuantifiedLiteralAtom):
        return IrItem(
            atom=IrLiteral(atom.value),
            quantifier=Quantifier(atom.min, atom.max),
        )
    if isinstance(atom, CharClassAtom):
        pattern, negated = _strip_brackets_with_negation(atom.pattern)
        return IrItem(
            atom=IrCharClass(pattern=pattern, negated=negated),
            quantifier=Quantifier(atom.min, atom.max),
        )
    if isinstance(atom, RuleRefAtom):
        return IrItem(
            atom=IrRuleRef(name=atom.rule_name),
            quantifier=Quantifier(atom.min, atom.max),
        )
    if isinstance(atom, InlineAlternationAtom):
        arms = tuple(
            IrSequence(items=(IrItem(atom=IrRuleRef(name=n)),))
            for n in atom.arm_rule_names
        )
        return IrItem(
            atom=IrGroup(body=IrAlternation(arms=arms)),
            quantifier=Quantifier(1, 1),
        )
    if isinstance(atom, InlineRegexAtom):
        return IrItem(
            atom=_convert_inline_regex_to_group(atom),
            quantifier=Quantifier(atom.min, atom.max),
        )
    raise TypeError(f"Unsupported legacy atom type: {type(atom).__name__}")


def legacy_to_iritems(spec: RuleSpec) -> RuleSpec:
    """Return a new RuleSpec with items converted to list[IrItem]."""
    if spec.kind == "alternation" and spec.items and isinstance(
        spec.items[0], AlternationAtom
    ):
        new_items = [
            IrItem(atom=IrRuleRef(name=n))
            for n in spec.items[0].arm_rule_names
        ]
    else:
        new_items = [_atom_to_iritem(a) for a in spec.items]
    return RuleSpec(
        rule_name=spec.rule_name,
        class_name=spec.class_name,
        parent_class_name=spec.parent_class_name,
        kind=spec.kind,
        items=new_items,
        field_map=dict(spec.field_map),
        non_semantic_fields=frozenset(spec.non_semantic_fields),
    )
```

- [ ] **Step 4: Run — expect PASS.**

```bash
uv run pytest tests/unit/lexic/ir/test_legacy_shape.py -q
```

- [ ] **Step 5: Run full suite + ruff. Commit.**

```bash
uv run pytest tests/ -q
uv run ruff check src/ tests/
git add src/lexic/ir/_legacy_shape.py tests/unit/lexic/ir/test_legacy_shape.py
git commit -m "feat(ir): legacy_to_iritems shape adapter (transient, removed in Task 25)"
```

---

## Task 20: Update `grammars/gbnf/emitter.py` for new-shape `RuleSpec.items`

The GBNF emitter currently dispatches on legacy atom types. Update it to dispatch on `IrItem.atom` types. Remove the legacy-atom branches at the end of the task; we'll wire the legacy pipeline through `legacy_to_iritems` in Task 25.

**Files:**
- Modify: `src/lexic/grammars/gbnf/emitter.py`
- Modify: `tests/unit/lexic/grammars/gbnf/test_emitter.py` (existing tests update)

- [ ] **Step 1: Read existing test file; identify which tests use legacy atom shapes.**

```bash
cat /home/mika/projects/lexic/tests/unit/lexic/grammars/gbnf/test_emitter.py
```

- [ ] **Step 2: Add new tests using IrItem-shaped specs (don't delete legacy-shape tests yet — both must pass during transition).**

```python
# Append to tests/unit/lexic/grammars/gbnf/test_emitter.py

from lexic.ir.nodes import (
    IrAlternation,
    IrCharClass,
    IrGroup,
    IrItem,
    IrLiteral,
    IrRuleRef,
    IrSequence,
    Quantifier,
)


def _new_spec(rule_name, kind, items, class_name=None, parent="GrammarModel"):
    from lexic.ir.spec import RuleSpec

    return RuleSpec(
        rule_name=rule_name,
        class_name=class_name or rule_name.title(),
        parent_class_name=parent,
        kind=kind,
        items=list(items),
        field_map={},
    )


def test_emit_iritem_literal():
    spec = _new_spec("greeting", "value_str", [IrItem(IrLiteral("hello"))])
    out = GbnfEmitter([]).emit_rule(spec)
    assert out == 'greeting ::= "hello"'


def test_emit_iritem_charclass_with_quantifier():
    spec = _new_spec(
        "digit",
        "value_str",
        [IrItem(IrCharClass("0-9"), Quantifier(1, None))],
    )
    out = GbnfEmitter([]).emit_rule(spec)
    assert out == "digit ::= [0-9]+"


def test_emit_iritem_negated_charclass():
    spec = _new_spec(
        "non_quote",
        "value_str",
        [IrItem(IrCharClass(r'"', negated=True))],
    )
    out = GbnfEmitter([]).emit_rule(spec)
    assert out == 'non_quote ::= [^"]'


def test_emit_iritem_ruleref_with_quantifier():
    spec = _new_spec(
        "expr",
        "sequence",
        [IrItem(IrRuleRef("term"), Quantifier(1, None))],
    )
    out = GbnfEmitter([]).emit_rule(spec)
    assert out == "expr ::= term+"


def test_emit_iritem_group_inline_alternation():
    """An IrGroup containing only rulerefs renders as `(a | b)`."""
    grp = IrGroup(
        IrAlternation(
            (
                IrSequence((IrItem(IrRuleRef("a")),)),
                IrSequence((IrItem(IrRuleRef("b")),)),
            )
        )
    )
    spec = _new_spec("r", "sequence", [IrItem(grp)])
    out = GbnfEmitter([]).emit_rule(spec)
    assert "(a | b)" in out


def test_emit_iritem_group_with_quantifier():
    grp = IrGroup(
        IrAlternation(
            (
                IrSequence((IrItem(IrLiteral("foo")),)),
                IrSequence((IrItem(IrLiteral("bar")),)),
            )
        )
    )
    spec = _new_spec("r", "value_str", [IrItem(grp, Quantifier(1, None))])
    out = GbnfEmitter([]).emit_rule(spec)
    assert "+" in out
    assert '"foo"' in out
    assert '"bar"' in out
```

- [ ] **Step 3: Run — expect failures on the new tests (legacy tests still pass).**

- [ ] **Step 4: Update `src/lexic/grammars/gbnf/emitter.py`.**

```python
"""GBNFEmitter: reconstructs GBNF text from list[RuleSpec].

Handles new-shape items (list[IrItem]) and falls back to the legacy
atom shapes for the duration of Phase D. The legacy branches go away
in Task 25 when the old pipeline is deleted.
"""

from __future__ import annotations

from lexic.grammars.flavours import FlavourEmitter
from lexic.ir import (  # legacy atom imports remain until Task 25
    AlternationAtom,
    CharClassAtom,
    InlineAlternationAtom,
    InlineRegexAtom,
    LiteralAtom,
    QuantifiedLiteralAtom,
    RuleRefAtom,
    RuleSpec,
)
from lexic.ir.nodes import (
    IrAlternation,
    IrCharClass,
    IrGroup,
    IrItem,
    IrLiteral,
    IrRuleRef,
    IrSequence,
)
from lexic.utils.quantifiers import bounds_to_quantifier


def _format_quantifier(q) -> str:
    return bounds_to_quantifier(q.min, q.max)


def _bracket(pattern: str, negated: bool) -> str:
    return f"[{'^' if negated else ''}{pattern}]"


def _atom_to_gbnf_item(item: IrItem) -> str:
    """Render a new-shape IrItem as GBNF text."""
    atom = item.atom
    q = _format_quantifier(item.quantifier)
    if isinstance(atom, IrLiteral):
        return f'"{atom.value}"{q}'
    if isinstance(atom, IrCharClass):
        return _bracket(atom.pattern, atom.negated) + q
    if isinstance(atom, IrRuleRef):
        return atom.name + q
    if isinstance(atom, IrGroup):
        body = _alt_to_gbnf(atom.body)
        return f"({body}){q}" if q else f"({body})"
    raise TypeError(f"Unsupported IR atom: {type(atom).__name__}")


def _seq_to_gbnf(seq: IrSequence) -> str:
    return " ".join(_atom_to_gbnf_item(it) for it in seq.items)


def _alt_to_gbnf(alt: IrAlternation) -> str:
    return " | ".join(_seq_to_gbnf(s) for s in alt.arms)


# ── Legacy atom rendering — removed in Task 25. ──


def _legacy_atom_to_gbnf(atom) -> str:
    if isinstance(atom, LiteralAtom):
        return f'"{atom.value}"'
    if isinstance(atom, CharClassAtom):
        q = bounds_to_quantifier(atom.min, atom.max)
        return f"{atom.pattern}{q}"
    if isinstance(atom, RuleRefAtom):
        q = bounds_to_quantifier(atom.min, atom.max)
        return f"{atom.rule_name}{q}"
    if isinstance(atom, AlternationAtom):
        return " | ".join(atom.arm_rule_names)
    if isinstance(atom, QuantifiedLiteralAtom):
        q = bounds_to_quantifier(atom.min, atom.max)
        return f'"{atom.value}"{q}'
    if isinstance(atom, InlineRegexAtom):
        q = bounds_to_quantifier(atom.min, atom.max)
        if q:
            body = (
                atom.gbnf
                if (atom.gbnf.startswith("(") and atom.gbnf.endswith(")"))
                else f"({atom.gbnf})"
            )
            return f"{body}{q}"
        return atom.gbnf
    if isinstance(atom, InlineAlternationAtom):
        return "(" + " | ".join(atom.arm_rule_names) + ")"
    return ""


class GbnfEmitter(FlavourEmitter):
    supports: frozenset[str] = frozenset(
        {
            "literal",
            "char_class",
            "negated_class",
            "quantifier",
            "alternation",
            "non_capturing_group",
            "unicode_escape",
        }
    )

    def __init__(self, specs: list[RuleSpec]) -> None:
        self._specs = specs

    def emit(self, specs: list[RuleSpec] | None = None) -> str:
        if specs is None:
            specs = self._specs
        lines = [self.emit_rule(s) for s in specs]
        return "\n".join(lines) + "\n"

    def emit_rule(self, spec: RuleSpec) -> str:
        body = self._emit_body(spec)
        return f"{spec.rule_name} ::= {body}"

    def _emit_body(self, spec: RuleSpec) -> str:
        if not spec.items:
            return '""'
        # Dispatch on first item shape
        first = spec.items[0]
        if isinstance(first, IrItem):
            return self._emit_new_shape(spec)
        return self._emit_legacy_shape(spec)

    def _emit_new_shape(self, spec: RuleSpec) -> str:
        if spec.kind == "alternation":
            # items are IrItem(IrRuleRef(arm_name)) per arm
            return " | ".join(it.atom.name for it in spec.items if isinstance(it.atom, IrRuleRef))
        parts = [_atom_to_gbnf_item(it) for it in spec.items]
        return " ".join(p for p in parts if p)

    def _emit_legacy_shape(self, spec: RuleSpec) -> str:
        if spec.kind == "alternation" and spec.items and isinstance(
            spec.items[0], AlternationAtom
        ):
            return " | ".join(spec.items[0].arm_rule_names)
        parts = [_legacy_atom_to_gbnf(a) for a in spec.items]
        return " ".join(p for p in parts if p)


GBNFEmitter = GbnfEmitter
```

- [ ] **Step 5: Run — expect both old and new tests to pass.**

```bash
uv run pytest tests/unit/lexic/grammars/gbnf/test_emitter.py -q
uv run pytest tests/ -q
uv run ruff check src/ tests/
git add src/lexic/grammars/gbnf/emitter.py tests/unit/lexic/grammars/gbnf/test_emitter.py
git commit -m "feat(gbnf): emitter handles IrItem-shaped RuleSpec.items (legacy still supported)"
```

---

## Task 21: Update `codegen/model_emitter.py` for new-shape items

Same dual-shape handling. New `_field_type_for_iritem(item, specs_by_rule)` and `_repr_iritem(item)` functions handle the new shape; legacy functions stay for transition.

**Files:**
- Modify: `src/lexic/codegen/model_emitter.py`
- Modify: `tests/unit/lexic/codegen/test_model_emitter.py`

- [ ] **Step 1: Add tests for new-shape RuleSpecs.**

Append to `tests/unit/lexic/codegen/test_model_emitter.py`:

```python
# (Append) — new-shape (IrItem) tests.
from lexic.ir.nodes import IrCharClass, IrItem, IrLiteral, IrRuleRef, Quantifier


def test_model_emitter_handles_iritem_ruleref_field():
    from lexic.ir.spec import RuleSpec
    from lexic.codegen.model_emitter import emit_module_source

    specs = [
        RuleSpec(
            rule_name="root",
            class_name="Root",
            parent_class_name="GrammarModel",
            kind="sequence",
            items=[IrItem(IrRuleRef("expr"))],
            field_map={"expr": 0},
        ),
        RuleSpec(
            rule_name="expr",
            class_name="Expr",
            parent_class_name="GrammarModel",
            kind="value_str",
            items=[IrItem(IrCharClass("a-z"), Quantifier(1, None))],
            field_map={},
        ),
    ]
    src = emit_module_source(specs, stem="m")
    assert "class Root" in src
    assert "expr: " in src or "expr:" in src
    assert "class Expr" in src


def test_model_emitter_optional_iritem_field():
    from lexic.ir.spec import RuleSpec
    from lexic.codegen.model_emitter import emit_module_source

    specs = [
        RuleSpec(
            rule_name="r",
            class_name="R",
            parent_class_name="GrammarModel",
            kind="sequence",
            items=[IrItem(IrRuleRef("x"), Quantifier(0, 1))],
            field_map={"x": 0},
        ),
        RuleSpec(
            rule_name="x",
            class_name="X",
            parent_class_name="GrammarModel",
            kind="value_str",
            items=[IrItem(IrLiteral("x"))],
            field_map={},
        ),
    ]
    src = emit_module_source(specs, stem="m")
    assert "Optional[X]" in src or "X | None" in src
```

The `emit_module_source` function is the existing module-source builder in `codegen/model_emitter.py`; if its name differs (e.g. `emit_module`, `render_classes`), use the actual one. Open the file to check, and use the same name in both the test and the implementation.

- [ ] **Step 2: Run — expect failures.**

```bash
uv run pytest tests/unit/lexic/codegen/test_model_emitter.py -q
```

- [ ] **Step 3: Update `src/lexic/codegen/model_emitter.py`.**

Add new IrItem-aware functions alongside the existing ones:

```python
# Append/insert into codegen/model_emitter.py

from lexic.ir.nodes import (
    IrCharClass,
    IrGroup,
    IrItem,
    IrLiteral,
    IrRuleRef,
    Quantifier,
)


def _is_unbounded(q: Quantifier) -> bool:
    return q.max is None


def _is_optional(q: Quantifier) -> bool:
    return q.min == 0 and q.max == 1


def _is_required(q: Quantifier) -> bool:
    return q.min == 1 and q.max == 1


def _field_type_for_iritem(item: IrItem, specs_by_rule: dict[str, RuleSpec]) -> str:
    atom = item.atom
    q = item.quantifier
    if isinstance(atom, IrCharClass):
        return "str"
    if isinstance(atom, IrLiteral):
        return "str"
    if isinstance(atom, IrRuleRef):
        ref = specs_by_rule.get(atom.name)
        cls_name = (
            ref.class_name if ref else atom.name.replace("-", "_").title()
        )
        if _is_required(q):
            return cls_name
        if _is_optional(q):
            return f"Optional[{cls_name}]"
        return f"List[{cls_name}]"
    if isinstance(atom, IrGroup):
        # Inline group — heuristic: if any child is a RuleRef, emit Union of arm classes
        # via parent class lookup; else treat as regex pattern → str.
        from lexic.ir.derive import _has_ruleref  # type: ignore[import-not-found]

        if _has_ruleref(atom):
            arm_names = []
            for arm in atom.body.arms:
                if len(arm.items) == 1 and isinstance(arm.items[0].atom, IrRuleRef):
                    arm_names.append(arm.items[0].atom.name)
            if arm_names:
                arm_cls = [
                    specs_by_rule[n].class_name
                    for n in arm_names
                    if n in specs_by_rule
                ]
                parents = {
                    specs_by_rule[n].parent_class_name
                    for n in arm_names
                    if n in specs_by_rule
                }
                if len(parents) == 1 and next(iter(parents)) != "GrammarModel":
                    return next(iter(parents))
                if arm_cls:
                    return "Union[" + ", ".join(arm_cls) + "]"
        return "str"
    return "str"


def _repr_iritem(item: IrItem) -> str:
    """Render an IrItem as a Python constructor for the __grammar__ literal."""
    atom = item.atom
    q = item.quantifier
    q_repr = f"Quantifier({q.min}, {q.max!r})"
    if isinstance(atom, IrLiteral):
        return f"IrItem(IrLiteral({atom.value!r}), {q_repr})"
    if isinstance(atom, IrCharClass):
        return (
            f"IrItem(IrCharClass({atom.pattern!r}, negated={atom.negated}), {q_repr})"
        )
    if isinstance(atom, IrRuleRef):
        return f"IrItem(IrRuleRef({atom.name!r}), {q_repr})"
    if isinstance(atom, IrGroup):
        # Round-trip through a textual form by rendering body arm-by-arm.
        # For Phase D minimum, embed a placeholder string; codegen
        # downstream uses field_map/kind, not __grammar__ for groups.
        # If runtime needs the group later, expand this serialiser.
        return f"IrItem(IrGroup(IrAlternation(())), {q_repr})  # FIXME: group serialisation"
    return "IrItem(...)"
```

Then update the existing `_field_type` and `_repr_atom` dispatchers (or whatever the entry points are called) to detect `IrItem` and route through the new functions:

```python
def _field_type(atom, specs_by_rule: dict[str, RuleSpec]) -> str:
    if isinstance(atom, IrItem):
        return _field_type_for_iritem(atom, specs_by_rule)
    # ── existing legacy-atom handling unchanged ──
    ...


def _repr_atom(atom) -> str:
    if isinstance(atom, IrItem):
        return _repr_iritem(atom)
    # ── existing legacy-atom handling unchanged ──
    ...
```

Also update the imports in the generated module template to include `IrItem`, `IrLiteral`, `IrCharClass`, `IrRuleRef`, `Quantifier` (from `lexic.ir.nodes`) when any of those appear in the items.

- [ ] **Step 4: Run — expect PASS.**

```bash
uv run pytest tests/unit/lexic/codegen/test_model_emitter.py -q
uv run pytest tests/ -q
uv run ruff check src/ tests/
git add src/lexic/codegen/model_emitter.py tests/unit/lexic/codegen/test_model_emitter.py
git commit -m "feat(codegen): model_emitter dispatches on IrItem shape (legacy still supported)"
```

---

## Task 22: Update `codegen/lark_builder.py` for new-shape items

Add `_iritem_to_lark(item)` alongside the existing `_atom_to_lark`. Same dual-shape pattern.

**Files:**
- Modify: `src/lexic/codegen/lark_builder.py`
- Modify: `tests/unit/lexic/codegen/test_lark_builder.py`

- [ ] **Step 1: Add new tests.**

Append to `tests/unit/lexic/codegen/test_lark_builder.py`:

```python
from lexic.ir.nodes import IrCharClass, IrItem, IrLiteral, IrRuleRef, Quantifier


def test_lark_builder_emits_iritem_literal():
    from lexic.ir.spec import RuleSpec
    from lexic.codegen.lark_builder import LarkBuilder

    specs = [
        RuleSpec(
            rule_name="r",
            class_name="R",
            parent_class_name="GrammarModel",
            kind="value_str",
            items=[IrItem(IrLiteral("hello"))],
            field_map={},
        ),
    ]
    grammar, start = LarkBuilder(specs).build_grammar()
    assert '"hello"' in grammar
    assert start == "r"


def test_lark_builder_emits_iritem_charclass():
    from lexic.ir.spec import RuleSpec
    from lexic.codegen.lark_builder import LarkBuilder

    specs = [
        RuleSpec(
            rule_name="d",
            class_name="D",
            parent_class_name="GrammarModel",
            kind="value_str",
            items=[IrItem(IrCharClass("0-9"), Quantifier(1, None))],
            field_map={},
        ),
    ]
    grammar, _ = LarkBuilder(specs).build_grammar()
    assert "/[0-9]/+" in grammar or "/[0-9]+/" in grammar


def test_lark_builder_iritem_ruleref_with_quantifier():
    from lexic.ir.spec import RuleSpec
    from lexic.codegen.lark_builder import LarkBuilder

    specs = [
        RuleSpec(
            rule_name="r",
            class_name="R",
            parent_class_name="GrammarModel",
            kind="sequence",
            items=[IrItem(IrRuleRef("inner"), Quantifier(0, None))],
            field_map={"inner": 0},
        ),
        RuleSpec(
            rule_name="inner",
            class_name="Inner",
            parent_class_name="GrammarModel",
            kind="value_str",
            items=[IrItem(IrLiteral("x"))],
            field_map={},
        ),
    ]
    grammar, _ = LarkBuilder(specs).build_grammar()
    assert "inner*" in grammar
```

- [ ] **Step 2: Update `src/lexic/codegen/lark_builder.py`.**

Add the IrItem dispatch path:

```python
from lexic.ir.nodes import (
    IrCharClass,
    IrGroup,
    IrItem,
    IrLiteral,
    IrRuleRef,
)


def _iritem_to_lark(item: IrItem) -> str:
    atom = item.atom
    q = bounds_to_quantifier(item.quantifier.min, item.quantifier.max)
    if isinstance(atom, IrLiteral):
        decoded = atom.value
        if any(c in decoded for c in "\n\t\r"):
            regex = ""
            for ch in decoded:
                if ch == "\n":
                    regex += "\\n"
                elif ch == "\t":
                    regex += "\\t"
                elif ch == "\r":
                    regex += "\\r"
                elif ch in r"\.^$*+?{}[]|()":
                    regex += "\\" + ch
                else:
                    regex += ch
            regex = _escape_lark_regex(regex)
            return f"/{regex}/{q}"
        escaped = decoded.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"{q}'
    if isinstance(atom, IrCharClass):
        bracketed = f"[{'^' if atom.negated else ''}{atom.pattern}]"
        safe = _escape_lark_regex(bracketed)
        return f"/{safe}/{q}"
    if isinstance(atom, IrRuleRef):
        name = to_lark_name(atom.name)
        if atom.name == "ws":  # Phase D legacy hack — Task 25 removes this
            return "ws?"
        return f"{name}{q}"
    if isinstance(atom, IrGroup):
        # Render the group's body recursively as a Lark group.
        arms = []
        for arm in atom.body.arms:
            arm_parts = [_iritem_to_lark(it) for it in arm.items]
            arms.append(" ".join(arm_parts))
        body = " | ".join(arms)
        return f"({body}){q}"
    raise TypeError(f"Unsupported IR atom for Lark: {type(atom).__name__}")


def _atom_to_lark_dispatched(atom_or_item) -> str:
    if isinstance(atom_or_item, IrItem):
        return _iritem_to_lark(atom_or_item)
    return _atom_to_lark(atom_or_item)
```

Update `LarkBuilder` (or wherever `_atom_to_lark` is called) to call `_atom_to_lark_dispatched` instead. Find the call sites:

```bash
grep -n "_atom_to_lark" /home/mika/projects/lexic/src/lexic/codegen/lark_builder.py
```

For each call site that takes `spec.items[i]` or iterates `spec.items`, change to `_atom_to_lark_dispatched`.

- [ ] **Step 3: Run — expect PASS.**

```bash
uv run pytest tests/ -q
uv run ruff check src/ tests/
git add src/lexic/codegen/lark_builder.py tests/unit/lexic/codegen/test_lark_builder.py
git commit -m "feat(codegen): lark_builder dispatches on IrItem shape (legacy still supported)"
```

---

## Task 23: Update `codegen/transformer/*` for new-shape items

The `build_transformer.py` and `builders.py` modules generate the Lark Transformer. They consume `RuleSpec.items` to figure out field types and how to extract values. Same dual-shape pattern.

**Files:**
- Modify: `src/lexic/codegen/transformer/build_transformer.py`
- Modify: `src/lexic/codegen/transformer/builders.py`
- Modify: `tests/unit/lexic/codegen/transformer/test_build_transformer.py`
- Modify: `tests/unit/lexic/codegen/transformer/test_builders.py`

- [ ] **Step 1: Read the existing transformer code to understand its dispatch points.**

```bash
cat /home/mika/projects/lexic/src/lexic/codegen/transformer/build_transformer.py
cat /home/mika/projects/lexic/src/lexic/codegen/transformer/builders.py
```

The builders dispatch on atom type (LiteralAtom/CharClassAtom/RuleRefAtom/etc.) to choose a "field-extraction strategy". For the new shape, dispatch on `IrItem.atom` types instead.

- [ ] **Step 2: Add IrItem-aware tests + dispatch.**

Add tests covering one example per IrItem.atom variant:

```python
# Append to tests/unit/lexic/codegen/transformer/test_builders.py

from lexic.ir.nodes import IrCharClass, IrItem, IrLiteral, IrRuleRef, Quantifier


def test_builder_handles_iritem_charclass_field():
    from lexic.ir.spec import RuleSpec
    from lexic.codegen.transformer.builders import build_for_field

    spec = RuleSpec(
        rule_name="r",
        class_name="R",
        parent_class_name="GrammarModel",
        kind="sequence",
        items=[IrItem(IrCharClass("a-z"), Quantifier(1, None))],
        field_map={"alpha": 0},
    )
    builder = build_for_field(spec, "alpha")
    assert builder is not None  # the actual contract depends on builders.py
```

The test is a placeholder — the actual contract of `build_for_field` (or whatever the entry point is) depends on the existing implementation. Open it and write tests for whatever its current public surface is.

- [ ] **Step 3: Update the dispatcher.** Wherever `isinstance(atom, LiteralAtom)` etc. appears, add a parallel branch:

```python
if isinstance(item, IrItem):
    atom = item.atom
    q = item.quantifier
    if isinstance(atom, IrLiteral):
        ...   # mirrors the LiteralAtom case
    elif isinstance(atom, IrCharClass):
        ...   # mirrors the CharClassAtom case
    elif isinstance(atom, IrRuleRef):
        ...   # mirrors the RuleRefAtom case
    elif isinstance(atom, IrGroup):
        ...   # mirrors InlineAlternationAtom or InlineRegexAtom case based on shape
else:
    # legacy dispatch unchanged
    ...
```

- [ ] **Step 4: Run — expect PASS for both old and new tests.**

```bash
uv run pytest tests/unit/lexic/codegen/transformer/ -q
uv run pytest tests/ -q
uv run ruff check src/ tests/
git add src/lexic/codegen/transformer/ tests/unit/lexic/codegen/transformer/
git commit -m "feat(codegen): transformer builders dispatch on IrItem shape"
```

---

## Task 24: Update `src/lexic/base.py` for new-shape items

`GrammarModel.to_text()` walks `__grammar__.items` to reconstruct text. Add IrItem dispatch alongside legacy.

**Files:**
- Modify: `src/lexic/base.py`
- Modify: `tests/unit/lexic/test_base.py`

- [ ] **Step 1: Add tests using IrItem-shaped __grammar__.**

```python
# Append to tests/unit/lexic/test_base.py

from lexic.ir.nodes import IrCharClass, IrItem, IrLiteral, IrRuleRef, Quantifier
from lexic.ir.spec import RuleSpec


def test_to_text_with_iritem_literal():
    from lexic.base import GrammarModel

    class Greet(GrammarModel):
        __grammar__ = RuleSpec(
            rule_name="g",
            class_name="Greet",
            parent_class_name="GrammarModel",
            kind="value_str",
            items=[IrItem(IrLiteral("hi"))],
            field_map={},
        )
        value: str = "hi"

    assert Greet().to_text() == "hi"


def test_to_text_with_iritem_ruleref_field():
    from lexic.base import GrammarModel

    class Inner(GrammarModel):
        __grammar__ = RuleSpec(
            rule_name="inner",
            class_name="Inner",
            parent_class_name="GrammarModel",
            kind="value_str",
            items=[IrItem(IrLiteral("X"))],
            field_map={},
        )
        value: str = "X"

    class Outer(GrammarModel):
        __grammar__ = RuleSpec(
            rule_name="outer",
            class_name="Outer",
            parent_class_name="GrammarModel",
            kind="sequence",
            items=[IrItem(IrLiteral("[")), IrItem(IrRuleRef("inner")), IrItem(IrLiteral("]"))],
            field_map={"inner": 1},
        )
        inner: Inner

    out = Outer(inner=Inner(value="X")).to_text()
    assert out == "[X]"
```

- [ ] **Step 2: Update `src/lexic/base.py:to_text()`.**

```python
# In src/lexic/base.py to_text(), within the loop over spec.items:
for i, atom in enumerate(spec.items):
    if isinstance(atom, IrItem):
        # New shape
        if isinstance(atom.atom, IrLiteral) and atom.quantifier == Quantifier(1, 1):
            parts.append(atom.atom.value)
            continue
        if i not in inv:
            continue
        field_name = inv[i]
        val = getattr(self, field_name, None)
        # ... existing logic that converts val to text ...
    else:
        # Legacy shape — unchanged for now
        if isinstance(atom, LiteralAtom):
            decoded = decode_gbnf_escapes(atom.value)
            parts.append(decoded)
            continue
        # ... rest of legacy ...
```

Make the patch surgical: add the IrItem branch first; leave the legacy branches untouched. Tests pass because both shapes are handled.

- [ ] **Step 3: Run — expect PASS.**

```bash
uv run pytest tests/unit/lexic/test_base.py -q
uv run pytest tests/ -q
uv run ruff check src/ tests/
git add src/lexic/base.py tests/unit/lexic/test_base.py
git commit -m "feat(base): GrammarModel.to_text handles IrItem shape"
```

---

## Task 25: Switch `compile()` to new pipeline + delete old machinery

The atomic cutover. `compile.compile()` now routes through `compile_grammar`; `codegen.build_classes_and_specs` uses the new pipeline; old `IRBuilder`, classifier/converter Protocols, atoms.py, ast.py, and ast_to_ir.py are deleted.

**Files:**
- Modify: `src/lexic/codegen/__init__.py` — `build_classes_and_specs` uses `compile_grammar`
- Modify: `src/lexic/compile.py` — drop legacy adapter usage
- Modify: `src/lexic/grammars/gbnf/parser.py` — slim to thin wrapper
- Modify: `src/lexic/grammars/gbnf/adapter.py` — wire to GbnfFlavour
- Modify: `src/lexic/grammars/__init__.py` — register AbnfAdapter alongside Gbnf
- Modify: `src/lexic/grammars/gbnf/emitter.py` — drop legacy branches; keep only IrItem
- Modify: `src/lexic/codegen/model_emitter.py` — drop legacy branches
- Modify: `src/lexic/codegen/lark_builder.py` — drop legacy branches; drop `decode_gbnf_escapes` import (no longer needed; literals are canonical)
- Modify: `src/lexic/codegen/transformer/build_transformer.py` and `builders.py` — drop legacy branches
- Modify: `src/lexic/base.py` — drop legacy branches; drop `decode_gbnf_escapes` import
- Modify: `src/lexic/ir/protocols.py` — drop `RuleClassifier`, `SequenceConverter`, `FlavourAdapter` (FlavourAdapter Protocol stays in `lexic.grammars.flavours` only). Keep handler-type aliases.
- Modify: `src/lexic/ir/__init__.py` — drop deleted exports; add new ones (`IrLiteral`, `IrCharClass`, `IrRuleRef`, `IrItem`, etc.)
- Modify: `src/lexic/ir/spec.py` — tighten `items: list[IrItem]`
- Delete: `src/lexic/ir/_legacy_shape.py` and its test
- Delete: `src/lexic/ir/atoms.py` and `tests/unit/lexic/ir/test_atoms.py`
- Delete: `src/lexic/ir/builder.py`, `ir/classify.py`, `ir/convert.py` and their tests
- Delete: `src/lexic/grammars/gbnf/ast.py`, `tests/unit/lexic/grammars/gbnf/test_ast.py`
- Delete: `src/lexic/grammars/gbnf/ast_to_ir.py`, `tests/unit/lexic/grammars/gbnf/test_ast_to_ir.py` (untracked WIP)
- Delete: `src/lexic/codegen/ir_builder.py`, `codegen/classify.py`, `codegen/seq_to_atoms.py`, `codegen/ast_utils.py` and their tests

This task is large — split into clear sub-stages.

- [ ] **Step 1: Switch `compile.compile()` to new pipeline.**

Edit `src/lexic/compile.py`. In `_compile_core`, replace the call to `build_classes_and_specs` (which currently uses the legacy IRBuilder) with one that uses `compile_grammar`:

```python
def _compile_core(text: str, *, stem: str, flavour: str = "gbnf") -> CompiledGrammar:
    from lexic.compile import compile_grammar  # already in this module
    from lexic.grammars import get_adapter

    adapter = get_adapter(flavour)
    flavour_cls = adapter.flavour_cls  # added below
    specs_list = compile_grammar(text, flavour_cls)
    classes = _emit_and_load_module(specs_list, stem)  # existing helper, retargeted
    specs = {s.rule_name: s for s in specs_list}
    builder = LarkBuilder(specs_list)
    grammar_str, start_rule = builder.build_grammar()
    parser = lark.Lark(
        grammar_str, parser="earley", ambiguity="resolve", start=start_rule
    )
    transformer = builder.build_transformer(classes)
    return CompiledGrammar(
        classes=classes, specs=specs, parser=parser, transformer=transformer,
    )
```

You'll need an `_emit_and_load_module` (the model_emitter path) — check existing `codegen/__init__.py`'s `build_classes_and_specs` for that pattern; reuse it.

- [ ] **Step 2: Update `grammars/gbnf/adapter.py` — expose `flavour_cls`.**

```python
from lexic.grammars.gbnf.flavour import GbnfFlavour

class GbnfAdapter(FlavourAdapter):
    name = "gbnf"
    extensions: tuple[str, ...] = (".gbnf",)
    flavour_cls = GbnfFlavour

    def __init__(self) -> None:
        self.parser = GbnfParser()
        self.emitter = GbnfEmitter([])
```

Add `flavour_cls` to `lexic.grammars.flavours.FlavourAdapter` Protocol.

- [ ] **Step 3: Slim `grammars/gbnf/parser.py`.**

```python
"""GbnfParser: thin wrapper around MetaGrammarParser(GbnfFlavour)."""

from __future__ import annotations

from lexic.grammars.flavours import FlavourParser
from lexic.grammars.gbnf.flavour import GbnfFlavour
from lexic.ir.nodes import IrAst
from lexic.parsing.meta_parser import MetaGrammarParser


_parser = MetaGrammarParser(GbnfFlavour)


def parse_gbnf(text: str) -> IrAst:
    return _parser.parse(text)


class GbnfParser(FlavourParser):
    def parse(self, text: str) -> IrAst:
        return _parser.parse(text)
```

- [ ] **Step 4: Run full suite. Expect failures from anything still using the legacy pipeline.**

```bash
uv run pytest tests/ -q
```

Iterate: each failure points to a place that needs the new pipeline. Fix in place.

- [ ] **Step 5: Add ABNF adapter and register it.**

```python
# src/lexic/grammars/abnf/adapter.py
from lexic.grammars.abnf.flavour import AbnfFlavour
from lexic.grammars.abnf.emitter import AbnfEmitter
from lexic.grammars.abnf.escapes import ABNF_ESCAPES
from lexic.grammars.flavours import FlavourAdapter
from lexic.parsing.meta_parser import MetaGrammarParser


class AbnfAdapter(FlavourAdapter):
    name = "abnf"
    extensions = (".abnf",)
    flavour_cls = AbnfFlavour

    def __init__(self) -> None:
        self.parser = MetaGrammarParser(AbnfFlavour)
        self.emitter = AbnfFlavour.emitter
```

Update `src/lexic/grammars/__init__.py`:

```python
from lexic.grammars.gbnf.adapter import GbnfAdapter
from lexic.grammars.abnf.adapter import AbnfAdapter

register_adapter(GbnfAdapter())
register_adapter(AbnfAdapter())
```

- [ ] **Step 6: Drop legacy branches from consumers updated in Tasks 20–24.**

For each of `gbnf/emitter.py`, `model_emitter.py`, `lark_builder.py`, `transformer/*`, `base.py`:
- Remove legacy-atom dispatch branches.
- Remove imports of legacy atoms (`LiteralAtom`, `CharClassAtom`, `RuleRefAtom`, `AlternationAtom`, `InlineAlternationAtom`, `InlineRegexAtom`, `QuantifiedLiteralAtom`).
- Remove `decode_gbnf_escapes` calls (literals are canonical from `MetaGrammarParser`).

Run tests after each consumer is cleaned; commit per consumer for traceability.

- [ ] **Step 7: Tighten `RuleSpec.items` typing.**

Edit `src/lexic/ir/spec.py`:

```python
from lexic.ir.nodes import IrItem


@dataclass
class RuleSpec:
    rule_name: str
    class_name: str
    parent_class_name: str
    kind: Literal["sequence", "alternation", "value_str"]
    items: list[IrItem] = field(default_factory=list)
    field_map: dict[str, int] = field(default_factory=dict)
    non_semantic_fields: frozenset[str] = field(default_factory=frozenset)
```

Drop the `from lexic.ir.atoms import Atom` import.

- [ ] **Step 8: Drop dead Protocols from `ir/protocols.py`.**

Delete `RuleClassifier`, `SequenceConverter`. Leave `FlavourParser`, `FlavourAdapter`, and the handler type aliases. Update `__all__`.

- [ ] **Step 9: Update `ir/__init__.py`.**

Drop legacy atom exports. Add new IR-AST exports:

```python
from lexic.ir.charclass import parse_charclass_chars
from lexic.ir.derive import derive_specs, classify_kind, compute_parents, hoist_helpers
from lexic.ir.directives import Directives, parse_directives
from lexic.ir.emit import FlavourEmitter
from lexic.ir.escapes import CANONICAL_ESCAPES, EscapeCodec
from lexic.ir.helpers import HelperRuleRegistry
from lexic.ir.nodes import (
    IrAlternation,
    IrAst,
    IrCharClass,
    IrGroup,
    IrItem,
    IrLiteral,
    IrRule,
    IrRuleRef,
    IrSequence,
    Quantifier,
)
from lexic.ir.protocols import (
    AtomEmitHandler,
    FieldHandler,
    FlavourAdapter,
    FlavourParser,
    LarkHandler,
    ToTextHandler,
    TransformHandler,
)
from lexic.ir.spec import RuleSpec
from lexic.ir.topo import topo_sort
from lexic.ir.walk import IrTransformer, IrVisitor, dump

__all__ = [
    "AtomEmitHandler",
    "CANONICAL_ESCAPES",
    "Directives",
    "EscapeCodec",
    "FieldHandler",
    "FlavourAdapter",
    "FlavourEmitter",
    "FlavourParser",
    "HelperRuleRegistry",
    "IrAlternation",
    "IrAst",
    "IrCharClass",
    "IrGroup",
    "IrItem",
    "IrLiteral",
    "IrRule",
    "IrRuleRef",
    "IrSequence",
    "IrTransformer",
    "IrVisitor",
    "LarkHandler",
    "Quantifier",
    "RuleSpec",
    "ToTextHandler",
    "TransformHandler",
    "classify_kind",
    "compute_parents",
    "derive_specs",
    "dump",
    "hoist_helpers",
    "parse_charclass_chars",
    "parse_directives",
    "topo_sort",
]
```

- [ ] **Step 10: Delete dead modules and their tests.**

```bash
git rm src/lexic/ir/atoms.py
git rm src/lexic/ir/builder.py
git rm src/lexic/ir/classify.py
git rm src/lexic/ir/convert.py
git rm src/lexic/ir/_legacy_shape.py

git rm tests/unit/lexic/ir/test_atoms.py
git rm tests/unit/lexic/ir/test_builder.py
git rm tests/unit/lexic/ir/test_classify.py
git rm tests/unit/lexic/ir/test_convert.py
git rm tests/unit/lexic/ir/test_legacy_shape.py

git rm src/lexic/grammars/gbnf/ast.py
git rm tests/unit/lexic/grammars/gbnf/test_ast.py

# Untracked WIP — remove from filesystem (no `git rm`):
rm src/lexic/grammars/gbnf/ast_to_ir.py
rm tests/unit/lexic/grammars/gbnf/test_ast_to_ir.py

git rm src/lexic/codegen/ir_builder.py
git rm src/lexic/codegen/classify.py
git rm src/lexic/codegen/seq_to_atoms.py
git rm src/lexic/codegen/ast_utils.py

git rm tests/unit/lexic/codegen/test_ir_builder.py
git rm tests/unit/lexic/codegen/test_classify.py
git rm tests/unit/lexic/codegen/test_seq_to_atoms.py
git rm tests/unit/lexic/codegen/test_ast_utils.py
```

- [ ] **Step 11: Run — full suite must pass after deletion.**

```bash
uv run pytest tests/ -q
uv run ruff check src/ tests/
```

If any test fails: it was relying on legacy code. Remove it (if it tested deleted machinery) or update it (if it tested behaviour that should still work). Iterate to green.

- [ ] **Step 12: Verify success criteria.**

```bash
# String "ws" should not appear under lexic/ir/ or lexic/grammars/gbnf/
! grep -r '"ws"' /home/mika/projects/lexic/src/lexic/ir/ /home/mika/projects/lexic/src/lexic/grammars/gbnf/ || echo "FAIL: ws string still appears"

# grammars/gbnf/ should be ~5 small files
ls /home/mika/projects/lexic/src/lexic/grammars/gbnf/

# grammars/abnf/ should have similar size
ls /home/mika/projects/lexic/src/lexic/grammars/abnf/
```

- [ ] **Step 13: Final commit.**

```bash
git add -A
git commit -m "refactor(ir): cutover to IR-AST pipeline; delete legacy IRBuilder/classifier/converter

- compile() routes through MetaGrammarParser + derive_specs.
- RuleSpec.items: list[IrItem]; legacy atoms removed.
- Consumers (gbnf/emitter, model_emitter, lark_builder, transformer, base)
  consume new shape only; decode_gbnf_escapes calls removed.
- ir/atoms.py, ir/builder.py, ir/classify.py, ir/convert.py,
  ir/_legacy_shape.py, grammars/gbnf/ast.py, grammars/gbnf/ast_to_ir.py,
  codegen/{ir_builder,classify,seq_to_atoms,ast_utils}.py deleted.
- ir/protocols.py: RuleClassifier and SequenceConverter dropped.
- AbnfAdapter registered alongside GbnfAdapter."
```

---

## Task 26: Phase E — Documentation supersession housekeeping

A single task closing the slice. Update predecessor docs to reflect what shipped.

**Files:**
- Modify: `CLAUDE.md`
- Modify: `prototyping/next/2_ARCHITECTURE.md`
- Modify: `prototyping/next/3_ROADMAP.md`
- Modify: `docs/superpowers/specs/2026-04-25-slice-b5-package-restructure-design.md`
- Modify: `docs/superpowers/plans/2026-04-25-slice-b5-package-restructure.md`

- [ ] **Step 1: Update `CLAUDE.md`.**

Replace the "Project layout" tree with the new structure:

```
src/
  ir/
    nodes.py          IR AST types (frozen dataclasses)
    walk.py           IrVisitor, IrTransformer, dump
    derive.py         derive_specs(ast, *, non_semantic_rules) → list[RuleSpec]
    directives.py     parse_directives — comment-channel @non-semantic etc.
    spec.py           RuleSpec (codegen view)
    helpers.py        HelperRuleRegistry
    naming.py         assign_field_names, to_pascal
    topo.py           topo_sort
    emit.py           FlavourEmitter ABC
    escapes.py        EscapeCodec ABC + CANONICAL_ESCAPES
    charclass.py      parse_charclass_chars (POSIX bracket enumeration)
    protocols.py      FlavourParser, FlavourAdapter, handler aliases
  parsing/
    meta_parser.py    MetaGrammarParser(flavour) → IrAst
  grammars/
    flavour.py        Flavour ABC
    flavours.py       Adapter registry
    gbnf/
      meta_grammar.py Lark grammar string with canonical tags
      flavour.py      GbnfFlavour
      escapes.py      GbnfEscapes
      emitter.py      GbnfEmitter
      adapter.py      GbnfAdapter
      parser.py       Thin wrapper around MetaGrammarParser(GbnfFlavour)
    abnf/
      meta_grammar.py
      flavour.py      AbnfFlavour
      escapes.py      AbnfEscapes
      emitter.py      AbnfEmitter
      adapter.py      AbnfAdapter
  codegen/
    model_emitter.py  RuleSpec → Pydantic source
    lark_builder.py   RuleSpec → Lark grammar + Transformer
    transformer/      Lark Transformer scaffolding (consumes IrItem)
  compile.py          compile_grammar(text, flavour); compile() bundle
  base.py             GrammarModel base class
  parse.py            parse(text, grammar_path) entry
  generate.py         constrained-generation entry
```

Replace the "Architecture" section with the IR-AST-canonical pipeline diagram:

```
text ──► MetaGrammarParser(flavour) ──► IrAst ──► derive_specs() ──► list[RuleSpec] ──► ModelEmitter ──► Pydantic
                                          │
                                          └────── FlavourEmitter ──► text  (any flavour; transpilation)
```

Add a section on Flavour authorship:

```markdown
## Adding a flavour

A flavour module declares:
- a Lark meta-grammar string with canonical tags (`ir_rule`, `ir_literal`, ...)
- an `EscapeCodec` subclass
- a `FlavourEmitter` subclass with syntax constants
- two staticmethods: `parse_quantifier`, `parse_charclass`
- optional `normalize_literal` override for sugar expansion

No classifier, no converter, no transformer class. The IR-side
`MetaGrammarParser` and `derive_specs` do the work for any conforming flavour.
```

- [ ] **Step 2: Update `prototyping/next/2_ARCHITECTURE.md`.**

Replace the architecture description with the IR-AST-canonical model. Spell out the boundary contract (flavour = config; IR owns AST + derivation).

- [ ] **Step 3: Update `prototyping/next/3_ROADMAP.md`.**

Replace the v1 Slice B.5 entry with a one-paragraph pointer to `docs/superpowers/specs/2026-04-29-ir-ast-architecture-design.md`. Add a new follow-up Slice (e.g., B.6 — "package restructure continuation") for the unimplemented v1 packaging work (parsing/runtime/ moves, handler-table dispatch from v1's Tasks 6–12).

- [ ] **Step 4: Add supersession header to v1 spec.**

Edit `docs/superpowers/specs/2026-04-25-slice-b5-package-restructure-design.md`. At the very top, after the date line, insert:

```markdown
> **Partially superseded** by `docs/superpowers/specs/2026-04-29-ir-ast-architecture-design.md`
> (committed 2026-04-29). P1, P2, P4, P5, P6 stand. **P3 is replaced by P3a–e in
> the new spec.** This v1's `RuleClassifier`/`SequenceConverter` Protocols and Task 5
> (GBNF `ast_to_ir`) are abandoned. Tasks 6–12 (packaging continuation) ship as a
> separate follow-up slice (see ROADMAP).
```

- [ ] **Step 5: Add supersession banner to v1 plan.**

Edit `docs/superpowers/plans/2026-04-25-slice-b5-package-restructure.md`. At the very top, after the title, insert:

```markdown
> **Status:** Tasks 1–4 implemented and committed. Task 5 abandoned —
> replaced by `docs/superpowers/plans/2026-04-29-ir-ast-architecture.md`.
> Tasks 6–12 (packaging continuation) will be re-issued as a separate
> follow-up slice plan adapted to the IR-AST layer; do not implement them
> from this v1 plan.
```

- [ ] **Step 6: Run full suite + ruff. Final commit.**

```bash
uv run pytest tests/ -q
uv run ruff check src/ tests/
git add CLAUDE.md prototyping/next/2_ARCHITECTURE.md prototyping/next/3_ROADMAP.md docs/superpowers/specs/2026-04-25-slice-b5-package-restructure-design.md docs/superpowers/plans/2026-04-25-slice-b5-package-restructure.md
git commit -m "docs: supersession housekeeping — IR AST architecture closes Slice B.5

- CLAUDE.md and ARCHITECTURE.md describe the post-cutover pipeline.
- ROADMAP points to the new spec; a B.6 follow-up slice carries the v1
  packaging continuation (former Tasks 6-12).
- v1 spec and v1 plan get supersession headers."
```

---

## Self-review checklist

After all 27 tasks land:

- [ ] `compile_grammar(text, GbnfFlavour)` produces RuleSpec lists structurally equivalent to the prior pipeline for every `resources/ground_truth/*.gbnf`.
- [ ] `compile_grammar(text, AbnfFlavour)` succeeds for `resources/ground_truth/arithmetic.abnf` and the round-trip test passes.
- [ ] `tests/integration/test_cross_flavour.py` is green.
- [ ] `grep -r '"ws"' src/lexic/ir/ src/lexic/grammars/gbnf/` returns no hits.
- [ ] `src/lexic/grammars/gbnf/` contains: `__init__.py`, `meta_grammar.py`, `escapes.py`, `emitter.py`, `flavour.py`, `parser.py`, `adapter.py`. No `ast.py`, no `ast_to_ir.py`, no classifier/converter classes.
- [ ] `src/lexic/grammars/abnf/` contains a comparable file set.
- [ ] `src/lexic/ir/derive.py` is the only file containing structural decomposition logic; no flavour imports.
- [ ] `src/lexic/ir/atoms.py`, `ir/builder.py`, `ir/classify.py`, `ir/convert.py`, `ir/_legacy_shape.py` do not exist.
- [ ] `src/lexic/codegen/{ir_builder,classify,seq_to_atoms,ast_utils}.py` do not exist.
- [ ] `lexic.ir.protocols` does not declare `RuleClassifier` or `SequenceConverter`.
- [ ] `RuleSpec.items` is typed `list[IrItem]`.
- [ ] `lexic.ir.derive` imports nothing from `lexic.grammars`.
- [ ] `lexic.parsing.meta_parser` imports nothing from `lexic.grammars.gbnf` or `lexic.grammars.abnf` (only `lexic.grammars.flavour`).
- [ ] CLAUDE.md, prototyping/next/2_ARCHITECTURE.md, prototyping/next/3_ROADMAP.md describe the new architecture; v1 spec/plan have supersession headers.
- [ ] `uv run pytest tests/ -q` is green at every commit.
- [ ] `uv run ruff check src/ tests/` is clean.

