"""Tests for lexic.parsing.product.lower — authored records into flat tables.

Three obligations the module states for itself: every authored enum becomes
an exact int, one rule completion is one instruction, and operands index
their own opcode's POOLED and DEDUPLICATED rows. Each is exercised directly,
plus every refusal lowering owns: a pre-filled lowering-owned table, a
constructor that is not a real class, a declared matched-text field that
disagrees with the class or a capture, a symbol absent from its registry, a
repeated symbol keyword, and an empty expression program.
"""

from __future__ import annotations

import pytest

from lexic.exceptions import UnsupportedConstructError
from lexic.parsing.product.abi.construction import RecordConstructor, SymbolConstructor
from lexic.parsing.product.abi.expressions import ArgExpr, ExprProgram
from lexic.parsing.product.abi.records import (
    CaptureMode,
    CaptureSpec,
    LoweredRoute,
    MeaningOp,
    OpCode,
    OperandTables,
    PassOp,
    RangeKind,
    RecordOp,
    RootOp,
    RouteTable,
    RuleProduct,
    UniformRoute,
)
from lexic.parsing.product.lower import LoweringOwned, lower_product, lower_routes

_ROOTS = (lambda carry, _verdicts: carry,)
_MEANINGS = (lambda left, right: left == right,)


class _Pair(tuple):
    """A minimal declared record class with two fields, no defaults."""

    @classmethod
    def fast_construct(cls):
        return (cls, {}, ("a", "b"))


def _operands(
    constructors: tuple[RecordConstructor, ...] = (),
    routes: tuple[LoweredRoute, ...] = (),
) -> OperandTables:
    return OperandTables(
        constants=(),
        constructors=constructors,
        sequences=(),
        mappings=(),
        meanings=_MEANINGS,
        roots=_ROOTS,
        routes=routes,
        continuations=(),
    )


def _lower(rules, owned=LoweringOwned()):
    return lower_product(
        rules, _operands(), owned=owned, root=RootOp(0), meaning=MeaningOp(0)
    )


# ── one instruction per rule, exact-int rows ─────────────────────────────


def test_a_pass_op_lowers_to_one_fused_instruction():
    """PassOp becomes one FUSED range of length 1, PASS opcode, source row."""
    program = _lower([RuleProduct(captures=(), completion=PassOp(3))])
    rng = program.completions[0]
    assert rng.kind == int(RangeKind.FUSED)
    assert rng.length == 1
    assert program.fused_opcodes[rng.start] == int(OpCode.PASS)
    row = program.fused_operand_rows[int(OpCode.PASS)][
        program.fused_operands[rng.start]
    ]
    assert row == (3,)
    assert all(field.__class__ is int for field in row)


def test_two_rules_with_the_identical_operation_share_one_pooled_row():
    """Row pooling deduplicates: two PassOp(5) rules index the SAME row."""
    program = _lower(
        [
            RuleProduct(captures=(), completion=PassOp(5)),
            RuleProduct(captures=(), completion=PassOp(5)),
        ]
    )
    first, second = program.completions
    op1 = program.fused_operands[first.start]
    op2 = program.fused_operands[second.start]
    assert op1 == op2  # same pool slot, not two copies of an equal row


def test_two_rules_with_different_operations_get_distinct_rows():
    """Distinct operations of the same opcode never collide in the pool."""
    program = _lower(
        [
            RuleProduct(captures=(), completion=PassOp(0)),
            RuleProduct(captures=(), completion=PassOp(1)),
        ]
    )
    first, second = program.completions
    assert program.fused_operands[first.start] != program.fused_operands[second.start]


def test_an_expression_program_lowers_into_the_separate_expression_table():
    """An ExprProgram completion occupies the EXPRESSION range, not FUSED."""
    program = _lower([RuleProduct(captures=(), completion=ExprProgram((ArgExpr(0),)))])
    rng = program.completions[0]
    assert rng.kind == int(RangeKind.EXPRESSION)
    assert rng.length == 1
    assert program.fused_opcodes == ()  # nothing touched the fused table at all


def test_an_empty_expression_program_refuses():
    """A body with no operations would compile to an empty completion range."""
    with pytest.raises(UnsupportedConstructError, match="empty completion range"):
        _lower([RuleProduct(captures=(), completion=ExprProgram(()))])


# ── the stateful flag is derived, not declared ───────────────────────────


def test_a_pass_only_program_is_not_stateful():
    """No collection opcode anywhere — the generated-model shape."""
    program = _lower([RuleProduct(captures=(), completion=PassOp(0))])
    assert program.stateful is False


def test_a_record_only_program_is_not_stateful():
    """RECORD alone builds directly from captures — still no builder needed."""
    owned = LoweringOwned(
        constructors=(RecordConstructor(cls=_Pair, names=("a", "b")),)
    )
    rules = [
        RuleProduct(
            captures=(
                CaptureSpec(int(CaptureMode.TEXT), 0),
                CaptureSpec(int(CaptureMode.TEXT), 1),
            ),
            completion=RecordOp(0),
            n_items=2,
        )
    ]
    assert _lower(rules, owned).stateful is False


def test_a_program_with_a_sequence_opcode_is_stateful():
    """Any collection-builder opcode anywhere makes the WHOLE program stateful."""
    from lexic.parsing.product.abi.records import BeginSequenceOp

    program = _lower([RuleProduct(captures=(), completion=BeginSequenceOp(0))])
    assert program.stateful is True


# ── lower_routes: cardinality-specialized, no scan survives ─────────────


def test_lower_routes_zero_known_keys_becomes_uniform():
    """A vocabulary table with no known keys bypasses classification entirely."""
    (route,) = lower_routes([RouteTable(known=(), extension=7)])
    assert route.route_of("anything") == 7


def test_lower_routes_one_known_key_becomes_singleton():
    """Exactly one known key specializes to a single equality test."""
    (route,) = lower_routes([RouteTable(known=(("type", 1),), extension=0)])
    assert route.route_of("type") == 1
    assert route.route_of("other") == 0


def test_lower_routes_two_or_more_known_keys_becomes_a_table():
    """Two or more known keys specialize to one dictionary probe."""
    (route,) = lower_routes([RouteTable(known=(("a", 1), ("b", 2)), extension=0)])
    assert route.route_of("a") == 1
    assert route.route_of("b") == 2
    assert route.route_of("c") == 0


def test_lower_routes_refuses_a_continuation_count_mismatch():
    """Continuations, when supplied, must pair one-to-one with the tables."""
    from lexic.parsing.product.abi.records import RouteContinuation

    with pytest.raises(UnsupportedConstructError, match="do not pair"):
        lower_routes(
            [RouteTable(known=(), extension=0), RouteTable(known=(), extension=0)],
            [RouteContinuation(producer=0, path=(0,), destinations=())],
        )


# ── constructor validation ────────────────────────────────────────────────


def test_refuses_a_constructor_entry_that_is_not_a_record_constructor():
    """The constructor table is written by lowering; a caller cannot pre-fill it."""
    with pytest.raises(UnsupportedConstructError, match="written by lowering alone"):
        lower_product(
            [RuleProduct(captures=(), completion=PassOp(0))],
            _operands(constructors=(RecordConstructor(cls=_Pair),)),
            root=RootOp(0),
            meaning=MeaningOp(0),
        )


def test_refuses_a_constructor_whose_cls_is_not_a_class():
    """A RecordConstructor naming a non-class object cannot build anything."""
    entry = RecordConstructor._make(["not-a-class", (), (), {}, "", False])
    owned = LoweringOwned(constructors=(entry,))
    with pytest.raises(UnsupportedConstructError, match="not a class"):
        _lower([RuleProduct(captures=(), completion=RecordOp(0))], owned)


def test_refuses_a_matched_field_the_class_does_not_have():
    """A declared own-text field the class's own fast_construct never names."""
    owned = LoweringOwned(
        constructors=(RecordConstructor(cls=_Pair, matched_field="c"),)
    )
    with pytest.raises(UnsupportedConstructError, match="has no such"):
        _lower([RuleProduct(captures=(), completion=RecordOp(0))], owned)


def test_refuses_a_matched_field_that_is_also_a_capture():
    """A field cannot be filled from BOTH the rule's own text and a capture."""
    owned = LoweringOwned(
        constructors=(RecordConstructor(cls=_Pair, names=("a",), matched_field="a"),)
    )
    with pytest.raises(UnsupportedConstructError, match="AND with a capture"):
        _lower([RuleProduct(captures=(), completion=RecordOp(0))], owned)


def test_refuses_a_licensed_constructor_leaving_a_field_uncovered():
    """A licensed entry whose class has a field no capture or default reaches."""
    owned = LoweringOwned(
        constructors=(RecordConstructor(cls=_Pair, names=("a",), licensed=True),)
    )
    with pytest.raises(
        UnsupportedConstructError, match="neither a capture nor a default"
    ):
        _lower([RuleProduct(captures=(), completion=RecordOp(0))], owned)


# ── symbol resolution: the no-eval boundary ──────────────────────────────


def test_refuses_a_symbol_not_in_the_registry():
    """A symbol name reaches a parse only by being registered at lowering."""
    owned = LoweringOwned(symbols=(SymbolConstructor(symbol="missing"),), registry={})
    with pytest.raises(UnsupportedConstructError, match="not in the registry"):
        _lower([RuleProduct(captures=(), completion=RecordOp(0))], owned)


def test_refuses_a_symbol_with_a_repeated_keyword():
    """Two captures cannot write the same keyword — the later would silently win."""
    owned = LoweringOwned(
        symbols=(SymbolConstructor(symbol="dup", names=("x", "x")),),
        registry={"dup": lambda **kw: kw},
    )
    with pytest.raises(UnsupportedConstructError, match="repeats one"):
        _lower([RuleProduct(captures=(), completion=RecordOp(0))], owned)


def test_refuses_a_symbol_whose_optional_index_names_no_capture():
    """An optional index outside the keyword range the names describe."""
    owned = LoweringOwned(
        symbols=(SymbolConstructor(symbol="s", names=("x",), optional=(5,)),),
        registry={"s": lambda **kw: kw},
    )
    with pytest.raises(UnsupportedConstructError, match="marks captures"):
        _lower([RuleProduct(captures=(), completion=RecordOp(0))], owned)


def test_a_resolved_symbol_is_callable_through_its_registry_entry():
    """A valid symbol resolves to the exact registered callable, applied by keyword."""
    marker = object()
    registry = {"tag": lambda **kw: (marker, kw)}
    owned = LoweringOwned(
        symbols=(SymbolConstructor(symbol="tag", names=("value",)),), registry=registry
    )
    program = _lower([RuleProduct(captures=(), completion=RecordOp(0))], owned)
    bound = program.operands.symbols[0]
    assert bound.apply(value="hi") == (marker, {"value": "hi"})


def test_refuses_a_prefilled_route_or_symbol_table():
    """The route and symbol operand tables are lowering's own output only."""
    with pytest.raises(UnsupportedConstructError, match="written by lowering alone"):
        lower_product(
            [RuleProduct(captures=(), completion=PassOp(0))],
            _operands(routes=(UniformRoute(extension=0),)),
            root=RootOp(0),
            meaning=MeaningOp(0),
        )
