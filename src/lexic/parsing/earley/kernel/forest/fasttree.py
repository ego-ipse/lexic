"""The fast tree build — the unambiguous parse's short path.

Its own module because it sits between the two it needs: the forest defines the
nodes it produces and the tables define the predecessor chain it walks, and
those two already point one way (``tables`` → ``forest``). Putting this in
either would close the loop.
"""

from __future__ import annotations

from collections.abc import Sequence
from functools import partial
from typing import TYPE_CHECKING, NamedTuple

from lexic.exceptions import UnsupportedConstructError
from lexic.ir import IrLeaf, IrNone, IrSelf, IrSeq, IrTuple
from lexic.parsing.earley.kernel.forest.chart import Chart
from lexic.parsing.earley.kernel.forest.forest import (
    DERIVATION_STREAM,
    ParseTree,
    PayloadLeaf,
)
from lexic.parsing.earley.kernel.loop.leo import expand_leo
from lexic.parsing.earley.kernel.tables.decider import Decider
from lexic.parsing.earley.kernel.tables.splits import (
    ChainSpec,
    Steering,
    leftmost_chain,
    sole_chain,
)

if TYPE_CHECKING:  # `kernel` imports this module, so the reference is mutual
    from lexic.parsing.earley.kernel.loop.kernel import Kernel


class _Unbounded(Exception):
    """An untracked build re-entered a handle it is still building."""


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
        if self.choices is None:
            # Bail mode cannot loop: a cycle's keys cannot all hold one family
            # (a completed item has a finite derivation, so some key on the cycle
            # offers another), and bail mode declines at the first that holds two.
            return self._run(handle, None)
        pins = dict(self.choices)
        try:
            return self._run(handle, None)
        except _Unbounded:
            # A cycle: build again with the same pins, tracking every handle
            # still being built so each re-entry is avoided or refused.
            # The memo keeps what the first try finished: each entry was
            # assembled from its whole chain, a complete subtree either way.
            opened: set[int] = set()
            self.choices = Steering(pins, opened)
            return self._run(handle, opened)

    def _run(self, handle: int, opened: set[int] | None) -> IrSelf:
        """One build of ``handle``; ``opened`` tracks re-entries, or is ``None``
        for the untracked first try, which only watches for one.

        :raises _Unbounded: When an untracked resolving build re-enters a handle
            it is still building — its stack outgrows the chart and repeats one.
        """
        holder: list[IrSelf] = [IrNone]
        stack = self.stack = [(handle, holder, 0, None)]
        step = self._step if opened is None else partial(self._tracked, opened)
        budget = 8 * len(self.kernel.cols) + 4096
        while True:
            # Steps in rounds: an acyclic build ends well inside its first, and
            # only past a round's end is the stack read for a repeated handle.
            for _ in range(budget):
                if not stack:
                    return self.memo.get(handle, IrNone)
                if not step():
                    return IrNone
            if opened is None and self.choices is not None and self._repeats():
                raise _Unbounded
            budget *= 2

    def _tracked(self, opened: set[int]) -> bool:
        """One step of a tracked build: :meth:`_step`, with every handle that
        waits on its kids marked open until it is assembled. The chain reader
        avoids the open handles wherever another family remains; a re-entry
        into one anyway is a key no family could leave, and is refused.

        :param opened: The handles still being built.
        :raises UnsupportedConstructError: On a re-entry, in a resolving build.
        """
        stack = self.stack
        handle, _dest, _slot, resolved = stack[-1]
        if resolved is not None:
            opened.discard(handle)
            return self._step()
        if handle in opened and self.memo.get(handle) is None:
            return self._cycle()
        depth = len(stack)
        if not self._step():
            return False
        if len(stack) > depth and stack[depth - 1][3] is not None:
            opened.add(handle)  # its frame now waits on the kids above it
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

    def _repeats(self) -> bool:
        """Whether a handle waits on its kids twice in the stack — re-entered."""
        waiting = [frame[0] for frame in self.stack if frame[3] is not None]
        return len(waiting) != len(set(waiting))

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


class FirstTree(NamedTuple):
    """The first derivation of a span, and what building it left behind.

    :ivar handle: The packed accepting handle the tree derives.
    :ivar tree: The derivation.
    :ivar memo: Handle → the subtree the fast build made for it; empty when
        the tree came off the decoded chart instead, which keeps no handles.
    """

    handle: int
    tree: ParseTree
    memo: dict[int, ParseTree]


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
            return FirstTree(handle, tree, build.memo)
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
