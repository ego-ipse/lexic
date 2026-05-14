"""IR AST node dataclasses — canonical, frozen, hashable.

Every IR node implements the structural protocol from IrNode:
  - children() -> tuple[IrNode, ...]   children in traversal order
  - rebuild(new_children) -> IrNode    reconstruct under transformation
  - emit(indent=0) -> str              default string rendering (debug)

Hierarchy:
  IrNode (ABC) ── IrLeaf          leaves: IrLiteral, IrCharClass, IrRuleRef, Quantifier
               └─ IrStructure ─── IrCollection[_T]    homogeneous variable-length children
                                └─ IrComposite[*_Ts]  heterogeneous fixed-arity children
"""

from __future__ import annotations

import dataclasses
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, ClassVar, Generic, Self, TypeAlias, TypeVar, Unpack

from typing_extensions import TypeVarTuple

_T_co = TypeVar("_T_co", bound="IrNode", covariant=True)
_Ts = TypeVarTuple("_Ts")


# ── Root protocol ─────────────────────────────────────────────────────


class IrNode(ABC):
    """Structural protocol every IR node implements."""

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
    """Base for all leaf nodes — identity implementations of the structural protocol."""

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
    """

    __dataclass_fields__: ClassVar[dict[str, dataclasses.Field[Any]]]


# ── Variable-length homogeneous branch nodes ──────────────────────────


class IrCollection(IrStructure, Generic[_T_co]):
    """Branch node carrying a single variable-length tuple of homogeneous children.

    Concrete subclasses declare:
        _items_attr: ClassVar[str] = "<field_name>"

    children() and rebuild() are fully auto-implemented from that declaration.
    Extra dataclass fields (e.g. IrAst.start) are preserved on rebuild.
    """

    _items_attr: ClassVar[str]

    def children(self) -> tuple[_T_co, ...]:
        """Return the homogeneous children tuple.

        :returns: Tuple of child nodes.
        """
        return getattr(self, self._items_attr)

    def rebuild(self, new_children: tuple[_T_co, ...]) -> Self:
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

    children() returns them in declaration order as tuple[IrNode, ...].
    rebuild() zips new_children back onto those attribute names.
    Extra fields (those not in _child_attrs) are preserved on rebuild.

    The TypeVarTuple *_Ts encodes each child's precise type, which benefits
    rebuild() callers and field-level type checks; children() intentionally
    returns the covariant-safe tuple[IrNode, ...].
    """

    _child_attrs: ClassVar[tuple[str, ...]]

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


@dataclass(frozen=True, slots=True)
class IrRuleRef(IrLeaf):
    """Reference to another rule by name."""

    name: str


# ── Quantifier (also a leaf IrNode) ──────────────────────────────────


@dataclass(frozen=True, slots=True)
class Quantifier(IrLeaf):
    """Repetition bounds. `max=None` means unbounded."""

    min: int = 1
    max: int | None = 1


# ── Collection nodes ──────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class IrSequence(IrCollection["IrItem"]):
    """Concatenation of items."""

    _items_attr: ClassVar[str] = "items"
    items: tuple[IrItem, ...] = ()


@dataclass(frozen=True, slots=True)
class IrAlternation(IrCollection["IrSequence"]):
    """Choice between sequences. Always >= 1 arm."""

    _items_attr: ClassVar[str] = "arms"
    arms: tuple[IrSequence, ...] = ()


@dataclass(frozen=True, slots=True)
class IrAst(IrCollection["IrRule"]):
    """Full grammar: rules + start-rule name."""

    _items_attr: ClassVar[str] = "rules"
    rules: tuple[IrRule, ...] = ()
    start: str = ""


# ── Composite nodes ───────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class IrGroup(IrComposite["IrAlternation"]):
    """Parenthesised group. Body is always an IrAlternation."""

    _child_attrs: ClassVar[tuple[str, ...]] = ("body",)
    body: IrAlternation


@dataclass(frozen=True, slots=True)
class IrItem(IrComposite["IrAtom", "Quantifier"]):
    """An atom (leaf or group) with a quantifier."""

    _child_attrs: ClassVar[tuple[str, ...]] = ("atom", "quantifier")
    atom: IrAtom
    quantifier: Quantifier = field(default_factory=Quantifier)


@dataclass(frozen=True, slots=True)
class IrRule(IrComposite["IrAlternation"]):
    """A named rule. Body is always an IrAlternation, even single-arm."""

    _child_attrs: ClassVar[tuple[str, ...]] = ("body",)
    name: str
    body: IrAlternation


# ── Type aliases (structural unions) ──────────────────────────────────

IrAtom: TypeAlias = IrLeaf | IrGroup
