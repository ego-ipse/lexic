"""Tests for lexic.parsing.product.abi.records — the product ABI's two layers.

Field ORDER is load-bearing here, not decorative: ``lower.py`` reads an
authored operation's row via ``tuple(operation)`` (positional), and
``ProductProgram``/``OperandTables`` are built positionally too — a silently
reordered field would desync the row a lowered instruction reads from the
field a caller thinks it wrote, with no type error anywhere. Every field-order
pin below is therefore checked against the exact tuple the class declares, not
against what a call happens to produce.
"""

from __future__ import annotations

import pytest

from lexic.exceptions import UnsupportedConstructError
from lexic.ir.spine.bind import BIND_MODES
from lexic.parsing.product.abi.records import (
    CAPTURE_FOR_BIND,
    AppendSequenceOp,
    BeginMappingOp,
    BeginSequenceOp,
    CaptureMode,
    CaptureSpec,
    CompletionRange,
    ConstantOp,
    DecodeOp,
    FinishMappingOp,
    FinishSequenceOp,
    FlatRuleProduct,
    InsertMappingOp,
    LoweredRoute,
    MeaningOp,
    OpCode,
    OperandTables,
    PassOp,
    ProductProgram,
    RangeKind,
    RecordOp,
    RootOp,
    RouteContinuation,
    RouteOp,
    RouteTable,
    RuleProduct,
    SingletonRoute,
    TableRoute,
    UniformRoute,
    ValidateOp,
)

# ── the closed capture vocabulary ───────────────────────────────────────


def test_capture_mode_values_are_pinned():
    """CaptureMode's exact ints, cross-module contracts index by value."""
    assert (
        int(CaptureMode.SKIP),
        int(CaptureMode.TEXT),
        int(CaptureMode.EXTENT),
        int(CaptureMode.ONE),
        int(CaptureMode.MANY),
    ) == (0, 1, 2, 3, 4)


def test_capture_for_bind_covers_exactly_the_ir_bind_vocabulary():
    """The translation table's keys are ir.spine.bind.BIND_MODES, independently.

    An oracle outside this module: if a bind mode were added or renamed in
    ``lexic.ir`` without updating this table, an IrBind of that mode would
    have no capture translation and this is the test that would say so.
    """
    assert set(CAPTURE_FOR_BIND) == set(BIND_MODES)


def test_capture_for_bind_text_and_gtext_share_one_mode():
    """text/gtext differ only by absence handling, not by capture mode."""
    assert CAPTURE_FOR_BIND["text"] == CAPTURE_FOR_BIND["gtext"] == CaptureMode.TEXT


def test_capture_for_bind_the_other_three_modes_are_distinct():
    """model/models/span each own a distinct mode — no two collapse."""
    modes = {CAPTURE_FOR_BIND[name] for name in ("model", "models", "span")}
    assert modes == {CaptureMode.ONE, CaptureMode.MANY, CaptureMode.EXTENT}


# ── the closed opcode/range vocabularies ────────────────────────────────


def test_range_kind_members_are_four_distinct_ints():
    """A rule names exactly one range kind — the vocabulary must not collide."""
    values = {int(kind) for kind in RangeKind}
    assert len(values) == 4


def test_opcode_members_are_eleven_distinct_ints_from_zero():
    """The flat instruction vocabulary is dense from 0 — no gaps, no repeats."""
    values = sorted(int(code) for code in OpCode)
    assert values == list(range(11))


# ── authored operation field order (positional lowering depends on this) ──


def test_pass_op_field_order():
    """PassOp is (source,) — lower.py reads it as one field row."""
    assert tuple(PassOp(7)) == (7,)


def test_constant_op_field_order():
    """ConstantOp is (constant,)."""
    assert tuple(ConstantOp(3)) == (3,)


def test_decode_op_field_order():
    """DecodeOp is (text, decoder) in that order."""
    op = DecodeOp(text=2, decoder=1)
    assert tuple(op) == (2, 1)


def test_route_op_field_order():
    """RouteOp is (text, routes)."""
    assert tuple(RouteOp(text=4, routes=0)) == (4, 0)


def test_validate_op_field_order():
    """ValidateOp is (source, check)."""
    assert tuple(ValidateOp(source=5, check=2)) == (5, 2)


def test_begin_sequence_op_field_order():
    """BeginSequenceOp is (destination,)."""
    assert tuple(BeginSequenceOp(1)) == (1,)


def test_append_sequence_op_field_order():
    """AppendSequenceOp is (builder, value)."""
    assert tuple(AppendSequenceOp(builder=0, value=3)) == (0, 3)


def test_finish_sequence_op_field_order():
    """FinishSequenceOp is (builder, finisher)."""
    assert tuple(FinishSequenceOp(builder=1, finisher=2)) == (1, 2)


def test_begin_mapping_op_field_order():
    """BeginMappingOp is (destination, duplicates)."""
    assert tuple(BeginMappingOp(destination=0, duplicates=1)) == (0, 1)


def test_insert_mapping_op_field_order():
    """InsertMappingOp is (builder, key, value)."""
    assert tuple(InsertMappingOp(builder=0, key=1, value=2)) == (0, 1, 2)


def test_finish_mapping_op_field_order():
    """FinishMappingOp is (builder, finisher)."""
    assert tuple(FinishMappingOp(builder=0, finisher=1)) == (0, 1)


def test_record_op_field_order():
    """RecordOp is (constructor,)."""
    assert tuple(RecordOp(9)) == (9,)


def test_meaning_op_field_order():
    """MeaningOp is (comparator,)."""
    assert tuple(MeaningOp(0)) == (0,)


def test_root_op_field_order():
    """RootOp is (finalizer,)."""
    assert tuple(RootOp(0)) == (0,)


# ── flat records ─────────────────────────────────────────────────────────


def test_capture_spec_field_order():
    """CaptureSpec is (mode, slot)."""
    spec = CaptureSpec(mode=int(CaptureMode.TEXT), slot=3)
    assert (spec.mode, spec.slot) == (int(CaptureMode.TEXT), 3)


def test_rule_product_n_items_defaults_to_zero():
    """A rule with no sequence arm declares zero items by default."""
    product = RuleProduct(captures=(), completion=PassOp(0))
    assert product.n_items == 0


def test_flat_rule_product_field_order_and_default():
    """FlatRuleProduct is (capture_modes, capture_slots, completion, n_items=0)."""
    flat = FlatRuleProduct((int(CaptureMode.ONE),), (0,), 5)
    assert flat.capture_modes == (int(CaptureMode.ONE),)
    assert flat.capture_slots == (0,)
    assert flat.completion == 5
    assert flat.n_items == 0


def test_completion_range_field_order():
    """CompletionRange is (kind, start, length)."""
    rng = CompletionRange(kind=int(RangeKind.FUSED), start=2, length=1)
    assert (rng.kind, rng.start, rng.length) == (int(RangeKind.FUSED), 2, 1)


# ── lowered routes — no scan, no silent default ─────────────────────────


def test_lowered_route_base_refuses_rather_than_defaulting():
    """The base class's route_of raises by name — never a silent 0."""
    base = LoweredRoute(extension=9)
    with pytest.raises(UnsupportedConstructError, match="does not say where"):
        base.route_of("anything")


def test_uniform_route_ignores_every_key():
    """A dynamic-mapping route classifies nothing — every key, one route."""
    route = UniformRoute(extension=3)
    for key in ("", "a", "unrelated-key", "3"):
        assert route.route_of(key) == 3


def test_singleton_route_distinguishes_its_one_key_from_everything_else():
    """One equality test: the exact key routes; a near-miss falls to extension.

    ``destinations`` is dense BY ROUTE ID (extension=0, route=1), which is
    what ``destination_of`` indexes into — not by the arbitrary value a
    caller might put in ``extension``/``route`` themselves.
    """
    route = SingletonRoute(extension=0, key="type", route=1, destinations=(10, 20))
    assert route.route_of("type") == 1
    assert route.destination_of("type") == 20
    # adversarial: a prefix, a suffix, and case variance are all NOT the key
    for near_miss in ("typ", "types", "Type", ""):
        assert route.route_of(near_miss) == 0
        assert route.destination_of(near_miss) == 10


def test_table_route_probes_a_dict_rather_than_scanning():
    """Two or more keys route through the lowered dict, unknown keys extend."""
    route = TableRoute(
        extension=0, lookup={"a": 1, "b": 2}, destinations=(100, 101, 102)
    )
    assert route.route_of("a") == 1
    assert route.route_of("b") == 2
    assert route.route_of("c") == 0  # unknown key: the catch-all route
    assert route.destination_of("a") == 101
    assert route.destination_of("c") == 100


# ── operand and program containers — positional field order ────────────


def test_operand_tables_symbols_defaults_to_empty():
    """OperandTables.symbols is the one optional field — every other is required."""
    tables = OperandTables((), (), (), (), (), (), (), ())
    assert not tables.symbols


def test_operand_tables_field_order():
    """OperandTables' eight fields, in the order lower_product constructs them."""
    continuation = RouteContinuation(producer=0, path=(0,), destinations=())
    tables = OperandTables(
        constants=("c",),
        constructors=(),
        sequences=(),
        mappings=(),
        meanings=(),
        roots=(),
        routes=(),
        continuations=(continuation,),
        symbols=(),
    )
    assert tuple(type(tables).__annotations__) == (
        "constants",
        "constructors",
        "sequences",
        "mappings",
        "meanings",
        "roots",
        "routes",
        "continuations",
        "symbols",
    )
    assert tables.constants == ("c",)
    assert tables.continuations == (continuation,)


def test_product_program_field_order():
    """ProductProgram's field order — lower_product builds it POSITIONALLY.

    A silent reorder here would desync every positional construction site with
    no type error, which is exactly why this pins the tuple rather than only
    the keyword access.
    """
    assert tuple(ProductProgram.__annotations__) == (
        "rules",
        "completions",
        "expression_opcodes",
        "expression_operands",
        "expression_operand_rows",
        "fused_opcodes",
        "fused_operands",
        "fused_operand_rows",
        "operands",
        "root",
        "meaning",
        "stateful",
    )


def test_product_program_stateful_defaults_to_false():
    """A program built without saying so is not stateful — an explicit opt-in."""
    empty = OperandTables((), (), (), (), (), (), (), ())
    program = ProductProgram(
        (), (), (), (), (), (), (), (), empty, RootOp(0), MeaningOp(0)
    )
    assert program.stateful is False


def test_route_table_field_order():
    """RouteTable is (known, extension)."""
    table = RouteTable(known=(("a", 0),), extension=1)
    assert (table.known, table.extension) == ((("a", 0),), 1)


def test_route_continuation_field_order():
    """RouteContinuation is (producer, path, destinations)."""
    cont = RouteContinuation(producer=3, path=(1, 2), destinations=(4, 5))
    assert (cont.producer, cont.path, cont.destinations) == (3, (1, 2), (4, 5))
