"""Earley operations as IR action bodies, dispatched on the symbol after the dot.

The three classical Earley operations are the three IR bodies here, and the
choice between them IS the dispatch on the symbol after the dot:

==================================  ============================  ===========
symbol after the dot                meaning                       body
==================================  ============================  ===========
:class:`~lexic.ir.nodes.IrRuleRef`  non-terminal                  :class:`Predict`
:class:`~lexic.ir.nodes.IrLiteral`  terminal (single char)        :class:`Scan`
:class:`~lexic.ir.nodes.IrCharClass` / :class:`~lexic.ir.nodes.IrRange`  terminal set  :class:`Scan`
:class:`~lexic.ir.base.IrNoneType`  none left — arm complete      :class:`Complete`
==================================  ============================  ===========

:data:`EARLEY_OPS` is the :class:`~lexic.ir.mapping.IrTypeMap` wiring those up —
the exact dispatch substrate the emit flavours use, pointed the other way. Each
body is side-effecting (it mutates the chart and returns :data:`IrNone`, the
visitor convention); the per-item context arrives through ``nc`` as a single
:class:`ParseCtx`, the documented "argument channel" use of ``nc``.

:class:`Scan` is the deferral half — a terminal needs no action while a column is
closing; the actual character match runs between columns in the driver, which
re-derives the scannable items by filtering the closed column. So :class:`Scan`
is a no-op that exists only to give terminals a (do-nothing) dispatch target.
"""

from __future__ import annotations

from typing import Sequence, cast

from lexic.ir.action import IrAction
from lexic.ir.base import (
    IrInt,
    IrLeaf,
    IrNone,
    IrNoneType,
    IrSelf,
    IrSeq,
    IrTuple,
)
from lexic.ir.mapping import IrMap, IrTypeMap
from lexic.ir.nodes import IrAlternation, IrCharClass, IrLiteral, IrRange, IrRuleRef
from lexic.parsing_2.chart import Chart, Link
from lexic.parsing_2.forest import BUILD_TREE, ParseTree
from lexic.parsing_2.item import EarleyItem


class ParseCtx(IrLeaf[IrSelf, IrSelf]):
    """Per-parse engine cursor handed to an operation body through ``nc``.

    A **mutable** leaf (the mutable-chart exception, like
    :class:`~lexic.parsing_2.chart.Chart`): the parse-invariant fields
    (``chart``, ``rules``, ``nullable``) are set once, while ``col`` and ``item``
    are advanced in place by the driver as it walks each column. Exactly one
    ``ParseCtx`` exists per parse, so the per-item ``ParseCtx`` + ``IrTuple``
    allocation the dispatch protocol once paid (~67 K/parse) is gone — the driver
    reuses a single ``IrTuple(ctx)`` across every dispatch. It is engine state,
    never walked (``children()`` is empty), emitted, or reduced.

    :ivar chart: The chart being grown.
    :ivar rules: Rule index — :class:`~lexic.ir.nodes.IrRuleRef` → its
        :class:`~lexic.ir.nodes.IrAlternation` body.
    :ivar nullable: Names of rules that can derive the empty string (an
        :class:`~lexic.ir.base.IrSeq` of name leaves) — the predictor advances
        over these immediately (Aycock-Horspool).
    :ivar col: The column currently being closed.
    :ivar item: The item currently being dispatched.
    """

    __slots__ = ("chart", "rules", "nullable", "col", "item")

    chart: Chart
    rules: IrMap[IrRuleRef, IrAlternation]
    nullable: IrSeq
    col: int
    item: EarleyItem

    def __init__(
        self, chart: Chart, rules: IrMap[IrRuleRef, IrAlternation], nullable: IrSeq
    ) -> None:
        """Seed the parse-invariant fields; the driver advances ``col``/``item``.

        :param chart: The chart to grow.
        :param rules: The rule-ref → body index.
        :param nullable: Names of nullable rules.
        """
        self.chart = chart
        self.rules = rules
        self.nullable = nullable
        self.col = 0
        # ``item`` is set by the driver before each dispatch; IrNone is the
        # absence sentinel until then (it fits every slot, signatures union-free).
        self.item = cast(EarleyItem, IrNone)


class Predict(IrLeaf[IrSelf, IrSelf]):
    """Earley predictor: the dot faces non-terminal ``n``; seed its arms.

    For every arm of ``rules[n]`` add a fresh dot-0 item originating at the
    current column. A nullable target also advances the predicting item at once
    (Aycock-Horspool), recording an empty derivation as the consumed child — the
    advanced item is dedup-merged with the one the empty completion produces, so
    the empty-span link is set exactly once. Newly added items extend the column
    the driver is iterating.
    """

    def eval(self, _d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> IrNoneType:
        """Add a dot-0 item per arm; advance over a nullable target.

        :param _d: Dispatcher (unused — prediction reads the chart, not children).
        :param n: The :class:`~lexic.ir.nodes.IrRuleRef` after the dot.
        :param nc: ``(ParseCtx,)``.
        :returns: :data:`IrNone`.
        """
        ctx = cast(ParseCtx, nc[0])
        ref = cast(IrRuleRef, n)
        col = ctx.chart[ctx.col]
        for arm in ctx.rules.resolve(ref):
            col += EarleyItem(ref, arm, 0, ctx.col)
        if str(ref) in ctx.nullable:
            it = ctx.item
            advanced = EarleyItem(it.rule_name, it.arm, it.dot + 1, it.origin)
            if advanced not in col:
                col += advanced
                ctx.chart.links[(advanced, ctx.col)] = Link(
                    it, ctx.col, ParseTree(ref, IrSeq())
                )
        return IrNone


class Scan(IrLeaf[IrSelf, IrSelf]):
    """Earley scanner (deferral half): a terminal needs no close-time action.

    The character match happens between columns in the driver, which re-derives
    the scannable items by filtering the closed column — so this body is a no-op,
    present only so a terminal symbol has a dispatch target.
    """

    def eval(self, _d: IrSelf, _n: IrSelf, _nc: Sequence[IrSelf], /) -> IrNoneType:
        """No-op: terminals are scanned by the driver, not here.

        :returns: :data:`IrNone`.
        """
        return IrNone


class Complete(IrLeaf[IrSelf, IrSelf]):
    """Earley completer: the item is complete; advance its waiting predecessors.

    The completed item recognised ``rule_name`` spanning ``origin .. col``. Every
    item in column ``origin`` whose dot faces that same rule advances into the
    current column. The completed item's sub-derivation is built once (eagerly —
    all its children are already linked) and recorded as the child each advanced
    predecessor consumed, so :class:`~lexic.parsing_2.forest.BuildTree` can later
    walk the provenance links.
    """

    def eval(self, _d: IrSelf, _n: IrSelf, nc: Sequence[IrSelf], /) -> IrNoneType:
        """Advance predecessors that were waiting on the completed rule.

        :param _d: Dispatcher (unused).
        :param _n: :data:`IrNone` (unused — the item carries everything).
        :param nc: ``(ParseCtx,)``.
        :returns: :data:`IrNone`.
        """
        ctx = cast(ParseCtx, nc[0])
        done = ctx.item
        chart = ctx.chart
        waiters = chart[done.origin].waiting[done.rule_name]
        if not waiters:  # nothing to advance — skip the subtree build entirely
            return IrNone
        subtree = BUILD_TREE.eval(_d, done, IrTuple(chart, IrInt(ctx.col)))
        current = chart[ctx.col]
        for waiting in waiters:
            advanced = EarleyItem(
                waiting.rule_name, waiting.arm, waiting.dot + 1, waiting.origin
            )
            if advanced not in current:
                current += advanced
                chart.links[(advanced, ctx.col)] = Link(waiting, done.origin, subtree)
        return IrNone


EARLEY_OPS: IrTypeMap = IrTypeMap(
    IrAction(IrRuleRef, Predict()),
    IrAction(IrLiteral, Scan()),
    IrAction(IrCharClass, Scan()),
    IrAction(IrRange, Scan()),
    IrAction(IrNoneType, Complete()),
)
"""The Earley engine, as a dispatch table keyed on the symbol after the dot.

``IrRuleRef`` resolves to :class:`Predict` over its own MRO entry, ahead of the
``IrStr`` it subclasses — concrete-first resolution, the same property the emit
flavours rely on. A bare :class:`~lexic.ir.base.IrStr` run inside a char class is
reached through ``IrCharClass`` (its container), so it needs no own entry here.
"""
