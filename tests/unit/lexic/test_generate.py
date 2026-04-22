"""Unit tests for src/lexic/generate.py"""

from __future__ import annotations
import random
from pathlib import Path
from lexic.codegen.parser import parse_gbnf
from lexic.codegen.ir_builder import IRBuilder
from lexic.generate import generate

GRAMMAR_DIR = Path(__file__).parent.parent.parent.parent / "resources" / "ground_truth"


def _specs(grammar: str) -> dict:
    text = (GRAMMAR_DIR / f"{grammar}.gbnf").read_text()
    return {s.rule_name: s for s in IRBuilder(parse_gbnf(text)).build()}


def test_generate_returns_string():
    specs = _specs("arithmetic")
    result = generate("root", specs, rng=random.Random(42))
    assert isinstance(result, str)
    assert len(result) > 0


def test_generate_arithmetic_is_parseable():
    from lexic.parse import parse

    specs = _specs("arithmetic")
    gpath = GRAMMAR_DIR / "arithmetic.gbnf"
    for seed in range(10):
        text = generate("root", specs, rng=random.Random(seed))
        inst = parse(text, gpath)
        assert inst.to_text() == text, f"Round-trip failed for seed={seed}: {text!r}"


def test_generate_list_is_parseable():
    from lexic.parse import parse

    specs = _specs("list")
    gpath = GRAMMAR_DIR / "list.gbnf"
    for seed in range(5):
        text = generate("root", specs, rng=random.Random(seed))
        inst = parse(text, gpath)
        assert inst.to_text() == text


def test_generate_japanese_is_parseable():
    from lexic.parse import parse

    specs = _specs("japanese")
    gpath = GRAMMAR_DIR / "japanese.gbnf"
    for seed in range(5):
        text = generate("root", specs, rng=random.Random(seed))
        inst = parse(text, gpath)
        assert inst.to_text() == text


def test_generate_respects_max_depth():
    # arithmetic has recursive rules — max_depth must prevent infinite recursion
    specs = _specs("arithmetic")
    text = generate("root", specs, rng=random.Random(0), max_depth=3)
    assert isinstance(text, str)


def test_generate_deterministic_with_same_seed():
    specs = _specs("arithmetic")
    t1 = generate("root", specs, rng=random.Random(7))
    t2 = generate("root", specs, rng=random.Random(7))
    assert t1 == t2


def test_generate_different_with_different_seeds():
    specs = _specs("arithmetic")
    results = {generate("root", specs, rng=random.Random(i)) for i in range(20)}
    assert len(results) > 1


def test_generate_sequence_rule():
    # arithmetic: root ::= expr "=" ws term "\n" — kind=sequence
    specs = _specs("arithmetic")
    result = generate("root", specs, rng=random.Random(42))
    assert isinstance(result, str)
    assert len(result) > 0


def test_generate_alternation_rule():
    # arithmetic: term ::= ident | num | "(" ws expr ")" ws — kind=alternation
    specs = _specs("arithmetic")
    for seed in range(10):
        result = generate("term", specs, rng=random.Random(seed))
        assert isinstance(result, str)
        assert len(result) > 0


def test_generate_value_str_rule():
    # arithmetic: ws ::= [ \t\n]* — kind=value_str
    specs = _specs("arithmetic")
    result = generate("ws", specs, rng=random.Random(0))
    assert isinstance(result, str)


def test_generate_max_depth_zero_picks_non_recursive_arm():
    # With max_depth=0, generate must still return a valid non-empty string
    # by picking a non-recursive arm (ident or num, not the "(" expr ")" arm)
    specs = _specs("arithmetic")
    for seed in range(10):
        result = generate("term", specs, rng=random.Random(seed), max_depth=0)
        assert isinstance(result, str)
        assert len(result) > 0
