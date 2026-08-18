"""Desugar an IR grammar into classical Earley shape.

The IR is richer than textbook BNF, so two canonicalisations precede Earley.
Run them in this order — the second assumes the first:

1. **Flatten inline groups** (:class:`FlattenGroups`). An
   :class:`~lexic.ir.grammar.nodes.IrAlternation` used as an atom (a parenthesised group)
   is hoisted to a fresh synthetic rule so every atom after the dot is a ruleref
   or a terminal. The hoisted item keeps its quantifier, which step (2) consumes.

2. **Desugar quantifiers** (:class:`DesugarQuantifiers`). An
   ``IrItem(atom, IrQuantifier(lo, hi))`` with a non-``(1, 1)`` quantifier becomes
   an ``IrItem`` referencing a synthetic right-recursive rule (``*`` →
   ``X = "" / elem X``; ``+`` → ``X = elem / elem X``; ``?`` → ``X = "" / elem``;
   bounded counts unrolled). ``*`` and ``?`` introduce *nullable* rules.

Multi-char literals are NOT split: a k-char literal is one scan atom — the
kernel matches it with ``text.startswith`` and lands the advance k columns
ahead, so one leaf covers the whole literal.

Each transform is an :class:`~lexic.ir.action.walk.IrBottomUp`: the iterative
post-order driver walks and rebuilds the tree (depth-independent), so a
transform only declares the node types where it *deviates* — no hand-rolled
``rules → arms → items`` recursion, and bodies see children already in final
form. Both steps mint fresh rule names and collect new rules in a mutable
:class:`Minter` leaf carried on the transformer (reached through the
dispatcher ``d``); numeric recursion params (repeat bounds) ride the argument
channel as :class:`~lexic.ir.base.IrInt`, so ``nc`` stays ``IrSelf``.

Synthetic rules carry the :data:`SYNTHETIC_PREFIX` so a later reduction step can
recognise and collapse them. The module-level :func:`flatten_groups` /
:func:`desugar_quantifiers` / :func:`normalize` are the normalisation entry
points — each builds a fresh transformer and applies it.
"""

from __future__ import annotations

from typing import Iterator, Sequence, cast

from lexic.exceptions import UnsupportedConstructError
from lexic.ir import (
    Field,
    IrAction,
    IrAlternation,
    IrAst,
    IrBottomUp,
    IrInt,
    IrItem,
    IrLeaf,
    IrMultiMap,
    IrNone,
    IrNoneType,
    IrQuantifier,
    IrRule,
    IrRuleRef,
    IrSelf,
    IrSeq,
    IrSequence,
    IrStr,
    IrTuple,
    IrTypeMap,
)

_ONE = IrQuantifier(1, 1)

SYNTHETIC_PREFIX = "__"
"""Name prefix marking a rule minted by normalisation, not present in the source."""

QUANTIFIER_PREFIXES = (
    f"{SYNTHETIC_PREFIX}rep_",
    f"{SYNTHETIC_PREFIX}opt_",
)
"""Prefixes whose rule arms are states of one authored quantified item.

Unlike ``__grp_*`` arms, repeat/optional helper arms are not authored choices:
they encode different extents of one item. Table compilation preserves that
origin so the forest's structural split test does not mistake implementation
arms for grammar alternatives.
"""


class Minter(IrLeaf[IrSelf, IrSelf]):
    """Per-run minting state: fresh synthetic names + the rules they define.

    A mutable leaf (like the chart) seeded with the grammar's existing names so
    minted names never collide. The surface is ``eval`` + dunders: ``eval(hint)``
    mints and reserves a fresh ``__<hint>_<n>`` name; ``minter += rule`` records a
    synthetic rule; iterating the minter yields the collected rules in order.
    """

    __slots__ = ("_used", "_counter", "_new")

    _used: set[str]
    _counter: int
    _new: list[IrRule]

    def __init__(self, used: set[str] | None = None) -> None:
        """Seed the minter, reserving ``used`` (the grammar's existing names)."""
        self._used = set(used) if used else set()
        self._counter = 0
        self._new = []

    def eval(self, _d: IrSelf, n: IrSelf, _nc: Sequence[IrSelf], /) -> IrStr:
        """Mint a fresh name from hint ``n`` (an :class:`IrStr`), reserving it."""
        hint = str(n)
        self._counter += 1
        name = f"{SYNTHETIC_PREFIX}{hint}_{self._counter}"
        while name in self._used:
            self._counter += 1
            name = f"{SYNTHETIC_PREFIX}{hint}_{self._counter}"
        self._used.add(name)
        return IrStr(name)

    def __iadd__(self, rule: IrRule) -> Minter:
        """Record a synthetic ``rule``; return self (in-place)."""
        self._new.append(rule)
        return self

    def __iter__(self) -> Iterator[IrRule]:
        """Iterate the collected synthetic rules, in mint order."""
        return iter(self._new)


class HoistItem(IrLeaf[IrSelf, IrSelf]):
    """``IrItem`` action: hoist a group atom to a synthetic rule, else identity.

    A group (an :class:`IrAlternation` used as an atom) is recorded in the
    minter under a fresh name and replaced by a ruleref item keeping the
    original quantifier. The bottom-up driver has already hoisted any nested
    groups inside it (inner groups mint before outer ones), so the body only
    handles this level.
    """

    def eval(self, d: IrSelf, n: IrSelf, _nc: Sequence[IrSelf], /) -> IrItem:
        """:param n: the item; :returns: the (possibly hoisted) item."""
        item = cast(IrItem, n)
        if not isinstance(item.atom, IrAlternation):
            return item
        minter = cast(_Minting, d).minter
        name = str(minter.eval(d, IrStr("grp"), ()))
        minter += IrRule(name, item.atom)
        return IrItem(IrRuleRef(name), item.quantifier)


class Expand(IrLeaf[IrSelf, IrSelf]):
    """Mint the right-recursive rule for an :class:`IrQuantifier`'s repeat bounds.

    ``n`` is the unit :class:`IrItem` (quantifier ``(1, 1)``); ``nc`` is
    ``(IrQuantifier(lo, hi),)`` — the bounds carried as their own node (``hi`` an
    ``int`` or :data:`IrNone` for unbounded) rather than a raw ``(lo, hi)`` pair.
    Recurses through itself / :data:`OPT_CHAIN` for the multi-copy cases,
    appending each rule to the minter. Returns a ruleref to the new rule.

    Identical ``(unit, quant)`` expansions are interned in the run's ``memo``, so
    a repeated quantifier (e.g. two ``[a-z]*`` occurrences) reuses one synthetic
    rule instead of minting a fresh copy — fewer rules, fewer Earley items.
    """

    def eval(self, d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> IrRuleRef:
        """:param n: unit item; :param nc: ``(IrQuantifier,)``; :returns: the new ref."""
        unit = cast(IrItem, n)
        quant = cast(IrQuantifier, nc[0])
        memo = cast(_Minting, d).memo
        key = IrTuple(IrStr("rep"), unit, quant)
        interned = memo[key]
        if interned:
            return cast(IrRuleRef, interned[0])
        minter = cast(_Minting, d).minter
        name = str(minter.eval(d, IrStr("rep"), ()))
        minter += IrRule(name, self._body(d, unit, quant, IrItem(IrRuleRef(name))))
        ref = IrRuleRef(name)
        memo += (key, ref)
        return ref

    def _body(
        self, d: IrSelf, unit: IrItem, quant: IrQuantifier, self_ref: IrItem
    ) -> IrAlternation:
        """Right-recursive body for ``quant``'s copies of ``unit``.

        :param self_ref: An item referencing the rule being built (the recursion
            tail of the unbounded cases).
        """
        lo, hi = quant.lo, quant.hi
        if isinstance(hi, IrNoneType):
            if lo == 0:  # *  →  X = "" / unit X
                return IrAlternation(IrSequence(), IrSequence(unit, self_ref))
            if lo == 1:  # +  →  X = unit / unit X
                return IrAlternation(IrSequence(unit), IrSequence(unit, self_ref))
            # m* (m > 1): one mandatory copy, then (m-1)* via a sub-rule
            tail = IrItem(self.eval(d, unit, (IrQuantifier(lo - 1, IrNone),)))
            return IrAlternation(IrSequence(unit, tail))
        if lo == 0 and hi == 1:  # ?  →  X = "" / unit
            return IrAlternation(IrSequence(), IrSequence(unit))
        if lo == hi:  # exactly lo copies
            return IrAlternation(IrSequence(*((unit,) * lo)))
        # lo mandatory, then up to (hi - lo) optional via an opt-chain
        tail = IrItem(OPT_CHAIN.eval(d, unit, (IrInt(hi - lo),)))
        return IrAlternation(IrSequence(*((unit,) * lo), tail))


class OptChain(IrLeaf[IrSelf, IrSelf]):
    """Mint rules matching 0..``k`` copies of a unit item (nested optionals).

    ``n`` is the unit :class:`IrItem`; ``nc`` is ``(IrInt(k),)`` with ``k >= 1``.
    Recurses for ``k > 1``, appending each rule to the minter. Returns a ruleref to
    the head of the optional chain. Identical ``(unit, k)`` chains are interned in
    the run's ``memo`` so repeated bounded quantifiers share one chain.
    """

    def eval(self, d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> IrRuleRef:
        """:param n: unit item; :param nc: ``(IrInt(k),)``; :returns: chain-head ref."""
        unit = cast(IrItem, n)
        k = int(cast(int, nc[0]))
        ctx = cast(_Minting, d)
        memo = ctx.memo
        key = IrTuple(IrStr("opt"), unit, IrInt(k))
        interned = memo[key]
        if interned:
            return cast(IrRuleRef, interned[0])
        minter = ctx.minter
        name = str(minter.eval(d, IrStr("opt"), ()))
        if k == 1:
            body = IrAlternation(IrSequence(), IrSequence(unit))
        else:
            inner = IrItem(self.eval(d, unit, (IrInt(k - 1),)))
            body = IrAlternation(IrSequence(), IrSequence(unit, inner))
        minter += IrRule(name, body)
        result = IrRuleRef(name)
        memo += (key, result)
        return result


class DesugarItem(IrLeaf[IrSelf, IrSelf]):
    """``IrItem`` action: rewrite a quantified item to a ref into a synthetic rule.

    A ``(1, 1)`` item passes through; otherwise the bounds are validated and the
    synthetic right-recursive rule is built by :data:`EXPAND`, leaving a ``(1, 1)``
    ruleref item in place.
    """

    def eval(self, d: IrSelf, n: IrSelf, _nc: Sequence[IrSelf], /) -> IrItem:
        """:param n: the item; :returns: the (possibly desugared) item.

        :raises UnsupportedConstructError: On invalid bounds (``lo < 0``/``hi < lo``).
        """
        item = cast(IrItem, n)
        quant = item.quantifier
        if quant == _ONE:
            return item
        hi = quant.hi
        if quant.lo < 0 or (not isinstance(hi, IrNoneType) and hi < quant.lo):
            raise UnsupportedConstructError(
                f"parsing: invalid quantifier bounds {(quant.lo, quant.hi)!r}"
            )
        ref = EXPAND.eval(d, IrItem(item.atom), (quant,))
        return IrItem(cast(IrRuleRef, ref))


class CollectRules(IrLeaf[IrSelf, IrSelf]):
    """``IrAst`` action: append the minted rules to the transformed grammar.

    The bottom-up driver has already transformed every rule (populating the
    minter as the per-item actions fired); the body only splices the
    collected synthetic rules onto the end.
    """

    def eval(self, d: IrSelf, n: IrSelf, _nc: Sequence[IrSelf], /) -> IrAst:
        """:param n: the grammar; :returns: the rewritten grammar."""
        grammar = cast(IrAst, n)
        minter = cast(_Minting, d).minter
        return IrAst(rules=IrSeq(*grammar.rules, *minter), start=grammar.start)


EXPAND = Expand()
OPT_CHAIN = OptChain()
"""Shared numeric-recursion nodes for quantifier desugaring (minter lives on ``d``)."""


class _Minting(IrBottomUp):
    """An :class:`IrBottomUp` carrying a per-run :class:`Minter` and memo.

    The minter is reached by the action bodies through the dispatcher ``d``; a
    fresh one is supplied per call by the entry-point wrappers. The ``memo``
    interns already-minted synthetic rules by expansion signature so identical
    quantifier expansions share one rule (see :class:`Expand` / :class:`OptChain`).

    :ivar minter: The run's minting state (names + collected synthetic rules).
    :ivar memo: Expansion signature → the ruleref already minted for it.
    """

    minter: Minter = Field(default_factory=Minter)
    memo: IrMultiMap = Field(default_factory=IrMultiMap)


class FlattenGroups(_Minting):
    """Hoist every inline group atom in a grammar into fresh synthetic rules."""

    actions: IrTypeMap = IrTypeMap(
        IrAction(IrItem, HoistItem()),
        IrAction(IrAst, CollectRules()),
    )


class DesugarQuantifiers(_Minting):
    """Replace non-``(1, 1)`` quantifiers with synthetic recursive rules."""

    actions: IrTypeMap = IrTypeMap(
        IrAction(IrItem, DesugarItem()),
        IrAction(IrAst, CollectRules()),
    )


def flatten_groups(grammar: IrAst) -> IrAst:
    """Hoist inline group atoms into fresh synthetic rules (entry point).

    :param grammar: The grammar to rewrite.
    :returns: An equivalent grammar whose only alternations are rule bodies.
    """
    minter = Minter({rule.name for rule in grammar.rules})
    return cast(IrAst, FlattenGroups(minter=minter).apply(grammar))


def desugar_quantifiers(grammar: IrAst) -> IrAst:
    """Replace non-``(1, 1)`` quantifiers with synthetic recursive rules (entry point).

    :param grammar: The grammar to rewrite (groups already flattened).
    :returns: An equivalent grammar carrying only ``(1, 1)`` quantifiers.
    :raises UnsupportedConstructError: On invalid bounds (``lo < 0`` or ``hi < lo``).
    """
    minter = Minter({rule.name for rule in grammar.rules})
    return cast(IrAst, DesugarQuantifiers(minter=minter).apply(grammar))


def normalize(grammar: IrAst) -> IrAst:
    """Full normalisation: flatten groups, desugar quantifiers.

    Multi-char literals stay atomic — the kernel scans a k-char literal in
    one step (``text.startswith``) and lands the advance k columns ahead, so
    splitting them would only multiply the column work.

    :param grammar: The grammar to normalise.
    :returns: The Earley-shaped grammar.
    """
    return desugar_quantifiers(flatten_groups(grammar))
