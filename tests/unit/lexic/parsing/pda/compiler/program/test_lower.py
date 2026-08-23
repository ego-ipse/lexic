"""Tests for lexic.parsing.pda.compiler.program.lower — the flat int-coded
lowering pass.

The specialised op-codes lower's own ``optimize_program`` call produces
(``OP_VSTR``/``OP_LIT1``/``OP_LEAF1``) are pinned in
``tests/unit/lexic/parsing/pda/compiler/program/test_specialize.py``; this
file targets ``flatten_clones``'s own base contributions: build-mode
assignment and per-item quantifier/gate flattening, through the same
``pda_from_text``/``only_arm`` compiler seam.
"""

from __future__ import annotations

from lexic.parsing.pda.compiler.program.opcodes import (
    BUILD_SEQ,
    BUILD_VALUE_STR,
    GATE_STOP,
    HI_UNBOUNDED,
)
from tests.unit.lexic.parsing.pda.compiler.test_clones import only_arm, pda_from_text


def test_a_sequence_rule_with_bound_fields_gets_build_seq():
    """A rule with two bound fields flattens to BUILD_SEQ."""
    pda = pda_from_text('root ::= a b\na ::= [0-9]+\nb ::= "x"\n')
    assert pda.program.start.mode == BUILD_SEQ


def test_a_value_str_rule_gets_build_value_str():
    """The nested all-terminal digit-run rule flattens to BUILD_VALUE_STR."""
    pda = pda_from_text('root ::= a b\na ::= [0-9]+\nb ::= "x"\n')
    a_clone = only_arm(pda.program.start).payloads[0]
    assert a_clone.mode == BUILD_VALUE_STR


def test_an_unbounded_repeat_item_flattens_hi_to_the_unbounded_sentinel():
    """A ``+`` loop's upper bound flattens to HI_UNBOUNDED, not a real int."""
    pda = pda_from_text("root ::= [0-9]+\n")
    arm = only_arm(pda.program.start)
    assert arm.los == (1,)
    assert arm.his == (HI_UNBOUNDED,)


def test_a_bounded_item_flattens_its_exact_lo_and_hi():
    """An exactly-once item flattens lo == hi == 1."""
    pda = pda_from_text('root ::= "a"\n')
    arm = only_arm(pda.program.start)
    assert arm.los == (1,)
    assert arm.his == (1,)


def test_a_single_char_loop_item_flattens_a_stop_set_gate():
    """A digit-run loop gets a GATE_STOP gate over its own char set."""
    pda = pda_from_text('root ::= [0-9]+ "x"\n')
    arm = only_arm(pda.program.start)
    assert arm.gate_kinds[0] == GATE_STOP
    chars, negated = arm.gate_data[0]
    assert negated is False
    assert chars == frozenset("0123456789")
