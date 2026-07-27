"""Left-recursion detection — the predictive-descent impossibility check.

A predictive (top-down) machine cannot run left recursion: entering the rule
re-enters it at the same input position before consuming anything, an
unbounded descent. No gate family can license the decision away — a gate only
picks an arm, and the winning recursive arm still re-enters — so every rule
on a left-recursive cycle must island (the windowed Earley sub-parse handles
left recursion natively). Arm FIRST-overlap conflicts already island *most*
left recursion by accident: a direct left recursion's recursive arm has
``FIRST ⊇ FIRST(escape arm)``, a guaranteed overlap. The shapes that slip
through are a nullable-only escape arm (contributes no FIRST —
``root ::= root "a" | ""`` compiled to a clone and descended forever) and the
sole-arm degenerate (``x ::= x "a"``, no decision at all).

The relation is the **nullable-prefix left corner**: rule ``R`` directly
left-reaches ``S`` when some arm of ``R`` mentions ``ref(S)`` at a position
where everything before it can consume nothing. ``R`` is left-recursive iff
``R`` reaches itself in the transitive closure.

A leaf w.r.t. :mod:`lexic.parsing.pda.analysis.analysis` (the kwindow/noise
precedent): the analysis is taken as an ``Any``-typed oracle argument
(``rules`` / ``item_nullable``), so ``analysis`` imports this, never the
reverse. Atom steps route through an open :class:`~lexic.ir.mapping.IrTypeMap`
table with a raising default.
"""

from __future__ import annotations

from typing import Any, Sequence, cast

from lexic.ir import (
    IrAction,
    IrAlphabet,
    IrAlternation,
    IrCharClass,
    IrItem,
    IrLambda,
    IrLiteral,
    IrNot,
    IrRuleRef,
    IrSelf,
    IrTypeMap,
)

__all__ = ["left_recursive_names"]


def _corner_ruleref(_d: Any, n: IrSelf, nc: Sequence[Any]) -> None:
    """A ref in nullable-prefix position is a direct left corner."""
    nc[0].add(str(n))


def _corner_terminal(_d: Any, _n: IrSelf, _nc: object) -> None:
    """Terminals contribute no left corner."""


def _corner_alternation(d: Any, n: IrSelf, nc: Sequence[Any]) -> None:
    """An inline group's arms each contribute their own left corners."""
    for arm in cast(IrAlternation, n):
        _arm_corners(d, arm, nc[0])


_CORNER_ATOM: IrTypeMap = IrTypeMap(
    IrAction(IrLiteral, IrLambda(_corner_terminal)),
    IrAction(IrCharClass, IrLambda(_corner_terminal)),
    IrAction(IrNot, IrLambda(_corner_terminal)),
    IrAction(IrAlphabet, IrLambda(_corner_terminal)),
    IrAction(IrRuleRef, IrLambda(_corner_ruleref)),
    IrAction(IrAlternation, IrLambda(_corner_alternation)),
)


def _arm_corners(analysis: Any, items: Sequence[IrItem], out: set[str]) -> None:
    """Collect ``items``' left corners: refs reachable through a nullable prefix.

    Every atom in scan order contributes its refs; the scan stops after the
    first item that must consume (its predecessors are the nullable prefix).
    """
    for item in items:
        _CORNER_ATOM.resolve(item.atom).eval(analysis, item.atom, (out,))
        if not analysis.item_nullable(item):
            return


def left_recursive_names(analysis: Any) -> frozenset[str]:
    """The rules of ``analysis.rules`` that sit on a left-recursive cycle.

    Computes each rule's direct left-corner set, closes the relation
    transitively (chaotic iteration, the sibling fixpoints' idiom), and
    returns every rule that left-reaches itself.

    :param analysis: The analysis oracle (``rules``, ``item_nullable``).
    :returns: The left-recursive rule names, possibly empty.
    """
    reach: dict[str, set[str]] = {}
    for name, rule in analysis.rules.items():
        corners: set[str] = set()
        for arm in rule.body:
            _arm_corners(analysis, arm, corners)
        reach[name] = corners
    changed = True
    while changed:
        changed = False
        for corners in reach.values():
            for corner in list(corners):
                step = reach.get(corner)
                if step is not None and not step <= corners:
                    corners |= step
                    changed = True
    return frozenset(name for name, corners in reach.items() if name in corners)
