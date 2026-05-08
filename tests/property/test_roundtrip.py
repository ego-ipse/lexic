"""Property-based round-trip tests: generate → parse → to_text == original.

Integers are used as RNG seeds rather than grammar-aware strategies; hypothesis
shrinking navigates numerically not structurally, but failing seeds are
reproducible and replayable.
"""

from __future__ import annotations

import random

import hypothesis.strategies as st
from hypothesis import HealthCheck, given, settings

from lexic.generate import generate
from lexic.parse import parse
from tests.paths import GROUND_TRUTH as _GRAMMAR_DIR


def _roundtrip(grammar: str, specs: dict, seed: int) -> None:
    rng = random.Random(seed)
    text = generate("root", specs, rng=rng, max_depth=4)
    if not text:
        # Generator returns "" when root is optional (min=0) — always the case
        # for grammars like c where root ::= (declaration)*. Skip rather than
        # parsing an empty string.
        return
    gpath = _GRAMMAR_DIR / f"{grammar}.gbnf"
    inst = parse(text, gpath)
    assert inst.to_text() == text, (
        f"Round-trip failed [{grammar}] seed={seed}:\n"
        f"  generated: {text!r}\n"
        f"  to_text:   {inst.to_text()!r}"
    )
    # Second parse verifies parse() is deterministic: same input → same model_dump()
    inst2 = parse(inst.to_text(), gpath)
    assert inst.model_dump() == inst2.model_dump()


# parse() regenerates Pydantic models from grammar on every call (~20ms each);
# suppress_health_check=[HealthCheck.too_slow] acknowledges this known cost.


@given(seed=st.integers(min_value=0, max_value=2**32 - 1))
@settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow])
def test_arithmetic_roundtrip(seed: int, all_grammar_specs: dict) -> None:
    _roundtrip("arithmetic", all_grammar_specs["arithmetic"], seed)


@given(seed=st.integers(min_value=0, max_value=2**32 - 1))
@settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow])
def test_list_roundtrip(seed: int, all_grammar_specs: dict) -> None:
    _roundtrip("list", all_grammar_specs["list"], seed)


@given(seed=st.integers(min_value=0, max_value=2**32 - 1))
@settings(max_examples=20, suppress_health_check=[HealthCheck.too_slow])
def test_japanese_roundtrip(seed: int, all_grammar_specs: dict) -> None:
    _roundtrip("japanese", all_grammar_specs["japanese"], seed)


@given(seed=st.integers(min_value=0, max_value=2**32 - 1))
@settings(max_examples=20, suppress_health_check=[HealthCheck.too_slow])
def test_chess_roundtrip(seed: int, all_grammar_specs: dict) -> None:
    _roundtrip("chess", all_grammar_specs["chess"], seed)


@given(seed=st.integers(min_value=0, max_value=2**32 - 1))
@settings(max_examples=20, suppress_health_check=[HealthCheck.too_slow])
def test_json_ws_roundtrip(seed: int, all_grammar_specs: dict) -> None:
    _roundtrip("json_ws", all_grammar_specs["json_ws"], seed)


@given(seed=st.integers(min_value=0, max_value=2**32 - 1))
@settings(max_examples=20, suppress_health_check=[HealthCheck.too_slow])
def test_json_arr_roundtrip(seed: int, all_grammar_specs: dict) -> None:
    _roundtrip("json_arr", all_grammar_specs["json_arr"], seed)
