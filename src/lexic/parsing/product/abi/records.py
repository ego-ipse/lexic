"""Immutable authored and flat ABI records — what a product program IS.

Two layers live here, and the split is the point.

The **authored** layer is a named union of typed operation records
(:class:`PassOp` … :class:`RootOp`) plus :class:`CaptureSpec` and
:class:`RuleProduct`. It is what a compiler writes: readable, checked by the
type system, and allowed to carry :class:`~enum.IntEnum` names.

The **flat** layer is what an engine executes: :class:`FlatRuleProduct`,
:class:`CompletionRange`, and the opcode/operand tables on
:class:`ProductProgram`. Every value in it is a plain ``int`` indexing a
separate typed table. No enum instance survives lowering — ``verify.py``
audits that with ``type(value) is int``, because ``isinstance`` would admit an
``IntEnum`` and let one reach the paid loop.

Begin, append and finish are three record types rather than one discriminated
record with ignored fields: their operands and their results differ, and a
single record would state a contract none of the three keeps.

The CONSTRUCTION records live in ``construction`` and are re-exported here:
both layers name them, so a record shared by two layers belongs to neither.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from enum import IntEnum
from typing import NamedTuple

from lexic.exceptions import SemanticVerdict, UnsupportedConstructError
from lexic.parsing.product.abi.construction import (
    BoundSymbol,
    Construction,
    ConstructionTables,
    ProductValue,
    RecordConstructor,
    SymbolConstructor,
    record_construction,
    symbol_construction,
)
from lexic.parsing.product.abi.expressions import ExprProgram, SymbolExpr

__all__ = [
    "LoweredRoute",
    "OpCode",
    "RuleBody",
    "SingletonRoute",
    "TableRoute",
    "UniformRoute",
    "AppendSequenceOp",
    "BeginMappingOp",
    "BeginSequenceOp",
    "BoundSymbol",
    "CAPTURE_FOR_BIND",
    "CaptureMode",
    "CaptureSpec",
    "CompletionRange",
    "ConstantOp",
    "Construction",
    "ConstructionTables",
    "construction_of",
    "DecodeCode",
    "DecodeOp",
    "Extent",
    "FinishMappingOp",
    "FinishSequenceOp",
    "FlatRuleProduct",
    "FragmentProduct",
    "InsertMappingOp",
    "MappingFinisher",
    "MeaningComparator",
    "MeaningOp",
    "OperandTables",
    "PassOp",
    "ProductOp",
    "ProductValue",
    "ProductProgram",
    "RangeKind",
    "RecordConstructor",
    "RecordOp",
    "RootFinalizer",
    "RootOp",
    "RouteContinuation",
    "RouteOp",
    "RouteTable",
    "RuleCompletion",
    "RuleProduct",
    "SequenceFinisher",
    "SymbolConstructor",
    "ValidateOp",
]


class Extent(NamedTuple):
    """One parser-certified half-open source extent, in code units.

    A certificate, never a guess: it is the span the recognizer actually
    consumed for an occurrence. A delimiter scan does not produce one.
    """

    lo: int
    hi: int


# ── Authored vocabularies (cold; lowered to exact ints) ───────────────


class CaptureMode(IntEnum):
    """What one occurrence hands its parent — the closed capture vocabulary."""

    SKIP = 0
    TEXT = 1
    EXTENT = 2
    ONE = 3
    MANY = 4


CAPTURE_FOR_BIND: Mapping[str, CaptureMode] = {
    "text": CaptureMode.TEXT,
    "gtext": CaptureMode.TEXT,
    "model": CaptureMode.ONE,
    "models": CaptureMode.MANY,
    "span": CaptureMode.EXTENT,
}
"""The IR bind vocabulary in this ABI's terms — the one translation table.

``text`` and ``gtext`` capture the same way (a slot's consumed text) and differ
only in what an EMPTY capture means, which a rule says with its ``optional``
set rather than with a second mode. It lives beside :class:`CaptureMode`
because it is a fact about this vocabulary, and every authoring surface reads
the same one rather than restating it."""


class RangeKind(IntEnum):
    """Which physical instruction table a completion range indexes.

    A rule names exactly one. There are deliberately no parallel expression
    and fused fields on a rule: two populated fields would be a rule that can
    execute twice, and the reducer-expression program and a fused target
    program are alternatives, never a pipeline.
    """

    EXPRESSION = 1
    FUSED = 2
    RECOVERY = 3
    DELEGATE = 4


class OpCode(IntEnum):
    """The flat instruction vocabulary — one code per authored operation.

    An instruction is ``(opcode, operand)``, and ``operand`` indexes the row
    table belonging to THAT opcode. Multi-field operations therefore stay one
    instruction: ``InsertMappingOp``'s three lane indices are one row of its
    own table, not three anonymous slots in a shared operand array. Which
    keeps the promise the authored layer makes — separate typed tables, no
    catch-all widened to ``object``.
    """

    PASS = 0
    CONSTANT = 1
    DECODE = 2
    VALIDATE = 3
    BEGIN_SEQUENCE = 4
    APPEND_SEQUENCE = 5
    FINISH_SEQUENCE = 6
    BEGIN_MAPPING = 7
    INSERT_MAPPING = 8
    FINISH_MAPPING = 9
    RECORD = 10


class DecodeCode(IntEnum):
    """The engine-owned scalar decoders, selected by plain int at completion.

    Closed on purpose. A target that could supply its own decoder here would
    put a target callable in every frequently completed rule; instead a target
    declares WHICH of these its signature's sorts decode through, and the
    engine owns the code.
    """

    TEXT = 0
    INTEGER = 1
    FRACTION = 2
    TRUTH = 3
    ABSENCE = 4


# ── Authored operation records ────────────────────────────────────────


class PassOp(NamedTuple):
    """Pass one completed child through unchanged."""

    source: int


class ConstantOp[Carry](NamedTuple):
    """Produce one typed constant from the program's operand table."""

    constant: int


class DecodeOp(NamedTuple):
    """Decode one captured text through an engine-owned :class:`DecodeCode`."""

    text: int
    decoder: int


class RouteOp(NamedTuple):
    """Classify one decoded discriminator into a finite route id."""

    text: int
    routes: int


class ValidateOp(NamedTuple):
    """Run one engine-owned check on a completed value and retain it."""

    source: int
    check: int


class BeginSequenceOp(NamedTuple):
    """Open one sequence accumulator in its own frame lane."""

    destination: int


class AppendSequenceOp(NamedTuple):
    """Append one finished value to an occurrence-owned sequence."""

    builder: int
    value: int


class FinishSequenceOp(NamedTuple):
    """Close one sequence into a finished value."""

    builder: int
    finisher: int


class BeginMappingOp(NamedTuple):
    """Open one mapping accumulator in its own frame lane."""

    destination: int
    duplicates: int


class InsertMappingOp(NamedTuple):
    """Insert one decoded key and its finished value."""

    builder: int
    key: int
    value: int


class FinishMappingOp(NamedTuple):
    """Close one mapping into a finished value."""

    builder: int
    finisher: int


class RecordOp[Carry](NamedTuple):
    """Build one declared record from completed children."""

    constructor: int


class MeaningOp(NamedTuple):
    """Compare two candidate meanings of one span."""

    comparator: int


class RootOp(NamedTuple):
    """Finalize the root result."""

    finalizer: int


type RuleCompletion[Carry] = (
    PassOp
    | ConstantOp[Carry]
    | DecodeOp
    | ValidateOp
    | BeginSequenceOp
    | AppendSequenceOp
    | FinishSequenceOp
    | BeginMappingOp
    | InsertMappingOp
    | FinishMappingOp
    | RecordOp[Carry]
)
"""What one contextual rule's completion may be. Routing, meaning comparison
and root finalization are not here: they happen at a discriminator, an
ambiguity gate and the root, none of which is an ordinary rule completion."""

type ProductOp[Carry] = RuleCompletion[Carry] | RouteOp | MeaningOp | RootOp
"""Every authored operation, including the three that are not rule completions."""


type RuleBody[Carry] = RuleCompletion[Carry] | ExprProgram[Carry]
"""What one rule's completion is: a fused target operation, or the reducer's
own expression program. One field, two possibilities, never both at once."""


# ── Lowered routes (hot; no scan on any runtime path) ─────────────────


class LoweredRoute:
    """Where a decoded key goes — the route family's lowered base.

    Three shapes, chosen by actual cardinality at lowering time, because a
    tuple scan measured 121.9–907.8 ns against 28.9–33.5 ns for a dictionary
    over 2–64 routes. The authored :class:`RouteTable` stays a tuple of pairs;
    nothing scans it after lowering.

    Plain slotted classes rather than records: each shape answers ``route_of``
    with its OWN code, so a routed completion pays one call and no test of
    which shape it is holding.

    Classification and destination selection live together because they are
    one step at a producer's completion: classify the decoded key to a dense
    route id, then index the destination directly. Splitting them would put a
    second lookup between the two halves of one decision.

    :ivar extension: The route id a key this table does not name takes.
    :ivar destinations: Dense route id → the contextual code to enter.
    """

    __slots__ = ("destinations", "extension")

    def __init__(self, extension: int, destinations: tuple[int, ...] = ()) -> None:
        """Bind the catch-all route id and the dense destination table."""
        self.extension = extension
        self.destinations = destinations

    def destination_of(self, key: str) -> int:
        """The contextual code ``key`` enters, by dense index.

        :param key: The decoded discriminator.
        :returns: The destination contextual code.
        """
        return self.destinations[self.route_of(key)]

    def route_of(self, key: str) -> int:
        """The dense route id ``key`` takes.

        :param key: The decoded discriminator.
        :returns: Its route id.
        :raises UnsupportedConstructError: Always, on the base — a lowered
            route that cannot answer would otherwise fall through silently.
        """
        del key
        raise UnsupportedConstructError(
            f"{type(self).__name__} does not say where a decoded key routes"
        )


class UniformRoute(LoweredRoute):
    """Every key takes one route — a dynamic mapping classifies nothing.

    The bypass case: a vocabulary's keys are data, so there is no comparison
    to make at all.
    """

    __slots__ = ()

    def route_of(self, key: str) -> int:
        """Take the one route, whatever the key is."""
        del key
        return self.extension


class SingletonRoute(LoweredRoute):
    """One known key — one equality test, no table to build or probe."""

    __slots__ = ("key", "route")

    def __init__(
        self, extension: int, key: str, route: int, destinations: tuple[int, ...] = ()
    ) -> None:
        """Bind the one known key, its route, and the catch-all."""
        super().__init__(extension, destinations)
        self.key = key
        self.route = route

    def route_of(self, key: str) -> int:
        """Compare against the one known key."""
        return self.route if key == self.key else self.extension


class TableRoute(LoweredRoute):
    """Two or more known keys — one dictionary probe, never a scan."""

    __slots__ = ("lookup",)

    def __init__(
        self,
        extension: int,
        lookup: Mapping[str, int],
        destinations: tuple[int, ...] = (),
    ) -> None:
        """Bind the lowered dictionary and the catch-all."""
        super().__init__(extension, destinations)
        self.lookup = lookup

    def route_of(self, key: str) -> int:
        """Probe the lowered dictionary."""
        return self.lookup.get(key, self.extension)


class CaptureSpec(NamedTuple):
    """One capture destination in a rule's flat frame.

    :ivar mode: A :class:`CaptureMode`.
    :ivar slot: The index within that mode's own typed lane.
    """

    mode: int
    slot: int


class RuleProduct[Carry](NamedTuple):
    """One rule's authored captures and its single completion body.

    ``completion`` is ONE field holding either a fused target operation or the
    reducer's own :class:`ExprProgram`. Its type decides which physical table
    the rule lowers into, so "a rule executes one or the other, never both" is
    a property of the record rather than a rule about filling two fields.

    :ivar captures: What each captured occurrence hands the completion.
    :ivar completion: The fused operation or expression program it runs.
    :ivar n_items: How many items the rule's sequence arm has. NOT derivable
        from ``captures`` — an item nothing binds is not a capture — and a
        completion needs it to tell "this arm matched nothing, so the rule's
        EMPTY alternate arm matched" from a compile/runtime disagreement.
        Zero for a rule with no sequence arm to count.
    """

    captures: tuple[CaptureSpec, ...]
    completion: RuleBody[Carry]
    n_items: int = 0


def construction_of[Carry](
    product: RuleProduct[Carry], tables: ConstructionTables[Carry]
) -> Construction[Carry] | None:
    """Resolve the construction one rule completion names, if any.

    A pass-through rule constructs nothing. A symbol expression is a
    construction only when it is the completion's sole operation; more
    involved expression programs remain the later generic-product executor's
    concern.
    """
    completion = product.completion
    if isinstance(completion, RecordOp):
        return record_construction(tables.constructors[completion.constructor])
    if not isinstance(completion, ExprProgram):
        return None
    if len(completion.ops) == 1 and isinstance(completion.ops[0], SymbolExpr):
        return symbol_construction(tables.symbols[completion.ops[0].symbol])
    return None


# ── Flat records (hot; plain ints only) ───────────────────────────────


class FlatRuleProduct(NamedTuple):
    """One int-coded rule: its capture layout and ONE completion range index.

    :ivar capture_modes: One :class:`CaptureMode` value per capture, as int.
    :ivar capture_slots: The matching lane index per capture.
    :ivar completion: Index into :attr:`ProductProgram.completions`.
    :ivar n_items: The rule's sequence-arm item count, carried through from
        :attr:`RuleProduct.n_items` so a completion can recognise the empty
        alternate arm without reaching back to the authored layer.
    """

    capture_modes: tuple[int, ...]
    capture_slots: tuple[int, ...]
    completion: int
    n_items: int = 0


class CompletionRange(NamedTuple):
    """One half-open instruction range, tagged by which table it indexes.

    :ivar kind: A :class:`RangeKind` value, as int.
    :ivar start: First instruction index.
    :ivar length: How many instructions; never zero — an empty range is a
        rule that completes without completing, which ``verify.py`` refuses.
    """

    kind: int
    start: int
    length: int


class RouteTable(NamedTuple):
    """One discriminator's decoded spellings and its catch-all.

    :ivar known: Decoded key → dense route id, already escape-resolved so
        every spelling that decodes to a key reaches its one route.
    :ivar extension: The route id an unlisted key takes.
    """

    known: tuple[tuple[str, int], ...]
    extension: int


class RouteContinuation(NamedTuple):
    """Where a producer's route is consumed — a path, not a sibling position.

    The consumer need not sit beside the producer. ``path`` names the
    descendant reference chain from the producer's parent down to the
    occurrence that reads the route, so every intervening clone is specialized
    by the route and no descendant reaches back into an ancestor frame at run
    time.

    :ivar producer: The contextual code whose completion publishes the route.
    :ivar path: The descendant slot chain from the producer's parent to the
        consumer; a one-element path is the sibling case.
    :ivar destinations: Dense route id → the contextual code to enter.
    """

    producer: int
    path: tuple[int, ...]
    destinations: tuple[int, ...]


type SequenceFinisher[Carry] = Callable[[tuple[Carry, ...]], Carry]
type MappingFinisher[Carry] = Callable[[tuple[tuple[str, Carry], ...]], Carry]
type MeaningComparator[Carry] = Callable[[Carry, Carry], bool]
type RootFinalizer[Carry, Result] = Callable[
    [Carry, tuple[SemanticVerdict, ...]], Result
]


class OperandTables[Carry, Result](NamedTuple):
    """The typed operands flat instructions index into.

    Only three of these hold a TARGET-supplied callable — ``sequences``,
    ``mappings`` and ``roots``, plus ``meanings`` at an ambiguity gate — and
    none of the four runs at a frequent completion. Scalar decode, validation
    and insertion are engine-owned codes, not entries here.

    ``constructors`` is the one that needs saying out loud, because
    :class:`RecordOp` DOES run at frequent completions: it holds only
    binding-owned constructor symbols — the immutable class objects a
    declaration named, resolved once at binding — never an arbitrary target
    callable, factory, lambda or closure. Lowering is what enforces that; a
    target cannot reach this table.

    ``routes`` holds LOWERED routes, not the authored :class:`RouteTable`
    records: what an engine indexes must already be specialized, or a routed
    completion would scan a tuple of pairs. Lowering is this table's only
    writer too, for the same reason.

    ``symbols`` is the fifth callable table and the one that needs its line
    drawn precisely. The rule is, and has always been, that no target callable
    runs in the character loop, the item loop, gate selection, or any
    FREQUENTLY completed rule — the generated-model product completes through
    inert binding-owned data and reaches no table here at all. An authored
    compile-time surface is the other case: the IR-constructor notation and
    the generated-module self-grammar complete through transforms that decode
    escapes and assemble headers, they parse authored text rather than
    documents, and their completions are not frequent by any measure. Those
    are what :class:`~lexic.parsing.product.abi.expressions.SymbolExpr` serves.
    Two things keep it from becoming a general callback channel: the authored
    operand is a :class:`SymbolConstructor` carrying a registry KEY, so no
    callable appears in a program's records, and lowering resolves the key
    through the surface's own whitelist and refuses one that is not there. The
    resolved rows are :class:`BoundSymbol`\\ s rather than bare callables
    because the keywords are half the contract: applying one positionally
    would erase the absent-optional distinction its transforms depend on.
    """

    constants: tuple[Carry, ...]
    constructors: tuple[RecordConstructor, ...]
    sequences: tuple[SequenceFinisher[Carry], ...]
    mappings: tuple[MappingFinisher[Carry], ...]
    meanings: tuple[MeaningComparator[Carry], ...]
    roots: tuple[RootFinalizer[Carry, Result], ...]
    routes: tuple[LoweredRoute, ...]
    continuations: tuple[RouteContinuation, ...]
    symbols: tuple[BoundSymbol, ...] = ()


class ProductProgram[Carry, Result](NamedTuple):
    """One immutable compiled product — the common input to both engines.

    The expression and fused instruction tables are physically separate, and a
    rule's single :class:`CompletionRange` says which one it runs in. That is
    what makes "a rule cannot execute both" a structural property rather than
    a convention.

    ``*_operand_rows`` is indexed by opcode and holds that opcode's own rows
    of int fields, so an operand's bound IS the length of its opcode's table —
    there is no second "limits" tuple to keep in step with it.

    :ivar stateful: Whether execution needs a :class:`~lexic.parsing.product.
        state.ParseState`. A product with no mutable builder and no deferred
        verdict — the generated-model product among them — sets this ``False``
        and allocates none.
    """

    rules: tuple[FlatRuleProduct, ...]
    completions: tuple[CompletionRange, ...]
    expression_opcodes: tuple[int, ...]
    expression_operands: tuple[int, ...]
    expression_operand_rows: tuple[tuple[tuple[int, ...], ...], ...]
    fused_opcodes: tuple[int, ...]
    fused_operands: tuple[int, ...]
    fused_operand_rows: tuple[tuple[tuple[int, ...], ...], ...]
    operands: OperandTables[Carry, Result]
    root: RootOp
    meaning: MeaningOp
    stateful: bool = False


class FragmentProduct[Carry](NamedTuple):
    """One parallel worker's product, with the boundaries its join needs.

    Carries both layers' entry and exit states so a coordinator can certify
    that two fragments actually meet, rather than assuming adjacency.
    """

    lower_entry: int
    upper_entry: int
    lower_exit: int
    upper_exit: int
    carry: Carry
    verdicts: tuple[SemanticVerdict, ...]
