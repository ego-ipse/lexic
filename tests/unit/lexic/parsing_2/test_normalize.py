"""Tests for lexic.parsing_2.normalize — desugar, flatten, split, invariants.

API changes:

- ``is_synthetic_name(name)`` removed.  All uses replaced with
  ``name.startswith(SYNTHETIC_PREFIX)``.

- ``normalize()`` composer function added; a few tests exercise it directly.

- New node classes (``Minter``, ``SplitSeq``, ``HoistItem``, ``DesugarItem``,
  ``CollectRules``, ``Expand``, ``OptChain``, ``SplitLiterals``,
  ``FlattenGroups``, ``DesugarQuantifiers``) are importable.
"""

from __future__ import annotations

import pytest

from lexic.exceptions import UnsupportedConstructError
from lexic.grammars.abnf_2 import ABNF_GRAMMAR
from lexic.grammars.json import JSON_GRAMMAR
from lexic.ir.base import IrNone, IrSeq
from lexic.ir.nodes import (
    IrAlternation,
    IrAst,
    IrCharClass,
    IrItem,
    IrLiteral,
    IrQuantifier,
    IrRange,
    IrRule,
    IrRuleRef,
    IrSequence,
)
from lexic.parsing_2.engine import recognize
from lexic.parsing_2.normalize import (
    SYNTHETIC_PREFIX,
    CollectRules,
    DesugarItem,
    DesugarQuantifiers,
    Expand,
    FlattenGroups,
    HoistItem,
    Minter,
    OptChain,
    SplitLiterals,
    SplitSeq,
    desugar_quantifiers,
    flatten_groups,
    normalize,
    split_literals,
)

_ONE = IrQuantifier(1, 1)


def _normalize(g: IrAst) -> IrAst:
    """Full normalization pipeline: flatten_groups → desugar_quantifiers → split_literals."""
    return split_literals(desugar_quantifiers(flatten_groups(g)))


def _single_rule(atom, quant: IrQuantifier = _ONE) -> IrAst:
    """Grammar with one rule 's' containing one item."""
    rule = IrRule("s", IrAlternation(IrSequence(IrItem(atom, quant))))
    return IrAst(rules=IrSeq(rule), start="s")


def _literal_rule(text: str, quant: IrQuantifier = _ONE) -> IrAst:
    """Grammar: s = '<text>' <quant>."""
    return _single_rule(IrLiteral(text), quant)


def _ruleref_rule(target: str, quant: IrQuantifier = _ONE) -> IrAst:
    """Grammar: s = <target> <quant>."""
    s = IrRule("s", IrAlternation(IrSequence(IrItem(IrRuleRef(target), quant))))
    t = IrRule(target, IrAlternation(IrSequence(IrItem(IrLiteral("x")))))
    return IrAst(rules=IrSeq(s, t), start="s")


# ── SYNTHETIC_PREFIX ──────────────────────────────────────────────────


def test_synthetic_prefix_is_double_underscore():
    """SYNTHETIC_PREFIX is '__' — well-known, not a source name prefix."""
    assert SYNTHETIC_PREFIX == "__"


def test_synthetic_name_detected_via_startswith():
    """Names starting with SYNTHETIC_PREFIX are synthetic (use startswith)."""
    assert f"{SYNTHETIC_PREFIX}rep_1".startswith(SYNTHETIC_PREFIX)


def test_source_names_do_not_start_with_prefix():
    """Ordinary source rule names do not start with SYNTHETIC_PREFIX."""
    for name in ("rulelist", "s", "catrest"):
        assert not name.startswith(SYNTHETIC_PREFIX)


# ── split_literals ────────────────────────────────────────────────────


def test_split_literals_multichar_literal_becomes_individual_items():
    """'true' (4 chars) becomes 4 single-char IrItem nodes."""
    g = _literal_rule("true")
    result = split_literals(g)
    arm = list(list(result.rules)[0].body)[0]
    assert len(arm) == 4
    chars = [str(item.atom) for item in arm]
    assert chars == ["t", "r", "u", "e"]


def test_split_literals_single_char_literal_unchanged():
    """A single-char literal is not split."""
    g = _literal_rule("x")
    result = split_literals(g)
    arm = list(list(result.rules)[0].body)[0]
    assert len(arm) == 1
    assert arm[0].atom == IrLiteral("x")


def test_split_literals_quantified_multichar_literal_not_split():
    """A quantified multi-char literal (non-(1,1)) is left as-is by split_literals.

    Quantified literals must be desugared first by desugar_quantifiers.
    split_literals only splits unquantified (1,1) multi-char literals.
    """
    g = _literal_rule("ab", IrQuantifier(0, IrNone))
    result = split_literals(g)
    arm = list(list(result.rules)[0].body)[0]
    # The item is NOT split because its quantifier is not (1,1)
    assert len(arm) == 1
    assert arm[0].atom == IrLiteral("ab")


def test_split_literals_ruleref_atom_untouched():
    """IrRuleRef atoms are not affected by split_literals."""
    g = _ruleref_rule("expr")
    result = split_literals(g)
    rules = list(result.rules)
    arm = list(rules[0].body)[0]
    assert arm[0].atom == IrRuleRef("expr")


def test_split_literals_charclass_atom_untouched():
    """IrCharClass atoms are not split."""
    g = _single_rule(IrCharClass(IrRange("0", "9")))
    result = split_literals(g)
    arm = list(list(result.rules)[0].body)[0]
    assert isinstance(arm[0].atom, IrCharClass)


def test_split_literals_all_items_in_split_have_one_one_quantifier():
    """All items after splitting a multi-char literal have (1,1) quantifier."""
    g = _literal_rule("abc")
    result = split_literals(g)
    arm = list(list(result.rules)[0].body)[0]
    for item in arm:
        assert item.quantifier == _ONE


def test_split_literals_preserves_start_rule():
    """split_literals keeps the grammar's start rule name unchanged."""
    g = _literal_rule("hello")
    result = split_literals(g)
    assert result.start == g.start


def test_split_literals_recognizes_split_word():
    """After split_literals, the recognizer accepts the word."""
    g = _literal_rule("true")
    result = split_literals(g)
    assert recognize(result, "true") is True


def test_split_literals_rejects_partial_match_after_split():
    """After split_literals, the recognizer rejects a partial word."""
    g = _literal_rule("true")
    result = split_literals(g)
    assert recognize(result, "tru") is False


# ── flatten_groups ────────────────────────────────────────────────────


def test_flatten_groups_hoists_group_to_synthetic_rule():
    """An IrAlternation atom (group) is hoisted to a synthetic rule."""
    inner_alt = IrAlternation(
        IrSequence(IrItem(IrLiteral("a"))), IrSequence(IrItem(IrLiteral("b")))
    )
    rule = IrRule("s", IrAlternation(IrSequence(IrItem(inner_alt))))
    g = IrAst(rules=IrSeq(rule), start="s")
    result = flatten_groups(g)
    rules = list(result.rules)
    assert len(rules) == 2
    # The second rule is the synthetic one
    syn_rule = rules[1]
    assert syn_rule.name.startswith(SYNTHETIC_PREFIX)


def test_flatten_groups_replaces_atom_with_ruleref():
    """After flattening, the group atom in 's' is replaced by an IrRuleRef."""
    inner_alt = IrAlternation(
        IrSequence(IrItem(IrLiteral("a"))), IrSequence(IrItem(IrLiteral("b")))
    )
    rule = IrRule("s", IrAlternation(IrSequence(IrItem(inner_alt))))
    g = IrAst(rules=IrSeq(rule), start="s")
    result = flatten_groups(g)
    arm_s = list(list(result.rules)[0].body)[0]
    assert isinstance(arm_s[0].atom, IrRuleRef)


def test_flatten_groups_preserves_quantifier_on_group():
    """The original item's quantifier is preserved on the hoisted ruleref."""
    quant = IrQuantifier(0, IrNone)
    inner_alt = IrAlternation(IrSequence(IrItem(IrLiteral("x"))))
    rule = IrRule("s", IrAlternation(IrSequence(IrItem(inner_alt, quant))))
    g = IrAst(rules=IrSeq(rule), start="s")
    result = flatten_groups(g)
    arm_s = list(list(result.rules)[0].body)[0]
    assert arm_s[0].quantifier == quant


def test_flatten_groups_non_group_rules_unchanged_in_shape():
    """Rules with no group atoms are returned unchanged in shape."""
    g = _literal_rule("x")
    result = flatten_groups(g)
    assert len(list(result.rules)) == len(list(g.rules))
    arm_before = list(list(g.rules)[0].body)[0]
    arm_after = list(list(result.rules)[0].body)[0]
    assert arm_before[0].atom == arm_after[0].atom


def test_flatten_groups_synthetic_names_carry_prefix():
    """All hoisted synthetic rules carry SYNTHETIC_PREFIX."""
    inner_alt = IrAlternation(IrSequence(IrItem(IrLiteral("z"))))
    rule = IrRule("s", IrAlternation(IrSequence(IrItem(inner_alt))))
    g = IrAst(rules=IrSeq(rule), start="s")
    result = flatten_groups(g)
    for r in result.rules:
        if r.name != "s":
            assert r.name.startswith(SYNTHETIC_PREFIX), (
                f"Expected synthetic name, got {r.name!r}"
            )


# ── desugar_quantifiers ───────────────────────────────────────────────


def _desugar(quant: IrQuantifier) -> IrAst:
    """Desugar a grammar with a single quantified literal atom."""
    return desugar_quantifiers(_literal_rule("a", quant))


def _synthetic_rules(g: IrAst) -> list[IrRule]:
    return [r for r in g.rules if r.name.startswith(SYNTHETIC_PREFIX)]


def test_desugar_one_one_unchanged():
    """(1,1) items pass through desugar_quantifiers unchanged — no synthetic rules."""
    g = _literal_rule("a", _ONE)
    result = desugar_quantifiers(g)
    assert len(_synthetic_rules(result)) == 0


def test_desugar_star_mints_synthetic_rule():
    """(0,IrNone) mints one synthetic rule."""
    result = _desugar(IrQuantifier(0, IrNone))
    syn = _synthetic_rules(result)
    assert len(syn) == 1


def test_desugar_star_has_two_arms():
    """* synthetic rule: X = ε / atom X (first arm empty)."""
    result = _desugar(IrQuantifier(0, IrNone))
    syn = _synthetic_rules(result)[0]
    arms = list(syn.body)
    assert len(arms) == 2


def test_desugar_star_first_arm_is_empty():
    """* synthetic rule first arm is IrSequence() (epsilon)."""
    result = _desugar(IrQuantifier(0, IrNone))
    syn = _synthetic_rules(result)[0]
    first_arm = list(syn.body)[0]
    assert not list(first_arm)


def test_desugar_star_second_arm_has_atom_and_self_ref():
    """* synthetic rule second arm: unit then a self-referencing ruleref."""
    result = _desugar(IrQuantifier(0, IrNone))
    syn = _synthetic_rules(result)[0]
    second_arm = list(syn.body)[1]
    items = list(second_arm)
    assert len(items) == 2
    assert items[0].atom == IrLiteral("a")
    assert isinstance(items[1].atom, IrRuleRef)
    assert str(items[1].atom) == syn.name


def test_desugar_plus_has_two_arms():
    """+ synthetic rule: X = atom / atom X."""
    result = _desugar(IrQuantifier(1, IrNone))
    syn = _synthetic_rules(result)[0]
    arms = list(syn.body)
    assert len(arms) == 2


def test_desugar_plus_first_arm_is_single_atom():
    """+ synthetic first arm: just the atom (no self-ref)."""
    result = _desugar(IrQuantifier(1, IrNone))
    syn = _synthetic_rules(result)[0]
    first_arm = list(syn.body)[0]
    items = list(first_arm)
    assert len(items) == 1
    assert items[0].atom == IrLiteral("a")


def test_desugar_plus_second_arm_has_atom_and_self_ref():
    """+ synthetic second arm: atom then self-ref."""
    result = _desugar(IrQuantifier(1, IrNone))
    syn = _synthetic_rules(result)[0]
    second_arm = list(syn.body)[1]
    items = list(second_arm)
    assert len(items) == 2
    assert items[1].atom == IrRuleRef(syn.name)


def test_desugar_optional_has_two_arms():
    """? synthetic rule: X = ε / atom."""
    result = _desugar(IrQuantifier(0, 1))
    syn = _synthetic_rules(result)[0]
    arms = list(syn.body)
    assert len(arms) == 2


def test_desugar_optional_first_arm_is_empty():
    """? synthetic first arm is epsilon."""
    result = _desugar(IrQuantifier(0, 1))
    syn = _synthetic_rules(result)[0]
    first_arm = list(syn.body)[0]
    assert not list(first_arm)


def test_desugar_optional_second_arm_is_atom():
    """? synthetic second arm is just the atom."""
    result = _desugar(IrQuantifier(0, 1))
    syn = _synthetic_rules(result)[0]
    second_arm = list(syn.body)[1]
    items = list(second_arm)
    assert len(items) == 1
    assert items[0].atom == IrLiteral("a")


def test_desugar_exact_two_single_arm():
    """{2,2} synthetic rule has a single arm with exactly 2 atoms."""
    result = _desugar(IrQuantifier(2, 2))
    syn = _synthetic_rules(result)[0]
    arms = list(syn.body)
    assert len(arms) == 1
    items = list(arms[0])
    assert len(items) == 2
    assert all(item.atom == IrLiteral("a") for item in items)


def test_desugar_general_bounded_mints_opt_rules():
    """{2,4} mints an opt-chain plus a rep rule for the mandatory part."""
    result = _desugar(IrQuantifier(2, 4))
    syn = _synthetic_rules(result)
    # There should be more than one synthetic rule (rep + opt chain)
    assert len(syn) > 1


def test_desugar_after_desugar_all_items_have_one_one():
    """After desugar_quantifiers, every item in every rule has (1,1) quantifier."""
    g = _literal_rule("a", IrQuantifier(0, IrNone))
    result = desugar_quantifiers(g)
    for rule in result.rules:
        for arm in rule.body:
            for item in arm:
                assert item.quantifier == _ONE


def test_desugar_invalid_negative_lo_raises():
    """lo < 0 raises UnsupportedConstructError."""
    with pytest.raises(UnsupportedConstructError):
        desugar_quantifiers(_literal_rule("a", IrQuantifier(-1, 1)))


def test_desugar_invalid_hi_less_than_lo_raises():
    """hi < lo raises UnsupportedConstructError."""
    with pytest.raises(UnsupportedConstructError):
        desugar_quantifiers(_literal_rule("a", IrQuantifier(3, 2)))


def test_desugar_s_now_references_synthetic_rule():
    """After desugaring, the 's' rule's item references the synthetic rule by ruleref."""
    result = _desugar(IrQuantifier(0, IrNone))
    s_rule = list(result.rules)[0]
    assert s_rule.name == "s"
    arm = list(s_rule.body)[0]
    item = list(arm)[0]
    assert isinstance(item.atom, IrRuleRef)
    assert str(item.atom).startswith(SYNTHETIC_PREFIX)


# ── normalize() composer ──────────────────────────────────────────────


def test_normalize_composer_equals_manual_pipeline():
    """normalize() returns the same result as the manual three-step pipeline."""
    g = _literal_rule("ab", IrQuantifier(0, IrNone))
    assert normalize(g) == _normalize(g)


def test_normalize_composer_returns_ir_ast():
    """normalize() returns an IrAst."""
    g = _literal_rule("x")
    result = normalize(g)
    assert isinstance(result, IrAst)


# ── Node class exports ────────────────────────────────────────────────


def test_normalize_node_classes_are_importable():
    """The IrSelf node classes are importable from normalize."""
    for cls in (
        Minter,
        SplitSeq,
        HoistItem,
        DesugarItem,
        CollectRules,
        Expand,
        OptChain,
        SplitLiterals,
        FlattenGroups,
        DesugarQuantifiers,
    ):
        assert callable(cls)


# ── Full normalize invariants ─────────────────────────────────────────


def _check_normalized(g: IrAst) -> list[str]:
    """Return descriptions of any normalization violations."""
    issues: list[str] = []
    for rule in g.rules:
        for arm in rule.body:
            for item in arm:
                if item.quantifier != _ONE:
                    issues.append(
                        f"{rule.name}: non-(1,1) quantifier {item.quantifier}"
                    )
                if isinstance(item.atom, IrAlternation):
                    issues.append(f"{rule.name}: IrAlternation atom (unhoist group)")
                if isinstance(item.atom, IrLiteral) and len(str(item.atom)) > 1:
                    issues.append(f"{rule.name}: multi-char literal {item.atom!r}")
    return issues


def test_normalize_abnf_grammar_no_violations():
    """After full normalization, ABNF_GRAMMAR has no non-(1,1) quantifiers,
    no IrAlternation atoms, and no multi-char IrLiteral atoms."""
    issues = _check_normalized(_normalize(ABNF_GRAMMAR))
    assert not issues, f"Normalization violations: {issues}"


def test_normalize_json_grammar_no_violations():
    """After full normalization, JSON_GRAMMAR has no non-(1,1) quantifiers,
    no IrAlternation atoms, and no multi-char IrLiteral atoms."""
    issues = _check_normalized(_normalize(JSON_GRAMMAR))
    assert not issues, f"Normalization violations: {issues}"
