"""The fast tree build — the unambiguous parse's short path.

Its own module because it sits between the two it needs: the forest defines the
nodes it produces and the tables define the predecessor chain it walks, and
those two already point one way (``tables`` → ``forest``). Putting this in
either would close the loop.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from lexic.ir import IrLeaf, IrNone, IrSelf, IrSeq
from lexic.parsing.earley.kernel.forest.forest import ParseTree, PayloadLeaf
from lexic.parsing.earley.kernel.loop.leo import expand_leo
from lexic.parsing.earley.kernel.tables.atoms import predecessor_chain
from lexic.parsing.earley.kernel.tables.decider import Decider
from lexic.parsing.earley.kernel.tables.splits import ChainSpec

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
        holder: list[IrSelf] = [IrNone]
        self.stack = [(handle, holder, 0, None)]
        while self.stack:
            if not self._step():
                return IrNone
        return self.memo.get(handle, IrNone)

    def _step(self) -> bool:
        """Process the top frame; ``False`` aborts the build (fast-path miss)."""
        handle, dest, slot, resolved = self.stack[-1]
        kernel = self.kernel
        if resolved is not None:  # revisit — every pending kid built in place
            self._build(handle, dest, slot, resolved)
            return True
        cached = self.memo.get(handle)
        if cached is not None:
            dest[slot] = cached
            self.stack.pop()
            return True
        packing = self._packing
        bits = packing.bits
        mask = packing.mask
        item = handle >> bits
        if item & mask == handle & mask:  # zero-width
            t = kernel.tables
            tree = t.empty_tree(t.codes.arm_rule[t.codes.code_arm[item >> bits]])
            if tree is not None:  # the shared input-independent derivation
                dest[slot] = tree
                self.stack.pop()
                return True
        st = kernel.st
        if handle in st.leo_links:
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
        chain = predecessor_chain(
            self._links,
            handle,
            ChainSpec(base, bits, t.code_choice),
            self.choices,
        )
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
