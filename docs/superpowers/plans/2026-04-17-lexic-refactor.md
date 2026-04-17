# Lexic Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restructure Lexic into a proper `lexic` package, refactor the IR atom types for clarity, simplify all emitters, restructure tests into unit/integration/property layers, and improve CharClassAtom field naming.

**Architecture:** Three sequential phases — Part A (package rename + IR refactor + emitter simplification + transformer extraction), Part B (test restructuring + generator), Part C (semantic field naming). Each phase leaves `uv run pytest tests/ -v` green before the next begins.

**Tech Stack:** Python 3.12, Pydantic v2, Lark, uv, pytest, hypothesis, exrex

**Spec:** `docs/superpowers/specs/2026-04-17-refactor-ir-tests-naming-design.md`

---

## PART A — Package Rename, IR Refactor, Emitter Simplification

---

### Task 1: Rename `src/` → `src/lexic/` and update all imports

**Files:**
- Create: `src/lexic/__init__.py`
- Move: all `src/*.py` and `src/codegen/**` → `src/lexic/` equivalents
- Modify: `pyproject.toml`
- Modify: `src/lexic/codegen/model_emitter.py` (template strings)
- Modify: all test files (import paths)

- [ ] **Step 1: Verify baseline**

```bash
uv run pytest tests/ -q
```
Expected: `220 passed`

- [ ] **Step 2: Create the new directory structure**

```bash
mkdir -p src/lexic/codegen
touch src/lexic/__init__.py src/lexic/codegen/__init__.py
```

- [ ] **Step 3: Copy source files into src/lexic/**

```bash
cp src/base.py src/lexic/base.py
cp src/parse.py src/lexic/parse.py
cp src/codegen/ast.py src/lexic/codegen/ast.py
cp src/codegen/parser.py src/lexic/codegen/parser.py
cp src/codegen/ir.py src/lexic/codegen/ir.py
cp src/codegen/ir_builder.py src/lexic/codegen/ir_builder.py
cp src/codegen/model_emitter.py src/lexic/codegen/model_emitter.py
cp src/codegen/gbnf_emitter.py src/lexic/codegen/gbnf_emitter.py
cp src/codegen/lark_builder.py src/lexic/codegen/lark_builder.py
cp src/codegen/__init__.py src/lexic/codegen/__init__.py
```

- [ ] **Step 4: Update internal imports in src/lexic/ files**

In `src/lexic/base.py`, change:
```python
# OLD
from codegen.ir import LiteralAtom, RuleRefAtom, RuleSpec
```
```python
# NEW
from lexic.codegen.ir import LiteralAtom, RuleRefAtom, RuleSpec
```
Also in `base.py`, the lazy import in `to_gbnf`:
```python
# OLD
from codegen.gbnf_emitter import GBNFEmitter
# NEW
from lexic.codegen.gbnf_emitter import GBNFEmitter
```

In `src/lexic/parse.py`, change all imports:
```python
# OLD
from base import GrammarModel
from codegen import codegen
from codegen.ir_builder import IRBuilder
from codegen.lark_builder import LarkBuilder
from codegen.parser import parse_gbnf
# NEW
from lexic.base import GrammarModel
from lexic.codegen import codegen
from lexic.codegen.ir_builder import IRBuilder
from lexic.codegen.lark_builder import LarkBuilder
from lexic.codegen.parser import parse_gbnf
```

In `src/lexic/codegen/__init__.py`, change:
```python
# OLD
from .ir_builder import IRBuilder
from .model_emitter import ModelEmitter
from .parser import parse_gbnf
# NEW  (same relative imports — already correct inside package)
```
No change needed — relative imports still work.

In `src/lexic/codegen/ir_builder.py`, change:
```python
# OLD
from .ast import Alternation, CharClass, Group, Item, Literal, Rule, RuleRef, Sequence
from .ir import (AlternationAtom, Atom, CharClassAtom, LiteralAtom, RuleRefAtom, RuleSpec)
# NEW — same relative imports, no change needed
```

In `src/lexic/codegen/model_emitter.py`, update the two template strings:
```python
# OLD
lines.append("from base import GrammarModel")
lines.append(f"from codegen.ir import {ir_imports}")
# NEW
lines.append("from lexic.base import GrammarModel")
lines.append(f"from lexic.codegen.ir import {ir_imports}")
```

In `src/lexic/codegen/lark_builder.py`, update:
```python
# OLD (in _build_instance)
from base import GrammarModel
# NEW
from lexic.base import GrammarModel
```

- [ ] **Step 5: Write src/lexic/__init__.py public API**

```python
"""Lexic — GBNF grammar engine."""
from lexic.parse import parse
from lexic.codegen import codegen

__all__ = ["parse", "codegen"]
```

- [ ] **Step 6: Update pyproject.toml**

```toml
[tool.hatch.build.targets.wheel]
packages = ["src/lexic"]
```

Remove the `[tool.hatch.build.targets.wheel.force-include]` section entirely.

Also add pythonpath to pytest config if not present:
```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]
python_files = ["test_*.py"]
python_classes = ["Test*"]
python_functions = ["test_*"]
```

- [ ] **Step 7: Update all test file imports**

In every file under `tests/`, replace:
```python
from codegen.ir import        →  from lexic.codegen.ir import
from codegen.ir_builder import →  from lexic.codegen.ir_builder import
from codegen.parser import    →  from lexic.codegen.parser import
from codegen.gbnf_emitter import → from lexic.codegen.gbnf_emitter import
from codegen.lark_builder import → from lexic.codegen.lark_builder import
from codegen import codegen   →  from lexic.codegen import codegen
from base import GrammarModel →  from lexic.base import GrammarModel
from parse import parse       →  from lexic.parse import parse
```

```bash
find tests/ -name "*.py" -exec sed -i \
  -e 's/from codegen\.ir import/from lexic.codegen.ir import/g' \
  -e 's/from codegen\.ir_builder import/from lexic.codegen.ir_builder import/g' \
  -e 's/from codegen\.parser import/from lexic.codegen.parser import/g' \
  -e 's/from codegen\.gbnf_emitter import/from lexic.codegen.gbnf_emitter import/g' \
  -e 's/from codegen\.lark_builder import/from lexic.codegen.lark_builder import/g' \
  -e 's/from codegen import codegen/from lexic.codegen import codegen/g' \
  -e 's/from base import GrammarModel/from lexic.base import GrammarModel/g' \
  -e 's/from parse import parse/from lexic.parse import parse/g' \
  {} +
```

- [ ] **Step 8: Regenerate grammar files with new import paths**

```bash
uv run python -c "
from pathlib import Path
from lexic.codegen import codegen
for p in sorted(Path('resources/ground_truth').glob('*.gbnf')):
    print(f'Generating {p.stem}...')
    codegen(p)
print('Done.')
"
```
Expected: seven grammar names printed, `generated/*.py` now contain `from lexic.base import GrammarModel`.

- [ ] **Step 9: Remove old src/ files**

```bash
rm src/base.py src/parse.py
rm -rf src/codegen/
```

- [ ] **Step 10: Run tests**

```bash
uv run pytest tests/ -q
```
Expected: `220 passed`

- [ ] **Step 11: Commit**

```bash
git add -A
git commit -m "refactor: rename src/ to src/lexic/ — proper installable package"
```

---

### Task 2: Extract `lexic/utils/` (escapes + quantifiers)

**Files:**
- Create: `src/lexic/utils/__init__.py`
- Create: `src/lexic/utils/escapes.py`
- Create: `src/lexic/utils/quantifiers.py`
- Modify: `src/lexic/codegen/lark_builder.py`
- Modify: `src/lexic/codegen/gbnf_emitter.py`
- Modify: `src/lexic/base.py`

- [ ] **Step 1: Create utils package with escapes module**

```bash
mkdir -p src/lexic/utils
touch src/lexic/utils/__init__.py
```

`src/lexic/utils/escapes.py`:
```python
"""GBNF escape sequence decoding."""
from __future__ import annotations


def decode_gbnf_escapes(s: str) -> str:
    """Decode GBNF string escape sequences (\\n, \\t, \\r, \\", \\\\) to real chars."""
    return (
        s.replace("\\\\", "\x00BS\x00")
        .replace("\\n", "\n")
        .replace("\\t", "\t")
        .replace("\\r", "\r")
        .replace('\\"', '"')
        .replace("\x00BS\x00", "\\")
    )
```

- [ ] **Step 2: Create quantifiers module**

`src/lexic/utils/quantifiers.py`:
```python
"""IR quantifier bound utilities."""
from __future__ import annotations


def bounds_to_quantifier(min_: int, max_: int | None) -> str:
    """Convert (min, max) bounds to a GBNF/Lark quantifier string."""
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
```

- [ ] **Step 3: Wire escapes into lark_builder.py**

In `src/lexic/codegen/lark_builder.py`, add at top:
```python
from lexic.utils.escapes import decode_gbnf_escapes
from lexic.utils.quantifiers import bounds_to_quantifier
```

Delete the `_decode_gbnf_escapes` function definition (lines 40–55).
Delete the `_bounds_to_quantifier` function definition.

Replace all calls to `_decode_gbnf_escapes(` with `decode_gbnf_escapes(`.
Replace all calls to `_bounds_to_quantifier(` with `bounds_to_quantifier(`.

- [ ] **Step 4: Wire quantifiers into gbnf_emitter.py**

In `src/lexic/codegen/gbnf_emitter.py`, add at top:
```python
from lexic.utils.quantifiers import bounds_to_quantifier
```

Delete the `_bounds_to_gbnf_quantifier` function definition.
Replace all calls to `_bounds_to_gbnf_quantifier(` with `bounds_to_quantifier(`.

- [ ] **Step 5: Wire escapes into base.py**

In `src/lexic/base.py`, add at top:
```python
from lexic.utils.escapes import decode_gbnf_escapes
```

In `to_text()`, replace the inline escape block (lines 47–55):
```python
# OLD
decoded = (
    atom.value.replace("\\\\", "\x00BS\x00")
    .replace("\\n", "\n")
    .replace("\\t", "\t")
    .replace("\\r", "\r")
    .replace('\\"', '"')
    .replace("\x00BS\x00", "\\")
)
# NEW
decoded = decode_gbnf_escapes(atom.value)
```

- [ ] **Step 6: Run tests**

```bash
uv run pytest tests/ -q
```
Expected: `220 passed`

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "refactor: extract decode_gbnf_escapes and bounds_to_quantifier to lexic/utils/"
```

---

### Task 3: Create `lexic/ir/` package — split codegen/ir.py

**Files:**
- Create: `src/lexic/ir/__init__.py`
- Create: `src/lexic/ir/atoms.py`
- Create: `src/lexic/ir/spec.py`
- Delete: `src/lexic/codegen/ir.py`
- Modify: `src/lexic/base.py`, `src/lexic/codegen/ir_builder.py`, `src/lexic/codegen/model_emitter.py`, `src/lexic/codegen/gbnf_emitter.py`, `src/lexic/codegen/lark_builder.py`

- [ ] **Step 1: Create ir/atoms.py with current 4 atom types**

```bash
mkdir -p src/lexic/ir
```

`src/lexic/ir/atoms.py`:
```python
"""IR atom dataclasses for the GBNF → Pydantic pipeline."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class LiteralAtom:
    """A quoted string literal. Structural glue — never a Pydantic field."""
    value: str


@dataclass
class CharClassAtom:
    """A character class bracket expression with quantifier bounds, e.g. [a-z]{1,1}."""
    pattern: str
    min: int
    max: int | None


@dataclass
class RuleRefAtom:
    """A reference to another rule with quantifier bounds."""
    rule_name: str
    min: int
    max: int | None


@dataclass
class AlternationAtom:
    """Arm rule names for a top-level alternation rule (kind='alternation' only)."""
    arm_rule_names: list[str]


Atom = LiteralAtom | CharClassAtom | RuleRefAtom | AlternationAtom
```

- [ ] **Step 2: Create ir/spec.py**

`src/lexic/ir/spec.py`:
```python
"""RuleSpec — canonical representation of one GBNF rule."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from lexic.ir.atoms import Atom


@dataclass
class RuleSpec:
    """Complete specification of one GBNF rule consumed by all emitters."""
    rule_name: str
    class_name: str
    parent_class_name: str
    kind: Literal["sequence", "alternation", "value_str"]
    items: list[Atom] = field(default_factory=list)
    field_map: dict[str, int] = field(default_factory=dict)
```

- [ ] **Step 3: Create ir/__init__.py**

`src/lexic/ir/__init__.py`:
```python
"""Public IR surface — import everything from here."""
from lexic.ir.atoms import (
    Atom,
    AlternationAtom,
    CharClassAtom,
    LiteralAtom,
    RuleRefAtom,
)
from lexic.ir.spec import RuleSpec

__all__ = [
    "Atom",
    "AlternationAtom",
    "CharClassAtom",
    "LiteralAtom",
    "RuleRefAtom",
    "RuleSpec",
]
```

- [ ] **Step 4: Update all imports to use lexic.ir**

In `src/lexic/base.py`:
```python
# OLD
from lexic.codegen.ir import LiteralAtom, RuleRefAtom, RuleSpec
# NEW
from lexic.ir import LiteralAtom, RuleRefAtom, RuleSpec
```

In `src/lexic/codegen/ir_builder.py`:
```python
# OLD
from .ir import (AlternationAtom, Atom, CharClassAtom, LiteralAtom, RuleRefAtom, RuleSpec)
# NEW
from lexic.ir import AlternationAtom, Atom, CharClassAtom, LiteralAtom, RuleRefAtom, RuleSpec
```

In `src/lexic/codegen/model_emitter.py`:
```python
# OLD
from .ir import AlternationAtom, CharClassAtom, LiteralAtom, RuleRefAtom, RuleSpec
# NEW
from lexic.ir import AlternationAtom, CharClassAtom, LiteralAtom, RuleRefAtom, RuleSpec
```
Also update the template string:
```python
# OLD
lines.append(f"from lexic.codegen.ir import {ir_imports}")
# NEW
lines.append(f"from lexic.ir import {ir_imports}")
```

In `src/lexic/codegen/gbnf_emitter.py`:
```python
# OLD
from .ir import AlternationAtom, CharClassAtom, LiteralAtom, RuleRefAtom, RuleSpec
# NEW
from lexic.ir import AlternationAtom, CharClassAtom, LiteralAtom, RuleRefAtom, RuleSpec
```

In `src/lexic/codegen/lark_builder.py`:
```python
# OLD
from .ir import AlternationAtom, CharClassAtom, LiteralAtom, RuleRefAtom, RuleSpec
# NEW
from lexic.ir import AlternationAtom, CharClassAtom, LiteralAtom, RuleRefAtom, RuleSpec
```

In all test files:
```bash
find tests/ -name "*.py" -exec sed -i \
  's/from lexic\.codegen\.ir import/from lexic.ir import/g' {} +
```

- [ ] **Step 5: Delete codegen/ir.py**

```bash
rm src/lexic/codegen/ir.py
```

- [ ] **Step 6: Regenerate grammar files**

```bash
uv run python -c "
from pathlib import Path
from lexic.codegen import codegen
for p in sorted(Path('resources/ground_truth').glob('*.gbnf')):
    codegen(p)
print('Done.')
"
```

Verify `generated/arithmetic.py` now contains `from lexic.ir import`.

- [ ] **Step 7: Run tests**

```bash
uv run pytest tests/ -q
```
Expected: `220 passed`

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "refactor: create lexic/ir/ package, split atoms.py + spec.py from codegen/ir.py"
```

---

### Task 4: Add three new atom types + unit tests

**Files:**
- Modify: `src/lexic/ir/atoms.py`
- Modify: `src/lexic/ir/__init__.py`

- [ ] **Step 1: Write failing tests for new atom types**

Create `tests/test_new_atoms.py` (temporary location — will be moved in Task 10):
```python
"""Tests for the three new IR atom types."""
from __future__ import annotations
import pytest
from lexic.ir import (
    QuantifiedLiteralAtom,
    InlineRegexAtom,
    InlineAlternationAtom,
)


def test_quantified_literal_atom_fields():
    a = QuantifiedLiteralAtom(value="-", min=0, max=1)
    assert a.value == "-"
    assert a.min == 0
    assert a.max == 1


def test_inline_regex_atom_has_both_fields():
    a = InlineRegexAtom(regex="(true|false|null)", gbnf='("true"|"false"|"null")', min=1, max=1)
    assert a.regex == "(true|false|null)"
    assert a.gbnf == '("true"|"false"|"null")'
    assert a.min == 1
    assert a.max == 1


def test_inline_alternation_atom_fields():
    a = InlineAlternationAtom(arm_rule_names=["pawn", "nonpawn", "castle"])
    assert a.arm_rule_names == ["pawn", "nonpawn", "castle"]


def test_atom_union_includes_new_types():
    from lexic.ir.atoms import Atom
    import typing
    args = typing.get_args(Atom)
    names = {a.__name__ for a in args}
    assert "QuantifiedLiteralAtom" in names
    assert "InlineRegexAtom" in names
    assert "InlineAlternationAtom" in names
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_new_atoms.py -v
```
Expected: `ImportError` — `QuantifiedLiteralAtom` not defined.

- [ ] **Step 3: Add new atom types to atoms.py**

In `src/lexic/ir/atoms.py`, add after `AlternationAtom`:
```python
@dataclass
class QuantifiedLiteralAtom:
    """A quoted literal with a quantifier — must be a Pydantic field.

    e.g. "-"? becomes QuantifiedLiteralAtom(value="-", min=0, max=1).
    Replaces the CharClassAtom('"-"', 0, 1) kludge.
    """
    value: str
    min: int
    max: int | None


@dataclass
class InlineRegexAtom:
    """An inlined group compiled to both regex and GBNF forms at IR build time.

    regex: ready for Lark /regex/ terminal.
    gbnf:  ready for GBNFEmitter, e.g. ("true"|"false"|"null").
    Replaces CharClassAtom('("true"|...)', ...) and the _normalize hack.
    """
    regex: str
    gbnf: str
    min: int
    max: int | None


@dataclass
class InlineAlternationAtom:
    """Inline alternation inside a sequence, e.g. (pawn | nonpawn | castle).

    Only valid inside kind='sequence' RuleSpecs. Always in field_map.
    No quantifier — quantified inline alternations become helper rules.
    Replaces the AlternationAtom dual-contract problem.
    """
    arm_rule_names: list[str]
```

Update the `Atom` union at the bottom:
```python
Atom = (
    LiteralAtom
    | CharClassAtom
    | QuantifiedLiteralAtom
    | InlineRegexAtom
    | RuleRefAtom
    | AlternationAtom
    | InlineAlternationAtom
)
```

- [ ] **Step 4: Export from ir/__init__.py**

Add to `src/lexic/ir/__init__.py`:
```python
from lexic.ir.atoms import (
    Atom,
    AlternationAtom,
    CharClassAtom,
    InlineAlternationAtom,
    InlineRegexAtom,
    LiteralAtom,
    QuantifiedLiteralAtom,
    RuleRefAtom,
)
```

Update `__all__` to include the three new names.

- [ ] **Step 5: Run tests**

```bash
uv run pytest tests/test_new_atoms.py tests/ -q
```
Expected: `224 passed` (4 new + 220 existing)

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat: add QuantifiedLiteralAtom, InlineRegexAtom, InlineAlternationAtom to lexic/ir/"
```

---

### Task 5: Extend emitters to handle new atom types (additive)

Add `match` branches for the three new atoms to each emitter. Behaviour is unchanged for existing grammars — new branches are simply never triggered yet.

**Files:**
- Modify: `src/lexic/codegen/gbnf_emitter.py`
- Modify: `src/lexic/codegen/lark_builder.py`
- Modify: `src/lexic/codegen/model_emitter.py`

- [ ] **Step 1: Update gbnf_emitter.py _atom_to_gbnf**

Replace the existing `_atom_to_gbnf` function with:
```python
def _atom_to_gbnf(atom: Atom) -> str:
    """Convert an Atom to GBNF string representation."""
    if isinstance(atom, LiteralAtom):
        return f'"{atom.value}"'
    if isinstance(atom, CharClassAtom):
        q = bounds_to_quantifier(atom.min, atom.max)
        return f"{atom.pattern}{q}"
    if isinstance(atom, QuantifiedLiteralAtom):
        q = bounds_to_quantifier(atom.min, atom.max)
        return f'"{atom.value}"{q}'
    if isinstance(atom, InlineRegexAtom):
        q = bounds_to_quantifier(atom.min, atom.max)
        return f"{atom.gbnf}{q}"
    if isinstance(atom, RuleRefAtom):
        q = bounds_to_quantifier(atom.min, atom.max)
        return f"{atom.rule_name}{q}"
    if isinstance(atom, AlternationAtom):
        return " | ".join(atom.arm_rule_names)
    if isinstance(atom, InlineAlternationAtom):
        return "(" + " | ".join(atom.arm_rule_names) + ")"
    return ""
```

Add missing imports at top of file:
```python
from lexic.ir import (
    AlternationAtom, CharClassAtom, InlineAlternationAtom,
    InlineRegexAtom, LiteralAtom, QuantifiedLiteralAtom, RuleRefAtom, RuleSpec,
)
```

- [ ] **Step 2: Update lark_builder.py _atom_to_lark**

Add imports at top:
```python
from lexic.ir import (
    AlternationAtom, CharClassAtom, InlineAlternationAtom,
    InlineRegexAtom, LiteralAtom, QuantifiedLiteralAtom, RuleRefAtom, RuleSpec,
)
```

Replace `_atom_to_lark`:
```python
def _atom_to_lark(atom: Atom) -> str:
    if isinstance(atom, LiteralAtom):
        return _lark_literal(atom.value)
    if isinstance(atom, CharClassAtom):
        q = bounds_to_quantifier(atom.min, atom.max)
        normalized = _normalize_charclass_pattern(atom.pattern)
        safe = _escape_lark_regex(normalized)
        return f"/{safe}/{q}"
    if isinstance(atom, QuantifiedLiteralAtom):
        q = bounds_to_quantifier(atom.min, atom.max)
        decoded = decode_gbnf_escapes(atom.value)
        escaped = decoded.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"{q}'
    if isinstance(atom, InlineRegexAtom):
        q = bounds_to_quantifier(atom.min, atom.max)
        safe = _escape_lark_regex(atom.regex)
        return f"/{safe}/{q}"
    if isinstance(atom, RuleRefAtom):
        if atom.rule_name == "ws":
            return "ws?"
        q = bounds_to_quantifier(atom.min, atom.max)
        return f"{_to_lark_name(atom.rule_name)}{q}"
    if isinstance(atom, InlineAlternationAtom):
        return "(" + " | ".join(_to_lark_name(n) for n in atom.arm_rule_names) + ")"
    if isinstance(atom, AlternationAtom):
        return ""
    return '""'
```

Note: `_normalize_charclass_pattern` and `_escape_lark_regex` stay for now — they handle `CharClassAtom` only. The `is_complex_regex` heuristic is NOT needed for the new branches.

- [ ] **Step 3: Update model_emitter.py _field_type and _repr_atom**

In `_field_type`, add cases before the final `return "str"`:
```python
def _field_type(atom, specs_by_rule: dict[str, RuleSpec]) -> str:
    if isinstance(atom, (CharClassAtom, QuantifiedLiteralAtom, InlineRegexAtom)):
        return "str"
    if isinstance(atom, RuleRefAtom):
        ref = specs_by_rule.get(atom.rule_name)
        cls_name = ref.class_name if ref else atom.rule_name.replace("-", "_").title()
        if atom.min == 1 and atom.max == 1:
            return cls_name
        if atom.min == 0 and atom.max == 1:
            return f"Optional[{cls_name}]"
        return f"List[{cls_name}]"
    if isinstance(atom, InlineAlternationAtom):
        arm_cls_names = [
            specs_by_rule[n].class_name
            for n in atom.arm_rule_names
            if n in specs_by_rule
        ]
        parent_classes = {
            specs_by_rule[n].parent_class_name
            for n in atom.arm_rule_names
            if n in specs_by_rule
        }
        if len(parent_classes) == 1:
            parent = next(iter(parent_classes))
            if parent != "GrammarModel":
                return parent
        if arm_cls_names:
            return "Union[" + ", ".join(arm_cls_names) + "]"
        return "GrammarModel"
    if isinstance(atom, AlternationAtom):
        return "GrammarModel"
    return "str"
```

In `_repr_atom`, add cases:
```python
def _repr_atom(atom) -> str:
    if isinstance(atom, LiteralAtom):
        escaped = atom.value.replace("\\", "\\\\").replace('"', '\\"')
        return f'LiteralAtom("{escaped}")'
    if isinstance(atom, CharClassAtom):
        escaped = atom.pattern.replace("\\", "\\\\").replace('"', '\\"')
        max_repr = "None" if atom.max is None else str(atom.max)
        return f'CharClassAtom("{escaped}", min={atom.min}, max={max_repr})'
    if isinstance(atom, QuantifiedLiteralAtom):
        escaped = atom.value.replace("\\", "\\\\").replace('"', '\\"')
        max_repr = "None" if atom.max is None else str(atom.max)
        return f'QuantifiedLiteralAtom("{escaped}", min={atom.min}, max={max_repr})'
    if isinstance(atom, InlineRegexAtom):
        r = atom.regex.replace("\\", "\\\\").replace('"', '\\"')
        g = atom.gbnf.replace("\\", "\\\\").replace('"', '\\"')
        max_repr = "None" if atom.max is None else str(atom.max)
        return f'InlineRegexAtom("{r}", "{g}", min={atom.min}, max={max_repr})'
    if isinstance(atom, RuleRefAtom):
        max_repr = "None" if atom.max is None else str(atom.max)
        return f'RuleRefAtom("{atom.rule_name}", min={atom.min}, max={max_repr})'
    if isinstance(atom, AlternationAtom):
        names = ", ".join(f'"{n}"' for n in atom.arm_rule_names)
        return f"AlternationAtom([{names}])"
    if isinstance(atom, InlineAlternationAtom):
        names = ", ".join(f'"{n}"' for n in atom.arm_rule_names)
        return f"InlineAlternationAtom([{names}])"
    return "None"
```

Update `needs_union` scan to include `InlineAlternationAtom` fields.

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/ -q
```
Expected: `224 passed` (all existing + 4 new atom tests)

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: extend all emitters to handle new atom types (QuantifiedLiteralAtom, InlineRegexAtom, InlineAlternationAtom)"
```

---

### Task 6: Update IRBuilder to emit new atom types + fix bugs

**Files:**
- Modify: `src/lexic/codegen/ir_builder.py`

- [ ] **Step 1: Write failing tests for new IRBuilder behaviour**

Add to `tests/test_ir_builder.py`:
```python
def test_quantified_literal_atom_from_literal_with_quantifier():
    """"-"? in a grammar sequence should produce QuantifiedLiteralAtom, not CharClassAtom."""
    from lexic.ir import QuantifiedLiteralAtom
    # number in json_ws has "-"? at the start
    text = (GRAMMAR_DIR / "json_ws.gbnf").read_text()
    rules = parse_gbnf(text)
    specs = IRBuilder(rules).build()
    d = _by_rule(specs)
    number = d["number"]
    # First atom in number sequence should be QuantifiedLiteralAtom("-", 0, 1)
    first = number.items[0]
    assert isinstance(first, QuantifiedLiteralAtom), f"Expected QuantifiedLiteralAtom, got {type(first)}"
    assert first.value == "-"
    assert first.min == 0
    assert first.max == 1


def test_inline_alternation_atom_in_sequence():
    """(pawn | nonpawn | castle) in move should be InlineAlternationAtom."""
    from lexic.ir import InlineAlternationAtom
    text = (GRAMMAR_DIR / "chess.gbnf").read_text()
    rules = parse_gbnf(text)
    specs = IRBuilder(rules).build()
    d = _by_rule(specs)
    move = d["move"]
    inline_alts = [a for a in move.items if isinstance(a, InlineAlternationAtom)]
    assert len(inline_alts) == 1
    assert set(inline_alts[0].arm_rule_names) == {"pawn", "nonpawn", "castle"}


def test_inline_regex_atom_for_pure_literal_group():
    """("true"|"false"|"null") in json_ws value should be InlineRegexAtom."""
    from lexic.ir import InlineRegexAtom
    text = (GRAMMAR_DIR / "json_ws.gbnf").read_text()
    rules = parse_gbnf(text)
    specs = IRBuilder(rules).build()
    d = _by_rule(specs)
    # value-arm5 holds the ("true"|"false"|"null") group
    arm5 = d.get("value-arm5")
    assert arm5 is not None
    inline_regex = [a for a in arm5.items if isinstance(a, InlineRegexAtom)]
    assert len(inline_regex) >= 1
    assert "true" in inline_regex[0].regex
    assert "true" in inline_regex[0].gbnf


def test_quantifier_preserved_in_inline_group():
    """[0-9]{0,15} inside a group arm must not lose the {0,15} quantifier."""
    from lexic.ir import InlineRegexAtom
    text = (GRAMMAR_DIR / "json_ws.gbnf").read_text()
    rules = parse_gbnf(text)
    specs = IRBuilder(rules).build()
    d = _by_rule(specs)
    number = d["number"]
    # Find InlineRegexAtom containing [1-9][0-9]{0,15}
    regex_atoms = [a for a in number.items if isinstance(a, InlineRegexAtom)]
    assert any("{0,15}" in a.regex for a in regex_atoms), (
        f"No InlineRegexAtom with {{0,15}}. Atoms: {[a.regex for a in regex_atoms]}"
    )


def test_topo_sort_root_is_first():
    """Root rule must always be the first spec regardless of grammar order."""
    for grammar in ["arithmetic", "c", "chess", "japanese", "json_arr", "json_ws", "list"]:
        specs = _build(grammar)
        assert specs[0].rule_name == "root", f"{grammar}: first spec is {specs[0].rule_name}"
```

- [ ] **Step 2: Run failing tests**

```bash
uv run pytest tests/test_ir_builder.py::test_quantified_literal_atom_from_literal_with_quantifier tests/test_ir_builder.py::test_inline_alternation_atom_in_sequence tests/test_ir_builder.py::test_inline_regex_atom_for_pure_literal_group tests/test_ir_builder.py::test_quantifier_preserved_in_inline_group -v
```
Expected: all FAIL (currently produces `CharClassAtom` or `AlternationAtom`).

- [ ] **Step 3: Add _to_regex, _to_gbnf, _build_inline_regex helpers**

In `src/lexic/codegen/ir_builder.py`, add after `_group_to_regex` (keep old function temporarily):

```python
def _to_regex(group: Group) -> str:
    """Convert a GBNF Group to a regex pattern string for Lark terminals."""
    arms: list[str] = []
    for seq in group.alt.seqs:
        parts: list[str] = []
        for it in seq.items:
            if isinstance(it.atom, Literal):
                q = it.quantifier or ""          # BUG FIX: include quantifier
                parts.append(re.escape(it.atom.value) + q)
            elif isinstance(it.atom, CharClass):
                q = it.quantifier or ""
                parts.append(it.atom.pattern + q)
            elif isinstance(it.atom, Group):
                q = it.quantifier or ""
                parts.append(_to_regex(it.atom) + q)
            # RuleRef inside a group cannot be inlined — skip
        arms.append("".join(parts))
    body = "|".join(arms)
    return f"({body})" if len(arms) > 1 else body


def _to_gbnf(group: Group) -> str:
    """Convert a GBNF Group back to GBNF syntax for GBNFEmitter."""
    arms: list[str] = []
    for seq in group.alt.seqs:
        parts: list[str] = []
        for it in seq.items:
            if isinstance(it.atom, Literal):
                q = it.quantifier or ""
                parts.append(f'"{it.atom.value}"{q}')
            elif isinstance(it.atom, CharClass):
                q = it.quantifier or ""
                parts.append(it.atom.pattern + q)
            elif isinstance(it.atom, Group):
                q = it.quantifier or ""
                parts.append(_to_gbnf(it.atom) + q)
        arms.append("".join(parts))
    body = "|".join(arms)
    return f"({body})" if len(arms) > 1 else body


def _build_inline_regex(group: Group, min_: int, max_: int | None) -> "InlineRegexAtom":
    """Build an InlineRegexAtom from a pure-literal or mixed GBNF group."""
    from lexic.ir import InlineRegexAtom
    return InlineRegexAtom(
        regex=_to_regex(group),
        gbnf=_to_gbnf(group),
        min=min_,
        max=max_,
    )
```

- [ ] **Step 4: Update _seq_to_atoms — Literal with quantifier**

In `_seq_to_atoms`, find the `isinstance(item.atom, Literal)` block and replace:
```python
elif isinstance(item.atom, Literal):
    if item.quantifier in ("+", "*", "?"):
        min_, max_ = _quantifier_to_bounds(item.quantifier)
        atoms.append(
            CharClassAtom(
                pattern=f'"{item.atom.value}"',
                min=min_,
                max=max_,
            )
        )
    else:
        atoms.append(LiteralAtom(value=item.atom.value))
```
with:
```python
elif isinstance(item.atom, Literal):
    if item.quantifier is not None:
        min_, max_ = _quantifier_to_bounds(item.quantifier)
        atoms.append(QuantifiedLiteralAtom(value=item.atom.value, min=min_, max=max_))
    else:
        atoms.append(LiteralAtom(value=item.atom.value))
```

Add `QuantifiedLiteralAtom` to the import from `lexic.ir` at top of file.

- [ ] **Step 5: Update _seq_to_atoms — inline pure-literal group**

Find the "Inline literal alternation" block:
```python
# Inline literal alternation → treat as single char-class-like atom
if all(_is_pure_literal_seq(a) for a in inner_arms):
    atoms.append(
        CharClassAtom(
            pattern="("
            + "|".join(...)
            + ")",
            ...
        )
    )
    continue
```

Replace with:
```python
# Inline literal alternation → InlineRegexAtom with both regex and gbnf forms
if all(_is_pure_literal_seq(a) for a in inner_arms):
    atoms.append(_build_inline_regex(item.atom, min_, max_))
    continue
```

- [ ] **Step 6: Update _seq_to_atoms — inline alternation of named rules**

Find the "Inline union of named rules" block:
```python
if (
    item.quantifier is None
    and len(inner_arms) > 1
    and all(_is_single_ruleref(a) is not None for a in inner_arms)
):
    arm_names: list[str] = [
        cast(str, _is_single_ruleref(a)) for a in inner_arms
    ]
    atoms.append(AlternationAtom(arm_rule_names=arm_names))
    continue
```

Replace `AlternationAtom` with `InlineAlternationAtom`:
```python
if (
    item.quantifier is None
    and len(inner_arms) > 1
    and all(_is_single_ruleref(a) is not None for a in inner_arms)
):
    arm_names: list[str] = [cast(str, _is_single_ruleref(a)) for a in inner_arms]
    atoms.append(InlineAlternationAtom(arm_rule_names=arm_names))
    continue
```

Add `InlineAlternationAtom` to the import from `lexic.ir`.

- [ ] **Step 7: Update _build_rule for value_str — Literal with quantifier**

In `_build_rule`, inside the `value_str`/`pure_literal_alt` branch, find:
```python
elif isinstance(it.atom, Literal):
    if it.quantifier in ("+", "*", "?"):
        min_, max_ = _quantifier_to_bounds(it.quantifier)
        items.append(
            CharClassAtom(
                pattern=f'"{it.atom.value}"',
                min=min_,
                max=max_,
            )
        )
    else:
        items.append(LiteralAtom(it.atom.value))
```

Replace with:
```python
elif isinstance(it.atom, Literal):
    if it.quantifier is not None:
        min_, max_ = _quantifier_to_bounds(it.quantifier)
        items.append(QuantifiedLiteralAtom(value=it.atom.value, min=min_, max=max_))
    else:
        items.append(LiteralAtom(it.atom.value))
```

Also in the same branch, find:
```python
elif isinstance(it.atom, Group):
    min_, max_ = _quantifier_to_bounds(it.quantifier)
    pattern = _group_to_regex(it.atom, None)
    items.append(CharClassAtom(pattern=pattern, min=min_, max=max_))
```

Replace with:
```python
elif isinstance(it.atom, Group):
    min_, max_ = _quantifier_to_bounds(it.quantifier)
    items.append(_build_inline_regex(it.atom, min_, max_))
```

- [ ] **Step 8: Fix _topo_sort**

Replace the `_topo_sort` method:
```python
def _topo_sort(self, specs: list[RuleSpec]) -> list[RuleSpec]:
    """Order specs so parent classes appear before subclasses, with root first."""
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

    # Seed with root first so it always appears at index 0
    root_spec = next((s for s in specs if s.rule_name == "root"), None)
    if root_spec:
        visit(root_spec.class_name)
    for s in specs:
        visit(s.class_name)

    return ordered
```

- [ ] **Step 9: Run the new tests**

```bash
uv run pytest tests/test_ir_builder.py -v
```
Expected: all pass including the 5 new tests.

- [ ] **Step 10: Run full test suite**

```bash
uv run pytest tests/ -q
```
Expected: all pass (existing round-trip tests still work because the emitters handle both old CharClassAtom paths AND new atoms).

- [ ] **Step 11: Commit**

```bash
git add -A
git commit -m "feat: IRBuilder emits QuantifiedLiteralAtom, InlineRegexAtom, InlineAlternationAtom; fix quantifier loss bug; fix topo_sort"
```

---

### Task 7: Remove dead code from emitters

**Files:**
- Modify: `src/lexic/codegen/gbnf_emitter.py`
- Modify: `src/lexic/codegen/lark_builder.py`
- Modify: `src/lexic/codegen/ir_builder.py`
- Modify: `src/lexic/codegen/model_emitter.py`

- [ ] **Step 1: Delete _normalize_charclass_pattern_for_gbnf from gbnf_emitter.py**

Remove the entire `_normalize_charclass_pattern_for_gbnf` function (lines 12–35). It's no longer called — `InlineRegexAtom.gbnf` is used directly.

Verify `_atom_to_gbnf` no longer calls it (it shouldn't after Task 5).

- [ ] **Step 2: Delete is_complex_regex heuristic and _normalize_charclass_pattern from lark_builder.py**

The `CharClassAtom` branch in `_atom_to_lark` still calls `_normalize_charclass_pattern`. Since `CharClassAtom` now only holds true bracket expressions (never a compiled regex), simplify:

```python
if isinstance(atom, CharClassAtom):
    q = bounds_to_quantifier(atom.min, atom.max)
    safe = _escape_lark_regex(atom.pattern)
    return f"/{safe}/{q}"
```

Delete `_normalize_charclass_pattern` function entirely.
Delete the `is_complex_regex` variable and its conditional — it's gone from the `CharClassAtom` branch.

- [ ] **Step 3: Delete _group_to_regex from ir_builder.py**

Remove the `_group_to_regex` function. It's been replaced by `_to_regex` + `_build_inline_regex`.

- [ ] **Step 4: Collapse model_emitter scanning passes**

Replace the three separate scanning loops (`needs_list`, `needs_optional`, `needs_union`) with one:

```python
def _collect_typing_needs(specs: list[RuleSpec], by_rule: dict[str, RuleSpec]) -> dict[str, bool]:
    needs = {"List": False, "Optional": False, "Union": False}
    for s in specs:
        for fname, idx in s.field_map.items():
            t = _field_type(s.items[idx], by_rule)
            if "List[" in t:
                needs["List"] = True
            if "Optional[" in t:
                needs["Optional"] = True
            if "Union[" in t:
                needs["Union"] = True
    return needs
```

In `render()`, replace the three boolean assignments with:
```python
needs = _collect_typing_needs(self._specs, self._by_rule)
needs_list = needs["List"]
needs_optional = needs["Optional"]
needs_union = needs["Union"]
```

- [ ] **Step 5: Run tests**

```bash
uv run pytest tests/ -q
```
Expected: all pass

- [ ] **Step 6: Regenerate grammar files**

```bash
uv run python -c "
from pathlib import Path
from lexic.codegen import codegen
for p in sorted(Path('resources/ground_truth').glob('*.gbnf')):
    codegen(p)
print('Done.')
"
```

Inspect `generated/chess.py` — `Move` should now have `value: Union[Pawn, Nonpawn, Castle]` from `InlineAlternationAtom`, and `first: str` from `CharClassAtom("[+#]", 0, 1)`.

Inspect `generated/json_ws.py` — `Number.first` atom should now be `QuantifiedLiteralAtom`.

- [ ] **Step 7: Run integration tests**

```bash
uv run pytest tests/ -q
```
Expected: all pass

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "refactor: remove dead emitter code (_normalize, is_complex_regex, _group_to_regex); collapse model_emitter scanning passes"
```

---

### Task 8: Extract transformer to `lexic/codegen/transformer.py`

**Files:**
- Create: `src/lexic/codegen/transformer.py`
- Modify: `src/lexic/codegen/lark_builder.py`

- [ ] **Step 1: Create transformer.py with extracted code**

`src/lexic/codegen/transformer.py`:
```python
"""GrammarTransformer: builds a Lark Transformer from RuleSpec + Pydantic classes.

Extracted from lark_builder.py so it can be tested and evolved independently.
"""
from __future__ import annotations

from typing import get_args, get_origin, get_type_hints

from lark import Token, Transformer, Tree

from lexic.ir import (
    AlternationAtom,
    CharClassAtom,
    InlineAlternationAtom,
    InlineRegexAtom,
    LiteralAtom,
    QuantifiedLiteralAtom,
    RuleRefAtom,
    RuleSpec,
)
from lexic.utils.escapes import decode_gbnf_escapes


def _to_lark_name(rule_name: str) -> str:
    return rule_name.replace("-", "_").lower()


def _flatten(tree_or_token) -> str:
    if isinstance(tree_or_token, Token):
        return str(tree_or_token)
    if isinstance(tree_or_token, Tree):
        return "".join(_flatten(c) for c in tree_or_token.children)
    return str(tree_or_token) if tree_or_token is not None else ""


def _is_ws_ref(atom) -> bool:
    return isinstance(atom, RuleRefAtom) and atom.rule_name == "ws"


def _is_optional_char(atom) -> bool:
    return isinstance(atom, (CharClassAtom, QuantifiedLiteralAtom, InlineRegexAtom)) and atom.min == 0


def _build_instance(cls, spec: RuleSpec, items: list):
    """Build a Pydantic instance from Lark tree children using spec.field_map."""
    from lexic.base import GrammarModel

    children = [i for i in items if i is not None]
    ordered = sorted(spec.field_map.items(), key=lambda x: x[1])
    kwargs: dict[str, object] = {}
    child_idx = 0

    try:
        hints = get_type_hints(cls)
    except Exception:
        hints = {k: v for k, v in cls.__annotations__.items()}

    def _atom_for(item_idx: int):
        if 0 <= item_idx < len(spec.items):
            return spec.items[item_idx]
        return None

    for fname, item_idx in ordered:
        hint = hints.get(fname)
        origin = get_origin(hint)
        args = get_args(hint)
        atom = _atom_for(item_idx)

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
                    if isinstance(c, GrammarModel) and isinstance(c, inner):
                        collected.append(c)
                        child_idx += 1
                    elif isinstance(c, (Token, str)):
                        child_idx += 1
                    else:
                        break
            kwargs[fname] = collected

        elif origin is type(None) or (
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
            if hint is None:
                continue
            if child_idx < len(children):
                c = children[child_idx]
                if hint is str or hint is type(None):
                    if isinstance(c, (Token, str)):
                        kwargs[fname] = str(c)
                        child_idx += 1
                    elif _is_optional_char(atom):
                        kwargs[fname] = ""
                    else:
                        kwargs[fname] = str(c)
                        child_idx += 1
                else:
                    if isinstance(c, hint):
                        kwargs[fname] = c
                        child_idx += 1
                    elif _is_ws_ref(atom):
                        kwargs[fname] = hint(value="")
                    elif _is_optional_char(atom):
                        kwargs[fname] = ""
                    else:
                        kwargs[fname] = c
                        child_idx += 1
            else:
                if hint is str or hint is type(None):
                    kwargs[fname] = ""
                elif _is_ws_ref(atom):
                    kwargs[fname] = hint(value="")
                elif _is_optional_char(atom):
                    kwargs[fname] = ""

    return cls(**kwargs)


def _literal_is_quoted(lit_value: str) -> bool:
    decoded = decode_gbnf_escapes(lit_value)
    return not any(c in decoded for c in "\n\t\r")


def build_transformer(specs: list[RuleSpec], classes: dict[str, type]) -> Transformer:
    """Build a Lark Transformer that maps rule names to Pydantic constructors."""
    methods: dict[str, object] = {}
    specs_by_lark = {_to_lark_name(s.rule_name): s for s in specs}

    ws_cls = classes.get("Ws")

    def ws_method(self_, items):
        text = "".join(str(i) for i in items if i is not None)
        if ws_cls is not None:
            return ws_cls(value=text)
        return text

    methods["ws"] = ws_method

    for lark_name, spec in specs_by_lark.items():
        if spec.rule_name == "ws":
            continue
        cls = classes.get(spec.class_name)
        if cls is None:
            continue

        if spec.kind == "alternation":
            def make_abstract(cn=spec.class_name):
                def method(self_, items):
                    children = [
                        i for i in items
                        if i is not None and not isinstance(i, Token)
                    ]
                    return children[0] if children else None
                return method
            methods[lark_name] = make_abstract()

        elif spec.kind == "value_str":
            def make_value(ct=cls, sp=spec):
                def method(self_, items):
                    token_text = "".join(str(i) for i in items if i is not None)
                    result: list[str] = []
                    token_placed = False
                    for atom in sp.items:
                        if isinstance(atom, LiteralAtom) and _literal_is_quoted(atom.value):
                            result.append(decode_gbnf_escapes(atom.value))
                        elif not token_placed:
                            result.append(token_text)
                            token_placed = True
                    if not token_placed:
                        result.append(token_text)
                    return ct(value="".join(result))
                return method
            methods[lark_name] = make_value()

        else:
            def make_seq(ct=cls, sp=spec):
                def method(self_, items):
                    return _build_instance(ct, sp, items)
                return method
            methods[lark_name] = make_seq()

    return type("GrammarTransformer", (Transformer,), methods)()
```

- [ ] **Step 2: Update LarkBuilder.build_transformer to delegate**

Replace `build_transformer` in `lark_builder.py`:
```python
def build_transformer(self, classes: dict[str, type]) -> Transformer:
    """Build a Lark Transformer that maps rule names to Pydantic constructors."""
    from lexic.codegen.transformer import build_transformer
    return build_transformer(self._specs, classes)
```

Remove the now-unused imports and functions from `lark_builder.py`:
- `get_args, get_origin, get_type_hints` imports (if only used in transformer)
- `_flatten`, `_build_instance`, all `make_*` closures, `_literal_is_quoted`

- [ ] **Step 3: Run tests**

```bash
uv run pytest tests/ -q
```
Expected: all pass

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "refactor: extract transformer factory to lexic/codegen/transformer.py; lark_builder.py owns grammar string only"
```

---

## PART B — Test Restructuring

---

### Task 9: Create `tests/unit/lexic/` mirroring `src/lexic/`

**Files:** Create entire `tests/unit/` hierarchy; migrate existing tests.

- [ ] **Step 1: Create directory structure**

```bash
mkdir -p tests/unit/lexic/ir
mkdir -p tests/unit/lexic/utils
mkdir -p tests/unit/lexic/codegen
mkdir -p tests/integration
mkdir -p tests/property
touch tests/unit/__init__.py
touch tests/unit/lexic/__init__.py
touch tests/unit/lexic/ir/__init__.py
touch tests/unit/lexic/utils/__init__.py
touch tests/unit/lexic/codegen/__init__.py
touch tests/integration/__init__.py
touch tests/property/__init__.py
```

- [ ] **Step 2: Migrate test_ir.py → unit/lexic/ir/test_atoms.py + test_spec.py**

`tests/unit/lexic/ir/test_atoms.py` — move all atom dataclass tests from `tests/test_ir.py` here, plus the new atom tests from `tests/test_new_atoms.py`. Add:
```python
"""Unit tests for src/lexic/ir/atoms.py"""
from __future__ import annotations
import pytest
from lexic.ir import (
    Atom, AlternationAtom, CharClassAtom, InlineAlternationAtom,
    InlineRegexAtom, LiteralAtom, QuantifiedLiteralAtom, RuleRefAtom,
)
import typing


def test_literal_atom():
    a = LiteralAtom("=")
    assert a.value == "="


def test_char_class_atom():
    a = CharClassAtom("[a-z]", 1, 1)
    assert a.pattern == "[a-z]"
    assert a.min == 1
    assert a.max == 1


def test_char_class_atom_unbounded():
    a = CharClassAtom("[a-z]", 0, None)
    assert a.max is None


def test_rule_ref_atom():
    a = RuleRefAtom("ws", 1, 1)
    assert a.rule_name == "ws"


def test_alternation_atom():
    a = AlternationAtom(["a", "b", "c"])
    assert a.arm_rule_names == ["a", "b", "c"]


def test_quantified_literal_atom():
    a = QuantifiedLiteralAtom("-", 0, 1)
    assert a.value == "-"
    assert a.min == 0
    assert a.max == 1


def test_inline_regex_atom():
    a = InlineRegexAtom("(true|false)", '("true"|"false")', 1, 1)
    assert a.regex == "(true|false)"
    assert a.gbnf == '("true"|"false")'


def test_inline_alternation_atom():
    a = InlineAlternationAtom(["pawn", "nonpawn", "castle"])
    assert a.arm_rule_names == ["pawn", "nonpawn", "castle"]


def test_atom_union_contains_all_seven_types():
    args = {t.__name__ for t in typing.get_args(Atom)}
    assert args == {
        "LiteralAtom", "CharClassAtom", "QuantifiedLiteralAtom",
        "InlineRegexAtom", "RuleRefAtom", "AlternationAtom", "InlineAlternationAtom",
    }
```

`tests/unit/lexic/ir/test_spec.py`:
```python
"""Unit tests for src/lexic/ir/spec.py"""
from __future__ import annotations
from lexic.ir import RuleSpec, LiteralAtom, CharClassAtom, RuleRefAtom


def test_rulespec_defaults():
    spec = RuleSpec("ws", "Ws", "GrammarModel", "value_str")
    assert spec.items == []
    assert spec.field_map == {}


def test_rulespec_field_map_populated():
    spec = RuleSpec(
        "ident", "Ident", "GrammarModel", "sequence",
        items=[CharClassAtom("[a-z]", 1, 1), RuleRefAtom("ws", 1, 1)],
        field_map={"first": 0, "ws": 1},
    )
    assert spec.field_map["first"] == 0
    assert spec.field_map["ws"] == 1


def test_rulespec_kind_literals():
    for kind in ("sequence", "alternation", "value_str"):
        spec = RuleSpec("r", "R", "GrammarModel", kind)
        assert spec.kind == kind
```

- [ ] **Step 3: Migrate utils tests**

`tests/unit/lexic/utils/test_escapes.py`:
```python
"""Unit tests for src/lexic/utils/escapes.py"""
from lexic.utils.escapes import decode_gbnf_escapes


def test_newline():
    assert decode_gbnf_escapes("\\n") == "\n"


def test_tab():
    assert decode_gbnf_escapes("\\t") == "\t"


def test_carriage_return():
    assert decode_gbnf_escapes("\\r") == "\r"


def test_double_quote():
    assert decode_gbnf_escapes('\\"') == '"'


def test_backslash():
    assert decode_gbnf_escapes("\\\\") == "\\"


def test_mixed():
    assert decode_gbnf_escapes("a\\nb") == "a\nb"


def test_no_escapes():
    assert decode_gbnf_escapes("hello") == "hello"


def test_backslash_then_n_not_confused():
    # \\n should decode to \n (backslash + n literal), not newline
    # Input: 4-char string \\\\n (represents the text \\n)
    assert decode_gbnf_escapes("\\\\n") == "\\n"
```

`tests/unit/lexic/utils/test_quantifiers.py`:
```python
"""Unit tests for src/lexic/utils/quantifiers.py"""
from lexic.utils.quantifiers import bounds_to_quantifier


def test_required_singular():
    assert bounds_to_quantifier(1, 1) == ""


def test_optional():
    assert bounds_to_quantifier(0, 1) == "?"


def test_zero_or_more():
    assert bounds_to_quantifier(0, None) == "*"


def test_one_or_more():
    assert bounds_to_quantifier(1, None) == "+"


def test_exact():
    assert bounds_to_quantifier(3, 3) == "{3}"


def test_range():
    assert bounds_to_quantifier(2, 5) == "{2,5}"


def test_min_with_no_max():
    assert bounds_to_quantifier(2, None) == "{2,}"
```

- [ ] **Step 4: Migrate codegen unit tests**

Move the content of the existing test files into the new locations:

- `tests/test_ir_builder.py` → `tests/unit/lexic/codegen/test_ir_builder.py`
- `tests/test_model_emitter.py` → `tests/unit/lexic/codegen/test_model_emitter.py`
- `tests/test_gbnf_emitter.py` → `tests/unit/lexic/codegen/test_gbnf_emitter.py`
- `tests/test_lark_builder.py` → `tests/unit/lexic/codegen/test_lark_builder.py`
- `tests/test_parser.py` → `tests/unit/lexic/codegen/test_parser.py`
- `tests/test_base.py` → `tests/unit/lexic/test_base.py`

Create `tests/unit/lexic/codegen/test_ast.py`:
```python
"""Unit tests for src/lexic/codegen/ast.py"""
from lexic.codegen.ast import (
    Literal, CharClass, RuleRef, Group, Item, Sequence, Alternation, Rule,
)


def test_literal():
    assert Literal("=").value == "="


def test_charclass():
    assert CharClass("[a-z]").pattern == "[a-z]"


def test_ruleref():
    assert RuleRef("ws").name == "ws"


def test_item_with_quantifier():
    it = Item(Literal("x"), "?")
    assert it.quantifier == "?"


def test_item_bare():
    it = Item(Literal("x"), None)
    assert it.quantifier is None


def test_sequence():
    s = Sequence([Item(Literal("a"), None)])
    assert len(s.items) == 1


def test_alternation():
    a = Alternation([Sequence([]), Sequence([])])
    assert len(a.seqs) == 2


def test_rule():
    r = Rule("ws", Alternation([]))
    assert r.name == "ws"
```

Create `tests/unit/lexic/codegen/test_transformer.py`:
```python
"""Unit tests for src/lexic/codegen/transformer.py"""
from __future__ import annotations
from pathlib import Path
from lexic.codegen.parser import parse_gbnf
from lexic.codegen.ir_builder import IRBuilder
from lexic.codegen.lark_builder import LarkBuilder
from lexic.codegen import codegen
import lark

GRAMMAR_DIR = Path(__file__).parent.parent.parent.parent.parent / "resources" / "ground_truth"


def _parse_and_transform(text: str, grammar: str):
    gpath = GRAMMAR_DIR / f"{grammar}.gbnf"
    classes = codegen(gpath)
    rules = parse_gbnf(gpath.read_text())
    specs = IRBuilder(rules).build()
    builder = LarkBuilder(specs)
    grammar_str, start = builder.build_grammar()
    parser = lark.Lark(grammar_str, parser="earley", ambiguity="resolve", start=start)
    tree = parser.parse(text)
    transformer = builder.build_transformer(classes)
    return transformer.transform(tree)


def test_transformer_arithmetic_simple():
    result = _parse_and_transform("x=1\n", "arithmetic")
    assert result is not None
    assert result.to_text() == "x=1\n"


def test_transformer_chess_move():
    result = _parse_and_transform("1. e4 e5\n2. d4 d5\n", "chess")
    assert result is not None
    assert result.to_text() == "1. e4 e5\n2. d4 d5\n"


def test_transformer_ws_empty():
    result = _parse_and_transform("{}", "json_ws")
    assert result is not None
    assert result.to_text() == "{}"
```

- [ ] **Step 5: Migrate integration tests**

Move `tests/test_codegen.py` → `tests/integration/test_codegen.py` (update imports).
Move the `parse()` round-trip tests from `tests/test_parser.py` → `tests/integration/test_parse.py`.

- [ ] **Step 6: Delete old root-level test files**

```bash
rm tests/test_ir.py tests/test_ir_builder.py tests/test_model_emitter.py
rm tests/test_gbnf_emitter.py tests/test_lark_builder.py tests/test_parser.py
rm tests/test_base.py tests/test_codegen.py tests/test_new_atoms.py
```

- [ ] **Step 7: Run tests**

```bash
uv run pytest tests/ -q
```
Expected: all pass (same test count ± new ones added)

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "refactor: restructure tests into unit/lexic/, integration/ mirroring src/lexic/"
```

---

### Task 10: Add complex integration test cases

**Files:**
- Modify: `tests/integration/test_parse.py`
- Create: `tests/integration/test_gbnf_roundtrip.py`

- [ ] **Step 1: Add complex arithmetic cases**

In `tests/integration/test_parse.py`, add:
```python
def test_arithmetic_multi_assignment():
    _roundtrip("x=1\na=b\n", "arithmetic")


def test_arithmetic_nested_parens():
    _roundtrip("x=(a+b)\n", "arithmetic")


def test_arithmetic_deeply_nested_parens():
    _roundtrip("x=((a+b))\n", "arithmetic")


def test_arithmetic_multi_char_ident():
    _roundtrip("foo=bar\n", "arithmetic")
```

- [ ] **Step 2: Add json_ws complex cases**

```python
def test_json_ws_null_value():
    _roundtrip('{"k":null}', "json_ws")


def test_json_ws_true_value():
    _roundtrip('{"k":true}', "json_ws")


def test_json_ws_false_value():
    _roundtrip('{"k":false}', "json_ws")


def test_json_ws_number_decimal():
    _roundtrip('{"n":1}', "json_ws")


def test_json_ws_nested_object():
    _roundtrip('{"a":{"b":{}}}', "json_ws")


def test_json_ws_string_with_escaped_quote():
    _roundtrip('{"k":"a\\"b"}', "json_ws")


def test_json_ws_array_value():
    _roundtrip('{"k":[]}', "json_ws")
```

- [ ] **Step 3: Add json_arr cases**

```python
def test_json_arr_empty():
    _roundtrip("[\n]", "json_arr")


def test_json_arr_single_null():
    _roundtrip("[\nnull\n]", "json_arr")


def test_json_arr_multiple_values():
    _roundtrip('[\nnull\n,\ntrue\n,\nfalse\n]', "json_arr")
```

- [ ] **Step 4: Add chess complex cases**

```python
def test_chess_three_moves():
    _roundtrip("1. e4 e5\n2. d4 d5\n3. Nc3 Nf6\n", "chess")


def test_chess_castling():
    _roundtrip("1. O-O e5\n2. d4 d5\n", "chess")


def test_chess_check():
    _roundtrip("1. Nf3+ e5\n2. d4 d5\n", "chess")


def test_chess_checkmate():
    _roundtrip("1. Qh5 e5\n2. d4 d5\n", "chess")
```

- [ ] **Step 5: Add c grammar parse tests (currently zero)**

```python
def test_c_empty_function():
    _roundtrip("int foo(){}", "c")


def test_c_function_with_return():
    _roundtrip("int foo(){return 1;}", "c")


def test_c_function_with_param():
    _roundtrip("int add(int x){return x;}", "c")


def test_c_while_loop():
    _roundtrip("int foo(){while(x>0){x=x;}}", "c")


def test_c_if_statement():
    _roundtrip("int foo(){if(x>0){x=x;}}", "c")
```

- [ ] **Step 6: Add japanese and list cases**

```python
def test_japanese_five_chars():
    _roundtrip("あいうえお", "japanese")


def test_list_ten_items():
    _roundtrip("".join(f"- item{i}\n" for i in range(10)), "list")
```

- [ ] **Step 7: Create test_gbnf_roundtrip.py**

`tests/integration/test_gbnf_roundtrip.py`:
```python
"""GBNF round-trip tests: grammar → IR → GBNFEmitter → re-parse → same IR."""
from __future__ import annotations
from pathlib import Path
import pytest
from lexic.codegen.parser import parse_gbnf
from lexic.codegen.ir_builder import IRBuilder
from lexic.codegen.gbnf_emitter import GBNFEmitter

GRAMMAR_DIR = Path(__file__).parent.parent.parent / "resources" / "ground_truth"

ALL_GRAMMARS = ["arithmetic", "c", "chess", "japanese", "json_arr", "json_ws", "list"]


def _rule_names(specs):
    return {s.rule_name for s in specs}


@pytest.mark.parametrize("grammar", ALL_GRAMMARS)
def test_emitted_gbnf_parses(grammar: str):
    text = (GRAMMAR_DIR / f"{grammar}.gbnf").read_text()
    specs = IRBuilder(parse_gbnf(text)).build()
    emitted = GBNFEmitter(specs).emit()
    assert emitted.strip()
    rt_rules = parse_gbnf(emitted)
    assert len(rt_rules) > 0


@pytest.mark.parametrize("grammar", ALL_GRAMMARS)
def test_emitted_gbnf_has_same_rule_names(grammar: str):
    text = (GRAMMAR_DIR / f"{grammar}.gbnf").read_text()
    original_rules = parse_gbnf(text)
    specs = IRBuilder(original_rules).build()
    emitted = GBNFEmitter(specs).emit()
    rt_rules = parse_gbnf(emitted)
    original_names = {r.name for r in original_rules}
    rt_names = {r.name for r in rt_rules}
    assert original_names <= rt_names


@pytest.mark.parametrize("grammar", ALL_GRAMMARS)
def test_emitted_gbnf_produces_same_rule_count(grammar: str):
    text = (GRAMMAR_DIR / f"{grammar}.gbnf").read_text()
    specs = IRBuilder(parse_gbnf(text)).build()
    emitted = GBNFEmitter(specs).emit()
    rt_specs = IRBuilder(parse_gbnf(emitted)).build()
    assert len(specs) == len(rt_specs), (
        f"Rule count mismatch: original={len(specs)}, roundtrip={len(rt_specs)}"
    )
```

- [ ] **Step 8: Run all tests**

```bash
uv run pytest tests/ -q
```
Expected: all pass

- [ ] **Step 9: Commit**

```bash
git add -A
git commit -m "test: add complex integration tests for all 7 grammars; add GBNF round-trip tests"
```

---

### Task 11: Create `src/lexic/generate.py` + unit tests

**Files:**
- Create: `src/lexic/generate.py`
- Create: `tests/unit/lexic/test_generate.py`
- Modify: `src/lexic/__init__.py`

- [ ] **Step 1: Write failing tests**

`tests/unit/lexic/test_generate.py`:
```python
"""Unit tests for src/lexic/generate.py"""
from __future__ import annotations
import random
from pathlib import Path
from lexic.codegen.parser import parse_gbnf
from lexic.codegen.ir_builder import IRBuilder
from lexic.generate import generate
from lexic.parse import parse

GRAMMAR_DIR = Path(__file__).parent.parent.parent.parent / "resources" / "ground_truth"


def _specs(grammar: str) -> dict:
    text = (GRAMMAR_DIR / f"{grammar}.gbnf").read_text()
    return {s.rule_name: s for s in IRBuilder(parse_gbnf(text)).build()}


def test_generate_returns_string():
    specs = _specs("arithmetic")
    result = generate("root", specs, rng=random.Random(42))
    assert isinstance(result, str)
    assert len(result) > 0


def test_generate_arithmetic_is_parseable():
    specs = _specs("arithmetic")
    for seed in range(10):
        text = generate("root", specs, rng=random.Random(seed))
        inst = parse(text, GRAMMAR_DIR / "arithmetic.gbnf")
        assert inst.to_text() == text, f"Round-trip failed for seed={seed}: {text!r}"


def test_generate_list_is_parseable():
    specs = _specs("list")
    for seed in range(5):
        text = generate("root", specs, rng=random.Random(seed))
        inst = parse(text, GRAMMAR_DIR / "list.gbnf")
        assert inst.to_text() == text


def test_generate_japanese_is_parseable():
    specs = _specs("japanese")
    for seed in range(5):
        text = generate("root", specs, rng=random.Random(seed))
        inst = parse(text, GRAMMAR_DIR / "japanese.gbnf")
        assert inst.to_text() == text


def test_generate_respects_max_depth():
    # arithmetic has recursive rules — max_depth must prevent infinite recursion
    specs = _specs("arithmetic")
    text = generate("root", specs, rng=random.Random(0), max_depth=3)
    assert isinstance(text, str)


def test_generate_deterministic_with_same_seed():
    specs = _specs("arithmetic")
    t1 = generate("root", specs, rng=random.Random(7))
    t2 = generate("root", specs, rng=random.Random(7))
    assert t1 == t2


def test_generate_different_with_different_seeds():
    specs = _specs("arithmetic")
    results = {generate("root", specs, rng=random.Random(i)) for i in range(20)}
    assert len(results) > 1  # must produce variety
```

- [ ] **Step 2: Run failing tests**

```bash
uv run pytest tests/unit/lexic/test_generate.py -v
```
Expected: `ImportError` — `lexic.generate` not found.

- [ ] **Step 3: Create src/lexic/generate.py**

```python
"""Grammar-agnostic string generator from RuleSpec IR.

Works with any GBNF grammar. Pass the result of IRBuilder.build() keyed
by rule_name. Designed to be extended for R005 constrained generation.
"""
from __future__ import annotations

import random as _random
import re
from typing import TYPE_CHECKING

from lexic.ir import (
    AlternationAtom,
    CharClassAtom,
    InlineAlternationAtom,
    InlineRegexAtom,
    LiteralAtom,
    QuantifiedLiteralAtom,
    RuleRefAtom,
    RuleSpec,
)
from lexic.utils.escapes import decode_gbnf_escapes

try:
    import exrex as _exrex
    _HAS_EXREX = True
except ImportError:
    _HAS_EXREX = False


def _pick_count(min_: int, max_: int | None, rng: _random.Random) -> int:
    """Pick a repetition count, capping lists at 2 to avoid exponential blowup."""
    hi = min(max_, 2) if max_ is not None else 2
    return rng.randint(min_, max(min_, hi))


def _gen_charclass(pattern: str, min_: int, max_: int | None, rng: _random.Random) -> str:
    """Generate a string matching a bracket expression."""
    count = _pick_count(min_, max_, rng)
    if count == 0:
        return ""
    if _HAS_EXREX:
        try:
            return "".join(_exrex.getone(pattern) for _ in range(count))
        except Exception:
            pass
    # Fallback: parse simple bracket expressions manually
    inner = pattern.lstrip("[").rstrip("]")
    chars: list[str] = []
    i = 0
    while i < len(inner):
        if i + 2 < len(inner) and inner[i + 1] == "-":
            chars.extend(chr(c) for c in range(ord(inner[i]), ord(inner[i + 2]) + 1))
            i += 3
        else:
            chars.append(inner[i])
            i += 1
    if not chars:
        return ""
    return "".join(rng.choice(chars) for _ in range(count))


def _gen_inline_regex(gbnf: str, min_: int, max_: int | None, rng: _random.Random) -> str:
    """Generate a string matching one arm of an InlineRegexAtom (using gbnf form)."""
    count = _pick_count(min_, max_, rng)
    if count == 0:
        return ""
    # Parse arms from gbnf: strip outer ( ) and split on |
    body = gbnf.strip()
    if body.startswith("(") and body.endswith(")"):
        body = body[1:-1]
    arms = [a.strip() for a in body.split("|")]
    result = []
    for _ in range(count):
        arm = rng.choice(arms).strip()
        # Strip surrounding quotes if present: "true" → true
        if arm.startswith('"') and arm.endswith('"'):
            arm = arm[1:-1]
        result.append(arm)
    return "".join(result)


def generate(
    rule_name: str,
    specs: dict[str, RuleSpec],
    *,
    rng: _random.Random | None = None,
    max_depth: int = 5,
) -> str:
    """Generate a valid string for rule_name from a compiled RuleSpec dict.

    Works with any grammar — pass IRBuilder.build() keyed by rule_name.
    max_depth caps recursion on self-referential rules (expr → term → expr).
    rng accepts an explicit Random instance so callers can seed deterministically.
    """
    if rng is None:
        rng = _random.Random()

    if max_depth <= 0:
        # At max depth, return simplest possible value for the rule
        spec = specs.get(rule_name)
        if spec is None:
            return ""
        if spec.kind == "value_str":
            return ""
        if spec.kind == "alternation":
            arm = spec.items[0].arm_rule_names[0] if spec.items else rule_name
            return generate(arm, specs, rng=rng, max_depth=0)
        return ""

    spec = specs.get(rule_name)
    if spec is None:
        return ""

    if spec.kind == "alternation":
        arms = spec.items[0].arm_rule_names if spec.items else []
        if not arms:
            return ""
        arm = rng.choice(arms)
        return generate(arm, specs, rng=rng, max_depth=max_depth - 1)

    parts: list[str] = []

    for atom in spec.items:
        if isinstance(atom, LiteralAtom):
            parts.append(decode_gbnf_escapes(atom.value))

        elif isinstance(atom, CharClassAtom):
            parts.append(_gen_charclass(atom.pattern, atom.min, atom.max, rng))

        elif isinstance(atom, QuantifiedLiteralAtom):
            count = _pick_count(atom.min, atom.max, rng)
            parts.append(atom.value * count)

        elif isinstance(atom, InlineRegexAtom):
            parts.append(_gen_inline_regex(atom.gbnf, atom.min, atom.max, rng))

        elif isinstance(atom, RuleRefAtom):
            count = _pick_count(atom.min, atom.max, rng)
            for _ in range(count):
                parts.append(generate(atom.rule_name, specs, rng=rng, max_depth=max_depth - 1))

        elif isinstance(atom, InlineAlternationAtom):
            arm = rng.choice(atom.arm_rule_names)
            parts.append(generate(arm, specs, rng=rng, max_depth=max_depth - 1))

        elif isinstance(atom, AlternationAtom):
            arm = rng.choice(atom.arm_rule_names)
            parts.append(generate(arm, specs, rng=rng, max_depth=max_depth - 1))

    return "".join(parts)
```

- [ ] **Step 4: Expose in lexic/__init__.py**

```python
from lexic.parse import parse
from lexic.codegen import codegen
from lexic.generate import generate

__all__ = ["parse", "codegen", "generate"]
```

- [ ] **Step 5: Run tests**

```bash
uv run pytest tests/unit/lexic/test_generate.py -v
```
Expected: all pass (exrex not yet installed, fallback path used)

- [ ] **Step 6: Run full suite**

```bash
uv run pytest tests/ -q
```
Expected: all pass

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "feat: add src/lexic/generate.py — grammar-agnostic string generator from RuleSpec"
```

---

### Task 12: Add property tests (hypothesis + exrex)

**Files:**
- Modify: `pyproject.toml`
- Create: `tests/property/conftest.py`
- Create: `tests/property/test_roundtrip.py`

- [ ] **Step 1: Add exrex and hypothesis to dev dependencies**

```bash
uv add --dev hypothesis exrex
```

- [ ] **Step 2: Create property test conftest**

`tests/property/conftest.py`:
```python
"""Session-scoped RuleSpec fixtures for all 7 ground-truth grammars."""
from __future__ import annotations
from pathlib import Path
import pytest
from lexic.codegen.parser import parse_gbnf
from lexic.codegen.ir_builder import IRBuilder

GRAMMAR_DIR = Path(__file__).parent.parent.parent / "resources" / "ground_truth"
ALL_GRAMMARS = ["arithmetic", "c", "chess", "japanese", "json_arr", "json_ws", "list"]


@pytest.fixture(scope="session")
def all_grammar_specs() -> dict[str, dict]:
    result = {}
    for name in ALL_GRAMMARS:
        text = (GRAMMAR_DIR / f"{name}.gbnf").read_text()
        specs = IRBuilder(parse_gbnf(text)).build()
        result[name] = {s.rule_name: s for s in specs}
    return result


@pytest.fixture(scope="session")
def grammar_dir() -> Path:
    return GRAMMAR_DIR
```

- [ ] **Step 3: Create property test file**

`tests/property/test_roundtrip.py`:
```python
"""Property-based round-trip tests: generate → parse → to_text == original.

Uses hypothesis seeds to drive the generator, ensuring reproducible failures.
"""
from __future__ import annotations
import random
from pathlib import Path
import pytest
from hypothesis import given, settings, HealthCheck
import hypothesis.strategies as st

from lexic.generate import generate
from lexic.parse import parse

GRAMMAR_DIR = Path(__file__).parent.parent.parent / "resources" / "ground_truth"


def _roundtrip(grammar: str, specs: dict, seed: int) -> None:
    rng = random.Random(seed)
    text = generate("root", specs, rng=rng, max_depth=4)
    gpath = GRAMMAR_DIR / f"{grammar}.gbnf"
    inst = parse(text, gpath)
    assert inst.to_text() == text, (
        f"Round-trip failed [{grammar}] seed={seed}:\n"
        f"  generated: {text!r}\n"
        f"  to_text:   {inst.to_text()!r}"
    )
    inst2 = parse(inst.to_text(), gpath)
    assert inst.model_dump() == inst2.model_dump()


@given(st.integers(min_value=0, max_value=2**32 - 1))
@settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow])
def test_arithmetic_roundtrip(seed, all_grammar_specs):
    _roundtrip("arithmetic", all_grammar_specs["arithmetic"], seed)


@given(st.integers(min_value=0, max_value=2**32 - 1))
@settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow])
def test_list_roundtrip(seed, all_grammar_specs):
    _roundtrip("list", all_grammar_specs["list"], seed)


@given(st.integers(min_value=0, max_value=2**32 - 1))
@settings(max_examples=20, suppress_health_check=[HealthCheck.too_slow])
def test_japanese_roundtrip(seed, all_grammar_specs):
    _roundtrip("japanese", all_grammar_specs["japanese"], seed)


@given(st.integers(min_value=0, max_value=2**32 - 1))
@settings(max_examples=20, suppress_health_check=[HealthCheck.too_slow])
def test_chess_roundtrip(seed, all_grammar_specs):
    _roundtrip("chess", all_grammar_specs["chess"], seed)


@given(st.integers(min_value=0, max_value=2**32 - 1))
@settings(max_examples=20, suppress_health_check=[HealthCheck.too_slow])
def test_json_ws_roundtrip(seed, all_grammar_specs):
    _roundtrip("json_ws", all_grammar_specs["json_ws"], seed)
```

Note: `all_grammar_specs` fixture is session-scoped from conftest.py but hypothesis requires it per-call. Add `@pytest.fixture` indirect parametrize or pass via module-level variable if hypothesis+fixtures conflict. If they do, use:
```python
# At module level, after imports:
_GRAMMAR_DIR = Path(__file__).parent.parent.parent / "resources" / "ground_truth"
_ALL_SPECS: dict[str, dict] = {}

def _get_specs(grammar: str) -> dict:
    if grammar not in _ALL_SPECS:
        from lexic.codegen.parser import parse_gbnf
        from lexic.codegen.ir_builder import IRBuilder
        text = (_GRAMMAR_DIR / f"{grammar}.gbnf").read_text()
        _ALL_SPECS[grammar] = {s.rule_name: s for s in IRBuilder(parse_gbnf(text)).build()}
    return _ALL_SPECS[grammar]
```
And replace `all_grammar_specs["arithmetic"]` with `_get_specs("arithmetic")` in each test.

- [ ] **Step 4: Run property tests**

```bash
uv run pytest tests/property/ -v --tb=short
```
Expected: all pass (some may be slow — normal for hypothesis + earley parsing)

- [ ] **Step 5: Run full suite**

```bash
uv run pytest tests/ -q
```
Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "test: add hypothesis property tests for all grammars; add exrex dev dependency"
```

---

## PART C — Semantic Field Naming

---

### Task 13: Semantic field naming for CharClassAtom fields

**Files:**
- Modify: `src/lexic/codegen/ir_builder.py`
- Modify: `tests/unit/lexic/codegen/test_ir_builder.py`
- Modify: `README.md`

- [ ] **Step 1: Write failing tests for new names**

Add to `tests/unit/lexic/codegen/test_ir_builder.py`:
```python
def test_ident_field_names_are_semantic():
    """[a-z] → 'lower', [a-z0-9_]* → 'alnum', not 'first'/'second'."""
    d = _by_rule(_build("arithmetic"))
    ident = d["ident"]
    assert "lower" in ident.field_map, f"Expected 'lower', got {list(ident.field_map)}"
    assert "alnum" in ident.field_map, f"Expected 'alnum', got {list(ident.field_map)}"
    assert "first" not in ident.field_map
    assert "second" not in ident.field_map


def test_chess_root_item_field_names():
    """[1-9] → 'digit', [0-9]? → 'digit2'."""
    d = _by_rule(_build("chess"))
    root_item = d["root-item"]
    assert "digit" in root_item.field_map, f"Got {list(root_item.field_map)}"
    assert "first" not in root_item.field_map


def test_no_positional_names_any_grammar():
    """No field should be named 'first', 'second', 'third', 'fourth', 'fifth'."""
    positional = {"first", "second", "third", "fourth", "fifth"}
    for grammar in ["arithmetic", "c", "chess", "japanese", "json_arr", "json_ws", "list"]:
        specs = _build(grammar)
        for spec in specs:
            for fname in spec.field_map:
                assert fname not in positional, (
                    f"Grammar '{grammar}', rule '{spec.rule_name}': "
                    f"field '{fname}' is a positional name"
                )
```

- [ ] **Step 2: Run failing tests**

```bash
uv run pytest tests/unit/lexic/codegen/test_ir_builder.py::test_ident_field_names_are_semantic tests/unit/lexic/codegen/test_ir_builder.py::test_no_positional_names_any_grammar -v
```
Expected: FAIL (currently produces `first`, `second`, etc.)

- [ ] **Step 3: Add lookup table and naming helpers to ir_builder.py**

In `src/lexic/codegen/ir_builder.py`, replace the `_CC_NAMES` constant and add:
```python
# ── Semantic field naming ─────────────────────────────────────────────────────

_CHARCLASS_NAMES: dict[str, str] = {
    "[0-9]":           "digit",
    "[1-9]":           "digit",
    "[0-9a-fA-F]":     "hex",
    "[a-fA-F0-9]":     "hex",
    "[a-f]":           "hex_lower",
    "[A-F]":           "hex_upper",
    "[a-z]":           "lower",
    "[A-Z]":           "upper",
    "[a-zA-Z]":        "alpha",
    "[a-z0-9_]":       "alnum",
    "[a-zA-Z_]":       "name_start",
    "[a-zA-Z0-9_]":    "alnum",
    "[a-zA-Z_0-9]":    "alnum",
    "[+\\-*/]":        "op",
    "[+#]":            "annotation",
    "[ \\t\\n]":       "ws_char",
    "[ \\t]":          "hspace",
    "[^\\n]":          "non_newline",
    "[^\"\\\\]":       "str_char",
}

_LITERAL_NAMES: dict[str, str] = {
    "-": "sign",
    "+": "sign",
    ".": "dot",
    ",": "comma",
    ":": "colon",
    ";": "semicolon",
    "=": "eq",
    "x": "x",
    "e": "e",
    "E": "E",
}


def _sanitize_pattern(pattern: str) -> str:
    """Derive a readable name hint from a bracket expression.

    '[NBKQR]' → 'nbkqr', '[a-h]' → 'a_h', '[1-8]' → '1_8'
    """
    inner = re.sub(r"[\[\]\^]", "", pattern)
    inner = inner.replace("-", "_").lower()
    # Remove trailing/leading underscores
    inner = inner.strip("_")
    # Truncate to 12 chars
    return inner[:12] if inner else ""


def _charclass_field_name(atom: "CharClassAtom", min_: int, max_: int | None) -> str:
    """Derive a semantic field name for a CharClassAtom."""
    # Tier 1: known pattern lookup
    if atom.pattern in _CHARCLASS_NAMES:
        return _CHARCLASS_NAMES[atom.pattern]
    # Tier 2: sanitize the pattern content
    hint = _sanitize_pattern(atom.pattern)
    if hint:
        return hint
    # Tier 3: quantifier role fallback
    if max_ is None:
        return "tail"
    if min_ == 0 and max_ == 1:
        return "opt"
    return "cc"


def _quantified_literal_field_name(value: str) -> str:
    """Derive a field name for a QuantifiedLiteralAtom."""
    if value in _LITERAL_NAMES:
        return _LITERAL_NAMES[value]
    # Sanitize the literal value itself
    sanitized = re.sub(r"[^a-zA-Z0-9]", "_", value).strip("_").lower()[:12]
    return sanitized or "lit"


def _inline_regex_field_name(gbnf: str) -> str:
    """Derive a field name for an InlineRegexAtom from its first arm."""
    body = gbnf.strip()
    if body.startswith("(") and body.endswith(")"):
        body = body[1:-1]
    first_arm = body.split("|")[0].strip().strip('"')
    sanitized = re.sub(r"[^a-zA-Z0-9]", "_", first_arm).strip("_").lower()[:12]
    return sanitized or "inline"
```

- [ ] **Step 4: Update _assign_field_names to use new naming**

Replace `_assign_field_names`:
```python
def _assign_field_names(items: list[Atom]) -> dict[str, int]:
    """Assign semantic field names to non-literal atoms."""
    field_map: dict[str, int] = {}
    name_counts: dict[str, int] = {}

    def _unique(base: str, idx: int) -> str:
        count = name_counts.get(base, 0) + 1
        name_counts[base] = count
        return base if count == 1 else f"{base}{count}"

    for i, atom in enumerate(items):
        if isinstance(atom, LiteralAtom):
            continue

        if isinstance(atom, AlternationAtom):
            continue  # kind='alternation' rules have no fields

        if isinstance(atom, InlineAlternationAtom):
            field_map[_unique("value", i)] = i

        elif isinstance(atom, RuleRefAtom):
            base = atom.rule_name.replace("-", "_")
            field_map[_unique(base, i)] = i

        elif isinstance(atom, CharClassAtom):
            base = _charclass_field_name(atom, atom.min, atom.max)
            field_map[_unique(base, i)] = i

        elif isinstance(atom, QuantifiedLiteralAtom):
            base = _quantified_literal_field_name(atom.value)
            field_map[_unique(base, i)] = i

        elif isinstance(atom, InlineRegexAtom):
            base = _inline_regex_field_name(atom.gbnf)
            field_map[_unique(base, i)] = i

    return field_map
```

- [ ] **Step 5: Run the new naming tests**

```bash
uv run pytest tests/unit/lexic/codegen/test_ir_builder.py::test_ident_field_names_are_semantic tests/unit/lexic/codegen/test_ir_builder.py::test_no_positional_names_any_grammar -v
```
Expected: PASS

- [ ] **Step 6: Update existing tests that assert old field names**

Search for tests asserting `"first"`, `"second"`, `"third"` in field_map:
```bash
grep -n '"first"\|"second"\|"third"' tests/unit/lexic/codegen/test_ir_builder.py
```

Update each assertion to use the new name. For example:
```python
# OLD
assert "first" in fm  # [a-z]
assert "second" in fm  # [a-z0-9_]*
# NEW
assert "lower" in fm   # [a-z]
assert "alnum" in fm   # [a-z0-9_]*
```

Also update `test_arithmetic_ident_field_map`:
```python
def test_arithmetic_ident_field_map():
    d = _by_rule(_build("arithmetic"))
    ident = d["ident"]
    fm = ident.field_map
    assert "lower" in fm   # [a-z]
    assert "alnum" in fm   # [a-z0-9_]*
    assert "ws" in fm      # ws
    assert fm["lower"] == 0
    assert fm["alnum"] == 1
    assert fm["ws"] == 2
```

- [ ] **Step 7: Regenerate all grammar files**

```bash
uv run python -c "
from pathlib import Path
from lexic.codegen import codegen
for p in sorted(Path('resources/ground_truth').glob('*.gbnf')):
    codegen(p)
print('Done.')
"
```

Inspect `generated/arithmetic.py` — `Ident` should have `lower: str` and `alnum: str` instead of `first` and `second`.

- [ ] **Step 8: Update integration tests that reference old field names**

Search for any integration test that accesses `inst.first` or similar:
```bash
grep -rn "\.first\b\|\.second\b\|\.third\b" tests/
```

Update to use new names. For example, if any test accesses `ident.first`, change to `ident.lower`.

- [ ] **Step 9: Run full test suite**

```bash
uv run pytest tests/ -q
```
Expected: all pass

- [ ] **Step 10: Add README TODO for annotation mechanism**

In `README.md`, add a section after the "Quick start" section:

```markdown
## Field naming

Field names for character-class atoms are derived automatically from the pattern:

| Pattern | Field name |
|---|---|
| `[0-9]` | `digit` |
| `[a-z]` | `lower` |
| `[a-zA-Z0-9_]` | `alnum` |
| `[+#]` | `annotation` |
| other | sanitized pattern content |

**Planned:** Grammar authors will be able to override field names using inline GBNF
comments (`# @field=captureFile`). This annotation mechanism is not yet implemented.
```

- [ ] **Step 11: Final commit**

```bash
git add -A
git commit -m "feat: semantic field naming for CharClassAtom fields (lookup table + sanitize + quantifier fallback); update generated files"
```

---

## Self-Review

**Spec coverage check:**

| Spec section | Covered by |
|---|---|
| A1 — src/lexic/ package | Task 1 |
| A2 — 7 atom types | Tasks 3, 4 |
| A3 — IRBuilder changes + bug fix | Task 6 |
| A4 — Emitter simplification | Tasks 5, 7 |
| A5 — Transformer extraction | Task 8 |
| A6 — File map | Tasks 1–8 |
| B1 — tests/unit/lexic/ mirrors src/lexic/ | Task 9 |
| B2 — generate.py public API | Task 11 |
| B3 — complex integration test cases | Task 10 |
| B4 — property test shape | Task 12 |
| C1 — lookup table + sanitize + role fallback | Task 13 |
| C2 — examples in generated code | Task 13 step 7 |
| C3 — README TODO | Task 13 step 10 |
| D — out of scope | Not implemented |
