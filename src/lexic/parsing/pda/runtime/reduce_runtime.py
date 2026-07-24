"""Reduce (grammar-text) predictive runtime — the b1 twin of :class:`PdaKernel`.

Split out of :mod:`lexic.parsing.pda.runtime.runtime` (C0302 headroom): the model kernel
stays byte-for-byte unchanged there, and this module homes the grammar-text
completion — :class:`_ReducePdaKernel`, which shares the whole recognition
machinery (``run`` / ``_drive`` / ``_enter`` / ``prefix_run`` / the terminal
matchers) and only overrides the two completion callbacks (:meth:`_complete`,
:meth:`_island`) plus the delegate sub-run. :func:`parse_pda` — the single
public runtime entry — dispatches model vs reduce here so both kernels live
behind one seam. A leaf w.r.t. the model kernel: it imports ``PdaKernel`` from
``runtime`` and the frame-slot vocabulary / delegate-completion from ``build``,
never the reverse.
"""

from __future__ import annotations

from typing import Any, cast

from lexic.ir.base import IrNone, IrSelf, IrStr, IrTuple
from lexic.parsing.earley.reduce import DROP_KIND
from lexic.parsing.fold import ModelFold
from lexic.parsing.pda.compiler.clones import PdaTables, ReduceRun
from lexic.parsing.pda.compiler.flatten import OP_CC, R_DROP, R_SPLICE, FlatClone
from lexic.parsing.pda.core.errors import PdaFail
from lexic.parsing.pda.runtime.build import (
    F_ARM,
    F_CLONE,
    F_ENDS,
    F_OUT,
    F_SINKS,
    F_START,
    finish_delegate,
)
from lexic.parsing.pda.runtime.islands import island_value
from lexic.parsing.pda.runtime.runtime import PdaKernel

__all__ = ["parse_pda"]


class _ReducePdaKernel(PdaKernel):
    """The grammar-text (b1) twin of :class:`PdaKernel` — reducer completion.

    Shares the whole recognition machinery (``run`` / ``_drive`` / ``_enter`` /
    ``_quant_step`` / the terminal matchers) and only overrides the two
    completion callbacks — :meth:`_complete` (feed the reducer's cleaned children
    to its reduction ``body.eval``, no intermediate ParseTree) and
    :meth:`_island` (reduce the windowed Earley sub-parse through the same
    :class:`~lexic.parsing.earley.reduce.Reducer`). The model :class:`PdaKernel`
    is therefore left byte-for-byte unchanged — its hot path carries no reduce
    branch (the model-path perf guard). "One PDA compilation, one frame/island
    stack; only the completion callback differs" (the plan's settled design).

    :ivar reduce: The reduce runtime context (reducer, plan, tables, policy).
    """

    __slots__ = ("reduce",)

    reduce: ReduceRun

    def __init__(self, tables: PdaTables, text: str) -> None:
        """Prepare a reduce parse; ``tables.reduce`` supplies the completion context.

        :param tables: A reduce PDA (``tables.reduce`` is set).
        :param text: The grammar-text input to parse.
        """
        super().__init__(tables, text, None)
        self.reduce = cast(ReduceRun, tables.reduce)

    def _complete(self, frame: list[Any]) -> None:
        """Complete a reduce clone: evaluate its reduction body, splice, or drop.

        A ``KEEP`` clone feeds the reducer's cleaned children
        (:meth:`_reduce_parts`) to its reduction ``body.eval`` and reports the IR
        to the caller; a ``SPLICE`` (inline group) flattens its ordered children
        into the caller; a ``DROP`` (noise) clone contributes nothing. The b1
        completion callback — the sole per-path difference from the model build.
        """
        clone = frame[F_CLONE]
        kind = clone.reduce_kind
        self.stack.pop()
        if kind == R_DROP:
            return
        parts = self._reduce_parts(frame)
        out = frame[F_OUT]
        if kind == R_SPLICE:
            out.extend(parts)
            return
        reducer = self.reduce.reducer
        if clone.reduce_is_yield:
            value: IrSelf = IrStr(self._reduce_span(frame))
        else:
            span = IrStr(self._reduce_span(frame)) if clone.reduce_span else IrNone
            value = clone.reduce_body.eval(reducer, span, IrTuple(*parts))
        out.append(value)

    def _reduce_parts(self, frame: list[Any]) -> list[IrSelf]:
        """The clone's cleaned children in source order (the ``nc`` channel).

        Reconstructed from the frame's per-item ends + sinks: a terminal item
        contributes its KEEP_RAW char leaves (dropped under a DROP literal
        policy); a reference / group / island item contributes the captured
        sub-results already collected in its sink (a DROP child left its sink
        empty; a SPLICE group flattened its children in). The single home for the
        cleaning policy is the compiled
        :class:`~lexic.parsing.earley.reduce.ReducePlan` the clone baked from —
        this reconstructs, it does not re-derive (H5).
        """
        arm = frame[F_ARM]
        ends = frame[F_ENDS]
        sinks = frame[F_SINKS]
        text = self.text
        char_leaf = self.reduce.tables.terms.char_leaf
        lit_keep = self.reduce.literal_keep
        parts: list[IrSelf] = []
        prev = frame[F_START]
        for i in range(arm.n):
            end = ends[i]
            if arm.kinds[i] <= OP_CC:  # terminal (LIT / CC) — KEEP_RAW leaves
                if lit_keep and end > prev:
                    parts.extend(char_leaf(c) for c in text[prev:end])
            else:  # ref / group / island — captured sub-results
                sub = sinks[i] if sinks else None
                if sub:
                    parts.extend(sub)
            prev = end
        return parts

    def _reduce_span(self, frame: list[Any]) -> str:
        """The clone's matched span (a YIELD rule's value).

        A rule with no droppable descendant yields one contiguous slice. With
        a DROP-noise rule reachable beneath (ABNF ``cchar``'s ``htab``), the
        span is stitched the way the Earley fold walks it: terminal items
        contribute their raw slices, reference items the *kept* string values
        their subtrees reduced to — a DROP child left its sink empty, so its
        chars vanish from the yield exactly as on the engine path.

        :raises PdaFail: When a stitched child reduced to a non-string — a
            BUILD node under a YIELD span, a shape the stitch cannot express
            (defers to the Earley fold).
        """
        if not frame[F_CLONE].reduce_can_drop:
            return self.text[frame[F_START] : self.pos]
        arm = frame[F_ARM]
        ends = frame[F_ENDS]
        sinks = frame[F_SINKS]
        text = self.text
        parts: list[str] = []
        prev = frame[F_START]
        for i in range(arm.n):
            end = ends[i]
            if arm.kinds[i] <= OP_CC:  # terminal (LIT / CC) — raw slice
                parts.append(text[prev:end])
            else:  # ref / group / island — the subtree's kept strings
                sub = sinks[i] if sinks else None
                for value in sub or ():
                    if not isinstance(value, str):
                        raise PdaFail(
                            "reduce: non-string child under a YIELD span — "
                            "engine fallback"
                        )
                    parts.append(value)
            prev = end
        return "".join(parts)

    def _island(self, name: str, sink: list[object]) -> None:
        """Resolve an island reference on the reduce path: sub-parse, reduce, splice.

        The windowed Earley sub-parse over the island rule's tables — its
        conflict-free interior rules delegated to their reduce clones
        (:meth:`_delegates`) — reduces through the flavour's
        :class:`~lexic.parsing.earley.reduce.Reducer` (the same fold the
        whole-input engine path runs) to IR, spliced into the current children
        unless the island rule is DROP-noise.
        """
        run = self.reduce
        tree, end = self._island_subparse(name)
        reducer = run.reducer
        value = island_value(lambda: reducer.eval(reducer, tree, ()), name, self.pos)
        rid = run.name_to_rid.get(name)
        if (rid is None or run.plan.noise_kind[rid] != DROP_KIND) and value is not None:
            sink.append(value)
        self.pos += end

    def _delegate_run(
        self, clone: FlatClone, window_text: str, pos: int
    ) -> tuple[int, object] | None:
        """Run a delegable clone as a reduce sub-parse (the b1 delegate body).

        The reduce twin of :meth:`PdaKernel._delegate_run`: a fresh
        :class:`_ReducePdaKernel` drives ``clone`` to completion, its payload the
        reduced IR fragment the reducer splices straight through. Same fail-soft
        and window-edge rules.

        :param clone: The delegable rule's flat clone.
        :param window_text: The island window (the sub-parse's whole input).
        :param pos: The start position within ``window_text``.
        :returns: ``(end, reduced_ir)``, or ``None`` (declined).
        """
        sub = _ReducePdaKernel(self.tables, window_text)
        return finish_delegate(sub, clone, window_text, pos)


def parse_pda(tables: PdaTables, text: str, fold: ModelFold | None = None) -> object:
    """Parse ``text`` with the fused predictive runtime — model or reduce.

    On a reduce PDA (``tables.reduce`` set — the grammar-text path) the
    :class:`_ReducePdaKernel` drives the reducer's bodies and returns an
    ``IrAst``; otherwise :class:`PdaKernel` builds and returns a model.

    :param tables: The compiled predictive-parser tables.
    :param text: The input to parse.
    :param fold: The full-grammar fold for splicing island sub-models (model
        path only); ``None`` (the island-free path) makes any island reference
        raise :class:`PdaFail`.
    :returns: The start rule's model instance, or (reduce PDA) its ``IrAst``.
    :raises PdaFail: On any deterministic-parse failure (caught by the compile
        seam, which retries on the full engine).
    """
    if tables.reduce is not None:
        return _ReducePdaKernel(tables, text).run()
    return PdaKernel(tables, text, fold).run()
