"""Tests for ir/canonical.py — the language-preserving canonical-form rewrites.

Each rewrite (1-9, per the module docstring) is isolated to a minimal grammar
so a failure points at the exact pass that broke, rather than a real
ground-truth fixture where several rewrites fire together (that coverage
lives in tests/integration/test_canonical_fixpoint.py).
"""

from __future__ import annotations

import time

import pytest

from lexic.exceptions import UnsupportedConstructError
from lexic.ir.base import IrSeq
from lexic.ir.canonical import canonicalize, fold_name
from lexic.ir.nodes import (
    IrAlphabet,
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

MAX_CODEPOINT = 0x10FFFF


def ast_for(body, start: str = "r", extra: tuple[IrRule, ...] = ()) -> IrAst:
    """A single-rule (plus optional extra rules) IrAst wrapping ``body``."""
    return IrAst(IrSeq(IrRule("r", body), *extra), start)


def canon_body(body, start: str = "r", extra: tuple[IrRule, ...] = ()):
    """canonicalize(ast_for(body, ...)) and return rule "r"'s canonical body."""
    ast = canonicalize(ast_for(body, start, extra))
    return next(rule.body for rule in ast.rules if rule.name == "r")


# ── rewrite 1: one-member char class -> literal ─────────────────────────


def test_rewrite1_one_member_charclass_becomes_literal():
    """A single-code-point char class collapses to an IrLiteral."""
    result = canon_body(IrCharClass(IrChr("x")))
    assert result == IrAlternation(IrSequence(IrItem(IrLiteral("x"))))


def test_rewrite1_multi_member_charclass_stays_a_charclass():
    """A multi-member char class is untouched by rewrite 1."""
    result = canon_body(IrCharClass(IrChr("x"), IrChr("y")))
    assert isinstance(result[0][0].atom, IrCharClass)


# ── rewrite 2: single-char/range arm merge ──────────────────────────────


def test_rewrite2_merges_single_char_literal_arms_into_one_charclass():
    """Adjacent single-char literal alternation arms fuse into one char class."""
    body = IrAlternation(
        IrSequence(IrItem(IrLiteral("a"))), IrSequence(IrItem(IrLiteral("b")))
    )
    result = canon_body(body)
    assert len(result) == 1
    atom = result[0][0].atom
    assert isinstance(atom, IrCharClass)
    assert atom.members() == [ord("a"), ord("b")]


def test_rewrite2_does_not_merge_a_multi_char_arm():
    """An arm covering more than one item is not char-class material — kept apart."""
    body = IrAlternation(
        IrSequence(IrItem(IrLiteral("a"))),
        IrSequence(IrItem(IrRuleRef("thing")), IrItem(IrLiteral("b"))),
    )
    result = canon_body(body, extra=(IrRule("thing", IrLiteral("T")),))
    assert len(result) == 2


def test_rewrite2_merges_charclass_arms_via_intervals():
    """Two char-class arms fuse by interval math into one coalesced class."""
    body = IrAlternation(
        IrSequence(IrItem(IrCharClass(IrRange(IrChr("0"), IrChr("4"))))),
        IrSequence(IrItem(IrCharClass(IrRange(IrChr("5"), IrChr("9"))))),
    )
    result = canon_body(body)
    assert result == IrAlternation(
        IrSequence(IrItem(IrCharClass(IrRange(IrChr("0"), IrChr("9")))))
    )


def test_rewrite2_does_not_merge_a_multi_char_literal_arm():
    """A multi-char literal arm is not char-class material — a mergeable run
    on either side of it stays separate (two flushes, not one)."""
    body = IrAlternation(
        IrSequence(IrItem(IrLiteral("a"))),
        IrSequence(IrItem(IrLiteral("b"))),
        IrSequence(IrItem(IrLiteral("cd"))),
        IrSequence(IrItem(IrLiteral("e"))),
        IrSequence(IrItem(IrLiteral("f"))),
    )
    result = canon_body(body)
    assert len(result) == 3
    assert isinstance(result[0][0].atom, IrCharClass)
    assert result[0][0].atom.members() == [ord("a"), ord("b")]
    assert result[1] == IrSequence(IrItem(IrLiteral("cd")))
    assert isinstance(result[2][0].atom, IrCharClass)
    assert result[2][0].atom.members() == [ord("e"), ord("f")]


def test_rewrite2_unmergeable_middle_arm_splits_into_two_flushes():
    """Two mergeable runs separated by an unmergeable arm merge independently."""
    body = IrAlternation(
        IrSequence(IrItem(IrLiteral("a"))),
        IrSequence(IrItem(IrLiteral("b"))),
        IrSequence(IrItem(IrRuleRef("thing"))),
        IrSequence(IrItem(IrLiteral("c"))),
        IrSequence(IrItem(IrLiteral("d"))),
    )
    result = canon_body(body, extra=(IrRule("thing", IrLiteral("T")),))
    assert len(result) == 3
    first, ref_arm, last = result
    assert isinstance(first[0].atom, IrCharClass)
    assert first[0].atom.members() == [ord("a"), ord("b")]
    assert ref_arm == IrSequence(IrItem(IrRuleRef("thing")))
    assert isinstance(last[0].atom, IrCharClass)
    assert last[0].atom.members() == [ord("c"), ord("d")]


def test_rewrite2_does_not_merge_a_quantified_charclass_arm():
    """A quantified char-class arm is excluded from the interval-merge run."""
    body = IrAlternation(
        IrSequence(IrItem(IrLiteral("a"))),
        IrSequence(IrItem(IrCharClass(IrChr("b")), IrQuantifier(0, 1))),
    )
    result = canon_body(body)
    assert len(result) == 2
    assert str(result[0][0].atom) == "a"
    assert result[1][0].quantifier == IrQuantifier(0, 1)


def test_rewrite2_merge_collapsing_to_a_single_point_becomes_a_literal():
    """Two arms of the identical single char merge to a one-member class,
    which then collapses to an IrLiteral via the same flush path (rewrite 1)."""
    body = IrAlternation(
        IrSequence(IrItem(IrLiteral("a"))), IrSequence(IrItem(IrLiteral("a")))
    )
    result = canon_body(body)
    assert result == IrAlternation(IrSequence(IrItem(IrLiteral("a"))))


def test_rewrite2_merges_a_unicode_complement_arm_without_materialising():
    """A ``[^a]`` complement arm (rewrite 4 → ~1.1M-point cover) merges by interval.

    The merge path must stay in the interval domain — enumerating the
    complement's members would build a million-entry list. The result is the
    complement class itself (the single-char literal arm falls inside it).
    """
    body = IrAlternation(
        IrSequence(IrItem(IrNot(IrCharClass(IrChr("a"))))),
        IrSequence(IrItem(IrLiteral("a"))),
    )
    result = canon_body(body)
    assert len(result) == 1
    atom = result[0][0].atom
    assert isinstance(atom, IrCharClass)
    assert atom == IrCharClass(IrRange(IrChr(0), IrChr(MAX_CODEPOINT)))


def test_rewrite2_unicode_complement_merge_stays_interval_native():
    """The whole canonicalize pass over a ``[^a]`` alternation arm is fast.

    A time bound (not a structural one) here guards the full pipeline —
    canonicalize() dispatching down through _merge_arms/flush — against a
    regression that reintroduces per-point materialisation (the Task 1 defect
    was ~1.1M IrChr constructions for exactly this shape).
    """
    body = IrAlternation(IrSequence(IrItem(IrNot(IrCharClass(IrChr("a"))))))
    start = time.perf_counter()
    canon_body(body)
    elapsed = time.perf_counter() - start
    assert elapsed < 0.5, (
        f"canonicalize of a Unicode-complement arm took {elapsed:.3f}s"
    )


# ── rewrite 3: adjacent literal run merge ───────────────────────────────


def test_rewrite3_merges_adjacent_unquantified_literals():
    """A run of adjacent unquantified literal items folds to one multi-char literal."""
    body = IrSequence(
        IrItem(IrLiteral("a")), IrItem(IrLiteral("b")), IrItem(IrLiteral("c"))
    )
    result = canon_body(body)
    assert result == IrAlternation(IrSequence(IrItem(IrLiteral("abc"))))


def test_rewrite3_does_not_merge_across_a_quantified_literal():
    """A quantified literal breaks the run — it does not fold into its neighbours."""
    body = IrSequence(
        IrItem(IrLiteral("a")),
        IrItem(IrLiteral("b"), IrQuantifier(0, 1)),
        IrItem(IrLiteral("c")),
    )
    result = canon_body(body)
    items = result[0]
    assert [str(item.atom) for item in items] == ["a", "b", "c"]
    assert items[1].quantifier == IrQuantifier(0, 1)


# ── rewrite 4: IrNot(charclass) -> positive complement ──────────────────


def test_rewrite4_not_charclass_becomes_positive_complement():
    """IrNot of a char class rewrites to its positive Unicode-complement spans."""
    body = IrItem(IrNot(IrCharClass(IrChr("a"))))
    result = canon_body(body)
    atom = result[0][0].atom
    assert isinstance(atom, IrCharClass)
    assert atom == IrCharClass(IrChr("a")).complement()


# ── rewrite 5: redundant single-arm/single-item group inline ────────────


def test_rewrite5_inlines_a_redundant_unquantified_group():
    """A single-arm, single-item, unquantified group splices into its parent sequence."""
    body = IrSequence(
        IrItem(IrAlternation(IrSequence(IrItem(IrLiteral("a"))))),
        IrItem(IrRuleRef("thing")),
    )
    result = canon_body(body, extra=(IrRule("thing", IrLiteral("T")),))
    assert result == IrAlternation(
        IrSequence(IrItem(IrLiteral("a")), IrItem(IrRuleRef("thing")))
    )


def test_rewrite5_does_not_inline_a_multi_arm_group():
    """A group with more than one arm is not redundant — left as a group atom.

    The arms are a literal and a ruleref (not char-class material), so
    rewrite 2's arm merge does not collapse them into a single-member
    class first — this isolates rewrite 5's own single-arm precondition.
    """
    body = IrItem(
        IrAlternation(
            IrSequence(IrItem(IrLiteral("a"))), IrSequence(IrItem(IrRuleRef("thing")))
        )
    )
    result = canon_body(body, extra=(IrRule("thing", IrLiteral("T")),))
    atom = result[0][0].atom
    assert isinstance(atom, IrAlternation)
    assert len(atom) == 2


# ── rewrite 6: quantifier pushed onto the inner atom ────────────────────


def test_rewrite6_pushes_quantifier_through_single_item_group():
    """``("!")?`` collapses to the plain quantified literal ``"!"?``."""
    body = IrItem(IrAlternation(IrSequence(IrItem(IrLiteral("!")))), IrQuantifier(0, 1))
    result = canon_body(body)
    item = result[0][0]
    assert item.atom == IrLiteral("!")
    assert item.quantifier == IrQuantifier(0, 1)


def test_rewrite6_leaves_a_quantified_inner_item_untouched():
    """A group whose inner item is itself quantified is not collapsed."""
    body = IrItem(
        IrAlternation(IrSequence(IrItem(IrLiteral("!"), IrQuantifier(0, 1)))),
        IrQuantifier(0, 1),
    )
    result = canon_body(body)
    atom = result[0][0].atom
    assert isinstance(atom, IrAlternation)


# ── rewrite 7: name folding + collision detection ───────────────────────


def test_rewrite7_folds_rule_names_and_refs_to_lowercase_hyphenated():
    """Rule names and refs fold: lowercase, ``_`` -> ``-``."""
    ast = IrAst(
        IrSeq(
            IrRule("My_Rule", IrRuleRef("Other_Thing")),
            IrRule("Other_Thing", IrLiteral("x")),
        ),
        "My_Rule",
    )
    result = canonicalize(ast)
    names = {rule.name for rule in result.rules}
    assert names == {"my-rule", "other-thing"}
    assert result.start == "my-rule"


def test_rewrite7_distinct_rule_name_collision_raises():
    """Two distinct rules folding to the same canonical name is an error."""
    ast = IrAst(
        IrSeq(IrRule("Foo", IrLiteral("a")), IrRule("foo", IrLiteral("b"))), "Foo"
    )
    with pytest.raises(UnsupportedConstructError):
        canonicalize(ast)


def test_fold_name_is_lowercase_underscore_to_hyphen():
    """fold_name is the raw name-folding function rewrite 7 applies."""
    assert fold_name("My_Rule_Name") == "my-rule-name"


# ── rewrite 8: char-class normal form ────────────────────────────────────


def test_rewrite8_charclass_deduped_sorted_and_coalesced():
    """A charclass with duplicate/unsorted/coalescible members normalises."""
    body = IrCharClass(IrChr("c"), IrChr("a"), IrChr("b"))
    result = canon_body(body)
    atom = result[0][0].atom
    assert atom == IrCharClass(IrChr("a"), IrChr("b"), IrChr("c")).normalized()


# ── rewrite 8b: empty-literal item elimination ───────────────────────────


def test_rewrite8b_drops_empty_literal_item_preserving_arm_shape():
    """An ``IrLiteral('')`` (epsilon) item is dropped; the arm shape stays."""
    body = IrSequence(IrItem(IrLiteral("")), IrItem(IrLiteral("x")))
    result = canon_body(body)
    assert result == IrAlternation(IrSequence(IrItem(IrLiteral("x"))))


# ── rewrite 9: canonical rule order ──────────────────────────────────────


def test_rewrite9_reorders_rules_start_first_by_reference():
    """Rules reorder start-first, then breadth-first by reference (RuleOrder)."""
    ast = IrAst(
        IrSeq(
            IrRule("unrelated", IrLiteral("z")),
            IrRule("b", IrLiteral("y")),
            IrRule("root", IrRuleRef("b")),
        ),
        "root",
    )
    result = canonicalize(ast)
    assert [rule.name for rule in result.rules] == ["root", "b", "unrelated"]


# ── idempotence over a composite grammar ─────────────────────────────────


def test_canonicalize_is_idempotent_on_a_composite_grammar():
    """canonicalize(canonicalize(ast)) == canonicalize(ast) across several rewrites at once."""
    ast = IrAst(
        IrSeq(
            IrRule(
                "Root",
                IrSequence(
                    IrItem(IrAlternation(IrSequence(IrItem(IrLiteral("a"))))),
                    IrItem(IrLiteral("")),
                    IrItem(IrLiteral("b")),
                    IrItem(IrNot(IrCharClass(IrChr("c"))), IrQuantifier(0, 1)),
                    IrItem(IrRuleRef("Digit")),
                ),
            ),
            IrRule("Digit", IrCharClass(IrChr("3"), IrChr("1"), IrChr("2"))),
        ),
        "Root",
    )
    once = canonicalize(ast)
    twice = canonicalize(once)
    assert twice == once


# ── IrAlphabet fencing (a foreign encoding — the UTF passes must not touch it) ──


def _alpha_item(inner, quant: IrQuantifier = IrQuantifier()) -> IrItem:
    """A sequence item wrapping ``inner`` in a token-encoding alphabet."""
    return IrItem(IrAlphabet("tok", inner), quant)


def test_canonicalize_does_not_collapse_id_form_token_to_a_glyph():
    """A lone token id stays an ordinal class, not a UTF glyph literal."""
    body = IrSequence(_alpha_item(IrCharClass(IrChr(1000))))
    inner = canon_body(body)[0][0].atom.inner
    assert inner == IrCharClass(IrChr(1000))


def test_canonicalize_does_not_complement_a_negated_token():
    """A negated token keeps its ``IrNot`` — no ``MAX_CODEPOINT`` blow-up."""
    body = IrSequence(_alpha_item(IrNot(IrCharClass(IrChr(1001)))))
    inner = canon_body(body)[0][0].atom.inner
    assert inner == IrNot(IrCharClass(IrChr(1001)))


def test_canonicalize_leaves_text_form_token_literal_verbatim():
    """A text-form token literal is preserved as-is."""
    body = IrSequence(_alpha_item(IrLiteral("<think>")))
    inner = canon_body(body)[0][0].atom.inner
    assert inner == IrLiteral("<think>")


def test_canonicalize_does_not_merge_token_and_char_arms():
    """A token arm and a char arm must never fuse into one class."""
    body = IrAlternation(
        IrSequence(_alpha_item(IrCharClass(IrChr(1)))),
        IrSequence(IrItem(IrCharClass(IrChr(97)))),
    )
    canon = canon_body(body)
    assert len(canon) == 2  # two distinct arms, not one merged class
    assert canon[0][0].atom == IrAlphabet("tok", IrCharClass(IrChr(1)))
    assert canon[1][0].atom == IrLiteral("a")  # the char arm still canonicalises


def test_canonicalize_still_canonicalises_around_an_alphabet():
    """Fencing the alphabet does not stop the rest of the rule normalising."""
    body = IrSequence(
        IrItem(IrCharClass(IrChr(48), IrChr(49), IrChr(50))),  # [012] -> [0-2]
        _alpha_item(IrCharClass(IrChr(5))),
    )
    canon = canon_body(body)
    assert canon[0][0].atom == IrCharClass(IrRange(IrChr(48), IrChr(50)))
    assert canon[0][1].atom == IrAlphabet("tok", IrCharClass(IrChr(5)))
