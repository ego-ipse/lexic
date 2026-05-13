"""Session-scoped RuleSpec fixtures for all 7 ground-truth grammars."""

from __future__ import annotations

from pathlib import Path

import pytest

from lexic.compile import compile_grammar
from lexic.grammars.gbnf.flavour import GbnfFlavour
from tests.paths import GROUND_TRUTH

ALL_GRAMMARS = ["arithmetic", "c", "chess", "japanese", "json_arr", "json_ws", "list"]


@pytest.fixture(scope="session")
def all_grammar_specs() -> dict[str, dict]:
    result = {}
    for name in ALL_GRAMMARS:
        text = (GROUND_TRUTH / f"{name}.gbnf").read_text()
        _, specs_list = compile_grammar(text, GbnfFlavour)
        result[name] = {s.rule_name: s for s in specs_list}
    return result


@pytest.fixture(scope="session")
def grammar_dir() -> Path:
    return GROUND_TRUTH
