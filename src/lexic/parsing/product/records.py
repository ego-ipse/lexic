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
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from enum import IntEnum
from typing import NamedTuple

from lexic.exceptions import SemanticVerdict, UnsupportedConstructError

__all__ = [
    "ArgExpr",
    "ArgsExpr",
    "BuildExpr",
    "CondExpr",
    "ConstantExpr",
    "ContributeExpr",
    "ExprCode",
    "ExprOp",
    "ExprProgram",
    "JoinExpr",
    "LookupExpr",
    "LoweredRoute",
    "OpCode",
    "PipeExpr",
    "RaiseExpr",
    "RuleBody",
    "SingletonRoute",
    "TableRoute",
    "UniformRoute",
    "AppendSequenceOp",
    "BeginMappingOp",
    "BeginSequenceOp",
    "CaptureMode",
    "CaptureSpec",
    "CompletionRange",
    "ConstantOp",
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
    "ProductProgram",
    "RangeKind",
    "RecordOp",
    "RootFinalizer",
    "RootOp",
    "RouteContinuation",
    "RouteOp",
    "RouteTable",
    "RuleCompletion",
    "RuleProduct",
    "SequenceFinisher",
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


# ── The reducer-expression layer ──────────────────────────────────────


class ExprCode(IntEnum):
    """The typed reducer-expression vocabulary, by category.

    A fused target constructs its codomain directly; the DEFAULT product
    instead evaluates the reducer's own algebra, and this is that algebra's
    flat form. The categories are the ones a reducer body actually uses:
    access, build, compute, control, lookup, refusal, and contribution.

    A rule runs an expression range or a fused range, never both — which is
    why these codes index a table physically separate from :class:`OpCode`'s.
    """

    ARG = 0
    ARGS = 1
    CONSTANT = 2
    JOIN = 3
    BUILD = 4
    PIPE = 5
    COND = 6
    LOOKUP = 7
    RAISE = 8
    CONTRIBUTE = 9


class ArgExpr(NamedTuple):
    """Access: one slot of the argument channel."""

    slot: int


class ArgsExpr(NamedTuple):
    """Access: the whole argument channel."""

    channel: int = 0


class ConstantExpr[Carry](NamedTuple):
    """Build: one typed constant from the operand table."""

    constant: int


class JoinExpr(NamedTuple):
    """Compute: join the channel under a separator constant."""

    separator: int


class BuildExpr[Carry](NamedTuple):
    """Build: construct through a binding-owned constructor."""

    constructor: int


class PipeExpr(NamedTuple):
    """Control: feed one expression's value into the next."""

    first: int
    then: int


class CondExpr(NamedTuple):
    """Control: branch on a test expression."""

    test: int
    then_at: int
    else_at: int


class LookupExpr(NamedTuple):
    """Lookup: value-keyed dispatch through a route table."""

    subject: int
    table: int


class RaiseExpr(NamedTuple):
    """Refusal: refuse with the words a constant carries."""

    message: int


class ContributeExpr(NamedTuple):
    """Contribution: what this occurrence hands its parent's channel."""

    policy: int


type ExprOp[Carry] = (
    ArgExpr
    | ArgsExpr
    | ConstantExpr[Carry]
    | JoinExpr
    | BuildExpr[Carry]
    | PipeExpr
    | CondExpr
    | LookupExpr
    | RaiseExpr
    | ContributeExpr
)
"""One authored expression operation."""


class ExprProgram[Carry](NamedTuple):
    """One rule's reducer-expression body, as an ordered operation list.

    Distinct from a bare :data:`RuleCompletion` so a rule's single body field
    says WHICH table it lowers into by its own type — the alternative would be
    two fields on a rule, which is a rule that could execute twice.
    """

    ops: tuple[ExprOp[Carry], ...]


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
    """

    captures: tuple[CaptureSpec, ...]
    completion: RuleBody[Carry]


# ── Flat records (hot; plain ints only) ───────────────────────────────


class FlatRuleProduct(NamedTuple):
    """One int-coded rule: its capture layout and ONE completion range index.

    :ivar capture_modes: One :class:`CaptureMode` value per capture, as int.
    :ivar capture_slots: The matching lane index per capture.
    :ivar completion: Index into :attr:`ProductProgram.completions`.
    """

    capture_modes: tuple[int, ...]
    capture_slots: tuple[int, ...]
    completion: int


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
    """

    constants: tuple[Carry, ...]
    constructors: tuple[Callable[..., Carry], ...]
    sequences: tuple[SequenceFinisher[Carry], ...]
    mappings: tuple[MappingFinisher[Carry], ...]
    meanings: tuple[MeaningComparator[Carry], ...]
    roots: tuple[RootFinalizer[Carry, Result], ...]
    routes: tuple[LoweredRoute, ...]
    continuations: tuple[RouteContinuation, ...]


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
