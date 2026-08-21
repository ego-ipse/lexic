"""Adversarial split ownership at nested and adjacent quantifiers.

These are structural splits, not authored arm choices. Earley owns the
definition (the left slot takes the longest extent that leaves a complete
derivation); the PDA must either build that exact model or decline safely.
"""

from __future__ import annotations

import pytest

from lexic.compile import compile_text
from lexic.parsing.pda.core.errors import PdaFail
from lexic.parsing.pda.runtime.kernel.kernel import pda_model
from lexic.parsing.products import earley_model
from tests.unit.lexic.parsing.parsing_helpers import prod

NESTED_PLUS = "root ::= item+\nitem ::= [a-z]+\n"
ADJACENT_PLUS = "root ::= item item+\nitem ::= [a-z]+\n"


def test_nested_plus_is_one_native_pda_item_not_two_short_items() -> None:
    """The outer repeat does not enter the child clone's hard FOLLOW."""
    compiled = compile_text(NESTED_PLUS, cache_key="adversarial-split-nested-plus")
    product = prod(compiled)
    via_pda = pda_model(product.pda, "ab", compiled.fold)
    via_earley = earley_model(
        product.instance_grammar, "ab", compiled.fold, product.tables
    )
    assert via_pda == via_earley
    assert repr(via_pda) == "Root((Item('ab'),))"


def test_adjacent_variable_width_refs_decline_instead_of_reversing_the_split() -> None:
    """Without an extent-aware PDA gate, ``a | bc`` must never be committed."""
    compiled = compile_text(ADJACENT_PLUS, cache_key="adversarial-split-adjacent-plus")
    product = prod(compiled)
    with pytest.raises(PdaFail, match="start rule 'root' is an island"):
        pda_model(product.pda, "abc", compiled.fold)
    via_earley = earley_model(
        product.instance_grammar, "abc", compiled.fold, product.tables
    )
    assert compiled.parse("abc") == via_earley
    assert repr(via_earley) == "Root(Item('ab'), (Item('c'),))"


@pytest.mark.parametrize(
    ("quantifier", "text"),
    [("{2}", "abc"), ("{2,3}", "abc"), ("{2,}", "abc")],
)
def test_bounded_nested_splits_never_disagree(quantifier: str, text: str) -> None:
    """Bounded forms may run natively or fall back, but cannot change ownership."""
    compiled = compile_text(
        f"root ::= item{quantifier}\nitem ::= [a-z]+\n",
        cache_key=f"adversarial-split-{quantifier}",
    )
    product = prod(compiled)
    expected = earley_model(
        product.instance_grammar, text, compiled.fold, product.tables
    )
    assert compiled.parse(text) == expected
    try:
        direct = pda_model(product.pda, text, compiled.fold)
    except PdaFail:
        return
    assert direct == expected
