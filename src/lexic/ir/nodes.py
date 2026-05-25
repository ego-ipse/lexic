"""IR AST node dataclasses — canonical, frozen, hashable.

Every IR node implements the structural protocol from ``IrNode``:
  - ``children() -> tuple[IrNode, ...]``    children in traversal order
  - ``rebuild(new_children) -> Self``       reconstruct under transformation
  - ``__call__(d, n, nc) -> Ir_co``         evaluate as an action body

Identity vs. value-producing nodes
----------------------------------
Identity nodes (those whose dispatched value IS themselves) multi-inherit
from :class:`IrSelf` to pick up the identity ``__call__`` for free.
``IrSelf[Ir_co]`` is a generic mixin — decoupled from the ``IrNode`` hierarchy
— whose ``__call__`` returns ``self`` typed as ``T``. Subclasses bind
``T`` to their own class name (forward-string ref):

    class IrCharClass(IrLeaf["IrCharClass"], IrAtom):
        ...

Value-producing nodes (``IrLiteral``, action-algebra nodes) override
``__call__`` themselves.

Absence in dispatch slots
-------------------------
``IrNone[Ir_co]`` is a sentinel ``IrNode[None]`` that replaces the historical
``IrNode | None`` slots in ``__call__``'s signature. Callers pass
``IrNone[IrNode]()`` instead of ``None`` — ``IrNone`` IS an ``IrNode``,
so the union collapses.

Hierarchy
---------
  IrNode[Ir_co] (ABC) ── IrLeaf[Ir_co]
                       └─ IrStructure[Ir_co] ─── IrCollection[Ir_co]
                                              └─ IrComposite[Ir_co]
                       └─ IrSuperSet[Ir_co] ── IrAtom    role marker
                       └─ IrNone[Ir_co]                       absence sentinel

  IrSelf[Ir_co]            generic identity mixin (NOT an IrNode subclass)

``_str_name`` is auto-derived (strip ``Ir``, uppercase) unless overridden.
``_str_opener``/``_str_closer`` default to ``(``/``)``. ``Quantifier``
uses ``[``/``]``.
"""

from __future__ import annotations

import dataclasses
import functools
import typing
from abc import ABC, abstractmethod
from dataclasses import MISSING, dataclass, field
from typing import Any, ClassVar, Self, Sequence, TypeVar, cast

# ── Identity mixin — decoupled from IrNode hierarchy ──────────────────


class IrSelf[Ir_co: "IrSelf"]:
    """Generic identity mixin and IR-protocol root.

    Subclasses inherit ``__call__`` (returns self via PEP 673 ``Self``)
    and ``eval`` (returns ``Ir_co`` — cast of self by default; overridden
    by value-producing subclasses).

    ``IrSelf(bound)`` invokes the factory inherited from :class:`IrMeta`,
    producing typed neutral singletons (see :data:`Str`).

    :param Ir_co: the return type of ``eval``.
    """

    _bound: ClassVar[type]

    def __call__(self, _d: IrSelf, _n: IrSelf, _nc: Sequence[IrSelf], /) -> Self:
        """Identity. Returns ``self`` typed via PEP 673 ``Self`` so
        subclasses auto-thread the concrete type with no ``[X]`` binding.
        """
        return self

    def eval(self, d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> Ir_co:
        """Action-body protocol: default delegates to ``__call__``.

        Default returns ``self`` cast to ``Ir_co`` — sound when ``Ir_co``
        is the default ``IrSelf`` (identity nodes) since ``Self <: IrSelf``.
        Value-producing subclasses override ``eval`` with a typed return
        (``-> str``, etc.) without colliding with the Self-shaped identity
        of ``__call__``.
        """
        return cast(Ir_co, self(d, n, nc))

    def children(self) -> Sequence[Ir_co]:
        """Default: no children.

        Sentinels and non-structural ``IrSelf`` subclasses use this empty
        default. Structural IR nodes (``IrCollection``, ``IrComposite``)
        override to return their actual children.

        :returns: Empty tuple.
        """
        return ()

    def rebuild(self, _new_children: Sequence[Ir_co]) -> Self:
        """Default: identity rebuild.

        Sentinels and leaves return ``self``. Structural IR nodes
        override to reconstruct with new children.

        :param _new_children: Ignored at this level.
        :returns: ``self`` unchanged.
        """
        return self

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        # Resolve bound once per class definition
        for ancestor in cls.__mro__:
            params = getattr(ancestor, "__type_params__", ())
            if not params or not isinstance(params[0], TypeVar):
                continue
            bound = params[0].__bound__
            if bound is not None:
                cls._bound = bound
                break

    @property
    def bound(self) -> type[Ir_co]:
        """O(1) class-level lookup, no instance mutation required"""
        return type(self)._bound

    def bind(self, other: Any) -> Ir_co:
        """Object is bound to Ir_co or exploded"""
        if isinstance(other, self._bound):
            return other
        raise TypeError(f"Cannot bind {other!r} to {self!r}")


# ── Absence sentinel ──────────────────────────────────────────────────


class _IrNoneSentinel(IrSelf):  # pylint: disable=too-few-public-methods
    """Singleton sentinel — an ``IrSelf`` instance used wherever a missing
    dispatch slot needs a value. Pass ``IrNone`` directly (no call):

        result = some_node(IrNone, IrNone, ())

    ``IrNone`` is structurally inside ``IrSelf``: its type IS ``IrSelf``,
    which means it satisfies the ``_d: IrSelf`` / ``_n: IrSelf`` parameters
    of every ``__call__`` without bringing back a ``| None`` union.
    """


IrNone = _IrNoneSentinel()  # pylint: disable=invalid-name


# ── Typed-output base and concrete typed classes ──────────────────────


class IrType(IrSelf):
    """Typed-output base.

    Subclasses multi-inherit ``(IrType, <python type>)`` so instances are
    both ``IrSelf``-shaped (full protocol) AND a concrete Python type
    (full native methods). ``_bound`` records the python type for the
    cached :attr:`IrSelf.bound` property; ``eval`` returns the bound's
    neutral element (``str()`` → ``""``, ``int()`` → ``0``, …).

    Usable as a TypeVar bound: ``Ir_co: IrType = IrStr`` lets pyright
    accept the type at the bound site while preserving the IrSelf
    protocol on the produced value.
    """

    def eval(self, _d: IrSelf, _n: IrSelf, _nc: Sequence[IrSelf], /) -> Self:
        """Return the bound's neutral element (``self._bound()``)."""
        return type(self)._bound()

    @classmethod
    def coerce(cls, value: Any) -> Self:
        """Wrap ``value`` as an instance of ``cls``. Default: single-arg ctor.

        Subclasses override when the constructor shape differs
        (see :meth:`IrTuple.coerce`). The ``cls`` call is dynamically
        dispatched — concrete subclasses (e.g. :class:`IrStr`) provide
        the value-accepting constructor via their native python base.
        """
        return value if isinstance(value, cls) else cast(Any, cls)(value)


class IrStr(IrType, str):
    """``IrSelf+str`` typed class. ``IrStr()`` is the empty-str singleton.

    ``IrStr`` IS-A ``str`` so all string methods (notably ``.join``)
    work natively; it IS-A ``IrSelf`` so the IR protocol applies.
    """

    _bound: ClassVar[type[str]] = str


class IrTuple[T](IrType, tuple):
    """``IrSelf+tuple`` typed class. ``IrTuple()`` is the empty-tuple singleton."""

    _bound: ClassVar[type[tuple]] = tuple

    def __new__(cls, *args) -> IrTuple[T]:
        """Build from positional items: ``IrTuple(a, b, c)``."""
        return super().__new__(cls, args)

    @classmethod
    def coerce(cls, value: Any) -> Self:
        """Iterable → IrTuple via ``cls(*value)``; pass through if already ``cls``."""
        return value if isinstance(value, cls) else cls(*value)


# ── Root protocol ─────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True, init=False, repr=False)
class IrNode[Ir_co: IrSelf = IrSelf](IrSelf[Ir_co], ABC):
    """Structural protocol every IR node implements.

    Generic in ``Ir_co`` — the return type of ``__call__`` when this node is
    invoked as an action body. ``IrNode[X]`` IS-AN ``IrSelf[X]`` and inherits
    the identity ``__call__ -> X`` from ``IrSelf``. Value-producing nodes
    (``Ir_co != Self``) override ``__call__``.

    Dispatch slots use bare ``IrNode`` types — absence is carried by
    :class:`IrNone`, not ``None``. The signature is union-free.

    ``_str_name`` is auto-derived by ``__init_subclass__``: strip the ``Ir``
    prefix, uppercase the remainder. Override the class attribute to
    customise (e.g. ``_str_name: ClassVar[str] = "SEQ"``).

    Construction
    ------------
    Every subclass declared with ``@dataclass(..., init=False)`` inherits
    :meth:`__init__`. It accepts positional or keyword args matching the
    subclass's dataclass fields, and for any field annotated as an
    :class:`IrType` subclass it delegates widening to
    :meth:`IrType.coerce` — so callers can pass raw ``str`` where
    :class:`IrStr` is expected, raw iterables where :class:`IrTuple` is
    expected, etc. Missing fields fall back to the dataclass default; if
    none, the field's ``IrType`` neutral element is used.
    """

    _str_name: ClassVar[str]
    _str_opener: ClassVar[str] = "("
    _str_closer: ClassVar[str] = ")"

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if "_str_name" in cls.__dict__:
            return
        cls._str_name = cls.__name__.removeprefix("Ir").upper()

    @classmethod
    @functools.cache
    def _ir_field_types(cls) -> dict[str, type[IrType] | None]:
        """Per-field ``IrType`` subclass (origin) when annotated, else ``None``."""
        out: dict[str, type[IrType] | None] = {}
        for name, hint in typing.get_type_hints(cls).items():
            origin = typing.get_origin(hint) or hint
            out[name] = (
                origin
                if isinstance(origin, type) and issubclass(origin, IrType)
                else None
            )
        return out

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Construct from positional or keyword args."""
        cls = type(self)
        fields_list = dataclasses.fields(cls)
        ir_types = cls._ir_field_types()
        kwargs.update({fields_list[i].name: a for i, a in enumerate(args)})
        for f in fields_list:
            ir = ir_types.get(f.name)
            if f.name in kwargs:
                v = kwargs[f.name]
                val = ir.coerce(v) if ir is not None else v
            elif f.default is not MISSING:
                val = f.default
            elif f.default_factory is not MISSING:
                val = f.default_factory()
            elif ir is not None:
                val = ir()
            else:
                raise TypeError(f"{cls.__name__}: missing field {f.name!r}")
            object.__setattr__(self, f.name, val)

    @abstractmethod
    def _inner_str(self) -> str:
        """Content between the brackets in ``__str__``.

        :returns: Inner string content.
        """

    def __str__(self) -> str:
        return (
            f"{self._str_name}{self._str_opener}{self._inner_str()}{self._str_closer}"
        )


# ── Leaf base ─────────────────────────────────────────────────────────


class IrLeaf[Ir_co: IrSelf](IrNode[Ir_co]):
    """Base for all leaf nodes.

    Provides identity ``children()`` (empty) and ``rebuild()`` (no-op).
    Does NOT provide ``__call__`` — concrete leaves either multi-inherit
    ``IrSelf[Self]`` (identity) or override ``__call__`` (value-producing).
    """

    __dataclass_fields__: ClassVar[dict[str, dataclasses.Field[Any]]]

    def _inner_str(self) -> str:
        """Default: ``repr`` of the first dataclass field.

        :returns: ``repr(first_field_value)``.
        """
        flds = dataclasses.fields(self)
        return repr(getattr(self, flds[0].name)) if flds else ""


# ── Branch-node abstract base ─────────────────────────────────────────


class IrStructure[Ir_co: IrSelf](IrNode[Ir_co]):
    """Abstract base for non-leaf IR nodes.

    Provides ``_inner_str`` / ``__repr__`` machinery for nodes with extras
    and children. Does NOT provide ``__call__``.

    Concrete structural subclasses must carry ``@dataclass(repr=False)`` —
    ``repr=False`` is required per-class because ``@dataclass`` runs after
    ``__init_subclass__`` and would otherwise overwrite ``__repr__``.
    """

    __dataclass_fields__: ClassVar[dict[str, dataclasses.Field[Any]]]

    @abstractmethod
    def _extra_field_names(self) -> tuple[str, ...]:
        """Names of dataclass fields that are non-child extras.

        :returns: Tuple of field names excluded from ``children()``.
        """

    def _extra_reprs(self) -> list[str]:
        """``key=repr(val)`` strings for each extra field.

        :returns: List of formatted extra-field strings.
        """
        return [f"{n}={getattr(self, n)!r}" for n in self._extra_field_names()]

    def _extra_str_parts(self) -> list[str]:
        """Canonical str parts for extra fields.

        :returns: List of formatted extra-field strings.
        """
        return self._extra_reprs()

    def _inner_str(self) -> str:
        """Comma-joined extras and children for ``__str__``.

        :returns: Inner string content.
        """
        return ", ".join(self._extra_str_parts() + [str(c) for c in self.children()])

    def __repr__(self) -> str:
        """Debug raw visualisation."""
        parts = self._extra_reprs() + [repr(c) for c in self.children()]
        if not parts:
            return f"{type(self).__name__}()"
        body = ",\n".join(parts)
        indented = "  " + body.replace("\n", "\n  ")
        return f"{type(self).__name__}(\n{indented}\n)"


# ── Variable-length homogeneous branch nodes ──────────────────────────


class IrCollection[Ir_co: IrSelf](IrStructure[Ir_co]):
    """Branch node carrying a single variable-length tuple of children.

    Concrete subclasses declare::

        _items_attr: ClassVar[str] = "<field_name>"
    """

    _items_attr: ClassVar[str]

    def _extra_field_names(self) -> tuple[str, ...]:
        """Fields that are not the homogeneous items tuple.

        :returns: Tuple of extra field names.
        """
        return tuple(
            f.name for f in dataclasses.fields(self) if f.name != self._items_attr
        )

    def children(self) -> Sequence[Ir_co]:
        """Return the homogeneous children tuple.

        :returns: Tuple of child nodes.
        """
        return getattr(self, self._items_attr)

    def rebuild(self, new_children: Sequence[Ir_co]) -> Self:
        """Reconstruct, replacing the items field with ``new_children``.

        :param new_children: Replacement children tuple.
        :returns: New instance with updated children.
        """
        return dataclasses.replace(self, **{self._items_attr: new_children})


# ── Fixed-arity heterogeneous branch nodes ────────────────────────────


class IrComposite[Ir_co: IrSelf](IrStructure[Ir_co]):
    """Branch node carrying a fixed, named set of children.

    Concrete subclasses declare::

        _child_attrs: ClassVar[tuple[str, ...]] = ("<attr1>", "<attr2>", ...)
    """

    _child_attrs: ClassVar[tuple[str, ...]]

    def _extra_field_names(self) -> tuple[str, ...]:
        """Fields that are not named child attributes.

        :returns: Tuple of extra field names.
        """
        return tuple(
            f.name for f in dataclasses.fields(self) if f.name not in self._child_attrs
        )

    def _extra_str_parts(self) -> list[str]:
        """Extras rendered positionally.

        :returns: List of ``repr(value)`` strings.
        """
        return [repr(getattr(self, n)) for n in self._extra_field_names()]

    def children(self) -> Sequence[Ir_co]:
        """Return children in ``_child_attrs`` declaration order.

        :returns: Tuple of child nodes.
        """
        return tuple(getattr(self, a) for a in self._child_attrs)

    def rebuild(self, new_children: Sequence[Ir_co]) -> Self:
        """Reconstruct, replacing child attrs from ``new_children`` in order.

        :param new_children: Replacements matching ``_child_attrs`` order.
        :returns: New instance with updated children.
        """
        return dataclasses.replace(self, **dict(zip(self._child_attrs, new_children)))


# ── Superset role ─────────────────────────────────────────────────────


class IrSuperSet[Ir_co: IrSelf = IrSelf](IrNode[Ir_co]):
    """IrNode parent of ``IrAtom`` and any future role-marker supersets.

    Class-local ``Ir_co`` TypeVar so concrete atoms can multi-inherit with
    parameterised leaves without TypeVar conflicts.
    """


class IrAtom[Ir_co: IrSelf = IrSelf](IrSuperSet[Ir_co]):
    """Role marker for IR nodes that ``IrItem`` can wrap with a quantifier.

    Decoupled from leaf-vs-composite structure. Concrete atoms multi-
    inherit ``IrAtom`` alongside their structural base::

        class IrLiteral(IrLeaf[str], IrAtom): ...
        class IrCharClass(IrLeaf["IrCharClass"], IrAtom): ...
        class IrRuleRef(IrLeaf["IrRuleRef"], IrAtom): ...
        class IrGroup(IrComposite["IrGroup"], IrAtom): ...

    Open-set: a future atom type just adds ``IrAtom`` to its bases.
    """


# ── Leaves ────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True, init=False)
class IrStrLeaf[Ir_co: IrStr](IrLeaf[Ir_co]):
    """Base for leaves carrying a single :class:`IrStr`-shaped value.

    Generic in ``Ir_co`` (bounded by :class:`IrStr`, defaulting to
    :class:`IrStr`). The base :meth:`IrNode.__init__` coerces the raw
    ``str`` payload via :meth:`IrStr.coerce`.
    """

    value: Ir_co

    def eval(self, _d: IrSelf, _n: IrSelf, _nc: Sequence[IrSelf], /) -> Ir_co:
        """Return the stored value (already coerced to ``Ir_co``)."""
        return self.value


@dataclass(frozen=True, slots=True, init=False)
class IrLiteral(IrStrLeaf, IrAtom):
    """Literal string. ``.value`` is canonical Python (escapes decoded)."""


@dataclass(frozen=True, slots=True, init=False)
class IrCharClass(IrStrLeaf, IrAtom):
    """Character class. ``.value`` is the canonical POSIX-style interior."""


@dataclass(frozen=True, slots=True, init=False)
class IrRuleRef(IrStrLeaf, IrAtom):
    """Reference to another rule. ``.value`` is the rule name."""

    _str_name: ClassVar[str] = "REF"


@dataclass(frozen=True, slots=True, init=False)
class Quantifier(IrLeaf):
    """Repetition bounds. ``max=None`` means unbounded.

    Uses ``[``/``]`` brackets — subscript/bounds notation, distinct from
    the constructor-call ``(``/``)`` used by all other nodes.
    """

    _str_name: ClassVar[str] = "Q"
    _str_opener: ClassVar[str] = "["
    _str_closer: ClassVar[str] = "]"

    min: int = 1
    max: int | None = 1

    def _inner_str(self) -> str:
        """Compact bounds notation: ``n`` for exact, ``m..n`` for range.

        :returns: Inner string content.
        """
        if self.min == self.max:
            return str(self.min)
        hi = "*" if self.max is None else str(self.max)
        return f"{self.min}..{hi}"


# ── Collection nodes ──────────────────────────────────────────────────


@dataclass(frozen=True, slots=True, init=False, repr=False)
class IrSequence(IrCollection):
    """Concatenation of items."""

    _items_attr: ClassVar[str] = "items"
    _str_name: ClassVar[str] = "SEQ"
    items: IrTuple[IrItem] = IrTuple()


@dataclass(frozen=True, slots=True, init=False, repr=False)
class IrAlternation(IrCollection):
    """Choice between sequences. Always >= 1 arm."""

    _items_attr: ClassVar[str] = "arms"
    _str_name: ClassVar[str] = "ALT"
    arms: IrTuple[IrSequence] = IrTuple()


@dataclass(frozen=True, slots=True, init=False, repr=False)
class IrAst(IrCollection):
    """Full grammar: rules + start-rule name."""

    _items_attr: ClassVar[str] = "rules"
    rules: IrTuple[IrRule] = IrTuple()
    start: IrStr = IrStr("")


# ── Composite nodes ───────────────────────────────────────────────────


@dataclass(frozen=True, slots=True, init=False, repr=False)
class IrGroup(IrComposite, IrAtom):
    """Parenthesised group. Body is always an ``IrAlternation``."""

    _child_attrs: ClassVar[tuple[str, ...]] = ("body",)
    body: IrAlternation


@dataclass(frozen=True, slots=True, init=False, repr=False)
class IrNot[Ir_co: IrAtom = IrAtom](IrComposite, IrAtom):
    """Negation. Wraps an atom; ``IrNot(IrCharClass("a-z"))`` is ``[^a-z]``."""

    _child_attrs: ClassVar[tuple[str, ...]] = ("body",)
    body: Ir_co


@dataclass(frozen=True, slots=True, init=False, repr=False)
class IrItem(IrComposite):
    """An atom (leaf or group) with a quantifier."""

    _child_attrs: ClassVar[tuple[str, ...]] = ("atom", "quantifier")
    atom: IrAtom
    quantifier: Quantifier = field(default_factory=Quantifier)


@dataclass(frozen=True, slots=True, init=False, repr=False)
class IrRule(IrComposite):
    """A named rule. Body is always an ``IrAlternation``, even single-arm."""

    _child_attrs: ClassVar[tuple[str, ...]] = ("body",)
    name: IrStr
    body: IrAlternation
