"""Adjacent same-class items of a text-only rule as one — the PDA's own view.

A text-only rule's value is the text it matched, so where one run of a class
ends inside it and the next begins is read by nothing. Over one class,
``C{a,b} C{c,d}`` derives exactly the strings ``C{a+c, b+d}`` does, so
``[a-z]* [a-z]``, ``[a-z] [a-z]*`` and ``[a-z]+`` are one item here, and
compile to one program: none pays a window to place a boundary nothing reads.

Applied to the grammar the predictive descent runs, and to nothing else. The
canonical grammar is the grammar's own normal form and does not change for
speed; Earley, and every island sub-parse, run the items as authored. This is
the canonical pass's literal-run merge, stated over class items and kept here.
"""

from __future__ import annotations

from lexic.ir import (
    IrAlternation,
    IrAst,
    IrCharClass,
    IrItem,
    IrNone,
    IrQuantifier,
    IrRule,
    IrSeq,
    IrSequence,
)
from lexic.parsing.pda.analysis.conflicts import text_only


def fused_grammar(grammar: IrAst) -> IrAst:
    """``grammar`` with every text-only rule's adjacent same-class items fused.

    :param grammar: The grammar the PDA compiles.
    :returns: The fused grammar; ``grammar`` itself when nothing fuses.
    """
    rules = tuple(
        _fused_rule(rule) if text_only(rule) else rule for rule in grammar.rules
    )
    if all(new is old for new, old in zip(rules, grammar.rules)):
        return grammar
    return IrAst(rules=IrSeq(*rules), start=str(grammar.start))


def _fused_rule(rule: IrRule) -> IrRule:
    """``rule`` with each arm's adjacent same-class items fused, or itself."""
    arms = tuple(_fused_arm(arm) for arm in rule.body)
    if all(new is old for new, old in zip(arms, rule.body)):
        return rule
    return IrRule(str(rule.name), IrAlternation(*arms), rule.semantic)


def _fused_arm(arm: IrSequence) -> IrSequence:
    """One arm with each run of one class that loops folded into one item, or
    itself. A run of fixed counts alone is left: no window places a boundary
    in it, so fusing it saves nothing."""
    out: list[IrItem] = []
    run: list[IrItem] = []
    for item in (*arm, None):
        if item is not None and run and _same_class(run[0], item):
            run.append(item)
            continue
        if len(run) > 1 and any(not one.quantifier.fixed() for one in run):
            out.append(IrItem(run[0].atom, _summed(run)))
        else:
            out.extend(run)
        run = [] if item is None else [item]
    return arm if len(out) == len(arm) else IrSequence(*out)


def _same_class(one: IrItem, other: IrItem) -> bool:
    """Whether two items are runs of one character class."""
    return isinstance(one.atom, IrCharClass) and other.atom == one.atom


def _summed(run: list[IrItem]) -> IrQuantifier:
    """The bounds of adjacent runs of one class, read as one run."""
    his = [one.quantifier.upper() for one in run]
    lo = sum(one.quantifier.lo for one in run)
    if any(hi is None for hi in his):
        return IrQuantifier(lo, IrNone)
    return IrQuantifier(lo, sum(hi for hi in his if hi is not None))
