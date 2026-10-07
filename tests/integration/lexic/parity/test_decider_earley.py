"""Whole-document Earley keeps the decider's carving, and the PDA agrees.

The decider is leftmost-longest over authored slots, top-down: a node's
boundaries are chosen first, the first slot longest, and only a choice between
ARMS at the boundaries it keeps is a question of meaning. These are the census
witnesses, each once decided by chart order or refused over a carving the
decider rejects.
"""

from __future__ import annotations

import pytest

from lexic.exceptions import UnsupportedConstructError

from lexic.compile import compile_text
from lexic.parsing.products import earley_model, pda_model
from tests.unit.lexic.parsing.parsing_helpers import prod

WITNESSES = {
    "nested repetition": (
        'doc ::= sec+\nsec ::= stmt+ end\nstmt ::= "!" ";" | "a;"\nend ::= ";"?\n',
        "a;a;a;",
        "{'sec': [{'stmt': [{'value': 'a;'}, {'value': 'a;'}, {'value': 'a;'}], "
        "'end': {'value': ''}}]}",
    ),
    "arm only at a rejected boundary": (
        'doc ::= part+ tail\npart ::= [a;]\ntail ::= [a]* | "aa" [a]*\n',
        "aaa",
        "{'part': [{'value': 'a'}, {'value': 'a'}, {'value': 'a'}], "
        "'tail': {'value': ''}}",
    ),
    "one run, not two": (
        "root ::= item+\nitem ::= [a-z]+\n",
        "abc",
        "{'item': [{'value': 'abc'}]}",
    ),
}
"""``(grammar, text, the decider's model)``. Chart order gave two secs over
``a;a;a;``; ``aaa`` refused because ``tail``'s other arm exists only where
``part+`` ends early; ``abc`` split into two items."""


@pytest.mark.parametrize("case", sorted(WITNESSES))
def test_earley_keeps_the_deciders_carving_and_the_pda_agrees(case: str) -> None:
    """Earley's model is the decider's, and so is the PDA's."""
    source, text, want = WITNESSES[case]
    compiled = compile_text(source, cache_key=f"decider-{case}")
    product = prod(compiled)
    earley = earley_model(
        product.instance_grammar, text, compiled.product, product.tables
    )
    assert str(earley.dump()) == want
    assert pda_model(product.pda, text, compiled.executor) == earley


DEEP_ARM = (
    'doc ::= sec+\nsec ::= stmt+ end\nstmt ::= "a;" | a2\na2 ::= "a;"\nend ::= ";"?\n'
)
"""The nested repetition with an arm choice two levels below it: every
``stmt`` is ``"a;"`` or an ``a2`` over the same text, which build different
models."""


def test_an_arm_choice_inside_a_decided_repetition_still_refuses() -> None:
    """The decider settles how ``sec+`` and ``stmt+`` carve ``a;a;a;``; the
    arm choice inside each ``stmt`` sits in that decided derivation, so it is
    still a question of meaning, on both engines."""
    compiled = compile_text(DEEP_ARM, cache_key="decider-deep-arm")
    product = prod(compiled)
    with pytest.raises(UnsupportedConstructError, match="ambiguous"):
        earley_model(
            product.instance_grammar, "a;a;a;", compiled.product, product.tables
        )
    with pytest.raises(UnsupportedConstructError, match="ambiguous"):
        compiled.parse("a;a;a;", cores=1)
