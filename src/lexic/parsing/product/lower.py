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
:class:`~lexic.parsing.product.abi.records.CompletionRange` of length one. The
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

from collections.abc import Callable, Mapping, Sequence
from types import MappingProxyType
from typing import NamedTuple

from lexic.exceptions import UnsupportedConstructError
from lexic.parsing.product import (
    AppendSequenceOp,
    ArgExpr,
    ArgsExpr,
    BeginMappingOp,
    BeginSequenceOp,
    BoundSymbol,
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
    RecordConstructor,
    RecordOp,
    RootOp,
    RouteContinuation,
    RouteTable,
    RuleBody,
    RuleProduct,
    SingletonRoute,
    SymbolConstructor,
    SymbolExpr,
    TableRoute,
    UniformRoute,
    ValidateOp,
)

__all__ = ["LoweringOwned", "bind_symbols", "lower_product", "lower_routes"]


class LoweringOwned(NamedTuple):
    """The authored tables LOWERING writes into a program, never a caller.

    Each needs something done to it before an engine may index it: a
    constructor must be checked to be a class, a route must be specialized by
    cardinality, a symbol must be resolved through its registry. Naming them
    together is what makes "a caller hands these in authored form and gets
    them back lowered" one rule instead of three coincidences.

    ``symbols`` is authored :class:`~lexic.parsing.product.SymbolConstructor`
    records — registry keys and keyword layouts, never callables, because the
    authored side of the ABI never holds one — and ``registry`` is what turns
    them into callables. The two travel together because a name is only
    meaningful against the whitelist it is resolved through: separating them is
    how a program could name a symbol with no registry to check it against.
    """

    constructors: tuple[RecordConstructor, ...] = ()
    routes: tuple[RouteTable, ...] = ()
    symbols: tuple[SymbolConstructor, ...] = ()
    registry: Mapping[str, Callable[..., object]] = MappingProxyType({})


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
    SymbolExpr: ExprCode.SYMBOL,
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
    operation: tuple[int, ...],
    table: dict[type, ExprCode] | dict[type, OpCode],
    what: str,
) -> tuple[int, tuple[int, ...]]:
    """One authored operation as its code and its exact-int row.

    Every authored operation IS its int row: each is a ``NamedTuple`` whose
    fields are indices into the typed operand tables, which is what lets the
    row be read off the record itself rather than spelled per operation.

    :param operation: The authored record — its own fields, in order.
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
    return int(code), tuple(int(field) for field in operation)


def _constructors(
    entries: Sequence[RecordConstructor],
) -> tuple[RecordConstructor, ...]:
    """Validate the constructor table lowering is the sole writer of.

    ``RecordOp`` reaches this table at frequent completions, so every entry
    must be a :class:`RecordConstructor` whose ``cls`` is a real class — the
    immutable class object a declaration named, carried with the field
    spelling its captures fill. A lambda, closure, bound method or factory in
    that slot would be an arbitrary callable on the hot path, which the ABI
    does not admit.

    :param entries: The declared constructors.
    :returns: The validated table.
    :raises UnsupportedConstructError: On an entry that is not a
        :class:`RecordConstructor`, whose ``cls`` is not a class, or whose
        ``matched_field`` disagrees with the class it names.
    """
    for at, entry in enumerate(entries):
        if not isinstance(entry, RecordConstructor):
            raise UnsupportedConstructError(
                f"product lowering: constructor {at} is "
                f"{type(entry).__name__}, not a RecordConstructor"
            )
        if not isinstance(entry.cls, type):
            raise UnsupportedConstructError(
                f"product lowering: constructor {at} names "
                f"{type(entry.cls).__name__}, not a class; the constructor "
                "table holds only binding-owned constructor symbols"
            )
        _check_matched_field(at, entry)
    return tuple(entries)


def _field_order(at: int, cls: type) -> tuple[str, ...]:
    """The declared record class's field names, in construction order.

    :raises UnsupportedConstructError: When the class cannot say how one of
        itself is built — a constructor table entry that no bake could use.
    """
    construct: Callable[[], tuple[object, Mapping[str, object], tuple[str, ...]]] | None
    construct = getattr(cls, "fast_construct", None)
    if construct is None:
        raise UnsupportedConstructError(
            f"product lowering: constructor {at} names {cls.__name__}, which "
            "does not say how one of itself is built"
        )
    return construct()[2]


def _check_matched_field(at: int, entry: RecordConstructor) -> None:
    """Cross-check the declared own-text field against the class and the record.

    The field is DECLARED rather than derived, but it is also derivable — a
    class field that no capture fills and no default covers has nothing else
    that could construct it — so the derivation is kept here as a guard. A
    record whose defaults later change makes the two disagree, and this says
    so with words instead of quietly baking a default where the matched text
    belongs.

    The derivation is only tight under the validation-skip licence, which is
    refused outright when an unfilled field has no default; an unlicensed
    entry is constructed by name through the class's own checks, so only the
    declaration itself is checked there.

    :param at: The entry's index, for the message.
    :param entry: The constructor record.
    :raises UnsupportedConstructError: When the declaration names a field the
        class does not have, one a capture already fills, or one the class's
        own defaults contradict.
    """
    if not entry.matched_field and not entry.licensed:
        return  # nothing declared and nothing baked — no class to consult
    order = _field_order(at, entry.cls)
    if entry.matched_field and entry.matched_field not in order:
        raise UnsupportedConstructError(
            f"product lowering: constructor {at} fills {entry.matched_field!r} "
            f"with its own matched text, but {entry.cls.__name__} has no such "
            f"field (it has {order})"
        )
    if entry.matched_field and entry.matched_field in entry.names:
        raise UnsupportedConstructError(
            f"product lowering: constructor {at} fills {entry.matched_field!r} "
            "with its own matched text AND with a capture; a field takes one "
            "value, from one place"
        )
    if not entry.licensed:
        return
    unfilled = tuple(
        name for name in order if name not in entry.names and name not in entry.defaults
    )
    declared = (entry.matched_field,) if entry.matched_field else ()
    if unfilled != declared:
        raise UnsupportedConstructError(
            f"product lowering: constructor {at} declares {declared} as filled "
            f"by its own matched text, but {entry.cls.__name__} leaves "
            f"{unfilled} with neither a capture nor a default"
        )


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

    Three tables lowering owns: ``constructors``, reached at every
    ``RecordOp`` completion; ``routes``, at every routed one; and ``symbols``,
    the only table that holds a resolved callable. Each has to be lowering's
    own output — a class it checked, a route it specialized, a name it looked
    up — so a caller handing one pre-filled is refused rather than trusted.
    The symbol table is the sharpest case: filling it directly is how an
    arbitrary callable would otherwise reach a completion without ever passing
    a registry.
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
    if operands.symbols:
        raise UnsupportedConstructError(
            "product lowering: the symbol table is written by lowering alone; "
            "pass authored symbol constructors as `symbols=` rather than "
            "filling the operand record with callables"
        )


def bind_symbols(
    authored: Sequence[SymbolConstructor],
    registry: Mapping[str, Callable[..., object]],
) -> tuple[BoundSymbol, ...]:
    """Resolve each authored symbol constructor through its surface's registry.

    The no-``eval`` boundary, and the only place a name becomes a callable —
    for the flat program AND for the predictive runtime's clone bake, which
    reach the same rows by the same index. A name the registry does not carry
    refuses here, at lowering, cold, rather than raising a ``KeyError``
    mid-parse or resolving through something wider than the whitelist.

    The keyword layout is checked at the same moment, because a record that
    passes registry membership and then names one keyword twice would build a
    silently wrong value: two captures would write one keyword and the later
    one would win.

    :param authored: The authored constructors, in operand order.
    :param registry: The surface's whitelist.
    :returns: The resolved rows, in the same order.
    :raises UnsupportedConstructError: On a name the registry does not carry,
        a repeated keyword, or an optional index naming no capture.
    """
    resolved: list[BoundSymbol] = []
    for at, entry in enumerate(authored):
        transform = registry.get(entry.symbol)
        if transform is None:
            raise UnsupportedConstructError(
                f"product lowering: symbol {at} names {entry.symbol!r}, which is "
                f"not in the registry (it carries {sorted(registry)}); a symbol "
                "reaches a parse only by being registered when the program is "
                "lowered"
            )
        _check_keywords(at, entry)
        resolved.append(
            BoundSymbol(transform, entry.names, entry.optional, entry.matched)
        )
    return tuple(resolved)


def _check_keywords(at: int, entry: SymbolConstructor) -> None:
    """Refuse a symbol constructor whose keyword layout cannot be applied.

    :param at: The operand row, for the message.
    :param entry: The authored constructor.
    :raises UnsupportedConstructError: On a repeated keyword or an optional
        index outside the capture range the names describe.
    """
    if len(set(entry.names)) != len(entry.names):
        raise UnsupportedConstructError(
            f"product lowering: symbol {at} ({entry.symbol!r}) fills keywords "
            f"{list(entry.names)}, which repeats one — two captures cannot write "
            "the same keyword, and the later would silently win"
        )
    outside = [index for index in entry.optional if not 0 <= index < len(entry.names)]
    if outside:
        raise UnsupportedConstructError(
            f"product lowering: symbol {at} ({entry.symbol!r}) marks captures "
            f"{outside} optional, and it fills only {len(entry.names)} keywords"
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

    :param rules: One :class:`~lexic.parsing.product.abi.records.RuleProduct` per
        contextual rule, in contextual-code order.
    :param operands: The typed operand tables the instructions index. Its
        ``constructors``, ``routes`` and ``symbols`` fields must be empty —
        lowering is their only writer, so a caller cannot slip an arbitrary
        callable onto a completion, or an unspecialized route table into a
        routed one, by constructing the record itself.
    :param owned: The authored tables lowering writes — binding-owned
        constructor classes, route tables to specialize by cardinality, and
        the registry names an authored surface's transforms are spelled as,
        with the whitelist those names resolve through.
    :param root: The root finalizer operation.
    :param meaning: The ambiguity-gate comparison operation.
    :returns: The program. It is NOT verified here — call
        :func:`~lexic.parsing.product.verify.verify_program` before executing,
        so verification stays one cold gate rather than something a caller can
        skip by building a program another way.
    :raises UnsupportedConstructError: On an operation with no lowering, a
        pre-populated constructor, route or symbol table, a constructor that
        is not a class, or a symbol absent from the registry.
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
                int(rule.n_items),
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
            symbols=bind_symbols(owned.symbols, owned.registry),
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
