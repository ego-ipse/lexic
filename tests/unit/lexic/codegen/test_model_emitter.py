"""Model emitter — field-type helpers and module rendering (binding-driven)."""

from __future__ import annotations

from lexic.codegen.binding import compute_binding
from lexic.codegen.model_emitter import (
    _base_field_type,
    _group_union_type,
    _value_str_type,
    _wrap_field_type,
    emit_module_source,
)
from lexic.codegen.passes import build_codegen_grammar
from lexic.compile import canonical_grammar
from lexic.grammars.gbnf import GBNF_FLAVOUR
from lexic.ir.base import IrNone
from lexic.ir.bind import IrBind
from lexic.ir.nodes import (
    IrAlternation,
    IrCharClass,
    IrChr,
    IrItem,
    IrLiteral,
    IrQuantifier,
    IrRange,
    IrRule,
    IrRuleRef,
)

_DIGIT = IrCharClass(IrRange(IrChr("0"), IrChr("9")))
_PLUS = IrQuantifier(1, IrNone)


def _emit(text: str, stem: str = "m") -> str:
    """Render a grammar through the whole binding-driven emit path."""
    canonical = canonical_grammar(text, GBNF_FLAVOUR)
    codegen_grammar = build_codegen_grammar(canonical)
    binding = compute_binding(codegen_grammar)
    return emit_module_source(canonical, codegen_grammar, binding, stem=stem)


# ── value_str field type ──────────────────────────────────────────────


def test_value_str_charclass_emits_string_constraints():
    """A charclass value_str field emits an inline Annotated[str, StringConstraints]."""
    rule = IrRule("d", IrItem(_DIGIT, _PLUS))
    assert (
        _value_str_type(rule, {})
        == 'Annotated[str, StringConstraints(pattern=r"^[0-9]+$")]'
    )


def test_value_str_literal_is_plain_str():
    """A lone literal value_str field is plain ``str``."""
    assert _value_str_type(IrRule("d", IrItem(IrLiteral("x"))), {}) == "str"


def test_value_str_pure_literal_alternation_is_literal_type():
    """An alternation of unquantified literals becomes a ``Literal[...]``."""
    rule = IrRule(
        "ty", IrAlternation(IrLiteral("int"), IrLiteral("float"), IrLiteral("char"))
    )
    assert _value_str_type(rule, {}) == 'Literal["int", "float", "char"]'


def test_value_str_quantified_literal_arm_is_str():
    """A quantified literal arm defeats the pure-literal path → flat ``str``."""
    rule = IrRule(
        "t",
        IrAlternation(
            IrItem(IrLiteral("a"), IrQuantifier(1, 1)),
            IrItem(IrLiteral("b"), IrQuantifier(0, 1)),
        ),
    )
    assert _value_str_type(rule, {}) == "str"


def test_value_str_charclass_uses_registered_alias():
    """A registered pattern resolves to the alias name, not an inline form."""
    rule = IrRule("d", IrItem(_DIGIT, _PLUS))
    assert _value_str_type(rule, {r"^[0-9]+$": "Digit"}) == "Digit"


# ── base field type (mode × atom) ─────────────────────────────────────


def test_base_ruleref_model_is_referred_class():
    """A model-mode ref field takes the referred class name."""
    item = IrItem(IrRuleRef("expr"))
    assert _base_field_type(item, "model", {"expr": "Expr"}, {}) == "Expr"


def test_base_charclass_text_inline_when_unregistered():
    """A text-mode charclass field emits an inline Annotated when no alias hits."""
    item = IrItem(_DIGIT, _PLUS)
    assert (
        _base_field_type(item, "text", {}, {})
        == 'Annotated[str, StringConstraints(pattern=r"^[0-9]+$")]'
    )


def test_group_union_type_joins_ref_arms():
    """A ref-bearing group's type is a Union over its unit-ref arms."""
    group = IrAlternation(IrRuleRef("a"), IrRuleRef("b"))
    assert _group_union_type(group, {"a": "A", "b": "B"}) == "Union[A, B]"


def test_group_union_type_single_ref_is_bare_class():
    """A single unit-ref group is just that class."""
    group = IrAlternation(IrRuleRef("a"))
    assert _group_union_type(group, {"a": "A"}) == "A"


def test_group_union_type_no_ref_arm_is_str():
    """A group with no clean ref arm has no model type → ``str``."""
    group = IrAlternation(IrItem(IrLiteral("+")))
    assert _group_union_type(group, {}) == "str"


# ── field wrapping (Optional / List / empty-arm) ──────────────────────


def test_wrap_optional_for_0_1_quantifier():
    """A (0,1) model field wraps in Optional."""
    item = IrItem(IrRuleRef("expr"), IrQuantifier(0, 1))
    assert _wrap_field_type("Expr", IrBind(0, "model"), item, False) == "Optional[Expr]"


def test_wrap_list_for_models_mode():
    """A models-mode field wraps in List."""
    item = IrItem(IrRuleRef("expr"), _PLUS)
    assert _wrap_field_type("Expr", IrBind(0, "models"), item, False) == "List[Expr]"


def test_wrap_empty_arm_forces_optional():
    """An epsilon alternate arm forces every field Optional."""
    item = IrItem(IrRuleRef("expr"))
    assert _wrap_field_type("Expr", IrBind(0, "model"), item, True) == "Optional[Expr]"


def test_wrap_required_ref_is_bare():
    """A required single-model field is unwrapped."""
    item = IrItem(IrRuleRef("expr"))
    assert _wrap_field_type("Expr", IrBind(0, "model"), item, False) == "Expr"


# ── module rendering ──────────────────────────────────────────────────


def test_module_hoists_pattern_alias_and_references_it():
    """A pattern gets a module-level alias; the field references it by name."""
    src = _emit("root ::= [0-9]+\n")
    assert 'Digit = Annotated[str, StringConstraints(pattern=r"^[0-9]+$")]' in src
    assert "value: Digit" in src


def test_module_shares_one_alias_for_repeated_pattern():
    """Two rules with [0-9]+ share a single Digit alias declaration."""
    src = _emit("root ::= a b\na ::= [0-9]+\nb ::= [0-9]+\n")
    assert src.count("Digit = Annotated[") == 1


def test_module_class_carries_grammar_footer():
    """Each class footers its ``__grammar__: ClassVar[IrRule]`` and the module GRAMMAR."""
    src = _emit('root ::= "x"\n')
    assert "class Root(GrammarModel):" in src
    assert "__grammar__: ClassVar[IrRule] =" in src
    assert "GRAMMAR: IrAst =" in src


def test_module_alternation_class_is_field_less():
    """An alternation class emits only its footer (no value field)."""
    src = _emit("root ::= num | ident\nnum ::= [0-9]+\nident ::= [a-z]+\n")
    root_section = src.split("class Root(GrammarModel):")[1].split("\n\n")[0]
    assert "value:" not in root_section
