"""Action-driven IR dispatcher on the IrSelf substrate.

:class:`IrDispatch` is an :class:`~lexic.ir.base.IrCachingTuple` of
``(actions, default)`` carrying the per-type action table. It does NOT walk
children automatically — the action body owns any recursion (typically by
calling ``d.eval(d, c, ())`` on each child it cares about, or by reading
pre-dispatched ``nc``).

Entry forms
-----------
- ``dispatcher.eval(d, n, nc)`` — protocol-shaped. ``d`` is the outer
  dispatcher driving the call (often ``self`` for entry); ``n`` is the
  IR node to dispatch; ``nc`` is the pre-dispatched children.
- ``dispatcher.apply(root)`` — façade that seeds ``d = self`` and ``nc = ()``.

Resolution is a pure function of ``(actions, type(n), default)``, so
:meth:`IrDispatch._resolve` is memoised on those keys instead of a per-instance
cache — the dispatcher stays an immutable value.

Short-circuit
-------------
A body that raises :class:`~lexic.ir.action.IrReturn` unwinds to the
dispatcher's catch; the IrReturn instance itself is returned when it satisfies
the ``Ir_co`` bound. A bare :class:`~lexic.ir.action._Return` propagates past.
"""

from __future__ import annotations

from functools import lru_cache
from typing import ClassVar, Sequence, cast

from lexic.ir.action import IrAction, IrEmit, IrRaise, IrRebuild, IrReturn, IrWalk
from lexic.ir.base import IrCachingTuple, IrNode, IrSelf, IrTuple
from lexic.ir.nodes import IrLiteral


class IrDispatch[Iri: IrSelf, Ir_co: IrSelf](
    IrCachingTuple[tuple[IrAction[Ir_co], ...], IrSelf]
):
    """Action-driven IR dispatcher — a record of ``(actions, default)``.

    ``eval``/``apply`` resolve the matching :class:`~lexic.ir.action.IrAction`
    for ``type(n)`` and invoke its body. ``_child_attrs`` is ``()`` so the
    dispatcher is never walked as a grammar node.

    :param actions: Action table; concrete ``target_type`` keys win over abstract
        ones via MRO order.
    :param default: Body invoked when no action matches (presets override).
    """

    _child_attrs: ClassVar[tuple[str, ...]] = ()
    actions: tuple[IrAction[Ir_co], ...] = ()
    default: IrSelf = IrRaise()

    @staticmethod
    @lru_cache(maxsize=None)
    def _resolve(
        actions: tuple[IrAction, ...], node_type: type, default: IrSelf
    ) -> IrAction:
        """The action matching ``node_type`` via concrete-first MRO walk; memoised.

        :param actions: The dispatcher's action table.
        :param node_type: Runtime type of the dispatched node.
        :param default: Body used when no action matches ``node_type.__mro__``.
        :returns: The matching action, or a synthetic ``default``-wrapping action.
        """
        for cls in node_type.__mro__:
            for action in actions:
                if action.target_type is cls:
                    return action
        return IrAction(node_type, default)

    def eval(self, d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> Ir_co:
        """Resolve an action for ``type(n)`` and invoke its body.

        :param d: The dispatcher driving the walk (used for recursive sub-dispatch).
        :param n: The IR node to dispatch.
        :param nc: Pre-dispatched children of ``n`` (empty when called as entry).
        :returns: The action body's ``Ir_co`` result.
        :raises UnsupportedConstructError: If the resolved default refuses ``n``.
        """
        return self._resolve(self.actions, type(n), self.default).body.eval(d, n, nc)

    def apply(self, root: IrNode) -> Ir_co:
        """Friendly entry — equivalent to ``self.eval(self, root, ())``.

        Catches :class:`~lexic.ir.action.IrReturn` and surfaces its ``.value``
        (or the IrReturn itself) when it satisfies the ``Ir_co`` bound; otherwise
        the exception re-raises.

        :param root: Root IR node to dispatch.
        :returns: The dispatched ``Ir_co`` value.
        """
        try:
            return self.eval(self, root, IrTuple())
        except IrReturn as ret:
            if isinstance(ret.value, self.bound):
                return cast(Ir_co, ret.value)
            if isinstance(ret, self.bound):
                return cast(Ir_co, ret)
            raise


# ── Presets ──────────────────────────────────────────────────────────


class IrVisitor(IrDispatch):
    """Side-effect walker. Default action :class:`~lexic.ir.action.IrWalk`
    recurses into children and returns :data:`~lexic.ir.base.IrNone`."""

    default: IrSelf = IrWalk()


class IrTransformer[Iri: IrSelf, Ir_co: IrNode](IrDispatch[Iri, Ir_co]):
    """Rewrites IR trees. Default action :class:`~lexic.ir.action.IrRebuild`
    walks each node's children via ``d`` and rebuilds the node."""

    default: IrSelf = IrRebuild()


class IrEmitter[Iri: IrSelf, Ir_co: IrLiteral](IrDispatch[Iri, Ir_co]):
    """Produces :class:`~lexic.ir.nodes.IrLiteral` strings. Default body
    :class:`~lexic.ir.action.IrEmit`; override with ``default=IrRaise()``."""

    default: IrSelf = IrEmit()
