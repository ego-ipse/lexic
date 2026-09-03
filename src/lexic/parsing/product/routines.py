"""Per-rule executable completions, read back off the VERIFIED program.

Lowering runs one way — authored records into flat int-coded tables — and
``verify.py`` bounds what it produced. This module reads those tables back into
the form a completion actually runs, so what executes IS the artefact the
verifier passed. Without it the authored records would stay live beside the
program and every engine would resolve its completion from them, leaving the
verifier bounding ranges nothing indexes.

One routine per rule, resolved once at bind and never again. It carries the
verified capture layout, the verified arm width, the verified completion range
index, and the construction that range's own instruction names — which is why
a completion takes ONE argument here where it used to take an authored product
and a table that could belong to a different grammar.

A rule that passes a child through names no construction and records the
capture its instruction sources instead. That is the one distinction the two
completion shapes turn on, and it comes off the instruction rather than off a
type test on an authored record.
"""

from __future__ import annotations

from typing import NamedTuple

from lexic.exceptions import UnsupportedConstructError
from lexic.parsing.product.abi.construction import (
    Construction,
    record_construction,
    symbol_construction,
)
from lexic.parsing.product.abi.expressions import ExprCode
from lexic.parsing.product.abi.records import (
    CompletionRange,
    FlatRuleProduct,
    OpCode,
    ProductProgram,
    RangeKind,
)

__all__ = ["RuleRoutine", "rule_routines"]

_EXPRESSION = int(RangeKind.EXPRESSION)
_PASS = int(OpCode.PASS)
_RECORD = int(OpCode.RECORD)
_SYMBOL = int(ExprCode.SYMBOL)


class RuleRoutine[Carry](NamedTuple):
    """One rule's completion, exactly as the verified program states it.

    :ivar completion: The rule's index into
        :attr:`~lexic.parsing.product.abi.records.ProductProgram.completions` —
        the range the verifier bounded, carried so a baked clone records what
        it was derived from rather than a second derivation of the answer.
    :ivar modes: One lowered
        :class:`~lexic.parsing.product.abi.records.CaptureMode` per capture.
    :ivar slots: The matching lane index per capture.
    :ivar n_items: The rule's sequence-arm item count.
    :ivar source: The capture a pass-through completion forwards, or ``-1``
        when this rule's instruction is not a pass-through.
    :ivar construction: What the completion builds with, or ``None`` when its
        instruction names none.
    """

    completion: int
    modes: tuple[int, ...]
    slots: tuple[int, ...]
    n_items: int
    source: int
    construction: Construction[Carry] | None


def rule_routines[Carry, Result](
    program: ProductProgram[Carry, Result],
) -> tuple[RuleRoutine[Carry], ...]:
    """Resolve one executable routine per rule of a verified program.

    :param program: The lowered program, already through
        :func:`~lexic.parsing.product.verify.verify_program`.
    :returns: One routine per rule, in contextual-code order.
    :raises UnsupportedConstructError: When a fused range holds more than the
        one instruction a rule completion lowers to — reading only its first
        would silently drop the rest.
    """
    return tuple(_routine_of(program, rule) for rule in program.rules)


def _routine_of[Carry, Result](
    program: ProductProgram[Carry, Result], rule: FlatRuleProduct
) -> RuleRoutine[Carry]:
    """One rule's routine, resolved through its own verified range."""
    completion = program.completions[rule.completion]
    if completion.kind == _EXPRESSION:
        source, construction = _expression_construction(program, completion)
    else:
        source, construction = _fused_construction(program, completion)
    return RuleRoutine(
        rule.completion,
        rule.capture_modes,
        rule.capture_slots,
        rule.n_items,
        source,
        construction,
    )


def _fused_construction[Carry, Result](
    program: ProductProgram[Carry, Result], completion: CompletionRange
) -> tuple[int, Construction[Carry] | None]:
    """The pass source and construction one fused completion range names."""
    if completion.length != 1:
        raise UnsupportedConstructError(
            f"product program: a fused completion range of {completion.length} "
            "instructions is not one rule completion"
        )
    opcode = program.fused_opcodes[completion.start]
    row = program.fused_operand_rows[opcode][program.fused_operands[completion.start]]
    if opcode == _PASS:
        return row[0], None
    if opcode == _RECORD:
        return -1, record_construction(program.operands.constructors[row[0]])
    return -1, None


def _expression_construction[Carry, Result](
    program: ProductProgram[Carry, Result], completion: CompletionRange
) -> tuple[int, Construction[Carry] | None]:
    """The construction one expression range names, when it is a lone symbol.

    A symbol expression is a construction only as a completion's SOLE
    operation; a longer program is the later generic-product executor's
    concern and names none here.
    """
    if completion.length != 1:
        return -1, None
    opcode = program.expression_opcodes[completion.start]
    if opcode != _SYMBOL:
        return -1, None
    rows = program.expression_operand_rows[opcode]
    row = rows[program.expression_operands[completion.start]]
    return -1, symbol_construction(program.operands.symbols[row[0]])
