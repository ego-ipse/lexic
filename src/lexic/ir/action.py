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
from typing import Callable, ClassVar, cast

from lexic.ir.nodes import (
    IrCollection,
    IrComposite,
    IrLeaf,
    IrNode,
    IrSelf,
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
class IrField[Ir_co: str = str](IrLeaf[Ir_co]):
    """Read a ``str``-typed attribute from the dispatched node ``n``.

    Generic in ``Ir_co`` (bounded by ``str``, defaulting to ``str``) so
    narrower string types (``LiteralString``, branded ``NewType`` over
    ``str``) thread through the result.
    """

    name: Ir_co

    def eval(self, _d: IrSelf, n: IrSelf, _nc: tuple, /) -> Ir_co:
        """Read ``getattr(n, self.name)`` and coerce via ``self.bound(value)``.

        For ``Ir_co=str`` the coercion is ``str(value)`` — a no-op on string
        attributes, a stringification on non-string attributes (``True`` →
        ``"True"``).
        """
        return self.bound(getattr(n, self.name))


# ── Procedural escape hatch ───────────────────────────────────────────


@dataclass(frozen=True, slots=True, eq=False)
class IrCallable[Ir_co = IrSelf](IrLeaf[Ir_co]):
    """Procedural body. ``handler(d, n, nc) -> Ir_co``.

    Generic in ``Ir_co``; callers narrow at construction:
    ``IrCallable[str](my_handler)``.
    """

    handler: Callable[[IrSelf, IrSelf, tuple], Ir_co]

    def eval(self, d: IrSelf, n: IrSelf, nc: tuple, /) -> Ir_co:
        """Forward to the wrapped handler."""
        return self.handler(d, n, nc)

    def _inner_str(self) -> str:
        """Reflect the handler's ``__name__`` for debug output."""
        name = getattr(self.handler, "__name__", "callable")
        return f"<{name}>"


# ── Sibling lookup ────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class IrChild[Ir_co = IrSelf](IrLeaf[Ir_co]):
    """Single dispatched child by name from ``n``'s ``_child_attrs``.

    ``Ir_co`` is the dispatcher's per-child result type — ``str`` under
    an emitter, ``IrNode`` under a transformer.

    :raises ValueError: if ``self.name`` is not in ``type(n)._child_attrs``.
    """

    name: str

    def eval(self, _d: IrSelf, n: IrSelf, new_children: tuple, /) -> Ir_co:
        """Index into ``new_children`` at the position of ``self.name``."""
        attrs = getattr(type(n), "_child_attrs", ())
        try:
            idx = attrs.index(self.name)
        except ValueError as exc:
            raise ValueError(
                f"IrChild({self.name!r}): {type(n).__name__} has no such child "
                f"(known: {attrs})"
            ) from exc
        return new_children[idx]


@dataclass(frozen=True, slots=True)
class IrChildren[Ir_co = IrSelf](IrLeaf[tuple[Ir_co, ...]]):
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
        new_children: tuple,
        /,
    ) -> tuple[Ir_co, ...]:
        """Return ``new_children`` after checking it matches ``_items_attr``."""
        items_attr = getattr(type(n), "_items_attr", None)
        if items_attr != self.name:
            raise ValueError(
                f"IrChildren({self.name!r}): {type(n).__name__} _items_attr "
                f"is {items_attr!r}"
            )
        return new_children


# ── String concatenation ──────────────────────────────────────────────


@dataclass(frozen=True, slots=True, repr=False)
class IrConcat[Ir_co: str = str](IrCollection[Ir_co]):
    """Evaluate ``parts`` in order; return ``empty.join(...)`` of results.

    Generic in ``Ir_co`` (bounded by ``str``, defaulting to ``str``).
    ``empty`` is the neutral string used as the join base — its concrete
    type determines the ``Ir_co`` of the result, avoiding any
    runtime/type-system bridging.
    """

    _items_attr: ClassVar[str] = "parts"
    parts: tuple[IrNode[Ir_co], ...] = ()

    def eval(self, d: IrSelf, n: IrSelf, nc: tuple, /) -> Ir_co:
        """Concatenate evaluated parts using the bound's empty literal."""
        return cast(Ir_co, self.bound().join(p.eval(d, n, nc) for p in self.parts))


# ── Variable-arity join with separator ────────────────────────────────


@dataclass(frozen=True, slots=True, repr=False)
class IrJoin[Ir_co: str = str](IrComposite[Ir_co]):
    """Variable-arity join. Evaluate ``children_op`` to get an iterable,
    then join with ``separator``; fall back to ``empty`` when no items.

    Generic in ``Ir_co`` (bounded by ``str``, defaulting to ``str``).
    ``separator`` and ``empty`` are ``IrNode[Ir_co]`` rather than concrete
    ``IrLiteral`` so the separator or fallback can be computed
    (``IrField``, ``IrCallable``, …) — not just a static literal.
    """

    _child_attrs: ClassVar[tuple[str, ...]] = ("children_op", "separator", "empty")
    children_op: IrNode[tuple[Ir_co, ...]]
    separator: IrNode[Ir_co]
    empty: IrNode[Ir_co]

    def eval(self, d: IrSelf, n: IrSelf, nc: tuple, /) -> Ir_co:
        """Evaluate items; join with ``separator`` or return ``empty``."""
        items = self.children_op.eval(d, n, nc)
        if not items:
            return self.empty.eval(d, n, nc)
        sep: Ir_co = self.separator.eval(d, n, nc)
        return cast(Ir_co, self.bound.join(sep, items))


# ── Truthy-field branch ───────────────────────────────────────────────


@dataclass(frozen=True, slots=True, repr=False)
class IrCond[Ir_co = IrSelf](IrComposite[Ir_co]):
    """If ``bool(getattr(n, field))`` is true, evaluate ``then_op``;
    else ``else_op``. Both branches must share ``Ir_co``.
    """

    _child_attrs: ClassVar[tuple[str, ...]] = ("then_op", "else_op")
    field: str
    then_op: IrNode[Ir_co]
    else_op: IrNode[Ir_co]

    def eval(self, d: IrSelf, n: IrSelf, nc: tuple, /) -> Ir_co:
        """Branch on the truthiness of ``getattr(n, self.field)``."""
        branch = self.then_op if getattr(n, self.field) else self.else_op
        return branch.eval(d, n, nc)


# ── Short-circuit return ──────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class IrReturn[Ir_co = IrSelf](IrLeaf[Ir_co]):
    """Short-circuit. Evaluating raises ``_Return(self.value)``.

    ``Ir_co`` is the static return type the surrounding dispatcher will
    yield once it catches the ``_Return``; ``eval`` never returns
    normally.
    """

    value: Ir_co

    def eval(self, _d: IrSelf, _n: IrSelf, _nc: tuple, /) -> Ir_co:
        """Raise :class:`_Return` carrying ``self.value``."""
        raise _Return(self.value)


# ── Action binding ────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True, eq=False, repr=False)
class IrAction[Ir_co = IrSelf](IrComposite[Ir_co]):
    """Bind a target IR node type to a callable IrNode body.

    ``target_type`` is metadata (a concrete IR-node type, rendered in
    ``__str__`` but excluded from ``children()`` via ``_child_attrs``).
    ``body`` is the single IrNode child invoked under dispatch.
    """

    _child_attrs: ClassVar[tuple[str, ...]] = ("body",)
    target_type: type[IrSelf]
    body: IrNode[Ir_co]

    def eval(self, d: IrSelf, n: IrSelf, nc: tuple, /) -> Ir_co:
        """Delegate to the body."""
        return self.body.eval(d, n, nc)

    def _inner_str(self) -> str:
        """Render the target-type name plus the body."""
        return f"{self.target_type.__name__}, {self.body}"
