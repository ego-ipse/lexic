"""IR spine — the abstract base classes shared by every IR node.

This module holds the reusable, grammar-agnostic machinery:

- :class:`IrSelf` — the generic identity root and IR-protocol base.
- :class:`IrNoneType` / :data:`IrNone` — the absence sentinel.
- :class:`IrNode` / :class:`IrLeaf` / :class:`IrAtom` — structural markers.
- the three primitive tiers' *base* classes: :class:`IrScalar` (with
  :class:`IrStr` / :class:`IrInt`), :class:`IrTuple`, and :class:`IrComposite`.

Concrete grammar-AST nodes (``IrLiteral``, ``IrItem``, ``IrNot``, …) live in
:mod:`lexic.ir.nodes`, which imports and re-exports everything here.

Splitting the spine out of ``nodes.py`` lets both ``nodes.py`` and
``action.py`` build on these bases without an import cycle.

Every IR node implements the structural protocol from :class:`IrSelf`:

- ``__call__(d, n, nc) -> Self``       identity evaluation
- ``eval(d, n, nc) -> Ir_co``          action-body protocol
- ``children() -> Sequence[Ir_co]``    children in traversal order
- ``rebuild(new_children) -> Self``    reconstruct under transformation

``__repr__`` is codegen: every node reproduces its own constructor call.
"""

from __future__ import annotations

from abc import ABC
from dataclasses import fields, replace
from typing import Any, ClassVar, Self, Sequence, TypeVar, cast, final

# ── Spine ─────────────────────────────────────────────────────────────


class IrSelf[Iri: "IrSelf", Ir_co: "IrSelf" = Iri]:
    """Generic identity root and IR-protocol base.

    Every IR node inherits from ``IrSelf``. ``Ir_co`` is a return-position
    TypeVar only — PEP 695 infers it covariant. The class provides:

    - ``__call__(d, n, nc) -> Self``   identity evaluation (returns ``self``)
    - ``eval(d, n, nc) -> Ir_co``      action-body protocol (default: delegates to ``__call__``)
    - ``children() -> Sequence[Ir_co]`` structural children in traversal order
    - ``rebuild(new_children) -> Self`` reconstruct self under transformation
    - ``bound`` property               the concrete type materialised from ``Ir_co``
    - ``bind(other) -> Ir_co``         type-safe cast enforcing ``bound``

    ``__repr__`` is codegen on every subclass — each node reproduces its own
    constructor call so that ``eval(repr(node))`` is a valid Python expression.

    :param Ir_co: the return type of ``eval``.
    """

    __slots__ = ()
    _bound: ClassVar[type]

    def __call__(self, _d: Iri, _n: Iri, _nc: Sequence[Iri], /) -> Self:
        """Identity: return ``self`` typed via PEP 673 ``Self``.

        Subclasses that produce values (rather than returning themselves) override
        ``eval`` instead; ``__call__`` stays identity so the dispatch machinery
        can always obtain ``self`` regardless of parameterisation.

        :param _d: Dispatcher (unused at identity level).
        :param _n: Current parent node (unused at identity level).
        :param _nc: Pre-walked node-children sequence (unused at identity level).
        :returns: ``self``, typed as the concrete subclass via ``Self``.
        """
        return self

    def eval(self, d: Iri, n: Iri, nc: Sequence[Iri], /) -> Ir_co:
        """Action-body protocol: default delegates to identity ``__call__``.

        Default returns ``self`` cast to ``Ir_co`` — sound when ``Ir_co`` is
        the default ``IrSelf`` (identity nodes) because ``Self <: IrSelf``.
        Value-producing subclasses (e.g. ``IrStr`` leaves) override ``eval``
        with a typed return (``-> Self``) without colliding with the
        ``Self``-shaped identity of ``__call__``.

        :param d: Dispatcher — an ``IrDispatch`` or equivalent.
        :param n: Current parent node.
        :param nc: Pre-walked node-children sequence (populated by the dispatcher).
        :returns: Evaluation result typed as ``Ir_co``.
        """
        return cast(Ir_co, self(d, n, nc))

    def children(self) -> Sequence[Ir_co]:
        """Return structural children in traversal order.

        Default: empty tuple — used by sentinels, leaves, and any
        ``IrSelf`` subclass that carries no IR-node children.
        Structural nodes (``IrTuple``, ``IrComposite``) override this.

        :returns: Empty tuple.
        """
        return ()

    def rebuild(self, _new_children: Sequence[Ir_co]) -> Self:
        """Reconstruct self under a tree transformation.

        Default: identity — return ``self`` unchanged.  Structural nodes
        override to splice in the transformed children supplied by a walker.

        :param _new_children: Replacement children (ignored at this level).
        :returns: ``self`` unchanged.
        """
        return self

    def __init_subclass__(cls, **kwargs: Any) -> None:
        """Auto-derive ``_bound`` from the class's OWN PEP 695 type parameters.

        Resolution strategy (applied once per class definition):

        1. If the subclass already declares ``_bound`` in its own ``__dict__``
           (e.g. ``IrStr._bound = str``, ``IrTuple._bound = tuple``), skip —
           the explicit declaration wins.
        2. Otherwise, inspect ``cls.__dict__["__type_params__"]`` (OWN params
           only — never walk the MRO, to avoid inheriting a parent's bound
           when the subclass introduces no new type parameters).
        3. Select the **last** own type parameter — the covariant return type
           ``Ir_co`` the :attr:`bound` property exposes (``type[Ir_co]``). It is
           the second of the ``[Iri, Ir_co]`` pair, or the sole parameter on
           single-parameter nodes. Taking the *last* (not the first) keeps the
           derivation correct now that nodes carry an input ``Iri`` parameter
           ahead of ``Ir_co``. If that ``TypeVar`` has a ``__bound__``, record
           it as ``cls._bound``.

        This means nodes declared as ``class IrFoo[Iri: IrSelf, Ir_co: IrStr]``
        automatically acquire ``_bound = IrStr`` without any explicit
        assignment.

        :param kwargs: Forwarded to ``super().__init_subclass__``.
        """
        super().__init_subclass__(**kwargs)
        if "_bound" in cls.__dict__:  # explicit _bound wins (IrStr/IrTuple)
            return
        params = cls.__dict__.get("__type_params__", ())  # OWN params — never MRO
        if params and isinstance(params[-1], TypeVar) and params[-1].__bound__:
            cls._bound = params[-1].__bound__

    @classmethod
    def bound_type(cls) -> type:
        """Return the concrete type bound to ``Ir_co`` for this class.

        Exposes the ``_bound`` ClassVar set by :meth:`__init_subclass__` or an
        explicit declaration on the concrete subclass.  Use this for class-level
        introspection (e.g. tests verifying derivation); use the :attr:`bound`
        instance property when you have an instance.

        :returns: The runtime class recorded as ``_bound`` on this class.
        :raises AttributeError: If ``_bound`` was never resolved for this class.
        """
        return cls._bound

    @property
    def bound(self) -> type[Ir_co]:
        """Concrete type bound to ``Ir_co`` for this instance.

        Used by generic action nodes (``IrDispatch``, ``IrTransformer``) to
        materialise their result type at runtime — this is NOT coercion;
        no value conversion happens here.  The property delegates to the
        class-level ``_bound`` ClassVar set by ``__init_subclass__`` or an
        explicit declaration on the concrete subclass.

        :returns: The runtime class recorded as ``_bound`` on ``type(self)``.
        :raises AttributeError: If ``_bound`` was never resolved for this class.
        """
        return type(self)._bound

    def bind(self, other: Any) -> Ir_co:
        """Return ``other`` typed as ``Ir_co`` if it satisfies ``_bound``, else raise.

        A lightweight type-safe cast used by action-algebra nodes to convert
        an untyped dispatch result back to the expected ``Ir_co``.  Does NOT
        construct or coerce — the value must already be the right type.

        :param other: Candidate value to bind.
        :returns: ``other`` as ``Ir_co``.
        :raises TypeError: If ``other`` is not an instance of ``_bound``.
        """
        if isinstance(other, self._bound):
            return other
        raise TypeError(f"Cannot bind {other!r} to {self!r}")


@final
class IrNoneType(IrSelf):
    """Type of the absence sentinel, mirroring ``NoneType``/``None``.

    ``IrNoneType`` is marked ``@final`` — subclassing is a **static** error
    (pyright/mypy flag it at type-check time).  No runtime ``__init_subclass__``
    guard is installed; ``@final`` is intentionally a static-only guarantee.

    ``IrNoneType`` IS-A ``IrSelf``, so the singleton :data:`IrNone` fits every
    dispatch slot typed ``IrSelf`` without introducing a ``| None`` union.  This
    collapses the historical ``IrNode | None`` pattern to a single concrete type.

    The class is public so callers can write ``isinstance(x, IrNoneType)`` or
    annotate parameters as ``IrSelf | IrNoneType``; the *value* to pass is
    always the singleton :data:`IrNone`.

    Implementation: singleton via ``__new__`` with a ``_instance`` ClassVar.
    The first call allocates; subsequent calls return the cached instance.
    """

    __slots__ = ()
    _instance: ClassVar[Self | None] = None

    def __new__(cls) -> Self:
        """Return the singleton instance, allocating it on the first call.

        :returns: The single ``IrNoneType`` instance.
        """
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance


# Public singleton VALUE — callers pass bare `IrNone`
IrNone = IrNoneType()


class IrNode[Iri: IrSelf, Ir_co: IrSelf = IrSelf](IrSelf[Iri, Ir_co], ABC):
    """ABC marker for all structural IR nodes.

    Generic in ``Ir_co`` — the return type of ``__call__`` when this node is
    invoked as an action body. ``IrNode[X]`` IS-AN ``IrSelf[X]`` and inherits
    the identity ``__call__ -> X`` from ``IrSelf``. Value-producing nodes
    (where ``Ir_co != Self``) override ``__call__``.

    **repr-is-codegen:** ``__repr__`` returns a valid Python constructor call
    that reconstructs an equal node. ``IrNode`` supplies a zero-argument default
    (``ClassName()``); field-bearing subclasses (``IrStr``/``IrTuple``/
    ``IrComposite``) override it to render their payload/children/fields. There
    is no separate ``__str__`` or ``_str_name``/``_inner_str`` cascade — that was
    deliberately removed in the G3 rewrite. Only ``__repr__`` exists.

    Dispatch slots carry bare ``IrNode`` types; absence is represented by
    :data:`IrNone`, not ``None``, keeping the signature union-free.

    :param Ir_co: the return type of ``eval`` (defaults to ``IrSelf``).
    """

    __slots__ = ()

    def __repr__(self) -> str:
        """Codegen default: a zero-argument constructor call ``ClassName()``.

        Field-bearing nodes override this — ``IrStr`` leaves render their string
        payload, ``IrTuple`` collections their elements, ``IrComposite`` records
        their dataclass fields. Zero-field nodes (the default action bodies
        ``IrPass``/``IrWalk``/``IrEmit``/``IrRebuild``) inherit this default,
        which is already valid codegen for them.

        :returns: A valid Python expression that constructs an equal node.
        """
        return f"{type(self).__name__}()"


class IrLeaf[Iri: IrSelf, Ir_co: IrSelf](IrNode[Iri, Ir_co]):
    """Base for all leaf nodes: no children, identity rebuild.

    Provides the default empty ``children()`` and identity ``rebuild()``
    from ``IrSelf``.  Concrete leaves inherit from ``IrStr`` (str-typed
    leaves) or from ``IrComposite`` (fixed-field records); ``IrLeaf`` itself
    carries no fields.

    Does NOT provide ``__call__`` — concrete leaves either inherit the
    identity from ``IrSelf`` or override ``eval`` (e.g. ``IrStr.eval``).
    """

    __slots__ = ()


class IrAtom(IrNode):
    """NON-generic role marker — mixed into atoms by plain inheritance.

    ``IrItem.atom: IrAtom`` accepts any ``IrAtom`` subclass; an
    ``isinstance(x, IrAtom)`` check is genuine MRO at zero runtime cost.

    ``IrAtom`` is intentionally non-generic (no ``[Ir_co]`` parameter) to
    avoid TypeVar conflicts when concrete atoms multi-inherit from both
    a parameterised structural base and ``IrAtom``.

    Open-set: a future atom type simply adds ``IrAtom`` to its bases without
    modifying any dispatch table.
    """

    __slots__ = ()


# ── Primitive str tier ────────────────────────────────────────────────


class IrScalar(IrLeaf):
    """Abstract base for value-carrying leaves (:class:`IrStr`, :class:`IrInt`).

    Hosts the behaviour shared by all value leaves: self-evaluating ``eval``,
    type-aware equality/hash (distinct leaf kinds never compare equal), and
    codegen ``__repr__``. Each subclass sets ``_bound`` to its primitive base,
    which drives payload comparison, hashing and rendering.

    Abstract **by convention**: instantiate a concrete leaf (``IrStr``/``IrInt``),
    never ``IrScalar`` itself — it has no primitive base to hold a payload, so
    ``IrScalar("x")`` fails. (Not an ``@abstractmethod`` ABC: the concrete leaves
    override no method to mark abstract, and an abstract ``IrScalar`` would make
    ``type[IrScalar]`` — e.g. :attr:`~lexic.ir.action.IrField.out` — un-callable
    for the type checker.)
    """

    __slots__ = ()

    def __new__(cls, *args: object) -> Self:
        """Forward construction to the primitive base.

        Exists so ``type[IrScalar]`` is callable with a payload (e.g. for
        :attr:`~lexic.ir.action.IrField.out`); subclasses carry no ``__new__``.
        No args ⇒ the primitive's own default (``""`` / ``0``).

        :param args: The payload, forwarded to the primitive ``__new__``.
        :returns: A new value-leaf instance.
        """
        return super().__new__(cls, *args)

    def eval(self, _d: IrSelf, _n: IrSelf, _nc: Sequence[IrSelf], /) -> Self:
        """Return ``self`` — the node IS the value.

        :returns: ``self``.
        """
        return self

    def __eq__(self, other: object) -> bool:
        """Type-aware equality: distinct leaf kinds never compare equal.

        ``IrLiteral('x') != IrRuleRef('x')`` even though each equals plain
        ``'x'`` — otherwise same-payload leaves of different kinds would collide
        in structural equality/hashing. Falls back to the primitive's equality
        (so a leaf still matches its plain-``str``/``int`` value).

        :param other: The value to compare against.
        :returns: ``True`` when equal under the rules above.
        """
        if isinstance(other, IrScalar) and type(self) is not type(other):
            return False
        return super().__eq__(other)

    def __ne__(self, other: object) -> bool:
        """Negation of :meth:`__eq__`, kept consistent with it.

        ``str``/``int`` supply their own ``__ne__`` (which ignores the
        leaf-kind check), so without this override ``a != b`` would disagree
        with ``not (a == b)`` for distinct same-payload leaves.

        :param other: The value to compare against.
        :returns: ``True`` when not equal under :meth:`__eq__`.
        """
        return not self == other

    def __hash__(self) -> int:
        """Hash by primitive payload, so a leaf matches its plain value as a key.

        :returns: The native ``str``/``int`` hash of the payload.
        """
        return super().__hash__()

    def __repr__(self) -> str:
        """Codegen repr: ``ClassName(payload)`` via the primitive's ``repr``.

        ``self._bound(self)`` strips the subclass to a plain ``str``/``int`` so
        ``!r`` renders the bare payload (quoted string / bare int), not a
        recursive node repr.

        :returns: Constructor call reproducing this node.
        """
        return f"{type(self).__name__}({self._bound(self)!r})"


class IrStr(IrScalar, str):
    """``IrSelf + str`` value leaf — the node IS the string.

    Multi-inherits :class:`IrScalar` and ``str`` so instances are both IR nodes
    and native strings. ``_bound`` is set explicitly (no PEP 695 type params).

    **Design note:** do **not** write ``IrLeaf[str]`` — ``str`` violates the
    ``Ir_co: IrSelf`` bound and triggers "mutually incompatible bases".
    """

    __slots__ = ()
    _bound: ClassVar[type[str]] = str


class IrInt(IrScalar, int):
    """Int-typed value leaf — the node IS the integer. Sibling of :class:`IrStr`.

    ``_bound`` is set explicitly (no PEP 695 type params).
    """

    __slots__ = ()
    _bound: ClassVar[type[int]] = int


# ── Primitive tuple tier ──────────────────────────────────────────────


class IrTuple[*Ts](IrNode, tuple[*Ts]):
    """``IrSelf + tuple`` primitive tier — a **heterogeneous** node IS its children.

    ``IrTuple`` is generic over a :pep:`646` ``TypeVarTuple`` (``*Ts``), so its
    type parameters ARE its positional element types, mirroring ``tuple``:

    - ``IrTuple[*tuple[IrItem, ...]]`` — homogeneous, variable length
      (what ``IrSequence``/``IrAlternation``/``IrAnd`` use).
    - ``IrTuple[IrOp, *tuple[IrSelf, ...]]`` — a fixed head followed by a
      variadic tail (an operator node: ``op`` at ``[0]``, then operands). The
      head is positionally type-checked.
    - ``IrTuple[IrAtom, IrQuantifier]`` — a fixed positional record (the shape
      ``IrComposite`` records could later fold into, e.g. as a ``NamedTuple``).

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

    __slots__ = ()
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
        return type(self)(*cast("tuple[*Ts]", tuple(evaluated)))

    def __repr__(self) -> str:
        """Codegen repr: ``ClassName(elem0, elem1, …)``.

        :returns: Constructor call reproducing this node.
        """
        return f"{type(self).__name__}({', '.join(map(repr, self))})"


class IrSeq[T: IrSelf](IrTuple[*tuple[T, ...]]):
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

    __slots__ = ()
    _bound: ClassVar[type[tuple]] = tuple


# ── Composite dataclass tier ──────────────────────────────────────────


class IrComposite[Iri: IrSelf, Ir_co: IrSelf = IrSelf](IrNode[Iri, Ir_co]):
    """Dataclass record base for fixed-arity IR nodes.

    All concrete composite nodes are ``@dataclass(frozen=True, slots=True,
    repr=False)`` subclasses. They declare:

    - ``_child_attrs: ClassVar[tuple[str, ...]]`` — names of dataclass fields
      that are IR-node children (in traversal order).  Records with no
      IR-node children declare ``_child_attrs = ()`` (the default).
    - The remaining dataclass fields (not in ``_child_attrs``) are non-child
      payload: names, bounds, flags, etc.

    ``__repr__`` is codegen: all dataclass fields are rendered as ``name=repr(value)``
    keyword arguments in declaration order, giving a valid constructor call.

    ``__dataclass_fields__`` is declared on the base class so that pyright
    accepts ``dataclasses.fields(self)`` / ``dataclasses.replace(self, …)``
    calls on ``IrComposite``-typed references, even though ``IrComposite``
    itself carries no ``@dataclass`` decorator.  Without this declaration,
    pyright reports ``"__dataclass_fields__ is not present"``.

    :param Ir_co: the return type of ``eval`` (defaults to ``IrSelf``).
    """

    __slots__ = ()
    # Declared so pyright accepts ``fields(self)``/``replace(self, …)`` on the
    # base even though IrComposite itself is not @dataclass-decorated (concrete
    # subclasses are). Without this the base errors with "__dataclass_fields__
    # is not present".
    __dataclass_fields__: ClassVar[dict[str, Any]]
    _child_attrs: ClassVar[tuple[str, ...]] = ()

    def children(self) -> Sequence[Ir_co]:
        """Return children in ``_child_attrs`` declaration order.

        :returns: Tuple of child IR nodes.
        """
        return tuple(getattr(self, a) for a in self._child_attrs)

    def rebuild(self, new_children: Sequence[Ir_co]) -> Self:
        """Reconstruct, replacing child attrs from ``new_children`` in order.

        Uses ``dataclasses.replace`` so frozen-dataclass immutability is
        respected; non-child payload fields are preserved unchanged.

        :param new_children: Replacements matching ``_child_attrs`` order.
        :returns: New instance with updated children.
        """
        return replace(self, **dict(zip(self._child_attrs, new_children)))

    def __repr__(self) -> str:
        """Codegen repr: ``ClassName(field=val, …)`` for all dataclass fields.

        Fields render as ``name=value`` keyword arguments in declaration order.
        A field holding a class (e.g. ``IrField.out``, ``IrAction.target_type``)
        renders as the bare class name (``out=IrInt``) so the result stays valid
        codegen; every other value uses ``repr``.

        :returns: Constructor call reproducing this node.
        """
        inner = ", ".join(
            f"{f.name}={self._field_repr(getattr(self, f.name))}" for f in fields(self)
        )
        return f"{type(self).__name__}({inner})"

    @staticmethod
    def _field_repr(value: object) -> str:
        """Render one field value as codegen: a class as its bare name, else ``repr``.

        :param value: The field value to render.
        :returns: ``value.__name__`` for a class, otherwise ``repr(value)``.
        """
        return value.__name__ if isinstance(value, type) else repr(value)
