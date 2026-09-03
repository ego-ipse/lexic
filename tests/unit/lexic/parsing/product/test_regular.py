"""Tests for lexic.parsing.product.regular — the authoritative regular proof.

Two obligations are pinned with a mutation control that proves each check is
load-bearing rather than merely present: an inline group owes the same
first-disjoint/ordered-literal obligations a rule body does
(``_group_holds``), and a rule reached through a reference is proved against
its OWN continuation, not the region's (``_references_hold``). For four of
the declining shapes, the decline is also shown to prevent a concrete wrong
answer: the pattern an unsound proof would license is built directly and
compared against what the grammar's own engine derives.
"""

from __future__ import annotations

import pytest

import lexic.parsing.product.regular as regular
from lexic.compile import canonical_grammar, compile_text
from lexic.exceptions import UnsupportedConstructError
from lexic.grammars import GBNF_FLAVOUR
from lexic.ir import IrRule
from lexic.parsing.pda.core.charsets import CharSet
from lexic.parsing.pda.core.scanner import build_recognizer
from lexic.parsing.product.regular import prove_regular

RELATION = (
    "root ::= expr op expr\n"
    "expr ::= [a-z]+\n"
    'op ::= ("<=" | "<" | "==" | "!=" | ">=" | ">")\n'
)
"""Ordered literal arms one character cannot separate — the sound shortcut."""


def _rules(source: str) -> dict[str, IrRule]:
    """The canonical rule table of one GBNF source."""
    ast = canonical_grammar(source, GBNF_FLAVOUR)
    return {str(rule.name): rule for rule in ast.rules}


def _proves(source: str, root: str, tail: str) -> bool:
    """Whether ``root``'s region proves regular against ``tail``."""
    return prove_regular(_rules(source), root, CharSet.from_chars(*tail)) is not None


def _licensed_extent(source: str, root: str, document: str) -> int:
    """What the possessive pattern for ``root`` alone consumes at position 0.

    Built directly (bypassing the proof), so a decline's value is measured
    against what WOULD have been licensed, not merely asserted.
    """
    recognizer = build_recognizer(_rules(source), frozenset({root}))
    assert recognizer is not None
    matched = recognizer.pats[recognizer.index[root]].match(document, 0)
    return -1 if matched is None else matched.end()


# ── the four unsound group shapes decline ────────────────────────────────

UNSOUND = pytest.mark.parametrize(
    "source, root, tail",
    [
        pytest.param(
            'root ::= pair "c"\npair ::= ("a" | "ab")+\n', "pair", "c", id="a_ab_plus"
        ),
        pytest.param(
            'root ::= word "c"\nword ::= ("a" | "ab")\n', "word", "c", id="a_ab_once"
        ),
        pytest.param(
            'root ::= word "bc"\nword ::= ("ab" | "a")\n', "word", "b", id="ab_a_once"
        ),
        pytest.param(RELATION, "op", "=", id="relation_eq_may_follow"),
    ],
)


@UNSOUND
def test_unsound_group_shapes_decline(source, root, tail):
    """A group whose ordered commitment can disagree with the grammar earns
    no proof — declining is always safe."""
    assert not _proves(source, root, tail)


# ── the sound shapes keep proving — not a blanket refusal ───────────────


def test_relation_group_proves_when_the_munch_is_truly_forced():
    """Extended so ``=`` cannot follow, the same literals ARE forced."""
    assert _proves(RELATION, "op", "abz")


def test_reordered_literals_prove_when_the_longer_arm_comes_first():
    """``("ab" | "a")+`` — same literals as the unsound case, order fixes it."""
    assert _proves('root ::= pair "c"\npair ::= ("ab" | "a")+\n', "pair", "c")


# ── declining prevents a concrete wrong extent ───────────────────────────


def test_the_short_before_long_decline_prevents_reading_ab_as_a():
    """``("a"|"ab")`` before ``c``: the grammar means "ab"; the naive pattern
    would have matched only "a" and stranded the "b" — a genuinely wrong span,
    not merely a declined one."""
    source = 'root ::= word "c"\nword ::= ("a" | "ab")\n'
    model = compile_text(source).parse("abc", cores=1)
    meant = getattr(model, "word").to_text()
    assert meant == "ab"
    licensed = _licensed_extent(source, "word", "abc")
    assert licensed != len(meant)  # the would-be pattern disagrees with the grammar


def test_the_long_before_short_decline_prevents_reading_a_as_ab():
    """``("ab"|"a")`` before ``bc``: the grammar means "a"; the naive pattern
    would have greedily taken "ab" and stranded the following "b"."""
    source = 'root ::= word "bc"\nword ::= ("ab" | "a")\n'
    model = compile_text(source).parse("abc", cores=1)
    meant = getattr(model, "word").to_text()
    assert meant == "a"
    licensed = _licensed_extent(source, "word", "abc")
    assert licensed != len(meant)


def test_declining_an_ambiguous_shape_matches_the_engines_own_refusal():
    """A document the grammar refuses as ambiguous still has SOME possessive
    reading — the decline is what keeps a consult from silently picking one."""
    source = 'root ::= word tail\nword ::= ("a" | "ab")\ntail ::= "bc" | "c"\n'
    assert not _proves(source, "word", "bc")
    with pytest.raises(UnsupportedConstructError, match="ambiguous"):
        compile_text(source).parse("abc", cores=1)
    assert _licensed_extent(source, "word", "abc") > 0  # a reading DOES exist


# ── a referenced rule is proved against ITS OWN continuation ────────────

REFERENCED = pytest.mark.parametrize(
    "source",
    [
        pytest.param(
            'root ::= word "z"\nword ::= a b\na ::= ("px" | "p")\nb ::= "x"\n',
            id="referenced_group",
        ),
        pytest.param(
            'root ::= word "z"\nword ::= a b\na ::= "p" "x"?\nb ::= "x"\n',
            id="referenced_optional",
        ),
    ],
)


@REFERENCED
def test_a_rule_reached_by_reference_declines_the_regions_follow(source):
    """``a`` is followed by ``b`` (FIRST = "x"), never by the region's "z" —
    proving against "z" would ask the wrong question and must decline."""
    assert not _proves(source, "word", "z")


@REFERENCED
def test_the_regions_follow_would_have_licensed_a_wrong_answer(source):
    """Measured, not merely asserted: the pattern the wrong question would
    have licensed does not match "pxz" at all, though the grammar derives it."""
    model = compile_text(source).parse("pxz", cores=1)
    meant = getattr(model, "word").to_text()
    assert meant == "px"
    licensed = _licensed_extent(source, "word", "pxz")
    assert licensed != len(meant)


# ── mutation controls: each obligation is load-bearing ──────────────────


def test_neutralising_the_group_obligation_revives_every_unsound_shape(monkeypatch):
    """With ``_group_holds`` stubbed to always succeed, the unsound shapes
    that this module's own machinery declines would ALL prove again — proof
    that the obligation, not something else, is what makes them decline."""
    monkeypatch.setattr(regular, "_group_holds", lambda *_args: True)
    cases = [
        ('root ::= pair "c"\npair ::= ("a" | "ab")+\n', "pair", "c"),
        ('root ::= word "c"\nword ::= ("a" | "ab")\n', "word", "c"),
        ('root ::= word "bc"\nword ::= ("ab" | "a")\n', "word", "b"),
        (RELATION, "op", "="),
    ]
    for source, root, tail in cases:
        assert _proves(source, root, tail)
    # the sound shapes must not have depended on the same obligation
    assert _proves(RELATION, "op", "abz")
    assert _proves('root ::= pair "c"\npair ::= ("ab" | "a")+\n', "pair", "c")


def test_neutralising_the_reference_walk_revives_both_referenced_shapes(monkeypatch):
    """With every reference proved against the REGION's follow (the old,
    wrong question), both referenced shapes would prove again."""

    # Restore the exact old behaviour: thread the REGION tail to every
    # reference instead of each reference's own remainder.
    def _old_question(first, rules, items, tail, proved):
        from lexic.ir import IrAlternation, IrRuleRef

        for item in items:
            atom = item.atom
            if isinstance(atom, IrRuleRef):
                if not regular._closure_holds(first, rules, str(atom), tail, proved):
                    return False
            elif isinstance(atom, IrAlternation) and not all(
                _old_question(first, rules, regular._items(arm), tail, proved)
                for arm in atom
            ):
                return False
        return True

    monkeypatch.setattr(regular, "_references_hold", _old_question)
    for source in (
        'root ::= word "z"\nword ::= a b\na ::= ("px" | "p")\nb ::= "x"\n',
        'root ::= word "z"\nword ::= a b\na ::= "p" "x"?\nb ::= "x"\n',
    ):
        assert _proves(source, "word", "z")
