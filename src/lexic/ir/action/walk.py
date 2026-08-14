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

``actions`` IS the table — an :class:`~lexic.ir.action.mapping.IrTypeMap` whose dyads
are :class:`~lexic.ir.action.IrAction` records (``(target_type, body)``).
Resolution is the map's own concrete-first MRO lookup: one ``getattr`` per
``type(n).__mro__`` entry, no memo, no per-instance cache — the dispatcher
stays an immutable value. Only a resolution miss falls back to ``default``.

Short-circuit
-------------
A body that raises :class:`~lexic.ir.action.IrReturn` unwinds to the
dispatcher's catch; the IrReturn instance itself is returned when it satisfies
the ``Ir_co`` bound. A bare :class:`~lexic.ir.action._Return` propagates past.
"""

from __future__ import annotations

from typing import ClassVar, Sequence, cast

from lexic.exceptions import IrKeyError
from lexic.ir.action.build import IrEmit, IrRaise, IrRebuild, IrWalk
from lexic.ir.action.control import IrReturn, IrThis
from lexic.ir.action.mapping import IrMap, IrTypeMap
from lexic.ir.grammar.nodes import IrLiteral
from lexic.ir.spine.records import IrCachingTuple, IrTuple
from lexic.ir.spine.spine import IrNode, IrSelf


class IrDispatch[Iri: IrSelf, Ir_co: IrSelf](IrCachingTuple[IrTypeMap, IrSelf]):
    """Action-driven IR dispatcher — a record of ``(actions, default)``.

    ``eval``/``apply`` resolve the matching action body for ``type(n)`` and
    invoke it. ``_child_attrs`` is ``()`` so the dispatcher is never walked as
    a grammar node.

    :param actions: Action table — an :class:`~lexic.ir.action.mapping.IrMap` whose
        ``resolve`` picks the body. An :class:`~lexic.ir.action.mapping.IrTypeMap`
        (the usual case) keys on ``target_type``, concrete winning over
        abstract via MRO order; the plain ``IrMap`` keys on the dispatched
        VALUE, which is what a rule-ref-keyed dispatcher needs.
    :param default: Body invoked when no action matches (presets override).
    """

    _child_attrs: ClassVar[tuple[str, ...]] = ()
    actions: IrMap = IrTypeMap()
    default: IrSelf = IrRaise()

    def eval(self, d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> Ir_co:
        """Resolve an action body for ``type(n)`` and invoke it.

        Resolution and evaluation are deliberately separated: only a
        resolution *miss* falls back to ``default`` — an
        :exc:`~lexic.exceptions.IrKeyError` raised inside a body propagates.

        :param d: The dispatcher driving the walk (used for recursive sub-dispatch).
        :param n: The IR node to dispatch.
        :param nc: Pre-dispatched children of ``n`` (empty when called as entry).
        :returns: The action body's ``Ir_co`` result.
        :raises UnsupportedConstructError: If the resolved default refuses ``n``.
        """
        actions = self.actions
        try:
            body: IrSelf = actions[type(n)]
        except KeyError:
            body = self._resolve_miss(actions, n)
        return body.eval(d, n, nc)

    def _resolve_miss(self, actions: IrMap, n: IrSelf) -> IrSelf:
        """Slow-path resolution: MRO walk + ``IR_DEFAULT``, else ``default``.

        Reached only when ``type(n)`` is not an exact key — rare in practice
        (dispatched node types are registered concretely). Kept off the hot
        ``eval`` path so the common exact-type hit pays no extra frame.

        :param actions: The dispatcher's action table.
        :param n: The node whose exact type missed.
        :returns: The resolved body, or ``self.default`` on a full miss.
        """
        try:
            return actions.resolve(n)
        except IrKeyError:
            return self.default

    def apply(self, root: IrNode) -> Ir_co:
        """Friendly entry — dispatch ``root`` via the preset's :meth:`_run`.

        Catches :class:`~lexic.ir.action.IrReturn` and surfaces its ``.value``
        (or the IrReturn itself) when it satisfies the ``Ir_co`` bound; otherwise
        the exception re-raises.

        :param root: Root IR node to dispatch.
        :returns: The dispatched ``Ir_co`` value.
        """
        try:
            return self._run(root)
        except IrReturn as ret:
            if isinstance(ret.value, self.bound):
                return cast(Ir_co, ret.value)
            if isinstance(ret, self.bound):
                return cast(Ir_co, ret)
            raise

    def _run(self, root: IrNode) -> Ir_co:
        """The ``apply`` strategy — ``self.eval(self, root, ())``.

        Presets with a different drive (:class:`IrBottomUp`'s iterative
        post-order walk) override this, keeping :meth:`apply`'s
        :class:`~lexic.ir.action.IrReturn` handling in one place.

        :param root: Root IR node to dispatch.
        :returns: The dispatched ``Ir_co`` value.
        """
        return self.eval(self, root, IrTuple())


# ── Presets ──────────────────────────────────────────────────────────


class IrVisitor(IrDispatch):
    """Side-effect walker. Default action :class:`~lexic.ir.action.IrWalk`
    recurses into children and returns :data:`~lexic.ir.base.IrNone`."""

    default: IrSelf = IrWalk()


class IrTransformer[Iri: IrSelf, Ir_co: IrNode](IrDispatch[Iri, Ir_co]):
    """Rewrites IR trees. Default action :class:`~lexic.ir.action.IrRebuild`
    walks each node's children via ``d`` and rebuilds the node."""

    default: IrSelf = IrRebuild()


class IrBottomUp[Iri: IrSelf, Ir_co: IrNode](IrTransformer[Iri, Ir_co]):
    """Iterative post-order transformer — stack-safe at any tree depth.

    ``apply`` drives an explicit work stack instead of Python recursion:
    every node's children are transformed first, the node is rebuilt with
    them, and only then does its action body run — on a node whose children
    are already in final form (the transformed children also ride the ``nc``
    channel). Bodies are therefore pure per-node combiners and must NOT
    recurse (no ``d.eval`` on children); the default on a table miss is
    :class:`~lexic.ir.action.IrThis` (the driver's rebuild IS the identity
    transform).

    Trade-off vs :class:`IrTransformer`: the driver visits every node — a
    body cannot skip or lazily prune a subtree — so this preset fits
    whole-tree normal-form passes (canonicalize, name folding), not
    selective rewrites. A shared subtree (one object reachable twice)
    transforms once and splices everywhere it appeared.

    The driver walks the whole RECORD SPINE, models included — and the model
    layer is deliberately not IR-strict (its ergonomic concessions): an
    absent optional field is Python ``None``, a ``models``-mode field is a
    plain ``tuple``, and payload slots may hold classes or plain strings.
    The driver takes each for what it is — a plain tuple is transparent
    (elements walked, rebuilt as a tuple), everything else non-IR is an
    opaque leaf — and only genuine :class:`~lexic.ir.spine.spine.IrSelf`
    nodes are offered to the action table.
    """

    default: IrSelf = IrThis()

    def _descend(self, node: IrSelf) -> Sequence[IrSelf]:
        """Children the driver recurses into — an overridable strategy seam.

        Defaults to the node's own :meth:`~lexic.ir.base.IrSelf.children`.
        The record spine's model concessions ride the walk under the spine's
        own ``children()``/``rebuild()`` typing (the one cast lives at the
        model layer's seam, not here): a plain-tuple ``models`` field is
        transparent — its elements are walked — and any other payload value
        (``None``, a string, a class) is an opaque leaf. A pass that must
        treat some node as opaque (its subtree in a foreign domain the pass
        does not own) overrides this to return ``()`` for that node — the
        node is still visited and rebuilt, but its subtree is left verbatim.
        Mirrors the overridable ``_run`` seam.

        :param node: The node about to be expanded.
        :returns: The children to recurse into (``()`` to fence the subtree).
        """
        if isinstance(node, IrSelf):
            return node.children()
        if isinstance(node, tuple):
            return node
        return ()

    def _run(self, root: IrNode) -> Ir_co:
        """Post-order drive: transform children, rebuild, act — iteratively.

        Per-run fast paths keep the driver at recursive-walk cost: action
        bodies are resolved once per node *type* (a full miss on the
        :class:`~lexic.ir.action.IrThis` default skips the call entirely),
        and a node none of whose children changed is reused instead of
        rebuilt.

        :param root: Root IR node to transform.
        :returns: The transformed tree.
        """
        identity = isinstance(self.default, IrThis)
        bodies: dict[type, IrSelf | None] = {}
        done: dict[int, IrSelf] = {}
        stack: list[tuple[IrSelf, Sequence[IrSelf] | None]] = [(root, None)]
        while stack:
            node, kids = stack.pop()
            key = id(node)
            if key in done:
                continue
            if kids is None:  # first visit — expand children, revisit after
                kids = self._descend(node)
                if kids:
                    stack.append((node, kids))
                    # Reversed so pops run left-to-right: the visit order
                    # (and thus any stateful body's side-effect order, e.g.
                    # synthetic rule minting) matches the recursive walk's.
                    stack.extend((kid, None) for kid in reversed(kids))
                    continue
            new = tuple(done[id(kid)] for kid in kids)
            if all(a is b for a, b in zip(new, kids)):
                rebuilt = node
            elif isinstance(node, IrSelf):
                rebuilt = node.rebuild(new)
            else:
                # the model layer's plain-tuple field — rebuilt onto the
                # spine (an IrTuple IS a tuple, so the field contract holds)
                rebuilt = IrTuple(*new)
            if not isinstance(rebuilt, IrSelf):
                # a payload leaf (None, a string, a class) is never offered
                # to the table — it is the model layer's payload, not a node
                done[key] = rebuilt
                continue
            node_type = type(rebuilt)
            try:
                body = bodies[node_type]
            except KeyError:
                try:
                    body = self.actions[node_type]
                except KeyError:
                    resolved = self._resolve_miss(self.actions, rebuilt)
                    body = None if identity and resolved is self.default else resolved
                bodies[node_type] = body
            done[key] = rebuilt if body is None else body.eval(self, rebuilt, new)
        return cast(Ir_co, done[id(root)])


class IrEmitter[Iri: IrSelf, Ir_co: IrLiteral](IrDispatch[Iri, Ir_co]):
    """Produces :class:`~lexic.ir.grammar.nodes.IrLiteral` strings. Default body
    :class:`~lexic.ir.action.IrEmit`; override with ``default=IrRaise()``."""

    default: IrSelf = IrEmit()
