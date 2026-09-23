"""A stop-set loop answers as Earley does.

A stop-set leaves a run at the first character its continuation can start
with: the SHORTEST take. The split answer is the longest take that completes.
They agree where every carving builds one model, or where no text lets both
the exit and the take go on; everywhere else the rule islands and the gated
engine answers.
"""

from __future__ import annotations

import pytest

from lexic.compile import compile_text
from lexic.exceptions import LexicError
from lexic.parsing.pda.core.errors import PdaFail
from lexic.parsing.products import earley_model, pda_model
from tests.unit.lexic.parsing.parsing_helpers import prod

CASES = {
    "run before its own character": (
        's ::= x "a" y\nx ::= [ab]*\ny ::= [ab]*\n',
        ["baab", "aab", "ab"],
    ),
    "noise run holding its follower": (
        '# @non-semantic ws\ns ::= w ws "=" ws w\nw ::= [a-z]+\nws ::= [ =]*\n',
        ["a = b", "a == b", "a= =b"],
    ),
    "run before a reference that goes on both ways": (
        's ::= r ";"\nr ::= [ab]* "a" t\nt ::= [ab]* "!"\n',
        ["aab!;", "ab!;", "abab!;"],
    ),
}
"""The census's witnesses: before the fix the public parse returned
``x = b, y = ab`` for ``baab``, where Earley keeps ``x = ba, y = b``."""


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
def test_a_visible_stop_set_answers_as_earley(case: str, text: str) -> None:
    """The public parse is Earley's answer."""
    source, _texts = CASES[case]
    compiled = compile_text(source, cache_key=f"stop-set-{case}")
    product = prod(compiled)
    want = answer(
        lambda: earley_model(
            product.instance_grammar, text, compiled.product, product.tables
        )
    )
    assert answer(lambda: compiled.parse(text)) == want


GRANTED = {
    "invisible": ('s ::= w ";"\nw ::= [ab]* "a" [ab]* "!"\n', "abba!;"),
    "two deep": ('s ::= r ";"\nr ::= [ab]* "a" t\nt ::= "!"\n', "ba!;"),
}
"""Stop-sets that stay granted: ``w``'s model is its text with a fixed end (on
``abba!`` the first exit and the split carve it differently into one model),
and ``r``'s exit and take never both go on."""


@pytest.mark.parametrize("case", sorted(GRANTED))
def test_a_granted_stop_set_keeps_the_pda_route(case: str) -> None:
    """Where the first exit completes, the PDA answers, asked directly."""
    source, text = GRANTED[case]
    compiled = compile_text(source, cache_key=f"stop-set-granted-{case}")
    product = prod(compiled)
    got = pda_model(product.pda, text, compiled.product.executor)
    want = earley_model(
        product.instance_grammar, text, compiled.product, product.tables
    )
    assert got.dump() == want.dump()


def test_a_two_deep_stop_set_that_exits_too_soon_bails() -> None:
    """On ``aa!``, the first exit leaves ``"a" t`` to meet ``a!``: the PDA
    fails, and the public parse is still Earley's answer."""
    source, _text = GRANTED["two deep"]
    compiled = compile_text(source, cache_key="stop-set-bail-two-deep")
    product = prod(compiled)
    with pytest.raises(PdaFail):
        pda_model(product.pda, "aa!;", compiled.product.executor)
    want = earley_model(
        product.instance_grammar, "aa!;", compiled.product, product.tables
    )
    assert compiled.parse("aa!;").dump() == want.dump()
