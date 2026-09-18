"""Which rules the fold can take, and what their pieces are.

`A ::= A β1 | A β2 | γ1 | γ2` — DIRECT left recursion, with every recursive arm
continuing past the reference and every base arm not starting with it — is the
classical rewrite's precondition and the only shape read here. Anything else is
left alone and still islands: indirect recursion through another rule, a `β`
that can vanish (the loop would spin), a bare `A` arm (a cycle), a quantified
leading reference.

**The shape is read through the hoisted arm rules.** `hoist_arms` lifts every
alternation arm into a rule of its own before the PDA sees the grammar, so a
grammar whose source says `expr ::= expr op term | term` arrives as
`expr ::= expr-arm1 | term` with `expr-arm1 ::= expr op term`. Direct left
recursion is therefore indirect *by construction* here, and a test for the
direct shape matches nothing. Reading through a one-armed rule that an arm
consists of entirely is exactly undoing that hoist, and is not a general
inlining.
"""

from __future__ import annotations

from typing import NamedTuple

from lexic.ir import IrItem, IrRule, IrRuleRef
from lexic.parsing.pda.compiler.specs import arm_items


class Recursive(NamedTuple):
    """One recursive arm, as the fold needs it.

    :ivar at: The arm's index in the rule's body.
    :ivar rule: The name of the hoisted arm rule this arm consists of — the
        rule whose ROUTINE builds the nested node, and therefore the one an
        iteration folds through. Empty when the arm was not hoisted, which
        the fold refuses: without a routine there is nothing to build with.
    :ivar rest: The arm's items past the leading self-reference: the `β`.
    """

    at: int
    rule: str
    rest: tuple[IrItem, ...]


class Fold(NamedTuple):
    """One rule's foldable decomposition.

    :ivar base: The indices of the arms that do not begin with the rule.
    :ivar steps: The recursive arms, in body order.
    """

    base: tuple[int, ...]
    steps: tuple[Recursive, ...]


def through_hoist(items: list[IrItem], rules: dict[str, IrRule]) -> list[IrItem]:
    """An arm, with a hoisted single-reference arm rule read through.

    Only an arm that consists ENTIRELY of one reference to a rule with exactly
    one arm is read through — that is what `hoist_arms` produces and nothing
    else. A reference to a multi-armed rule stays a reference, because
    inlining it would be a different transformation with a different proof.
    """
    if len(items) != 1 or not isinstance(items[0].atom, IrRuleRef):
        return items
    target = rules.get(str(items[0].atom))
    if target is None or len(target.body) != 1:
        return items
    return arm_items(target.body[0])


def _leads_with(items: list[IrItem], name: str) -> bool:
    """Whether the arm begins with exactly one reference to ``name``."""
    if not items or not isinstance(items[0].atom, IrRuleRef):
        return False
    quantifier = items[0].quantifier
    return (
        str(items[0].atom) == name
        and int(quantifier.lo) == 1
        and isinstance(quantifier.hi, int)
        and int(quantifier.hi) == 1
    )


def any_candidate(rules: dict[str, IrRule]) -> bool:
    """Whether ANY rule even leads an arm with a reference to itself.

    A cheap structural pre-test, so the fold costs nothing on a grammar it
    cannot serve. The full test needs a nullability oracle, and building one
    means a second :class:`GrammarAnalysis` over every rule; almost every
    grammar's answer is "no" and should be reached without paying for one.

    Deliberately weaker than :func:`foldable`: it may say yes where the full
    test says no, never the reverse. A pre-test that could say NO wrongly would
    silently stop folding a rule that qualifies.
    """
    for name, rule in rules.items():
        for arm in rule.body:
            items = through_hoist(arm_items(arm), rules)
            if (
                items
                and isinstance(items[0].atom, IrRuleRef)
                and str(items[0].atom) == name
            ):
                return True
    return False


def foldable(
    name: str, rule: IrRule, rules: dict[str, IrRule], nullable
) -> Fold | None:
    """The rule's decomposition, or ``None`` when the fold cannot take it.

    :param name: The rule's own name.
    :param rule: The rule.
    :param rules: Every rule by name, for reading through hoisted arms.
    :param nullable: ``item -> bool`` — whether an item can consume nothing.
    :returns: The decomposition, or ``None``.
    """
    base: list[int] = []
    steps: list[Recursive] = []
    for at, arm in enumerate(rule.body):
        raw = arm_items(arm)
        items = through_hoist(raw, rules)
        hoisted = "" if items is raw else str(raw[0].atom)
        if not _leads_with(items, name):
            if any(
                isinstance(one.atom, IrRuleRef) and str(one.atom) == name
                for one in items[:1]
            ):
                return None  # leads with a quantified self-reference
            base.append(at)
            continue
        rest = items[1:]
        if not rest or all(nullable(one) for one in rest):
            return None  # a vanishing β — the loop would spin
        if not hoisted:
            return None  # an un-hoisted recursive arm has no routine to fold
        steps.append(Recursive(at, hoisted, tuple(rest)))
    if not steps or not base:
        return None
    return Fold(tuple(base), tuple(steps))
