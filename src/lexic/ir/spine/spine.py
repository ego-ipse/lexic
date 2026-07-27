"""IR spine — the abstract bases every node sits on.

``IrSelf`` and the tiers over it: ``IrNode`` (children and rebuild),
``IrLeaf`` (no children), ``IrAtom``, and the two values that need no tier —
``IrNoneType``/``IrNone``, which is absence, and ``IrLambda``, which is the one
node whose payload is a callable and therefore the one the notation refuses.

Everything else in ``lexic.ir`` is downstream of this file: the scalars and the
tuple tiers both build on it, and nothing here imports either.
"""

from __future__ import annotations

import ast
from abc import ABC
from collections.abc import Callable
from inspect import getsourcefile
from pathlib import Path
from types import FunctionType
from typing import (
    Any,
    ClassVar,
    Self,
    Sequence,
    TypeVar,
    cast,
    final,
)

from lexic.exceptions import UnsupportedConstructError
from lexic.ir.spine.meta import IrMeta, IrSingleton


class IrSelf[Iri: "IrSelf", Ir_co: "IrSelf" = Iri](metaclass=IrMeta):
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

    :param Iri: the concrete type of ``self``
    :param Ir_co: the return type of ``eval``.
    """

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
        Structural nodes (``IrTuple``, ``IrNamedTuple``) override this.

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

    @classmethod
    def ensure(cls, node: object, what: str = "") -> Self:
        """Return ``node`` typed as this class, or refuse.

        The boundary narrow. Several seams hand a value back at a type wider
        than the caller can use — ``parse_reduced`` returns ``IrSelf`` because
        a reducer folds to whatever its bodies produce, and a document's
        actual shape is runtime information no signature can carry. Asserting
        that shape is legitimate; hand-rolling the assert at every seam is
        not, so this is the one spelling.

        The class-level sibling of :meth:`bind`: ``bind`` narrows a dispatch
        result to an instance's ``_bound`` at runtime, ``ensure`` narrows an
        untyped value to a named class *statically* — ``IrMap.ensure(x)`` is
        an ``IrMap`` to a type checker.

        Not a coercion and not a cast: nothing is converted, and a value of
        the wrong type raises rather than being reinterpreted.

        :param node: The value to narrow.
        :param what: What ``node`` is, for the message (e.g. ``"the reduced
            document"``); omitted, the message just names the types.
        :returns: ``node``, typed as this class.
        :raises UnsupportedConstructError: If ``node`` is not an instance.
        """
        if isinstance(node, cls):
            return node
        subject = f"{what} is" if what else "expected"
        raise UnsupportedConstructError(
            f"{subject} {type(node).__name__}, not {cls.__name__}"
        )


@final
class IrNoneType(IrSelf, metaclass=IrSingleton):
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

    Implementation: one instance per class via the
    :class:`~lexic.ir.spine.meta.IrSingleton` metaclass.
    """

    def __repr__(self) -> str:
        """Codegen repr — the singleton's public name.

        :returns: ``"IrNone"``, a valid expression naming the singleton.
        """
        return "IrNone"


# Public singleton VALUE — callers pass bare `IrNone`
IrNone = IrNoneType()
"""Public singleton instance of ``IrNoneType``. Ir's pythonic answer to ``None``."""


class IrNode[Iri: IrSelf, Ir_co: IrSelf = IrSelf](IrSelf[Iri, Ir_co], ABC):
    """ABC marker for all structural IR nodes.

    Generic in ``Ir_co`` — the return type of ``__call__`` when this node is
    invoked as an action body. ``IrNode[X]`` IS-AN ``IrSelf[X]`` and inherits
    the identity ``__call__ -> X`` from ``IrSelf``. Value-producing nodes
    (where ``Ir_co != Self``) override ``__call__``.

    **repr-is-codegen:** ``__repr__`` returns a valid Python constructor call
    that reconstructs an equal node. ``IrNode`` supplies a zero-argument default
    (``ClassName()``); field-bearing subclasses (``IrStr``/``IrTuple``/
    ``IrNamedTuple``) override it to render their payload/children/fields. There
    is no separate ``__str__`` or ``_str_name``/``_inner_str`` cascade — that was
    deliberately removed in the G3 rewrite. Only ``__repr__`` exists.

    Dispatch slots carry bare ``IrNode`` types; absence is represented by
    :data:`IrNone`, not ``None``, keeping the signature union-free.

    :param Ir_co: the return type of ``eval`` (defaults to ``IrSelf``).
    """

    def __repr__(self) -> str:
        """Codegen default: a zero-argument constructor call ``ClassName()``.

        Field-bearing nodes override this — ``IrStr`` leaves render their string
        payload, ``IrTuple`` collections their elements, ``IrNamedTuple`` records
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
    leaves) or from ``IrNamedTuple`` (fixed-field records); ``IrLeaf`` itself
    carries no fields.

    Does NOT provide ``__call__`` — concrete leaves either inherit the
    identity from ``IrSelf`` or override ``eval`` (e.g. ``IrStr.eval``).
    """

    def children(self) -> Sequence[Ir_co]:
        """Leaf nodes have no children by definition.

        :returns: The empty tuple.
        """
        return ()


class IrLambda(IrNode[IrSelf, IrSelf]):
    """Minimal procedural escape hatch — the stored callable IS the eval.

    Variadic: the wrapped callable is attached as the ``eval`` slot and invoked
    with whatever arguments the caller supplies — a dispatch body is called as
    ``(d, n, nc) -> IrSelf``, while an operator body is called variadically over
    the operands (``IrLambda(operator.eq).eval(*nc)``). No fold convention, no
    node-handler branch (the two modes the old IrCallable had). Equality
    is by identity and ``repr`` is name-based: a closure is not round-trippable
    codegen, the one invariant this node may break.

    :param fn: The callable invoked on dispatch.
    """

    __slots__ = ("eval",)
    # The wrapped callable IS eval. Its return is heterogeneous — IrSelf for a
    # dispatch body, a raw operand-fold result the caller wraps — so Any is the
    # honest escape-hatch type. Dispatch consumers are unaffected: they hold
    # bodies as IrSelf and call IrSelf.eval, never IrLambda.eval directly.
    eval: Callable[..., Any]

    def __new__(cls, fn: Callable[..., Any], /) -> Self:
        """Wrap ``fn`` as an immutable leaf.

        :param fn: The callable serving as ``eval`` — a ``(d, n, nc) -> IrSelf``
            dispatch body or a bare operand fold applied variadically.
        :returns: The new ``IrLambda`` leaf.
        """
        obj = object.__new__(cls)
        object.__setattr__(obj, "eval", fn)
        return obj

    def __repr__(self) -> str:
        """Codegen repr: the closure's name, or a lambda's exact source.

        A named closure renders by name (a module global, in scope at
        ``eval(repr(...))`` time); a lambda renders by the source segment of
        its own AST node — located in the defining file by first line and
        positional arg count, so the surrounding statement is never captured
        (``getsource`` would return the whole physical line).

        :returns: ``IrLambda(<name-or-lambda-source>)``.
        :raises UnsupportedConstructError: If a lambda has no source file or
            cannot be uniquely located (two same-arity lambdas share its line) —
            failing loudly keeps the repr honest codegen, never a wrong segment.
        """
        fn = cast(FunctionType, self.eval)
        if fn.__name__ != "<lambda>":
            return f"{type(self).__name__}({fn.__name__})"
        path = getsourcefile(fn)
        if path is None:
            raise UnsupportedConstructError("IrLambda repr: closure has no source")
        source = Path(path).read_text(encoding="utf-8")
        line, nargs = fn.__code__.co_firstlineno, fn.__code__.co_argcount
        hits = [
            node
            for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.Lambda)
            and node.lineno == line
            and len(node.args.args) == nargs
        ]
        segment = ast.get_source_segment(source, hits[0]) if len(hits) == 1 else None
        if segment is None:
            raise UnsupportedConstructError(
                f"IrLambda repr: cannot isolate lambda at {path}:{line} "
                f"({len(hits)} candidate(s))"
            )
        return f"{type(self).__name__}({segment})"


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


# ── Primitive str tier ────────────────────────────────────────────────
