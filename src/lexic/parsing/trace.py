"""The watched run — what the predictive kernel DID, as an ordered stream.

A parse leaves no account of itself. The fused runtime walks a flat program,
takes arms, probes boundaries, rolls back, and consumes text, and all that
survives is the model. This is the account: an ordered stream of events, each
one naming what the machine did, in which rule, with what verdict, and WHERE —
the where being an :class:`~lexic.ir.text.spans.IrSpan`, the same record an
emission's extents carry, so a trace row and a document occurrence point into
one text with one vocabulary and no translation between them.

**Pay to watch.** Watching is a RE-RUN — an execution of its own, never a
replay of an earlier parse, because the unwatched path keeps nothing to replay.
It pays nothing for this and is not asked to: :class:`WatchedKernel` is a
SUBCLASS, so the kernel's own methods are the ones an unwatched parse calls —
there is no flag on the hot loop, no branch in the driver, and nothing in
``pda/`` imports this module. The arrow proves the claim.

**A refused run is an account too.** The predictive machine failing is ordinary
— the compile seam catches it and retries on the gated engine — and it is
exactly the run worth watching. So a watched run does not raise: the refusal
becomes the stream's last event, in the engine's own words, and the product
says it did not derive.

**Capped, and it says so.** A pathological input can decide a great many times.
The stream stops recording at :data:`TRACE_CAP` events and the product says
``capped``; the parse itself is never truncated, and a run that fits under the
cap says that too.

**Where the events come from.** Every recording point is a seam the runtime
already calls once per decision or per descent — never the per-character op
dispatch, which is the paid loop. A ``scan`` is therefore the run of text
consumed between two decisions, attributed to the frame that consumed it,
rather than one event per literal: the driver matches an exactly-once terminal
inline with no call at all, and reading its span back out of the frame's own
``ENDS`` array (which the loop writes anyway) is what makes the account
complete without instrumenting it.
"""

from __future__ import annotations

from typing import Any, ClassVar, Self

from lexic.ir import IrNamedTuple, IrSeq, IrSpan
from lexic.parsing.earley.kernel.forest.support.ambiguity import Resolver
from lexic.parsing.fold import ModelFold
from lexic.parsing.pda.compiler.program.flatten import FlatArm, FlatClone
from lexic.parsing.pda.compiler.tables import PdaTables
from lexic.parsing.pda.core.errors import PdaFail
from lexic.parsing.pda.runtime.build import F_CLONE
from lexic.parsing.pda.runtime.kernel.kernel import PdaKernel

__all__ = [
    "SCAN",
    "PROBE",
    "ROLLBACK",
    "GATE",
    "TRACE_CAP",
    "TRACE_KINDS",
    "Trace",
    "TraceEvent",
    "WatchedKernel",
    "WatchedRun",
    "watch",
]

SCAN, PROBE, ROLLBACK, GATE = "scan", "probe", "rollback", "gate"

TRACE_KINDS: tuple[str, ...] = (SCAN, PROBE, ROLLBACK, GATE)
"""What a machine does, as four words: consume text, try a side speculatively,
give a tried side back, consult a gate the analysis decided."""

TRACE_CAP = 4096
"""Events one watched run records before it stops recording. The parse is never
cut short — only the account is, and then the product says ``capped``."""


class TraceEvent(IrNamedTuple[int, str, str, str, IrSpan]):
    """One thing the machine did.

    :ivar order: Its place in the stream, from zero. Order IS the content of a
        trace: two events are not comparable by anything else.
    :ivar kind: One of :data:`TRACE_KINDS`.
    :ivar rule: The rule whose clone was executing, or ``""`` for a frame the
        grammar never named (an inline group).
    :ivar verdict: What the machine decided, in its own words — the text a scan
        consumed, which side a probe ran, why a rollback gave it back, which
        gate was consulted and over what.
    :ivar span: Where in the document, in code units. A zero-width span is a
        decision taken AT a position rather than over one, which is what a
        probe and a gate are.
    """

    _child_attrs: ClassVar[tuple[str, ...]] = ("span",)
    order: int
    kind: str
    rule: str
    verdict: str
    span: IrSpan


class Trace(IrSeq[TraceEvent]):
    """One watched run's events, in the order the machine produced them."""

    def of_kind(self, kind: str) -> Self:
        """The events of one kind, order preserved.

        :param kind: One of :data:`TRACE_KINDS`.
        :returns: The sub-stream.
        """
        return type(self)(*(event for event in self if event.kind == kind))


class WatchedRun(IrNamedTuple[Trace, int, bool, bool]):
    """The account of one watched run — a re-run, and its two honest facts.

    It deliberately carries no model. A caller watching a parse already holds
    the model from the parse it is asking about; what this describes is a
    DIFFERENT execution of the same input, and handing back a second model
    would invite the two to be read as one.

    :ivar events: The ordered stream.
    :ivar cap: The recording ceiling this run ran under.
    :ivar capped: Whether it was reached. ``True`` means events are missing
        from the END of the stream, said rather than passed off as a complete
        account.
    :ivar derived: Whether the watched run reached a model. ``False`` is
        ordinary — the predictive machine refuses and the compile seam retries
        on the gated engine — and the refusal is the stream's last event.
    """

    _child_attrs: ClassVar[tuple[str, ...]] = ("events",)
    events: Trace
    cap: int
    capped: bool
    derived: bool


class WatchedKernel[M](PdaKernel[M]):
    """A kernel that keeps an account of its own run.

    Every override flushes the text consumed since the last event, then records
    what this seam is about, then delegates. The base class is untouched — an
    unwatched parse never constructs one of these and never executes a line of
    it.
    """

    __slots__ = ("events", "cap", "capped", "_scanned")

    events: list[TraceEvent]
    cap: int  # the recording ceiling — per-run state, set by `watch`
    capped: bool
    _scanned: int

    def __init__(
        self,
        tables: PdaTables,
        text: str,
        fold: ModelFold[M] | None = None,
        *,
        resolve: Resolver | None = None,
    ) -> None:
        """Prepare a watched parse — the base's construction, unchanged.

        The signature deliberately mirrors :class:`PdaKernel`'s: the recording
        ceiling is per-run state like the cursor, so :func:`watch` sets
        :attr:`cap` on the instance rather than the subclass growing a
        construction parameter its base does not have.

        :param tables: The compiled predictive-parser tables.
        :param text: The input to parse.
        :param fold: The full-grammar fold, for island splicing.
        :param resolve: The caller's answer to an ambiguous island.
        """
        super().__init__(tables, text, fold, resolve=resolve)
        self.events = []
        self.cap = TRACE_CAP
        self.capped = False
        self._scanned = 0

    # ── recording ─────────────────────────────────────────────────────

    def _note(self, kind: str, rule: str, verdict: str, span: IrSpan) -> None:
        """Record one event, or note that the cap stopped it."""
        if len(self.events) >= self.cap:
            self.capped = True
            return
        self.events.append(TraceEvent(len(self.events), kind, rule, verdict, span))

    def _here(self) -> str:
        """The rule whose frame is executing, or ``""`` at the top."""
        return str(self.stack[-1][F_CLONE].name) if self.stack else ""

    def _flush(self, rule: str = "") -> None:
        """Emit the text consumed since the last event as one scan.

        Coarser than one event per terminal, and deliberately: the driver
        matches an exactly-once literal inline with no call to intercept, so a
        per-terminal stream could only be built by instrumenting the paid loop.
        A run of text with no decision inside it is one scan.

        :param rule: The rule to attribute it to; the executing frame's by
            default.
        """
        if self.pos <= self._scanned:
            return
        span = IrSpan(self._scanned, self.pos)
        self._scanned = self.pos
        self._note(SCAN, rule or self._here(), span.of(self.text), span)

    def _at(self) -> IrSpan:
        """The zero-width span at the cursor — where a decision is taken."""
        return IrSpan(self.pos, self.pos)

    # ── the seams ─────────────────────────────────────────────────────

    def run(self) -> M:
        """Parse, keeping the account; the tail scan lands before returning."""
        product = super().run()
        self._flush()
        return product

    def watched_run(self) -> bool:
        """Run to a model or to a refusal, keeping the account either way.

        :returns: Whether the run derived. A refusal lands as the stream's last
            event, carrying the engine's words and the offset it stopped at.
        """
        try:
            self.run()
        except PdaFail as fail:
            self._flush()
            at = fail.pos if fail.pos >= 0 else self.pos
            self._note(ROLLBACK, str(fail.rule), str(fail), IrSpan(at, at))
            return False
        return True

    def _enter(self, clone: FlatClone, out: list[object]) -> bool:
        """Record the gate this entry consults, if it consults one."""
        self._flush()
        gate = _gate_of(clone)
        if gate:
            self._note(GATE, str(clone.name), gate, self._at())
        return super()._enter(clone, out)

    def _run_leaf(self, clone: FlatClone, out: list[Any], pos: int) -> int:
        """A leaf clone runs frame-lessly, so attribute its text to it."""
        self._flush()
        end = super()._run_leaf(clone, out, pos)
        saved, self.pos = self.pos, end
        self._flush(str(clone.name))
        self.pos = saved
        return end

    def _complete(self, frame: list[Any]) -> None:
        """A frame finishing is the last chance to attribute its own text."""
        self._flush(str(frame[F_CLONE].name))
        super()._complete(frame)

    def _attempt_run(self, sub: FlatClone, pos: int) -> tuple[int, list[object]] | None:
        """One attempt entry, tried and rolled back by construction."""
        self._flush()
        self._note(PROBE, str(sub.name), "attempt entry", IrSpan(pos, pos))
        scanned = self._scanned
        got = super()._attempt_run(sub, pos)
        self._scanned = scanned
        if got is None:
            self._note(ROLLBACK, str(sub.name), "did not derive", IrSpan(pos, pos))
        return got

    def _probe(
        self,
        arm: FlatArm,
        i: int,
        pos: int,
        taken: tuple[int, list[object]] | None,
    ) -> tuple[list[object] | None, bool]:
        """One side of a boundary, run to end-of-input on a copied stack."""
        self._flush()
        side = "stop side" if taken is None else "take side"
        rule = self._here()
        self._note(PROBE, rule, side, IrSpan(pos, pos))
        scanned = self._scanned
        done, uncertain = super()._probe(arm, i, pos, taken)
        self._scanned = scanned
        if done is None:
            self._note(ROLLBACK, rule, f"{side} did not derive", IrSpan(pos, pos))
        return done, uncertain


def _gate_of(clone: FlatClone) -> str:
    """Which gate this clone's entry consults, in words, or ``""`` for none.

    The plain FIRST-char selector is not one: it is the table read every entry
    does. A gate is what the analysis had to DECIDE — a bounded-lookahead
    window, a prefix negation, a structured-noise scan, or an attempt set whose
    arms are settled by running them.

    :param clone: The clone being entered.
    :returns: The gate's words, or ``""``.
    """
    if clone.attempt is not None:
        return f"attempt over {len(clone.attempt[1])} entries"
    if clone.kwin_selectors is not None:
        return f"k-window over {len(clone.kwin_selectors)} arms"
    if clone.pn_selectors is not None:
        return f"prefix negation over {len(clone.pn_selectors)} arms"
    if clone.struct_arm is not None:
        return "structured-noise scan"
    return ""


def watch[M](
    tables: PdaTables,
    text: str,
    fold: ModelFold[M] | None = None,
    *,
    cap: int = TRACE_CAP,
    resolve: Resolver | None = None,
) -> WatchedRun:
    """Parse ``text`` again, watched, and hand back what the machine did.

    A re-run by construction: this parses, it does not read back an earlier
    parse's account, because there is none to read — the unwatched path keeps
    nothing.

    :param tables: The compiled predictive-parser tables
        (:meth:`~lexic.compile.CompiledGrammar.pda_tables`).
    :param text: The input to parse.
    :param fold: The full-grammar fold, for island splicing.
    :param cap: How many events to record before the account stops.
    :param resolve: The caller's answer to an ambiguous island.
    :returns: The stream and the run's own facts. A refusal is an event, not
        an exception: the predictive machine failing is what the compile seam
        retries on the gated engine, and it is the run most worth watching.
    """
    kernel = WatchedKernel(tables, text, fold, resolve=resolve)
    kernel.cap = cap
    derived = kernel.watched_run()
    return WatchedRun(Trace(*kernel.events), cap, kernel.capped, derived)
