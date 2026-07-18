"""Tests for lexic.parsing.pda.analysis.leftrec — nullable-prefix left corners.

``left_recursive_names`` must flag exactly the rules on a left-recursive
cycle: those the predictive descent would re-enter at the same position. The
classification wiring test pins that such a rule islands unconditionally
(hard conflict note, no demotion, no gate analysis).
"""

from __future__ import annotations

from lexic.ir.nodes import IrAlternation, IrLiteral, IrRuleRef, IrSequence
from lexic.parsing.pda.analysis.leftrec import left_recursive_names
from tests.unit.lexic.parsing.ir_fixtures import analysis_of as _analysis
from tests.unit.lexic.parsing.ir_fixtures import item_of as _item
from tests.unit.lexic.parsing.ir_fixtures import rule_of as _rule

# ── the relation ──────────────────────────────────────────────────────


def test_direct_left_recursion_with_nullable_escape_detected():
    """root ::= root "a" | "" — the shape no FIRST overlap ever islands."""
    g = _analysis(
        _rule(
            "root",
            IrSequence(_item(IrRuleRef("root")), _item(IrLiteral("a"))),
            IrSequence(),
        )
    )
    assert left_recursive_names(g) == frozenset({"root"})


def test_direct_left_recursion_with_consuming_escape_detected():
    """root ::= root "a" | "b" — flagged structurally, not via FIRST overlap."""
    g = _analysis(
        _rule(
            "root",
            IrSequence(_item(IrRuleRef("root")), _item(IrLiteral("a"))),
            IrSequence(_item(IrLiteral("b"))),
        )
    )
    assert left_recursive_names(g) == frozenset({"root"})


def test_sole_arm_degenerate_detected():
    """x ::= x "a" — no decision at all, still an unbounded descent."""
    g = _analysis(_rule("x", IrSequence(_item(IrRuleRef("x")), _item(IrLiteral("a")))))
    assert left_recursive_names(g) == frozenset({"x"})


def test_indirect_cycle_flags_every_member():
    """a ::= b | "" and b ::= a "x" | "y" — both rules sit on the cycle."""
    g = _analysis(
        _rule("a", IrSequence(_item(IrRuleRef("b"))), IrSequence()),
        _rule(
            "b",
            IrSequence(_item(IrRuleRef("a")), _item(IrLiteral("x"))),
            IrSequence(_item(IrLiteral("y"))),
        ),
    )
    assert left_recursive_names(g) == frozenset({"a", "b"})


def test_ref_behind_nullable_prefix_detected():
    """root ::= opt root "x" | "" with nullable opt — root reaches itself."""
    g = _analysis(
        _rule(
            "root",
            IrSequence(
                _item(IrRuleRef("opt")),
                _item(IrRuleRef("root")),
                _item(IrLiteral("x")),
            ),
            IrSequence(),
        ),
        _rule("opt", IrSequence(_item(IrLiteral("o"), lo=0))),
    )
    assert left_recursive_names(g) == frozenset({"root"})


def test_ref_behind_consuming_prefix_not_flagged():
    """root ::= lead root | "" with consuming lead — right recursion, safe."""
    g = _analysis(
        _rule(
            "root",
            IrSequence(_item(IrRuleRef("lead")), _item(IrRuleRef("root"))),
            IrSequence(),
        ),
        _rule("lead", IrSequence(_item(IrLiteral("l")))),
    )
    assert left_recursive_names(g) == frozenset()


def test_right_recursion_not_flagged():
    """root ::= "a" root | "" — the classic safe shape."""
    g = _analysis(
        _rule(
            "root",
            IrSequence(_item(IrLiteral("a")), _item(IrRuleRef("root"))),
            IrSequence(),
        )
    )
    assert left_recursive_names(g) == frozenset()


def test_ref_inside_inline_group_arm_detected():
    """x ::= ("y" | x) "z" — a group arm's leading ref is a left corner."""
    group = IrAlternation(
        IrSequence(_item(IrLiteral("y"))), IrSequence(_item(IrRuleRef("x")))
    )
    g = _analysis(_rule("x", IrSequence(_item(group), _item(IrLiteral("z")))))
    assert left_recursive_names(g) == frozenset({"x"})


def test_rule_referencing_a_cycle_is_not_itself_flagged():
    """w ::= root over a left-recursive root: only the cycle member islands.

    ``w`` is safe to clone — its descent enters ``root`` through an island
    ref, never re-entering ``w`` at the same position.
    """
    g = _analysis(
        _rule("w", IrSequence(_item(IrRuleRef("root")))),
        _rule(
            "root",
            IrSequence(_item(IrRuleRef("root")), _item(IrLiteral("a"))),
            IrSequence(),
        ),
        start="w",
    )
    assert left_recursive_names(g) == frozenset({"root"})


def test_undefined_corner_ref_is_harmless():
    """A left corner naming an undefined rule closes to nothing."""
    g = _analysis(
        _rule("top", IrSequence(_item(IrRuleRef("missing")), _item(IrLiteral("z"))))
    )
    assert left_recursive_names(g) == frozenset()


# ── classification wiring ─────────────────────────────────────────────


def test_left_recursive_rule_islands_unconditionally():
    """The cycle member gets a hard conflict note and nothing else.

    No demotion, no gate analysis, no F1 marking — the rule islands before
    any gate family could claim to license it.
    """
    g = _analysis(
        _rule(
            "root",
            IrSequence(_item(IrRuleRef("root")), _item(IrLiteral("a"))),
            IrSequence(),
        )
    )
    assert "root" in g.islands
    assert any("left-recursive" in note for note in g.conflicts["root"])
    assert "root" not in g.demoted
    assert not g.fail_islands
