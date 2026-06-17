"""Earley operations as IR action bodies, dispatched on the symbol after the dot.

The three classical Earley operations are the three IR bodies here, and the
choice between them IS the dispatch on ``item.next_symbol()``:

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
"""

from __future__ import annotations

from typing import ClassVar, Sequence, cast

from lexic.ir.action import IrAction
from lexic.ir.base import IrLeaf, IrNamedTuple, IrNone, IrNoneType, IrSelf, IrSeq
from lexic.ir.mapping import IrMap, IrTypeMap
from lexic.ir.nodes import IrAlternation, IrCharClass, IrLiteral, IrRange, IrRuleRef
from lexic.parsing_2.chart import Chart
from lexic.parsing_2.forest import ParseTree, build_tree
from lexic.parsing_2.item import EarleyItem


class ParseCtx(IrNamedTuple):
    """Per-dispatch context handed to an operation body through ``nc``.

    Scalar payload only (``_child_attrs = ()``): the context is engine state,
    not a grammar node to walk.

    :ivar chart: The chart being grown.
    :ivar rules: Rule index — :class:`~lexic.ir.nodes.IrRuleRef` → its
        :class:`~lexic.ir.nodes.IrAlternation` body.
    :ivar text: The full input string.
    :ivar col: The current column index.
    :ivar item: The item currently being processed.
    :ivar nullable: Names of rules that can derive the empty string — the
        predictor advances over these immediately (Aycock-Horspool).
    """

    _child_attrs: ClassVar[tuple[str, ...]] = ()
    chart: Chart
    rules: IrMap[IrRuleRef, IrAlternation]
    text: str
    col: int
    item: EarleyItem
    nullable: frozenset[str]


def _ctx(nc: Sequence[IrSelf]) -> ParseCtx:
    """Pull the :class:`ParseCtx` out of the argument channel.

    :param nc: The argument channel — ``(ParseCtx,)``.
    :returns: The context.
    """
    return cast(ParseCtx, nc[0])


def _advance_over_empty(ctx: ParseCtx, ref: IrRuleRef) -> None:
    """Advance the predicting item past a nullable ``ref`` (Aycock-Horspool).

    A nullable non-terminal may match the empty string, so the item that
    predicted it can move its dot at once, recording an empty derivation as the
    consumed child. This covers the items predicted *after* the empty completion
    already fired in the column — the classic nullable-rule gap. The advanced
    item is identical to (and dedup-merged with) the one the empty completion
    produces, so the empty-span link is set exactly once.

    :param ctx: The current dispatch context.
    :param ref: The nullable non-terminal after the dot.
    """
    advanced = ctx.item.advance()
    if ctx.chart[ctx.col].add(advanced):
        ctx.chart.links[(advanced, ctx.col)] = (
            ctx.item,
            ctx.col,
            ParseTree(ref, IrSeq()),
        )


class Predict(IrLeaf[IrSelf, IrSelf]):
    """Earley predictor: the dot faces non-terminal ``n``; seed its arms.

    For every arm of ``rules[n]`` add a fresh dot-0 item originating at the
    current column. Newly added items extend the column the driver is iterating.
    """

    def eval(self, _d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> IrNoneType:
        """Add a dot-0 item per arm of the predicted rule.

        :param _d: Dispatcher (unused — prediction reads the chart, not children).
        :param n: The :class:`~lexic.ir.nodes.IrRuleRef` after the dot.
        :param nc: ``(ParseCtx,)``.
        :returns: :data:`IrNone`.
        """
        ctx = _ctx(nc)
        ref = cast(IrRuleRef, n)
        for arm in ctx.rules.resolve(ref):
            ctx.chart[ctx.col].add(EarleyItem(ref, arm, 0, ctx.col))
        if str(ref) in ctx.nullable:
            _advance_over_empty(ctx, ref)
        return IrNone


class Scan(IrLeaf[IrSelf, IrSelf]):
    """Earley scanner (deferral half): the dot faces a terminal; queue the item.

    The actual character match happens in :meth:`EarleyParser._scan` between
    columns — here we only buffer the item, mirroring Lark's ``to_scan`` set.
    """

    def eval(self, _d: IrSelf, _n: IrSelf, nc: Sequence[IrSelf], /) -> IrNoneType:
        """Buffer the current item for the scanner step.

        :param _d: Dispatcher (unused).
        :param _n: The terminal atom after the dot (unused — read from the item).
        :param nc: ``(ParseCtx,)``.
        :returns: :data:`IrNone`.
        """
        ctx = _ctx(nc)
        ctx.chart[ctx.col].to_scan.append(ctx.item)
        return IrNone


class Complete(IrLeaf[IrSelf, IrSelf]):
    """Earley completer: the item is complete; advance its waiting predecessors.

    The completed item recognised ``rule_name`` spanning ``origin .. col``. Every
    item in column ``origin`` whose dot faces that same rule advances into the
    current column.
    """

    def eval(self, _d: IrSelf, _n: IrSelf, nc: Sequence[IrSelf], /) -> IrNoneType:
        """Advance predecessors that were waiting on the completed rule.

        The completed item's sub-derivation is built once (eagerly — all its
        children are already linked) and recorded as the child each advanced
        predecessor consumed, so :func:`~lexic.parsing_2.forest.build_tree` can
        later walk the provenance links.

        Nullable rules (``origin == col``) also advance their predecessors here,
        but predecessors *predicted after* this completion are caught by the
        predictor's Aycock-Horspool shortcut (:func:`_advance_over_empty`); the
        two paths produce the same advanced item and merge.

        :param _d: Dispatcher (unused).
        :param _n: :data:`IrNone` (unused — the item carries everything).
        :param nc: ``(ParseCtx,)``.
        :returns: :data:`IrNone`.
        """
        ctx = _ctx(nc)
        done = ctx.item
        chart = ctx.chart
        subtree = build_tree(chart, done, ctx.col)
        current = chart[ctx.col]
        for waiting in chart[done.origin]:
            if waiting.next_symbol() == done.rule_name:  # both IrRuleRef ⇒ eq holds
                advanced = waiting.advance()
                if current.add(advanced):
                    chart.links[(advanced, ctx.col)] = (waiting, done.origin, subtree)
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
