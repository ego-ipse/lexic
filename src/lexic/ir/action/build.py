"""Build — producing a node from the pieces.

Construction and dispatch: applying a constructor, rebuilding a node, walking
one, emitting, raising, and ``IrAction`` binding a type to a body.
"""

from __future__ import annotations

from typing import ClassVar, Sequence

from lexic.exceptions import UnsupportedConstructError
from lexic.ir.grammar.nodes import IrLiteral
from lexic.ir.spine.spine import IrLeaf, IrNode, IrNone, IrSelf
from lexic.ir.spine.records import IrNamedTuple, IrTuple


class IrApply[Ir_co: IrSelf](IrNamedTuple[IrTuple]):
    """Delegation — re-dispatch the current focus ``n`` with arguments.

    Evaluates each element of ``args`` against the current context, then
    dispatches ``n`` itself through ``d`` with the results as the argument
    channel. The node's own action runs and decides what the received
    arguments mean — e.g. a negation mark spliced into a class's brackets
    via :class:`IrArgs`. Carries no selector: compose with :class:`IrAt`
    to aim the delegation at an operand.

    :param Ir_co: the dispatched action's result type.
    """

    _child_attrs: ClassVar[tuple[str, ...]] = ("args",)
    args: IrTuple = IrTuple()

    def eval(self, d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> Ir_co:
        """Dispatch ``n`` via ``d`` with the evaluated ``args`` as the channel.

        :param d: Dispatcher resolving ``n``'s own action.
        :param n: The focus to re-dispatch.
        :param nc: Current arguments, forwarded while evaluating ``args``.
        :returns: The dispatched action's result.
        """
        evaluated = IrTuple(*(a.eval(d, n, nc) for a in self.args))
        return d.eval(d, n, evaluated)


class IrBuild(IrNamedTuple[type[IrSelf], IrSelf]):
    """Construct ``target`` from the argument channel.

    ``args=IrNone`` (default) splats the raw channel — ``target(*nc)``; an
    ``args`` body reshapes it first — ``target(*args.eval(...))``.
    """

    _child_attrs: ClassVar[tuple[str, ...]] = ("args",)
    target: type[IrSelf]
    args: IrSelf = IrNone

    def eval(self, d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> IrSelf:
        """Construct ``target`` from raw ``nc`` or the evaluated ``args``."""
        return self.target(*(nc if self.args is IrNone else self.args.eval(d, n, nc)))


class IrWalk(IrLeaf[IrSelf, IrSelf]):
    """Walk ``n``'s children via ``d``; return :data:`IrNone`.

    Canonical body for visitor defaults — the visitor analogue of
    :class:`IrRebuild`. Side-effect-only: child results are dispatched
    for their effects and discarded. Honours ``nc``: if the caller has
    already dispatched children, no re-walk happens.
    """

    def eval(self, d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> IrSelf:
        """Walk children unless they were pre-dispatched; return :data:`IrNone`.

        :param d: Dispatcher driving child recursion.
        :param n: Node whose children to walk. Runtime contract: ``IrNode``.
        :param nc: Pre-dispatched children, if any — skips the walk when truthy.
        :returns: :data:`IrNone`.
        """
        if not nc:
            for c in n.children():
                d.eval(d, c, ())
        return IrNone


class IrEmit[Iri: IrSelf, Ir_co: IrLiteral](IrLeaf[Iri, Ir_co]):
    """Body that emits ``IrLiteral(str(n))`` for the dispatched node.

    Default body for :class:`~lexic.ir.action.walk.IrEmitter`. Stringifies
    ``n`` via its ``__str__`` (str-leaves ARE their value; other nodes fall
    back to their str form) and wraps the result as an :class:`IrLiteral`.
    Override an emitter's ``default`` with :class:`IrRaise` to refuse
    unmatched types instead.

    A plain ``__slots__`` leaf with an explicit ``_bound`` (no PEP 695 type
    parameter carries the bound at construction here, so it is declared).

    :param Ir_co: the :class:`IrLiteral`-typed result type.
    """

    _bound: ClassVar[type] = IrLiteral

    def eval(self, _d: IrSelf, n: IrSelf, _nc: Sequence[IrSelf], /) -> Ir_co:
        """Return ``IrLiteral(str(n))``.

        :param _d: Dispatcher (unused).
        :param n: The dispatched node.
        :param _nc: Pre-walked children (unused).
        :returns: ``IrLiteral`` wrapping the node's string form.
        """
        return self.bound(str(n))


class IrRebuild(IrLeaf[IrSelf, IrNode]):
    """Walk ``n``'s children via ``d``, then rebuild ``n`` with the result.

    Canonical body for transformer defaults. Always rebuilds — change
    detection lives in callers if they want it.

    A plain ``__slots__`` leaf. ``n`` is
    narrowed with an explicit :func:`isinstance` guard that raises
    :exc:`~lexic.exceptions.UnsupportedConstructError` — no suppression
    (matches the codebase's "explicit raise in every dispatch path" rule).

    :raises UnsupportedConstructError: if ``n`` is not an :class:`IrNode`.
    """

    def eval(self, d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> IrNode:
        """Walk ``n.children()`` via ``d`` (or accept ``nc``), then rebuild.

        :param d: Dispatcher driving child recursion.
        :param n: Node to rebuild. Must be an :class:`IrNode`.
        :param nc: Pre-dispatched children, if any.
        :returns: ``n.rebuild(new_children)``.
        :raises UnsupportedConstructError: if ``n`` is not an :class:`IrNode`.
        """
        if not isinstance(n, IrNode):  # narrow: only IrNodes can be rebuilt
            raise UnsupportedConstructError(
                f"IrRebuild: cannot rebuild {type(n).__name__}"
            )
        new_children = nc or IrTuple(*(d.eval(d, c, ()) for c in n.children()))
        return n.rebuild(new_children)


class IrRaise[Ir_co: IrSelf](IrNamedTuple[type[BaseException], str]):
    """Body that raises a configured exception on dispatch.

    Strict-default body for :class:`~lexic.ir.action.walk.IrDispatch`. When
    no action in the dispatcher's table matches ``type(n).__mro__``,
    the dispatcher falls through to ``self.default`` — when that is
    :class:`IrRaise`, this body raises ``exc_type`` with a formatted
    message. The default ``exc_type`` is
    :exc:`~lexic.exceptions.UnsupportedConstructError`.

    :param Ir_co: the (never-produced) result type.
    :param exc_type: Exception class to raise.
    :param message: ``str.format``-style template. Substitutions:
        ``{dispatcher}`` → ``type(d).__name__``; ``{node_type}`` →
        ``type(n).__name__``.
    """

    exc_type: type[BaseException] = UnsupportedConstructError
    message: str = "{dispatcher}: no action for {node_type!r}"

    def eval(self, d: IrSelf, n: IrSelf, _nc: Sequence[IrSelf], /) -> Ir_co:
        """Raise ``self.exc_type`` with the formatted message.

        :param d: Dispatcher driving the walk.
        :param n: Node whose type had no matching action.
        :param _nc: Pre-walked children (unused).
        :returns: Never returns normally.
        :raises BaseException: Always — an instance of ``self.exc_type``.
        """
        raise self.exc_type(
            self.message.format(
                dispatcher=type(d).__name__,
                node_type=type(n).__name__,
            )
        )


class IrAction[Ir_co: IrSelf](IrNamedTuple[type[IrSelf], IrSelf]):
    """Bind a target IR node type to a callable IrNode body.

    ``target_type`` is metadata (a concrete IR-node type, scalar payload
    excluded from ``children()`` via ``_child_attrs``); the class-aware repr
    renders it as a bare name. ``body`` is the single IrNode child invoked
    under dispatch.

    :param Ir_co: the result type the body produces.
    """

    _child_attrs: ClassVar[tuple[str, ...]] = ("body",)
    target_type: type[IrSelf]
    body: IrSelf

    def eval(self, d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> Ir_co:
        """Delegate to the body.

        :param d: Dispatcher forwarded to the body's ``eval``.
        :param n: Current node forwarded to the body's ``eval``.
        :param nc: Pre-walked children forwarded to the body's ``eval``.
        :returns: The body's result.
        """
        return self.body.eval(d, n, nc)
