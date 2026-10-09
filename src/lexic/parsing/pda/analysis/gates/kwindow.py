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

from collections.abc import Callable
from typing import Iterable, Iterator, Mapping, Sequence

from lexic.ir import (
    IrItem,
    IrQuantifier,
    IrRule,
    IrRuleRef,
    IrSelf,
)
from lexic.parsing.pda.analysis.gates.windows import (
    Depth,
    FollowWindows,
    KWindowFirst,
    Pref,
    collide,
    extend_follow,
    first_separating,
    windows_of,
)
from lexic.parsing.pda.core.charsets import CharSet


def _items(seq: Sequence[IrSelf]) -> list[IrItem]:
    """The :class:`IrItem` members of a sequence arm, in order (others skipped)."""
    return [i for i in seq if isinstance(i, IrItem)]


__all__ = [
    "FOLLOW_LOOP_K",
    "MAX_K",
    "arm_final_loop_depths",
    "arm_gate",
    "arm_windows",
    "follow_depths",
    "loop_gate",
    "window_depths",
    "rule_references",
    "stop_exit_settles",
]


MAX_K = 3
"""The widest lookahead window any gate tries (``k ≤ 3``)."""

FOLLOW_LOOP_K = 2
"""The one width :func:`arm_final_loop_depths` asks at.

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


# ── the gate classification (arm-selection + loop take/skip) ───────────────
#
# One gate per decision — the arms of an alternation, the take/skip of a loop —
# asked at whatever depths the caller supplies: the follow read one character
# deep (:func:`follow_depths`) or ``k`` deep through the grammar's FOLLOW_k
# windows (:func:`window_depths`, :func:`arm_final_loop_depths`).


def follow_depths(
    rules: Mapping[str, IrRule], follow: CharSet, max_k: int = MAX_K
) -> Iterator[Depth]:
    """Widths ``2..max_k``, every side END-extended by one FOLLOW character set.

    :param rules: The grammar's rule table.
    :param follow: The FOLLOW at the decision's end, read one character deep.
    :param max_k: The widest window to try (``≤ MAX_K``).
    """
    return ((k, KWindowFirst(rules, k), follow) for k in range(2, max_k + 1))


def window_depths(
    windows_at: Callable[[int], FollowWindows], label: str, max_k: int = MAX_K
) -> Iterator[Depth]:
    """Widths ``2..max_k``, every side END-extended by ``label``'s
    FOLLOW\\ :sub:`k` windows — so an empty (escape) arm carries exactly the rule's
    FOLLOW windows, and a FOLLOW-overlapping literal-led arm is told apart past
    the one character :func:`follow_depths` reaches (``cc-tail``'s ``- cc-hi``
    vs a trailing ``-`` before ``]``). Each width is built as it is tried.

    :param windows_at: The grammar's FOLLOW\\ :sub:`k` windows by width, each
        built once (:meth:`~...analysis.Follows.windows`).
    :param label: The rule whose FOLLOW windows extend the sides.
    :param max_k: The widest window to try (``≤ MAX_K``).
    """
    return (
        (k, fw.solver, fw.follow.get(label, set()))
        for k, fw in ((k, windows_at(k)) for k in range(2, max_k + 1))
    )


def arm_gate(
    arms: Sequence[Sequence[IrItem]], depths: Iterable[Depth]
) -> tuple[int, list[set[Pref]]] | None:
    """The first width among ``depths`` at which the arm-selection decision
    separates.

    :param arms: The alternation's arms (each a list of :class:`IrItem`), in
        body order — an escape (nullable) arm included.
    :param depths: The widths to ask at, each with its solver and follow.
    :returns: ``(k, per-arm prefix sets)`` at the separating ``k``, or ``None``
        when the arms collide at every depth (the decision stays island).
    """
    return first_separating(arms, depths)


def arm_windows(
    gate: tuple[int, list[set[Pref]]],
) -> tuple[tuple[tuple[CharSet, ...], ...], ...]:
    """A separating arm gate's per-arm windows, body-arm order — the spec the
    taxonomy stores and the runtime selects with."""
    return tuple(windows_of(s) for s in gate[1])


def loop_gate(
    items: Sequence[IrItem], idx: int, depths: Iterable[Depth]
) -> tuple[int, set[Pref], set[Pref]] | None:
    """The first width among ``depths`` at which item ``idx``'s take/skip loop
    separates.

    ``taken`` is the arm from the looping item's ``{1,hi}`` quantifier onward —
    :meth:`~KWindowFirst.arm_prefixes` unrolls it across the whole window, so a
    collision at any rep depth up to the budget surfaces (a hand-rolled 1∪2-rep
    union under-covers 3-rep windows at ``k = 3``); ``skip`` is the arm from the
    following item. Both are FOLLOW-extended.

    :param items: The enclosing arm's items.
    :param idx: The looping item's index.
    :param depths: The widths to ask at, each with its solver and follow.
    :returns: ``(k, taken set, skip set)`` at the separating ``k``, or ``None``
        (the loop decision stays island).
    """
    item = items[idx]
    rest = list(items[idx + 1 :])
    loop_item = IrItem(item.atom, IrQuantifier(1, item.quantifier.hi))
    found = first_separating([[loop_item, *rest], rest], depths)
    if found is None:
        return None
    k, (taken, skip) = found
    return k, taken, skip


def arm_final_loop_depths(
    rules: Mapping[str, IrRule],
    windows_at: Callable[[int], FollowWindows],
    items: Sequence[IrItem],
    idx: int,
    label: str,
) -> list[Depth] | None:
    """The depths an ARM-FINAL loop's take/skip decision is asked at under a
    ``k``-deep FOLLOW, or ``None`` where a precondition fails.

    :func:`loop_gate` takes the enclosing rule's FOLLOW as a single
    :class:`CharSet`, which :func:`~...windows.extend_follow` turns into exactly
    ONE length-1 window; :func:`~...windows.collide` compares two prefixes over
    their shorter length. So when the looping item is the arm's LAST, the skip
    side is one position wide and separation collapses to
    ``FIRST(item) ∩ FOLLOW(rule) = ∅`` — the single-character stop-set test.
    Every character past the first is compared against nothing, and widening
    ``k`` cannot change the verdict. This asks the same decision with both sides
    ``k`` deep, over the :class:`FollowWindows` fixpoint that already serves
    the arm gate's :func:`window_depths`.

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
    :param windows_at: The grammar's FOLLOW\\ :sub:`k` windows by width, each
        built once — asked only once the preconditions hold.
    :param items: The enclosing arm's items.
    :param idx: The looping item's index — must be the arm's last.
    :param label: The enclosing rule, whose FOLLOW\\ :sub:`k` extends both sides.
    :returns: The one depth to ask :func:`loop_gate` at, or ``None`` where a
        precondition fails.
    """
    if idx != len(items) - 1:
        return None  # not arm-final: the skip side is already k deep
    if rule_references(rules, label) != 1:
        return None  # a cost bound — see "Why one reference", not soundness
    windows = windows_at(FOLLOW_LOOP_K)
    follow = windows.follow.get(label, set())
    if not follow:
        return None  # nothing known to follow: a zero-length skip side collides
    return [(FOLLOW_LOOP_K, windows.solver, follow)]


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
        if any(collide(t, s, exits, eof=True) for t in take for s in stop):
            return False
    return True
