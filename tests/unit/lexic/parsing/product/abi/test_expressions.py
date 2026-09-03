"""Tests for lexic.parsing.product.abi.expressions — the reducer's own algebra, flat.

Field order is pinned for the same reason as in ``test_records.py``:
``lower.py``'s ``_coded`` reads each authored expression record via
``tuple(operation)``, positionally, so a silently reordered field would desync
what a caller wrote from what the flat row holds.
"""

from __future__ import annotations

from lexic.parsing.product.abi.expressions import (
    ArgExpr,
    ArgsExpr,
    BuildExpr,
    CondExpr,
    ConstantExpr,
    ContributeExpr,
    ExprCode,
    ExprProgram,
    JoinExpr,
    LookupExpr,
    PipeExpr,
    RaiseExpr,
    SymbolExpr,
)


def test_expr_code_members_are_eleven_distinct_ints_from_zero():
    """The reducer-expression vocabulary is dense from 0 — no gaps, no repeats."""
    values = sorted(int(code) for code in ExprCode)
    assert values == list(range(11))


def test_expr_code_is_disjoint_in_value_space_from_opcode_by_convention_only():
    """SYMBOL (10) collides numerically with OpCode.RECORD (10) — by design.

    The two tables are physically separate (fused vs expression), so the same
    integer means different things in each; this pins the value the rest of
    the tree (``routines.py``'s ``_SYMBOL``/``_RECORD`` constants) relies on.
    """
    assert int(ExprCode.SYMBOL) == 10


def test_arg_expr_field_order():
    """ArgExpr is (slot,)."""
    assert tuple(ArgExpr(3)) == (3,)


def test_args_expr_channel_defaults_to_zero():
    """ArgsExpr's one field, ``channel``, defaults to 0."""
    assert ArgsExpr().channel == 0
    assert tuple(ArgsExpr(2)) == (2,)


def test_constant_expr_field_order():
    """ConstantExpr is (constant,)."""
    assert tuple(ConstantExpr(5)) == (5,)


def test_join_expr_field_order():
    """JoinExpr is (separator,)."""
    assert tuple(JoinExpr(1)) == (1,)


def test_build_expr_field_order():
    """BuildExpr is (constructor,)."""
    assert tuple(BuildExpr(4)) == (4,)


def test_pipe_expr_field_order():
    """PipeExpr is (first, then)."""
    assert tuple(PipeExpr(first=1, then=2)) == (1, 2)


def test_cond_expr_field_order():
    """CondExpr is (test, then_at, else_at)."""
    assert tuple(CondExpr(test=0, then_at=1, else_at=2)) == (0, 1, 2)


def test_lookup_expr_field_order():
    """LookupExpr is (subject, table)."""
    assert tuple(LookupExpr(subject=3, table=1)) == (3, 1)


def test_raise_expr_field_order():
    """RaiseExpr is (message,)."""
    assert tuple(RaiseExpr(2)) == (2,)


def test_contribute_expr_field_order():
    """ContributeExpr is (policy,)."""
    assert tuple(ContributeExpr(1)) == (1,)


def test_symbol_expr_field_order():
    """SymbolExpr is (symbol,) — the operand is an int index, never a callable."""
    field = SymbolExpr(3)
    assert tuple(field) == (3,)
    assert field.symbol.__class__ is int


def test_expr_program_carries_its_ops_in_order():
    """ExprProgram's one field is the ordered operation tuple, unchanged."""
    ops = (ArgExpr(0), ConstantExpr(1), PipeExpr(0, 1))
    program = ExprProgram(ops)
    assert program.ops == ops
    assert program.ops[0] is ops[0]
