"""A repetition whose item can match nothing, carved over an empty span.

``X+`` is read as ``X | X X+``. Over an empty span both families of ``X X+``
take nothing, which is the reading ``X+`` again: chosen, the tree build pushes
the same node forever. The split rule drops a step that takes nothing, so the
cycle is never the family kept, under any decider.
"""

from __future__ import annotations

from lexic.compile import compile_text
from lexic.parsing.earley.kernel.forest.support.ambiguity import ParseConfig
from lexic.parsing.earley.kernel.tables.decider import Decider
from lexic.parsing.products import (
    earley_model,
    model_product,
    pda_model,
)
from tests.adversarial.lexic.adversarial_helpers import watchdog
from tests.unit.lexic.parsing.parsing_helpers import decider_program


class _Shortest(Decider):
    """The first slot takes as little as it can."""

    def slot(self, end: int) -> int:
        """The end negated."""
        return -end


EMPTY_TAIL = (
    'top ::= "[" doc "]"\ndoc ::= sec* tail+\nsec ::= part* sepr\npart ::= "b"\n'
    'tail ::= ("a")*\nsepr ::= ";"\n'
)
"""``tail+`` over a ``tail`` that matches nothing; the shortest decider keeps
``sec*`` empty, so ``tail+`` meets its empty span at once."""


def test_the_shortest_decider_answers_a_repetition_of_an_empty_item() -> None:
    """Earley returns the shortest carving, and the PDA compiled for that
    decider's grants, which hands the rule to Earley, returns the same."""
    decide = _Shortest(frozenset())
    config = ParseConfig(decide=decide)
    compiled = compile_text(EMPTY_TAIL, cache_key="zero-width-shortest")
    product = model_product(compiled.codegen_grammar, compiled.product)
    want = "Top(Doc((), (Tail('a'),)))"
    with watchdog(10):
        earley = earley_model(
            product.instance_grammar,
            "[a]",
            compiled.product,
            product.tables,
            config=config,
        )
        assert repr(earley) == want
        assert repr(compiled.parse("[a]", cores=1, decide=decide)) == want
        program = decider_program(compiled, decide)
        got = pda_model(program, "[a]", compiled.executor, config=config)
        assert repr(got) == want


OPTIONAL_SECTIONS = (
    'doc ::= sec* tail?\nsec ::= part* sepr?\npart ::= [ab]\ntail ::= ("a")+\n'
    'sepr ::= ";"\n'
)
"""``sec`` can match nothing, and leftmost-longest reaches ``sec*``'s empty
tail after the text is carved."""


def test_leftmost_longest_answers_a_repetition_of_an_empty_item() -> None:
    """The default decider keeps ``sec*`` longest and stops, instead of
    building the empty ``sec sec*`` forever."""
    compiled = compile_text(OPTIONAL_SECTIONS, cache_key="zero-width-ll")
    product = model_product(compiled.codegen_grammar, compiled.product)
    with watchdog(10):
        got = earley_model(
            product.instance_grammar, ";a", compiled.product, product.tables
        )
    assert repr(got) == "Doc((Sec((), Sepr(';')), Sec((Part('a'),))))"
