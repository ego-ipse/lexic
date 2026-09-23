"""Tests for lexic.generate.sizing — size-targeted generation, through ``generate(size=)``.

Every target is checked against the measured length of what comes back, every
document against a grammar compiled from the same source, and each steering
mechanism has a witness that fails when the mechanism is removed.
"""

from __future__ import annotations

import random

import pytest

from lexic.compile import canonical_grammar, compile_text
from lexic.exceptions import UnsupportedConstructError
from lexic.generate import generate
from lexic.grammars.gbnf import GBNF_FLAVOUR
from lexic.ir import (
    IrAlternation,
    IrItem,
    IrLiteral,
    IrRule,
    IrRuleRef,
    IrSequence,
)
from tests.paths import GROUND_TRUTH as GRAMMAR_DIR


def _sized(name: str, size: int, seed: int = 0) -> tuple[str, str]:
    """A ``size``-targeted document of a ground-truth grammar, with its source."""
    source = (GRAMMAR_DIR / name).read_text()
    ast = canonical_grammar(source, GBNF_FLAVOUR)
    rules = {rule.name: rule for rule in ast.rules}
    rng = random.Random(seed)
    return source, generate(str(ast.start), rules, rng=rng, max_depth=48, size=size)


@pytest.mark.parametrize(
    "name", ["json.gbnf", "arithmetic.gbnf", "list.gbnf", "vyx.gbnf"]
)
@pytest.mark.parametrize("seed", [0, 1, 2])
def test_a_size_target_is_met_within_one_percent(name, seed):
    """20,000 asked, 1% either way. vyx is the witness for re-sharing what a
    capped item's room refuses: its packet ends in an optional body with a
    finite room, and nothing after it could take the excess."""
    _source, text = _sized(name, 20_000, seed)
    assert abs(len(text) - 20_000) <= 200, len(text)


REACHED_THROUGH_REFERENCES = r"""root ::= expr "\n"
expr ::= expr (" + " | " - ") term | term
term ::= call | name
call ::= name "(" text ")"
name ::= [a-z] [0-9_a-z]*
text ::= [,.-9_a-z]*
"""
"""No repetition at the top: the budget must reach a character run THROUGH
references. It is the witness for a spent depth having NO room — a reference
that the fill would walk freely must not be priced as if it could be steered,
or the budget is sent where nothing spends it."""


@pytest.mark.parametrize("seed", [0, 1])
def test_a_budget_reaches_a_run_through_references(seed):
    """The whole budget arrives, though no repetition sits at the top."""
    ast = canonical_grammar(REACHED_THROUGH_REFERENCES, GBNF_FLAVOUR)
    rules = {rule.name: rule for rule in ast.rules}
    rng = random.Random(seed)
    text = generate(str(ast.start), rules, rng=rng, max_depth=48, size=20_000)
    assert abs(len(text) - 20_000) <= 200, len(text)
    assert compile_text(REACHED_THROUGH_REFERENCES).parse(text, cores=1) is not None


@pytest.mark.parametrize("name", ["json.gbnf", "arithmetic.gbnf"])
def test_a_sized_document_is_a_document_of_the_grammar(name):
    """Steering picks arms and counts; it never leaves the language."""
    source, text = _sized(name, 5_000)
    assert compile_text(source).parse(text, cores=1) is not None


def test_a_sized_document_nests_where_the_grammar_can():
    """json's budget becomes structure: depth well past a flat run's zero or one,
    and brackets that are a large share of the text rather than a stray few."""
    _source, text = _sized("json.gbnf", 20_000)
    depth = deepest = 0
    for char in text:
        depth += (char in "[{") - (char in "]}")
        deepest = max(deepest, depth)
    assert deepest >= 5, deepest
    assert sum(text.count(c) for c in "[]{}") > 200


@pytest.mark.parametrize("seed", [0, 3])
def test_a_budget_past_the_depth_repeats_structure_not_a_terminal_run(seed):
    """At the default depth json cannot nest far enough for 20,000 characters.
    The budget must become more members and elements, walked freely, not one
    unbounded whitespace run: a repeating reference's room counts its free
    units once its steered room is spent."""
    source = (GRAMMAR_DIR / "json.gbnf").read_text()
    ast = canonical_grammar(source, GBNF_FLAVOUR)
    rules = {rule.name: rule for rule in ast.rules}
    text = generate(str(ast.start), rules, rng=random.Random(seed), size=20_000)
    assert abs(len(text) - 20_000) <= 200, len(text)
    assert sum(char in " \t\r\n" for char in text) < len(text) // 2
    assert "      " not in text


def test_size_targeting_is_deterministic_per_seed():
    """One seed, one document."""
    assert _sized("json.gbnf", 5_000, 7) == _sized("json.gbnf", 5_000, 7)


def test_a_grammar_that_only_grows_one_level_at_a_time_comes_out_short():
    """``root ::= "a" root | "a"`` grows one character per reference, so the depth
    IS the size: it cannot reach a target larger than its depth, and says so by
    length rather than recursing past the interpreter's limit."""
    rules = {
        "root": IrRule(
            "root",
            IrAlternation(
                IrSequence(IrItem(IrLiteral("a")), IrItem(IrRuleRef("root"))),
                IrSequence(IrItem(IrLiteral("a"))),
            ),
        )
    }
    text = generate("root", rules, rng=random.Random(0), max_depth=20, size=10_000)
    assert set(text) == {"a"}
    # No arm has room for the budget, so the ROOMIEST is taken at every level:
    # the depth is spent in full rather than on a random short arm.
    assert 20 <= len(text) <= 22, len(text)


THROUGH_FOUR_GROUPS = (
    'root ::= item\nitem ::= "p" ("q" ("r" ("s" ("t" item)?)?)?)? | "a"\n'
)
"""Linear recursion through four nested optional groups: every group between a
rule and its own reference adds frames to a steered level, so frames per level
are the GRAMMAR's, and no constant bounds them."""


@pytest.mark.parametrize(
    ("source", "depth"),
    [(THROUGH_FOUR_GROUPS, 48), ('root ::= "a" root | "a"\n', 1_000)],
)
def test_a_target_deeper_than_the_stack_is_refused_with_words(source, depth):
    """Not a RecursionError, and not a silently clamped depth: a refusal that
    says what the target needs and what to lower."""
    ast = canonical_grammar(source, GBNF_FLAVOUR)
    rules = {rule.name: rule for rule in ast.rules}
    with pytest.raises(
        UnsupportedConstructError, match="deeper nesting than the stack"
    ):
        generate("root", rules, rng=random.Random(1), max_depth=depth, size=5_000)


NESTED_LISTS = 'value ::= "[" (value ("," value)*)? "]" | "x"\n'
"""A self-reference inside an OPTIONAL group, on an arm as cheap as the
terminal one — sized eagerly, it recursed to negative depths before a character
was generated. The sizer must be as lazy as the walk it predicts."""


@pytest.mark.parametrize("depth", [2, 5, 48])
def test_an_optional_self_reference_is_sized_and_reached(depth):
    """Any depth, the target met: nothing recurses past a spent depth."""
    ast = canonical_grammar(NESTED_LISTS, GBNF_FLAVOUR)
    rules = {rule.name: rule for rule in ast.rules}
    text = generate("value", rules, rng=random.Random(0), max_depth=depth, size=10_000)
    assert abs(len(text) - 10_000) <= 100, len(text)
    assert compile_text(NESTED_LISTS).parse(text, cores=1) is not None


OPTIONAL_SELF = 'value ::= "[" value? "]" | "x"\n'
"""The same laziness for a REFERENCE: a bare optional self-reference, no group
around it. It grows only by nesting, so it comes out short — but it comes out."""


def test_an_optional_self_reference_without_a_group_is_sized():
    """Short by length at a shallow depth, never a RecursionError."""
    ast = canonical_grammar(OPTIONAL_SELF, GBNF_FLAVOUR)
    rules = {rule.name: rule for rule in ast.rules}
    text = generate("value", rules, rng=random.Random(0), max_depth=2, size=10_000)
    assert compile_text(OPTIONAL_SELF).parse(text, cores=1) is not None


BOUNDED = 'root ::= "ab" "c"? | "de" [x-z]?\n'
"""Room 3 on either arm against a natural size of 2.3: no arm can grow past
twice what the free walk already yields, so there is nothing to steer."""


@pytest.mark.parametrize("seed", [0, 1, 2, 3])
def test_a_grammar_without_room_is_walked_freely_whatever_the_target(seed):
    """With no arm able to grow, a huge target is NOT steered: the document is
    the free walk's, draw for draw, at the natural depth."""
    ast = canonical_grammar(BOUNDED, GBNF_FLAVOUR)
    rules = {rule.name: rule for rule in ast.rules}
    start = str(ast.start)
    sized = generate(start, rules, rng=random.Random(seed), max_depth=48, size=10**6)
    free = generate(start, rules, rng=random.Random(seed), max_depth=3)
    assert sized == free
