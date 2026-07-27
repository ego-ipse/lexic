"""Value → the three flat tables — the projection's lexic side.

Sharing is keyed on **object identity, with a keepalive**. Mutability was a
proxy: it destroyed aliasing in both directions and lost a mutable ``tuple``
subclass's class. Identity answers both — and the memo holds a reference,
because *a memo key is valid only while something holds the object*: a container
that synthesises its children frees them when its frame pops, and CPython hands
the next one the same id.

The vocabulary is **wide** and every non-exact type gets a symbol, so a subclass
is recorded rather than silently decoded as its builtin base.
"""

from __future__ import annotations

from typing import Iterable, NamedTuple

from lexic.compile.payload import reader
from lexic.compile.payload.codec import Row, row_for
from lexic.exceptions import UnsupportedConstructError
from lexic.ir.base import IrNoneType
from lexic.ir.mapping import IR_DEFAULT

SENTINEL = "<plain>"
"""``TYPES[0]`` — "this record names no symbol". Refused as a symbol name: a
class actually called ``<plain>`` once exported with zero symbols and decoded to
a plain ``str``, silently. A sentinel a payload can collide with is not one."""

EXACT_PLAIN: frozenset[type] = frozenset(
    {str, int, bool, tuple, list, dict, float, bytes, set, frozenset, type(None)}
)
"""Builtins whose EXACT type the reader rebuilds without a symbol."""


class Payload(NamedTuple):
    """The three flat tables. The last node is the value.

    :ivar types: The symbols the payload names; ``types[0]`` is the sentinel.
    :ivar origins: Each symbol's module, positionally — recorded as DATA, so a
        name that legitimately repeats across two grammars is recoverable by
        inspection instead of invisible.
    :ivar strs: Every distinct string, deduplicated.
    :ivar nodes: One flat int array — a bottom-up node table.
    """

    types: tuple[str, ...]
    origins: tuple[str, ...]
    strs: tuple[str, ...]
    nodes: tuple[int, ...]
    owners: dict[str, object]

    @property
    def symbols(self) -> tuple[str, ...]:
        """The symbols the payload names — empty for a ``plain`` value."""
        return self.types[1:]

    @property
    def tables(self) -> tuple:
        """The four literals an artefact writes, in the order the reader takes."""
        return (self.types, self.origins, self.strs, self.nodes)

    def digest(self) -> int:
        """The tables' digest — see :func:`~lexic.compile.payload.reader.digest`."""
        return reader.digest(self.tables)

    def shape(self) -> int:
        """The rules its symbols carry — see
        :func:`~lexic.compile.payload.reader.shape_of`."""
        return reader.shape_of(self.types, self.owners)


class _Strings:
    """An append-only string table with a first-appearance index."""

    def __init__(self) -> None:
        self.items: list[str] = []
        self._ids: dict[str, int] = {}

    def intern(self, text: str) -> int:
        """This string's id, appending it on first sight."""
        got = self._ids.get(text)
        if got is None:
            got = len(self.items)
            self._ids[text] = got
            self.items.append(text)
        return got

    def frozen(self) -> tuple[str, ...]:
        """The finished table, as an artefact writes it."""
        return tuple(self.items)


class _Symbols:
    """The symbol table: a name per id, its origin module beside it."""

    def __init__(self) -> None:
        self.names: list[str] = [SENTINEL]
        self.origins: list[str] = [""]
        self.owners: dict[str, object] = {}
        self._ids: dict[tuple[str, str], int] = {}

    def intern(self, name: str, origin: str, owner: object) -> int:
        """This ``(origin, name)`` spec's id, appending it on first sight.

        Keyed on the pair rather than on a class object: two compilations of one
        grammar are twins whose classes differ by identity and by nothing a
        header can express.
        """
        key = (origin, name)
        got = self._ids.get(key)
        if got is None:
            got = len(self.names)
            self._ids[key] = got
            self.names.append(name)
            self.origins.append(origin)
        # The owner is kept so the export gate can decode with the very symbols
        # the walk saw. Re-deriving them means walking the value a second time
        # with a second notion of what a container is — and the gate would then
        # be checking the encoder against that notion instead of against itself.
        self.owners.setdefault(name, owner)
        return got

    def frozen(self) -> tuple[tuple[str, ...], tuple[str, ...]]:
        """The finished ``(names, origins)`` pair, as an artefact writes it."""
        return tuple(self.names), tuple(self.origins)


class _Encoder:
    """Builds the tables, sharing by identity and deduplicating strings."""

    def __init__(self) -> None:
        self.symbols = _Symbols()
        self.strings = _Strings()
        self.nodes: list[int] = []
        self.count = 0
        self.memo: dict[tuple, int] = {}
        self.rows: dict[type, Row] = {}
        # id → (record, the object itself). The object rides in the VALUE so the
        # keepalive cannot be forgotten: an id means nothing once its object is
        # gone, and a container that synthesises its children frees them when
        # its frame pops, after which CPython hands the next one the same id.
        self.by_id: dict[int, tuple[int, object]] = {}

    def symbol_id(self, value: object) -> int:
        """Intern a symbol by the IMPORT SPEC a header would write for it.

        Keyed on ``(module, name)`` rather than on the class object: two
        compilations of one grammar are twins whose classes differ by identity
        and not by anything a header can express, and one module exports one
        name. The projection does not police the name — push a value through a
        different shape and either it passes or it fails loudly, and reshaping
        data is a form of transpilation.
        """
        cls = value if isinstance(value, type) else type(value)
        if cls.__name__ == SENTINEL:
            raise UnsupportedConstructError(
                f"payload: {SENTINEL!r} is the symbol table's sentinel and cannot "
                "also be a symbol name"
            )
        return self.symbols.intern(cls.__name__, cls.__module__, cls)

    def singleton_id(self, value: object) -> int:
        """Intern a bare-name singleton by its VALUE name.

        ``IrNone`` is what an importer imports; ``IrNoneType`` is not.
        """
        return self.symbols.intern(repr(value), type(value).__module__, value)

    def str_id(self, text: str) -> int:
        """Intern a payload string."""
        return self.strings.intern(text)

    def type_of(self, value: object) -> int:
        """This value's symbol — the sentinel only for an EXACT builtin."""
        # `IR_DEFAULT` by IDENTITY, not by its private class: it is a singleton,
        # so identity is the honest test and nothing here reaches across a
        # module boundary for a name that starts with an underscore.
        if isinstance(value, IrNoneType) or value is IR_DEFAULT:
            return self.singleton_id(value)
        return reader.PLAIN if type(value) in EXACT_PLAIN else self.symbol_id(value)

    def emit(
        self, head: tuple[int, int, int], kids: Iterable[int], *, share: bool
    ) -> int:
        """Append one record, reusing an identical earlier one when it may share.

        :param head: The record's ``(type_id, kind, payload)``.
        :param kids: Its child record indices.
        :param share: Whether an identical earlier record may stand in.
        :returns: The record's index.
        """
        tid, kind, payload = head
        children = tuple(kids)
        key = (tid, kind, payload, children)
        got = self.memo.get(key) if share else None
        if got is not None:
            return got
        index = self.count
        self.count += 1
        self.nodes.extend((tid, kind, payload, *children))
        if share:
            self.memo[key] = index
        return index

    def classify(self, value: object) -> tuple[int, int, int, tuple]:
        """One node's ``(type_id, kind, payload, children)`` — no traversal."""
        row = row_for(type(value), self.rows)
        payload, children = row.encode(self, value)
        return self.type_of(value), row.kind, payload, children

    def walk(self, root: object) -> None:
        """Encode ``root``. Iterative — a payload may be arbitrarily deep.

        A frame is ``(value, classified, child records)``: classification
        happens once, at push, so the frame has one shape for its whole life and
        nothing has to read a slot that may or may not be filled yet. The memo
        is consulted before pushing, so a shared subtree is never classified
        twice.
        """
        stack: list[tuple[object, tuple[int, int, int, tuple], list[int]]] = [
            (root, self.classify(root), [])
        ]
        open_ids: set[int] = {id(root)}
        while stack:
            value, (tid, kind, payload, children), kids = stack[-1]
            if len(kids) < len(children):
                self._visit(stack, open_ids, children[len(kids)], kids)
                continue
            record = self.emit(
                (tid, kind, payload), kids, share=not _in_place_mutable(value)
            )
            # The value AND its synthesised children ride in the memo entry, so
            # the keepalive cannot be forgotten.
            self.by_id[id(value)] = (record, (value, children))
            stack.pop()
            open_ids.discard(id(value))
            if stack:
                stack[-1][2].append(record)

    def _visit(
        self, stack: list, open_ids: set[int], child: object, kids: list[int]
    ) -> None:
        """Take one child: reuse its record, or push a frame for it.

        :raises UnsupportedConstructError: When the child is already open — a
            value that contains itself has no finite encoding.
        """
        seen = self.by_id.get(id(child))
        if seen is not None:
            kids.append(seen[0])
            return
        if id(child) in open_ids:
            raise UnsupportedConstructError(
                "payload: value contains a cycle — a value that contains itself "
                f"has no finite encoding ({type(child).__name__})"
            )
        open_ids.add(id(child))
        stack.append((child, self.classify(child), []))


def _in_place_mutable(value: object) -> bool:
    """Can this record be changed in place, so two equal ones must stay apart?

    NOT "is this type mutable". Identity already handles *the same object twice*;
    this handles *two distinct objects that happen to be equal*, where merging is
    safe exactly when nobody can tell them apart afterwards.
    """
    return isinstance(value, (list, dict, set)) or hasattr(type(value), "__iadd__")


def project(value: object) -> Payload:
    """Project any parsed value onto the three flat tables.

    :param value: Anything lexic parsed — a model, a reduced IR value, or plain
        data.
    :returns: The payload.
    :raises UnsupportedConstructError: On a value outside the vocabulary, a
        cycle, or a type no codec row uniquely claims.
    """
    enc = _Encoder()
    enc.walk(value)
    return _finish(enc)


def _finish(enc: _Encoder) -> Payload:
    """The encoder's tables, frozen into the record an artefact writes.

    ``owners`` rides along and is deliberately NOT one of the four literals: it
    is the classes the walk saw, which the gate decodes with and the exporter
    reads provenance off, and neither of those is something a file carries.
    """
    names, origins = enc.symbols.frozen()
    return Payload(
        names, origins, enc.strings.frozen(), tuple(enc.nodes), enc.symbols.owners
    )


def project_checked(value: object) -> Payload:
    """Project ``value``, and refuse unless the tables are a fixpoint.

    ``project(decode(project(v))) == project(v)``. No ``==`` (an always-on
    equality gate refuses ``nan``, which round-trips perfectly) and no ``repr``
    (it dies at 498 frames, on the very shape that exposed the missing gate).

    **What it does not establish:** that the tables represent the SOURCE. A wrong
    value is a perfectly good fixpoint of a wrong encoder — so this says the
    tables agree with the encoder, and nothing more.

    :param value: The value to project.
    :returns: The payload.
    :raises UnsupportedConstructError: When the tables are not a fixpoint.
    """
    enc = _Encoder()
    enc.walk(value)
    first = _finish(enc)
    back = reader.decode(first.tables, enc.symbols.owners)
    if project(back).tables != first.tables:
        raise UnsupportedConstructError(
            "payload: the tables do not re-encode to themselves — decode is not "
            "the inverse of encode for this value"
        )
    return first
