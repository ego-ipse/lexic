"""FIRST_k over CharSet tuples — the k-window (bounded-lookahead) analysis.

The P2 substrate (Task 6.3): a decision the single-char FIRST analysis calls a
conflict may still separate under a ``k``-character window. :class:`KWindowFirst`
computes FIRST_k as sets of ``≤k``-length :class:`~lexic.parsing.pda.charsets
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

A leaf w.r.t. :mod:`lexic.parsing.pda.analysis`: it takes the rule table
(``Mapping[str, IrRule]``) and the pre-computed FOLLOW sets it needs as plain
arguments, so ``analysis`` imports this, never the reverse. It also homes the
older 2-char LL(2) prefix machinery (:func:`two_prefix_seq` /
:func:`atom_two_prefix`, the pivot-6 ``pairs`` substrate) as free functions
over the analysis — superseded by the k-window fixpoint for demotion, still
the :class:`~lexic.parsing.pda.clones.PairGate` source.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence, cast

from lexic.exceptions import UnsupportedConstructError
from lexic.ir.action import IrAction
from lexic.ir.base import IrLambda, IrLeaf, IrNoneType, IrSelf
from lexic.ir.mapping import IrTypeMap
from lexic.ir.nodes import (
    IrAlternation,
    IrCharClass,
    IrItem,
    IrLiteral,
    IrQuantifier,
    IrRule,
    IrRuleRef,
)
from lexic.ir.operators import IrNot
from lexic.parsing.pda.charsets import CharSet

__all__ = [
    "P2_DEMOTION_ENABLED",
    "KWindowFirst",
    "Pref",
    "END",
    "MORE",
    "UNK",
    "arm_gate",
    "loop_gate",
    "collide",
    "separable",
    "extend_follow",
    "windows_of",
    "two_prefix_seq",
    "group_two_prefix",
    "atom_two_prefix",
]

P2_DEMOTION_ENABLED = True
"""Master switch for P2 k-window demotion (Task 6.3, ON since part c landed).
A decision that separates at ``k ≤ 3`` is demoted from island to the k-window
gate the runtime executes (:data:`~lexic.parsing.pda.flatten._GATE_KWIN` loops,
:attr:`~lexic.parsing.pda.flatten._FlatClone.kwin_selectors` arm selection, the
EOF-exact :func:`~lexic.parsing.pda.flatten._window_admits` matcher), compiled
from the analysis-**stored** gate spec (:class:`~lexic.parsing.pda.analysis
.Taxonomy` ``arm_gates``/``loop_gates`` — single source, never recomputed).
When ``False`` the islanding path does not consult the k-window gates and the
island set is identical to pre-P2 (the A/B test seam)."""

END, MORE, UNK = "END", "MORE", "UNK"
"""A prefix state: END — the tuple is a complete derivation (may be extended by
FOLLOW); MORE — a longer derivation exists past the window; UNK — the window is
poisoned (an unexpanded/over-wide construct), which collides with everything."""

_STATE_CAP = 3000
"""Per-arm prefix-set cap; a wider fan-out poisons the arm to ``{((), UNK)}``
rather than enumerating exponentially (the poc's ``_STATE_CAP``)."""

Pref = tuple[tuple[CharSet, ...], str]
"""One FIRST_k prefix: a ``≤k``-length CharSet tuple plus its END/MORE/UNK state."""


def _items(seq: Sequence[IrSelf]) -> list[IrItem]:
    """The :class:`IrItem` members of a sequence arm, in order (others skipped)."""
    return [i for i in seq if isinstance(i, IrItem)]


# ── atom-prefix dispatch (open IrTypeMap, budget on nc) ────────────────────


class _Budget(IrLeaf[IrSelf, IrSelf]):
    """The remaining window budget ``r`` an atom may consume, riding ``nc``."""

    __slots__ = ("r",)

    r: int

    def __init__(self, r: int) -> None:
        self.r = r


def _kp_literal(_d: IrSelf, n: IrSelf, nc: Sequence[IrSelf]) -> set[Pref]:
    """A literal contributes one per-char CharSet tuple (END if it fits ``r``)."""
    r = _budget(nc)
    text = str(n)
    tup = tuple(CharSet.from_chars(c) for c in text[:r])
    return {(tup, END if len(text) <= r else MORE)}


def _kp_charclass(_d: IrSelf, n: IrSelf, _nc: Sequence[IrSelf]) -> set[Pref]:
    """A char class contributes its exact member CharSet, one position, END."""
    assert isinstance(n, IrCharClass)
    return {((CharSet.from_charclass(n),), END)}


def _kp_not(_d: IrSelf, n: IrSelf, _nc: Sequence[IrSelf]) -> set[Pref]:
    """An ``IrNot`` contributes the complement CharSet, one position, END."""
    assert isinstance(n, IrNot)
    inner = n[0]
    cs = CharSet.from_not(inner) if isinstance(inner, IrCharClass) else CharSet.ANY
    return {((cs,), END)}


def _kp_ruleref(d: IrSelf, n: IrSelf, nc: Sequence[IrSelf]) -> set[Pref]:
    """A rule ref's prefixes are the target rule's FIRST_r (cycle-guarded)."""
    return _kw(d).rule_prefixes(str(n), _budget(nc))


def _kp_alternation(d: IrSelf, n: IrSelf, nc: Sequence[IrSelf]) -> set[Pref]:
    """A group's prefixes are the union of its arms' FIRST_r."""
    assert isinstance(n, IrAlternation)
    kw = _kw(d)
    r = _budget(nc)
    out: set[Pref] = set()
    for arm in n:
        out |= kw.arm_prefixes(_items(arm), r)
    return out


def _budget(nc: Sequence[IrSelf]) -> int:
    """The remaining window budget off the ``nc`` cursor."""
    ctx = nc[0]
    assert isinstance(ctx, _Budget)
    return ctx.r


def _kw(d: IrSelf) -> "KWindowFirst":
    """The dispatching :class:`KWindowFirst` off the ``d`` slot."""
    assert isinstance(d, KWindowFirst)
    return d


_KW_ATOM: IrTypeMap = IrTypeMap(
    IrAction(IrLiteral, IrLambda(_kp_literal)),
    IrAction(IrCharClass, IrLambda(_kp_charclass)),
    IrAction(IrNot, IrLambda(_kp_not)),
    IrAction(IrRuleRef, IrLambda(_kp_ruleref)),
    IrAction(IrAlternation, IrLambda(_kp_alternation)),
)
"""Open atom-type prefix dispatch — an unregistered atom raises
:exc:`~lexic.exceptions.UnsupportedConstructError` on the miss."""


# ── the FIRST_k fixpoint ───────────────────────────────────────────────────


class KWindowFirst(IrLeaf[IrSelf, IrSelf]):
    """FIRST_k as sets of ``≤k``-length CharSet tuples, memoised per (rule, budget).

    Construct per window ``k`` over one grammar's rule table; :meth:`arm_prefixes`
    /:meth:`rule_prefixes` compute the bounded-lookahead prefix set of an arm or
    rule (recursion cycle-guarded via :attr:`busy` — a re-entered rule yields the
    poisoning ``{((), UNK)}``). The atom step routes through :data:`_KW_ATOM`; the
    analysis IS the dispatcher slot ``d`` and the per-atom budget rides ``nc``.

    :ivar rules: The rule table (name → :class:`~lexic.ir.nodes.IrRule`).
    :ivar k: The window width.
    :ivar memo: ``(rule, budget)`` → its prefix set.
    :ivar busy: ``(rule, budget)`` keys currently being computed (cycle guard).
    """

    __slots__ = ("rules", "k", "memo", "busy")

    rules: Mapping[str, IrRule]
    k: int
    memo: dict[tuple[str, int], set[Pref]]
    busy: set[tuple[str, int]]

    def __init__(self, rules: Mapping[str, IrRule], k: int) -> None:
        """Prepare the FIRST_k solver over ``rules`` at window ``k``."""
        self.rules = rules
        self.k = k
        self.memo = {}
        self.busy = set()

    def rule_prefixes(self, name: str, r: int) -> set[Pref]:
        """FIRST_r of rule ``name`` — the union of its arms' prefixes.

        A recursive re-entry (``name`` already on the stack) or an undefined rule
        yields ``{((), UNK)}`` (poison), keeping unbounded recursion finite and
        conservative.
        """
        key = (name, r)
        if key in self.memo:
            return self.memo[key]
        if key in self.busy or name not in self.rules:
            return {((), UNK)}
        self.busy.add(key)
        out: set[Pref] = set()
        for arm in self.rules[name].body:
            out |= self.arm_prefixes(_items(arm), r)
        self.busy.discard(key)
        self.memo[key] = out
        return out

    def atom_prefixes(self, atom: IrSelf, r: int) -> set[Pref]:
        """FIRST_r of a single atom (``r <= 0`` is the exhausted-window MORE state).

        :raises UnsupportedConstructError: On an unregistered atom type.
        """
        if r <= 0:
            return {((), MORE)}
        return _resolve(_KW_ATOM, atom).eval(self, atom, (_Budget(r),))

    def _apply(self, states: set[Pref], atom: IrSelf) -> set[Pref]:
        """Extend each END prefix (with window room) by ``atom``; others pass through."""
        nxt: set[Pref] = set()
        for tup, state in states:
            if state != END or len(tup) >= self.k:
                nxt.add((tup, state))
                continue
            for atup, astate in self.atom_prefixes(atom, self.k - len(tup)):
                nxt.add((tup + atup, astate))
        return nxt

    def arm_prefixes(self, items: Sequence[IrItem], r: int) -> set[Pref]:
        """FIRST_r of a sequence arm — sequential composition over its items.

        Each item's quantifier is unrolled up to ``min(hi, r)`` reps (``r`` for an
        unbounded loop): an optional item (``lo == 0``) keeps the pre-item states,
        each rep past ``lo`` accumulates. When ``lo`` exceeds the window budget
        (``lo > reps``) the derivation cannot complete inside the window, so the
        states after ``reps`` unrollings are unioned in with END demoted to MORE
        rather than dropped — dropping them silently empties a non-nullable arm
        (the retired ``prefixes.py`` vanishing-derivation hole). Prefixes are
        truncated to ``r`` (a truncated END becomes MORE). A per-arm fan-out past
        :data:`_STATE_CAP` poisons the arm to ``{((), UNK)}``.

        :raises UnsupportedConstructError: On an empty prefix set — unproducible
            from a parsed grammar (only a zero-arm empty-language alternation),
            but this is the silent-wrong-parse surface, so the invariant is a
            real raise (never an ``-O``-stripped assert) and the compile seam's
            opt-out turns it into "no PDA for this grammar".
        """
        states: set[Pref] = {((), END)}
        for item in items:
            if all(state != END or len(tup) >= r for tup, state in states):
                break
            lo = int(item.quantifier.lo)
            hi = item.quantifier.hi
            hi_i = None if isinstance(hi, IrNoneType) else int(hi)
            reps = r if hi_i is None else min(hi_i, r)
            acc: set[Pref] = set(states) if lo == 0 else set()
            cur = set(states)
            for rep in range(1, reps + 1):
                cur = self._apply(cur, item.atom)
                if rep >= lo:
                    acc |= cur
                if len(acc) > _STATE_CAP:
                    return {((), UNK)}
            if lo > reps:
                acc |= {(t, MORE if s == END else s) for t, s in cur}
            elif reps == 0:
                acc |= states
            states = {(tup[:r], state if len(tup) <= r else MORE) for tup, state in acc}
        if not states:
            raise UnsupportedConstructError(
                "kwindow: arm_prefixes yielded an empty prefix set "
                "(empty-language alternation arm)"
            )
        return states


def _resolve(table: IrTypeMap, atom: IrSelf) -> IrSelf:
    """Resolve ``atom`` in ``table`` (the raising-default open dispatch)."""
    return table.resolve(atom)


# ── separability + FOLLOW extension ────────────────────────────────────────


def collide(a: Pref, b: Pref) -> bool:
    """Whether two prefixes overlap positionwise over their min window.

    Two prefixes collide when every position of the shorter one's CharSet
    overlaps the other's — a shorter prefix (a nullable/short arm) collides with
    any longer prefix sharing its lead, which is exactly why ε keeps states short
    and short states are un-separable (the nullable hole closed structurally).
    """
    ta, tb = a[0], b[0]
    m = min(len(ta), len(tb))
    return all(ta[i].overlaps(tb[i]) for i in range(m))


def separable(sets: Sequence[set[Pref]]) -> bool:
    """Whether the prefix sets are pairwise collision-free (the decision separates).

    All-or-nothing per decision: any cross-branch collision fails the whole
    decision (it stays an island).
    """
    for i, sa in enumerate(sets):
        for sb in sets[i + 1 :]:
            if any(collide(pa, pb) for pa in sa for pb in sb):
                return False
    return True


def extend_follow(prefs: set[Pref], follow: CharSet, k: int) -> set[Pref]:
    """Extend each short END prefix by one FOLLOW char, then mark it UNK.

    An END prefix shorter than ``k`` can be continued by whatever follows the rule
    at its call site; appending one FOLLOW CharSet (then UNK, since past FOLLOW is
    unknown) is what lets rule-FOLLOW disambiguate a decision at ``k`` — chess
    ``nonpawn`` separates only with this extension.
    """
    out: set[Pref] = set()
    for tup, state in prefs:
        if state == END and len(tup) < k and not follow.is_empty():
            out.add((tup + (follow,), UNK))
        else:
            out.add((tup, state))
    return out


def _window_key(win: tuple[CharSet, ...]) -> tuple[tuple[bool, tuple[str, ...]], ...]:
    """A deterministic sort key for a CharSet window (per-position polarity+chars)."""
    return tuple((cs.negated, tuple(sorted(cs.chars))) for cs in win)


def windows_of(prefs: set[Pref]) -> tuple[tuple[CharSet, ...], ...]:
    """The gate-spec windows of a prefix set — tags dropped, dedup'd, sorted.

    The END/MORE/UNK tag is irrelevant to the runtime's positionwise consistency
    test (separability guarantees at most one branch matches), so the stored spec
    is just the CharSet tuples; sorting makes the compiled spec deterministic and
    directly comparable.
    """
    return tuple(sorted({tup for tup, _tag in prefs}, key=_window_key))


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
    nullability oracle (the :class:`~lexic.parsing.pda.analysis.GrammarAnalysis`
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
