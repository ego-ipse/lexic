"""Whole-document Earley keeps the decider's carving, and the PDA agrees.

The decider is leftmost-longest over authored slots, top-down: a node's
boundaries are chosen first, the first slot longest, and only a choice between
ARMS at the boundaries it keeps is a question of meaning. These are the census
witnesses, each once decided by chart order or refused over a carving the
decider rejects.
"""

from __future__ import annotations

import pytest

from lexic.compile import compile_text
from lexic.exceptions import UnsupportedConstructError
from lexic.parsing.earley.kernel.forest.support.ambiguity import ParseConfig
from lexic.parsing.earley.kernel.tables.decider import Decider
from lexic.parsing.pda.compiler.program.flatten import clone_arms
from lexic.parsing.pda.compiler.program.opcodes import GATE_SCAN
from lexic.parsing.pda.compiler.tables import PdaTables
from lexic.parsing.pda.core.errors import PdaFail
from lexic.parsing.products import (
    earley_model,
    grants_program,
    model_product,
    pda_model,
)
from tests.clone_walk import walk_program_clones
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


class _Shortest(Decider):
    """The reverse order: the first slot takes as little as it can."""

    def slot(self, end: int) -> int:
        """The end negated."""
        return -end


SHORTEST = {
    "W-a": ("root ::= x+\nx ::= [a]+\n", "aaa", "Root((X('a'), X('a'), X('a')))"),
    "one run per character": (
        "root ::= item+\nitem ::= [a-z]+\n",
        "abc",
        "Root((Item('a'), Item('b'), Item('c')))",
    ),
}
"""``(grammar, text, the shortest decider's model)``: each loop the PDA takes
by a leftmost-longest licence, carved the other way."""


@pytest.mark.parametrize("case", sorted(SHORTEST))
def test_the_public_parse_keeps_a_shortest_deciders_carving(case: str) -> None:
    """The PDA compiled for the shortest decider's grants takes none of the
    leftmost-longest shortcuts: the rule they settled islands, its extent is
    undecided, and the predictive parse declines rather than commit the
    longest carving. Earley, reading the decider's slots, answers — the same
    model the public parse returns."""
    source, text, want = SHORTEST[case]
    decide = _Shortest(frozenset())
    compiled = compile_text(source, cache_key=f"shortest-{case}")
    product = model_product(compiled.codegen_grammar, compiled.product)
    program = grants_program(
        compiled.codegen_grammar,
        compiled.product,
        product.instance_grammar,
        decide.grants,
    )
    with pytest.raises(PdaFail):
        pda_model(program, text, compiled.executor, config=ParseConfig(decide=decide))
    assert repr(compiled.parse(text, cores=1, decide=decide)) == want
    assert repr(compiled.parse(text, cores=1)) != want


@pytest.mark.parametrize("case", sorted(SHORTEST))
def test_a_leftmost_longest_program_refuses_a_decider_it_was_not_compiled_for(
    case: str,
) -> None:
    """The artefact's own tables (``pda_tables()``) are compiled under
    leftmost-longest's licences. Driven directly under a decider that grants
    none of them, they refuse instead of answering in the wrong order."""
    source, text, want = SHORTEST[case]
    compiled = compile_text(source, cache_key=f"shortest-{case}")
    config = ParseConfig(decide=_Shortest(frozenset()))
    with pytest.raises(PdaFail, match="licences"):
        pda_model(compiled.pda_tables(), text, compiled.executor, config=config)
    assert repr(pda_model(compiled.pda_tables(), text, compiled.executor)) != want


SECTIONS = (
    'doc ::= sec+ tail?\nsec ::= part* sepr\npart ::= [a;]\ntail ::= ("a")*\n'
    'sepr ::= ";"\n'
)
"""Under a shortest decider ``;;`` is two sections, each an empty ``part*`` and
its separator. Leftmost-longest gates ``sec+`` by skipping a whole ``part*``
run and peeking for the separator, which eats the second ``;``."""


def _scans(tables: PdaTables) -> bool:
    """Whether any item of the program is gated by a scan gate."""
    clones = walk_program_clones(tables.program.start).values()
    return any(
        GATE_SCAN in arm.gate_kinds[: arm.n] for c in clones for arm in clone_arms(c)
    )


def test_a_scan_gate_is_a_conflict_for_a_decider_that_does_not_grant_it() -> None:
    """The program compiled for the shortest decider's grants carries no scan
    gate, so the predictive parse refuses rather than read ``part*`` the
    leftmost-longest way; the public parse is the gated engine's model."""
    decide = _Shortest(frozenset())
    compiled = compile_text(SECTIONS, cache_key="shortest-sections")
    product = model_product(compiled.codegen_grammar, compiled.product)
    program = grants_program(
        compiled.codegen_grammar,
        compiled.product,
        product.instance_grammar,
        decide.grants,
    )
    assert _scans(product.pda)
    assert not _scans(program)
    with pytest.raises(PdaFail):
        pda_model(program, ";;", compiled.executor, config=ParseConfig(decide=decide))
    want = "Doc((Sec((), Sepr(';')), Sec((), Sepr(';'))), Tail(''))"
    assert repr(compiled.parse(";;", cores=1, decide=decide)) == want


BRACKETED = (
    'top ::= "[" doc [ab;]* "]"\ndoc ::= sec* tail\nsec ::= part+ sepr?\n'
    'part ::= [ab]\ntail ::= ("a" "b"?)*\nsepr ::= "a"\n'
)
"""``doc`` islands for a decider that grants nothing, and inside the brackets it
may end at any of its completions: the run after it takes what it leaves."""


def test_an_islands_two_ends_are_ranked_by_another_decider() -> None:
    """The predictive parse ranks the island's followable ends by the decider
    it is asked under: the shortest keeps ``doc`` empty, which is the gated
    engine's model and not leftmost-longest's."""
    decide = _Shortest(frozenset())
    compiled = compile_text(BRACKETED, cache_key="shortest-bracketed")
    product = model_product(compiled.codegen_grammar, compiled.product)
    program = grants_program(
        compiled.codegen_grammar,
        compiled.product,
        product.instance_grammar,
        decide.grants,
    )
    config = ParseConfig(decide=decide)
    want = "Top(Doc((), Tail('')), 'ab')"
    assert repr(pda_model(program, "[ab]", compiled.executor, config=config)) == want
    assert repr(compiled.parse("[ab]", cores=1, decide=decide)) == want
    assert repr(compiled.parse("[ab]", cores=1)) != want


CLOSED = (
    'top ::= "[" doc "]" [ab;]*\ndoc ::= sec+ tail?\nsec ::= part+ sepr?\n'
    'part ::= "b"\ntail ::= ("a" "b"?)*\nsepr ::= "a"\n'
)
"""``sec`` islands, and its two ends inside ``[bb]`` are two carvings of the
``sec+`` repetition: one ``bb`` section, or two ``b`` sections."""


def test_a_completed_pair_another_decider_cannot_rank_is_not_taken() -> None:
    """The two ends are iterations, ranked here only under leftmost-longest, so
    under the shortest decider the pair forks rather than keep the longer end
    leftmost-longest would; the public parse is the gated engine's two
    sections."""
    decide = _Shortest(frozenset())
    compiled = compile_text(CLOSED, cache_key="shortest-closed")
    product = model_product(compiled.codegen_grammar, compiled.product)
    program = grants_program(
        compiled.codegen_grammar,
        compiled.product,
        product.instance_grammar,
        decide.grants,
    )
    with pytest.raises(PdaFail):
        pda_model(program, "[bb]", compiled.executor, config=ParseConfig(decide=decide))
    want = "Top(Doc((Sec((Part('b'),)), Sec((Part('b'),))), Tail('')), '')"
    assert repr(compiled.parse("[bb]", cores=1, decide=decide)) == want
