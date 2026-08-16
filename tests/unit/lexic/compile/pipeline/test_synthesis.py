"""Tests for compile/synthesis.py — runtime model-class synthesis.

No codegen equivalent exists (source emission is gone), so these tests pin
the spine :func:`~lexic.compile.synthesis.synthesize` builds directly: class
identity (module/qualname/``__grammar__``/``__binds__``), MI base ordering,
per-``kind`` field shape, optional-field defaults, and construction/
round-trip behavior on the resulting :class:`~lexic.model.GrammarModel`
subclasses.
"""

from __future__ import annotations

from lexic.compile import canonical_grammar, compile_from_path, compile_text
from lexic.compile.pipeline.binding import RuleBinding, compute_binding
from lexic.compile.pipeline.moments import build_codegen_grammar
from lexic.compile.pipeline.synthesis import synthesize
from lexic.grammars.gbnf import GBNF_FLAVOUR
from lexic.ir import (
    IrAlternation,
    IrAst,
    IrItem,
    IrLiteral,
    IrRule,
    IrRuleRef,
    IrSeq,
    IrSequence,
)
from lexic.model import GrammarModel


def synth(
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


def by_name(binding: list[RuleBinding]) -> dict[str, RuleBinding]:
    """Index a binding view by rule name."""
    return {b.rule_name: b for b in binding}


# ── class-set identity ──────────────────────────────────────────────────


def test_synthesize_returns_one_class_per_binding():
    """The returned keys match the binding view's class names, exactly."""
    classes, _grammar, binding = synth('root ::= "hi"\n')
    assert set(classes) == {b.class_name for b in binding}


def test_synthesize_classes_are_grammar_model_subclasses():
    """Every synthesized class descends from GrammarModel."""
    classes, _grammar, _binding = synth('root ::= "hi"\n')
    assert all(issubclass(cls, GrammarModel) for cls in classes.values())


def test_synthesize_class_carries_its_own_rule_as_grammar():
    """__grammar__ is the class's own IrRule from the codegen grammar."""
    classes, codegen_grammar, binding = synth('root ::= "hi"\n')
    rules = {str(r.name): r for r in codegen_grammar.rules}
    for bound in binding:
        cls = classes[bound.class_name]
        assert isinstance(cls.__grammar__, IrRule)
        assert cls.__grammar__ == rules[bound.rule_name]


def test_synthesize_module_and_qualname():
    """__module__ is generated.<stem>; __qualname__ is the class name."""
    classes, _grammar, _binding = synth('root ::= "hi"\n', stem="probe_stem")
    for name, cls in classes.items():
        assert cls.__module__ == "generated.probe_stem"
        assert cls.__qualname__ == name


# ── __binds__ / bound_fields() ──────────────────────────────────────────


def test_synthesize_binds_table_is_a_direct_class_attribute():
    """__binds__ is written directly onto the class (no annotation resolution)."""
    classes, _grammar, _binding = synth("root ::= word [0-9]*\nword ::= [a-z]+\n")
    assert "__binds__" in classes["Root"].__dict__


def test_synthesize_bound_fields_matches_the_binding_view():
    """bound_fields() returns slot -> (name, IrBind), matching the binding's fields."""
    classes, _grammar, binding = synth("root ::= word [0-9]*\nword ::= [a-z]+\n")
    root_binding = by_name(binding)["root"]
    expected = {
        ibind.item: (name, ibind) for name, ibind in root_binding.fields.items()
    }
    assert classes["Root"].bound_fields() == expected


# ── MI base ordering ─────────────────────────────────────────────────────


def alt_text() -> str:
    """root -> a | b, a/b concrete unit-ref arms of the Root alternation."""
    return 'root ::= a | b\na ::= "x"\nb ::= "y"\n'


def test_synthesize_unit_arm_subclasses_its_alternation():
    """A rule that is a unit-ref arm of an alternation subclasses that class."""
    classes, _grammar, _binding = synth(alt_text())
    assert issubclass(classes["A"], classes["Root"])
    assert issubclass(classes["B"], classes["Root"])


def test_synthesize_parentless_rule_subclasses_grammar_model_directly():
    """A rule with no alternation parent subclasses GrammarModel directly."""
    classes, _grammar, binding = synth(alt_text())
    root_binding = by_name(binding)["root"]
    assert root_binding.parent_class_names == ()
    assert classes["Root"].__bases__ == (GrammarModel,)


def test_synthesize_bases_follow_binding_parent_order():
    """A class's bases are exactly the classes named by its parent_class_names."""
    classes, _grammar, binding = synth(alt_text())
    a_binding = by_name(binding)["a"]
    assert a_binding.parent_class_names == ("Root",)
    assert classes["A"].__bases__ == (classes["Root"],)


# ── kind-specific field shape ─────────────────────────────────────────────


def test_value_str_kind_has_single_implicit_value_field():
    """A value_str rule (no rulerefs) gets one implicit `value` field, no binds."""
    classes, _grammar, binding = synth('root ::= "hi"\n')
    assert by_name(binding)["root"].kind == "value_str"
    assert classes["Root"]._fields == ("value",)
    assert classes["Root"].bound_fields() == {}


def test_alternation_kind_is_field_less():
    """An alternation class has no fields at all and no binds."""
    classes, _grammar, binding = synth(alt_text())
    assert by_name(binding)["root"].kind == "alternation"
    assert classes["Root"]._fields == ()
    assert classes["Root"].bound_fields() == {}


def test_sequence_kind_fields_match_bound_field_names_in_item_order():
    """A sequence class's _fields are its bound field names, in item order."""
    classes, _grammar, binding = synth("root ::= word [0-9]*\nword ::= [a-z]+\n")
    root_binding = by_name(binding)["root"]
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
    classes, _grammar, _binding = synth("root ::= word [0-9]*\nword ::= [a-z]+\n")
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
    classes, _grammar, binding = synth('root ::= (a | b)+\na ::= "x"\nb ::= "y"\n')
    root_binding = by_name(binding)["root"]
    (name,) = root_binding.fields
    assert root_binding.fields[name].mode == "models"
    _make, defaults = classes["Root"].fast_construct()
    assert name not in defaults


# ── construction + behavior ───────────────────────────────────────────────


def test_construct_a_sequence_class_with_keyword_fields():
    """A sequence class builds via keyword construction like the fold uses."""
    classes, _grammar, _binding = synth("root ::= word [0-9]*\nword ::= [a-z]+\n")
    inst = classes["Root"](word=classes["Word"](value="ab"), digit="123")
    assert inst.word.value == "ab"
    assert inst.digit == "123"


def test_construct_coerces_a_models_mode_list_to_a_hashable_tuple():
    """A list argument for a models-mode field coerces to a tuple (hashable)."""
    classes, _grammar, binding = synth('root ::= (a | b)+\na ::= "x"\nb ::= "y"\n')
    root_binding = by_name(binding)["root"]
    (name,) = root_binding.fields
    a_inst = classes["A"](value="x")
    inst = classes["Root"](**{name: [a_inst]})
    value = getattr(inst, name)
    assert isinstance(value, tuple)
    hash(inst)  # does not raise


def test_to_text_round_trips_a_synthesized_sequence_instance():
    """to_text() reconstructs the source text from a synthesized instance."""
    classes, _grammar, _binding = synth("root ::= word [0-9]*\nword ::= [a-z]+\n")
    inst = classes["Root"](word=classes["Word"](value="ab"), digit="123")
    assert inst.to_text() == "ab123"


def test_dump_and_semantic_dump_behave_on_a_synthesized_instance():
    """dump keeps every field; semantic_dump drops non-semantic ones."""
    classes, _grammar, _binding = synth(
        "# @non-semantic ws\nroot ::= word ws num\nword ::= [a-z]+\nnum ::= [0-9]+\n"
        "ws ::= [ ]*\n"
    )
    inst = classes["Root"](
        word=classes["Word"](value="ab"),
        ws=classes["Ws"](value=" "),
        num=classes["Num"](value="12"),
    )
    dumped = inst.dump()
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
    assert inst.dump() == {"word": {"value": "ab"}, "digit": "123"}


# ── the synthetic module name identifies CONTENT, not a filename ──────────


def test_two_files_with_one_stem_get_different_module_names(tmp_path) -> None:
    """``g.gbnf`` in two directories is two grammars, not one.

    A generated class's ``__module__`` is its grammar's identity: the payload
    projection interns a symbol per ``(module, name)``, so two different
    grammars whose classes are both called ``Root`` are only distinguishable if
    the module is. Deriving it from the file STEM made ``a/g.gbnf`` and
    ``b/g.gbnf`` indistinguishable, and the two ``Root``s merged silently.
    """
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    first = tmp_path / "a" / "g.gbnf"
    second = tmp_path / "b" / "g.gbnf"
    first.write_text("root ::= item+\nitem ::= [a-z]+\n", encoding="utf-8")
    second.write_text("root ::= word+\nword ::= [A-Z]+\n", encoding="utf-8")
    one = compile_from_path(first).classes["Root"]
    two = compile_from_path(second).classes["Root"]
    assert one.__name__ == two.__name__ == "Root"
    assert one.__module__ != two.__module__


def test_the_same_content_gets_the_same_module_name(tmp_path) -> None:
    """Two names for one grammar are one identity — the hash is of the text."""
    (tmp_path / "x.gbnf").write_text("root ::= [a-z]+\n", encoding="utf-8")
    (tmp_path / "y.gbnf").write_text("root ::= [a-z]+\n", encoding="utf-8")
    one = compile_from_path(tmp_path / "x.gbnf").classes["Root"]
    two = compile_from_path(tmp_path / "y.gbnf").classes["Root"]
    assert one.__module__.startswith("generated.x_")
    assert two.__module__.startswith("generated.y_")
    assert one.__module__.split("_")[-1] == two.__module__.split("_")[-1]


def test_the_module_name_still_reads_as_the_file(tmp_path) -> None:
    """The stem stays legible — the hash is a suffix, not a replacement."""
    (tmp_path / "chess.gbnf").write_text("root ::= [a-z]+\n", encoding="utf-8")
    cls = compile_from_path(tmp_path / "chess.gbnf").classes["Root"]
    assert cls.__module__.startswith("generated.chess_")
