"""Action-driven IR dispatcher on the IrSelf substrate.

:class:`IrDispatch` is an :class:`~lexic.ir.nodes.IrComposite` carrying the
per-type action table. It does NOT walk children automatically — the action body
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
A body that raises :class:`~lexic.ir.action.IrReturn` unwinds to the
dispatcher's catch. The IrReturn instance itself is returned — it IS-A
:class:`~lexic.ir.nodes.IrNode` IS-A :class:`~lexic.ir.nodes.IrSelf`,
fitting the dispatcher's ``Ir_co: IrSelf`` bound. Callers needing the carried
value read ``.value`` from the result.

A bare :class:`~lexic.ir.action._Return` (not an IrReturn) propagates past
the dispatcher.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from lexic.ir.action import IrAction, IrEmit, IrRaise, IrRebuild, IrReturn, IrWalk
from lexic.ir.nodes import IrComposite, IrLiteral, IrNode, IrSelf, IrTuple


@dataclass(frozen=True, slots=True, repr=False)
class IrDispatch[Iri: IrSelf, Ir_co: IrSelf](IrComposite[Iri, Ir_co]):
    """Action-driven IR dispatcher.

    Holds a per-type ``actions`` table. ``eval`` (or ``apply``) resolves
    the matching :class:`~lexic.ir.action.IrAction` for ``type(n)`` via
    concrete-first MRO walk (memoised) and invokes its body.

    The dispatcher does no children-walking on its own. Action bodies that
    need pre-dispatched children call ``d.eval(d, c, ())`` themselves —
    ``d`` is the dispatcher driving the call.

    ``actions`` is a plain tuple field — ``_child_attrs`` inherits ``()``
    from :class:`~lexic.ir.nodes.IrComposite`, so the dispatcher is not
    walked as a grammar node. ``_resolve_cache`` is excluded from ``__eq__``
    and ``__hash__`` so two dispatchers with the same action table compare
    equal regardless of cache state.

    :param actions: Action table. Concrete ``target_type`` keys win over
        abstract ones via MRO order.
    :param default: Body invoked when no action matches ``type(n).__mro__``.
        Base default is :class:`~lexic.ir.action.IrRaise`; presets
        override (e.g. :class:`IrVisitor` →
        :class:`~lexic.ir.action.IrWalk`).
    """

    actions: tuple[IrAction[Ir_co], ...] = ()
    default: IrSelf = IrRaise()
    _resolve_cache: dict[type, IrAction[Ir_co]] = field(
        default_factory=dict,
        hash=False,
        compare=False,
        repr=False,
    )

    def eval(self, d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> Ir_co:
        """Resolve an action for ``type(n)`` and invoke its body.

        :param d: The dispatcher driving the walk. Action bodies use this
            for recursive sub-dispatch.
        :param n: The IR node to dispatch.
        :param nc: Pre-dispatched children of ``n`` (empty when called as
            an entry; populated when an outer action body pre-walked).
        :returns: The action body's ``Ir_co`` result, or the
            :class:`~lexic.ir.action.IrReturn` instance if a body raised
            one.
        :raises UnsupportedConstructError: If no action matches
            ``type(n)`` in the MRO walk.
        """
        return self._resolve(type(n)).body.eval(d, n, nc)

    def apply(self, root: IrNode) -> Ir_co:
        """Friendly entry — equivalent to ``self.eval(self, root, ())``.

        Catches :class:`~lexic.ir.action.IrReturn` from bodies and
        surfaces its ``.value`` when it satisfies the dispatcher's
        ``Ir_co`` bound. If the value does not satisfy the bound, the
        :class:`~lexic.ir.action.IrReturn` instance itself is checked;
        if that too does not satisfy, the exception re-raises.

        A bare :class:`~lexic.ir.action._Return` (not
        :class:`~lexic.ir.action.IrReturn`) propagates unconditionally.

        :param root: Root IR node to dispatch.
        :returns: The dispatched ``Ir_co`` value.
        """
        try:
            return self.eval(self, root, IrTuple())
        except IrReturn as ret:
            if isinstance(ret.value, self.bound):
                return ret.value
            if isinstance(ret, self.bound):
                return ret
            raise

    def _resolve(self, node_type: type) -> IrAction[Ir_co]:
        """Concrete-first MRO walk against ``self.actions``; memoised.

        Should be O(1) after the first call for a given ``node_type``.
        On a miss, constructs a synthetic :class:`~lexic.ir.action.IrAction`
        wrapping ``self.default`` and stores it in the cache, so subsequent
        dispatches on the same unmatched type skip the MRO scan.

        :param node_type: Runtime type of the dispatched node.
        :returns: The matching action, or a synthetic default-wrapping action
            if no explicit entry matches.
        """
        cache = self._resolve_cache
        if node_type in cache:
            return cache[node_type]
        for cls in node_type.__mro__:
            for action in self.actions:
                if action.target_type is cls:
                    cache[node_type] = action
                    return action
        action = IrAction[Ir_co](node_type, self.default)
        cache[node_type] = action
        return action


# ── Presets ──────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True, repr=False)
class IrVisitor(IrDispatch):
    """Side-effect walker. ``Ir_co = IrSelf`` (inherited default).

    The default action catches every node, recurses into its children
    via :class:`~lexic.ir.action.IrWalk`, and returns
    :data:`~lexic.ir.nodes.IrNone`. User actions resolve first via MRO
    and may produce side effects; a body that wants to stop the walk for a
    given type simply registers a more specific action that doesn't recurse
    (e.g. :class:`~lexic.ir.action.IrPass`,
    :class:`~lexic.ir.action.IrReturn`).
    """

    default: IrSelf = IrWalk()


@dataclass(frozen=True, slots=True, repr=False)
class IrTransformer[Iri: IrSelf, Ir_co: IrNode](IrDispatch[Iri, Ir_co]):
    """Rewrites IR trees. ``Ir_co = IrNode``.

    The default action walks each node's children via ``d`` and rebuilds
    the node — :class:`~lexic.ir.action.IrRebuild` is the canonical body.
    User actions resolve first; matching actions can return any
    :class:`~lexic.ir.nodes.IrNode`.
    """

    default: IrSelf = IrRebuild()


@dataclass(frozen=True, slots=True, repr=False)
class IrEmitter[Iri: IrSelf, Ir_co: IrLiteral](IrDispatch[Iri, Ir_co]):
    """Produces :class:`~lexic.ir.nodes.IrLiteral`-wrapped strings.
    ``Ir_co = IrLiteral``.

    Default body is :class:`~lexic.ir.action.IrEmit` — unmatched nodes
    degrade to ``IrLiteral(str(n))`` via the node's ``__str__``. Override
    via ``default=IrRaise()`` to refuse unmatched types instead.
    """

    default: IrSelf = IrEmit()
