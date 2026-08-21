"""Declarative grammar-reduction data and contribution policies.

A :class:`Reducer` says what a grammar parse is for: rule refs map to IR
actions, while child and literal policies say which values reach an action's
argument channel. These are grammar-side IR values, independent of any parser.
The compile layer derives a pruned model artefact from them and supplies the
drop-aware text view used by :data:`YIELD`.
"""

from __future__ import annotations

from collections.abc import Sequence

from lexic.ir.action.mapping import IR_DEFAULT, IrMap
from lexic.ir.action.walk import IrDispatch
from lexic.ir.spine.meta import IrSingleton
from lexic.ir.spine.records import IrTuple
from lexic.ir.spine.scalars import IrStr
from lexic.ir.spine.spine import IrLeaf, IrSelf


class Drop(IrLeaf[IrSelf, IrSelf], metaclass=IrSingleton):
    """Contribute nothing: a non-semantic child or inline terminal."""

    def eval(self, _d: IrSelf, _n: IrSelf, _nc: Sequence[IrSelf], /) -> IrTuple:
        """Return the empty argument channel."""
        return IrTuple()


class KeepRaw(IrLeaf[IrSelf, IrSelf], metaclass=IrSingleton):
    """Contribute the input node unchanged."""

    def eval(self, _d: IrSelf, n: IrSelf, _nc: Sequence[IrSelf], /) -> IrTuple:
        """Return ``n`` as a one-element argument channel."""
        return IrTuple(n)


class KeepReduced(IrLeaf[IrSelf, IrSelf], metaclass=IrSingleton):
    """Contribute the dispatcher's interpretation of the input node."""

    def eval(self, d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> IrTuple:
        """Dispatch ``n`` and return its value as a one-element channel."""
        return IrTuple(d.eval(d, n, nc))


class Yield(IrLeaf[IrSelf, IrSelf], metaclass=IrSingleton):
    """Contribute the source-text view supplied by the caller.

    ``ReduceFold`` wraps model nodes in a view whose ``str`` is the emission
    stream minus dropped subtrees. Probe and notation callers likewise supply
    their own text-bearing IR node, so the policy remains parser-independent.
    """

    def eval(self, _d: IrSelf, n: IrSelf, _nc: Sequence[IrSelf], /) -> IrStr:
        """Return the caller-provided text view of ``n``."""
        return IrStr(str(n))


DROP = Drop()
"""Contribute nothing."""
KEEP_RAW = KeepRaw()
"""Contribute the node unchanged."""
KEEP_REDUCED = KeepReduced()
"""Contribute the node's interpreted value."""
YIELD = Yield()
"""Contribute the node's source-text view."""


class Reducer(IrDispatch):
    """Rule-action declarations plus child and literal contribution policies."""

    noise: IrMap = IrMap(IrTuple(IR_DEFAULT, KEEP_REDUCED))
    literal: IrSelf = KEEP_RAW

    def body(self, symbol: IrSelf) -> IrSelf:
        """Return the explicit action for ``symbol``, or the default action."""
        found = self.actions.get(symbol)
        return self.default if found is None else found


__all__ = [
    "DROP",
    "KEEP_RAW",
    "KEEP_REDUCED",
    "YIELD",
    "Drop",
    "KeepRaw",
    "KeepReduced",
    "Reducer",
    "Yield",
]
