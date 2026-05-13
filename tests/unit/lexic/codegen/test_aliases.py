"""Pattern alias collection — module-level alias names for IrCharClass / pure-pattern IrGroup."""

from __future__ import annotations

from lexic.codegen.aliases import (
    PatternAlias,
    collect_aliases,
    regex_for_charclass,
    regex_for_group,
)
from lexic.ir.nodes import (
    IrAlternation,
    IrCharClass,
    IrGroup,
    IrItem,
    IrLiteral,
    IrRuleRef,
    IrSequence,
    Quantifier,
)
from lexic.ir.spec import RuleSpec


def _spec(name, kind, items, field_map=None):
    """Helper to create a RuleSpec with the given items."""
    return RuleSpec(
        rule_name=name,
        class_name=name.title(),
        parent_class_name="GrammarModel",
        kind=kind,
        items=list(items),
        field_map=field_map or {},
    )


def test_regex_for_charclass_simple():
    """[0-9]+ → ^[0-9]+$."""
    cc = IrCharClass("0-9")
    assert regex_for_charclass(cc, Quantifier(1, None)) == r"^[0-9]+$"


def test_regex_for_charclass_negated():
    """[^"] → ^[^"]$."""
    cc = IrCharClass('"', negated=True)
    assert regex_for_charclass(cc, Quantifier(1, 1)) == r'^[^"]$'


def test_regex_for_charclass_bounded_quantifier():
    """[0-9]{0,15} → ^[0-9]{0,15}$."""
    cc = IrCharClass("0-9")
    assert regex_for_charclass(cc, Quantifier(0, 15)) == r"^[0-9]{0,15}$"


def test_regex_for_charclass_optional():
    """[a-z]? → ^[a-z]?$."""
    cc = IrCharClass("a-z")
    assert regex_for_charclass(cc, Quantifier(0, 1)) == r"^[a-z]?$"


def test_regex_for_group_pure_pattern():
    """([a-h] 'x')? → ^([a-h]x)?$."""
    grp = IrGroup(
        IrAlternation(
            (
                IrSequence(
                    (
                        IrItem(IrCharClass("a-h"), Quantifier(1, 1)),
                        IrItem(IrLiteral("x"), Quantifier(1, 1)),
                    )
                ),
            )
        )
    )
    assert regex_for_group(grp, Quantifier(0, 1)) == r"^([a-h]x)?$"


def test_regex_for_group_alternation():
    """('foo' | 'bar')+ → ^(foo|bar)+$."""
    grp = IrGroup(
        IrAlternation(
            (
                IrSequence((IrItem(IrLiteral("foo"), Quantifier(1, 1)),)),
                IrSequence((IrItem(IrLiteral("bar"), Quantifier(1, 1)),)),
            )
        )
    )
    assert regex_for_group(grp, Quantifier(1, None)) == r"^(foo|bar)+$"


def test_collect_aliases_dedupes_identical_patterns():
    """Two rules with identical [0-9]+ pattern share one alias."""
    s1 = _spec("a", "value_str", [IrItem(IrCharClass("0-9"), Quantifier(1, None))])
    s2 = _spec("b", "value_str", [IrItem(IrCharClass("0-9"), Quantifier(1, None))])
    aliases = collect_aliases([s1, s2])
    assert len(aliases) == 1
    a = aliases[0]
    assert isinstance(a, PatternAlias)
    assert a.regex == r"^[0-9]+$"
    assert a.name == "Digit"  # Tier 2: bracket-only lookup → 'digit' → CamelCase


def test_collect_aliases_distinguishes_different_quantifiers():
    """[0-9] and [0-9]+ produce different aliases."""
    s = _spec(
        "r",
        "sequence",
        [
            IrItem(IrCharClass("0-9"), Quantifier(1, 1)),
            IrItem(IrCharClass("0-9"), Quantifier(1, None)),
        ],
    )
    aliases = collect_aliases([s])
    regexes = {a.regex for a in aliases}
    assert regexes == {r"^[0-9]$", r"^[0-9]+$"}


def test_collect_aliases_naming_via_tier_pipeline():
    """Tier 2 lookup → CamelCase; Tier 3 fallback → 'Pattern' / 'Pattern2'."""
    s = _spec(
        "r",
        "sequence",
        [
            IrItem(IrCharClass("a-z"), Quantifier(1, None)),  # Tier 2: lower → Lower
            IrItem(IrCharClass("0-9"), Quantifier(1, None)),  # Tier 2: digit → Digit
        ],
    )
    aliases = collect_aliases([s])
    names = {a.name for a in aliases}
    assert names == {"Lower", "Digit"}


def test_collect_aliases_disambiguates_same_base_name():
    """Two distinct [0-9] regexes (different quantifiers) yield Digit + Digit2."""
    s = _spec(
        "r",
        "sequence",
        [
            IrItem(IrCharClass("0-9"), Quantifier(1, 1)),
            IrItem(IrCharClass("0-9"), Quantifier(1, None)),
        ],
    )
    names = [a.name for a in collect_aliases([s])]
    assert names == ["Digit", "Digit2"]


def test_collect_aliases_skips_group_with_ruleref():
    """A group containing an IrRuleRef does not produce a PatternAlias."""
    grp = IrGroup(
        IrAlternation(
            (
                IrSequence(
                    (
                        IrItem(IrLiteral("("), Quantifier(1, 1)),
                        IrItem(IrRuleRef("expr"), Quantifier(1, 1)),
                        IrItem(IrLiteral(")"), Quantifier(1, 1)),
                    )
                ),
            )
        )
    )
    s = _spec(
        "r",
        "sequence",
        [IrItem(grp, Quantifier(1, 1))],
        field_map={"kind": 0},
    )
    assert not collect_aliases([s])


def test_collect_aliases_pure_group_with_inner_charclass_emits_both():
    """Pure-pattern outer group + inner [0-9] both produce aliases."""
    grp = IrGroup(
        IrAlternation(
            (
                IrSequence(
                    (
                        IrItem(IrCharClass("0-9"), Quantifier(1, None)),
                        IrItem(IrLiteral("x"), Quantifier(1, 1)),
                    )
                ),
            )
        )
    )
    s = _spec(
        "r",
        "sequence",
        [IrItem(grp, Quantifier(0, 1))],
        field_map={"head": 0},
    )
    aliases = collect_aliases([s])
    regexes = {a.regex for a in aliases}
    assert regexes == {r"^[0-9]+$", r"^([0-9]+x)?$"}
    names = {a.name for a in aliases}
    assert "Digit" in names
    assert "Pattern" in names


def test_collect_aliases_empty_for_no_patterns():
    """A grammar with only literals + rulerefs has no pattern aliases."""
    s = _spec(
        "r",
        "sequence",
        [
            IrItem(IrLiteral("hi"), Quantifier(1, 1)),
            IrItem(IrRuleRef("expr"), Quantifier(1, 1)),
        ],
    )
    assert not collect_aliases([s])
