"""Tests for lexic.parsing.fold — the positional instance-parsing bridge.

An IR body-table (IrMap[IrRuleRef, ModelBody]) that bakes to RuleFold config
drives ModelFold over ``parse_first`` trees of the *real* instance grammar —
no wrapper rules. End-to-end fold behaviors run through the compiled pipeline
fixtures (``arithmetic`` / ``optional_shapes`` in conftest); the generic-fold
sections use opaque dict constructors to prove the fold needs no knowledge of
the model layer.
"""

from __future__ import annotations

from typing import cast

import pytest

from lexic.compile import compile_text, reset_cache_for_tests
from lexic.exceptions import UnsupportedConstructError
from lexic.ir import (
    IrAlternation,
    IrArg,
    IrArgs,
    IrAst,
    IrItem,
    IrLambda,
    IrLiteral,
    IrMap,
    IrNone,
    IrQuantifier,
    IrRule,
    IrRuleRef,
    IrSeq,
    IrSequence,
    IrTuple,
)
from lexic.parsing import parse_first
from lexic.parsing.earley.kernel.forest.forest import ParseTree
from lexic.parsing.earley.kernel.tables.builder import compile_tables
from lexic.parsing.earley.normalize import SYNTHETIC_PREFIX, normalize
from lexic.parsing.fold import (
    FieldFold,
    ModelBody,
    ModelFold,
    RuleFold,
    collapsed_fold_tables,
    lift_optional_nullables,
)
from lexic.parsing.pda.runtime.kernel.kernel import pda_model
from lexic.parsing.products import _model_product, earley_model
from tests.paths import GROUND_TRUTH
from tests.unit.lexic.parsing.ir_fixtures import (
    malformed_synthetic_rule,
    nested_synthetic_grammar,
)
from tests.unit.lexic.parsing.parsing_helpers import prod

# ── the compiled config — structure ─────────────────────────────────────


def test_instance_grammar_is_normalized(arithmetic):
    """The compiled instance grammar is Earley-normalized: parse_first accepts
    it directly (tables.py raises 'run normalize() before compiling' on a raw
    grammar, so a successful parse is itself proof of normalization)."""
    tree = parse_first(prod(arithmetic).instance_grammar, "x=1\n")
    assert tree is not None


def test_config_carries_modes_and_lo_for_field_bearing_items(arithmetic):
    """Each field-bearing item folds under the expected mode and original
    (pre-lift) quantifier lo — the successor of the wrapper-rule registry."""
    config = arithmetic.fold.config
    by_name = {
        rule: {f.name: (f.mode, f.lo) for f in rf.fields} for rule, rf in config.items()
    }
    assert by_name["root"]["root_item"] == ("models", 1)
    assert by_name["expr"]["term"] == ("model", 1)
    assert by_name["expr"]["expr_item"] == ("models", 0)
    assert by_name["ident"]["lower"] == ("text", 1)
    assert by_name["num"]["digit"] == ("text", 1)


def test_unquantified_literals_stay_inline_no_field(arithmetic):
    """Structural (1,1) literals never get a field, but keep their kid slot.

    root-item ::= expr "=" ws term "\\n" — items 1 ('=') and 4 ('\\n') are
    unquantified literals: absent from the fields, present in n_items.
    """
    root_item = arithmetic.fold.config["root-item"]
    bound_slots = {f.item for f in root_item.fields}
    assert 1 not in bound_slots
    assert 4 not in bound_slots
    assert root_item.n_items == 5


# ── ModelFold construction — config validation ─────────────────────


def test_fold_rejects_unknown_kind():
    """A config kind outside FOLD_KINDS is refused at construction."""
    config = {"r": RuleFold("mystery", dict, 0, ())}
    with pytest.raises(UnsupportedConstructError, match="unknown kind"):
        ModelFold.from_config(config)


def test_fold_rejects_unknown_mode():
    """A field mode outside BIND_MODES is refused at construction."""
    config = {"r": RuleFold("sequence", dict, 1, (FieldFold(0, "bogus", "x", 1),))}
    with pytest.raises(UnsupportedConstructError, match="unknown mode"):
        ModelFold.from_config(config)


def test_fold_kid_count_mismatch_raises():
    """Non-zero kids that match neither n_items nor the empty arm raise."""
    fold = ModelFold.from_config({"r": RuleFold("sequence", dict, 2, ())})
    node = ParseTree(IrRuleRef("r"), IrSeq(IrLiteral("a")))
    with pytest.raises(UnsupportedConstructError, match="do not match"):
        fold.apply(node)


def test_fold_sequence_zero_item_arm_takes_the_equal_length_path():
    """A rule whose single (non-alternate) arm is itself empty (n_items=0)
    folds through the equal-length branch, not the empty-alternate-arm
    mismatch branch — both end up calling ctor() with no kwargs, but a
    kid-count mismatch there would incorrectly raise (kids=0, n_items=0 are
    equal, so ``if len(kids) != rule_fold.n_items`` is False from the start)."""
    fold = ModelFold.from_config({"r": RuleFold("sequence", dict, 0, ())})
    node = ParseTree(IrRuleRef("r"), IrSeq())
    assert fold.apply(node) == {}


# ── ModelFold.apply — fold behaviors end-to-end ────────────────────


def test_sequence_kwargs_by_position(arithmetic):
    """A sequence rule's fields fold from their positional kid slots."""
    model = arithmetic.parse("x=1\n")
    item = model.root_item[0]
    assert item.expr.term.lower == "x"
    assert item.term.digit == "1"


def test_terminal_field_empty_match_is_empty_string(arithmetic):
    """An empty terminal match (ident's [a-z0-9_]* tail, unmatched) folds to ''."""
    model = arithmetic.parse("x=1\n")
    ident = model.root_item[0].expr.term
    assert ident.head == ""


def test_ruleref_list_field_unbounded(arithmetic):
    """An unbounded ref list ('root_item', one per repetition) collects all."""
    model = arithmetic.parse("x=1\ny=2\n")
    assert len(model.root_item) == 2
    assert model.root_item[0].expr.term.lower == "x"
    assert model.root_item[1].expr.term.lower == "y"


def test_alternation_passthrough(arithmetic):
    """An alternation-kind rule ('term') folds through to its matched arm's model."""
    model = arithmetic.parse("x=1\n")
    term = model.root_item[0].expr.term
    assert type(term).__name__ == "Ident"


def test_value_str_joins_matched_text(arithmetic):
    """A value_str rule ('ws') folds to its matched span joined as one string."""
    model = arithmetic.parse("x = 1\n")
    # ident's own trailing ws eats the space before '='; root-item's ws slot
    # eats the space after '=' — two distinct single-space gaps, not one.
    assert model.root_item[0].expr.term.ws.value == " "
    assert model.root_item[0].ws.value == " "


def test_end_to_end_round_trip(arithmetic):
    """parse(text).to_text() reproduces the input exactly."""
    text = "x=1\n"
    assert arithmetic.parse(text).to_text() == text


def test_optional_ref_absent_is_none(optional_shapes):
    """An optional ref to a non-nullable rule is None when absent."""
    model = optional_shapes.parse("ab")
    assert model.thing is None


def test_optional_ref_present_is_the_submodel(optional_shapes):
    """An optional ref to a non-nullable rule is the sub-model when present."""
    model = optional_shapes.parse("aTb")
    assert model.thing.value == "T"


def test_optional_literal_group_absent_is_empty_text(optional_shapes):
    """``("!")?`` is empty text ('text' mode) when absent.

    canonicalize's rewrite 6 (quantifier push-onto-inner-atom) collapses the
    single-arm single-item group ``("!")?`` to the plain quantified literal
    ``"!"?`` before codegen ever sees it — an ordinary 'text'-mode field
    (``''`` when absent), field name ``lit``.
    """
    model = optional_shapes.parse("ab")
    assert model.lit == ""


def test_optional_literal_group_present_is_text(optional_shapes):
    """``("!")?`` is the matched text when present — same collapse as above."""
    model = optional_shapes.parse("a!b")
    assert model.lit == "!"


# ── zero-kid nodes (empty alternate arm) ─────────────────────────────────


def test_empty_alternate_arm_folds_with_no_kwargs():
    """A rule with an empty alternate arm parses empty input to a model with
    every field absent, and the full arm keeps its positional fields.

    New capability of the positional pipeline (the old derive silently
    dropped empty arms). When the full arm is itself all-nullable the empty
    match is ambiguous between the arms; parse_first resolves it to the
    first derivation, deterministically.
    """
    cg = compile_text('root ::= "<" pair ">"\npair ::= a b |\na ::= "a"\nb ::= "b"\n')
    full = cg.parse("<ab>")
    empty = cg.parse("<>")
    assert full.dump()["pair"] == {"a": {"value": "a"}, "b": {"value": "b"}}
    assert empty.dump()["pair"] == {"a": None, "b": None}
    assert full.to_text() == "<ab>"
    assert empty.to_text() == "<>"


def test_fold_is_generic_over_opaque_constructors():
    """The fold needs no model class: dict constructors work positionally."""
    grammar = normalize(
        IrAst(
            rules=IrSeq(
                IrRule(
                    "pair",
                    IrAlternation(
                        IrSequence(IrItem(IrRuleRef("a")), IrItem(IrRuleRef("b"))),
                        IrSequence(),
                    ),
                ),
                IrRule("a", IrAlternation(IrSequence(IrItem(IrLiteral("a"))))),
                IrRule("b", IrAlternation(IrSequence(IrItem(IrLiteral("b"))))),
            ),
            start="pair",
        )
    )
    fold = ModelFold.from_config(
        {
            "pair": RuleFold(
                "sequence",
                dict,
                2,
                (FieldFold(0, "model", "a", 1), FieldFold(1, "model", "b", 1)),
            ),
            "a": RuleFold("value_str", lambda value: value, 1, ()),
            "b": RuleFold("value_str", lambda value: value, 1, ()),
        }
    )
    assert fold.apply(parse_first(grammar, "ab")) == {"a": "a", "b": "b"}
    assert fold.apply(parse_first(grammar, "")) == {}


# ── lift_optional_nullables ──────────────────────────────────────────────


def test_lift_rewrites_optional_ref_to_nullable_as_mandatory():
    """An optional (0,1) ref to a nullable rule is lifted to (1,1)."""
    empty = IrRule("empty", IrAlternation(IrSequence(IrItem(IrLiteral("")))))
    host = IrRule(
        "host",
        IrAlternation(IrSequence(IrItem(IrRuleRef("empty"), IrQuantifier(0, 1)))),
    )
    lifted = lift_optional_nullables(IrAst(rules=IrSeq(empty, host), start="host"))
    host_lifted = next(r for r in lifted.rules if str(r.name) == "host")
    item = host_lifted.body[0][0]
    assert item.atom == IrRuleRef("empty")
    assert item.quantifier == IrQuantifier(1, 1)


def test_lift_leaves_optional_ref_to_non_nullable_untouched():
    """An optional (0,1) ref to a non-nullable rule is left as-is."""
    solid = IrRule("solid", IrAlternation(IrSequence(IrItem(IrLiteral("z")))))
    host = IrRule(
        "host",
        IrAlternation(IrSequence(IrItem(IrRuleRef("solid"), IrQuantifier(0, 1)))),
    )
    lifted = lift_optional_nullables(IrAst(rules=IrSeq(solid, host), start="host"))
    host_lifted = next(r for r in lifted.rules if str(r.name) == "host")
    item = host_lifted.body[0][0]
    assert item.quantifier == IrQuantifier(0, 1)


def test_lift_preserves_positions_and_start():
    """The lift rewrites items in place: item count, order and start stable."""
    empty = IrRule("empty", IrAlternation(IrSequence(IrItem(IrLiteral("")))))
    host = IrRule(
        "host",
        IrAlternation(
            IrSequence(
                IrItem(IrLiteral("x")),
                IrItem(IrRuleRef("empty"), IrQuantifier(0, 1)),
                IrItem(IrLiteral("y")),
            )
        ),
    )
    lifted = lift_optional_nullables(IrAst(rules=IrSeq(empty, host), start="host"))
    assert lifted.start == "host"
    host_lifted = next(r for r in lifted.rules if str(r.name) == "host")
    arm = host_lifted.body[0]
    assert len(arm) == 3
    assert arm[0].atom == IrLiteral("x")
    assert arm[2].atom == IrLiteral("y")


def test_lift_is_idempotent():
    """Lifting an already-lifted grammar changes nothing further: once an
    item is (1, 1) the rewrite condition (``lo == 0``) no longer holds."""
    empty = IrRule("empty", IrAlternation(IrSequence(IrItem(IrLiteral("")))))
    host = IrRule(
        "host",
        IrAlternation(IrSequence(IrItem(IrRuleRef("empty"), IrQuantifier(0, 1)))),
    )
    ast = IrAst(rules=IrSeq(empty, host), start="host")
    once = lift_optional_nullables(ast)
    twice = lift_optional_nullables(once)
    assert twice == once


# ── collapsed_fold_tables ────────────────────────────────────────────────


def test_collapsed_fold_tables_collapses_a_run_on_arithmetic(arithmetic):
    """arithmetic.gbnf's num/ident charclass runs collapse to RunTerm leaves.

    A collapsed run shows up as a ``lens == 0`` terminal — see
    :class:`~lexic.parsing.earley.kernel.tables.TermTables`.
    """
    plain = compile_tables(prod(arithmetic).instance_grammar)
    collapsed = collapsed_fold_tables(
        prod(arithmetic).instance_grammar, arithmetic.fold
    )
    assert collapsed is not plain
    assert any(length == 0 for length in collapsed.terms.lens)


def test_collapsed_fold_tables_memoises_per_fold_and_grammar(arithmetic):
    """The same (fold, grammar) pair returns the identical tables object."""
    first = collapsed_fold_tables(prod(arithmetic).instance_grammar, arithmetic.fold)
    second = collapsed_fold_tables(prod(arithmetic).instance_grammar, arithmetic.fold)
    assert first is second


def test_collapsed_fold_tables_returns_plain_when_no_candidates(optional_shapes):
    """A grammar with no star/plus run candidates gets back the plain tables."""
    plain = compile_tables(prod(optional_shapes).instance_grammar)
    collapsed = collapsed_fold_tables(
        prod(optional_shapes).instance_grammar, optional_shapes.fold
    )
    assert collapsed is plain


def test_compiled_tables_are_the_collapsed_ones(arithmetic):
    """CompiledGrammar.tables is exactly the memoised collapsed tables."""
    assert prod(arithmetic).tables is collapsed_fold_tables(
        prod(arithmetic).instance_grammar, arithmetic.fold
    )


def test_collapsed_fold_tables_memo_keys_on_identity_not_equality():
    """Two independent compiles of the same source produce structurally equal
    but distinct (grammar, fold) objects — the memo (keyed on ``id()``, per
    its own docstring) must not alias across them."""
    text = (GROUND_TRUTH / "arithmetic.gbnf").read_text(encoding="utf-8")
    cg1 = compile_text(text)
    reset_cache_for_tests()  # force a genuinely fresh second compile
    cg2 = compile_text(text)
    assert prod(cg1).instance_grammar == prod(cg2).instance_grammar
    assert prod(cg1).instance_grammar is not prod(cg2).instance_grammar
    assert prod(cg1).tables is not prod(cg2).tables


def test_collapsed_fold_tables_distinct_fold_objects_do_not_share_cache(arithmetic):
    """A fold object with an identical config is still a distinct object —
    collapsed_fold_tables must recompute, not alias, for it."""
    duplicate_fold = ModelFold.from_config(dict(arithmetic.fold.config))
    first = collapsed_fold_tables(prod(arithmetic).instance_grammar, arithmetic.fold)
    second = collapsed_fold_tables(prod(arithmetic).instance_grammar, duplicate_fold)
    assert first is not second


# ── ModelFold.run_ok (the run-collapse licence) ─────────────────────


def test_run_ok_true_for_bare_terminal_unit(digit_grammar):
    """A bare-terminal run unit (unit_rid == -1) is always fold-safe."""
    fold = ModelFold.from_config({})
    tables = compile_tables(digit_grammar)
    assert fold.run_ok(tables, -1) is True


def test_run_ok_false_when_unit_is_a_config_rule(digit_grammar):
    """A run whose unit resolves to a constructor-bearing rule is not safe."""
    fold = ModelFold.from_config({"digit": RuleFold("value_str", dict, 1, ())})
    tables = compile_tables(digit_grammar)
    digit_rid = tables.decode.rule_ids["digit"]
    assert fold.run_ok(tables, digit_rid) is False


def test_run_ok_true_when_leaf_rule_untracked_by_fold(digit_grammar):
    """A leaf rule absent from the fold config hides no model structure."""
    fold = ModelFold.from_config({})
    tables = compile_tables(digit_grammar)
    digit_rid = tables.decode.rule_ids["digit"]
    assert fold.run_ok(tables, digit_rid) is True


def test_run_ok_true_when_leaf_rule_is_discarded(digit_grammar):
    """A recognition-only leaf hides no model when collapsed into a run."""
    fold = ModelFold.from_config({"digit": RuleFold("discard", dict, 0, ())})
    tables = compile_tables(digit_grammar)
    digit_rid = tables.decode.rule_ids["digit"]
    assert fold.run_ok(tables, digit_rid) is True


def test_run_ok_false_for_malformed_synthetic_shape():
    """unit_leaves returning None (not a charset-rule shape) is not fold-safe.

    The existing run_ok tests only exercise a non-synthetic unit_rid, where
    unit_leaves short-circuits to ``({rid}, False)`` without ever reaching
    the transitive walk or its failure mode. This drives that branch.
    """
    bad = malformed_synthetic_rule()
    g = IrAst(rules=IrSeq(bad), start=f"{SYNTHETIC_PREFIX}bad")
    tables = compile_tables(g)
    rid = tables.decode.rule_ids[f"{SYNTHETIC_PREFIX}bad"]
    fold = ModelFold.from_config({})
    assert fold.run_ok(tables, rid) is False


def test_run_ok_false_when_transitive_leaf_is_a_config_rule():
    """The unit_rid passed in names no config rule directly ('__outer' isn't a
    config key) — only the leaf two hops down ('digit') is. run_ok must still
    block, proving it consults the full transitive leaf set, not just the
    rule named by unit_rid itself."""
    g = nested_synthetic_grammar()
    tables = compile_tables(g)
    outer_rid = tables.decode.rule_ids[f"{SYNTHETIC_PREFIX}outer"]
    fold = ModelFold.from_config({"digit": RuleFold("value_str", dict, 0, ())})
    assert fold.run_ok(tables, outer_rid) is False


def test_run_ok_true_when_transitive_leaf_untracked():
    """Same nested-synthetic structure, but the leaf carries no config entry —
    the run is safe to collapse."""
    g = nested_synthetic_grammar()
    tables = compile_tables(g)
    outer_rid = tables.decode.rule_ids[f"{SYNTHETIC_PREFIX}outer"]
    fold = ModelFold.from_config({})
    assert fold.run_ok(tables, outer_rid) is True


def test_ambiguous_input_folds_deterministically(arithmetic):
    """parse_first under collapsed tables equals the plain-tables fold output."""
    text = "ab1+cd2*34/x9-z=result0\n"
    collapsed_model = arithmetic.parse(text)
    plain_model = arithmetic.fold.apply(
        parse_first(prod(arithmetic).instance_grammar, text)
    )
    assert collapsed_model.dump() == plain_model.dump()
    assert collapsed_model.to_text() == plain_model.to_text() == text


# ── run-collapse licence smoke over the sequence text fold ──────────────


def test_run_collapsed_leaf_text_reads_identically(arithmetic):
    """A collapsed multi-char run leaf yields the same field text (probe b)."""
    model = arithmetic.parse("abc1=z\n")
    ident = model.root_item[0].expr.term
    assert ident.lower == "a"
    assert ident.head == "bc1"


def test_fold_value_str_via_hand_tree():
    """value_str folds to ctor(value=<all consumed chars under the node>)."""
    fold = ModelFold.from_config({"w": RuleFold("value_str", dict, 0, ())})
    node = ParseTree(IrRuleRef("w"), IrSeq(IrLiteral("a"), IrLiteral("bc")))
    assert fold.apply(node) == {"value": "abc"}


def test_discard_is_a_barrier_and_never_calls_its_constructor():
    """Both engines recognize a discarded wrapper without building/leaking it."""

    def forbidden(**_kwargs: object) -> object:
        raise AssertionError("discard constructor was called")

    def root(**kwargs: object) -> object:
        return {"noise": kwargs.get("noise")}

    compiled = compile_text('root ::= noise\nnoise ::= word\nword ::= "a"\n')
    fold = ModelFold(
        IrMap(
            IrTuple(
                IrRuleRef("root"),
                ModelBody(
                    "sequence",
                    IrLambda(root),
                    1,
                    (FieldFold(0, "model", "noise", 1),),
                ),
            ),
            IrTuple(
                IrRuleRef("noise"), ModelBody("discard", IrLambda(forbidden), 0, ())
            ),
            IrTuple(IrRuleRef("word"), ModelBody("value_str", IrLambda(dict), 0, ())),
        )
    )
    product = _model_product(compiled.codegen_grammar, fold)
    expected = {"noise": None}
    assert earley_model(product.instance_grammar, "a", fold, product.tables) == expected
    assert pda_model(product.pda, "a", fold) == expected


# ── ModelBody / ModelFold — the IR-native body-table ─────────────────────


def test_model_body_of_bake_round_trips_sequence():
    """ModelBody.of(rf).bake() is runtime-identical to rf for a sequence body."""
    rf = RuleFold("sequence", dict, 2, (FieldFold(0, "model", "a", 1),))
    baked = ModelBody.of(rf).bake()
    assert baked.kind == rf.kind
    assert baked.n_items == rf.n_items
    assert baked.fields == rf.fields
    assert baked.fast == rf.fast
    assert baked.ctor is rf.ctor


def test_model_body_of_bake_round_trips_value_str():
    """Same round trip for a value_str body."""
    rf = RuleFold("value_str", dict, 0, ())
    baked = ModelBody.of(rf).bake()
    assert baked.kind == rf.kind
    assert baked.n_items == rf.n_items
    assert baked.fields == rf.fields
    assert baked.ctor is rf.ctor


def test_model_body_of_bake_alternation_ctor_is_not_the_original():
    """An alternation body's ctor is IrNone in between — bake() hands back a
    stand-in constructor (_alt_ctor), never the original rf.ctor object, but
    the metadata is preserved."""
    rf = RuleFold("alternation", dict, 0, ())
    body = ModelBody.of(rf)
    assert body.ctor is IrNone
    baked = body.bake()
    assert baked.ctor is not rf.ctor
    assert baked.kind == rf.kind
    assert baked.n_items == rf.n_items
    assert baked.fields == rf.fields
    assert baked.fast == rf.fast


def test_model_fold_from_config_round_trips_baked():
    """ModelFold.from_config(cfg).baked == cfg round-trips a small config."""
    cfg = {
        "r": RuleFold("sequence", dict, 1, (FieldFold(0, "text", "a", 1),)),
        "w": RuleFold("value_str", dict, 0, ()),
    }
    assert ModelFold.from_config(cfg).baked == cfg


def test_model_fold_bodies_is_the_passed_ir_map():
    """ModelFold(bodies).bodies is the exact IrMap passed to the constructor."""
    bodies = IrMap(
        IrTuple(IrRuleRef("r"), ModelBody.of(RuleFold("value_str", dict, 1, ())))
    )
    fold = ModelFold(bodies)
    assert fold.bodies is bodies


# ── ModelBody.bake — the channel adapter for non-IrLambda IR bodies ──────


def test_model_body_bakes_a_channel_ir_body_ctor():
    """A non-IrLambda IR body ctor bakes to a kwargs→channel adapter: the fold
    calls ctor(**kwargs); the body reads IrArg positions in fields order."""
    body = ModelBody("sequence", IrArg(0), 1, (FieldFold(0, "text", "a", 1),))
    ctor = body.bake().ctor
    assert ctor(a="hello") == "hello"


def test_model_body_channel_ctor_fills_omitted_optional_with_ir_none():
    """An optional field omitted from kwargs arrives as IrNone on the channel
    (a body branches on absence by IrNoneType, since IrNone is truthy)."""
    body = ModelBody(
        "sequence",
        IrArgs(),
        2,
        (FieldFold(0, "text", "a", 1), FieldFold(1, "model", "b", 0)),
    )
    ctor = body.bake().ctor
    assert tuple(cast("tuple[object, ...]", ctor(a="x"))) == ("x", IrNone)  # b → IrNone


def test_model_body_channel_ctor_value_str_reads_the_value_kwarg():
    """A value_str IR body reads the sole ``value`` kwarg as its channel."""
    body = ModelBody("value_str", IrArg(0), 0, ())
    ctor = body.bake().ctor
    assert ctor(value="v") == "v"


def test_model_body_channel_ctor_empty_arm_is_an_empty_channel():
    """A fieldless sequence body evaluates over an empty channel (empty arm)."""
    body = ModelBody("sequence", IrArgs(), 0, ())
    ctor = body.bake().ctor
    assert not tuple(cast("tuple[object, ...]", ctor()))


def test_model_body_ir_lambda_stays_the_identity_kwargs_ctor():
    """An IrLambda body bakes to its wrapped kwargs-taking callable unchanged."""

    def marker(**kw: object) -> dict[str, object]:
        return kw

    body = ModelBody("sequence", IrLambda(marker), 1, (FieldFold(0, "text", "a", 1),))
    assert body.bake().ctor is marker


# ── a required field whose rule matched its EMPTY arm ─────────────────────


def test_required_field_matching_the_empty_arm_folds_to_explicit_none():
    """A required ref whose rule matched its empty arm binds None, not nothing.

    ``t = "" / tr / ts`` over ``"x"``: ``t`` matches the empty arm and folds to
    no sub-model. The field must carry an explicit ``None`` — the record the
    PDA's trusted build produces via ``parts.get`` — rather than being dropped
    from the kwargs, which made the checked constructor refuse the engine's own
    parse with a missing-required-field error. RFC 5234's bare ``%x31`` (a
    num-val with no range and no dot-tail) is exactly this shape.
    """
    src = 'a = %s"x" t\r\nt = "" / tr / ts\r\ntr = %s"-" %s"h"\r\nts = 1*%s"."\r\n'
    cg = compile_text(src, cache_key="fold-empty-arm-field", flavour="abnf")
    product = _model_product(cg.codegen_grammar, cg.fold)
    via_earley = earley_model(product.instance_grammar, "x", cg.fold, product.tables)
    via_pda = pda_model(product.pda, "x", cg.fold)
    assert via_earley == via_pda, "the two engines must build the same record"
    # A record IS its field tuple; `A` binds one field (`t`), read by index.
    assert via_earley[0] is None
    assert via_earley.to_text() == "x"
