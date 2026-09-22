"""The left-recursion fold keeps "ambiguity is refused, by both engines".

`A ::= A β | γ` parsed as `(γ)(β)*` turns the choice between the rule's arms
into where one piece ends. The descent settles a piece's end greedily, which
is the grammar's answer only when no piece can be lengthened into a β. Where
one can, the text means two things, and the public parse must refuse it as
Earley does instead of returning the greedy carving.

The refusal comes from the island sub-parse the unfolded rule falls to, so
its wording is the island's. Earley's wording differs, but the type and the
resolver opt-out are the same.
"""

from __future__ import annotations

import pytest

from lexic.compile import compile_text
from lexic.exceptions import UnsupportedConstructError
from lexic.parsing.products import _model_product, earley_model
from tests.unit.lexic.parsing.pda.runtime.pda_runtime_helpers import pda_and_earley

AMBIGUOUS = {
    "width 0": ('root ::= item\nitem ::= item "a" | x\nx ::= "b" "a"*\n', "ba"),
    "width 1": (
        'root ::= item\nitem ::= item y | x\ny ::= "a"\nx ::= "b" "a"*\n',
        "baa",
    ),
    "noise base": (
        '# @non-semantic x\nroot ::= item\nitem ::= item "a" | x\nx ::= "b" "a"*\n',
        "ba",
    ),
    "base in a sequence": (
        'root ::= item\nitem ::= item "a" | "c" x\nx ::= "b" "a"*\n',
        "cba",
    ),
    "noise base in a sequence": (
        '# @non-semantic x\nroot ::= item\nitem ::= item "a" | "c" x\nx ::= "b" "a"*\n',
        "cbaa",
    ),
    "interior": ('doc ::= item ";"\nitem ::= item "a" | x\nx ::= "b" "a"*\n', "ba;"),
}
"""Each text is ``x`` taking the ``a``s, or the recursive arm taking them."""


@pytest.mark.parametrize("case", sorted(AMBIGUOUS))
def test_a_text_the_fold_could_carve_two_ways_is_refused(case: str) -> None:
    """Refused by the public parse, as Earley refuses it."""
    source, text = AMBIGUOUS[case]
    compiled = compile_text(source, cache_key=f"boundary-{case}")
    product = _model_product(compiled.codegen_grammar, compiled.product)
    with pytest.raises(UnsupportedConstructError, match="supply a resolver"):
        earley_model(product.instance_grammar, text, compiled.product, product.tables)
    with pytest.raises(UnsupportedConstructError, match="supply a resolver"):
        compiled.parse(text)


@pytest.mark.parametrize("text", ["caa", "caaa"])
def test_a_step_that_could_swallow_the_next_is_carved_as_earley_carves(
    text: str,
) -> None:
    """``x ::= "a"+`` as the step: Earley answers one ``a`` per iteration, and
    a fold taking the run greedily would build one iteration instead. The rule
    is left unfolded, so the public parse IS Earley's answer."""
    source = 'root ::= item\nitem ::= item x | "c"\nx ::= "a"+\n'
    compiled = compile_text(source, cache_key="boundary-step-into-step")
    product = _model_product(compiled.codegen_grammar, compiled.product)
    earley = earley_model(
        product.instance_grammar, text, compiled.product, product.tables
    )
    assert compiled.parse(text).dump() == earley.dump()


NEAR_MISSES = {
    "base closes on the step's character": (
        'root ::= item\nitem ::= item "a" | "b" "a"\n',
        ["ba", "baa", "baaaa"],
    ),
    "run then an operator it cannot hold": (
        'root ::= expr\nexpr ::= expr op term | term\nterm ::= [a-z]+\nop ::= "+"\n',
        ["ab", "ab+c", "a+bc+d"],
    ),
    "step whose run cannot start a step": (
        'root ::= item\nitem ::= item x | "c"\nx ::= "a" "b"*\n',
        ["c", "cab", "cabbab"],
    ),
}


@pytest.mark.parametrize(
    ("case", "text"),
    [(case, text) for case, (_source, texts) in NEAR_MISSES.items() for text in texts],
)
def test_a_fold_the_text_settles_is_answered_by_the_pda(case: str, text: str) -> None:
    """The PDA, asked directly, builds Earley's model: still folded."""
    source, _texts = NEAR_MISSES[case]
    pda, earley = pda_and_earley(source, text, f"near-miss-{case}")
    assert pda == earley
