"""FIRST_k over CharSet tuples — the k-window (bounded-lookahead) analysis.

The P2 substrate (Task 6.3): a decision the single-char FIRST analysis calls a
conflict may still separate under a ``k``-character window. :class:`KWindowFirst`
computes FIRST_k as sets of ``≤k``-length :class:`~lexic.parsing.pda.core.charsets
.CharSet` tuples (the exact co-finite algebra from P1), each tagged END / MORE /
UNK; :func:`arm_gate` / :func:`loop_gate` then ask whether an arm-selection or a
loop take/skip decision separates at ``k ≤ 3`` (positionwise CharSet overlap over
the min window — all-or-nothing per decision).

This is what structurally closes the retired ``prefixes.py``'s nullable hole: a
nullable arm keeps its states SHORT (an ε-derivation contributes the empty tuple
``()``), and short tuples collide with everything under
:func:`collide` by construction — there is no nullable oracle to store and forget
to consult. The semantics run on the production (exact) :class:`CharSet` and
the open-``IrTypeMap`` atom dispatch idiom.

A leaf w.r.t. :mod:`lexic.parsing.pda.analysis.analysis`: it takes the rule table
(``Mapping[str, IrRule]``) and the pre-computed FOLLOW sets it needs as plain
arguments, so ``analysis`` imports this, never the reverse.
"""

from __future__ import annotations

from typing import Mapping, Sequence

from lexic.ir import (
    IrItem,
    IrQuantifier,
    IrRule,
    IrRuleRef,
    IrSelf,
)
from lexic.parsing.pda.analysis.gates.windows import (
    END,
    FollowWindows,
    KWindowFirst,
    Pref,
    extend_follow,
    separable,
    windows_of,
)
from lexic.parsing.pda.core.charsets import CharSet


def _items(seq: Sequence[IrSelf]) -> list[IrItem]:
    """The :class:`IrItem` members of a sequence arm, in order (others skipped)."""
    return [i for i in seq if isinstance(i, IrItem)]


__all__ = [
    "FOLLOW_LOOP_K",
    "MAX_K",
    "arm_gate",
    "follow_arm_gate",
    "follow_loop_gate",
    "loop_gate",
    "rule_references",
]


MAX_K = 3
"""The widest lookahead window any gate tries (``k ≤ 3``)."""

FOLLOW_LOOP_K = 2
"""The one width :func:`follow_loop_gate` tries.

Not a budget to be raised. Measured across the roster's loop conflicts, every
decision FOLLOW\\ :sub:`k` settles is settled at ``k = 2``, nothing further
separates at 3 or 4, and the fixpoint's cost climbs from unmeasurable at 2 to
seconds at 4 on the self-grammars — which would put those seconds on COMPILING
every grammar that reaches this tier, in exchange for nothing.
"""


# ── atom-prefix dispatch (open IrTypeMap, budget on nc) ────────────────────


# ── the FIRST_k fixpoint ───────────────────────────────────────────────────


# ── separability + FOLLOW extension ────────────────────────────────────────


# ── FOLLOW_k windows (the k-deep generalization of FOLLOW) ─────────────────


def rule_references(rules: Mapping[str, IrRule], name: str) -> int:
    """How many times ``name`` is referenced anywhere in the grammar.

    A gate stored per RULE is applied at every use of it while being proved
    against ONE occurrence's continuation, so a gate whose proof reads a rule's
    FOLLOW is only sound where that FOLLOW belongs to a single site. Counting
    is the cheap way to know: one reference means the rule's FOLLOW IS its call
    site's continuation, and the union a FOLLOW fixpoint computes is a union of
    one.

    The walk is over each rule body's own tree, never through a reference, so
    it terminates on a recursive grammar without a visited set.

    :param rules: The grammar's rule table.
    :param name: The rule name to count references to.
    :returns: The number of :class:`IrRuleRef` nodes naming ``name``.
    """
    return sum(_refs_in(body, name) for body in rules.values())


def _refs_in(node: object, name: str) -> int:
    """References to ``name`` in one node's tree — IR records ARE tuples."""
    if isinstance(node, IrRuleRef):
        return int(str(node) == name)
    if isinstance(node, str) or not isinstance(node, tuple):
        return 0
    return sum(_refs_in(child, name) for child in node)


def follow_arm_gate(
    rules: Mapping[str, IrRule],
    start: str,
    arms: Sequence[Sequence[IrItem]],
    label: str,
    max_k: int = MAX_K,
) -> tuple[tuple[tuple[CharSet, ...], ...], ...] | None:
    """Per-arm windows at the smallest ``k ≤ max_k`` where ``label``'s arms
    separate under ``k``-deep FOLLOW, else ``None``.

    Each arm's FIRST\\ :sub:`k` prefixes are END-extended by the rule's
    FOLLOW\\ :sub:`k` windows — so an empty (escape) arm carries exactly the
    rule's FOLLOW windows, and a FOLLOW-overlapping literal-led arm is
    disambiguated past the single FOLLOW char :func:`arm_gate` reaches
    (``cc-tail``'s ``- cc-hi`` vs a trailing ``-`` before ``]``). The
    FOLLOW\\ :sub:`k` fixpoint is built here — the empty-arm demotion is its only
    caller, so a grammar that never reaches one never runs it.

    :param rules: The grammar's rule table.
    :param start: The start rule (the FOLLOW EOF seed).
    :param arms: The alternation's arms (each a list of :class:`IrItem`), in
        body order — the escape (nullable) arm included.
    :param label: The rule whose FOLLOW windows extend the arms.
    :param max_k: The widest window to try (``≤ MAX_K``).
    :returns: The per-arm window tuples at the separating ``k``, or ``None``.
    """
    for k in range(2, max_k + 1):
        fw = FollowWindows(rules, start, k)
        follow = fw.follow.get(label, set())
        sets = [
            extend_follow(fw.solver.arm_prefixes(list(arm), k), follow, k)
            for arm in arms
        ]
        if separable(sets):
            return tuple(windows_of(s) for s in sets)
    return None


# ── the gate classification (arm-selection + loop take/skip) ───────────────


def arm_gate(
    rules: Mapping[str, IrRule],
    arms: Sequence[Sequence[IrItem]],
    ext_follow: CharSet,
    max_k: int = 3,
) -> tuple[int, list[set[Pref]]] | None:
    """The smallest ``k ≤ max_k`` at which the arm-selection decision separates.

    :param rules: The grammar's rule table.
    :param arms: The alternation's arms (each a list of :class:`IrItem`).
    :param ext_follow: The FOLLOW at the alternation's end (for END extension).
    :param max_k: The largest window to try (``≤ 3``).
    :returns: ``(k, per-arm prefix sets)`` at the separating ``k``, or ``None``
        when the arms collide at every ``k ≤ max_k`` (the decision stays island).
    """
    for k in range(2, max_k + 1):
        solver = KWindowFirst(rules, k)
        sets = [
            extend_follow(solver.arm_prefixes(list(arm), k), ext_follow, k)
            for arm in arms
        ]
        if separable(sets):
            return k, sets
    return None


def loop_gate(
    rules: Mapping[str, IrRule],
    items: Sequence[IrItem],
    idx: int,
    rule_follow: CharSet,
    max_k: int = 3,
) -> tuple[int, set[Pref], set[Pref]] | None:
    """The smallest ``k ≤ max_k`` at which item ``idx``'s take/skip loop separates.

    ``taken`` is the arm from the looping item's ``{1,hi}`` quantifier onward —
    :meth:`~KWindowFirst.arm_prefixes` unrolls it across the whole window, so a
    collision at any rep depth up to the budget surfaces (a hand-rolled 1∪2-rep
    union under-covers 3-rep windows at ``k = 3``); ``skip`` is the arm from the
    following item. Both are FOLLOW-extended.

    :param rules: The grammar's rule table.
    :param items: The enclosing arm's items.
    :param idx: The looping item's index.
    :param rule_follow: The enclosing rule's FOLLOW (for END extension).
    :param max_k: The largest window to try (``≤ 3``).
    :returns: ``(k, taken set, skip set)`` at the separating ``k``, or ``None``
        (the loop decision stays island).
    """
    item = items[idx]
    rest = list(items[idx + 1 :])
    loop_item = IrItem(item.atom, IrQuantifier(1, item.quantifier.hi))
    for k in range(2, max_k + 1):
        solver = KWindowFirst(rules, k)
        taken = solver.arm_prefixes([loop_item, *rest], k)
        skip = solver.arm_prefixes(rest, k)
        taken = extend_follow(taken, rule_follow, k)
        skip = extend_follow(skip, rule_follow, k)
        if separable([taken, skip]):
            return k, taken, skip
    return None


def follow_loop_gate(
    rules: Mapping[str, IrRule],
    start: str,
    items: Sequence[IrItem],
    idx: int,
    label: str,
) -> tuple[tuple[CharSet, ...], ...] | None:
    """An ARM-FINAL loop's take/skip decision under a ``k``-deep FOLLOW.

    :func:`loop_gate` takes the enclosing rule's FOLLOW as a single
    :class:`CharSet`, which :func:`~...windows.extend_follow` turns into exactly
    ONE length-1 window; :func:`~...windows.collide` compares two prefixes over
    their shorter length. So when the looping item is the arm's LAST, the skip
    side is one position wide and separation collapses to
    ``FIRST(item) ∩ FOLLOW(rule) = ∅`` — the single-character stop-set test.
    Every character past the first is compared against nothing, and widening
    ``k`` cannot change the verdict. This asks the same decision with both sides
    ``k`` deep, over the :class:`FollowWindows` fixpoint that already serves
    :func:`follow_arm_gate`.

    **Soundness — the direction of approximation.** ``taken`` is FIRST\\ :sub:`k`
    of one more iteration, an over-approximation of what a real continuation can
    look like. ``skip`` is built from the SOFT FOLLOW, which over-approximates
    what can follow a real exit — soft is the correct side here, and the hard
    tail would be unsound because it is too small. Two over-approximations that
    are disjoint imply the true sets are disjoint, so a separation proved here is
    stronger than the runtime needs: the window admits every real continuation
    and no real exit.

    **Why one reference.** The fixpoint unions every call site's continuation. A
    window separating in the union need not separate at the site that runs, so
    the licence is withheld unless the rule is referenced exactly once — then the
    union is a union of one. This also keeps the fixpoint off grammars that
    cannot use it: a multiply-referenced rule is refused before one is built.

    :param rules: The grammar's rule table.
    :param start: The start rule name (the FOLLOW fixpoint's EOF seed).
    :param items: The enclosing arm's items.
    :param idx: The looping item's index — must be the arm's last.
    :param label: The enclosing rule, whose FOLLOW\\ :sub:`k` extends both sides.
    :returns: The ``taken`` windows, ready for the ``GATE_KWIN`` runtime op, or
        ``None`` where any precondition fails or the decision does not separate.
    """
    if idx != len(items) - 1:
        return None  # not arm-final: `loop_gate`'s skip side is already k deep
    if rule_references(rules, label) != 1:
        return None
    k = FOLLOW_LOOP_K
    windows = FollowWindows(rules, start, k)
    follow = windows.follow.get(label, set())
    if not follow:
        return None  # nothing known to follow: a zero-length skip side collides
    item = items[idx]
    loop_item = IrItem(item.atom, IrQuantifier(1, item.quantifier.hi))
    taken = extend_follow(windows.solver.arm_prefixes([loop_item], k), follow, k)
    skip = extend_follow({((), END)}, follow, k)
    return windows_of(taken) if separable([taken, skip]) else None
