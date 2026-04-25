from pathlib import Path

import pytest

from lexic.codegen import codegen, codegen_from_path
from lexic.exceptions import UnsupportedConstructError

GROUND_TRUTH = Path(__file__).resolve().parents[4] / "resources" / "ground_truth"


def test_codegen_rejects_positional_stem():
    """Stem must be keyword-only to prevent accidental path-as-text calls."""
    text = (GROUND_TRUTH / "arithmetic.gbnf").read_text()
    with pytest.raises(TypeError):
        codegen(text, "arithmetic")  # type: ignore[misc]


def test_codegen_unknown_flavour_raises():
    text = (GROUND_TRUTH / "arithmetic.gbnf").read_text()
    with pytest.raises(UnsupportedConstructError):
        codegen(text, stem="arith_flavour_test", flavour="abnf")


def test_codegen_from_path_unknown_flavour_raises():
    with pytest.raises(UnsupportedConstructError):
        codegen_from_path(GROUND_TRUTH / "arithmetic.gbnf", flavour="abnf")
