"""Immutable hash map as a tuple subclass — attribute access IS the index.

The dyads ARE the tuple elements (payload, equality, hash, children, codegen
repr — all canonically sorted by key repr, so construction order never
matters). The index lives in the **class namespace**: ``IrMap(*dyads)``
resolves a memoised subclass — equal dyad tables share one class, weakly held —
and ``__init_subclass__`` mirrors each dyad as a class attribute named
``str(hash(key))``. Instance attribute lookup falls
back to the class natively, so key lookup is a single ``getattr`` — Python's
own O(1) machinery — with the dyad's key verified on read (a lookup may
collide with a stored hash; stored keys never collide, attribution rejects
that). No instance ``__dict__``, no ``__slots__`` exception: instances stay
pure tuples; the synthesized class keeps the constructor's name, so codegen
repr round-trips.

``m[key]``: ``IrSelf`` keys resolve via the index (``IrInt`` included —
node-ness wins over int-ness); plain integer/slice subscripts keep native
tuple indexing; any other key resolves via the index. A miss is a **hard
error** — :exc:`~lexic.exceptions.IrKeyError`, an ``UnsupportedConstructError``
that IS-A ``KeyError`` — everywhere: ``m[key]``, ``eval``, ``_find``.
``eval(d, n, nc)`` resolves ``n`` and evaluates the bound value against
``(d, n, nc)``: scalars self-evaluate (a data map), bodies run (an action
table).

``Mapping`` conformance: ``keys``/``values``/``items`` are real dict views
over a plain-dict snapshot — the map is immutable, so a snapshot view is
indistinguishable from a live one — and ``__contains__`` is key-based
(``get`` is the inherited mixin — it works because a miss IS-A ``KeyError``).
The one deliberate deviation is ``__iter__``, which yields **dyads** — the
node IS its children tuple, and walk/rebuild/structural equality depend on
that — so ``iter(m)`` ≠ ``iter(m.keys())``.
"""

from __future__ import annotations

from functools import lru_cache
from typing import (
    Any,
    ClassVar,
    Hashable,
    ItemsView,
    KeysView,
    Mapping,
    NoReturn,
    Self,
    Sequence,
    SupportsIndex,
    ValuesView,
    cast,
    final,
    overload,
)
from weakref import WeakValueDictionary

from lexic.exceptions import IrKeyError, UnsupportedConstructError
from lexic.ir.base import IrNone, IrSelf, IrSeq, IrTuple
from lexic.ir.meta import IrSingleton


@final
class _IrMapDefault(IrSelf, metaclass=IrSingleton):
    """Type of the :class:`IrMap`/:class:`IrTypeMap` catch-all sentinel key.

    A singleton key, distinct from every real key (identity eq/hash, like
    :class:`~lexic.ir.base.IrNoneType`). Register its value once — ``IrTuple(
    IR_DEFAULT, body)`` — and a key miss in :meth:`IrMap.resolve` resolves
    to it instead of raising :exc:`~lexic.exceptions.IrKeyError`. Omit it and a
    miss still errors. Opt-in fallback, no subclass needed. One instance per
    class via the :class:`~lexic.ir.meta.IrSingleton` metaclass.
    """

    def __repr__(self) -> str:
        """Codegen repr — the singleton's public name."""
        return "IR_DEFAULT"


IR_DEFAULT = _IrMapDefault()
"""Catch-all sentinel key for :class:`IrMap`/:class:`IrTypeMap` miss-fallback."""


class IrMap[K, V: IrSelf](IrSeq[IrTuple[K, V]], Mapping):
    """Dyad tuple whose entries are attributes of its synthesized class.

    ``_bound`` is re-declared ``tuple`` so the own ``V`` parameter does not
    re-derive it (the :class:`~lexic.ir.base.IrSeq` move).
    """

    _bound: ClassVar[type[tuple]] = tuple
    _classes: ClassVar[WeakValueDictionary[tuple[type, tuple], type]] = (
        WeakValueDictionary()
    )

    def __init_subclass__(cls, dyads: tuple[IrTuple, ...] = (), **kwargs: Any) -> None:
        """Attribute each dyad into the new class's namespace, by key hash.

        Statically declared subclasses (:class:`IrTypeMap`) pass no ``dyads``
        and are left untouched; :meth:`__new__` passes the instance's table.

        :raises UnsupportedConstructError: On duplicate or hash-colliding keys.
        """
        super().__init_subclass__(**kwargs)
        for dyad in dyads:
            name = str(hash(dyad[0]))
            if name in vars(cls):
                raise UnsupportedConstructError(
                    f"{cls.__name__}: duplicate or hash-colliding key {dyad[0]!r}"
                )
            setattr(cls, name, dyad)

    @overload
    def __new__(cls, *dyads: IrTuple[K, V]) -> Self: ...
    @overload
    def __new__(
        cls, *dyads: IrTuple[K, V] | IrTuple[_IrMapDefault, IrSelf]
    ) -> Self: ...
    def __new__(cls, *dyads: IrTuple) -> Self:
        """Sort canonically, resolve the memoised indexed subclass, build the tuple.

        Equal dyad tables share one synthesized class — keyed by ``(cls, dyads)``,
        weakly held — so type-keyed caches (e.g. dispatch memoisation) grow with
        distinct map values, not instances. The subclass keeps ``cls.__name__``,
        so ``repr`` stays valid codegen.

        Two overloads: the homogeneous ``IrTuple[K, V]`` form infers ``K``/``V``
        for ordinary tables; the bare ``IrTuple`` fallback admits a heterogeneous
        :data:`IR_DEFAULT` dyad (its ``_IrMapDefault`` key and distinct value
        would otherwise clash with the invariant ``Ts`` solved from the first
        dyad). When the fallback applies, ``K``/``V`` come from the binding
        annotation.
        """
        order = tuple(sorted(dyads, key=lambda d: repr(d[0])))
        sub = cls._classes.get((cls, order))
        if sub is None:
            sub = type(cls)(cls.__name__, (cls,), {}, dyads=order)
            cls._classes[cls, order] = sub
        return super().__new__(cast(type[Self], sub), *order)

    def _frozen(self, *_: object) -> NoReturn:
        """Attribute surface is frozen. :raises TypeError: Always."""
        raise TypeError(f"{type(self).__name__} is immutable")

    __setattr__ = __delattr__ = _frozen

    def _keys(self, n: IrSelf) -> tuple[Hashable, ...]:
        """Candidate keys for ``n`` — just ``n`` itself at this level."""
        return (n,)

    def _find(self, *keys: object) -> IrTuple[K, V]:
        """First dyad among candidate ``keys`` — one ``getattr`` each, key-verified.

        :raises IrKeyError: When no candidate resolves.
        """
        for key in keys:
            dyad = getattr(self, str(hash(key)), IrNone)
            if isinstance(dyad, IrTuple) and dyad[0] == key:
                return dyad
        raise IrKeyError(f"{type(self).__name__}: no entry for {keys!r}")

    @lru_cache
    def _as_dict(self) -> dict[K, V]:
        """Plain-dict snapshot of the dyads, in canonical order.

        Safe to snapshot: the map is immutable, so the copy never drifts.
        """
        return {dyad[0]: dyad[1] for dyad in self}

    def keys(self) -> KeysView[K]:
        """Key view, canonical order."""
        return self._as_dict().keys()

    def values(self) -> ValuesView[V]:
        """Value view, canonical order."""
        return self._as_dict().values()

    def items(self) -> ItemsView[K, V]:
        """``(key, value)`` pair view, canonical order."""
        return self._as_dict().items()

    def __contains__(self, key: object) -> bool:
        """Key containment (``Mapping`` semantics), not dyad containment."""
        try:
            self._find(key)
        except IrKeyError:
            return False
        return True

    @overload
    def __getitem__(self, key: SupportsIndex, /) -> Any: ...
    @overload
    def __getitem__(self, key: slice, /) -> tuple[Any, ...]: ...
    @overload
    def __getitem__(self, key: IrSelf | type, /) -> IrSelf: ...
    def __getitem__(self, key: object, /) -> object:
        """Key lookup for IR nodes; positional for plain index/slice.

        ``IrSelf`` wins over ``int``, so ``IrInt`` keys resolve via the index;
        only plain integers/slices keep tuple semantics.

        :raises IrKeyError: On a key miss.
        """
        if not isinstance(key, IrSelf) and isinstance(key, (int, slice)):
            return super().__getitem__(key)
        return self._find(key)[1]

    def resolve(self, n: IrSelf) -> V:
        """The value bound to ``n``'s first matching candidate key, unevaluated.

        The resolution seam for consumers that separate lookup from evaluation
        (e.g. :class:`~lexic.ir.walk.IrDispatch` falling back to a default on
        a miss without muting errors raised by the resolved body).
        :data:`IR_DEFAULT` is the last candidate tried, so a table that
        registers it resolves any miss to its value; one that does not still
        raises. ``__getitem__``/``__contains__`` bypass this — membership and
        subscript stay explicit-key only.

        :raises IrKeyError: On a miss with no :data:`IR_DEFAULT` entry.
        """
        return self._find(*self._keys(n), IR_DEFAULT)[1]

    def eval(self, d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> IrSelf:
        """Resolve ``n`` to its value; evaluate it against ``(d, n, nc)``.

        :raises IrKeyError: On a miss.
        """
        return self.resolve(n).eval(d, n, nc)


class IrTypeMap(IrMap[type, IrSelf]):
    """Type-keyed :class:`IrMap` — resolves ``n`` via ``type(n).__mro__``,
    concrete first: one ``getattr`` per MRO entry, bounded by class depth, not
    table size. The dispatch-table shape: an ``IrAction(target_type, body)``
    is exactly a ``(type, body)`` dyad. The parameterised base pins
    ``keys() -> KeysView[type]`` and ``resolve() -> IrSelf`` statically."""

    def _keys(self, n: IrSelf) -> tuple[Hashable, ...]:
        """``type(n).__mro__`` — concrete-first resolution order."""
        return type(n).__mro__


class IrMultiMap[K, V: IrSelf](IrMap[K, V]):
    """Mutable, multi-valued :class:`IrMap` — a key to its insertion-ordered bucket.

    The mutable counterpart of :class:`IrMap`. A tuple subtype cannot carry an
    extra instance slot, so the backing ``dict`` rides as the map's sole tuple
    element (read past the key-override via ``tuple.__getitem__``): the tuple
    reference stays constant while its dict mutates in place. ``mm += (key,
    value)`` files a value in O(1) and ``mm[key]`` reads the bucket as an
    :class:`~lexic.ir.base.IrSeq` snapshot (empty on a miss) — an ``IrSeq`` so
    the read stays assignable to :class:`IrMap`'s value-returning ``__getitem__``.
    ``key in mm`` tests for a filed bucket. It is its own value (identity
    equality): a mutable map never structurally equals another.

    Engine-internal — the Earley driver's per-column "waiting on" index, the
    mapping form of the package's mutable-chart exception. It is never walked,
    emitted, or reduced as a tree, so the frozen :class:`IrMap` surface
    (``resolve`` / ``eval`` / dyad iteration) is left behind; only the read and
    write dunders below are live.
    """

    __slots__ = ()

    def __new__(cls, *_dyads: IrTuple) -> Self:
        """Build an empty map whose sole tuple element is its backing dict."""
        return tuple.__new__(cls, ({},))

    @property
    def _table(self) -> dict[K, list[V]]:
        """The backing dict — the sole tuple element, read past the override."""
        return tuple.__getitem__(self, 0)

    def __iadd__(self, entry: tuple[K, V]) -> Self:
        """File ``value`` under ``key``, preserving insertion order.

        :param entry: The ``(key, value)`` pair to file.
        :returns: ``self`` (the in-place-mutated map).
        """
        key, value = entry
        self._table.setdefault(key, []).append(value)
        return self

    def __getitem__(self, key: object, /) -> IrSeq[V]:
        """The bucket filed under ``key`` as an :class:`IrSeq` (empty on a miss)."""
        return IrSeq(*self._table.get(cast(K, key), ()))

    def __contains__(self, key: object) -> bool:
        """Whether ``key`` has a filed bucket."""
        return key in self._table

    def __eq__(self, other: object) -> bool:
        """Identity equality — a mutable map is its own value."""
        return self is other

    def __ne__(self, other: object) -> bool:
        """Negation of :meth:`__eq__`."""
        return self is not other

    def __hash__(self) -> int:
        """Identity hash, consistent with identity equality."""
        return id(self)
