"""What follows a child the parse descended into through an exactly-once
reference: the item after the reference, not the one after that.

An exactly-once reference advances its frame past itself before it descends,
so a walk up the chain that reads "the rest after the current item" skipped
the item that actually follows the child. A loop inside the child then saw
no continuation for a character the parent's next item needs, called the
boundary dead, and took the character: the PDA failed where the decider
stops the loop.
"""

from __future__ import annotations

import pytest

from lexic.compile import compile_text
from lexic.parsing.pda.core.errors import PdaFail
from lexic.parsing.pda.runtime.admission import REST_DEAD
from lexic.parsing.pda.runtime.kernel import decisions
from lexic.parsing.pda.runtime.kernel.kernel import pda_model
from lexic.parsing.products import earley_model
from tests.unit.lexic.parsing.parsing_helpers import prod
from tools.benchmark.cases.grammars import BENCHES

CLOSED_BODY = (
    'root ::= "<" body\nbody ::= " " text " " ">"\n'
    'text ::= word (" " word)*\nword ::= [^ ]+\n'
)
"""``text`` is an exactly-once reference followed by a mandatory ``" "``; a
word may be ``>``, so `` >`` could be one more word or the body's close."""


@pytest.mark.parametrize("text", ["< a >", "< a b >", "< a b c >"])
def test_a_loop_stops_where_the_parents_next_item_needs_its_character(
    text: str,
) -> None:
    """The PDA answers, and answers what Earley does: the words stop before
    `` >``, which closes the body."""
    compiled = compile_text(CLOSED_BODY, cache_key="exactly-once-body")
    product = prod(compiled)
    earley = earley_model(
        product.instance_grammar, text, compiled.product, product.tables
    )
    try:
        assert pda_model(product.pda, text, compiled.executor) == earley
    except PdaFail as fail:
        pytest.fail(f"the PDA did not answer {text!r}: {fail}")


def test_the_vyx_body_close_is_never_a_dead_end(monkeypatch) -> None:
    """The vyx packet that exposed it: at each word boundary of its inline body
    the space is the body's mandatory close. Read past the item after the
    reference, the boundary was DEAD and the loop took the space; now it never
    is. (It reads ADMITS rather than HARD: whether that item is still due is
    not told apart from an attempted iteration, so it is read as optional.)
    The public parse is Earley's."""
    bench = next(one for one in BENCHES if one.name == "vyx")
    text = '!O c:\\U00075728\\U0010c40c\\U000f7780="" ^E L9< \\\\n\\U000cc001 >'
    text = text.encode().decode("unicode_escape")
    real = vars(decisions.Attempting)["_beyond_class"]
    seen: list[tuple[str, int]] = []

    def classing(self, arm, i, char):
        got = real(self, arm, i, char)
        seen.append((self.stack[-1].clone.name, got))
        return got

    monkeypatch.setattr(decisions.Attempting, "_beyond_class", classing)
    compiled = bench.compiled
    product = prod(compiled)
    earley = earley_model(
        product.instance_grammar, text, compiled.product, product.tables
    )
    assert compiled.parse(text) == earley
    body = [cls for name, cls in seen if name == "nl-text"]
    assert body and REST_DEAD not in body, seen
