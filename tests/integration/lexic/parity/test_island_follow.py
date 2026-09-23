"""An island inside a repetition answers as Earley does.

With ``doc ::= sec+`` and ``sec`` an island, a shorter ``sec`` that another
``sec`` would continue is a second carving of ``doc``. The island's follow
set must hold that next occurrence, or longest-match settles the carving
unchecked and the public parse builds a model Earley does not.
"""

from __future__ import annotations

import random

import pytest

from lexic.compile import compile_from_path, compile_text
from lexic.exceptions import LexicError
from lexic.generate import generate
from lexic.parsing.products import _model_product, earley_model, pda_model
from tests.paths import GROUND_TRUTH
from tools.benchmark.cases.grammars import BENCHES

_SEC = 'sec ::= sec "~" | sec "^" | stmt+ end\n'
"""Left recursive with two recursive arms: an island by grammar, so no licence
or fold stands between the text and the island's own answer."""

CASES = {
    "closing-end": (
        "doc ::= sec+\n" + _SEC + 'stmt ::= [a-z]* ";"\nend ::= ";" | "!"\n',
        [";!;;;!", ";!;;;;"],
    ),
    "mid-y": (
        "doc ::= sec+\n" + _SEC + 'stmt ::= "ab" | ";"\nend ::= "a" | ";"\n',
        [";a;;;a", ";a;;;;"],
    ),
}


def answer(run) -> str:
    """A parse's model dump, or the refusal it raised."""
    try:
        return str(run().dump())
    except LexicError as refused:  # the refusal IS the answer being compared
        return f"refused: {type(refused).__name__}"


@pytest.mark.parametrize(
    ("case", "text"),
    [(case, text) for case, (_s, texts) in CASES.items() for text in texts],
)
def test_an_island_inside_a_repetition_answers_as_earley(case: str, text: str) -> None:
    """The shortest texts the island got wrong: the public parse is Earley's."""
    source, _texts = CASES[case]
    compiled = compile_text(source, cache_key=f"island-follow-{case}")
    product = _model_product(compiled.codegen_grammar, compiled.product)
    want = answer(
        lambda: earley_model(
            product.instance_grammar, text, compiled.product, product.tables
        )
    )
    assert answer(lambda: compiled.parse(text)) == want


def test_the_bench_with_a_repeating_island_keeps_its_answers() -> None:
    """backtrack's ``stmt`` island is referenced as a repetition: its corpus
    and accepted inputs still parse to Earley's models."""
    bench = next(one for one in BENCHES if one.name == "backtrack")
    compiled = bench.compiled
    product = _model_product(compiled.codegen_grammar, compiled.product)
    for text in (bench.corpus, *bench.accepts):
        want = earley_model(
            product.instance_grammar, text, compiled.product, product.tables
        )
        assert compiled.parse(text).dump() == want.dump()


def test_the_ground_truth_grammar_with_repeating_islands_keeps_its_answers() -> None:
    """c.gbnf references its ``statement`` island as a repetition at four
    sites: generated programs still parse to Earley's models."""
    compiled = compile_from_path(GROUND_TRUTH / "c.gbnf")
    product = _model_product(compiled.codegen_grammar, compiled.product)
    rules = {str(rule.name): rule for rule in compiled.codegen_grammar.rules}
    start = str(compiled.codegen_grammar.start)
    checked = 0
    for seed in range(8):
        text = generate(start, rules, rng=random.Random(seed), size=200)
        want = earley_model(
            product.instance_grammar, text, compiled.product, product.tables
        )
        assert compiled.parse(text).dump() == want.dump()
        checked += 1
    assert checked == 8


# ── two characters deep: a space that no continuation follows the same way ──

_SPACED = 'root ::= x " ;"\nx ::= x " a" | x " b" | "c"\n'
"""After a shorter ``x`` comes a space, which the caller's `` ;`` also starts
with, so one character says the shorter end could compose. The second
character (``a`` against ``;``) says it cannot."""


@pytest.mark.parametrize("text", ["c a ;", "c a b ;", "c ;"])
def test_a_second_character_settles_what_one_could_not(text: str) -> None:
    """The PDA, asked directly, answers with Earley's model."""
    compiled = compile_text(_SPACED, cache_key="island-window-spaced")
    product = _model_product(compiled.codegen_grammar, compiled.product)
    got = pda_model(product.pda, text, compiled.product.executor)
    want = earley_model(
        product.instance_grammar, text, compiled.product, product.tables
    )
    assert got.dump() == want.dump()


# ── per site: another site's continuation does not follow this one ──────────

_TWO_PLACES = (
    'doc ::= x? "a" rest x? "#a"\nrest ::= [b-z]*\nx ::= x "#" | x "~" | "~"\n'
)
"""A shorter ``x`` at the start is followed by ``#a``, which only ever follows
``x`` at the later site. The two sites never stand at one position, so that
continuation is not this one's, and the longer ``x`` is the answer."""


@pytest.mark.parametrize("text", ["~#abc#a", "~~#a#a", "a#a"])
def test_a_site_ignores_what_follows_a_site_it_can_never_be(text: str) -> None:
    """The PDA, asked directly, answers with Earley's model."""
    compiled = compile_text(_TWO_PLACES, cache_key="island-two-places")
    product = _model_product(compiled.codegen_grammar, compiled.product)
    got = pda_model(product.pda, text, compiled.product.executor)
    want = earley_model(
        product.instance_grammar, text, compiled.product, product.tables
    )
    assert got.dump() == want.dump()
