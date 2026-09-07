"""Tests for lexic.parsing.lift — the optional-nullable lift.

``R?`` where ``R`` itself derives empty is ambiguous on the empty span, so the
lift rewrites the occurrence to ``R``. These pin the four properties that make
that safe: it fires on a nullable target, it leaves a non-nullable one alone,
it rewrites in place so item positions survive, and it is idempotent.

Ported unchanged from ``test_fold.py`` when the lift moved out of the deleted
fold module; the assertions are byte-for-byte what they were.
"""

from lexic.ir import (
    IrAlternation,
    IrAst,
    IrItem,
    IrLiteral,
    IrQuantifier,
    IrRule,
    IrRuleRef,
    IrSeq,
    IrSequence,
)
from lexic.parsing.lift import lift_optional_nullables


def test_lift_rewrites_optional_ref_to_nullable_as_mandatory():
    """An optional (0,1) ref to a nullable rule is lifted to (1,1)."""
    empty = IrRule("empty", IrAlternation(IrSequence(IrItem(IrLiteral("")))))
    host = IrRule(
        "host",
        IrAlternation(IrSequence(IrItem(IrRuleRef("empty"), IrQuantifier(0, 1)))),
    )
    lifted = lift_optional_nullables(IrAst(rules=IrSeq(empty, host), start="host"))
    host_lifted = next(r for r in lifted.rules if str(r.name) == "host")
    item = host_lifted.body[0][0]
    assert item.atom == IrRuleRef("empty")
    assert item.quantifier == IrQuantifier(1, 1)


def test_lift_leaves_optional_ref_to_non_nullable_untouched():
    """An optional (0,1) ref to a non-nullable rule is left as-is."""
    solid = IrRule("solid", IrAlternation(IrSequence(IrItem(IrLiteral("z")))))
    host = IrRule(
        "host",
        IrAlternation(IrSequence(IrItem(IrRuleRef("solid"), IrQuantifier(0, 1)))),
    )
    lifted = lift_optional_nullables(IrAst(rules=IrSeq(solid, host), start="host"))
    host_lifted = next(r for r in lifted.rules if str(r.name) == "host")
    item = host_lifted.body[0][0]
    assert item.quantifier == IrQuantifier(0, 1)


def test_lift_preserves_positions_and_start():
    """The lift rewrites items in place: item count, order and start stable."""
    empty = IrRule("empty", IrAlternation(IrSequence(IrItem(IrLiteral("")))))
    host = IrRule(
        "host",
        IrAlternation(
            IrSequence(
                IrItem(IrLiteral("x")),
                IrItem(IrRuleRef("empty"), IrQuantifier(0, 1)),
                IrItem(IrLiteral("y")),
            )
        ),
    )
    lifted = lift_optional_nullables(IrAst(rules=IrSeq(empty, host), start="host"))
    assert lifted.start == "host"
    host_lifted = next(r for r in lifted.rules if str(r.name) == "host")
    arm = host_lifted.body[0]
    assert len(arm) == 3
    assert arm[0].atom == IrLiteral("x")
    assert arm[2].atom == IrLiteral("y")


def test_lift_is_idempotent():
    """Lifting an already-lifted grammar changes nothing further: once an
    item is (1, 1) the rewrite condition (``lo == 0``) no longer holds."""
    empty = IrRule("empty", IrAlternation(IrSequence(IrItem(IrLiteral("")))))
    host = IrRule(
        "host",
        IrAlternation(IrSequence(IrItem(IrRuleRef("empty"), IrQuantifier(0, 1)))),
    )
    ast = IrAst(rules=IrSeq(empty, host), start="host")
    once = lift_optional_nullables(ast)
    twice = lift_optional_nullables(once)
    assert twice == once
