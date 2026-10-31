"""The optional-nullable lift — one engine-ambiguity policy over a grammar.

``R?`` where ``R`` itself derives empty is genuinely ambiguous on the empty
span: absent and present-but-empty are two derivations of one text, and the
engine refuses an ambiguity rather than picking. The lift removes the question
by rewriting the occurrence to ``R``, which is language-preserving and leaves
every item position untouched.

Its own module, and not beside :func:`~lexic.parsing.earley.normalize.normalize`
that it is always composed with, for one reason: it consumes the nullability
fixpoint from :mod:`lexic.parsing.pda.analysis`, and the Earley package is a
leaf with respect to the predictive one — an invariant a test enforces by
static grep. Sitting at the package root is what lets both engines and the
split planner reach it without either importing the other.
"""

from __future__ import annotations

from lexic.exceptions import UnsupportedConstructError
from lexic.ir import (
    IrAlternation,
    IrAst,
    IrItem,
    IrRule,
    IrRuleRef,
    IrSeq,
    IrSequence,
)

__all__ = ["lift_optional_nullables"]


def lift_optional_nullables(grammar: IrAst) -> IrAst:
    """Rewrite ``R?`` to ``R`` where ``R`` is nullable.

    An optional occurrence of a rule that itself derives empty is genuinely
    ambiguous on the empty span (absent vs empty match) — the engine raises on
    it. The lift is language-preserving (``R? == R`` for nullable ``R``) and
    keeps the empty match present as a zero-width kid, so item positions are
    untouched. Applied to the codegen grammar before :func:`normalize`.

    :param grammar: The instance grammar to lift.
    :returns: The lifted grammar (same rule order, same item positions).
    """
    rules = tuple(grammar.rules)
    # The engine's first pass on every grammar the compile seam hands it, so the
    # one place an arm is checked to hold only items: past here every reader
    # takes an arm as its items (``IrSequence`` passes an unknown element
    # through, for the emit side's rebuilds).
    stray = next(
        (
            (rule, element)
            for rule in rules
            for arm in rule.body
            for element in arm
            if not isinstance(element, IrItem)
        ),
        None,
    )
    if stray is not None:
        raise UnsupportedConstructError(
            f"rule `{stray[0].name}`: unsupported construct "
            f"`{type(stray[1]).__name__}` in an arm, where only items stand"
        )
    nullable = grammar.nullable()

    def lift_item(item: IrItem) -> IrItem:
        atom = item.atom
        quantifier = item.quantifier
        if (
            isinstance(atom, IrRuleRef)
            and str(atom) in nullable
            and quantifier.optional()
        ):
            return IrItem(atom)
        return item

    lifted = tuple(
        IrRule(
            rule.name,
            IrAlternation(
                *(IrSequence(*(lift_item(i) for i in arm)) for arm in rule.body)
            ),
            rule.semantic,
        )
        for rule in rules
    )
    return IrAst(rules=IrSeq(*lifted), start=grammar.start)
