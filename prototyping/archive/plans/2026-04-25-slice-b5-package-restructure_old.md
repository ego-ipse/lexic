# Slice B.5 — Package Restructure Implementation Plan (v2)

> **Supersedes:** `docs/superpowers/plans/2026-04-24-slice-b5-package-restructure.md` (v1).
> v2 folds in eleven review findings: ws-rewrite leaking into generic `IRBuilder`, GBNF-flavour policy in generic code (`_compute_parents`, `_topo_sort` `"root"` literal), dead `name_map`/`parent_of` parameters in `seq_to_atoms`, `decode_gbnf_escapes` calls at five sites in `parsing/`, asymmetric `value_str_atoms(rule)` vs `sequence_atoms(body)`, redundant re-classification in `GbnfClassifier`, lax round-trip test, fragile string-match import-boundary test, off-by-one `parents[N]` paths in test fixtures, and the `CHARCLASS_NAMES` vs `_CHARCLASS_NAMES` spec/plan mismatch.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restructure into `ir/` (generic protocols), `parsing/` (Lark machinery — zero `lexic.grammars` imports), `grammars/gbnf/` (thin overrides + decode/encode), `codegen/` (Python-source emission only).

**Architecture:** Generic `IRBuilder[Node]` parameterised by `RuleClassifier` and `SequenceConverter` Protocols. GBNF supplies thin implementations. Escape-decoding moves to the AST→IR boundary inside `GbnfConverter`; encoding back happens in `GbnfEmitter`. `LiteralAtom.value` is canonical Python everywhere downstream — `parsing/` never decodes.

**Tech Stack:** Python 3.12+, `uv run pytest`, `uv run ruff check`, `git mv`.

---

## Cleaner-code audit (what v1 would have copied verbatim)

The original plan replicated several smells. v2 fixes them at move-time so the new files start clean rather than carrying technical debt across the seam:

1. **Dead parameters in `seq_to_atoms`.** `name_map: dict[str, str]` and `parent_of: dict[str, str]` are accepted, threaded through recursive calls, but **never read**. Both deleted.
2. **`Classifier` is a stateless wrapper class with one method.** Replaced by a module-level `classify_rule(rule) -> Classification` function.
3. **`decode_gbnf_escapes` is called five times in `lark_builder.py` + `transformer/build_transformer.py`.** Moved upstream: `GbnfConverter` decodes once when constructing `LiteralAtom`/`QuantifiedLiteralAtom`; `GbnfEmitter` encodes back via a new `encode_gbnf_escapes` helper. `parsing/` never imports from `grammars/gbnf/`.
4. **v1's `IRBuilder._build_rule` was given a `if a.rule_name == "ws"` rewrite** — generic IR holding a GBNF naming convention. Moved to `GbnfConverter.sequence_atoms`.
5. **`_topo_sort` hardcodes `"root"`.** Replaced by `RuleClassifier.is_start_rule(rule) -> bool`. GBNF returns `rule_name == "root"`; the protocol stays clean.
6. **`GbnfClassifier` would re-classify on every method call.** Memoised per-instance by `id(rule)`.
7. **`value_str_atoms(rule)` vs `sequence_atoms(body)` asymmetry.** Both take bodies. `RuleClassifier` gains `value_str_body(rule) -> Node`.
8. **`Sequence` and `Rule` smushed into one `Node` TypeVar.** Acceptable for slice B.5 (only one flavour today). Documented in `2_ARCHITECTURE.md` as a known compromise.
9. **`v1` shipped `parents[5]`/`parents[6]` test paths that are off-by-one** vs the existing `tests/unit/lexic/...` convention. Corrected.
10. **`v1`'s import-boundary test used substring search** on source files. Replaced with an `ast.parse` walk that inspects only `Import`/`ImportFrom` nodes.
11. **`v1`'s round-trip test compared only `rule_name` + `kind`.** Compares full `RuleSpec` equality.

What slice B.5 does **not** fix (deliberate scope):
- Other `rule_name == "ws"` literals in `parsing/` (`lark_builder.py:99`, `transformer/build_transformer.py:97`, `transformer/builders.py:88`, `base.py:97`). These are `"ws"` *string* uses, not imports — the import-boundary invariant remains met. A future slice can introduce a "drop-this-rule" / "is-this-whitespace" hook in the IR. Documented as known seam.

---

## File map

**Creates:**
- `src/lexic/ir/protocols.py` — `RuleClassifier[Node]`, `SequenceConverter[Node]`, `HelperRuleRegistry`, `IRBuilder[Node]`
- `src/lexic/grammars/gbnf/naming_hints.py` — `CHARCLASS_NAMES`, `LITERAL_NAMES` (public; cross-module)
- `src/lexic/parsing/__init__.py` — empty package marker
- `tests/unit/lexic/ir/__init__.py` (if missing — already exists per current branch)
- `tests/unit/lexic/parsing/__init__.py`
- `tests/unit/lexic/parsing/test_import_boundary.py` — AST-based import scan

**Moves (`git mv`):**
- `src/lexic/codegen/naming.py` → `src/lexic/ir/naming.py` *(already done on current branch; commit cleanly)*
- `src/lexic/codegen/ast_utils.py` → `src/lexic/grammars/gbnf/ast_utils.py`
- `src/lexic/codegen/classify.py` → `src/lexic/grammars/gbnf/classify.py`
- `src/lexic/codegen/seq_to_atoms.py` → `src/lexic/grammars/gbnf/seq_to_atoms.py`
- `src/lexic/codegen/ir_builder.py` → `src/lexic/grammars/gbnf/ir_builder.py`
- `src/lexic/codegen/lark_builder.py` → `src/lexic/parsing/lark_builder.py`
- `src/lexic/codegen/transformer/` → `src/lexic/parsing/transformer/`
- All test mirrors follow.

**Deletes:**
- `src/lexic/codegen/helpers.py` — `HelperRuleRegistry` absorbed into `ir/protocols.py`
- `tests/unit/lexic/codegen/test_helpers.py` — content absorbed into `tests/unit/lexic/ir/test_protocols.py`
- `src/lexic/ir/protocols_orig.py` — earlier draft, superseded
- `generated/arith_flavour_test.py` — stray artifact (untracked, generated/)

**Modified (in place):**
- `src/lexic/grammars/gbnf/escapes.py` — adds `encode_gbnf_escapes`
- `src/lexic/grammars/gbnf/parser.py` — `GbnfParser.parse()` returns `list[RuleSpec]`
- `src/lexic/grammars/gbnf/emitter.py` — calls `encode_gbnf_escapes` on `LiteralAtom`/`QuantifiedLiteralAtom`
- `src/lexic/codegen/__init__.py` — drops `IRBuilder` import
- `src/lexic/compile.py` — `LarkBuilder` import path updated
- `src/lexic/ir/naming.py` — adds `charclass_names` / `literal_names` hint params; hardcoded tables removed
- `src/lexic/ir/__init__.py` — re-exports `RuleClassifier`, `SequenceConverter`, `HelperRuleRegistry`, `IRBuilder`

**Unchanged source:**
- `src/lexic/codegen/model_emitter.py`
- `src/lexic/base.py`, `parse.py`, `generate.py`
- `src/lexic/ir/atoms.py`, `spec.py`, `regex_portable.py`
- `src/lexic/grammars/gbnf/ast.py`, `adapter.py`, `charclass.py`

---

## Task 1 — `ir/protocols.py` + finalise `ir/naming.py`

The current branch already moved `naming.py` and drafted two competing `protocols.py`/`protocols_orig.py`. This task picks the canonical version (Protocol-based), wires it into `ir/__init__.py`, and commits. `IRBuilder.build()` is a stub here (full body lands in Task 3) so this commit is purely additive.

**Files:**
- Create: `src/lexic/ir/protocols.py` (overwrite the current draft)
- Delete: `src/lexic/ir/protocols_orig.py`
- Modify: `src/lexic/ir/__init__.py`
- Modify: `src/lexic/ir/naming.py` (defer hint-param work to Task 3 — keep API stable here so existing callers still work)
- Modify: `src/lexic/codegen/ir_builder.py` (import path: `lexic.codegen.naming` → `lexic.ir.naming`)
- Modify: `src/lexic/codegen/seq_to_atoms.py` (same import update)
- Create: `tests/unit/lexic/ir/test_protocols.py`

- [ ] **Step 1: Write the failing tests for `HelperRuleRegistry`**

Create `tests/unit/lexic/ir/test_protocols.py`:

```python
"""Tests for ir/protocols.py — HelperRuleRegistry; IRBuilder round-trip lands in Task 5."""
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


def test_helper_registry_reserve_returns_base_when_unused():
    reg = HelperRuleRegistry()
    assert reg.reserve("arithmetic-item") == "arithmetic-item"


def test_helper_registry_reserve_numbers_collisions():
    reg = HelperRuleRegistry()
    reg.register(_spec("arithmetic-item"))
    assert reg.reserve("arithmetic-item") == "arithmetic-item2"
    reg.register(_spec("arithmetic-item2"))
    assert reg.reserve("arithmetic-item") == "arithmetic-item3"


def test_helper_registry_reserve_idempotent_until_register():
    reg = HelperRuleRegistry()
    reg.register(_spec("a"))
    assert reg.reserve("a") == "a2"
    assert reg.reserve("a") == "a2"


def test_helper_registry_all_specs_preserves_insertion_order():
    reg = HelperRuleRegistry()
    reg.register(_spec("p"))
    reg.register(_spec("q"))
    assert [s.rule_name for s in reg.all_specs()] == ["p", "q"]


def test_helper_registry_register_rejects_duplicate():
    reg = HelperRuleRegistry()
    reg.register(_spec("x"))
    with pytest.raises(ValueError, match="already registered"):
        reg.register(_spec("x"))
```

- [ ] **Step 2: Run — expect ModuleNotFoundError**

```bash
uv run pytest tests/unit/lexic/ir/test_protocols.py -q
```

Expected: `ModuleNotFoundError: No module named 'lexic.ir.protocols'` (or import error from the existing draft — fine; the next step overwrites it).

- [ ] **Step 3: Write `src/lexic/ir/protocols.py` (canonical version)**

Overwrite the current file (and ignore `protocols_orig.py` — Step 5 deletes it). `IRBuilder.build()` is a `NotImplementedError` stub; the body lands in Task 3.

```python
"""Generic IR-construction protocols + HelperRuleRegistry + IRBuilder.

IRBuilder[Node] is parameterised by a RuleClassifier and SequenceConverter and
contains zero flavour-specific knowledge. Concrete flavours (e.g. GBNF) supply
thin protocol implementations.
"""

from __future__ import annotations

from typing import Generic, Literal, Protocol, TypeVar

from lexic.ir.atoms import Atom
from lexic.ir.spec import RuleSpec

Node = TypeVar("Node")


class RuleClassifier(Protocol[Node]):
    """Single-purpose queries over a flavour AST node.

    `value_str_body` and `sequence_body` return the body subtree the converter
    will consume. `is_start_rule` lets `IRBuilder` order specs without
    hardcoding a flavour-specific name.
    """

    def rule_name(self, rule: Node) -> str: ...

    def kind(self, rule: Node) -> Literal["sequence", "alternation", "value_str"]: ...

    def is_start_rule(self, rule: Node) -> bool: ...

    def alternation_arm_nodes(self, rule: Node) -> list[Node]: ...

    def sequence_body(self, rule: Node) -> Node: ...

    def value_str_body(self, rule: Node) -> Node: ...

    def single_ruleref(self, arm: Node) -> str | None: ...


class SequenceConverter(Protocol[Node]):
    """Build IR Atoms (and the per-rule field_map) from flavour body nodes.

    Both methods take *body* nodes (extracted by the classifier), keeping the
    surface symmetric. Helper RuleSpecs created during conversion are pushed
    into the supplied registry.
    """

    def value_str_atoms(self, body: Node) -> list[Atom]: ...

    def sequence_atoms(
        self,
        body: Node,
        cls_name: str,
        helpers: HelperRuleRegistry,
    ) -> tuple[list[Atom], dict[str, int]]: ...


class HelperRuleRegistry:
    """One-per-build registry for synthesised helper RuleSpecs."""

    def __init__(self) -> None:
        self._specs: list[RuleSpec] = []
        self._names: set[str] = set()

    def reserve(self, base_name: str) -> str:
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
    """list[Node] → list[RuleSpec]. Wired by the flavour layer."""

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

- [ ] **Step 4: Run — Step-1 tests pass**

```bash
uv run pytest tests/unit/lexic/ir/test_protocols.py -q
```

Expected: 5 passed.

- [ ] **Step 5: Delete the superseded draft**

```bash
rm src/lexic/ir/protocols_orig.py
```

- [ ] **Step 6: Update `src/lexic/ir/__init__.py`**

Confirm it re-exports the new names (this should already match the current branch state):

```python
"""Public IR surface — import everything from here."""

from lexic.ir.atoms import (
    AlternationAtom,
    Atom,
    CharClassAtom,
    InlineAlternationAtom,
    InlineRegexAtom,
    LiteralAtom,
    QuantifiedLiteralAtom,
    RuleRefAtom,
)
from lexic.ir.protocols import (
    HelperRuleRegistry,
    IRBuilder,
    RuleClassifier,
    SequenceConverter,
)
from lexic.ir.spec import RuleSpec

__all__ = [
    "AlternationAtom",
    "Atom",
    "CharClassAtom",
    "HelperRuleRegistry",
    "IRBuilder",
    "InlineAlternationAtom",
    "InlineRegexAtom",
    "LiteralAtom",
    "QuantifiedLiteralAtom",
    "RuleClassifier",
    "RuleRefAtom",
    "RuleSpec",
    "SequenceConverter",
]
```

- [ ] **Step 7: Verify `naming.py` imports work**

`codegen/ir_builder.py:15` and `codegen/seq_to_atoms.py:22` should already import `from lexic.ir.naming import assign_field_names` (current branch state). Confirm:

```bash
grep -n "from lexic.ir.naming" src/lexic/codegen/ir_builder.py src/lexic/codegen/seq_to_atoms.py
```

Expected: both files have the line. If not, update them now.

- [ ] **Step 8: Full suite + lint**

```bash
uv run pytest tests/ -q
uv run ruff check src/ tests/
```

Expected: all green.

- [ ] **Step 9: Commit**

```bash
git add src/lexic/ir/protocols.py src/lexic/ir/__init__.py \
        tests/unit/lexic/ir/test_protocols.py
git rm src/lexic/ir/protocols_orig.py
# naming.py move + import updates may already be in tracked state from prior work — include them
git add -u
git commit -m "refactor(ir): introduce protocols.py; finalise ir/naming.py move"
```

---

## Task 2 — Move GBNF AST helpers + `Classifier` simplification + drop dead `seq_to_atoms` parameters

`Classifier.classify(rule)` becomes a module-level `classify_rule(rule)`. `seq_to_atoms`'s `name_map` and `parent_of` parameters disappear. Everything else is `git mv`.

**Files:**
- Move: `src/lexic/codegen/ast_utils.py` → `src/lexic/grammars/gbnf/ast_utils.py`
- Move: `src/lexic/codegen/classify.py` → `src/lexic/grammars/gbnf/classify.py`
- Move: `src/lexic/codegen/seq_to_atoms.py` → `src/lexic/grammars/gbnf/seq_to_atoms.py`
- Move test mirrors
- Modify: `grammars/gbnf/classify.py` — replace `class Classifier` with `def classify_rule`
- Modify: `grammars/gbnf/seq_to_atoms.py` — drop `name_map` and `parent_of` parameters
- Modify: `src/lexic/codegen/ir_builder.py` — import path updates; drop dead args at call sites
- Modify: `tests/unit/lexic/grammars/gbnf/test_seq_to_atoms.py` — drop dead args

- [ ] **Step 1: `git mv` the three source files**

```bash
git mv src/lexic/codegen/ast_utils.py    src/lexic/grammars/gbnf/ast_utils.py
git mv src/lexic/codegen/classify.py     src/lexic/grammars/gbnf/classify.py
git mv src/lexic/codegen/seq_to_atoms.py src/lexic/grammars/gbnf/seq_to_atoms.py
```

- [ ] **Step 2: `git mv` the three test files**

```bash
git mv tests/unit/lexic/codegen/test_ast_utils.py    tests/unit/lexic/grammars/gbnf/test_ast_utils.py
git mv tests/unit/lexic/codegen/test_classify.py     tests/unit/lexic/grammars/gbnf/test_classify.py
git mv tests/unit/lexic/codegen/test_seq_to_atoms.py tests/unit/lexic/grammars/gbnf/test_seq_to_atoms.py
```

- [ ] **Step 3: Update imports inside the moved source files**

In `src/lexic/grammars/gbnf/classify.py`:
```python
# Before:
from lexic.codegen.ast_utils import (
    is_pure_literal_seq,
    is_ws_item,
    strip_ws,
    unwrap_group_alt,
)
# After:
from lexic.grammars.gbnf.ast_utils import (
    is_pure_literal_seq,
    is_ws_item,
    strip_ws,
    unwrap_group_alt,
)
```

In `src/lexic/grammars/gbnf/seq_to_atoms.py`:
```python
# Before:
from lexic.codegen.ast_utils import is_pure_literal_seq, single_ruleref_of, strip_ws
from lexic.codegen.helpers import HelperRuleRegistry
# After:
from lexic.grammars.gbnf.ast_utils import is_pure_literal_seq, single_ruleref_of, strip_ws
from lexic.ir.protocols import HelperRuleRegistry
```

`ast_utils.py` has no `lexic.codegen.*` imports — leave it alone.

- [ ] **Step 4: Replace `Classifier` class with `classify_rule` function**

In `src/lexic/grammars/gbnf/classify.py`, delete the `class Classifier` block (the last 10 lines) and replace it with a module-level function. The internal predicates and `Classification` dataclasses stay unchanged.

```python
def classify_rule(rule: Rule) -> Classification:
    if _is_structurally_complex(rule.body):
        return ValueStr(alt=rule.body)
    alt = unwrap_group_alt(rule.body)
    paired = [
        (seq, strip_ws(seq)) for seq in alt.seqs if len(strip_ws(seq).items) > 0
    ]
    if not paired:
        return ValueStr(alt=alt)
    full_arms = [full for full, _ in paired]
    arms = [stripped for _, stripped in paired]

    if len(arms) > 1 and all(is_pure_literal_seq(a) for a in arms):
        return PureLiteralAlt(alt=alt)
    if (
        len(arms) == 1
        and len(arms[0].items) == 1
        and isinstance(arms[0].items[0].atom, Group)
        and arms[0].items[0].quantifier is None
        and all(
            is_pure_literal_seq(strip_ws(s)) for s in arms[0].items[0].atom.alt.seqs
        )
    ):
        return PureLiteralAlt(alt=alt)
    if len(arms) == 1:
        full_seqs = alt.seqs
        has_any_rule_ref = any(
            any(isinstance(it.atom, RuleRef) for it in s.items) for s in full_seqs
        )
        if not has_any_rule_ref and is_pure_literal_seq(arms[0]):
            return ValueStr(alt=alt)
        return SequenceKind(body=full_arms[0])
    assert len(arms) > 1, "single-arm case handled above"
    return NamedAlt(arms=arms)
```

The module docstring header should be updated to reflect that there is no class anymore:

```python
"""Classification: determine a GBNF rule's IR kind.

`classify_rule(rule)` returns one of four Classification variants, each
carrying exactly the payload its downstream handler needs.
"""
```

- [ ] **Step 5: Drop dead parameters from `seq_to_atoms`**

In `src/lexic/grammars/gbnf/seq_to_atoms.py`, change the signature and call sites. Verify they are dead first:

```bash
grep -nE "name_map|parent_of" src/lexic/grammars/gbnf/seq_to_atoms.py
```

Expected: only the parameter declaration and the recursive forwarding lines (no indexing, no `.get`, no `[...]`). Then edit to drop both:

```python
def seq_to_atoms(
    seq: Sequence,
    parent_class_name: str,
    helpers: HelperRuleRegistry,
) -> list[Atom]:
    """Convert a single grammar sequence into a list of IR atoms.

    Helper RuleSpecs created for quantified groups are pushed into `helpers`.
    """
    atoms: list[Atom] = []

    for item in seq.items:
        if isinstance(item.atom, Literal):
            if item.quantifier is not None:
                min_, max_ = quantifier_to_bounds(item.quantifier)
                atoms.append(
                    QuantifiedLiteralAtom(value=item.atom.value, min=min_, max=max_)
                )
            else:
                atoms.append(LiteralAtom(value=item.atom.value))

        elif isinstance(item.atom, CharClass):
            min_, max_ = quantifier_to_bounds(item.quantifier)
            atoms.append(CharClassAtom(pattern=item.atom.pattern, min=min_, max=max_))

        elif isinstance(item.atom, RuleRef):
            min_, max_ = quantifier_to_bounds(item.quantifier)
            atoms.append(RuleRefAtom(rule_name=item.atom.name, min=min_, max=max_))

        elif isinstance(item.atom, Group):
            min_, max_ = quantifier_to_bounds(item.quantifier)
            inner_arms = [
                a for a in (strip_ws(s) for s in item.atom.alt.seqs) if len(a.items) > 0
            ]

            if all(is_pure_literal_seq(arm) for arm in inner_arms):
                atoms.append(_build_inline_regex(item.atom, min_, max_))
                continue

            if (
                item.quantifier is None
                and len(inner_arms) > 1
                and all(single_ruleref_of(a) is not None for a in inner_arms)
            ):
                arm_names: list[str] = [
                    cast(str, single_ruleref_of(a)) for a in inner_arms
                ]
                atoms.append(InlineAlternationAtom(arm_rule_names=arm_names))
                continue

            if item.quantifier is None and len(inner_arms) == 1:
                inner_atoms = seq_to_atoms(inner_arms[0], parent_class_name, helpers)
                atoms.extend(inner_atoms)
                continue

            helper_rule_name = helpers.reserve(f"{parent_class_name.lower()}-item")
            helper_class_name = to_pascal(helper_rule_name)
            helper_atoms = seq_to_atoms(
                inner_arms[0] if inner_arms else seq,
                helper_class_name,
                helpers,
            )
            helper_fm = assign_field_names(helper_atoms)
            helper_spec = RuleSpec(
                rule_name=helper_rule_name,
                class_name=helper_class_name,
                parent_class_name="GrammarModel",
                kind="sequence",
                items=helper_atoms,
                field_map=helper_fm,
            )
            helpers.register(helper_spec)
            atoms.append(RuleRefAtom(rule_name=helper_rule_name, min=min_, max=max_))

    return atoms
```

(Task 3 will replace `assign_field_names(helper_atoms)` with the hint-aware variant once `naming_hints.py` is wired in. For now this still works because `assign_field_names` accepts no extra args.)

- [ ] **Step 6: Update `codegen/ir_builder.py` call sites and imports**

```python
# Imports at top of file — Before:
from lexic.codegen.ast_utils import single_ruleref_of
from lexic.codegen.helpers import HelperRuleRegistry
from lexic.codegen.classify import (
    Classifier, NamedAlt, PureLiteralAlt, SequenceKind, ValueStr,
)
from lexic.codegen.seq_to_atoms import seq_to_atoms, value_str_to_atoms
# After:
from lexic.grammars.gbnf.ast_utils import single_ruleref_of
from lexic.ir.protocols import HelperRuleRegistry
from lexic.grammars.gbnf.classify import (
    classify_rule, NamedAlt, PureLiteralAlt, SequenceKind, ValueStr,
)
from lexic.grammars.gbnf.seq_to_atoms import seq_to_atoms, value_str_to_atoms
```

Replace all `Classifier()` instantiations and `self._classifier.classify(rule)` calls with `classify_rule(rule)`. Drop `self._classifier = Classifier()` from `__init__`. Update both `seq_to_atoms(...)` call sites to drop the trailing `self._name_map, parent_of` arguments:

```python
# _build_named_alt — Before:
atoms = seq_to_atoms(
    stripped, arm_cls_name, self._helpers, self._name_map, parent_of
)
# After:
atoms = seq_to_atoms(stripped, arm_cls_name, self._helpers)

# _build_sequence — Before:
atoms_seq = seq_to_atoms(
    body, cls_name, self._helpers, self._name_map, parent_of
)
# After:
atoms_seq = seq_to_atoms(body, cls_name, self._helpers)
```

Drop `parent_of` from `_build_sequence`'s and `_build_named_alt`'s parameter lists if it's no longer used (it is; `_compute_parents` still feeds it into `_build_rule`'s sequencing — keep there). Re-read after edit to confirm.

Note: `_compute_parents` itself still uses `single_ruleref_of` and the classification result — that logic moves into `IRBuilder.build()` in Task 3. For now `codegen/ir_builder.py` keeps working as a transitional bridge.

- [ ] **Step 7: Update test mirrors**

In `tests/unit/lexic/grammars/gbnf/test_ast_utils.py`:
```python
# Before:  from lexic.codegen.ast_utils import ...
# After:   from lexic.grammars.gbnf.ast_utils import ...
```

In `tests/unit/lexic/grammars/gbnf/test_classify.py`:
```python
# Before:  from lexic.codegen.classify import Classifier, ...
# After:   from lexic.grammars.gbnf.classify import classify_rule, ...
```

Replace any `Classifier().classify(rule)` in tests with `classify_rule(rule)`.

In `tests/unit/lexic/grammars/gbnf/test_seq_to_atoms.py`:
```python
# Before:
from lexic.codegen.seq_to_atoms import ...
from lexic.codegen.helpers import HelperRuleRegistry
# After:
from lexic.grammars.gbnf.seq_to_atoms import ...
from lexic.ir.protocols import HelperRuleRegistry
```

And every `seq_to_atoms(...)` call in tests drops the trailing `name_map, parent_of` args:
```python
# Before:  atoms = seq_to_atoms(seq, "Root", HelperRuleRegistry(), {"expr": "Expr"}, {})
# After:   atoms = seq_to_atoms(seq, "Root", HelperRuleRegistry())
```

(Eight call sites in `test_seq_to_atoms.py`.)

- [ ] **Step 8: Full suite + lint**

```bash
uv run pytest tests/ -q
uv run ruff check src/ tests/
```

Expected: all green. (No behaviour change — dead args removed, classifier function-ised.)

- [ ] **Step 9: Commit**

```bash
git add -A
git commit -m "refactor(gbnf): git mv ast_utils/classify/seq_to_atoms; drop dead name_map/parent_of args; classify_rule()"
```

---

## Task 3 — `GbnfClassifier`, `GbnfConverter`, `IRBuilder.build()` body, thin `ir_builder.py`, `GbnfParser.parse()` returns `list[RuleSpec]`

Single atomic commit (per user direction). Twelve sub-steps. The cleaner-code findings (ws-rewrite in converter not builder; `is_start_rule`; classifier memoisation; symmetric body-taking protocol; hint-aware `assign_field_names`) all land here.

**Files:**
- Create: `src/lexic/grammars/gbnf/naming_hints.py`
- Modify: `src/lexic/ir/naming.py` (add hint params; remove hardcoded tables)
- Modify: `src/lexic/grammars/gbnf/classify.py` (add `GbnfClassifier`)
- Modify: `src/lexic/grammars/gbnf/seq_to_atoms.py` (add `GbnfConverter`; ws rewrite)
- Modify: `src/lexic/ir/protocols.py` (full `IRBuilder.build()` body)
- Move + rewrite: `src/lexic/codegen/ir_builder.py` → `src/lexic/grammars/gbnf/ir_builder.py`
- Move: `tests/unit/lexic/codegen/test_ir_builder.py` → `tests/unit/lexic/grammars/gbnf/test_ir_builder.py`
- Delete: `src/lexic/codegen/helpers.py`, `tests/unit/lexic/codegen/test_helpers.py`
- Modify: `src/lexic/grammars/gbnf/parser.py` (returns `list[RuleSpec]`)
- Modify: `src/lexic/codegen/__init__.py` (drop `IRBuilder` import; consume `list[RuleSpec]` directly)

- [ ] **Step 1: Create `src/lexic/grammars/gbnf/naming_hints.py`**

```python
"""GBNF-specific naming hint tables consumed by ir.naming.assign_field_names."""

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

- [ ] **Step 2: Update `src/lexic/ir/naming.py` — add hint params; remove hardcoded tables**

Delete the module-level `_CHARCLASS_NAMES` and `_LITERAL_NAMES` dicts. Update `assign_field_names`:

```python
def assign_field_names(
    atoms: Seq[Atom],
    *,
    charclass_names: dict[str, str] | None = None,
    literal_names: dict[str, str] | None = None,
) -> dict[str, int]:
    """Assign semantic field names to atoms. Per-rule scope; stateless.

    `charclass_names` and `literal_names` are flavour-supplied lookup tables.
    With None, generic fallbacks (sanitized pattern names) are used.
    """
    cc = charclass_names or {}
    lit = literal_names or {}
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
            field_map[unique(_charclass_field_name(atom, cc))] = i
        elif isinstance(atom, QuantifiedLiteralAtom):
            field_map[unique(_quantified_literal_field_name(atom.value, lit))] = i
        elif isinstance(atom, InlineRegexAtom):
            field_map[unique(_inline_regex_field_name(atom.gbnf))] = i

    return field_map


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


def _quantified_literal_field_name(value: str, literal_names: dict[str, str]) -> str:
    if value in literal_names:
        return literal_names[value]
    sanitized = re.sub(r"[^a-zA-Z0-9]", "_", value).strip("_").lower()[:12]
    return sanitized or "lit"
```

`_inline_regex_field_name` and `_sanitize_pattern` are unchanged.

- [ ] **Step 3: Add `encode_gbnf_escapes` to `src/lexic/grammars/gbnf/escapes.py`**

```python
_ENCODE_MAP = {
    "\n": "\\n",
    "\t": "\\t",
    "\r": "\\r",
    '"': '\\"',
    "\\": "\\\\",
}


def encode_gbnf_escapes(s: str) -> str:
    """Encode special chars to GBNF escape sequences. Inverse of decode_gbnf_escapes."""
    out: list[str] = []
    for ch in s:
        if ch in _ENCODE_MAP:
            out.append(_ENCODE_MAP[ch])
        elif 32 <= ord(ch) < 127:
            out.append(ch)
        elif ord(ch) <= 0xFF:
            out.append(f"\\x{ord(ch):02x}")
        elif ord(ch) <= 0xFFFF:
            out.append(f"\\u{ord(ch):04x}")
        else:
            out.append(f"\\U{ord(ch):08x}")
    return "".join(out)
```

(Backslash-and-quote handling first ensures `\\` doesn't double-encode. Tested in Task 5 via the existing GBNF round-trip property tests.)

- [ ] **Step 4: Update `src/lexic/grammars/gbnf/emitter.py` — call `encode_gbnf_escapes`**

Add the import and update the two LiteralAtom branches:

```python
# Add at top:
from lexic.grammars.gbnf.escapes import encode_gbnf_escapes

# In _atom_to_gbnf — Before:
if isinstance(atom, LiteralAtom):
    return f'"{atom.value}"'
...
if isinstance(atom, QuantifiedLiteralAtom):
    q = bounds_to_quantifier(atom.min, atom.max)
    return f'"{atom.value}"{q}'

# After:
if isinstance(atom, LiteralAtom):
    return f'"{encode_gbnf_escapes(atom.value)}"'
...
if isinstance(atom, QuantifiedLiteralAtom):
    q = bounds_to_quantifier(atom.min, atom.max)
    return f'"{encode_gbnf_escapes(atom.value)}"{q}'
```

- [ ] **Step 5: Update `src/lexic/grammars/gbnf/seq_to_atoms.py` — decode literals; add `GbnfConverter`; ws rewrite; hint-aware naming**

Add imports at top:

```python
from lexic.grammars.gbnf.escapes import decode_gbnf_escapes
from lexic.grammars.gbnf.naming_hints import CHARCLASS_NAMES, LITERAL_NAMES
from lexic.ir.protocols import SequenceConverter
```

Decode `Literal.value` everywhere a `LiteralAtom` or `QuantifiedLiteralAtom` is constructed (two sites in `seq_to_atoms`, two sites in `value_str_to_atoms`):

```python
# In seq_to_atoms — Before:
QuantifiedLiteralAtom(value=item.atom.value, min=min_, max=max_)
LiteralAtom(value=item.atom.value)
# After:
QuantifiedLiteralAtom(value=decode_gbnf_escapes(item.atom.value), min=min_, max=max_)
LiteralAtom(value=decode_gbnf_escapes(item.atom.value))

# In value_str_to_atoms — Before:
QuantifiedLiteralAtom(value=it.atom.value, min=min_, max=max_)
LiteralAtom(it.atom.value)
# After:
QuantifiedLiteralAtom(value=decode_gbnf_escapes(it.atom.value), min=min_, max=max_)
LiteralAtom(decode_gbnf_escapes(it.atom.value))
```

The helper-rule `assign_field_names(helper_atoms)` call (around line 164) gains the hint kwargs:

```python
helper_fm = assign_field_names(
    helper_atoms,
    charclass_names=CHARCLASS_NAMES,
    literal_names=LITERAL_NAMES,
)
```

Append the converter class at the bottom of the file:

```python
def _ws_optional(atom: Atom) -> Atom:
    """Mark a `RuleRefAtom("ws", ...)` as optional. GBNF convention."""
    if isinstance(atom, RuleRefAtom) and atom.rule_name == "ws":
        return RuleRefAtom(rule_name="ws", min=0, max=1)
    return atom


class GbnfConverter:
    """SequenceConverter[Sequence] for GBNF AST bodies."""

    def value_str_atoms(self, body: Alternation) -> list[Atom]:
        return value_str_to_atoms(body)

    def sequence_atoms(
        self,
        body: Sequence,
        cls_name: str,
        helpers: HelperRuleRegistry,
    ) -> tuple[list[Atom], dict[str, int]]:
        atoms = [_ws_optional(a) for a in seq_to_atoms(body, cls_name, helpers)]
        field_map = assign_field_names(
            atoms,
            charclass_names=CHARCLASS_NAMES,
            literal_names=LITERAL_NAMES,
        )
        return atoms, field_map
```

- [ ] **Step 6: Add `GbnfClassifier` to `src/lexic/grammars/gbnf/classify.py`**

Append after `classify_rule`:

```python
from lexic.grammars.gbnf.ast_utils import single_ruleref_of


class GbnfClassifier:
    """RuleClassifier[Rule] for GBNF AST nodes. Memoises classify_rule by id(rule)."""

    def __init__(self) -> None:
        self._cache: dict[int, Classification] = {}

    def _classify(self, rule: Rule) -> Classification:
        key = id(rule)
        cached = self._cache.get(key)
        if cached is None:
            cached = classify_rule(rule)
            self._cache[key] = cached
        return cached

    def rule_name(self, rule: Rule) -> str:
        return rule.name

    def kind(self, rule: Rule) -> str:
        c = self._classify(rule)
        if isinstance(c, (ValueStr, PureLiteralAlt)):
            return "value_str"
        if isinstance(c, NamedAlt):
            return "alternation"
        return "sequence"

    def is_start_rule(self, rule: Rule) -> bool:
        return rule.name == "root"

    def alternation_arm_nodes(self, rule: Rule) -> list[Sequence]:
        c = self._classify(rule)
        assert isinstance(c, NamedAlt)
        return c.arms

    def sequence_body(self, rule: Rule) -> Sequence:
        c = self._classify(rule)
        assert isinstance(c, SequenceKind)
        return c.body

    def value_str_body(self, rule: Rule) -> Alternation:
        c = self._classify(rule)
        assert isinstance(c, (ValueStr, PureLiteralAlt))
        return c.alt

    def single_ruleref(self, arm: Sequence) -> str | None:
        return single_ruleref_of(arm)
```

(`Classification` and the four variant dataclasses already exist in this file.)

- [ ] **Step 7: Implement `IRBuilder.build()` in `src/lexic/ir/protocols.py`**

Add the body imports and replace the `NotImplementedError` stub:

```python
# Top of file — add:
from lexic.ir.atoms import AlternationAtom
from lexic.utils.names import to_pascal


class IRBuilder(Generic[Node]):
    """list[Node] → list[RuleSpec]. Wired by the flavour layer."""

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
        return self._topo_sort(rules, primary + helpers.all_specs())

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
            body = self._classifier.value_str_body(rule)
            return [
                RuleSpec(
                    rule_name=rule_name,
                    class_name=cls_name,
                    parent_class_name=parent_cls,
                    kind="value_str",
                    items=self._converter.value_str_atoms(body),
                    field_map={},
                )
            ]
        if kind == "alternation":
            return self._build_named_alt(
                rule, rule_name, cls_name, parent_cls, name_map, helpers
            )
        body = self._classifier.sequence_body(rule)
        atoms, field_map = self._converter.sequence_atoms(body, cls_name, helpers)
        return [
            RuleSpec(
                rule_name=rule_name,
                class_name=cls_name,
                parent_class_name=parent_cls,
                kind="sequence",
                items=atoms,
                field_map=field_map,
            )
        ]

    def _build_named_alt(
        self,
        rule: Node,
        rule_name: str,
        cls_name: str,
        parent_cls: str,
        name_map: dict[str, str],
        helpers: HelperRuleRegistry,
    ) -> list[RuleSpec]:
        arm_rule_names: list[str] = []
        arm_specs: list[RuleSpec] = []
        for arm_idx, arm in enumerate(
            self._classifier.alternation_arm_nodes(rule), start=1
        ):
            ref = self._classifier.single_ruleref(arm)
            if ref is not None:
                arm_rule_names.append(ref)
                continue
            arm_rule_name = f"{rule_name}-arm{arm_idx}"
            arm_cls_name = f"{cls_name}Arm{arm_idx}"
            arm_rule_names.append(arm_rule_name)
            atoms, field_map = self._converter.sequence_atoms(arm, arm_cls_name, helpers)
            arm_specs.append(
                RuleSpec(
                    rule_name=arm_rule_name,
                    class_name=arm_cls_name,
                    parent_class_name=cls_name,
                    kind="sequence",
                    items=atoms,
                    field_map=field_map,
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

    def _topo_sort(
        self, rules: list[Node], specs: list[RuleSpec]
    ) -> list[RuleSpec]:
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

        start_rule = next(
            (r for r in rules if self._classifier.is_start_rule(r)), None
        )
        if start_rule is not None:
            start_name = self._classifier.rule_name(start_rule)
            start_spec = next((s for s in specs if s.rule_name == start_name), None)
            if start_spec is not None:
                visit(start_spec.class_name)
        for s in specs:
            visit(s.class_name)
        return ordered
```

- [ ] **Step 8: `git mv` `codegen/ir_builder.py` → `grammars/gbnf/ir_builder.py`; rewrite as thin wiring**

```bash
git mv src/lexic/codegen/ir_builder.py        src/lexic/grammars/gbnf/ir_builder.py
git mv tests/unit/lexic/codegen/test_ir_builder.py tests/unit/lexic/grammars/gbnf/test_ir_builder.py
```

Replace the contents of `src/lexic/grammars/gbnf/ir_builder.py` with:

```python
"""Thin GBNF wiring: IRBuilder[Rule](GbnfClassifier(), GbnfConverter()).build(rules)."""

from __future__ import annotations

from lexic.grammars.gbnf.ast import Rule
from lexic.grammars.gbnf.classify import GbnfClassifier
from lexic.grammars.gbnf.seq_to_atoms import GbnfConverter
from lexic.ir import IRBuilder, RuleSpec


def build_specs(rules: list[Rule]) -> list[RuleSpec]:
    """Convert a list of GBNF Rule AST nodes into IR RuleSpecs."""
    return IRBuilder(GbnfClassifier(), GbnfConverter()).build(rules)
```

Replace the contents of `tests/unit/lexic/grammars/gbnf/test_ir_builder.py` with a thin-wiring test (full round-trip parity lands in Task 5):

```python
"""Tests for grammars/gbnf/ir_builder.py — thin wiring."""
from __future__ import annotations

from pathlib import Path

from lexic.grammars.gbnf.ir_builder import build_specs
from lexic.grammars.gbnf.parser import parse_gbnf
from lexic.ir import RuleSpec

GROUND_TRUTH = Path(__file__).resolve().parents[5] / "resources" / "ground_truth"


def test_build_specs_returns_list_of_rule_spec():
    specs = build_specs(parse_gbnf('root ::= "hello"\n'))
    assert isinstance(specs, list)
    assert all(isinstance(s, RuleSpec) for s in specs)


def test_build_specs_root_first():
    specs = build_specs(parse_gbnf('root ::= "hello"\n'))
    assert specs[0].rule_name == "root"


def test_build_specs_arithmetic():
    text = (GROUND_TRUTH / "arithmetic.gbnf").read_text()
    specs = build_specs(parse_gbnf(text))
    assert len(specs) > 0
    assert specs[0].rule_name == "root"
```

(`parents[5]` from `tests/unit/lexic/grammars/gbnf/test_ir_builder.py`: `gbnf` → `grammars` → `lexic` → `unit` → `tests` → project root. Verified.)

- [ ] **Step 9: Delete `codegen/helpers.py` and its test**

```bash
git rm src/lexic/codegen/helpers.py
git rm tests/unit/lexic/codegen/test_helpers.py
```

- [ ] **Step 10: Update `src/lexic/grammars/gbnf/parser.py` — `GbnfParser.parse()` returns `list[RuleSpec]`**

```python
# Add at top:
from lexic.grammars.gbnf.ir_builder import build_specs
from lexic.ir import RuleSpec

# Replace the GbnfParser class:
class GbnfParser(FlavourParser):
    """GBNF flavour parser. Parses text and constructs IR in one step."""

    def parse(self, text: str) -> list[RuleSpec]:
        return build_specs(parse_gbnf(text))
```

(Drop the "Phase 2 will return list[RuleSpec]" comment.)

- [ ] **Step 11: Update `src/lexic/codegen/__init__.py` — drop `IRBuilder` import**

```python
# Imports — Before:
from lexic.codegen.ir_builder import IRBuilder
# After:
# (line removed)

# build_classes_and_specs — Before:
ast_rules = adapter.parser.parse(text)
specs = IRBuilder(ast_rules).build()
# After:
specs = adapter.parser.parse(text)
```

Drop the "Phase 1 / Phase 2" comment block.

- [ ] **Step 12: Full suite + lint, then commit**

```bash
uv run pytest tests/ -q
uv run ruff check src/ tests/
```

Expected: all green.

```bash
git add -A
git commit -m "refactor(gbnf): GbnfClassifier+GbnfConverter+IRBuilder.build; ws optional in converter; GbnfParser returns list[RuleSpec]"
```

---

## Task 4 — Create `parsing/`; move `lark_builder` + `transformer/`; remove all `decode_gbnf_escapes` calls

`LiteralAtom.value` and `QuantifiedLiteralAtom.value` are already canonical Python (Task 3 Step 5). `parsing/` therefore needs no decode calls. Five sites disappear; `_literal_is_quoted` simplifies; the `rule_name == "ws"` ref check is gone (already optional via `min=0`).

**Files:**
- Create: `src/lexic/parsing/__init__.py`
- Create: `tests/unit/lexic/parsing/__init__.py`
- Move: `src/lexic/codegen/lark_builder.py` → `src/lexic/parsing/lark_builder.py`
- Move: `src/lexic/codegen/transformer/` → `src/lexic/parsing/transformer/`
- Move: `tests/unit/lexic/codegen/test_lark_builder.py` → `tests/unit/lexic/parsing/test_lark_builder.py`
- Move: `tests/unit/lexic/codegen/transformer/` → `tests/unit/lexic/parsing/transformer/`
- Modify: `parsing/lark_builder.py` — drop decode imports + calls; drop `if atom.rule_name == "ws": return "ws?"`
- Modify: `parsing/transformer/build_transformer.py` — drop decode imports + calls
- Modify: `parsing/transformer/__init__.py` — internal import path
- Modify: `parsing/transformer/builders.py` / `registry.py` — internal import paths
- Modify: `src/lexic/compile.py` — `LarkBuilder` import path

- [ ] **Step 1: Create empty package markers**

```bash
mkdir -p src/lexic/parsing tests/unit/lexic/parsing
touch src/lexic/parsing/__init__.py
touch tests/unit/lexic/parsing/__init__.py
```

- [ ] **Step 2: `git mv` source**

```bash
git mv src/lexic/codegen/lark_builder.py src/lexic/parsing/lark_builder.py
git mv src/lexic/codegen/transformer    src/lexic/parsing/transformer
```

- [ ] **Step 3: `git mv` tests**

```bash
git mv tests/unit/lexic/codegen/test_lark_builder.py tests/unit/lexic/parsing/test_lark_builder.py
git mv tests/unit/lexic/codegen/transformer          tests/unit/lexic/parsing/transformer
```

- [ ] **Step 4: Update internal `transformer/` imports**

In `src/lexic/parsing/transformer/__init__.py`:
```python
# Before:  from lexic.codegen.transformer.build_transformer import build_transformer
# After:   from lexic.parsing.transformer.build_transformer import build_transformer
```

In `src/lexic/parsing/transformer/builders.py` (line 15) and `registry.py` (lines 15, 24): change `from lexic.codegen.transformer.<x>` → `from lexic.parsing.transformer.<x>`.

- [ ] **Step 5: Strip GBNF imports + decode calls from `parsing/lark_builder.py`**

Remove `from lexic.grammars.gbnf.escapes import decode_gbnf_escapes`.
Update transformer import: `from lexic.codegen.transformer import build_transformer` → `from lexic.parsing.transformer import build_transformer`.

In `_atom_to_lark`:

```python
# LiteralAtom branch — Before:
if isinstance(atom, LiteralAtom):
    decoded = decode_gbnf_escapes(atom.value)
    if any(c in decoded for c in "\n\t\r"):
        # ...regex emission...

# After:
if isinstance(atom, LiteralAtom):
    if any(c in atom.value for c in "\n\t\r"):
        # ...regex emission... (use atom.value in place of decoded throughout the block)

# RuleRefAtom branch — Before:
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

# QuantifiedLiteralAtom branch — Before:
if isinstance(atom, QuantifiedLiteralAtom):
    q = bounds_to_quantifier(atom.min, atom.max)
    decoded = decode_gbnf_escapes(atom.value)
    escaped = decoded.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"{q}'
# After:
if isinstance(atom, QuantifiedLiteralAtom):
    q = bounds_to_quantifier(atom.min, atom.max)
    escaped = atom.value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"{q}'
```

(The `if spec.rule_name == "ws": continue` lines at `lark_builder.py:99` + the trailing `lines.append(r"ws : /[ \t\n]+/")` block stay — out of slice B.5 scope. They are *string* uses, not imports.)

- [ ] **Step 6: Strip GBNF imports + decode calls from `parsing/transformer/build_transformer.py`**

Remove `from lexic.grammars.gbnf.escapes import decode_gbnf_escapes`.

`_literal_is_quoted` simplifies:

```python
# Before:
def _literal_is_quoted(lit_value: str) -> bool:
    decoded = decode_gbnf_escapes(lit_value)
    return not any(c in decoded for c in "\n\t\r")
# After:
def _literal_is_quoted(lit_value: str) -> bool:
    return not any(c in lit_value for c in "\n\t\r")
```

In `_build_instance`:

```python
# Before:
non_field_regex_values = {
    decode_gbnf_escapes(a.value)
    for a in spec.items
    if isinstance(a, LiteralAtom) and not _literal_is_quoted(a.value)
}
# After:
non_field_regex_values = {
    a.value
    for a in spec.items
    if isinstance(a, LiteralAtom) and not _literal_is_quoted(a.value)
}
```

In the value_str `make_value` closure (around line 138):

```python
# Before:
result.append(decode_gbnf_escapes(atom.value))
# After:
result.append(atom.value)
```

- [ ] **Step 7: Update `src/lexic/compile.py`**

```python
# Before:  from lexic.codegen.lark_builder import LarkBuilder
# After:   from lexic.parsing.lark_builder import LarkBuilder
```

If the module docstring references `lexic.codegen.lark_builder`, update to `lexic.parsing.lark_builder`.

- [ ] **Step 8: Update test imports**

`tests/unit/lexic/parsing/test_lark_builder.py`: `from lexic.codegen.lark_builder import ...` → `from lexic.parsing.lark_builder import ...`.

`tests/unit/lexic/parsing/transformer/*.py`: `from lexic.codegen.transformer.<x>` → `from lexic.parsing.transformer.<x>`.

- [ ] **Step 9: Full suite + lint**

```bash
uv run pytest tests/ -q
uv run ruff check src/ tests/
```

Expected: all green. The decode-once-at-parse change should be transparent — escape semantics are preserved end-to-end (decode at AST→IR; encode back at IR→GBNF text in the emitter).

- [ ] **Step 10: Commit**

```bash
git add -A
git commit -m "refactor(parsing): git mv lark_builder + transformer; remove all decode_gbnf_escapes (decode at AST→IR; encode in GbnfEmitter)"
```

---

## Task 5 — Round-trip tests + AST-based import-boundary test

**Files:**
- Modify: `tests/unit/lexic/ir/test_protocols.py` (append round-trip tests)
- Create: `tests/unit/lexic/parsing/test_import_boundary.py`

- [ ] **Step 1: Append IRBuilder round-trip tests to `tests/unit/lexic/ir/test_protocols.py`**

```python
from pathlib import Path

from lexic.grammars import get_adapter
from lexic.grammars.gbnf.classify import GbnfClassifier
from lexic.grammars.gbnf.parser import parse_gbnf
from lexic.grammars.gbnf.seq_to_atoms import GbnfConverter
from lexic.ir.protocols import IRBuilder

GROUND_TRUTH = Path(__file__).resolve().parents[4] / "resources" / "ground_truth"


def _build(text: str):
    return IRBuilder(GbnfClassifier(), GbnfConverter()).build(parse_gbnf(text))


def test_irbuilder_simple_value_str():
    specs = _build('root ::= "hello"\n')
    assert len(specs) == 1
    assert specs[0].rule_name == "root"
    assert specs[0].kind == "value_str"


def test_irbuilder_start_rule_first():
    specs = _build('root ::= expr\nexpr ::= [0-9]+\n')
    assert specs[0].rule_name == "root"


def test_irbuilder_matches_gbnf_parser_on_all_ground_truth_grammars():
    """IRBuilder produces specs identical to GbnfParser.parse() across the suite."""
    adapter = get_adapter("gbnf")
    for path in sorted(GROUND_TRUTH.glob("*.gbnf")):
        text = path.read_text()
        direct = IRBuilder(GbnfClassifier(), GbnfConverter()).build(parse_gbnf(text))
        via_parser = adapter.parser.parse(text)
        assert direct == via_parser, f"RuleSpec mismatch for {path.name}"
```

(`parents[4]` from `tests/unit/lexic/ir/test_protocols.py`: `ir/` → `lexic/` → `unit/` → `tests/` → project root. Verified against `tests/unit/lexic/codegen/test_init_codegen.py` which uses the same `parents[4]`.)

- [ ] **Step 2: Create `tests/unit/lexic/parsing/test_import_boundary.py` (AST walk)**

```python
"""Verify lexic.parsing imports nothing from lexic.grammars.*."""
from __future__ import annotations

import ast
import importlib.util
import pkgutil

FORBIDDEN_PREFIX = "lexic.grammars"


def _module_files_under(package: str) -> list[str]:
    spec = importlib.util.find_spec(package)
    assert spec is not None and spec.submodule_search_locations is not None
    files: list[str] = []
    for info in pkgutil.walk_packages(
        spec.submodule_search_locations, prefix=package + "."
    ):
        sub = importlib.util.find_spec(info.name)
        if sub and sub.origin and sub.origin != "built-in":
            files.append(sub.origin)
    return files


def _imports_from(source_file: str) -> set[str]:
    with open(source_file) as f:
        tree = ast.parse(f.read(), filename=source_file)
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
    return names


def test_parsing_does_not_import_grammars():
    violations: list[tuple[str, str]] = []
    for src_file in _module_files_under("lexic.parsing"):
        for imported in _imports_from(src_file):
            if imported == FORBIDDEN_PREFIX or imported.startswith(
                FORBIDDEN_PREFIX + "."
            ):
                violations.append((src_file, imported))
    assert not violations, (
        f"parsing/ has forbidden grammars imports:\n"
        + "\n".join(f"  {src}: {mod}" for src, mod in violations)
    )
```

- [ ] **Step 3: Run new tests in isolation, then full suite**

```bash
uv run pytest tests/unit/lexic/ir/test_protocols.py tests/unit/lexic/parsing/test_import_boundary.py -v
uv run pytest tests/ -q
uv run ruff check src/ tests/
```

Expected: all green.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "test(ir,parsing): IRBuilder round-trip with full RuleSpec equality; AST-based parsing/ import-boundary"
```

---

## Task 6 — Documentation

**Files:**
- Modify: `CLAUDE.md`
- Modify: `prototyping/next/2_ARCHITECTURE.md`
- Modify: `prototyping/next/3_ROADMAP.md`
- Modify: `docs/superpowers/specs/2026-04-23-slice-b-design.md`
- Modify: `docs/superpowers/specs/2026-04-24-slice-b5-package-restructure-design.md` (note that v2 plan supersedes the v1 *plan*; spec stays load-bearing for the architectural intent, with the cleaner-code amendments captured here)

- [ ] **Step 1: Update `CLAUDE.md` — project layout**

Replace the `## Project layout` block with:

```
src/lexic/
  __init__.py
  base.py                   GrammarModel base
  compile.py                compile(text) → CompiledGrammar
  exceptions.py             LexicError hierarchy
  generate.py               random string generator from RuleSpec
  parse.py                  parse(text, grammar_path) → GrammarModel
  ir/
    __init__.py             public IR surface (atoms, RuleSpec, protocols)
    atoms.py                seven Atom dataclasses
    spec.py                 RuleSpec dataclass
    protocols.py            RuleClassifier, SequenceConverter, HelperRuleRegistry, IRBuilder[Node]
    naming.py               assign_field_names (hint-aware)
    regex_portable.py       PORTABLE_FEATURES, validate_portable
  parsing/                  Lark machinery — zero lexic.grammars imports
    __init__.py
    lark_builder.py         LarkBuilder: list[RuleSpec] → Lark grammar string
    transformer/            build_transformer: Lark tree → Pydantic instance
  grammars/
    __init__.py             get_adapter, adapter_for_extension, register_adapter
    flavours.py             FlavourAdapter/Parser/Emitter protocols + ADAPTERS
    gbnf/                   GBNF flavour — thin overrides
      adapter.py            GbnfAdapter
      parser.py             GbnfParser: text → list[RuleSpec]
      emitter.py            GbnfEmitter (calls encode_gbnf_escapes)
      ir_builder.py         build_specs = IRBuilder(GbnfClassifier(), GbnfConverter()).build
      classify.py           classify_rule(rule); GbnfClassifier
      seq_to_atoms.py       seq_to_atoms; GbnfConverter (decodes literals at AST→IR)
      naming_hints.py       CHARCLASS_NAMES, LITERAL_NAMES
      ast.py                GBNF AST
      ast_utils.py          AST traversal helpers
      escapes.py            decode_gbnf_escapes, encode_gbnf_escapes
      charclass.py          GBNF bracket-expression parsing
  codegen/
    __init__.py             build_classes_and_specs, codegen, codegen_from_path
    model_emitter.py        ModelEmitter: list[RuleSpec] → Python source
  utils/
    __init__.py
    quantifiers.py
    names.py
```

Update the `## Architecture` pipeline diagram:

```
GBNF text
  → GbnfParser.parse()      [grammars/gbnf/]
    → parse_gbnf            (Lark meta-grammar → Rule AST)
    → IRBuilder(GbnfClassifier(), GbnfConverter()).build()   [ir/]
  → list[RuleSpec]
    → ModelEmitter          [codegen/]   → generated/*.py
    → GbnfEmitter           [grammars/gbnf/] → GBNF text  (encode_gbnf_escapes)
    → LarkBuilder           [parsing/]   → Lark grammar
    → build_transformer     [parsing/]   → Lark Transformer → Pydantic instance
```

In `## Key constraints`, add:

- `parsing/` has zero imports from `lexic.grammars.*`. Enforced by `tests/unit/lexic/parsing/test_import_boundary.py`.
- `ir/` has zero imports from `lexic.codegen`, `lexic.grammars`, or `lexic.parsing`.
- `LiteralAtom.value` and `QuantifiedLiteralAtom.value` are canonical Python (escapes decoded by `GbnfConverter`); `GbnfEmitter` re-encodes when emitting GBNF text.
- `GbnfParser.parse()` returns `list[RuleSpec]`.

- [ ] **Step 2: Update `prototyping/next/2_ARCHITECTURE.md`**

Update the target module-layout block to match the CLAUDE.md layout above. In Layering rules:

- Add: `parsing/` depends only on `ir/` and `utils/`. No `lexic.grammars.*` imports.
- Add: `ir/` depends only on `utils/`. No `codegen/`, `grammars/`, `parsing/` imports.
- Add: GBNF AST never crosses `grammars/gbnf/`'s boundary — the seam is `list[RuleSpec]`.
- Note: the `Node` TypeVar in `ir/protocols.py` is invariant. A second TypeVar for body-vs-rule asymmetry is deliberately not introduced (single-flavour codebase; revisit if a second flavour with a distinct AST hierarchy is added).
- Note: `"ws"` string literals in `parsing/` (`lark_builder.py:99` block; `transformer/build_transformer.py:97`; `transformer/builders.py:88`) are deliberately retained as a known soft seam. A future slice can replace them with an `IRBuilder`-emitted "drop-this-rule" hint or an `is_whitespace_rule(spec)` predicate.

In `codegen/` description: "Python source generation only — `model_emitter.py` + `__init__.py`."

- [ ] **Step 3: Update `prototyping/next/3_ROADMAP.md` — insert Slice B.5**

Insert between Slice B Phase 1 and Phase 2:

```markdown
### Slice B.5 — Package restructure (lands before Phase 2)

**Goal:** No GBNF imports outside `grammars/gbnf/`. Each package has one responsibility.

**Scope:**
- `ir/protocols.py`: `RuleClassifier[Node]`, `SequenceConverter[Node]`, `HelperRuleRegistry`, `IRBuilder[Node]`
- `ir/naming.py`: `assign_field_names` (hint-aware; moved from `codegen/`)
- `parsing/`: `lark_builder.py` + `transformer/` (moved from `codegen/`); no `lexic.grammars` imports
- `grammars/gbnf/`: `classify.py` (`classify_rule` + `GbnfClassifier`), `seq_to_atoms.py` (`GbnfConverter`), thin `ir_builder.py`, `naming_hints.py`, `escapes.py` gains `encode_gbnf_escapes`
- `codegen/`: shrinks to `__init__.py` + `model_emitter.py`
- `GbnfParser.parse()` returns `list[RuleSpec]`; `LiteralAtom.value` is canonical Python

**Exit criteria:**
- [ ] Files exist / removed per the layout in `2_ARCHITECTURE.md`.
- [ ] `GbnfParser.parse()` returns `list[RuleSpec]`; `codegen/__init__.py` has no `IRBuilder` import.
- [ ] `parsing/lark_builder.py` and `parsing/transformer/build_transformer.py` import nothing from `lexic.grammars.*`.
- [ ] `decode_gbnf_escapes` is invoked only inside `grammars/gbnf/`; `encode_gbnf_escapes` is invoked only by `GbnfEmitter`.
- [ ] `GbnfConverter.sequence_atoms` rewrites `RuleRefAtom("ws", …)` to `min=0`.
- [ ] `IRBuilder._compute_parents` and `_topo_sort` use only `RuleClassifier` protocol methods (`is_start_rule`, `single_ruleref`, etc.).
- [ ] All existing tests green; AST-based import-boundary test green; `uv run ruff check src/ tests/` clean.
```

- [ ] **Step 4: Update `docs/superpowers/specs/2026-04-23-slice-b-design.md`**

In §Architecture delta / Target module layout, add a top-of-section note:

```markdown
> **Amended by Slice B.5 (2026-04-24 spec; 2026-04-25 plan v2):** the layout below is
> superseded. See `2026-04-24-slice-b5-package-restructure-design.md` for the post-B.5
> structure; Phase 2 and Phase 3 of Slice B operate on that layout.
```

In §D1 ("Delete `LarkBuilder.build_transformer`"): note implementation lands in Slice B.5 Task 4 alongside the ws-ref-bounds rewrite.

- [ ] **Step 5: Update `docs/superpowers/specs/2026-04-24-slice-b5-package-restructure-design.md`**

Add a top-of-file note pointing at the v2 plan and listing the cleaner-code amendments (decode-at-parse-time, ws in converter, dead-arg removal, `is_start_rule`, hint-aware naming, AST-based boundary test). The architectural intent is unchanged.

- [ ] **Step 6: Full suite to confirm doc-only changes are inert**

```bash
uv run pytest tests/ -q
uv run ruff check src/ tests/
```

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "docs(slice-b5): update CLAUDE.md, 2_ARCHITECTURE.md, 3_ROADMAP.md, slice-b/b5 specs for v2 plan"
```

---

## Self-review pass

- **Spec coverage:** all 11 review findings folded in (1–11 from the audit); both `decode_gbnf_escapes` and `parent_of`/`name_map` deletions reflected. Exit criteria in roadmap line up with task outputs.
- **Placeholder scan:** none. Each step shows the actual code.
- **Type/symbol consistency:** `IRBuilder.build(rules: list[Node])` — yes; `RuleClassifier` methods used in Task 3 Step 7 all declared in Task 1 Step 3; `GbnfClassifier`/`GbnfConverter` live where Task 3 Step 11 imports them; `encode_gbnf_escapes` defined in Task 3 Step 3 and called in Task 3 Step 4; `_topo_sort` signature matches its callers (`build()` and itself).
- **Off-by-one paths:** `tests/unit/lexic/ir/test_protocols.py` → `parents[4]`; `tests/unit/lexic/grammars/gbnf/test_ir_builder.py` → `parents[5]`. Both verified against the existing convention (`tests/unit/lexic/codegen/test_init_codegen.py` uses `parents[4]`).
- **`LiteralAtom.value` semantics shift:** every constructor site is updated (Task 3 Step 5 — both `seq_to_atoms` and `value_str_to_atoms`); every consumer that previously decoded is updated (Task 4 Steps 5 + 6); the emitter now encodes (Task 3 Step 4). `model_emitter.py` consumes `LiteralAtom.value` for the generated `to_text()`; canonical Python is what's wanted there too — verified by inspection.
- **Atomicity of Task 3:** intentional (per user direction). The 12 sub-steps are listed in dependency order and the final commit lands them as one.

---

## Execution handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-25-slice-b5-package-restructure.md`. Two execution options:

**1. Subagent-Driven (recommended)** — fresh subagent per task, review between tasks.

**2. Inline Execution** — execute tasks in this session with checkpoints.

Per your standing rule ("ask before each task: subagent or manual?"), I'll pause before each task and ask either way. Which approach?
