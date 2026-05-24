"""Action-driven IR dispatcher on the IrSelf substrate.

:class:`IrDispatch` is an :class:`IrCollection` whose items are the per-type
action table. It does NOT walk children automatically — the action body
is responsible for any recursion (typically by calling ``d.eval(d, c, ())``
on each child it cares about, or by reading pre-dispatched ``nc``).

Entry forms
-----------
- ``dispatcher.eval(d, n, nc)`` — protocol-shaped. ``d`` is the outer
  dispatcher driving the call (often ``self`` for entry); ``n`` is the
  IR node to dispatch; ``nc`` is the pre-dispatched children (empty when
  called as entry).
- ``dispatcher.apply(root)`` — friendly façade that seeds ``d = self``
  and ``nc = ()``.

Short-circuit
-------------
A body that raises :class:`IrReturn` unwinds to the dispatcher's catch.
The IrReturn instance itself is returned — it IS-A :class:`IrNode`
IS-A :class:`IrSelf`, fitting the dispatcher's ``Ir_co: IrSelf`` bound.
Callers needing the carried value read ``.value`` from the result.

A bare :class:`_Return` (not an IrReturn) propagates past the dispatcher.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import ClassVar, Sequence

from lexic.exceptions import UnsupportedConstructError
from lexic.ir.action import IrAction, IrPass, IrRebuild, IrReturn
from lexic.ir.nodes import IrCollection, IrLiteral, IrNode, IrSelf, IrTuple


@dataclass(frozen=True, slots=True, repr=False)
class IrDispatch[Ir_co : IrSelf](IrCollection[Ir_co]):
    """Action-driven IR dispatcher.

    Holds a per-type ``actions`` table. ``eval`` (or ``apply``) resolves
    the matching :class:`IrAction` for ``type(n)`` via concrete-first MRO
    walk (memoised) and invokes its body.

    The dispatcher does no children-walking on its own. Action bodies that
    need pre-dispatched children call ``d.eval(d, c, ())`` themselves —
    ``d`` is the dispatcher driving the call.

    :param actions: Action table. Concrete ``target_type`` keys win over
        abstract ones via MRO order. A user-supplied default catch-all is
        expressed as ``IrAction(IrSelf, …)`` at the end of the tuple.
    """

    _items_attr: ClassVar[str] = "actions"
    actions: tuple[IrAction[Ir_co], ...] = ()
    _resolve_cache: dict[type, IrAction[Ir_co]] = field(
        init=False,
        default_factory=dict,
        hash=False,
        compare=False,
        repr=False,
    )

    def _extra_field_names(self) -> tuple[str, ...]:
        """``actions`` is items; ``_resolve_cache`` is internal — no extras.

        :returns: Empty tuple.
        """
        return ()

    def eval(self, d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> Ir_co:
        """Resolve an action for ``type(n)`` and invoke its body.

        :param d: The dispatcher driving the walk. Action bodies use this
            for recursive sub-dispatch.
        :param n: The IR node to dispatch.
        :param nc: Pre-dispatched children of ``n`` (empty when called as
            an entry; populated when an outer action body pre-walked).
        :returns: The action body's ``Ir_co`` result, or the IrReturn
            instance if a body raised one.
        :raises UnsupportedConstructError: If no action matches
            ``type(n)`` in the MRO walk.
        """
        try:
            return self._resolve(type(n)).body.eval(d, n, nc)
        except IrReturn as ret:
            ret_val = ret.value
            if not isinstance(ret_val, self.bound):
                raise ret
            return ret_val

    def apply(self, root: IrNode) -> Ir_co:
        """Friendly entry — equivalent to ``self.eval(self, root, ())``.

        :param root: Root IR node to dispatch.
        :returns: The dispatched ``Ir_co`` value.
        """
        return self.eval(self, root, IrTuple())

    def _resolve(self, node_type: type) -> IrAction[Ir_co]:
        """Concrete-first MRO walk against ``self.actions``; memoised.

        Should be O(1) after the first call for a given node_type.

        :param node_type: Runtime type of the dispatched node.
        :returns: The matching action.
        :raises UnsupportedConstructError: If no ``target_type`` in
            ``node_type.__mro__`` matches any action in the table.
        """
        cache = self._resolve_cache
        if node_type in cache:
            return cache[node_type]
        for cls in node_type.__mro__:
            for action in self.actions:
                if action.target_type is cls:
                    cache[node_type] = action
                    return action
        raise UnsupportedConstructError(
            f"{type(self).__name__}: no action for {node_type.__name__!r}"
        )


# ── Presets ──────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True, repr=False)
class IrVisitor(IrDispatch):
    """Side-effect walker. ``Ir_co = IrSelf`` (inherited default).

    The default action catches every node and returns :data:`IrNone` via
    :class:`IrPass`. User actions resolve first via MRO and may produce
    side effects. To compose, include :class:`IrPass` at the end of your
    ``actions`` tuple explicitly.
    """

    actions: tuple[IrAction[IrSelf], ...] = (IrAction(IrSelf, IrPass()),)


@dataclass(frozen=True, slots=True, repr=False)
class IrTransformer(IrDispatch[IrNode]):
    """Rewrites IR trees. ``Ir_co = IrNode``.

    The default action walks each node's children via ``d`` and rebuilds
    the node — :class:`IrRebuild` is the canonical body. User actions
    resolve first; matching actions can return any ``IrNode``.
    """

    actions: tuple[IrAction[IrNode], ...] = (IrAction(IrNode, IrRebuild()),)


@dataclass(frozen=True, slots=True, repr=False)
class IrEmitter(IrDispatch[IrLiteral]):
    """Produces :class:`IrLiteral`-wrapped strings. ``Ir_co = IrLiteral``.

    No default action — users define per-type emit actions and unmatched
    types raise :exc:`UnsupportedConstructError`. The "emit ``str(n)``"
    fallback is a use-case-specific convenience, not a default.
    """

    actions: tuple[IrAction[IrLiteral], ...] = ()
