"""`A ::= A β | γ` as `A ::= γ (β)*` — the grammar the predictive descent runs.

The classical rewrite, applied to the PDA's own view of the grammar and to
nothing else: Earley parses the original and its model is the reference, so
rewriting the shared grammar would move the answer rather than reach it.

What comes out is a rule with ONE arm of two items — the base alternation, then
the step alternation under an unbounded quantifier. The ordinary loop gates
decide it like any other loop; no gate kind is added and no rule is generated,
because a generated rule would carry no class and no routine and the value
would have nowhere to come from.

The value is not this module's business. :mod:`.fold` carries the arm indices
back so the build can call the rule's own per-arm routine, and without that
half this rewrite would parse the same language into a different model.
"""

from __future__ import annotations

from lexic.ir import (
    IrAlternation,
    IrAst,
    IrItem,
    IrNone,
    IrQuantifier,
    IrRule,
    IrSeq,
    IrSequence,
    reachable,
)
from lexic.parsing.pda.compiler.leftrec.shape import Fold


def _group(arms: tuple[tuple[IrItem, ...], ...]) -> IrAlternation:
    """The arms as one alternation, ready to be an item's atom."""
    return IrAlternation(*(IrSequence(*items) for items in arms))


def rewritten(rule: IrRule, fold: Fold) -> IrRule:
    """``rule`` as ``(γ)(β)*`` — one arm, two items, same name.

    The name is kept because the CLONE is what the rest of the compiler and the
    product routines are keyed by: this changes how the rule is parsed, not
    which rule it is.

    :param rule: The left-recursive rule.
    :param fold: Its decomposition.
    :returns: The rewritten rule.
    """
    base = _group(tuple(tuple(rule.body[at]) for at in fold.base))
    steps = _group(tuple(step.rest for step in fold.steps))
    return IrRule(
        str(rule.name),
        IrAlternation(
            IrSequence(
                IrItem(base, IrQuantifier(1, 1)),
                IrItem(steps, IrQuantifier(0, IrNone)),
            )
        ),
    )


def fold_grammar(grammar: IrAst, folds: dict[str, Fold]) -> IrAst:
    """``grammar`` with every foldable rule rewritten, and the orphans dropped.

    The orphans are not housekeeping. `hoist_arms` gave each arm its own rule,
    so folding ``expr`` leaves ``expr-arm1 ::= expr op term`` referenced by
    nothing — and the FOLLOW fixpoint walks every rule, so that corpse puts
    ``op``'s FIRST straight back into FOLLOW(``expr``) and the new loop reads
    as "overlap, not gatable". The rule would still island, for a reason that
    is no longer in the language.

    :param grammar: The lifted grammar the PDA compiles.
    :param folds: The decompositions, by rule name.
    :returns: The rewritten grammar; ``grammar`` itself when nothing folds.
    """
    if not folds:
        return grammar
    folded = {
        str(rule.name): (
            rewritten(rule, folds[str(rule.name)]) if str(rule.name) in folds else rule
        )
        for rule in grammar.rules
    }
    live = reachable(folded, (str(grammar.start),))
    return IrAst(
        rules=IrSeq(*(rule for name, rule in folded.items() if name in live)),
        start=str(grammar.start),
    )
