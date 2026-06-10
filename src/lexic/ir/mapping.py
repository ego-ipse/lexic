"""Immutable hash map as a tuple subclass — attribute access IS the index.

The dyads ARE the tuple elements (payload, equality, hash, children, codegen
repr — all canonically sorted by key repr, so construction order never
matters). The index lives in the **class namespace**: ``IrMap(*dyads)``
synthesizes a one-off subclass and ``__init_subclass__`` mirrors each dyad as
a class attribute named ``str(hash(key))``. Instance attribute lookup falls
back to the class natively, so key lookup is a single ``getattr`` — Python's
own O(1) machinery — with the dyad's key verified on read (a lookup may
collide with a stored hash; stored keys never collide, attribution rejects
that). No instance ``__dict__``, no ``__slots__`` exception: instances stay
pure tuples; the synthesized class keeps the constructor's name, so codegen
repr round-trips.

``m[key]``: integer/slice subscripts keep native tuple indexing (the overloads
say so); any other key resolves via the index. A miss is a **hard error** —
:exc:`~lexic.exceptions.UnsupportedConstructError` — everywhere: ``m[key]``,
``eval``, ``_find``. ``eval(d, n, nc)`` resolves ``n`` and evaluates the bound
value against ``(d, n, nc)``: scalars self-evaluate (a data map), bodies run
(an action table).
"""

from __future__ import annotations

from typing import (
    Any,
    ClassVar,
    Hashable,
    NoReturn,
    Self,
    Sequence,
    SupportsIndex,
    cast,
    overload,
)

from lexic.exceptions import UnsupportedConstructError
from lexic.ir.base import IrSelf, IrSeq, IrTuple


class IrMap[K, V: IrSelf](IrSeq[IrTuple[K, V]]):
    """Dyad tuple whose entries are attributes of its synthesized class.

    ``_bound`` is re-declared ``tuple`` so the own ``V`` parameter does not
    re-derive it (the :class:`~lexic.ir.base.IrSeq` move).
    """

    _bound: ClassVar[type[tuple]] = tuple

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

    def __new__(cls, *dyads: IrTuple[K, V]) -> Self:
        """Sort canonically, synthesize the indexed subclass, build the tuple.

        The subclass keeps ``cls.__name__``, so ``repr`` stays valid codegen.
        """
        order = tuple(sorted(dyads, key=lambda d: repr(d[0])))
        sub = type(cls)(cls.__name__, (cls,), {}, dyads=order)
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

        :raises UnsupportedConstructError: When no candidate resolves.
        """
        for key in keys:
            dyad = getattr(self, str(hash(key)), None)
            if isinstance(dyad, IrTuple) and dyad[0] == key:
                return dyad
        raise UnsupportedConstructError(f"{type(self).__name__}: no entry for {keys!r}")

    @overload
    def __getitem__(self, key: SupportsIndex, /) -> Any: ...
    @overload
    def __getitem__(self, key: slice, /) -> tuple[Any, ...]: ...
    @overload
    def __getitem__(self, key: IrSelf | type, /) -> IrSelf: ...
    def __getitem__(self, key: object, /) -> object:
        """Positional for index/slice (tuple semantics); key lookup otherwise.

        Note: ``IrInt`` keys are ints and therefore index positionally.

        :raises UnsupportedConstructError: On a key miss.
        """
        if isinstance(key, (int, slice)):
            return super().__getitem__(key)
        return self._find(key)[1]

    def eval(self, d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> IrSelf:
        """Resolve ``n`` to its dyad; evaluate the value against ``(d, n, nc)``.

        :raises UnsupportedConstructError: On a miss.
        """
        return self._find(*self._keys(n))[1].eval(d, n, nc)


class IrTypeMap(IrMap):
    """Type-keyed :class:`IrMap` — resolves ``n`` via ``type(n).__mro__``,
    concrete first: one ``getattr`` per MRO entry, bounded by class depth, not
    table size. The dispatch-table shape: an ``IrAction(target_type, body)``
    is exactly a ``(type, body)`` dyad."""

    def _keys(self, n: IrSelf) -> tuple[Hashable, ...]:
        """``type(n).__mro__`` — concrete-first resolution order."""
        return type(n).__mro__


# ── Examples ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    from lexic.ir.action import IrCallable, IrThis
    from lexic.ir.base import IrInt, IrStr
    from lexic.ir.nodes import IrLiteral, IrRuleRef

    # 1. Data map — direct instantiation; m[key] via getattr; positional
    #    indexing intact (IrScalar.eval is identity, values come back as-is).
    names = IrMap(
        IrTuple(IrStr("[0-9]"), IrStr("digit")),
        IrTuple(IrStr("[a-z]"), IrStr("lower")),
    )
    print("mapx [key]    :", names[IrStr("[0-9]")])  # IrStr('digit'), no eval
    print("mapx [0]      :", names[0])  # first dyad — tuple semantics intact
    print("mapx eval hit :", names.eval(names, IrStr("[a-z]"), ()))

    # 2. Dispatch table — MRO resolution, bodies run against the node.
    disp = IrTypeMap(
        IrTuple(IrLiteral, IrCallable(lambda d, n, nc: IrStr(f"lit:{n}"))),
        IrTuple(IrSelf, IrThis()),
    )
    print("mapx dispatch :", disp.eval(disp, IrLiteral("x"), ()))  # IrStr('lit:x')
    print("mapx mro fall :", disp.eval(disp, IrRuleRef("r"), ()))  # IrRuleRef('r')

    # 3. Pure value: construction order never matters (canonical sort);
    #    codegen repr round-trips; a miss is a hard error.
    a = IrMap(IrTuple(IrStr("a"), IrInt(1)), IrTuple(IrStr("b"), IrInt(2)))
    b = IrMap(IrTuple(IrStr("b"), IrInt(2)), IrTuple(IrStr("a"), IrInt(1)))
    print("mapx ord-indep:", a == b, hash(a) == hash(b), len({a, b}) == 1)
    print("mapx repr     :", repr(a))
    try:
        a[IrStr("?")]
    except UnsupportedConstructError as exc:
        print("mapx hard miss:", exc)
