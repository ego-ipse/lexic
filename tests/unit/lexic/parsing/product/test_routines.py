"""Tests for lexic.parsing.product.routines — completions read off the verified program.

``rule_routines`` reads every field off the program the verifier bounded,
never off a second (authored) representation. A PASS instruction becomes
``source`` with no construction; every other instruction leaves
``source == -1``; a RECORD names its constructor lane; a lone SYMBOL
expression names its symbol lane and a longer expression program names none;
and a fused range of more than one instruction refuses by name rather than
silently reading its first.
"""

from __future__ import annotations

import pytest

from lexic.exceptions import UnsupportedConstructError
from lexic.parsing.product.abi.construction import RecordConstructor, SymbolConstructor
from lexic.parsing.product.abi.expressions import ArgExpr, ExprProgram, SymbolExpr
from lexic.parsing.product.abi.records import (
    CaptureMode,
    CaptureSpec,
    ConstantOp,
    MeaningOp,
    OperandTables,
    PassOp,
    RecordOp,
    RootOp,
    RuleProduct,
)
from lexic.parsing.product.lower import LoweringOwned, lower_product
from lexic.parsing.product.routines import rule_routines

_ROOTS = (lambda carry, _verdicts: carry,)
_MEANINGS = (lambda left, right: left == right,)


class _Pair(tuple):
    """A minimal declared record class with two fields."""

    @classmethod
    def fast_construct(cls):
        return (cls, {}, ("a", "b"))


def _operands() -> OperandTables:
    return OperandTables(
        constants=(),
        constructors=(),
        sequences=(),
        mappings=(),
        meanings=_MEANINGS,
        roots=_ROOTS,
        routes=(),
        continuations=(),
    )


def _lower(rules, owned=LoweringOwned()):
    return lower_product(
        rules, _operands(), owned=owned, root=RootOp(0), meaning=MeaningOp(0)
    )


# ── PASS: source, no construction ────────────────────────────────────────


def test_pass_becomes_a_source_with_no_construction():
    """A PASS instruction's routine names the source it forwards, nothing built."""
    program = _lower([RuleProduct(captures=(), completion=PassOp(4))])
    (routine,) = rule_routines(program)
    assert routine.source == 4
    assert routine.construction is None
    assert routine.completion == program.rules[0].completion


def test_routine_copies_the_verified_capture_layout_and_arm_width():
    """modes/slots/n_items are read straight off the program's FlatRuleProduct."""
    rule = RuleProduct(
        captures=(
            CaptureSpec(int(CaptureMode.MANY), 0),
            CaptureSpec(int(CaptureMode.EXTENT), 1),
        ),
        completion=PassOp(0),
        n_items=2,
    )
    program = _lower([rule])
    (routine,) = rule_routines(program)
    flat = program.rules[0]
    assert (
        routine.modes
        == flat.capture_modes
        == (int(CaptureMode.MANY), int(CaptureMode.EXTENT))
    )
    assert routine.slots == flat.capture_slots == (0, 1)
    assert routine.n_items == flat.n_items == 2


# ── every non-pass fused instruction leaves source == -1 ────────────────


def test_a_non_pass_non_record_fused_instruction_leaves_source_negative_one():
    """CONSTANT is neither PASS nor RECORD — no source, no construction."""
    program = _lower(
        [RuleProduct(captures=(), completion=ConstantOp(0))],
        owned=LoweringOwned(),
    )
    program = program._replace(
        operands=program.operands._replace(constants=(object(),))
    )
    (routine,) = rule_routines(program)
    assert routine.source == -1
    assert routine.construction is None


def test_a_record_instruction_leaves_source_negative_one():
    """RECORD builds a record, not a pass-through — source is unused here."""
    owned = LoweringOwned(
        constructors=(RecordConstructor(cls=_Pair, names=("a", "b")),)
    )
    rule = RuleProduct(
        captures=(
            CaptureSpec(int(CaptureMode.TEXT), 0),
            CaptureSpec(int(CaptureMode.TEXT), 1),
        ),
        completion=RecordOp(0),
        n_items=2,
    )
    program = _lower([rule], owned)
    (routine,) = rule_routines(program)
    assert routine.source == -1


# ── RECORD resolves its constructor lane ─────────────────────────────────


def test_record_resolves_the_constructor_lane_its_row_names():
    """The routine's construction is record_construction of the NAMED entry."""
    owned = LoweringOwned(
        constructors=(RecordConstructor(cls=_Pair, names=("a", "b"), matched_field=""),)
    )
    rule = RuleProduct(
        captures=(
            CaptureSpec(int(CaptureMode.TEXT), 0),
            CaptureSpec(int(CaptureMode.TEXT), 1),
        ),
        completion=RecordOp(0),
        n_items=2,
    )
    program = _lower([rule], owned)
    (routine,) = rule_routines(program)
    assert routine.construction is not None
    assert routine.construction.call is _Pair
    assert routine.construction.names == ("a", "b")


# ── SYMBOL: a lone expression resolves; a longer program does not ───────


def test_a_lone_symbol_expression_resolves_the_symbol_lane():
    """A SYMBOL expression as the COMPLETE (length-1) body names a construction."""
    owned = LoweringOwned(
        symbols=(SymbolConstructor(symbol="tag", names=("value",)),),
        registry={"tag": lambda **kw: kw},
    )
    rule = RuleProduct(captures=(), completion=ExprProgram((SymbolExpr(0),)))
    program = _lower([rule], owned)
    (routine,) = rule_routines(program)
    assert routine.construction is not None
    assert routine.construction.names == ("value",)
    assert routine.source == -1


def test_a_longer_expression_program_names_no_construction():
    """A SYMBOL expression that is NOT the whole body is not a construction here.

    This is the boundary the module draws deliberately: a longer expression
    program is the later generic executor's concern, and reading only the
    first instruction of a multi-op program would silently drop the rest.
    """
    owned = LoweringOwned(
        symbols=(SymbolConstructor(symbol="tag", names=("value",)),),
        registry={"tag": lambda **kw: kw},
    )
    rule = RuleProduct(captures=(), completion=ExprProgram((ArgExpr(0), SymbolExpr(0))))
    program = _lower([rule], owned)
    (routine,) = rule_routines(program)
    assert routine.construction is None
    assert routine.source == -1


def test_a_non_symbol_lone_expression_names_no_construction():
    """A one-instruction expression program that is not SYMBOL builds nothing here."""
    rule = RuleProduct(captures=(), completion=ExprProgram((ArgExpr(0),)))
    program = _lower([rule])
    (routine,) = rule_routines(program)
    assert routine.construction is None


# ── a fused range of more than one instruction refuses by name ──────────


def test_a_fused_range_of_more_than_one_instruction_refuses():
    """Reading only the first instruction of a wider range would drop the rest."""
    program = _lower(
        [
            RuleProduct(captures=(), completion=PassOp(0)),
            RuleProduct(captures=(), completion=PassOp(1)),
        ]
    )
    # Two rules, two length-1 ranges over two distinct fused instructions
    # (distinct sources so the pool did not dedup them into one row).
    assert program.rules[0].completion != program.rules[1].completion
    widened = program.completions[0]._replace(length=2)
    mutated_completions = (widened, *program.completions[1:])
    mutated = program._replace(completions=mutated_completions)
    with pytest.raises(UnsupportedConstructError, match="not one rule completion"):
        rule_routines(mutated)


def test_rule_routines_returns_one_routine_per_rule_in_contextual_order():
    """Order is preserved — the caller indexes routines by contextual code."""
    program = _lower(
        [
            RuleProduct(captures=(), completion=PassOp(0)),
            RuleProduct(captures=(), completion=PassOp(1)),
            RuleProduct(captures=(), completion=PassOp(2)),
        ]
    )
    routines = rule_routines(program)
    assert [routine.source for routine in routines] == [0, 1, 2]
