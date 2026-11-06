"""The fast tree build — the unambiguous parse's short path.

Its own module because it sits between the two it needs: the forest defines the
nodes it produces and the tables define the predecessor chain it walks, and
those two already point one way (``tables`` → ``forest``). Putting this in
either would close the loop.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from functools import partial
from typing import TYPE_CHECKING, NamedTuple, cast

from lexic.exceptions import UnsupportedConstructError
from lexic.ir import IrLeaf, IrNone, IrSelf, IrSeq, IrTuple
from lexic.parsing.earley.kernel.forest.chart import Chart
from lexic.parsing.earley.kernel.forest.forest import (
    DERIVATION_STREAM,
    ParseTree,
    PayloadLeaf,
)
from lexic.parsing.earley.kernel.loop.leo import expand_leo
from lexic.parsing.earley.kernel.tables.atoms import KLink
from lexic.parsing.earley.kernel.tables.decider import Decider
from lexic.parsing.earley.kernel.tables.splits import (
    ChainSpec,
    Steering,
    is_handle,
    leftmost_chain,
    sole_chain,
)

if TYPE_CHECKING:  # `kernel` imports this module, so the reference is mutual
    from lexic.parsing.earley.kernel.loop.kernel import Kernel


class FastTree(IrLeaf[IrSelf, IrSelf]):
    """Iterative single-derivation builder over the packed SPPF.

    The unambiguous fast path: an explicit work stack (never the C stack)
    resolves each handle's kids by walking the binarised predecessor chain,
    memoising built subtrees. :meth:`build` returns :data:`IrNone` on a
    fast-path miss (a key with more than one family, i.e. ambiguity, or a
    missing link) so the caller falls back to the trampolined enumeration
    over the decoded chart.

    :ivar kernel: The finished kernel whose links to walk.
    :ivar memo: handle → its built :class:`ParseTree`.
    :ivar stack: Work frames ``(handle, dest, slot, resolved | None)``.
    :ivar choices: key → which family to take at an ambiguity point, or
        ``None`` for the fast path's "an ambiguity point is a miss" contract.
        With choices supplied the build no longer misses on ambiguity; it
        builds THE derivation those choices name, which is what lets two
        derivations of one span be compared by the values they build. A pin
        applies to the OUTERMOST visit of its key and is consumed there: on a
        cyclic chart the pinned family leads back to its own key, and a pin
        that re-applied would name no finite derivation at all.
    :ivar decide: The split decider whose carving the build keeps.
    """

    __slots__ = (
        "kernel",
        "memo",
        "stack",
        "choices",
        "decide",
        "_packing",
        "_links",
    )

    kernel: Kernel
    memo: dict[int, ParseTree]
    stack: list[tuple[int, list, int, list | None]]
    choices: dict[int, int] | None
    decide: Decider

    def __init__(
        self,
        kernel: Kernel,
        choices: dict[int, int] | None,
        decide: Decider,
    ) -> None:
        """:param kernel: the finished kernel to read.
        :param choices: the family to take at each ambiguity point, if any.
        :param decide: the split decider whose carving to keep.
        """
        self.kernel = kernel
        self.decide = decide
        # A copy, because the build CONSUMES pinned entries (see
        # `splits._descend`) — the caller's map must not be eaten.
        self.choices = choices if choices is None else dict(choices)
        self.memo = {}
        self.stack = []
        self._packing = kernel.tables.packing
        self._links = kernel.family_reader()

    def build(self, handle: int) -> IrSelf:
        """The single :class:`ParseTree` under ``handle``, or :data:`IrNone`.

        :param handle: The packed accepting handle ``(item << B) | end``.
        :returns: The tree, or :data:`IrNone` on a fast-path miss.
        """
        if self.choices is None or not self.kernel.tables.decode.cyclic:
            # Nothing to watch. Only a cyclic grammar (``A ⇒+ A``) can put a
            # node inside itself; and bail mode declines at the first key that
            # holds two families, which every cycle's keys include — a completed
            # item has a finite derivation, so some key on its cycle offers one.
            return self._run(handle, None)
        # A cyclic grammar: track every handle still being built, and steer
        # each chain away from a child that cannot complete beneath them, so a
        # re-entry is only ever a pin's unroll, or a pinned flip refused.
        opened: dict[int, int] = {}
        stalled = Stalled(self, opened)
        self.choices = Steering(self.choices, stalled)
        return self._run(handle, partial(self._tracked, opened, stalled))

    def _run(self, handle: int, step: Callable[[], bool] | None = None) -> IrSelf:
        """One build of ``handle``, by ``step`` (the plain one by default)."""
        holder: list[IrSelf] = [IrNone]
        stack = self.stack = [(handle, holder, 0, None)]
        step = step or self._step
        while stack:
            if not step():
                return IrNone
        # The holder, not the memo: a zero-width handle takes its rule's shared
        # empty tree without a memo entry, and a zero-width ROOT is still built.
        return holder.pop()

    def _tracked(self, opened: dict[int, int], stalled: Stalled) -> bool:
        """One step of a tracked build: :meth:`_step`, with every handle that
        waits on its kids marked open, with the pins left before its own key
        took one, until it is assembled.

        The chain reader drops every family whose child cannot complete beneath
        the open handles (:class:`Stalled`) wherever another family remains, so
        an unpinned build never re-enters one. A re-entry after a pin was
        consumed since the handle opened is that pin's one-lap unroll: the
        pinned family led back to the handle, and the inner occurrence is a
        fresh visit under the default choices — its own chain covers its span,
        and the outer occurrence keeps the pinned family, so the unroll is
        complete. Any other re-entry follows a pin no complete derivation
        honours, and is refused.

        :param opened: Each handle still being built → pins left when it opened.
        :param stalled: The completeness test, told which handle is collected.
        :raises UnsupportedConstructError: On a re-entry no family could leave.
        """
        stack = self.stack
        handle, _dest, _slot, resolved = stack[-1]
        if resolved is not None:
            opened.pop(handle, None)
            return self._step()
        pins = len(self.choices) if self.choices else 0
        if (
            handle in opened
            and self.memo.get(handle) is None
            and pins >= opened[handle]
        ):
            return self._cycle()
        depth = len(stack)
        stalled.at = handle
        if not self._step():
            return False
        if len(stack) > depth and stack[depth - 1][3] is not None:
            opened[handle] = pins  # its frame now waits on the kids above it
        return True

    def _step(self) -> bool:
        """Process the top frame; ``False`` aborts the build (fast-path miss)."""
        handle, dest, slot, resolved = self.stack[-1]
        if resolved is not None:  # revisit — every pending kid built in place
            self._build(handle, dest, slot, resolved)
            return True
        kernel = self.kernel
        ready = self.memo.get(handle)
        if ready is None:
            packing = self._packing
            item = handle >> packing.bits
            if item & packing.mask == handle & packing.mask:
                t = kernel.tables  # zero-width: the shared derivation, when unique
                ready = t.empty_tree(
                    t.codes.arm_rule[t.codes.code_arm[item >> packing.bits]]
                )
        if ready is not None:
            dest[slot] = ready
            self.stack.pop()
            return True
        if handle in kernel.st.leo_links:
            expand_leo(kernel.st, kernel.tables, handle)
        resolved = self._collect(handle)
        if resolved is None:
            return False
        pending = self._pending(resolved)
        if pending:
            self.stack[-1] = (handle, dest, slot, resolved)
            self.stack.extend(pending)
            return True
        self._build(handle, dest, slot, resolved)
        return True

    def _cycle(self) -> bool:
        """A re-entry no family could leave: bail mode misses as on any key it
        cannot settle; a resolving build refuses, since no complete derivation
        follows these choices and none is put in its place."""
        if self.choices is None:
            return False
        raise UnsupportedConstructError(
            "parsing: a cycle the decided derivation cannot leave — no complete "
            "derivation along these choices, so the span cannot be compared"
        )

    def _build(self, handle: int, dest: list, slot: int, resolved: list) -> None:
        """Assemble and memoise the node's tree; pop its frame."""
        t = self.kernel.tables
        rid = t.codes.arm_rule[t.codes.code_arm[handle >> (2 * self._packing.bits)]]
        tree = ParseTree(t.decode.rule_refs[rid], IrSeq(*resolved))
        self.memo[handle] = tree
        dest[slot] = tree
        self.stack.pop()

    def _collect(self, handle: int) -> list | None:
        """Kids of ``handle`` in source order, walking the predecessor chain.

        ``None`` when a key is missing or packs more than one family — the
        caller falls back to the trampolined enumeration.
        """
        t = self.kernel.tables
        bits = self._packing.bits
        base = t.codes.arm_base[t.codes.code_arm[(handle >> bits) >> bits]]
        if self.choices is None:
            chain = sole_chain(self._links, handle, base, bits)
        else:
            spec = ChainSpec(
                base,
                bits,
                t.code_choice,
                t.codes.code_arm,
                t.codes.arm_base,
                t.decode.code_droppable,
            )
            chain = leftmost_chain(self._links, handle, spec, self.choices, self.decide)
        if chain is None:
            return None  # missing (no build) or ambiguous (fall back)
        return [
            c if isinstance(c, (int, PayloadLeaf)) else t.terms.char_leaf(c)
            for _, _, c in chain
        ]

    def _pending(self, resolved: list) -> list:
        """Swap memoised kids in place; return frames for those still unbuilt."""
        memo = self.memo
        tables = self.kernel.tables
        codes = tables.codes
        packing = self._packing
        bits = packing.bits
        mask = packing.mask
        out: list[tuple[int, list, int, None]] = []
        for idx, child in enumerate(resolved):
            if isinstance(child, int):  # a packed handle, not yet built
                cached = memo.get(child)
                if cached is not None:
                    resolved[idx] = cached
                    continue
                if (child >> bits) & mask == child & mask:
                    tree = tables.empty_tree(
                        codes.arm_rule[codes.code_arm[child >> (2 * bits)]]
                    )
                    if tree is not None:  # zero-width — the shared derivation
                        resolved[idx] = tree
                        continue
                out.append((child, resolved, idx, None))
        return out


class Stalled(IrLeaf[IrSelf, IrSelf]):
    """The families a tracked build must not take: those with no complete
    derivation beneath the handle being collected.

    A family completes when its child does and its predecessor still reaches
    dot 0 through families that complete — a family can be sound in its own
    child and still lead, through a split, to a predecessor whose every child
    re-enters the cycle. Only a child over the SAME span as the handle can fail:
    a shorter one has a finite derivation whose smallest repeats no handle on
    any path, and no open handle shares its span. Such a child must end where
    the handle does, so only a predecessor ending there is walked. A child
    completes when its own chain does, without meeting a handle to avoid: the
    handle being collected, and every open one over that span except those a
    pin was spent beneath since they opened — re-entering one of those is the
    pin's one-lap unroll, a fresh visit.

    The **mutable** per-build cursor (like :class:`FastTree`): it reads the
    chart alone, so its answers are memoised by the handles avoided. It runs
    only in a cyclic grammar's resolving build, and its depth is bounded by the
    grammar's items, never the document.

    :ivar at: The handle whose chain is being read.
    """

    __slots__ = ("at", "_build", "_links", "_opened", "_known")

    at: int

    def __init__(self, build: FastTree, opened: dict[int, int]) -> None:
        """:param build: The tracked build — its kernel, and its pins left.
        :param opened: Its handles still being built → pins left when each
            opened, in path order.
        """
        self.at = -1
        self._build = build
        self._links = build.kernel.family_reader()
        self._opened = opened
        self._known: dict[tuple[int, int, frozenset[int]], bool] = {}

    def __contains__(self, link: object) -> bool:
        """Whether family ``link`` of the handle being read cannot complete."""
        at = self.at
        t = self._build.kernel.tables
        bits = t.packing.bits
        pred, end, child = cast(KLink, link)
        held = self._held(at, bits)
        if is_handle(child) and not self._completes(child, held):
            return True
        base = t.codes.arm_base[t.codes.code_arm[at >> bits >> bits]]
        return not self._reaches((pred << bits) | end, at, base, held)

    def _held(self, at: int, bits: int) -> frozenset[int]:
        """The handles a child of ``at`` must not re-enter."""
        opened = self._opened
        pins = len(self._build.choices or ())
        held = {at}
        for handle in reversed(opened):  # the path's same-span tail
            if not _same_span(handle, at, bits):
                break
            if pins >= opened[handle]:  # no pin spent beneath it: no unroll
                held.add(handle)
        return frozenset(held)

    def _completes(self, handle: int, held: frozenset[int]) -> bool:
        """Whether ``handle`` derives its span without any of ``held``."""
        if handle in held:
            return False
        kernel = self._build.kernel
        t = kernel.tables
        packing = t.packing
        if not _same_span(handle, self.at, packing.bits):
            return True  # shorter than the handles avoided: it meets none
        item = handle >> packing.bits
        code = item >> packing.bits
        if item & packing.mask == handle & packing.mask:
            if t.empty_tree(t.codes.arm_rule[t.codes.code_arm[code]]) is not None:
                return True  # the build takes the rule's shared empty tree
        if handle in kernel.st.leo_links:
            expand_leo(kernel.st, t, handle)
        base = t.codes.arm_base[t.codes.code_arm[code]]
        return self._reaches(handle, handle, base, held | {handle})

    def _reaches(self, key: int, owner: int, base: int, held: frozenset[int]) -> bool:
        """Whether ``key``'s chain reaches dot 0 through families whose children
        complete without ``held``; ``owner`` is the completed handle it builds.
        A key ending short of ``owner`` holds no child over its span."""
        bits = self._build.kernel.tables.packing.bits
        if (key >> bits >> bits) == base or (key ^ owner) & ((1 << bits) - 1):
            return True
        known = self._known.get((key, owner, held))
        if known is None:
            known = any(
                not (is_handle(link[2]) and not self._completes(link[2], held))
                and self._reaches((link[0] << bits) | link[1], owner, base, held)
                for link in self._links.get(key) or ()
            )
            self._known[(key, owner, held)] = known
        return known


def _same_span(handle: int, other: int, bits: int) -> bool:
    """Whether two packed handles start and end at the same columns."""
    mask = (1 << bits) - 1
    return (handle ^ other) & mask == 0 and ((handle ^ other) >> bits) & mask == 0


class FirstTree(NamedTuple):
    """The first derivation of a span, and what building it left behind.

    :ivar handle: The packed accepting handle the tree derives.
    :ivar tree: The derivation.
    :ivar memo: Handle → the subtree the fast build made for it; empty when
        the tree came off the decoded chart instead, which keeps no handles.
    :ivar steered: Handle → the chain a cyclic grammar's build chose where it
        had a choice, which its steering can move off the unsteered reading;
        ``None`` where nothing was steered.
    """

    handle: int
    tree: ParseTree
    memo: dict[int, ParseTree]
    steered: dict[int, list[KLink]] | None = None


def first_tree(
    kern: Kernel, handles: Sequence[int], decide: Decider
) -> FirstTree | None:
    """The first of ``handles`` the fast build derives, under ``decide``.

    RESOLVING mode: an empty choices map pins nothing, so the decider settles
    every split — bail mode would decline on exactly the ambiguous spans and
    leave them to chart order. Every handle is tried in chart order, because a
    many-production root is not a packed key: each sibling production builds
    on its own, and the siblings are what a meaning comparison reads after.

    :param kern: The finished kernel whose links to walk.
    :param handles: The accepting handles, in chart order.
    :param decide: The split decider whose carving the build keeps.
    :returns: The first that builds, or ``None`` when none does.
    """
    for handle in handles:
        build = FastTree(kern, {}, decide)
        tree = build.build(handle)
        if isinstance(tree, ParseTree):
            steering = build.choices
            steered = steering.taken if isinstance(steering, Steering) else None
            return FirstTree(handle, tree, build.memo, steered)
    return None


def streamed_first(node: IrSelf, chart: Chart, handle: int) -> FirstTree | None:
    """The decoded chart's first derivation of ``node`` — the fast build's
    fallback, read in chart order where the short path declined.

    :param node: The forest node to derive (an :class:`SppfNode` or a
        :class:`RootNode` over several accepting productions).
    :param chart: The kernel's decoded chart.
    :param handle: The packed accepting handle ``node`` stands for.
    :returns: The first derivation with an empty memo, or ``None`` when the
        chart derives none.
    """
    got = next(iter(DERIVATION_STREAM.eval(IrNone, node, IrTuple(chart))), IrNone)
    return FirstTree(handle, got, {}) if isinstance(got, ParseTree) else None
