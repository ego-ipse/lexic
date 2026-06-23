"""Earley driver — the Scott/Earley loop over an :class:`~lexic.ir.nodes.IrAst`.

:class:`EarleyParser` IS-AN :class:`~lexic.ir.walk.IrDispatch`: its ``actions``
table is :data:`~lexic.parsing_2.ops.EARLEY_OPS`, so resolving the next operation
is the inherited type-dispatch. It carries no methods of its own — the loop lives
in :class:`BuildChart`, whose ``eval`` runs predict/complete to a fixpoint per
column then scans one character into the next, threading the mutable
:class:`~lexic.parsing_2.chart.Chart` and dispatching each item's next symbol
back through the parser.

The grammar-derived inputs are themselves ``eval`` nodes: :class:`RuleIndex`
(rule ref → body), :class:`NullableRules` (least-fixpoint nullable set), and
:class:`Matches` (terminal-accepts-char predicate). :class:`AcceptingItem` finds
the completed start item spanning the whole input.

The module-level :func:`recognize` and :func:`parse` are the package's two entry
points: thin orchestration over the nodes above, wiring an
:class:`~lexic.parsing_2.forest.ParseTree` out for the
:class:`~lexic.parsing_2.reduce.Reducer`.
"""

from __future__ import annotations

from typing import NamedTuple, Sequence, cast

from lexic.exceptions import UnsupportedConstructError
from lexic.ir.base import (
    IrInt,
    IrLeaf,
    IrNone,
    IrNoneType,
    IrSelf,
    IrSeq,
    IrStr,
    IrTuple,
)
from lexic.ir.mapping import IrMap, IrTypeMap
from lexic.ir.nodes import (
    IrAlternation,
    IrAst,
    IrCharClass,
    IrLiteral,
    IrRange,
    IrRuleRef,
)
from lexic.ir.walk import IrDispatch
from lexic.parsing_2.chart import Chart, Column, Link
from lexic.parsing_2.forest import BUILD_TREE, ParseTree, walk_links
from lexic.parsing_2.item import EarleyItem
from lexic.parsing_2.ops import EARLEY_OPS


class RuleIndex(IrLeaf[IrSelf, IrSelf]):
    """Build the rule index: :class:`IrRuleRef` → its alternation body.

    Keys are ``IrRuleRef`` (not the rule's bare ``name`` string) so lookups by a
    dotted item's ``IrRuleRef`` resolve under type-aware equality.
    """

    def eval(self, _d: IrSelf, n: IrSelf, _nc: Sequence[IrSelf], /) -> IrMap:
        """:param n: the grammar; :returns: rule-ref → body :class:`IrMap`."""
        grammar = cast(IrAst, n)
        return IrMap(
            *(IrTuple(IrRuleRef(rule.name), rule.body) for rule in grammar.rules)
        )


class NullableRules(IrLeaf[IrSelf, IrSelf]):
    """Names of rules that can derive the empty string, by least-fixpoint.

    A rule is nullable if any arm is nullable; an arm is nullable if every item
    is a ruleref to a currently-nullable rule (an empty arm vacuously). Assumes
    the grammar is Earley-normalised (all quantifiers ``(1, 1)``), so nullability
    flows purely through empty arms and nullable rulerefs.
    """

    def eval(self, _d: IrSelf, n: IrSelf, _nc: Sequence[IrSelf], /) -> IrSeq:
        """:param n: the grammar; :returns: :class:`IrSeq` of nullable names."""
        grammar = cast(IrAst, n)
        nullable: set[str] = set()
        changed = True
        while changed:
            changed = False
            for rule in grammar.rules:
                if rule.name in nullable:
                    continue
                if any(
                    all(
                        isinstance(it.atom, IrRuleRef) and str(it.atom) in nullable
                        for it in arm
                    )
                    for arm in rule.body
                ):
                    nullable.add(rule.name)
                    changed = True
        return IrSeq(*(IrStr(name) for name in nullable))


def _matches_char(atom: IrSelf, char: str) -> bool:
    """Whether terminal ``atom`` accepts the single character ``char``.

    The terminal-match predicate shared by :class:`Matches` (the IR-protocol
    form) and the engine's inlined :func:`_scan_column`. Assumes literals were
    split to one char each (see :mod:`lexic.parsing_2.normalize`); a non-terminal
    atom never matches.

    :param atom: The terminal atom after a dot.
    :param char: A single input character.
    :returns: ``True`` if ``atom`` accepts ``char``.
    """
    if isinstance(atom, IrLiteral):
        return char == atom  # IrLiteral IS-A str
    if isinstance(atom, IrCharClass):
        for element in atom:
            if isinstance(element, IrRange):
                if str(element.lo) <= char <= str(element.hi):
                    return True
            elif char in str(element):
                return True
    return False


class Matches(IrLeaf[IrSelf, IrSelf]):
    """Whether a terminal atom accepts a single character.

    Assumes literals were split to one char each (see
    :mod:`lexic.parsing_2.normalize`). A non-terminal atom (a ruleref) never
    matches, so the scanner can call this for every dotted item and skip on a
    zero result.
    """

    def eval(self, _d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> IrInt:
        """:param n: terminal atom; :param nc: ``(IrStr(char),)``; :returns: 0/1."""
        return IrInt(1 if _matches_char(n, str(nc[0])) else 0)


class AcceptingItem(IrLeaf[IrSelf, IrSelf]):
    """The start-rule item that completed spanning the whole input, if any."""

    def eval(self, _d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> IrSelf:
        """:param n: the chart; :param nc: ``(IrStr(start), IrInt(end))``.

        :returns: the accepting :class:`EarleyItem`, or :data:`IrNone`.
        """
        chart = cast(Chart, n)
        start = str(nc[0])
        end = int(cast(int, nc[1]))
        for item in chart[end]:
            if (
                item.dot >= len(item.arm)
                and str(item.rule_name) == start
                and item.origin == 0
            ):
                return item
        return IrNone


class _ParseState(NamedTuple):
    """Parse-invariant engine state, built **once per parse** (not per item).

    Bundles the three things every inlined operation needs, keeping their
    signatures small. Unlike the old per-dispatch ``ParseCtx`` (one per item,
    ~67 K/parse), exactly one of these exists for a whole parse.

    :ivar chart: The chart being grown.
    :ivar rules: Rule name → its :class:`~lexic.ir.nodes.IrAlternation` body, a
        plain ``dict`` for O(1) predict lookup.
    :ivar nullable: Names of rules that derive the empty string.
    """

    chart: Chart
    rules: dict[str, IrAlternation]
    nullable: set[str]


def _predict(
    state: _ParseState, symbol: IrRuleRef, item: EarleyItem, column: Column
) -> None:
    """Seed ``symbol``'s arms in ``column``; advance over a nullable target.

    Aycock-Horspool: a nullable target also advances the predicting item at
    once, recording an empty derivation as the consumed child (dedup-merged with
    the empty completion, so the link is set once).

    :param state: The parse-invariant engine state.
    :param symbol: The :class:`~lexic.ir.nodes.IrRuleRef` after the dot.
    :param item: The predicting item.
    :param column: The column being closed (its ``index`` is the current column).
    """
    col = column.index
    for arm in state.rules[symbol]:
        column += EarleyItem(symbol, arm, 0, col)
    if symbol in state.nullable:
        advanced = EarleyItem(item.rule_name, item.arm, item.dot + 1, item.origin)
        if advanced not in column:
            column += advanced
            empty = ParseTree(symbol, IrSeq())
            state.chart.links[(advanced, col)] = Link(item, col, empty)


def _complete(state: _ParseState, done: EarleyItem, column: Column) -> None:
    """Advance predecessors awaiting the just-completed rule ``done``.

    ``done`` recognised ``done.rule_name`` spanning ``done.origin .. col``; every
    item in the origin column awaiting that rule advances into ``column``. The
    sub-derivation is built once and recorded as each advanced item's consumed
    child.

    :param state: The parse-invariant engine state.
    :param done: The completed item (dot at arm end).
    :param column: The column being closed (its ``index`` is the current column).
    """
    col = column.index
    chart = state.chart
    subtree = walk_links(done, chart.links, col)
    for waiting in chart[done.origin].waiting[done.rule_name]:
        advanced = EarleyItem(
            waiting.rule_name, waiting.arm, waiting.dot + 1, waiting.origin
        )
        if advanced not in column:
            column += advanced
            chart.links[(advanced, col)] = Link(waiting, done.origin, subtree)


def _close_column(state: _ParseState, col: int) -> None:
    """Close Earley column ``col`` to a fixpoint — the inlined hot path.

    A cursor walks the column; predict/complete append in place, so newly added
    items are visited without a worklist. The operation is chosen by
    ``isinstance`` on the symbol after the dot (ruleref → predict, end → complete,
    terminal → scanned between columns). This avoids the per-item ``ParseCtx`` +
    ``IrTuple`` allocation the dispatch protocol would build (~100 K
    objects/parse). All chart access is through the public Column/Links surface.

    :param state: The parse-invariant engine state.
    :param col: The column index to close.
    """
    column = state.chart[col]
    cursor = 0
    while cursor < len(column):
        item = column[cursor]
        cursor += 1
        if item.dot >= len(item.arm):
            _complete(state, item, column)
            continue
        symbol = item.arm[item.dot].atom
        if isinstance(symbol, IrRuleRef):
            _predict(state, symbol, item, column)


def _scan_column(chart: Chart, text: str, i: int) -> None:
    """Scan ``text[i]``, advancing matching terminal items into column ``i+1``.

    The inlined scanner — avoids the ``IrStr``/``IrInt`` boxing and ``IrTuple``
    wrapper the protocol form builds per scannable item. The consumed character
    is built once as an :class:`~lexic.ir.nodes.IrLiteral` shared by all links.

    :param chart: The parse chart, mutated in place.
    :param text: The full input string.
    :param i: The column index to scan from.
    """
    char = text[i]
    char_leaf = IrLiteral(char)
    nxt = chart[i + 1]
    for item in chart[i]:
        if item.dot < len(item.arm) and _matches_char(item.arm[item.dot].atom, char):
            advanced = EarleyItem(item.rule_name, item.arm, item.dot + 1, item.origin)
            if advanced not in nxt:
                nxt += advanced
                chart.links[(advanced, i + 1)] = Link(item, i, char_leaf)


class CloseColumn(IrLeaf[IrSelf, IrSelf]):
    """Close column ``i`` to a fixpoint by dispatching each item's next symbol.

    ``d`` is the parser, ``n`` the chart, ``nc`` is
    ``(rules, IrStr(text), nullable, IrInt(i))``. A cursor walks the column;
    predict/complete append in place, so newly added items are visited without a
    separate worklist.
    """

    def eval(self, _d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> IrNoneType:
        """:param n: chart; :param nc: ``(rules, IrStr(text), nullable, IrInt(i))``."""
        chart = cast(Chart, n)
        rules = cast("IrMap[IrRuleRef, IrAlternation]", nc[0])
        nullable = cast(IrSeq, nc[2])
        i = int(cast(int, nc[3]))
        rules_dict = {str(dyad[0]): dyad[1] for dyad in rules}
        nullable_set = {str(name) for name in nullable}
        _close_column(_ParseState(chart, rules_dict, nullable_set), i)
        return IrNone


class ScanColumn(IrLeaf[IrSelf, IrSelf]):
    """Scan one character of input, advancing matching terminal items.

    ``d`` is the parser, ``n`` the chart, ``nc`` is ``(IrStr(text), IrInt(i))``.
    Each item in column ``i`` whose dot faces a terminal that accepts ``text[i]``
    advances into column ``i+1``, recording the consumed character as provenance.
    """

    def eval(self, _d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> IrNoneType:
        """:param n: chart; :param nc: ``(IrStr(text), IrInt(i))``."""
        chart = cast(Chart, n)
        text = str(nc[0])
        i = int(cast(int, nc[1]))
        _scan_column(chart, text, i)
        return IrNone


class BuildChart(IrLeaf[IrSelf, IrSelf]):
    """Run the full Earley loop and return the completed chart.

    ``d`` is the parser; ``n`` is the grammar; ``nc`` is ``(IrStr(text),)``. Seeds
    column 0 with the start rule's arms, then per column closes it
    (:class:`CloseColumn`) and scans one character into the next
    (:class:`ScanColumn`).
    """

    def eval(self, d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> IrSelf:
        """:param n: grammar; :param nc: ``(IrStr(text),)``; :returns: the chart."""
        grammar = cast(IrAst, n)
        text = str(nc[0])
        nullable_seq = cast(IrSeq, NULLABLE.eval(d, grammar, ()))
        rules: dict[str, IrAlternation] = {
            str(rule.name): rule.body for rule in grammar.rules
        }
        nullable: set[str] = {str(name) for name in nullable_seq}
        state = _ParseState(Chart(), rules, nullable)
        chart = state.chart

        start = IrRuleRef(grammar.start)
        column0 = chart[0]
        for arm in rules[grammar.start]:
            column0 += EarleyItem(start, arm, 0, 0)

        for i in range(len(text) + 1):
            _close_column(state, i)
            if i < len(text):
                _scan_column(chart, text, i)
        return chart


class EarleyParser(IrDispatch):
    """Recognises and parses text against an IR grammar by the Earley algorithm.

    The dispatch table IS the engine — resolving a symbol's operation is the
    inherited :class:`~lexic.ir.walk.IrDispatch` type-dispatch over
    :data:`~lexic.parsing_2.ops.EARLEY_OPS`. The driver loop lives in
    :class:`BuildChart`, which threads the chart and dispatches through here.
    """

    actions: IrTypeMap = EARLEY_OPS


RULE_INDEX = RuleIndex()
NULLABLE = NullableRules()
MATCHES = Matches()
ACCEPT = AcceptingItem()
CLOSE_COLUMN = CloseColumn()
SCAN_COLUMN = ScanColumn()
BUILD_CHART = BuildChart()
"""Shared engine nodes — all stateless, so one instance each."""


def recognize(grammar: IrAst, text: str) -> bool:
    """Whether ``text`` derives from ``grammar``'s start rule.

    :param grammar: The grammar, Earley-normalised (see
        :mod:`lexic.parsing_2.normalize`).
    :param text: The input string.
    :returns: ``True`` if the start rule spans the whole input.
    """
    parser = EarleyParser()
    chart = BUILD_CHART.eval(parser, grammar, IrTuple(IrStr(text)))
    item = ACCEPT.eval(parser, chart, IrTuple(IrStr(grammar.start), IrInt(len(text))))
    return not isinstance(item, IrNoneType)


def parse(grammar: IrAst, text: str) -> ParseTree:
    """Parse ``text`` into its derivation tree.

    The returned :class:`~lexic.parsing_2.forest.ParseTree` is reduced to an
    :class:`IrAst` (or a value) by a flavour's
    :class:`~lexic.parsing_2.reduce.Reducer`.

    :param grammar: The grammar, Earley-normalised.
    :param text: The input string.
    :returns: The derivation of ``text`` under the start rule.
    :raises UnsupportedConstructError: If ``text`` does not parse.
    """
    parser = EarleyParser()
    chart = BUILD_CHART.eval(parser, grammar, IrTuple(IrStr(text)))
    item = ACCEPT.eval(parser, chart, IrTuple(IrStr(grammar.start), IrInt(len(text))))
    if isinstance(item, IrNoneType):
        raise UnsupportedConstructError(
            f"parsing_2: input does not derive from {grammar.start!r}"
        )
    return cast(
        ParseTree,
        BUILD_TREE.eval(parser, item, IrTuple(chart, IrInt(len(text)))),
    )
