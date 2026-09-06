"""Integration test: the PDA→engine fallback chain (the parse_model product).

:meth:`~lexic.compile.CompiledGrammar.parse` delegates to
:func:`~lexic.parsing.parse_model`, which runs the predictive PDA first and
completes on a whole-input engine reparse on any
:class:`~lexic.parsing.pda.runtime.kernel.kernel.PdaFail`. This module pins one input that
genuinely forces that completion on a real ground-truth grammar (arithmetic's
trailing-whitespace stop-set residue, pivot 4) and proves it both fires and
returns the engine-correct model — ``PdaFail`` never leaks to the public
``parse()`` caller.
"""

from __future__ import annotations

from typing import cast

import pytest

from lexic.compile import compile_from_path
from lexic.model import GrammarModel
from lexic.parsing.pda.compiler.specs import IslandRef
from lexic.parsing.pda.runtime.kernel.kernel import PdaFail, pda_model
from lexic.parsing.products import earley_model
from tests.paths import GROUND_TRUTH
from tests.unit.lexic.parsing.parsing_helpers import prod

# The pinned fallback input: a valid assignment followed by extra blank lines.
# arithmetic's ``ident``/``num``/``term`` all end in their own ``ws ::= [ \t\n]*``,
# whose stop-gate excludes ``\n`` at this call site (it must leave one ``\n`` for
# the mandatory literal after ``term`` in ``root``'s ``(expr "=" ws term "\n")+``)
# — so the loop refuses to consume *any* newline. A single trailing ``\n`` is
# then matched by the mandatory literal, but a second one has no repetition left
# to consume it (there is no ident/num/"(" to start another iteration), so the
# PDA reports unconsumed trailing input rather than guess. The engine parses it
# fine — its ``ws`` isn't cut to one clone's hard tail.
FALLBACK_INPUT = "x=1\n\n\n"


def test_arithmetic_stop_set_residue_forces_pda_fallback():
    """The pinned input genuinely PdaFails the direct PDA call.

    Confirms the premise before trusting the fallback assertions below: this
    input is not merely "some edge case" but one the deterministic PDA cannot
    resolve at all.
    """
    cg = compile_from_path(GROUND_TRUTH / "arithmetic.gbnf")
    p = prod(cg)
    # arithmetic compiles a real clone start — no whole-grammar opt-out.
    assert not isinstance(p.pda.start_key, IslandRef)
    with pytest.raises(PdaFail):
        pda_model(p.pda, FALLBACK_INPUT, cg.executor)


def test_pda_fallback_returns_engine_correct_model():
    """``CompiledGrammar.parse`` swallows the ``PdaFail`` and matches the engine.

    Compares against the forced Earley completion (``earley_model`` over the
    instance grammar) on ``semantic_dump()`` and asserts the round-trip,
    proving the completion is both silent and correct.
    """
    cg = compile_from_path(GROUND_TRUTH / "arithmetic.gbnf")
    p = prod(cg)

    model = cg.parse(FALLBACK_INPUT)
    engine_model = cast(
        GrammarModel,
        earley_model(p.instance_grammar, FALLBACK_INPUT, cg.product, p.tables),
    )

    assert model.semantic_dump() == engine_model.semantic_dump()
    assert model.to_text() == FALLBACK_INPUT
