"""The authoritative regular-language proof.

A region is *regular* here in a strong, operational sense: a possessive
recognizer over it accepts exactly the strings the grammar's own rules accept,
consuming exactly as far. That is stronger than "the shape looks regular", and
it is what licenses a recognizer to become AUTHORITATIVE — to decide a region
outright instead of merely proposing a boundary the parser re-checks.

Three obligations, and a region declines unless all three hold:

1. **Acyclic simple closure.** :func:`~lexic.parsing.pda.core.scanner.
   build_recognizer` already answers this — it refuses a cyclic or
   non-greedy-recognizable closure — so the possessive lowering and the
   closure test are one call, not a second implementation.
2. **First-disjoint ordered arms, nullable arm last.** An arm choice a single
   character cannot settle is not regular here. A nullable arm ahead of
   another arm would silently win at zero width. This is owed by every
   alternation the region contains, not only by a rule body: ``build_
   recognizer`` lowers an inline group to the same ordered, committed
   alternation a same-bodied rule gets, so a group that is not proved is a
   commitment nobody checked. A group earns one further way to discharge it —
   ordered literal arms whose munch is forced (:func:`_ordered_literals`),
   which is what ``("<=" | "<")`` has and ``("a" | "ab")`` does not. That way
   is offered to a GROUP and not to a rule body, because a rule is proved
   against the region's follow rather than against its own call site, so the
   munch obligation would be asked of text that need not be there; the
   asymmetry withholds a shortcut and never grants one.
3. **Boundaries that do not steal.** Wherever the recognizer must decide
   "another repetition, or the continuation" — a variable item, or a nullable
   atom even at ``{1,1}`` — the atom's leading characters must not overlap
   what follows it. A possessive match that can consume its successor's first
   character does not merely mis-order the two: it takes it.

The first-set algebra is :class:`~lexic.parsing.pda.analysis.gates.windows.
KWindowFirst` and its ``collide``/``separable``/``extend_follow``, not a
second copy of it; the possessive lowering is ``build_recognizer``'s. This
module owns the PROOF, and nothing else.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import NamedTuple

from lexic.ir import (
    IrAlternation,
    IrItem,
    IrLiteral,
    IrNoneType,
    IrQuantifier,
    IrRule,
    IrSelf,
)
from lexic.parsing.pda.analysis.gates.windows import (
    END,
    UNK,
    KWindowFirst,
    Pref,
    collide,
    extend_follow,
    separable,
)
from lexic.parsing.pda.core.charsets import CharSet
from lexic.parsing.pda.core.scanner import Recognizer, build_recognizer

__all__ = ["RegularProof", "prove_regular"]

_WINDOW = 1
"""The proof is a one-character decision. A region needing two characters of
lookahead to know what it is doing is not one a possessive recognizer may
decide on its own — it stays with the parser."""


class RegularProof(NamedTuple):
    """One region proved regular, with the recognizer that may decide it.

    ``entry`` rather than ``index``: a ``NamedTuple`` IS a tuple, and a field
    called ``index`` would shadow ``tuple.index``.

    :ivar root: The rule the region enters at.
    :ivar recognizer: The possessive recognizer over its acyclic closure.
    :ivar entry: ``root``'s index inside that recognizer's tables.
    """

    root: str
    recognizer: Recognizer
    entry: int


def prove_regular(
    rules: Mapping[str, IrRule], root: str, follow: CharSet
) -> RegularProof | None:
    """Prove ``root``'s region regular, or decline with no proof.

    :param rules: The grammar's rule table.
    :param root: The region's entry rule.
    :param follow: What may appear immediately after the region — its
        terminator or separator, supplied by the surrounding parser, which
        owns the opener and terminator and does not hand them over.
    :returns: The proof, or ``None`` when any obligation fails. Declining is
        always safe: the region falls back to the interpreted product.
    """
    recognizer = build_recognizer(rules, frozenset({root}))
    if recognizer is None:
        return None
    first = KWindowFirst(rules, _WINDOW)
    tail = extend_follow({((), END)}, follow, _WINDOW)
    for name in recognizer.index:
        if not _rule_is_deterministic(first, rules[name], tail):
            return None
    return RegularProof(root, recognizer, recognizer.index[root])


def _items(arm: Sequence[IrSelf]) -> list[IrItem]:
    """The arm's items, in order."""
    return [item for item in arm if isinstance(item, IrItem)]


def _poisoned(prefixes: set[Pref]) -> bool:
    """Whether the window could not be resolved — conservatively a decline."""
    return any(state == UNK for _window, state in prefixes)


def _derives_empty(prefixes: set[Pref]) -> bool:
    """Whether this prefix set contains the complete zero-width derivation."""
    return any(state == END and not window for window, state in prefixes)


def _leads(prefixes: set[Pref]) -> set[Pref]:
    """The prefixes that actually consume a character.

    The zero-width derivation is dropped deliberately. An empty window
    ``collide``s with everything (there is no position to disagree on), so
    keeping it would make every nullable atom decline — including the ones
    whose real leading characters are perfectly disjoint from what follows.
    What matters is whether the atom can EAT its successor's first character.
    """
    return {prefix for prefix in prefixes if prefix[0]}


def _rule_is_deterministic(first: KWindowFirst, rule: IrRule, tail: set[Pref]) -> bool:
    """Whether one rule's arms separate and none of its boundaries steals."""
    arms = [_items(arm) for arm in rule.body]
    if not _first_disjoint(first, arms, tail):
        return False
    return all(_arm_boundaries_hold(first, arm, tail) for arm in arms)


def _group_is_deterministic(
    first: KWindowFirst, group: IrAlternation, tail: set[Pref]
) -> bool:
    """Whether an inline group owes and pays what a same-bodied rule would.

    The extra way to pay is :func:`_ordered_literals`. It is offered here and
    not to a rule body because a rule is proved against the REGION's follow,
    which is not its call site's continuation; a group's continuation is the
    enclosing arm's own remainder, so the munch obligation is asked of the
    text that actually follows it.
    """
    arms = [_items(arm) for arm in group]
    if not _first_disjoint(first, arms, tail):
        if not _ordered_literals(arms, tail):
            return False
    return all(_arm_boundaries_hold(first, arm, tail) for arm in arms)


def _first_disjoint(
    first: KWindowFirst, arms: Sequence[Sequence[IrItem]], tail: set[Pref]
) -> bool:
    """Whether one character settles the arm choice, any nullable arm last."""
    prefixes = [first.arm_prefixes(arm, _WINDOW) for arm in arms]
    if any(_poisoned(prefix) for prefix in prefixes):
        return False
    if not separable([extend_follow(p, tail, _WINDOW) for p in prefixes]):
        return False
    return not any(_derives_empty(prefix) for prefix in prefixes[:-1])


def _ordered_literals(arms: Sequence[Sequence[IrItem]], tail: set[Pref]) -> bool:
    """Whether ordered literal arms commit exactly where the grammar does.

    A literal arm is exact, so at most one arm can match at a position unless
    two arms are prefix-related — and there the ordered alternation takes the
    first that matches, which is the whole decision. Two obligations make that
    reading the only one:

    * no earlier arm is a proper prefix of a later one, or the short arm wins
      where the long one was meant (``("a" | "ab")`` reads ``a`` out of ``ab``);
    * where a later arm IS a proper prefix of an earlier one, the character the
      longer arm holds past it may not begin the continuation, or the short arm
      plus that continuation is a live reading the commitment throws away
      (``("ab" | "a")`` before a ``b`` takes ``ab`` and strands the ``b``).
    """
    texts = _literal_arms(arms)
    if texts is None:
        return False
    for at, earlier in enumerate(texts):
        for later in texts[at + 1 :]:
            if later.startswith(earlier):
                return False
            if earlier.startswith(later) and _residual_leads(earlier, later, tail):
                return False
    return True


def _literal_arms(arms: Sequence[Sequence[IrItem]]) -> "list[str] | None":
    """Each arm's one exact literal text, or ``None`` if any arm is not one."""
    texts: list[str] = []
    for arm in arms:
        text = _sole_literal(arm)
        if text is None:
            return None
        texts.append(text)
    return texts


def _sole_literal(items: Sequence[IrItem]) -> "str | None":
    """One arm's single unquantified non-empty literal, or ``None``."""
    if len(items) != 1:
        return None
    atom, quantifier = items[0].atom, items[0].quantifier
    hi = quantifier.hi
    if isinstance(hi, IrNoneType) or (int(quantifier.lo), int(hi)) != (1, 1):
        return None
    if not isinstance(atom, IrLiteral) or not atom:
        return None
    return str(atom)


def _residual_leads(longer: str, shorter: str, tail: set[Pref]) -> bool:
    """Whether the continuation can begin where the shorter arm would end."""
    residual: Pref = ((CharSet.from_chars(longer[len(shorter)]),), END)
    return any(collide(residual, after) for after in _leads(tail))


def _arm_boundaries_hold(
    first: KWindowFirst, items: Sequence[IrItem], tail: set[Pref]
) -> bool:
    """Whether every deciding boundary in one arm is settled by one character."""
    for at, item in enumerate(items):
        rest = items[at + 1 :]
        deciding = _decides_here(first, item)
        if deciding and not _boundary_separates(first, item, rest, tail):
            return False
        if not _group_holds(first, item, rest, tail):
            return False
    return True


def _group_holds(
    first: KWindowFirst, item: IrItem, rest: Sequence[IrItem], tail: set[Pref]
) -> bool:
    """Whether an inline-group atom's own arms hold, under its continuation.

    What an inner arm faces is the enclosing arm's remainder extended by the
    enclosing continuation — and, for a repeatable group, another instance of
    the group first, which is what makes ``("a" | "ab")+`` a decision about
    its own next iteration rather than only about what comes after.
    """
    atom = item.atom
    if not isinstance(atom, IrAlternation):
        return True
    after = extend_follow(first.arm_prefixes(rest, _WINDOW), tail, _WINDOW)
    return _group_is_deterministic(first, atom, _repeat_tail(first, item, after))


def _repeat_tail(first: KWindowFirst, item: IrItem, after: set[Pref]) -> set[Pref]:
    """What may follow ONE instance of ``item``: another of it, then ``after``."""
    hi = item.quantifier.hi
    if not isinstance(hi, IrNoneType) and int(hi) <= 1:
        return after
    loop = IrItem(item.atom, IrQuantifier(0, hi))
    return extend_follow(first.arm_prefixes([loop], _WINDOW), after, _WINDOW)


def _decides_here(first: KWindowFirst, item: IrItem) -> bool:
    """Whether this item forces a repeat-or-continue decision.

    Two shapes do. A **variable** item — any quantifier whose bounds differ —
    must decide whether to take another. A **nullable atom** must decide
    whether it is here at all, and that is true even at ``{1,1}``: a
    once-required reference to a rule that derives empty is still a decision.
    """
    quantifier = item.quantifier
    hi = quantifier.hi
    if isinstance(hi, IrNoneType) or int(quantifier.lo) != int(hi):
        return True
    return _derives_empty(first.atom_prefixes(item.atom, _WINDOW))


def _boundary_separates(
    first: KWindowFirst,
    item: IrItem,
    rest: Sequence[IrItem],
    tail: set[Pref],
) -> bool:
    """Whether ``item``'s leading characters stay clear of what follows it."""
    leads = first.atom_prefixes(item.atom, _WINDOW)
    after = first.arm_prefixes(rest, _WINDOW)
    # Poison is tested BEFORE the follow extension: `extend_follow` marks its
    # own result UNK on purpose (what lies past FOLLOW is unknown), so testing
    # after it would read every extended continuation as unresolvable and
    # decline every region that has a terminator at all.
    if _poisoned(leads) or _poisoned(after):
        return False
    continuation = extend_follow(after, tail, _WINDOW)
    return not any(
        collide(lead, after) for lead in _leads(leads) for after in _leads(continuation)
    )
