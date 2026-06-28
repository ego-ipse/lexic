"""Fast map family — a common ``IrMapping`` ancestor owning all shared logic.

Drop-in replacement for :mod:`~lexic.ir.mapping` (does **not** import from it —
:data:`IR_DEFAULT` is duplicated so this module stands alone and can supersede
the original by a file rename). The ancestor owns the whole read/eval surface
over a single ``_table`` slot; the concrete maps add only construction and the
one read that genuinely differs (bucket vs value).

- :class:`IrMapping` — common ancestor on :class:`~lexic.ir.base.IrLeaf`, generic
  over ``[K, V, R]`` (key, eval-value, read-return). Owns ``_table``, empty
  construction, the frozen surface, ``__getitem__`` (value, raise on miss — the
  mapping default), ``__contains__`` / ``get`` / ``__len__`` / ``keys`` /
  ``values`` / ``items`` / ``__iter__`` / ``__repr__``, the eval protocol
  (``resolve`` + ``eval``), and structural ``__eq__`` / ``__ne__`` / ``__hash__``.
- :class:`IrMap` — immutable key→value map (``R = V``); adds only the dyad-indexing
  ``__new__``.
- :class:`IrTypeMap` — type-keyed dispatch; overrides ``resolve`` for the
  ``type(n).__mro__`` walk (exact-type ``_table.get`` fast path first).
- :class:`IrMultiMap` — mutable multi-valued map (``R = Sequence[V]``); ``mm[key]``
  overrides to return the **live** bucket (``()`` on a miss, no raise, no copy),
  ``mm += (k, v)`` files in O(1). Identity equality.
"""

from __future__ import annotations

from typing import (
    Any,
    ItemsView,
    Iterator,
    KeysView,
    NoReturn,
    Self,
    Sequence,
    ValuesView,
    final,
)

from lexic.exceptions import IrKeyError, UnsupportedConstructError
from lexic.ir.base import IrLeaf, IrSelf, IrTuple
from lexic.ir.meta import IrSingleton


@final
class _IrMapDefault(IrSelf, metaclass=IrSingleton):
    """Type of the :data:`IR_DEFAULT` catch-all key — a singleton distinct from
    every real key (identity eq/hash, like :data:`~lexic.ir.base.IrNone`)."""

    def __repr__(self) -> str:
        """Codegen repr — the singleton's public name."""
        return "IR_DEFAULT"


IR_DEFAULT = _IrMapDefault()
"""Catch-all sentinel key: register ``(IR_DEFAULT, body)`` and a key miss in
:meth:`IrMapping.resolve` resolves to it instead of raising."""


class IrMapping[K, V: IrSelf, R](IrLeaf[IrSelf, IrSelf]):
    """Common ancestor of the map family — owns the whole surface over ``_table``.

    Generic over the key ``K``, the eval-value ``V`` (an :class:`IrSelf`, what
    :meth:`resolve` yields and :meth:`eval` runs) and the **read return** ``R``
    (what ``__getitem__`` / ``values`` / ``get`` yield — a value for
    :class:`IrMap`, a bucket for :class:`IrMultiMap`). The default
    ``__getitem__`` is the value read (raise on miss); :class:`IrMultiMap`
    overrides it for live buckets. Subclasses otherwise add only construction.
    """

    __slots__ = ("_table",)
    _table: dict[Any, Any]

    def __new__(cls, *_dyads: IrTuple) -> Self:
        """Seed an empty map. :class:`IrMap` overrides to index its dyads."""
        obj = object.__new__(cls)
        object.__setattr__(obj, "_table", {})
        return obj

    def __setattr__(self, name: str, value: object) -> NoReturn:
        """Frozen. :raises TypeError: Always."""
        raise TypeError(f"{type(self).__name__} is immutable")

    def __delattr__(self, name: str) -> NoReturn:
        """Frozen. :raises TypeError: Always."""
        raise TypeError(f"{type(self).__name__} is immutable")

    def __getitem__(self, key: object) -> R:
        """Value bound to ``key`` (the mapping default — raise on miss).

        :class:`IrMultiMap` overrides this to return a live bucket.
        :raises IrKeyError: On a miss.
        """
        value = self._table.get(key)
        if value is not None:
            return value
        raise IrKeyError(f"{type(self).__name__}: no entry for {key!r}")

    def __contains__(self, key: object) -> bool:
        """Whether ``key`` has an entry (key-based, not dyad membership)."""
        return key in self._table

    def __len__(self) -> int:
        """Number of entries."""
        return len(self._table)

    def get(self, key: object, default: R | None = None) -> R | None:
        """Read under ``key``, or ``default`` on a miss (never raises)."""
        return self._table.get(key, default)

    def keys(self) -> KeysView[K]:
        """Key view over ``_table`` (canonical order for :class:`IrMap`)."""
        return self._table.keys()

    def values(self) -> ValuesView[R]:
        """Value view over ``_table``."""
        return self._table.values()

    def items(self) -> ItemsView[K, R]:
        """``(key, value)`` view over ``_table``."""
        return self._table.items()

    def __iter__(self) -> Iterator[IrSelf]:
        """Iterate dyads reconstructed from ``_table`` (the walk contract)."""
        return (IrTuple(key, value) for key, value in self._table.items())

    def resolve(self, n: IrSelf) -> V:
        """Eval-value bound to ``n``, with :data:`IR_DEFAULT` fallback.

        :raises IrKeyError: On a miss with no :data:`IR_DEFAULT` entry.
        """
        table = self._table
        value = table.get(n)
        if value is not None:
            return value
        value = table.get(IR_DEFAULT)
        if value is not None:
            return value
        raise IrKeyError(f"{type(self).__name__}: no entry for {n!r}")

    def eval(self, d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> IrSelf:
        """Resolve ``n`` to its value and evaluate it against ``(d, n, nc)``.

        :raises IrKeyError: On a miss.
        """
        return self.resolve(n).eval(d, n, nc)

    def __eq__(self, other: object) -> bool:
        """Structural equality — same concrete type and same table.

        The default for immutable maps; :class:`IrMultiMap` overrides to identity.
        """
        if not isinstance(other, IrMapping) or type(self) is not type(other):
            return NotImplemented
        return self._table == other._table

    def __ne__(self, other: object) -> bool:
        """Negation of :meth:`__eq__`."""
        result = self.__eq__(other)
        if result is NotImplemented:
            return result
        return not result

    def __hash__(self) -> int:
        """Structural hash over the table entries."""
        return hash(frozenset(self._table.items()))

    def __repr__(self) -> str:
        """Codegen repr — the entries rendered as ``IrTuple`` dyads.

        ``eval(repr(m))`` reconstructs a structurally equal map (equality is over
        ``_table``, so the dyad node type is immaterial).
        """
        dyads = ", ".join(repr(IrTuple(k, v)) for k, v in self._table.items())
        return f"{type(self).__name__}({dyads})"


class IrMap[K, V: IrSelf](IrMapping[K, V, V]):
    """Immutable key→value map (``R = V``). Adds only the dyad-indexing
    constructor; the whole read/eval/equality surface is inherited from
    :class:`IrMapping`. ``_table`` is built in canonical (key-repr-sorted) order,
    so the inherited views and repr are order-stable.
    """

    __slots__ = ()

    def __new__(cls, *dyads: IrTuple) -> Self:
        """Index each dyad by its key, in canonical order.

        :param dyads: ``(key, value)`` records supporting ``d[0]``/``d[1]`` (an
            :class:`~lexic.ir.base.IrTuple` or an :class:`~lexic.ir.action.IrAction`).
        :raises UnsupportedConstructError: On a duplicate key.
        """
        obj = object.__new__(cls)
        table: dict[Any, Any] = {}
        for dyad in sorted(dyads, key=lambda d: repr(d[0])):
            key = dyad[0]
            if key in table:
                raise UnsupportedConstructError(
                    f"{cls.__name__}: duplicate key {key!r}"
                )
            table[key] = dyad[1]
        object.__setattr__(obj, "_table", table)
        return obj


class IrTypeMap[Ir_co: IrSelf = IrSelf](IrMap[type, IrSelf]):
    """Type-keyed :class:`IrMap` — resolves ``n`` via ``type(n).__mro__``,
    concrete-first. ``_table.get(type(n))`` is the exact-type fast path; only an
    unregistered concrete type walks the MRO, then falls back to :data:`IR_DEFAULT`.

    The dispatch-table shape: an :class:`~lexic.ir.action.IrAction`
    ``(target_type, body)`` IS a ``(type, value)`` dyad.
    """

    __slots__ = ()

    def resolve(self, n: IrSelf) -> IrSelf:
        """Resolve via ``type(n)`` (exact then MRO), then :data:`IR_DEFAULT`.

        :raises IrKeyError: On a miss with no :data:`IR_DEFAULT` entry.
        """
        table = self._table
        body = table.get(type(n))
        if body is not None:
            return body
        for base in type(n).__mro__:
            body = table.get(base)
            if body is not None:
                return body
        body = table.get(IR_DEFAULT)
        if body is not None:
            return body
        raise IrKeyError(f"{type(self).__name__}: no entry for {type(n).__name__}")

    def eval(self, d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> Ir_co:
        """Resolve ``n`` to its body and evaluate it, typed as ``Ir_co``.

        :raises IrKeyError: On a miss with no :data:`IR_DEFAULT` entry.
        """
        return self.resolve(n).eval(d, n, nc)


class IrMultiMap[K, V: IrSelf](IrMapping[K, V, Sequence[V]]):
    """Mutable multi-valued map (``R = Sequence[V]``) — a key to its bucket.

    Engine-internal (the package's mutable-chart exception): the Earley driver's
    per-column "waiting" index. Inherits empty construction and the read surface
    from :class:`IrMapping`; ``mm += (key, value)`` files in O(1) and ``mm[key]``
    overrides to return the **live** bucket (the backing ``list``, ``()`` on a
    miss) — no raise, no snapshot copy, so the read is at the dict floor. A caller
    appending while it iterates must index-iterate (a plain ``for`` over a list
    does, picking up same-pass appends). Overrides equality to **identity** — a
    mutable map is its own value; never walked, emitted, or reduced as a tree.
    """

    __slots__ = ()

    def __iadd__(self, entry: tuple[K, V]) -> Self:
        """File ``value`` under ``key`` in O(1), preserving insertion order.

        :param entry: The ``(key, value)`` pair to file.
        :returns: ``self`` (the in-place-mutated map).
        """
        key, value = entry
        bucket = self._table.get(key)
        if bucket is None:
            self._table[key] = [value]
        else:
            bucket.append(value)
        return self

    def __getitem__(self, key: object) -> Sequence[V]:
        """The **live** bucket under ``key`` (empty tuple on a miss) — no copy.

        The returned list IS the backing bucket; a caller appending while it reads
        must index-iterate (a plain ``for`` over a list does, picking up same-pass
        appends).
        """
        return self._table.get(key, ())

    def __eq__(self, other: object) -> bool:
        """Identity equality — a mutable map is its own value."""
        return self is other

    def __hash__(self) -> int:
        """Identity hash, consistent with identity equality."""
        return id(self)
