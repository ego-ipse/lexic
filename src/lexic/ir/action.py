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

import operator
from dataclasses import dataclass
from typing import Callable, ClassVar, Sequence

from lexic.exceptions import UnsupportedConstructError
from lexic.ir.nodes import (
    IrComposite,
    IrInt,
    IrLeaf,
    IrLiteral,
    IrNode,
    IrNone,
    IrScalar,
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
class IrField(IrComposite[IrSelf, IrScalar]):
    """Read a typed attribute from the dispatched node ``n`` and wrap it.

    The read value is wrapped via the **runtime** constructor ``out`` — a
    value-leaf type such as :class:`~lexic.ir.nodes.IrStr` / :class:`IrInt`
    (default ``IrStr``). Read an int with ``IrField("min", IrInt)``; the default
    ``out=IrStr`` keeps every existing ``IrField("name")`` caller unchanged.

    Cast-free and open: ``out`` is any ``type[IrScalar]`` — callable with the
    payload thanks to :meth:`IrScalar.__new__`, so ``self.out(value)``
    type-checks without a cast and a new ``IrScalar`` subtype needs no change
    here (no enumerated leaf-type union).

    A record-leaf: an :class:`IrComposite` with no IR-node children.
    """

    name: str
    out: type[IrScalar] = IrStr

    def eval(self, _d: IrSelf, n: IrSelf, _nc: Sequence[IrSelf], /) -> IrScalar:
        """Read ``getattr(n, self.name)`` and wrap via ``self.out(value)``.

        :param _d: Dispatcher (unused — no recursion).
        :param n: Node whose attribute to read.
        :param _nc: Pre-walked children (unused).
        :returns: The attribute value wrapped in ``self.out`` (an ``IrScalar``).
        """
        return self.out(getattr(n, self.name))


# ── Comparison ────────────────────────────────────────────────────────


class IrOp(IrStr):
    """Infix operator leaf — the node IS the operator string (e.g. ``IrOp(">")``).

    No enum: the operator is its own string, keyed directly into ``_OPS`` (an
    ``IrStr`` leaf matches its plain-``str`` key). ``eval`` applies the mapped
    builtin to the operands handed in as ``nc`` and returns the truth value as
    ``IrInt(0/1)`` — the consumer (:class:`IrCompare`) supplies both operands.
    """

    _OPS: ClassVar[dict[str, Callable[..., bool]]] = {
        "==": operator.eq,
        "<": operator.lt,
        ">": operator.gt,
        "<=": operator.le,
        ">=": operator.ge,
    }

    def eval(self, _d: IrSelf, _n: IrSelf, nc: Sequence[IrSelf], /) -> IrInt:
        """Apply this operator to the operands in ``nc``.

        :param _d: Dispatcher (unused).
        :param _n: Current node (unused).
        :param nc: The pre-evaluated operands (two, for a binary operator).
        :returns: ``IrInt(1)`` if the comparison holds, else ``IrInt(0)``.
        """
        return IrInt(self._OPS[self](*nc))


@dataclass(frozen=True, slots=True, repr=False)
class IrCompare[Iri: IrSelf](IrComposite[Iri, IrInt]):
    """Compare two operand nodes; eval to ``IrInt(1)`` (true) or ``IrInt(0)``.

    Evaluates ``left`` and ``right`` and hands the results to ``op`` (an
    :class:`IrOp`), which applies the comparison. A truth value is an ``IrInt``
    in ``{0, 1}`` — there is no ``IrBool``. Operands are typed ``IrSelf`` (not
    ``IrNode``): ``IrNode``'s ``Ir_co`` is invariant, so a value operand like
    ``IrField`` would not be assignable to a bare ``IrNode`` slot.

    :param Iri: the dispatcher input type.
    """

    _child_attrs: ClassVar[tuple[str, ...]] = ("left", "right")
    left: IrSelf
    op: IrOp
    right: IrSelf

    def eval(self, d: Iri, n: Iri, nc: Sequence[Iri], /) -> IrInt:
        """Evaluate both operands and apply ``self.op``.

        :param d: Dispatcher forwarded to each operand's ``eval``.
        :param n: Current node forwarded to each operand's ``eval``.
        :param nc: Pre-walked children forwarded to each operand's ``eval``.
        :returns: ``IrInt(1)`` if the comparison holds, else ``IrInt(0)``.
        """
        operands = (self.left.eval(d, n, nc), self.right.eval(d, n, nc))
        return self.op.eval(d, n, operands)


# ── Conjunction ───────────────────────────────────────────────────────


class IrAnd(IrTuple[IrSelf]):
    """Short-circuit conjunction — an :class:`~lexic.ir.nodes.IrTuple` subclass.

    The node IS its operand tuple. ``eval`` ANDs the truthiness of each
    evaluated operand, short-circuiting on the first falsy one, and yields
    ``IrInt(1)`` (all truthy / empty / vacuously true) or ``IrInt(0)``.
    Construct variadically: ``IrAnd(pred1, pred2, …)``.
    """

    __slots__ = ()

    def eval(self, d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> IrInt:
        """AND the truthiness of each evaluated operand, short-circuiting.

        :param d: Dispatcher forwarded to each operand's ``eval``.
        :param n: Current node forwarded to each operand's ``eval``.
        :param nc: Pre-walked children forwarded to each operand's ``eval``.
        :returns: ``IrInt(0)`` on the first falsy operand, else ``IrInt(1)``.
        """
        for part in self:
            if not part.eval(d, n, nc):
                return IrInt(0)
        return IrInt(1)


# ── Procedural escape hatch ───────────────────────────────────────────


@dataclass(frozen=True, slots=True, eq=False, repr=False)
class IrCallable[Iri: IrSelf = IrSelf, Ir_co: IrSelf = IrSelf](IrComposite[Iri, Ir_co]):
    """Procedural body. ``handler(d, n, nc) -> Ir_co``.

    The escape hatch for logic the algebra can't express. Generic in
    ``Ir_co``; callers narrow at construction: ``IrCallable[IrStr](handler)``.

    ``eq=False`` because callables are not value-comparable. A record-leaf:
    an :class:`IrComposite` with no IR-node children.

    :param Ir_co: the result type the handler produces.
    """

    handler: Callable[[Iri, Iri, Sequence[Iri]], Ir_co]

    def eval(self, d: Iri, n: Iri, nc: Sequence[Iri], /) -> Ir_co:
        """Forward to the wrapped handler.

        :param d: Dispatcher forwarded to the handler.
        :param n: Current node forwarded to the handler.
        :param nc: Pre-walked children forwarded to the handler.
        :returns: Whatever the handler returns.
        """
        return self.handler(d, n, nc)


# ── Sibling lookup ────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True, repr=False)
class IrChild[Iri: IrSelf, Ir_co: IrSelf](IrComposite[Iri, Ir_co]):
    """Single dispatched child by name from ``n``'s ``_child_attrs``.

    ``Ir_co`` is the dispatcher's per-child result type — ``IrStr`` under
    an emitter, ``IrNode`` under a transformer.

    A record-leaf: an :class:`IrComposite` with no IR-node children of its
    own (it resolves a child of the *dispatched* node ``n``, not its own).

    :param Ir_co: the dispatcher's per-child result type.
    :raises ValueError: if ``self.name`` is not in ``type(n)._child_attrs``.
    """

    name: str

    def eval(self, d: Iri, n: Iri, nc: Sequence[Iri], /) -> Ir_co:
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
class IrChildren[Iri: IrSelf, Ir_co: IrSelf = IrSelf](IrComposite[Iri, Ir_co]):
    """Full tuple of dispatched children of ``n`` (reads ``n.children()``).

    ``Ir_co`` is the dispatcher's per-child result type. The result is the
    whole children sequence — distinct from :class:`IrChild` at the type
    level.

    A record-leaf: an :class:`IrComposite` with no IR-node children of its
    own.

    :param Ir_co: the dispatcher's per-child result type.
    """

    def eval(self, d: Iri, n: Iri, nc: Sequence[Iri], /) -> Ir_co:
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
class IrConcat[Iri: IrSelf, Ir_co: IrStr = IrStr](IrComposite[Iri, Ir_co]):
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

    def eval(self, d: Iri, n: Iri, nc: Sequence[Iri], /) -> Ir_co:
        """Concatenate evaluated parts via the bound's neutral element.

        :param d: Dispatcher forwarded to each part's ``eval``.
        :param n: Current node forwarded to each part's ``eval``.
        :param nc: Pre-walked children forwarded to each part's ``eval``.
        :returns: The concatenation of all parts wrapped in ``self.bound``.
        """
        return self.bound(self.bound().join(p.eval(d, n, nc) for p in self.parts))


# ── Variable-arity join with separator ────────────────────────────────


@dataclass(frozen=True, slots=True, repr=False)
class IrJoin[Iri: IrSelf, Ir_co: IrStr = IrStr](IrComposite[Iri, Ir_co]):
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

    def eval(self, d: Iri, n: Iri, nc: Sequence[Iri], /) -> Ir_co:
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


# ── Conditional branch ────────────────────────────────────────────────


@dataclass(frozen=True, slots=True, repr=False)
class IrCond[Iri: IrSelf, Ir_co: IrSelf](IrComposite[Iri, Ir_co]):
    """If ``test`` evaluates truthy, evaluate ``then_op``; else ``else_op``.

    ``test`` is any node whose ``eval`` yields a truthy/falsy value (e.g.
    :class:`IrCompare`, :class:`IrAnd`). Typed ``IrSelf`` (not ``IrNode``) for
    the same reason as :class:`IrCompare`'s operands — ``IrNode``'s ``Ir_co`` is
    invariant, which rejects value operands like ``IrField``. Both branches
    share ``Ir_co``.

    :param Ir_co: the shared result type of both branches.
    """

    _child_attrs: ClassVar[tuple[str, ...]] = ("test", "then_op", "else_op")
    test: IrSelf
    then_op: IrSelf
    else_op: IrSelf

    def eval(self, d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> Ir_co:
        """Branch on the truthiness of ``self.test.eval(d, n, nc)``.

        :param d: Dispatcher forwarded to the test and the chosen branch.
        :param n: Current node forwarded to the test and the chosen branch.
        :param nc: Pre-walked children forwarded onward.
        :returns: The chosen branch's result.
        """
        branch = self.then_op if self.test.eval(d, n, nc) else self.else_op
        return branch.eval(d, n, nc)


# ── Default bodies ────────────────────────────────────────────────────


class IrThis(IrLeaf[IrSelf, IrSelf]):
    """Identity body — evaluates to the dispatched node ``n`` as-is.

    Use when an action matches and the dispatcher's return-shape contract
    is satisfied by the dispatched node itself. Equivalent to Python's
    ``lambda d, n, nc: n``.
    """

    __slots__ = ()

    def eval(self, _d: IrSelf, n: IrSelf, _nc: Sequence[IrSelf], /) -> IrSelf:
        """Return the dispatched node ``n``.

        :param _d: Dispatcher (unused).
        :param n: Node to return as-is.
        :param _nc: Pre-walked children (unused).
        :returns: The dispatched node ``n``.
        """
        return n


class IrPass(IrLeaf[IrSelf, IrSelf]):
    """No-op body — evaluates to :data:`IrNone` without recursing.

    Use when an action matches but neither a value nor a child walk is
    desired. Equivalent to Python's ``pass``. Not the default for
    :class:`~lexic.ir.walk.IrVisitor` — that role belongs to
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


class IrWalk(IrLeaf[IrSelf, IrSelf]):
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


class IrEmit[Iri: IrSelf, Ir_co: IrLiteral](IrLeaf[Iri, Ir_co]):
    """Body that emits ``IrLiteral(str(n))`` for the dispatched node.

    Default body for :class:`~lexic.ir.walk.IrEmitter`. Stringifies
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

    Strict-default body for :class:`~lexic.ir.walk.IrDispatch`. When
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

    value: object = (
        IrThis()
    )  # default to the dispatched node itself when no value is given
    lazy_eval: bool = True

    def __post_init__(self) -> None:
        """Initialise the BaseException machinery (``self.args``)."""
        BaseException.__init__(self)

    def eval(self, d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> Ir_co:
        """Raise ``self`` — unwinds to the dispatcher's catch.

        :param _d: Dispatcher (unused).
        :param _n: Node (unused).
        :param _nc: Pre-walked children (unused).
        :returns: Never returns normally.
        :raises IrReturn: Always — raises ``self``.
        """

        if self.lazy_eval and isinstance(self.value, IrSelf):
            raise self.__class__(self.value.eval(d, n, nc))
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
