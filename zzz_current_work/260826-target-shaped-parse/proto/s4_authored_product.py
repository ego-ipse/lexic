"""Hold an authored surface's product half to its fold half, rule by rule.

The notation authors its rules twice for the length of the migration: once as
the `ModelBody` table it runs today, once as the `RuleProduct` table the
engines will run. Authored twice rather than derived, because deriving one
from the other would keep the fold the source of truth and turn its deletion
into a rename — which is the adapter the effort forbids.

Two tables mean drift, so this is the guard. For every rule it asserts the
product captures exactly what the fold binds — same order, same slot, same
mode — and that the transform the product NAMES is the very callable the fold
body wraps, by identity. A rule renamed, re-slotted or re-pointed on one side
and not the other fails here rather than at a parse.

It also lowers the result through the real `lower_product`, so the symbol
names resolve against the surface's own registry and the program passes the
cold verifier — the same gate any engine-bound program passes.

Uncommitted evidence, not a test. Luna owns the committed suite.
"""

from __future__ import annotations

from typing import Any

from lexic.compile.module.selfgrammar import (
    MODULE_FOLD,
    MODULE_PRODUCT,
    MODULE_SYMBOLS,
)
from lexic.compile.notation.parse import (
    NOTATION_FOLD,
    NOTATION_PRODUCT,
    NOTATION_SYMBOLS,
)

SURFACES = (
    ("notation", NOTATION_FOLD, NOTATION_PRODUCT, NOTATION_SYMBOLS),
    ("selfgrammar", MODULE_FOLD, MODULE_PRODUCT, MODULE_SYMBOLS),
)
"""Both authored surfaces. The self-grammar EXTENDS the notation, so its rules
include the notation's — running both is what says the extension did not drop
or re-point one of them."""
from lexic.compile.product import LoweringOwned, lower_product
from lexic.exceptions import UnsupportedConstructError
from lexic.parsing.product import (
    CaptureMode,
    ExprProgram,
    MeaningOp,
    OperandTables,
    PassOp,
    RootOp,
    SymbolExpr,
    verify_program,
)

CAPTURE_FOR_BIND = {
    "text": CaptureMode.TEXT,
    "gtext": CaptureMode.TEXT,
    "model": CaptureMode.ONE,
    "models": CaptureMode.MANY,
    "span": CaptureMode.EXTENT,
}
"""The bind vocabulary in the ABI's terms — the same table the generated-model
authoring uses, restated here so the differential reads the fold's own words."""


def _same_value(left: object, right: object) -> bool:
    """The ambiguity gate's comparison."""
    return left == right


def _root(carry: object, verdicts: tuple[object, ...]) -> object:
    """Root finalization — the surface hands its value back."""
    del verdicts
    return carry


SURFACE_OPERANDS: OperandTables = OperandTables(
    constants=(),
    constructors=(),
    sequences=(),
    mappings=(),
    meanings=(_same_value,),
    roots=(_root,),
    routes=(),
    continuations=(),
)
"""Every table a program must name an entry of, and nothing it does not use.

The root finalizer and the meaning comparator are named by the program itself
rather than by an instruction, so a program that declares them must carry
them — which the lane bounds now enforce."""


def _check(claim: str, held: bool) -> None:
    """Refuse the witness the moment one claim stops holding."""
    if not held:
        raise AssertionError(f"s4 authored product: {claim}")


def _transform(body: Any, symbols: dict) -> Any:
    """The callable a fold body completes through, whatever it is wrapped in.

    An `IrLambda` carries its callable as `eval`; an `IrNamed` resolves its
    key. Both are how a surface spells a transform today, so both have to be
    reachable for the identity comparison to mean anything.
    """
    key = getattr(body.ctor, "key", None)
    if key is not None:
        return symbols[key]
    return body.ctor.eval


def _agree(label: str, fold: Any, product: Any, symbols: dict) -> tuple[int, int]:
    """Every rule of one surface: same captures, same transform, by identity."""
    bodies = {str(ref): body for ref, body in fold.bodies.items()}
    _check(
        f"{label}: the product covers {len(product.codes)} rules, the fold "
        f"{len(bodies)}",
        set(product.codes) == set(bodies),
    )
    alternations = 0
    captures = 0
    for name, code in product.codes.items():
        body = bodies[name]
        rule = product.rules[code]
        completion = rule.completion

        if body.kind == "alternation":
            alternations += 1
            _check(
                f"{label}/{name}: an alternation does not pass its arm through",
                isinstance(completion, PassOp),
            )
            continue

        _check(
            f"{label}/{name}: a transforming rule completes through "
            f"{type(completion).__name__}",
            isinstance(completion, ExprProgram) and len(completion.ops) == 1,
        )
        operation = completion.ops[0]
        _check(
            f"{label}/{name}: its one operation is not a symbol",
            isinstance(operation, SymbolExpr),
        )
        symbol = product.symbols[operation.symbol]
        _check(
            f"{label}/{name}: the product names {symbol!r}, whose transform is not the "
            f"one the fold body wraps",
            symbols[symbol] is _transform(body, symbols),
        )

        _check(
            f"{label}/{name}: captures {len(rule.captures)} of {len(body.fields)} "
            f"bound fields",
            len(rule.captures) == len(body.fields),
        )
        for at, field in enumerate(body.fields):
            spec = rule.captures[at]
            _check(
                f"{label}/{name}.{field.name}: capture reads slot {spec.slot}, the fold "
                f"reads item {field.item}",
                spec.slot == field.item,
            )
            _check(
                f"{label}/{name}.{field.name}: mode {spec.mode} does not match bind "
                f"{field.mode!r}",
                spec.mode == int(CAPTURE_FOR_BIND[field.mode]),
            )
            captures += 1
    print(
        f"{label}\trules={len(bodies)}\talternations={alternations}\t"
        f"captures={captures}\tsymbols={len(product.symbols)}"
    )
    return len(bodies), captures


def the_two_halves_say_the_same_thing() -> None:
    """Both surfaces, every rule."""
    for label, fold, product, symbols in SURFACES:
        _agree(label, fold, product, symbols)


def the_product_lowers_against_its_own_registry() -> None:
    """Both surfaces: the names resolve, the program verifies, no callable authored."""
    for label, _fold, product, symbols in SURFACES:
        _lowers(label, product, symbols)


def _lowers(label: str, product: Any, symbols: dict) -> None:
    """One surface through the real lowering and the cold verifier."""
    program = lower_product(
        product.rules,
        SURFACE_OPERANDS,
        owned=LoweringOwned(symbols=product.symbols),
        registry=symbols,
        root=RootOp(0),
        meaning=MeaningOp(0),
    )
    verify_program(program)
    _check(
        f"{label}: the authored symbol table holds something other than names",
        all(isinstance(name, str) for name in product.symbols),
    )
    _check(
        f"{label}: lowering resolved {len(program.operands.symbols)} of "
        f"{len(product.symbols)} symbols",
        len(program.operands.symbols) == len(product.symbols),
    )
    _check(
        f"{label}: a resolved transform is not the registry's own object",
        all(
            resolved is symbols[name]
            for name, resolved in zip(product.symbols, program.operands.symbols)
        ),
    )
    print(
        f"lowered\t{label:<12}\tsymbols={len(program.operands.symbols)}\t"
        f"expression-ops={len(program.expression_opcodes)}\t"
        f"fused-ops={len(program.fused_opcodes)}"
    )


def an_unregistered_transform_cannot_reach_a_parse() -> None:
    """The registry is a boundary: lowering against a narrower one refuses."""
    try:
        lower_product(
            NOTATION_PRODUCT.rules,
            SURFACE_OPERANDS,
            owned=LoweringOwned(symbols=NOTATION_PRODUCT.symbols),
            registry={"passthrough": NOTATION_SYMBOLS["passthrough"]},
            root=RootOp(0),
            meaning=MeaningOp(0),
        )
    except UnsupportedConstructError as refusal:
        print(f"registry\trefuses a surface transform it does not carry\t{refusal}")
        return
    raise AssertionError("s4 authored product: a narrowed registry lowered anyway")


def main() -> None:
    """Run the differential; any disagreement raises."""
    the_two_halves_say_the_same_thing()
    the_product_lowers_against_its_own_registry()
    an_unregistered_transform_cannot_reach_a_parse()
    print(
        "s4 authored product\tPASS\t"
        "both authored surfaces say one thing in two vocabularies"
    )


if __name__ == "__main__":
    main()
