"""Tests for lexic.parsing.pda.compiler.program.opcodes — the flat program's
int-coded vocabulary.

A leaf module of plain constants, imported by both the compiler's lowering
passes and the runtime driver — this file pins the invariants that keep the
two sides talking about the same codes.
"""

from __future__ import annotations

from lexic.ir import BIND_MODES
from lexic.parsing.pda.compiler.program import opcodes
from lexic.parsing.pda.compiler.program.opcodes import (
    DISPATCH_EMPTY,
    HI_UNBOUNDED,
    MODE_CODE,
    OP_CC,
    OP_CC1,
    OP_FAIL,
    OP_GRP,
    OP_ISLAND,
    OP_LIT,
    OP_LIT1,
    OP_REF,
    TERMINAL_OPS,
)


def test_every_flat_item_opcode_is_a_distinct_int():
    """No two of the base item op-codes collide."""
    codes = [OP_LIT, OP_CC, OP_REF, OP_GRP, OP_ISLAND, OP_FAIL]
    assert len(codes) == len(set(codes))
    assert all(isinstance(c, int) for c in codes)


def test_terminal_ops_is_exactly_the_text_consuming_codes():
    """The base and specialised literal/charclass codes, and nothing else."""
    assert TERMINAL_OPS == frozenset((OP_LIT, OP_CC, OP_LIT1, OP_CC1))


def test_mode_code_covers_every_bind_mode_in_declared_order():
    """``MODE_CODE`` keys match :data:`BIND_MODES` exactly, and its values are
    assigned in that same order (0..len-1)."""
    assert tuple(MODE_CODE.keys()) == BIND_MODES
    assert tuple(MODE_CODE.values()) == tuple(range(len(BIND_MODES)))


def test_hi_unbounded_is_a_sentinel_distinct_from_any_real_bound():
    """No legal quantifier upper bound is negative."""
    assert HI_UNBOUNDED == -1


def test_dispatch_empty_is_a_stable_sentinel_identity():
    """The module-level constant is the same object across accesses."""
    assert DISPATCH_EMPTY is opcodes.DISPATCH_EMPTY
