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
reads each column's ``scannable_by_atom`` index (items already filed by the atom
their dot faces). So :class:`Scan` is a no-op that exists only to give terminals
a (do-nothing) dispatch target.
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
from lexic.parsing_2.chart import Chart, Column
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

    ``char_accepts`` is the grammar-level char → accepting terminal atoms index,
    seeded with every terminal atom under a sentinel key and filled lazily (per
    char, on first scan) by the driver — so the scanner resolves which atoms a
    character matches once, then reads each column's ``scannable_by_atom`` bucket.

    :ivar chart: The chart being grown.
    :ivar rules: Rule ref → its alternation body.
    :ivar nullable: Nullable ref → its empty-deriving arms — the predictor
        advances over these immediately (Aycock-Horspool).
    :ivar char_accepts: Char → the terminal atoms that accept it (lazily filled).
    :ivar record_links: Whether to record SPPF provenance links — ``True`` for
        parse/forest/ambiguity, ``False`` for pure recognition (which never reads
        the forest, so building it is wasted work).
    :ivar column: The column currently being closed — stashed by the driver so the
        predictor/completer skip re-indexing the chart on the hot path; its
        ``index`` is the current input position (the origin of new predictions).
    :ivar item: The item currently being dispatched.
    """

    __slots__ = (
        "chart",
        "rules",
        "nullable",
        "char_accepts",
        "record_links",
        "column",
        "item",
    )

    chart: Chart
    rules: IrMap[IrRuleRef, IrAlternation]
    nullable: IrMultiMap[IrRuleRef, IrSequence]
    char_accepts: IrMultiMap[str, IrSelf]
    record_links: bool
    column: Column
    item: EarleyItem

    def __init__(
        self,
        chart: Chart,
        rules: IrMap[IrRuleRef, IrAlternation],
        nullable: IrMultiMap[IrRuleRef, IrSequence],
        char_accepts: IrMultiMap[str, IrSelf],
    ) -> None:
        """Seed the parse-invariant fields; the driver advances ``col``/``item``.

        :param chart: The chart to grow.
        :param rules: The rule-ref → alternation-body index.
        :param nullable: Nullable ref → its empty-deriving arms.
        :param char_accepts: Char → accepting terminal atoms (lazily filled).
        """
        self.chart = chart
        self.rules = rules
        self.nullable = nullable
        self.char_accepts = char_accepts
        self.record_links = True  # the driver flips this off for pure recognition
        # ``column``/``item`` are set by the driver before each dispatch; IrNone is
        # the absence sentinel until then (it fits every slot, signatures union-free).
        self.column = cast(Column, IrNone)
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
        column = ctx.column  # the current column the driver is closing
        origin = column.index
        if ref not in column.predicted:  # seed each rule's arms once per column
            column.predicted.add(ref)
            for arm in ctx.rules.resolve(ref):
                column += (ref, arm, 0, origin)
        if ref in ctx.nullable:
            it = ctx.item  # advance the dot: (rule, arm, dot + 1, origin)
            advanced = (it[0], it[1], it[2] + 1, it[3])
            column += advanced
            if ctx.record_links:  # SPPF provenance — skipped for pure recognition
                for arm in ctx.nullable[ref]:  # precomputed empty-deriving arms
                    done = (ref, arm, len(arm), origin)
                    child = SppfNode(done, origin)
                    ctx.chart.links += ((advanced, origin), (it, origin, child))
        return IrNone


class Scan(IrLeaf[IrSelf, IrSelf]):
    """Earley scanner (deferral half): a terminal needs no close-time action.

    The character match happens between columns in the driver, which reads each
    column's ``scannable_by_atom`` index — so this body is a no-op, present only
    so a terminal symbol has a dispatch target.
    """

    def eval(self, _d: IrSelf, _n: IrSelf, _nc: Sequence[IrSelf], /) -> IrNoneType:
        """No-op: terminals are scanned by the driver, not here.

        :returns: :data:`IrNone`.
        """
        return IrNone


class LeoItem(IrLeaf[IrSelf, IrSelf]):
    """Leo's transitive (topmost) item for a deterministic right-recursive reduction.

    Leo (1991): a *deterministic* right-recursive reduction may jump straight to
    the chain's topmost item instead of the completer re-walking the chain at each
    column (the O(n²)→O(n) win). The recursion up the chain is this node's
    :meth:`resolve`; the per-column memo is the column's ``leo``
    :class:`IrMultiMap` — so the logic stays on a node and the state on a cursor,
    never a free function. :meth:`resolve` takes plain indices (no per-call
    boxing — the completer hits it once per right-recursive reduction);
    :meth:`eval` is the :class:`IrSelf`-protocol wrapper over it.

    A Leo candidate is the **unique** waiter ``[B → α • ref]`` in the column with
    ``ref`` the *last* symbol (read from the small ``waiting[ref]`` bucket). The
    transitive item is the parent's own Leo item, else the parent's completion
    ``[B → α ref •, k]``. :data:`IrNone` means not deterministic (the normal
    completer must run). Closed columns are memoised; the current column is
    recomputed (its waiters may still grow), so the memo never goes stale.
    """

    def eval(self, _d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> IrSelf:
        """Protocol wrapper over :meth:`resolve`.

        :param n: the chart; :param nc: ``(IrInt(col), ref, IrInt(cur))``.
        :returns: the topmost :class:`EarleyItem` to add, or :data:`IrNone`.
        """
        return self.resolve(
            cast(Chart, n),
            int(cast(int, nc[0])),
            cast(IrRuleRef, nc[1]),
            int(cast(int, nc[2])),
        )

    def resolve(
        self,
        chart: Chart,
        col: int,
        ref: IrRuleRef,
        cur: int,
        seen: set[tuple[int, IrRuleRef]] | None = None,
    ) -> IrSelf:
        """The Leo transitive item for completing ``ref`` ending at column ``col``.

        A nullable cycle (e.g. ``a = b`` / ``b = a / ''``) makes the chain re-enter
        the same ``(col, ref)`` over empty spans — no topmost item exists. Such a
        cycle can only close across **same-column** steps: a step that consumes
        input lowers ``col``, and ``col`` is non-increasing up the climb, so once it
        drops it can never return. The cycle guard is therefore needed only on a
        same-column (empty-span) step; ``seen`` is allocated lazily there and stays
        ``None`` for the common cross-column right-recursion, which never cycles.
        Revisiting a recorded ``(col, ref)`` yields :data:`IrNone`, and the normal
        completer runs instead (it terminates the cycle via the forest's empty-span
        guard).

        :param col: The column to resolve in (the completion's origin).
        :param ref: The completing non-terminal.
        :param cur: The column currently being closed (its memo is unstable).
        :param seen: The same-column ``(col, ref)`` pairs on this climb, or ``None``
            until the first empty-span step needs the guard (cycle guard).
        :returns: the topmost :class:`EarleyItem`, or :data:`IrNone`.
        """
        column = chart[col]
        if col != cur:  # a closed column — its memo is stable
            memo = column.leo[ref]
            if memo:
                return memo[0]
        if seen is not None and (col, ref) in seen:  # re-entered ⇒ nullable cycle
            return IrNone
        found = self.sole_candidate(column, ref)
        if found is IrNone:
            result: IrSelf = IrNone
        else:
            item = cast(EarleyItem, found)
            if item[3] == col:  # empty-span step — the only way to close a cycle
                if seen is None:
                    seen = set()
                seen.add((col, ref))
            parent = self.resolve(chart, item[3], item[0], cur, seen)
            # parent's Leo item, else the parent's own completion [B → α ref •, k]
            result = (
                parent
                if parent is not IrNone
                else cast(IrSelf, (item[0], item[1], item[2] + 1, item[3]))
            )
        if col != cur:
            column.leo += (ref, result)
        return result

    @staticmethod
    def sole_candidate(column: Column, ref: IrRuleRef) -> IrSelf:
        """The deterministic right-recursion waiter for ``ref``, else :data:`IrNone`.

        Leo applies only when ``ref`` completing is a *purely* deterministic
        reduction: ``ref`` has exactly **one** waiter ``[B → α • ref]`` in the
        column AND it is last-symbol (so completing ``ref`` does nothing but
        complete ``B`` — the chain link Leo replaces). Any second waiter — even
        one where ``ref`` is *not* last (``[B → α • ref β]``, which must advance
        normally) — makes it non-deterministic, so the normal completer runs.
        """
        waiters = column.waiting[ref]
        if len(waiters) != 1:
            return IrNone  # zero or multiple waiters ⇒ not a deterministic chain
        sole = waiters[0]
        if sole[2] + 1 == len(sole[1]):  # ref is the last symbol of its arm
            return cast(IrSelf, sole)
        return IrNone


LEO_ITEM = LeoItem()
"""Shared Leo-resolver node — stateless (its state is the columns' memos)."""


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
        current = ctx.column  # the current column the driver is closing
        # Leo fast path: a *lone* last-symbol waiter is a deterministic
        # right-recursion chain link — jump to the transitive top instead of
        # advancing it (advancing re-walks the whole chain at every column,
        # Θ(n²)). The cheap gate here (``waiters`` already in hand) keeps the node
        # call off normal grammars.
        if len(waiters) == 1:
            sole = waiters[0]
            # Leo only pays when the lone waiter's *own* rule also reduces
            # deterministically one level up — i.e. the chain is length ≥ 2. A
            # length-1 completion (or a nullable cycle, caught as IrNone by resolve)
            # is an ordinary single completion: deferring it and re-expanding the
            # forest later costs more than recording the direct link, so it falls
            # through to the normal completer below. This one-level pre-check keeps
            # grammars of many *shallow* right-recursions at the normal cost and
            # reserves Leo's deferral for genuinely deep chains.
            if sole[2] + 1 == len(sole[1]) and (  # dot before ref, ref last symbol
                LEO_ITEM.sole_candidate(chart[sole[3]], sole[0]) is not IrNone
            ):
                cur = current.index
                top = LEO_ITEM.resolve(chart, done_origin, done[0], cur)
                if not isinstance(top, IrNoneType):  # IrNone ⇒ nullable cycle, run normal
                    current += cast(EarleyItem, top)
                    # File the chain's bottom under the top so the forest can rebuild
                    # the skipped completions on demand (Θ(chain) once, lazily, only
                    # if walked). Pure recognition never reads the forest, so skip it.
                    if ctx.record_links and (top, cur) not in chart.leo_links:
                        chart.leo_links += (
                            (top, cur),
                            (sole, done_origin, SppfNode(done, cur)),
                        )
                    return IrNone
        col = current.index
        record_links = ctx.record_links  # SPPF off for pure recognition
        subnode = SppfNode(done, col) if record_links else IrNone
        # waiters is the live bucket; a plain ``for`` over the list picks up any
        # same-pass appends (advancing files a new waiter when origin == col)
        for waiting in waiters:  # advance the dot: (rule, arm, dot + 1, origin)
            advanced = (waiting[0], waiting[1], waiting[2] + 1, waiting[3])
            current += advanced
            if record_links:
                chart.links += ((advanced, col), (waiting, done_origin, subnode))
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
