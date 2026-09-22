"""Which rules the fold can take, and what their pieces are.

`A ::= A β1 | A β2 | γ1 | γ2` — DIRECT left recursion, with every recursive arm
continuing past the reference and every base arm not starting with it — is the
classical rewrite's precondition and the only shape read here. Anything else is
left alone and still islands: indirect recursion through another rule, a `β`
that can vanish (the loop would spin), a bare `A` arm (a cycle), a quantified
leading reference.

**The shape is not enough on its own.** Each boundary between pieces is one
application of an arm, but the descent settles it greedily, as it settles a
split. So a rule folds only when no piece can be lengthened into where a `β`
begins (:func:`settled`). Otherwise two different models could come out of one
text, and the rule is left to island, where Earley refuses it.

**The shape is read through the hoisted arm rules.** `hoist_arms` lifts every
alternation arm into a rule of its own before the PDA sees the grammar, so a
grammar whose source says `expr ::= expr op term | term` arrives as
`expr ::= expr-arm1 | term` with `expr-arm1 ::= expr op term`. Direct left
recursion is therefore indirect *by construction* here, and a reader matching
only the direct shape would find nothing to fold in anything the project ships
— which is a census, not a claim, and is asserted over every bench and
ground-truth grammar by
`test_nothing_in_the_corpus_is_directly_left_recursive`. Reading through a
one-armed rule that an arm consists of entirely is exactly undoing that hoist,
and is not a general inlining.
"""

from __future__ import annotations

from typing import NamedTuple

from lexic.ir import IrItem, IrRule, IrRuleRef
from lexic.parsing.pda.analysis.analysis import GrammarAnalysis
from lexic.parsing.pda.analysis.predicates import arms_extension, rule_extensions
from lexic.parsing.pda.compiler.specs import arm_items
from lexic.parsing.pda.core.charsets import CharSet


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
    name: str, rule: IrRule, rules: dict[str, IrRule], analysis: GrammarAnalysis
) -> Fold | None:
    """The rule's decomposition, or ``None`` when the fold cannot take it.

    The shape is necessary, not sufficient: the boundaries must be settled too
    (:func:`settled`).

    :param name: The rule's own name.
    :param rule: The rule.
    :param rules: Every rule by name, for reading through hoisted arms.
    :param analysis: The grammar's analysis — nullability, FIRST, EXTEND.
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
        if not rest or all(analysis.item_nullable(one) for one in rest):
            return None  # a vanishing β — the loop would spin
        if not hoisted:
            return None  # an un-hoisted recursive arm has no routine to fold
        steps.append(Recursive(at, hoisted, tuple(rest)))
    if not steps or not base:
        return None
    fold = Fold(tuple(base), tuple(steps))
    return fold if settled(rule, fold, analysis) else None


def settled(rule: IrRule, fold: Fold, analysis: GrammarAnalysis) -> bool:
    """Whether every boundary between the fold's pieces is fixed by the text.

    `(γ)(β)*` carves a match into pieces, and each boundary is one application
    of an ARM of the original rule. The descent settles where a piece ends the
    way it settles a split, greedily. That is only the grammar's answer if no
    piece can be lengthened past a point where a β could start. Where
    `item ::= item "a" | x` has `x ::= "b" "a"*`, the text `ba` is `x("ba")`
    or `item(x("b")) "a"`: two models, refused as ambiguous. The fold would
    return one of them.

    Take two carvings of one text and their first differing boundary. Both
    pieces there start at one place and one is a prefix of the other, so the
    character after the shorter one lengthens a complete piece (EXTEND) and
    starts a β. So γ's and β's EXTEND disjoint from β's FIRST leaves one
    carving, whatever the fold's width. Declared by analysis: a rule that fails
    it is left unfolded and islands, where Earley refuses what is ambiguous.
    """
    arms = tuple(rule.body)
    bases = [arm_items(arms[at]) for at in fold.base]
    steps = [list(step.rest) for step in fold.steps]
    starts = CharSet.EMPTY
    for rest in steps:
        starts = starts.union(analysis.seq_first(rest))
    maps = rule_extensions(analysis)
    return not (
        arms_extension(analysis, bases, maps).overlaps(starts)
        or arms_extension(analysis, steps, maps).overlaps(starts)
    )
