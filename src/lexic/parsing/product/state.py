"""Parse-local builders and transactions — everything mutable in one parse.

One :class:`ParseState` belongs to one parse, one alternative, or one worker,
and is never shared or cached. Sequence and mapping accumulators sit in
separate typed lanes addressed by an occurrence-owned handle, so ``Carry``
never widens to include a builder handle and there is no parse-global "current
collection" for two nested occurrences to fight over.

Speculation is transactional. A mark is constant size — five integers — and
undo is proportional to what was actually mutated since the mark, not to the
size of the builders. A successful outer commit copies nothing: it drops the
log, because a committed mutation is simply kept.
"""

from __future__ import annotations

from typing import NamedTuple

from lexic.exceptions import SemanticVerdict, UnsupportedConstructError

__all__ = [
    "MAPPING_INSERT",
    "MAPPING_REPLACE",
    "SEQUENCE_APPEND",
    "MappingHandle",
    "ParseState",
    "ProductMark",
    "SequenceHandle",
]

SEQUENCE_APPEND = 1
MAPPING_INSERT = 2
MAPPING_REPLACE = 3
"""The reversible mutation kinds a live mark logs. Plain ints: undo runs on
the speculation-failure path and reads them as codes, never as names.

``MAPPING_REPLACE`` exists because a keep-last duplicate can overwrite an
entry inserted BEFORE the live mark. Removing the newest entry cannot restore
that — the entry is older than the transaction — so the overwritten value is
logged with it."""

_REFUSE_DUPLICATE = 0
_FIRST_DUPLICATE = 1
_LAST_DUPLICATE = 2
"""Lowered duplicate policies, mirroring the authored vocabulary in
``lexic.ir.reduction``. A mapping carries the policy its schema declared."""


class SequenceHandle(NamedTuple):
    """One parse-local ordered accumulator, addressed by lane slot."""

    slot: int


class MappingHandle(NamedTuple):
    """One parse-local keyed accumulator, addressed by lane slot."""

    slot: int


class ProductMark(NamedTuple):
    """A constant-size position in one speculative transaction.

    Five integers, whatever the builders hold. Rollback walks only the
    mutations logged after ``mutations`` and truncates the lanes back to
    their recorded counts; it never scans live builders or rebuilds a key set.
    """

    mutations: int
    sequences: int
    mappings: int
    verdicts: int
    depth: int


class _SequenceBuilder[Carry]:
    """One occurrence-owned ordered accumulator."""

    __slots__ = ("_values",)

    def __init__(self) -> None:
        self._values: list[Carry] = []

    def append(self, value: Carry) -> None:
        """Add one finished value at the end."""
        self._values.append(value)

    def undo(self) -> None:
        """Remove the most recent append — the only reversal it can need."""
        self._values.pop()

    def finished(self) -> tuple[Carry, ...]:
        """The accumulated values, in append order."""
        return tuple(self._values)


class _MappingBuilder[Carry]:
    """One occurrence-owned decoded-key accumulator and its duplicate policy."""

    __slots__ = ("_entries", "_keys", "duplicates")

    def __init__(self, duplicates: int) -> None:
        self.duplicates = duplicates
        self._entries: list[tuple[str, Carry]] = []
        self._keys: dict[str, int] = {}

    def holds(self, key: str) -> bool:
        """Whether this decoded key has already been inserted."""
        return key in self._keys

    def insert(self, key: str, value: Carry) -> None:
        """Add one first-seen key, remembering where its entry landed."""
        self._keys[key] = len(self._entries)
        self._entries.append((key, value))

    def entry_of(self, key: str) -> tuple[int, tuple[str, Carry]]:
        """Where an existing key's entry sits, and what it currently holds."""
        at = self._keys[key]
        return at, self._entries[at]

    def replace(self, key: str, value: Carry) -> None:
        """Overwrite an existing key's value in place, keeping its position."""
        self._entries[self._keys[key]] = (key, value)

    def restore(self, at: int, entry: tuple[str, Carry]) -> None:
        """Put a previously overwritten entry back where it was."""
        self._entries[at] = entry

    def undo(self) -> None:
        """Remove the most recent fresh insert, key included."""
        key, _value = self._entries.pop()
        del self._keys[key]

    def finished(self) -> tuple[tuple[str, Carry], ...]:
        """The accumulated entries, in insertion order."""
        return tuple(self._entries)


class ParseState[Carry]:
    """Every mutable builder and deferred verdict of ONE parse.

    Allocated only for a product that has mutable builders or defers a
    verdict. A product with neither — the generated-model product among them —
    never constructs one, so its completion path pays no state, no
    transaction test and no extra frame slot.
    """

    __slots__ = (
        "_mappings",
        "_marks",
        "_mutation_kinds",
        "_mutation_slots",
        "_overwritten",
        "_sequences",
        "_verdicts",
    )

    def __init__(self) -> None:
        """Open one empty parse-local state."""
        self._sequences: list[_SequenceBuilder[Carry]] = []
        self._mappings: list[_MappingBuilder[Carry]] = []
        self._verdicts: list[SemanticVerdict] = []
        self._mutation_kinds: list[int] = []
        self._mutation_slots: list[int] = []
        self._overwritten: list[tuple[int, tuple[str, Carry]]] = []
        self._marks: list[ProductMark] = []

    @property
    def verdicts(self) -> tuple[SemanticVerdict, ...]:
        """The recorded verdicts, in the order they were recorded."""
        return tuple(self._verdicts)

    # ── sequence lane ────────────────────────────────────────────────

    def begin_sequence(self) -> SequenceHandle:
        """Open one ordered accumulator and hand back its occurrence handle."""
        self._sequences.append(_SequenceBuilder[Carry]())
        return SequenceHandle(len(self._sequences) - 1)

    def append_sequence(self, handle: SequenceHandle, value: Carry) -> None:
        """Append one finished value, logging it while a mark is live."""
        self._sequences[handle.slot].append(value)
        if self._marks:
            self._mutation_kinds.append(SEQUENCE_APPEND)
            self._mutation_slots.append(handle.slot)

    def finish_sequence(self, handle: SequenceHandle) -> tuple[Carry, ...]:
        """Read one accumulator's values in append order."""
        return self._sequences[handle.slot].finished()

    # ── mapping lane ─────────────────────────────────────────────────

    def begin_mapping(self, duplicates: int = _REFUSE_DUPLICATE) -> MappingHandle:
        """Open one keyed accumulator under a declared duplicate policy."""
        self._mappings.append(_MappingBuilder[Carry](duplicates))
        return MappingHandle(len(self._mappings) - 1)

    def insert_mapping(
        self,
        handle: MappingHandle,
        key: str,
        value: Carry,
        verdict: SemanticVerdict,
    ) -> None:
        """Insert one decoded key under the mapping's declared policy.

        :param handle: The occurrence's accumulator.
        :param key: The DECODED key — escape-equivalent spellings arrive here
            already resolved, so they collide as the one key they denote.
        :param value: The finished value.
        :param verdict: What a refused duplicate records; unused by the
            keep-first and keep-last policies.
        :raises UnsupportedConstructError: On a duplicate policy the state
            does not implement.
        """
        builder = self._mappings[handle.slot]
        if builder.holds(key):
            self._resolve_duplicate(handle, key, value, verdict)
            return
        builder.insert(key, value)
        if self._marks:
            self._mutation_kinds.append(MAPPING_INSERT)
            self._mutation_slots.append(handle.slot)

    def _resolve_duplicate(
        self,
        handle: MappingHandle,
        key: str,
        value: Carry,
        verdict: SemanticVerdict,
    ) -> None:
        """Apply the mapping's declared policy to a key it already holds.

        Refusing and keep-first mutate nothing, so neither is logged. Keep-last
        overwrites an entry that may be OLDER than the live mark, which undoing
        the newest insert cannot restore — so the overwritten entry is logged
        with its position and put back verbatim on rollback.
        """
        builder = self._mappings[handle.slot]
        if builder.duplicates == _REFUSE_DUPLICATE:
            self._verdicts.append(verdict)
            return
        if builder.duplicates == _FIRST_DUPLICATE:
            return
        if builder.duplicates == _LAST_DUPLICATE:
            if self._marks:
                self._overwritten.append(builder.entry_of(key))
                self._mutation_kinds.append(MAPPING_REPLACE)
                self._mutation_slots.append(handle.slot)
            builder.replace(key, value)
            return
        raise UnsupportedConstructError(
            f"product state: unknown duplicate policy {builder.duplicates}"
        )

    def finish_mapping(self, handle: MappingHandle) -> tuple[tuple[str, Carry], ...]:
        """Read one accumulator's entries in insertion order."""
        return self._mappings[handle.slot].finished()

    # ── verdicts ─────────────────────────────────────────────────────

    def record(self, verdict: SemanticVerdict) -> None:
        """Retain one semantic refusal instead of raising it now."""
        self._verdicts.append(verdict)

    # ── transactions ─────────────────────────────────────────────────

    def mark(self) -> ProductMark:
        """Open one nested transaction, in constant time and constant size."""
        mark = ProductMark(
            len(self._mutation_kinds),
            len(self._sequences),
            len(self._mappings),
            len(self._verdicts),
            len(self._marks),
        )
        self._marks.append(mark)
        return mark

    def commit(self, mark: ProductMark) -> None:
        """Close the newest transaction, keeping everything it did.

        :param mark: The mark being closed.
        :raises UnsupportedConstructError: If it is not the newest.
        """
        self._require_top(mark)
        self._marks.pop()
        if not self._marks:
            self._drop_log()

    def rollback(self, mark: ProductMark) -> None:
        """Undo exactly what happened since ``mark``, newest mutation first.

        :param mark: The mark being abandoned.
        :raises UnsupportedConstructError: If it is not the newest, or the
            log holds a mutation kind this state cannot undo.
        """
        self._require_top(mark)
        for at in range(len(self._mutation_kinds) - 1, mark.mutations - 1, -1):
            self._undo(self._mutation_kinds[at], self._mutation_slots[at])
        del self._mutation_kinds[mark.mutations :]
        del self._mutation_slots[mark.mutations :]
        del self._sequences[mark.sequences :]
        del self._mappings[mark.mappings :]
        del self._verdicts[mark.verdicts :]
        self._marks.pop()
        if not self._marks:
            self._drop_log()

    def _drop_log(self) -> None:
        """Discard the undo log — nothing outside a live transaction needs it.

        The accumulated VALUES are untouched: a committed mutation is simply
        kept, and this drops only the record of how to reverse it, which is
        what makes an outer commit free of any whole-builder copy.
        """
        self._mutation_kinds.clear()
        self._mutation_slots.clear()
        self._overwritten.clear()

    def _undo(self, kind: int, slot: int) -> None:
        """Reverse one logged mutation."""
        if kind == SEQUENCE_APPEND:
            self._sequences[slot].undo()
            return
        if kind == MAPPING_INSERT:
            self._mappings[slot].undo()
            return
        if kind == MAPPING_REPLACE:
            at, entry = self._overwritten.pop()
            self._mappings[slot].restore(at, entry)
            return
        raise UnsupportedConstructError(
            f"product state: unknown reversible mutation {kind}"
        )

    def _require_top(self, mark: ProductMark) -> None:
        """Refuse a transaction closed out of order — marks are LIFO."""
        if not self._marks or self._marks[-1] != mark:
            raise UnsupportedConstructError(
                "product state: transactions must close newest first"
            )
