"""Property-based addressed emission: generate → parse → addresses hold.

The corpus gates in
``tests/integration/lexic/roundtrip/test_addressed_emission.py`` pin the
contract on fixed seeds; this drives it over random documents, where the
shapes that break an offset walk actually live — empty repeated fields,
adjacent equal siblings, whitespace runs that spell nothing.

Integers are RNG seeds rather than grammar-aware strategies, the same
discipline ``test_roundtrip`` uses: shrinking navigates numerically, but a
failing seed is reproducible and replayable.
"""

from __future__ import annotations

import random

import hypothesis.strategies as st
from hypothesis import HealthCheck, given, settings

from lexic.compile import compile_from_path
from lexic.generate import generate
from tests.addressed_helpers import check_addressed
from tests.paths import GROUND_TRUTH as _GRAMMAR_DIR


def addressed(grammar: str, specs: dict, seed: int) -> None:
    """Generate at ``seed``, parse, and assert the addressed-emission contract.

    :param grammar: The ground-truth grammar's stem.
    :param specs: Its rules-by-name view, for generation.
    :param seed: The RNG seed hypothesis chose.
    """
    text = generate("root", specs, rng=random.Random(seed), max_depth=4)
    if not text:
        return  # a star-rooted rule rolled empty; nothing to address
    model = compile_from_path(_GRAMMAR_DIR / f"{grammar}.gbnf").parse(text)
    check_addressed(model, f"{grammar} seed={seed}")


@given(seed=st.integers(min_value=0, max_value=2**32 - 1))
@settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow])
def test_arithmetic_addressed(seed: int, all_grammar_specs: dict) -> None:
    """Arithmetic documents address cleanly for random seeds."""
    addressed("arithmetic", all_grammar_specs["arithmetic"], seed)


@given(seed=st.integers(min_value=0, max_value=2**32 - 1))
@settings(max_examples=20, suppress_health_check=[HealthCheck.too_slow])
def test_json_ws_addressed(seed: int, all_grammar_specs: dict) -> None:
    """JSON-with-whitespace exercises noise rules that spell nothing."""
    addressed("json_ws", all_grammar_specs["json_ws"], seed)


@given(seed=st.integers(min_value=0, max_value=2**32 - 1))
@settings(max_examples=20, suppress_health_check=[HealthCheck.too_slow])
def test_json_arr_addressed(seed: int, all_grammar_specs: dict) -> None:
    """JSON-array exercises repeated fields, including empty ones."""
    addressed("json_arr", all_grammar_specs["json_arr"], seed)


@given(seed=st.integers(min_value=0, max_value=2**32 - 1))
@settings(max_examples=20, suppress_health_check=[HealthCheck.too_slow])
def test_japanese_addressed(seed: int, all_grammar_specs: dict) -> None:
    """Japanese is the wide-glyph case: spans stay in CODE UNITS (D1)."""
    addressed("japanese", all_grammar_specs["japanese"], seed)


@given(seed=st.integers(min_value=0, max_value=2**32 - 1))
@settings(max_examples=20, suppress_health_check=[HealthCheck.too_slow])
def test_list_addressed(seed: int, all_grammar_specs: dict) -> None:
    """List documents address cleanly for random seeds."""
    addressed("list", all_grammar_specs["list"], seed)


@given(seed=st.integers(min_value=0, max_value=2**32 - 1))
@settings(max_examples=20, suppress_health_check=[HealthCheck.too_slow])
def test_chess_addressed(seed: int, all_grammar_specs: dict) -> None:
    """Chess documents address cleanly for random seeds."""
    addressed("chess", all_grammar_specs["chess"], seed)
