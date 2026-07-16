"""Characterization freeze: the surviving public model surface, TODAY.

Task 0 of ``zzz_current_work/260716-ir-native/PLAN_v4.md`` (the unified
``compile/`` subsystem effort). This module pins observed behavior of the
CURRENT pydantic-backed :class:`~lexic.base.GrammarModel` so later tasks —
which replace the record spine wholesale (ruling 9: models move onto
``IrNamedTuple``) — have a concrete, runnable oracle for what must (and must
not) survive the cutover. It is a companion to the golden JSON fixtures
(``tests/golden_fixtures.py``, ``tests/integration/test_golden_parity.py``):
the goldens pin per-grammar *values*; this module pins the *surface* those
values are read through.

FREEZE CHECKLIST — the pydantic-surface inventory (V3_REVIEW.md finding R4,
carried from ``PLAN.md``'s adversarial review). Every one of these is either
pinned by a test below, or named here as a documented gap the spine
rewrite (Task 1) must consciously retire:

- ``model_validate`` / the validated keyword constructor (pinned below).
- ``__get_pydantic_core_schema__`` + ``GetCoreSchemaHandler`` + ``CoreSchema``
  + ``core_schema.no_info_plain_validator_function`` /
  ``plain_serializer_function_ser_schema`` / ``any_schema`` — the
  schema-joint path (``lexic/base.py``). Pydantic-only apparatus; dies
  wholesale with the spine (PLAN.md §NON-CONCERNS) — NOT pinned via its own
  API surface here, but its *consequence* for dumping (F-DUMP-1, below) is.
- ``IncEx`` / ``SerializationInfo`` — typing support for ``_joint_dump``.
  Same fate as the schema-joint path.
- **F-DUMP-1 (coordinator finding, mid-Task-0 addendum):**
  ``model_dump()`` is declared-schema-driven — an arm instance riding a
  field annotated with its field-less abstract alternation PARENT
  serializes as ``{}`` (the whole subtree erased); pinned by
  ``test_model_dump_erases_an_abstract_typed_arm_field`` below.
  ``model_dump(serialize_as_any=True)`` (the ``runtime_dump``/
  ``runtime_semantic_dump`` golden pair, ``tests/golden_fixtures.py``)
  recovers the full subtree instead — pinned equal to a hand-rolled
  runtime-type walker by
  ``test_serialize_as_any_matches_a_runtime_type_walker`` and, through a
  hand-built schema-joint boundary (no GT grammar reaches the 64-rule
  joint stride),
  ``test_serialize_as_any_matches_a_runtime_type_walker_through_a_joint``
  — which also records an empirical correction to the addendum's initial
  worry: the flag does NOT degrade through a joint, because pydantic-core
  bypasses the joint's custom ``_joint_dump`` serializer entirely under
  ``serialize_as_any=True`` rather than calling it without the flag.
- ``__pydantic_post_init__`` / ``__pydantic_decorators__`` /
  ``__private_attributes__`` / ``model_config`` — the ``fast_construct()``
  licence checks (pinned in ``tests/unit/lexic/test_base.py``, not
  duplicated here).
- ``__pydantic_fields_set__`` / ``__pydantic_extra__`` /
  ``__pydantic_private__`` — ``_from_parts()``'s raw ``__dict__`` build
  (pinned in ``tests/unit/lexic/test_base.py``).
- ``model_rebuild`` + ``__pydantic_complete__`` — codegen's
  ``_rebuild_leaf_first`` (``src/lexic/codegen/__init__.py``), asserted in
  ``tests/unit/lexic/codegen/test_init_new_codegen.py``.
- ``dir(BaseModel)`` feeding ``_RESERVED_FIELD_NAMES``
  (``src/lexic/codegen/binding.py``) — R2-4 measured the unmangle delta
  (the whole ``model_*``/``construct``/``copy``/``dict``/``json``/``schema``/
  ``validate``/... family) and the newly-reserved spine surface
  (``bind, bound, bound_type, children, count, eval, index, rebuild``);
  re-pinned as its own drift test when Task 3 lands the re-pin, not here.
- ``model_fields`` — read by :meth:`~lexic.base.GrammarModel.bound_fields`
  (pinned below and in ``test_base.py``), ``fast_construct()``, and
  ``compile.py``'s ``_fast_ctor``.
- ``model_dump(exclude=...)`` — :meth:`~lexic.base.GrammarModel.semantic_dump`
  (pinned below: top-level-only exclusion depth, R2-5).
- ``ConfigDict`` / ``Field`` / ``PrivateAttr`` / ``field_validator`` — the
  ``fast_construct()`` refusal surface, exercised directly in
  ``tests/unit/lexic/test_base.py`` (the sole test file importing pydantic
  symbols, per R6 — its exact-target tests are what die with the spine).

FORWARD-LOOKING ACCEPTANCES (settled design, PLAN_v4.md) — stated here as
notes for the implementer of Task 1, NOT tested, because they cannot be
demonstrated on pydantic models:

- **Tuple surface** (settled design 9/ruling 9, demo_01 finding F-SPINE-5):
  once models live on ``IrNamedTuple``, they become iterable, sized,
  orderable, and containment-testable, and gain ``count``/``index`` (hence
  those names joining the reserved set, R2-4). A hypothetical zero-field
  record is falsy. None of this exists on today's pydantic models — see
  ``test_todays_models_do_not_expose_a_tuple_surface`` below, which pins the
  ABSENCE as today's starting point.
- **Hash-consistent type-aware equality** (settled design 4): today's
  generated classes are plain (non-frozen) pydantic models and are
  UNHASHABLE (see ``test_todays_models_are_unhashable`` below). Equality
  IS already type-aware today (pydantic's own ``__eq__`` checks
  ``type(self) is type(other)`` first) — that half of settled 4 already
  holds and is pinned below; hashability is the new half Task 1 adds.
- ``_child_attrs`` / dispatch admission (settled design 13, ruling 9's
  ``children()`` consequence) has no analogue on a pydantic model at all —
  nothing to freeze.
"""

from __future__ import annotations

from typing import ClassVar

import pydantic
import pytest

from lexic.base import GrammarModel
from lexic.compile import compile_from_path
from lexic.ir.bind import IrBind
from lexic.ir.nodes import IrAlternation, IrItem, IrLiteral, IrRule, IrSequence
from tests.paths import GROUND_TRUTH

# ── construction ──────────────────────────────────────────────────────────


def test_construct_accepts_valid_kwargs():
    """The validated constructor builds an instance from field kwargs."""
    cg = compile_from_path(GROUND_TRUTH / "list.gbnf")
    model = cg.parse("- apple\n")
    assert isinstance(model, GrammarModel)


def test_construct_raises_pydantic_validation_error_on_missing_field():
    """TODAY, hand construction with a missing required field raises pydantic's
    own ValidationError — not FieldValidationError (that vocabulary is a stub
    until Task 3 wires real checked construction, PLAN.md finding R3)."""
    cg = compile_from_path(GROUND_TRUTH / "list.gbnf")
    model = cg.parse("- apple\n")
    cls = type(model)
    with pytest.raises(pydantic.ValidationError):
        cls()


# ── to_text / _emit_parts ────────────────────────────────────────────────


def test_to_text_round_trips_a_compiled_instance():
    """to_text() reproduces the parsed source verbatim."""
    cg = compile_from_path(GROUND_TRUTH / "arithmetic.gbnf")
    text = "x=1\n"
    assert cg.parse(text).to_text() == text


def test_to_text_recurses_through_nested_models_and_lists():
    """to_text() (backed by _emit_parts()'s per-model item walk) recurses
    into nested models, flattens list-of-model fields, and emits unbound
    structural literals — pinned through the public surface, on a grammar
    whose root is a hoisted "+"-quantified group (a list field) of records
    that themselves nest a model field (ws) and a literal ("=")."""
    cg = compile_from_path(GROUND_TRUTH / "arithmetic.gbnf")
    text = "x=1\ny=2\n"
    model = cg.parse(text)
    assert model.to_text() == text


# ── to_grammar ────────────────────────────────────────────────────────────


def test_to_grammar_gbnf_contains_rule_name():
    """to_grammar() (default gbnf) contains the instance's own rule name."""
    cg = compile_from_path(GROUND_TRUTH / "arithmetic.gbnf")
    model = cg.parse("x=1\n")
    assert str(model.__grammar__.name) in model.to_grammar()


def test_to_grammar_abnf_contains_rule_name():
    """to_grammar("abnf") also contains the instance's own rule name — the
    flavour argument is not gbnf-only."""
    cg = compile_from_path(GROUND_TRUTH / "arithmetic.gbnf")
    model = cg.parse("x=1\n")
    assert str(model.__grammar__.name) in model.to_grammar("abnf")


# ── semantic_dump: top-level-only exclusion depth (R2-5) ─────────────────


def test_semantic_dump_excludes_only_the_receivers_own_non_semantic_fields():
    """semantic_dump() excludes a bound field whose own bind is non-semantic,
    at the receiving instance's own level."""
    cg = compile_from_path(GROUND_TRUTH / "json_ws.gbnf")
    obj = getattr(cg.parse('{"a":1}'), "object")
    dumped = obj.semantic_dump()
    assert "ws" not in dumped
    assert "ws2" not in dumped


def test_semantic_dump_does_not_recurse_into_nested_models_own_exclusions():
    """R2-5, empirical: a nested model's OWN non-semantic fields remain in the
    dump — semantic_dump()'s exclusion is top-level-only, not a deep walk."""
    cg = compile_from_path(GROUND_TRUTH / "json_ws.gbnf")
    obj = getattr(cg.parse('{"a":1}'), "object")
    dumped = obj.semantic_dump()
    assert "object_item2" in dumped
    assert "ws" in dumped["object_item2"]


def test_semantic_dump_equals_model_dump_when_receiver_has_no_own_noise_field():
    """A model whose only bound field is itself semantic (no direct
    non-semantic bind) has semantic_dump() == model_dump() — exclusion never
    reaches down through the field's own value."""
    cg = compile_from_path(GROUND_TRUTH / "json_ws.gbnf")
    model = cg.parse('{"a":1}')
    assert model.semantic_dump() == model.model_dump()


# ── equality: type-aware today (pydantic default), pinned as settled-4's
#    half that already holds ────────────────────────────────────────────


class _PairA(GrammarModel):
    """a ::= "x" — single-field value_str shape, for cross-class eq tests."""

    __grammar__: ClassVar[IrRule] = IrRule(
        "a", IrAlternation(IrSequence(IrItem(IrLiteral("x"))))
    )
    value: str


class _PairB(GrammarModel):
    """b ::= "x" — identical shape to _PairA, distinct class."""

    __grammar__: ClassVar[IrRule] = IrRule(
        "b", IrAlternation(IrSequence(IrItem(IrLiteral("x"))))
    )
    value: str


def test_same_class_equal_payload_compares_equal():
    """Two instances of the same class with equal fields compare equal."""
    assert _PairA(value="x") == _PairA(value="x")


def test_cross_class_equal_payload_compares_unequal():
    """Two DISTINCT classes with an identical field name/value compare
    UNEQUAL today (pydantic's __eq__ checks type(self) is type(other) first).
    Settled design 4 keeps this as the new record spine's own contract."""
    assert _PairA(value="x") != _PairB(value="x")


def test_todays_models_are_unhashable():
    """TODAY's generated classes are plain (non-frozen) pydantic models and
    are unhashable — settled design 4's hash-consistency clause is new
    behavior Task 1 adds, not something being preserved."""
    cg = compile_from_path(GROUND_TRUTH / "arithmetic.gbnf")
    model = cg.parse("x=1\n")
    with pytest.raises(TypeError):
        hash(model)


def test_todays_models_do_not_expose_a_tuple_surface():
    """TODAY's models are not iterable/sized/indexable — the tuple surface
    (settled design 9, demo_01 F-SPINE-5) is new with the IrNamedTuple spine."""
    cg = compile_from_path(GROUND_TRUTH / "arithmetic.gbnf")
    model = cg.parse("x=1\n")
    assert not hasattr(model, "__len__")
    assert not hasattr(model, "__getitem__")


# ── in-process model_dump() dict equality (the stricter medium, C12) ──────


def test_model_dump_dict_equality_across_independent_parses():
    """Two independent parses of the same text produce == model_dump() dicts,
    compared as live Python objects (no JSON round trip) — the stricter
    medium settled 12 requires beside the JSON goldens, since JSON hides
    tuple-vs-list and IrInt-vs-int distinctions that don't yet exist on
    pydantic-era models but will after the spine rewrite."""
    cg = compile_from_path(GROUND_TRUTH / "json_ws.gbnf")
    first = cg.parse('{"a":1}').model_dump()
    second = cg.parse('{"a":1}').model_dump()
    assert first == second
    assert first is not second


# ── bound_fields() ────────────────────────────────────────────────────────


def test_bound_fields_reflects_a_real_compiled_grammars_binding():
    """bound_fields() on a real compiled class matches the grammar's binding:
    one entry per bound item slot, semantic flags intact."""
    cg = compile_from_path(GROUND_TRUTH / "json_ws.gbnf")
    obj_cls = type(getattr(cg.parse('{"a":1}'), "object"))
    bound = obj_cls.bound_fields()
    semantics = {name: bind.semantic for name, bind in bound.values()}
    assert semantics["ws"] is False
    assert semantics["ws2"] is False
    assert semantics["object_item2"] is True


def test_bound_fields_metadata_is_irbind_instances():
    """Every value in bound_fields() carries a real IrBind, not a stand-in."""
    cg = compile_from_path(GROUND_TRUTH / "arithmetic.gbnf")
    cls = type(cg.parse("x=1\n"))
    for _name, bind in cls.bound_fields().values():
        assert isinstance(bind, IrBind)


# ── F-DUMP-1: model_dump() erasure vs. serialize_as_any ────────────────────


def _walk_runtime(node: object) -> object:
    """A hand-rolled runtime-type-driven dump — the cross-check reference.

    For every field in ``type(node).model_fields``, ``getattr`` and recurse
    into ``GrammarModel`` values, walk lists element-wise, pass everything
    else through verbatim. Independent of
    :func:`tests.golden_fixtures.runtime_dump` (which uses pydantic's own
    ``serialize_as_any=True``) so the two can be cross-checked against each
    other rather than one trivially validating itself.
    """
    if isinstance(node, GrammarModel):
        return {
            name: _walk_runtime(getattr(node, name)) for name in type(node).model_fields
        }
    if isinstance(node, list):
        return [_walk_runtime(item) for item in node]
    return node


def test_model_dump_erases_an_abstract_typed_arm_field():
    """F-DUMP-1: an arm instance riding a field typed as its field-less
    abstract alternation parent serializes as {} under plain model_dump() —
    the whole subtree erased, since pydantic-core builds the field's
    serializer off the DECLARED annotation, not the runtime type."""
    cg = compile_from_path(GROUND_TRUTH / "arithmetic.gbnf")
    model = cg.parse("6=k\t \n")
    item = getattr(model, "root_item")[0]
    assert item.model_dump()["term"] == {}
    assert item.term.model_dump() != {}


def test_serialize_as_any_recovers_the_erased_subtree():
    """model_dump(serialize_as_any=True) recovers what plain model_dump()
    erases (F-DUMP-1's fix, the golden's "runtime_dump" form)."""
    cg = compile_from_path(GROUND_TRUTH / "arithmetic.gbnf")
    model = cg.parse("6=k\t \n")
    item = getattr(model, "root_item")[0]
    assert item.model_dump(serialize_as_any=True)["term"] == item.term.model_dump()


def test_serialize_as_any_matches_a_runtime_type_walker():
    """serialize_as_any=True matches the hand-rolled runtime-type walker on a
    real ground-truth grammar (the ordinary, non-joint erasure case)."""
    cg = compile_from_path(GROUND_TRUTH / "arithmetic.gbnf")
    model = cg.parse("6=k\t \n")
    assert model.model_dump(serialize_as_any=True) == _walk_runtime(model)


class _JointValue(GrammarModel):
    """A field-less abstract alternation parent — erases under plain dump."""


class _JointStrLeaf(_JointValue):
    """A concrete arm of _JointValue."""

    v: str


class _JointMid(GrammarModel):
    """A schema-joint-flagged class whose OWN field is abstract-typed —
    the shape that would erase under plain model_dump()."""

    __schema_joint__: ClassVar[bool] = True
    value: _JointValue


class _JointTopContainer(GrammarModel):
    """References the joint through a plain field, as codegen would for a
    deep grammar (c.gbnf, vyx.gbnf) crossing a stride boundary."""

    mid: _JointMid


def test_serialize_as_any_matches_a_runtime_type_walker_through_a_joint():
    """Cross-check pinning the joint caveat: no GT grammar reaches the
    64-rule schema-joint stride, so this hand-built minimal joint stands in.
    Empirically, serialize_as_any=True does NOT degrade through the joint —
    pydantic-core bypasses the joint's custom _joint_dump serializer
    entirely under serialize_as_any (verified by tracing _joint_dump calls:
    zero calls under serialize_as_any=True, one call without it), rather
    than calling it without forwarding the flag. This corrects the
    addendum's initial worry that _joint_dump's non-forwarding of
    serialize_as_any would degrade the runtime_dump golden form."""
    top = _JointTopContainer(mid=_JointMid(value=_JointStrLeaf(v="x")))
    assert top.model_dump() == {"mid": {"value": {}}}  # the erasure, for contrast
    assert top.model_dump(serialize_as_any=True) == _walk_runtime(top)
    assert top.model_dump(serialize_as_any=True) == {"mid": {"value": {"v": "x"}}}
