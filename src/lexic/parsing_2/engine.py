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

The package's callable API (``recognize``, ``parse``, ``parse_forest``,
``derivations``, ``is_ambiguous``) lives in :mod:`lexic.parsing_2.__init__` as
thin wrappers that drive the on-node orchestration here. This module contains
only the :class:`~lexic.ir.base.IrSelf` engine nodes and their shared singletons.
"""

from __future__ import annotations

from typing import Sequence, cast

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
from lexic.ir.mapping import IrMap, IrMultiMap, IrTypeMap
from lexic.ir.nodes import (
    IrAst,
    IrCharClass,
    IrLiteral,
    IrRange,
    IrRuleRef,
    IrSequence,
)
from lexic.ir.walk import IrDispatch
from lexic.parsing_2.chart import Chart, Link
from lexic.parsing_2.forest import (
    BUILD_TREE,
    DERIVATION_STREAM,
    DERIVATIONS,
    ParseTree,
    SppfNode,
)
from lexic.parsing_2.item import EarleyItem
from lexic.parsing_2.ops import EARLEY_OPS, ParseCtx


class RuleIndex(IrLeaf[IrSelf, IrSelf]):
    """Build the rule index: :class:`IrRuleRef` → its alternation body.

    A dict-backed :class:`~lexic.ir.mapping.IrMap` keyed by ``IrRuleRef`` — so
    the predictor's ``rules.resolve(ref)`` is an O(1) lookup returning the stored
    alternation with no per-read allocation, under type-aware key equality.
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

    Returned as an :class:`~lexic.ir.mapping.IrMultiMap` keyed by nullable
    ``IrRuleRef``: ``ref in nullable`` is the O(1) membership the predictor tests
    each prediction (``IrMultiMap.__contains__`` is an exception-free ``key in
    dict``), and ``nullable[ref]`` is the rule's **empty-deriving arms** — the set
    the Aycock-Horspool advance needs, computed once here instead of per predict.
    """

    def eval(self, _d: IrSelf, n: IrSelf, _nc: Sequence[IrSelf], /) -> IrMultiMap:
        """:param n: the grammar; :returns: nullable ref → its empty-deriving arms."""
        grammar = cast(IrAst, n)
        nullable: set[str] = set()
        changed = True
        while changed:
            changed = False
            for rule in grammar.rules:
                if rule.name in nullable:
                    continue
                if any(self._arm_is_nullable(arm, nullable) for arm in rule.body):
                    nullable.add(rule.name)
                    changed = True
        index: IrMultiMap[IrRuleRef, IrSequence] = IrMultiMap()
        for rule in grammar.rules:
            if rule.name not in nullable:
                continue
            ref = IrRuleRef(rule.name)
            for arm in rule.body:
                if self._arm_is_nullable(arm, nullable):
                    index += (ref, arm)
        return index

    @staticmethod
    def _arm_is_nullable(arm: IrSequence, nullable: set[str]) -> bool:
        """Whether ``arm`` derives the empty string — every item is a nullable
        ruleref (an empty arm vacuously). ``nullable`` is the name set so far."""
        return all(
            isinstance(it.atom, IrRuleRef) and str(it.atom) in nullable for it in arm
        )


_MATCH = IrInt(1)
_NO_MATCH = IrInt(0)
"""Shared truth-value leaves — :class:`Matches` returns one per scanned item, so
caching the two immutable results avoids an ``IrInt`` allocation each time."""


class Matches(IrLeaf[IrSelf, IrSelf]):
    """Whether a terminal atom accepts a single character.

    Assumes literals were split to one char each (see
    :mod:`lexic.parsing_2.normalize`). A non-terminal atom (a ruleref) never
    matches, so the scanner can call this for every dotted item and skip on a
    zero result.
    """

    def eval(self, _d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> IrInt:
        """:param n: terminal atom; :param nc: ``(IrStr(char),)``; :returns: 0/1."""
        atom = n
        char = str(nc[0])
        if isinstance(atom, IrLiteral):
            return _MATCH if char == atom else _NO_MATCH  # IrLiteral IS-A str
        if isinstance(atom, IrCharClass):
            for element in atom:
                if isinstance(element, IrRange):
                    if str(element.lo) <= char <= str(element.hi):
                        return _MATCH
                elif char in str(element):
                    return _MATCH
        return _NO_MATCH


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


class Accepting(IrLeaf[IrSelf, IrSelf]):
    """Build the chart once and locate the accepting start item.

    The shared front half of every entry point: it runs the Earley loop
    (:class:`BuildChart`) then finds the completed start item spanning the whole
    input (:class:`AcceptingItem`). Returned together as an :class:`IrSeq` so each
    public reader (recognise / parse / forest / enumerate) builds the chart once
    then reads it its own way — the orchestration is on a node, not a free function.
    """

    def eval(self, d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> IrSeq:
        """:param d: the parser; :param n: the grammar; :param nc: ``(IrStr(text),)``.

        :returns: ``IrSeq(chart, item)`` — ``item`` is :data:`IrNone` on no parse.
        """
        grammar = cast(IrAst, n)
        text = str(nc[0])
        chart = BUILD_CHART.eval(d, grammar, nc)
        item = ACCEPT.eval(d, chart, IrTuple(IrStr(grammar.start), IrInt(len(text))))
        return IrSeq(chart, item)


class CloseColumn(IrLeaf[IrSelf, IrSelf]):
    """Close the cursor's column to a fixpoint by dispatching each item's symbol.

    ``n`` is the chart, ``nc`` is ``(ParseCtx,)`` — the per-parse cursor, whose
    ``col`` the driver has set to the column to close. A cursor walks the column;
    the symbol after each item's dot is dispatched through ``d`` (predict /
    complete / scan-deferral via :data:`~lexic.parsing_2.ops.EARLEY_OPS`).
    Predict/complete append in place, so newly added items are visited without a
    separate worklist. The same ``nc`` (wrapping the reused ``ParseCtx``) is
    handed to every dispatch — only ``ctx.item`` advances — so no per-item
    context is allocated.
    """

    def eval(self, d: IrSelf, _n: IrSelf, nc: Sequence[IrSelf], /) -> IrNoneType:
        """:param nc: ``(ParseCtx,)`` with ``col`` set to the column to close."""
        ctx = cast(ParseCtx, nc[0])
        # ``for`` over the column yields a live list iterator that picks up the
        # items predict/complete append mid-pass (the Earley fixpoint) — no
        # per-item __len__/__getitem__ method call, unlike a manual cursor
        for item in ctx.chart[ctx.col]:
            _, arm, dot, _ = item  # tuple unpack: skips per-field descriptor reads
            symbol = arm[dot].atom if dot < len(arm) else IrNone
            ctx.item = item
            d.eval(d, symbol, nc)
        return IrNone


class ScanColumn(IrLeaf[IrSelf, IrSelf]):
    """Scan one character of input, advancing matching terminal items.

    ``n`` is the chart, ``nc`` is ``(IrStr(text), IrInt(i))``. Each item in column
    ``i`` whose dot faces a terminal that accepts ``text[i]`` advances into column
    ``i+1``, recording the consumed character as provenance. The match is the
    :class:`Matches` op (dispatched once per dotted item); the boxed character and
    its consumed-leaf are built once per column and shared across links.
    """

    def eval(self, d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> IrNoneType:
        """:param n: chart; :param nc: ``(IrStr(text), IrInt(i))``."""
        chart = cast(Chart, n)
        text = str(nc[0])
        i = int(cast(int, nc[1]))
        char_nc = IrTuple(IrStr(text[i]))
        char_leaf = IrLiteral(text[i])
        nxt = chart[i + 1]
        for item in chart[i]:
            arm, dot = item[1], item[2]  # index past the field descriptors
            if dot < len(arm) and MATCHES.eval(d, arm[dot].atom, char_nc):
                # advance the dot: (rule_name, arm, dot + 1, origin)
                advanced = EarleyItem(item[0], arm, dot + 1, item[3])
                nxt += advanced
                chart.links += ((advanced, i + 1), Link(item, i, char_leaf))
        return IrNone


class BuildChart(IrLeaf[IrSelf, IrSelf]):
    """Run the full Earley loop and return the completed chart.

    ``d`` is the parser; ``n`` is the grammar; ``nc`` is ``(IrStr(text),)``. Builds
    the per-parse :class:`~lexic.parsing_2.ops.ParseCtx` cursor once, seeds column
    0 with the start rule's arms, then per column closes it (:class:`CloseColumn`)
    and scans one character into the next (:class:`ScanColumn`).
    """

    def eval(self, d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> IrSelf:
        """:param n: grammar; :param nc: ``(IrStr(text),)``; :returns: the chart."""
        grammar = cast(IrAst, n)
        text = str(nc[0])
        rules = cast(IrMap, RULE_INDEX.eval(d, grammar, ()))
        nullable = cast(IrMultiMap, NULLABLE.eval(d, grammar, ()))
        ctx = ParseCtx(Chart(), rules, nullable)
        ctx_nc = IrTuple(ctx)
        text_node = IrStr(text)

        start = IrRuleRef(grammar.start)
        column0 = ctx.chart[0]
        for arm in rules.resolve(start):
            column0 += EarleyItem(start, arm, 0, 0)

        for i in range(len(text) + 1):
            ctx.col = i
            CLOSE_COLUMN.eval(d, ctx.chart, ctx_nc)
            if i < len(text):
                SCAN_COLUMN.eval(d, ctx.chart, (text_node, IrInt(i)))
        return ctx.chart


class Recognize(IrLeaf[IrSelf, IrSelf]):
    """Whether ``text`` derives from the grammar's start rule — a truth value.

    ``d`` is the parser; ``n`` is the grammar; ``nc`` is ``(IrStr(text),)``. Reads
    only whether :class:`Accepting` found a completed start item.
    """

    def eval(self, d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> IrInt:
        """:param n: grammar; :param nc: ``(IrStr(text),)``; :returns: ``IrInt`` 0/1."""
        _, item = ACCEPTING.eval(d, n, nc)
        return IrInt(0) if isinstance(item, IrNoneType) else IrInt(1)


class Parse(IrLeaf[IrSelf, IrSelf]):
    """The strict single derivation of ``text`` as a :class:`~lexic.parsing_2.forest.ParseTree`.

    ``d`` is the parser; ``n`` is the grammar; ``nc`` is ``(IrStr(text),)``.
    Delegates the build to :data:`~lexic.parsing_2.forest.BUILD_TREE`, which raises
    on ambiguous input; a non-parse raises here.
    """

    def eval(self, d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> ParseTree:
        """:param n: grammar; :param nc: ``(IrStr(text),)``; :returns: the derivation.

        :raises UnsupportedConstructError: If ``text`` does not parse, or parses
            ambiguously.
        """
        chart, item = ACCEPTING.eval(d, n, nc)
        if isinstance(item, IrNoneType):
            raise UnsupportedConstructError(
                f"parsing_2: input does not derive from {cast(IrAst, n).start!r}"
            )
        tree = BUILD_TREE.eval(d, item, IrTuple(chart, IrInt(len(str(nc[0])))))
        return cast(ParseTree, tree)


class ParseForest(IrLeaf[IrSelf, IrSelf]):
    """The shared packed parse forest root — an :class:`~lexic.parsing_2.forest.SppfNode`.

    ``d`` is the parser; ``n`` is the grammar; ``nc`` is ``(IrStr(text),)``.
    Returns :data:`~lexic.ir.base.IrNone` when ``text`` does not parse.
    """

    def eval(self, d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> IrSelf:
        """:param n: grammar; :param nc: ``(IrStr(text),)``; :returns: the SPPF root."""
        _, item = ACCEPTING.eval(d, n, nc)
        if isinstance(item, IrNoneType):
            return IrNone
        return SppfNode(cast(EarleyItem, item), len(str(nc[0])))


class Enumerate(IrLeaf[IrSelf, IrSelf]):
    """ALL derivation trees of ``text`` as an :class:`~lexic.ir.base.IrSeq` (empty on no parse).

    ``d`` is the parser; ``n`` is the grammar; ``nc`` is ``(IrStr(text),)``. Builds
    the SPPF root then enumerates it via :data:`~lexic.parsing_2.forest.DERIVATIONS`.
    """

    def eval(self, d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> IrSeq:
        """:param n: grammar; :param nc: ``(IrStr(text),)``; :returns: every derivation."""
        chart, item = ACCEPTING.eval(d, n, nc)
        if isinstance(item, IrNoneType):
            return IrSeq()
        node = SppfNode(cast(EarleyItem, item), len(str(nc[0])))
        return cast(IrSeq, DERIVATIONS.eval(d, node, IrTuple(chart)))


class IsAmbiguous(IrLeaf[IrSelf, IrSelf]):
    """Whether ``text`` has more than one derivation — a truth value.

    ``d`` is the parser; ``n`` is the grammar; ``nc`` is ``(IrStr(text),)``.
    """

    def eval(self, d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> IrInt:
        """:param n: grammar; :param nc: ``(IrStr(text),)``; :returns: ``IrInt`` 0/1.

        Short-circuits: takes only the first two derivations from the lazy
        :data:`~lexic.parsing_2.forest.DERIVATION_STREAM`, never the full
        (potentially exponential) enumeration.
        """
        chart, item = ACCEPTING.eval(d, n, nc)
        if isinstance(item, IrNoneType):
            return _NO_MATCH
        node = SppfNode(cast(EarleyItem, item), len(str(nc[0])))
        seen = 0
        for _tree in DERIVATION_STREAM.eval(d, node, IrTuple(chart)):
            seen += 1
            if seen > 1:  # a second derivation ⇒ ambiguous; stop driving
                return _MATCH
        return _NO_MATCH


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
ACCEPTING = Accepting()
CLOSE_COLUMN = CloseColumn()
SCAN_COLUMN = ScanColumn()
BUILD_CHART = BuildChart()
RECOGNIZE = Recognize()
PARSE = Parse()
PARSE_FOREST = ParseForest()
ENUMERATE = Enumerate()
IS_AMBIGUOUS = IsAmbiguous()
"""Shared engine nodes — all stateless, so one instance each."""
