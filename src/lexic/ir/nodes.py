"""IR AST node dataclasses — canonical, frozen, hashable.

Every IR node implements the structural protocol from IrNode:
  - children() -> tuple[IrNode, ...]   children in traversal order
  - rebuild(new_children) -> IrNode    reconstruct under transformation
  - __call__(dispatch, node, new_children) -> _T_co   evaluate as an action body

Hierarchy:
  IrNode[_T_co] (ABC) ── IrLeaf[_T_co]      leaves: IrLiteral, IrCharClass, IrRuleRef,
                                              Quantifier
                       └─ IrStructure ─── IrCollection[_T_co]   homogeneous variable-
                                                         length children
                                        └─ IrComposite[_T_co]  heterogeneous fixed-
                                                         arity children
                       └─ IrSuperSet[_Tsuper_co] ─── IrAtom    role marker for nodes
                                      IrItem can wrap: IrLiteral, IrCharClass, IrRuleRef,
                                      IrGroup (NOT Quantifier — leaf but not quantifiable).
                                      IrSuperSet uses a class-local PEP 695 TypeVar so
                                      bare IrAtom doesn't conflict with IrLeaf's IrNode
                                      parameterization in multi-inheritance.

``__str__`` is templated at IrNode level as:

    f"{_str_name}{_str_opener}{_inner_str()}{_str_closer}"

``_str_name`` is auto-derived (strip ``Ir``, uppercase) unless overridden.
``_str_opener``/``_str_closer`` default to ``(``/``)``.
Quantifier uses ``[``/``]`` — subscript/bounds notation, distinct from
constructor-call ``()``.
``_inner_str()`` is abstract; IrLeaf defaults to ``repr(first_field)``,
IrStructure to comma-joined extras and children.

Generic parameter ``_T_co`` is the return type of ``__call__`` — the value
this node produces when invoked as an action body inside an IrDispatch
walk. A single module-scope TypeVar with ``default="IrNode"`` threads
through IrLeaf / IrCollection / IrComposite; subclasses that don't
override the parameter inherit ``_T_co = IrNode``. Subclasses that pin
``_T_co`` (e.g. ``IrLiteral(IrLeaf[str])``) must override ``__call__``.
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
    TypeVar,
)

# Return type of ``__call__`` when this node is invoked as an action body.
# Default fires when a subclass omits the parameter:
# ``class IrCharClass(IrLeaf):`` → ``IrLeaf[IrNode]``.
_T_co = TypeVar("_T_co", default="IrNode", covariant=True, bound=object)

# ── Root protocol ─────────────────────────────────────────────────────


class IrNode[_T_co](ABC):
    """Structural protocol every IR node implements.

    ``_str_name`` is auto-derived by ``__init_subclass__``: strip the ``Ir``
    prefix and uppercase the remainder (e.g. ``IrRule`` → ``RULE``).
    Subclasses that want a different name (e.g. ``SEQ`` instead of
    ``SEQUENCE``) declare ``_str_name: ClassVar[str] = "SEQ"`` explicitly.

    Generic in ``_T_co`` — the return type of ``__call__`` when this node is
    invoked as an action body. Subclasses either pin ``_T_co`` by
    parameterizing the structural base (``IrLeaf[str]`` for ``IrLiteral``)
    or accept the default ``_T_co = IrNode``.
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
    def rebuild[U](self, new_children: tuple[U, ...]) -> Self:
        """Reconstruct with new children.

        :param new_children: Tuple of new child nodes to rebuild with.
        :returns: A new IrNode instance with the new children.
        """

    @abstractmethod
    def __call__(
        self,
        dispatch: IrNode | None,
        node: IrNode | None,
        new_children: tuple,
    ) -> _T_co | Self:
        """Evaluate this node as an action body.

        :param dispatch: Dispatcher driving the surrounding walk. ``None``
            when this node is invoked outside a dispatch (unit tests or
            pure-data bodies needing no context).
        :param node: The dispatched domain node providing sibling-lookup
            context. ``None`` outside a dispatch.
        :param new_children: The dispatched domain node's already-walked
            children, aligned to ``node.children()`` order.
        :returns: This node's contribution to the surrounding evaluation.
        """


# ── Leaf base ─────────────────────────────────────────────────────────


class IrLeaf[_T_co](IrNode):
    """Base for all leaf nodes — identity implementations of the structural protocol.

    Default ``_inner_str`` renders ``repr(first_field)``.
    Default ``__call__`` returns ``self`` (statically typed as ``_T_co``,
    which defaults to ``IrNode``).
    Leaves with multi-field or non-standard formatting override ``_inner_str``.
    Leaves that pin ``_T_co`` (e.g. ``IrLeaf[str]`` for ``IrLiteral``) must
    override ``__call__``.
    """

    __dataclass_fields__: ClassVar[dict[str, dataclasses.Field[Any]]]

    def _inner_str(self) -> str:
        """Default: repr of the first dataclass field.

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

        :param new_children: Ignored.
        :returns: self unchanged.
        """
        return self

    def __call__(
        self,
        _dispatch: IrNode | None,
        _node: IrNode | None,
        _new_children: tuple,
    ) -> _T_co | Self:
        """Default leaf evaluation: return ``self``.

        Typechecks because every IrLeaf IS-A IrNode (the default for ``_T_co``).
        Subclasses that re-parameterize ``_T_co`` must override.
        """
        return self


# ── Branch-node abstract base ─────────────────────────────────────────


class IrStructure(IrNode[_T_co], Generic[_T_co]):
    """Abstract base for all non-leaf IR nodes.

    PYLINT is bugged here: Use Generic to thread the ``_T_co`` parameter through IrCollection
    until https://github.com/pylint-dev/astroid/pull/3061 is in release.

    Update to IrStructure[_T_co](IrNode): once that lands.


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

    def __call__(
        self,
        dispatch: IrNode | None,
        node: IrNode | None,
        new_children: tuple,
    ) -> _T_co | Self:
        """Default structural evaluation: rebuild with each child invoked.

        Typechecks because every IrStructure IS-A IrNode (the default for
        ``_T_co``). Subclasses that re-parameterize ``_T_co`` must override.
        """
        called = tuple(c(dispatch, node, new_children) for c in self.children())
        return self.rebuild(called)


# ── Variable-length homogeneous branch nodes ──────────────────────────


class IrCollection(IrStructure[_T_co]):
    """Branch node carrying a single variable-length tuple of children.

    Concrete subclasses declare:
        _items_attr: ClassVar[str] = "<field_name>"

    ``_str_name`` is auto-derived from the class name unless overridden.
    children() and rebuild() are fully auto-implemented from _items_attr.
    Extra dataclass fields (e.g. IrAst.start) are preserved on rebuild.

    Default ``__call__`` rebuilds Self with each child invoked. Subclasses
    that re-parameterize ``_T_co`` must override.

    Element type is pinned per-subclass via the dataclass field annotation
    (e.g. ``items: tuple[IrItem, ...]``); IrCollection itself does not
    parameterize over element type.
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
        """Reconstruct, replacing the items field with new_children.

        ``U`` is a method-level TypeVar (PEP 695), independent of the
        class's ``_T_co``. Lets the default ``__call__`` body pass
        dispatch-walked children regardless of their per-child return type.
        Semantic constraint (children should be IrNode-shaped) is informal.

        :param new_children: Replacement children tuple.
        :returns: New instance with updated children.
        """
        return dataclasses.replace(self, **{self._items_attr: new_children})


# ── Fixed-arity heterogeneous branch nodes ────────────────────────────


class IrComposite(IrStructure[_T_co]):
    """Branch node carrying a fixed, named set of children.

    Concrete subclasses declare:
        _child_attrs: ClassVar[tuple[str, ...]] = ("<attr1>", "<attr2>", ...)

    ``_str_name`` is auto-derived from the class name unless overridden.
    children() returns them in declaration order as tuple[IrNode, ...].
    rebuild() zips new_children back onto those attribute names.
    Extra fields (those not in _child_attrs) are preserved on rebuild.

    Default ``__call__`` rebuilds Self with each child invoked. Subclasses
    that re-parameterize ``_T_co`` must override.

    Child types are pinned per-subclass via the dataclass field annotations
    (e.g. ``body: IrAlternation``); IrComposite itself does not parameterize
    over child types.
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

    def rebuild[U](self, new_children: tuple[U, ...]) -> Self:
        """Reconstruct, replacing child attrs from new_children in order.

        ``U`` is a method-level TypeVar (PEP 695), independent of the
        class's ``_T_co``. Lets the default ``__call__`` body pass
        dispatch-walked children regardless of their per-child return type.
        Semantic constraint (children should be IrNode-shaped) is informal.

        :param new_children: Replacement children, matching _child_attrs order.
        :returns: New instance with updated children.
        """
        return dataclasses.replace(self, **dict(zip(self._child_attrs, new_children)))


# ── Superset role ─────────────────────────────────────────────────────────


class IrSuperSet(IrNode):
    """IrNode parent of IrAtom role marker and any future supersets."""


class IrAtom(IrSuperSet):
    """Role marker for IR nodes that ``IrItem`` can wrap with a quantifier.

    Decoupled from leaf-vs-composite structure. ``IrLiteral`` /
    ``IrCharClass`` / ``IrRuleRef`` are leaves AND atoms; ``IrGroup`` is a
    composite AND an atom; ``Quantifier`` is a leaf but NOT an atom
    (you can't quantify a quantifier).

    Concrete atoms multi-inherit (IrAtom is unparameterized — IrSuperSet's
    class-local TypeVar makes that work in multi-inheritance):

      class IrLiteral(IrLeaf[str], IrAtom): ...
      class IrCharClass(IrLeaf, IrAtom): ...
      class IrRuleRef(IrLeaf, IrAtom): ...
      class IrGroup(IrAtom, IrComposite): ...

    Open-set: a future atom type just adds ``IrAtom`` to its bases.
    """


# ── Leaves ────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class IrLiteral[_T_co: str](IrLeaf, IrAtom):
    """Literal string. `value` is canonical Python (escapes decoded).

    Overrides ``__call__`` to return ``self.value`` directly — keeps
    ``__str__`` free for debug output (``LITERAL('foo')``) while ``__call__``
    returns the string content for emission. Subsumes the ``IrText`` role.
    """

    value: str

    def __call__(
        self,
        _dispatch: IrNode | None,
        _node: IrNode | None,
        _new_children: tuple,
    ) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class IrCharClass(IrLeaf, IrAtom):
    """Character class. `pattern` is canonical POSIX-style interior."""

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
class IrGroup(IrAtom, IrComposite):
    """Parenthesised group. Body is always an IrAlternation."""

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
    """A named rule. Body is always an IrAlternation, even single-arm."""

    _child_attrs: ClassVar[tuple[str, ...]] = ("body",)
    name: str
    body: IrAlternation
