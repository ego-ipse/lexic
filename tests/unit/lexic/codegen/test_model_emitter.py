"""Model emitter — class-body emission (skeleton)."""

from __future__ import annotations

from ast import AnnAssign, ClassDef, Name, parse

from lexic.codegen.model_emitter import emit_module_source
from lexic.ir.nodes import (
    IrAlternation,
    IrCharClass,
    IrGroup,
    IrItem,
    IrLiteral,
    IrNot,
    IrRuleRef,
    IrSequence,
    Quantifier,
)
from tests.unit.lexic.codegen.conftest import load_emitted, make_charclass_literal_group
from tests.unit.lexic.conftest import make_spec as _spec


def test_emit_value_str_class_body():
    """Value-str with a charclass item emits a constrained value field."""
    spec = _spec(
        "digit", "value_str", [IrItem(IrCharClass("0-9"), Quantifier(1, None))]
    )
    src = emit_module_source([spec], stem="m")
    assert "class Digit(GrammarModel):" in src
    assert "value: Digit" in src


def test_emit_sequence_class_with_ruleref_field():
    """Sequence classes with rulerefs emit fields of the referred type."""
    inner = _spec(
        "expr", "value_str", [IrItem(IrCharClass("a-z"), Quantifier(1, None))]
    )
    outer = _spec(
        "root", "sequence", [IrItem(IrRuleRef("expr"))], field_map={"expr": 0}
    )
    src = emit_module_source([outer, inner], stem="m")
    assert "class Root(GrammarModel):" in src
    assert "expr: Expr" in src


def test_emit_optional_field_for_quantifier_0_1():
    """Quantifier {0,1} emits Optional[...] field."""
    inner = _spec(
        "expr", "value_str", [IrItem(IrCharClass("a-z"), Quantifier(1, None))]
    )
    outer = _spec(
        "r",
        "sequence",
        [IrItem(IrRuleRef("expr"), Quantifier(0, 1))],
        field_map={"expr": 0},
    )
    src = emit_module_source([outer, inner], stem="m")
    assert "Optional[Expr]" in src or "Expr | None" in src


def test_emit_list_field_for_quantifier_unbounded():
    """Quantifier {1,+inf} emits List[...] field."""
    inner = _spec(
        "expr", "value_str", [IrItem(IrCharClass("a-z"), Quantifier(1, None))]
    )
    outer = _spec(
        "r",
        "sequence",
        [IrItem(IrRuleRef("expr"), Quantifier(1, None))],
        field_map={"expr": 0},
    )
    src = emit_module_source([outer, inner], stem="m")
    assert "List[Expr]" in src


def test_emit_list_field_for_quantifier_zero_or_more():
    """Quantifier {0,+inf} also emits List[...] field."""
    inner = _spec(
        "expr", "value_str", [IrItem(IrCharClass("a-z"), Quantifier(1, None))]
    )
    outer = _spec(
        "r",
        "sequence",
        [IrItem(IrRuleRef("expr"), Quantifier(0, None))],
        field_map={"expr": 0},
    )
    src = emit_module_source([outer, inner], stem="m")
    assert "List[Expr]" in src


def test_emit_alternation_kind_emits_pass():
    """Alternation-kind specs emit only __grammar__ + pass (no fields)."""
    spec = _spec("node", "alternation", [], field_map={})
    src = emit_module_source([spec], stem="m")
    assert "class Node(GrammarModel):" in src
    assert "pass" in src
    assert "value:" not in src


def test_emit_value_str_multi_arm():
    """Multi-arm value_str (IrAlternation in items) serialises without FIXME."""
    spec = _spec(
        "tok",
        "value_str",
        [
            IrAlternation(
                (
                    IrSequence((IrItem(IrLiteral("a")),)),
                    IrSequence((IrItem(IrLiteral("b")),)),
                )
            )
        ],
    )
    src = emit_module_source([spec], stem="m")
    assert "class Tok(GrammarModel):" in src
    assert "FIXME" not in src
    assert "IrAlternation" in src


def test_emitted_module_has_canonical_imports():
    """Emitted modules have canonical imports."""
    spec = _spec("r", "value_str", [IrItem(IrLiteral("x"))])
    src = emit_module_source([spec], stem="m")
    expected_lines = [
        "from lexic.base import GrammarModel",
        "from lexic.ir.spec import RuleSpec",
        "from lexic.ir.nodes import",
    ]
    for line in expected_lines:
        assert line in src, f"missing canonical import: {line}"


def test_no_fixme_in_emitted_source():
    """Decision CQ #1: never emit # FIXME placeholders."""
    grp = IrGroup(
        IrAlternation(
            (
                IrSequence((IrItem(IrLiteral("a")),)),
                IrSequence((IrItem(IrLiteral("b")),)),
            )
        )
    )
    spec = _spec("r", "value_str", [IrItem(grp, Quantifier(1, 1))])
    src = emit_module_source([spec], stem="m")
    assert "# FIXME" not in src
    assert "FIXME" not in src


def test_charclass_field_emits_annotated_string_constraints():
    """IrCharClass sequence field emits Annotated[str, StringConstraints(...)]."""
    spec = _spec("d", "value_str", [IrItem(IrCharClass("0-9"), Quantifier(1, None))])
    src = emit_module_source([spec], stem="m")
    assert 'Annotated[str, StringConstraints(pattern=r"^[0-9]+$")]' in src


def test_negated_charclass_field_inverts_pattern():
    """IrNot(IrCharClass) emits [^...] in the regex."""
    spec = _spec("nq", "value_str", [IrItem(IrNot(IrCharClass('"')))])
    src = emit_module_source([spec], stem="m")
    assert "Annotated[str, StringConstraints(pattern=r'^[^\"]$')]" in src


def test_charclass_field_in_sequence_emits_alias():
    """IrCharClass named field in a sequence spec references the module-level alias."""
    spec = _spec(
        "row",
        "sequence",
        [IrItem(IrCharClass("a-z"), Quantifier(1, None))],
        field_map={"lower": 0},
    )
    src = emit_module_source([spec], stem="m")
    assert "lower: Lower" in src


def test_pure_pattern_group_field_composes_regex():
    """([a-h] 'x')? → alias Pattern2; field references the alias."""
    grp = make_charclass_literal_group()
    spec = _spec(
        "p", "sequence", [IrItem(grp, Quantifier(0, 1))], field_map={"head": 0}
    )
    src = emit_module_source([spec], stem="m")
    # Alias is declared at module level
    assert 'Pattern2 = Annotated[str, StringConstraints(pattern=r"^([a-h]x)?$")]' in src
    # Field references the alias, not the inline form
    assert "head: Optional[Pattern2]" in src
    class_section = src.split("class P(")[1] if "class P(" in src else ""
    assert "Annotated[" not in class_section.split("\n\n")[0]


def test_pure_literal_alternation_emits_literal_type():
    """Alternation of pure literals emits a Literal[...] field."""
    alt = IrAlternation(
        (
            IrSequence((IrItem(IrLiteral("int"), Quantifier(1, 1)),)),
            IrSequence((IrItem(IrLiteral("float"), Quantifier(1, 1)),)),
            IrSequence((IrItem(IrLiteral("char"), Quantifier(1, 1)),)),
        )
    )
    spec = _spec("ty", "value_str", [alt])
    src = emit_module_source([spec], stem="m")
    assert 'value: Literal["int", "float", "char"]' in src


def test_mixed_alternation_does_not_emit_literal():
    """Arms mixing literal + ruleref keep the helper-class shape (no Literal)."""
    alt = IrAlternation(
        (
            IrSequence((IrItem(IrLiteral("int"), Quantifier(1, 1)),)),
            IrSequence((IrItem(IrRuleRef("typename"), Quantifier(1, 1)),)),
        )
    )
    spec = _spec("t", "value_str", [alt])
    src = emit_module_source([spec], stem="m")
    assert "Literal[" not in src.split("class T")[1].split("\n\n")[0]


def test_quantified_literal_arm_does_not_emit_literal():
    """An arm with a quantified literal (min!=max!=1) is not a pure-literal."""
    alt = IrAlternation(
        (
            IrSequence((IrItem(IrLiteral("a"), Quantifier(1, 1)),)),
            IrSequence((IrItem(IrLiteral("b"), Quantifier(0, 1)),)),  # quantified
        )
    )
    spec = _spec("t", "value_str", [alt])
    src = emit_module_source([spec], stem="m")
    assert "Literal[" not in src.split("class T")[1].split("\n\n")[0]


def test_module_emits_pattern_aliases_at_top():
    """Patterns get module-level aliases; field types reference the alias."""
    spec = _spec("d", "value_str", [IrItem(IrCharClass("0-9"), Quantifier(1, None))])
    src = emit_module_source([spec], stem="m")
    # Tier 2 hit: [0-9]+ → 'digit' → CamelCase 'Digit'
    assert 'Digit = Annotated[str, StringConstraints(pattern=r"^[0-9]+$")]' in src
    # Field type uses the alias, not the inline form
    assert "value: Digit" in src
    # The inline form should NOT appear in the class body section
    class_section = src.split("class D(")[1] if "class D(" in src else ""
    assert "Annotated[" not in class_section.split("\n\n")[0]


def test_repeated_pattern_shares_one_alias():
    """Two rules with [0-9]+ produce one alias."""
    s1 = _spec("a", "value_str", [IrItem(IrCharClass("0-9"), Quantifier(1, None))])
    s2 = _spec("b", "value_str", [IrItem(IrCharClass("0-9"), Quantifier(1, None))])
    src = emit_module_source([s1, s2], stem="m")
    # One alias declaration
    assert src.count("Digit = Annotated[") == 1
    # Both classes reference Digit
    assert "value: Digit" in src


def test_class_body_has_no_grammar_assignment():
    """Class body contains only field declarations (and pass for empty)."""
    spec = _spec("d", "value_str", [IrItem(IrCharClass("0-9"), Quantifier(1, None))])
    src = emit_module_source([spec], stem="m")
    tree = parse(src)
    classes = [n for n in tree.body if isinstance(n, ClassDef)]
    assert len(classes) == 1
    # No __grammar__ assignment inside class body
    for stmt in classes[0].body:
        if isinstance(stmt, AnnAssign) and isinstance(stmt.target, Name):
            assert stmt.target.id != "__grammar__", "__grammar__ leaked into class body"


def test_module_footer_registers_grammar():
    """Footer block sets cls.__grammar__ for each class."""
    spec = _spec("d", "value_str", [IrItem(IrCharClass("0-9"), Quantifier(1, None))])
    src = emit_module_source([spec], stem="m")
    assert "D.__grammar__ = RuleSpec(" in src


def test_emitted_module_loads_and_grammar_attribute_present():
    """The emitted source loads and D.__grammar__ is reachable at runtime."""
    spec = _spec("d", "value_str", [IrItem(IrLiteral("x"))])
    src = emit_module_source([spec], stem="m")
    mod = load_emitted(src)
    assert hasattr(mod.D, "__grammar__")
    assert mod.D.__grammar__.rule_name == "d"


def test_grammar_round_trip_through_load():
    """Load the emitted source; verify __grammar__.items[0] == original IR."""
    grp_spec = _spec(
        "r",
        "sequence",
        [IrItem(IrCharClass("0-9"), Quantifier(1, None))],
        field_map={"digit": 0},
    )
    src = emit_module_source([grp_spec], stem="m")
    mod = load_emitted(src)
    item0 = mod.R.__grammar__.items[0]
    assert item0.atom == IrCharClass("0-9")
    assert item0.quantifier == Quantifier(1, None)
