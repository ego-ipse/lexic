"""Lower a tiny sequence/map target, verify it, and execute it end to end.

What this proves: authored operations lower to flat int tables that the cold
verifier accepts, no `IntEnum` survives lowering, multi-field operations stay
ONE instruction with their fields pooled in their own opcode's row table, and
the resulting program actually builds a value through `ParseState`.

What this does NOT prove, and the §3 exit still needs: execution through the
real PDA, Earley and island/delegate paths. The interpreter here is a proto
stand-in for the engine completion sites, so it demonstrates the ABI is
executable — not that either engine executes it yet.

Uncommitted evidence, not a test. Luna owns the committed suite.
"""

from __future__ import annotations

from typing import NamedTuple

from lexic.compile.product import LoweringOwned, lower_product, lower_routes
from lexic.exceptions import SemanticVerdict, UnsupportedConstructError
from lexic.parsing.product import (
    AppendSequenceOp,
    RecordConstructor,
    ArgExpr,
    ArgsExpr,
    ExprCode,
    ExprProgram,
    JoinExpr,
    RangeKind,
    RouteTable,
    SingletonRoute,
    TableRoute,
    UniformRoute,
    BeginMappingOp,
    BeginSequenceOp,
    CaptureMode,
    CaptureSpec,
    DecodeCode,
    DecodeOp,
    FinishMappingOp,
    FinishSequenceOp,
    InsertMappingOp,
    MeaningOp,
    OpCode,
    OperandTables,
    ParseState,
    PassOp,
    ProductProgram,
    RootOp,
    RouteContinuation,
    RuleProduct,
    SymbolExpr,
    verify_exact_ints,
    verify_program,
)

type Carry = str | tuple[str, ...] | tuple[tuple[str, str], ...]

# Contextual rule codes for the tiny target.
OPEN_MAP, PUT, CLOSE_MAP = 0, 1, 2
OPEN_SEQ, PUSH, CLOSE_SEQ = 3, 4, 5
DECODE = 6

RULES: tuple[RuleProduct[Carry], ...] = (
    RuleProduct((), BeginMappingOp(0, 0)),
    RuleProduct(
        (CaptureSpec(CaptureMode.TEXT, 0), CaptureSpec(CaptureMode.ONE, 0)),
        InsertMappingOp(0, 0, 0),
    ),
    RuleProduct((), FinishMappingOp(0, 0)),
    RuleProduct((), BeginSequenceOp(0)),
    RuleProduct((CaptureSpec(CaptureMode.ONE, 0),), AppendSequenceOp(0, 0)),
    RuleProduct((), FinishSequenceOp(0, 0)),
    RuleProduct((CaptureSpec(CaptureMode.TEXT, 0),), DecodeOp(0, DecodeCode.TEXT)),
)
"""Six operations plus a decode — every collection op the ABI declares, with
the container's begin/finish and the entry's insert on DIFFERENT rules."""


def _finish_mapping(entries: tuple[tuple[str, Carry], ...]) -> Carry:
    """The target's mapping finisher — one of the three admitted callables."""
    return tuple((key, value) for key, value in entries)  # type: ignore[return-value]


def _finish_sequence(values: tuple[Carry, ...]) -> Carry:
    """The target's sequence finisher."""
    return tuple(values)  # type: ignore[return-value]


def _same_value(left: Carry, right: Carry) -> bool:
    """The ambiguity gate's comparison — do two derivations mean the same?"""
    return left == right


def _root(carry: Carry, verdicts: tuple[SemanticVerdict, ...]) -> Carry:
    """Root finalization: the earliest verdict wins over a value."""
    if verdicts:
        raise UnsupportedConstructError(f"tiny target refused: {verdicts[0].words}")
    return carry


OPERANDS: OperandTables[Carry, Carry] = OperandTables(
    constants=(),
    constructors=(),
    sequences=(_finish_sequence,),
    mappings=(_finish_mapping,),
    meanings=(_same_value,),
    roots=(_root,),
    routes=(),
    continuations=(),
)


class Frame(NamedTuple):
    """One completion's captures — the lanes the flat layout addresses."""

    texts: tuple[str, ...] = ()
    ones: tuple[Carry, ...] = ()


class _Interpreter:
    """A proto stand-in for the engines' completion sites.

    Executes exactly the flat tables the engines would: read the rule's one
    completion range, dispatch on the plain-int opcode, read the operand row
    from that opcode's own table.
    """

    __slots__ = ("mapping", "program", "sequence", "state")

    def __init__(self, program: ProductProgram[Carry, Carry]) -> None:
        self.program = program
        self.state: ParseState[Carry] = ParseState()
        self.mapping = None
        self.sequence = None

    def run(self, code: int, frame: Frame) -> Carry | None:
        """Complete one contextual rule; return its value when it makes one."""
        rule = self.program.rules[code]
        completion = self.program.completions[rule.completion]
        opcode = self.program.fused_opcodes[completion.start]
        row = self.program.fused_operand_rows[opcode][
            self.program.fused_operands[completion.start]
        ]
        return self._execute(opcode, row, frame)

    def _execute(self, opcode: int, row: tuple[int, ...], frame: Frame) -> Carry | None:
        """One plain-int opcode over its own row."""
        if opcode == OpCode.BEGIN_MAPPING:
            self.mapping = self.state.begin_mapping(row[1])
            return None
        if opcode == OpCode.INSERT_MAPPING:
            assert self.mapping is not None
            self.state.insert_mapping(
                self.mapping,
                frame.texts[row[1]],
                frame.ones[row[2]],
                SemanticVerdict("duplicate-key", f"repeated {frame.texts[row[1]]!r}"),
            )
            return None
        if opcode == OpCode.FINISH_MAPPING:
            assert self.mapping is not None
            entries = self.state.finish_mapping(self.mapping)
            return self.program.operands.mappings[row[1]](entries)
        if opcode == OpCode.BEGIN_SEQUENCE:
            self.sequence = self.state.begin_sequence()
            return None
        if opcode == OpCode.APPEND_SEQUENCE:
            assert self.sequence is not None
            self.state.append_sequence(self.sequence, frame.ones[row[1]])
            return None
        if opcode == OpCode.FINISH_SEQUENCE:
            assert self.sequence is not None
            values = self.state.finish_sequence(self.sequence)
            return self.program.operands.sequences[row[1]](values)
        if opcode == OpCode.DECODE:
            return frame.texts[row[0]]
        if opcode == OpCode.PASS:
            return frame.ones[row[0]]
        raise UnsupportedConstructError(f"tiny target: unhandled opcode {opcode}")


def _check(claim: str, held: bool) -> None:
    """Refuse the witness the moment one claim stops holding."""
    if not held:
        raise AssertionError(f"s3 lowering: {claim}")


def lowering_produces_a_verifiable_program() -> ProductProgram[Carry, Carry]:
    """Lower the target and put it through the cold gate."""
    program = lower_product(RULES, OPERANDS, root=RootOp(0), meaning=MeaningOp(0))
    verify_program(program)

    verify_exact_ints(program.fused_opcodes, "the lowered opcode table")
    verify_exact_ints(program.fused_operands, "the lowered operand table")
    for rows in program.fused_operand_rows:
        for row in rows:
            verify_exact_ints(row, "a lowered operand row")
    for rule in program.rules:
        verify_exact_ints(rule.capture_modes, "a lowered capture mode")
        verify_exact_ints(rule.capture_slots, "a lowered capture slot")

    _check("a rule lowered to more than one instruction", len(program.rules) == 7)
    _check(
        "a completion range is not exactly one instruction",
        all(completion.length == 1 for completion in program.completions),
    )
    _check(
        "a collection-building product was not derived stateful",
        program.stateful,
    )
    _check(
        "the multi-field insert did not stay one instruction",
        len(program.fused_operand_rows[int(OpCode.INSERT_MAPPING)]) == 1
        and program.fused_operand_rows[int(OpCode.INSERT_MAPPING)][0] == (0, 0, 0),
    )
    print(
        "lowering",
        f"rules={len(program.rules)}",
        f"instructions={len(program.fused_opcodes)}",
        "every range length 1; no enum survived",
        sep="\t",
    )
    return program


def the_program_builds_a_value(program: ProductProgram[Carry, Carry]) -> None:
    """Execute the tiny target: a map of two entries, one holding a list."""
    run = _Interpreter(program)
    run.run(OPEN_SEQ, Frame())
    for item in ("a", "b"):
        decoded = run.run(DECODE, Frame(texts=(item,)))
        assert decoded is not None
        run.run(PUSH, Frame(ones=(decoded,)))
    listed = run.run(CLOSE_SEQ, Frame())
    assert listed is not None
    _check("the sequence did not build", listed == ("a", "b"))

    run.run(OPEN_MAP, Frame())
    name = run.run(DECODE, Frame(texts=("qwen",)))
    assert name is not None
    run.run(PUT, Frame(texts=("model",), ones=(name,)))
    run.run(PUT, Frame(texts=("tokens",), ones=(listed,)))
    built = run.run(CLOSE_MAP, Frame())
    _check(
        "the mapping did not build",
        built == (("model", "qwen"), ("tokens", ("a", "b"))),
    )
    print(f"execution\tbuilt\t{built}")


def an_unlowerable_operation_refuses() -> None:
    """An operation with no opcode refuses at compile time, by name."""

    class Invented(NamedTuple):
        """An operation nobody taught the lowering."""

        slot: int

    try:
        lower_product(
            (RuleProduct((), Invented(0)),),  # type: ignore[arg-type]
            OPERANDS,
            root=RootOp(0),
            meaning=MeaningOp(0),
        )
    except UnsupportedConstructError as refusal:
        print(f"lowering\trefuses an unlowered operation\t{refusal}")
        return
    raise AssertionError("s3 lowering: an unlowered operation did not refuse")


def the_constructor_table_admits_only_classes() -> None:
    """Lowering is the table's only writer, and it refuses a non-class.

    `RecordOp` reaches this table at frequent completions, so an arbitrary
    target callable here would be a callback on the hot path.
    """
    classes = lower_product(
        RULES,
        OPERANDS,
        owned=LoweringOwned(
            constructors=(RecordConstructor(str), RecordConstructor(tuple))
        ),
        root=RootOp(0),
        meaning=MeaningOp(0),
    )
    _check(
        "the validated classes did not reach the table",
        tuple(entry.cls for entry in classes.operands.constructors) == (str, tuple),
    )

    try:
        lower_product(
            RULES,
            OPERANDS,
            owned=LoweringOwned(constructors=(lambda value: value,)),  # type: ignore[arg-type]
            root=RootOp(0),
            meaning=MeaningOp(0),
        )
    except UnsupportedConstructError as refusal:
        print(f"constructors\trefuses a bare callable\t{refusal}")
    else:
        raise AssertionError("s3 lowering: a lambda constructor did not refuse")

    # The record shape does not launder a callable through it either: the
    # entry may be a RecordConstructor and still name something that is not
    # a class, which is the case the cls check exists for.
    try:
        lower_product(
            RULES,
            OPERANDS,
            owned=LoweringOwned(
                constructors=(RecordConstructor(lambda value: value),)  # type: ignore[arg-type]
            ),
            root=RootOp(0),
            meaning=MeaningOp(0),
        )
    except UnsupportedConstructError as refusal:
        print(f"constructors\trefuses a non-class cls\t{refusal}")
    else:
        raise AssertionError("s3 lowering: a non-class RecordConstructor passed")

    try:
        lower_product(
            RULES,
            OPERANDS._replace(constructors=(RecordConstructor(str),)),
            root=RootOp(0),
            meaning=MeaningOp(0),
        )
    except UnsupportedConstructError as refusal:
        print(f"constructors\trefuses a caller-filled table\t{refusal}")
        return
    raise AssertionError("s3 lowering: a pre-populated constructor table passed")


class Spelled(NamedTuple):
    """A declared record whose own matched text fills one field."""

    value: str
    tag: str = ""

    @classmethod
    def fast_construct(
        cls,
    ) -> tuple[object, dict[str, object], tuple[str, ...]]:
        """The construction licence, in the shape a record class answers with."""
        return cls._make, dict(cls._field_defaults), cls._fields


def _refuses(claim: str, entry: RecordConstructor) -> None:
    """Lower a one-entry constructor table and require a refusal."""
    try:
        lower_product(
            RULES,
            OPERANDS,
            owned=LoweringOwned(constructors=(entry,)),
            root=RootOp(0),
            meaning=MeaningOp(0),
        )
    except UnsupportedConstructError as refusal:
        print(f"matched\trefuses {claim}\t{refusal}")
        return
    raise AssertionError(f"s3 lowering: {claim} passed")


def the_matched_field_is_declared_and_cross_checked() -> None:
    """The own-text field is stated on the record, and lowering audits it.

    Declared rather than derived because the derivation's failure mode is
    silent: a record whose defaults changed would start baking a default where
    the matched text belongs. Lowering keeps the derivation as the guard that
    catches exactly that.
    """
    accepted = lower_product(
        RULES,
        OPERANDS,
        owned=LoweringOwned(
            constructors=(
                RecordConstructor(
                    Spelled,
                    defaults={"tag": ""},
                    matched_field="value",
                    licensed=True,
                ),
            )
        ),
        root=RootOp(0),
        meaning=MeaningOp(0),
    )
    _check(
        "the declared own-text field did not survive lowering",
        accepted.operands.constructors[0].matched_field == "value",
    )

    _refuses(
        "a field the class does not have",
        RecordConstructor(Spelled, matched_field="absent"),
    )
    _refuses(
        "a field a capture already fills",
        RecordConstructor(Spelled, names=("value",), matched_field="value"),
    )
    _refuses(
        "a licensed record leaving an undeclared field unfilled",
        RecordConstructor(Spelled, defaults={"tag": ""}, licensed=True),
    )
    _refuses(
        "a class that cannot say how it is built",
        RecordConstructor(str, matched_field="value"),
    )


def _refuses_program(claim: str, program: ProductProgram) -> None:
    """Verify a program and require a refusal with words."""
    try:
        verify_program(program)
    except UnsupportedConstructError as refusal:
        print(f"lanes\trefuses {claim}\t{refusal}")
        return
    raise AssertionError(f"s3 lowering: {claim} verified anyway")


def every_operand_lane_is_bounded() -> None:
    """An instruction may not name an operand entry that does not exist.

    The row's own bounds were always checked; where the row POINTS was not, so
    an instruction could name constructor 9 of a two-entry table and reach the
    engine. One row per lane class, because the classes are reached by
    different routes: a fused instruction, an expression instruction, the
    program-level operands, and the route/continuation pairing.
    """
    good = lower_product(RULES, OPERANDS, root=RootOp(0), meaning=MeaningOp(0))
    verify_program(good)

    # A fused instruction's lane: FINISH_MAPPING names mapping finisher 0, and
    # the table it points into is emptied underneath it.
    _refuses_program(
        "a fused instruction naming a missing finisher",
        good._replace(operands=good.operands._replace(mappings=())),
    )
    # An expression instruction's lane: the symbol table is emptied.
    symbolic = lower_product(
        SYMBOL_RULES,
        OPERANDS,
        owned=LoweringOwned(symbols=("shout",)),
        registry={"shout": _shout},
        root=RootOp(0),
        meaning=MeaningOp(0),
    )
    verify_program(symbolic)
    _refuses_program(
        "an expression instruction naming a missing symbol",
        symbolic._replace(operands=symbolic.operands._replace(symbols=())),
    )
    # The program-level lanes, which no instruction names.
    _refuses_program("a root finalizer past its table", good._replace(root=RootOp(7)))
    _refuses_program(
        "a meaning comparator past its table", good._replace(meaning=MeaningOp(7))
    )
    # The pairing lane: a continuation with no route to consume it.
    _refuses_program(
        "routes and continuations that do not pair",
        good._replace(
            operands=good.operands._replace(
                continuations=(RouteContinuation(0, (0,), (0,)),)
            )
        ),
    )


def _shout(text: str = "") -> str:
    """A stand-in authored transform — the kind a surface registers."""
    return text.upper()


SYMBOL_RULES = (RuleProduct((), ExprProgram((SymbolExpr(0),))),)
"""One rule completing through a registered transform."""


def the_symbol_operation_resolves_through_a_registry() -> None:
    """A symbol is a NAME in the program and a callable only after lowering.

    The authored side of the ABI never holds a callable: the operand indexes a
    table of registry keys, and lowering is the one place a key becomes
    something callable — through the surface's own whitelist, refusing
    anything the whitelist does not carry.
    """
    registry = {"shout": _shout}
    program = lower_product(
        SYMBOL_RULES,
        OPERANDS,
        owned=LoweringOwned(symbols=("shout",)),
        registry=registry,
        root=RootOp(0),
        meaning=MeaningOp(0),
    )
    verify_program(program)
    _check(
        "the symbol did not lower to its own expression code",
        tuple(program.expression_opcodes) == (int(ExprCode.SYMBOL),),
    )
    _check(
        "the registry's transform did not reach the cold operand table",
        program.operands.symbols == (_shout,),
    )
    _check(
        "the authored table holds something other than a name",
        all(
            isinstance(name, str) for name in LoweringOwned(symbols=("shout",)).symbols
        ),
    )

    try:
        lower_product(
            SYMBOL_RULES,
            OPERANDS,
            owned=LoweringOwned(symbols=("nowhere",)),
            registry=registry,
            root=RootOp(0),
            meaning=MeaningOp(0),
        )
    except UnsupportedConstructError as refusal:
        print(f"symbols\trefuses an unregistered name\t{refusal}")
    else:
        raise AssertionError("s3 lowering: an unregistered symbol passed")

    try:
        lower_product(
            SYMBOL_RULES,
            OPERANDS,
            owned=LoweringOwned(symbols=("shout",)),
            root=RootOp(0),
            meaning=MeaningOp(0),
        )
    except UnsupportedConstructError as refusal:
        print(f"symbols\trefuses a name with no registry\t{refusal}")
    else:
        raise AssertionError("s3 lowering: a symbol without a registry passed")

    try:
        lower_product(
            SYMBOL_RULES,
            OPERANDS._replace(symbols=(_shout,)),
            root=RootOp(0),
            meaning=MeaningOp(0),
        )
    except UnsupportedConstructError as refusal:
        print(f"symbols\trefuses a caller-filled table\t{refusal}")
        return
    raise AssertionError("s3 lowering: a caller-filled symbol table passed")


def an_expression_program_lowers_to_its_own_table() -> None:
    """The reducer-expression layer lands in the EXPRESSION table, not fused."""
    reducer_body = ExprProgram((ArgsExpr(), JoinExpr(0), ArgExpr(0)))
    rules = (RuleProduct((), reducer_body), RuleProduct((), PassOp(0)))
    program = lower_product(rules, OPERANDS, root=RootOp(0), meaning=MeaningOp(0))
    verify_program(program)

    expression, fused = program.completions
    _check(
        "the expression body did not become an EXPRESSION range",
        expression.kind == int(RangeKind.EXPRESSION) and expression.length == 3,
    )
    _check(
        "the fused body did not become a FUSED range",
        fused.kind == int(RangeKind.FUSED) and fused.length == 1,
    )
    _check(
        "the two bodies did not land in physically separate tables",
        len(program.expression_opcodes) == 3 and len(program.fused_opcodes) == 1,
    )
    _check(
        "a product with no accumulator was derived stateful",
        not program.stateful,
    )
    _check(
        "the expression codes are not the expression vocabulary",
        tuple(program.expression_opcodes)
        == (int(ExprCode.ARGS), int(ExprCode.JOIN), int(ExprCode.ARG)),
    )
    verify_exact_ints(program.expression_opcodes, "the expression opcode table")

    try:
        lower_product(
            (RuleProduct((), ExprProgram(())),),
            OPERANDS,
            root=RootOp(0),
            meaning=MeaningOp(0),
        )
    except UnsupportedConstructError as refusal:
        print(f"expression\trefuses an empty program\t{refusal}")
    else:
        raise AssertionError("s3 lowering: an empty expression program passed")
    print(
        "expression",
        f"ops={len(program.expression_opcodes)}",
        f"fused={len(program.fused_opcodes)}",
        "one body per rule, separate tables",
        sep="\t",
    )


def routes_specialize_by_cardinality() -> None:
    """Uniform bypasses, one key is an equality test, two or more is a dict."""
    uniform, singleton, table = lower_routes(
        (
            RouteTable((), 7),
            RouteTable((("model", 1),), 9),
            RouteTable((("model", 1), ("version", 2), ("added", 3)), 9),
        )
    )
    _check("a keyless table did not bypass", isinstance(uniform, UniformRoute))
    _check("a one-key table is not a singleton", isinstance(singleton, SingletonRoute))
    _check("a three-key table is not a dict probe", isinstance(table, TableRoute))

    _check("the uniform route classified a key", uniform.route_of("anything") == 7)
    _check("the singleton missed its key", singleton.route_of("model") == 1)
    _check("the singleton took an unknown key", singleton.route_of("other") == 9)
    _check("the table missed a known key", table.route_of("version") == 2)
    _check("the table took an unknown key", table.route_of("nope") == 9)

    _check(
        "the lowered table kept a scannable sequence",
        isinstance(table.lookup, dict) and len(table.lookup) == 3,
    )
    print(
        "routes",
        "uniform bypass / singleton equality / dict probe",
        "no tuple scan on any runtime path",
        sep="\t",
    )


def main() -> None:
    """Run every claim; any failure raises."""
    program = lowering_produces_a_verifiable_program()
    the_program_builds_a_value(program)
    an_unlowerable_operation_refuses()
    the_constructor_table_admits_only_classes()
    the_matched_field_is_declared_and_cross_checked()
    the_symbol_operation_resolves_through_a_registry()
    every_operand_lane_is_bounded()
    an_expression_program_lowers_to_its_own_table()
    routes_specialize_by_cardinality()
    print("s3 lowering\tPASS\tauthored -> flat -> verified -> executed")


if __name__ == "__main__":
    main()
