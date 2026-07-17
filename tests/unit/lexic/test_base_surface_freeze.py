"""Characterization freeze: the surviving public model surface, on the spine.

Task 0 of ``zzz_current_work/260716-ir-native/PLAN_v4.md`` recorded this
module against the pydantic-backed :class:`~lexic.base.GrammarModel`; Task 1
(the record spine, ruling 9: models live on ``IrNamedTuple``) ported it. It
remains the companion to the golden JSON fixtures
(``tests/golden_fixtures.py``, ``tests/integration/test_golden_parity.py``):
the goldens pin per-grammar *values*; this module pins the *surface* those
values are read through.

FREEZE CHECKLIST — how the R4 pydantic-surface inventory resolved at the
Task-1 cutover (every item either survives, ported below, or died with its
exact target):

- The validated keyword constructor → the record constructor (pinned below;
  a missing required field now raises ``TypeError`` — trusted construction
  until Task 3 wires ``FieldValidationError``).
- ``__get_pydantic_core_schema__`` / ``_joint_dump`` / ``__schema_joint__``
  / ``IncEx`` / ``SerializationInfo`` — the schema-joint apparatus: DELETED
  with the spine (PLAN.md §NON-CONCERNS). The joint cross-check tests died
  with those exact targets; the *behavior* they guarded (runtime-complete
  dumping) is pinned directly below.
- **F-DUMP-1**: pydantic's ``model_dump()`` erased an arm instance riding a
  field annotated with its field-less abstract alternation parent to ``{}``.
  The native dump serializes by RUNTIME type (ruling 12) — the erasure is
  GONE, pinned by ``test_model_dump_does_not_erase_an_abstract_typed_arm_
  field`` and cross-checked against an independent hand-rolled runtime-type
  walker below.
- ``fast_construct()``'s pydantic refusal surface (validators / post-init /
  config / private attributes) — DIED with pydantic; the licence is now
  trivially granted (pinned in ``tests/unit/lexic/test_base.py``).
- ``model_fields`` — gone; the slot → field mapping reads through the
  public :meth:`~lexic.base.GrammarModel.bound_fields` (pinned below).
- ``model_dump(exclude=...)`` — :meth:`~lexic.base.GrammarModel.
  semantic_dump` is native (same top-level-only exclusion depth, R2-5 —
  pinned below).
- ``model_rebuild`` — a no-op shim for the old codegen loader until the
  runtime-synthesis flip (pinned in ``test_base.py``).
- The FORWARD-LOOKING ACCEPTANCES recorded at Task 0 are now the live
  surface, pinned below: models are hashable with type-aware equality
  (settled 4 — both halves hold), and expose the tuple surface (iterable,
  sized, indexable — ruling 9 / demo_01 F-SPINE-5, accepted).
"""

from __future__ import annotations

import pytest

from lexic.base import GrammarModel
from lexic.compile import compile_from_path
from lexic.ir.bind import IrBind
from tests.paths import GROUND_TRUTH

# ── construction ──────────────────────────────────────────────────────────


def test_construct_accepts_valid_kwargs():
    """The record constructor builds an instance from field kwargs."""
    cg = compile_from_path(GROUND_TRUTH / "list.gbnf")
    model = cg.parse("- apple\n")
    assert isinstance(model, GrammarModel)


def test_construct_raises_type_error_on_missing_field():
    """Hand construction with a missing required field raises TypeError —
    the trusted-construction interim contract (checked construction, raising
    FieldValidationError, is Task 3's separate wiring)."""
    cg = compile_from_path(GROUND_TRUTH / "list.gbnf")
    model = cg.parse("- apple\n")
    cls = type(model)
    with pytest.raises(TypeError):
        cls()


# ── to_text / _emit_parts ────────────────────────────────────────────────


def test_to_text_round_trips_a_compiled_instance():
    """to_text() reproduces the parsed source verbatim."""
    cg = compile_from_path(GROUND_TRUTH / "arithmetic.gbnf")
    text = "x=1\n"
    assert cg.parse(text).to_text() == text


def test_to_text_recurses_through_nested_models_and_lists():
    """to_text() (backed by _emit_parts()'s per-model item walk) recurses
    into nested models, flattens models-mode fields, and emits unbound
    structural literals — pinned through the public surface, on a grammar
    whose root is a hoisted "+"-quantified group (a models field) of records
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


# ── equality + hashing: settled 4, both halves now live ──────────────────


def test_same_class_equal_payload_compares_equal():
    """Two independent parses of the same text compare equal."""
    cg = compile_from_path(GROUND_TRUTH / "arithmetic.gbnf")
    assert cg.parse("x=1\n") == cg.parse("x=1\n")


def test_cross_class_equal_payload_compares_unequal():
    """Distinct classes never compare equal — the type-aware half of
    settled 4, preserved from pydantic (whose __eq__ also checked the type);
    detailed cross-class pins live in test_base.py (_PairA/_PairB)."""
    cg = compile_from_path(GROUND_TRUTH / "json_ws.gbnf")
    model = cg.parse('{"a":1}')
    obj = getattr(model, "object")
    assert model != obj


def test_models_are_hashable_consistently_with_equality():
    """Models are hashable (settled 4's NEW half — pydantic-era models
    raised TypeError): equal parses share a hash and coexist in a set."""
    cg = compile_from_path(GROUND_TRUTH / "arithmetic.gbnf")
    one = cg.parse("x=1\n")
    two = cg.parse("x=1\n")
    assert hash(one) == hash(two)
    assert len({one, two}) == 1


def test_models_expose_the_tuple_surface():
    """Models ARE tuples (ruling 9, accepted at Task 0 as a forward-looking
    acceptance): iterable, sized, indexable — the record spine's surface."""
    cg = compile_from_path(GROUND_TRUTH / "arithmetic.gbnf")
    model = cg.parse("x=1\n")
    assert isinstance(model, tuple)
    assert len(model) == len(model.model_dump())


# ── in-process model_dump() dict equality (the stricter medium, C12) ──────


def test_model_dump_dict_equality_across_independent_parses():
    """Two independent parses of the same text produce == model_dump() dicts,
    compared as live Python objects (no JSON round trip) — the stricter
    medium settled 12 requires beside the JSON goldens, since JSON hides
    tuple-vs-list distinctions the native dump normalizes (tuples re-emit
    as lists)."""
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


# ── F-DUMP-1 resolved: the native dump is runtime-complete (ruling 12) ─────


def _walk_runtime(node: object) -> object:
    """A hand-rolled runtime-type-driven dump — the cross-check reference.

    For every field of a model, ``getattr`` and recurse into
    :class:`GrammarModel` values, walk tuples element-wise into lists, pass
    everything else through verbatim. Independent of the spine's own
    ``model_dump()`` walker so the two cross-check each other rather than
    one trivially validating itself.
    """
    if isinstance(node, GrammarModel):
        return {name: _walk_runtime(getattr(node, name)) for name in type(node)._fields}
    if isinstance(node, tuple):
        return [_walk_runtime(item) for item in node]
    return node


def test_model_dump_does_not_erase_an_abstract_typed_arm_field():
    """F-DUMP-1 resolved: an arm instance riding a field whose pydantic-era
    annotation was its field-less abstract alternation parent dumps IN FULL —
    the native dump serializes by runtime type, never by declared schema."""
    cg = compile_from_path(GROUND_TRUTH / "arithmetic.gbnf")
    model = cg.parse("6=k\t \n")
    item = getattr(model, "root_item")[0]
    assert item.model_dump()["term"] == item.term.model_dump()
    assert item.model_dump()["term"] != {}


def test_model_dump_matches_a_runtime_type_walker():
    """The native dump matches the independent hand-rolled runtime-type
    walker on a real ground-truth grammar (the shape that erased under
    pydantic's declared-schema serializer)."""
    cg = compile_from_path(GROUND_TRUTH / "arithmetic.gbnf")
    model = cg.parse("6=k\t \n")
    assert model.model_dump() == _walk_runtime(model)


def test_model_dump_distinguishes_inputs_the_erasure_conflated():
    """The measured F-DUMP-1 clincher, inverted: under pydantic,
    model_dump("6=k...") == model_dump("9=z...") because the erased arm
    subtrees carried the distinguishing content. The runtime-complete dump
    keeps them distinct."""
    cg = compile_from_path(GROUND_TRUTH / "arithmetic.gbnf")
    assert cg.parse("6=k\t \n").model_dump() != cg.parse("9=z\t \n").model_dump()
