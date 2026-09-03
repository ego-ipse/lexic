"""Tests for lexic.parsing.product.verify — the cold gate before the paid loop.

Every check refuses a SPECIFIC physical defect: a missing/empty/out-of-bounds
completion range, a mismatched opcode/operand table, an unknown opcode, an
out-of-range operand, an out-of-range lane an instruction points INTO (not
just its own row), and a value that is not an exact ``int`` — including an
``IntEnum``, which the exact-class test exists specifically to catch (an
``IntEnum`` member passes ``isinstance(x, int)``, so that would be the wrong
test). Each test below starts from a program ``lower_product`` actually
produced (so the baseline is real, not hand-typed) and mutates exactly one
physical fact via ``_replace``, then asserts the refusal names it.
"""

from __future__ import annotations

from enum import IntEnum

import pytest

from lexic.exceptions import UnsupportedConstructError
from lexic.parsing.product.abi.records import (
    CaptureMode,
    CaptureSpec,
    ConstructionLicence,
    MeaningOp,
    OpCode,
    PassOp,
    RecordConstructor,
    RecordOp,
    RootOp,
    RuleProduct,
)
from lexic.parsing.product.lower import LoweringOwned, lower_product
from lexic.parsing.product.verify import verify_exact_ints, verify_program
from tests.unit.lexic.parsing.product_test_helpers import (
    Pair,
    operands,
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


# ── constructor relations: what the rule and its constructor must agree on ──


def _record_program(entry, captures=()):
    """One lowered RECORD rule over ``entry`` — lowered, not yet verified."""
    return lower_product(
        [RuleProduct(captures=captures, completion=RecordOp(0))],
        operands(),
        owned=LoweringOwned(constructors=(entry,)),
        root=RootOp(0),
        meaning=MeaningOp(0),
    )


def test_refuses_a_matched_field_the_licence_does_not_order():
    """A declared own-text field the class's own construction order never names."""
    entry = RecordConstructor(
        cls=Pair, matched_field="c", licence=ConstructionLicence(Pair, {}, ("a", "b"))
    )
    with pytest.raises(UnsupportedConstructError, match="licence orders"):
        verify_program(_record_program(entry))


def test_refuses_a_matched_field_that_is_also_a_capture():
    """A field cannot be filled from BOTH the rule's own text and a capture."""
    entry = RecordConstructor(cls=Pair, names=("a",), matched_field="a")
    captures = (CaptureSpec(int(CaptureMode.TEXT), 0),)
    with pytest.raises(UnsupportedConstructError, match="AND with a capture"):
        verify_program(_record_program(entry, captures))


def test_refuses_a_licensed_constructor_leaving_a_field_uncovered():
    """A licensed entry whose class has a field no capture or default reaches."""
    entry = RecordConstructor(
        cls=Pair, names=("a",), licence=ConstructionLicence(Pair, {}, ("a", "b"))
    )
    captures = (CaptureSpec(int(CaptureMode.TEXT), 0),)
    with pytest.raises(
        UnsupportedConstructError, match="neither a capture nor a default"
    ):
        verify_program(_record_program(entry, captures))


def test_refuses_a_record_whose_names_do_not_match_the_rules_captures():
    """A constructor naming two fields cannot be filled by one capture."""
    entry = RecordConstructor(cls=Pair, names=("a", "b"))
    captures = (CaptureSpec(int(CaptureMode.TEXT), 0),)
    with pytest.raises(UnsupportedConstructError, match="captures and"):
        verify_program(_record_program(entry, captures))


def test_refuses_an_optional_index_outside_the_constructors_names():
    """An optional capture index past the names marks a field that is not there."""
    entry = RecordConstructor(cls=Pair, names=("a",), optional=(3,))
    captures = (CaptureSpec(int(CaptureMode.TEXT), 0),)
    with pytest.raises(UnsupportedConstructError, match="optional, outside"):
        verify_program(_record_program(entry, captures))


# ── pass-through relations: the source names one single-value capture ───────


def test_refuses_a_pass_source_that_names_no_capture():
    """PASS(0) on a rule with no captures cannot forward anything."""
    program = lower_product(
        [RuleProduct(captures=(), completion=PassOp(0))],
        operands(),
        root=RootOp(0),
        meaning=MeaningOp(0),
    )
    with pytest.raises(UnsupportedConstructError, match="passes capture 0"):
        verify_program(program)


def test_refuses_a_pass_source_that_is_not_a_single_value_capture():
    """A pass-through forwards ONE value; a TEXT capture is not one."""
    program = lower_product(
        [
            RuleProduct(
                captures=(CaptureSpec(int(CaptureMode.TEXT), 0),), completion=PassOp(0)
            )
        ],
        operands(),
        root=RootOp(0),
        meaning=MeaningOp(0),
    )
    with pytest.raises(UnsupportedConstructError, match="is not one value"):
        verify_program(program)


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
    bad_rule = program.rules[0]._replace(completion=len(program.completions))
    mutated = program._replace(rules=(bad_rule, *program.rules[1:]))
    with pytest.raises(UnsupportedConstructError, match="names completion range"):
        verify_program(mutated)


def test_refuses_an_empty_completion_range():
    """A completion range of length 0 would complete without completing."""
    program = _baseline()
    ranges = list(program.completions)
    ranges[0] = ranges[0]._replace(length=0)
    mutated = program._replace(completions=tuple(ranges))
    with pytest.raises(UnsupportedConstructError, match="empty"):
        verify_program(mutated)


def test_refuses_a_completion_range_that_runs_off_its_table():
    """A range whose start+length exceeds the physical instruction table."""
    program = _baseline()
    ranges = list(program.completions)
    over = ranges[0]._replace(length=ranges[0].length + 1000)
    ranges[0] = over
    mutated = program._replace(completions=tuple(ranges))
    with pytest.raises(UnsupportedConstructError, match="past its"):
        verify_program(mutated)


def test_refuses_a_negative_range_start():
    """A negative start index is refused outright."""
    program = _baseline()
    ranges = list(program.completions)
    ranges[0] = ranges[0]._replace(start=-1)
    mutated = program._replace(completions=tuple(ranges))
    with pytest.raises(UnsupportedConstructError, match="starts at"):
        verify_program(mutated)


def test_refuses_an_unknown_range_kind():
    """A range kind naming neither the expression nor the fused tables."""
    program = _baseline()
    ranges = list(program.completions)
    ranges[0] = ranges[0]._replace(kind=99)
    mutated = program._replace(completions=tuple(ranges))
    with pytest.raises(UnsupportedConstructError, match="unknown kind"):
        verify_program(mutated)


# ── opcode/operand table shape ──────────────────────────────────────────


def test_refuses_mismatched_fused_opcode_and_operand_table_lengths():
    """The fused opcode and operand tables must be the same length."""
    program = _baseline()
    mutated = program._replace(fused_operands=(*program.fused_operands, 0))
    with pytest.raises(UnsupportedConstructError, match="differ in length"):
        verify_program(mutated)


def test_refuses_mismatched_expression_opcode_and_operand_table_lengths():
    """The same shape check, for the physically separate expression tables."""
    program = _baseline()
    mutated = program._replace(expression_operands=(*program.expression_operands, 0))
    with pytest.raises(UnsupportedConstructError, match="differ in length"):
        verify_program(mutated)


def test_refuses_an_unknown_opcode_in_the_fused_table():
    """An opcode with no operand table at all — nothing to route it through."""
    program = _baseline()
    opcodes = list(program.fused_opcodes)
    opcodes[0] = 999
    mutated = program._replace(fused_opcodes=tuple(opcodes))
    with pytest.raises(UnsupportedConstructError, match="unknown opcode"):
        verify_program(mutated)


def test_refuses_an_operand_past_its_own_opcodes_row_table():
    """An operand index beyond the rows its own opcode actually declared."""
    program = _baseline()
    fused_operands = list(program.fused_operands)
    fused_operands[0] = fused_operands[0] + 1000
    mutated = program._replace(fused_operands=tuple(fused_operands))
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
    mutated = program._replace(fused_operand_rows=tuple(rows))
    with pytest.raises(UnsupportedConstructError, match="into `constructors`"):
        verify_program(mutated)


def test_refuses_a_program_level_root_finalizer_out_of_range():
    """The root finalizer is named once for the whole program, bounded too."""
    program = _baseline()
    mutated = program._replace(root=RootOp(len(program.operands.roots)))
    with pytest.raises(UnsupportedConstructError, match="root finalizer"):
        verify_program(mutated)


def test_refuses_a_program_level_meaning_comparator_out_of_range():
    """The ambiguity-gate comparator is bounded the same way."""
    program = _baseline()
    mutated = program._replace(meaning=MeaningOp(len(program.operands.meanings)))
    with pytest.raises(UnsupportedConstructError, match="meaning comparator"):
        verify_program(mutated)


def test_refuses_continuations_that_do_not_pair_with_routes():
    """Continuations are positional against routes — an unpaired count is refused."""
    program = _baseline()
    mutated_operands = program.operands._replace(continuations=(object(),))
    mutated = program._replace(operands=mutated_operands)
    with pytest.raises(UnsupportedConstructError, match="do not pair"):
        verify_program(mutated)


# ── rule-shape defects ───────────────────────────────────────────────────


def test_refuses_a_rule_whose_capture_modes_and_slots_disagree_in_length():
    """One mode per slot — mismatched lengths are a malformed capture layout."""
    program = _baseline()
    bad_rule = program.rules[0]._replace(capture_slots=(0, 1))
    mutated = program._replace(rules=(bad_rule, *program.rules[1:]))
    with pytest.raises(UnsupportedConstructError, match="capture modes"):
        verify_program(mutated)


def test_refuses_an_unknown_capture_mode():
    """A capture mode outside the five lowered CaptureMode values."""
    program = _baseline()
    bad_rule = program.rules[0]._replace(capture_modes=(99,))
    mutated = program._replace(rules=(bad_rule, *program.rules[1:]))
    with pytest.raises(UnsupportedConstructError, match="unknown modes"):
        verify_program(mutated)


def test_refuses_a_negative_capture_slot():
    """A negative slot indexes nothing in any frame lane."""
    program = _baseline()
    bad_rule = program.rules[0]._replace(capture_slots=(-1,))
    mutated = program._replace(rules=(bad_rule, *program.rules[1:]))
    with pytest.raises(UnsupportedConstructError, match="negative slots"):
        verify_program(mutated)


def test_refuses_a_negative_arm_width():
    """n_items is a declared count — negative is not a lowered fact."""
    program = _baseline()
    bad_rule = program.rules[1]._replace(n_items=-1)
    mutated = program._replace(rules=(program.rules[0], bad_rule))
    with pytest.raises(UnsupportedConstructError, match="declares -1 items"):
        verify_program(mutated)
