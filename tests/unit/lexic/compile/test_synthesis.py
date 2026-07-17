"""Tests for compile/synthesis.py — runtime model-class synthesis.

No codegen equivalent exists (source emission is gone), so these tests pin
the spine :func:`~lexic.compile.synthesis.synthesize` builds directly: class
identity (module/qualname/``__grammar__``/``__binds__``), MI base ordering,
per-``kind`` field shape, optional-field defaults, and construction/
round-trip behavior on the resulting :class:`~lexic.base.GrammarModel`
subclasses.
"""

from __future__ import annotations

from lexic.base import GrammarModel
from lexic.compile import canonical_grammar, compile_text
from lexic.compile.binding import RuleBinding, compute_binding
from lexic.compile.passes import build_codegen_grammar
from lexic.compile.synthesis import synthesize
from lexic.grammars.gbnf import GBNF_FLAVOUR
from lexic.ir.base import IrSeq
from lexic.ir.nodes import (
    IrAlternation,
    IrAst,
    IrItem,
    IrLiteral,
    IrRule,
    IrRuleRef,
    IrSequence,
)


def _synth(
    text: str, stem: str = "m"
) -> tuple[dict[str, type], IrAst, list[RuleBinding]]:
    """Run the front half then synthesize: canonical -> codegen grammar -> binding -> classes.

    :param text: GBNF grammar source.
    :param stem: The synthetic ``__module__`` stem.
    :returns: ``(classes, codegen_grammar, binding)``.
    """
    canonical = canonical_grammar(text, GBNF_FLAVOUR)
    codegen_grammar = build_codegen_grammar(canonical)
    binding = compute_binding(codegen_grammar)
    classes = synthesize(codegen_grammar, binding, stem)
    return classes, codegen_grammar, binding


def _by_name(binding: list[RuleBinding]) -> dict[str, RuleBinding]:
    """Index a binding view by rule name."""
    return {b.rule_name: b for b in binding}


# ── class-set identity ──────────────────────────────────────────────────


def test_synthesize_returns_one_class_per_binding():
    """The returned keys match the binding view's class names, exactly."""
    classes, _grammar, binding = _synth('root ::= "hi"\n')
    assert set(classes) == {b.class_name for b in binding}


def test_synthesize_classes_are_grammar_model_subclasses():
    """Every synthesized class descends from GrammarModel."""
    classes, _grammar, _binding = _synth('root ::= "hi"\n')
    assert all(issubclass(cls, GrammarModel) for cls in classes.values())


def test_synthesize_class_carries_its_own_rule_as_grammar():
    """__grammar__ is the class's own IrRule from the codegen grammar."""
    classes, codegen_grammar, binding = _synth('root ::= "hi"\n')
    rules = {str(r.name): r for r in codegen_grammar.rules}
    for bound in binding:
        cls = classes[bound.class_name]
        assert isinstance(cls.__grammar__, IrRule)
        assert cls.__grammar__ == rules[bound.rule_name]


def test_synthesize_module_and_qualname():
    """__module__ is generated.<stem>; __qualname__ is the class name."""
    classes, _grammar, _binding = _synth('root ::= "hi"\n', stem="probe_stem")
    for name, cls in classes.items():
        assert cls.__module__ == "generated.probe_stem"
        assert cls.__qualname__ == name


# ── __binds__ / bound_fields() ──────────────────────────────────────────


def test_synthesize_binds_table_is_a_direct_class_attribute():
    """__binds__ is written directly onto the class (no annotation resolution)."""
    classes, _grammar, _binding = _synth("root ::= word [0-9]*\nword ::= [a-z]+\n")
    assert "__binds__" in classes["Root"].__dict__


def test_synthesize_bound_fields_matches_the_binding_view():
    """bound_fields() returns slot -> (name, IrBind), matching the binding's fields."""
    classes, _grammar, binding = _synth("root ::= word [0-9]*\nword ::= [a-z]+\n")
    root_binding = _by_name(binding)["root"]
    expected = {
        ibind.item: (name, ibind) for name, ibind in root_binding.fields.items()
    }
    assert classes["Root"].bound_fields() == expected


# ── MI base ordering ─────────────────────────────────────────────────────


def _alt_text() -> str:
    """root -> a | b, a/b concrete unit-ref arms of the Root alternation."""
    return 'root ::= a | b\na ::= "x"\nb ::= "y"\n'


def test_synthesize_unit_arm_subclasses_its_alternation():
    """A rule that is a unit-ref arm of an alternation subclasses that class."""
    classes, _grammar, _binding = _synth(_alt_text())
    assert issubclass(classes["A"], classes["Root"])
    assert issubclass(classes["B"], classes["Root"])


def test_synthesize_parentless_rule_subclasses_grammar_model_directly():
    """A rule with no alternation parent subclasses GrammarModel directly."""
    classes, _grammar, binding = _synth(_alt_text())
    root_binding = _by_name(binding)["root"]
    assert root_binding.parent_class_names == ()
    assert classes["Root"].__bases__ == (GrammarModel,)


def test_synthesize_bases_follow_binding_parent_order():
    """A class's bases are exactly the classes named by its parent_class_names."""
    classes, _grammar, binding = _synth(_alt_text())
    a_binding = _by_name(binding)["a"]
    assert a_binding.parent_class_names == ("Root",)
    assert classes["A"].__bases__ == (classes["Root"],)


# ── kind-specific field shape ─────────────────────────────────────────────


def test_value_str_kind_has_single_implicit_value_field():
    """A value_str rule (no rulerefs) gets one implicit `value` field, no binds."""
    classes, _grammar, binding = _synth('root ::= "hi"\n')
    assert _by_name(binding)["root"].kind == "value_str"
    assert classes["Root"]._fields == ("value",)
    assert classes["Root"].bound_fields() == {}


def test_alternation_kind_is_field_less():
    """An alternation class has no fields at all and no binds."""
    classes, _grammar, binding = _synth(_alt_text())
    assert _by_name(binding)["root"].kind == "alternation"
    assert classes["Root"]._fields == ()
    assert classes["Root"].bound_fields() == {}


def test_sequence_kind_fields_match_bound_field_names_in_item_order():
    """A sequence class's _fields are its bound field names, in item order."""
    classes, _grammar, binding = _synth("root ::= word [0-9]*\nword ::= [a-z]+\n")
    root_binding = _by_name(binding)["root"]
    expected = tuple(
        name
        for _slot, (name, _bind) in sorted(
            {ibind.item: (n, ibind) for n, ibind in root_binding.fields.items()}.items()
        )
    )
    assert classes["Root"]._fields == expected


# ── optional-field defaults ───────────────────────────────────────────────


def test_optional_star_quantified_field_defaults_to_none():
    """A field whose item can match zero times (lo == 0) defaults to None;
    a required (lo == 1) sibling field on the same rule does not."""
    classes, _grammar, _binding = _synth("root ::= word [0-9]*\nword ::= [a-z]+\n")
    _make, defaults = classes["Root"].fast_construct()
    assert defaults.get("digit") is None
    assert "word" not in defaults


def test_empty_alternate_arm_forces_every_field_optional():
    """A rule with an empty alternate arm defaults its (otherwise required,
    unit-quantified) bound field to None — the empty-arm force, distinct from
    the lo == 0 case above. Hand-built codegen grammar: text authoring has no
    direct spelling for an in-place epsilon alternate arm (only quantifiers,
    which hoist to a helper rule instead — see the lo == 0 test)."""
    codegen_grammar = IrAst(
        IrSeq(
            IrRule(
                "s", IrAlternation(IrSequence(IrItem(IrRuleRef("x"))), IrSequence())
            ),
            IrRule("x", IrLiteral("x")),
        ),
        "s",
    )
    binding = compute_binding(codegen_grammar)
    classes = synthesize(codegen_grammar, binding, "empty_arm_probe")
    _make, defaults = classes["S"].fast_construct()
    assert defaults.get("x") is None
    inst = classes["S"]()
    assert inst.x is None
    assert inst.to_text() == ""


def test_models_mode_field_without_empty_arm_has_no_default():
    """A required (lo >= 1) models-mode field is not defaulted."""
    classes, _grammar, binding = _synth('root ::= (a | b)+\na ::= "x"\nb ::= "y"\n')
    root_binding = _by_name(binding)["root"]
    (name,) = root_binding.fields
    assert root_binding.fields[name].mode == "models"
    _make, defaults = classes["Root"].fast_construct()
    assert name not in defaults


# ── construction + behavior ───────────────────────────────────────────────


def test_construct_a_sequence_class_with_keyword_fields():
    """A sequence class builds via keyword construction like the fold uses."""
    classes, _grammar, _binding = _synth("root ::= word [0-9]*\nword ::= [a-z]+\n")
    inst = classes["Root"](word=classes["Word"](value="ab"), digit="123")
    assert inst.word.value == "ab"
    assert inst.digit == "123"


def test_construct_coerces_a_models_mode_list_to_a_hashable_tuple():
    """A list argument for a models-mode field coerces to a tuple (hashable)."""
    classes, _grammar, binding = _synth('root ::= (a | b)+\na ::= "x"\nb ::= "y"\n')
    root_binding = _by_name(binding)["root"]
    (name,) = root_binding.fields
    a_inst = classes["A"](value="x")
    inst = classes["Root"](**{name: [a_inst]})
    value = getattr(inst, name)
    assert isinstance(value, tuple)
    hash(inst)  # does not raise


def test_to_text_round_trips_a_synthesized_sequence_instance():
    """to_text() reconstructs the source text from a synthesized instance."""
    classes, _grammar, _binding = _synth("root ::= word [0-9]*\nword ::= [a-z]+\n")
    inst = classes["Root"](word=classes["Word"](value="ab"), digit="123")
    assert inst.to_text() == "ab123"


def test_model_dump_and_semantic_dump_behave_on_a_synthesized_instance():
    """model_dump keeps every field; semantic_dump drops non-semantic ones."""
    classes, _grammar, _binding = _synth(
        "# @non-semantic ws\nroot ::= word ws num\nword ::= [a-z]+\nnum ::= [0-9]+\n"
        "ws ::= [ ]*\n"
    )
    inst = classes["Root"](
        word=classes["Word"](value="ab"),
        ws=classes["Ws"](value=" "),
        num=classes["Num"](value="12"),
    )
    dumped = inst.model_dump()
    assert dumped == {
        "word": {"value": "ab"},
        "ws": {"value": " "},
        "num": {"value": "12"},
    }
    semantic = inst.semantic_dump()
    assert "ws" not in semantic
    assert semantic == {"word": {"value": "ab"}, "num": {"value": "12"}}


def test_synthesis_matches_end_to_end_compile_text_round_trip():
    """A grammar compiled through compile_text() parses and round-trips —
    cross-checking synthesis against the full public pipeline."""
    text = "root ::= word [0-9]*\nword ::= [a-z]+\n"
    cg = compile_text(text)
    inst = cg.parse("ab123")
    assert inst.to_text() == "ab123"
    assert inst.model_dump() == {"word": {"value": "ab"}, "digit": "123"}
