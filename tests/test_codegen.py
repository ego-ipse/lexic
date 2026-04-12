"""
pytest test suite for src/codegen.py — covers all 7 GBNF grammars.
"""

from pathlib import Path

import pytest
from pydantic import BaseModel

import tempfile

from src.codegen import build, build_file, generate

GRAMMAR_DIR = Path("resources/ground_truth")
ALL_GRAMMARS = sorted(GRAMMAR_DIR.glob("*.gbnf*"))


# ---------------------------------------------------------------------------
# 1. json_ws SOLID inheritance hierarchy
# ---------------------------------------------------------------------------


def test_json_ws_inheritance():
    mods = build(GRAMMAR_DIR / "json_ws.gbnf")
    # Abstract base and its concrete subclasses
    assert mods["ObjectValue"].__bases__ == (mods["Value"],)
    assert mods["ArrayValue"].__bases__ == (mods["Value"],)
    # Root is a subclass of Object (single-ref rule)
    assert issubclass(mods["Root"], mods["Object"])
    # All expected top-level classes are present
    assert "Value" in mods
    assert "Object" in mods
    assert "Array" in mods


# ---------------------------------------------------------------------------
# 2. json_ws field type structure
# ---------------------------------------------------------------------------


def test_json_ws_field_types():
    mods = build(GRAMMAR_DIR / "json_ws.gbnf")
    # Object has at least one pydantic field
    assert len(mods["Object"].model_fields) >= 1
    # ObjectValue has a field typed to Object
    ov_fields = mods["ObjectValue"].model_fields
    assert len(ov_fields) >= 1
    field_annotation = next(iter(ov_fields.values())).annotation
    assert field_annotation is mods["Object"]


# ---------------------------------------------------------------------------
# 3. All 7 grammars parse without error
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("grammar_path", ALL_GRAMMARS, ids=lambda p: p.name)
def test_all_grammars_parse(grammar_path: Path):
    mods = build(grammar_path)
    # Must return a non-empty dict
    assert len(mods) > 0
    # Every value must be a BaseModel subclass
    for name, cls in mods.items():
        assert issubclass(cls, BaseModel), f"{name} is not a BaseModel subclass"


# ---------------------------------------------------------------------------
# 4. arithmetic.gbnf basic structure
# ---------------------------------------------------------------------------


def test_arithmetic_structure():
    mods = build(GRAMMAR_DIR / "arithmetic.gbnf")
    assert "Root" in mods
    assert len(mods) > 0


# ---------------------------------------------------------------------------
# 5. Module naming
# ---------------------------------------------------------------------------


def test_module_naming():
    mods = build(GRAMMAR_DIR / "json_ws.gbnf")
    for cls in mods.values():
        assert cls.__module__ == "src.generated.json_ws", (
            f"{cls.__name__}.__module__ == {cls.__module__!r}"
        )


# ---------------------------------------------------------------------------
# 6. Abstract base has no required fields; subclasses have fields
# ---------------------------------------------------------------------------


def test_abstract_base_has_no_required_fields():
    mods = build(GRAMMAR_DIR / "json_ws.gbnf")
    # Value is the abstract base — it has no fields (just `pass`)
    assert mods["Value"].model_fields == {}
    # ObjectValue is a concrete subclass — it has at least one field
    assert len(mods["ObjectValue"].model_fields) >= 1


# ---------------------------------------------------------------------------
# 7. generate / build / load separation
# ---------------------------------------------------------------------------


def test_generate_returns_string():
    code = generate(GRAMMAR_DIR / "json_ws.gbnf")
    assert isinstance(code, str)
    assert "class Value(BaseModel)" in code
    assert "class ObjectValue(Value)" in code


def test_build_writes_file():
    with tempfile.TemporaryDirectory() as tmp:
        out = build_file(GRAMMAR_DIR / "json_ws.gbnf", output_dir=tmp)
        assert out.exists()
        assert out.suffix == ".py"
        content = out.read_text()
        assert "class Value(BaseModel)" in content


def test_load_returns_live_classes():
    mods = build(GRAMMAR_DIR / "json_ws.gbnf")
    assert isinstance(mods, dict)
    assert len(mods) > 0
    for cls in mods.values():
        assert isinstance(cls, type)
        assert issubclass(cls, BaseModel)
