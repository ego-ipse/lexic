"""Pattern alias collection — module-level alias names for IrCharClass / pure-pattern IrGroup."""

from __future__ import annotations

import pytest

from lexic.codegen.aliases import (
    PatternAlias,
    _atom_regex_fragment,
    _name_for_charclass,
    collect_aliases,
    regex_for_charclass,
    regex_for_group,
)
from lexic.exceptions import UnsupportedConstructError
from lexic.ir.base import IrNone, IrSeq
from lexic.ir.nodes import (
    IrAlternation,
    IrAst,
    IrCharClass,
    IrChr,
    IrItem,
    IrLiteral,
    IrQuantifier,
    IrRange,
    IrRule,
    IrRuleRef,
    IrSequence,
)
from lexic.ir.operators import IrNot
from tests.unit.lexic.codegen.conftest import make_charclass_literal_group

_DIGIT = IrCharClass(IrRange(IrChr("0"), IrChr("9")))
_PLUS = IrQuantifier(1, IrNone)


def _one_rule(*items: IrItem) -> IrAst:
    """A one-rule grammar whose sole arm holds ``items``."""
    return IrAst(IrSeq(IrRule("r", IrAlternation(IrSequence(*items)))), "r")


# ── regex builders ────────────────────────────────────────────────────


def test_regex_for_charclass_simple():
    """[0-9]+ → ^[0-9]+$."""
    cc = IrCharClass(IrRange(IrChr("0"), IrChr("9")))
    assert regex_for_charclass(cc, IrQuantifier(1, IrNone)) == r"^[0-9]+$"


def test_regex_for_charclass_negated():
    """[^"] → ^[^"]$."""
    cc = IrCharClass(IrChr('"'))
    assert regex_for_charclass(cc, IrQuantifier(1, 1), negated=True) == r'^[^"]$'


def test_regex_for_charclass_optional():
    """[a-z]? → ^[a-z]?$."""
    cc = IrCharClass(IrRange(IrChr("a"), IrChr("z")))
    assert regex_for_charclass(cc, IrQuantifier(0, 1)) == r"^[a-z]?$"


# ── quantifier-suffix rendering (re-homed from utils/quantifiers) ──────


def test_suffix_required_is_empty():
    """(1,1) renders no suffix."""
    assert regex_for_charclass(_DIGIT, IrQuantifier(1, 1)) == r"^[0-9]$"


def test_suffix_zero_or_more_is_star():
    """(0,None) renders ``*``."""
    assert regex_for_charclass(_DIGIT, IrQuantifier(0, IrNone)) == r"^[0-9]*$"


def test_suffix_exact_count_is_braced():
    """(3,3) renders ``{3}``."""
    assert regex_for_charclass(_DIGIT, IrQuantifier(3, 3)) == r"^[0-9]{3}$"


def test_suffix_min_without_max_is_open_brace():
    """(2,None) renders ``{2,}``."""
    assert regex_for_charclass(_DIGIT, IrQuantifier(2, IrNone)) == r"^[0-9]{2,}$"


def test_suffix_bounded_range_is_braced_pair():
    """(2,5) renders ``{2,5}``."""
    assert regex_for_charclass(_DIGIT, IrQuantifier(2, 5)) == r"^[0-9]{2,5}$"


def test_name_for_charclass_tier2_hit_on_positive_form():
    """Tier-2 lookup matches the plain (non-negated) bracket form."""
    assert _name_for_charclass(_DIGIT) == "Digit"


def test_name_for_charclass_negated_never_matches_tier2():
    """CHARCLASS_NAMES has no negated (``[^...]``) entries — negated=True
    always falls through to the empty-string (Tier-3 fallback) result, even
    for a class whose positive form IS a Tier-2 hit."""
    assert _name_for_charclass(_DIGIT, negated=True) == ""


def test_regex_for_group_pure_pattern():
    """([a-h] 'x')? → ^([a-h]x)?$."""
    grp = make_charclass_literal_group()
    assert regex_for_group(grp, IrQuantifier(0, 1)) == r"^([a-h]x)?$"


def test_regex_for_group_alternation():
    """('foo' | 'bar')+ → ^(foo|bar)+$."""
    grp = IrAlternation(
        IrSequence(IrItem(IrLiteral("foo"), IrQuantifier(1, 1))),
        IrSequence(IrItem(IrLiteral("bar"), IrQuantifier(1, 1))),
    )
    assert regex_for_group(grp, IrQuantifier(1, IrNone)) == r"^(foo|bar)+$"


def test_atom_regex_fragment_ruleref_raises():
    """A rule ref has no pattern rendering — the open fragment table refuses it."""
    with pytest.raises(UnsupportedConstructError):
        _atom_regex_fragment(IrItem(IrRuleRef("expr")))


def test_atom_regex_fragment_stray_not_raises():
    """A stray IrNot (dead on canonical input) hits the raising default."""
    with pytest.raises(UnsupportedConstructError):
        _atom_regex_fragment(IrItem(IrNot(IrCharClass(IrChr('"')))))


# ── collect_aliases over a codegen grammar ────────────────────────────


def test_collect_aliases_dedupes_identical_patterns():
    """Two rules with identical [0-9]+ pattern share one alias."""
    grammar = IrAst(
        IrSeq(
            IrRule("a", IrAlternation(IrSequence(IrItem(_DIGIT, _PLUS)))),
            IrRule("b", IrAlternation(IrSequence(IrItem(_DIGIT, _PLUS)))),
        ),
        "a",
    )
    aliases = collect_aliases(grammar)
    assert len(aliases) == 1
    a = aliases[0]
    assert isinstance(a, PatternAlias)
    assert a.regex == r"^[0-9]+$"
    assert a.name == "Digit"  # Tier 2: bracket-only lookup → 'digit' → CamelCase


def test_collect_aliases_distinguishes_different_quantifiers():
    """[0-9] and [0-9]+ produce different aliases."""
    aliases = collect_aliases(
        _one_rule(IrItem(_DIGIT, IrQuantifier(1, 1)), IrItem(_DIGIT, _PLUS))
    )
    assert {a.regex for a in aliases} == {r"^[0-9]$", r"^[0-9]+$"}


def test_collect_aliases_naming_via_tier_pipeline():
    """Tier 2 lookup → CamelCase; Tier 3 fallback → 'Pattern' / 'Pattern2'."""
    lower = IrCharClass(IrRange(IrChr("a"), IrChr("z")))
    aliases = collect_aliases(_one_rule(IrItem(lower, _PLUS), IrItem(_DIGIT, _PLUS)))
    assert {a.name for a in aliases} == {"Lower", "Digit"}


def test_collect_aliases_disambiguates_same_base_name():
    """Two distinct [0-9] regexes (different quantifiers) yield Digit + Digit2."""
    aliases = collect_aliases(
        _one_rule(IrItem(_DIGIT, IrQuantifier(1, 1)), IrItem(_DIGIT, _PLUS))
    )
    assert [a.name for a in aliases] == ["Digit", "Digit2"]


def test_collect_aliases_skips_group_with_ruleref():
    """A group containing an IrRuleRef does not produce a PatternAlias."""
    grp = IrAlternation(
        IrSequence(
            IrItem(IrLiteral("("), IrQuantifier(1, 1)),
            IrItem(IrRuleRef("expr"), IrQuantifier(1, 1)),
            IrItem(IrLiteral(")"), IrQuantifier(1, 1)),
        )
    )
    assert not collect_aliases(_one_rule(IrItem(grp, IrQuantifier(1, 1))))


def test_collect_aliases_pure_group_with_inner_charclass_emits_both():
    """Pure-pattern outer group + inner [0-9] both produce aliases."""
    grp = IrAlternation(
        IrSequence(
            IrItem(_DIGIT, _PLUS),
            IrItem(IrLiteral("x"), IrQuantifier(1, 1)),
        )
    )
    aliases = collect_aliases(_one_rule(IrItem(grp, IrQuantifier(0, 1))))
    assert {a.regex for a in aliases} == {r"^[0-9]+$", r"^([0-9]+x)?$"}
    names = {a.name for a in aliases}
    assert "Digit" in names
    assert "Pattern" in names


def test_collect_aliases_empty_for_no_patterns():
    """A grammar with only literals + rulerefs has no pattern aliases."""
    aliases = collect_aliases(
        _one_rule(
            IrItem(IrLiteral("hi"), IrQuantifier(1, 1)),
            IrItem(IrRuleRef("expr"), IrQuantifier(1, 1)),
        )
    )
    assert not aliases
