"""Tests for lexic.parsing.product.verify — the cold gate before the paid loop.

Every check refuses a SPECIFIC physical defect: a missing/empty/out-of-bounds
completion range, a mismatched opcode/operand table, an unknown opcode, an
out-of-range operand, an out-of-range lane an instruction points INTO (not
just its own row), and a value that is not an exact ``int`` — including an
``IntEnum``, which the exact-class test exists specifically to catch (an
``IntEnum`` member passes ``isinstance(x, int)``, so that would be the wrong
test). Each test below starts from a program ``lower_product`` actually
produced (so the baseline is real, not hand-typed) and mutates exactly one
physical fact via ``replaced``, then asserts the refusal names it.
"""

from __future__ import annotations

from enum import IntEnum

import pytest

from lexic.exceptions import UnsupportedConstructError
from lexic.parsing.product.abi.records import (
    CaptureMode,
    CaptureSpec,
    MeaningOp,
    OpCode,
    PassOp,
    ProductProgram,
    RecordConstructor,
    RootOp,
    RuleProduct,
)
from lexic.parsing.product.lower import LoweringOwned, lower_product
from lexic.parsing.product.verify import verify_exact_ints, verify_program
from tests.unit.lexic.parsing.product_test_helpers import (
    Pair,
    operands,
    replaced,
    two_text_capture_rule,
)


def _baseline():
    """A small, REAL lowered-and-verified program: one pass rule, one record rule."""
    rules = [
        RuleProduct(
            captures=(CaptureSpec(int(CaptureMode.ONE), 0),), completion=PassOp(0)
        ),
        two_text_capture_rule(),
    ]
    owned = LoweringOwned(constructors=(RecordConstructor(cls=Pair, names=("a", "b")),))
    program = lower_product(
        rules, operands(), owned=owned, root=RootOp(0), meaning=MeaningOp(0)
    )
    verify_program(program)  # the baseline itself must be clean
    return program


# ── verify_exact_ints: the exact-class boundary ─────────────────────────


class _FakeInt(IntEnum):
    """An IntEnum member — passes isinstance(x, int) but must fail here."""

    ONE = 1


def test_verify_exact_ints_accepts_plain_ints():
    """A table of real ints raises nothing."""
    verify_exact_ints([0, 1, 2], "a table")


def test_verify_exact_ints_refuses_an_intenum_member():
    """An IntEnum passes isinstance(x, int) — the exact-class test must not.

    This is the test that would fail if ``verify_exact_ints`` were rewritten
    to use ``isinstance`` instead of ``value.__class__ is not int``.
    """
    with pytest.raises(UnsupportedConstructError, match="not a lowered int"):
        verify_exact_ints([0, _FakeInt.ONE], "a table")


def test_verify_exact_ints_refuses_a_bool():
    """``bool`` is a subclass of ``int`` in Python — still not an exact int here."""
    with pytest.raises(UnsupportedConstructError, match="not a lowered int"):
        verify_exact_ints([True], "a table")


# ── the baseline itself is accepted ─────────────────────────────────────


def test_a_real_lowered_program_verifies_clean():
    """lower_product's own output passes verify_program — the control row."""
    verify_program(_baseline())  # raises on failure; no exception is the assertion


# ── completion range defects ────────────────────────────────────────────


def test_refuses_a_completion_index_past_the_table():
    """A rule naming a completion range outside the declared table."""
    program = _baseline()
    bad_rule = replaced(program.rules[0], completion=len(program.completions))
    mutated = replaced(program, rules=(bad_rule, *program.rules[1:]))
    with pytest.raises(UnsupportedConstructError, match="names completion range"):
        verify_program(mutated)


def test_refuses_an_empty_completion_range():
    """A completion range of length 0 would complete without completing."""
    program = _baseline()
    ranges = list(program.completions)
    ranges[0] = replaced(ranges[0], length=0)
    mutated = replaced(program, completions=tuple(ranges))
    with pytest.raises(UnsupportedConstructError, match="empty"):
        verify_program(mutated)


def test_refuses_a_completion_range_that_runs_off_its_table():
    """A range whose start+length exceeds the physical instruction table."""
    program = _baseline()
    ranges = list(program.completions)
    over = replaced(ranges[0], length=ranges[0].length + 1000)
    ranges[0] = over
    mutated = replaced(program, completions=tuple(ranges))
    with pytest.raises(UnsupportedConstructError, match="past its"):
        verify_program(mutated)


def test_refuses_a_negative_range_start():
    """A negative start index is refused outright."""
    program = _baseline()
    ranges = list(program.completions)
    ranges[0] = replaced(ranges[0], start=-1)
    mutated = replaced(program, completions=tuple(ranges))
    with pytest.raises(UnsupportedConstructError, match="starts at"):
        verify_program(mutated)


def test_refuses_an_unknown_range_kind():
    """A range kind naming neither the expression nor the fused tables."""
    program = _baseline()
    ranges = list(program.completions)
    ranges[0] = replaced(ranges[0], kind=99)
    mutated = replaced(program, completions=tuple(ranges))
    with pytest.raises(UnsupportedConstructError, match="unknown kind"):
        verify_program(mutated)


# ── opcode/operand table shape ──────────────────────────────────────────


def test_refuses_mismatched_fused_opcode_and_operand_table_lengths():
    """The fused opcode and operand tables must be the same length."""
    program = _baseline()
    mutated = replaced(program, fused_operands=(*program.fused_operands, 0))
    with pytest.raises(UnsupportedConstructError, match="differ in length"):
        verify_program(mutated)


def test_refuses_mismatched_expression_opcode_and_operand_table_lengths():
    """The same shape check, for the physically separate expression tables."""
    program = _baseline()
    mutated = replaced(program, expression_operands=(*program.expression_operands, 0))
    with pytest.raises(UnsupportedConstructError, match="differ in length"):
        verify_program(mutated)


def test_refuses_an_unknown_opcode_in_the_fused_table():
    """An opcode with no operand table at all — nothing to route it through."""
    program = _baseline()
    opcodes = list(program.fused_opcodes)
    opcodes[0] = 999
    mutated = replaced(program, fused_opcodes=tuple(opcodes))
    with pytest.raises(UnsupportedConstructError, match="unknown opcode"):
        verify_program(mutated)


def test_refuses_an_operand_past_its_own_opcodes_row_table():
    """An operand index beyond the rows its own opcode actually declared."""
    program = _baseline()
    fused_operands = list(program.fused_operands)
    fused_operands[0] = fused_operands[0] + 1000
    mutated = replaced(program, fused_operands=tuple(fused_operands))
    with pytest.raises(UnsupportedConstructError, match="past the"):
        verify_program(mutated)


# ── the lanes an instruction's row POINTS into ──────────────────────────


def test_refuses_a_record_instruction_naming_an_out_of_range_constructor():
    """RECORD's row names a constructor lane — bounded, not just its own row.

    This is exactly finding-shaped: a verifier that only bounds the RECORD
    opcode's own row table (which holds one row: the constructor index) would
    miss that the index inside that row points past the constructor table —
    the defect this module's docstring calls out by name.
    """
    program = _baseline()
    row = program.fused_operand_rows[int(OpCode.RECORD)]
    bad_row = tuple((999,) if entry == row[0] else entry for entry in row)
    rows = list(program.fused_operand_rows)
    rows[int(OpCode.RECORD)] = bad_row
    mutated = replaced(program, fused_operand_rows=tuple(rows))
    with pytest.raises(UnsupportedConstructError, match="into `constructors`"):
        verify_program(mutated)


def test_refuses_a_program_level_root_finalizer_out_of_range():
    """The root finalizer is named once for the whole program, bounded too."""
    program = _baseline()
    mutated = replaced(program, root=RootOp(len(program.operands.roots)))
    with pytest.raises(UnsupportedConstructError, match="root finalizer"):
        verify_program(mutated)


def test_refuses_a_program_level_meaning_comparator_out_of_range():
    """The ambiguity-gate comparator is bounded the same way."""
    program = _baseline()
    mutated = replaced(program, meaning=MeaningOp(len(program.operands.meanings)))
    with pytest.raises(UnsupportedConstructError, match="meaning comparator"):
        verify_program(mutated)


def test_refuses_continuations_that_do_not_pair_with_routes():
    """Continuations are positional against routes — an unpaired count is refused."""
    program = _baseline()
    mutated_operands = replaced(program.operands, continuations=(object(),))
    mutated = replaced(program, operands=mutated_operands)
    with pytest.raises(UnsupportedConstructError, match="do not pair"):
        verify_program(mutated)


# ── rule-shape defects ───────────────────────────────────────────────────


def test_refuses_a_rule_whose_capture_modes_and_slots_disagree_in_length():
    """One mode per slot — mismatched lengths are a malformed capture layout."""
    program = _baseline()
    bad_rule = replaced(program.rules[0], capture_slots=(0, 1))
    mutated = replaced(program, rules=(bad_rule, *program.rules[1:]))
    with pytest.raises(UnsupportedConstructError, match="capture modes"):
        verify_program(mutated)


def test_refuses_an_unknown_capture_mode():
    """A capture mode outside the five lowered CaptureMode values."""
    program = _baseline()
    bad_rule = replaced(program.rules[0], capture_modes=(99,))
    mutated = replaced(program, rules=(bad_rule, *program.rules[1:]))
    with pytest.raises(UnsupportedConstructError, match="unknown modes"):
        verify_program(mutated)


def test_refuses_a_negative_capture_slot():
    """A negative slot indexes nothing in any frame lane."""
    program = _baseline()
    bad_rule = replaced(program.rules[0], capture_slots=(-1,))
    mutated = replaced(program, rules=(bad_rule, *program.rules[1:]))
    with pytest.raises(UnsupportedConstructError, match="negative slots"):
        verify_program(mutated)


def test_refuses_a_negative_arm_width():
    """n_items is a declared count — negative is not a lowered fact."""
    program = _baseline()
    bad_rule = replaced(program.rules[1], n_items=-1)
    mutated = replaced(program, rules=(program.rules[0], bad_rule))
    with pytest.raises(UnsupportedConstructError, match="declares -1 items"):
        verify_program(mutated)


# ── replaced(): the shared _replace stand-in itself ──────────────────────


def test_replaced_rebuilds_a_record_equal_to_one_hand_built():
    """Overriding one field gives the SAME record a real ``_replace`` would."""
    program = _baseline()
    rebuilt = replaced(program, stateful=not program.stateful)
    by_hand = ProductProgram(
        program.rules,
        program.completions,
        program.expression_opcodes,
        program.expression_operands,
        program.expression_operand_rows,
        program.fused_opcodes,
        program.fused_operands,
        program.fused_operand_rows,
        program.operands,
        program.root,
        program.meaning,
        not program.stateful,
    )
    assert rebuilt == by_hand


def test_replaced_refuses_an_unknown_field_name():
    """A typo'd override name is refused, not silently ignored."""
    program = _baseline()
    with pytest.raises(ValueError, match="bogus_field"):
        replaced(program, bogus_field=1)
