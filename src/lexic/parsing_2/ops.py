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
    IrLeaf,
    IrNone,
    IrNoneType,
    IrSelf,
)
from lexic.ir.mapping import IrMap, IrMultiMap, IrTypeMap
from lexic.ir.nodes import (
    IrAlternation,
    IrCharClass,
    IrLiteral,
    IrRange,
    IrRuleRef,
    IrSequence,
)
from lexic.parsing_2.chart import Chart, Link
from lexic.parsing_2.forest import SppfNode
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

    ``rules`` is a dict-backed :class:`~lexic.ir.mapping.IrMap` (rule ref → its
    alternation body), so ``resolve`` is an O(1) lookup returning the stored
    alternation with no per-read allocation; ``nullable`` is an
    :class:`~lexic.ir.mapping.IrMultiMap` keyed by nullable ref, so ``ref in
    nullable`` is O(1) and ``nullable[ref]`` is the rule's empty-deriving arms.

    :ivar chart: The chart being grown.
    :ivar rules: Rule ref → its alternation body.
    :ivar nullable: Nullable ref → its empty-deriving arms — the predictor
        advances over these immediately (Aycock-Horspool).
    :ivar col: The column currently being closed.
    :ivar item: The item currently being dispatched.
    """

    __slots__ = ("chart", "rules", "nullable", "col", "item")

    chart: Chart
    rules: IrMap[IrRuleRef, IrAlternation]
    nullable: IrMultiMap[IrRuleRef, IrSequence]
    col: int
    item: EarleyItem

    def __init__(
        self,
        chart: Chart,
        rules: IrMap[IrRuleRef, IrAlternation],
        nullable: IrMultiMap[IrRuleRef, IrSequence],
    ) -> None:
        """Seed the parse-invariant fields; the driver advances ``col``/``item``.

        :param chart: The chart to grow.
        :param rules: The rule-ref → alternation-body index.
        :param nullable: Nullable ref → its empty-deriving arms.
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
    (Aycock-Horspool) — needed for correctness, since a nullable ``ref`` predicted
    *after* its own empty completion already fired in this column would otherwise
    never advance its waiter.

    The advance's consumed child is the **same** shared
    :class:`~lexic.parsing_2.forest.SppfNode` the completer would record for
    ``ref``'s empty completion: ``SppfNode(EarleyItem(ref, arm, len(arm), col),
    col)`` for each arm of ``ref`` that derives the empty string (Scott 2008). An
    arm derives empty when every item is a nullable ruleref (the empty arm
    vacuously) — the same condition :class:`~lexic.parsing_2.engine.NullableRules`
    uses. Recording the identical node identity (rather than a hand-built
    ``ParseTree``) lets :class:`~lexic.parsing_2.chart.Links` dedup collapse the AH
    advance and the matching empty completion into ONE family, so an unambiguous
    nullable derivation is recorded once — while a rule with two distinct
    empty-deriving arms still records both families (genuine ambiguity preserved).
    Newly added items extend the column the driver is iterating.
    """

    def eval(self, _d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> IrNoneType:
        """Add a dot-0 item per arm; advance over a nullable target (Aycock-Horspool).

        For a nullable ``ref``, advances the predicting item and records one packed
        family per empty-deriving arm of ``ref``, each using the canonical
        :class:`~lexic.parsing_2.forest.SppfNode` the completer records for that
        arm's empty completion — so the two provenances dedup to one family.

        :param _d: Dispatcher (unused — prediction reads the chart, not children).
        :param n: The :class:`~lexic.ir.nodes.IrRuleRef` after the dot.
        :param nc: ``(ParseCtx,)``.
        :returns: :data:`IrNone`.
        """
        ctx = cast(ParseCtx, nc[0])
        ref = cast(IrRuleRef, n)
        origin = ctx.col
        column = ctx.chart[origin]
        arms = ctx.rules.resolve(ref)  # one resolve, reused by the nullable branch
        for arm in arms:
            column += EarleyItem(ref, arm, 0, origin)
        if ref in ctx.nullable:
            it = ctx.item  # advance the dot: (rule, arm, dot + 1, origin)
            advanced = EarleyItem(it[0], it[1], it[2] + 1, it[3])
            column += advanced
            for arm in ctx.nullable[ref]:  # precomputed empty-deriving arms
                done = EarleyItem(ref, arm, len(arm), origin)
                child = SppfNode(done, origin)
                ctx.chart.links += ((advanced, origin), Link(it, origin, child))
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
    current column. The completed item is referenced by a shared
    :class:`~lexic.parsing_2.forest.SppfNode` ``(done, col)`` — NOT flattened to one
    tree — so the sub-derivation (and any ambiguity it packs) is recovered lazily by
    the forest. Each advanced predecessor records that node as the child it
    consumed; the family is always recorded (deduped by
    :class:`~lexic.parsing_2.chart.Links`) even when the advanced item already
    exists, so a second distinct derivation of the same item is an ADDITIONAL
    family, not a dropped one (Scott 2008).
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
        done_origin = done[3]  # index past the field descriptor (origin)
        waiters = chart[done_origin].waiting[done[0]]  # done[0] is rule_name
        if not waiters:  # nothing waiting — no advance, no family to record
            return IrNone
        col = ctx.col
        subnode = SppfNode(done, col)
        current = chart[col]
        # waiters is the live bucket; a plain ``for`` over the list picks up any
        # same-pass appends (advancing files a new waiter when origin == col)
        for waiting in waiters:  # advance the dot: (rule, arm, dot + 1, origin)
            advanced = EarleyItem(waiting[0], waiting[1], waiting[2] + 1, waiting[3])
            current += advanced
            chart.links += ((advanced, col), Link(waiting, done_origin, subnode))
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
