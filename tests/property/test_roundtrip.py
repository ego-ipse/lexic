"""Property-based round-trip tests: generate → parse → to_text == original."""

from __future__ import annotations
import random
from pathlib import Path

from hypothesis import HealthCheck, given, settings
import hypothesis.strategies as st

from lexic.codegen.ir_builder import IRBuilder
from lexic.codegen.parser import parse_gbnf
from lexic.generate import generate
from lexic.parse import parse

_GRAMMAR_DIR = Path(__file__).parent.parent.parent / "resources" / "ground_truth"
_ALL_SPECS: dict[str, dict] = {}


def _get_specs(grammar: str) -> dict:
    if grammar not in _ALL_SPECS:
        text = (_GRAMMAR_DIR / f"{grammar}.gbnf").read_text()
        _ALL_SPECS[grammar] = {
            s.rule_name: s for s in IRBuilder(parse_gbnf(text)).build()
        }
    return _ALL_SPECS[grammar]


def _roundtrip(grammar: str, seed: int) -> None:
    specs = _get_specs(grammar)
    rng = random.Random(seed)
    text = generate("root", specs, rng=rng, max_depth=4)
    if not text:
        return  # grammar allows empty (e.g. c with 0 declarations)
    gpath = _GRAMMAR_DIR / f"{grammar}.gbnf"
    inst = parse(text, gpath)
    assert inst.to_text() == text, (
        f"Round-trip failed [{grammar}] seed={seed}:\n"
        f"  generated: {text!r}\n"
        f"  to_text:   {inst.to_text()!r}"
    )
    inst2 = parse(inst.to_text(), gpath)
    assert inst.model_dump() == inst2.model_dump()


@given(st.integers(min_value=0, max_value=2**32 - 1))
@settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow])
def test_arithmetic_roundtrip(seed: int) -> None:
    _roundtrip("arithmetic", seed)


@given(st.integers(min_value=0, max_value=2**32 - 1))
@settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow])
def test_list_roundtrip(seed: int) -> None:
    _roundtrip("list", seed)


@given(st.integers(min_value=0, max_value=2**32 - 1))
@settings(max_examples=20, suppress_health_check=[HealthCheck.too_slow])
def test_japanese_roundtrip(seed: int) -> None:
    _roundtrip("japanese", seed)


@given(st.integers(min_value=0, max_value=2**32 - 1))
@settings(max_examples=20, suppress_health_check=[HealthCheck.too_slow])
def test_chess_roundtrip(seed: int) -> None:
    _roundtrip("chess", seed)


@given(st.integers(min_value=0, max_value=2**32 - 1))
@settings(max_examples=20, suppress_health_check=[HealthCheck.too_slow])
def test_json_ws_roundtrip(seed: int) -> None:
    _roundtrip("json_ws", seed)


@given(st.integers(min_value=0, max_value=2**32 - 1))
@settings(max_examples=20, suppress_health_check=[HealthCheck.too_slow])
def test_json_arr_roundtrip(seed: int) -> None:
    _roundtrip("json_arr", seed)
