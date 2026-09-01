"""Physical-table verification — refuse a defective program before it runs.

A compiled product is data, and data can be wrong in ways the type system
cannot see: a rule pointing at no completion range, an empty range, a range
running off its table, an opcode with no operand table, an operand past that
table's end. Each of those is a defect of the artefact, so each is diagnosed
with words *before* the paid loop starts rather than crashing inside it.

The exact-int audit is the other half. Lowering converts every authored
:class:`~enum.IntEnum` to a plain ``int``; this checks it did, by comparing the
value's exact class. ``isinstance`` is the wrong test here and would defeat the
purpose — an ``IntEnum`` member passes ``isinstance(x, int)`` happily and would
ride into a runtime table, paying enum lookup on every completion.

This is cold work. It runs once per bound program, never at a completion.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from lexic.exceptions import UnsupportedConstructError
from lexic.parsing.product.expressions import ExprCode
from lexic.parsing.product.records import (
    CaptureMode,
    CompletionRange,
    OpCode,
    ProductProgram,
    RangeKind,
)

__all__ = ["verify_exact_ints", "verify_program"]

_CAPTURE_MODES = frozenset(int(mode) for mode in CaptureMode)
"""The lowered capture vocabulary. A mode outside it would index a lane the
frame does not have, so it is refused here rather than at the first capture."""

_EXPRESSION = int(RangeKind.EXPRESSION)
_FUSED_KINDS = frozenset(
    (int(RangeKind.FUSED), int(RangeKind.RECOVERY), int(RangeKind.DELEGATE))
)
"""EXPRESSION indexes the reducer-expression tables; the other three index the
fused tables. A range naming anything else is refused."""

_FUSED_LANES: Mapping[int, tuple[tuple[int, str], ...]] = {
    int(OpCode.CONSTANT): ((0, "constants"),),
    int(OpCode.FINISH_SEQUENCE): ((1, "sequences"),),
    int(OpCode.FINISH_MAPPING): ((1, "mappings"),),
    int(OpCode.RECORD): ((0, "constructors"),),
}
"""Which row field of a fused instruction indexes which operand table.

An operation's fields are all lane indices, and until now only the operand's
own row table was bounded — an instruction could name constructor 9 of a
two-entry table and reach the engine. Open, like every other dispatch here: an
operation joins by adding its row, and one with no row indexes no operand
table, which is the truth for the collection begins and the pass-through."""

_EXPRESSION_LANES: Mapping[int, tuple[tuple[int, str], ...]] = {
    int(ExprCode.CONSTANT): ((0, "constants"),),
    int(ExprCode.BUILD): ((0, "constructors"),),
    int(ExprCode.LOOKUP): ((1, "routes"),),
    int(ExprCode.SYMBOL): ((0, "symbols"),),
}
"""The same, for the reducer-expression table. ``SYMBOL`` is the one that must
never be unbounded: its lane holds the only resolved callables in the program."""


def verify_exact_ints(values: Iterable[object], what: str) -> None:
    """Refuse any value that is not a plain ``int``.

    :param values: The lowered table entries to audit.
    :param what: What the table is, for the message.
    :raises UnsupportedConstructError: On the first non-``int`` value. An
        ``IntEnum`` member fails here by design, which is why the test is an
        exact-class comparison and not ``isinstance``.
    """
    for value in values:
        if value.__class__ is not int:
            raise UnsupportedConstructError(
                f"product program: {what} holds {value!r} of type "
                f"{type(value).__name__}, not a lowered int"
            )


def verify_program[Carry, Result](program: ProductProgram[Carry, Result]) -> None:
    """Refuse a program whose physical tables cannot be executed.

    :param program: The compiled product to check.
    :raises UnsupportedConstructError: On a missing, empty, mixed, or
        out-of-bounds completion range, a mismatched opcode/operand table, an
        unknown opcode, an out-of-range operand, or a table entry that is not
        a plain ``int``.
    """
    _verify_table_shape(program)
    _verify_program_lanes(program)
    for at, rule in enumerate(program.rules):
        _verify_rule_shape(program, at, rule.capture_modes, rule.capture_slots)
        completion = _completion_of(program, at, rule.completion)
        _verify_range(program, at, completion)


def _verify_program_lanes[Carry, Result](
    program: ProductProgram[Carry, Result],
) -> None:
    """Refuse the program-level operands that name a lane out of range.

    The root finalizer and the meaning comparator are named once for the whole
    program rather than by an instruction, so they are bounded here. Routes and
    continuations pair positionally — a route classifies a key and the
    continuation says where it goes — so an unpaired table would leave a
    classified key with nowhere to land.
    """
    operands = program.operands
    _verify_lane("the root finalizer", program.root.finalizer, len(operands.roots))
    _verify_lane(
        "the meaning comparator", program.meaning.comparator, len(operands.meanings)
    )
    if operands.continuations and len(operands.continuations) != len(operands.routes):
        raise UnsupportedConstructError(
            f"product program: {len(operands.routes)} routes and "
            f"{len(operands.continuations)} continuations do not pair"
        )


def _verify_lane(what: str, index: int, size: int) -> None:
    """Refuse a lane index outside the table it names.

    :param what: What names the lane, for the message.
    :param index: The index it names.
    :param size: How many entries that table holds.
    :raises UnsupportedConstructError: When the index is not a lowered int, is
        negative, or is past the table's end.
    """
    if index.__class__ is not int:
        raise UnsupportedConstructError(f"product program: {what} is not a lowered int")
    if index < 0 or index >= size:
        raise UnsupportedConstructError(
            f"product program: {what} names entry {index} of a {size}-entry table"
        )


def _verify_table_shape[Carry, Result](program: ProductProgram[Carry, Result]) -> None:
    """Refuse instruction tables whose opcodes and operands disagree."""
    if len(program.expression_opcodes) != len(program.expression_operands):
        raise UnsupportedConstructError(
            "product program: expression opcode and operand tables differ in "
            f"length ({len(program.expression_opcodes)} vs "
            f"{len(program.expression_operands)})"
        )
    if len(program.fused_opcodes) != len(program.fused_operands):
        raise UnsupportedConstructError(
            "product program: fused opcode and operand tables differ in "
            f"length ({len(program.fused_opcodes)} vs "
            f"{len(program.fused_operands)})"
        )
    verify_exact_ints(program.expression_opcodes, "the expression opcode table")
    verify_exact_ints(program.expression_operands, "the expression operand table")
    verify_exact_ints(program.fused_opcodes, "the fused opcode table")
    verify_exact_ints(program.fused_operands, "the fused operand table")


def _verify_rule_shape[Carry, Result](
    program: ProductProgram[Carry, Result],
    at: int,
    modes: tuple[int, ...],
    slots: tuple[int, ...],
) -> None:
    """Refuse a capture layout that is not int-coded, paired, and in range."""
    del program
    if len(modes) != len(slots):
        raise UnsupportedConstructError(
            f"product program: rule {at} has {len(modes)} capture modes and "
            f"{len(slots)} capture slots"
        )
    verify_exact_ints(modes, f"rule {at}'s capture modes")
    verify_exact_ints(slots, f"rule {at}'s capture slots")
    unknown = sorted(set(modes) - _CAPTURE_MODES)
    if unknown:
        raise UnsupportedConstructError(
            f"product program: rule {at} captures under unknown modes {unknown}"
        )
    negative = sorted(slot for slot in slots if slot < 0)
    if negative:
        raise UnsupportedConstructError(
            f"product program: rule {at} captures into negative slots {negative}"
        )


def _completion_of[Carry, Result](
    program: ProductProgram[Carry, Result], at: int, index: int
) -> CompletionRange:
    """The rule's one completion range, or a refusal naming the rule."""
    if index.__class__ is not int:
        raise UnsupportedConstructError(
            f"product program: rule {at}'s completion index is not a lowered int"
        )
    if index < 0 or index >= len(program.completions):
        raise UnsupportedConstructError(
            f"product program: rule {at} names completion range {index}, "
            f"which is outside the {len(program.completions)} declared"
        )
    return program.completions[index]


def _verify_range[Carry, Result](
    program: ProductProgram[Carry, Result], at: int, completion: CompletionRange
) -> None:
    """Refuse an empty, mis-tagged, or out-of-bounds instruction range."""
    if completion.length <= 0:
        raise UnsupportedConstructError(
            f"product program: rule {at}'s completion range is empty"
        )
    if completion.start < 0:
        raise UnsupportedConstructError(
            f"product program: rule {at}'s completion range starts at "
            f"{completion.start}"
        )
    opcodes, operands, rows = _tables_for(program, at, completion.kind)
    lanes = _EXPRESSION_LANES if completion.kind == _EXPRESSION else _FUSED_LANES
    stop = completion.start + completion.length
    if stop > len(opcodes):
        raise UnsupportedConstructError(
            f"product program: rule {at}'s completion range ends at {stop}, "
            f"past its {len(opcodes)}-instruction table"
        )
    for index in range(completion.start, stop):
        _verify_instruction(at, index, opcodes[index], operands[index], rows)
        opcode = opcodes[index]
        _verify_operand_lanes(
            program,
            f"rule {at}'s instruction {index} (opcode {opcode})",
            opcode,
            rows[opcode][operands[index]],
            lanes,
        )


def _verify_operand_lanes[Carry, Result](
    program: ProductProgram[Carry, Result],
    where: str,
    opcode: int,
    row: tuple[int, ...],
    lanes: Mapping[int, tuple[tuple[int, str], ...]],
) -> None:
    """Refuse an instruction naming an entry its operand table does not have.

    The row's own bounds are checked by :func:`_verify_instruction`; this
    checks where the row POINTS. An operation with no lane row indexes no
    operand table and is passed over.
    """
    for field, table in lanes.get(opcode, ()):
        _verify_lane(
            f"{where} into `{table}`",
            row[field],
            len(getattr(program.operands, table)),
        )


def _tables_for[Carry, Result](
    program: ProductProgram[Carry, Result], at: int, kind: int
) -> tuple[tuple[int, ...], tuple[int, ...], tuple[tuple[tuple[int, ...], ...], ...]]:
    """The physical tables one range kind indexes.

    The tables are separate objects, which is what makes "a rule executes its
    expression range or its fused range, never both" structural: a rule holds
    one range index, and that index resolves into exactly one table.
    """
    if kind == _EXPRESSION:
        return (
            program.expression_opcodes,
            program.expression_operands,
            program.expression_operand_rows,
        )
    if kind in _FUSED_KINDS:
        return (
            program.fused_opcodes,
            program.fused_operands,
            program.fused_operand_rows,
        )
    raise UnsupportedConstructError(
        f"product program: rule {at}'s completion range has unknown kind {kind}"
    )


def _verify_instruction(
    at: int,
    index: int,
    opcode: int,
    operand: int,
    rows: tuple[tuple[tuple[int, ...], ...], ...],
) -> None:
    """Refuse an unknown opcode or an operand past its own opcode's rows."""
    if opcode < 0 or opcode >= len(rows):
        raise UnsupportedConstructError(
            f"product program: rule {at}'s instruction {index} has unknown "
            f"opcode {opcode}"
        )
    if operand < 0 or operand >= len(rows[opcode]):
        raise UnsupportedConstructError(
            f"product program: rule {at}'s instruction {index} has operand "
            f"{operand}, past the {len(rows[opcode])} rows opcode {opcode} declares"
        )
    verify_exact_ints(rows[opcode][operand], f"opcode {opcode}'s row {operand}")
