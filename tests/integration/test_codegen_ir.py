"""Codegen gate — the binding-driven emit path.

For every ground-truth grammar, drives the front half of the codegen pipeline
(``parse_grammar`` → ``canonicalize`` → semantic flags →
``build_codegen_grammar`` → ``compute_binding``) and then the emit entry
(``codegen``), asserting the emitted module:

- imports and every generated class is a valid Pydantic model;
- carries each field's :class:`~lexic.ir.bind.IrBind` in its metadata and a
  per-class ``__grammar__: IrRule`` from the codegen grammar;
- footers ``GRAMMAR`` (the canonical, pre-pass AST) and ``START`` that re-import
  to the exact objects; and
- is ruff-format stable (re-formatting the written source is a no-op).

This is the same emit path ``compile.py`` drives; it is exercised here by
direct invocation across every flavour/grammar.
"""

from __future__ import annotations

import importlib
import subprocess
from pathlib import Path

import pytest
from ruff import find_ruff_bin

from lexic.base import GrammarModel
from lexic.codegen import codegen
from lexic.codegen.binding import RuleBinding, compute_binding
from lexic.codegen.passes import build_codegen_grammar
from lexic.ir.bind import IrBind
from lexic.ir.nodes import IrAst, IrRule
from tests.integration._codegen_pipeline import canonical_ast
from tests.paths import GENERATED, GROUND_TRUTH

_GRAMMARS = sorted(GROUND_TRUTH.glob("*.gbnf")) + sorted(GROUND_TRUTH.glob("*.abnf"))


def _emit(path: Path) -> tuple[IrAst, list[RuleBinding], str, dict[str, type]]:
    """Run the emit path; return (canonical, binding, stem, classes)."""
    canonical = canonical_ast(path)
    codegen_grammar = build_codegen_grammar(canonical)
    binding = compute_binding(codegen_grammar)
    suffix = "_abnf" if path.suffix == ".abnf" else ""
    stem = f"iremit_{path.stem}{suffix}"
    classes = codegen(canonical, codegen_grammar, binding, stem)
    return canonical, binding, stem, classes


@pytest.mark.parametrize("path", _GRAMMARS, ids=lambda p: p.name)
def test_generated_classes_are_valid_models(path: Path):
    """Every emitted class imports and rebuilds as a Pydantic GrammarModel."""
    _, binding, _, classes = _emit(path)
    assert set(classes) == {b.class_name for b in binding}
    for cls in classes.values():
        assert issubclass(cls, GrammarModel)
        cls.model_rebuild()
        cls.model_json_schema()


@pytest.mark.parametrize("path", _GRAMMARS, ids=lambda p: p.name)
def test_fields_carry_irbind_and_grammar_footer(path: Path):
    """Sequence fields expose their IrBind; each class carries an IrRule footer."""
    _, binding, _, classes = _emit(path)
    by_name = {b.class_name: b for b in binding}
    for name, cls in classes.items():
        assert isinstance(cls.__grammar__, IrRule)
        bind = by_name[name]
        for field_name, ibind in bind.fields.items():
            metadata = cls.model_fields[field_name].metadata
            assert ibind in metadata, f"{name}.{field_name} missing {ibind!r}"
            assert isinstance(ibind, IrBind)


@pytest.mark.parametrize("path", _GRAMMARS, ids=lambda p: p.name)
def test_module_footer_reimports_to_canonical(path: Path):
    """GRAMMAR (canonical AST) and START re-import to the exact objects."""
    canonical, _, stem, _ = _emit(path)
    module = importlib.import_module(f"generated.{stem}")
    assert module.GRAMMAR == canonical
    assert module.START == canonical.start


@pytest.mark.parametrize("path", _GRAMMARS, ids=lambda p: p.name)
def test_emitted_source_is_ruff_format_stable(path: Path):
    """Re-formatting the written module is a no-op (formatting is idempotent)."""
    _, _, stem, _ = _emit(path)
    source = (GENERATED / f"{stem}.py").read_text(encoding="utf-8")
    result = subprocess.run(
        [find_ruff_bin(), "format", "-"],
        input=source,
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout == source
