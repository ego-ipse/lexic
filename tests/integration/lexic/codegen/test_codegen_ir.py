"""Codegen-grammar gate — the binding-driven synthesis path.

For every ground-truth grammar, drives the front half of the pipeline
(``parse_grammar`` → ``canonicalize`` → semantic flags →
``build_codegen_grammar`` → ``compute_binding``) and then ``synthesize``,
asserting each synthesized class:

- is a valid :class:`~lexic.model.GrammarModel` record;
- carries each field's :class:`~lexic.ir.spine.bind.IrBind` (readable through the
  public ``bound_fields()``) and a per-class ``__grammar__: IrRule`` from the
  codegen grammar.

This is the same synthesis path ``lexic.compile`` drives; it is exercised here
by direct invocation across every flavour/grammar.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lexic.compile.pipeline.moments import build_codegen_grammar
from lexic.compile.pipeline.rulemap import RuleMap, compute_binding
from lexic.compile.pipeline.synthesis import synthesize
from lexic.ir import IrBind, IrRule
from lexic.model import GrammarModel
from tests.integration.lexic.codegen.codegen_pipeline import canonical_ast
from tests.paths import GROUND_TRUTH

GRAMMARS = sorted(GROUND_TRUTH.glob("*.gbnf")) + sorted(GROUND_TRUTH.glob("*.abnf"))


def emit(path: Path) -> tuple[list[RuleMap], dict[str, type]]:
    """Run the synthesis path; return (binding, classes)."""
    canonical = canonical_ast(path)
    codegen_grammar = build_codegen_grammar(canonical)
    binding = compute_binding(codegen_grammar)
    flavour = "abnf" if path.suffix == ".abnf" else "gbnf"
    stem = f"emit_{path.stem}_{flavour}"
    classes = synthesize(codegen_grammar, binding, stem)
    return binding, classes


@pytest.mark.parametrize("path", GRAMMARS, ids=lambda p: p.name)
def test_generated_classes_are_valid_models(path: Path):
    """Every synthesized class is a GrammarModel record class."""
    binding, classes = emit(path)
    assert set(classes) == {b.class_name for b in binding}
    for cls in classes.values():
        assert issubclass(cls, GrammarModel)


@pytest.mark.parametrize("path", GRAMMARS, ids=lambda p: p.name)
def test_fields_carry_irbind_and_grammar_footer(path: Path):
    """Sequence fields expose their IrBind; each class carries an IrRule footer."""
    binding, classes = emit(path)
    by_name = {b.class_name: b for b in binding}
    for name, cls in classes.items():
        assert isinstance(cls.__grammar__, IrRule)
        bind = by_name[name]
        bound = cls.bound_fields()
        for field_name, ibind in bind.fields.items():
            assert isinstance(ibind, IrBind)
            assert bound[ibind.item] == (field_name, ibind), (
                f"{name}.{field_name} missing {ibind!r}"
            )
