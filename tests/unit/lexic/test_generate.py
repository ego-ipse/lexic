"""Unit tests for src/lexic/generate.py"""

from __future__ import annotations

import random

from lexic.compile import compile_grammar
from lexic.generate import generate
from lexic.grammars.gbnf import GBNF_FLAVOUR
from lexic.parse import parse
from tests.paths import GROUND_TRUTH as GRAMMAR_DIR


def _specs(grammar: str) -> dict:
    text = (GRAMMAR_DIR / f"{grammar}.gbnf").read_text()
    _, specs_list = compile_grammar(text, GBNF_FLAVOUR)
    return {s.rule_name: s for s in specs_list}


def test_generate_returns_string():
    """generate() returns a string for a valid root rule."""
    specs = _specs("arithmetic")
    result = generate("root", specs, rng=random.Random(42))
    assert isinstance(result, str)
    assert len(result) > 0


def test_generate_arithmetic_is_parseable():
    """Generated arithmetic strings parse and round-trip."""
    specs = _specs("arithmetic")
    gpath = GRAMMAR_DIR / "arithmetic.gbnf"
    for seed in range(10):
        text = generate("root", specs, rng=random.Random(seed))
        inst = parse(text, gpath)
        assert inst.to_text() == text, f"Round-trip failed for seed={seed}: {text!r}"


def test_generate_list_is_parseable():
    """Generated list strings parse and round-trip."""
    specs = _specs("list")
    gpath = GRAMMAR_DIR / "list.gbnf"
    for seed in range(5):
        text = generate("root", specs, rng=random.Random(seed))
        inst = parse(text, gpath)
        assert inst.to_text() == text


def test_generate_japanese_is_parseable():
    """Generated japanese strings parse and round-trip."""
    specs = _specs("japanese")
    gpath = GRAMMAR_DIR / "japanese.gbnf"
    for seed in range(5):
        text = generate("root", specs, rng=random.Random(seed))
        inst = parse(text, gpath)
        assert inst.to_text() == text


def test_generate_respects_max_depth():
    """generate() respects the max_depth parameter."""
    specs = _specs("arithmetic")
    text = generate("root", specs, rng=random.Random(0), max_depth=3)
    assert isinstance(text, str)


def test_generate_deterministic_with_same_seed():
    """generate() produces the same output for the same seed."""
    specs = _specs("arithmetic")
    t1 = generate("root", specs, rng=random.Random(7))
    t2 = generate("root", specs, rng=random.Random(7))
    assert t1 == t2


def test_generate_different_with_different_seeds():
    """generate() produces different outputs for different seeds."""
    specs = _specs("arithmetic")
    results = {generate("root", specs, rng=random.Random(i)) for i in range(20)}
    assert len(results) > 1


def test_generate_sequence_rule():
    """generate() works for sequence rules."""
    specs = _specs("arithmetic")
    result = generate("root", specs, rng=random.Random(42))
    assert isinstance(result, str)
    assert len(result) > 0


def test_generate_alternation_rule():
    """generate() works for alternation rules."""
    specs = _specs("arithmetic")
    for seed in range(10):
        result = generate("term", specs, rng=random.Random(seed))
        assert isinstance(result, str)
        assert len(result) > 0


def test_generate_value_str_rule():
    """generate() works for value_str rules."""
    specs = _specs("arithmetic")
    result = generate("ws", specs, rng=random.Random(0))
    assert isinstance(result, str)


def test_generate_max_depth_zero_picks_non_recursive_arm():
    """generate() with max_depth=0 picks a non-recursive arm."""
    specs = _specs("arithmetic")
    for seed in range(10):
        result = generate("term", specs, rng=random.Random(seed), max_depth=0)
        assert isinstance(result, str)
        assert len(result) > 0
