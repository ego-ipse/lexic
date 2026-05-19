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
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, ClassVar, Self

# ── Identity mixin — decoupled from IrNode hierarchy ──────────────────


class IrSelf[Ir_co = "IrSelf"]:
    """Generic identity mixin.

    Subclasses bind ``Ir_co`` to themselves via inheritance and inherit a
    ``__call__`` that returns ``self`` typed as ``Ir_co``. The ``self: Ir_co``
    self-type annotation is what lets pyright prove ``Self <: Ir_co`` without
    a ``cast`` or an ignore.

    ``__call__`` is signature-permissive: ``*_args: object`` accepts the
    ``(d, n, nc)`` triple imposed by the IrNode protocol — or anything
    else. IrSelf intentionally does not reference IrNode.

    Usage::

        class IrCharClass(IrLeaf["IrCharClass"], IrAtom):
            pattern: str
            negated: bool = False
            # __call__ inherited from IrSelf — returns IrCharClass

    :param Ir_co: the class binding ``self`` for the identity return type.
    """

    def __call__(self: Ir_co, _d: IrSelf, _n: IrSelf, _nc: tuple, /) -> Ir_co:
        """Return ``self`` typed as ``Ir_co``.

        ``_d`` / ``_n`` are typed as ``IrSelf`` — the root of the IR
        hierarchy — so that any IrNode (including ``IrNone``) is acceptable
        without referencing ``IrNode`` from this module-level class.
        """
        return self


# ── Absence sentinel ──────────────────────────────────────────────────


IrNone: IrSelf = IrSelf()
"""Singleton sentinel — an ``IrSelf`` instance used wherever a missing
dispatch slot needs a value. Pass ``IrNone`` directly (no call):

    result = some_node(IrNone, IrNone, ())

``IrNone`` is structurally inside ``IrSelf``: its type IS ``IrSelf``,
which means it satisfies the ``_d: IrSelf`` / ``_n: IrSelf`` parameters
of every ``__call__`` without bringing back a ``| None`` union.
"""


# ── Root protocol ─────────────────────────────────────────────────────


class IrNode[Ir_co](IrSelf[Ir_co], ABC):
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
    """

    _str_name: ClassVar[str]
    _str_opener: ClassVar[str] = "("
    _str_closer: ClassVar[str] = ")"

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if "_str_name" in cls.__dict__:
            return
        cls._str_name = cls.__name__.removeprefix("Ir").upper()

    @abstractmethod
    def _inner_str(self) -> str:
        """Content between the brackets in ``__str__``.

        :returns: Inner string content.
        """

    def __str__(self) -> str:
        return (
            f"{self._str_name}{self._str_opener}{self._inner_str()}{self._str_closer}"
        )

    @abstractmethod
    def children(self) -> tuple[IrNode, ...]:
        """Children in traversal order.

        :returns: Tuple of child nodes.
        """

    @abstractmethod
    def rebuild[U](self, new_children: tuple[U, ...]) -> Self:
        """Reconstruct with new children.

        :param new_children: Tuple of replacements (method-level ``U``
            keeps this free of ``Any``).
        :returns: A new instance of the same concrete class.
        """

    # __call__ inherited from IrSelf[Ir_co] — concrete identity (returns self typed
    # as Ir_co). Value-producing subclasses override.


# ── Leaf base ─────────────────────────────────────────────────────────


class IrLeaf[Ir_co](IrNode[Ir_co]):
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

    def children(self) -> tuple[IrNode, ...]:
        """Leaves have no children.

        :returns: Empty tuple.
        """
        return ()

    def rebuild[U](self, new_children: tuple[U, ...]) -> Self:
        """Leaves reconstruct as identity.

        :param _new_children: Ignored.
        :returns: ``self`` unchanged.
        """
        return self


# ── Branch-node abstract base ─────────────────────────────────────────


class IrStructure[Ir_co](IrNode[Ir_co]):
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


class IrCollection[Ir_co](IrStructure[Ir_co]):
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

    def children(self) -> tuple[IrNode, ...]:
        """Return the homogeneous children tuple.

        :returns: Tuple of child nodes.
        """
        return getattr(self, self._items_attr)

    def rebuild[U](self, new_children: tuple[U, ...]) -> Self:
        """Reconstruct, replacing the items field with ``new_children``.

        :param new_children: Replacement children tuple.
        :returns: New instance with updated children.
        """
        return dataclasses.replace(self, **{self._items_attr: new_children})


# ── Fixed-arity heterogeneous branch nodes ────────────────────────────


class IrComposite[Ir_co](IrStructure[Ir_co]):
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

    def children(self) -> tuple[IrNode, ...]:
        """Return children in ``_child_attrs`` declaration order.

        :returns: Tuple of child nodes.
        """
        return tuple(getattr(self, a) for a in self._child_attrs)

    def rebuild[U](self, new_children: tuple[U, ...]) -> Self:
        """Reconstruct, replacing child attrs from ``new_children`` in order.

        :param new_children: Replacements matching ``_child_attrs`` order.
        :returns: New instance with updated children.
        """
        return dataclasses.replace(self, **dict(zip(self._child_attrs, new_children)))


# ── Superset role ─────────────────────────────────────────────────────


class IrSuperSet(IrNode):
    """IrNode parent of ``IrAtom`` and any future role-marker supersets.

    Class-local ``Ir_co`` TypeVar so concrete atoms can multi-inherit with
    parameterised leaves without TypeVar conflicts.
    """


class IrAtom(IrSuperSet):
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


@dataclass(frozen=True, slots=True)
class IrLiteral(IrLeaf[str], IrAtom):
    """Literal string. ``value`` is canonical Python (escapes decoded).

    Overrides ``__call__`` to return ``self.value`` — keeps ``__str__``
    free for debug output while ``__call__`` returns the string content
    for emission.
    """

    value: str

    def __call__(self, _d: IrSelf, _n: IrSelf, _nc: tuple, /) -> str:
        """Return the literal string value."""
        return self.value


@dataclass(frozen=True, slots=True)
class IrCharClass(IrLeaf, IrAtom):
    """Character class. ``pattern`` is canonical POSIX-style interior."""

    pattern: str
    negated: bool = False

    def _inner_str(self) -> str:
        """Pattern plus optional negated flag.

        :returns: Inner string content.
        """
        return f"{self.pattern!r}, negated" if self.negated else repr(self.pattern)


@dataclass(frozen=True, slots=True)
class IrRuleRef(IrLeaf, IrAtom):
    """Reference to another rule by name."""

    _str_name: ClassVar[str] = "REF"
    name: str


@dataclass(frozen=True, slots=True)
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


@dataclass(frozen=True, slots=True, repr=False)
class IrSequence(IrCollection):
    """Concatenation of items."""

    _items_attr: ClassVar[str] = "items"
    _str_name: ClassVar[str] = "SEQ"
    items: tuple[IrItem, ...] = ()


@dataclass(frozen=True, slots=True, repr=False)
class IrAlternation(IrCollection):
    """Choice between sequences. Always >= 1 arm."""

    _items_attr: ClassVar[str] = "arms"
    _str_name: ClassVar[str] = "ALT"
    arms: tuple[IrSequence, ...] = ()


@dataclass(frozen=True, slots=True, repr=False)
class IrAst(IrCollection):
    """Full grammar: rules + start-rule name."""

    _items_attr: ClassVar[str] = "rules"
    rules: tuple[IrRule, ...] = ()
    start: str = ""


# ── Composite nodes ───────────────────────────────────────────────────


@dataclass(frozen=True, slots=True, repr=False)
class IrGroup(IrComposite, IrAtom):
    """Parenthesised group. Body is always an ``IrAlternation``."""

    _child_attrs: ClassVar[tuple[str, ...]] = ("body",)
    body: IrAlternation


@dataclass(frozen=True, slots=True, repr=False)
class IrItem(IrComposite):
    """An atom (leaf or group) with a quantifier."""

    _child_attrs: ClassVar[tuple[str, ...]] = ("atom", "quantifier")
    atom: IrAtom
    quantifier: Quantifier = field(default_factory=Quantifier)


@dataclass(frozen=True, slots=True, repr=False)
class IrRule(IrComposite):
    """A named rule. Body is always an ``IrAlternation``, even single-arm."""

    _child_attrs: ClassVar[tuple[str, ...]] = ("body",)
    name: str
    body: IrAlternation
