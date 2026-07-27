"""The compiled payload's reader — **zero lexic imports**, by design and by test.

A compiled text is a payload plus a reference to an already-compiled shape. The
payload is three flat literals — ``TYPES`` (the symbols it names), ``STRS``,
``NODES`` (a flat int array; each record is ``type_id, kind, payload,
*child_indices``, and every child index points at an EARLIER record, so decoding
is one forward pass with no recursion).

Nothing here imports lexic. A ``plain`` payload names no symbol at all, so its
reader must pay for nothing; every class it does build arrives in ``symbols``,
supplied by the artefact's own imports. This module's source is also what an
exported payload **inlines**, which is why it stands alone.

A ``kind`` is an index into :data:`DECODE`: the kind space is closed by
construction because :mod:`lexic.compile.payload.codec` declares one row per
kind carrying BOTH directions, so lexic cannot emit a kind nothing here reads.
"""

from __future__ import annotations

import array
import hashlib
from typing import Any, Callable, Sequence

PLAIN = 0
"""``TYPES[0]`` — the payload at this position names no symbol."""

(
    K_STR,
    K_INT,
    K_BOOL,
    K_FLOAT,
    K_BYTES,
    K_NONE,
    K_UNIT,
    K_CLASS,
    K_SEQ,
    K_LIST,
    K_SET,
    K_FROZEN,
    K_MAP,
    K_DICT,
) = range(14)

CHILD_SLOTS = (0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 2, 2)
"""Child slots each record's ``payload`` counts — 0 leaf, 1 sequence, 2 mapping."""


def de_str(cls: Any, payload: int, _kids: list, ctx: tuple) -> Any:
    """A string leaf, interned in ``STRS``."""
    text = ctx[1][payload]
    return text if cls is None else cls(text)


def de_int(cls: Any, payload: int, _kids: list, _ctx: tuple) -> Any:
    """An integer leaf — the value rides in the record, at any width."""
    return payload if cls is None else cls(payload)


def de_bool(cls: Any, payload: int, _kids: list, _ctx: tuple) -> Any:
    """A boolean leaf."""
    return bool(payload) if cls is None else cls(bool(payload))


def de_float(cls: Any, payload: int, _kids: list, ctx: tuple) -> Any:
    """A float leaf, spelled by ``float.hex`` — exact, and it keeps ``-0.0``."""
    got = float.fromhex(ctx[1][payload])
    return got if cls is None else cls(got)


def de_bytes(cls: Any, payload: int, _kids: list, ctx: tuple) -> Any:
    """A bytes leaf — latin-1 is a total byte↔str bijection, so ``STRS`` holds it."""
    raw = ctx[1][payload].encode("latin-1")
    return raw if cls is None else cls(raw)


def de_none(_cls: Any, _payload: int, _kids: list, _ctx: tuple) -> Any:
    """Python ``None``.

    Not ``IrNone``: a generated model's absent field IS ``None`` (its twin
    declares ``head: str | None = None``). The spine's absence rule holds inside
    ``ir/``; a projection over anything parsed meets both.
    """
    return None


def de_unit(cls: Any, _payload: int, _kids: list, _ctx: tuple) -> Any:
    """A childless value — a bare-name singleton, or a node with no children."""
    return cls() if isinstance(cls, type) else cls


def de_class(_cls: Any, payload: int, _kids: list, ctx: tuple) -> Any:
    """A CLASS as a value: the payload is the symbol id it names."""
    types, _strs, symbols = ctx
    return symbols[types[payload]]


def de_seq(cls: Any, _payload: int, kids: list, _ctx: tuple) -> Any:
    """A tuple, or a record built positionally from one."""
    if cls is None:
        return tuple(kids)
    return cls(kids) if _takes_iterable(cls) else cls(*kids)


def de_list(cls: Any, _payload: int, kids: list, _ctx: tuple) -> Any:
    """A list."""
    return kids if cls is None else cls(kids)


def de_set(cls: Any, _payload: int, kids: list, _ctx: tuple) -> Any:
    """A set."""
    return set(kids) if cls is None else cls(kids)


def de_frozen(cls: Any, _payload: int, kids: list, _ctx: tuple) -> Any:
    """A frozenset."""
    return frozenset(kids) if cls is None else cls(kids)


def de_map(cls: Any, _payload: int, kids: list, _ctx: tuple) -> Any:
    """A spine mapping, through its own ``from_table``.

    Never ``object.__setattr__(obj, "_table", …)``: that names a private slot
    across a boundary no import makes visible, so renaming the slot would make
    every artefact ever written decode wrong in silence.
    """
    return cls.from_table(_pairs(kids))


def de_dict(cls: Any, _payload: int, kids: list, _ctx: tuple) -> Any:
    """A plain dict."""
    pairs = _pairs(kids)
    return dict(pairs) if cls is None else cls(pairs)


DECODE: tuple[Callable[[Any, int, list, tuple], Any], ...] = (
    de_str,
    de_int,
    de_bool,
    de_float,
    de_bytes,
    de_none,
    de_unit,
    de_class,
    de_seq,
    de_list,
    de_set,
    de_frozen,
    de_map,
    de_dict,
)
"""One decoder per kind, indexed by the kind. An out-of-range kind is an
``IndexError`` — the raising default, for free."""


def _pairs(kids: list) -> tuple:
    """A flat ``key, value, key, value…`` run as pairs."""
    return tuple(zip(kids[0::2], kids[1::2]))


def _takes_iterable(cls: type) -> bool:
    """Does this class construct from ONE iterable, or positionally?

    A caller's ``class L(list)`` or ``class T(tuple)`` takes an iterable; a spine
    record takes its fields. The question is the constructor, so the test is
    whether the class descends from a non-tuple builtin container, or is a tuple
    subclass whose ``__new__`` is still the builtin one.
    """
    if issubclass(cls, (list, set, frozenset, dict)):
        return True
    return issubclass(cls, tuple) and cls.__new__ is tuple.__new__


def digest(types: Sequence[str], strs: Sequence[str], nodes: Sequence[int]) -> int:
    """A checksum over the three tables — order-sensitive and injective.

    The LENGTH VECTOR is digested beside the joined text, so no concatenation of
    one field can be read as a different split of another and no separator is
    needed: ``('a','b')`` and ``('a\\x00b')`` differ in the lengths. Ints keep
    the ``array('q')`` fast path and fall back to a width-independent form when
    one does not fit, under a scheme tag so the two forms cannot collide.

    Not ``crc32``: it is affine over GF(2), so a compensating word is SOLVED in
    64 evaluations rather than searched. Not ``marshal``: it is C-speed and
    injective, and its back-references are keyed on object identity, so the
    digest changes across the very export/import cycle this defends — which is
    invisible to any in-process check.

    :param types: The symbol table.
    :param strs: The string table.
    :param nodes: The flat node table.
    :returns: A 64-bit digest.
    """
    head = array.array("q", (len(types), len(strs), len(nodes))).tobytes()
    lens = array.array("q", [len(t) for t in (*types, *strs)]).tobytes()
    text = ("".join(types) + "".join(strs)).encode("utf-8")
    try:
        body = b"\x00" + array.array("q", nodes).tobytes()
    except OverflowError:
        body = b"\x01" + b"".join(
            len(raw).to_bytes(2, "little") + raw
            for raw in (
                n.to_bytes((n.bit_length() + 8) // 8 or 1, "little", signed=True)
                for n in nodes
            )
        )
    packed = head + lens + text + body
    return int.from_bytes(hashlib.blake2b(packed, digest_size=8).digest(), "little")


def decode(
    types: Sequence[str],
    strs: Sequence[str],
    nodes: Sequence[int],
    symbols: dict[str, Any],
    expect: int | None = None,
) -> Any:
    """Rebuild the value. One forward pass; children are always already built.

    :param types: The symbol table; ``TYPES[0]`` is the "names no symbol" sentinel.
    :param strs: The string table.
    :param nodes: The flat node table.
    :param symbols: Symbol name → class or singleton. The artefact names its
        symbols and imports them; nothing is guessed from text.
    :param expect: The digest recorded at export. Supplied, a corrupted table
        raises instead of decoding to a plausible wrong value.
    :returns: The decoded value. ``Any`` is the honest type and not a shrug:
        this module cannot name the caller's vocabulary — it imports no lexic,
        and every class it builds arrives in ``symbols``. That is the whole
        point of a symbol table, and it is why the three targets are one
        projection rather than three return types.
    :raises ValueError: On a digest mismatch or a structurally impossible table.
    """
    if expect is not None and digest(types, strs, nodes) != expect:
        raise ValueError(
            "payload: digest mismatch — the tables were altered since export, "
            "and decoding them would produce a wrong value silently"
        )
    ctx = (types, strs, symbols)
    built: list[Any] = []
    at, total = 0, len(nodes)
    while at < total:
        tid, kind, payload = nodes[at], nodes[at + 1], nodes[at + 2]
        at += 3
        # Free structural checks. They cannot catch a child index corrupted into
        # ANOTHER valid earlier record — that is the digest's job — but they
        # catch truncation, forward references and a bad symbol id, which is
        # what a partial write looks like.
        if not 0 <= tid < len(types):
            raise ValueError(f"payload: symbol id {tid} out of range")
        if not 0 <= kind < len(DECODE):
            raise ValueError(f"payload: unknown record kind {kind}")
        span = payload * CHILD_SLOTS[kind]
        kids = [_child(built, nodes[at + i]) for i in range(span)]
        at += span
        cls = None if tid == PLAIN else symbols[types[tid]]
        built.append(DECODE[kind](cls, payload, kids, ctx))
    if not built:
        raise ValueError("payload: the node table is empty")
    return built[-1]


def _child(built: list, index: int) -> Any:
    """One child by record index, refusing a forward or out-of-range reference."""
    if not 0 <= index < len(built):
        raise ValueError(
            f"payload: child index {index} is not an earlier record "
            f"({len(built)} built so far) — the table is truncated or reordered"
        )
    return built[index]
