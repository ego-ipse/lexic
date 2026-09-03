"""Hold each authored surface's product to the chain that will run it.

The three compile-time surfaces author their rules once, in the product
vocabulary. This lowers each through the real `lower_product`, so its symbol
names resolve against the surface's own registry and the program passes the
cold verifier — the same gate any engine-bound program passes.

The rule-by-rule differential against a second, fold-shaped table is gone
with that table. It existed to police a transitional duplication: while both
halves were authored, drift between them was silent, and the guard made it
loud. There is one table now, so there is nothing to drift against, and a
guard comparing a table to itself would say nothing.

What survives is the boundary the duplication was protecting. A transform is
named, not held: an unregistered name cannot reach a parse, and a slot may be
captured twice in two modes. Both still have their rows below.

Uncommitted evidence, not a test. Luna owns the committed suite.
"""

from __future__ import annotations

from typing import Any

from lexic.compile.module.selfgrammar import MODULE_PRODUCT, MODULE_SYMBOLS
from lexic.compile.notation.parse import NOTATION_PRODUCT, NOTATION_SYMBOLS

SURFACES = (
    ("notation", NOTATION_PRODUCT, NOTATION_SYMBOLS),
    ("selfgrammar", MODULE_PRODUCT, MODULE_SYMBOLS),
)
"""Both authored surfaces. The self-grammar EXTENDS the notation, so its rules
include the notation's — running both is what says the extension did not drop
or re-point one of them."""
from pathlib import Path

from lexic.compile import compile_from_path
from lexic.compile.output.templating import MapShape, spanify
from lexic.exceptions import UnsupportedConstructError
from lexic.parsing.product import (
    CAPTURE_FOR_BIND,
    CaptureMode,
    ExprProgram,
    LoweringOwned,
    MeaningOp,
    OperandTables,
    PassOp,
    RootOp,
    SymbolConstructor,
    SymbolExpr,
    lower_product,
    verify_program,
)


def _same_value(left: object, right: object) -> bool:
    """The ambiguity gate's comparison."""
    return left == right


def _root(carry: object, verdicts: tuple[object, ...]) -> object:
    """Root finalization — the surface hands its value back."""
    del verdicts
    return carry


GROUND_TRUTH = Path(__file__).resolve().parents[3] / "resources" / "ground_truth"

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


def the_product_lowers_against_its_own_registry() -> None:
    """Both surfaces: the names resolve, the program verifies, no callable authored."""
    for label, product, symbols in SURFACES:
        _lowers(label, product, symbols)


def _lowers(label: str, product: Any, symbols: dict) -> None:
    """One surface through the real lowering and the cold verifier."""
    program = lower_product(
        product.rules,
        SURFACE_OPERANDS,
        owned=LoweringOwned(symbols=product.symbols, registry=symbols),
        root=RootOp(0),
        meaning=MeaningOp(0),
    )
    verify_program(program)
    _check(
        f"{label}: the authored symbol table holds a callable",
        all(
            isinstance(entry, SymbolConstructor) and isinstance(entry.symbol, str)
            for entry in product.symbols
        ),
    )
    _check(
        f"{label}: lowering resolved {len(program.operands.symbols)} of "
        f"{len(product.symbols)} symbols",
        len(program.operands.symbols) == len(product.symbols),
    )
    _check(
        f"{label}: a resolved row is not its authored record's own transform",
        all(
            row.apply is symbols[entry.symbol]
            and row.names == entry.names
            and row.optional == entry.optional
            for entry, row in zip(product.symbols, program.operands.symbols)
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
            owned=LoweringOwned(
                symbols=NOTATION_PRODUCT.symbols,
                registry={"passthrough": NOTATION_SYMBOLS["passthrough"]},
            ),
            root=RootOp(0),
            meaning=MeaningOp(0),
        )
    except UnsupportedConstructError as refusal:
        print(f"registry\trefuses a surface transform it does not carry\t{refusal}")
        return
    raise AssertionError("s4 authored product: a narrowed registry lowered anyway")


def one_slot_can_be_captured_twice_in_two_modes() -> None:
    """The templating surface's shape: what an entry says AND where it said it.

    A capture is a (mode, slot) pair and nothing makes a slot exclusive, so two
    captures on one slot in different modes are well-formed. Nothing exercised
    that until templating authored its product, and slice 2's completion sites
    will meet it — so it is pinned here rather than discovered there.
    """
    compiled = compile_from_path(GROUND_TRUTH / "json.gbnf")
    pair = spanify(compiled, MapShape("object", "member", "string", "value"))
    routines = pair.span_binding.routines
    entry = next(rule for name, rule in routines.items() if name.endswith("member-tm"))

    slots = list(entry.slots)
    repeated = sorted({slot for slot in slots if slots.count(slot) > 1})
    _check(
        f"the entry clone captures {len(slots)} times over "
        f"{len(set(slots))} slots — the two-mode shape is gone",
        len(slots) == 4 and len(set(slots)) == 2 and len(repeated) == 2,
    )
    both = sorted({int(CaptureMode.TEXT), int(CaptureMode.EXTENT)})
    for slot in repeated:
        modes = sorted(
            {mode for at, mode in enumerate(entry.modes) if slots[at] == slot}
        )
        _check(f"slot {slot} is captured twice under modes {modes}", modes == both)

    # The layout above is the VERIFIED program's own, not the authored records
    # beside it — a binding cannot exist without having passed this gate, and
    # running it again here says so rather than re-lowering a second artefact.
    verify_program(pair.span_binding.program)
    print(
        f"two-mode\tmember-tm captures {len(slots)} times over "
        f"{len(set(slots))} slots — TEXT and EXTENT on each, and it verifies"
    )


def main() -> None:
    """Run every claim; any disagreement raises."""
    the_product_lowers_against_its_own_registry()
    an_unregistered_transform_cannot_reach_a_parse()
    one_slot_can_be_captured_twice_in_two_modes()
    print(
        "s4 authored product\tPASS\t"
        "every authored surface lowers and verifies through the real chain"
    )


if __name__ == "__main__":
    main()
