"""Action-algebra IrNodes — primitive-node model.

Every class here is a plain :class:`IrNode` (via :class:`IrLeaf` /
:class:`IrComposite`) that overrides ``eval`` to do work other than
identity. The action algebra adds operations the grammar AST nodes don't
cover: attribute reads, sibling lookup, joining, branching, short-circuit,
and a procedural escape hatch.

All nodes inherit ``__call__ -> Self`` from :class:`IrSelf` (identity).
The value-producing protocol is ``eval(d, n, nc) -> Ir_co`` — every class
here overrides ``eval`` to produce its typed result. Pass :data:`IrNone`
to a slot that has no relevant value.

**Node-shape note (G3):** record-leaf actions (``IrField``, ``IrCallable``,
``IrChild``, ``IrChildren``) and the string/branch operators (``IrConcat``,
``IrJoin``, ``IrCond``) are :class:`IrComposite` dataclasses — the sole
dataclass base in the primitive model. The default bodies (``IrPass``,
``IrWalk``, ``IrEmit``, ``IrRebuild``) are plain ``__slots__``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, ClassVar, Sequence

from lexic.exceptions import UnsupportedConstructError
from lexic.ir.nodes_2 import (
    IrComposite,
    IrLeaf,
    IrLiteral,
    IrNode,
    IrNone,
    IrSelf,
    IrStr,
    IrTuple,
)

# ── Control-flow exception ────────────────────────────────────────────


class _Return(BaseException):
    """Control-flow exception raised by :class:`IrReturn`.

    Inherits :class:`BaseException` (not :class:`Exception`) so
    :class:`IrCallable` bodies that wrap their work in
    ``except Exception:`` cannot swallow it.
    """

    def __init__(self, value: object) -> None:
        """Initialise with the value to surface to the dispatcher.

        :param value: The value carried out to the catching dispatcher.
        """
        super().__init__()
        self.value = value


# ── Attribute reader ──────────────────────────────────────────────────


@dataclass(frozen=True, slots=True, repr=False)
class IrField[Ir_co: IrStr = IrStr](IrComposite[Ir_co]):
    """Read a typed attribute from the dispatched node ``n``.

    Generic in ``Ir_co`` (bounded by :class:`IrStr`, defaulting to
    :class:`IrStr` itself). Output is wrapped via ``self.bound(value)``
    so it carries both ``str`` shape AND the IrSelf protocol.

    Use ``IrField`` only where a node has a *named* field to read (e.g.
    ``IrField("name")`` on an :class:`~lexic.ir.nodes_2.IrRule`). A
    str-leaf that IS its own value should be emitted directly via
    :class:`IrEmit` instead.

    A record-leaf: an :class:`IrComposite` with ``_child_attrs = ()`` (the
    inherited default), so it carries no IR-node children.

    :param Ir_co: the str-typed result type (defaults to :class:`IrStr`).
    """

    name: str

    def eval(self, _d: IrSelf, n: IrSelf, _nc: Sequence[IrSelf], /) -> Ir_co:
        """Read ``getattr(n, self.name)`` and wrap via ``self.bound(value)``.

        For ``Ir_co=IrStr`` the wrap is ``IrStr(value)`` — a no-op on
        string-derived attributes, a stringification on non-string ones.

        :param _d: Dispatcher (unused — no recursion).
        :param n: Node whose attribute to read.
        :param _nc: Pre-walked children (unused).
        :returns: The attribute value wrapped in ``self.bound``.
        """
        return self.bound(getattr(n, self.name))


# ── Procedural escape hatch ───────────────────────────────────────────


@dataclass(frozen=True, slots=True, eq=False, repr=False)
class IrCallable[Ir_co: IrSelf](IrComposite[Ir_co]):
    """Procedural body. ``handler(d, n, nc) -> Ir_co``.

    The escape hatch for logic the algebra can't express. Generic in
    ``Ir_co``; callers narrow at construction: ``IrCallable[IrStr](handler)``.

    ``eq=False`` because callables are not value-comparable. A record-leaf:
    an :class:`IrComposite` with no IR-node children.

    :param Ir_co: the result type the handler produces.
    """

    handler: Callable[[IrSelf, IrSelf, Sequence[IrSelf]], Ir_co]

    def eval(self, d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> Ir_co:
        """Forward to the wrapped handler.

        :param d: Dispatcher forwarded to the handler.
        :param n: Current node forwarded to the handler.
        :param nc: Pre-walked children forwarded to the handler.
        :returns: Whatever the handler returns.
        """
        return self.handler(d, n, nc)


# ── Sibling lookup ────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True, repr=False)
class IrChild[Ir_co: IrSelf](IrComposite[Ir_co]):
    """Single dispatched child by name from ``n``'s ``_child_attrs``.

    ``Ir_co`` is the dispatcher's per-child result type — ``IrStr`` under
    an emitter, ``IrNode`` under a transformer.

    A record-leaf: an :class:`IrComposite` with no IR-node children of its
    own (it resolves a child of the *dispatched* node ``n``, not its own).

    :param Ir_co: the dispatcher's per-child result type.
    :raises ValueError: if ``self.name`` is not in ``type(n)._child_attrs``.
    """

    name: str

    def eval(self, d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> Ir_co:
        """Resolve the named child.

        Hybrid: eager when ``nc`` is populated (caller pre-walked) — index
        into it; lazy otherwise — dispatch the looked-up child via ``d``.

        :param d: Dispatcher used for lazy sub-dispatch.
        :param n: Node whose child to resolve.
        :param nc: Pre-walked children, if any.
        :returns: The resolved child, type-checked against ``self.bound``.
        :raises ValueError: if ``self.name`` is not in ``type(n)._child_attrs``.
        """
        attrs = getattr(type(n), "_child_attrs", ())
        try:
            idx = attrs.index(self.name)
        except ValueError as exc:
            raise ValueError(
                f"IrChild({self.name!r}): {type(n).__name__} has no such child "
                f"(known: {attrs})"
            ) from exc
        if nc:
            return self.bind(nc[idx])
        return self.bind(d.eval(d, n.children()[idx], IrTuple()))


@dataclass(frozen=True, slots=True, repr=False)
class IrChildren[Ir_co: IrSelf = IrSelf](IrComposite[Ir_co]):
    """Full tuple of dispatched children of ``n`` (reads ``n.children()``).

    ``Ir_co`` is the dispatcher's per-child result type. The result is the
    whole children sequence — distinct from :class:`IrChild` at the type
    level.

    **R2:** ``IrChildren`` carries no ``name`` argument. With the old
    ``IrCollection``/``_items_attr`` removed there is nothing to validate
    against — ``IrChildren`` reads ``n.children()`` regardless, so the name
    was inert.

    A record-leaf: an :class:`IrComposite` with no IR-node children of its
    own.

    :param Ir_co: the dispatcher's per-child result type.
    """

    def eval(self, d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> Ir_co:
        """Resolve the children collection.

        Hybrid: eager when ``nc`` is populated (caller pre-walked) — return
        it as-is; lazy otherwise — dispatch each child via ``d``.

        :param d: Dispatcher used for lazy per-child sub-dispatch.
        :param n: Node whose children to resolve.
        :param nc: Pre-walked children, if any.
        :returns: The children sequence, type-checked against ``self.bound``.
        """
        if nc:
            return self.bind(nc)
        return self.bind(IrTuple(*(d.eval(d, c, IrTuple()) for c in n.children())))


# ── String concatenation ──────────────────────────────────────────────


@dataclass(frozen=True, slots=True, repr=False)
class IrConcat[Ir_co: IrStr = IrStr](IrComposite[Ir_co]):
    """Evaluate ``parts`` in order; return ``bound().join(...)`` of results.

    Generic in ``Ir_co`` (bounded by :class:`IrStr`, defaulting to
    :class:`IrStr`). The bound's neutral element (``IrStr()`` → ``""``)
    serves as the join base, and the bound's own ``.join`` is the
    type-native join — no casts needed.

    **Shape note (Task 6):** ``IrConcat`` is an :class:`IrComposite` holding
    ``parts: IrTuple``, NOT an :class:`IrTuple` subclass. The
    generic-``+``-``IrTuple`` form breaks ``bound`` under pyright (the dual
    generic lineage ``Ir_co: IrStr`` vs inherited ``IrTuple[IrSelf]`` makes
    ``self.bound().join(...)`` error). The composite form matches
    :class:`IrJoin` and is pyright-clean.

    :param Ir_co: the str-typed result type (defaults to :class:`IrStr`).
    """

    _child_attrs: ClassVar[tuple[str, ...]] = ("parts",)
    parts: IrTuple = IrTuple()

    def eval(self, d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> Ir_co:
        """Concatenate evaluated parts via the bound's neutral element.

        :param d: Dispatcher forwarded to each part's ``eval``.
        :param n: Current node forwarded to each part's ``eval``.
        :param nc: Pre-walked children forwarded to each part's ``eval``.
        :returns: The concatenation of all parts wrapped in ``self.bound``.
        """
        return self.bound(self.bound().join(p.eval(d, n, nc) for p in self.parts))


# ── Variable-arity join with separator ────────────────────────────────


@dataclass(frozen=True, slots=True, repr=False)
class IrJoin[Ir_co: IrStr = IrStr](IrComposite[Ir_co]):
    r"""Evaluate ``parts``; join results with ``separator``, fall back to
    ``empty`` when ``parts`` evaluates empty.

    All three children are :class:`IrNode`\\ s and participate in tree
    walks / rebuilds. ``parts`` is typically an :class:`IrTuple` (itself an
    IrNode); ``separator`` and ``empty`` are arbitrary IrNodes computed at
    eval time.

    :param Ir_co: the str-typed result type (defaults to :class:`IrStr`).
    """

    _child_attrs: ClassVar[tuple[str, ...]] = ("parts", "separator", "empty")
    parts: IrSelf = IrTuple()
    separator: IrSelf = IrLiteral("")
    empty: IrSelf = IrLiteral("")

    def eval(self, d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> Ir_co:
        """Evaluate ``parts``; join or return the empty fallback.

        :param d: Dispatcher forwarded to each child's ``eval``.
        :param n: Current node forwarded to each child's ``eval``.
        :param nc: Pre-walked children forwarded to each child's ``eval``.
        :returns: The separator-joined parts, or ``empty`` when parts is empty.
        """
        rendered = self.parts.eval(d, n, nc)
        if not rendered:
            return self.empty.eval(d, n, nc)
        sep = self.separator.eval(d, n, nc)
        return self.bound(self.bound(sep).join(rendered))


# ── Truthy-field branch ───────────────────────────────────────────────


@dataclass(frozen=True, slots=True, repr=False)
class IrCond[Ir_co: IrSelf](IrComposite[Ir_co]):
    """If ``bool(getattr(n, field))`` is true, evaluate ``then_op``;
    else ``else_op``. Both branches must share ``Ir_co``.

    :param Ir_co: the shared result type of both branches.
    """

    _child_attrs: ClassVar[tuple[str, ...]] = ("then_op", "else_op")
    field: str
    then_op: IrSelf
    else_op: IrSelf

    def eval(self, d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> Ir_co:
        """Branch on the truthiness of ``getattr(n, self.field)``.

        :param d: Dispatcher forwarded to the chosen branch's ``eval``.
        :param n: Node whose ``field`` attribute selects the branch.
        :param nc: Pre-walked children forwarded to the chosen branch.
        :returns: The chosen branch's result.
        """
        branch = self.then_op if getattr(n, self.field) else self.else_op
        return branch.eval(d, n, nc)


# ── Default bodies ────────────────────────────────────────────────────


class IrPass(IrLeaf[IrSelf]):
    """No-op body — evaluates to :data:`IrNone` without recursing.

    Use when an action matches but neither a value nor a child walk is
    desired. Equivalent to Python's ``pass``. Not the default for
    :class:`~lexic.ir.walk_2.IrVisitor` — that role belongs to
    :class:`IrWalk`.
    """

    __slots__ = ()

    def eval(self, _d: IrSelf, _n: IrSelf, _nc: Sequence[IrSelf], /) -> IrSelf:
        """Return :data:`IrNone`.

        :param _d: Dispatcher (unused).
        :param _n: Node (unused).
        :param _nc: Pre-walked children (unused).
        :returns: :data:`IrNone`.
        """
        return IrNone


class IrWalk(IrLeaf[IrSelf]):
    """Walk ``n``'s children via ``d``; return :data:`IrNone`.

    Canonical body for visitor defaults — the visitor analogue of
    :class:`IrRebuild`. Side-effect-only: child results are dispatched
    for their effects and discarded. Honours ``nc``: if the caller has
    already dispatched children, no re-walk happens.
    """

    __slots__ = ()

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


class IrEmit[Ir_co: IrLiteral](IrLeaf[Ir_co]):
    """Body that emits ``IrLiteral(str(n))`` for the dispatched node.

    Default body for :class:`~lexic.ir.walk_2.IrEmitter`. Stringifies
    ``n`` via its ``__str__`` (str-leaves ARE their value; other nodes fall
    back to their str form) and wraps the result as an :class:`IrLiteral`.
    Override an emitter's ``default`` with :class:`IrRaise` to refuse
    unmatched types instead.

    A plain ``__slots__`` leaf with an explicit ``_bound`` (no PEP 695 type
    parameter carries the bound at construction here, so it is declared).

    :param Ir_co: the :class:`IrLiteral`-typed result type.
    """

    __slots__ = ()
    _bound: ClassVar[type] = IrLiteral

    def eval(self, _d: IrSelf, n: IrSelf, _nc: Sequence[IrSelf], /) -> Ir_co:
        """Return ``IrLiteral(str(n))``.

        :param _d: Dispatcher (unused).
        :param n: The dispatched node.
        :param _nc: Pre-walked children (unused).
        :returns: ``IrLiteral`` wrapping the node's string form.
        """
        return self.bound(str(n))


class IrRebuild(IrLeaf[IrNode]):
    """Walk ``n``'s children via ``d``, then rebuild ``n`` with the result.

    Canonical body for transformer defaults. Always rebuilds — change
    detection lives in callers if they want it.

    A plain ``__slots__`` leaf. ``n`` is
    narrowed with an explicit :func:`isinstance` guard that raises
    :exc:`~lexic.exceptions.UnsupportedConstructError` — no suppression
    (matches the codebase's "explicit raise in every dispatch path" rule).

    :raises UnsupportedConstructError: if ``n`` is not an :class:`IrNode`.
    """

    __slots__ = ()

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


# ── Strict default ────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True, repr=False)
class IrRaise[Ir_co: IrSelf](IrComposite[Ir_co]):
    """Body that raises a configured exception on dispatch.

    Strict-default body for :class:`~lexic.ir.walk_2.IrDispatch`. When
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


# ── Short-circuit return ──────────────────────────────────────────────


@dataclass(frozen=True, slots=True, eq=False, repr=False)
class IrReturn[Ir_co: IrSelf](IrComposite[Ir_co], _Return):
    """Short-circuit IR node that IS-A control-flow exception.

    ``IrReturn`` mixes :class:`IrComposite` (structural IR contract) with
    :class:`_Return` (BaseException machinery). ``eval`` raises ``self``;
    the surrounding dispatcher catches the IrReturn instance and may
    surface ``self.value`` or the instance itself, depending on its
    return-shape contract.

    ``eq=False`` because ``BaseException`` identity semantics take
    precedence over dataclass value equality.

    :param Ir_co: the type of the carried value.
    """

    value: Ir_co

    def __post_init__(self) -> None:
        """Initialise the BaseException machinery (``self.args``)."""
        BaseException.__init__(self)

    def eval(self, _d: IrSelf, _n: IrSelf, _nc: Sequence[IrSelf], /) -> Ir_co:
        """Raise ``self`` — unwinds to the dispatcher's catch.

        :param _d: Dispatcher (unused).
        :param _n: Node (unused).
        :param _nc: Pre-walked children (unused).
        :returns: Never returns normally.
        :raises IrReturn: Always — raises ``self``.
        """
        raise self


# ── Action binding ────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True, eq=False, repr=False)
class IrAction[Ir_co: IrSelf](IrComposite[Ir_co]):
    """Bind a target IR node type to a callable IrNode body.

    ``target_type`` is metadata (a concrete IR-node type, excluded from
    ``children()`` via ``_child_attrs``). ``body`` is the single IrNode
    child invoked under dispatch.

    ``eq=False`` because ``target_type`` is a class object and ``body`` may
    be a non-comparable :class:`IrCallable`.

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
