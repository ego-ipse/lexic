# Slice B.5 — Package Restructure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restructure `codegen/` into `ir/` (generic protocols), `parsing/` (Lark machinery), `grammars/gbnf/` (thin GBNF overrides), and a shrunken `codegen/` (Python source only) — no GBNF knowledge outside `grammars/gbnf/`.

**Architecture:** A generic `IRBuilder[Node]` in `ir/protocols.py` takes a `RuleClassifier` and a `SequenceConverter`; GBNF provides thin implementations. `GbnfParser.parse()` returns `list[RuleSpec]` directly so `codegen/__init__` has no flavour-specific imports. `parsing/` holds Lark machinery with no GBNF imports.

**Tech Stack:** Python 3.12+, `uv run pytest`, `uv run ruff check`, `git mv` for all file moves.

---

> **Spec note — naming.py placement:** The spec says `codegen/naming.py` remains in `codegen/`. Implementation analysis shows `assign_field_names` populates `RuleSpec.field_map` (IR construction), so it belongs in `ir/naming.py`. `codegen/` after this plan contains only `__init__.py` and `model_emitter.py`. This is consistent with the approved invariant; the spec text is amended by this plan.

---

## File Map

**Creates:**
- `src/lexic/ir/protocols.py` — `RuleClassifier[Node]`, `SequenceConverter[Node]`, `HelperRuleRegistry`, `IRBuilder[Node]`
- `src/lexic/ir/naming.py` — `assign_field_names` (moved from `codegen/naming.py`)
- `src/lexic/grammars/gbnf/naming_hints.py` — `_CHARCLASS_NAMES`, `_LITERAL_NAMES`
- `src/lexic/parsing/__init__.py` — empty package marker
- `tests/unit/lexic/ir/test_protocols.py` — `IRBuilder` round-trip + `HelperRuleRegistry` tests
- `tests/unit/lexic/ir/test_naming.py` — `assign_field_names` tests (moved from codegen)
- `tests/unit/lexic/parsing/__init__.py`
- `tests/unit/lexic/parsing/test_import_boundary.py`
- `tests/unit/lexic/grammars/gbnf/test_ir_builder.py`

**Moves (git mv):**
- `src/lexic/codegen/naming.py` → `src/lexic/ir/naming.py`
- `src/lexic/codegen/ast_utils.py` → `src/lexic/grammars/gbnf/ast_utils.py`
- `src/lexic/codegen/classify.py` → `src/lexic/grammars/gbnf/classify.py`
- `src/lexic/codegen/seq_to_atoms.py` → `src/lexic/grammars/gbnf/seq_to_atoms.py`
- `src/lexic/codegen/ir_builder.py` → `src/lexic/grammars/gbnf/ir_builder.py`
- `src/lexic/codegen/lark_builder.py` → `src/lexic/parsing/lark_builder.py`
- `src/lexic/codegen/transformer/` → `src/lexic/parsing/transformer/`
- `tests/unit/lexic/codegen/test_naming.py` → `tests/unit/lexic/ir/test_naming.py`
- `tests/unit/lexic/codegen/test_ast_utils.py` → `tests/unit/lexic/grammars/gbnf/test_ast_utils.py`
- `tests/unit/lexic/codegen/test_classify.py` → `tests/unit/lexic/grammars/gbnf/test_classify.py`
- `tests/unit/lexic/codegen/test_seq_to_atoms.py` → `tests/unit/lexic/grammars/gbnf/test_seq_to_atoms.py`
- `tests/unit/lexic/codegen/test_ir_builder.py` → `tests/unit/lexic/grammars/gbnf/test_ir_builder.py`
- `tests/unit/lexic/codegen/test_lark_builder.py` → `tests/unit/lexic/parsing/test_lark_builder.py`
- `tests/unit/lexic/codegen/transformer/` → `tests/unit/lexic/parsing/transformer/`

**Deletes:**
- `src/lexic/codegen/helpers.py` — `HelperRuleRegistry` absorbed into `ir/protocols.py`
- `tests/unit/lexic/codegen/test_helpers.py` — content absorbed into `tests/unit/lexic/ir/test_protocols.py`

**Unchanged:**
- `src/lexic/codegen/__init__.py` — updated (drops `IRBuilder` import, simplified)
- `src/lexic/codegen/model_emitter.py` — unchanged
- `src/lexic/compile.py` — updated (import path changes for `LarkBuilder`)
- `src/lexic/grammars/gbnf/parser.py` — updated (returns `list[RuleSpec]`)
- `src/lexic/ir/__init__.py` — updated (re-exports new names)

---

## Task 1: `ir/protocols.py` + `ir/naming.py`

**Files:**
- Create: `src/lexic/ir/protocols.py`
- Move: `src/lexic/codegen/naming.py` → `src/lexic/ir/naming.py`
- Move: `tests/unit/lexic/codegen/test_naming.py` → `tests/unit/lexic/ir/test_naming.py`
- Modify: `src/lexic/ir/__init__.py`
- Modify: `src/lexic/codegen/ir_builder.py` (import path update)
- Modify: `src/lexic/codegen/seq_to_atoms.py` (import path update)

- [ ] **Step 1: Write the failing test for `HelperRuleRegistry` in `ir/protocols.py`**

Create `tests/unit/lexic/ir/test_protocols.py`:

```python
"""Tests for ir/protocols.py — HelperRuleRegistry and IRBuilder protocol wiring."""
from __future__ import annotations
import pytest
from lexic.ir import RuleSpec
from lexic.ir.protocols import HelperRuleRegistry


def _spec(name: str) -> RuleSpec:
    return RuleSpec(
        rule_name=name,
        class_name="X",
        parent_class_name="GrammarModel",
        kind="sequence",
        items=[],
        field_map={},
    )


def test_helper_registry_reserve_base_on_first_use():
    reg = HelperRuleRegistry()
    assert reg.reserve("arithmetic-item") == "arithmetic-item"


def test_helper_registry_reserve_numbers_collisions():
    reg = HelperRuleRegistry()
    reg.register(_spec("arithmetic-item"))
    assert reg.reserve("arithmetic-item") == "arithmetic-item2"
    reg.register(_spec("arithmetic-item2"))
    assert reg.reserve("arithmetic-item") == "arithmetic-item3"


def test_helper_registry_reserve_idempotent_before_register():
    reg = HelperRuleRegistry()
    reg.register(_spec("a"))
    assert reg.reserve("a") == "a2"
    assert reg.reserve("a") == "a2"


def test_helper_registry_all_specs_order():
    reg = HelperRuleRegistry()
    reg.register(_spec("p"))
    reg.register(_spec("q"))
    assert [s.rule_name for s in reg.all_specs()] == ["p", "q"]


def test_helper_registry_rejects_duplicate():
    reg = HelperRuleRegistry()
    reg.register(_spec("x"))
    with pytest.raises(ValueError, match="already registered"):
        reg.register(_spec("x"))
```

- [ ] **Step 2: Run — expect ImportError (module doesn't exist yet)**

```bash
uv run pytest tests/unit/lexic/ir/test_protocols.py -q
```

Expected: `ModuleNotFoundError: No module named 'lexic.ir.protocols'`

- [ ] **Step 3: Create `src/lexic/ir/protocols.py`**

```python
"""Generic IR-construction protocols + HelperRuleRegistry + IRBuilder.

IRBuilder[Node] is parameterised by a RuleClassifier and SequenceConverter
so it contains zero flavour-specific knowledge.
"""

from __future__ import annotations

from typing import Generic, Literal, Protocol, TypeVar

from lexic.ir.atoms import Atom
from lexic.ir.spec import RuleSpec

Node = TypeVar("Node")


class RuleClassifier(Protocol[Node]):
    """Determines the IR kind and structure of a single grammar rule node."""

    def rule_name(self, rule: Node) -> str: ...

    def kind(self, rule: Node) -> Literal["sequence", "alternation", "value_str"]: ...

    def alternation_arm_nodes(self, rule: Node) -> list[Node]:
        """For alternation rules: return the stripped arm nodes."""
        ...

    def sequence_body(self, rule: Node) -> Node:
        """For sequence rules: return the body node to convert."""
        ...

    def single_ruleref(self, arm: Node) -> str | None:
        """If arm is a single unquantified rule reference, return its name; else None."""
        ...


class SequenceConverter(Protocol[Node]):
    """Converts flavour AST nodes to IR Atoms + field_map."""

    def value_str_atoms(self, rule: Node) -> list[Atom]:
        """Atoms for a value_str rule (literals/chars/groups only, no rule refs)."""
        ...

    def sequence_atoms(
        self,
        body: Node,
        cls_name: str,
        helpers: "HelperRuleRegistry",
        name_map: dict[str, str],
        parent_of: dict[str, str],
    ) -> tuple[list[Atom], dict[str, int]]:
        """Atoms + field_map for a sequence or alternation-arm body."""
        ...


class HelperRuleRegistry:
    """Accumulates synthesised helper RuleSpecs during IR construction."""

    def __init__(self) -> None:
        self._specs: list[RuleSpec] = []
        self._names: set[str] = set()

    def reserve(self, base_name: str) -> str:
        """Return a unique rule_name without marking it as taken."""
        if base_name not in self._names:
            return base_name
        suffix = 2
        while f"{base_name}{suffix}" in self._names:
            suffix += 1
        return f"{base_name}{suffix}"

    def register(self, spec: RuleSpec) -> None:
        if spec.rule_name in self._names:
            raise ValueError(f"Helper rule {spec.rule_name!r} already registered")
        self._names.add(spec.rule_name)
        self._specs.append(spec)

    def all_specs(self) -> list[RuleSpec]:
        return list(self._specs)


class IRBuilder(Generic[Node]):
    """Generic orchestrator: list[Node] → list[RuleSpec].

    Callers wire: IRBuilder(GbnfClassifier(), GbnfConverter()).build(ast_rules).
    """

    def __init__(
        self,
        classifier: RuleClassifier[Node],
        converter: SequenceConverter[Node],
    ) -> None:
        self._classifier = classifier
        self._converter = converter

    def build(self, rules: list[Node]) -> list[RuleSpec]:
        raise NotImplementedError("Implemented in Task 3")
```

- [ ] **Step 4: Run — expect tests to pass**

```bash
uv run pytest tests/unit/lexic/ir/test_protocols.py -q
```

Expected: 5 passed.

- [ ] **Step 5: Move `codegen/naming.py` → `ir/naming.py`**

```bash
git mv src/lexic/codegen/naming.py src/lexic/ir/naming.py
git mv tests/unit/lexic/codegen/test_naming.py tests/unit/lexic/ir/test_naming.py
```

Update the import in `tests/unit/lexic/ir/test_naming.py` — change `from lexic.codegen.naming import ...` → `from lexic.ir.naming import ...`.

Update `src/lexic/codegen/ir_builder.py` line 15:
```python
# Before:
from lexic.codegen.naming import assign_field_names
# After:
from lexic.ir.naming import assign_field_names
```

Update `src/lexic/codegen/seq_to_atoms.py` line 22:
```python
# Before:
from lexic.codegen.naming import assign_field_names
# After:
from lexic.ir.naming import assign_field_names
```

- [ ] **Step 6: Update `src/lexic/ir/__init__.py` to re-export new names**

```python
"""Public IR surface — import everything from here."""

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
from lexic.ir.spec import RuleSpec
from lexic.ir.protocols import (
    RuleClassifier,
    SequenceConverter,
    HelperRuleRegistry,
    IRBuilder,
)

__all__ = [
    "Atom",
    "AlternationAtom",
    "CharClassAtom",
    "InlineAlternationAtom",
    "InlineRegexAtom",
    "LiteralAtom",
    "QuantifiedLiteralAtom",
    "RuleRefAtom",
    "RuleSpec",
    "RuleClassifier",
    "SequenceConverter",
    "HelperRuleRegistry",
    "IRBuilder",
]
```

- [ ] **Step 7: Run full test suite — all tests must pass**

```bash
uv run pytest tests/ -q
uv run ruff check src/ tests/
```

Expected: all existing tests pass (no broken imports).

- [ ] **Step 8: Commit**

```bash
git add src/lexic/ir/protocols.py src/lexic/ir/naming.py src/lexic/ir/__init__.py \
        tests/unit/lexic/ir/test_protocols.py tests/unit/lexic/ir/test_naming.py \
        src/lexic/codegen/ir_builder.py src/lexic/codegen/seq_to_atoms.py
git commit -m "refactor(ir): introduce protocols.py, move naming.py from codegen/, extract HelperRuleRegistry"
```

---

## Task 2: Move GBNF-specific source files to `grammars/gbnf/`

**Files:**
- Move: `codegen/ast_utils.py` → `grammars/gbnf/ast_utils.py`
- Move: `codegen/classify.py` → `grammars/gbnf/classify.py`
- Move: `codegen/seq_to_atoms.py` → `grammars/gbnf/seq_to_atoms.py`
- Move test mirrors accordingly
- Modify: `codegen/ir_builder.py` (import paths)

- [ ] **Step 1: `git mv` source files**

```bash
git mv src/lexic/codegen/ast_utils.py src/lexic/grammars/gbnf/ast_utils.py
git mv src/lexic/codegen/classify.py src/lexic/grammars/gbnf/classify.py
git mv src/lexic/codegen/seq_to_atoms.py src/lexic/grammars/gbnf/seq_to_atoms.py
```

- [ ] **Step 2: `git mv` test mirrors**

```bash
git mv tests/unit/lexic/codegen/test_ast_utils.py tests/unit/lexic/grammars/gbnf/test_ast_utils.py
git mv tests/unit/lexic/codegen/test_classify.py tests/unit/lexic/grammars/gbnf/test_classify.py
git mv tests/unit/lexic/codegen/test_seq_to_atoms.py tests/unit/lexic/grammars/gbnf/test_seq_to_atoms.py
```

- [ ] **Step 3: Update imports in moved source files**

In `src/lexic/grammars/gbnf/ast_utils.py` — no import changes needed (already imports from `grammars.gbnf.ast`).

In `src/lexic/grammars/gbnf/classify.py` — update:
```python
# Before:
from lexic.codegen.ast_utils import (...)
# After:
from lexic.grammars.gbnf.ast_utils import (...)
```

In `src/lexic/grammars/gbnf/seq_to_atoms.py` — update:
```python
# Before:
from lexic.codegen.ast_utils import is_pure_literal_seq, single_ruleref_of, strip_ws
from lexic.codegen.helpers import HelperRuleRegistry
from lexic.ir.naming import assign_field_names
# After:
from lexic.grammars.gbnf.ast_utils import is_pure_literal_seq, single_ruleref_of, strip_ws
from lexic.ir.protocols import HelperRuleRegistry
from lexic.ir.naming import assign_field_names
```

- [ ] **Step 4: Update imports in test mirrors**

In `tests/unit/lexic/grammars/gbnf/test_ast_utils.py`:
```python
# Before:
from lexic.codegen.ast_utils import ...
# After:
from lexic.grammars.gbnf.ast_utils import ...
```

In `tests/unit/lexic/grammars/gbnf/test_classify.py`:
```python
# Before:
from lexic.codegen.classify import ...
# After:
from lexic.grammars.gbnf.classify import ...
```

In `tests/unit/lexic/grammars/gbnf/test_seq_to_atoms.py`:
```python
# Before:
from lexic.codegen.seq_to_atoms import ...
from lexic.codegen.helpers import HelperRuleRegistry
# After:
from lexic.grammars.gbnf.seq_to_atoms import ...
from lexic.ir.protocols import HelperRuleRegistry
```

- [ ] **Step 5: Update imports in `codegen/ir_builder.py`**

```python
# Before:
from lexic.codegen.ast_utils import single_ruleref_of
from lexic.codegen.helpers import HelperRuleRegistry
from lexic.codegen.classify import (Classifier, NamedAlt, PureLiteralAlt, SequenceKind, ValueStr)
from lexic.codegen.seq_to_atoms import seq_to_atoms, value_str_to_atoms
# After:
from lexic.grammars.gbnf.ast_utils import single_ruleref_of
from lexic.ir.protocols import HelperRuleRegistry
from lexic.grammars.gbnf.classify import (Classifier, NamedAlt, PureLiteralAlt, SequenceKind, ValueStr)
from lexic.grammars.gbnf.seq_to_atoms import seq_to_atoms, value_str_to_atoms
```

- [ ] **Step 6: Run full suite — all tests pass**

```bash
uv run pytest tests/ -q
uv run ruff check src/ tests/
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git commit -m "refactor(gbnf): git mv ast_utils, classify, seq_to_atoms into grammars/gbnf/"
```

---

## Task 3: Adapt GBNF files to protocols + implement `IRBuilder` + thin `ir_builder.py` + `GbnfParser.parse()` return type

This task is a single atomic commit. Every sub-step must be complete before the commit, because `GbnfParser.parse()` changing its return type and `codegen/__init__.py` dropping `IRBuilder` must happen together.

**Files:**
- Modify: `src/lexic/grammars/gbnf/naming_hints.py` (create)
- Modify: `src/lexic/ir/naming.py` (add hints param, remove hardcoded tables)
- Modify: `src/lexic/grammars/gbnf/classify.py` (add `GbnfClassifier`)
- Modify: `src/lexic/grammars/gbnf/seq_to_atoms.py` (add `GbnfConverter`)
- Modify: `src/lexic/ir/protocols.py` (implement `IRBuilder.build()`)
- Move+rewrite: `src/lexic/codegen/ir_builder.py` → `src/lexic/grammars/gbnf/ir_builder.py`
- Delete: `src/lexic/codegen/helpers.py`
- Delete: `tests/unit/lexic/codegen/test_helpers.py`
- Modify: `src/lexic/grammars/gbnf/parser.py`
- Modify: `src/lexic/codegen/__init__.py`
- Move: `tests/unit/lexic/codegen/test_ir_builder.py` → `tests/unit/lexic/grammars/gbnf/test_ir_builder.py`

- [ ] **Step 1: Create `grammars/gbnf/naming_hints.py`**

```python
"""GBNF-specific naming hints injected into ir.naming.assign_field_names."""

from __future__ import annotations

CHARCLASS_NAMES: dict[str, str] = {
    "[0-9]": "digit",
    "[1-9]": "digit",
    "[0-9a-fA-F]": "hex",
    "[a-fA-F0-9]": "hex",
    "[a-f]": "hex_lower",
    "[A-F]": "hex_upper",
    "[a-z]": "lower",
    "[A-Z]": "upper",
    "[a-zA-Z]": "alpha",
    "[a-z0-9_]": "alnum",
    "[a-zA-Z_]": "name_start",
    "[a-zA-Z0-9_]": "alnum",
    "[a-zA-Z_0-9]": "alnum",
    "[+\\-*/]": "op",
    "[-+*/]": "op",
    "[+#]": "annotation",
    "[ \\t\\n]": "ws_char",
    "[ \\t]": "hspace",
    "[^\\n]": "non_newline",
    '[^"\\\\]': "str_char",
}

LITERAL_NAMES: dict[str, str] = {
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
```

- [ ] **Step 2: Update `ir/naming.py` — add hints params, remove hardcoded tables**

Remove `_CHARCLASS_NAMES` and `_LITERAL_NAMES` from `ir/naming.py`. Update `assign_field_names` signature:

```python
def assign_field_names(
    atoms: Seq[Atom],
    *,
    charclass_names: dict[str, str] | None = None,
    literal_names: dict[str, str] | None = None,
) -> dict[str, int]:
    """Assign semantic field names to atoms.

    charclass_names and literal_names are flavour-specific lookup tables.
    When None, falls back to sanitized pattern names (generic).
    """
    _cc = charclass_names or {}
    _lit = literal_names or {}
    field_map: dict[str, int] = {}
    counts: dict[str, int] = {}

    def unique(base: str) -> str:
        n = counts.get(base, 0) + 1
        counts[base] = n
        return base if n == 1 else f"{base}{n}"

    for i, atom in enumerate(atoms):
        if isinstance(atom, LiteralAtom):
            continue
        if isinstance(atom, AlternationAtom):
            continue
        if isinstance(atom, InlineAlternationAtom):
            field_map[unique("value")] = i
        elif isinstance(atom, RuleRefAtom):
            field_map[unique(atom.rule_name.replace("-", "_"))] = i
        elif isinstance(atom, CharClassAtom):
            field_map[unique(_charclass_field_name(atom, _cc))] = i
        elif isinstance(atom, QuantifiedLiteralAtom):
            field_map[unique(_quantified_literal_field_name(atom.value, _lit))] = i
        elif isinstance(atom, InlineRegexAtom):
            field_map[unique(_inline_regex_field_name(atom.gbnf))] = i

    return field_map
```

Update `_charclass_field_name` to accept the hints dict:
```python
def _charclass_field_name(atom: CharClassAtom, charclass_names: dict[str, str]) -> str:
    if atom.pattern in charclass_names:
        return charclass_names[atom.pattern]
    hint = _sanitize_pattern(atom.pattern)
    if hint:
        return hint
    if atom.max is None:
        return "tail"
    if atom.min == 0 and atom.max == 1:
        return "opt"
    return "cc"
```

Update `_quantified_literal_field_name` to accept the hints dict:
```python
def _quantified_literal_field_name(value: str, literal_names: dict[str, str]) -> str:
    if value in literal_names:
        return literal_names[value]
    sanitized = re.sub(r"[^a-zA-Z0-9]", "_", value).strip("_").lower()[:12]
    return sanitized or "lit"
```

- [ ] **Step 3: Add `GbnfClassifier` to `grammars/gbnf/classify.py`**

Add the class after the existing `Classifier` class. (The old `Classifier` is deleted at step end of this task.)

```python
from lexic.ir.protocols import RuleClassifier
from lexic.grammars.gbnf.ast import Rule, Sequence


class GbnfClassifier:
    """Implements RuleClassifier[Rule] for GBNF AST nodes."""

    def _classify(self, rule: Rule) -> Classification:
        """Internal helper — reuses existing classification logic."""
        return _classify_rule(rule)  # module-level function extracted from old Classifier.classify()

    def rule_name(self, rule: Rule) -> str:
        return rule.name

    def kind(self, rule: Rule) -> str:
        c = self._classify(rule)
        if isinstance(c, (ValueStr, PureLiteralAlt)):
            return "value_str"
        if isinstance(c, NamedAlt):
            return "alternation"
        return "sequence"

    def alternation_arm_nodes(self, rule: Rule) -> list[Sequence]:
        c = self._classify(rule)
        assert isinstance(c, NamedAlt)
        return c.arms

    def sequence_body(self, rule: Rule) -> Sequence:
        c = self._classify(rule)
        assert isinstance(c, SequenceKind)
        return c.body

    def single_ruleref(self, arm: Sequence) -> str | None:
        return single_ruleref_of(arm)
```

- [ ] **Step 4: Add `GbnfConverter` to `grammars/gbnf/seq_to_atoms.py`**

Add the class after existing module-level functions. (Old functions deleted at end of this task.)

```python
from lexic.ir.protocols import HelperRuleRegistry, SequenceConverter
from lexic.grammars.gbnf.naming_hints import CHARCLASS_NAMES, LITERAL_NAMES
from lexic.ir.naming import assign_field_names
from lexic.grammars.gbnf.ast import Alternation, Rule


class GbnfConverter:
    """Implements SequenceConverter[Rule] for GBNF AST nodes."""

    def value_str_atoms(self, rule: Rule) -> list[Atom]:
        return value_str_to_atoms(rule.body)

    def sequence_atoms(
        self,
        body: Sequence,
        cls_name: str,
        helpers: HelperRuleRegistry,
        name_map: dict[str, str],
        parent_of: dict[str, str],
    ) -> tuple[list[Atom], dict[str, int]]:
        atoms = seq_to_atoms(body, cls_name, helpers, name_map, parent_of)
        field_map = assign_field_names(
            atoms,
            charclass_names=CHARCLASS_NAMES,
            literal_names=LITERAL_NAMES,
        )
        return atoms, field_map
```

Also update the internal `seq_to_atoms` function to use `assign_field_names` with hints for the helper-spec creation (line ~164 in the current file):

```python
helper_fm = assign_field_names(
    helper_atoms,
    charclass_names=CHARCLASS_NAMES,
    literal_names=LITERAL_NAMES,
)
```

- [ ] **Step 5: Implement `IRBuilder[Node].build()` in `ir/protocols.py`**

Replace the `raise NotImplementedError` stub with the full implementation. Also add required imports at top of `protocols.py`:

```python
from lexic.ir.atoms import AlternationAtom
from lexic.utils.names import to_pascal
```

Replace the `IRBuilder` class body:

```python
class IRBuilder(Generic[Node]):
    """Generic orchestrator: list[Node] → list[RuleSpec]."""

    def __init__(
        self,
        classifier: RuleClassifier[Node],
        converter: SequenceConverter[Node],
    ) -> None:
        self._classifier = classifier
        self._converter = converter

    def build(self, rules: list[Node]) -> list[RuleSpec]:
        name_map = {
            self._classifier.rule_name(r): to_pascal(self._classifier.rule_name(r))
            for r in rules
        }
        parent_of = self._compute_parents(rules, name_map)
        helpers = HelperRuleRegistry()
        primary: list[RuleSpec] = []
        for rule in rules:
            primary.extend(self._build_rule(rule, name_map, parent_of, helpers))
        all_specs = primary + helpers.all_specs()
        return self._topo_sort(all_specs)

    def _compute_parents(
        self, rules: list[Node], name_map: dict[str, str]
    ) -> dict[str, str]:
        parent_of: dict[str, str] = {}
        for rule in rules:
            if self._classifier.kind(rule) != "alternation":
                continue
            cls_name = name_map[self._classifier.rule_name(rule)]
            for arm in self._classifier.alternation_arm_nodes(rule):
                ref = self._classifier.single_ruleref(arm)
                if ref is not None:
                    parent_of[ref] = cls_name
        return parent_of

    def _build_rule(
        self,
        rule: Node,
        name_map: dict[str, str],
        parent_of: dict[str, str],
        helpers: HelperRuleRegistry,
    ) -> list[RuleSpec]:
        rule_name = self._classifier.rule_name(rule)
        cls_name = name_map[rule_name]
        parent_cls = parent_of.get(rule_name, "GrammarModel")
        kind = self._classifier.kind(rule)

        if kind == "value_str":
            return [
                RuleSpec(
                    rule_name=rule_name,
                    class_name=cls_name,
                    parent_class_name=parent_cls,
                    kind="value_str",
                    items=self._converter.value_str_atoms(rule),
                    field_map={},
                )
            ]
        if kind == "alternation":
            return self._build_named_alt(rule, rule_name, cls_name, parent_cls, name_map, parent_of, helpers)
        # sequence
        body = self._classifier.sequence_body(rule)
        atoms, fm = self._converter.sequence_atoms(body, cls_name, helpers, name_map, parent_of)
        return [
            RuleSpec(
                rule_name=rule_name,
                class_name=cls_name,
                parent_class_name=parent_cls,
                kind="sequence",
                items=atoms,
                field_map=fm,
            )
        ]

    def _build_named_alt(
        self,
        rule: Node,
        rule_name: str,
        cls_name: str,
        parent_cls: str,
        name_map: dict[str, str],
        parent_of: dict[str, str],
        helpers: HelperRuleRegistry,
    ) -> list[RuleSpec]:
        arm_rule_names: list[str] = []
        arm_specs: list[RuleSpec] = []
        for arm_idx, arm_node in enumerate(
            self._classifier.alternation_arm_nodes(rule), start=1
        ):
            ref = self._classifier.single_ruleref(arm_node)
            if ref is not None:
                arm_rule_names.append(ref)
            else:
                arm_rule_name = f"{rule_name}-arm{arm_idx}"
                arm_cls_name = f"{cls_name}Arm{arm_idx}"
                arm_rule_names.append(arm_rule_name)
                atoms, fm = self._converter.sequence_atoms(
                    arm_node, arm_cls_name, helpers, name_map, parent_of
                )
                arm_specs.append(
                    RuleSpec(
                        rule_name=arm_rule_name,
                        class_name=arm_cls_name,
                        parent_class_name=cls_name,
                        kind="sequence",
                        items=atoms,
                        field_map=fm,
                    )
                )
        abstract = RuleSpec(
            rule_name=rule_name,
            class_name=cls_name,
            parent_class_name=parent_cls,
            kind="alternation",
            items=[AlternationAtom(arm_rule_names=arm_rule_names)],
            field_map={},
        )
        return [abstract] + arm_specs

    def _topo_sort(self, specs: list[RuleSpec]) -> list[RuleSpec]:
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

        root = next((s for s in specs if s.rule_name == "root"), None)
        if root:
            visit(root.class_name)
        for s in specs:
            visit(s.class_name)
        return ordered
```

- [ ] **Step 6: `git mv codegen/ir_builder.py` → `grammars/gbnf/ir_builder.py` and rewrite as thin wiring**

```bash
git mv src/lexic/codegen/ir_builder.py src/lexic/grammars/gbnf/ir_builder.py
git mv tests/unit/lexic/codegen/test_ir_builder.py tests/unit/lexic/grammars/gbnf/test_ir_builder.py
```

Rewrite `src/lexic/grammars/gbnf/ir_builder.py` to contain only:

```python
"""Thin GBNF wiring: IRBuilder[Rule](GbnfClassifier(), GbnfConverter()).build(rules)."""

from __future__ import annotations

from lexic.ir import IRBuilder, RuleSpec
from lexic.grammars.gbnf.ast import Rule
from lexic.grammars.gbnf.classify import GbnfClassifier
from lexic.grammars.gbnf.seq_to_atoms import GbnfConverter


def build_specs(rules: list[Rule]) -> list[RuleSpec]:
    """Convert GBNF AST rules to a list of RuleSpec IR objects."""
    return IRBuilder(GbnfClassifier(), GbnfConverter()).build(rules)
```

Update `tests/unit/lexic/grammars/gbnf/test_ir_builder.py` — replace old content with a test that verifies the thin wiring:

```python
"""Tests for grammars/gbnf/ir_builder.py thin wiring."""
from __future__ import annotations
from pathlib import Path
from lexic.grammars.gbnf.parser import parse_gbnf
from lexic.grammars.gbnf.ir_builder import build_specs
from lexic.ir import RuleSpec

GROUND_TRUTH = Path(__file__).resolve().parents[6] / "resources" / "ground_truth"


def test_build_specs_returns_list_of_rule_spec():
    rules = parse_gbnf('root ::= "hello"\n')
    specs = build_specs(rules)
    assert isinstance(specs, list)
    assert all(isinstance(s, RuleSpec) for s in specs)


def test_build_specs_root_is_first():
    rules = parse_gbnf('root ::= "hello"\n')
    specs = build_specs(rules)
    assert specs[0].rule_name == "root"


def test_build_specs_arithmetic_grammar():
    text = (GROUND_TRUTH / "arithmetic.gbnf").read_text()
    rules = parse_gbnf(text)
    specs = build_specs(rules)
    assert len(specs) > 0
    assert specs[0].rule_name == "root"
```

- [ ] **Step 7: Delete `codegen/helpers.py` and its test**

```bash
git rm src/lexic/codegen/helpers.py
git rm tests/unit/lexic/codegen/test_helpers.py
```

- [ ] **Step 8: Refactor `grammars/gbnf/classify.py` — promote `Classifier.classify` to module-level `_classify_rule`**

The existing `Classifier.classify` method becomes a module-level function `_classify_rule(rule: Rule) -> Classification` used by `GbnfClassifier._classify`. Delete the `Classifier` class. Keep the `Classification` dataclasses (`ValueStr`, `PureLiteralAlt`, `NamedAlt`, `SequenceKind`) and all module-level predicate helpers unchanged.

- [ ] **Step 9: Update `grammars/gbnf/parser.py` — `GbnfParser.parse()` returns `list[RuleSpec]`**

```python
from lexic.ir import RuleSpec
from lexic.grammars.gbnf.ir_builder import build_specs


class GbnfParser(FlavourParser):
    """GBNF flavour parser — returns list[RuleSpec] directly."""

    def parse(self, text: str) -> list[RuleSpec]:
        return build_specs(parse_gbnf(text))
```

Remove the old `list[Rule]` return type annotation and the "Phase 2" comment.

- [ ] **Step 10: Update `codegen/__init__.py` — drop `IRBuilder` import**

```python
"""Codegen public surface.

- build_classes_and_specs(text, *, stem, flavour="gbnf") → (classes, specs)
- codegen(text, *, stem, flavour="gbnf") → classes
- codegen_from_path(path, *, flavour=None) → classes  (infers flavour from ext)
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from lexic.grammars import adapter_for_extension, get_adapter
from lexic.codegen.model_emitter import ModelEmitter
from lexic.ir import RuleSpec


def _emit_and_load_module(
    specs: list[RuleSpec], stem: str, *, source: str | None
) -> dict[str, type]:
    out_dir = Path(__file__).resolve().parent.parent.parent.parent / "generated"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{stem}.py"
    out_path.write_text(ModelEmitter(specs, source or f"<string:{stem}>").render())

    module_name = f"generated.{stem}"
    if module_name in sys.modules:
        del sys.modules[module_name]
    spec = importlib.util.spec_from_file_location(module_name, out_path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return {
        s.class_name: getattr(mod, s.class_name)
        for s in specs
        if hasattr(mod, s.class_name)
    }


def build_classes_and_specs(
    text: str, *, stem: str, flavour: str = "gbnf"
) -> tuple[dict[str, type], list[RuleSpec]]:
    """Parse + emit + load. Returns (classes, specs)."""
    adapter = get_adapter(flavour)
    specs = adapter.parser.parse(text)
    classes = _emit_and_load_module(specs, stem, source=None)
    return classes, specs


def codegen(text: str, *, stem: str, flavour: str = "gbnf") -> dict[str, type]:
    """Classes-only wrapper."""
    classes, _ = build_classes_and_specs(text, stem=stem, flavour=flavour)
    return classes


def codegen_from_path(
    grammar_path: str | Path, *, flavour: str | None = None
) -> dict[str, type]:
    """Read-file wrapper; infers flavour from extension if flavour=None."""
    path = Path(grammar_path)
    if flavour is None:
        flavour = adapter_for_extension(path).name
    return codegen(path.read_text(), stem=path.stem, flavour=flavour)
```

- [ ] **Step 11: Run full suite — all tests must pass**

```bash
uv run pytest tests/ -q
uv run ruff check src/ tests/
```

Expected: all tests pass.

- [ ] **Step 12: Commit**

```bash
git commit -m "refactor(gbnf): GbnfClassifier + GbnfConverter + IRBuilder impl + thin ir_builder + GbnfParser returns list[RuleSpec]"
```

---

## Task 4: Create `parsing/` package — move `lark_builder` + `transformer`, remove GBNF seam

**Files:**
- Create: `src/lexic/parsing/__init__.py`
- Create: `tests/unit/lexic/parsing/__init__.py`
- Move: `src/lexic/codegen/lark_builder.py` → `src/lexic/parsing/lark_builder.py`
- Move: `src/lexic/codegen/transformer/` → `src/lexic/parsing/transformer/`
- Move: `tests/unit/lexic/codegen/test_lark_builder.py` → `tests/unit/lexic/parsing/test_lark_builder.py`
- Move: `tests/unit/lexic/codegen/transformer/` → `tests/unit/lexic/parsing/transformer/`
- Modify: `src/lexic/parsing/lark_builder.py` (remove GBNF seam)
- Modify: `src/lexic/ir/protocols.py` (`IRBuilder.build` — ws min=0)
- Modify: `src/lexic/compile.py` (import path update)

- [ ] **Step 1: Create package markers**

```bash
touch src/lexic/parsing/__init__.py
touch tests/unit/lexic/parsing/__init__.py
```

- [ ] **Step 2: `git mv` source files**

```bash
git mv src/lexic/codegen/lark_builder.py src/lexic/parsing/lark_builder.py
git mv src/lexic/codegen/transformer src/lexic/parsing/transformer
```

- [ ] **Step 3: `git mv` test mirrors**

```bash
git mv tests/unit/lexic/codegen/test_lark_builder.py tests/unit/lexic/parsing/test_lark_builder.py
git mv tests/unit/lexic/codegen/transformer tests/unit/lexic/parsing/transformer
```

- [ ] **Step 4: Update imports in moved source files**

In `src/lexic/parsing/lark_builder.py`:
```python
# Remove this import entirely:
from lexic.grammars.gbnf.escapes import decode_gbnf_escapes

# Update transformer import:
# Before:
from lexic.codegen.transformer import build_transformer
# After:
from lexic.parsing.transformer import build_transformer
```

In `src/lexic/parsing/transformer/__init__.py`:
```python
# Before:
from lexic.codegen.transformer.build_transformer import build_transformer
# After:
from lexic.parsing.transformer.build_transformer import build_transformer
```

In `src/lexic/parsing/transformer/builders.py`, `registry.py`, `build_transformer.py`, `context.py` — update any `from lexic.codegen.transformer` → `from lexic.parsing.transformer`.

- [ ] **Step 5: Remove `decode_gbnf_escapes` usage from `parsing/lark_builder.py`**

In `_atom_to_lark`, the `LiteralAtom` branch currently calls `decode_gbnf_escapes(atom.value)`. Remove it — `atom.value` is already canonical Python after `GbnfParser.parse()` decodes escapes at parse time. Replace all occurrences:

```python
# Before (two occurrences):
decoded = decode_gbnf_escapes(atom.value)
# After:
decoded = atom.value
```

- [ ] **Step 6: Remove `rule_name == "ws"` special case; use `min == 0` instead**

In `_atom_to_lark`, the `RuleRefAtom` branch:

```python
# Before:
if isinstance(atom, RuleRefAtom):
    name = to_lark_name(atom.rule_name)
    if atom.rule_name == "ws":
        return "ws?"
    q = bounds_to_quantifier(atom.min, atom.max)
    return f"{name}{q}"

# After:
if isinstance(atom, RuleRefAtom):
    name = to_lark_name(atom.rule_name)
    q = bounds_to_quantifier(atom.min, atom.max)
    return f"{name}{q}"
```

- [ ] **Step 7: Update `IRBuilder._build_rule` to set `min=0` on ws `RuleRefAtom`s**

In `src/lexic/ir/protocols.py`, in the `_build_rule` method, replace the sequence-kind block:

```python
# sequence
body = self._classifier.sequence_body(rule)
atoms, fm = self._converter.sequence_atoms(body, cls_name, helpers, name_map, parent_of)
# Mark ws refs as optional (min=0) — downstream consumers use bounds, not name checks
atoms = [
    RuleRefAtom(rule_name=a.rule_name, min=0, max=1)
    if isinstance(a, RuleRefAtom) and a.rule_name == "ws"
    else a
    for a in atoms
]
return [
    RuleSpec(
        rule_name=rule_name,
        class_name=cls_name,
        parent_class_name=parent_cls,
        kind="sequence",
        items=atoms,
        field_map=fm,
    )
]
```

Add the `RuleRefAtom` import at the top of `protocols.py`:
```python
from lexic.ir.atoms import Atom, AlternationAtom, RuleRefAtom
```

- [ ] **Step 8: Update `compile.py` — fix import paths**

```python
# Before:
from lexic.codegen.lark_builder import LarkBuilder
# After:
from lexic.parsing.lark_builder import LarkBuilder
```

Also update the module docstring line referencing `lexic.codegen.lark_builder`:
```python
# Before:
# and LarkBuilder from lexic.codegen.lark_builder (the sub-module).
# After:
# and LarkBuilder from lexic.parsing.lark_builder (the sub-module).
```

- [ ] **Step 9: Update test mirrors — fix imports in moved test files**

In `tests/unit/lexic/parsing/test_lark_builder.py`:
```python
# Before:
from lexic.codegen.lark_builder import LarkBuilder, _atom_to_lark
# After:
from lexic.parsing.lark_builder import LarkBuilder, _atom_to_lark
```

In `tests/unit/lexic/parsing/transformer/` files — update imports from `lexic.codegen.transformer` → `lexic.parsing.transformer`.

- [ ] **Step 10: Run full suite — all tests pass**

```bash
uv run pytest tests/ -q
uv run ruff check src/ tests/
```

Expected: all tests pass.

- [ ] **Step 11: Commit**

```bash
git commit -m "refactor(parsing): git mv lark_builder + transformer to parsing/; remove GBNF seam violations"
```

---

## Task 5: Write `test_protocols.py` round-trip test + import boundary test

**Files:**
- Modify: `tests/unit/lexic/ir/test_protocols.py` (add round-trip tests)
- Create: `tests/unit/lexic/parsing/test_import_boundary.py`

- [ ] **Step 1: Write round-trip tests in `test_protocols.py`**

Append to `tests/unit/lexic/ir/test_protocols.py`:

```python
from pathlib import Path
from lexic.grammars.gbnf.parser import parse_gbnf
from lexic.grammars.gbnf.classify import GbnfClassifier
from lexic.grammars.gbnf.seq_to_atoms import GbnfConverter
from lexic.ir.protocols import IRBuilder

GROUND_TRUTH = Path(__file__).resolve().parents[5] / "resources" / "ground_truth"


def _build(text: str):
    rules = parse_gbnf(text)
    return IRBuilder(GbnfClassifier(), GbnfConverter()).build(rules)


def test_irbuilder_simple_grammar():
    specs = _build('root ::= "hello"\n')
    assert len(specs) == 1
    assert specs[0].rule_name == "root"
    assert specs[0].kind == "value_str"


def test_irbuilder_root_is_first():
    specs = _build('root ::= expr\nexpr ::= [0-9]+\n')
    assert specs[0].rule_name == "root"


def test_irbuilder_all_ground_truth_grammars():
    """IRBuilder produces the same specs as GbnfParser.parse() (they share the same path)."""
    from lexic.grammars import get_adapter
    adapter = get_adapter("gbnf")
    for path in sorted(GROUND_TRUTH.glob("*.gbnf")):
        rules = parse_gbnf(path.read_text())
        direct = IRBuilder(GbnfClassifier(), GbnfConverter()).build(rules)
        via_parser = adapter.parser.parse(path.read_text())
        assert [s.rule_name for s in direct] == [s.rule_name for s in via_parser], \
            f"Mismatch for {path.name}"
        assert [s.kind for s in direct] == [s.kind for s in via_parser], \
            f"Kind mismatch for {path.name}"
```

- [ ] **Step 2: Write import boundary test**

Create `tests/unit/lexic/parsing/test_import_boundary.py`:

```python
"""Verify that lexic.parsing has no imports from lexic.grammars.gbnf."""
import importlib
import importlib.util
import pkgutil
import sys


def _module_names_under(package: str) -> list[str]:
    spec = importlib.util.find_spec(package)
    assert spec is not None and spec.submodule_search_locations is not None
    names = [package]
    for info in pkgutil.walk_packages(spec.submodule_search_locations, prefix=package + "."):
        names.append(info.name)
    return names


def test_parsing_does_not_import_grammars_gbnf():
    """No module under lexic.parsing may import from lexic.grammars.gbnf."""
    forbidden_prefix = "lexic.grammars.gbnf"
    violations: list[str] = []

    for mod_name in _module_names_under("lexic.parsing"):
        # Force import so __spec__ is populated
        importlib.import_module(mod_name)
        mod = sys.modules[mod_name]
        source_file = getattr(mod, "__file__", None)
        if source_file is None:
            continue
        with open(source_file) as f:
            source = f.read()
        if forbidden_prefix in source:
            violations.append(mod_name)

    assert not violations, (
        f"These parsing/ modules import from grammars.gbnf: {violations}"
    )
```

- [ ] **Step 3: Run new tests**

```bash
uv run pytest tests/unit/lexic/ir/test_protocols.py tests/unit/lexic/parsing/test_import_boundary.py -v
uv run pytest tests/ -q
```

Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git commit -m "test(ir): add IRBuilder round-trip tests; test(parsing): add import boundary assertion"
```

---

## Task 6: Update documents

**Files:**
- Modify: `CLAUDE.md`
- Modify: `prototyping/next/2_ARCHITECTURE.md`
- Modify: `prototyping/next/3_ROADMAP.md`
- Modify: `docs/superpowers/specs/2026-04-23-slice-b-design.md`

- [ ] **Step 1: Update `CLAUDE.md` — project layout table**

In the `## Project layout` section, update the layout block to:

```
src/lexic/
  __init__.py
  base.py                   GrammarModel base
  compile.py                compile(text) → CompiledGrammar
  exceptions.py             LexicError hierarchy
  generate.py               random string generator from RuleSpec
  parse.py                  parse(text, grammar_path) → GrammarModel
  ir/
    __init__.py             re-exports Atom types, RuleSpec, protocols
    atoms.py                seven Atom dataclasses
    spec.py                 RuleSpec dataclass
    protocols.py            RuleClassifier, SequenceConverter, HelperRuleRegistry, IRBuilder[Node]
    naming.py               assign_field_names (field_map construction)
    regex_portable.py       PORTABLE_FEATURES, validate_portable, features_used
  parsing/                  Lark machinery — zero GBNF knowledge
    __init__.py
    lark_builder.py         LarkBuilder: list[RuleSpec] → Lark grammar string
    transformer/            build_transformer: Lark tree → Pydantic instance
  grammars/
    __init__.py             get_adapter(), adapter_for_extension(), register_adapter()
    flavours.py             FlavourAdapter/Parser/Emitter protocols + ADAPTERS registry
    gbnf/                   GBNF flavour — thin overrides only
      adapter.py            GbnfAdapter
      parser.py             GbnfParser: text → list[RuleSpec] (via ir_builder)
      emitter.py            GbnfEmitter: list[RuleSpec] → GBNF text
      ir_builder.py         thin wiring: IRBuilder(GbnfClassifier(), GbnfConverter()).build(rules)
      classify.py           GbnfClassifier(RuleClassifier[Rule])
      seq_to_atoms.py       GbnfConverter(SequenceConverter[Rule])
      naming_hints.py       CHARCLASS_NAMES, LITERAL_NAMES (GBNF-specific)
      ast.py                GBNF AST nodes
      ast_utils.py          GBNF AST traversal helpers
      escapes.py            decode_gbnf_escapes
      charclass.py          GBNF bracket-expression parsing
  codegen/
    __init__.py             build_classes_and_specs, codegen, codegen_from_path
    model_emitter.py        ModelEmitter: list[RuleSpec] → Python source
  utils/
    __init__.py
    quantifiers.py          bounds_to_quantifier
    names.py                to_lark_name, to_pascal, etc.
```

Also update the `## Architecture` section pipeline description:

```
GBNF text → GbnfParser.parse() → list[RuleSpec] IR → ModelEmitter  → generated/*.py
                                                    → GbnfEmitter   → GBNF text
                                                    → LarkBuilder   → Lark grammar
                                                    → Transformer   → Pydantic instance
```

Update the `## Key constraints` section — add:
- `parsing/` has zero imports from `lexic.grammars.gbnf`.
- `ir/` has zero imports from `lexic.codegen` or `lexic.grammars`.
- `GbnfParser.parse()` returns `list[RuleSpec]` directly.

- [ ] **Step 2: Update `prototyping/next/2_ARCHITECTURE.md`**

Update the target module layout section to reflect the new package structure (same layout as CLAUDE.md above). Update the Layering rules section:

- Add rule: "`parsing/` depends only on `ir/` and `utils/`. No `grammars/gbnf` imports."
- Add rule: "`ir/` depends only on `utils/`. No `codegen/`, `grammars/`, or `parsing/` imports."
- Update `codegen/` description: "Python source generation only — `model_emitter.py` + `__init__.py`."
- Note: `GbnfParser.parse()` returns `list[RuleSpec]` — the GBNF AST never leaves `grammars/gbnf/`.

- [ ] **Step 3: Update `prototyping/next/3_ROADMAP.md` — insert Slice B.5**

Insert after the Slice B Phase 1 exit criteria section and before the Slice B Phase 2 section:

```markdown
### Slice B.5 — Package restructure (completes before Phase 2)

**Goal:** No GBNF knowledge outside `grammars/gbnf/`. Each package has one responsibility.

**Scope:**
- `ir/protocols.py`: `RuleClassifier[Node]`, `SequenceConverter[Node]`, `HelperRuleRegistry`, `IRBuilder[Node]`
- `ir/naming.py`: `assign_field_names` (moved from `codegen/naming.py`)
- `parsing/`: `lark_builder.py` + `transformer/` (moved from `codegen/`); zero GBNF imports
- `grammars/gbnf/`: `classify.py` → `GbnfClassifier`; `seq_to_atoms.py` → `GbnfConverter`; `ir_builder.py` thin wiring; `naming_hints.py`
- `codegen/`: shrinks to `__init__.py` + `model_emitter.py`
- `GbnfParser.parse()` returns `list[RuleSpec]` directly

**Exit criteria:**
- [ ] `ir/protocols.py`, `ir/naming.py` exist; `codegen/naming.py`, `codegen/helpers.py` deleted.
- [ ] `parsing/lark_builder.py` and `parsing/transformer/` exist; `codegen/lark_builder.py` and `codegen/transformer/` deleted.
- [ ] `grammars/gbnf/classify.py` has `GbnfClassifier`; `grammars/gbnf/seq_to_atoms.py` has `GbnfConverter`; `grammars/gbnf/ir_builder.py` is thin wiring only; `grammars/gbnf/naming_hints.py` exists.
- [ ] `codegen/` contains only `__init__.py` and `model_emitter.py`.
- [ ] `GbnfParser.parse()` returns `list[RuleSpec]`; `codegen/__init__.py` contains no `IRBuilder` import.
- [ ] `parsing/lark_builder.py` has no import from `lexic.grammars.gbnf`; no `rule_name == "ws"` special case.
- [ ] `IRBuilder.build()` sets `min=0` on ws `RuleRefAtom`s.
- [ ] All existing tests green; import boundary test green; `uv run ruff check src/ tests/` clean.
```

- [ ] **Step 4: Update `docs/superpowers/specs/2026-04-23-slice-b-design.md`**

In §Architecture delta / Target module layout, replace the layout block with a note:

```markdown
> **Amended by Slice B.5 (2026-04-24):** The layout below has been superseded.
> See `docs/superpowers/specs/2026-04-24-slice-b5-package-restructure-design.md`
> for the pre-Phase-2 package structure. Phase 2 and Phase 3 below operate on the
> post-B.5 architecture.
```

In §Additional decisions D1 ("Delete `LarkBuilder.build_transformer`"): note it is implemented in Slice B.5 Task 4 (already done as part of the ws special-case removal).

In §Creates, moves, deletes: add a note that moves into `parsing/` and `ir/` are handled by Slice B.5.

In §Phase 1 (per-phase structure): add note that Phase 1 is complete; Slice B.5 lands between Phase 1 and Phase 2.

- [ ] **Step 5: Run full suite to confirm docs-only changes don't break anything**

```bash
uv run pytest tests/ -q
uv run ruff check src/ tests/
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git commit -m "docs(slice-b5): update CLAUDE.md, 2_ARCHITECTURE.md, 3_ROADMAP.md, slice-b spec for post-B.5 layout"
```
