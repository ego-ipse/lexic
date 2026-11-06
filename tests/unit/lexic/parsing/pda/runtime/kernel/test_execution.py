"""Tests for lexic.parsing.pda.runtime.kernel.execution — leaf execution,
island delegation, and frame completion.

``KernelExecutionMixin``'s methods read the live ``PdaKernel`` cursor's state
and have no standalone construction; the general PDA/Earley parity coverage
(``test_kernel.py``, the parity suite) exercises the driver end to end. This
file targets small grammars chosen so a real ``pda_model`` parse is forced
through each of execution.py's distinct leaf/dispatch shapes: a frame-less
``value_str`` + ``sequence`` mix (``_run_leaf``'s OP_LIT/OP_V1/OP_CC1
branches), a nested leaf-in-leaf reference (``OP_LEAF1``), and an all-
``value_str`` dispatch (``OP_VDISP`` / ``_match_vdisp``).
"""

from __future__ import annotations

import pytest

from lexic.compile import compile_text
from lexic.exceptions import EngineInvariantError, LexicError
from lexic.parsing.pda.compiler.program.bake.lowering import no_shape_build
from lexic.parsing.pda.compiler.program.opcodes import BUILD_ALT, BUILD_SEQ
from lexic.parsing.pda.runtime.build import Frame
from lexic.parsing.pda.runtime.kernel.execution import KernelExecutionMixin
from lexic.parsing.pda.runtime.kernel.kernel import pda_model
from tests.paths import GROUND_TRUTH
from tests.unit.lexic.parsing.pda.compiler.test_clones import pda_from_text
from tests.unit.lexic.parsing.pda.runtime.flat_support import flat_arm, flat_clone
from tests.unit.lexic.parsing.pda.runtime.kernel.verdicts.side_support import (
    live_kernel,
)

COMPLETE = vars(KernelExecutionMixin)["_complete"]
"""Frame completion as the mixin defines it, driven on a real kernel."""


def _model_for(text: str, grammar: str, cache_key: str):
    pda = pda_from_text(grammar)
    compiled = compile_text(grammar, flavour="gbnf", cache_key=cache_key)
    return pda_model(pda, text, compiled.executor)


def test_a_mixed_literal_clone_ref_and_charclass_leaf_builds_correctly():
    """``root ::= "a"? mid [0-9]`` runs the leaf licence over OP_LIT (optional
    literal), OP_V1 (an inline value_str clone reference), and OP_CC1 (an
    exactly-once char class) in the same frame-less arm."""
    grammar = 'root ::= "a"? mid [0-9]\nmid ::= "m"\n'
    model = _model_for("am5", grammar, "exec-mixed-leaf")
    assert model.dump() == {"mid": {"value": "m"}, "digit": "5", "a": "a"}
    assert model.to_text() == "am5"


def test_a_mixed_leaf_without_the_optional_prefix_omits_it():
    """The same leaf shape with the optional literal absent still parses."""
    grammar = 'root ::= "a"? mid [0-9]\nmid ::= "m"\n'
    model = _model_for("m5", grammar, "exec-mixed-leaf-no-a")
    assert model.to_text() == "m5"


def test_a_nested_leaf_in_leaf_reference_builds_without_a_frame_per_hop():
    """``p`` is a pass-through single-ref rule to the all-terminal ``a`` —
    OP_LEAF1 recurs into ``_run_leaf`` rather than descending a frame."""
    grammar = 'root ::= p q\np ::= a\na ::= [0-9]+ "x"\nq ::= "y"\n'
    model = _model_for("12xy", grammar, "exec-leaf1")
    assert model.dump() == {"p": {"a": {"value": "12x"}}, "q": {"value": "y"}}
    assert model.to_text() == "12xy"


def test_an_all_value_str_dispatch_inlines_without_a_table():
    """Every arm of ``item`` is an inlinable ``value_str`` target — the
    repeated reference runs through ``_match_vdisp`` (OP_VDISP), selecting a
    fresh target clone by lead character each iteration."""
    grammar = "root ::= item+\nitem ::= a | b\na ::= [0-9]+\nb ::= [a-z]+\n"
    model = _model_for("12abc34", grammar, "exec-vdisp")
    assert model.to_text() == "12abc34"
    assert model.dump() == {
        "item": [{"value": "12"}, {"value": "abc"}, {"value": "34"}]
    }


def test_completion_round_trips_a_realistic_grammar_end_to_end():
    """A catch-all correctness pin over ``_complete``'s full clone-mode
    dispatch (value_str, sequence, alt/dispatch) via a compiled ground-truth
    grammar, exercising whichever modes that grammar's own shapes reach."""
    compiled = compile_text(
        (GROUND_TRUTH / "arithmetic.gbnf").read_text(),
        flavour="gbnf",
        cache_key="exec-roundtrip",
    )
    text = "1+2*3=x\n"
    model = compiled.parse(text, cores=1)
    assert model.to_text() == text


def test_a_build_that_refuses_its_values_refuses_the_parse(monkeypatch) -> None:
    """A completion whose build refuses its values raises that refusal itself:
    on the plain path it is the document's answer. Turned into a decline, the
    parse fell back to the gated engine, whose own fold need not refuse (the
    notation's stray comma came back as a value)."""
    kern = live_kernel()
    frame = Frame(flat_arm(1), [], flat_clone(BUILD_ALT, name="x"), 0)
    kern.stack = [frame]
    refused = LexicError("the build refused")
    monkeypatch.setattr(Frame, "alt_model", lambda _self: _refuse(refused))
    with pytest.raises(LexicError) as fail:
        COMPLETE(kern, frame)
    assert fail.value is refused
    assert not frame.out


def test_a_build_that_disagrees_with_its_clone_is_no_refusal() -> None:
    """An arm whose item count matches neither its clone's slots nor the empty
    arm is a compile/runtime disagreement: it leaves the parse as an engine
    invariant, never as a refusal a fallback would answer."""
    kern = live_kernel()
    clone = flat_clone(BUILD_SEQ, name="x", ctor=None, n_items=2, build=no_shape_build)
    frame = Frame(flat_arm(1), [], clone, 0)
    kern.stack = [frame]
    with pytest.raises(EngineInvariantError, match="match neither"):
        COMPLETE(kern, frame)


def _refuse(why: LexicError) -> None:
    """Raise from inside a lambda, so the patched build stays one expression."""
    raise why
