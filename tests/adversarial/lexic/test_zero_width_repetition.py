"""A repetition whose item can match nothing, carved over an empty span.

``X+`` is read as ``X | X X+``. Over an empty span both families of ``X X+``
take nothing, which is the reading ``X+`` again: chosen, the tree build pushes
the same node forever. The split rule drops a step that takes nothing, so the
cycle is never the family kept, under any decider.
"""

from __future__ import annotations

import pytest

from lexic.compile import compile_text
from lexic.parsing.earley.kernel.forest.support.ambiguity import ParseConfig
from lexic.parsing.pda.core.errors import PdaFail
from lexic.parsing.products import (
    earley_model,
    model_product,
    pda_model,
)
from tests.adversarial.lexic.adversarial_helpers import watchdog
from tests.unit.lexic.parsing.parsing_helpers import Shortest, decider_program

EMPTY_TAIL = (
    'top ::= "[" doc "]"\ndoc ::= sec* tail+\nsec ::= part* sepr\npart ::= "b"\n'
    'tail ::= ("a")*\nsepr ::= ";"\n'
)
"""``tail+`` over a ``tail`` that matches nothing; the shortest decider keeps
``sec*`` empty, so ``tail+`` meets its empty span at once."""


def test_the_shortest_decider_answers_a_repetition_of_an_empty_item() -> None:
    """Earley returns the shortest carving, and the PDA compiled for that
    decider's grants, which hands the rule to Earley, returns the same."""
    decide = Shortest(frozenset())
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


OPTIONAL_PARTS = (
    'top ::= "[" doc "]"\ndoc ::= sec* tail\nsec ::= part* sepr?\npart ::= "a"\n'
    'tail ::= ([a;])\nsepr ::= ";"\n'
)
"""``sec`` can match nothing, so a chain of ``sec*`` may step through an empty
``sec``; the shortest decider reads such a step as taking nothing, not as the
shortest step there is."""


def test_a_chain_step_that_takes_nothing_is_not_the_shortest_step() -> None:
    """Under the shortest decider ``[aa]`` is one section ``a`` and a tail,
    found without stepping through an empty section forever."""
    decide = Shortest(frozenset())
    config = ParseConfig(decide=decide)
    compiled = compile_text(OPTIONAL_PARTS, cache_key="zero-width-chain")
    product = model_product(compiled.codegen_grammar, compiled.product)
    with watchdog(10):
        got = earley_model(
            product.instance_grammar,
            "[aa]",
            compiled.product,
            product.tables,
            config=config,
        )
    assert repr(got) == "Top(Doc((Sec((Part('a'),)),), Tail('a')))"


BRACKETED_RUN = (
    'top ::= "[" doc [ab;]* "]"\ndoc ::= sec* tail\nsec ::= part* sepr\n'
    'part ::= "a"\ntail ::= ([ab])*\nsepr ::= "a"\n'
)
"""``doc`` is an authored slot that may take nothing, beside a run that takes
what it leaves."""


def test_an_authored_slot_that_takes_nothing_is_still_a_slot() -> None:
    """Only a repetition's empty iteration is dropped from a carving; an empty
    ``doc`` is the shortest first slot, so the shortest decider keeps it and
    the run takes ``a`` — on Earley and on the PDA compiled for that decider."""
    decide = Shortest(frozenset())
    config = ParseConfig(decide=decide)
    compiled = compile_text(BRACKETED_RUN, cache_key="zero-width-authored")
    product = model_product(compiled.codegen_grammar, compiled.product)
    want = "Top(Doc((), Tail('')), 'a')"
    with watchdog(10):
        earley = earley_model(
            product.instance_grammar,
            "[a]",
            compiled.product,
            product.tables,
            config=config,
        )
        program = decider_program(compiled, decide)
        pda = pda_model(program, "[a]", compiled.executor, config=config)
    assert repr(earley) == want
    assert repr(pda) == want


AT_LEAST_TWO = 'root ::= x{2,} "b"\nx ::= "a"*\n'
"""``x{2,}`` over ``a``: two iterations the minimum needs, one of them empty."""


def test_an_empty_iteration_the_minimum_needs_is_a_step() -> None:
    """Only an empty iteration beyond the minimum is dropped from a carving.
    ``x{2,}`` needs both of its iterations, so ``("", "a")`` and ``("a", "")``
    are two carvings, and the shortest decider keeps the empty first one: on
    Earley, and on the public parse, which the PDA compiled for that decider
    hands to Earley."""
    decide = Shortest(frozenset())
    config = ParseConfig(decide=decide)
    compiled = compile_text(AT_LEAST_TWO, cache_key="zero-width-minimum")
    product = model_product(compiled.codegen_grammar, compiled.product)
    want = "Root((X(''), X('a')))"
    with watchdog(10):
        earley = earley_model(
            product.instance_grammar,
            "ab",
            compiled.product,
            product.tables,
            config=config,
        )
        with pytest.raises(PdaFail):
            pda_model(
                decider_program(compiled, decide),
                "ab",
                compiled.executor,
                config=config,
            )
        public = compiled.parse("ab", cores=1, decide=decide)
    assert repr(earley) == want
    assert repr(public) == want
    assert repr(compiled.parse("ab", cores=1)) == "Root((X('a'), X('')))"
