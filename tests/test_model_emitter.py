# tests/test_model_emitter.py
from __future__ import annotations
import importlib
import sys
from pathlib import Path

import pytest
from abc import ABC
from typing import get_type_hints

from lexic.base import GrammarModel
from lexic.codegen import codegen
from lexic.ir import RuleSpec

GRAMMAR_DIR = Path(__file__).parent.parent / "resources" / "ground_truth"
GENERATED_DIR = Path(__file__).parent.parent / "generated"

ALL_GRAMMARS = ["arithmetic", "c", "chess", "japanese", "json_arr", "json_ws", "list"]


def _fresh(stem: str):
    name = f"generated.{stem}"
    if name in sys.modules:
        del sys.modules[name]
    codegen(GRAMMAR_DIR / f"{stem}.gbnf")
    return importlib.import_module(name)


# ── All grammars: __grammar__ present ─────────────────────────────────────────


@pytest.mark.parametrize("grammar", ALL_GRAMMARS)
def test_all_classes_have_grammar(grammar: str):
    from lexic.base import GrammarModel

    mod = _fresh(grammar)
    for name in dir(mod):
        cls = getattr(mod, name)
        if not (
            isinstance(cls, type) and issubclass(cls, __import__("pydantic").BaseModel)
        ):
            continue
        if cls is GrammarModel:
            continue
        assert hasattr(cls, "__grammar__") and isinstance(
            cls.__dict__.get("__grammar__"), RuleSpec
        ), f"{grammar}.{name} is missing __grammar__ or it is not a RuleSpec instance"


@pytest.mark.parametrize("grammar", ALL_GRAMMARS)
def test_no_field_n_names(grammar: str):
    import re

    mod = _fresh(grammar)
    for name in dir(mod):
        cls = getattr(mod, name)
        if not (
            isinstance(cls, type) and issubclass(cls, __import__("pydantic").BaseModel)
        ):
            continue
        for fname in get_type_hints(cls):
            assert not re.fullmatch(r"field\d+", fname), (
                f"{grammar}.{name} has positional field name '{fname}'"
            )


@pytest.mark.parametrize("grammar", ALL_GRAMMARS)
def test_generated_imports_grammar_model(grammar: str):
    stem = grammar
    codegen(GRAMMAR_DIR / f"{stem}.gbnf")
    source = (GENERATED_DIR / f"{stem}.py").read_text()
    assert "GrammarModel" in source, f"{stem}.py must import and use GrammarModel"
    assert "from lexic.base import GrammarModel" in source or "GrammarModel" in source


@pytest.mark.parametrize("grammar", ALL_GRAMMARS)
def test_no_to_text_defined_in_source(grammar: str):
    """to_text() must NOT be defined in generated source — it is inherited."""
    stem = grammar
    codegen(GRAMMAR_DIR / f"{stem}.gbnf")
    source = (GENERATED_DIR / f"{stem}.py").read_text()
    assert "def to_text" not in source, (
        f"{stem}.py must not define to_text() — inherited from GrammarModel"
    )


# ── arithmetic: specific class structure ──────────────────────────────────────


@pytest.fixture(scope="module")
def arithmetic_mod():
    return _fresh("arithmetic")


def test_arithmetic_term_is_abstract(arithmetic_mod):
    term: type[GrammarModel] = arithmetic_mod.Term
    assert term.__grammar__.kind == "alternation"
    assert issubclass(term, ABC)


def test_arithmetic_ident_parent_is_term(arithmetic_mod):
    ident: type[GrammarModel] = arithmetic_mod.Ident
    assert ident.__grammar__.kind == "sequence"
    assert issubclass(ident, arithmetic_mod.Term)


def test_arithmetic_ident_fields(arithmetic_mod):
    hints = get_type_hints(arithmetic_mod.Ident)
    assert "first" in hints
    assert hints["first"] is str
    assert "second" in hints
    assert hints["second"] is str
    assert "ws" in hints


def test_arithmetic_ws_is_value_str(arithmetic_mod):
    assert arithmetic_mod.Ws.__grammar__.kind == "value_str"
    hints = get_type_hints(arithmetic_mod.Ws)
    assert "value" in hints
    assert hints["value"] is str


def test_arithmetic_root_has_list_field(arithmetic_mod):
    from typing import get_origin

    hints = get_type_hints(arithmetic_mod.Root)
    list_fields = [f for f, h in hints.items() if get_origin(h) is list]
    assert len(list_fields) >= 1, "Root must have at least one List field"
