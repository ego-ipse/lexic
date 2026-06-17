"""Desugar an IR grammar into classical Earley shape.

The IR is richer than textbook BNF, so a few canonicalisations precede Earley.
Run them in this order — each assumes its predecessors:

1. **Flatten inline groups** (:func:`flatten_groups`). An
   :class:`~lexic.ir.nodes.IrAlternation` used as an atom (a parenthesised group)
   is hoisted to a fresh synthetic rule so every atom after the dot is a ruleref
   or a terminal. The hoisted item keeps its quantifier, which step (2) then
   consumes.

2. **Desugar quantifiers** (:func:`desugar_quantifiers`). An
   ``IrItem(atom, IrQuantifier(lo, hi))`` with a non-``(1, 1)`` quantifier becomes
   an ``IrItem`` referencing a synthetic right-recursive rule
   (``*`` → ``X = "" / elem X``; ``+`` → ``X = elem / elem X``; ``?`` →
   ``X = "" / elem``; bounded counts unrolled). ``*`` and ``?`` introduce
   *nullable* rules, which the completer must then handle (see
   :class:`~lexic.parsing_2.ops.Complete`) — that completer is a later increment,
   so the full parse does not run on quantified grammars yet, only the rewrite.

3. **Split multi-char literals** (:func:`split_literals`). Scannerless Earley
   scans one character per column, so ``IrLiteral("false")`` becomes five
   single-char items. Run last, after a quantified literal has been moved into a
   synthetic rule with a ``(1, 1)`` quantifier.

Synthetic rules minted by (1) and (2) carry the :data:`SYNTHETIC_PREFIX` so a
later reduction step can recognise and collapse them (see
:func:`is_synthetic_name`). Source grammars must not use that prefix; names are
otherwise kept collision-free by seeding the minter with the existing names.
"""

from __future__ import annotations

from lexic.exceptions import UnsupportedConstructError
from lexic.ir.base import IrNone, IrNoneType, IrSeq
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

_ONE = IrQuantifier(1, 1)

SYNTHETIC_PREFIX = "__"
"""Name prefix marking a rule minted by normalisation, not present in the source."""


def is_synthetic_name(name: str) -> bool:
    """Whether ``name`` was minted by normalisation (vs. a source rule).

    :param name: A rule name.
    :returns: Whether it carries :data:`SYNTHETIC_PREFIX`.
    """
    return name.startswith(SYNTHETIC_PREFIX)


# ── Split multi-char literals ─────────────────────────────────────────


def split_literals(grammar: IrAst) -> IrAst:
    """Rewrite every multi-char :class:`IrLiteral` atom into single-char items.

    Only unquantified literals are split (a quantified multi-char literal must
    first be desugared to a synthetic rule by :func:`desugar_quantifiers`).

    :param grammar: The grammar to rewrite.
    :returns: An equivalent grammar with one character per literal item.
    """
    rules = tuple(
        IrRule(rule.name, _split_alternation(rule.body)) for rule in grammar.rules
    )
    return IrAst(rules=IrSeq(*rules), start=grammar.start)


def _split_alternation(alt: IrAlternation) -> IrAlternation:
    """Split literals within every arm of ``alt``.

    :param alt: The alternation to rewrite.
    :returns: The rewritten alternation.
    """
    return IrAlternation(*(_split_sequence(arm) for arm in alt))


def _split_sequence(seq: IrSequence) -> IrSequence:
    """Expand multi-char literal items in ``seq`` into single-char items.

    :param seq: The sequence to rewrite.
    :returns: The rewritten sequence.
    """
    out: list[IrItem] = []
    for item in seq:
        if _is_multichar_literal(item):
            out.extend(IrItem(IrLiteral(ch)) for ch in str(item.atom))
        else:
            out.append(item)
    return IrSequence(*out)


def _is_multichar_literal(item: IrItem) -> bool:
    """Whether ``item`` is an unquantified literal longer than one character.

    :param item: The item to test.
    :returns: Whether it should be split.
    """
    return (
        isinstance(item.atom, IrLiteral)
        and item.quantifier == _ONE
        and len(str(item.atom)) > 1
    )


# ── _Rewriter — shared walk + name minting ────────────────────────────


class _Rewriter:
    """Rewrites a grammar's items, minting synthetic rules as needed.

    Provides two public entry points — :meth:`flatten_groups` and
    :meth:`desugar_quantifiers` — both of which share the same rule-walk
    infrastructure and name-minting state.
    """

    def __init__(self, grammar: IrAst) -> None:
        self._grammar = grammar
        self._used: set[str] = {rule.name for rule in grammar.rules}
        self._counter = 0
        self._new: list[IrRule] = []

    # ── public entry points ────────────────────────────────────────────

    def flatten_groups(self) -> IrAst:
        """Hoist inline :class:`IrAlternation` atoms into fresh synthetic rules.

        Every group atom (an alternation used where an atom is expected) is replaced
        by a ruleref to a synthetic rule holding that alternation; the original
        item's quantifier is preserved on the ruleref. Nested groups are hoisted too.

        :returns: An equivalent grammar whose only alternations are rule bodies.
        """
        return self._run(self._flatten_item)

    def desugar_quantifiers(self) -> IrAst:
        """Replace non-``(1, 1)`` quantifiers with synthetic recursive rules.

        Assumes groups are already flattened (see :func:`flatten_groups`), so every
        quantified atom is a terminal or a ruleref. ``*`` and ``?`` produce nullable
        synthetic rules.

        :returns: An equivalent grammar carrying only ``(1, 1)`` quantifiers.
        :raises UnsupportedConstructError: On invalid bounds (``lo < 0`` or ``hi < lo``).
        """
        return self._run(self._desugar_item)

    # ── shared walk ────────────────────────────────────────────────────

    def _run(self, item_fn) -> IrAst:
        rules = [
            IrRule(r.name, self._alt(r.body, item_fn)) for r in self._grammar.rules
        ]
        rules.extend(self._new)
        return IrAst(rules=IrSeq(*rules), start=self._grammar.start)

    def _alt(self, alt: IrAlternation, item_fn) -> IrAlternation:
        return IrAlternation(*(self._seq(arm, item_fn) for arm in alt))

    def _seq(self, seq: IrSequence, item_fn) -> IrSequence:
        return IrSequence(*(item_fn(item) for item in seq))

    # ── name minting ───────────────────────────────────────────────────

    def _fresh(self, hint: str) -> str:
        """A fresh ``__<hint>_<n>`` name not yet used.

        :param hint: A short kind tag (``"grp"``, ``"rep"``, ``"opt"``).
        :returns: The minted, reserved name.
        """
        self._counter += 1
        name = f"{SYNTHETIC_PREFIX}{hint}_{self._counter}"
        while name in self._used:
            self._counter += 1
            name = f"{SYNTHETIC_PREFIX}{hint}_{self._counter}"
        self._used.add(name)
        return name

    # ── flatten (from _GroupFlattener) ────────────────────────────────

    def _flatten_item(self, item: IrItem) -> IrItem:
        """Rewrite a group atom to a ruleref; leave other atoms as-is.

        :param item: The item to rewrite.
        :returns: The (possibly rewritten) item.
        """
        if isinstance(item.atom, IrAlternation):
            return IrItem(self._hoist(item.atom), item.quantifier)
        return item

    def _hoist(self, group: IrAlternation) -> IrRuleRef:
        """Register a synthetic rule for ``group`` (flattened) and ref it.

        :param group: The inline alternation to hoist.
        :returns: A ruleref to the new synthetic rule.
        """
        name = self._fresh("grp")
        self._new.append(IrRule(name, self._alt(group, self._flatten_item)))
        return IrRuleRef(name)

    # ── desugar (from _QuantifierDesugarer) ───────────────────────────

    def _desugar_item(self, item: IrItem) -> IrItem:
        """Rewrite a quantified item to a ref into a synthetic repetition rule.

        :param item: The item to rewrite.
        :returns: The (possibly rewritten) item.
        """
        quant = item.quantifier
        if quant == _ONE:
            return item
        self._validate(quant)
        return IrItem(self._expand(IrItem(item.atom), quant.lo, quant.hi))

    @staticmethod
    def _validate(quant: IrQuantifier) -> None:
        hi = quant.hi
        if quant.lo < 0 or (not isinstance(hi, IrNoneType) and hi < quant.lo):
            raise UnsupportedConstructError(
                f"parsing_2: invalid quantifier bounds {(quant.lo, quant.hi)!r}"
            )

    def _expand(self, unit: IrItem, lo: int, hi: int | IrNoneType) -> IrRuleRef:
        """Mint a synthetic rule matching ``lo``..``hi`` copies of ``unit``.

        :param unit: The single-occurrence item (quantifier ``(1, 1)``).
        :param lo: Minimum repetitions.
        :param hi: Maximum repetitions, or :data:`IrNone` for unbounded.
        :returns: A ruleref to the new synthetic rule.
        """
        name = self._fresh("rep")
        body = self._arms(unit, name, lo, hi)
        self._new.append(IrRule(name, body))
        return IrRuleRef(name)

    def _arms(
        self, unit: IrItem, name: str, lo: int, hi: int | IrNoneType
    ) -> IrAlternation:
        if isinstance(hi, IrNoneType):
            return self._unbounded_arms(unit, name, lo)
        return self._bounded_arms(unit, lo, hi)

    def _unbounded_arms(self, unit: IrItem, name: str, lo: int) -> IrAlternation:
        """Arms for ``lo*`` (unbounded above), right-recursive on ``name``."""
        if lo == 0:  # *  →  X = "" / unit X
            return IrAlternation(IrSequence(), IrSequence(unit, _ref(name)))
        if lo == 1:  # +  →  X = unit / unit X
            return IrAlternation(IrSequence(unit), IrSequence(unit, _ref(name)))
        # m* (m > 1): one mandatory copy, then (m-1)* via a sub-rule.
        tail = IrItem(self._expand(unit, lo - 1, IrNone))
        return IrAlternation(IrSequence(unit, tail))

    def _bounded_arms(self, unit: IrItem, lo: int, hi: int) -> IrAlternation:
        """Arms for ``{lo, hi}`` (finite upper bound)."""
        if lo == 0 and hi == 1:  # ?  →  X = "" / unit
            return IrAlternation(IrSequence(), IrSequence(unit))
        if lo == hi:  # exactly lo copies
            return IrAlternation(IrSequence(*((unit,) * lo)))
        # lo mandatory copies, then up to (hi - lo) optional via an opt-chain.
        tail = IrItem(self._opt_chain(unit, hi - lo))
        return IrAlternation(IrSequence(*((unit,) * lo), tail))

    def _opt_chain(self, unit: IrItem, k: int) -> IrRuleRef:
        """Mint rules matching 0..``k`` copies of ``unit`` (nested optionals).

        :param unit: The single-occurrence item.
        :param k: The maximum number of optional copies (``>= 1``).
        :returns: A ruleref to the head of the optional chain.
        """
        name = self._fresh("opt")
        if k == 1:
            body = IrAlternation(IrSequence(), IrSequence(unit))
        else:
            inner = IrItem(self._opt_chain(unit, k - 1))
            body = IrAlternation(IrSequence(), IrSequence(unit, inner))
        self._new.append(IrRule(name, body))
        return IrRuleRef(name)


# ── Public module functions ───────────────────────────────────────────


def flatten_groups(grammar: IrAst) -> IrAst:
    """Hoist inline :class:`IrAlternation` atoms into fresh synthetic rules.

    Every group atom (an alternation used where an atom is expected) is replaced
    by a ruleref to a synthetic rule holding that alternation; the original
    item's quantifier is preserved on the ruleref. Nested groups are hoisted too.

    :param grammar: The grammar to rewrite.
    :returns: An equivalent grammar whose only alternations are rule bodies.
    """
    return _Rewriter(grammar).flatten_groups()


def desugar_quantifiers(grammar: IrAst) -> IrAst:
    """Replace non-``(1, 1)`` quantifiers with synthetic recursive rules.

    Assumes groups are already flattened (see :func:`flatten_groups`), so every
    quantified atom is a terminal or a ruleref. ``*`` and ``?`` produce nullable
    synthetic rules.

    :param grammar: The grammar to rewrite.
    :returns: An equivalent grammar carrying only ``(1, 1)`` quantifiers.
    :raises UnsupportedConstructError: On invalid bounds (``lo < 0`` or ``hi < lo``).
    """
    return _Rewriter(grammar).desugar_quantifiers()


def _ref(name: str) -> IrItem:
    """A ``(1, 1)`` item referencing rule ``name``."""
    return IrItem(IrRuleRef(name))
