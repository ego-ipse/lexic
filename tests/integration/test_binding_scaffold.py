"""TEMPORARY scaffolding gate (Task 3) — binding view vs derive parity.

Asserts that the new grammar-pass + binding pipeline
(``build_codegen_grammar`` → ``compute_binding``) reproduces ``derive_specs``'s
output — same rule order, class names, parents, kinds, field→index maps and
non-semantic field sets — on every ground-truth grammar, and that the bound
fold modes match the retired wrapper-mode rule (inlined below — models.py is
gone since the Task 5 flip).

DELETE together with ``ir/derive.py`` in Task 6. No deliberate divergences are
exercised by this corpus; the divergences that exist are all outside it
(binding raises on unknown atom types where derive skipped them silently, and
``hoist_arms`` refuses an ``-arm<N>`` name collision where derive shadowed).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lexic.codegen.binding import RuleBinding, compute_binding
from lexic.codegen.passes import build_codegen_grammar
from lexic.ir.base import IrNoneType
from lexic.ir.derive import derive_specs
from lexic.ir.nodes import (
    IrAlternation,
    IrCharClass,
    IrItem,
    IrLiteral,
    IrRuleRef,
)
from lexic.ir.spec import RuleSpec
from tests.integration._codegen_pipeline import canonical_ast
from tests.paths import GROUND_TRUTH

_GRAMMARS = sorted(GROUND_TRUTH.glob("*.gbnf")) + sorted(GROUND_TRUTH.glob("*.abnf"))


def _both(path: Path) -> tuple[list[RuleSpec], list[RuleBinding]]:
    """(derive specs, binding view) for one grammar file.

    Both pipelines under comparison start from the identical
    :func:`~tests.integration._codegen_pipeline.canonical_ast`.
    """
    ast = canonical_ast(path)
    return derive_specs(ast), compute_binding(build_codegen_grammar(ast))


@pytest.mark.parametrize("path", _GRAMMARS, ids=lambda p: p.name)
def test_binding_matches_derive_rule_order(path: Path):
    """Emission order (rule name sequence) is identical to topo-sorted specs."""
    specs, bindings = _both(path)
    assert [b.rule_name for b in bindings] == [s.rule_name for s in specs]


@pytest.mark.parametrize("path", _GRAMMARS, ids=lambda p: p.name)
def test_binding_matches_derive_classes_parents_kinds(path: Path):
    """Per rule: same class name, parent class, and kind."""
    specs, bindings = _both(path)
    got = [(b.class_name, b.parent_class_name, b.kind) for b in bindings]
    want = [(s.class_name, s.parent_class_name, s.kind) for s in specs]
    assert got == want


@pytest.mark.parametrize("path", _GRAMMARS, ids=lambda p: p.name)
def test_binding_matches_derive_field_maps(path: Path):
    """Per rule: same field name → item index map."""
    specs, bindings = _both(path)
    got = [{name: bind.item for name, bind in b.fields.items()} for b in bindings]
    assert got == [s.field_map for s in specs]


@pytest.mark.parametrize("path", _GRAMMARS, ids=lambda p: p.name)
def test_binding_matches_derive_non_semantic_fields(path: Path):
    """Per rule: the semantic=False binds are exactly derive's noise fields."""
    specs, bindings = _both(path)
    got = [
        frozenset(name for name, bind in b.fields.items() if not bind.semantic)
        for b in bindings
    ]
    assert got == [s.non_semantic_fields for s in specs]


def _expected_mode(item: IrItem) -> str:
    """The retired models.py ``_wrapper_mode`` rule, inlined for the gate:
    terminal atoms → text; literal-only group → gtext; ref / ref-bearing
    group → model, or models when hi > 1 or unbounded."""
    atom = item.atom
    if isinstance(atom, (IrCharClass, IrLiteral)):
        return "text"
    hi = item.quantifier.hi
    many = isinstance(hi, IrNoneType) or int(hi) > 1
    if isinstance(atom, IrRuleRef):
        return "models" if many else "model"
    assert isinstance(atom, IrAlternation), type(atom).__name__
    has_ref = any(
        isinstance(sub.atom, IrRuleRef)
        for arm in atom
        for sub in arm
        if isinstance(sub, IrItem)
    )
    if has_ref:
        return "models" if many else "model"
    return "gtext"


@pytest.mark.parametrize("path", _GRAMMARS, ids=lambda p: p.name)
def test_binding_modes_match_wrapper_modes(path: Path):
    """Every bound field's mode equals the retired wrapper-mode rule."""
    specs, bindings = _both(path)
    for spec, binding in zip(specs, bindings):
        if spec.kind != "sequence":
            continue
        for name, index in spec.field_map.items():
            item = spec.items[index]
            assert isinstance(item, IrItem)
            assert binding.fields[name].mode == _expected_mode(item), (
                f"{spec.rule_name}.{name}"
            )
