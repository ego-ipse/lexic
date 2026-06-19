"""Desugar an IR grammar into classical Earley shape.

The IR is richer than textbook BNF, so a few canonicalisations precede Earley.
Run them in this order — each assumes its predecessors:

1. **Flatten inline groups** (:class:`FlattenGroups`). An
   :class:`~lexic.ir.nodes.IrAlternation` used as an atom (a parenthesised group)
   is hoisted to a fresh synthetic rule so every atom after the dot is a ruleref
   or a terminal. The hoisted item keeps its quantifier, which step (2) consumes.

2. **Desugar quantifiers** (:class:`DesugarQuantifiers`). An
   ``IrItem(atom, IrQuantifier(lo, hi))`` with a non-``(1, 1)`` quantifier becomes
   an ``IrItem`` referencing a synthetic right-recursive rule (``*`` →
   ``X = "" / elem X``; ``+`` → ``X = elem / elem X``; ``?`` → ``X = "" / elem``;
   bounded counts unrolled). ``*`` and ``?`` introduce *nullable* rules.

3. **Split multi-char literals** (:class:`SplitLiterals`). Scannerless Earley
   scans one character per column, so ``IrLiteral("false")`` becomes five
   single-char items. Run last, after a quantified literal has been moved into a
   synthetic rule with a ``(1, 1)`` quantifier.

Each transform is an :class:`~lexic.ir.walk.IrTransformer`: the generic
:class:`~lexic.ir.action.IrRebuild` default walks and rebuilds the tree, so a
transform only declares the node types where it *deviates* — no hand-rolled
``rules → arms → items`` recursion. Steps (1) and (2) mint fresh rule names and
collect new rules in a mutable :class:`Minter` leaf carried on the transformer
(reached through the dispatcher ``d``); numeric recursion params (repeat bounds)
ride the argument channel as :class:`~lexic.ir.base.IrInt`, so ``nc`` stays
``IrSelf``.

Synthetic rules carry the :data:`SYNTHETIC_PREFIX` so a later reduction step can
recognise and collapse them. The module-level :func:`flatten_groups` /
:func:`desugar_quantifiers` / :func:`split_literals` / :func:`normalize` are the
normalisation entry points — each builds a fresh transformer and applies it.
"""

from __future__ import annotations

from typing import Iterator, Sequence, cast

from lexic.exceptions import UnsupportedConstructError
from lexic.ir.action import IrAction
from lexic.ir.base import (
    Field,
    IrInt,
    IrLeaf,
    IrNone,
    IrNoneType,
    IrSelf,
    IrSeq,
    IrStr,
)
from lexic.ir.mapping import IrTypeMap
from lexic.ir.nodes import (
    IrAlternation,
    IrAst,
    IrItem,
    IrLiteral,
    IrQuantifier,
    IrRule,
    IrRuleRef,
    IrSequence,
)
from lexic.ir.walk import IrTransformer

_ONE = IrQuantifier(1, 1)

SYNTHETIC_PREFIX = "__"
"""Name prefix marking a rule minted by normalisation, not present in the source."""


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


class SplitSeq(IrLeaf[IrSelf, IrSelf]):
    """``IrSequence`` action: flat-expand multi-char literal items to one char each."""

    def eval(self, _d: IrSelf, n: IrSelf, _nc: Sequence[IrSelf], /) -> IrSequence:
        """:param n: the sequence; :returns: the sequence with literals split."""
        seq = cast(IrSequence, n)
        items: list[IrItem] = []
        for item in seq:
            if (
                isinstance(item.atom, IrLiteral)
                and item.quantifier == _ONE
                and len(str(item.atom)) > 1
            ):
                items.extend(IrItem(IrLiteral(ch)) for ch in str(item.atom))
            else:
                items.append(item)
        return IrSequence(*items)


class HoistItem(IrLeaf[IrSelf, IrSelf]):
    """``IrItem`` action: hoist a group atom to a synthetic rule, else identity.

    A group (an :class:`IrAlternation` used as an atom) is recursively flattened
    (via ``d``), recorded in the minter under a fresh name, and replaced by a
    ruleref item keeping the original quantifier. Nested groups are hoisted by the
    recursive ``d.eval`` re-dispatching down through this same action.
    """

    def eval(self, d: IrSelf, n: IrSelf, _nc: Sequence[IrSelf], /) -> IrItem:
        """:param n: the item; :returns: the (possibly hoisted) item."""
        item = cast(IrItem, n)
        if not isinstance(item.atom, IrAlternation):
            return item
        minter = cast(_Minting, d).minter
        name = str(minter.eval(d, IrStr("grp"), ()))
        flattened = cast(IrAlternation, d.eval(d, item.atom, ()))
        minter += IrRule(name, flattened)
        return IrItem(IrRuleRef(name), item.quantifier)


class Expand(IrLeaf[IrSelf, IrSelf]):
    """Mint the right-recursive rule for ``lo``..``hi`` copies of a unit item.

    ``n`` is the unit :class:`IrItem` (quantifier ``(1, 1)``); ``nc`` is
    ``(IrInt(lo), hi)`` with ``hi`` an :class:`IrInt` or :data:`IrNone`
    (unbounded). Recurses through itself / :data:`OPT_CHAIN` for the multi-copy
    cases, appending each rule to the minter. Returns a ruleref to the new rule.
    """

    def eval(self, d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> IrRuleRef:
        """:param n: unit item; :param nc: ``(IrInt(lo), hi)``; :returns: the new ref."""
        unit = cast(IrItem, n)
        lo = int(cast(int, nc[0]))
        hi = nc[1]
        minter = cast(_Minting, d).minter
        name = str(minter.eval(d, IrStr("rep"), ()))
        ref = IrItem(IrRuleRef(name))
        if isinstance(hi, IrNoneType):
            if lo == 0:  # *  →  X = "" / unit X
                body = IrAlternation(IrSequence(), IrSequence(unit, ref))
            elif lo == 1:  # +  →  X = unit / unit X
                body = IrAlternation(IrSequence(unit), IrSequence(unit, ref))
            else:  # m* (m > 1): one mandatory copy, then (m-1)* via a sub-rule
                tail = IrItem(self.eval(d, unit, (IrInt(lo - 1), IrNone)))
                body = IrAlternation(IrSequence(unit, tail))
        else:
            hi_i = int(cast(int, hi))
            if lo == 0 and hi_i == 1:  # ?  →  X = "" / unit
                body = IrAlternation(IrSequence(), IrSequence(unit))
            elif lo == hi_i:  # exactly lo copies
                body = IrAlternation(IrSequence(*((unit,) * lo)))
            else:  # lo mandatory, then up to (hi - lo) optional via an opt-chain
                tail = IrItem(OPT_CHAIN.eval(d, unit, (IrInt(hi_i - lo),)))
                body = IrAlternation(IrSequence(*((unit,) * lo), tail))
        minter += IrRule(name, body)
        return IrRuleRef(name)


class OptChain(IrLeaf[IrSelf, IrSelf]):
    """Mint rules matching 0..``k`` copies of a unit item (nested optionals).

    ``n`` is the unit :class:`IrItem`; ``nc`` is ``(IrInt(k),)`` with ``k >= 1``.
    Recurses for ``k > 1``, appending each rule to the minter. Returns a ruleref to
    the head of the optional chain.
    """

    def eval(self, d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> IrRuleRef:
        """:param n: unit item; :param nc: ``(IrInt(k),)``; :returns: chain-head ref."""
        unit = cast(IrItem, n)
        k = int(cast(int, nc[0]))
        minter = cast(_Minting, d).minter
        name = str(minter.eval(d, IrStr("opt"), ()))
        if k == 1:
            body = IrAlternation(IrSequence(), IrSequence(unit))
        else:
            inner = IrItem(self.eval(d, unit, (IrInt(k - 1),)))
            body = IrAlternation(IrSequence(), IrSequence(unit, inner))
        minter += IrRule(name, body)
        return IrRuleRef(name)


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
                f"parsing_2: invalid quantifier bounds {(quant.lo, quant.hi)!r}"
            )
        hi_node = hi if isinstance(hi, IrNoneType) else IrInt(hi)
        ref = EXPAND.eval(d, IrItem(item.atom), (IrInt(quant.lo), hi_node))
        return IrItem(cast(IrRuleRef, ref))


class CollectRules(IrLeaf[IrSelf, IrSelf]):
    """``IrAst`` action: transform every rule, then append the minted rules.

    Walking the rules via ``d`` populates the minter (the per-item actions hoist /
    desugar as they fire); the result grammar is the transformed rules followed by
    the collected synthetic rules.
    """

    def eval(self, d: IrSelf, n: IrSelf, _nc: Sequence[IrSelf], /) -> IrAst:
        """:param n: the grammar; :returns: the rewritten grammar."""
        grammar = cast(IrAst, n)
        minter = cast(_Minting, d).minter
        rules = tuple(cast(IrRule, d.eval(d, rule, ())) for rule in grammar.rules)
        return IrAst(rules=IrSeq(*rules, *minter), start=grammar.start)


EXPAND = Expand()
OPT_CHAIN = OptChain()
"""Shared numeric-recursion nodes for quantifier desugaring (minter lives on ``d``)."""


class _Minting(IrTransformer):
    """An :class:`IrTransformer` carrying a per-run :class:`Minter`.

    The minter is reached by the action bodies through the dispatcher ``d``; a
    fresh one is supplied per call by the entry-point wrappers.

    :ivar minter: The run's minting state (names + collected synthetic rules).
    """

    minter: Minter = Field(default_factory=Minter)


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


class SplitLiterals(IrTransformer):
    """Rewrite every multi-char literal atom into single-char items (no minting)."""

    actions: IrTypeMap = IrTypeMap(IrAction(IrSequence, SplitSeq()))


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


def split_literals(grammar: IrAst) -> IrAst:
    """Rewrite every multi-char literal atom into single-char items (entry point).

    :param grammar: The grammar to rewrite.
    :returns: An equivalent grammar with one character per literal item.
    """
    return cast(IrAst, SplitLiterals().apply(grammar))


def normalize(grammar: IrAst) -> IrAst:
    """Full normalisation: flatten groups, desugar quantifiers, split literals.

    :param grammar: The grammar to normalise.
    :returns: The Earley-shaped grammar.
    """
    return split_literals(desugar_quantifiers(flatten_groups(grammar)))
