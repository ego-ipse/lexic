"""Fast map family — a common ``IrMapping`` ancestor owning all shared logic.

The ancestor owns the whole read/eval surface over a single ``_table`` slot
(a plain ``dict``); the concrete maps add only construction and the one read
that genuinely differs (bucket vs value). Lookups are native ``dict``
operations with no per-read allocation, under the keys' own (type-aware)
equality.

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
    Iterable,
    Iterator,
    KeysView,
    NoReturn,
    Self,
    Sequence,
    ValuesView,
    final,
)

from lexic.exceptions import IrKeyError, UnsupportedConstructError
from lexic.ir.spine.meta import IrSingleton
from lexic.ir.spine.records import IrTuple
from lexic.ir.spine.spine import IrLeaf, IrSelf


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


def _indexed(cls: type, pairs: Iterable[tuple[Any, Any]]) -> dict[Any, Any]:
    """``pairs`` as a table, refusing a duplicate key.

    :param cls: The map class, for the refusal message.
    :param pairs: ``(key, value)`` pairs, in the order the table should hold.
    :returns: The table.
    :raises UnsupportedConstructError: On a duplicate key.
    """
    table: dict[Any, Any] = {}
    for key, value in pairs:
        if key in table:
            raise UnsupportedConstructError(f"{cls.__name__}: duplicate key {key!r}")
        table[key] = value
    return table


class IrMapping[K, V, R](IrLeaf[IrSelf, IrSelf]):
    """Common ancestor of the map family — the **container** surface over ``_table``.

    Generic over the key ``K``, the stored value ``V`` and the **read return** ``R``
    (what ``__getitem__`` / ``values`` / ``get`` yield — a value for
    :class:`IrMap`, a bucket for :class:`IrMultiMap`). The default ``__getitem__``
    is the value read (raise on miss); :class:`IrMultiMap` overrides it for live
    buckets. ``V`` is **unbounded** — this base is a pure container, so a value
    need not be an :class:`IrSelf` (the Earley engine files plain-tuple items in an
    :class:`IrMultiMap`). The **dispatch** surface (:meth:`~IrMap.resolve` /
    :meth:`~IrMap.eval`, which *run* a value) lives on :class:`IrMap`, whose ``V``
    is bounded :class:`IrSelf`. Subclasses otherwise add only construction.
    """

    __slots__ = ("_table",)
    _table: dict[Any, Any]

    def __new__(cls, *_dyads: IrTuple) -> Self:
        """Seed an empty map. :class:`IrMap` overrides to index its dyads."""
        obj = object.__new__(cls)
        object.__setattr__(obj, "_table", {})
        return obj

    @classmethod
    def from_table(cls, pairs: Iterable[tuple[Any, Any]]) -> Self:
        """Build from ``(key, value)`` pairs, in the order given.

        The public way to rebuild a map whose table is already known — a reader
        of a compiled payload, say, which has the pairs and no dyads. Without it
        a caller has to write ``object.__setattr__(obj, "_table", …)``, naming a
        private slot across a boundary no import makes visible: rename the slot
        and every artefact ever written decodes wrong, silently.

        The base is a pure container with no ordering claim, so insertion order
        is its order; :meth:`IrMap.from_table` overrides to canonicalise, which
        is the invariant *that* class documents.

        :param pairs: ``(key, value)`` pairs.
        :returns: The map.
        :raises UnsupportedConstructError: On a duplicate key — a repeated key
            is a corrupt table, not a last-one-wins merge.
        """
        obj = object.__new__(cls)
        object.__setattr__(obj, "_table", _indexed(cls, pairs))
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
        try:
            return self._table[key]
        except KeyError:
            raise IrKeyError(f"{type(self).__name__}: no entry for {key!r}") from None

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
    """Immutable key→value map (``R = V``) and the **dispatch** base: ``V`` is an
    :class:`IrSelf`, so :meth:`resolve` yields a runnable value and :meth:`eval`
    runs it. Adds the dyad-indexing constructor; the container read/equality
    surface is inherited from :class:`IrMapping`. ``_table`` is built in canonical
    (key-repr-sorted) order, so the inherited views and repr are order-stable.
    """

    __slots__ = ()

    def __new__(cls, *dyads: IrTuple) -> Self:
        """Index each dyad by its key, in canonical order.

        :param dyads: ``(key, value)`` records supporting ``d[0]``/``d[1]`` (an
            :class:`~lexic.ir.base.IrTuple` or an :class:`~lexic.ir.action.IrAction`).
        :raises UnsupportedConstructError: On a duplicate key.
        """
        return cls.from_table((dyad[0], dyad[1]) for dyad in dyads)

    @classmethod
    def from_table(cls, pairs: Iterable[tuple[Any, Any]]) -> Self:
        """Build from pairs, canonicalising the order — this class's invariant.

        ``_table`` is key-repr-sorted so the inherited views and repr are
        order-stable, and that has to hold however the map was built: a reader
        rebuilding one from a file cannot be trusted to supply the order,
        because a file can be edited and the export fixpoint cannot catch a
        wrong one (a wrongly-ordered map re-encodes to itself). Costs 3x a bare
        table build at vocabulary scale — 15 ms against 4.6 for 49 152 entries.

        :param pairs: ``(key, value)`` pairs, in any order.
        :returns: The map, canonically ordered.
        :raises UnsupportedConstructError: On a duplicate key.
        """
        obj = object.__new__(cls)
        ordered = sorted(pairs, key=lambda kv: repr(kv[0]))
        object.__setattr__(obj, "_table", _indexed(cls, ordered))
        return obj

    def children(self) -> Sequence[IrTuple]:
        """The map's dyads as fresh ``(key, value)`` records — the walk surface.

        Mirrors :meth:`__new__`: what construction takes is what a walk sees,
        so a transformer's :meth:`rebuild` round-trips through the constructor
        unchanged. Built per call — the table stores no dyad objects. This is
        what lets a dispatch table, a reducer's action map or any map-shaped
        value stand under :class:`~lexic.ir.action.walk.IrBottomUp` and
        :class:`~lexic.ir.action.flow.control.IrEach` like every other node.
        """
        return tuple(IrTuple(key, value) for key, value in self._table.items())

    def rebuild(self, new_children: Sequence[IrSelf]) -> Self:
        """Reconstruct from replacement dyads — the inverse of :meth:`children`.

        :param new_children: One ``(key, value)`` record per entry.
        :returns: A new map indexed from the replacement dyads.
        :raises UnsupportedConstructError: On a duplicate key among them.
        """
        return type(self)(*(IrTuple.ensure(dyad, "map dyad") for dyad in new_children))

    def resolve(self, n: IrSelf) -> V:
        """Eval-value bound to ``n``, with :data:`IR_DEFAULT` fallback.

        :raises IrKeyError: On a miss with no :data:`IR_DEFAULT` entry.
        """
        table = self._table
        try:
            return table[n]
        except KeyError:
            value = table.get(IR_DEFAULT)
            if value is not None:
                return value
            raise IrKeyError(f"{type(self).__name__}: no entry for {n!r}") from None

    def eval(self, d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> IrSelf:
        """Resolve ``n`` to its value and evaluate it against ``(d, n, nc)``.

        :raises IrKeyError: On a miss.
        """
        return self.resolve(n).eval(d, n, nc)


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
        t = type(n)
        try:
            return table[t]
        except KeyError:
            pass
        for base in t.__mro__:
            body = table.get(base)
            if body is not None:
                return body
        body = table.get(IR_DEFAULT)
        if body is not None:
            return body
        raise IrKeyError(f"{type(self).__name__}: no entry for {t.__name__}")

    def eval(self, d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> Ir_co:
        """Resolve ``n`` to its body and evaluate it, typed as ``Ir_co``.

        :raises IrKeyError: On a miss with no :data:`IR_DEFAULT` entry.
        """
        return self.resolve(n).eval(d, n, nc)


class IrMultiMap[K, V](IrMapping[K, V, Sequence[V]]):
    """Mutable multi-valued map (``R = Sequence[V]``) — a key to its bucket.

    Engine-internal (the package's mutable-chart exception): the Earley driver's
    per-column "waiting" index. A pure **container** — never ``eval``'d (the
    dispatch surface lives on :class:`IrMap`), so ``V`` is unbounded and a bucket
    may hold non-:class:`IrSelf` values (e.g. plain-tuple Earley items). Inherits
    empty construction and the read surface from :class:`IrMapping`; ``mm += (key,
    value)`` files in O(1) and ``mm[key]``
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
