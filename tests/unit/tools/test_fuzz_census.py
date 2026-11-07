"""Tests for tools.fuzz_census — a census classifies, and two censuses compare.

The classification is written out by hand from the rule: a decline is never
WRONG, and a predictive model Earley does not build is WRONG even where Earley
refuses the text. One tiny grammar runs end to end through both engines.
"""

from __future__ import annotations

import random

import pytest

from lexic.compile import compile_text
from lexic.parsing.products import model_product
from tools.fuzz_census import (
    DECLINED,
    ERROR,
    REFUSED,
    VARIANTS,
    census,
    classify,
    grammar,
    kind,
    moves,
    new_wrong,
    words,
)


@pytest.mark.parametrize(
    ("predictive", "gated", "expected"),
    [
        ("Root('a')", "Root('a')", "EQUAL"),
        (REFUSED, REFUSED, "BOTH_REFUSE"),
        (DECLINED, "Root('a')", "DECLINED"),
        (DECLINED, REFUSED, "DECLINED_REFUSED"),
        ("Root('a')", "Root('b')", "WRONG"),
        ("Root('a')", REFUSED, "WRONG"),
        (REFUSED, "Root('a')", "WRONG"),
        (
            f"{ERROR}FieldValidationError",
            "Root('a')",
            "ERROR:predictive:FieldValidationError",
        ),
        (DECLINED, f"{ERROR}TargetRefusalError", "ERROR:gated:TargetRefusalError"),
    ],
)
def test_a_pair_of_answers_is_classified(
    predictive: str, gated: str, expected: str
) -> None:
    """Each pair of rendered answers has exactly one kind."""
    assert kind(predictive, gated) == expected


def test_words_are_every_short_word_shortest_first() -> None:
    """``3 + 9`` words of length one and two, in order."""
    assert words(2) == ["a", "b", ";"] + [x + y for x in "ab;" for y in "ab;"]


@pytest.mark.parametrize("name", sorted(VARIANTS))
def test_a_generated_grammar_names_only_its_allowed_rules(name: str) -> None:
    """Every rule line is ``rule ::= …``, in definition order, and compiles."""
    variant = VARIANTS[name]
    source = grammar(variant, random.Random(1))
    assert [line.split(" ::= ")[0] for line in source.splitlines()] == list(
        variant.refs
    )
    compile_text(source, cache_key=f"fuzz-census-test-{name}-{source}")


def test_one_tiny_grammar_runs_through_both_engines() -> None:
    """``[ab]+`` answers ``ab`` alike; on ``;`` the predictive engine's miss is a
    decline, beside Earley's refusal."""
    compiled = compile_text("root ::= [ab]+\n", cache_key="fuzz-census-tiny")
    product = model_product(compiled.codegen_grammar, compiled.product)
    assert classify(compiled, product, "ab").kind == "EQUAL"
    assert classify(compiled, product, ";").kind == "DECLINED_REFUSED"


def test_a_census_keys_every_word_of_every_grammar() -> None:
    """Seed 1's first two variant-B grammars both compile, so every word up to
    two of each is one entry: ``2 * 12``."""
    found = census(["B"], [1], 2, 2)
    expected = {f"B-fuzz1:{index}|{word}" for index in (0, 1) for word in words(2)}
    assert set(found) == expected
    assert len(found) == 24


def test_a_compare_reports_moves_and_only_new_wrong() -> None:
    """A WRONG kept as it was is not new; one that appears is, and so is an
    error that appears."""
    base = {
        "k1": ["WRONG", "g", "p"],
        "k2": ["EQUAL", "g", "g"],
        "k3": ["DECLINED", "g", ""],
        "k4": ["EQUAL", "g", "g"],
    }
    head = {
        "k1": ["WRONG", "g", "p"],
        "k2": ["WRONG", "g", "q"],
        "k3": ["EQUAL", "g", "g"],
        "k4": ["ERROR:predictive:FieldValidationError", "g", "e"],
    }
    assert moves(base, head) == {
        ("EQUAL", "WRONG"): 1,
        ("DECLINED", "EQUAL"): 1,
        ("EQUAL", "ERROR:predictive:FieldValidationError"): 1,
    }
    assert new_wrong(base, head) == ["k2", "k4"]
