"""IR AST node dataclasses — primitive node model.

Nodes *are* their payload:

- str-leaves subclass :class:`str` (``IrStr`` tier);
- variadic collections subclass :class:`tuple` (``IrTuple`` tier);
- fixed-arity records are :class:`IrComposite` dataclasses.

Every IR node implements the structural protocol from :class:`IrSelf`:

- ``__call__(d, n, nc) -> Self``       identity evaluation
- ``eval(d, n, nc) -> Ir_co``          action-body protocol
- ``children() -> Sequence[Ir_co]``    children in traversal order
- ``rebuild(new_children) -> Self``    reconstruct under transformation

``__repr__`` is codegen: every node reproduces its own constructor call.
"""

from __future__ import annotations

from abc import ABC
from dataclasses import dataclass, fields, replace
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
    """Base for value-carrying leaves (:class:`IrStr`, :class:`IrInt`).

    Hosts the behaviour shared by all value leaves: self-evaluating ``eval``,
    type-aware equality/hash (distinct leaf kinds never compare equal), and
    codegen ``__repr__``. Each subclass sets ``_bound`` to its primitive base
    (``str``/``int``), which drives payload comparison, hashing and rendering.
    """

    __slots__ = ()

    def __new__(cls, *args: object) -> Self:
        """Forward construction to the primitive base (``str``/``int``).

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


class IrLiteral(IrStr, IrAtom):
    """Literal string. The string itself is the payload (escapes already decoded).

    Carries a dual role in the IR:

    - As a grammar AST leaf: the literal characters that must appear verbatim.
    - As an action-language constant: a baked-in string an action body returns.

    The two roles are distinguished at eval time by the ``nc`` parameter — see
    the IR-shapes wiki entry.  Both roles produce the same ``str`` value, so
    the same node class serves both.
    """

    __slots__ = ()


class IrCharClass(IrStr, IrAtom):
    """Character class. The string is the canonical POSIX-style interior pattern.

    Examples: ``'a-z'``, ``'0-9'``, ``'a-zA-Z_'``.  The surrounding ``[``/``]``
    brackets are NOT stored — they are emitted by the flavour renderer.
    """

    __slots__ = ()


class IrRuleRef(IrStr, IrAtom):
    """Reference to another rule. The string is the rule name.

    Used in rule bodies to denote a non-terminal; the name matches the
    ``IrRule.name`` of the referenced rule.
    """

    __slots__ = ()


# ── Primitive tuple tier ──────────────────────────────────────────────


class IrTuple[T: IrSelf](IrNode, tuple):
    """``IrSelf + tuple`` primitive tier. A variadic node IS its children.

    ``IrTuple`` multi-inherits ``IrNode`` and ``tuple`` so instances are both
    full IR nodes and native Python tuples (indexing, iteration, equality,
    hashing all work natively).

    The node's children ARE the tuple elements; ``children()`` returns
    ``self`` and ``rebuild(new_children)`` constructs a new instance from the
    replacement elements via the variadic ``*items`` constructor.

    ``_bound`` is explicitly set to ``tuple`` (parallel to ``IrStr._bound = str``)
    so :attr:`IrSelf.bound` resolves correctly without PEP 695 auto-derivation.

    ``__repr__`` is codegen: ``IrSequence(IrItem(...), IrItem(...))`` reproduces
    the constructor call.

    :param T: The element type, bounded by ``IrSelf``.
    """

    __slots__ = ()
    _bound: ClassVar[type[tuple]] = tuple

    def __new__(cls, *items: T) -> Self:
        """Construct from variadic positional items.

        :param items: Zero or more child nodes.
        :returns: A new instance of the concrete subclass containing ``items``.
        """
        return super().__new__(cls, items)

    def children(self) -> Sequence[T]:
        """Return the tuple elements as the structural children.

        :returns: ``self`` (the tuple IS the children sequence).
        """
        return self

    def rebuild(self, new_children: Sequence[IrSelf]) -> Self:
        """Reconstruct with replacement children.

        :param new_children: Replacement elements; must be compatible with ``T``.
        :returns: New instance of the same concrete type containing ``new_children``.
        """
        # base-compatible param (Sequence[IrSelf]); cast for the *items: T ctor
        return type(self)(*cast(Sequence[Any], new_children))

    def eval(self, d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> Self:
        """Dispatch each element via its own ``eval`` and rebuild the tuple.

        :param d: Dispatcher forwarded to each element's ``eval``.
        :param n: Parent node forwarded to each element's ``eval``.
        :param nc: Pre-walked children forwarded to each element's ``eval``.
        :returns: New instance containing the evaluated elements.
        """
        return type(self)(*(p.eval(d, n, nc) for p in self))

    def __repr__(self) -> str:
        """Codegen repr: ``ClassName(elem0, elem1, …)``.

        :returns: Constructor call reproducing this node.
        """
        return f"{type(self).__name__}({', '.join(map(repr, self))})"


class IrSequence(IrTuple["IrItem"]):
    """Concatenation (sequence) of ``IrItem`` nodes.

    Represents an ordered sequence of grammar items that must all match in
    order.  Corresponds to the ``items`` tuple in a single alternation arm.
    """

    __slots__ = ()


class IrAlternation(IrTuple["IrSequence"]):
    """Ordered choice (alternation) between ``IrSequence`` arms.

    Represents the ``|``-separated alternatives in a grammar rule body.
    Each arm is an ``IrSequence``; the first matching arm wins.
    """

    __slots__ = ()


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

        All fields — both child attrs and non-child payload — are rendered
        as ``name=repr(value)`` keyword arguments in dataclass declaration
        order.  This ensures the output is a valid Python constructor call.

        :returns: Constructor call reproducing this node.
        """
        inner = ", ".join(f"{f.name}={getattr(self, f.name)!r}" for f in fields(self))
        return f"{type(self).__name__}({inner})"


@dataclass(frozen=True, slots=True, repr=False)
class IrQuantifier(IrComposite):
    """Repetition bounds for an ``IrItem``.

    ``min`` and ``max`` mirror POSIX/PCRE repetition bounds:

    - ``IrQuantifier(1, 1)`` — exactly once (the default; no postfix operator).
    - ``IrQuantifier(0, 1)`` — optional (``?``).
    - ``IrQuantifier(0, None)`` — zero-or-more (``*``).
    - ``IrQuantifier(1, None)`` — one-or-more (``+``).
    - ``IrQuantifier(m, n)`` — between ``m`` and ``n`` times (``{m,n}``).

    ``max=None`` means unbounded (no upper limit).  ``IrQuantifier`` carries
    no IR-node children (``_child_attrs = ()`` inherited default).
    """

    min: int = 1
    max: int | None = 1


@dataclass(frozen=True, slots=True, repr=False)
class IrItem(IrComposite):
    """An atom paired with a quantifier — the universal wrapper node.

    ``IrItem`` is the fundamental unit of a grammar sequence.  Every element
    in an ``IrSequence`` is an ``IrItem``.  The ``atom`` field accepts any
    ``IrAtom`` subclass (``IrLiteral``, ``IrCharClass``, ``IrRuleRef``,
    ``IrGroup``, ``IrNot``).

    Children (in ``_child_attrs`` order): ``atom``, ``quantifier``.
    """

    _child_attrs: ClassVar[tuple[str, ...]] = ("atom", "quantifier")
    atom: IrAtom
    quantifier: IrQuantifier = IrQuantifier()


@dataclass(frozen=True, slots=True, repr=False)
class IrGroup(IrComposite, IrAtom):
    """Parenthesised group — an ``IrAtom`` whose body is an ``IrAlternation``.

    Corresponds to ``( … )`` in GBNF/ABNF.  Because ``IrGroup`` IS-AN
    ``IrAtom``, it can be wrapped by ``IrItem`` and appear anywhere an atom
    is expected — including as the ``atom`` field of another ``IrItem``.

    Children: the single ``body`` ``IrAlternation``.
    """

    _child_attrs: ClassVar[tuple[str, ...]] = ("body",)
    body: IrAlternation


@dataclass(frozen=True, slots=True, repr=False)
class IrNot[Ir_co: IrAtom = IrAtom](IrComposite, IrAtom):
    """Negation — an ``IrAtom`` that inverts a character class or atom.

    Corresponds to ``[^…]`` (negated character class) in GBNF.  The ``body``
    field is typically an ``IrCharClass`` but accepts any ``IrAtom`` subtype
    via the ``Ir_co`` parameter.

    Because ``IrNot`` IS-AN ``IrAtom``, it can be wrapped by ``IrItem``
    like any other atom.

    Children: the single ``body`` atom.

    :param Ir_co: Concrete atom type of the wrapped body (defaults to ``IrAtom``).
    """

    _child_attrs: ClassVar[tuple[str, ...]] = ("body",)
    body: Ir_co


@dataclass(frozen=True, slots=True, repr=False)
class IrRule(IrComposite):
    """A named grammar rule.

    The ``body`` is always an ``IrAlternation``, even for single-arm rules
    (a single arm is an ``IrAlternation`` containing one ``IrSequence``).

    Children: the single ``body`` ``IrAlternation``.
    Non-child payload: ``name`` (the rule identifier string).
    """

    _child_attrs: ClassVar[tuple[str, ...]] = ("body",)
    name: str
    body: IrAlternation


@dataclass(frozen=True, slots=True, repr=False)
class IrAst(IrComposite):
    """Full grammar AST: a collection of rules plus the start-rule name.

    ``rules`` is an ``IrTuple`` of ``IrRule`` nodes (wrapped so a single
    child attribute can hold the whole collection and be replaced atomically
    by tree transformations).  ``start`` is the plain string name of the
    start rule.

    Children: the single ``rules`` ``IrTuple``.
    Non-child payload: ``start`` (start-rule name).
    """

    _child_attrs: ClassVar[tuple[str, ...]] = ("rules",)
    rules: IrTuple = IrTuple()
    start: str = ""
