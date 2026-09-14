"""The demotion cascade: what settles a conflicted decision, and in what order.

`demote_loop` tries four gates and stops at the first that answers. The order is
not arbitrary — the first three ask whether the decision SEPARATES, and the
fourth asks whether the split rule already settles it. A loop the k-window can
decide must therefore never reach the licence, or a decision with a bounded
lookahead answer would be taken by a policy proof instead.
"""

from __future__ import annotations

import pytest

from lexic.compile import compile_text
from lexic.exceptions import UnsupportedConstructError
from lexic.parsing.pda.analysis.analysis import GrammarAnalysis
from lexic.parsing.pda.analysis.demote import demote_loop, store_loop_gate

SEPARABLE = 'doc ::= u+\nu ::= i+ tl\ni ::= [ab]* t\ntl ::= "."\nt ::= ";"\n'
"""The tail is a character no item can end with — the k-window separates it."""

GREEDY = 'doc ::= u+\nu ::= i+ tl\ni ::= [ab]* t\ntl ::= t\nt ::= ";"\n'
"""The tail IS the item's terminator — nothing separates it, and the split
rule settles it."""


def _analysed(source: str, key: str, delegated: bool = False) -> GrammarAnalysis:
    """A finished analysis of ``source``."""
    compiled = compile_text(source, cache_key=key)
    analysis = GrammarAnalysis(compiled.codegen_grammar, delegated=delegated)
    analysis.eval(analysis, compiled.codegen_grammar, ())
    return analysis


def test_a_loop_that_never_conflicts_is_issued_no_licence() -> None:
    """The cascade runs on CONFLICTED decisions, and this one does not conflict.

    ``tl ::= "."`` against ``t ::= ";"`` separates on its first character, so
    the ordinary stop-set settles the loop and no demotion is ever attempted —
    which is why `loop_gates` is empty here too, not only `ready_loop_gates`.
    The licence takes nothing that was already decided.
    """
    analysis = _analysed(SEPARABLE, "demote-separable")

    assert not analysis.taxonomy.ready_loop_gates
    assert not analysis.taxonomy.loop_gates
    assert analysis.islands == frozenset(), "it should parse predictively already"


def test_a_loop_nothing_separates_reaches_the_licence() -> None:
    """The other side of the same order: no k-window gate, one licence."""
    analysis = _analysed(GREEDY, "demote-greedy")

    assert not analysis.taxonomy.loop_gates
    assert len(analysis.taxonomy.ready_loop_gates) == 1
    assert analysis.islands == frozenset()


def test_the_licence_is_withheld_from_a_delegated_analysis() -> None:
    """An island interior runs over a window whose end is not the document's.

    The licence's condition (e) is about where the INPUT ends, so it is not
    certified against the boundary it would execute against, and the cascade
    returns before the certifier is reached.
    """
    delegated = _analysed(GREEDY, "demote-greedy", delegated=True)

    assert not delegated.taxonomy.ready_loop_gates


def test_a_demotion_that_answers_reports_a_soft_note() -> None:
    """A demoted decision is not a silent one: the note says which gate took it."""
    analysis = _analysed(GREEDY, "demote-greedy")
    notes = analysis.demoted.get("u", [])

    assert any("split-greedy" in note for note in notes), notes


def test_store_loop_gate_refuses_two_different_specs_for_one_node() -> None:
    """The identity key cannot express a node at two decision sites.

    A confident-wrong gate would be silent, so the whole grammar opts out
    instead — asserted here because the store moved modules and a tripwire that
    moved without its test is a tripwire nobody is watching.
    """
    analysis = _analysed(GREEDY, "demote-greedy")
    item = list(analysis.rules["u"].body[0])[0]
    spec: tuple = ((),)

    store_loop_gate(analysis, item, spec)
    store_loop_gate(analysis, item, spec)  # equal: fine

    with pytest.raises(UnsupportedConstructError, match="conflicting"):
        store_loop_gate(analysis, item, ((), ()))


def test_demote_loop_is_callable_as_a_free_function() -> None:
    """It is PUBLIC now, because `conflicts` already reached across for it.

    The cascade used to be a private method another module called through the
    analysis object. Shedding it made the name public in its new home rather
    than carrying a private cross-module call.
    """
    assert callable(demote_loop)
    assert demote_loop.__module__.endswith("analysis.demote")
