"""Action-algebra IrNodes.

Every class here is a plain :class:`IrNode` (via :class:`IrLeaf` /
:class:`IrCollection` / :class:`IrComposite`) that overrides ``eval`` to
do work other than identity. The action algebra adds operations the
grammar AST nodes don't cover: sibling lookup, joining, branching,
short-circuit, and procedural escape hatches.

All nodes inherit ``__call__ -> Self`` from :class:`IrSelf` (identity).
The value-producing protocol is ``eval(d, n, nc) -> Ir_co`` — every class
here overrides ``eval`` to produce its typed result. Pass :data:`IrNone`
to a slot that has no relevant value.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, ClassVar, Sequence

from lexic.ir.nodes import (
    IrCollection,
    IrComposite,
    IrLeaf,
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
        """Initialise with the value to surface to the dispatcher."""
        super().__init__()
        self.value = value


# ── Attribute reader ──────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class IrField[Ir_co: IrStr = IrStr](IrLeaf[Ir_co]):
    """Read a typed attribute from the dispatched node ``n``.

    Generic in ``Ir_co`` (bounded by :class:`IrStr`, defaulting to
    :class:`IrStr` itself). Output is wrapped via ``self.bound(value)``
    so it carries both ``str`` shape AND the IrSelf protocol.
    """

    name: str

    def eval(self, _d: IrSelf, n: IrSelf, _nc: Sequence[IrSelf], /) -> Ir_co:
        """Read ``getattr(n, self.name)`` and wrap via ``self.bound(value)``.

        For ``Ir_co=IrStr`` the wrap is ``IrStr(value)`` — a no-op on
        string-derived attributes, a stringification on non-string ones.
        """
        return self.bound(getattr(n, self.name))


# ── Procedural escape hatch ───────────────────────────────────────────


@dataclass(frozen=True, slots=True, eq=False)
class IrCallable[Ir_co : IrSelf](IrLeaf[Ir_co]):
    """Procedural body. ``handler(d, n, nc) -> Ir_co``.

    Generic in ``Ir_co``; callers narrow at construction:
    ``IrCallable[str](my_handler)``.
    """

    handler: Callable[[IrSelf, IrSelf, Sequence[IrSelf]], Ir_co]

    def eval(self, d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> Ir_co:
        """Forward to the wrapped handler."""
        return self.handler(d, n, nc)

    def _inner_str(self) -> str:
        """Reflect the handler's ``__name__`` for debug output."""
        name = getattr(self.handler, "__name__", "callable")
        return f"<{name}>"


# ── Sibling lookup ────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class IrChild[Ir_co : IrSelf](IrLeaf[Ir_co]):
    """Single dispatched child by name from ``n``'s ``_child_attrs``.

    ``Ir_co`` is the dispatcher's per-child result type — ``str`` under
    an emitter, ``IrNode`` under a transformer.

    :raises ValueError: if ``self.name`` is not in ``type(n)._child_attrs``.
    """

    name: str

    def eval(self, _d: IrSelf, n: IrSelf, new_children: Sequence[IrSelf], /) -> Ir_co:
        """Index into ``new_children`` at the position of ``self.name``."""
        attrs = getattr(type(n), "_child_attrs", ())
        try:
            idx = attrs.index(self.name)
            return self.bind(new_children[idx])
        except IndexError as exc:
            raise ValueError(
                f"IrChild({self.name!r}): {type(n).__name__} has no such child "
                f"(known: {attrs})"
            ) from exc


@dataclass(frozen=True, slots=True)
class IrChildren[Ir_co : IrSelf = IrSelf](IrLeaf[Ir_co]):
    """Full tuple of dispatched children from ``n``'s ``_items_attr``.

    ``Ir_co`` is the dispatcher's per-child result type. Return type is
    ``tuple[Ir_co, ...]`` — distinct from :class:`IrChild` at the type
    level.

    :raises ValueError: if ``self.name`` does not match ``type(n)._items_attr``.
    """

    name: str

    def eval(
        self,
        _d: IrSelf,
        n: IrSelf,
        new_children: Sequence[IrSelf],
        /,
    ) -> Ir_co:
        """Return ``new_children`` after checking it matches ``_items_attr``."""
        items_attr = getattr(type(n), "_items_attr", None)
        if items_attr != self.name:
            raise ValueError(
                f"IrChildren({self.name!r}): {type(n).__name__} _items_attr "
                f"is {items_attr!r}"
            )

        return self.bind(new_children)

# ── String concatenation ──────────────────────────────────────────────


@dataclass(frozen=True, slots=True, repr=False)
class IrConcat[Ir_co: IrStr = IrStr](IrCollection[Ir_co]):
    """Evaluate ``parts`` in order; return ``bound().join(...)`` of results.

    Generic in ``Ir_co`` (bounded by :class:`IrStr`, defaulting to
    :class:`IrStr`). The bound's neutral element (``IrStr()`` → ``""``)
    serves as the join base, and the bound's own ``.join`` is the
    type-native join — no casts needed.
    """

    _items_attr: ClassVar[str] = "parts"
    parts: IrTuple = IrTuple()

    def eval(self, d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> Ir_co:
        """Concatenate evaluated parts via the bound's neutral element."""
        return self.bound(self.bound().join(p.eval(d, n, nc) for p in self.parts))


# ── Variable-arity join with separator ────────────────────────────────


@dataclass(frozen=True, slots=True, repr=False)
class IrJoin[Ir_co: IrStr](IrComposite[Ir_co]):
    """Variable-arity join. Evaluate ``children_op`` to get an iterable,
    then join with ``separator``; fall back to ``empty`` when no items.

    Generic in ``Ir_co`` (bounded by :class:`IrType`, defaulting to
    :class:`IrStr`). ``separator`` and ``empty`` are ``IrNode[Ir_co]`` so
    both can be computed at eval time (``IrField``, ``IrCallable``,
    nested ``IrJoin``) rather than restricted to static values.
    """

    _child_attrs: ClassVar[tuple[str, ...]] = ("children_op", "separator", "empty")
    children_op: IrNode[Ir_co]
    separator: IrNode[Ir_co]
    empty: IrNode[Ir_co]

    def eval(self, d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> Ir_co:
        """Evaluate items; join with ``separator`` or return ``empty``."""
        items = self.children_op.eval(d, n, nc)
        if not items:
            return self.empty.eval(d, n, nc)
        sep = self.separator.eval(d, n, nc)
        return self.bound(self.bound(sep).join(items))


# ── Truthy-field branch ───────────────────────────────────────────────


@dataclass(frozen=True, slots=True, repr=False)
class IrCond[Ir_co : IrSelf](IrComposite[Ir_co]):
    """If ``bool(getattr(n, field))`` is true, evaluate ``then_op``;
    else ``else_op``. Both branches must share ``Ir_co``.
    """

    _child_attrs: ClassVar[tuple[str, ...]] = ("then_op", "else_op")
    field: str
    then_op: IrNode[Ir_co]
    else_op: IrNode[Ir_co]

    def eval(self, d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> Ir_co:
        """Branch on the truthiness of ``getattr(n, self.field)``."""
        branch = self.then_op if getattr(n, self.field) else self.else_op
        return branch.eval(d, n, nc)


# ── Short-circuit return ──────────────────────────────────────────────


@dataclass(frozen=True, slots=True, eq=False, repr=False)
class IrReturn[Ir_co](IrLeaf, _Return):
    """Short-circuit IR node that IS-A control-flow exception.

    ``IrReturn`` mixes :class:`IrLeaf` (structural IR contract) with
    :class:`_Return` (BaseException machinery). ``eval`` raises ``self``;
    the surrounding dispatcher catches the IrReturn instance and may
    surface ``self.value`` or the instance itself, depending on its
    return-shape contract.
    """

    value: Ir_co

    def __post_init__(self) -> None:
        """Initialise the BaseException machinery (``self.args``)."""
        BaseException.__init__(self)

    def eval(self, _d: IrSelf, _n: IrSelf, _nc: Sequence[IrSelf], /) -> Ir_co:
        """Raise ``self`` — unwinds to the dispatcher's catch."""
        raise self


# ── Default bodies ────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True, repr=False)
class IrPass(IrLeaf[IrSelf]):
    """No-op body — evaluates to :data:`IrNone`.

    Canonical body for visitor defaults: the dispatcher's action matched
    but there is nothing meaningful to produce. Equivalent to Python's
    ``pass``.
    """

    def eval(self, _d: IrSelf, _n: IrSelf, _nc: Sequence[IrSelf], /) -> IrSelf:
        """Return :data:`IrNone`."""
        return IrNone


@dataclass(frozen=True, slots=True, repr=False)
class IrRebuild(IrLeaf):
    """Walk ``n``'s children via ``d``, then rebuild ``n`` with the result.

    Canonical body for transformer defaults. Always rebuilds — change
    detection lives in callers if they want it.

    :raises: whatever ``d.eval`` or ``n.rebuild`` raises.
    """

    def eval(self, d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> IrSelf:
        """Walk ``n.children()`` via ``d`` (or accept ``nc``), then rebuild.

        :param d: Dispatcher driving child recursion.
        :param n: Node to rebuild. Runtime contract: ``IrNode``.
        :param nc: Pre-dispatched children, if any.
        :returns: ``n.rebuild(new_children)``.
        """
        new_children = nc or IrTuple(d.eval(d, c, ()) for c in n.children())
        return n.rebuild(new_children)


# ── Action binding ────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True, eq=False, repr=False)
class IrAction[Ir_co : IrSelf](IrComposite[Ir_co]):
    """Bind a target IR node type to a callable IrNode body.

    ``target_type`` is metadata (a concrete IR-node type, rendered in
    ``__str__`` but excluded from ``children()`` via ``_child_attrs``).
    ``body`` is the single IrNode child invoked under dispatch.
    """

    _child_attrs: ClassVar[tuple[str, ...]] = ("body",)
    target_type: type[IrSelf]
    body: IrNode[Ir_co]

    def eval(self, d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> Ir_co:
        """Delegate to the body."""
        return self.body.eval(d, n, nc)

    def _inner_str(self) -> str:
        """Render the target-type name plus the body."""
        return f"{self.target_type.__name__}, {self.body}"
