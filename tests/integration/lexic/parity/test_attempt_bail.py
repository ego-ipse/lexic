"""A question the PDA hands to the gated engine reaches it.

An attempt audit that finds two arms over one span, or a shorter arm that
could compose, hands the text to the gated engine. From inside an enclosing
attempted iteration, that hand-off must not read as the iteration failing,
or the loop closes and commits a reading the engine would not build.
"""

from __future__ import annotations

import pytest

from lexic.compile import compile_text
from lexic.exceptions import LexicError
from lexic.parsing.products import _model_product, earley_model

AUDIT_INSIDE_AN_ITERATION = (
    'doc ::= part+ tail\npart ::= "aa" ";"? | "a" "a"\ntail ::= [a]*\n'
)
"""At the second ``part``, both arms match ``aa``: the audit bails, and the
``part+`` loop around it had read the bail as a miss, closed, and let ``tail``
take ``aa``."""


def answer(run) -> str:
    """A parse's model dump, or the refusal it raised."""
    try:
        return str(run().dump())
    except LexicError as refused:  # the refusal IS the answer being compared
        return f"refused: {type(refused).__name__}"


@pytest.mark.parametrize("text", ["aa;aa", "aa;aaa"])
def test_an_audit_inside_an_iteration_reaches_the_gated_engine(text: str) -> None:
    """The public parse builds Earley's model: two ``part``s, not one."""
    compiled = compile_text(AUDIT_INSIDE_AN_ITERATION, cache_key="attempt-bail")
    product = _model_product(compiled.codegen_grammar, compiled.product)
    want = answer(
        lambda: earley_model(
            product.instance_grammar, text, compiled.product, product.tables
        )
    )
    assert answer(lambda: compiled.parse(text)) == want
