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
from lexic.parsing.products import earley_model, pda_model
from tests.paths import GROUND_TRUTH
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


def test_a_two_deep_stop_set_reads_its_exit_s_second_character() -> None:
    """On ``aa!``, the first ``a`` is an exit, and the character after it says
    the loop goes on: the window the exit was proved on takes it, and the
    second ``a`` — before ``!`` — stops. A stop set alone left ``"a" t`` to
    meet ``a!`` and failed."""
    source, _text = GRANTED["two deep"]
    compiled = compile_text(source, cache_key="stop-set-second-two-deep")
    product = prod(compiled)
    got = pda_model(product.pda, "aa!;", compiled.product.executor)
    want = earley_model(
        product.instance_grammar, "aa!;", compiled.product, product.tables
    )
    assert got.dump() == want.dump()


_TAGGED = 'root ::= "!" tag? " " content\ntag ::= " %" [a-z]+\n'
"""An optional tag before a body: a live set weighs taking it against not,
so the body is first parsed inside a reading, where a death is a prune."""

IN_A_READING = {
    "two deep, a reference after the run": (
        _TAGGED
        + 'content ::= w | prose\nw ::= [a-z-]* close\nclose ::= "->"\n'
        + 'prose ::= "%" [a-z %>-]*\n',
        ["! %a a-b->", "! a-b->", "! %a a->"],
    ),
    "two deep, a word before its tail": (
        _TAGGED
        + 'content ::= word | prose\nword ::= [a-z]* tail\ntail ::= "a;"\n'
        + 'prose ::= "%" [a-z %;]*\n',
        ["! %a xaba;", "! xaba;", "! %a ba;"],
    ),
    "noise run before a required noise token": (
        "# @non-semantic ws sep end\n"
        + _TAGGED.replace("content\n", "content end?\n")
        + "content ::= list | prose\nlist ::= item (sep item)*\n"
        + 'item ::= [a-z]+ ws\nws ::= [ \\n]*\nsep ::= "\\n" "-"\n'
        + 'prose ::= "%" [a-z %\\n-]*\nend ::= " " "!"\n',
        ["! %a a\n-b", "! %a a\n-b !", "! %a a"],
    ),
}
"""Policy grants a reading crossed: the two-deep stop set that stopped at its
first exit, and the noise run that ate the token after it. The tag's live
set read the take's death as certain and kept the reading without the tag."""


@pytest.mark.parametrize(
    ("case", "text"),
    [(case, text) for case, (_s, texts) in IN_A_READING.items() for text in texts],
)
def test_a_policy_grant_inside_a_reading_answers_as_earley(
    case: str, text: str
) -> None:
    """The predictive engine builds Earley's model, asked directly."""
    source, _texts = IN_A_READING[case]
    compiled = compile_text(source, cache_key=f"stop-set-reading-{case}")
    product = prod(compiled)
    want = earley_model(
        product.instance_grammar, text, compiled.product, product.tables
    )
    got = pda_model(product.pda, text, compiled.product.executor)
    assert got.dump() == want.dump()


@pytest.mark.parametrize("stem", ["arithmetic.gbnf", "arithmetic.ebnf"])
@pytest.mark.parametrize("text", ["x=1\n\n", "x=1 \n\n", "x=1\n\ny=2\n"])
def test_a_blank_line_after_a_noise_run_stays_on_the_predictive_engine(
    stem: str, text: str
) -> None:
    """arithmetic's ``ws`` ends a term the line's own ``"\\n"`` follows: a
    blank line is ``ws`` taking a newline the next one does not."""
    flavour = stem.rsplit(".", 1)[1]
    compiled = compile_text(
        (GROUND_TRUTH / stem).read_text(), cache_key=f"stop-set-{stem}", flavour=flavour
    )
    product = prod(compiled)
    want = earley_model(
        product.instance_grammar, text, compiled.product, product.tables
    )
    got = pda_model(product.pda, text, compiled.product.executor)
    assert got.dump() == want.dump()
