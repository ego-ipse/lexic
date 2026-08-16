"""Unit tests for src/lexic/generate.py"""

from __future__ import annotations

import random

import pytest

from lexic.compile import canonical_grammar, compile_from_path
from lexic.exceptions import UnsupportedConstructError
from lexic.generate import _Generator, _pick_count, generate
from lexic.grammars.gbnf import GBNF_FLAVOUR
from lexic.ir import (
    IrAlternation,
    IrCharClass,
    IrChr,
    IrItem,
    IrLiteral,
    IrNone,
    IrNot,
    IrQuantifier,
    IrRule,
    IrRuleRef,
    IrSequence,
)
from tests.paths import GROUND_TRUTH as GRAMMAR_DIR


def grammar_specs(grammar: str) -> dict:
    """The rule-name -> IrRule view :func:`~lexic.generate.generate` walks."""
    text = (GRAMMAR_DIR / f"{grammar}.gbnf").read_text()
    ast = canonical_grammar(text, GBNF_FLAVOUR)
    return {r.name: r for r in ast.rules}


def test_generate_returns_string():
    """generate() returns a string for a valid root rule."""
    specs = grammar_specs("arithmetic")
    result = generate("root", specs, rng=random.Random(42))
    assert isinstance(result, str)
    assert len(result) > 0


def test_generate_arithmetic_is_parseable():
    """Generated arithmetic strings parse and round-trip."""
    specs = grammar_specs("arithmetic")
    gpath = GRAMMAR_DIR / "arithmetic.gbnf"
    for seed in range(10):
        text = generate("root", specs, rng=random.Random(seed))
        inst = compile_from_path(gpath).parse(text)
        assert inst.to_text() == text, f"Round-trip failed for seed={seed}: {text!r}"


def test_generate_list_is_parseable():
    """Generated list strings parse and round-trip."""
    specs = grammar_specs("list")
    gpath = GRAMMAR_DIR / "list.gbnf"
    for seed in range(5):
        text = generate("root", specs, rng=random.Random(seed))
        inst = compile_from_path(gpath).parse(text)
        assert inst.to_text() == text


def test_generate_japanese_is_parseable():
    """Generated japanese strings parse and round-trip."""
    specs = grammar_specs("japanese")
    gpath = GRAMMAR_DIR / "japanese.gbnf"
    for seed in range(5):
        text = generate("root", specs, rng=random.Random(seed))
        inst = compile_from_path(gpath).parse(text)
        assert inst.to_text() == text


def test_generate_respects_max_depth():
    """generate() respects the max_depth parameter."""
    specs = grammar_specs("arithmetic")
    text = generate("root", specs, rng=random.Random(0), max_depth=3)
    assert isinstance(text, str)


def test_generate_deterministic_with_same_seed():
    """generate() produces the same output for the same seed."""
    specs = grammar_specs("arithmetic")
    t1 = generate("root", specs, rng=random.Random(7))
    t2 = generate("root", specs, rng=random.Random(7))
    assert t1 == t2


def test_generate_different_with_different_seeds():
    """generate() produces different outputs for different seeds."""
    specs = grammar_specs("arithmetic")
    results = {generate("root", specs, rng=random.Random(i)) for i in range(20)}
    assert len(results) > 1


def test_generate_sequence_rule():
    """generate() works for sequence rules."""
    specs = grammar_specs("arithmetic")
    result = generate("root", specs, rng=random.Random(42))
    assert isinstance(result, str)
    assert len(result) > 0


def test_generate_alternation_rule():
    """generate() works for alternation rules."""
    specs = grammar_specs("arithmetic")
    for seed in range(10):
        result = generate("term", specs, rng=random.Random(seed))
        assert isinstance(result, str)
        assert len(result) > 0


def test_generate_value_str_rule():
    """generate() works for value_str rules."""
    specs = grammar_specs("arithmetic")
    result = generate("ws", specs, rng=random.Random(0))
    assert isinstance(result, str)


def test_generate_max_depth_zero_picks_non_recursive_arm():
    """generate() with max_depth=0 picks a non-recursive arm."""
    specs = grammar_specs("arithmetic")
    for seed in range(10):
        result = generate("term", specs, rng=random.Random(seed), max_depth=0)
        assert isinstance(result, str)
        assert len(result) > 0


# ── _pick_count: the lo==0 roll (Phase-2 behaviour change) ──────────────


def quantifier_counts(q: IrQuantifier) -> set[int]:
    """The set of counts _pick_count rolls for ``q`` across many seeds."""
    return {_pick_count(q, random.Random(s)) for s in range(200)}


def test_pick_count_star_reaches_zero_and_expands():
    """A ``*`` quantifier (lo=0) rolls both 0 and expanded counts (capped lo+2).

    Regression guard for the defect where lo==0 short-circuited to 0 always,
    so a ``*``/``?``-rooted rule could only ever generate ``""``.
    """
    counts = quantifier_counts(IrQuantifier(0, IrNone))
    assert 0 in counts, "should still roll the empty expansion"
    assert any(c > 0 for c in counts), "should now also expand, not always empty"
    assert max(counts) <= 2, "unbounded hi caps the expanded count at lo + 2"


def test_pick_count_optional_rolls_zero_or_one():
    """A ``?`` quantifier (0,1) rolls exactly {0, 1}, both reachable."""
    assert quantifier_counts(IrQuantifier(0, 1)) == {0, 1}


def test_pick_count_bounded_star_caps_at_lo_plus_two():
    """A ``{0,9}`` quantifier caps the expanded count at lo+2, not hi."""
    assert max(quantifier_counts(IrQuantifier(0, 9))) <= 2


def test_pick_count_plus_never_zero():
    """The lo>0 path is unchanged: ``+`` (1,None) never yields 0."""
    counts = quantifier_counts(IrQuantifier(1, IrNone))
    assert 0 not in counts and min(counts) == 1


def test_pick_count_fixed_is_verbatim():
    """A fixed count (hi==lo) returns lo without rolling the rng."""
    assert _pick_count(IrQuantifier(3, 3), random.Random(0)) == 3


# ── open dispatch table: raising default ────────────────────────────────


def test_generate_unknown_atom_raises():
    """An atom type outside the dispatch table raises, never a silent ``""``.

    ``IrNot`` is dead on canonical input (the canonicaliser rewrites it away),
    so the raising default is the honest response to a stray one.
    """
    gen = _Generator(rng=random.Random(0), rules={}, max_depth=3)
    item = IrItem(IrNot(IrCharClass(IrChr('"'))))
    with pytest.raises(UnsupportedConstructError):
        gen.atom(item)


def test_generate_unknown_atom_error_names_the_type():
    """The raising default's message identifies the offending node type."""
    gen = _Generator(rng=random.Random(0), rules={}, max_depth=3)
    item = IrItem(IrNot(IrCharClass(IrChr('"'))))
    with pytest.raises(UnsupportedConstructError, match="IrNot"):
        gen.atom(item)


# ── refusals off the table: undefined rule, arm-less alternation ────────


def test_generate_unknown_rule_raises() -> None:
    """An undefined rule name refuses, never a silent ``""``.

    A generation door built on the old fallback drew an empty sample
    indistinguishably from a grammar that legitimately generates one.
    """
    specs = grammar_specs("arithmetic")
    with pytest.raises(UnsupportedConstructError):
        generate("no-such-rule", specs, rng=random.Random(0))


def test_generate_unknown_rule_error_names_the_rule_and_the_grammar() -> None:
    """The refusal carries the missing name and what the grammar does define."""
    specs = grammar_specs("arithmetic")
    with pytest.raises(UnsupportedConstructError, match="no-such-rule") as caught:
        generate("no-such-rule", specs, rng=random.Random(0))
    assert "root" in str(caught.value), str(caught.value)


def test_generate_dangling_ref_raises_from_inside_an_expansion() -> None:
    """A reference to an undefined rule refuses mid-expansion, not silently."""
    rules = {
        "root": IrRule("root", IrAlternation(IrSequence(IrItem(IrRuleRef("gone")))))
    }
    with pytest.raises(UnsupportedConstructError, match="gone"):
        generate("root", rules, rng=random.Random(0))


def test_generate_armless_alternation_raises_naming_the_rule() -> None:
    """A rule whose body has no arms refuses, with the rule named."""
    rules = {"empty": IrRule("empty", IrAlternation())}
    with pytest.raises(UnsupportedConstructError, match="empty"):
        generate("empty", rules, rng=random.Random(0))


def test_generate_armless_inline_group_raises() -> None:
    """An arm-less inline group refuses too — same defect, same words."""
    gen = _Generator(rng=random.Random(0), rules={}, max_depth=3)
    with pytest.raises(UnsupportedConstructError, match="inline group"):
        gen.atom(IrItem(IrAlternation()))


def test_generate_single_empty_arm_still_yields_empty_string() -> None:
    """What genuinely derives ``""`` still does: one EMPTY arm is not no arms."""
    rules = {"nothing": IrRule("nothing", IrAlternation(IrSequence()))}
    assert generate("nothing", rules, rng=random.Random(0)) == ""


# ── open dispatch table: every canonical atom kind, in isolation ────────


def test_generate_atom_dispatches_literal():
    """A literal atom expands to itself under the unit quantifier."""
    gen = _Generator(rng=random.Random(0), rules={}, max_depth=3)
    assert gen.atom(IrItem(IrLiteral("abc"))) == "abc"


def test_generate_atom_dispatches_charclass():
    """A char-class atom expands to one sampled covered character."""
    gen = _Generator(rng=random.Random(0), rules={}, max_depth=3)
    result = gen.atom(IrItem(IrCharClass(IrChr("x"))))
    assert result == "x"


def test_generate_atom_dispatches_ruleref():
    """A ruleref atom recurses into the named rule's expansion."""
    rules = {"greeting": IrRule("greeting", IrLiteral("hi"))}
    gen = _Generator(rng=random.Random(0), rules=rules, max_depth=3)
    assert gen.atom(IrItem(IrRuleRef("greeting"))) == "hi"


def test_generate_atom_dispatches_alternation_group():
    """An inline group atom expands its chosen arm."""
    group = IrAlternation(IrSequence(IrItem(IrLiteral("only"))))
    gen = _Generator(rng=random.Random(0), rules={}, max_depth=3)
    assert gen.atom(IrItem(group)) == "only"
