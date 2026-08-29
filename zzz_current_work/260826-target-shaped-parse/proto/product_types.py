"""Type-feasibility prototype for target-shaped parser products.

This file is executable evidence, not production code. It tests the public
selection surface and the internal generic boundaries without importing a
target into the parser or widening a value to an unknown top type.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping
from enum import IntEnum
from functools import partial
from pathlib import Path
from threading import Lock
from typing import NamedTuple, Protocol, assert_type, overload

import weakref

from lexic.compile import compile_ast, compile_from_path
from lexic.compile.artifact import CompiledGrammar as SourceGrammar
from lexic.exceptions import UnsupportedConstructError
from lexic.ir import IrAst, IrSelf, IrStr, IrTokenizer
from lexic.ir.reduction import Reducer
from lexic.grammars.json import JSON_GRAMMAR, JSON_REDUCER
from lexic.model import GrammarModel

AUTO = 0


class Extent(NamedTuple):
    """One parser-certified half-open source extent."""

    lo: int
    hi: int


class SequenceHandle(NamedTuple):
    """A parse-local sequence occurrence."""

    slot: int


class MappingHandle(NamedTuple):
    """A parse-local mapping occurrence."""

    slot: int


class Verdict(NamedTuple):
    """One ordered semantic refusal."""

    order: int
    message: str


class SequenceBuilder[Carry]:
    """One occurrence-owned sequence accumulator."""

    __slots__ = ("values",)

    def __init__(self) -> None:
        self.values: list[Carry] = []


class MappingBuilder[Carry]:
    """One occurrence-owned decoded-key accumulator."""

    __slots__ = ("entries", "keys")

    def __init__(self) -> None:
        self.entries: list[tuple[str, Carry]] = []
        self.keys: set[str] = set()


class ProductMark(NamedTuple):
    """Constant-size position in one speculative product transaction."""

    mutation_count: int
    sequence_count: int
    mapping_count: int
    verdict_count: int
    depth: int


SEQUENCE_APPEND = 1
MAPPING_INSERT = 2


class ParseState[Carry]:
    """Mutable builders and verdicts owned by one parse or alternative."""

    __slots__ = (
        "mapping_count",
        "mappings",
        "marks",
        "mutation_kinds",
        "mutation_slots",
        "sequence_count",
        "sequences",
        "verdicts",
    )

    def __init__(self) -> None:
        self.sequences: list[SequenceBuilder[Carry]] = []
        self.mappings: list[MappingBuilder[Carry]] = []
        self.verdicts: list[Verdict] = []
        self.mutation_kinds: list[int] = []
        self.mutation_slots: list[int] = []
        self.marks: list[ProductMark] = []
        self.sequence_count = 0
        self.mapping_count = 0

    def begin_sequence(self) -> SequenceHandle:
        """Create one sequence occurrence."""
        slot = self.sequence_count
        self.sequences.append(SequenceBuilder[Carry]())
        self.sequence_count += 1
        return SequenceHandle(slot)

    def append_sequence(self, handle: SequenceHandle, value: Carry) -> None:
        """Append to one sequence occurrence."""
        self.sequences[handle.slot].values.append(value)
        if self.marks:
            self.mutation_kinds.append(SEQUENCE_APPEND)
            self.mutation_slots.append(handle.slot)

    def finish_sequence(self, handle: SequenceHandle) -> tuple[Carry, ...]:
        """Read one completed sequence occurrence."""
        return tuple(self.sequences[handle.slot].values)

    def begin_mapping(self) -> MappingHandle:
        """Create one mapping occurrence."""
        slot = self.mapping_count
        self.mappings.append(MappingBuilder[Carry]())
        self.mapping_count += 1
        return MappingHandle(slot)

    def insert_mapping(
        self,
        handle: MappingHandle,
        key: str,
        value: Carry,
        order: int,
    ) -> None:
        """Insert or record the first duplicate-key verdict."""
        builder = self.mappings[handle.slot]
        if key in builder.keys:
            self.verdicts.append(Verdict(order, f"duplicate key {key!r}"))
            return
        builder.keys.add(key)
        builder.entries.append((key, value))
        if self.marks:
            self.mutation_kinds.append(MAPPING_INSERT)
            self.mutation_slots.append(handle.slot)

    def finish_mapping(self, handle: MappingHandle) -> tuple[tuple[str, Carry], ...]:
        """Read one completed mapping occurrence."""
        return tuple(self.mappings[handle.slot].entries)

    def mark(self) -> ProductMark:
        """Open one constant-time nested transaction."""
        mark = ProductMark(
            len(self.mutation_kinds),
            self.sequence_count,
            self.mapping_count,
            len(self.verdicts),
            len(self.marks),
        )
        self.marks.append(mark)
        return mark

    def commit(self, mark: ProductMark) -> None:
        """Release the newest mark without copying accumulated values."""
        self._require_top(mark)
        self.marks.pop()
        if not self.marks:
            self.mutation_kinds.clear()
            self.mutation_slots.clear()

    def _require_top(self, mark: ProductMark) -> None:
        """Refuse an out-of-order transaction operation."""
        if not self.marks or self.marks[-1] != mark:
            raise UnsupportedConstructError(
                "prototype transaction: marks must close newest first"
            )

    def rollback(self, mark: ProductMark) -> None:
        """Undo only mutations performed since the newest mark."""
        self._require_top(mark)
        mutations = range(len(self.mutation_kinds) - 1, mark.mutation_count - 1, -1)
        for at in mutations:
            kind = self.mutation_kinds[at]
            slot = self.mutation_slots[at]
            if kind == SEQUENCE_APPEND:
                self.sequences[slot].values.pop()
            elif kind == MAPPING_INSERT:
                key, _value = self.mappings[slot].entries.pop()
                self.mappings[slot].keys.remove(key)
            else:
                raise UnsupportedConstructError(
                    f"prototype transaction: unknown mutation {kind}"
                )
        del self.mutation_kinds[mark.mutation_count :]
        del self.mutation_slots[mark.mutation_count :]
        del self.sequences[mark.sequence_count :]
        self.sequence_count = mark.sequence_count
        del self.mappings[mark.mapping_count :]
        self.mapping_count = mark.mapping_count
        del self.verdicts[mark.verdict_count :]
        self.marks.pop()
        if not self.marks:
            self.mutation_kinds.clear()
            self.mutation_slots.clear()


class CaptureMode(IntEnum):
    """The closed per-occurrence capture vocabulary."""

    SKIP = 0
    TEXT = 1
    EXTENT = 2
    ONE = 3
    MANY = 4


class CaptureSpec(NamedTuple):
    """One capture destination in the flat frame."""

    mode: CaptureMode
    slot: int


class CaptureFrame[Carry]:
    """Separate typed arrays for one rule completion."""

    __slots__ = (
        "extents",
        "many",
        "mapping_handles",
        "one",
        "sequence_handles",
        "texts",
    )

    def __init__(self) -> None:
        self.texts: list[str] = []
        self.extents: list[Extent] = []
        self.one: list[Carry] = []
        self.many: list[list[Carry]] = []
        self.sequence_handles: list[SequenceHandle] = []
        self.mapping_handles: list[MappingHandle] = []


class PassOp(NamedTuple):
    """Pass one completed child."""

    source: int


class ConstantOp[Carry](NamedTuple):
    """Return one typed constant operand."""

    constant: Carry


class DecodeOp(NamedTuple):
    """Decode one text capture through a typed decoder table."""

    text: int
    decoder: int


class RouteOp(NamedTuple):
    """Classify one decoded discriminator to a precompiled route."""

    text: int
    routes: int


class ValidateOp(NamedTuple):
    """Validate one completed value and retain it."""

    source: int
    validator: int


class BeginSequenceOp(NamedTuple):
    """Create one sequence builder in its dedicated frame lane."""

    destination: int


class AppendSequenceOp(NamedTuple):
    """Append one semantic value to an occurrence-owned sequence."""

    builder: int
    value: int


class FinishSequenceOp(NamedTuple):
    """Finalize one sequence into a semantic value."""

    builder: int
    finisher: int


type SequenceOp = BeginSequenceOp | AppendSequenceOp | FinishSequenceOp


class BeginMappingOp(NamedTuple):
    """Create one mapping builder in its dedicated frame lane."""

    destination: int


class InsertMappingOp(NamedTuple):
    """Insert one decoded key and semantic value."""

    builder: int
    key: int
    value: int


class FinishMappingOp(NamedTuple):
    """Finalize one mapping into a semantic value."""

    builder: int
    finisher: int


type MappingOp = BeginMappingOp | InsertMappingOp | FinishMappingOp


class RecordOp(NamedTuple):
    """Build one declared record from completed children."""

    constructor: int


class MeaningOp(NamedTuple):
    """Compare two target meanings."""

    comparator: int


class RootOp(NamedTuple):
    """Finalize one root result."""

    finalizer: int


type RuleCompletion[Carry] = (
    PassOp
    | ConstantOp[Carry]
    | DecodeOp
    | ValidateOp
    | SequenceOp
    | MappingOp
    | RecordOp
)
type ProductOp[Carry, Result] = RuleCompletion[Carry] | RouteOp | MeaningOp | RootOp


class RuleProduct[Carry](NamedTuple):
    """Authored captures and completion for one rule."""

    captures: tuple[CaptureSpec, ...]
    completion: RuleCompletion[Carry]


class FlatRuleProduct(NamedTuple):
    """One int-coded rule with exactly one completion-range reference."""

    capture_modes: tuple[int, ...]
    capture_slots: tuple[int, ...]
    completion: int


EXPRESSION_RANGE = 1
FUSED_RANGE = 2
RECOVERY_RANGE = 3
DELEGATE_RANGE = 4


class CompletionRange(NamedTuple):
    """One exclusive range in the table selected by its exact-int kind."""

    kind: int
    start: int
    length: int


class RouteTable(NamedTuple):
    """Known decoded spellings and the extension route."""

    known: tuple[tuple[str, int], ...]
    extension: int


type SequenceFinisher[Carry] = Callable[[tuple[Carry, ...]], Carry]
type MappingFinisher[Carry] = Callable[[tuple[tuple[str, Carry], ...]], Carry]
type MeaningComparator[Carry] = Callable[[Carry, Carry], bool]
type RootFinalizer[Carry, Result] = Callable[[Carry, ParseState[Carry]], Result]


class OperandTables[Carry, Result](NamedTuple):
    """Typed operands admitted only at collection and cold boundaries."""

    constants: tuple[Carry, ...]
    sequences: tuple[SequenceFinisher[Carry], ...]
    mappings: tuple[MappingFinisher[Carry], ...]
    meanings: tuple[MeaningComparator[Carry], ...]
    roots: tuple[RootFinalizer[Carry, Result], ...]
    routes: tuple[RouteTable, ...]


class ProductProgram[Carry, Result](NamedTuple):
    """Immutable flat product program shared by both engines."""

    rules: tuple[FlatRuleProduct, ...]
    completions: tuple[CompletionRange, ...]
    expression_opcodes: tuple[int, ...]
    expression_operands: tuple[int, ...]
    expression_operand_limits: tuple[int, ...]
    fused_opcodes: tuple[int, ...]
    fused_operands: tuple[int, ...]
    fused_operand_limits: tuple[int, ...]
    operands: OperandTables[Carry, Result]
    root: RootOp
    meaning: MeaningOp


def verify_product_program[Carry, Result](
    program: ProductProgram[Carry, Result],
) -> None:
    """Refuse missing, mixed, or out-of-bounds completion programs."""
    if len(program.expression_opcodes) != len(program.expression_operands):
        raise UnsupportedConstructError("expression opcode/operand mismatch")
    if len(program.fused_opcodes) != len(program.fused_operands):
        raise UnsupportedConstructError("fused opcode/operand mismatch")
    for rule in program.rules:
        if rule.completion < 0 or rule.completion >= len(program.completions):
            raise UnsupportedConstructError("rule has no completion range")
        completion = program.completions[rule.completion]
        if completion.length <= 0:
            raise UnsupportedConstructError("completion range is empty")
        if completion.kind == EXPRESSION_RANGE:
            opcodes = program.expression_opcodes
            operands = program.expression_operands
            limits = program.expression_operand_limits
        elif completion.kind in (
            FUSED_RANGE,
            RECOVERY_RANGE,
            DELEGATE_RANGE,
        ):
            opcodes = program.fused_opcodes
            operands = program.fused_operands
            limits = program.fused_operand_limits
        else:
            raise UnsupportedConstructError("unknown completion range kind")
        if completion.start < 0:
            raise UnsupportedConstructError("completion range starts below zero")
        stop = completion.start + completion.length
        if stop > len(opcodes):
            raise UnsupportedConstructError("completion range exceeds its table")
        for index in range(completion.start, stop):
            opcode = opcodes[index]
            operand = operands[index]
            if opcode < 0 or opcode >= len(limits):
                raise UnsupportedConstructError("completion opcode is unknown")
            if operand < 0 or operand >= limits[opcode]:
                raise UnsupportedConstructError(
                    "completion operand exceeds its typed table"
                )


class PdaFrame[Carry]:
    """One predictive frame carrying typed captures and a transaction mark."""

    __slots__ = ("captures", "mark")

    def __init__(self, state: ParseState[Carry]) -> None:
        self.captures = CaptureFrame[Carry]()
        self.mark = state.mark()


class EarleyMeaning[Carry](NamedTuple):
    """One freshly folded alternative's finished value and verdicts."""

    carry: Carry
    verdicts: tuple[Verdict, ...]


class FragmentProduct[Carry](NamedTuple):
    """One worker product with explicit lower and upper boundaries."""

    lower_entry: int
    upper_entry: int
    lower_exit: int
    upper_exit: int
    carry: Carry
    verdicts: tuple[Verdict, ...]


def route[Carry, Result](
    program: ProductProgram[Carry, Result], table: int, key: str
) -> int:
    """Resolve one decoded key through precompiled data."""
    routes = program.operands.routes[table]
    for spelling, target in routes.known:
        if spelling == key:
            return target
    return routes.extension


def same_meaning[Carry, Result](
    program: ProductProgram[Carry, Result],
    left: Carry,
    right: Carry,
) -> bool:
    """Compare two meanings through the program's typed table."""
    return program.operands.meanings[program.meaning.comparator](left, right)


def finish_root[Carry, Result](
    program: ProductProgram[Carry, Result],
    carry: Carry,
    state: ParseState[Carry],
) -> Result:
    """Finalize once after the selected engine route succeeds."""
    return program.operands.roots[program.root.finalizer](carry, state)


def join_fragments[Carry](
    left: FragmentProduct[Carry],
    right: FragmentProduct[Carry],
    join: Callable[[Carry, Carry], Carry],
) -> FragmentProduct[Carry]:
    """Join adjacent worker products while preserving boundary states."""
    if left.lower_exit != right.lower_entry:
        raise UnsupportedConstructError("fragment: lower state mismatch")
    if left.upper_exit != right.upper_entry:
        raise UnsupportedConstructError("fragment: upper state mismatch")
    return FragmentProduct(
        left.lower_entry,
        left.upper_entry,
        right.lower_exit,
        right.upper_exit,
        join(left.carry, right.carry),
        left.verdicts + right.verdicts,
    )


class SignatureRequirement(NamedTuple):
    """Semantic events a target must find on its reducer."""

    events: frozenset[str]


class ReducerBinding:
    """Prototype attachment of a signature and default to a real reducer."""

    __slots__ = ("default", "events", "grammar", "reducer")

    def __init__(
        self,
        reducer: Reducer,
        grammar: IrAst,
        events: frozenset[str],
        default: ReductionMorphism[IrSelf],
    ) -> None:
        self.reducer = reducer
        self.grammar = grammar
        self.events = events
        self.default = default


def verify_source(grammar: SourceGrammar, reducer: ReducerBinding) -> None:
    """Refuse a signature attached to a different canonical grammar."""
    if grammar.grammar != reducer.grammar:
        raise UnsupportedConstructError(
            "product: reducer signature does not describe this grammar"
        )


class BoundProduct[Result](ABC):
    """Result-only public runner; its concrete carrier stays hidden."""

    @abstractmethod
    def run(self, text: str, cores: int) -> Result:
        """Run the already-bound product."""


type ProductExecutor[Carry, Result] = Callable[
    [ProductProgram[Carry, Result], str, int], Result
]


class TypedBoundProduct[Carry, Result](BoundProduct[Result]):
    """Concrete bound runner which retains the carrier type internally."""

    __slots__ = ("executor", "program")

    def __init__(
        self,
        program: ProductProgram[Carry, Result],
        executor: ProductExecutor[Carry, Result],
    ) -> None:
        self.program = program
        self.executor = executor

    def run(self, text: str, cores: int) -> Result:
        """Run without exposing or erasing the carrier."""
        return self.executor(self.program, text, cores)


class ReductionMorphism[Result](Protocol):
    """Immutable declaration protocol at the public result-typed seam."""

    def _bind(
        self, grammar: SourceGrammar, reducer: ReducerBinding
    ) -> BoundProduct[Result]:
        """Enter a private compiler-owned binding registry."""
        ...


class BoundEntry[Declaration, Result](NamedTuple):
    """Private registry entry bounded by its weak source artefact."""

    declaration: Declaration
    grammar: weakref.ReferenceType[SourceGrammar]
    reducer: Reducer
    bound: BoundProduct[Result]


def _release_bound[Declaration, Result](
    entries: dict[tuple[int, int, int], BoundEntry[Declaration, Result]],
    lock: Lock,
    key: tuple[int, int, int],
    _grammar: weakref.ReferenceType[SourceGrammar],
) -> None:
    """Drop one typed entry when its source artefact dies."""
    with lock:
        entries.pop(key, None)


type BindingFactory[Declaration, Result] = Callable[
    [Declaration, SourceGrammar, ReducerBinding], BoundProduct[Result]
]


class BindingRegistry[Declaration, Result]:
    """Private compiler/artifact owner of mutable binding state."""

    __slots__ = ("_build_count", "_entries", "_lock")

    def __init__(self) -> None:
        self._build_count = 0
        self._entries: dict[tuple[int, int, int], BoundEntry[Declaration, Result]] = {}
        self._lock = Lock()

    @property
    def build_count(self) -> int:
        """Expose evidence without exposing mutable entries."""
        return self._build_count

    def bind(
        self,
        declaration: Declaration,
        grammar: SourceGrammar,
        reducer: ReducerBinding,
        factory: BindingFactory[Declaration, Result],
    ) -> BoundProduct[Result]:
        """Bind once while keeping all mutation outside the declaration."""
        key = (id(declaration), id(grammar), id(reducer.reducer))
        cached = self._entries.get(key)
        if (
            cached is not None
            and cached.declaration is declaration
            and cached.grammar() is grammar
            and cached.reducer is reducer.reducer
        ):
            return cached.bound
        with self._lock:
            cached = self._entries.get(key)
            if (
                cached is not None
                and cached.declaration is declaration
                and cached.grammar() is grammar
                and cached.reducer is reducer.reducer
            ):
                return cached.bound
            bound = factory(declaration, grammar, reducer)
            self._build_count += 1
            source = weakref.ref(
                grammar,
                partial(_release_bound, self._entries, self._lock, key),
            )
            self._entries[key] = BoundEntry(declaration, source, reducer.reducer, bound)
            return bound


class ReductionRunner:
    """Prototype public overload boundary."""

    __slots__ = ("compiled",)

    def __init__(self, compiled: SourceGrammar) -> None:
        self.compiled = compiled

    @overload
    def _bound_reduction(
        self,
        reducer: ReducerBinding,
    ) -> BoundProduct[IrSelf]: ...

    @overload
    def _bound_reduction[Result](
        self,
        reducer: ReducerBinding,
        *,
        into: ReductionMorphism[Result],
    ) -> BoundProduct[Result]: ...

    def _bound_reduction[Result](
        self,
        reducer: ReducerBinding,
        *,
        into: ReductionMorphism[Result] | None = None,
    ) -> BoundProduct[IrSelf] | BoundProduct[Result]:
        """Internal seam: bind once for direct or pooled execution."""
        if into is None:
            return reducer.default._bind(self.compiled, reducer)
        return into._bind(self.compiled, reducer)

    @overload
    def reduce(
        self,
        text: str,
        reducer: ReducerBinding,
        *,
        cores: int = AUTO,
    ) -> IrSelf: ...

    @overload
    def reduce[Result](
        self,
        text: str,
        reducer: ReducerBinding,
        *,
        into: ReductionMorphism[Result],
        cores: int = AUTO,
    ) -> Result: ...

    def reduce[Result](
        self,
        text: str,
        reducer: ReducerBinding,
        *,
        into: ReductionMorphism[Result] | None = None,
        cores: int = AUTO,
    ) -> IrSelf | Result:
        """Convenience surface over the same cached bound product."""
        if into is None:
            return self._bound_reduction(reducer).run(text, cores)
        return self._bound_reduction(reducer, into=into).run(text, cores)


class Keep:
    """Beginner selection leaf: retain this semantic value."""

    __slots__ = ()


KEEP = Keep()
type SelectionSpec = Mapping[str, Keep | SelectionSpec]
type Selection = dict[tuple[str, ...], IrSelf]


class SelectionBound(BoundProduct[Selection]):
    """Prototype bound selection; production lowering builds its product."""

    __slots__ = ("paths",)

    def __init__(self, paths: tuple[tuple[str, ...], ...]) -> None:
        self.paths = paths

    def run(self, text: str, cores: int) -> Selection:
        """Demonstrate the result shape without a second parse executor."""
        del cores
        return {path: IrStr(text) for path in self.paths}


def selection_paths(
    spec: SelectionSpec, prefix: tuple[str, ...] = ()
) -> tuple[tuple[str, ...], ...]:
    """Flatten one nested decoded-key selection declaration."""
    paths: list[tuple[str, ...]] = []
    for key, value in spec.items():
        path = prefix + (key,)
        if isinstance(value, Keep):
            paths.append(path)
        else:
            paths.extend(selection_paths(value, path))
    return tuple(paths)


class SelectionMorphism(NamedTuple):
    """Fully immutable beginner declaration; no binding state is reachable."""

    paths: tuple[tuple[str, ...], ...]

    def _bind(
        self, grammar: SourceGrammar, reducer: ReducerBinding
    ) -> BoundProduct[Selection]:
        """Enter the private selection binding owner."""
        return _SELECTION_BINDINGS.bind(self, grammar, reducer, _build_selection)


def _build_selection(
    declaration: SelectionMorphism,
    grammar: SourceGrammar,
    reducer: ReducerBinding,
) -> BoundProduct[Selection]:
    """Require mapping events, then build one selection product."""
    verify_source(grammar, reducer)
    if "mapping" not in reducer.events:
        raise UnsupportedConstructError(
            "selection: reducer has no mapping semantic event"
        )
    return SelectionBound(declaration.paths)


_SELECTION_BINDINGS = BindingRegistry[SelectionMorphism, Selection]()


def select(spec: SelectionSpec) -> ReductionMorphism[Selection]:
    """Declare a simple semantic selection through the real target channel."""
    return SelectionMorphism(selection_paths(spec))


class JsonArray(NamedTuple):
    """Prototype recursive sequence value."""

    values: tuple[JsonValue, ...]


class JsonMap(NamedTuple):
    """Prototype recursive mapping value."""

    entries: tuple[tuple[str, JsonValue], ...]


type JsonValue = None | bool | int | float | str | JsonArray | JsonMap


def json_array(values: tuple[JsonValue, ...]) -> JsonValue:
    """Finish one recursive JSON sequence."""
    out: list[JsonValue] = []
    out.extend(values)
    return JsonArray(tuple(out))


def json_map(
    entries: tuple[tuple[str, JsonValue], ...],
) -> JsonValue:
    """Finish one recursive JSON mapping."""
    out: list[tuple[str, JsonValue]] = []
    out.extend(entries)
    return JsonMap(tuple(out))


def join_json(left: JsonValue, right: JsonValue) -> JsonValue:
    """Associatively join two sequence fragments."""
    if not isinstance(left, JsonArray) or not isinstance(right, JsonArray):
        raise UnsupportedConstructError("prototype: fragment is not a sequence")
    return JsonArray(left.values + right.values)


def decode_ir(text: str) -> IrSelf:
    """Execute the engine-owned IR-string scalar decoder."""
    return IrStr(text)


def decode_text(text: str) -> str:
    """Execute the engine-owned text scalar decoder."""
    return text


def same_ir(left: IrSelf, right: IrSelf) -> bool:
    """Prototype meaning law."""
    return type(left) is type(right) and left == right


def root_ir(carry: IrSelf, state: ParseState[IrSelf]) -> IrSelf:
    """Prototype root finalizer."""
    if state.verdicts:
        raise UnsupportedConstructError(state.verdicts[0].message)
    return carry


def ir_program(
    grammar: SourceGrammar, reducer: ReducerBinding
) -> ProductProgram[IrSelf, IrSelf]:
    """Build one typed default-IR program."""
    del grammar, reducer
    operands = OperandTables[IrSelf, IrSelf](
        (),
        (),
        (),
        (same_ir,),
        (root_ir,),
        (RouteTable((("known", 1),), 2),),
    )
    program = ProductProgram(
        (
            FlatRuleProduct(
                (int(CaptureMode.TEXT),),
                (0,),
                0,
            ),
        ),
        (CompletionRange(FUSED_RANGE, 0, 1),),
        (),
        (),
        (),
        (int(DecodeOpCode.DECODE),),
        (DECODE_IR_STRING,),
        (0, CLOSED_DECODER_COUNT),
        operands,
        RootOp(0),
        MeaningOp(0),
    )
    verify_product_program(program)
    return program


class DecodeOpCode(IntEnum):
    """Prototype flat completion opcode."""

    DECODE = 1


DECODE_IR_STRING = 0
DECODE_TEXT = 1
CLOSED_DECODER_COUNT = 2
"""Engine-owned scalar decoder ids; no callable lives in an operand table."""


def execute_ir(
    program: ProductProgram[IrSelf, IrSelf], text: str, cores: int
) -> IrSelf:
    """Exercise a typed program through the public bound runner."""
    del cores
    state = ParseState[IrSelf]()
    decoder = program.fused_operands[0]
    if decoder != DECODE_IR_STRING:
        raise UnsupportedConstructError("prototype: wrong closed IR decoder")
    carry = decode_ir(text)
    return finish_root(program, carry, state)


class DefaultIrMorphism(NamedTuple):
    """Immutable default declaration with no cache or compiler callback."""

    requirement: SignatureRequirement

    def _bind(
        self, grammar: SourceGrammar, reducer: ReducerBinding
    ) -> BoundProduct[IrSelf]:
        """Enter the private default-product binding owner."""
        return _IR_BINDINGS.bind(self, grammar, reducer, _build_ir)


def _build_ir(
    declaration: DefaultIrMorphism,
    grammar: SourceGrammar,
    reducer: ReducerBinding,
) -> BoundProduct[IrSelf]:
    """Verify immutable declaration data and build the typed runner."""
    verify_source(grammar, reducer)
    missing = declaration.requirement.events - reducer.events
    if missing:
        names = ", ".join(sorted(missing))
        raise UnsupportedConstructError(
            f"product: reducer lacks semantic events {names}"
        )
    return TypedBoundProduct(ir_program(grammar, reducer), execute_ir)


_IR_BINDINGS = BindingRegistry[DefaultIrMorphism, IrSelf]()
DEFAULT_IR = DefaultIrMorphism(SignatureRequirement(frozenset()))


def same_tokenizer(left: str, right: str) -> bool:
    """Compare the prototype tokenizer's typed text meanings."""
    return left == right


def tokenizer_root(carry: str, state: ParseState[str]) -> IrTokenizer:
    """Build the real final class once at the cold root boundary."""
    if state.verdicts:
        raise UnsupportedConstructError(state.verdicts[0].message)
    return IrTokenizer.from_merges(
        carry,
        {"a": 0, "b": 1, "ab": 2},
        (("a", "b"),),
    )


def tokenizer_program(
    grammar: SourceGrammar, reducer: ReducerBinding
) -> ProductProgram[str, IrTokenizer]:
    """Build one advanced typed program."""
    del grammar, reducer
    operands = OperandTables[str, IrTokenizer](
        (),
        (),
        (),
        (same_tokenizer,),
        (tokenizer_root,),
        (),
    )
    program = ProductProgram(
        (
            FlatRuleProduct(
                (int(CaptureMode.TEXT),),
                (0,),
                0,
            ),
        ),
        (CompletionRange(FUSED_RANGE, 0, 1),),
        (),
        (),
        (),
        (int(DecodeOpCode.DECODE),),
        (DECODE_TEXT,),
        (0, CLOSED_DECODER_COUNT),
        operands,
        RootOp(0),
        MeaningOp(0),
    )
    verify_product_program(program)
    return program


def execute_tokenizer(
    program: ProductProgram[str, IrTokenizer], text: str, cores: int
) -> IrTokenizer:
    """Exercise an advanced typed program."""
    del cores
    state = ParseState[str]()
    decoder = program.fused_operands[0]
    if decoder != DECODE_TEXT:
        raise UnsupportedConstructError("prototype: wrong closed text decoder")
    carry = decode_text(text)
    return finish_root(program, carry, state)


class TokenizerMorphism(NamedTuple):
    """Immutable advanced declaration with no mutable binding state."""

    requirement: SignatureRequirement

    def _bind(
        self, grammar: SourceGrammar, reducer: ReducerBinding
    ) -> BoundProduct[IrTokenizer]:
        """Enter the private tokenizer binding owner."""
        return _TOKENIZER_BINDINGS.bind(self, grammar, reducer, _build_tokenizer)


def _build_tokenizer(
    declaration: TokenizerMorphism,
    grammar: SourceGrammar,
    reducer: ReducerBinding,
) -> BoundProduct[IrTokenizer]:
    """Verify immutable declaration data and build the typed runner."""
    verify_source(grammar, reducer)
    missing = declaration.requirement.events - reducer.events
    if missing:
        names = ", ".join(sorted(missing))
        raise UnsupportedConstructError(
            f"product: reducer lacks semantic events {names}"
        )
    return TypedBoundProduct(tokenizer_program(grammar, reducer), execute_tokenizer)


_TOKENIZER_BINDINGS = BindingRegistry[TokenizerMorphism, IrTokenizer]()
TOKENIZER = TokenizerMorphism(SignatureRequirement(frozenset({"mapping"})))


def prove_transactions() -> None:
    """Exercise rollback, fresh-state isolation, and fragment joining."""
    state = ParseState[JsonValue]()
    sequence = state.begin_sequence()
    state.append_sequence(sequence, 1)
    mark = state.mark()
    state.append_sequence(sequence, 2)
    mapping = state.begin_mapping()
    state.insert_mapping(mapping, "a", 1, 0)
    state.insert_mapping(mapping, "a", 2, 1)
    assert state.verdicts
    state.rollback(mark)
    assert json_array(state.finish_sequence(sequence)) == JsonArray((1,))
    assert not state.mappings
    assert not state.verdicts

    mapping = state.begin_mapping()
    state.insert_mapping(mapping, "stable", 1, 0)
    duplicate_mark = state.mark()
    state.insert_mapping(mapping, "stable", 2, 1)
    state.insert_mapping(mapping, "discarded", 3, 2)
    state.rollback(duplicate_mark)
    assert state.finish_mapping(mapping) == (("stable", 1),)
    assert not state.verdicts

    inner = state.begin_sequence()
    state.append_sequence(inner, "nested")
    nested = json_array(state.finish_sequence(inner))
    state.append_sequence(sequence, nested)
    assert json_array(state.finish_sequence(sequence)) == JsonArray(
        (1, JsonArray(("nested",)))
    )

    alternative = ParseState[JsonValue]()
    alternative_sequence = alternative.begin_sequence()
    alternative.append_sequence(alternative_sequence, 1)
    alternative.append_sequence(alternative_sequence, nested)
    alternative.append_sequence(alternative_sequence, 3)
    assert json_array(state.finish_sequence(sequence)) == JsonArray(
        (1, JsonArray(("nested",)))
    )
    assert json_array(alternative.finish_sequence(alternative_sequence)) == JsonArray(
        (1, JsonArray(("nested",)), 3)
    )

    outer = state.mark()
    state.append_sequence(sequence, 4)
    inner_mark = state.mark()
    state.append_sequence(sequence, 5)
    state.commit(inner_mark)
    state.rollback(outer)
    assert json_array(state.finish_sequence(sequence)) == JsonArray(
        (1, JsonArray(("nested",)))
    )

    committed = state.mark()
    state.append_sequence(sequence, 6)
    state.commit(committed)
    assert not state.mutation_kinds
    assert not state.mutation_slots
    assert json_array(state.finish_sequence(sequence)) == JsonArray(
        (1, JsonArray(("nested",)), 6)
    )

    island = ParseState[JsonValue]()
    island_mapping = island.begin_mapping()
    island.insert_mapping(island_mapping, "island", 4, 3)
    assert state.finish_mapping(mapping) == (("stable", 1),)
    assert island.finish_mapping(island_mapping) == (("island", 4),)

    left: FragmentProduct[JsonValue] = FragmentProduct(0, 0, 1, 1, JsonArray((1,)), ())
    right: FragmentProduct[JsonValue] = FragmentProduct(1, 1, 2, 2, JsonArray((2,)), ())
    joined = join_fragments(left, right, join_json)
    assert joined.carry == JsonArray((1, 2))

    refused_left: FragmentProduct[JsonValue] = FragmentProduct(
        0, 0, 1, 1, JsonArray((1,)), (Verdict(2, "later"),)
    )
    refused_right: FragmentProduct[JsonValue] = FragmentProduct(
        1, 1, 2, 2, JsonArray((2,)), (Verdict(1, "earlier"),)
    )
    refused = join_fragments(refused_left, refused_right, join_json)
    assert tuple(verdict.order for verdict in refused.verdicts) == (2, 1)


def prove_public_surface() -> None:
    """Exercise default, beginner, and advanced result inference."""
    compiled = ReductionRunner(compile_ast(JSON_GRAMMAR))
    reducer = ReducerBinding(
        JSON_REDUCER,
        JSON_GRAMMAR,
        frozenset({"mapping"}),
        DEFAULT_IR,
    )

    default = compiled.reduce("value", reducer)
    assert_type(default, IrSelf)
    assert default == IrStr("value")

    fields = select(
        {
            "version": KEEP,
            "model": {"type": KEEP},
        }
    )
    selected = compiled.reduce("value", reducer, into=fields)
    assert_type(selected, dict[tuple[str, ...], IrSelf])
    assert set(selected) == {("version",), ("model", "type")}

    bound = compiled._bound_reduction(reducer, into=fields)
    assert_type(bound, BoundProduct[dict[tuple[str, ...], IrSelf]])
    assert bound is compiled._bound_reduction(reducer, into=fields)
    assert bound.run("other", AUTO)[("version",)] == IrStr("other")

    tokenizer = compiled.reduce("value", reducer, into=TOKENIZER)
    assert_type(tokenizer, IrTokenizer)
    assert tokenizer.name == IrStr("value")
    assert tokenizer.encode[IrStr("ab")] == 2


def prove_real_formulations() -> None:
    """Bind one real reducer contract to every bundled JSON formulation."""
    root = Path(__file__).resolve().parents[3] / "resources" / "ground_truth"
    compiled = (
        compile_ast(JSON_GRAMMAR),
        compile_from_path(root / "json.gbnf"),
        compile_from_path(root / "json.abnf"),
        compile_from_path(root / "json.ebnf"),
    )
    reducer = ReducerBinding(
        JSON_REDUCER,
        JSON_GRAMMAR,
        frozenset({"mapping"}),
        DEFAULT_IR,
    )
    fields = select({"model": {"type": KEEP}})
    for grammar in compiled:
        assert grammar.grammar == JSON_GRAMMAR
        runner = ReductionRunner(grammar)
        first = runner._bound_reduction(reducer, into=fields)
        assert first is runner._bound_reduction(reducer, into=fields)

    unrelated = ReductionRunner(compile_from_path(root / "arithmetic.ebnf"))
    try:
        unrelated._bound_reduction(reducer, into=fields)
    except UnsupportedConstructError as error:
        assert "does not describe this grammar" in str(error)
    else:
        raise AssertionError("an unrelated grammar accepted the JSON signature")


def prove_decoded_routes() -> None:
    """Route escape-equivalent keys only after reducer-owned decoding."""
    compiled = compile_ast(JSON_GRAMMAR)
    plain = compiled.reduce('"model"', JSON_REDUCER, cores=1)
    escaped = compiled.reduce('"m\\u006fdel"', JSON_REDUCER, cores=1)
    assert isinstance(plain, IrStr)
    assert isinstance(escaped, IrStr)
    assert plain == escaped == IrStr("model")

    reducer = ReducerBinding(
        JSON_REDUCER,
        JSON_GRAMMAR,
        frozenset({"mapping"}),
        DEFAULT_IR,
    )
    program = ir_program(compiled, reducer)
    table = RouteTable((("model", 1),), 2)
    routed = program._replace(operands=program.operands._replace(routes=(table,)))
    assert route(routed, 0, str(plain)) == 1
    assert route(routed, 0, str(escaped)) == 1
    assert route(routed, 0, "extension-a") == 2
    assert route(routed, 0, "extension-b") == 2


def prove_generated_model_carrier() -> None:
    """Carry a real synthesized model through the generic engine records."""
    root = Path(__file__).resolve().parents[3] / "resources" / "ground_truth"
    compiled = compile_from_path(root / "arithmetic.ebnf")
    model = compiled.parse("a=1\n", cores=1)
    assert_type(model, GrammarModel)

    state = ParseState[GrammarModel]()
    sequence = state.begin_sequence()
    state.append_sequence(sequence, model)
    assert state.finish_sequence(sequence) == (model,)

    meaning = EarleyMeaning(model, ())
    fragment = FragmentProduct(0, 0, 1, 1, model, ())
    assert_type(meaning, EarleyMeaning[GrammarModel])
    assert_type(fragment, FragmentProduct[GrammarModel])
    assert meaning.carry is fragment.carry


def prove_one_bound_product() -> None:
    """Prove target execution neither binds nor executes the default product."""
    compiled = compile_ast(JSON_GRAMMAR, cache_key="prototype-one-product")
    runner = ReductionRunner(compiled)
    reducer = ReducerBinding(
        JSON_REDUCER,
        JSON_GRAMMAR,
        frozenset({"mapping"}),
        DEFAULT_IR,
    )
    default_binds = _IR_BINDINGS.build_count
    tokenizer_binds = _TOKENIZER_BINDINGS.build_count

    first = runner.reduce("first", reducer, into=TOKENIZER)
    second = runner.reduce("second", reducer, into=TOKENIZER)

    assert first.name == IrStr("first")
    assert second.name == IrStr("second")
    assert _IR_BINDINGS.build_count == default_binds
    assert _TOKENIZER_BINDINGS.build_count == tokenizer_binds + 1


def prove_completion_verifier() -> None:
    """Reject an invalid range and an operand outside its typed table."""
    compiled = compile_ast(JSON_GRAMMAR)
    reducer = ReducerBinding(
        JSON_REDUCER,
        JSON_GRAMMAR,
        frozenset({"mapping"}),
        DEFAULT_IR,
    )
    program = ir_program(compiled, reducer)
    outside = program._replace(completions=(CompletionRange(FUSED_RANGE, 1, 1),))
    try:
        verify_product_program(outside)
    except UnsupportedConstructError as error:
        assert "exceeds its table" in str(error)
    else:
        raise AssertionError("out-of-bounds completion range was accepted")

    bad_operand = program._replace(fused_operands=(CLOSED_DECODER_COUNT,))
    try:
        verify_product_program(bad_operand)
    except UnsupportedConstructError as error:
        assert "typed table" in str(error)
    else:
        raise AssertionError("out-of-bounds completion operand was accepted")


def prove_immutable_declarations() -> None:
    """Public declarations expose immutable data and no mutable binding owner."""
    fields = SelectionMorphism((("model", "type"),))
    assert fields.paths == (("model", "type"),)
    for declaration in (DEFAULT_IR, TOKENIZER, fields):
        assert not hasattr(declaration, "cache")
        assert not hasattr(declaration, "entries")
        assert not hasattr(declaration, "factory")
        assert not hasattr(declaration, "lock")
        assert not hasattr(declaration, "__dict__")
        assert isinstance(hash(declaration), int)


def main() -> None:
    """Run the executable proof."""
    prove_transactions()
    prove_public_surface()
    prove_real_formulations()
    prove_decoded_routes()
    prove_generated_model_carrier()
    prove_one_bound_product()
    prove_completion_verifier()
    prove_immutable_declarations()
    print("PASS: typed products, transactions, fragments, and public overloads")


if __name__ == "__main__":
    main()
