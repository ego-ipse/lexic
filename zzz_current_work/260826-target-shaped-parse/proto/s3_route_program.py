"""A synthetic route-bearing program, authored at the records layer.

Nothing in `src/` can declare a route until a `TargetSchema` exists (§6/§7),
so §3 proves the route chain on a program whose records are authored here —
and driven through the REAL `lower_product` / `lower_routes` / `verify_program`
path, never raw hand-built flat tables. That way §6 changes only WHO authors
the records; the lowering→verification→runtime chain it inherits is the one
proved here.

The shape under test is the NON-SIBLING one, which is the whole reason a route
carries a descendant path rather than a sibling offset:

    member ::= string tail
    tail   ::= separator value

`string` is the discriminator. Its consumer is not its sibling — it is `value`,
one level down inside `tail`. A mechanism that could only reach the next
sibling would never deliver this route.

Route coverage in §3 is SYNTHETIC-AUTHORED. Schema-compiled routes are §6's
differential against this.

Uncommitted evidence, not a test. Luna owns the committed suite.
"""

from __future__ import annotations

from lexic.compile.product import LoweringOwned, lower_product, lower_routes
from lexic.exceptions import UnsupportedConstructError
from lexic.parsing.product import (
    CaptureMode,
    CaptureSpec,
    DecodeCode,
    DecodeOp,
    MeaningOp,
    OperandTables,
    PassOp,
    RootOp,
    RouteContinuation,
    RouteTable,
    RuleProduct,
    SingletonRoute,
    TableRoute,
    UniformRoute,
    verify_program,
)

type Carry = str

# Contextual rule codes for the synthetic shape.
MEMBER, STRING, TAIL, SEPARATOR = 0, 1, 2, 3
VALUE_MODEL, VALUE_VOCAB, VALUE_ANY = 4, 5, 6

RULES: tuple[RuleProduct[Carry], ...] = (
    RuleProduct((CaptureSpec(CaptureMode.ONE, 0),), PassOp(0)),
    RuleProduct((CaptureSpec(CaptureMode.TEXT, 0),), DecodeOp(0, DecodeCode.TEXT)),
    RuleProduct((CaptureSpec(CaptureMode.ONE, 0),), PassOp(0)),
    RuleProduct((), PassOp(0)),
    RuleProduct((CaptureSpec(CaptureMode.TEXT, 0),), DecodeOp(0, DecodeCode.TEXT)),
    RuleProduct((CaptureSpec(CaptureMode.TEXT, 0),), DecodeOp(0, DecodeCode.TEXT)),
    RuleProduct((CaptureSpec(CaptureMode.SKIP, 0),), PassOp(0)),
)
"""Seven contextual rules. The last three are the routed value clones — one
per destination — which is what "deeper children are baked into the contextual
clone chain" means: the route picks a CLONE, it does not steer a generic one."""

KEYS = RouteTable((("model", 0), ("vocab", 1)), 2)
"""Two known decoded keys plus an extension — so lowering must pick the
dictionary probe, not an equality test and not a scan."""

CONTINUATION = RouteContinuation(STRING, (1, 1), (VALUE_MODEL, VALUE_VOCAB, VALUE_ANY))
"""`string` publishes; the consumer is reached by descending slot 1 (`tail`)
then slot 1 again (`value`). A one-element path would be the sibling case;
this is deliberately two."""

OPERANDS: OperandTables[Carry, Carry] = OperandTables(
    constants=(),
    constructors=(),
    sequences=(),
    mappings=(),
    meanings=(),
    roots=(lambda carry, verdicts: carry,),
    routes=(),
    continuations=(CONTINUATION,),
)


def _check(claim: str, held: bool) -> None:
    """Refuse the witness the moment one claim stops holding."""
    if not held:
        raise AssertionError(f"s3 route program: {claim}")


def the_program_lowers_and_verifies() -> None:
    """Authored records → real lowering → the cold gate accepts it."""
    program = lower_product(
        RULES,
        OPERANDS,
        owned=LoweringOwned(routes=(KEYS,)),
        root=RootOp(0),
        meaning=MeaningOp(0),
    )
    verify_program(program)

    _check("the routed clones did not survive lowering", len(program.rules) == 7)
    _check("the route table did not lower", len(program.operands.routes) == 1)
    _check(
        "two known keys did not lower to a dictionary probe",
        isinstance(program.operands.routes[0], TableRoute),
    )
    _check(
        "the continuation did not survive lowering",
        program.operands.continuations == (CONTINUATION,),
    )
    print(
        "lowered",
        f"rules={len(program.rules)}",
        f"routes={len(program.operands.routes)}",
        "verified",
        sep="\t",
    )


def the_route_reaches_a_non_sibling_consumer() -> None:
    """The descendant path is two links — the sibling mechanism cannot do this."""
    _check(
        "the continuation names a sibling, not a descendant",
        len(CONTINUATION.path) == 2,
    )
    _check("the producer is not the discriminator", CONTINUATION.producer == STRING)

    lowered = lower_routes((KEYS,), (CONTINUATION,))[0]
    _check(
        "a known key missed its destination",
        lowered.destination_of("model") == VALUE_MODEL,
    )
    _check(
        "the second known key missed", lowered.destination_of("vocab") == VALUE_VOCAB
    )
    _check(
        "an unknown key did not take the extension destination",
        lowered.destination_of("anything-else") == VALUE_ANY,
    )
    print(
        "non-sibling",
        f"path={CONTINUATION.path}",
        "model->4 vocab->5 other->6",
        sep="\t",
    )


def cardinality_decides_the_lookup_shape() -> None:
    """The same authored record shape lowers three ways by key count."""
    uniform, singleton, table = lower_routes(
        (
            RouteTable((), VALUE_ANY),
            RouteTable((("model", 0),), 1),
            KEYS,
        )
    )
    _check(
        "classification alone should leave destinations empty",
        uniform.destinations == () and table.destinations == (),
    )
    _check(
        "a keyless table did not bypass classification",
        isinstance(uniform, UniformRoute),
    )
    _check(
        "one key did not become an equality test", isinstance(singleton, SingletonRoute)
    )
    _check("three keys did not become a dict probe", isinstance(table, TableRoute))
    print("cardinality\t0 keys uniform / 1 singleton / 2+ dict", sep="\t")


def mismatched_continuations_refuse() -> None:
    """A table with no continuation to pair with is a lowering defect."""
    try:
        lower_routes((KEYS, KEYS), (CONTINUATION,))
    except UnsupportedConstructError as refusal:
        print(f"pairing\trefuses unpaired tables\t{refusal}")
        return
    raise AssertionError("s3 route program: unpaired continuations passed")


def lowering_owns_the_route_table() -> None:
    """A caller cannot put an unspecialized table where the engine reads."""
    try:
        lower_product(
            RULES,
            OPERANDS._replace(routes=(UniformRoute(0),)),
            root=RootOp(0),
            meaning=MeaningOp(0),
        )
    except UnsupportedConstructError as refusal:
        print(f"ownership\trefuses a caller-filled route table\t{refusal}")
        return
    raise AssertionError("s3 route program: a pre-filled route table passed")


def main() -> None:
    """Run every claim; any failure raises."""
    the_program_lowers_and_verifies()
    the_route_reaches_a_non_sibling_consumer()
    cardinality_decides_the_lookup_shape()
    mismatched_continuations_refuse()
    lowering_owns_the_route_table()
    print(
        "s3 route program",
        "PASS",
        "synthetic-authored routes through the real lowering chain",
        sep="\t",
    )


if __name__ == "__main__":
    main()
