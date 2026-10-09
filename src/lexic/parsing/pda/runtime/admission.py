"""Attempt-seam leaves — the admission test, the kernel scratch, the stack copy.

Shed from :mod:`lexic.parsing.pda.runtime.kernel.kernel` for the reason every leaf in
this package is shed: these take only plain values and frame lists, never the
``PdaKernel`` cursor, so ``runtime`` imports them and not the reverse. The
attempt/probe DRIVERS stay methods — their group writes the cursor's own state
(the ``PdaKernel._island`` precedent).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, NamedTuple

from lexic.exceptions import EngineInvariantError
from lexic.ir import IrLeaf, IrSelf
from lexic.parsing.earley.kernel.loop.kernel import Delegate
from lexic.parsing.pda.compiler.program.flatten import FlatClone
from lexic.parsing.pda.compiler.program.opcodes import (
    BUILD_FOLD,
)
from lexic.parsing.pda.runtime.build import (
    Frame,
    InternMemo,
)

__all__ = [
    "NESTING_DEPTH",
    "NO_ROUTE",
    "PARSE_NESTING",
    "RunScope",
    "Audit",
    "Floor",
    "RouteLane",
    "Side",
    "control_signature",
    "pending_values",
    "value_shape",
    "KernelCaches",
    "admits",
    "composes",
    "frames_copy",
    "sole_admitted",
]

NO_ROUTE = -1
"""No route is waiting here. A plain int rather than ``None`` so a routed
consumer's read stays one comparison against the dense route ids."""

type Floor = tuple[
    int,
    int,
    list[Any],
    list[Any],
    Frame | None,
    tuple[FlatClone, list[Any], int, tuple[int, list[Any]] | None] | None,
]
"""One attempt sub-run a boundary side was forked inside, as the side settles it.

``(depth, start, holder, live, loop, entry)``: the depth of the sub-run's root
frame; where it began; the side's list its root reports into; the live list's
prefix those values follow; and its caller — ``loop``, the side's frame whose
attempted iteration it is, or ``entry``, the attempt clone, the side's list
the winner splices into, the entry's index and — for an entry the attempt is
AUDITING — the winner's ``(end, values)``. Exactly one caller is set."""

type Audit = tuple[int, Any, int, int, tuple[int, list[Any]]]
"""One audit run in flight, as a fork inside it needs it: ``(depth, clone,
entry, pos, won)`` — the depth its sub-run roots at, the attempt clone, the
entry it runs, the attempt position and the winner's ``(end, values)``."""

type Side = tuple[
    list[Any],
    int,
    "RouteLane | None",
    list[Any],
    list[Floor],
    list[int] | None,
    Sequence[Frame],
    tuple[int, int] | tuple[()],
]
"""One resumable boundary side: its forked stack, its position, its route lane,
its root output, the attempt sub-runs it is still inside, its ledger — where
each frame the fork copied completed, by depth — and the copies themselves,
which keep where their items end, both kept only by a side built to record
them; and the fork's own step when it is no loop boundary's (the top frame's
item it stands in, and where that ends; empty at a loop boundary).

A UNIFORM shape. The lane slot is ``None`` for every program without route
continuations rather than the tuple changing arity by product, so the
boundary-decision path stays one shape and one call signature whatever is
being parsed. The root output is held apart from the stack because a side that
completes has emptied it."""


def admits(char: str, chars: Any, negated: Any) -> bool:
    """Whether an attempt entry's FIRST pre-filter admits the lookahead.

    ``chars is None`` is the nullable default entry — always admitted.
    """
    if chars is None:
        return True
    return (char != "" and char not in chars) if negated else char in chars


def sole_admitted(entries: tuple[Any, ...], text: str, pos: int) -> Any:
    """The single admitted entry's clone, or ``None`` when several admit.

    Admission is the first-char pre-filter AND the leading-prefix pattern
    (one C-level match per candidate) AND the arm's FIRST_k window — most
    overlapping-FIRST decisions collapse to a single survivor at their
    discriminator, and a sole survivor has no fork to audit and no rollback
    to arm: the runtime enters it as an ordinary clone (frame push) instead
    of a sub-run.
    """
    char = text[pos : pos + 1]
    sole = None
    for chars, negated, prefix, window, sub in entries:
        # `admits` read in place — this scan is the densest call site in the
        # engine (1.72 per character of vyx corpus), and the test is a set
        # membership either way.
        if chars is not None and (
            (char == "" or char in chars) if negated else (char not in chars)
        ):
            continue
        if prefix is not None and prefix.match(text, pos) is None:
            continue
        if window is not None and window.match(text, pos) is None:
            continue
        if sole is not None:
            return None
        sole = sub
    return sole


def composes(follow: Any, text: str, end: int) -> bool:
    """Whether an arm ending at ``end`` can be extended in ANY context.

    The rule's soft FOLLOW over-approximates what may come next, so a next
    character outside it proves this reading dead wherever the rule is used.
    End of input composes: nothing follows, and a rule that may end the parse
    carries the sentinel rather than a character.
    """
    return end >= len(text) or follow.has(text[end : end + 1])


PARSE_NESTING = 256
"""How many nested verdicts one parse may ask over all its retries, delegate
sub-runs' included: each costs a drive to the end of the input, and past it a
forked verdict goes to the gated engine as without a retry. The most any of
4,181 documents asked is 117 (decision families, ground truth, 200 generated
vyx documents, the roster)."""


class RunScope:
    """Where one kernel's run stands in its parse: the nested verdicts its
    retry may still ask, the parse's allowance — shared with the delegate
    sub-runs the parse starts — and whether its text and root are the
    document's.

    :ivar retry: How many nested verdicts the retry being asked may still run;
        ``0`` outside a retry (no boundary inside a side forks).
    :ivar root: The parse's own scope, whose ``left`` is the allowance.
    :ivar left: What is left of the allowance; a delegate's is never read.
    :ivar cut: Whether the run reads a truncated text, whose end is not the
        document's.
    """

    __slots__ = ("cut", "left", "retry", "root")

    cut: bool
    left: int
    retry: int
    root: RunScope

    def __init__(self, root: RunScope | None = None) -> None:
        """A kernel outside any retry, drawing on ``root``'s allowance — a
        fresh one (:data:`PARSE_NESTING`) for a parse of its own."""
        self.cut = False
        self.left = PARSE_NESTING if root is None else 0
        self.retry = 0
        self.root = self if root is None else root

    def whole(self) -> bool:
        """Whether the text is the whole document and the stack's root its
        root: not a delegate's run, whose root may end anywhere in a window,
        nor a run over a truncated text. Only then may a stop side be refuted
        against the text (:func:`~...matchers.stop_side_dead`)."""
        return self.root is self and not self.cut

    def open(self, most: int) -> bool:
        """Start a retry with up to ``most`` of the allowance; whether any was
        left."""
        root = self.root
        self.retry = min(most, root.left)
        root.left -= self.retry
        return self.retry > 0

    def close(self) -> None:
        """End the retry, giving back what it did not ask."""
        self.root.left += self.retry
        self.retry = 0

    def take(self) -> bool:
        """Spend one of the retry's nested verdicts, if it has one left."""
        if not self.retry:
            return False
        self.retry -= 1
        return True


class KernelCaches[Carry](IrLeaf[IrSelf, IrSelf]):
    """One kernel run's scratch — the memos and the stop-probe depth.

    :ivar deleg: Island name → its wrapped interior delegate table.
    :ivar intern: The sub-model intern memo (repeated identical sub-models
        built once and shared within one run).
    :ivar probing: How many probes are live. Non-zero means a boundary is
        resolved GREEDILY by class rather than by forking again, unless a
        forked verdict asked again nests a verdict there (``scope``). A
        counter rather than a flag because :meth:`_advance` counts its own
        drive too, and the nesting depth is read off it.
    :ivar audits: The audit runs in flight, innermost last — one record per
        audited entry run, pushed around it, read only by a fork inside one.
    :ivar uncertain: Set when a probe's drive resolved a both-viable
        boundary GREEDILY (forks nest one level, and only by convergence —
        the exponential chain of a rules-list grammar probing every later
        line is cut to one linear drive); the probe's outcome is then a
        SAMPLED path, and the outer verdict treats it conservatively — an
        uncertain outcome on a decisive side reads as a fork, which is a
        fallback, never a wrong commit.
    :ivar side: The side being driven, or ``None`` outside a side's drive —
        what a fork inside it copies its unsettled sub-runs and root from.
    :ivar scope: Where this kernel's run stands in its parse (:class:`RunScope`)
        — its retry's nested verdicts, the allowance, whether it is whole.
    """

    __slots__ = (
        "audits",
        "deleg",
        "intern",
        "probing",
        "scope",
        "side",
        "uncertain",
    )

    audits: list[Audit]
    deleg: dict[str, dict[int, Delegate]]
    intern: InternMemo[Carry]
    probing: int
    scope: RunScope
    side: Side | None
    uncertain: bool

    def __init__(self, scope: RunScope | None = None) -> None:
        """Seed the memos empty, the probe depth zero, certainty clean, and the
        run's scope — one inside ``scope``'s parse when a parse runs this
        kernel inside it."""
        self.audits = []
        self.deleg = {}
        self.intern = {}
        self.scope = RunScope(None if scope is None else scope.root)
        self.probing = 0
        self.side = None
        self.uncertain = False


NESTING_DEPTH = 16
"""How many forks deep a stack copy may already be, and so how many sides deep
a retried verdict nests one of its own (:meth:`~...verdicts.Verdicts._nests`).

A STACK bound, not a cost one: the retry's budget of nested verdicts bounds the
cost, while each level costs some twelve interpreter frames, so sixteen stay
far inside the recursion limit. Measured on the decision families: four
levels keep every rejection the engine made unnested, and none past six
settles anything more."""


def frames_copy[Carry](
    stack: list[Frame[Carry]],
    every_end: bool = False,
    remap: dict[int, list[Any]] | None = None,
) -> list[Frame[Carry]]:
    """A structural copy of the frame stack, aliasing topology preserved.

    Frames alias each other: a frame's ``out`` IS the run holder, a parent's
    per-item sink list, or (through a transparent frame) an ancestor's — so a
    plain per-frame copy would break the funnels. Every container is mapped
    once via an identity map and every reference re-resolved through it, so a
    list two frames share is one list on the far side too.

    **The containers fork EMPTY.** A fork needs the values it BUILDS; the
    prefix it inherited is common to every side by construction, which is the
    same fact :func:`pending_values` relies on to compare deltas rather than
    whole states. Copying that prefix made a linear number of forks each copy
    a linearly-growing sink — and it is a prefix almost nothing goes on to
    read, so the work was quadratic in the fork count and wasted besides. On a
    256 KB gbnf-meta document the copies moved 407 M list elements, of which
    the builds read 14,632 back. That is what the eighth
    :class:`~lexic.parsing.pda.runtime.build.Frame` slot buys: ``inherited``
    costs one pointer per frame and removes the copy entirely.

    Each copy keeps a reference to the frame it came from
    (:attr:`~lexic.parsing.pda.runtime.build.Frame.inherited`) and takes the
    prefix back — by copying it in front of its own values, never by writing
    through the original — at the one moment it is read, which is its build.
    Two live universes therefore still append only to their own lists.

    :param stack: The stack to copy.
    :param every_end: Give every copy an ``ends`` of its own, kept or not —
        what a side the rank reads needs.
    :param remap: Filled with each original container's copy, by ``id``, for
        a caller that must find the copies of lists it holds off the stack.
    """
    # The ROOT frame, because it is never popped before the drive reaches end
    # of input; the top frame is fresh and would prove nothing. Raised rather
    # than asserted because `-O` strips asserts and a nested fork builds a
    # SHORT model silently; the class says why it is outside the LexicError
    # family. See `invariants.md`.
    depth, origin = 0, stack[0].inherited if stack else None
    while origin is not None:
        depth += 1
        origin = origin.inherited
    if depth > NESTING_DEPTH:
        raise EngineInvariantError(
            f"frames_copy: a fork {depth + 1} deep — forks nest "
            f"{NESTING_DEPTH} levels at most"
        )
    if remap is None:
        remap = {}
    copies: list[Frame[Carry]] = []
    for frame in stack:
        new = Frame(frame.arm, _fork(frame.out, remap), frame.clone, 0)
        new.i = frame.i
        new.count = frame.count
        new.inherited = frame
        # `ends` is written by INDEX (``ends[i + 1] = pos``) and is fixed at
        # ``arm.n + 1``, so it neither grows with the document nor survives
        # being started empty. Copied whole, for a constant. With `every_end`
        # a copy of a frame that keeps none gets its own, so a side records
        # where its items end for the verdict's rank, starting at ``-1`` where
        # the span start stood.
        ends = frame.ends
        if ends is not None:
            new.ends = _dup(ends, remap)
        elif every_end:
            new.ends = [-1] * (frame.arm.n + 1)
        sinks = frame.sinks
        if sinks is not None:
            new.sinks = [slot if slot is None else _fork(slot, remap) for slot in sinks]
        copies.append(new)
    return copies


class _Published(NamedTuple):
    """One route waiting in a parent frame for the child that reads it.

    :ivar frame: The publishing frame ITSELF, not its depth. Depth alone
        aliases: a later frame arriving at the same depth would inherit a
        route published for the one before it.
    :ivar path: The descendant slot chain from this frame to the consumer.
        A one-element path is the sibling case; a longer one is why routing
        does not depend on the producer and consumer being adjacent.
    :ivar route: The dense route id the consumer enters on.
    """

    frame: Frame
    path: tuple[int, ...]
    route: int


class RouteLane:
    """Where a producer's route waits between publication and consumption.

    Cursor-side rather than a frame slot: a frame is one program-independent
    flat list, so widening it would tax every product's every frame push —
    including the generated-model product, which routes nothing, ever. This
    lives on the kernel instead and is ``None`` there for any program without
    route continuations, so the unrouted path pays one attribute and one test
    at a fork.

    Two independent guards keep a route from reaching the wrong occurrence,
    because they catch different mistakes:

    - **The frame identity** stops a LATER frame at the same depth reading a
      route published by one that has since popped.
    - **Clearing on advance** stops a later SIBLING under the same live parent
      reading a route the first routed child already consumed.

    Neither subsumes the other: the first leaves the parent alive, the second
    replaces it.
    """

    __slots__ = ("_table",)

    def __init__(self, table: dict[int, _Published] | None = None) -> None:
        """Open an empty lane, or adopt an already-remapped table."""
        self._table: dict[int, _Published] = {} if table is None else table

    def publish(
        self, depth: int, frame: Frame, path: tuple[int, ...], route: int
    ) -> None:
        """Record the route ``frame`` just classified, for its descendant."""
        self._table[depth] = _Published(frame, path, route)

    def route_at(self, depth: int, frame: Frame) -> int:
        """The route waiting in ``frame``, or :data:`NO_ROUTE`.

        :param depth: Where the publishing frame sits.
        :param frame: The frame the caller believes published it — checked by
            identity, so a recycled depth cannot serve a stale route.
        :returns: The dense route id, or :data:`NO_ROUTE`.
        """
        found = self._table.get(depth)
        if found is None or found.frame is not frame:
            return NO_ROUTE
        return found.route

    def path_at(self, depth: int, frame: Frame) -> tuple[int, ...]:
        """The consumer path waiting in ``frame``, empty when none is."""
        found = self._table.get(depth)
        if found is None or found.frame is not frame:
            return ()
        return found.path

    def clear(self, depth: int) -> None:
        """Drop the route at ``depth`` — its routed occurrence has advanced."""
        self._table.pop(depth, None)

    def discard_above(self, depth: int) -> None:
        """Drop everything published deeper than ``depth``.

        An abandoned attempt runs ON the live stack under a depth watermark
        rather than on a discarded copy, so unwinding the stack is not enough:
        whatever the attempt published below the watermark has to go with it.
        """
        for at in [key for key in self._table if key > depth]:
            del self._table[at]

    def forked(self, copies: list[Frame]) -> RouteLane:
        """This lane rebound to a forked stack's frames.

        :param copies: The forked stack, positionally matching the original —
            which is what :func:`frames_copy` guarantees, and why a
            depth-indexed lane needs no identity map of its own.
        :returns: A lane whose entries name the copied frames.
        """
        return RouteLane(
            {
                depth: _Published(copies[depth], entry.path, entry.route)
                for depth, entry in self._table.items()
                if depth < len(copies)
            }
        )


def _dup(lst: list[Any], remap: dict[int, list[Any]]) -> list[Any]:
    """``lst``'s one copy — the identity map keeps aliases aliased."""
    got = remap.get(id(lst))
    if got is None:
        got = list(lst)
        remap[id(lst)] = got
    return got


def _fork(lst: list[Any], remap: dict[int, list[Any]]) -> list[Any]:
    """``lst``'s empty fork — one per original, so aliases stay aliased.

    The contents are not copied; see :func:`frames_copy` for why, and
    :meth:`~lexic.parsing.pda.runtime.build.Frame.adopt_inherited` for where
    they come back.
    """
    got = remap.get(id(lst))
    if got is None:
        got = []
        remap[id(lst)] = got
    return got


def control_signature(stack: list[Frame], pos: int) -> tuple[Any, ...]:
    """What a probe side must SHARE with the other to have a common future.

    The stack IS the continuation, so two sides at the same position with the
    same control state consume the same remaining text and build the same
    additional values — which is what lets a boundary be settled without
    running either side to end-of-input.

    Deliberately excludes every value container (``out`` / ``sinks``): the
    two sides differing THERE is the fact being measured, and folding it into
    the signature would mean the sides never converge. Arm and clone enter by
    identity — the flat program is immutable and shared across every parse, so
    ``id`` is a stable key here rather than an accident of allocation.

    The iteration count is normalised by :func:`_count_key`, and that is what
    makes convergence possible at all: the take side has taken one iteration
    the stop side has not, so their raw counts differ FOREVER and no two states
    would ever match.
    """
    return (
        pos,
        len(stack),
        tuple(
            (
                id(frame.arm),
                frame.i,
                _count_key(frame),
                id(frame.clone),
                frame.span_start(),
            )
            for frame in stack
        ),
    )


_COUNT_FREE = -1
"""The count key of a loop whose exact iteration count can no longer constrain
anything — past its mandatory floor with no ceiling to hit."""


def _count_key(frame: Frame) -> int:
    """A frame's iteration count, or :data:`_COUNT_FREE` when it cannot matter.

    A count constrains the future only while it can still decide something: it
    is below the item's mandatory ``lo``, or the item has a ``hi`` to run into.
    Past ``lo`` on an unbounded item every further iteration is permitted, so
    the exact number is not part of the state — and collapsing it is what lets
    a side that took one more iteration converge with one that did not.

    Except where the count IS a value: a capture-free fold (one synthetic slot,
    no per-iteration values in any sink) keeps its depth in the count through
    its last loop and past it, so two sides differing there built different
    models and must not merge as one state.
    """
    arm = frame.arm
    i = frame.i
    count = frame.count
    clone = frame.clone
    if i + 1 >= arm.n and clone.mode == BUILD_FOLD and clone.n_items == 1:
        return count
    if i >= arm.n:
        return _COUNT_FREE
    if arm.his[i] >= 0 or count < arm.los[i]:
        return count
    return _COUNT_FREE


def value_shape(stack: list[Frame]) -> tuple[Any, ...]:
    """Every value container's length — the watermark taken AT the boundary.

    Both sides of a boundary are copies of one live stack, so everything
    already in a container when the fork was taken is identical between them
    by construction. Only what is appended AFTER can differ, and this is what
    lets :func:`pending_values` compare the delta instead of the whole
    accumulated state — the difference between O(built-since) and O(built), and
    the difference between a linear parse and a quadratic one.

    Taken on the LIVE stack, whose containers hold what they hold. A fork's
    containers start empty (:func:`frames_copy`), so its own values are
    everything past a watermark of zero — and :func:`pending_values` reads a
    container shorter than its watermark as "replaced, compare whole", which
    on a forked side is exactly its own values and nothing else.
    """
    return tuple(
        (
            len(frame.out),
            ()
            if frame.sinks is None
            else tuple(0 if slot is None else len(slot) for slot in frame.sinks),
        )
        for frame in stack
    )


def pending_values(stack: list[Frame], shape: tuple[Any, ...] = ()) -> tuple[Any, ...]:
    """Every value a probe side has built SINCE ``shape`` was taken.

    Containers grow by append, so the watermark's prefix is common to both
    sides and re-comparing it is pure waste — measured as 92% of the parse and
    the whole of its residual superlinearity. A container that came back
    SHORTER than its watermark was not appended to but replaced, and there the
    watermark means nothing: it is compared whole, which is the conservative
    reading.

    Frames deeper than ``shape`` did not exist at the boundary and are compared
    in full.

    Aliased containers (a frame's ``out`` IS a parent's sink slot) are read
    twice; harmless for an equality test, and cheaper than resolving identity.
    """
    out: list[Any] = []
    for depth, frame in enumerate(stack):
        was_out, was_sinks = shape[depth] if depth < len(shape) else (0, ())
        out.append(_since(frame.out, was_out))
        sinks = frame.sinks
        if sinks is None:
            out.append(())
            continue
        out.append(
            tuple(
                ()
                if slot is None
                else _since(slot, was_sinks[k] if k < len(was_sinks) else 0)
                for k, slot in enumerate(sinks)
            )
        )
    return tuple(out)


def _since(container: list[Any], mark: int) -> tuple[Any, ...]:
    """``container``'s tail past ``mark`` — or all of it if it shrank."""
    return tuple(container) if len(container) < mark else tuple(container[mark:])
