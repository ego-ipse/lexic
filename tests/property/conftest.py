"""Session-scoped RuleSpec fixtures for all 7 ground-truth grammars."""

from __future__ import annotations

from pathlib import Path

import pytest

from lexic.codegen.ir_builder import IRBuilder
from lexic.grammars.gbnf.parser import parse_gbnf
from tests.paths import GROUND_TRUTH

ALL_GRAMMARS = ["arithmetic", "c", "chess", "japanese", "json_arr", "json_ws", "list"]


@pytest.fixture(scope="session")
def all_grammar_specs() -> dict[str, dict]:
    result = {}
    for name in ALL_GRAMMARS:
        text = (GROUND_TRUTH / f"{name}.gbnf").read_text()
        specs = IRBuilder(parse_gbnf(text)).build()
        result[name] = {s.rule_name: s for s in specs}
    return result


@pytest.fixture(scope="session")
def grammar_dir() -> Path:
    return GROUND_TRUTH
