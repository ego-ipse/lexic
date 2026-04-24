from pathlib import Path

import pytest

from lexic.codegen import (
    build_classes_and_specs,
    codegen,
    codegen_from_path,
)
from lexic.ir import RuleSpec

GROUND_TRUTH = Path(__file__).resolve().parents[4] / "resources" / "ground_truth"


def test_codegen_takes_string_and_stem():
    text = (GROUND_TRUTH / "arithmetic.gbnf").read_text()
    classes = codegen(text, stem="arithmetic")
    assert classes
    assert all(isinstance(v, type) for v in classes.values())


def test_codegen_from_path_reads_and_delegates():
    classes = codegen_from_path(GROUND_TRUTH / "arithmetic.gbnf")
    assert classes


def test_build_classes_and_specs_returns_both():
    text = (GROUND_TRUTH / "arithmetic.gbnf").read_text()
    classes, specs = build_classes_and_specs(text, stem="arithmetic")
    assert classes
    assert isinstance(specs, list)
    assert specs
    assert all(isinstance(s, RuleSpec) for s in specs)


def test_codegen_and_build_classes_and_specs_produce_identical_classes():
    """codegen() is a thin wrapper; class objects are instance-equal."""
    text = (GROUND_TRUTH / "arithmetic.gbnf").read_text()
    classes_only = codegen(text, stem="arithmetic_a")
    classes_tuple, _ = build_classes_and_specs(text, stem="arithmetic_b")
    assert set(classes_only.keys()) == set(classes_tuple.keys())


def test_codegen_rejects_positional_stem():
    """Stem must be keyword-only to prevent accidental path-as-text calls."""
    text = (GROUND_TRUTH / "arithmetic.gbnf").read_text()
    with pytest.raises(TypeError):
        codegen(text, "arithmetic")  # type: ignore[misc]
