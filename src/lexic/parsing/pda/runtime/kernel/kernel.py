"""Fused predictive runtime — parses text to a model, no ParseTree on the path.

The runtime sibling of :class:`~lexic.parsing.earley.kernel.loop.kernel.Kernel`:
where the Earley kernel builds an SPPF a :class:`~lexic.parsing.fold.ModelFold`
later folds, :class:`PdaKernel` walks the flat int-coded
:class:`~lexic.parsing.pda.compiler.clones.PdaProgram` (``_OP_*`` op-codes,
pre-resolved ``(chars, negated)`` membership sets, direct :class:`FlatClone`
references — integer dispatch, no per-char method calls on the hot loop) and
builds the model **directly during the walk** — the fold is fused into the
parse, so no intermediate parse tree is allocated on the deterministic path.

**Explicit frame stack.** Rule, group and loop descent runs on an explicit
:attr:`PdaKernel.stack` of flat *list frames* (the ``kernel.py`` int-array
precedent) — never Python recursion. Per-parse state (input, cursor, stack)
lives on the kernel; the program is shared and immutable. A frame executes one
arm's items in order; a terminal item runs its whole quantifier loop inline in
:mod:`~lexic.parsing.pda.runtime.matchers`, while a rule reference or inline
group pushes a sub-frame per iteration.

**Fused capture.** A *clone frame* with a build-mode (``sequence`` /
``alternation`` / ``value_str``) captures what its fold needs and, on
completion, builds exactly one model (:meth:`PdaKernel._complete`); a
*transparent frame* funnels every model produced inside it straight to its
``F_OUT`` sink; a *discard frame* captures children locally and reports no
model. Item spans derive from the contiguous cursor via the frame's
``F_ENDS`` slot; descent sub-models collect per bound item in a lazily
allocated ``F_SINKS`` list, so a sub-model produced arbitrarily deep lands in
the nearest enclosing *bound* item's sink, exactly as the fold's look-through
``_models_at`` collects the topmost models under a kid. Per build-mode
(mirroring :meth:`~lexic.parsing.fold.ModelFold._fold_node`): ``value_str`` →
``ctor(value=text[a:b])`` over the clone's whole span; ``alternation`` →
pass-through of the first model under the matched arm; ``sequence`` → per
bound field, the item's span or its sub-model collection.
``discard`` performs recognition only and invokes no constructor.

**Islands.** A reference to a conflicted (island) rule cannot be walked
deterministically, so it delegates to a windowed Earley sub-parse
(:meth:`PdaKernel._island`): the longest completion over a doubling window
folds through the supplied fold and the sub-model splices into the current
capture; the cursor advances past the consumed span. Without a fold (the
island-free path) an island reference raises :class:`PdaFail`, as does a
**fail-island** reference (a semantic F1 stop-set-escape rule whose
longest-match split would silently diverge) — the compile seam then falls back
to the sound engine parse.

:class:`PdaFail` is internal to :mod:`lexic.parsing` — a PDA parse failure is
caught by the compile seam and retried on the full engine, which owns the
user-facing diagnostics. It never surfaces to the caller.
"""

from __future__ import annotations

from typing import Any

from lexic.ir import IrLeaf, IrSelf
from lexic.parsing.earley.kernel.forest.support.ambiguity import Resolver
from lexic.parsing.fold import ModelFold
from lexic.parsing.pda.compiler.program.flatten import (
    FlatArm,
    FlatClone,
    gate_take,
    select_gated,
)
from lexic.parsing.pda.compiler.program.opcodes import (
    BUILD_DISPATCH,
    BUILD_TRANSPARENT,
    GATE_ATTEMPT,
    GATE_STOP,
    OP_CC,
    OP_CC1,
    OP_FAIL,
    OP_GRP,
    OP_LEAF1,
    OP_LIT,
    OP_LIT1,
    OP_REF1,
    OP_VDISP,
    OP_VRUN,
    OP_VSTR,
)
from lexic.parsing.pda.compiler.tables import PdaTables
from lexic.parsing.pda.core.errors import PdaFail
from lexic.parsing.pda.core.scanner import scan_gate_take
from lexic.parsing.pda.runtime.admission import (
    KernelCaches,
    sole_admitted,
)
from lexic.parsing.pda.runtime.build import (
    F_ARM,
    F_COUNT,
    F_ENDS,
    F_I,
    F_MODE,
    F_OUT,
    F_SINKS,
)
from lexic.parsing.pda.runtime.islands import (
    IslandPolicy,
)
from lexic.parsing.pda.runtime.kernel.decisions import Attempting
from lexic.parsing.pda.runtime.kernel.execution import KernelExecutionMixin
from lexic.parsing.pda.runtime.matchers import (
    chase_dispatch,
    match_cc,
    match_lit,
)

__all__ = ["PdaFail", "PdaKernel", "pda_model"]

_EMPTY_SLOT: Any = None
"""An ``Any``-typed ``None`` — fills fresh per-item sink lists (``list[Any]``,
each slot later holding a sub-model list) without narrowing their type."""


class PdaKernel[M](KernelExecutionMixin, Attempting, IrLeaf[IrSelf, IrSelf]):
    """One predictive parse of ``text`` over a compiled :class:`PdaProgram`.

    Construct per parse, call :meth:`run` once; it returns the start clone's
    model. Per-parse state (:attr:`pos`, :attr:`stack`) is mutable on the
    kernel; :attr:`tables` is the shared, immutable compiled artifact.

    Generic in ``M``, the product the start clone folds to — the
    :class:`~lexic.parsing.fold.ModelFold` parameter's own type parameter, so
    a caller's model type rides through instead of decaying to ``object``.
    ``M`` is deliberately unbounded: :meth:`~lexic.ir.base.IrSelf
    .__init_subclass__` derives ``_bound`` from the last OWN type parameter
    only when that parameter carries one, so an unbounded ``M`` leaves the
    inherited ``_bound`` (``IrSelf``) intact.

    :ivar tables: The compiled predictive-parser tables (its
        :attr:`~lexic.parsing.pda.compiler.clones.PdaTables.program` is walked).
    :ivar text: The input string.
    :ivar pos: The cursor position (advances monotonically — no backtracking).
    :ivar stack: The explicit descent stack of flat frame lists (see the frame
        layout above).
    :ivar policy: The island policy this parse runs under — the full-grammar
        fold that splices island sub-models (``None`` on the island-free path,
        where an island reference raises :class:`PdaFail`) and whether an
        island may derive its text more than one way. The SAME record is handed
        to :func:`~lexic.parsing.pda.runtime.islands.island_parse`, with the
        per-island delegates filled in at the reference.
    :ivar _caches: The per-parse scratch (:class:`KernelCaches`) — the
        delegate-table and intern memos plus the stop-probe flag. Its lifetime
        is exactly one top-level kernel run: fresh per :class:`PdaKernel`
        (each island-interior delegate sub-run is a *separate* kernel with its
        own caches, so island sub-models — spliced by ``id`` — never share
        across the boundary).
    """

    __slots__ = ("tables", "text", "pos", "stack", "policy", "_caches")

    tables: PdaTables
    text: str
    pos: int
    stack: list[list[Any]]
    policy: IslandPolicy[M]
    _caches: KernelCaches

    def __init__(
        self,
        tables: PdaTables,
        text: str,
        fold: ModelFold[M] | None = None,
        *,
        resolve: Resolver | None = None,
    ) -> None:
        """Prepare a parse of ``text`` over ``tables``.

        :param tables: The compiled predictive-parser tables.
        :param text: The input to parse.
        :param fold: The full-grammar :class:`~lexic.parsing.fold.ModelFold`
            for splicing island sub-models; ``None`` disables island resolution
            (any island reference raises :class:`PdaFail`).
        :param resolve: The caller's deterministic answer to an island that
            derives its text two ways that mean different things; ``None``
            refuses one. Per-parse state, so it rides on the cursor.
        """
        self.tables = tables
        self.text = text
        self.policy = IslandPolicy(resolve=resolve, fold=fold)
        self.pos = 0
        self.stack = []
        self._caches = KernelCaches()

    # ── the driver ────────────────────────────────────────────────────

    def run(self) -> M:
        """Parse the whole input and return the start clone's model.

        :returns: The model instance the start rule folds to, typed ``M``.
        :raises PdaFail: On any deterministic-parse failure — a terminal
            mismatch, no viable arm, an unresolved island reference, trailing
            input, or a start rule that is itself an island (the whole-grammar
            opt-out the compile seam reads).
        """
        start = self.tables.program.start
        if not isinstance(start, FlatClone):  # IslandRef opt-out
            raise PdaFail(f"start rule {start.name!r} is an island — no PDA")
        holder: list[Any] = []
        self._enter(start, holder)
        self._drive()
        if self.pos != len(self.text):
            raise PdaFail(f"trailing input at {self.pos}", self.pos)
        if not holder:
            raise PdaFail("start rule produced no model")
        return holder[0]

    def prefix_run(self, clone: FlatClone, pos: int) -> tuple[int, object]:
        """Drive a self-contained sub-run of ``clone`` from ``pos`` — the
        island-interior delegation entry seam (Task 6.2, D-a).

        Initialises a *fresh* descent stack at ``clone`` and ``pos`` and drives
        until that clone's own frame completes — its subtree drains the fresh
        stack, so completion is detected by the stack returning to empty, not by
        end-of-input. Unlike :meth:`run` there is **no** trailing-input / EOF
        check: the caller (an island Earley predictor) files a completed span of
        length ``end`` and consumes only that far. The sub-run is exactly the
        entry mode :func:`pda_model` already trusts, just anchored at an
        arbitrary clone and position instead of the start clone at ``0``.

        Nested islands beneath ``clone`` resolve through the usual
        :meth:`_island` path (the shared cursor's ``fold`` / ``tables`` are
        untouched).

        :param clone: The delegable clone to run (never an island rule).
        :param pos: The start cursor position in :attr:`text`.
        :returns: ``(end, payload)`` — the position just past the clone's match
            and the model it produced (``None`` when the clone builds nothing,
            e.g. a nullable empty arm).
        :raises PdaFail: On any deterministic-parse failure inside the sub-run;
            the delegate wrapper catches it and falls through to prediction.
        """
        saved_stack, saved_pos = self.stack, self.pos
        self.stack = []
        self.pos = pos
        try:
            holder: list[object] = []
            self._enter(clone, holder)
            self._drive()
            end = self.pos
        finally:
            self.stack, self.pos = saved_stack, saved_pos
        return end, (holder[0] if holder else None)

    def _drive(self, floor: int = 0, limit: int = -1) -> None:
        """Drain the frame stack — the fused hot loop.

        With ``limit`` >= 0 the drive RETURNS as soon as the cursor reaches it,
        leaving the stack resumable: a later call continues where this one
        stopped. It is a PARAMETER and not a cursor field on purpose — the
        bound belongs to one call, and a nested drive (an attempt sub-run
        re-entering the driver) must be unbounded. Carried on the cursor it
        leaked into those sub-runs, which then stopped early and never
        converged; measured, that put every boundary back on the slow path.
        It folds into the OUTER loop's own condition, so the hot path gains no
        branch — and a
        frame boundary is exactly where ``self.pos`` and ``frame[F_I]`` are
        both current, which is what makes the pause resumable at all. Used by
        the lockstep boundary verdict, which advances two candidate
        continuations in step instead of running each to end-of-input.

        The outer loop processes the top frame; the inner loop runs its items
        in order. A terminal item matches its whole quantifier loop inline (no
        descent, no per-char call; the exactly-once ``OP_CC1``/``OP_LIT1``
        specialisations skip even the helper call); an ``OP_VSTR`` item runs
        its whole terminal-only ``value_str`` loop frame-lessly; an
        ``OP_REF1`` item (an exactly-once entry in an ends-free arm) advances
        past itself before descending, so its resume needs no re-check. Any
        other quantified atom steps through :meth:`_quant_step` — descend,
        inline splice, or loop close. A frame whose items run out (the
        ``while``'s ``else``) completes.
        """
        stack = self.stack
        text = self.text
        while len(stack) > floor and not 0 <= limit <= self.pos:
            frame = stack[-1]
            arm = frame[F_ARM]
            kinds = arm.kinds
            n = arm.n
            i = frame[F_I]
            pos = self.pos
            while i < n:
                k = kinds[i]
                if k == OP_CC1:
                    payload = arm.payloads[i]
                    char = text[pos : pos + 1]
                    if (
                        (char == "" or char in payload[0])
                        if payload[1]
                        else (char not in payload[0])
                    ):
                        raise PdaFail(f"char class miss at {pos}", pos)
                    pos += 1
                elif k == OP_LIT1:
                    lit = arm.payloads[i]
                    if not text.startswith(lit, pos):
                        raise PdaFail(f"expected {lit!r} at {pos}", pos)
                    pos += len(lit)
                elif k == OP_REF1:
                    frame[F_I] = i + 1
                    self.pos = pos
                    if self._enter(arm.payloads[i], self._sink_for(frame, arm, i)):
                        break  # pushed — the sub-frame drives next
                    pos = self.pos  # consumed inline — this item is done
                    i += 1
                    continue
                elif k == OP_VSTR or k >= OP_VRUN or k <= OP_CC:  # span-producing
                    pos = self._match_span(frame, arm, i, pos)
                else:  # OP_REF / OP_GRP / OP_ISLAND / OP_FAIL
                    i = self._quant_step(frame, arm, i, pos)
                    if i < 0:
                        break  # pushed — the sub-frame drives next
                    pos = self.pos
                    continue
                frame[F_ENDS][i] = pos
                i += 1
            else:  # items exhausted without a descent — the frame completes
                frame[F_I] = i
                self.pos = pos
                self._complete(frame)

    def _quant_step(self, frame: list[Any], arm: FlatArm, i: int, pos: int) -> int:
        """One step of a quantified atom's loop — descend, splice, or close.

        Consults the mandatory count then the loop gate; a due iteration
        descends (a clone entry pushes a frame; an island splices inline; a
        fail-island raises), a closed loop records the item's end and moves on.
        ``self.pos`` is left current in every non-pushing outcome.

        :returns: ``-1`` when a sub-frame was pushed; otherwise the item index
            the driver continues at (``i`` mid-loop, ``i + 1`` when closed).
        :raises PdaFail: On a fail-island reference, an island reference with
            no fold, or a mandatory iteration with no viable arm.
        """
        count = frame[F_COUNT]
        if count < arm.los[i]:
            need = True
        else:
            hi = arm.his[i]
            gk = arm.gate_kinds[i]
            need = False
            if hi < 0 or count < hi:
                if gk == GATE_ATTEMPT:
                    frame[F_I] = i
                    self.pos = pos
                    return self.attempt_iteration(frame, arm, i, pos)
                if gk == GATE_STOP:
                    # The hot gate, membership kept inline — the same reading
                    # `match_cc` keeps for its own loop. A descent iteration is
                    # not rare enough to pay a call for a set lookup.
                    char = self.text[pos : pos + 1]
                    chars, negated = arm.gate_data[i]
                    need = (
                        (char != "" and char not in chars) if negated else char in chars
                    )
                else:
                    need = gate_take(self.text, pos, gk, arm.gate_data[i])
        if not need:
            frame[F_COUNT] = 0
            frame[F_I] = i + 1
            frame[F_ENDS][i] = pos
            self.pos = pos
            return i + 1
        frame[F_COUNT] = count + 1
        frame[F_I] = i
        self.pos = pos
        k = arm.kinds[i]
        # The REPEAT descent's sink, read in place — `_sink_for` is the driver's
        # densest call (1.28 per character of arithmetic corpus) and its answer
        # is a list index once the frame's sink array exists. A frame whose
        # array is still absent (its first descent, or a transparent frame,
        # which never grows one) takes the call and its full protocol.
        sinks = frame[F_SINKS]
        if sinks is None:
            sink = self._sink_for(frame, arm, i)
        else:
            sink = sinks[i]
            if sink is None:
                sinks[i] = sink = []
        if k <= OP_GRP:  # OP_REF / OP_GRP — a clone entry
            if self._enter(arm.payloads[i], sink):
                return -1
            return i  # consumed inline — same item continues
        return self._descend_island(arm, i, pos, sink)

    def _descend_island(self, arm: FlatArm, i: int, pos: int, sink: list[Any]) -> int:
        """A due ``OP_ISLAND`` splice or ``OP_FAIL`` raise — the descent's cold tail.

        Hosted out of :meth:`_quant_step` because it never runs: an island is
        the residue no attempt can settle, and none survives on any grammar the
        engine has been measured against (zero ``OP_ISLAND`` and zero
        ``OP_FAIL`` steps across the whole benchmark). The hot path keeps the
        branch budget instead.
        """
        if arm.kinds[i] == OP_FAIL:
            raise PdaFail(
                f"fail-island {arm.payloads[i]!r} at {pos}: "
                "F1 semantic escape, engine fallback",
                pos,
            )
        self._island(arm.payloads[i], sink)  # OP_ISLAND — spliced inline
        return i

    # ── terminal matching (whole quantifier loop, inline, no per-char call) ─

    def _match_span(self, frame: list[Any], arm: FlatArm, i: int, pos: int) -> int:
        """Match a span-producing item — a ``value_str`` ref or a quantified
        literal / char class — routing to its matcher (the cold-ish tail of the
        driver's op dispatch; the exactly-once terminals stay inline)."""
        k = arm.kinds[i]
        if k == OP_LEAF1:
            return self._run_leaf(arm.payloads[i], self._sink_for(frame, arm, i), pos)
        if k == OP_VDISP:
            return self._match_vdisp(self._sink_for(frame, arm, i), arm, i, pos)
        if k == OP_VSTR or k >= OP_VRUN:
            # A tabled reference's specialisation is the LEAF walk's; reached
            # through a frame, it runs the ordinary loop (one iteration of it).
            if frame[F_MODE] == BUILD_TRANSPARENT:  # `_sink_for`, read in place
                sink = frame[F_OUT]
            else:
                sinks = frame[F_SINKS]
                if sinks is None:
                    frame[F_SINKS] = sinks = [_EMPTY_SLOT] * arm.n
                sink = sinks[i]
                if sink is None:
                    sinks[i] = sink = []
            return self._match_vstr(sink, arm, i, pos)
        if k == OP_LIT:
            return match_lit(self.text, arm, i, pos)
        return match_cc(self.text, arm, i, pos)

    # ── descent ────────────────────────────────────────────────────────

    def _sink_for(self, frame: list[Any], arm: FlatArm, i: int) -> list[Any]:
        """The sink item ``i``'s sub-models report into (allocated lazily).

        A transparent frame funnels everything to its parent sink; a capture
        frame collects per item in :attr:`_Frame.sinks`.
        """
        if frame[F_MODE] == BUILD_TRANSPARENT:
            return frame[F_OUT]
        sinks = frame[F_SINKS]
        if sinks is None:
            frame[F_SINKS] = sinks = [_EMPTY_SLOT] * arm.n
        sink = sinks[i]
        if sink is None:
            sinks[i] = sink = []
        return sink

    def _chase_dispatch(self, clone: FlatClone, char: str) -> "FlatClone | None":
        """Chase a frame-less dispatch alternation to its concrete target clone.

        :param clone: A :data:`~lexic.parsing.pda.compiler.program.flatten.BUILD_DISPATCH` clone.
        :param char: The lookahead char selecting each dispatch step.
        :returns: The concrete target clone, or ``None`` when the dispatch lands
            on its empty (nullable) arm (the caller then consumes nothing).
        :raises PdaFail: When no selector matches and there is no default.
        """
        return chase_dispatch(clone, char, self.pos)

    def _enter(self, clone: FlatClone, out: list[object]) -> bool:
        """Select ``clone``'s arm at the cursor and push its (flat) frame.

                A dispatch clone (a frame-less pass-through alternation) is chased
                first: its selectors carry target clones, so the walk lands on the
                concrete clone — reporting into the same ``out`` the alternation would
        have passed through to — before any frame is pushed. A leaf clone then
        runs frame-lessly in :meth:`_run_leaf`.

        A chase is taken straight here; only an ATTEMPT landing needs
        :meth:`_settle`'s fixpoint, because a substitution can install another
        dispatch clone. Chasing through the fixpoint unconditionally cost a
        second call on every dispatch entry, and on five of six bench grammars
        every one of them was a chase with no attempt anywhere in sight.

        :param clone: The clone (or inline group) to descend into.
        :param out: The parent sink list the clone's model reports into.
        :returns: ``True`` when a frame was pushed; ``False`` when the clone
            was consumed inline (a leaf run, or a dispatch clone's empty arm).
        :raises PdaFail: When no arm's FIRST matches and there is no default.
        """
        char = self.text[self.pos : self.pos + 1]
        if clone.mode == BUILD_DISPATCH:
            # The common substitution, taken straight: a chase alone needs no
            # fixpoint, and on five of six bench grammars EVERY dispatch entry
            # reached _settle only to chase. The fixpoint is still there for the
            # chains that need it — an attempt landing installs another clone.
            chased = chase_dispatch(clone, char, self.pos)
            if chased is None:
                return False  # the empty (nullable) arm — nothing consumed
            clone = chased
        if clone.attempt is not None:
            # Most entries resolve to themselves; pay the call only when one of
            # the two substituting shapes is actually present (measured: the
            # unconditional call cost 1-3% on every grammar).
            settled = self._settle(clone, char, out)
            if settled is None:
                return False  # consumed inline — empty arm, or an attempt run
            clone = settled
        if (
            clone.kwin_selectors is not None
            or clone.pn_selectors is not None
            or clone.struct_arm is not None
        ) and self._enter_gated(clone, out):
            return True  # short-circuits: an ungated clone never pays the call
        if clone.leaf:
            self._leaf_run(clone, out)
            return False
        arm = None
        for chars, negated, candidate in clone.selectors:
            if (char != "" and char not in chars) if negated else char in chars:
                arm = candidate
                break
        if arm is None:
            arm = clone.default
            if arm is None:
                raise PdaFail(f"no arm at {self.pos}", self.pos)
        # frame layout: arm, i, count, out, mode, clone, start, ends, sinks
        # ``ends`` is per-frame so the driver's per-item span write stays
        # unconditional (only span-reading sequence clones ever read it back).
        self.stack.append(
            [arm, 0, 0, out, clone.mode, clone, self.pos, [0] * arm.n, None]
        )
        return True

    def _enter_gated(self, clone: FlatClone, out: list[object]) -> bool:
        """Push the frame of a clone that selects its arm by something other
        than the lead char, or report that it does not.

        The two cold selections, together because they share that property: a
        ``k``-window / post-noise-peek clone picks its arm by
        :func:`~lexic.parsing.pda.compiler.program.flatten.select_gated`, and a
        struct-gated clone whose gate REFUSES takes its escape (default) arm. A
        struct gate that takes falls through to the ordinary lead-char path.

        :returns: ``True`` when a frame was pushed, ``False`` to continue.
        :raises PdaFail: When a refusing struct gate has no escape arm.
        """
        if clone.kwin_selectors is not None or clone.pn_selectors is not None:
            gated = select_gated(self.text, self.pos, clone)
            self.stack.append(
                [gated, 0, 0, out, clone.mode, clone, self.pos, [0] * gated.n, None]
            )
            return True
        if scan_gate_take(self.text, self.pos, clone.struct_arm):
            return False  # the gate takes — the lead char selects as usual
        arm = clone.default
        if arm is None:
            raise PdaFail(f"no arm at {self.pos}", self.pos)
        self.stack.append(
            [arm, 0, 0, out, clone.mode, clone, self.pos, [0] * arm.n, None]
        )
        return True

    def _settle(
        self, clone: FlatClone, char: str, out: list[object]
    ) -> "FlatClone | None":
        """Resolve dispatch chases and attempt substitutions to a fixpoint.

        Either step installs a *different* clone, and the clone it installs has
        not been through the tests above it: a chase yields the selected
        target, an attempt substitution yields the sole admitted entry. Run as
        straight-line tests each check happens at most once, in one order, and
        a substituted clone reaches the caller's arm selection carrying
        whatever specialisation it has — which is a crash when that
        specialisation is dispatch, whose selectors hold clones where the frame
        push expects a :class:`FlatArm`. Attempt → dispatch → attempt chains are
        the normal case rather than a corner: on the vyx grammar they run to 30
        hops.

        **It terminates.** Every hop follows a FIRST-position reference edge — a
        dispatch selector and an attempt entry both name what may *begin* the
        span — and a cycle of first-position references is left recursion, which
        the analysis refuses before any clone is built. Every chain is therefore
        bounded by the depth of an acyclic FIRST graph.

        :param clone: The clone to resolve.
        :param char: The lookahead, for the dispatch selectors.
        :param out: The parent sink, for an attempt run's inline consumption.
        :returns: The clone the caller should enter, or ``None`` when the walk
            was consumed inline (a dispatch clone's empty arm, or an attempt
            whose winning arm ran as a sub-run).
        """
        while True:
            if clone.mode == BUILD_DISPATCH:
                chased = self._chase_dispatch(clone, char)
                if chased is None:
                    return None  # the empty (nullable) arm — nothing consumed
                clone = chased
                continue
            if clone.attempt is not None:
                sole = sole_admitted(clone.attempt[1], self.text, self.pos)
                if sole is None:
                    self.attempt(clone, out)
                    return None  # the winning arm was consumed inline
                clone = sole  # one admitted entry — no fork is possible: a
                # plain frame push replaces the sub-run, and the audit has
                # nothing to ask
                continue
            return clone


def pda_model[M](
    tables: PdaTables,
    text: str,
    fold: ModelFold[M] | None = None,
    *,
    resolve: Resolver | None = None,
) -> M:
    """Parse ``text`` with the predictive runtime and build its model.

    :param tables: The compiled predictive-parser tables.
    :param text: The input to parse.
    :param fold: The full-grammar fold used by island sub-parses; ``None``
        makes any island reference raise :class:`PdaFail`.
    :param resolve: A deterministic ambiguity resolver for island parses.
    :returns: The start rule's model instance.
    :raises PdaFail: When the deterministic path cannot complete.
    """
    return PdaKernel(tables, text, fold, resolve=resolve).run()
