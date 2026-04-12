from pathlib import Path

import pytest
from pydantic import BaseModel

from src.codegen import build

GRAMMAR_DIR = Path("resources/ground_truth")
ALL_GRAMMARS = sorted(GRAMMAR_DIR.glob("*.gbnf*"))


# ── json_ws inheritance ───────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def json_ws():
    return build(GRAMMAR_DIR / "json_ws.gbnf")


def test_json_ws_value_hierarchy(json_ws):
    assert json_ws["ObjectValue"].__bases__ == (json_ws["Value"],)
    assert json_ws["ArrayValue"].__bases__ == (json_ws["Value"],)
    assert "Value" in json_ws
    assert "Object" in json_ws
    assert "Array" in json_ws


def test_json_ws_root_is_subclass_of_object(json_ws):
    assert issubclass(json_ws["Root"], json_ws["Object"])


def test_json_ws_field_types(json_ws):
    # Object must have at least one Pydantic field
    assert json_ws["Object"].model_fields

    # ObjectValue must have a field whose annotation resolves to the Object class
    ov_fields = json_ws["ObjectValue"].model_fields
    assert any(
        info.annotation is json_ws["Object"] or info.annotation == "Object"
        for info in ov_fields.values()
    )


def test_abstract_base_has_no_required_fields(json_ws):
    # Value is a pass-body abstract base — no required fields
    assert not json_ws["Value"].model_fields


# ── all grammars parse ────────────────────────────────────────────────────────


@pytest.mark.parametrize("grammar_path", ALL_GRAMMARS, ids=lambda p: p.name)
def test_all_grammars_parse(grammar_path):
    mods = build(grammar_path)
    assert mods, f"No classes generated from {grammar_path.name}"
    assert all(issubclass(cls, BaseModel) for cls in mods.values())


# ── arithmetic ────────────────────────────────────────────────────────────────


def test_arithmetic_structure():
    mods = build(GRAMMAR_DIR / "arithmetic.gbnf")
    assert "Root" in mods


# ── module naming ─────────────────────────────────────────────────────────────


def test_module_naming(json_ws):
    for cls in json_ws.values():
        assert cls.__module__ == "src.generated.json_ws", cls
