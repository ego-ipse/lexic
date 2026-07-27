"""The codec table — one row per kind, carrying BOTH directions.

A row is ``(types, kind, encode, decode)``, and its ``decode`` names a function
in the lexic-free :mod:`~lexic.compile.payload.reader`. So a kind cannot exist on
one side only: you cannot write a row without naming the reader that reads it,
and lexic cannot emit a payload nothing can load back — which is the defect class
this repo has paid for before.

**Resolution is by unique most-derived row, and a tie refuses.** First-hit MRO is
not safe here: the spine declares ``class IrStr(IrScalar, str)``, so ``IrSelf``
precedes ``str`` in every string leaf's MRO, and a table with an ``IrSelf``
catch-all captures every scalar as a childless unit. Measured on a real grammar
AST that turns 51 strings into **0**, and the export fixpoint passes, because an
empty ``IrLiteral()`` is a perfectly good fixpoint of a wrong encoder. Refusing a
tie instead turns a future ``class IrBytes(IrScalar, bytes)`` into an
export-time error naming the ambiguity, which is what neither a ladder nor
first-hit MRO can offer.
"""

from __future__ import annotations

from typing import Any, Callable, NamedTuple

from lexic.compile.payload import reader
from lexic.exceptions import UnsupportedConstructError
from lexic.ir.base import IrInt, IrLambda, IrSelf, IrStr, IrTuple
from lexic.ir.mapping import IrMapping

EncodeFn = Callable[[Any, Any], tuple[int, tuple[Any, ...]]]
"""``(encoder, value) -> (payload, children)`` — the row's encode half.

Every row takes both arguments whether or not it uses them: the signature is
uniform because the table is indexed, and an unused slot takes the underscore
name the spine's own dispatch bodies use (``_d``, ``_n``, ``_nc``)."""


class Row(NamedTuple):
    """One kind: the types that produce it, and the two halves that carry it.

    :ivar types: The types this row claims. Resolution picks the unique most
        derived claim for a value's class.
    :ivar kind: The record kind — an index into :data:`~reader.DECODE`.
    :ivar encode: ``(encoder, value) -> (payload, children)``.
    :ivar decode: The reader function for this kind, named here so the pair
        cannot come apart.
    """

    types: tuple[type, ...]
    kind: int
    encode: EncodeFn
    decode: Callable[..., Any]


def _enc_str(enc: Any, value: Any) -> tuple[int, tuple]:
    return enc.str_id(str(value)), ()


def _enc_int(_enc: Any, value: Any) -> tuple[int, tuple]:
    return int(value), ()


def _enc_bool(_enc: Any, value: Any) -> tuple[int, tuple]:
    return int(bool(value)), ()


def _enc_float(enc: Any, value: Any) -> tuple[int, tuple]:
    return enc.str_id(float(value).hex()), ()


def _enc_bytes(enc: Any, value: Any) -> tuple[int, tuple]:
    return enc.str_id(bytes(value).decode("latin-1")), ()


def _enc_none(_enc: Any, _value: Any) -> tuple[int, tuple]:
    return 0, ()


def _enc_unit(_enc: Any, _value: Any) -> tuple[int, tuple]:
    return 0, ()


def _enc_class(enc: Any, value: Any) -> tuple[int, tuple]:
    return enc.symbol_id(value), ()


def _enc_seq(_enc: Any, value: Any) -> tuple[int, tuple]:
    items = tuple(value)
    return len(items), items


def _enc_set(_enc: Any, value: Any) -> tuple[int, tuple]:
    items = tuple(sorted(value, key=repr))
    return len(items), items


def _enc_pairs(_enc: Any, value: Any) -> tuple[int, tuple]:
    flat = tuple(x for kv in value.items() for x in kv)
    return len(value), flat


def _refuse_lambda(_enc: Any, value: Any) -> tuple[int, tuple]:
    """An ``IrLambda`` wraps a closure — code is not data."""
    raise UnsupportedConstructError(
        f"payload: {value!r} carries a callable — code is not data"
    )


def _unreadable(*_args: Any, **_kwargs: Any) -> Any:  # pragma: no cover
    """The decode half of a row that never encodes."""
    raise ValueError("payload: this kind is never written")


ROWS: tuple[Row, ...] = (
    Row((str, IrStr), reader.K_STR, _enc_str, reader.de_str),
    Row((bool,), reader.K_BOOL, _enc_bool, reader.de_bool),
    Row((int, IrInt), reader.K_INT, _enc_int, reader.de_int),
    Row((float,), reader.K_FLOAT, _enc_float, reader.de_float),
    Row((bytes,), reader.K_BYTES, _enc_bytes, reader.de_bytes),
    Row((type(None),), reader.K_NONE, _enc_none, reader.de_none),
    Row((type,), reader.K_CLASS, _enc_class, reader.de_class),
    Row((tuple, IrTuple), reader.K_SEQ, _enc_seq, reader.de_seq),
    Row((list,), reader.K_LIST, _enc_seq, reader.de_list),
    Row((set,), reader.K_SET, _enc_set, reader.de_set),
    Row((frozenset,), reader.K_FROZEN, _enc_set, reader.de_frozen),
    Row((dict,), reader.K_DICT, _enc_pairs, reader.de_dict),
    # `IrStr`/`IrInt`/`IrTuple` ride on the builtin rows above: without them a
    # spine leaf ties between its builtin base and `IrSelf` and the resolution
    # refuses — 67 of 128 spine classes, measured. They are what makes the table
    # order-free.
    Row((IrMapping,), reader.K_MAP, _enc_pairs, reader.de_map),
    Row((IrSelf,), reader.K_UNIT, _enc_unit, reader.de_unit),
    Row((IrLambda,), -1, _refuse_lambda, _unreadable),
)
"""Every kind, once. ``IrLambda``'s row has no readable kind: it exists to
refuse at the point of dispatch rather than fall through to something plausible."""

_BY_TYPE: dict[type, Row] = {t: row for row in ROWS for t in row.types}


def row_for(cls: type, memo: dict[type, Row]) -> Row:
    """The unique most-derived row for ``cls``; a tie is a missing row.

    :param cls: The value's class.
    :param memo: Per-encoder cache — the exact-type fast path, 27 ns against
        1 187 for the walk.
    :returns: The row.
    :raises UnsupportedConstructError: When no row claims ``cls``, or when two
        claims tie and neither is more derived than the other.
    """
    got = memo.get(cls)
    if got is not None:
        return got
    hits = [claimed for claimed in _BY_TYPE if issubclass(cls, claimed)]
    if not hits:
        raise UnsupportedConstructError(
            f"payload: {cls.__module__}.{cls.__name__} is not payload — no codec "
            "row claims it"
        )
    best = [a for a in hits if all(issubclass(a, b) for b in hits)]
    if len(best) != 1:
        raise UnsupportedConstructError(
            f"payload: {cls.__name__} matches rows "
            f"{sorted(k.__name__ for k in hits)} and none is most derived — it "
            "needs a row of its own"
        )
    memo[cls] = _BY_TYPE[best[0]]
    return memo[cls]
