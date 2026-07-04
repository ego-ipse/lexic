"""Session-scoped grammar-rule fixtures for all 7 ground-truth grammars."""

from __future__ import annotations

from pathlib import Path

import pytest

from lexic.compile import canonical_grammar
from lexic.grammars.gbnf import GBNF_FLAVOUR
from tests.paths import GROUND_TRUTH

ALL_GRAMMARS = ["arithmetic", "c", "chess", "japanese", "json_arr", "json_ws", "list"]


@pytest.fixture(scope="session")
def all_grammar_specs() -> dict[str, dict]:
    """Compile all ground-truth grammars once, returning {name: {rule_name: IrRule}}.

    The inner mapping is the rules-by-name view :func:`lexic.generate.generate`
    walks (canonical grammar, directives applied).
    """
    result = {}
    for name in ALL_GRAMMARS:
        text = (GROUND_TRUTH / f"{name}.gbnf").read_text()
        ast = canonical_grammar(text, GBNF_FLAVOUR)
        result[name] = {r.name: r for r in ast.rules}
    return result


@pytest.fixture(scope="session")
def grammar_dir() -> Path:
    """Return the ground-truth grammars directory."""
    return GROUND_TRUTH
