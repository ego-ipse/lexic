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
from pathlib import Path

from lexic.compile import compile_from_path
from lexic.compile.output.templating import SPAN_SYMBOLS, MapShape, spanify
from lexic.compile.product import LoweringOwned, lower_product
from lexic.exceptions import UnsupportedConstructError
from lexic.parsing.product import (
    SymbolConstructor,
    CAPTURE_FOR_BIND,
    CaptureMode,
    ExprProgram,
    MeaningOp,
    OperandTables,
    PassOp,
    RootOp,
    SymbolExpr,
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


KEYWORD_TWINS: dict[str, str] = {"decode_int": "int"}
"""Registry keys whose product spelling differs from the fold's, and why.

A completion applies its transform BY KEYWORD; a fold body reads a positional
argument channel. The builtin `int` can only be called the second way, so the
product names the one-parameter twin instead. Same decode, two application
conventions — and the fold half, with `"int"`, goes when reducer semantics
lower. Every entry here is checked to compute what its fold spelling computes,
so the allowance is a proof rather than a waiver."""


def _same_transform(where: str, entry: Any, body: Any, symbols: dict) -> None:
    """The product's transform is the fold's, or its checked keyword twin."""
    folded = _transform(body, symbols)
    if symbols[entry.symbol] is folded:
        return
    twin = KEYWORD_TWINS.get(entry.symbol)
    _check(
        f"{where}: the product names {entry.symbol!r}, whose transform is not the "
        f"one the fold body wraps and is no declared keyword twin",
        twin is not None and symbols[twin] is folded,
    )
    _check(
        f"{where}: {entry.symbol!r} and {twin!r} decode '42' differently",
        symbols[entry.symbol](**{entry.names[0]: "42"}) == folded("42"),
    )


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
        entry = product.symbols[operation.symbol]
        _same_transform(f"{label}/{name}", entry, body, symbols)
        # The keywords are half of what an application IS: applying the same
        # transform under the wrong ones builds a silently different value.
        _check(
            f"{label}/{name}: keywords {entry.names} vs the fold's "
            f"{tuple(field.name for field in body.fields)}",
            entry.names == tuple(field.name for field in body.fields),
        )
        _check(
            f"{label}/{name}: arm width {rule.n_items} vs the fold's {body.n_items}",
            rule.n_items == body.n_items,
        )
        # Absence is declared, and only a gtext bind over an item that can
        # match nothing declares it.
        expected = tuple(
            at
            for at, field in enumerate(body.fields)
            if field.mode == "gtext" and field.lo == 0
        )
        _check(
            f"{label}/{name}: optional {entry.optional} vs the fold's {expected}",
            entry.optional == expected,
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
    rules = pair.span_binding.rules
    entry = next(rule for name, rule in rules.items() if name.endswith("member-tm"))

    slots = [spec.slot for spec in entry.captures]
    repeated = sorted({slot for slot in slots if slots.count(slot) > 1})
    _check(
        f"the entry clone captures {len(entry.captures)} times over "
        f"{len(set(slots))} slots — the two-mode shape is gone",
        len(entry.captures) == 4 and len(set(slots)) == 2 and len(repeated) == 2,
    )
    both = sorted({int(CaptureMode.TEXT), int(CaptureMode.EXTENT)})
    for slot in repeated:
        modes = sorted({spec.mode for spec in entry.captures if spec.slot == slot})
        _check(f"slot {slot} is captured twice under modes {modes}", modes == both)

    program = lower_product(
        tuple(rules.values()),
        SURFACE_OPERANDS,
        owned=LoweringOwned(
            symbols=_authored_again(pair.span_binding, SPAN_SYMBOLS),
            registry=SPAN_SYMBOLS,
        ),
        root=RootOp(0),
        meaning=MeaningOp(0),
    )
    verify_program(program)
    print(
        f"two-mode\tmember-tm captures {len(entry.captures)} times over "
        f"{len(set(slots))} slots — TEXT and EXTENT on each, and it verifies"
    )


def _authored_again(
    binding: Any, registry: dict[str, Any]
) -> tuple[SymbolConstructor, ...]:
    """A binding's resolved symbols back in authored form, for re-lowering.

    A binding keeps the RESOLVED rows; lowering takes the authored ones. The
    witness re-lowers a surface it already bound, so it names each callable
    again through the same registry — which also checks the resolution went
    where it said it did.
    """
    names = {id(transform): key for key, transform in registry.items()}
    return tuple(
        SymbolConstructor(names[id(entry.apply)], entry.names, entry.optional)
        for entry in binding.construction.symbols
    )


def main() -> None:
    """Run the differential; any disagreement raises."""
    the_two_halves_say_the_same_thing()
    the_product_lowers_against_its_own_registry()
    an_unregistered_transform_cannot_reach_a_parse()
    one_slot_can_be_captured_twice_in_two_modes()
    print(
        "s4 authored product\tPASS\t"
        "both authored surfaces say one thing in two vocabularies"
    )


if __name__ == "__main__":
    main()
