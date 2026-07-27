"""The compiled payload's reader — **zero lexic imports**, by design and by test.

A compiled text is a payload plus a reference to an already-compiled shape. The
payload is three flat literals — ``TYPES`` (the symbols it names), ``STRS``,
``NODES`` (a flat int array; each record is ``type_id, kind, payload,
*child_indices``, and every child index points at an EARLIER record, so decoding
is one forward pass with no recursion).

Nothing here imports lexic. A ``plain`` payload names no symbol at all, so its
reader must pay for nothing; every class it does build arrives in ``symbols``,
supplied by the artefact's own imports. This module's source is also what is
emitted beside an artefact as its reader sidecar, which is why it stands alone.

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


def _hashed(chunks: Sequence[bytes]) -> int:
    """Length-prefixed blake2b over ``chunks`` — injective by construction.

    Each chunk carries its own length, so no concatenation of one can be read
    as a different split of another. That is the property a separator does not
    have, and the reason the first digest here collided on ``('a','b')`` against
    ``('a\x00b')``.
    """
    packed = b"".join(len(c).to_bytes(8, "little") + c for c in chunks)
    return int.from_bytes(hashlib.blake2b(packed, digest_size=8).digest(), "little")


def shape_of(types: Sequence[str], symbols: dict[str, Any]) -> int:
    """A digest of the GRAMMAR the named symbols carry — the payload's provenance.

    A generated class knows the rule it was built from, and that rule survives
    the move from a runtime class to its exported twin while the module name
    does not: the runtime reports ``generated.json_<hash>`` and the twin reports
    its own file. So the grammar, not the module, identifies which compilation a
    payload belongs to.

    Each class's ``__shape__`` covers its own rule AND every rule that rule
    transitively references, because its own rule alone is not enough. An
    alternation is a pass-through — it never materialises in a value, so it is
    never a named symbol — and narrowing one leaves every named rule identical
    while the document the value re-emits no longer parses. The closure moves;
    the bare rule does not.

    Regenerate the grammar, re-export the shape, keep an old payload — the
    number moves and :func:`decode` refuses instead of reading a wrong value.
    ``0`` when no symbol carries a grammar, which is every ``ir`` and ``plain``
    payload.

    :param types: The symbol table.
    :param symbols: Symbol name → class, as the artefact supplies them.
    :returns: A 64-bit digest of the grammar, or ``0`` when there is none.
    """
    chunks: list[bytes] = []
    for name in types[1:]:
        shape = _own_shape(symbols.get(name))
        if shape is not None:
            chunks.append(name.encode("utf-8", "surrogatepass"))
            chunks.append(shape.to_bytes(8, "little"))
    return _hashed(chunks) if chunks else 0


def _own_shape(cls: Any) -> int | None:
    """A class's OWN closure digest, or ``None`` when it declares none.

    Own, not inherited: every generated class declares its own, and a caller's
    subclass of one would otherwise borrow its parent's provenance — passing the
    shape check on rules that are not its own and skipping the origin check that
    covers a class carrying no grammar.

    :param cls: The symbol, or ``None`` when the artefact supplied no such name.
    :returns: The digest, or ``None``.
    :raises ValueError: When a declared shape is not a 64-bit unsigned int —
        the artefact would otherwise fail deep inside the digest, on an
        ``OverflowError`` that names nothing.
    """
    if not isinstance(cls, type):
        return None
    shape = vars(cls).get("__shape__")
    if shape is None:
        return None
    if (
        not isinstance(shape, int)
        or isinstance(shape, bool)
        or not 0 <= shape < 1 << 64
    ):
        raise ValueError(
            f"payload: {cls.__name__}.__shape__ is {shape!r}, which is not a "
            "64-bit digest — the class does not come from a lexic compilation"
        )
    return shape


def reduction_digest(reduction: object) -> int:
    """A digest of the reduction a value was produced by.

    The grammar half of provenance is checkable at decode — a class carries its
    rules and the reader recomputes. The reduction half is NOT: an ``ir`` or
    ``plain`` artefact names spine classes or nothing at all, identical across
    every grammar and every reduction, so nothing at read time could disagree,
    and an artefact supplying its own expectation would only be checking itself.

    So it is RECORDED here and asked by the one party that can answer — whoever
    holds a live reduction and wants to know whether a cached artefact is still
    current. See :func:`lexic.compile.payload.built_under`.

    :param reduction: The reduction, or anything whose ``repr`` identifies it.
    :returns: A 64-bit digest, or ``0`` for no reduction.
    """
    if reduction is None:
        return 0
    return _hashed([repr(reduction).encode("utf-8", "surrogatepass")])


def digest(tables: tuple) -> int:
    """A checksum over the four tables — order-sensitive and injective.

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

    :param tables: ``(types, origins, strs, nodes)`` — all four, because
        ``origins`` is part of the artefact and a digest that skipped it would
        not notice an edit to it.
    :returns: A 64-bit digest.
    """
    types, origins, strs, nodes = tables
    words = (*types, *origins, *strs)
    head = array.array("q", (len(types), len(origins), len(strs), len(nodes))).tobytes()
    lens = array.array("q", [len(t) for t in words]).tobytes()
    # `surrogatepass`: a lone surrogate is a legal `str` and reaches here from
    # parsed text, so a digest that raises on one is a digest that refuses a
    # value the projection accepts.
    text = "".join(words).encode("utf-8", "surrogatepass")
    try:
        body = b"\x00" + array.array("q", nodes).tobytes()
    except OverflowError:
        # An 8-byte length, not 2: a 2-byte prefix caps an integer at 65 535
        # bytes, and `1 << 524288` is a legal Python int. The narrow prefix was
        # the same defect as the `array('q')` overflow it replaced, one order of
        # magnitude further out.
        body = b"\x01" + b"".join(
            len(raw).to_bytes(8, "little") + raw
            for raw in (
                n.to_bytes((n.bit_length() + 8) // 8 or 1, "little", signed=True)
                for n in nodes
            )
        )
    packed = head + lens + text + body
    return int.from_bytes(hashlib.blake2b(packed, digest_size=8).digest(), "little")


def decode(
    tables: tuple, symbols: dict[str, Any], expect: tuple[int, int] | None = None
) -> Any:
    """Rebuild the value. One forward pass; children are always already built.

    :param tables: ``(types, origins, strs, nodes)`` — ``types[0]`` is the
        "names no symbol" sentinel.
    :param symbols: Symbol name → class or singleton. The artefact names its
        symbols and imports them; nothing is guessed from text.
    :param expect: What the exporter recorded about itself —
        ``(digest, shape)``. The digest catches an altered table; the shape
        catches a payload read against a DIFFERENT compilation of its grammar,
        which no table check can see because the tables are intact.
    :returns: The decoded value. ``Any`` is the honest type and not a shrug:
        this module cannot name the caller's vocabulary — it imports no lexic,
        and every class it builds arrives in ``symbols``. That is the whole
        point of a symbol table, and it is why the three targets are one
        projection rather than three return types.
    :raises ValueError: On a digest mismatch or a structurally impossible table.
    """
    if expect is not None:
        _verify(tables, symbols, expect)
    ctx = (tables[0], tables[2], symbols)
    nodes = tables[3]
    built: list[Any] = []
    at, total = 0, len(nodes)
    while at < total:
        tid, kind, payload = nodes[at], nodes[at + 1], nodes[at + 2]
        at += 3
        # Free structural checks. They cannot catch a child index corrupted into
        # ANOTHER valid earlier record — that is the digest's job — but they
        # catch truncation, forward references and a bad symbol id, which is
        # what a partial write looks like.
        if not 0 <= tid < len(ctx[0]):
            raise ValueError(f"payload: symbol id {tid} out of range")
        if not 0 <= kind < len(DECODE):
            raise ValueError(f"payload: unknown record kind {kind}")
        span = payload * CHILD_SLOTS[kind]
        kids = [_child(built, nodes[at + i]) for i in range(span)]
        at += span
        cls = None if tid == PLAIN else symbols[ctx[0][tid]]
        built.append(DECODE[kind](cls, payload, kids, ctx))
    if not built:
        raise ValueError("payload: the node table is empty")
    return built[-1]


def offsets(nodes: Sequence[int]) -> list[int]:
    """Each record's start in ``NODES`` — one forward scan, building nothing.

    The table is self-describing but not indexable: a record is
    ``type_id, kind, payload, *child_indices`` and only its ``kind`` says how
    many slots follow. So reaching record N means walking N records — which is
    cheap precisely because it constructs no objects, and is why the format
    needs no offset table of its own.

    :param nodes: The flat node ints.
    :returns: The start offset of each record, in record order.
    :raises ValueError: On a kind the table does not define.
    """
    out: list[int] = []
    at, total = 0, len(nodes)
    while at < total:
        out.append(at)
        kind = nodes[at + 1]
        if not 0 <= kind < len(DECODE):
            raise ValueError(f"payload: unknown record kind {kind}")
        at += 3 + nodes[at + 2] * CHILD_SLOTS[kind]
    return out


def children(tables: tuple, index: int) -> tuple[int, ...]:
    """The record indices one record points at, in order.

    :param tables: ``(types, origins, strs, nodes)``.
    :param index: A record index.
    :returns: Its child record indices — empty for a leaf.
    :raises ValueError: When ``index`` names no record.
    """
    nodes = tables[3]
    starts = offsets(nodes)
    if not 0 <= index < len(starts):
        raise ValueError(f"payload: record {index} is not in a table of {len(starts)}")
    at = starts[index]
    span = nodes[at + 2] * CHILD_SLOTS[nodes[at + 1]]
    return tuple(nodes[at + 3 + i] for i in range(span))


def subtree(
    tables: tuple,
    symbols: dict[str, Any],
    index: int,
    expect: tuple[int, int] | None = None,
) -> Any:
    """Decode ONE record and only the records it reaches.

    The payload is a queryable compiled form, not merely a serialisation: every
    child index points at an EARLIER record, so a subtree is a closed set and
    materialising it costs what THAT subtree costs. Asking for the root is a
    full decode — it IS the document — and asking for one member of a large
    object is proportionally cheaper.

    :param tables: ``(types, origins, strs, nodes)``.
    :param symbols: Symbol name → class or singleton.
    :param index: The record to materialise.
    :param expect: ``(digest, shape)``, checked as in :func:`decode`.
    :returns: The value that record builds.
    :raises ValueError: On a failed check or a record index out of range.
    """
    if expect is not None:
        _verify(tables, symbols, expect)
    nodes = tables[3]
    starts = offsets(nodes)
    if not 0 <= index < len(starts):
        raise ValueError(f"payload: record {index} is not in a table of {len(starts)}")
    ctx = (tables[0], tables[2], symbols)
    built: dict[int, Any] = {}
    for record in reaches(tables, starts, index):
        built[record] = _one(nodes, starts[record], built, ctx)
    return built[index]


def _one(nodes: Sequence[int], here: int, built: dict, ctx: tuple) -> Any:
    """Build the single record at offset ``here``, its children already built."""
    tid, kind, payload = nodes[here], nodes[here + 1], nodes[here + 2]
    span = payload * CHILD_SLOTS[kind]
    kids = [built[nodes[here + 3 + i]] for i in range(span)]
    cls = None if tid == PLAIN else ctx[2][ctx[0][tid]]
    return DECODE[kind](cls, payload, kids, ctx)


def reaches(tables: tuple, starts: Sequence[int], index: int) -> list[int]:
    """Every record ``index`` reaches, in build order (children first).

    Public because it is the size of a subtree, which is the only honest way to
    read :func:`subtree`'s cost: the win is proportional to what is reached, and
    bounded below by :func:`offsets`, which walks the whole table.

    :param tables: ``(types, origins, strs, nodes)``.
    :param starts: The record offsets from :func:`offsets`.
    :param index: The record to start from.
    :returns: The reached record indices, ascending.
    :raises ValueError: On a child index that names no record.
    """
    nodes = tables[3]
    seen: set[int] = set()
    stack = [index]
    while stack:
        record = stack.pop()
        if record in seen:
            continue
        if not 0 <= record < len(starts):
            raise ValueError(f"payload: child index {record} is not a record")
        seen.add(record)
        here = starts[record]
        span = nodes[here + 2] * CHILD_SLOTS[nodes[here + 1]]
        stack.extend(nodes[here + 3 + i] for i in range(span))
    return sorted(seen)


def _moved(
    types: Sequence[str], origins: Sequence[str], symbols: dict[str, Any]
) -> list[str]:
    """Symbols that came from somewhere other than where they were recorded.

    Only for a class carrying no grammar. A generated class's module legitimately
    MOVES — a value is parsed with runtime classes tagged by content and read
    back against the twin, which reports its own file — so for those the rules
    are the provenance and :func:`shape_of` is the check. For a class the caller
    wrote, the module survives the cycle intact and is the only provenance there
    is: shape reads 0 for it, and a name silently rebound to another module's
    class of the same name would otherwise decode into the wrong class.

    :param types: The symbol table.
    :param origins: The module each symbol was recorded as coming from.
    :param symbols: Symbol name → class, as the artefact supplies them.
    :returns: One ``name: recorded -> found`` line per moved symbol.
    """
    moved = []
    for name, recorded in zip(types[1:], origins[1:]):
        found = symbols.get(name)
        if found is None or _own_shape(found) is not None:
            continue
        home = getattr(found, "__module__", "")
        if home != recorded:
            moved.append(f"{name}: {recorded} -> {home}")
    return moved


def _verify(tables: tuple, symbols: dict[str, Any], expect: tuple[int, int]) -> None:
    """Check what the exporter recorded about itself, before reading a record.

    Three different questions. The digest asks whether these are the tables that
    were written; the shape asks whether the SYMBOLS handed in are the ones they
    were written against — which no table check can see, because a payload read
    against a recompiled grammar has intact tables, resolvable names, and every
    record decoding to a wrong value. The origins ask the same of a symbol that
    carries no rule for shape to weigh.

    :raises ValueError: On any of the three.
    """
    if digest(tables) != expect[0]:
        raise ValueError(
            "payload: digest mismatch — the tables were altered since export, "
            "and decoding them would produce a wrong value silently"
        )
    if shape_of(tables[0], symbols) != expect[1]:
        raise ValueError(
            "payload: shape mismatch — the symbols this payload was given carry "
            "different rules than the ones it was built against, so the grammar "
            "was recompiled and this artefact is stale"
        )
    moved = _moved(tables[0], tables[1], symbols)
    if moved:
        raise ValueError(
            f"payload: {moved} — the name still resolves, but to a class from "
            "another module than the one this payload was built against"
        )


def _child(built: list, index: int) -> Any:
    """One child by record index, refusing a forward or out-of-range reference."""
    if not 0 <= index < len(built):
        raise ValueError(
            f"payload: child index {index} is not an earlier record "
            f"({len(built)} built so far) — the table is truncated or reordered"
        )
    return built[index]
