"""Integration test: the PDA→engine fallback chain (the parse_model product).

:meth:`~lexic.compile.CompiledGrammar.parse` delegates to
:func:`~lexic.parsing.parse_model`, which runs the predictive PDA first and
completes on a whole-input engine reparse on any
:class:`~lexic.parsing.pda.runtime.kernel.kernel.PdaFail`. This module pins one input that
genuinely forces that completion on a real ground-truth grammar (vyx's
``nl-escape`` island seeing two ends that both compose) and proves it
both fires and returns the engine-correct model — ``PdaFail`` never leaks to the
public ``parse()`` caller.
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

# The pinned fallback input: an inline body of escaped lines. ``nl-escape``'s
# tail takes every printable character, the ``\n`` separator's included, so the
# first line can end after ``\#`` or run on through the separators to the last
# line's end. The rule is an island, and its two ends both compose with what
# follows; the island refuses rather than pick one, and the PDA reports the
# refusal.
FALLBACK_GRAMMAR = GROUND_TRUTH / "vyx.gbnf"
FALLBACK_INPUT = "!R \\#\\n# \\n\\#\\n\\#\\n >"


def test_a_run_that_takes_its_separator_forces_pda_fallback():
    """The pinned input genuinely PdaFails the direct PDA call.

    Confirms the premise before trusting the fallback assertions below: this
    input is not merely "some edge case" but one the deterministic PDA cannot
    resolve at all.
    """
    cg = compile_from_path(FALLBACK_GRAMMAR)
    p = prod(cg)
    # vyx compiles a real clone start — no whole-grammar opt-out.
    assert not isinstance(p.pda.start_key, IslandRef)
    with pytest.raises(PdaFail):
        pda_model(p.pda, FALLBACK_INPUT, cg.executor)


def test_arithmetic_blank_lines_derive_on_the_pda():
    """arithmetic's trailing blank lines stay on the predictive engine: its
    ``ws`` run is decided where the run ends, so it takes every newline but the
    line's own ``"\\n"``, and the model is Earley's."""
    cg = compile_from_path(GROUND_TRUTH / "arithmetic.gbnf")
    p = prod(cg)
    text = "x=1\n\n\n"
    got = pda_model(p.pda, text, cg.executor)
    want = earley_model(p.instance_grammar, text, cg.product, p.tables)
    assert got.semantic_dump() == want.semantic_dump()


def test_pda_fallback_returns_engine_correct_model():
    """``CompiledGrammar.parse`` swallows the ``PdaFail`` and matches the engine.

    Compares against the forced Earley completion (``earley_model`` over the
    instance grammar) on ``semantic_dump()`` and asserts the round-trip,
    proving the completion is both silent and correct.
    """
    cg = compile_from_path(FALLBACK_GRAMMAR)
    p = prod(cg)

    model = cg.parse(FALLBACK_INPUT)
    engine_model = cast(
        GrammarModel,
        earley_model(p.instance_grammar, FALLBACK_INPUT, cg.product, p.tables),
    )

    assert model.semantic_dump() == engine_model.semantic_dump()
    assert model.to_text() == FALLBACK_INPUT
