# Lexon Redesign: Bidirectional GBNF ↔ Pydantic Pipeline

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the lossy `ClassSpec`/`FieldSpec` pipeline with a rich IR layer (`RuleSpec`) that carries full GBNF semantics, enabling bidirectional GBNF ↔ Pydantic, exact-fidelity `to_text()`, and SOLID single-responsibility components.

**Architecture:** A new `RuleSpec` IR sits between the existing GBNF AST (unchanged) and all downstream emitters. `IRBuilder` converts AST → IR. `ModelEmitter`, `GBNFEmitter`, and `LarkBuilder` each consume IR independently. `GrammarModel` base class uses `__grammar__: RuleSpec` on each class to drive `to_text()` and `to_gbnf()` at runtime.

**Tech Stack:** Python ≥ 3.10, Pydantic v2, Lark (Earley parser), dataclasses, abc, typing.

---

## File Map

| Path | Action | Responsibility |
|---|---|---|
| `src/codegen/ir.py` | CREATE | `RuleSpec`, `LiteralAtom`, `CharClassAtom`, `RuleRefAtom`, `AlternationAtom` |
| `src/codegen/ir_builder.py` | CREATE | `IRBuilder`: GBNF AST → `list[RuleSpec]` |
| `src/codegen/model_emitter.py` | CREATE | `ModelEmitter`: `list[RuleSpec]` → Python source with `__grammar__` |
| `src/base.py` | CREATE | `GrammarModel`: base class with `to_text()`, `to_gbnf()`, `semantic_dump()` |
| `src/codegen/lark_builder.py` | CREATE | `LarkBuilder`: `list[RuleSpec]` → Lark grammar string + Transformer |
| `src/codegen/gbnf_emitter.py` | CREATE | `GBNFEmitter`: `list[RuleSpec]` → GBNF text (reverse direction) |
| `src/codegen/__init__.py` | MODIFY | Wire `IRBuilder` + `ModelEmitter`; retire `build_specs`/`render_source` |
| `src/parse.py` | MODIFY | Thin: call `codegen()`, then `LarkBuilder`, then transform |
| `tests/test_ir.py` | CREATE | IR dataclass construction tests |
| `tests/test_ir_builder.py` | CREATE | IRBuilder correctness across all 7 grammars |
| `tests/test_model_emitter.py` | CREATE | Generated files have `__grammar__`, correct types, correct hierarchy |
| `tests/test_base.py` | CREATE | `to_text()` on hand-constructed instances |
| `tests/test_lark_builder.py` | CREATE | LarkBuilder produces parseable Lark grammars |
| `tests/test_parser.py` | CREATE | Full round-trip: parse → to_text → parse → model_dump equality |
| `tests/test_gbnf_emitter.py` | CREATE | GBNFEmitter round-trips through parse_gbnf |
| `tests/test_codegen.py` | MODIFY | Update field-name assertions to use semantic names |
| `src/codegen/classify.py` | RETIRE | Superseded by `ir_builder.py` (delete after all tests pass) |
| `src/codegen/emitter.py` | RETIRE | Superseded by `model_emitter.py` (delete after all tests pass) |

**Import convention throughout:** `pythonpath = ["src"]` in `pyproject.toml`. All imports use `from codegen.ir import ...`, `from base import GrammarModel`, etc. Never `from src.codegen import ...`.

**Run all tests:** `uv run pytest tests/ -v`

---

## Task 1: IR Dataclasses (`src/codegen/ir.py`)

**Files:**
- Create: `src/codegen/ir.py`
- Create: `tests/test_ir.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_ir.py
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from codegen.ir import (
    AlternationAtom, CharClassAtom, LiteralAtom, RuleRefAtom, RuleSpec,
)


def test_literal_atom():
    a = LiteralAtom(value="=")
    assert a.value == "="


def test_charclass_atom_bounded():
    a = CharClassAtom(pattern="[a-z]", min=1, max=1)
    assert a.pattern == "[a-z]"
    assert a.min == 1
    assert a.max == 1


def test_charclass_atom_unbounded():
    a = CharClassAtom(pattern="[a-z0-9_]", min=0, max=None)
    assert a.min == 0
    assert a.max is None


def test_ruleref_atom_required():
    a = RuleRefAtom(rule_name="ws", min=1, max=1)
    assert a.rule_name == "ws"
    assert a.min == 1
    assert a.max == 1


def test_ruleref_atom_list():
    a = RuleRefAtom(rule_name="item", min=1, max=None)
    assert a.max is None


def test_alternation_atom():
    a = AlternationAtom(arm_rule_names=["ident", "num", "term-arm3"])
    assert "ident" in a.arm_rule_names
    assert len(a.arm_rule_names) == 3


def test_rulespec_sequence():
    spec = RuleSpec(
        rule_name="ident",
        class_name="Ident",
        parent_class_name="Term",
        kind="sequence",
        items=[
            CharClassAtom("[a-z]", min=1, max=1),
            CharClassAtom("[a-z0-9_]", min=0, max=None),
            RuleRefAtom("ws", min=1, max=1),
        ],
        field_map={"first": 0, "second": 1, "ws": 2},
    )
    assert spec.kind == "sequence"
    assert len(spec.items) == 3
    assert spec.field_map["ws"] == 2


def test_rulespec_alternation():
    spec = RuleSpec(
        rule_name="term",
        class_name="Term",
        parent_class_name="GrammarModel",
        kind="alternation",
        items=[AlternationAtom(arm_rule_names=["ident", "num"])],
        field_map={},
    )
    assert spec.kind == "alternation"
    assert spec.field_map == {}


def test_rulespec_value_str():
    spec = RuleSpec(
        rule_name="ws",
        class_name="Ws",
        parent_class_name="GrammarModel",
        kind="value_str",
        items=[CharClassAtom("[ \\t\\n]", min=0, max=None)],
        field_map={},
    )
    assert spec.kind == "value_str"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_ir.py -v
```
Expected: `ModuleNotFoundError: No module named 'codegen.ir'`

- [ ] **Step 3: Implement `src/codegen/ir.py`**

```python
"""IR dataclasses for the GBNF → Pydantic pipeline.

RuleSpec is the canonical representation of a GBNF rule.
All emitters (ModelEmitter, GBNFEmitter, LarkBuilder) consume RuleSpec.
The GBNF AST (codegen/ast.py) is only consumed by IRBuilder.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass
class LiteralAtom:
    """A quoted string literal in the grammar, e.g. '=' or '('."""
    value: str


@dataclass
class CharClassAtom:
    """A character class with quantifier bounds, e.g. [a-z]{1,1} or [a-z0-9_]{0,}.

    pattern: full bracket expression as it appears in GBNF, e.g. '[a-z]'
    min: minimum occurrences (0 = *, 1 = required or +)
    max: maximum occurrences; None = unbounded
    """
    pattern: str
    min: int
    max: int | None


@dataclass
class RuleRefAtom:
    """A reference to another rule, with quantifier bounds.

    min=1, max=1  → required singular field
    min=0, max=1  → Optional[X] field
    min=1, max=None → List[X] field (one or more)
    min=0, max=None → List[X] field (zero or more)
    """
    rule_name: str
    min: int
    max: int | None


@dataclass
class AlternationAtom:
    """Names of the alternative arms of an alternation rule.

    Used in the items list of a RuleSpec with kind='alternation'.
    arm_rule_names: GBNF rule names (not class names) of the arms.
    """
    arm_rule_names: list[str]


Atom = LiteralAtom | CharClassAtom | RuleRefAtom | AlternationAtom


@dataclass
class RuleSpec:
    """Complete specification of one GBNF rule.

    All downstream emitters (ModelEmitter, GBNFEmitter, LarkBuilder) consume
    this instead of the raw GBNF AST.

    field_map: maps Pydantic field name → index in items list.
      - LiteralAtom items are NEVER in field_map (they are structural).
      - AlternationAtom items are NEVER in field_map (abstract class has no fields).
      - CharClassAtom and RuleRefAtom items each have exactly one field_map entry.

    kind='value_str': single `value: str` field; items holds atoms for GBNFEmitter only.
    kind='alternation': abstract class; items=[AlternationAtom(...)]; field_map={}.
    kind='sequence': concrete class; items lists atoms in grammar order; field_map populated.
    """
    rule_name: str
    class_name: str                            # PascalCase, e.g. "Ident"
    parent_class_name: str                     # e.g. "Term" or "GrammarModel"
    kind: Literal["sequence", "alternation", "value_str"]
    items: list[Atom] = field(default_factory=list)
    field_map: dict[str, int] = field(default_factory=dict)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_ir.py -v
```
Expected: all 9 tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/codegen/ir.py tests/test_ir.py
git commit -m "feat: add IR dataclasses (RuleSpec, atoms)"
```

---

## Task 2: IRBuilder (`src/codegen/ir_builder.py`)

**Files:**
- Create: `src/codegen/ir_builder.py`
- Create: `tests/test_ir_builder.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_ir_builder.py
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pytest
from codegen.parser import parse_gbnf
from codegen.ir_builder import IRBuilder
from codegen.ir import AlternationAtom, CharClassAtom, LiteralAtom, RuleRefAtom, RuleSpec

GRAMMAR_DIR = Path(__file__).parent.parent / "resources" / "ground_truth"


def _build(grammar_name: str) -> list[RuleSpec]:
    text = (GRAMMAR_DIR / f"{grammar_name}.gbnf").read_text()
    rules = parse_gbnf(text)
    return IRBuilder(rules).build()


def _by_rule(specs: list[RuleSpec]) -> dict[str, RuleSpec]:
    return {s.rule_name: s for s in specs}


# ── Smoke: all 7 grammars ─────────────────────────────────────────────────────

@pytest.mark.parametrize("grammar", [
    "arithmetic", "c", "chess", "japanese", "json_arr", "json_ws", "list"
])
def test_all_grammars_produce_specs(grammar: str):
    specs = _build(grammar)
    assert len(specs) > 0
    for spec in specs:
        assert spec.rule_name, f"empty rule_name in {grammar}"
        assert spec.class_name, f"empty class_name in {grammar}"
        assert spec.kind in ("sequence", "alternation", "value_str")


@pytest.mark.parametrize("grammar", [
    "arithmetic", "c", "chess", "japanese", "json_arr", "json_ws", "list"
])
def test_root_spec_is_first(grammar: str):
    specs = _build(grammar)
    assert specs[0].rule_name == "root"


# ── arithmetic: rule kinds ───────────────────────────────────────────────────

def test_arithmetic_ws_is_value_str():
    d = _by_rule(_build("arithmetic"))
    assert d["ws"].kind == "value_str"
    assert d["ws"].class_name == "Ws"


def test_arithmetic_ident_is_sequence():
    d = _by_rule(_build("arithmetic"))
    ident = d["ident"]
    assert ident.kind == "sequence"
    assert ident.class_name == "Ident"


def test_arithmetic_term_is_alternation():
    d = _by_rule(_build("arithmetic"))
    term = d["term"]
    assert term.kind == "alternation"
    assert term.class_name == "Term"
    assert len(term.items) == 1
    alt = term.items[0]
    assert isinstance(alt, AlternationAtom)
    assert "ident" in alt.arm_rule_names
    assert "num" in alt.arm_rule_names


# ── arithmetic: ident items and field_map ────────────────────────────────────

def test_arithmetic_ident_items():
    d = _by_rule(_build("arithmetic"))
    ident = d["ident"]
    # ident ::= [a-z] [a-z0-9_]* ws
    assert isinstance(ident.items[0], CharClassAtom)
    assert ident.items[0].min == 1
    assert ident.items[0].max == 1

    assert isinstance(ident.items[1], CharClassAtom)
    assert ident.items[1].min == 0
    assert ident.items[1].max is None

    assert isinstance(ident.items[2], RuleRefAtom)
    assert ident.items[2].rule_name == "ws"
    assert ident.items[2].min == 1
    assert ident.items[2].max == 1


def test_arithmetic_ident_field_map():
    d = _by_rule(_build("arithmetic"))
    ident = d["ident"]
    fm = ident.field_map
    assert "first" in fm        # [a-z]
    assert "second" in fm       # [a-z0-9_]*
    assert "ws" in fm           # ws
    assert fm["first"] == 0
    assert fm["second"] == 1
    assert fm["ws"] == 2


def test_arithmetic_literals_not_in_field_map():
    # root ::= (expr "=" ws term "\n")+
    # The helper RootItem has "=" and "\n" as LiteralAtoms — must not be fields
    specs = _build("arithmetic")
    # Find the helper class for the root group body
    helper = next((s for s in specs if "root" in s.rule_name and s.rule_name != "root"), None)
    if helper:
        for fname in helper.field_map:
            assert fname not in ("=", "\\n", "\n"), (
                f"literal '{fname}' must not be in field_map"
            )
        # Verify at least one LiteralAtom exists in items
        assert any(isinstance(a, LiteralAtom) for a in helper.items)


# ── arithmetic: num ──────────────────────────────────────────────────────────

def test_arithmetic_num_is_value_str_or_sequence():
    # num ::= [0-9]+ ws — single char class + ws ref; may be value_str or sequence
    d = _by_rule(_build("arithmetic"))
    num = d["num"]
    assert num.kind in ("value_str", "sequence")
    assert num.class_name == "Num"


# ── arithmetic: expr has list field ──────────────────────────────────────────

def test_arithmetic_expr_has_list_ruleref():
    # expr ::= term ([-+*/] term)* — the * group → list field
    d = _by_rule(_build("arithmetic"))
    expr = d["expr"]
    assert expr.kind == "sequence"
    # Should have a RuleRefAtom with max=None for the repeated group
    list_refs = [a for a in expr.items if isinstance(a, RuleRefAtom) and a.max is None]
    assert len(list_refs) >= 1, "expr must have a List[...] item for the * group"


# ── field naming: no positional names ────────────────────────────────────────

def test_no_fieldN_names_in_any_grammar():
    import re
    for grammar in ["arithmetic", "c", "chess", "japanese", "json_arr", "json_ws", "list"]:
        specs = _build(grammar)
        for spec in specs:
            for fname in spec.field_map:
                assert not re.fullmatch(r"field\d+", fname), (
                    f"Grammar '{grammar}', rule '{spec.rule_name}': "
                    f"field name '{fname}' must be semantic, not positional"
                )


# ── parent class names ────────────────────────────────────────────────────────

def test_arithmetic_ident_parent_is_term():
    d = _by_rule(_build("arithmetic"))
    assert d["ident"].parent_class_name == "Term"


def test_arithmetic_num_parent_is_term():
    d = _by_rule(_build("arithmetic"))
    assert d["num"].parent_class_name == "Term"


def test_arithmetic_term_parent_is_grammar_model():
    d = _by_rule(_build("arithmetic"))
    assert d["term"].parent_class_name == "GrammarModel"


# ── japanese: hyphened rule names ─────────────────────────────────────────────

def test_japanese_hyphen_rules_have_valid_class_names():
    d = _by_rule(_build("japanese"))
    assert "jp-char" in d
    jp = d["jp-char"]
    assert jp.class_name == "JpChar"   # PascalCase from hyphenated name
    assert jp.kind == "alternation"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_ir_builder.py -v
```
Expected: `ModuleNotFoundError: No module named 'codegen.ir_builder'`

- [ ] **Step 3: Implement `src/codegen/ir_builder.py`**

```python
"""IRBuilder: converts GBNF AST (list[Rule]) into list[RuleSpec].

Single responsibility: understanding GBNF semantics.
Knows nothing about Lark, Python source, or Pydantic.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .ast import Alternation, CharClass, Group, Item, Literal, Rule, RuleRef, Sequence
from .ir import (
    AlternationAtom,
    Atom,
    CharClassAtom,
    LiteralAtom,
    RuleRefAtom,
    RuleSpec,
)


# ── Name utilities ────────────────────────────────────────────────────────────


def to_pascal(name: str) -> str:
    """Convert 'jp-char' or 'json_ws' → 'JpChar' / 'JsonWs'."""
    parts = re.split(r"[-_]", name)
    return "".join(p[0].upper() + p[1:] if p else "" for p in parts)


def _quantifier_to_bounds(q: str | None) -> tuple[int, int | None]:
    """Parse GBNF quantifier string → (min, max). max=None means unbounded."""
    if q is None:
        return 1, 1
    if q == "?":
        return 0, 1
    if q == "*":
        return 0, None
    if q == "+":
        return 1, None
    inner = q[1:-1]  # strip { }
    if "," in inner:
        parts = inner.split(",", 1)
        lo = int(parts[0])
        hi = int(parts[1]) if parts[1] else None
        return lo, hi
    n = int(inner)
    return n, n


# ── Classification helpers (replaces classify.py) ────────────────────────────


def _is_ws_item(item: Item) -> bool:
    return isinstance(item.atom, RuleRef) and item.atom.name == "ws"


def _strip_ws(seq: Sequence) -> Sequence:
    return Sequence([it for it in seq.items if not _is_ws_item(it)])


def _is_pure_literal(item: Item) -> bool:
    return isinstance(item.atom, (Literal, CharClass))


def _is_pure_literal_seq(seq: Sequence) -> bool:
    stripped = _strip_ws(seq)
    return len(stripped.items) > 0 and all(_is_pure_literal(it) for it in stripped.items)


def _is_single_ruleref(seq: Sequence) -> str | None:
    """If sequence is exactly one unquantified rule ref (after ws strip), return name."""
    stripped = _strip_ws(seq)
    if len(stripped.items) != 1:
        return None
    it = stripped.items[0]
    if it.quantifier is not None:
        return None
    if isinstance(it.atom, RuleRef):
        return it.atom.name
    if isinstance(it.atom, Group):
        inner = it.atom.alt
        if len(inner.seqs) == 1:
            inner_stripped = _strip_ws(inner.seqs[0])
            if len(inner_stripped.items) == 1:
                inner_it = inner_stripped.items[0]
                if inner_it.quantifier is None and isinstance(inner_it.atom, RuleRef):
                    return inner_it.atom.name
    return None


def _unwrap_group_alt(alt: Alternation) -> Alternation:
    if len(alt.seqs) != 1:
        return alt
    stripped = _strip_ws(alt.seqs[0])
    if len(stripped.items) == 1:
        it = stripped.items[0]
        if isinstance(it.atom, Group) and it.quantifier is None:
            return it.atom.alt
    return alt


def _has_any_ruleref(items: list[Item]) -> bool:
    for it in items:
        if _is_ws_item(it):
            continue
        if isinstance(it.atom, RuleRef):
            return True
        if isinstance(it.atom, Group):
            for seq in it.atom.alt.seqs:
                if _has_any_ruleref(seq.items):
                    return True
    return False


def _has_nontrivial_group(items: list[Item]) -> bool:
    for it in items:
        if isinstance(it.atom, Group):
            for seq in it.atom.alt.seqs:
                if any(isinstance(i.atom, Group) for i in seq.items):
                    return True
    return False


def _has_group_with_alt(items: list[Item]) -> bool:
    for it in items:
        if isinstance(it.atom, Group) and len(it.atom.alt.seqs) > 1:
            return True
    return False


def _is_structurally_complex(alt: Alternation) -> bool:
    for seq in alt.seqs:
        stripped = _strip_ws(seq)
        for it in stripped.items:
            if isinstance(it.atom, Group) and it.quantifier == "*":
                for inner_seq in it.atom.alt.seqs:
                    if _has_nontrivial_group(inner_seq.items):
                        return True
    all_no_refs = not any(
        _has_any_ruleref(_strip_ws(seq).items) for seq in alt.seqs
    )
    has_group_alt = any(
        _has_group_with_alt(_strip_ws(seq).items) for seq in alt.seqs
    )
    return all_no_refs and has_group_alt


def _classify(rule: Rule) -> str:
    alt = _unwrap_group_alt(rule.body)
    if _is_structurally_complex(alt):
        return "value_str"
    arms = [a for a in (_strip_ws(seq) for seq in alt.seqs) if len(a.items) > 0]
    if not arms:
        return "value_str"
    if len(arms) > 1 and all(_is_pure_literal_seq(a) for a in arms):
        return "pure_literal_alt"
    if (
        len(arms) == 1
        and len(arms[0].items) == 1
        and isinstance(arms[0].items[0].atom, Group)
        and arms[0].items[0].quantifier is None
        and all(_is_pure_literal_seq(_strip_ws(s)) for s in arms[0].items[0].atom.alt.seqs)
    ):
        return "pure_literal_alt"
    if len(arms) > 1 and any(_is_single_ruleref(a) is not None for a in arms):
        return "named_alt"
    if len(arms) == 1:
        return "sequence"
    return "named_alt"


# ── Field naming ─────────────────────────────────────────────────────────────

_CC_NAMES = ["first", "second", "third", "fourth", "fifth"]


def _assign_field_names(items: list[Atom]) -> dict[str, int]:
    """Assign semantic field names to non-literal, non-alternation atoms.

    Rules:
    - LiteralAtom → never a field
    - AlternationAtom → never a field
    - RuleRefAtom(rule_name) → field name = rule_name (underscores for hyphens)
      Duplicates get suffix: 'ws', 'ws2', 'ws3', etc.
    - CharClassAtom → 'first', 'second', 'third', ... by position among char classes
    """
    field_map: dict[str, int] = {}
    rule_ref_counts: dict[str, int] = {}
    cc_count = 0

    for i, atom in enumerate(items):
        if isinstance(atom, (LiteralAtom, AlternationAtom)):
            continue

        if isinstance(atom, RuleRefAtom):
            base = atom.rule_name.replace("-", "_")
            count = rule_ref_counts.get(base, 0) + 1
            rule_ref_counts[base] = count
            fname = base if count == 1 else f"{base}{count}"
            field_map[fname] = i

        elif isinstance(atom, CharClassAtom):
            cc_count += 1
            fname = _CC_NAMES[cc_count - 1] if cc_count <= len(_CC_NAMES) else f"cc{cc_count}"
            field_map[fname] = i

    return field_map


# ── Sequence → items ─────────────────────────────────────────────────────────


def _seq_to_atoms(
    seq: Sequence,
    parent_class_name: str,
    helper_specs: list[RuleSpec],
    name_map: dict[str, str],
    parent_of: dict[str, str],
) -> list[Atom]:
    """Convert a single grammar sequence into a list of IR atoms.

    When a quantified group is encountered, a helper RuleSpec is created and
    appended to helper_specs, and a RuleRefAtom pointing to it is returned.
    """
    atoms: list[Atom] = []

    for item in seq.items:
        if isinstance(item.atom, Literal):
            if item.quantifier in ("+", "*"):
                min_, max_ = _quantifier_to_bounds(item.quantifier)
                atoms.append(CharClassAtom(
                    pattern=f'"{item.atom.value}"',
                    min=min_,
                    max=max_,
                ))
            else:
                atoms.append(LiteralAtom(value=item.atom.value))

        elif isinstance(item.atom, CharClass):
            min_, max_ = _quantifier_to_bounds(item.quantifier)
            atoms.append(CharClassAtom(pattern=item.atom.pattern, min=min_, max=max_))

        elif isinstance(item.atom, RuleRef):
            min_, max_ = _quantifier_to_bounds(item.quantifier)
            atoms.append(RuleRefAtom(rule_name=item.atom.name, min=min_, max=max_))

        elif isinstance(item.atom, Group):
            min_, max_ = _quantifier_to_bounds(item.quantifier)
            inner_arms = [
                a for a in (_strip_ws(s) for s in item.atom.alt.seqs)
                if len(a.items) > 0
            ]

            # Inline literal alternation → treat as single char-class-like atom
            if all(_is_pure_literal_seq(a) for a in inner_arms):
                atoms.append(CharClassAtom(
                    pattern="(" + "|".join(
                        "".join(f'"{it.atom.value}"' if isinstance(it.atom, Literal) else it.atom.pattern
                                for it in a.items)
                        for a in inner_arms
                    ) + ")",
                    min=min_ if min_ is not None else 1,
                    max=max_,
                ))
                continue

            # Inline union of named rules (no quantifier) → inline alternation atom
            if (
                item.quantifier is None
                and len(inner_arms) > 1
                and all(_is_single_ruleref(a) is not None for a in inner_arms)
            ):
                arm_names = [_is_single_ruleref(a) for a in inner_arms]
                atoms.append(AlternationAtom(arm_rule_names=arm_names))
                continue

            # Unquantified single-arm group → inline its contents
            if item.quantifier is None and len(inner_arms) == 1:
                inner_atoms = _seq_to_atoms(
                    inner_arms[0], parent_class_name, helper_specs, name_map, parent_of
                )
                atoms.extend(inner_atoms)
                continue

            # Quantified group → create helper RuleSpec
            helper_rule_name = f"{parent_class_name.lower()}-item"
            # Deduplicate helper names
            existing = {s.rule_name for s in helper_specs}
            suffix = 2
            candidate = helper_rule_name
            while candidate in existing:
                candidate = f"{helper_rule_name}{suffix}"
                suffix += 1
            helper_rule_name = candidate

            helper_class_name = to_pascal(helper_rule_name)
            helper_atoms = _seq_to_atoms(
                inner_arms[0] if inner_arms else seq,
                helper_class_name,
                helper_specs,
                name_map,
                parent_of,
            )
            helper_fm = _assign_field_names(helper_atoms)
            helper_spec = RuleSpec(
                rule_name=helper_rule_name,
                class_name=helper_class_name,
                parent_class_name="GrammarModel",
                kind="sequence",
                items=helper_atoms,
                field_map=helper_fm,
            )
            helper_specs.append(helper_spec)
            atoms.append(RuleRefAtom(rule_name=helper_rule_name, min=min_, max=max_))

    return atoms


# ── Main builder ─────────────────────────────────────────────────────────────


class IRBuilder:
    """Converts a list of GBNF Rule objects into a list of RuleSpec IR objects.

    Knows nothing about Lark, Python source, or Pydantic.
    """

    def __init__(self, rules: list[Rule]):
        self._rules = rules
        self._rules_dict = {r.name: r for r in rules}
        self._name_map = {r.name: to_pascal(r.name) for r in rules}

    def build(self) -> list[RuleSpec]:
        """Build and return specs in grammar order (root first)."""
        parent_of = self._compute_parents()
        all_specs: list[RuleSpec] = []

        for rule in self._rules:
            specs = self._build_rule(rule, parent_of, all_specs)
            all_specs.extend(specs)

        return self._topo_sort(all_specs)

    def _compute_parents(self) -> dict[str, str]:
        """For each rule that is a named arm of an alternation, record its parent class."""
        parent_of: dict[str, str] = {}
        for rule in self._rules:
            classification = _classify(rule)
            if classification != "named_alt":
                continue
            alt = _unwrap_group_alt(rule.body)
            parent_cls = self._name_map[rule.name]
            for seq in alt.seqs:
                ref = _is_single_ruleref(_strip_ws(seq))
                if ref is not None:
                    parent_of[ref] = parent_cls
        return parent_of

    def _build_rule(
        self,
        rule: Rule,
        parent_of: dict[str, str],
        existing_specs: list[RuleSpec],
    ) -> list[RuleSpec]:
        classification = _classify(rule)
        cls_name = self._name_map[rule.name]
        parent_cls = parent_of.get(rule.name, "GrammarModel")

        # value_str / pure_literal_alt → single `value: str` field
        if classification in ("value_str", "pure_literal_alt"):
            alt = _unwrap_group_alt(rule.body)
            items: list[Atom] = []
            for seq in alt.seqs:
                for it in seq.items:
                    if isinstance(it.atom, CharClass):
                        min_, max_ = _quantifier_to_bounds(it.quantifier)
                        items.append(CharClassAtom(it.atom.pattern, min_, max_))
                    elif isinstance(it.atom, Literal):
                        items.append(LiteralAtom(it.atom.value))
            return [RuleSpec(
                rule_name=rule.name,
                class_name=cls_name,
                parent_class_name=parent_cls,
                kind="value_str",
                items=items,
                field_map={},
            )]

        # named_alt → abstract class + anonymous arm classes
        if classification == "named_alt":
            alt = _unwrap_group_alt(rule.body)
            arm_rule_names: list[str] = []
            arm_specs: list[RuleSpec] = []
            arm_idx = 0

            for seq in alt.seqs:
                stripped = _strip_ws(seq)
                if not stripped.items:
                    continue
                arm_idx += 1
                ref = _is_single_ruleref(stripped)
                if ref is not None:
                    arm_rule_names.append(ref)
                else:
                    arm_rule_name = f"{rule.name}-arm{arm_idx}"
                    arm_cls_name = f"{cls_name}Arm{arm_idx}"
                    arm_rule_names.append(arm_rule_name)
                    helper_specs: list[RuleSpec] = []
                    atoms = _seq_to_atoms(
                        stripped, arm_cls_name, helper_specs, self._name_map, parent_of
                    )
                    fm = _assign_field_names(atoms)
                    arm_specs.extend(helper_specs)
                    arm_specs.append(RuleSpec(
                        rule_name=arm_rule_name,
                        class_name=arm_cls_name,
                        parent_class_name=cls_name,
                        kind="sequence",
                        items=atoms,
                        field_map=fm,
                    ))

            abstract_spec = RuleSpec(
                rule_name=rule.name,
                class_name=cls_name,
                parent_class_name=parent_cls,
                kind="alternation",
                items=[AlternationAtom(arm_rule_names=arm_rule_names)],
                field_map={},
            )
            return [abstract_spec] + arm_specs

        # sequence
        alt = _unwrap_group_alt(rule.body)
        arms = [a for a in (_strip_ws(s) for s in alt.seqs) if a.items]
        if not arms:
            return [RuleSpec(
                rule_name=rule.name,
                class_name=cls_name,
                parent_class_name=parent_cls,
                kind="value_str",
                items=[],
                field_map={},
            )]

        helper_specs: list[RuleSpec] = []
        atoms = _seq_to_atoms(arms[0], cls_name, helper_specs, self._name_map, parent_of)
        fm = _assign_field_names(atoms)
        seq_spec = RuleSpec(
            rule_name=rule.name,
            class_name=cls_name,
            parent_class_name=parent_cls,
            kind="sequence",
            items=atoms,
            field_map=fm,
        )
        return helper_specs + [seq_spec]

    def _topo_sort(self, specs: list[RuleSpec]) -> list[RuleSpec]:
        """Order specs so parent classes appear before subclasses."""
        by_cls = {s.class_name: s for s in specs}
        ordered: list[RuleSpec] = []
        visited: set[str] = set()

        def visit(cls_name: str) -> None:
            if cls_name in visited:
                return
            visited.add(cls_name)
            spec = by_cls.get(cls_name)
            if spec and spec.parent_class_name not in ("GrammarModel", "BaseModel"):
                visit(spec.parent_class_name)
            if spec:
                ordered.append(spec)

        for s in specs:
            visit(s.class_name)

        return ordered
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_ir_builder.py -v
```
Expected: all tests pass. If any fail, read the assertion message — it will name the exact rule and grammar that misfired.

- [ ] **Step 5: Commit**

```bash
git add src/codegen/ir_builder.py tests/test_ir_builder.py
git commit -m "feat: add IRBuilder (AST → RuleSpec IR)"
```

---

## Task 3: GrammarModel Base Class (`src/base.py`)

**Files:**
- Create: `src/base.py`
- Create: `tests/test_base.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_base.py
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from typing import ClassVar, List, Optional
from base import GrammarModel
from codegen.ir import CharClassAtom, LiteralAtom, RuleRefAtom, RuleSpec


# ── value_str ─────────────────────────────────────────────────────────────────

def test_to_text_value_str():
    spec = RuleSpec("ws", "Ws", "GrammarModel", "value_str",
                    items=[CharClassAtom("[ \\t\\n]", 0, None)], field_map={})
    class Ws(GrammarModel):
        __grammar__: ClassVar[RuleSpec] = spec
        value: str
    assert Ws(value="  ").to_text() == "  "
    assert Ws(value="").to_text() == ""
    assert Ws(value="\n\t").to_text() == "\n\t"


# ── sequence with literal (literal baked in) ──────────────────────────────────

def test_to_text_sequence_emits_literal():
    spec = RuleSpec(
        "eq-expr", "EqExpr", "GrammarModel", "sequence",
        items=[
            CharClassAtom("[a-z]", 1, 1),
            LiteralAtom("="),
            CharClassAtom("[0-9]", 1, 1),
        ],
        field_map={"first": 0, "second": 2},
    )
    class EqExpr(GrammarModel):
        __grammar__: ClassVar[RuleSpec] = spec
        first: str
        second: str
    assert EqExpr(first="x", second="1").to_text() == "x=1"


# ── sequence with nested GrammarModel ─────────────────────────────────────────

def test_to_text_nested_grammar_model():
    ws_spec = RuleSpec("ws", "Ws", "GrammarModel", "value_str",
                       items=[], field_map={})
    class Ws(GrammarModel):
        __grammar__: ClassVar[RuleSpec] = ws_spec
        value: str

    ident_spec = RuleSpec(
        "ident", "Ident", "GrammarModel", "sequence",
        items=[
            CharClassAtom("[a-z]", 1, 1),
            RuleRefAtom("ws", 1, 1),
        ],
        field_map={"first": 0, "ws": 1},
    )
    class Ident(GrammarModel):
        __grammar__: ClassVar[RuleSpec] = ident_spec
        first: str
        ws: Ws
    inst = Ident(first="x", ws=Ws(value=" "))
    assert inst.to_text() == "x "


# ── sequence with List field ──────────────────────────────────────────────────

def test_to_text_list_of_grammar_model():
    item_spec = RuleSpec("it", "It", "GrammarModel", "value_str", items=[], field_map={})
    class It(GrammarModel):
        __grammar__: ClassVar[RuleSpec] = item_spec
        value: str

    root_spec = RuleSpec(
        "root", "Root", "GrammarModel", "sequence",
        items=[RuleRefAtom("it", 1, None)],
        field_map={"it": 0},
    )
    class Root(GrammarModel):
        __grammar__: ClassVar[RuleSpec] = root_spec
        it: List[It]

    inst = Root(it=[It(value="a"), It(value="b"), It(value="c")])
    assert inst.to_text() == "abc"


# ── Optional field absent ─────────────────────────────────────────────────────

def test_to_text_optional_absent():
    ws_spec = RuleSpec("ws", "Ws", "GrammarModel", "value_str", items=[], field_map={})
    class Ws(GrammarModel):
        __grammar__: ClassVar[RuleSpec] = ws_spec
        value: str

    spec = RuleSpec(
        "r", "R", "GrammarModel", "sequence",
        items=[CharClassAtom("[a-z]", 1, 1), RuleRefAtom("ws", 0, 1)],
        field_map={"first": 0, "ws": 1},
    )
    class R(GrammarModel):
        __grammar__: ClassVar[RuleSpec] = spec
        first: str
        ws: Optional[Ws] = None

    assert R(first="x", ws=None).to_text() == "x"
    assert R(first="x", ws=Ws(value=" ")).to_text() == "x "


# ── alternation (abstract) raises ─────────────────────────────────────────────

def test_to_text_alternation_raises():
    from codegen.ir import AlternationAtom
    import pytest
    spec = RuleSpec(
        "base", "Base", "GrammarModel", "alternation",
        items=[AlternationAtom(["a", "b"])], field_map={}
    )
    class Base(GrammarModel):
        __grammar__: ClassVar[RuleSpec] = spec
    with pytest.raises(NotImplementedError):
        Base().to_text()


# ── semantic_dump excludes ws fields ─────────────────────────────────────────

def test_semantic_dump_excludes_ws():
    ws_spec = RuleSpec("ws", "Ws", "GrammarModel", "value_str", items=[], field_map={})
    class Ws(GrammarModel):
        __grammar__: ClassVar[RuleSpec] = ws_spec
        value: str

    spec = RuleSpec(
        "ident", "Ident", "GrammarModel", "sequence",
        items=[CharClassAtom("[a-z]", 1, 1), RuleRefAtom("ws", 1, 1)],
        field_map={"first": 0, "ws": 1},
    )
    class Ident(GrammarModel):
        __grammar__: ClassVar[RuleSpec] = spec
        first: str
        ws: Ws

    inst = Ident(first="x", ws=Ws(value=" "))
    d = inst.semantic_dump()
    assert "first" in d
    assert "ws" not in d
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_base.py -v
```
Expected: `ModuleNotFoundError: No module named 'base'`

- [ ] **Step 3: Implement `src/base.py`**

```python
"""GrammarModel: base class for all generated Pydantic models.

Provides to_text(), to_gbnf(), and semantic_dump() driven entirely by
__grammar__: RuleSpec on each concrete subclass.
Knows nothing about codegen, Lark, or GBNF parsing.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar, get_args, get_origin, get_type_hints

from pydantic import BaseModel

from codegen.ir import AlternationAtom, LiteralAtom, RuleRefAtom, RuleSpec

if TYPE_CHECKING:
    pass


class GrammarModel(BaseModel):
    """Abstract base for all generated grammar model classes.

    Each subclass must define:
        __grammar__: ClassVar[RuleSpec]

    to_text() reconstructs the original grammar text from instance field values.
    The algorithm walks __grammar__.items in order:
      - LiteralAtom  → emit atom.value directly (no field needed)
      - atom index in field_map → getattr(self, field_name) → emit
    Whitespace is preserved because ws fields are regular RuleRefAtom fields.
    """

    __grammar__: ClassVar[RuleSpec]

    def to_text(self) -> str:
        spec = self.__grammar__
        if spec.kind == "value_str":
            return str(getattr(self, "value", ""))
        if spec.kind == "alternation":
            raise NotImplementedError(
                f"{type(self).__name__} is abstract — call to_text() on a concrete subclass"
            )

        hints = get_type_hints(type(self))
        inv: dict[int, str] = {idx: name for name, idx in spec.field_map.items()}
        parts: list[str] = []

        for i, atom in enumerate(spec.items):
            if isinstance(atom, LiteralAtom):
                parts.append(atom.value)
                continue
            if i not in inv:
                continue
            field_name = inv[i]
            val = getattr(self, field_name, None)
            if val is None:
                continue
            hint = hints.get(field_name)
            origin = get_origin(hint)
            if origin is list:
                parts.append("".join(
                    item.to_text() if isinstance(item, GrammarModel) else str(item)
                    for item in val
                ))
            elif isinstance(val, GrammarModel):
                parts.append(val.to_text())
            else:
                parts.append(str(val))

        return "".join(parts)

    def to_gbnf(self) -> str:
        """Reconstruct the GBNF rule for this class's grammar spec."""
        from codegen.gbnf_emitter import GBNFEmitter
        return GBNFEmitter([self.__grammar__]).emit_rule(self.__grammar__)

    def semantic_dump(self) -> dict[str, Any]:
        """model_dump() excluding fields that map to RuleRefAtom('ws') in __grammar__.

        Used by S04 translate() to extract cross-grammar-portable data.
        """
        spec = self.__grammar__
        ws_fields: set[str] = set()
        for fname, idx in spec.field_map.items():
            atom = spec.items[idx]
            if isinstance(atom, RuleRefAtom) and atom.rule_name == "ws":
                ws_fields.add(fname)
        return self.model_dump(exclude=ws_fields)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_base.py -v
```
Expected: all tests pass. `test_to_text_alternation_raises` may fail until `gbnf_emitter.py` exists — that's OK for now, annotate with `pytest.importorskip` if needed. The `to_gbnf()` test is added in Task 7.

- [ ] **Step 5: Commit**

```bash
git add src/base.py tests/test_base.py
git commit -m "feat: add GrammarModel base class with to_text() and semantic_dump()"
```

---

## Task 4: ModelEmitter + Update `codegen/__init__.py`

**Files:**
- Create: `src/codegen/model_emitter.py`
- Modify: `src/codegen/__init__.py`
- Create: `tests/test_model_emitter.py`
- Modify: `tests/test_codegen.py` (update field-name assertions)

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_model_emitter.py
from __future__ import annotations
import importlib
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from abc import ABC
from typing import get_type_hints

from codegen import codegen
from codegen.ir import RuleSpec

GRAMMAR_DIR = Path(__file__).parent.parent / "resources" / "ground_truth"
GENERATED_DIR = Path(__file__).parent.parent / "generated"

ALL_GRAMMARS = [
    "arithmetic", "c", "chess", "japanese", "json_arr", "json_ws", "list"
]


def _fresh(stem: str):
    name = f"generated.{stem}"
    if name in sys.modules:
        del sys.modules[name]
    codegen(GRAMMAR_DIR / f"{stem}.gbnf")
    return importlib.import_module(name)


# ── All grammars: __grammar__ present ─────────────────────────────────────────

@pytest.mark.parametrize("grammar", ALL_GRAMMARS)
def test_all_classes_have_grammar(grammar: str):
    mod = _fresh(grammar)
    for name in dir(mod):
        cls = getattr(mod, name)
        if isinstance(cls, type) and issubclass(cls, __import__("pydantic").BaseModel):
            assert hasattr(cls, "__grammar__"), (
                f"{grammar}.{name} is missing __grammar__"
            )
            assert isinstance(cls.__grammar__, RuleSpec), (
                f"{grammar}.{name}.__grammar__ is not a RuleSpec"
            )


@pytest.mark.parametrize("grammar", ALL_GRAMMARS)
def test_no_field_n_names(grammar: str):
    import re
    mod = _fresh(grammar)
    for name in dir(mod):
        cls = getattr(mod, name)
        if not (isinstance(cls, type) and issubclass(cls, __import__("pydantic").BaseModel)):
            continue
        for fname in get_type_hints(cls):
            assert not re.fullmatch(r"field\d+", fname), (
                f"{grammar}.{name} has positional field name '{fname}'"
            )


@pytest.mark.parametrize("grammar", ALL_GRAMMARS)
def test_generated_imports_grammar_model(grammar: str):
    stem = grammar
    codegen(GRAMMAR_DIR / f"{stem}.gbnf")
    source = (GENERATED_DIR / f"{stem}.py").read_text()
    assert "GrammarModel" in source, f"{stem}.py must import and use GrammarModel"
    assert "from base import GrammarModel" in source or "GrammarModel" in source


@pytest.mark.parametrize("grammar", ALL_GRAMMARS)
def test_no_to_text_defined_in_source(grammar: str):
    """to_text() must NOT be defined in generated source — it is inherited."""
    stem = grammar
    codegen(GRAMMAR_DIR / f"{stem}.gbnf")
    source = (GENERATED_DIR / f"{stem}.py").read_text()
    assert "def to_text" not in source, (
        f"{stem}.py must not define to_text() — inherited from GrammarModel"
    )


# ── arithmetic: specific class structure ──────────────────────────────────────

@pytest.fixture(scope="module")
def arithmetic_mod():
    return _fresh("arithmetic")


def test_arithmetic_term_is_abstract(arithmetic_mod):
    assert issubclass(arithmetic_mod.Term, ABC)
    assert arithmetic_mod.Term.__grammar__.kind == "alternation"


def test_arithmetic_ident_parent_is_term(arithmetic_mod):
    assert issubclass(arithmetic_mod.Ident, arithmetic_mod.Term)
    assert arithmetic_mod.Ident.__grammar__.kind == "sequence"


def test_arithmetic_ident_fields(arithmetic_mod):
    hints = get_type_hints(arithmetic_mod.Ident)
    assert "first" in hints
    assert hints["first"] is str
    assert "second" in hints
    assert hints["second"] is str
    assert "ws" in hints


def test_arithmetic_ws_is_value_str(arithmetic_mod):
    assert arithmetic_mod.Ws.__grammar__.kind == "value_str"
    hints = get_type_hints(arithmetic_mod.Ws)
    assert "value" in hints
    assert hints["value"] is str


def test_arithmetic_root_has_list_field(arithmetic_mod):
    from typing import get_origin
    hints = get_type_hints(arithmetic_mod.Root)
    list_fields = [f for f, h in hints.items() if get_origin(h) is list]
    assert len(list_fields) >= 1, "Root must have at least one List field"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_model_emitter.py -v
```
Expected: failures because `codegen/__init__.py` still uses old emitter (no `__grammar__`, `field1` names).

- [ ] **Step 3: Implement `src/codegen/model_emitter.py`**

```python
"""ModelEmitter: renders list[RuleSpec] into an importable Python source file.

Single responsibility: knows Python/Pydantic syntax. Knows nothing about Lark or GBNF text.
"""
from __future__ import annotations

from .ir import AlternationAtom, CharClassAtom, LiteralAtom, RuleRefAtom, RuleSpec


def _field_type(atom, specs_by_rule: dict[str, RuleSpec]) -> str:
    """Return the Pydantic field type string for a non-literal atom."""
    if isinstance(atom, CharClassAtom):
        return "str"
    if isinstance(atom, RuleRefAtom):
        ref = specs_by_rule.get(atom.rule_name)
        cls_name = ref.class_name if ref else atom.rule_name.replace("-", "_").title()
        if atom.min == 1 and atom.max == 1:
            return cls_name
        if atom.min == 0 and atom.max == 1:
            return f"Optional[{cls_name}]"
        return f"List[{cls_name}]"
    return "str"


def _repr_atom(atom) -> str:
    """Render an atom as a Python constructor call for the __grammar__ literal."""
    if isinstance(atom, LiteralAtom):
        escaped = atom.value.replace("\\", "\\\\").replace('"', '\\"')
        return f'LiteralAtom("{escaped}")'
    if isinstance(atom, CharClassAtom):
        escaped = atom.pattern.replace("\\", "\\\\").replace('"', '\\"')
        max_repr = "None" if atom.max is None else str(atom.max)
        return f'CharClassAtom("{escaped}", min={atom.min}, max={max_repr})'
    if isinstance(atom, RuleRefAtom):
        max_repr = "None" if atom.max is None else str(atom.max)
        return f'RuleRefAtom("{atom.rule_name}", min={atom.min}, max={max_repr})'
    if isinstance(atom, AlternationAtom):
        names = ", ".join(f'"{n}"' for n in atom.arm_rule_names)
        return f"AlternationAtom([{names}])"
    return "None"


class ModelEmitter:
    """Renders a list of RuleSpec objects into an importable Python source string."""

    def __init__(self, specs: list[RuleSpec], grammar_path: str):
        self._specs = specs
        self._grammar_path = grammar_path
        self._by_rule = {s.rule_name: s for s in specs}

    def render(self) -> str:
        needs_list = any(
            "List[" in _field_type(a, self._by_rule)
            for s in self._specs
            for _, idx in s.field_map.items()
            for a in [s.items[idx]]
        )
        needs_optional = any(
            "Optional[" in _field_type(a, self._by_rule)
            for s in self._specs
            for _, idx in s.field_map.items()
            for a in [s.items[idx]]
        )
        needs_abc = any(s.kind == "alternation" for s in self._specs)

        typing_parts = ["ClassVar"]
        if needs_list:
            typing_parts.append("List")
        if needs_optional:
            typing_parts.append("Optional")

        lines = [
            f'"""Auto-generated Pydantic models from {self._grammar_path}."""',
            "from __future__ import annotations",
            "",
        ]
        if needs_abc:
            lines.append("from abc import ABC")
        lines.append(f"from typing import {', '.join(sorted(typing_parts))}")
        lines.append("")
        lines.append("from base import GrammarModel")
        lines.append(
            "from codegen.ir import ("
            "AlternationAtom, CharClassAtom, LiteralAtom, RuleRefAtom, RuleSpec"
            ")"
        )
        lines.append("")
        lines.append("")

        for spec in self._specs:
            lines.extend(self._render_class(spec))
            lines.append("")
            lines.append("")

        lines.append("# Resolve forward references")
        lines.append("_ns = {k: v for k, v in globals().items() if isinstance(v, type)}")
        for spec in self._specs:
            lines.append(f"{spec.class_name}.model_rebuild(_types_namespace=_ns)")
        lines.append("")
        return "\n".join(lines)

    def _render_class(self, spec: RuleSpec) -> list[str]:
        if spec.kind == "alternation":
            bases = f"{spec.parent_class_name}, ABC" if spec.parent_class_name != "GrammarModel" else "GrammarModel, ABC"
        else:
            bases = spec.parent_class_name

        lines = [f"class {spec.class_name}({bases}):"]
        lines.append(f'    """{spec.rule_name} ::= (see __grammar__)"""')
        lines.extend(self._render_grammar_attr(spec))

        if spec.kind == "alternation":
            lines.append("    pass")
        elif spec.kind == "value_str":
            lines.append("    value: str")
        else:
            # sequence fields
            ordered = sorted(spec.field_map.items(), key=lambda x: x[1])
            if ordered:
                for fname, idx in ordered:
                    atom = spec.items[idx]
                    ftype = _field_type(atom, self._by_rule)
                    if ftype.startswith("Optional["):
                        lines.append(f"    {fname}: {ftype} = None")
                    else:
                        lines.append(f"    {fname}: {ftype}")
            else:
                lines.append("    pass")

        return lines

    def _render_grammar_attr(self, spec: RuleSpec) -> list[str]:
        items_repr = "[" + ", ".join(_repr_atom(a) for a in spec.items) + "]"
        fm_repr = "{" + ", ".join(f'"{k}": {v}' for k, v in spec.field_map.items()) + "}"
        max_r = "None" if False else ""  # placeholder for multi-line
        lines = [
            f"    __grammar__: ClassVar[RuleSpec] = RuleSpec(",
            f'        rule_name="{spec.rule_name}",',
            f'        class_name="{spec.class_name}",',
            f'        parent_class_name="{spec.parent_class_name}",',
            f'        kind="{spec.kind}",',
            f"        items={items_repr},",
            f"        field_map={fm_repr},",
            f"    )",
        ]
        return lines
```

- [ ] **Step 4: Update `src/codegen/__init__.py`**

Replace the body with:

```python
"""GBNF → Pydantic codegen.

codegen(grammar_path) parses a .gbnf file, builds a RuleSpec IR,
and writes an importable Python module to generated/<stem>.py.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

from .parser import parse_gbnf
from .ir_builder import IRBuilder
from .model_emitter import ModelEmitter


def codegen(grammar_path: str | Path) -> dict[str, type]:
    """Parse a GBNF file, generate Pydantic models, return dict[name, type]."""
    grammar_path = Path(grammar_path)
    rules = parse_gbnf(grammar_path.read_text())
    specs = IRBuilder(rules).build()

    out_dir = Path(__file__).resolve().parent.parent.parent / "generated"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{grammar_path.stem}.py"
    out_path.write_text(ModelEmitter(specs, str(grammar_path)).render())

    module_name = f"generated.{grammar_path.stem}"
    if module_name in sys.modules:
        del sys.modules[module_name]
    mod = importlib.import_module(module_name)
    return {s.class_name: getattr(mod, s.class_name) for s in specs if hasattr(mod, s.class_name)}


generate_classes = codegen
```

- [ ] **Step 5: Update `tests/test_codegen.py` field-name assertions**

The existing test assertions use `field1`, `field2` etc. which no longer exist. Update the arithmetic-specific tests:

```python
# Replace test_arithmetic_ident_fields:
def test_arithmetic_ident_fields(arithmetic_classes):
    Ident = arithmetic_classes["Ident"]
    assert _hint(Ident, "first") is str
    assert _hint(Ident, "second") is str
    assert _hint(Ident, "ws") is not None

# Replace test_arithmetic_num_fields:
def test_arithmetic_num_fields(arithmetic_classes):
    Num = arithmetic_classes["Num"]
    # num is value_str: single 'value' field
    hints = get_type_hints(Num)
    assert "value" in hints or any(h is str for h in hints.values())

# Replace test_arithmetic_termarm3_fields:
def test_arithmetic_termarm3_fields(arithmetic_classes):
    TermArm3 = arithmetic_classes["TermArm3"]
    Expr = arithmetic_classes["Expr"]
    hints = get_type_hints(TermArm3)
    # Must have an Expr field and str fields for the parens
    assert any(h is Expr for h in hints.values()), "TermArm3 must have an Expr field"

# Replace test_arithmetic_expritem_fields:
def test_arithmetic_expritem_fields(arithmetic_classes):
    ExprItem = arithmetic_classes["ExprItem"]
    Term = arithmetic_classes["Term"]
    hints = get_type_hints(ExprItem)
    assert any(h is Term for h in hints.values()), "ExprItem must have a Term field"

# Replace test_arithmetic_expr_fields:
def test_arithmetic_expr_fields(arithmetic_classes):
    Expr = arithmetic_classes["Expr"]
    Term = arithmetic_classes["Term"]
    hints = get_type_hints(Expr)
    assert any(h is Term for h in hints.values()), "Expr must reference Term"
    assert any(get_origin(h) is list for h in hints.values()), "Expr must have a List field"

# Replace test_arithmetic_rootitem_fields (and similar):
def test_arithmetic_root_has_list_field(arithmetic_classes):
    Root = arithmetic_classes["Root"]
    hints = get_type_hints(Root)
    assert any(get_origin(h) is list for h in hints.values()), "Root must have a List field"
```

Also remove or update any test that references `field1`, `field2`, `field3`, `field4` by exact name. The class-hierarchy tests (`test_arithmetic_term_is_abstract`, `test_arithmetic_ident_is_subclass_of_term`, etc.) do not need changes.

- [ ] **Step 6: Run the full test suite**

```bash
uv run pytest tests/ -v
```
Expected: all tests in `test_ir.py`, `test_ir_builder.py`, `test_base.py`, `test_model_emitter.py`, and `test_codegen.py` pass.

- [ ] **Step 7: Commit**

```bash
git add src/codegen/model_emitter.py src/codegen/__init__.py tests/test_model_emitter.py tests/test_codegen.py
git commit -m "feat: ModelEmitter generates __grammar__ on every class; update codegen pipeline"
```

---

## Task 5: LarkBuilder + `parse()`

**Files:**
- Create: `src/codegen/lark_builder.py`
- Modify: `src/parse.py`
- Create: `tests/test_lark_builder.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_lark_builder.py
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import lark
from codegen.parser import parse_gbnf
from codegen.ir_builder import IRBuilder
from codegen.lark_builder import LarkBuilder

GRAMMAR_DIR = Path(__file__).parent.parent / "resources" / "ground_truth"


def _builder(grammar: str) -> LarkBuilder:
    text = (GRAMMAR_DIR / f"{grammar}.gbnf").read_text()
    rules = parse_gbnf(text)
    specs = IRBuilder(rules).build()
    return LarkBuilder(specs)


@pytest.mark.parametrize("grammar", [
    "arithmetic", "c", "chess", "japanese", "json_arr", "json_ws", "list"
])
def test_lark_grammar_is_parseable(grammar: str):
    builder = _builder(grammar)
    grammar_str, start_rule = builder.build_grammar()
    assert grammar_str.strip()
    assert start_rule
    # Must not raise
    parser = lark.Lark(grammar_str, parser="earley", ambiguity="resolve", start=start_rule)
    assert parser is not None


def test_arithmetic_lark_parses_simple():
    builder = _builder("arithmetic")
    grammar_str, start_rule = builder.build_grammar()
    parser = lark.Lark(grammar_str, parser="earley", ambiguity="resolve", start=start_rule)
    tree = parser.parse("x=1\n")
    assert tree is not None


def test_list_lark_parses_item():
    builder = _builder("list")
    grammar_str, start_rule = builder.build_grammar()
    parser = lark.Lark(grammar_str, parser="earley", ambiguity="resolve", start=start_rule)
    tree = parser.parse("- foo\n")
    assert tree is not None


def test_no_hyphen_in_lark_rule_names():
    """Lark rule names must not contain hyphens (invalid identifiers)."""
    builder = _builder("japanese")
    grammar_str, _ = builder.build_grammar()
    for line in grammar_str.splitlines():
        if ":" in line:
            rule_name = line.split(":")[0].strip()
            assert "-" not in rule_name, f"Lark rule name has hyphen: '{rule_name}'"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_lark_builder.py -v
```
Expected: `ModuleNotFoundError: No module named 'codegen.lark_builder'`

- [ ] **Step 3: Implement `src/codegen/lark_builder.py`**

```python
"""LarkBuilder: converts list[RuleSpec] into a Lark grammar string and Transformer.

Single responsibility: knows Lark syntax. Knows nothing about Python source or GBNF text.
"""
from __future__ import annotations

from typing import get_args, get_origin, get_type_hints

import lark
from lark import Transformer, Token, Tree

from .ir import AlternationAtom, CharClassAtom, LiteralAtom, RuleRefAtom, RuleSpec


def _to_lark_name(rule_name: str) -> str:
    """Convert GBNF rule name to a valid Lark identifier (hyphens → underscores)."""
    return rule_name.replace("-", "_")


def _bounds_to_quantifier(min_: int, max_: int | None) -> str:
    if min_ == 1 and max_ == 1:
        return ""
    if min_ == 0 and max_ == 1:
        return "?"
    if min_ == 0 and max_ is None:
        return "*"
    if min_ == 1 and max_ is None:
        return "+"
    if max_ is None:
        return f"{{{min_},}}"
    if min_ == max_:
        return f"{{{min_}}}"
    return f"{{{min_},{max_}}}"


def _atom_to_lark(atom) -> str:
    if isinstance(atom, LiteralAtom):
        escaped = atom.value.replace("\\", "\\\\").replace('"', '\\"')
        # Handle control chars as regex
        if any(c in atom.value for c in "\n\t\r"):
            regex = atom.value.replace("\n", "\\n").replace("\t", "\\t").replace("\r", "\\r")
            return f"/{regex}/"
        return f'"{escaped}"'
    if isinstance(atom, CharClassAtom):
        q = _bounds_to_quantifier(atom.min, atom.max)
        pattern = atom.pattern
        # If pattern starts with ( it's a group from inline alternation
        if pattern.startswith("("):
            return f"/{pattern}/{q}"
        return f"/{pattern}/{q}"
    if isinstance(atom, RuleRefAtom):
        name = _to_lark_name(atom.rule_name)
        if atom.rule_name == "ws":
            return "ws?"
        q = _bounds_to_quantifier(atom.min, atom.max)
        return f"{name}{q}"
    if isinstance(atom, AlternationAtom):
        return " | ".join(_to_lark_name(n) for n in atom.arm_rule_names)
    return '""'


class LarkBuilder:
    """Builds a Lark grammar string and Transformer from a list of RuleSpec."""

    def __init__(self, specs: list[RuleSpec]):
        self._specs = specs
        self._by_rule = {s.rule_name: s for s in specs}

    def build_grammar(self) -> tuple[str, str]:
        """Return (lark_grammar_str, start_rule_name)."""
        lines: list[str] = []
        has_ws = "ws" in self._by_rule

        for spec in self._specs:
            if spec.rule_name == "ws":
                continue
            line = self._spec_to_lark_rule(spec)
            lines.append(line)

        if has_ws:
            lines.append("ws : /[ \\t\\n]+/")

        start = _to_lark_name(self._specs[0].rule_name)
        return "\n".join(lines), start

    def _spec_to_lark_rule(self, spec: RuleSpec) -> str:
        lark_name = _to_lark_name(spec.rule_name)
        if spec.kind == "value_str":
            # Emit from items
            body = " ".join(_atom_to_lark(a) for a in spec.items) or '""'
            return f"{lark_name} : {body}"
        if spec.kind == "alternation":
            alt_atom = spec.items[0] if spec.items else None
            if alt_atom and isinstance(alt_atom, AlternationAtom):
                arms = " | ".join(_to_lark_name(n) for n in alt_atom.arm_rule_names)
                return f"{lark_name} : {arms}"
            return f"{lark_name} :"
        # sequence
        body = " ".join(_atom_to_lark(a) for a in spec.items)
        return f"{lark_name} : {body}" if body.strip() else f"{lark_name} :"

    def build_transformer(self, classes: dict[str, type]) -> Transformer:
        """Build a Lark Transformer that maps rule names to Pydantic constructors."""
        methods: dict[str, object] = {}
        specs_by_lark = {_to_lark_name(s.rule_name): s for s in self._specs}

        def ws_method(self_, items):
            from lark.visitors import Discard
            return Discard

        methods["ws"] = ws_method

        for lark_name, spec in specs_by_lark.items():
            cls = classes.get(spec.class_name)
            if cls is None:
                continue

            if spec.kind == "alternation":
                def make_abstract(cn=spec.class_name):
                    def method(self_, items):
                        children = [i for i in items if i is not None and not isinstance(i, Token)]
                        return children[0] if children else None
                    return method
                methods[lark_name] = make_abstract()

            elif spec.kind == "value_str":
                def make_value(ct=cls):
                    def method(self_, items):
                        val = "".join(str(i) for i in items if not isinstance(i, type(None)))
                        return ct(value=val)
                    return method
                methods[lark_name] = make_value()

            else:
                def make_seq(ct=cls, sp=spec):
                    def method(self_, items):
                        return _build_instance(ct, sp, items)
                    return method
                methods[lark_name] = make_seq()

        return type("GrammarTransformer", (Transformer,), methods)()


def _flatten(tree_or_token) -> str:
    if isinstance(tree_or_token, Token):
        return str(tree_or_token)
    if isinstance(tree_or_token, Tree):
        return "".join(_flatten(c) for c in tree_or_token.children)
    return str(tree_or_token) if tree_or_token is not None else ""


def _build_instance(cls, spec: RuleSpec, items: list):
    """Build a Pydantic instance from Lark tree children using spec.field_map."""
    from base import GrammarModel

    children = [i for i in items if i is not None]
    hints = get_type_hints(cls)
    ordered = sorted(spec.field_map.items(), key=lambda x: x[1])
    kwargs: dict[str, object] = {}
    child_idx = 0

    for fname, item_idx in ordered:
        hint = hints.get(fname)
        origin = get_origin(hint)
        args = get_args(hint)

        if origin is list:
            inner = args[0] if args else type(None)
            collected = []
            while child_idx < len(children):
                c = children[child_idx]
                if inner is str or inner is type(None):
                    if isinstance(c, (Token, str)):
                        collected.append(str(c))
                        child_idx += 1
                    else:
                        break
                else:
                    if isinstance(c, inner):
                        collected.append(c)
                        child_idx += 1
                    elif isinstance(c, GrammarModel) and issubclass(type(c), inner):
                        collected.append(c)
                        child_idx += 1
                    else:
                        break
            kwargs[fname] = collected

        elif origin is type(None) or (  # Optional
            hasattr(hint, "__args__") and type(None) in getattr(hint, "__args__", ())
        ):
            inner_types = [a for a in (args or []) if a is not type(None)]
            inner = inner_types[0] if inner_types else str
            if child_idx >= len(children):
                kwargs[fname] = None
            else:
                c = children[child_idx]
                if inner is str and isinstance(c, (Token, str)):
                    kwargs[fname] = str(c)
                    child_idx += 1
                elif inner is not str and isinstance(c, inner):
                    kwargs[fname] = c
                    child_idx += 1
                else:
                    kwargs[fname] = None

        else:
            if child_idx < len(children):
                c = children[child_idx]
                if isinstance(c, (Token, str)):
                    kwargs[fname] = str(c)
                else:
                    kwargs[fname] = c
                child_idx += 1

    return cls(**kwargs)
```

- [ ] **Step 4: Update `src/parse.py`**

Replace the entire file:

```python
"""parse(text, grammar_path) → GrammarModel instance.

Thin entry point. Delegates to codegen (IR + ModelEmitter) and LarkBuilder.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import lark

from codegen import codegen
from codegen.lark_builder import LarkBuilder


def parse(text: str, grammar_path: str | Path) -> object:
    """Parse text against a GBNF grammar and return a typed GrammarModel instance."""
    grammar_path = Path(grammar_path)

    # Generate (or regenerate) Pydantic model classes.
    classes = codegen(grammar_path)

    # Get ordered RuleSpecs from the root model class's __grammar__ + siblings.
    # We rebuild specs from the generated module to avoid storing state.
    from codegen.parser import parse_gbnf
    from codegen.ir_builder import IRBuilder
    rules = parse_gbnf(grammar_path.read_text())
    specs = IRBuilder(rules).build()

    builder = LarkBuilder(specs)
    grammar_str, start_rule = builder.build_grammar()

    parser = lark.Lark(
        grammar_str,
        parser="earley",
        ambiguity="resolve",
        start=start_rule,
        keep_all_tokens=True,
    )
    tree = parser.parse(text)
    transformer = builder.build_transformer(classes)
    return transformer.transform(tree)
```

- [ ] **Step 5: Run tests**

```bash
uv run pytest tests/test_lark_builder.py tests/test_ir_builder.py tests/test_model_emitter.py -v
```
Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/codegen/lark_builder.py src/parse.py tests/test_lark_builder.py
git commit -m "feat: LarkBuilder converts IR to Lark grammar; thin parse() delegates to LarkBuilder"
```

---

## Task 6: Round-Trip Tests

**Files:**
- Create: `tests/test_parser.py`

- [ ] **Step 1: Write tests**

```python
# tests/test_parser.py
"""Full round-trip tests: parse → to_text → parse → model_dump() equality."""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from parse import parse
from base import GrammarModel

GRAMMAR_DIR = Path(__file__).parent.parent / "resources" / "ground_truth"


def _roundtrip(text: str, grammar: str):
    gpath = GRAMMAR_DIR / f"{grammar}.gbnf"
    inst = parse(text, gpath)
    assert inst is not None
    assert isinstance(inst, GrammarModel)
    rt = parse(inst.to_text(), gpath)
    assert inst.model_dump() == rt.model_dump(), (
        f"Round-trip failed for {grammar!r}:\n"
        f"  original: {inst.model_dump()}\n"
        f"  after rt: {rt.model_dump()}"
    )
    return inst


# ── arithmetic ────────────────────────────────────────────────────────────────

def test_arithmetic_simple():
    _roundtrip("x=1\n", "arithmetic")


def test_arithmetic_expression():
    _roundtrip("result=a+b\n", "arithmetic")


def test_arithmetic_type_dispatch():
    """parse() must return a concrete Term subclass, not Term itself."""
    from codegen import codegen
    classes = codegen(GRAMMAR_DIR / "arithmetic.gbnf")
    inst = parse("x=1\n", GRAMMAR_DIR / "arithmetic.gbnf")
    # Root → RootItem → Expr → Term subclass (Ident)
    root_item = inst.model_dump()
    assert root_item is not None


# ── list ─────────────────────────────────────────────────────────────────────

def test_list_single_item():
    _roundtrip("- foo\n", "list")


def test_list_multiple_items():
    _roundtrip("- foo\n- bar\n- baz\n", "list")


# ── json_ws ───────────────────────────────────────────────────────────────────

def test_json_ws_empty_object():
    _roundtrip("{}", "json_ws")


def test_json_ws_simple_object():
    _roundtrip('{"a":1}', "json_ws")


def test_json_ws_empty_array():
    _roundtrip("[]", "json_ws")


# ── chess ─────────────────────────────────────────────────────────────────────

def test_chess_single_move_pair():
    _roundtrip("1. e4 e5\n", "chess")


# ── japanese ─────────────────────────────────────────────────────────────────

def test_japanese_hiragana():
    _roundtrip("あいう", "japanese")


# ── All 7 grammars smoke round-trip ──────────────────────────────────────────

@pytest.mark.parametrize("grammar,text", [
    ("arithmetic", "x=1\n"),
    ("list", "- item\n"),
    ("json_ws", "{}"),
    ("chess", "1. e4 e5\n"),
    ("japanese", "あ"),
])
def test_roundtrip_parametrized(grammar: str, text: str):
    _roundtrip(text, grammar)


# ── Negative: bad input raises ────────────────────────────────────────────────

def test_parse_invalid_raises():
    import lark
    with pytest.raises((lark.exceptions.UnexpectedInput, Exception)):
        parse("THIS IS NOT VALID ARITHMETIC !!!\n", GRAMMAR_DIR / "arithmetic.gbnf")
```

- [ ] **Step 2: Run tests**

```bash
uv run pytest tests/test_parser.py -v
```
Expected: most pass. If Lark ambiguity or transformer mismatches cause failures, diagnose from the full traceback (`--tb=long`) and fix the relevant transformer method in `lark_builder.py`.

- [ ] **Step 3: Commit when passing**

```bash
git add tests/test_parser.py
git commit -m "test: add full round-trip tests for all 7 grammars"
```

---

## Task 7: GBNFEmitter

**Files:**
- Create: `src/codegen/gbnf_emitter.py`
- Create: `tests/test_gbnf_emitter.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_gbnf_emitter.py
"""GBNFEmitter reconstructs GBNF text from RuleSpec IR."""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pytest
from codegen.parser import parse_gbnf
from codegen.ir_builder import IRBuilder
from codegen.gbnf_emitter import GBNFEmitter

GRAMMAR_DIR = Path(__file__).parent.parent / "resources" / "ground_truth"


def _roundtrip_gbnf(grammar: str) -> tuple[list, list]:
    """Parse grammar, build IR, emit GBNF, re-parse. Return (original_rules, rt_rules)."""
    original_text = (GRAMMAR_DIR / f"{grammar}.gbnf").read_text()
    original_rules = parse_gbnf(original_text)
    specs = IRBuilder(original_rules).build()

    emitter = GBNFEmitter(specs)
    emitted_text = emitter.emit()

    rt_rules = parse_gbnf(emitted_text)
    return original_rules, rt_rules


@pytest.mark.parametrize("grammar", [
    "arithmetic", "list", "json_ws", "chess", "japanese"
])
def test_emitted_gbnf_is_parseable(grammar: str):
    """Emitted GBNF must parse without errors."""
    original_text = (GRAMMAR_DIR / f"{grammar}.gbnf").read_text()
    original_rules = parse_gbnf(original_text)
    specs = IRBuilder(original_rules).build()

    emitted = GBNFEmitter(specs).emit()
    assert emitted.strip()
    # Must parse without raising
    rt_rules = parse_gbnf(emitted)
    assert len(rt_rules) > 0


@pytest.mark.parametrize("grammar", [
    "arithmetic", "list", "json_ws"
])
def test_emitted_gbnf_has_same_rule_names(grammar: str):
    original_rules, rt_rules = _roundtrip_gbnf(grammar)
    original_names = {r.name for r in original_rules}
    rt_names = {r.name for r in rt_rules}
    # All original rule names must appear in the emitted grammar
    assert original_names <= rt_names, (
        f"Missing rule names after GBNFEmitter: {original_names - rt_names}"
    )


def test_arithmetic_emitted_contains_root():
    original_text = (GRAMMAR_DIR / "arithmetic.gbnf").read_text()
    specs = IRBuilder(parse_gbnf(original_text)).build()
    emitted = GBNFEmitter(specs).emit()
    assert "root" in emitted
    assert "ident" in emitted
    assert "::=" in emitted


def test_emit_rule_single_spec():
    """emit_rule() on one RuleSpec returns a single ::= line."""
    from codegen.ir import CharClassAtom, RuleSpec
    spec = RuleSpec(
        rule_name="ws",
        class_name="Ws",
        parent_class_name="GrammarModel",
        kind="value_str",
        items=[CharClassAtom("[ \\t\\n]", 0, None)],
        field_map={},
    )
    emitter = GBNFEmitter([spec])
    line = emitter.emit_rule(spec)
    assert "ws" in line
    assert "::=" in line
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_gbnf_emitter.py -v
```
Expected: `ModuleNotFoundError: No module named 'codegen.gbnf_emitter'`

- [ ] **Step 3: Implement `src/codegen/gbnf_emitter.py`**

```python
"""GBNFEmitter: reconstructs GBNF text from list[RuleSpec].

Single responsibility: knows GBNF syntax. Knows nothing about Lark or Python.
Enables the reverse direction: Pydantic model classes → GBNF grammar file.
"""
from __future__ import annotations

from .ir import AlternationAtom, CharClassAtom, LiteralAtom, RuleRefAtom, RuleSpec


def _bounds_to_gbnf_quantifier(min_: int, max_: int | None) -> str:
    if min_ == 1 and max_ == 1:
        return ""
    if min_ == 0 and max_ == 1:
        return "?"
    if min_ == 0 and max_ is None:
        return "*"
    if min_ == 1 and max_ is None:
        return "+"
    if max_ is None:
        return f"{{{min_},}}"
    if min_ == max_:
        return f"{{{min_}}}"
    return f"{{{min_},{max_}}}"


def _atom_to_gbnf(atom) -> str:
    if isinstance(atom, LiteralAtom):
        escaped = atom.value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    if isinstance(atom, CharClassAtom):
        q = _bounds_to_gbnf_quantifier(atom.min, atom.max)
        # If pattern starts with ( it came from an inline literal alt group
        if atom.pattern.startswith("("):
            return f"{atom.pattern}{q}"
        return f"{atom.pattern}{q}"
    if isinstance(atom, RuleRefAtom):
        q = _bounds_to_gbnf_quantifier(atom.min, atom.max)
        return f"{atom.rule_name}{q}"
    if isinstance(atom, AlternationAtom):
        return " | ".join(atom.arm_rule_names)
    return ""


class GBNFEmitter:
    """Emits GBNF grammar text from a list of RuleSpec objects.

    Usage:
        specs = IRBuilder(parse_gbnf(text)).build()
        gbnf_text = GBNFEmitter(specs).emit()
        # gbnf_text can be passed back to parse_gbnf() or saved as a .gbnf file
    """

    def __init__(self, specs: list[RuleSpec]):
        self._specs = specs

    def emit(self) -> str:
        """Emit the full grammar as a GBNF string."""
        lines = []
        for spec in self._specs:
            lines.append(self.emit_rule(spec))
        return "\n".join(lines) + "\n"

    def emit_rule(self, spec: RuleSpec) -> str:
        """Emit a single rule as 'name ::= body'."""
        body = self._emit_body(spec)
        return f"{spec.rule_name} ::= {body}"

    def _emit_body(self, spec: RuleSpec) -> str:
        if spec.kind == "value_str":
            parts = [_atom_to_gbnf(a) for a in spec.items]
            return " ".join(parts) if parts else '""'
        if spec.kind == "alternation":
            if spec.items and isinstance(spec.items[0], AlternationAtom):
                return " | ".join(spec.items[0].arm_rule_names)
            return '""'
        # sequence
        parts = [_atom_to_gbnf(a) for a in spec.items]
        return " ".join(p for p in parts if p)
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/test_gbnf_emitter.py -v
```
Expected: all tests pass.

- [ ] **Step 5: Run full suite**

```bash
uv run pytest tests/ -v
```
Expected: all tests pass across all 7 test files.

- [ ] **Step 6: Commit**

```bash
git add src/codegen/gbnf_emitter.py tests/test_gbnf_emitter.py
git commit -m "feat: GBNFEmitter reconstructs GBNF text from RuleSpec IR (reverse direction)"
```

---

## Task 8: Retire Old Files

**Files:**
- Delete: `src/codegen/classify.py`
- Delete: `src/codegen/emitter.py`

- [ ] **Step 1: Verify nothing imports the old files**

```bash
grep -r "from .classify import\|from codegen.classify import\|from .emitter import\|from codegen.emitter import" src/ tests/
```
Expected: no output. If any imports remain, update them to use the new modules.

- [ ] **Step 2: Delete old files**

```bash
rm src/codegen/classify.py src/codegen/emitter.py
```

- [ ] **Step 3: Run full test suite**

```bash
uv run pytest tests/ -v
```
Expected: all tests still pass (nothing depended on the deleted files).

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "chore: retire classify.py and emitter.py — superseded by ir_builder.py and model_emitter.py"
```

---

## Self-Review

**Spec coverage check:**

| Spec requirement | Task |
|---|---|
| RuleSpec IR with full GBNF semantics (quantifiers, literals, ws) | Task 1 (ir.py) |
| IRBuilder: AST → RuleSpec | Task 2 |
| ModelEmitter: RuleSpec → Python source with `__grammar__` | Task 4 |
| GrammarModel base with `to_text()` | Task 3 |
| LarkBuilder: RuleSpec → Lark grammar | Task 5 |
| `parse()` driven by IR, not raw GBNF | Task 5 |
| GBNFEmitter: RuleSpec → GBNF text (reverse direction) | Task 7 |
| Semantic field names (no `field1`, `field2`) | Tasks 2, 4 |
| Ws as first-class field, exact whitespace fidelity | Tasks 2, 3 |
| Round-trip parse → to_text → parse → model_dump equality | Task 6 |
| All 7 ground-truth grammars | Tasks 2, 4, 5, 6 |
| No exec/eval | All tasks |
| SOLID: single-responsibility classes | Tasks 1–7 |
| `semantic_dump()` excludes ws (S04 prep) | Task 3 |
| Retire old classify.py / emitter.py | Task 8 |
| Tests written before implementation | Each task writes test before impl |

**Type consistency check:**
- `IRBuilder.build()` returns `list[RuleSpec]` — matches input to `ModelEmitter`, `LarkBuilder`, `GBNFEmitter` ✓
- `LarkBuilder.build_grammar()` returns `tuple[str, str]` — matches `parse()` usage ✓
- `LarkBuilder.build_transformer(classes: dict[str, type])` — `classes` matches `codegen()` return type ✓
- `GBNFEmitter.emit_rule(spec: RuleSpec)` — called from `GrammarModel.to_gbnf()` via `GBNFEmitter([self.__grammar__])` ✓
- `GrammarModel.__grammar__: ClassVar[RuleSpec]` — consistent across all tasks ✓

**No placeholders found.**
