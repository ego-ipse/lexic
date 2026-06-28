"""Fast map family — a common ``IrMapping`` ancestor, slot-backed reads.

Drop-in replacement for :mod:`~lexic.ir.mapping` (does **not** import from it —
:data:`IR_DEFAULT` is duplicated so this module stands alone and can supersede
the original by a file rename). The family shares one ancestor and both concrete
maps read at the backing-dict floor:

- :class:`IrMapping` — common ancestor on :class:`~lexic.ir.base.IrLeaf`. Holds
  the backing ``dict`` in a real ``_table`` slot, a frozen attribute surface, and
  key-based ``__contains__``. Defines **no** ``__getitem__`` — the two concrete
  maps are siblings, each with its own read shape, so neither overrides the other.
- :class:`IrMap` — immutable key→value map. ``m[key]`` is a single ``_table.get``.
  Dyads ride in ``_items`` for iteration/repr/views.
- :class:`IrTypeMap` — type-keyed dispatch; ``_table.get(type(n))`` is the
  exact-type fast path, then ``__mro__``, then :data:`IR_DEFAULT`.
- :class:`IrMultiMap` — mutable multi-valued map. ``mm[key]`` returns the **live**
  bucket (no snapshot copy); ``mm += (k, v)`` files in O(1). The backing dict is
  the same ``_table`` slot, so subclasses (``Links``/``Column.waiting``) are
  unchanged. Identity equality — a mutable map is its own value.
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
:meth:`IrMap.resolve` resolves to it instead of raising."""


class IrMapping[K, V: IrSelf](IrLeaf[IrSelf, IrSelf]):
    """Common ancestor of the map family — an :class:`~lexic.ir.base.IrLeaf` whose
    backing ``dict`` lives in the ``_table`` slot.

    Carries only what both concrete maps share: the slot, a frozen attribute
    surface, and key-based ``__contains__``. It deliberately defines no
    ``__getitem__`` — :class:`IrMap` (value per key) and :class:`IrMultiMap`
    (bucket per key) are siblings with different read shapes.
    """

    __slots__ = ("_table",)
    _table: dict[Any, Any]

    def __setattr__(self, name: str, value: object) -> NoReturn:
        """Frozen. :raises TypeError: Always."""
        raise TypeError(f"{type(self).__name__} is immutable")

    def __delattr__(self, name: str) -> NoReturn:
        """Frozen. :raises TypeError: Always."""
        raise TypeError(f"{type(self).__name__} is immutable")

    def __contains__(self, key: object) -> bool:
        """Whether ``key`` has an entry (key-based, not dyad membership)."""
        return key in self._table


class IrMap[K, V: IrSelf](IrMapping[K, V]):
    """Immutable key→value map. ``m[key]`` is a single ``_table.get``.

    ``_table`` drives O(1) lookup; ``_items`` (the dyads, canonically sorted by
    key repr so construction order is irrelevant) drives iteration, repr, and the
    dict views. ``__iter__`` yields **dyads** — the node IS its children — so
    ``iter(m)`` is not ``iter(m.keys())``.
    """

    __slots__ = ("_items",)
    _items: tuple[IrTuple, ...]

    def __new__(cls, *dyads: IrTuple) -> Self:
        """Index each dyad by its key; store the canonically sorted dyad tuple.

        :param dyads: ``(key, value)`` records supporting ``d[0]``/``d[1]`` (an
            :class:`~lexic.ir.base.IrTuple` or an :class:`~lexic.ir.action.IrAction`).
        :raises UnsupportedConstructError: On a duplicate key.
        """
        obj = object.__new__(cls)
        table: dict[Any, Any] = {}
        for dyad in dyads:
            key = dyad[0]
            if key in table:
                raise UnsupportedConstructError(
                    f"{cls.__name__}: duplicate key {key!r}"
                )
            table[key] = dyad[1]
        object.__setattr__(obj, "_table", table)
        object.__setattr__(
            obj, "_items", tuple(sorted(dyads, key=lambda d: repr(d[0])))
        )
        return obj

    def __getitem__(self, key: object) -> V:
        """Value bound to ``key``. :raises IrKeyError: On a miss."""
        value = self._table.get(key)
        if value is not None:
            return value
        raise IrKeyError(f"{type(self).__name__}: no entry for {key!r}")

    def get(self, key: object, default: V | None = None) -> V | None:
        """Value bound to ``key``, or ``default`` on a miss (never raises)."""
        return self._table.get(key, default)

    def resolve(self, n: IrSelf) -> V:
        """Value bound to ``n``, with :data:`IR_DEFAULT` fallback.

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

    def __iter__(self) -> Iterator[IrSelf]:
        """Iterate dyads (the walk/equality contract — not the key view)."""
        return iter(self._items)

    def __len__(self) -> int:
        """Number of entries."""
        return len(self._table)

    def _as_dict(self) -> dict[K, V]:
        """Plain-dict snapshot of the dyads, in canonical order."""
        return {d[0]: d[1] for d in self._items}

    def keys(self) -> KeysView[K]:
        """Key view, canonical order."""
        return self._as_dict().keys()

    def values(self) -> ValuesView[V]:
        """Value view, canonical order."""
        return self._as_dict().values()

    def items(self) -> ItemsView[K, V]:
        """``(key, value)`` view, canonical order."""
        return self._as_dict().items()

    def __eq__(self, other: object) -> bool:
        """Structural equality — same concrete type and same table."""
        if not isinstance(other, IrMap) or type(self) is not type(other):
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
        """Codegen repr — the constructor call over the canonical dyads."""
        return f"{type(self).__name__}({', '.join(repr(d) for d in self._items)})"


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


class IrMultiMap[K, V: IrSelf](IrMapping[K, V]):
    """Mutable multi-valued map — a key to its insertion-ordered bucket.

    Engine-internal (the package's mutable-chart exception): the Earley driver's
    per-column "waiting" index. ``mm += (key, value)`` files in O(1); ``mm[key]``
    returns the **live** bucket (the backing ``list`` itself, ``()`` on a miss) —
    no snapshot copy, so the read is at the dict floor. A caller that appends while
    iterating must index-iterate (a plain ``for`` over a ``list`` does — and so
    picks up same-pass appends). Identity equality/hash — a mutable map is its own
    value; never walked, emitted, or reduced as a tree.
    """

    __slots__ = ()

    def __new__(cls, *_dyads: IrTuple) -> Self:
        """Build an empty mutable map (any positional dyads are ignored)."""
        obj = object.__new__(cls)
        object.__setattr__(obj, "_table", {})
        return obj

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

    def __ne__(self, other: object) -> bool:
        """Negation of :meth:`__eq__`."""
        return self is not other

    def __hash__(self) -> int:
        """Identity hash, consistent with identity equality."""
        return id(self)
