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
to consult. The normative reference is
``zzz_current_work/260706-unified-parse-engine/poc_v4_verify.py`` part 4; this
mirrors its semantics on the production (exact) :class:`CharSet` and the
open-``IrTypeMap`` atom dispatch idiom.

A leaf w.r.t. :mod:`lexic.parsing.pda.analysis.analysis`: it takes the rule table
(``Mapping[str, IrRule]``) and the pre-computed FOLLOW sets it needs as plain
arguments, so ``analysis`` imports this, never the reverse. It also homes the
older 2-char LL(2) prefix machinery (:func:`two_prefix_seq` /
:func:`atom_two_prefix`, the pivot-6 ``pairs`` substrate) as free functions
over the analysis — superseded by the k-window fixpoint for demotion, still
the :class:`~lexic.parsing.pda.compiler.clones.PairGate` source.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence, cast

from lexic.ir import (
    IrAction,
    IrAlternation,
    IrCharClass,
    IrItem,
    IrLambda,
    IrLiteral,
    IrNot,
    IrQuantifier,
    IrRule,
    IrRuleRef,
    IrSelf,
    IrTypeMap,
)
from lexic.parsing.pda.analysis.gates.windows import (
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
    "MAX_K",
    "arm_gate",
    "follow_arm_gate",
    "loop_gate",
    "two_prefix_seq",
    "group_two_prefix",
    "atom_two_prefix",
]


MAX_K = 3
"""The widest lookahead window any gate tries (``k ≤ 3``)."""


# ── atom-prefix dispatch (open IrTypeMap, budget on nc) ────────────────────


# ── the FIRST_k fixpoint ───────────────────────────────────────────────────


# ── separability + FOLLOW extension ────────────────────────────────────────


# ── FOLLOW_k windows (the k-deep generalization of FOLLOW) ─────────────────


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


# ── 2-char LL(2) prefix machinery (the pivot-6 ``pairs`` substrate) ────────
# Moved from ``analysis.py`` (C0302 headroom); superseded by the k-window
# fixpoint for demotion, still the PairGate source via ``loop_policy``.


_MAX_PAIR_PRODUCT = 4096
"""Cap on the ``|FIRST(a)| * |FIRST(b)|`` product a 2-char prefix set will
enumerate; a wider product is treated as non-derivable (``None``)."""


def _single_literal(_d: object, n: IrSelf, _nc: object) -> frozenset[str] | None:
    """The single leading char of a non-empty literal, as a one-element set."""
    text = str(n)
    return frozenset({text[0]}) if text else None


def _single_charclass(_d: object, n: IrSelf, _nc: object) -> frozenset[str] | None:
    """The member set of a positive char class; ``None`` if it went co-finite."""
    assert isinstance(n, IrCharClass)
    cs = CharSet.from_charclass(n)
    return None if cs.negated else cs.chars


def _single_none(_d: object, _n: IrSelf, _nc: object) -> frozenset[str] | None:
    """Rule refs, groups and negations are not single deterministic chars."""
    return None


def _two_literal(_d: object, n: IrSelf, _nc: object) -> frozenset[str] | None:
    """The 2-char prefix of a ≥2-char literal, else ``None``."""
    text = str(n)
    return frozenset({text[:2]}) if len(text) >= 2 else None


def _two_group(d: Any, n: IrSelf, _nc: object) -> frozenset[str] | None:
    """The union of the arms' 2-char prefixes, or ``None`` if any is underivable."""
    assert isinstance(n, IrAlternation)
    return group_two_prefix(d, n)


def _two_none(_d: object, _n: IrSelf, _nc: object) -> frozenset[str] | None:
    """A char class, negation or rule ref yields no standalone 2-char prefix."""
    return None


def _lead_literal(_d: object, n: IrSelf, _nc: object) -> frozenset[str] | None:
    """A leading ≥2-char literal's 2-char prefix, else ``None`` (literal-only)."""
    text = str(n)
    return frozenset({text[:2]}) if len(text) >= 2 else None


def _lead_none(_d: object, _n: IrSelf, _nc: object) -> frozenset[str] | None:
    """Only a leading literal short-circuits a sequence's 2-char prefix."""
    return None


_SINGLE: IrTypeMap = IrTypeMap(
    IrAction(IrLiteral, IrLambda(_single_literal)),
    IrAction(IrCharClass, IrLambda(_single_charclass)),
    IrAction(IrNot, IrLambda(_single_none)),
    IrAction(IrRuleRef, IrLambda(_single_none)),
    IrAction(IrAlternation, IrLambda(_single_none)),
)

_TWO_PREFIX: IrTypeMap = IrTypeMap(
    IrAction(IrLiteral, IrLambda(_two_literal)),
    IrAction(IrCharClass, IrLambda(_two_none)),
    IrAction(IrNot, IrLambda(_two_none)),
    IrAction(IrRuleRef, IrLambda(_two_none)),
    IrAction(IrAlternation, IrLambda(_two_group)),
)

_LEAD_PREFIX: IrTypeMap = IrTypeMap(
    IrAction(IrLiteral, IrLambda(_lead_literal)),
    IrAction(IrCharClass, IrLambda(_lead_none)),
    IrAction(IrNot, IrLambda(_lead_none)),
    IrAction(IrRuleRef, IrLambda(_lead_none)),
    IrAction(IrAlternation, IrLambda(_lead_none)),
)


def _single_chars(d: Any, atom: IrSelf) -> frozenset[str] | None:
    """The finite positive single-char set of ``atom``, or ``None``.

    A literal contributes its leading char, a positive char class its members;
    refs, groups, negations and co-finite classes yield ``None``. ``d`` is the
    nullability oracle (the :class:`~lexic.parsing.pda.analysis.analysis.GrammarAnalysis`
    at every call site — ``Any``-typed to keep this module a leaf).
    """
    return cast("frozenset[str] | None", _SINGLE.resolve(atom).eval(d, atom, ()))


def two_prefix_seq(d: Any, items: Sequence[IrItem]) -> frozenset[str] | None:
    """The 2-char prefix set of a sequence, or ``None`` (not derivable).

    A leading ≥2-char literal supplies it; else the first two non-nullable
    single-char atoms' cross-product, subject to :data:`_MAX_PAIR_PRODUCT`.
    ``d`` is the nullability oracle (see :func:`_single_chars`).
    """
    if items and not d.item_nullable(items[0]):
        atom = items[0].atom
        lead = cast(
            "frozenset[str] | None", _LEAD_PREFIX.resolve(atom).eval(d, atom, ())
        )
        if lead is not None:
            return lead
    if len(items) < 2:
        return None
    first_item, second_item = items[0], items[1]
    if d.item_nullable(first_item) or d.item_nullable(second_item):
        return None
    first_chars = _single_chars(d, first_item.atom)
    second_chars = _single_chars(d, second_item.atom)
    if first_chars is None or second_chars is None:
        return None
    if len(first_chars) * len(second_chars) > _MAX_PAIR_PRODUCT:
        return None
    return frozenset(a + b for a in first_chars for b in second_chars)


def group_two_prefix(d: Any, group: IrAlternation) -> frozenset[str] | None:
    """The union of a group's arms' 2-char prefixes, else ``None``."""
    out: set[str] = set()
    for arm in group:
        sub = two_prefix_seq(d, _items(arm))
        if sub is None:
            return None
        out |= sub
    return frozenset(out)


def atom_two_prefix(d: Any, atom: IrSelf) -> frozenset[str] | None:
    """The standalone 2-char prefix set of ``atom``, or ``None``.

    ``d`` is the nullability oracle (see :func:`_single_chars`).

    :raises UnsupportedConstructError: On an unregistered atom type.
    """
    return cast("frozenset[str] | None", _TWO_PREFIX.resolve(atom).eval(d, atom, ()))
