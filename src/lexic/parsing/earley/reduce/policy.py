"""Reduction policy — what a child contributes, as real nodes.

``DROP`` contributes nothing, ``KEEP_RAW`` the node, ``KEEP_REDUCED`` its
reduction, and ``YIELD`` the subtree's text. Singletons, because the engine
asks ``body is DROP`` — a repr-equal twin would pass every comparison a test
makes and fail every one the engine makes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Sequence, cast

from lexic.ir import (
    IrLeaf,
    IrSelf,
    IrSingleton,
    IrStr,
    IrTuple,
)
from lexic.parsing.earley.kernel.forest import ParseTree, PayloadLeaf

if TYPE_CHECKING:  # `reducer` imports this module — the reference is mutual
    from lexic.parsing.earley.reduce.reducer import Reducer


class Drop(IrLeaf[IrSelf, IrSelf], metaclass=IrSingleton):
    """Contribute nothing — a non-semantic rule or an inline-literal terminal."""

    def eval(self, _d: IrSelf, _n: IrSelf, _nc: Sequence[IrSelf], /) -> IrTuple:
        """No contribution at all.

        :returns: The empty channel.
        """
        return IrTuple()


class KeepRaw(IrLeaf[IrSelf, IrSelf], metaclass=IrSingleton):
    """Contribute the node unchanged — a terminal leaf passed straight through."""

    def eval(self, _d: IrSelf, n: IrSelf, _nc: Sequence[IrSelf], /) -> IrTuple:
        """The node itself, unreduced.

        :param n: The parse node.
        :returns: A one-element channel.
        """
        return IrTuple(n)


class KeepReduced(IrLeaf[IrSelf, IrSelf], metaclass=IrSingleton):
    """Contribute the reduced node — a semantic sub-rule folded to its IR."""

    def eval(self, d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> IrTuple:
        """The node's own reduction.

        :param d: The driving :class:`Reducer`.
        :param n: The parse node.
        :param nc: Threads the :class:`ReduceCtx`, so ``d.eval`` reads the memo.
        :returns: A one-element channel.
        """
        return IrTuple(d.eval(d, n, nc))


DROP = Drop()
"""Contribute nothing — a non-semantic rule or an inline-literal terminal."""
KEEP_RAW = KeepRaw()
"""Contribute the node unchanged — a terminal leaf passed straight through."""
KEEP_REDUCED = KeepReduced()
"""Contribute the reduced node — a semantic sub-rule folded to its IR."""


class Yield(IrLeaf[IrSelf, IrSelf], metaclass=IrSingleton):
    """Source text of a parse subtree, skipping non-semantic sub-rule spans.

    Collects ``n``'s consumed characters in source order, recursing into
    sub-trees but skipping any whose rule the reducer's ``noise`` policy marks
    :data:`DROP` (e.g. ABNF ``DQUOTE`` delimiters). Inline-literal terminals are
    kept — so a numeric token like ``%x41-5A`` survives intact while a quoting
    rule's characters drop out. The text-yielding mirror of building from ``nc``.
    """

    def eval(self, d: IrSelf, n: IrSelf, _nc: Sequence[IrSelf], /) -> IrStr:
        """Concatenate the subtree's kept leaf characters.

        :param d: The driving :class:`Reducer` (supplies the ``noise`` policy).
        :param n: The parse node (or terminal leaf) whose text to recover.
        :returns: The subtree source text as an :class:`IrStr`.
        """
        if isinstance(n, PayloadLeaf):  # delegated child — its recorded span text
            return IrStr(n.text)
        if not isinstance(n, ParseTree):
            return IrStr(str(n))
        parts: list[str] = []
        for k in n.kids:
            if (
                isinstance(k, ParseTree)
                and cast("Reducer", d).noise.resolve(k.symbol) is DROP
            ):
                continue
            parts.append(str(self.eval(d, k, ())))
        return IrStr("".join(parts))


YIELD = Yield()
"""Shared subtree-text node — stateless, so one instance."""
