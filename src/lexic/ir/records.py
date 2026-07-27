"""Tuple tiers — a record IS its field tuple.

``IrTuple`` and ``IrSeq`` for positional payloads, ``IrNamedTuple`` for
records read by name or by index, ``Field`` for a declared field, and
``IrCachingTuple`` where a record's derived values are worth keeping.

A record has no ``.items`` and no ``.arms``: ``seq[0]`` works because the record
is the tuple.
"""

from __future__ import annotations

import copy
from collections.abc import Callable
from operator import itemgetter
from typing import (
    Any,
    ClassVar,
    Self,
    Sequence,
    cast,
    dataclass_transform,
    final,
    get_origin,
    overload,
)

from lexic.ir.spine import IrNode, IrSelf

_MISSING: Any = object()


class IrTuple[*Ts](tuple[*Ts], IrNode[IrSelf, IrSelf]):
    """``IrSelf + tuple`` primitive tier — a **heterogeneous** node IS its children.

    ``IrTuple`` is generic over a :pep:`646` ``TypeVarTuple`` (``*Ts``), so its
    type parameters ARE its positional element types, mirroring ``tuple``:

    - ``IrTuple[*tuple[IrItem, ...]]`` — homogeneous, variable length
      (what ``IrSequence``/``IrAlternation``/``IrAnd`` use).
    - ``IrTuple[IrOp, *tuple[IrSelf, ...]]`` — a fixed head followed by a
      variadic tail (an operator node: ``op`` at ``[0]``, then operands). The
      head is positionally type-checked.
    - ``IrTuple[IrAtom, IrQuantifier]`` — a fixed positional record (the shape
      ``IrNamedTuple`` records could later fold into, e.g. as a ``NamedTuple``).

    It multi-inherits ``IrNode`` and ``tuple[*Ts]`` so instances are both full
    IR nodes and native Python tuples (indexing, iteration, equality, hashing
    all work natively). The node's children ARE the tuple elements;
    ``children()`` returns ``self`` and ``rebuild(new_children)`` constructs a
    new instance from the replacement elements.

    ``_bound`` is explicitly ``tuple`` (parallel to ``IrStr._bound = str``); a
    ``TypeVarTuple`` carries no ``__bound__``, so :meth:`IrSelf.__init_subclass__`
    cannot derive it. Element-level ``IrSelf`` bounding is **not** expressible
    through ``*Ts`` (a ``TypeVarTuple`` cannot be bounded) — element types are
    constrained per use site / subclass parameterisation instead.

    ``__repr__`` is codegen: ``IrSequence(IrItem(...), IrItem(...))`` reproduces
    the constructor call.

    :param Ts: The positional element types (a ``TypeVarTuple`` — fixed,
        variadic, or mixed).
    """

    _bound: ClassVar[type[tuple]] = tuple

    def __new__(cls, *items: *Ts) -> Self:
        """Construct from variadic positional items.

        :param items: Zero or more child nodes, positionally typed by ``*Ts``.
        :returns: A new instance of the concrete subclass containing ``items``.
        """
        return super().__new__(cls, items)

    def children(self) -> Sequence[IrSelf]:
        """Return the tuple elements as the structural children.

        The precise positional element types stay available on the tuple
        itself (``self[0]`` etc., typed by ``*Ts``); ``children()`` exposes the
        walker-protocol view — a homogeneous ``IrSelf`` sequence. The cast is
        sound because every element is an ``IrSelf`` by construction; ``*Ts``
        simply cannot carry that bound.

        :returns: ``self`` as an ``IrSelf`` sequence.
        """
        return cast(Sequence[IrSelf], self)

    def rebuild(self, new_children: Sequence[IrSelf]) -> Self:
        """Reconstruct with replacement children.

        :param new_children: Replacement elements (each an ``IrSelf``).
        :returns: New instance of the same concrete type containing ``new_children``.
        """
        # cast to *Ts: runtime elements satisfy it; *Ts cannot carry the bound
        return type(self)(*cast(tuple[*Ts], tuple(new_children)))

    def eval(self, d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> IrSelf:
        """Dispatch each element via its own ``eval`` and rebuild the tuple.

        Returns ``IrSelf`` (not ``Self``) so reducer subclasses like ``IrAnd``
        may override ``eval`` with a non-tuple result (e.g. ``IrInt``); for
        rebuild collections the runtime result is still ``type(self)(...)``.

        :param d: Dispatcher forwarded to each element's ``eval``.
        :param n: Parent node forwarded to each element's ``eval``.
        :param nc: Pre-walked children forwarded to each element's ``eval``.
        :returns: New instance containing the evaluated elements.
        """
        evaluated = (p.eval(d, n, nc) for p in cast(tuple[IrSelf, ...], self))
        return type(self)(*cast(tuple[*Ts], tuple(evaluated)))

    def __repr__(self) -> str:
        """Codegen repr: ``ClassName(elem0, elem1, …)``.

        A class-valued element renders as its bare ``__name__`` (e.g.
        ``IrField('lo', IrInt)``) so the result stays valid codegen; homogeneous
        collections never hold classes, so this is a no-op for them.

        :returns: Constructor call reproducing this node.
        """
        inner = ", ".join(
            element.__name__ if isinstance(element, type) else repr(element)
            for element in self
        )
        return f"{type(self).__name__}({inner})"


class IrSeq[T: IrSelf](IrTuple[*tuple[T, ...]], IrNode[IrSelf, IrSelf]):
    """Generic **homogeneous** tuple — every element is a ``T`` (bounded ``IrSelf``).

    ``IrSeq[T]`` is ``IrTuple[*tuple[T, ...]]`` given a name. Because ``T`` is an
    ordinary bounded ``TypeVar`` (not a member of ``*Ts``), it **recovers the
    element bound** that the heterogeneous :class:`IrTuple` cannot express:
    ``IrSeq[int]`` is rejected, and ``IrSeq[IrItem](IrItem(...), x)`` rejects any
    ``x`` that is not an ``IrItem``.

    Variadic-length homogeneous collections subclass it instead of spelling the
    ``*tuple[X, ...]`` unpack at every site::

        class IrSequence(IrSeq["IrItem"]): ...

    ``_bound`` is re-declared ``tuple`` so :meth:`IrSelf.__init_subclass__` does
    not derive ``IrSelf`` from the own ``T`` parameter (the heterogeneous
    ``IrTuple`` already pins ``tuple``; subclasses with no own params inherit it).

    :param T: The single element type, bounded by ``IrSelf``.
    """

    _bound: ClassVar[type[tuple]] = tuple


@dataclass_transform(eq_default=True, frozen_default=True)
class IrNamedTuple[*Ts](IrTuple[*Ts], IrNode[IrSelf, IrSelf]):
    """Fixed-arity **named** tuple — the node IS its fields, by name or by index.

    Each class-body annotation is a field, in declaration order: the *i*-th
    field reads element ``[i]``. Storage is the tuple itself — a tuple subtype
    cannot carry non-empty ``__slots__``, so there is no separate per-field
    storage — and instances are immutable. :func:`~typing.dataclass_transform`
    makes the type checker synthesise a typed constructor from the fields
    (positional, keyword and defaults all checked); :meth:`__new__` builds the
    tuple from the same arguments at runtime.

    This is the :class:`typing.NamedTuple` mechanism generalised over
    :class:`IrTuple`: a record is simultaneously a positional heterogeneous
    tuple and a named record::

        class IrItemRec(IrNamedTuple[IrAtom, IrQuantifier]):
            atom: IrAtom
            quantifier: IrQuantifier

        rec = IrItemRec(atom, quant)
        rec.atom is rec[0]            # named access == positional access

    pyright reads the bare annotation for each named accessor's type, while the
    descriptor installed in :meth:`__init_subclass__` provides the runtime read
    as ``self[i]``. This is the base that ``IrNamedTuple`` records can fold onto.

    :param Ts: The positional field types, in declaration order.
    """

    _fields: ClassVar[tuple[str, ...]] = ()
    _field_defaults: ClassVar[dict[str, object]] = {}
    _child_attrs: ClassVar[tuple[str, ...]] = ()

    def __init_subclass__(cls, **kwargs: Any) -> None:
        """Record field names/defaults and install a positional accessor each.

        ``_child_attrs`` defaults to the field tuple (all fields are dispatched
        children); a record with scalar payload declares its own narrower
        ``_child_attrs`` in the class body, which is preserved.

        :param kwargs: Forwarded to ``super().__init_subclass__``.
        """
        super().__init_subclass__(**kwargs)
        anns = cls.__dict__.get("__annotations__", {})
        flds = tuple(name for name, ann in anns.items() if not cls._is_classvar(ann))
        cls._fields = flds
        cls._field_defaults = {
            name: cls.__dict__[name]
            for name in flds
            if name in cls.__dict__ and not isinstance(cls.__dict__[name], property)
        }
        if "_child_attrs" not in cls.__dict__:
            cls._child_attrs = flds
        cls._install_accessors()

    @classmethod
    def _install_accessors(cls) -> None:
        """Install a positional read accessor (``self[i]``) for each field."""
        for index, name in enumerate(cls._fields):
            setattr(cls, name, property(itemgetter(index)))

    def __new__[**P](cls, *args: P.args, **kwargs: P.kwargs) -> Self:
        """Build the tuple from positional args, keywords, and field defaults.

        :param args: Leading field values, positionally.
        :param kwargs: Remaining field values, by name.
        :returns: A new instance with the fields stored as tuple elements.
        :raises TypeError: On a missing field or an unexpected keyword.
        """
        if not kwargs and len(args) == len(cls._fields):  # all-positional fast path
            return super().__new__(cls, *cast(tuple[*Ts], args))
        values = list(args)
        for name in cls._fields[len(args) :]:
            if name in kwargs:
                values.append(kwargs.pop(name))
            elif name in cls._field_defaults:
                values.append(cls._field_defaults[name])
            else:
                raise TypeError(f"{cls.__name__} missing required field {name!r}")
        if kwargs:
            raise TypeError(f"{cls.__name__} got unexpected fields {list(kwargs)}")
        return super().__new__(cls, *cast(tuple[*Ts], tuple(values)))

    @staticmethod
    def _is_classvar(annotation: object) -> bool:
        """True if ``annotation`` denotes ``typing.ClassVar`` (so it is not a field).

        Handles both stringised annotations (``from __future__ import
        annotations``) and the live ``ClassVar`` form, so records can declare
        ``ClassVar`` class data (e.g. ``_child_attrs``) without it becoming a field.

        :param annotation: A value from a class ``__annotations__`` mapping.
        :returns: ``True`` when the annotation is a ``ClassVar``.
        """
        if isinstance(annotation, str):
            return annotation.lstrip().startswith(("ClassVar", "typing.ClassVar"))
        return annotation is ClassVar or get_origin(annotation) is ClassVar

    def children(self) -> Sequence[IrSelf]:
        """Return the fields named in ``_child_attrs`` (the IR-node children).

        Overrides :class:`IrTuple` so a record with scalar payload (a field not
        in ``_child_attrs``) excludes that payload from the walk.

        :returns: The child fields, in declaration order.
        """
        attrs = self._child_attrs
        return cast(
            Sequence[IrSelf],
            tuple(self[i] for i, name in enumerate(self._fields) if name in attrs),
        )

    def rebuild(self, new_children: Sequence[IrSelf]) -> Self:
        """Splice ``new_children`` into the child positions; keep scalar payload.

        :param new_children: Replacements for the ``_child_attrs`` fields, in order.
        :returns: A new instance with children replaced and payload preserved.
        """
        repl = list(new_children)
        values: list[object] = []
        k = 0
        for i, name in enumerate(self._fields):
            if name in self._child_attrs:
                values.append(repl[k])
                k += 1
            else:
                values.append(self[i])
        return cast(Callable[..., Self], type(self))(*values)

    def repr_args(self) -> tuple[object, ...]:
        """The constructor-arg prefix after trailing-default elision.

        Walks the fields from the end and drops each whose value is the same
        concrete type as its declared default AND equals it (``==``, so
        :class:`IrScalar`'s type-aware equality applies), stopping at the
        first field that differs or carries no default (never omittable). The
        prefix is still a valid constructor call — the omitted fields
        reconstruct to the same defaults. One source of elision truth for
        :meth:`__repr__` and the notation emit half.

        The type check is load-bearing, not pedantry: empty records compare
        equal CROSS-CLASS under tuple equality (``IrArgs() == IrTuple()``), so
        an equality-only elision renders ``IrJoin(IrArgs())`` as ``IrJoin()``,
        which reconstructs with the *wrong* default ``IrTuple()`` — repr-stable
        but behaviorally different (the F-REPR-1 finding, 2026-07-16).

        :returns: The positional args, trailing default-equal run elided.
        """
        fields, defaults = self._fields, self._field_defaults
        n = len(fields)
        while (
            n > 0
            and fields[n - 1] in defaults
            and type(self[n - 1]) is type(defaults[fields[n - 1]])
            and self[n - 1] == defaults[fields[n - 1]]
        ):
            n -= 1
        return tuple(self[:n])

    def __repr__(self) -> str:
        """Codegen repr — constructor call over :meth:`repr_args`.

        ``IrItem(IrLiteral('a'), IrQuantifier(1, 1))`` renders
        ``IrItem(IrLiteral('a'))``. A class-valued field renders as its bare
        ``__name__`` (as in :meth:`IrTuple.__repr__`) so the result stays
        valid codegen.

        :returns: Constructor call reproducing this node (defaults elided).
        """
        inner = ", ".join(
            element.__name__ if isinstance(element, type) else repr(element)
            for element in self.repr_args()
        )
        return f"{type(self).__name__}({inner})"


@final
class Field(IrNode):
    """A default value or per-instance factory for an :class:`IrCachingTuple`
    field — the ``dataclasses.field`` analogue, and itself an :class:`IrNode`.

    Typed (via the overloads) as the field's own type, so ``x: T = Field(...)``
    is assignable at the declaration site exactly like ``dataclasses.field``.

    Exactly one of ``default`` / ``default_factory`` is required: the overloads
    reject ``Field()`` statically, and :meth:`__new__` raises ``TypeError`` at
    runtime so a field never silently carries the missing-value sentinel.
    """

    __slots__ = ("default", "default_factory")

    @overload
    def __new__[T](cls, *, default: T) -> T: ...
    @overload
    def __new__[T](cls, *, default_factory: Callable[[], T]) -> T: ...
    def __new__[T](
        cls,
        *,
        default: T = _MISSING,
        default_factory: Callable[[], T] | None = None,
    ) -> T:
        if (default is _MISSING) == (default_factory is None):
            raise TypeError(
                "Field requires exactly one of 'default' or 'default_factory'"
            )
        self = object.__new__(cls)
        self.default = default
        self.default_factory = default_factory
        return cast(T, self)

    def build(self) -> object:
        """A fresh default — the factory result, or a deep copy of the default value.

        The default is deep-copied so a mutable ``default`` (e.g. ``[False]``)
        yields an independent value per instance instead of one object shared
        across every instance and every construction.
        """
        if self.default_factory is not None:
            return self.default_factory()
        return copy.deepcopy(self.default)


@dataclass_transform(eq_default=True, frozen_default=True, field_specifiers=(Field,))
class IrCachingTuple[*Ts](IrNamedTuple[*Ts], IrNode[IrSelf, IrSelf]):
    """An :class:`IrNamedTuple` whose subclasses inherit its field layout and whose
    :class:`Field` defaults are resolved to fresh per-instance values.

    ``IrNode[IrSelf, IrSelf]`` is re-listed (it is already reached via
    ``IrNamedTuple``) to mirror :class:`IrNamedTuple`/:class:`IrTuple`: a sole
    base subscripted with the bare ``*Ts`` defeats astroid's MRO resolution, and
    the concrete second base restores it."""

    def __init_subclass__(cls, **kwargs: Any) -> None:
        """Merge every caching base's fields ahead of own, then reinstall accessors.

        Bases are folded in reverse-MRO order (most-base first, dedup'd) — the
        ``dataclasses`` convention — so the layout is well defined under multiple
        inheritance, not just a single linear chain. ``super()`` has already set
        ``cls._fields`` / ``cls._field_defaults`` to this class's *own* fields.
        """
        own_child_attrs = "_child_attrs" in cls.__dict__
        super().__init_subclass__(**kwargs)
        own_fields, own_defaults = cls._fields, cls._field_defaults
        merged_fields: tuple[str, ...] = ()
        merged_defaults: dict[str, object] = {}
        nearest_child_attrs = cls._child_attrs
        for base in reversed(cls.__mro__):  # most-base first
            if base is cls or base is IrCachingTuple:
                continue
            if not issubclass(base, IrCachingTuple):
                continue
            merged_fields += tuple(f for f in base._fields if f not in merged_fields)
            merged_defaults |= base._field_defaults
            if base._fields:  # last write wins ⇒ nearest field-bearing base
                nearest_child_attrs = base._child_attrs
        cls._fields = merged_fields + tuple(
            f for f in own_fields if f not in merged_fields
        )
        cls._field_defaults = merged_defaults | own_defaults
        if not own_child_attrs:
            cls._child_attrs = nearest_child_attrs
        cls._install_accessors()

    def __new__[**P](cls, *args: P.args, **kwargs: P.kwargs) -> Self:
        """Resolve :class:`Field` factories, then build via :class:`IrNamedTuple`."""
        if cls.__abstractmethods__:
            raise TypeError(f"Can't instantiate abstract class {cls.__name__}")
        given = set(cls._fields[: len(args)]) | set(kwargs)
        kwargs |= {
            name: spec.build()
            for name, spec in cls._field_defaults.items()
            if name not in given and isinstance(spec, Field)
        }
        return super().__new__(cls, *args, **kwargs)
