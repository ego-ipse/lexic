"""IR AST node dataclasses — canonical, frozen, hashable.

Every IR node implements the structural protocol from IrNode:
  - children() -> tuple[IrNode, ...]   children in traversal order
  - rebuild(new_children) -> IrNode    reconstruct under transformation
  - emit(indent=0) -> str              default string rendering (debug)

Hierarchy:
  IrNode (ABC) ── IrLeaf          leaves: IrLiteral, IrCharClass, IrRuleRef, Quantifier
               └─ IrStructure ─── IrCollection[_T]    homogeneous variable-length children
                                └─ IrComposite[*_Ts]  heterogeneous fixed-arity children

``__str__`` is templated at IrNode level as:

    f"{_str_name}{_str_opener}{_inner_str()}{_str_closer}"

``_str_name`` is auto-derived (strip ``Ir``, uppercase) unless overridden.
``_str_opener``/``_str_closer`` default to ``(``/``)``.
Quantifier uses ``[``/``]`` — subscript/bounds notation, distinct from
constructor-call ``()``.
``_inner_str()`` is abstract; IrLeaf defaults to ``repr(first_field)``,
IrStructure to comma-joined extras and children.
"""

from __future__ import annotations

import dataclasses
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import (
    Any,
    ClassVar,
    Generic,
    Self,
    TypeAlias,
    TypeVar,
    TypeVarTuple,
    Unpack,
)

_T = TypeVar("_T", bound="IrNode")
_Ts = TypeVarTuple("_Ts")


# ── Root protocol ─────────────────────────────────────────────────────


class IrNode(ABC):
    """Structural protocol every IR node implements.

    ``_str_name`` is auto-derived by ``__init_subclass__``: strip the ``Ir``
    prefix and uppercase the remainder (e.g. ``IrRule`` → ``RULE``).
    Subclasses that want a different name (e.g. ``SEQ`` instead of
    ``SEQUENCE``) declare ``_str_name: ClassVar[str] = "SEQ"`` explicitly.
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
        """Content between the brackets in __str__.

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
    def rebuild(self, new_children: tuple) -> Self:
        """Reconstruct with new children.

        :param new_children: Tuple of new child nodes to rebuild with.
        :returns: A new IrNode instance with the new children.
        """

    def emit(self, indent: int = 0) -> str:  # pylint: disable=unused-argument
        """Default string rendering used by IrMetaEmitter.

        Leaves return repr(self), ignoring indent.
        Flavour emitters bypass this via their action dispatch table.

        :param indent: Indentation depth (number of two-space levels).
        :returns: String representation of the node.
        """
        return repr(self)


# ── Leaf base ─────────────────────────────────────────────────────────


class IrLeaf(IrNode):
    """Base for all leaf nodes — identity implementations of the structural protocol.

    Default ``_inner_str`` renders ``repr(first_field)``.
    Leaves with multi-field or non-standard formatting override it.
    """

    __dataclass_fields__: ClassVar[dict[str, dataclasses.Field[Any]]]

    def _inner_str(self) -> str:
        """Default: repr of the first dataclass field.

        :returns: ``repr(first_field_value)``.
        """
        flds = dataclasses.fields(self)
        return repr(getattr(self, flds[0].name))

    def children(self) -> tuple[IrNode, ...]:
        """Leaves have no children.

        :returns: Empty tuple.
        """
        return ()

    def rebuild(self, new_children: tuple[IrNode, ...]) -> Self:  # pylint: disable=unused-argument
        """Leaves reconstruct as identity.

        :param new_children: Ignored.
        :returns: self unchanged.
        """
        return self


# ── Branch-node abstract base ─────────────────────────────────────────


class IrStructure(IrNode, ABC):
    """Abstract base for all non-leaf IR nodes.

    Declares __dataclass_fields__ so that dataclasses.replace() accepts
    concrete subclasses without a cast.

    Concrete structural subclasses must carry ``@dataclass(repr=False)`` —
    repr=False is required per-class because @dataclass runs after
    __init_subclass__ and would otherwise overwrite IrStructure.__repr__.
    """

    __dataclass_fields__: ClassVar[dict[str, dataclasses.Field[Any]]]

    @abstractmethod
    def _extra_field_names(self) -> tuple[str, ...]:
        """Names of dataclass fields that are non-child extras.

        :returns: Tuple of field names excluded from children().
        """

    def _extra_reprs(self) -> list[str]:
        """``key=repr(val)`` strings for each extra field.

        :returns: List of ``name=repr(value)`` strings.
        """
        return [f"{n}={getattr(self, n)!r}" for n in self._extra_field_names()]

    def _extra_str_parts(self) -> list[str]:
        """Canonical str parts for extra fields.

        IrCollection renders extras as ``key=repr(val)``.
        IrComposite overrides to render positionally (just ``repr(val)``).

        :returns: List of formatted extra-field strings.
        """
        return self._extra_reprs()

    def _inner_str(self) -> str:
        """Comma-joined extras and children for __str__.

        :returns: Inner string content.
        """
        return ", ".join(self._extra_str_parts() + [str(c) for c in self.children()])

    def __repr__(self) -> str:
        """Debug raw visualization."""
        parts = self._extra_reprs() + [repr(c) for c in self.children()]
        if not parts:
            return f"{type(self).__name__}()"
        body = ",\n".join(parts)
        indented = "  " + body.replace("\n", "\n  ")
        return f"{type(self).__name__}(\n{indented}\n)"


# ── Variable-length homogeneous branch nodes ──────────────────────────


class IrCollection(IrStructure, Generic[_T]):
    """Branch node carrying a single variable-length tuple of homogeneous children.

    Concrete subclasses declare:
        _items_attr: ClassVar[str] = "<field_name>"

    ``_str_name`` is auto-derived from the class name unless overridden.
    children() and rebuild() are fully auto-implemented from _items_attr.
    Extra dataclass fields (e.g. IrAst.start) are preserved on rebuild.
    """

    _items_attr: ClassVar[str]

    def _extra_field_names(self) -> tuple[str, ...]:
        """Fields that are not the homogeneous items tuple.

        :returns: Tuple of extra field names.
        """
        return tuple(
            f.name for f in dataclasses.fields(self) if f.name != self._items_attr
        )

    def children(self) -> tuple[_T, ...]:
        """Return the homogeneous children tuple.

        :returns: Tuple of child nodes.
        """
        return getattr(self, self._items_attr)

    def rebuild(self, new_children: tuple[_T, ...]) -> Self:
        """Reconstruct, replacing the items field with new_children.

        :param new_children: Replacement children tuple.
        :returns: New instance with updated children.
        """
        return dataclasses.replace(self, **{self._items_attr: new_children})


# ── Fixed-arity heterogeneous branch nodes ────────────────────────────


class IrComposite(IrStructure, Generic[*_Ts]):
    """Branch node carrying a fixed, named set of typed children.

    Concrete subclasses declare:
        _child_attrs: ClassVar[tuple[str, ...]] = ("<attr1>", "<attr2>", ...)

    ``_str_name`` is auto-derived from the class name unless overridden.
    children() returns them in declaration order as tuple[IrNode, ...].
    rebuild() zips new_children back onto those attribute names.
    Extra fields (those not in _child_attrs) are preserved on rebuild.

    The TypeVarTuple *_Ts encodes each child's precise type, which benefits
    rebuild() callers and field-level type checks; children() intentionally
    returns the covariant-safe tuple[IrNode, ...].
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
        """Extra fields rendered positionally (just repr(val), no key prefix).

        :returns: List of ``repr(value)`` strings.
        """
        return [repr(getattr(self, n)) for n in self._extra_field_names()]

    def children(self) -> tuple[IrNode, ...]:
        """Return children in _child_attrs declaration order.

        :returns: Tuple of child nodes.
        """
        return tuple(getattr(self, a) for a in self._child_attrs)

    def rebuild(self, new_children: tuple[Unpack[_Ts]]) -> Self:
        """Reconstruct, replacing child attrs from new_children in order.

        :param new_children: Replacement children, matching _child_attrs order.
        :returns: New instance with updated children.
        """
        return dataclasses.replace(self, **dict(zip(self._child_attrs, new_children)))


# ── Leaves ────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class IrLiteral(IrLeaf):
    """Literal string. `value` is canonical Python (escapes decoded)."""

    value: str


@dataclass(frozen=True, slots=True)
class IrCharClass(IrLeaf):
    """Character class. `pattern` is canonical POSIX-style interior."""

    pattern: str
    negated: bool = False

    def _inner_str(self) -> str:
        """Pattern plus optional negated flag.

        :returns: Inner string content.
        """
        return f"{self.pattern!r}, negated" if self.negated else repr(self.pattern)


@dataclass(frozen=True, slots=True)
class IrRuleRef(IrLeaf):
    """Reference to another rule by name."""

    _str_name: ClassVar[str] = "REF"
    name: str


@dataclass(frozen=True, slots=True)
class Quantifier(IrLeaf):
    """Repetition bounds. `max=None` means unbounded.

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
class IrSequence(IrCollection["IrItem"]):
    """Concatenation of items."""

    _items_attr: ClassVar[str] = "items"
    _str_name: ClassVar[str] = "SEQ"
    items: tuple[IrItem, ...] = ()


@dataclass(frozen=True, slots=True, repr=False)
class IrAlternation(IrCollection["IrSequence"]):
    """Choice between sequences. Always >= 1 arm."""

    _items_attr: ClassVar[str] = "arms"
    _str_name: ClassVar[str] = "ALT"
    arms: tuple[IrSequence, ...] = ()


@dataclass(frozen=True, slots=True, repr=False)
class IrAst(IrCollection["IrRule"]):
    """Full grammar: rules + start-rule name."""

    _items_attr: ClassVar[str] = "rules"
    rules: tuple[IrRule, ...] = ()
    start: str = ""


# ── Composite nodes ───────────────────────────────────────────────────


@dataclass(frozen=True, slots=True, repr=False)
class IrGroup(IrComposite["IrAlternation"]):
    """Parenthesised group. Body is always an IrAlternation."""

    _child_attrs: ClassVar[tuple[str, ...]] = ("body",)
    body: IrAlternation


@dataclass(frozen=True, slots=True, repr=False)
class IrItem(IrComposite["IrAtom", "Quantifier"]):
    """An atom (leaf or group) with a quantifier."""

    _child_attrs: ClassVar[tuple[str, ...]] = ("atom", "quantifier")
    atom: IrAtom
    quantifier: Quantifier = field(default_factory=Quantifier)


@dataclass(frozen=True, slots=True, repr=False)
class IrRule(IrComposite["IrAlternation"]):
    """A named rule. Body is always an IrAlternation, even single-arm."""

    _child_attrs: ClassVar[tuple[str, ...]] = ("body",)
    name: str
    body: IrAlternation


# ── Type aliases (structural unions) ──────────────────────────────────

IrAtom: TypeAlias = IrLeaf | IrGroup
