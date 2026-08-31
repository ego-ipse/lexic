"""Authored product operations → the flat int-coded tables an engine runs.

The authored layer is readable and typed; the flat layer is what the paid loop
touches. Lowering is the one place that crosses between them, and it has three
obligations:

**Every authored enum becomes an exact ``int``.** An ``IntEnum`` that survived
would satisfy ``isinstance(x, int)`` and ride into a runtime table, paying an
enum lookup per completion. ``verify_exact_ints`` catches it afterwards; this
is what stops it happening.

**One instruction per rule completion.** A rule's completion is one authored
operation, so it lowers to one ``(opcode, operand)`` pair and a
:class:`~lexic.parsing.product.records.CompletionRange` of length one. The
granularity is right because a collection's begin, insert and finish belong to
*different* rules — the container's and the entry's — not to one rule's script.

**Operands index their own opcode's rows.** An authored operation's fields are
all lane indices, so the record IS its int row; rows are pooled per opcode and
deduplicated, and the operand is the row index. That keeps multi-field
operations one instruction and keeps every table typed — there is no catch-all
operand array widened to ``object``.

The type→opcode table is open with a raising default: an operation nobody has
lowered refuses by name at compile time rather than reaching an engine.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import NamedTuple

from lexic.exceptions import UnsupportedConstructError
from lexic.parsing.product import (
    AppendSequenceOp,
    ArgExpr,
    ArgsExpr,
    BeginMappingOp,
    BeginSequenceOp,
    BuildExpr,
    CompletionRange,
    CondExpr,
    ConstantExpr,
    ConstantOp,
    ContributeExpr,
    DecodeOp,
    ExprCode,
    ExprProgram,
    FinishMappingOp,
    FinishSequenceOp,
    FlatRuleProduct,
    InsertMappingOp,
    JoinExpr,
    LookupExpr,
    LoweredRoute,
    MeaningOp,
    OpCode,
    OperandTables,
    PassOp,
    PipeExpr,
    ProductProgram,
    RaiseExpr,
    RangeKind,
    RecordOp,
    RootOp,
    RouteContinuation,
    RouteTable,
    RuleBody,
    RuleProduct,
    SingletonRoute,
    TableRoute,
    UniformRoute,
    ValidateOp,
)

__all__ = ["LoweringOwned", "lower_product", "lower_routes"]


class LoweringOwned(NamedTuple):
    """The authored tables LOWERING writes into a program, never a caller.

    Both reach an engine on a hot path — ``constructors`` at every
    ``RecordOp`` completion, ``routes`` at every routed one — and both need
    something done to them first: a constructor must be checked to be a class,
    a route must be specialized by cardinality. Naming them together is what
    makes "a caller hands these in authored form and gets them back lowered"
    one rule instead of two coincidences.
    """

    constructors: tuple[type, ...] = ()
    routes: tuple[RouteTable, ...] = ()


_OPCODES: dict[type, OpCode] = {
    PassOp: OpCode.PASS,
    ConstantOp: OpCode.CONSTANT,
    DecodeOp: OpCode.DECODE,
    ValidateOp: OpCode.VALIDATE,
    BeginSequenceOp: OpCode.BEGIN_SEQUENCE,
    AppendSequenceOp: OpCode.APPEND_SEQUENCE,
    FinishSequenceOp: OpCode.FINISH_SEQUENCE,
    BeginMappingOp: OpCode.BEGIN_MAPPING,
    InsertMappingOp: OpCode.INSERT_MAPPING,
    FinishMappingOp: OpCode.FINISH_MAPPING,
    RecordOp: OpCode.RECORD,
}
"""Authored operation type → its flat opcode. Open: a new operation joins by
adding one row here, and an unregistered one refuses rather than defaulting."""

_EXPR_CODES: dict[type, ExprCode] = {
    ArgExpr: ExprCode.ARG,
    ArgsExpr: ExprCode.ARGS,
    ConstantExpr: ExprCode.CONSTANT,
    JoinExpr: ExprCode.JOIN,
    BuildExpr: ExprCode.BUILD,
    PipeExpr: ExprCode.PIPE,
    CondExpr: ExprCode.COND,
    LookupExpr: ExprCode.LOOKUP,
    RaiseExpr: ExprCode.RAISE,
    ContributeExpr: ExprCode.CONTRIBUTE,
}
"""Authored expression type → its flat code. Separate from :data:`_OPCODES`
because the two lower into physically separate tables, which is what makes a
rule structurally unable to run both."""

_OPCODE_COUNT = max(int(code) for code in OpCode) + 1
_EXPR_COUNT = max(int(code) for code in ExprCode) + 1
"""Row tables are indexed BY code, so they span the whole vocabulary."""

_STATEFUL_OPCODES = frozenset(
    (
        int(OpCode.BEGIN_SEQUENCE),
        int(OpCode.APPEND_SEQUENCE),
        int(OpCode.FINISH_SEQUENCE),
        int(OpCode.BEGIN_MAPPING),
        int(OpCode.INSERT_MAPPING),
        int(OpCode.FINISH_MAPPING),
    )
)
"""The operations that need a parse-local ``ParseState``. Whether a product is
stateful is DERIVED from the program's own instructions rather than declared
beside them: a caller could otherwise say ``False`` for a product that plainly
accumulates, and the generated-model product's no-state guarantee would rest
on a promise instead of on its instructions.

``ParseState`` holds mutable builders OR deferred verdicts, and this set names
only the builders — exact today, because no operation records a verdict yet.
**A verdict-recording operation must join this set when one lands** (the
poisoned-state / deferred-failure work), or a validate-only target would derive
``False`` and then have nowhere to put the verdict it defers."""


class _Pool:
    """The per-opcode row tables being filled, and the instruction stream."""

    __slots__ = ("opcodes", "operands", "rows")

    def __init__(self, codes: int) -> None:
        self.opcodes: list[int] = []
        self.operands: list[int] = []
        self.rows: list[list[tuple[int, ...]]] = [[] for _ in range(codes)]

    def add(self, opcode: int, row: tuple[int, ...]) -> int:
        """Append one instruction, pooling its row, and return its index."""
        table = self.rows[opcode]
        if row in table:
            operand = table.index(row)
        else:
            operand = len(table)
            table.append(row)
        at = len(self.opcodes)
        self.opcodes.append(opcode)
        self.operands.append(operand)
        return at

    def frozen(self) -> tuple[tuple[tuple[int, ...], ...], ...]:
        """The row tables, immutable and indexed by opcode."""
        return tuple(tuple(table) for table in self.rows)


def _coded(
    operation: object, table: dict[type, ExprCode] | dict[type, OpCode], what: str
) -> tuple[int, tuple[int, ...]]:
    """One authored operation as its code and its exact-int row.

    :param operation: The authored record.
    :param table: The type→code table it must appear in.
    :param what: Which layer is lowering, for the message.
    :returns: ``(code, row)`` — the row is the record's own fields, each
        converted to a plain ``int`` so no enum reaches a runtime table.
    :raises UnsupportedConstructError: On an operation with no lowering.
    """
    code = table.get(type(operation))
    if code is None:
        raise UnsupportedConstructError(
            f"product lowering: {type(operation).__name__} has no {what} code; "
            "an operation reaches an engine only by being lowered"
        )
    return int(code), tuple(int(field) for field in operation)  # type: ignore[union-attr]


def _constructors(entries: Sequence[object]) -> tuple[Callable[..., object], ...]:
    """Validate the constructor table lowering is the sole writer of.

    ``RecordOp`` reaches this table at frequent completions, so it may hold
    only BINDING-OWNED constructor symbols — the immutable class objects a
    declaration named. A lambda, closure, bound method or factory here would
    be an arbitrary target callable on the hot path, which the ABI does not
    admit.

    :param entries: The declared constructor symbols.
    :returns: The validated table.
    :raises UnsupportedConstructError: On an entry that is not a class.
    """
    for at, entry in enumerate(entries):
        if not isinstance(entry, type):
            raise UnsupportedConstructError(
                f"product lowering: constructor {at} is "
                f"{type(entry).__name__}, not a class; the constructor table "
                "holds only binding-owned constructor symbols"
            )
    return tuple(entries)  # type: ignore[arg-type]


def lower_routes(
    tables: Sequence[RouteTable],
    continuations: Sequence[RouteContinuation] = (),
) -> tuple[LoweredRoute, ...]:
    """Specialize each authored route table by its ACTUAL cardinality.

    No known keys is a uniform dynamic mapping and bypasses classification
    entirely; one known key is a single equality test; two or more become one
    dictionary probe. The authored tuple of pairs is never scanned again — a
    tuple scan measured 121.9–907.8 ns against 28.9–33.5 ns for a dictionary
    over 2–64 routes, so no scan may reach a runtime path.

    Each table is paired with the continuation that consumes it, so a lowered
    route carries the dense destinations too: classifying a key and entering
    its contextual clone are two halves of ONE decision at a producer's
    completion, and splitting them across two objects would put a second
    lookup between them.

    :param tables: The authored cold route tables.
    :param continuations: One per table, in the same order. Omitted only when
        the caller wants classification alone (destinations stay empty).
    :returns: One lowered route per table, in the same order.
    :raises UnsupportedConstructError: When the continuations are present but
        do not pair one-to-one with the tables.
    """
    if continuations and len(continuations) != len(tables):
        raise UnsupportedConstructError(
            f"product lowering: {len(tables)} route tables and "
            f"{len(continuations)} continuations do not pair"
        )
    lowered: list[LoweredRoute] = []
    for at, table in enumerate(tables):
        dense = continuations[at].destinations if continuations else ()
        if not table.known:
            lowered.append(UniformRoute(table.extension, dense))
        elif len(table.known) == 1:
            key, route = table.known[0]
            lowered.append(SingletonRoute(table.extension, key, route, dense))
        else:
            lowered.append(TableRoute(table.extension, dict(table.known), dense))
    return tuple(lowered)


def _refuse_prefilled[Carry, Result](operands: OperandTables[Carry, Result]) -> None:
    """Refuse an operand record a caller filled where lowering must write.

    Two tables an engine reaches on a hot path: ``constructors`` at every
    ``RecordOp`` completion, and ``routes`` at every routed one. Both have to
    be lowering's output — a class it checked, a route it specialized — so a
    caller handing either one pre-filled is refused rather than trusted.
    """
    if operands.constructors:
        raise UnsupportedConstructError(
            "product lowering: the constructor table is written by lowering "
            "alone; pass classes as `constructors=` rather than filling the "
            "operand record"
        )
    if operands.routes:
        raise UnsupportedConstructError(
            "product lowering: the route table is written by lowering alone; "
            "pass authored RouteTables as `routes=` rather than filling the "
            "operand record"
        )


def lower_product[Carry, Result](
    rules: Sequence[RuleProduct[Carry]],
    operands: OperandTables[Carry, Result],
    *,
    owned: LoweringOwned = LoweringOwned(),
    root: RootOp,
    meaning: MeaningOp,
) -> ProductProgram[Carry, Result]:
    """Lower authored rules into one immutable, executable program.

    :param rules: One :class:`~lexic.parsing.product.records.RuleProduct` per
        contextual rule, in contextual-code order.
    :param operands: The typed operand tables the instructions index. Its
        ``constructors`` and ``routes`` fields must be empty — lowering is
        their only writer, so a caller cannot slip an arbitrary callable onto
        the hot path, or an unspecialized route table into a routed
        completion, by constructing the record itself.
    :param owned: The authored tables lowering writes — binding-owned
        constructor classes, and route tables to specialize by cardinality.
    :param root: The root finalizer operation.
    :param meaning: The ambiguity-gate comparison operation.
    :returns: The program. It is NOT verified here — call
        :func:`~lexic.parsing.product.verify.verify_program` before executing,
        so verification stays one cold gate rather than something a caller can
        skip by building a program another way.
    :raises UnsupportedConstructError: On an operation with no lowering, a
        pre-populated constructor or route table, or a constructor that is
        not a class.
    """
    _refuse_prefilled(operands)
    fused = _Pool(_OPCODE_COUNT)
    expression = _Pool(_EXPR_COUNT)
    flat: list[FlatRuleProduct] = []
    completions: list[CompletionRange] = []
    for rule in rules:
        completions.append(_lower_body(rule.completion, fused, expression))
        flat.append(
            FlatRuleProduct(
                tuple(int(capture.mode) for capture in rule.captures),
                tuple(int(capture.slot) for capture in rule.captures),
                len(completions) - 1,
            )
        )
    return ProductProgram(
        tuple(flat),
        tuple(completions),
        tuple(expression.opcodes),
        tuple(expression.operands),
        expression.frozen(),
        tuple(fused.opcodes),
        tuple(fused.operands),
        fused.frozen(),
        operands._replace(
            constructors=_constructors(owned.constructors),
            routes=lower_routes(owned.routes, operands.continuations),
        ),
        root,
        meaning,
        any(opcode in _STATEFUL_OPCODES for opcode in fused.opcodes),
    )


def _lower_body[Carry](
    body: RuleBody[Carry], fused: _Pool, expression: _Pool
) -> CompletionRange:
    """Lower one rule's body into whichever table its own type selects.

    An :class:`ExprProgram` becomes a contiguous EXPRESSION range; anything
    else is one FUSED instruction. A rule holds one body, so it lands in one
    table — there is no state in which both are populated.
    """
    if isinstance(body, ExprProgram):
        if not body.ops:
            raise UnsupportedConstructError(
                "product lowering: an expression program with no operations "
                "would compile to an empty completion range"
            )
        start = len(expression.opcodes)
        for operation in body.ops:
            code, row = _coded(operation, _EXPR_CODES, "expression")
            expression.add(code, row)
        return CompletionRange(int(RangeKind.EXPRESSION), start, len(body.ops))
    code, row = _coded(body, _OPCODES, "opcode")
    return CompletionRange(int(RangeKind.FUSED), fused.add(code, row), 1)
