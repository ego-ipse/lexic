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
    "stop_exit_settles",
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

    **Why one reference — a COST bound, not a soundness one.** The fixpoint
    unions every call site's continuation, and that union is a SUPERSET of any
    one site's. Disjointness against the superset therefore implies disjointness
    at every site: extra references can only make the proof harder to obtain,
    never make an obtained proof wrong. So the precondition is not what makes
    the gate sound — the direction of approximation above already does that.

    It is here because the fixpoint is whole-grammar work and a multiply
    referenced rule is refused before one is built. Measured over the roster and
    the ground-truth corpus: of the 27 arm-final loop conflicts that reach this
    gate, requiring one reference licenses exactly the same 6 as not requiring
    it, so the bound costs no reach on any grammar measured. (Dropping it
    licenses more *arm-final loops* in the abstract — but those are loops that
    never conflict, and a loop that never conflicts never consults this gate.)

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
        return None  # a cost bound — see "Why one reference", not soundness
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


def stop_exit_settles(
    windows: FollowWindows,
    items: Sequence[IrItem],
    idx: int,
    label: str,
    exits: CharSet,
) -> bool:
    """Whether a stop-set's first exit is the only way on, two characters deep.

    The loop at item ``idx`` of rule ``label``'s arm leaves at the first
    character of ``exits``. Taking that character instead is an iteration the
    rest of the text must still complete. Where no text can continue both ways
    for its next two characters, at most one of them completes: the exit, or
    a failure that bails. So the exit is the split answer.

    Checked at each reference site of ``label`` alone, never across them. The
    other carving differs from the one taken only in where this loop ends, so
    it keeps the enclosing arm, and both continue through the same site. Each
    side is that site's continuation, END-extended by its rule's FOLLOW\\ :sub:`k`
    (an over-approximation of the text after the rule, the same on both
    sides).

    :param windows: The grammar's FOLLOW\\ :sub:`k` windows at
        :data:`FOLLOW_LOOP_K`.
    :param items: The rule arm holding the loop.
    :param idx: The looping item's index.
    :param label: The rule the arm belongs to.
    :param exits: The characters the loop can exit at.
    :returns: ``True`` when no site lets both continue.
    """
    k = FOLLOW_LOOP_K
    rest = list(items[idx + 1 :])
    item = IrItem(items[idx].atom, IrQuantifier(1, items[idx].quantifier.hi))
    taken = windows.solver.arm_prefixes([item, *rest], k)
    stopped = windows.solver.arm_prefixes(rest, k)
    for site in windows.site_windows(label):
        take = extend_follow(taken, site, k)
        stop = extend_follow(stopped, site, k)
        if any(_both_go_on(t, s, exits) for t in take for s in stop):
            return False
    return True


def _both_go_on(take: Pref, stop: Pref, exits: CharSet) -> bool:
    """Whether one text fits a take window and a stop window that both begin
    with an exit character. A window's characters are what it knows, as for
    :func:`~.windows.collide`; a one-character window ENDs the input there, or
    says nothing about what comes next."""
    if not take[0] or not stop[0]:
        # An empty window is the end of input, unless nothing is known.
        return (not take[0] and take[1] != END) or (not stop[0] and stop[1] != END)
    lead = take[0][0].subtract(take[0][0].subtract(stop[0][0]))
    if not lead.overlaps(exits):
        return False
    if len(take[0]) > 1 and len(stop[0]) > 1:
        return take[0][1].overlaps(stop[0][1])
    take_ends = len(take[0]) == 1 and take[1] == END
    stop_ends = len(stop[0]) == 1 and stop[1] == END
    # One side ends the input where the other has more: disjoint. Both ending
    # right after the exit character lands here too, and collides: a guard, not
    # a case that arises, since an exit character is a HARD continuation
    # character of the clone that exits and a take must still meet one after it.
    return not (take_ends and len(stop[0]) > 1 or stop_ends and len(take[0]) > 1)
